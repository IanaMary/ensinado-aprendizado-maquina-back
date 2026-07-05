"""Testes das correções do subsistema Turmas (revisão de código).

Cobre: ranking por rótulo da métrica + melhor-por-aluno, _valor_metrica,
progresso escopado à turma, validação de aluno_id, gate de chat por vínculo de
turma e enforcement server-side de is_public/atividade_id nos pipelines.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from app.routers.turmas import _valor_metrica


class AsyncCursor:
    """Cursor Mongo assíncrono simples (suporta `async for`, to_list, sort/limit)."""
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        self._it = iter(self._items)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration

    async def to_list(self, length=None):
        return list(self._items)

    def sort(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self


def _prof(pid=None):
    return {"_id": ObjectId(pid) if pid else ObjectId(), "nome_usuario": "prof",
            "email": "test@test.com", "role": "professor"}


def _admin():
    return {"_id": ObjectId(), "nome_usuario": "adm", "email": "a@a.com", "role": "admin"}


# --------------------------------------------------------------- unit: _valor_metrica
class TestValorMetrica:
    def test_le_por_rotulo_quando_slug_ausente(self):
        # dict indexado pelo RÓTULO ('Acurácia'); busca por slug deve cair no rótulo.
        resultados = {"Acurácia": {"Árvore": 0.8, "KNN": 0.95}}
        assert _valor_metrica(resultados, ["accuracy_score", "Acurácia"], "desc") == 0.95

    def test_asc_pega_menor(self):
        resultados = {"MAE": {"m1": 3.0, "m2": 1.5}}
        assert _valor_metrica(resultados, ["mean_absolute_error", "MAE"], "asc") == 1.5

    def test_ignora_nao_escalar_e_bool(self):
        resultados = {"Acurácia": {"m1": "Erro: x", "m2": True, "m3": 0.7}}
        assert _valor_metrica(resultados, ["Acurácia"], "desc") == 0.7

    def test_sem_valor_retorna_none(self):
        assert _valor_metrica({}, ["accuracy_score", "Acurácia"], "desc") is None
        assert _valor_metrica({"Acurácia": {"m": "N/A"}}, ["Acurácia"], "desc") is None


# --------------------------------------------------------------- integração: ranking
class TestRanking:
    @pytest.mark.asyncio
    async def test_resolve_rotulo_e_melhor_por_aluno(self, client, mock_db, auth_headers):
        prof = _prof()
        mock_db["usuarios"].find_one = AsyncMock(return_value=prof)
        turma = {"_id": ObjectId(), "professor_id": str(prof["_id"]), "alunos": []}
        atividade = {"_id": ObjectId(), "turma_id": str(turma["_id"]),
                     "criterio": {"metrica": "accuracy_score", "ordem": "desc"}}
        aluno = str(ObjectId())
        # duas submissões do MESMO aluno; dict keyed por 'Acurácia' (rótulo real)
        pipes = [
            {"_id": ObjectId(), "user_id": aluno, "nome": "p1",
             "resultadosDasAvaliacoes": {"Acurácia": {"Árvore": 0.80}}},
            {"_id": ObjectId(), "user_id": aluno, "nome": "p2",
             "resultadosDasAvaliacoes": {"Acurácia": {"Árvore": 0.95}}},
        ]
        turmas_m = MagicMock(find_one=AsyncMock(return_value=turma))
        ativ_m = MagicMock(find_one=AsyncMock(return_value=atividade))
        metr_m = MagicMock(find_one=AsyncMock(return_value={"valor": "accuracy_score", "label": "Acurácia"}))
        pipe_m = MagicMock(find=MagicMock(return_value=AsyncCursor(pipes)))
        user_m = MagicMock(find=MagicMock(return_value=AsyncCursor(
            [{"_id": ObjectId(aluno), "nome_usuario": "Aluno X"}])))

        with patch("app.routers.turmas.turmas", turmas_m), \
             patch("app.routers.turmas.atividades", ativ_m), \
             patch("app.routers.turmas.opcoes_metricas", metr_m), \
             patch("app.routers.turmas.pipelines", pipe_m), \
             patch("app.routers.turmas.colecao_usuario", user_m):
            r = await client.get(
                f"/turmas/{turma['_id']}/atividades/{atividade['_id']}/ranking",
                headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        # antes da correção: ranking vazio (buscava por 'accuracy_score')
        assert len(body["ranking"]) == 1                      # dedup por aluno
        assert body["ranking"][0]["valor"] == 0.95            # melhor submissão
        assert body["ranking"][0]["aluno_nome"] == "Aluno X"


# --------------------------------------------------------------- remover_aluno: id inválido
class TestRemoverAluno:
    @pytest.mark.asyncio
    async def test_id_invalido_retorna_400(self, client, mock_db, auth_headers):
        prof = _prof()
        mock_db["usuarios"].find_one = AsyncMock(return_value=prof)
        turma = {"_id": ObjectId(), "professor_id": str(prof["_id"]), "alunos": []}
        turmas_m = MagicMock(find_one=AsyncMock(return_value=turma),
                             update_one=AsyncMock())
        with patch("app.routers.turmas.turmas", turmas_m):
            r = await client.delete(f"/turmas/{turma['_id']}/alunos/nao-e-objectid",
                                    headers=auth_headers)
        assert r.status_code == 400
        turmas_m.update_one.assert_not_called()


# --------------------------------------------------------------- admin: supervisão global
class TestAdminSupervisao:
    @pytest.mark.asyncio
    async def test_admin_lista_todas_as_turmas(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value=_admin())
        todas = [
            {"_id": ObjectId(), "nome": "T1", "professor_id": str(ObjectId()), "alunos": []},
            {"_id": ObjectId(), "nome": "T2", "professor_id": str(ObjectId()), "alunos": []},
        ]
        turmas_m = MagicMock(find=MagicMock(return_value=AsyncCursor(todas)))
        with patch("app.routers.turmas.turmas", turmas_m):
            r = await client.get("/turmas", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) == 2                       # vê turmas de vários professores
        assert turmas_m.find.call_args[0][0] == {}      # filtro vazio = TODAS

    @pytest.mark.asyncio
    async def test_admin_gerencia_turma_de_outro_professor(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value=_admin())
        turma = {"_id": ObjectId(), "nome": "T", "professor_id": str(ObjectId()), "alunos": []}  # dono é outro
        turmas_m = MagicMock(find_one=AsyncMock(return_value=turma), update_one=AsyncMock())
        with patch("app.routers.turmas.turmas", turmas_m):
            r = await client.put(f"/turmas/{turma['_id']}", headers=auth_headers, json={"nome": "Novo"})
        assert r.status_code == 200
        # filtro do find_one NÃO restringe por professor_id (admin passa em qualquer turma)
        assert "professor_id" not in turmas_m.find_one.call_args[0][0]

    @pytest.mark.asyncio
    async def test_professor_nao_ve_turma_alheia(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value=_prof())
        # find_one com filtro incluindo professor_id (do outro) → None → 404
        turmas_m = MagicMock(find_one=AsyncMock(return_value=None), update_one=AsyncMock())
        with patch("app.routers.turmas.turmas", turmas_m):
            r = await client.put(f"/turmas/{ObjectId()}", headers=auth_headers, json={"nome": "X"})
        assert r.status_code == 404
        assert "professor_id" in turmas_m.find_one.call_args[0][0]  # professor É restringido


# --------------------------------------------------------------- pipelines: is_public gate
class TestPublicarGate:
    @pytest.mark.asyncio
    async def test_aluno_nao_publica(self, client, mock_db, auth_headers):
        # usuário padrão do mock = aluno; is_public deve ser forçado a False.
        pipe_m = MagicMock(insert_one=AsyncMock(return_value=MagicMock(inserted_id=ObjectId())))
        with patch("app.routers.pipelines.pipelines", pipe_m):
            r = await client.post("/pipelines/", headers=auth_headers,
                                   json={"nome": "meu", "is_public": True})
        assert r.status_code == 200
        assert r.json()["is_public"] is False

    @pytest.mark.asyncio
    async def test_professor_publica(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value=_prof())
        pipe_m = MagicMock(insert_one=AsyncMock(return_value=MagicMock(inserted_id=ObjectId())))
        with patch("app.routers.pipelines.pipelines", pipe_m):
            r = await client.post("/pipelines/", headers=auth_headers,
                                   json={"nome": "aula", "is_public": True})
        assert r.status_code == 200
        assert r.json()["is_public"] is True


# --------------------------------------------------------------- pipelines: vínculo atividade
class TestVinculoAtividade:
    @pytest.mark.asyncio
    async def test_nao_membro_da_turma_403(self, client, mock_db, auth_headers):
        # aluno tenta ligar submissão a atividade de turma da qual não participa.
        turma_id = ObjectId()
        atividade = {"_id": ObjectId(), "turma_id": str(turma_id)}
        turma = {"_id": turma_id, "professor_id": str(ObjectId()), "alunos": []}  # aluno fora
        ativ_m = MagicMock(find_one=AsyncMock(return_value=atividade))
        turmas_m = MagicMock(find_one=AsyncMock(return_value=turma))
        pipe_m = MagicMock(insert_one=AsyncMock(return_value=MagicMock(inserted_id=ObjectId())))
        with patch("app.routers.pipelines.atividades", ativ_m), \
             patch("app.routers.pipelines.turmas", turmas_m), \
             patch("app.routers.pipelines.pipelines", pipe_m):
            r = await client.post("/pipelines/", headers=auth_headers,
                                   json={"nome": "sub", "atividade_id": str(atividade["_id"])})
        assert r.status_code == 403
        pipe_m.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_membro_liga_e_turma_vem_da_atividade(self, client, mock_db, auth_headers):
        uid = mock_db["usuarios"].find_one.return_value["_id"]  # aluno padrão
        turma_id = ObjectId()
        atividade = {"_id": ObjectId(), "turma_id": str(turma_id)}
        turma = {"_id": turma_id, "professor_id": str(ObjectId()), "alunos": [str(uid)]}
        ativ_m = MagicMock(find_one=AsyncMock(return_value=atividade))
        turmas_m = MagicMock(find_one=AsyncMock(return_value=turma))
        pipe_m = MagicMock(insert_one=AsyncMock(return_value=MagicMock(inserted_id=ObjectId())))
        with patch("app.routers.pipelines.atividades", ativ_m), \
             patch("app.routers.pipelines.turmas", turmas_m), \
             patch("app.routers.pipelines.pipelines", pipe_m):
            r = await client.post("/pipelines/", headers=auth_headers,
                                   json={"nome": "sub", "atividade_id": str(atividade["_id"]),
                                         "turma_id": "forjado"})
        assert r.status_code == 200
        # turma_id canônico vem da atividade, não do cliente
        assert r.json()["turma_id"] == str(turma_id)


# --------------------------------------------------------------- chat do aluno: gate por turma
class TestChatScope:
    @pytest.mark.asyncio
    async def test_professor_sem_vinculo_403(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value=_prof())
        turmas_m = MagicMock(find_one=AsyncMock(return_value=None))  # sem vínculo
        with patch("app.routers.chat_tutor.turmas", turmas_m):
            r = await client.get(f"/tutor/chat/aluno/{ObjectId()}/historico", headers=auth_headers)
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_professor_com_vinculo_ok(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value=_prof())
        turmas_m = MagicMock(find_one=AsyncMock(return_value={"_id": ObjectId()}))  # vínculo
        hist_m = MagicMock(find=MagicMock(return_value=AsyncCursor([])))
        with patch("app.routers.chat_tutor.turmas", turmas_m), \
             patch("app.routers.chat_tutor.historico_chat", hist_m):
            r = await client.get(f"/tutor/chat/aluno/{ObjectId()}/historico", headers=auth_headers)
        assert r.status_code == 200
        assert r.json() == []

    @pytest.mark.asyncio
    async def test_admin_ve_qualquer(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value={
            "_id": ObjectId(), "nome_usuario": "adm", "email": "a@a.com", "role": "admin"})
        turmas_m = MagicMock(find_one=AsyncMock(return_value=None))  # admin ignora vínculo
        hist_m = MagicMock(find=MagicMock(return_value=AsyncCursor([])))
        with patch("app.routers.chat_tutor.turmas", turmas_m), \
             patch("app.routers.chat_tutor.historico_chat", hist_m):
            r = await client.get(f"/tutor/chat/aluno/{ObjectId()}/historico", headers=auth_headers)
        assert r.status_code == 200
