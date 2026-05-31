import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId


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
            "colunas": {"col1": "number", "col2": "string"},
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
