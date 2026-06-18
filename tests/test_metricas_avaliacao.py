import pytest
from unittest.mock import AsyncMock
from bson import ObjectId
import base64
import hashlib
import io
import joblib
import pandas as pd
from sklearn.neighbors import KNeighborsClassifier
from sklearn.linear_model import LinearRegression


def _treinar_knn():
    df = pd.DataFrame({
        "f1": [1, 2, 3, 4, 5, 6],
        "f2": [6, 5, 4, 3, 2, 1],
        "alvo": ["a", "a", "a", "b", "b", "b"],
    })
    modelo = KNeighborsClassifier(n_neighbors=1)
    modelo.fit(df[["f1", "f2"]], df["alvo"])
    buffer = io.BytesIO()
    joblib.dump(modelo, buffer)
    return df, modelo, buffer.getvalue()


def _csv_b64(df):
    return base64.b64encode(df.to_csv(index=False).encode("utf-8")).decode("utf-8")


def _doc_modelo(model_bytes, df, **overrides):
    doc = {
        "_id": ObjectId(),
        "modelo_treinado": model_bytes,
        "checksum": hashlib.sha256(model_bytes).hexdigest(),
        "atributos": ["f1", "f2"],
        "target": "alvo",
        "classes": ["a", "b"],
        "arquivo_id": None,
        "arq_teste": _csv_b64(df),
    }
    doc.update(overrides)
    return doc


def _payload(modelo_id, metricas=None):
    return {
        "modelos": [{"label": "KNN", "id": str(modelo_id)}],
        "metricas": metricas or [{"label": "Acurácia", "valor": "accuracy_score"}],
    }


