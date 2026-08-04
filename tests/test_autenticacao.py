import pytest
from unittest.mock import AsyncMock
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


class TestRenovacaoDeSessao:
    """O token não era renovado: o aluno caía no meio da atividade (Imagem 10). A duração vem de
    `TOKEN_EXPIRE_MINUTES` (240 min desde 04/08); estes testes não dependem do valor."""

    @pytest.mark.asyncio
    async def test_renova_com_token_valido(self, client, mock_db, auth_headers):
        r = await client.post("/login/renovar", headers=auth_headers)
        assert r.status_code == 200
        novo = r.json()["access_token"]
        assert novo and r.json()["token_type"] == "bearer"

        # O token novo vale de verdade e aponta para o mesmo usuário.
        import jwt
        from app.security import SECRET_KEY, ALGORITHM
        atual = jwt.decode(auth_headers["Authorization"].split()[1], SECRET_KEY,
                           algorithms=[ALGORITHM], options={"verify_exp": False})
        renovado = jwt.decode(novo, SECRET_KEY, algorithms=[ALGORITHM])
        assert renovado["sub"] == atual["sub"]
        # Expira no futuro, pela regra do login. (Não comparo com o `exp` do fixture: ele usa uma
        # data artificial lá no ano 2286, então a comparação não diria nada.)
        from datetime import datetime, timezone
        assert renovado["exp"] > datetime.now(timezone.utc).timestamp()

    @pytest.mark.asyncio
    async def test_sem_token_recusa(self, client, mock_db):
        r = await client.post("/login/renovar")
        assert r.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_token_expirado_nao_renova(self, client, mock_db):
        # A renovação exige um access token AINDA válido — senão seria um refresh token, e um
        # token vazado se manteria vivo para sempre.
        import jwt
        from datetime import datetime, timedelta, timezone
        from app.security import SECRET_KEY, ALGORITHM
        vencido = jwt.encode(
            {"sub": "teste@teste.com", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
            SECRET_KEY, algorithm=ALGORITHM,
        )
        r = await client.post("/login/renovar", headers={"Authorization": f"Bearer {vencido}"})
        assert r.status_code == 401
