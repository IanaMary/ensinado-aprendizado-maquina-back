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


class TestRateLimit:
    @pytest.mark.asyncio
    async def test_login_bloqueia_apos_20_tentativas(self, client, mock_db):
        """Regressão: a 21ª tentativa do mesmo IP em 1 minuto deve receber 429."""
        from app.routers.login import _request_log
        _request_log.clear()
        try:
            mock_db["usuarios"].find_one = AsyncMock(return_value=None)
            for _ in range(20):
                response = await client.post("/login", json={"email": "x@x.com", "senha": "123"})
                assert response.status_code == 401

            response = await client.post("/login", json={"email": "x@x.com", "senha": "123"})
            assert response.status_code == 429
        finally:
            _request_log.clear()


class TestAutorizacaoPorPapel:
    @pytest.mark.asyncio
    async def test_aluno_nao_gera_verificador(self, client, mock_db):
        mock_db["usuarios"].find_one = AsyncMock(return_value={
            "_id": ObjectId(), "email": "test@test.com", "role": "aluno", "nome_usuario": "aluno",
        })
        import jwt as pyjwt
        import os
        token = pyjwt.encode({"sub": "test@test.com", "exp": 9999999999}, os.environ["SECRET_KEY"], algorithm="HS256")
        response = await client.post("/usuario/gerar-verificador", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_gera_verificador(self, client, mock_db):
        mock_db["usuarios"].find_one = AsyncMock(return_value={
            "_id": ObjectId(), "email": "admin@test.com", "role": "admin", "nome_usuario": "admin",
        })
        import jwt as pyjwt
        import os
        token = pyjwt.encode({"sub": "admin@test.com", "exp": 9999999999}, os.environ["SECRET_KEY"], algorithm="HS256")
        response = await client.post("/usuario/gerar-verificador", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert "verificador" in response.json()


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
