import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
import pandas as pd
import io
import base64
import joblib
from sklearn.neighbors import KNeighborsClassifier


class TestTreinamentoBase:
    @pytest.mark.asyncio
    async def test_treinar_knn(self, client, mock_db, auth_headers):
        df = pd.DataFrame({"f1": [1, 2, 3, 4, 5], "f2": [5, 4, 3, 2, 1], "target": [0, 0, 0, 1, 1]})
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        b64 = base64.b64encode(buffer.getvalue()).decode()

        coleta_id = ObjectId()
        config_id = ObjectId()

        mock_db["configuracoes"].find_one = AsyncMock(return_value={
            "_id": config_id,
            "id_coleta": str(coleta_id),
            "target": "target",
            "atributos": {"f1": True, "f2": True},
            "tipo_target": "Número",
        })
        mock_db["arquivos"].find_one = AsyncMock(return_value={
            "_id": coleta_id,
            "content_treino_base64": b64,
            "content_teste_base64": b64,
        })
        mock_db["modelos"].find_one = AsyncMock(return_value={
            "_id": ObjectId(),
            "valor": "knn",
            "hiperparametros": [
                {"nomeHiperparametro": "n_neighbors", "valorPadrao": 5}
            ]
        })

        response = await client.post(
            "/classificador/treinamento/knn",
            headers=auth_headers,
            json={
                "arquivo_id": str(coleta_id),
                "tipo_arquivo": "excel",
                "configuracao_id": str(config_id),
                "modelo_id": str(ObjectId()),  # Mock modelo_id
                "hiperparametros": {"n_neighbors": 3},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["modelo"] == "knn"
        # Hiperparametro enviado pelo usuario deve ser aplicado (sobrepoe o padrao do seed).
        assert data["hiperparametros"]["n_neighbors"] == 3


def _montar_mocks_treinamento(mock_db, df):
    """Prepara os mocks de coleta/config/modelo para um treino de KNN com o df dado."""
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    b64 = base64.b64encode(buffer.getvalue()).decode()

    coleta_id = ObjectId()
    config_id = ObjectId()
    atributos = {c: True for c in df.columns if c != "target"}

    mock_db["configuracoes"].find_one = AsyncMock(return_value={
        "_id": config_id,
        "id_coleta": str(coleta_id),
        "target": "target",
        "atributos": atributos,
        "tipo_target": "Número",
    })
    mock_db["arquivos"].find_one = AsyncMock(return_value={
        "_id": coleta_id,
        "content_treino_base64": b64,
        "content_teste_base64": b64,
    })
    mock_db["modelos"].find_one = AsyncMock(return_value={
        "_id": ObjectId(),
        "valor": "knn",
        "hiperparametros": [{"nomeHiperparametro": "n_neighbors", "valorPadrao": 1}],
    })
    return coleta_id, config_id


def _payload_knn(coleta_id, config_id):
    return {
        "arquivo_id": str(coleta_id),
        "tipo_arquivo": "excel",
        "configuracao_id": str(config_id),
        "modelo_id": str(ObjectId()),
        "hiperparametros": {"n_neighbors": 1},
    }


def _montar_mocks_modelo(mock_db, df, valor, hiperparametros):
    """Mocks de coleta/config/modelo para treinar `valor` com o df e hiperparametros dados."""
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    b64 = base64.b64encode(buffer.getvalue()).decode()
    coleta_id = ObjectId()
    config_id = ObjectId()
    atributos = {c: True for c in df.columns if c != "target"}
    mock_db["configuracoes"].find_one = AsyncMock(return_value={
        "_id": config_id,
        "id_coleta": str(coleta_id),
        "target": "target",
        "atributos": atributos,
        "tipo_target": "Número",
    })
    mock_db["arquivos"].find_one = AsyncMock(return_value={
        "_id": coleta_id,
        "content_treino_base64": b64,
        "content_teste_base64": b64,
    })
    mock_db["modelos"].find_one = AsyncMock(return_value={
        "_id": ObjectId(),
        "valor": valor,
        "hiperparametros": hiperparametros,
    })
    return coleta_id, config_id


class TestNovosEstimadores:
    @pytest.mark.asyncio
    async def test_treinar_ridge(self, client, mock_db, auth_headers):
        # target continuo => regressao
        df = pd.DataFrame({"f1": [1, 2, 3, 4, 5, 6], "f2": [2, 1, 4, 3, 6, 5], "target": [1.1, 2.2, 3.0, 4.4, 5.1, 6.3]})
        coleta_id, config_id = _montar_mocks_modelo(
            mock_db, df, "ridge",
            [{"nomeHiperparametro": "alpha", "valorPadrao": 1.0}, {"nomeHiperparametro": "fit_intercept", "valorPadrao": True}],
        )
        response = await client.post(
            "/classificador/treinamento/ridge",
            headers=auth_headers,
            json={"arquivo_id": str(coleta_id), "tipo_arquivo": "excel", "configuracao_id": str(config_id),
                  "modelo_id": str(ObjectId()), "hiperparametros": {"alpha": 0.5}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["modelo"] == "ridge"
        assert data["hiperparametros"]["alpha"] == 0.5

    @pytest.mark.asyncio
    async def test_treinar_regressao_polinomial(self, client, mock_db, auth_headers):
        df = pd.DataFrame({"f1": [1, 2, 3, 4, 5, 6], "target": [1.0, 4.0, 9.0, 16.0, 25.0, 36.0]})
        coleta_id, config_id = _montar_mocks_modelo(
            mock_db, df, "regressao_polinomial",
            [{"nomeHiperparametro": "degree", "valorPadrao": 2}],
        )
        response = await client.post(
            "/classificador/treinamento/regressao_polinomial",
            headers=auth_headers,
            json={"arquivo_id": str(coleta_id), "tipo_arquivo": "excel", "configuracao_id": str(config_id),
                  "modelo_id": str(ObjectId()), "hiperparametros": {"degree": 3}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["modelo"] == "regressao_polinomial"
        assert data["hiperparametros"]["degree"] == 3

    @pytest.mark.asyncio
    async def test_treinar_sgd(self, client, mock_db, auth_headers):
        df = pd.DataFrame({"f1": [1, 2, 3, 4, 5, 6], "f2": [6, 5, 4, 3, 2, 1], "target": [0, 0, 0, 1, 1, 1]})
        coleta_id, config_id = _montar_mocks_modelo(
            mock_db, df, "sgd",
            [{"nomeHiperparametro": "loss", "valorPadrao": "hinge"}, {"nomeHiperparametro": "max_iter", "valorPadrao": 1000}],
        )
        response = await client.post(
            "/classificador/treinamento/sgd",
            headers=auth_headers,
            json={"arquivo_id": str(coleta_id), "tipo_arquivo": "excel", "configuracao_id": str(config_id),
                  "modelo_id": str(ObjectId()), "hiperparametros": {"max_iter": 500}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["modelo"] == "sgd"
        assert data["hiperparametros"]["max_iter"] == 500


class TestValidacaoDadosTreino:
    @pytest.mark.asyncio
    async def test_arquivo_muito_grande_retorna_413(self, client, mock_db, auth_headers):
        df = pd.DataFrame({"f1": [1, 2], "target": [0, 1]})
        coleta_id, config_id = _montar_mocks_treinamento(mock_db, df)
        mock_db["arquivos"].find_one = AsyncMock(return_value={
            "_id": coleta_id,
            "content_treino_base64": "A" * (50 * 1024 * 1024 + 1),
        })

        response = await client.post(
            "/classificador/treinamento/knn",
            headers=auth_headers,
            json=_payload_knn(coleta_id, config_id),
        )
        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_dados_com_nan_retorna_400(self, client, mock_db, auth_headers):
        df = pd.DataFrame({"f1": [1, None, 3, 4], "target": [0, 0, 1, 1]})
        coleta_id, config_id = _montar_mocks_treinamento(mock_db, df)

        response = await client.post(
            "/classificador/treinamento/knn",
            headers=auth_headers,
            json=_payload_knn(coleta_id, config_id),
        )
        assert response.status_code == 400
        assert "ausentes" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_target_classe_unica_retorna_400(self, client, mock_db, auth_headers):
        df = pd.DataFrame({"f1": [1, 2, 3, 4], "target": [1, 1, 1, 1]})
        coleta_id, config_id = _montar_mocks_treinamento(mock_db, df)

        response = await client.post(
            "/classificador/treinamento/knn",
            headers=auth_headers,
            json=_payload_knn(coleta_id, config_id),
        )
        assert response.status_code == 400
        assert "duas classes" in response.json()["detail"]
