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
    async def test_criar_turma_admin(self, client, mock_db, auth_headers):
        # Admin herda as capacidades de professor (exigir_admin_ou_professor).
        mock_db["usuarios"].find_one = AsyncMock(return_value={
            "_id": ObjectId(), "nome_usuario": "adm", "email": "a@a.com", "role": "admin"})
        with patch("app.routers.turmas.turmas", _turmas_mock()):
            r = await client.post("/turmas", headers=auth_headers, json={"nome": "Turma Admin"})
        assert r.status_code == 200
        assert r.json()["nome"] == "Turma Admin"

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


class TestExcluirTurmaEAlunos:
    """`DELETE /turmas/{id}` e `POST /turmas/{id}/alunos` não tinham teste.

    O delete faz **cascata**: `atividades.delete_many({"turma_id": ...})`. Se esse filtro estiver
    errado, apagar uma turma leva as atividades de OUTRAS turmas — perda de trabalho de professor,
    irrecuperável. E o `POST /alunos` ignora em silêncio um e-mail que não existe, o que é decisão de
    produto, mas precisa estar fixada para não virar defeito por acidente.
    """

    @pytest.mark.asyncio
    async def test_cascata_apaga_so_as_atividades_da_turma(self, client, mock_db, auth_headers):
        prof = _prof()
        turma = {"_id": ObjectId(), "professor_id": str(prof["_id"]), "nome": "Turma 1"}
        mock_db["usuarios"].find_one = AsyncMock(return_value=prof)
        ativ = MagicMock(delete_many=AsyncMock(return_value=MagicMock(deleted_count=3)))
        tur = MagicMock(find_one=AsyncMock(return_value=turma),
                        delete_one=AsyncMock(return_value=MagicMock(deleted_count=1)))

        with patch("app.routers.turmas.turmas", tur), \
             patch("app.routers.turmas.atividades", ativ):
            r = await client.delete(f"/turmas/{turma['_id']}", headers=auth_headers)

        assert r.status_code == 200
        # o filtro da cascata TEM de amarrar a turma; sem isso apaga atividade alheia
        assert ativ.delete_many.await_args[0][0] == {"turma_id": str(turma["_id"])}
        assert tur.delete_one.await_args[0][0] == {"_id": turma["_id"]}

    @pytest.mark.asyncio
    async def test_professor_nao_apaga_turma_de_outro(self, client, mock_db, auth_headers):
        """`_turma_do_professor` filtra por `professor_id`; turma de outro não existe para mim."""
        prof = _prof()
        mock_db["usuarios"].find_one = AsyncMock(return_value=prof)
        ativ = MagicMock(delete_many=AsyncMock())
        tur = MagicMock(find_one=AsyncMock(return_value=None), delete_one=AsyncMock())

        with patch("app.routers.turmas.turmas", tur), \
             patch("app.routers.turmas.atividades", ativ):
            r = await client.delete(f"/turmas/{ObjectId()}", headers=auth_headers)

        assert r.status_code == 404
        # nada foi apagado — nem a atividade, nem a turma
        assert ativ.delete_many.await_count == 0
        assert tur.delete_one.await_count == 0

    @pytest.mark.asyncio
    async def test_adicionar_aluno_por_email_e_ignorar_quem_nao_existe(
        self, client, mock_db, auth_headers,
    ):
        prof = _prof()
        turma = {"_id": ObjectId(), "professor_id": str(prof["_id"]), "alunos": []}
        aluno_id = ObjectId()

        async def find_one_usuario(filtro, *a, **k):
            # o professor (pelo token) e o aluno existente; o e-mail desconhecido não
            if filtro.get("email") == "existe@test.com":
                return {"_id": aluno_id, "email": "existe@test.com", "role": "aluno"}
            if filtro.get("email") == "naoexiste@test.com":
                return None
            return prof

        mock_db["usuarios"].find_one = AsyncMock(side_effect=find_one_usuario)
        tur = MagicMock(
            find_one=AsyncMock(return_value={**turma, "alunos": [str(aluno_id)]}),
            update_one=AsyncMock(return_value=MagicMock(matched_count=1)),
        )

        with patch("app.routers.turmas.turmas", tur):
            r = await client.post(
                f"/turmas/{turma['_id']}/alunos", headers=auth_headers,
                json={"alunos": ["existe@test.com", "naoexiste@test.com", "  "]})

        assert r.status_code == 200
        # só o que existe entra, e o `$addToSet` evita duplicar quem já está na turma
        gravado = tur.update_one.await_args[0][1]["$addToSet"]["alunos"]["$each"]
        assert gravado == [str(aluno_id)]
