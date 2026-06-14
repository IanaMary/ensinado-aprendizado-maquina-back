import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId
import base64
import hashlib
import io
import joblib
import pandas as pd
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier


class TestMetricas:
    @pytest.mark.asyncio
    async def test_avaliar_modelos_modelo_inexistente(self, client, mock_db, auth_headers):
        mock_db["modelos"].find_one = AsyncMock(return_value=None)
        response = await client.post(
            "/classificador/avaliar_modelos",
            headers=auth_headers,
            json={
                "modelos": [{"label": "KNN", "id": str(ObjectId())}],
                "metricas": [{"label": "Acurácia", "valor": "accuracy_score"}],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "Acurácia" in data
        assert "Modelo não encontrado" in data["Acurácia"]["KNN"]

    @pytest.mark.asyncio
    async def test_avaliar_modelos_csv_multiclasse(self, client, mock_db, auth_headers):
        df = pd.DataFrame({
            "mass": [192, 180, 86, 84, 80, 178, 172, 154, 164, 152, 156, 156],
            "width": [8.4, 8.0, 6.2, 6.0, 5.8, 7.1, 7.4, 7.0, 7.3, 7.6, 7.7, 7.6],
            "height": [7.3, 6.8, 4.7, 4.6, 4.3, 7.8, 7.0, 7.1, 7.7, 7.3, 7.1, 7.5],
            "color_score": [0.55, 0.59, 0.80, 0.79, 0.77, 0.92, 0.89, 0.88, 0.70, 0.69, 0.69, 0.67],
            "fruit_name": [
                "apple", "apple", "mandarin", "mandarin", "mandarin", "orange",
                "orange", "orange", "lemon", "lemon", "lemon", "lemon",
            ],
        })
        atributos = ["mass", "width", "height", "color_score"]
        target = "fruit_name"

        model = KNeighborsClassifier(n_neighbors=1)
        model.fit(df[atributos], df[target])
        buffer = io.BytesIO()
        joblib.dump(model, buffer)
        model_bytes = buffer.getvalue()
        csv_b64 = base64.b64encode(df.to_csv(index=False).encode("utf-8")).decode("utf-8")

        modelo_id = ObjectId()
        arquivo_id = ObjectId()
        mock_db["modelos"].find_one = AsyncMock(return_value={
            "_id": modelo_id,
            "modelo_treinado": model_bytes,
            "checksum": hashlib.sha256(model_bytes).hexdigest(),
            "atributos": atributos,
            "target": target,
            "classes": list(model.classes_),
            "arquivo_id": str(arquivo_id),
        })
        mock_db["arquivos"].find_one = AsyncMock(return_value={
            "_id": arquivo_id,
            "content_teste_base64": csv_b64,
        })

        response = await client.post(
            "/classificador/avaliar_modelos",
            headers=auth_headers,
            json={
                "modelos": [{"label": "KNN", "id": str(modelo_id)}],
                "metricas": [
                    {"label": "Acurácia", "valor": "accuracy_score"},
                    {"label": "F1-Score", "valor": "f1_score", "average": "macro"},
                    {"label": "Matriz de Confusão", "valor": "confusion_matrix"},
                    {"label": "Precisão", "valor": "precision_score", "average": "micro"},
                    {"label": "Recall", "valor": "recall_score", "average": "weighted"},
                ],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["Acurácia"]["KNN"] == 1.0
        assert data["F1-Score"]["KNN"] == 1.0
        assert data["Precisão"]["KNN"] == 1.0
        assert data["Recall"]["KNN"] == 1.0
        assert data["Matriz de Confusão"]["KNN"]["classes"] == list(model.classes_)
        assert data["Matriz de Confusão"]["KNN"]["total"] == len(df)
        assert "_visualizacoes" in data
        assert "KNN" in data["_visualizacoes"]
        assert len(data["_visualizacoes"]["KNN"]) >= 3
        primeira_visualizacao = data["_visualizacoes"]["KNN"][0]
        assert primeira_visualizacao["mime"] == "image/png"
        assert len(base64.b64decode(primeira_visualizacao["base64"])) > 1000


    @pytest.mark.asyncio
    async def test_avaliar_modelos_dois_modelos(self, client, mock_db, auth_headers):
        """Dois modelos avaliados ao mesmo tempo: ambos aparecem na resposta."""
        df = pd.DataFrame({
            "mass": [192, 180, 86, 84, 80, 178, 172, 154, 164, 152, 156, 156],
            "width": [8.4, 8.0, 6.2, 6.0, 5.8, 7.1, 7.4, 7.0, 7.3, 7.6, 7.7, 7.6],
            "height": [7.3, 6.8, 4.7, 4.6, 4.3, 7.8, 7.0, 7.1, 7.7, 7.3, 7.1, 7.5],
            "color_score": [0.55, 0.59, 0.80, 0.79, 0.77, 0.92, 0.89, 0.88, 0.70, 0.69, 0.69, 0.67],
            "fruit_name": [
                "apple", "apple", "mandarin", "mandarin", "mandarin", "orange",
                "orange", "orange", "lemon", "lemon", "lemon", "lemon",
            ],
        })
        atributos = ["mass", "width", "height", "color_score"]
        target = "fruit_name"
        csv_b64 = base64.b64encode(df.to_csv(index=False).encode("utf-8")).decode("utf-8")
        arquivo_id = ObjectId()

        def _make_doc(model, model_id):
            buf = io.BytesIO()
            joblib.dump(model, buf)
            b = buf.getvalue()
            return {
                "_id": model_id,
                "modelo_treinado": b,
                "checksum": hashlib.sha256(b).hexdigest(),
                "atributos": atributos,
                "target": target,
                "classes": list(model.classes_),
                "arquivo_id": str(arquivo_id),
            }

        knn_id = ObjectId()
        dt_id = ObjectId()
        knn = KNeighborsClassifier(n_neighbors=1)
        knn.fit(df[atributos], df[target])
        dt = DecisionTreeClassifier(max_depth=3, random_state=0)
        dt.fit(df[atributos], df[target])

        modelos_map = {knn_id: _make_doc(knn, knn_id), dt_id: _make_doc(dt, dt_id)}

        async def find_modelo(query):
            return modelos_map.get(query["_id"])

        mock_db["modelos"].find_one = AsyncMock(side_effect=find_modelo)
        mock_db["arquivos"].find_one = AsyncMock(return_value={
            "_id": arquivo_id,
            "content_teste_base64": csv_b64,
        })

        response = await client.post(
            "/classificador/avaliar_modelos",
            headers=auth_headers,
            json={
                "modelos": [
                    {"label": "KNN", "id": str(knn_id)},
                    {"label": "Árvore", "id": str(dt_id)},
                ],
                "metricas": [
                    {"label": "Acurácia", "valor": "accuracy_score"},
                    {"label": "Matriz de Confusão", "valor": "confusion_matrix"},
                ],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "KNN" in data["Acurácia"]
        assert "Árvore" in data["Acurácia"]
        assert data["Acurácia"]["KNN"] == 1.0
        assert "KNN" in data["Matriz de Confusão"]
        assert "Árvore" in data["Matriz de Confusão"]
        assert "_visualizacoes" in data
        assert "KNN" in data["_visualizacoes"]
        assert "Árvore" in data["_visualizacoes"]


class TestConfiguracaoTreinamento:
    @pytest.mark.asyncio
    async def test_get_configuracao_inexistente(self, client, mock_db, auth_headers):
        mock_db["configuracoes"].find_one = AsyncMock(return_value=None)
        response = await client.get(
            f"/configurar_treinamento/xlxs/{str(ObjectId())}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_configuracao_sucesso(self, client, mock_db, auth_headers):
        oid = ObjectId()
        mock_db["configuracoes"].find_one = AsyncMock(return_value={
            "_id": oid,
            "id_coleta": str(ObjectId()),
            "target": "col1",
            "atributos": {"col2": True},
        })
        mock_db["arquivos"].find_one = AsyncMock(return_value={
            "_id": ObjectId(),
            "tipo": "csv",
            "content_treino_base64": "",
            "content_teste_base64": "",
            "colunas": {"col1": "Número", "col2": "Texto"},
            "colunas_detalhes": [],
        })
        response = await client.get(
            f"/configurar_treinamento/xlxs/{str(oid)}",
            headers=auth_headers,
        )
        assert response.status_code == 200


class TestConfPipeline:
    @pytest.mark.asyncio
    async def test_get_modelos_todos(self, client, mock_db, auth_headers):
        mock_db["configuracoes"].find = MagicMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=[])
        ))
        response = await client.get(
            "/conf_pipeline/modelos/todos",
            headers=auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_metricas_todos(self, client, mock_db, auth_headers):
        mock_db["configuracoes"].find = MagicMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=[])
        ))
        response = await client.get(
            "/conf_pipeline/metricas/todos",
            headers=auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_coleta_dados_todos(self, client, mock_db, auth_headers):
        mock_db["configuracoes"].find = MagicMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=[])
        ))
        response = await client.get(
            "/conf_pipeline/coleta_dados/todos",
            headers=auth_headers,
        )
        assert response.status_code == 200


class TestHealthcheck:
    @pytest.mark.asyncio
    async def test_healthcheck(self, client):
        with patch("app.main.client") as mock_client:
            mock_client.admin.command = AsyncMock(return_value=True)
            response = await client.get("/healthcheck")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
