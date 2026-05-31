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
            "tipo_target": "number",
        })
        mock_db["arquivos"].find_one = AsyncMock(return_value={
            "_id": coleta_id,
            "content_treino_base64": b64,
            "content_teste_base64": b64,
        })

        response = await client.post(
            "/classificador/treinamento/knn",
            headers=auth_headers,
            json={
                "id_coleta": str(coleta_id),
                "configuracao_id": str(config_id),
                "hiperparametros": {"n_neighbors": 3},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "modelo_id" in data
        assert data["tipo_modelo"] == "knn"
