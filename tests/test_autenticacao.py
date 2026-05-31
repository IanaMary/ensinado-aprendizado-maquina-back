import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_credenciais_invalidas(self, client, mock_db):
        mock_db["usuarios"].find_one = AsyncMock(return_value=None)
        response = await client.post("/login", json={"email": "x@x.com", "senha": "123"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_senha_incorreta(self, client, mock_db):
        from app.security import get_senha_hash
        user = {
            "_id": ObjectId(),
            "email": "test@test.com",
            "senha": get_senha_hash("senha_correta"),
            "nome_usuario": "test",
            "role": "aluno",
        }
        mock_db["usuarios"].find_one = AsyncMock(return_value=user)
        response = await client.post("/login", json={"email": "test@test.com", "senha": "senha_errada"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_sucesso(self, client, mock_db):
        from app.security import get_senha_hash
        user = {
            "_id": ObjectId(),
            "email": "test@test.com",
            "senha": get_senha_hash("senha123"),
            "nome_usuario": "test",
            "role": "aluno",
        }
        mock_db["usuarios"].find_one = AsyncMock(return_value=user)
        response = await client.post("/login", json={"email": "test@test.com", "senha": "senha123"})
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["usuario"]["email"] == "test@test.com"


class TestRotaProtegida:
    @pytest.mark.asyncio
    async def test_rota_protegida_sem_token(self, client):
        response = await client.get("/tutor/?pipe=inicio")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_rota_protegida_token_invalido(self, client):
        response = await client.get(
            "/tutor/?pipe=inicio",
            headers={"Authorization": "Bearer token-invalido"}
        )
        assert response.status_code == 401