class TestAvaliarModelos:
    @pytest.mark.asyncio
    async def test_checksum_divergente_retorna_400(self, client, mock_db, auth_headers):
        df, _, model_bytes = _treinar_knn()
        doc = _doc_modelo(model_bytes, df, checksum="checksum-adulterado")
        mock_db["modelos"].find_one = AsyncMock(return_value=doc)

        response = await client.post(
            "/classificador/avaliar_modelos", headers=auth_headers, json=_payload(doc["_id"])
        )
        assert response.status_code == 400
        assert "integridade" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_prever_retorna_predicao(self, client, mock_db, auth_headers):
        """/prever: carrega o modelo e prevê um exemplo informado."""
        df, _, model_bytes = _treinar_knn()
        doc = _doc_modelo(model_bytes, df)
        mock_db["modelos"].find_one = AsyncMock(return_value=doc)

        response = await client.post(
            "/classificador/prever",
            headers=auth_headers,
            json={"modelo_id": str(doc["_id"]), "valores": {"f1": 1, "f2": 6}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["predicao"] == "a"  # (1,6) é vizinho exato de uma linha "a"

    @pytest.mark.asyncio
    async def test_prever_modelo_inexistente_404(self, client, mock_db, auth_headers):
        mock_db["modelos"].find_one = AsyncMock(return_value=None)
        response = await client.post(
            "/classificador/prever",
            headers=auth_headers,
            json={"modelo_id": str(ObjectId()), "valores": {"f1": 1, "f2": 6}},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_arquivo_teste_ausente_retorna_400(self, client, mock_db, auth_headers):
        df, _, model_bytes = _treinar_knn()
        doc = _doc_modelo(model_bytes, df, arq_teste=None)
        mock_db["modelos"].find_one = AsyncMock(return_value=doc)
        mock_db["arquivos"].find_one = AsyncMock(return_value=None)

        response = await client.post(
            "/classificador/avaliar_modelos", headers=auth_headers, json=_payload(doc["_id"])
        )
        assert response.status_code == 400
        assert "teste" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_arquivo_teste_muito_grande_retorna_413(self, client, mock_db, auth_headers):
        df, _, model_bytes = _treinar_knn()
        doc = _doc_modelo(model_bytes, df, arq_teste="A" * (50 * 1024 * 1024 + 1))
        mock_db["modelos"].find_one = AsyncMock(return_value=doc)

        response = await client.post(
            "/classificador/avaliar_modelos", headers=auth_headers, json=_payload(doc["_id"])
        )
        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_metrica_desconhecida(self, client, mock_db, auth_headers):
        df, _, model_bytes = _treinar_knn()
        doc = _doc_modelo(model_bytes, df)
        mock_db["modelos"].find_one = AsyncMock(return_value=doc)

        response = await client.post(
            "/classificador/avaliar_modelos",
            headers=auth_headers,
            json=_payload(doc["_id"], [{"label": "Inventada", "valor": "metrica_inexistente"}]),
        )
        assert response.status_code == 200
        assert response.json()["Inventada"]["KNN"] == "Métrica não suportada"

    @pytest.mark.asyncio
    async def test_doc_sem_classes_deriva_do_modelo(self, client, mock_db, auth_headers):
        """Regressão do except nu: doc sem 'classes' deriva os rótulos de modelo.classes_."""
        df, modelo, model_bytes = _treinar_knn()
        doc = _doc_modelo(model_bytes, df)
        del doc["classes"]
        mock_db["modelos"].find_one = AsyncMock(return_value=doc)

        response = await client.post(
            "/classificador/avaliar_modelos",
            headers=auth_headers,
            json=_payload(doc["_id"], [{"label": "Matriz", "valor": "confusion_matrix"}]),
        )
        assert response.status_code == 200
        assert response.json()["Matriz"]["KNN"]["classes"] == [str(c) for c in modelo.classes_]

    @pytest.mark.asyncio
    async def test_modelo_sem_classes_attr_nao_quebra(self, client, mock_db, auth_headers):
        """Regressão do except nu: estimador sem classes_ cai no fallback por AttributeError sem 500."""
        df = pd.DataFrame({"f1": [1, 2, 3, 4], "f2": [4, 3, 2, 1], "alvo": [0, 0, 1, 1]})
        modelo = LinearRegression()
        modelo.fit(df[["f1", "f2"]], df["alvo"])
        buffer = io.BytesIO()
        joblib.dump(modelo, buffer)
        model_bytes = buffer.getvalue()

        doc = _doc_modelo(model_bytes, df)
        del doc["classes"]
        mock_db["modelos"].find_one = AsyncMock(return_value=doc)

        response = await client.post(
            "/classificador/avaliar_modelos", headers=auth_headers, json=_payload(doc["_id"])
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_avaliar_regressao_calcula_metricas(self, client, mock_db, auth_headers):
        """Modelo de regressão calcula R²/MSE/RMSE/MAE, ignora métricas de classificação e gera visualizações."""
        df = pd.DataFrame({
            "f1": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "f2": [2.0, 4.0, 6.0, 8.0, 10.0, 12.0],
            "alvo": [3.0, 5.0, 7.0, 9.0, 11.0, 13.0],
        })
        modelo = LinearRegression().fit(df[["f1", "f2"]], df["alvo"])
        buffer = io.BytesIO()
        joblib.dump(modelo, buffer)
        model_bytes = buffer.getvalue()

        doc = _doc_modelo(model_bytes, df, classes=[])
        mock_db["modelos"].find_one = AsyncMock(return_value=doc)

        metricas = [
            {"label": "R²", "valor": "r2_score"},
            {"label": "MSE", "valor": "mean_squared_error"},
            {"label": "RMSE", "valor": "root_mean_squared_error"},
            {"label": "MAE", "valor": "mean_absolute_error"},
            {"label": "Acurácia", "valor": "accuracy_score"},
        ]
        response = await client.post(
            "/classificador/avaliar_modelos",
            headers=auth_headers,
            json={"modelos": [{"label": "Regressão Linear", "id": str(doc["_id"])}], "metricas": metricas},
        )
        assert response.status_code == 200
        data = response.json()
        for label in ["R²", "MSE", "RMSE", "MAE"]:
            assert isinstance(data[label]["Regressão Linear"], float)
        assert data["Acurácia"]["Regressão Linear"] == "N/A para regressão"
        assert len(data["_visualizacoes"]["Regressão Linear"]) >= 1

    @pytest.mark.asyncio
    async def test_resultado_json_nativo(self, client, mock_db, auth_headers):
        """Regressão converter_numpy: valores retornados devem ser tipos JSON nativos."""
        df, _, model_bytes = _treinar_knn()
        doc = _doc_modelo(model_bytes, df)
        mock_db["modelos"].find_one = AsyncMock(return_value=doc)

        response = await client.post(
            "/classificador/avaliar_modelos",
            headers=auth_headers,
            json=_payload(doc["_id"], [
                {"label": "Acurácia", "valor": "accuracy_score"},
                {"label": "Matriz", "valor": "confusion_matrix"},
            ]),
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["Acurácia"]["KNN"], float)
        matriz = data["Matriz"]["KNN"]
        assert isinstance(matriz["total"], int)
        assert all(isinstance(v, int) for linha in matriz["matriz"] for v in linha)
