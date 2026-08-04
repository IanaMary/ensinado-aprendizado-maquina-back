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
