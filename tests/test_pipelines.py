import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId


def _mock_pipeline_find(return_value=None):
    to_list = AsyncMock(return_value=return_value or [])
    m = MagicMock()
    m.to_list = to_list
    return m


class TestPipelines:
    @pytest.mark.asyncio
    async def test_criar_pipeline(self, client, mock_db, auth_headers):
        mock_db["modelos"].aggregate = MagicMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=[])
        ))
        response = await client.post(
            "/pipelines/",
            headers=auth_headers,
            json={
                "nome": "Pipeline Teste",
                "descricao": "Teste de criacao",
                "status": "rascunho",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] is not None
        assert data["nome"] == "Pipeline Teste"
        assert data["status"] == "rascunho"

    @pytest.mark.asyncio
    async def test_listar_pipelines_vazio(self, client, mock_db, auth_headers):
        mock_db["modelos"].aggregate = MagicMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=[])
        ))
        mock_db["tutor"].find_one = AsyncMock(return_value=None)
        mock_db["tutor"].aggregate = MagicMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=[])
        ))
        mock_db["pipelines"].find = MagicMock(return_value=MagicMock(
            sort=MagicMock(return_value=_mock_pipeline_find([]))
        ))

        response = await client.get("/pipelines/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_pipeline_nao_encontrado(self, client, mock_db, auth_headers):
        mock_db["modelos"].aggregate = MagicMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=[])
        ))
        mock_db["tutor"].find_one = AsyncMock(return_value=None)
        mock_db["tutor"].aggregate = MagicMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=[])
        ))
        mock_db["pipelines"].find_one = AsyncMock(return_value=None)

        oid = str(ObjectId())
        response = await client.get(f"/pipelines/{oid}", headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_nao_copia_pipeline_privado_de_outro_usuario(self, client, mock_db, auth_headers):
        oid = ObjectId()
        mock_db["pipelines"].find_one = AsyncMock(return_value={
            "_id": oid,
            "user_id": str(ObjectId()),
            "nome": "Privado",
            "is_public": False,
        })

        response = await client.post(f"/pipelines/{oid}/copiar", headers=auth_headers)
        assert response.status_code == 404
        mock_db["pipelines"].insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_copia_pipeline_publico_de_outro_usuario(self, client, mock_db, auth_headers):
        oid = ObjectId()
        mock_db["pipelines"].find_one = AsyncMock(return_value={
            "_id": oid,
            "user_id": str(ObjectId()),
            "nome": "Publico",
            "is_public": True,
        })

        response = await client.post(f"/pipelines/{oid}/copiar", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["nome"] == "Cópia de Publico"

    @pytest.mark.asyncio
    async def test_copia_pipeline_do_proprio_usuario(self, client, mock_db, auth_headers, mock_user):
        oid = ObjectId()
        mock_db["pipelines"].find_one = AsyncMock(return_value={
            "_id": oid,
            "user_id": str(mock_user["_id"]),
            "nome": "Meu pipeline",
            "is_public": False,
        })

        response = await client.post(f"/pipelines/{oid}/copiar", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["nome"] == "Cópia de Meu pipeline"

    @pytest.mark.asyncio
    async def test_galeria(self, client, mock_db, auth_headers):
        response = await client.get("/pipelines/galeria", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []
