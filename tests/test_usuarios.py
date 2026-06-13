import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId


class TestCriarUsuario:
    @pytest.mark.asyncio
    async def test_criar_usuario_sucesso(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(side_effect=[
            {"_id": ObjectId(), "email": "test@test.com", "role": "aluno"},  # auth check
            None,  # duplicate check
        ])
        response = await client.post("/usuario/", headers=auth_headers, json={
            "nome_usuario": "novo",
            "email": "novo@test.com",
            "senha": "senha123",
            "instituicao_ensino": "Teste",
            "role": "aluno",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "novo@test.com"

    @pytest.mark.asyncio
    async def test_criar_usuario_email_duplicado(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(side_effect=[
            {"_id": ObjectId(), "email": "test@test.com", "role": "aluno"},  # auth check
            {"email": "existente@test.com"},  # duplicate check
        ])
        response = await client.post("/usuario/", headers=auth_headers, json={
            "nome_usuario": "novo",
            "email": "existente@test.com",
            "senha": "senha123",
            "instituicao_ensino": "Teste",
            "role": "aluno",
        })
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_criar_professor_sem_verificador(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(side_effect=[
            {"_id": ObjectId(), "email": "test@test.com", "role": "admin"},  # auth check
            None,  # duplicate check
        ])
        mock_db["verificadores"].find_one = AsyncMock(return_value=None)
        response = await client.post("/usuario/", headers=auth_headers, json={
            "nome_usuario": "prof",
            "email": "prof@test.com",
            "senha": "senha123",
            "instituicao_ensino": "Teste",
            "role": "professor",
            "verificador": "codigo-invalido",
        })
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_criar_professor_com_verificador(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(side_effect=[
            {"_id": ObjectId(), "email": "test@test.com", "role": "admin"},  # auth check
            None,  # duplicate check
        ])
        mock_db["verificadores"].find_one = AsyncMock(return_value={
            "_id": ObjectId(),
            "codigo": "valid-code",
            "usado": False,
        })
        response = await client.post("/usuario/", headers=auth_headers, json={
            "nome_usuario": "prof",
            "email": "prof@test.com",
            "senha": "senha123",
            "instituicao_ensino": "Teste",
            "role": "professor",
            "verificador": "valid-code",
        })
        assert response.status_code == 200


class TestConviteEmail:
    @pytest.mark.asyncio
    async def test_convite_com_smtp_ok(self, client, mock_db, auth_headers):
        """O envio SMTP roda via asyncio.to_thread; sucesso → email_enviado=True."""
        mock_db["usuarios"].find_one = AsyncMock(side_effect=[
            {"_id": ObjectId(), "email": "admin@test.com", "role": "admin", "nome_usuario": "admin"},  # auth
            None,  # duplicate check
        ])
        smtp_mock = MagicMock()
        with patch("app.routers.usuarios.SMTP_USER", "user"), \
             patch("app.routers.usuarios.SMTP_PASSWORD", "pass"), \
             patch("app.routers.usuarios._enviar_smtp", smtp_mock):
            response = await client.post("/usuario/convite", headers=auth_headers, json={
                "nome": "Novo Aluno",
                "email": "aluno@test.com",
                "tipo": "aluno",
            })
        assert response.status_code == 200
        data = response.json()
        assert data["email_enviado"] is True
        assert data["link_convite"] is None
        smtp_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_convite_com_falha_smtp_retorna_link(self, client, mock_db, auth_headers):
        """Regressão: falha no SMTP não derruba o endpoint; retorna link_convite manual."""
        mock_db["usuarios"].find_one = AsyncMock(side_effect=[
            {"_id": ObjectId(), "email": "admin@test.com", "role": "admin", "nome_usuario": "admin"},  # auth
            None,  # duplicate check
        ])
        with patch("app.routers.usuarios.SMTP_USER", "user"), \
             patch("app.routers.usuarios.SMTP_PASSWORD", "pass"), \
             patch("app.routers.usuarios._enviar_smtp", MagicMock(side_effect=ConnectionError("smtp down"))):
            response = await client.post("/usuario/convite", headers=auth_headers, json={
                "nome": "Novo Aluno",
                "email": "aluno@test.com",
                "tipo": "aluno",
            })
        assert response.status_code == 200
        data = response.json()
        assert data["email_enviado"] is False
        assert data["link_convite"] is not None

    @pytest.mark.asyncio
    async def test_convite_nao_admin_retorna_403(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value={
            "_id": ObjectId(), "email": "aluno@test.com", "role": "aluno", "nome_usuario": "aluno",
        })
        response = await client.post("/usuario/convite", headers=auth_headers, json={
            "nome": "X", "email": "x@test.com", "tipo": "aluno",
        })
        assert response.status_code == 403


class TestGerenciarUsuarios:
    @pytest.mark.asyncio
    async def test_alterar_status_usuario_inexistente_retorna_404(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value={
            "_id": ObjectId(),
            "email": "admin@test.com",
            "role": "admin",
        })
        mock_db["usuarios"].update_one = AsyncMock(return_value=MagicMock(matched_count=0, modified_count=0))

        response = await client.put(f"/usuario/{ObjectId()}/status?novo_status=ativo", headers=auth_headers)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_alterar_status_usuario_id_invalido_retorna_400(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value={
            "_id": ObjectId(),
            "email": "admin@test.com",
            "role": "admin",
        })

        response = await client.put("/usuario/id-invalido/status?novo_status=ativo", headers=auth_headers)

        assert response.status_code == 400
