import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId


def _prof():
    return {"_id": ObjectId(), "nome_usuario": "prof", "email": "test@test.com", "role": "professor"}


def _turmas_mock(find_one_ret=None):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one_ret)
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    return col


class TestTurmas:
    @pytest.mark.asyncio
    async def test_criar_turma_professor(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value=_prof())
        with patch("app.routers.turmas.turmas", _turmas_mock()):
            r = await client.post("/turmas", headers=auth_headers, json={"nome": "Turma 1A"})
        assert r.status_code == 200
        body = r.json()
        assert body["nome"] == "Turma 1A"
        assert len(body["codigo"]) >= 6
        assert body["total_alunos"] == 0

    @pytest.mark.asyncio
    async def test_criar_turma_aluno_403(self, client, mock_db, auth_headers):
        # usuário padrão do mock tem role "aluno"
        r = await client.post("/turmas", headers=auth_headers, json={"nome": "Turma"})
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_entrar_turma_codigo_invalido_404(self, client, mock_db, auth_headers):
        with patch("app.routers.turmas.turmas", _turmas_mock(find_one_ret=None)):
            r = await client.post("/turmas/entrar", headers=auth_headers, json={"codigo": "ZZZZZZ"})
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_entrar_turma_ok(self, client, mock_db, auth_headers):
        turma = {"_id": ObjectId(), "nome": "1A", "codigo": "ABC234", "professor_id": str(ObjectId()), "alunos": []}
        with patch("app.routers.turmas.turmas", _turmas_mock(find_one_ret=turma)):
            r = await client.post("/turmas/entrar", headers=auth_headers, json={"codigo": "abc234"})
        assert r.status_code == 200
        assert r.json()["nome"] == "1A"
