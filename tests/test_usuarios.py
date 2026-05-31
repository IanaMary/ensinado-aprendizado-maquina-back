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
