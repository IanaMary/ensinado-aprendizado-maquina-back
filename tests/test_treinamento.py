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
