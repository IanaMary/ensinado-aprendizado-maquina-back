import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId


def _mock_pipeline_find(return_value=None):
    """Cursor encadeável: find().sort().skip().limit().to_list()."""
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=return_value or [])
    return cursor


def _mock_turmas_find(docs):
    """`turmas.find()` é consumido com `async for` (cursor assíncrono), não com `to_list`."""
    class Cursor:
        def __aiter__(self):
            self._i = iter(docs)
            return self

        async def __anext__(self):
            try:
                return next(self._i)
            except StopIteration:
                raise StopAsyncIteration
    return MagicMock(return_value=Cursor())

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
        mock_db["pipelines"].find = MagicMock(return_value=_mock_pipeline_find([]))

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
    async def test_listagem_default_limita_em_200(self, client, mock_db, auth_headers):
        """Por padrão a listagem traz a primeira página de até 200 pipelines."""
        cursor = _mock_pipeline_find([])
        mock_db["pipelines"].find = MagicMock(return_value=cursor)

        response = await client.get("/pipelines/", headers=auth_headers)
        assert response.status_code == 200
        cursor.skip.assert_called_once_with(0)
        cursor.limit.assert_called_once_with(200)
        cursor.to_list.assert_awaited_once_with(length=200)

    @pytest.mark.asyncio
    async def test_listagem_pagina_com_skip(self, client, mock_db, auth_headers):
        """Paginação: limite/pagina traduzem para skip e limit corretos."""
        cursor = _mock_pipeline_find([])
        mock_db["pipelines"].find = MagicMock(return_value=cursor)

        response = await client.get("/pipelines/?limite=10&pagina=3", headers=auth_headers)
        assert response.status_code == 200
        cursor.skip.assert_called_once_with(20)
        cursor.limit.assert_called_once_with(10)
        cursor.to_list.assert_awaited_once_with(length=10)

    @pytest.mark.asyncio
    async def test_galeria(self, client, mock_db, auth_headers):
        response = await client.get("/pipelines/galeria", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []


class TestGaleriaTurma:
    """A galeria mostra públicos **+ o material que o professor deixou nas minhas turmas**.

    O recorte é o ponto sensível desta classe: `turma_id` também marca **submissão de aluno a
    atividade** (é como o ranking sabe de quem é a entrega). Medido em produção em 04/08: das 7
    pipelines existentes, as 2 com `turma_id` não-públicas eram submissões de aluno. Sem os recortes
    de `user_id` e `atividade_id`, esta feature exporia o trabalho de cada colega para a turma toda —
    resultados e métricas incluídos — numa plataforma de menores de idade e com atividade pontuada.
    Estes testes existem para que ninguém afrouxe isso sem perceber.
    """

    TURMA = "t-1"
    PROF = "prof-1"

    def _minhas_turmas(self, mock_db):
        mock_db["turmas"].find = _mock_turmas_find([
            {"_id": self.TURMA, "nome": "Turma de IA", "professor_id": self.PROF},
        ])

    def _galeria(self, mock_db, docs):
        # `find` é o CALLABLE; `_mock_pipeline_find` devolve o cursor (padrão do arquivo).
        mock_db["pipelines"].find = MagicMock(return_value=_mock_pipeline_find(docs))

    @pytest.mark.asyncio
    async def test_item_da_minha_turma_vem_marcado_e_com_nome(self, client, mock_db, auth_headers):
        self._minhas_turmas(mock_db)
        self._galeria(mock_db, [{
            "_id": ObjectId(), "nome": "material", "user_id": self.PROF,
            "turma_id": self.TURMA, "is_public": False,
        }])

        r = await client.get("/pipelines/galeria", headers=auth_headers)

        assert r.status_code == 200
        item = r.json()[0]
        assert item["da_minha_turma"] is True
        assert item["turma_nome"] == "Turma de IA"

    @pytest.mark.asyncio
    async def test_publico_de_outra_turma_nao_revela_o_nome_dela(self, client, mock_db, auth_headers):
        self._minhas_turmas(mock_db)
        self._galeria(mock_db, [{
            "_id": ObjectId(), "nome": "de outra turma", "user_id": "outro-prof",
            "turma_id": "t-de-outro", "is_public": True,
        }])

        item = (await client.get("/pipelines/galeria", headers=auth_headers)).json()[0]

        assert item["da_minha_turma"] is False
        assert item["turma_nome"] is None

    @pytest.mark.asyncio
    async def test_publico_sem_turma_fica_fora_do_filtro(self, client, mock_db, auth_headers):
        self._minhas_turmas(mock_db)
        self._galeria(mock_db, [{
            "_id": ObjectId(), "nome": "publico", "user_id": "alguem", "is_public": True,
        }])

        item = (await client.get("/pipelines/galeria", headers=auth_headers)).json()[0]

        assert item["da_minha_turma"] is False
        assert item["turma_nome"] is None

    @pytest.mark.asyncio
    async def test_a_consulta_exige_o_professor_da_turma_e_nao_um_in_solto(
        self, client, mock_db, auth_headers
    ):
        """O ponto de virada da privacidade: `turma_id: {$in: [...]}` deixaria passar submissão de
        colega. O clause tem de amarrar `user_id` ao professor DAQUELA turma e exigir
        `atividade_id: None`, senão o gabarito do professor vaza junto."""
        self._minhas_turmas(mock_db)
        self._galeria(mock_db, [])

        await client.get("/pipelines/galeria", headers=auth_headers)

        filtro = mock_db["pipelines"].find.call_args[0][0]
        clauses = filtro["$or"]
        assert {"is_public": True} in clauses
        da_turma = [c for c in clauses if "turma_id" in c]
        assert da_turma == [{"turma_id": self.TURMA, "user_id": self.PROF, "atividade_id": None}]
        assert not any(isinstance(c.get("turma_id"), dict) for c in clauses), (
            "um $in em turma_id traria submissão de colega"
        )

    @pytest.mark.asyncio
    async def test_sem_turma_alguma_a_consulta_continua_so_publicos(self, client, mock_db, auth_headers):
        mock_db["turmas"].find = _mock_turmas_find([])
        self._galeria(mock_db, [])

        await client.get("/pipelines/galeria", headers=auth_headers)

        assert mock_db["pipelines"].find.call_args[0][0] == {"is_public": True}

    @pytest.mark.asyncio
    async def test_pertencimento_cobre_aluno_e_professor(self, client, mock_db, auth_headers):
        """`_turmas_do_usuario` procura por `alunos` E por `professor_id` — senão o professor clica em
        "Minha turma" e vê lista vazia, o mesmo defeito que motivou toda esta mudança."""
        self._minhas_turmas(mock_db)
        self._galeria(mock_db, [])

        await client.get("/pipelines/galeria", headers=auth_headers)

        consulta = mock_db["turmas"].find.call_args[0][0]
        chaves = {list(c.keys())[0] for c in consulta["$or"]}
        assert chaves == {"alunos", "professor_id"}


class TestMaterialDeTurmaRecorte:
    """Os recortes, testados na função pura — é onde o critério de privacidade vive."""

    MINHAS = {"t-1": {"nome": "Turma", "professor_id": "prof-1"}}

    def test_material_do_professor_da_turma_entra(self):
        from app.routers.pipelines import _e_material_de_turma
        assert _e_material_de_turma(
            {"turma_id": "t-1", "user_id": "prof-1", "atividade_id": None}, self.MINHAS) is True

    def test_submissao_de_colega_NAO_entra(self):
        from app.routers.pipelines import _e_material_de_turma
        assert _e_material_de_turma(
            {"turma_id": "t-1", "user_id": "aluno-2", "atividade_id": None}, self.MINHAS) is False

    def test_pipeline_do_professor_ligado_a_atividade_NAO_entra(self):
        """Seria o gabarito da atividade."""
        from app.routers.pipelines import _e_material_de_turma
        assert _e_material_de_turma(
            {"turma_id": "t-1", "user_id": "prof-1", "atividade_id": "a-1"}, self.MINHAS) is False

    def test_turma_que_nao_e_minha_NAO_entra(self):
        from app.routers.pipelines import _e_material_de_turma
        assert _e_material_de_turma(
            {"turma_id": "t-9", "user_id": "prof-1", "atividade_id": None}, self.MINHAS) is False

    def test_sem_turma_NAO_entra(self):
        from app.routers.pipelines import _e_material_de_turma
        assert _e_material_de_turma({"user_id": "prof-1"}, self.MINHAS) is False

    def test_pode_ver_mantem_o_proprio_e_o_publico(self):
        from app.routers.pipelines import _pode_ver
        assert _pode_ver({"user_id": "eu"}, "eu", {}) is True
        assert _pode_ver({"user_id": "outro", "is_public": True}, "eu", {}) is True
        assert _pode_ver({"user_id": "outro"}, "eu", {}) is False


class TestCopiarMaterialDeTurma:
    """A galeria e a cópia usam o MESMO critério (`_pode_ver`). Se divergirem, o botão "Copiar" do
    material da turma devolve 404 no cartão que a própria galeria acabou de mostrar."""

    @pytest.mark.asyncio
    async def test_copiar_material_da_turma_funciona(self, client, mock_db, auth_headers):
        oid = ObjectId()
        mock_db["pipelines"].find_one = AsyncMock(return_value={
            "_id": oid, "user_id": "prof-1", "nome": "material", "turma_id": "t-1",
            "is_public": False, "atividade_id": None,
        })
        mock_db["turmas"].find = _mock_turmas_find([
            {"_id": "t-1", "nome": "Turma", "professor_id": "prof-1"},
        ])

        r = await client.post(f"/pipelines/{oid}/copiar", headers=auth_headers)

        assert r.status_code == 200
        assert r.json()["nome"] == "Cópia de material"

    @pytest.mark.asyncio
    async def test_copiar_submissao_de_colega_da_404(self, client, mock_db, auth_headers):
        oid = ObjectId()
        mock_db["pipelines"].find_one = AsyncMock(return_value={
            "_id": oid, "user_id": "aluno-2", "nome": "entrega do colega",
            "turma_id": "t-1", "is_public": False, "atividade_id": "a-1",
        })
        mock_db["turmas"].find = _mock_turmas_find([
            {"_id": "t-1", "nome": "Turma", "professor_id": "prof-1"},
        ])

        r = await client.post(f"/pipelines/{oid}/copiar", headers=auth_headers)

        assert r.status_code == 404


class TestAtualizarEExcluir:
    """`PUT` e `DELETE /pipelines/{id}` não tinham teste — e são o único ponto do sistema onde o
    trabalho do aluno pode ser perdido ou vazado.

    Dois riscos concretos cobertos aqui: (a) escopo por dono, senão um aluno edita ou apaga o
    projeto de outro; (b) `is_public` — só professor/admin publicam na galeria, e o servidor tem de
    forçar isso, porque o checkbox do front é só conveniência.
    """

    def _doc(self, oid, user_id, **extra):
        return {"_id": oid, "user_id": user_id, "nome": "meu projeto", **extra}

    @pytest.mark.asyncio
    async def test_dono_atualiza_o_proprio_projeto(self, client, mock_db, auth_headers, mock_user):
        oid = ObjectId()
        user_id = str(mock_user["_id"])
        mock_db["pipelines"].update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        mock_db["pipelines"].find_one = AsyncMock(return_value=self._doc(oid, user_id, nome="novo"))

        resp = await client.put(f"/pipelines/{oid}", headers=auth_headers, json={"nome": "novo"})

        assert resp.status_code == 200
        assert resp.json()["nome"] == "novo"
        # o filtro tem de amarrar o dono, senão é IDOR
        filtro = mock_db["pipelines"].update_one.await_args[0][0]
        assert filtro["user_id"] == user_id
        # e a data de modificação é do servidor, não do cliente
        assert "dataModificacao" in mock_db["pipelines"].update_one.await_args[0][1]["$set"]

    @pytest.mark.asyncio
    async def test_projeto_de_outro_dono_da_404(self, client, mock_db, auth_headers):
        """`matched_count == 0` porque o filtro inclui `user_id`: o de outra pessoa não existe
        para mim. 404 e não 403, para não confirmar que o id existe."""
        mock_db["pipelines"].update_one = AsyncMock(return_value=MagicMock(matched_count=0))

        resp = await client.put(f"/pipelines/{ObjectId()}", headers=auth_headers, json={"nome": "x"})

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_aluno_nao_consegue_publicar_na_galeria(self, client, mock_db, auth_headers, mock_user):
        """`mock_user` é aluno. Pedir `is_public: true` não pode publicar — o projeto do aluno
        apareceria na galeria pública, que é conteúdo de professor."""
        oid = ObjectId()
        mock_db["pipelines"].update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        mock_db["pipelines"].find_one = AsyncMock(
            return_value=self._doc(oid, str(mock_user["_id"]), is_public=False))

        resp = await client.put(f"/pipelines/{oid}", headers=auth_headers, json={"is_public": True})

        assert resp.status_code == 200
        gravado = mock_db["pipelines"].update_one.await_args[0][1]["$set"]
        assert gravado["is_public"] is False

    @pytest.mark.asyncio
    async def test_id_invalido_e_corpo_vazio_dao_400(self, client, mock_db, auth_headers):
        assert (await client.put("/pipelines/nao-e-objectid", headers=auth_headers,
                                 json={"nome": "x"})).status_code == 400
        assert (await client.put(f"/pipelines/{ObjectId()}", headers=auth_headers,
                                 json={})).status_code == 400

    @pytest.mark.asyncio
    async def test_dono_exclui_e_o_de_outro_da_404(self, client, mock_db, auth_headers, mock_user):
        oid = ObjectId()
        mock_db["pipelines"].delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))

        resp = await client.delete(f"/pipelines/{oid}", headers=auth_headers)
        assert resp.status_code == 200
        filtro = mock_db["pipelines"].delete_one.await_args[0][0]
        assert filtro["user_id"] == str(mock_user["_id"])

        mock_db["pipelines"].delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))
        assert (await client.delete(f"/pipelines/{oid}", headers=auth_headers)).status_code == 404
