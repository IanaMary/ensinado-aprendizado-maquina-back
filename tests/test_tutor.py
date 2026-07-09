import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId


class TestTutorDescricao:
    @pytest.mark.asyncio
    async def test_buscar_tutor_inicio(self, client, mock_db, auth_headers):
        mock_db["tutor"].find_one = AsyncMock(return_value={
            "_id": ObjectId(),
            "pipe": "inicio",
            "texto_pipe": "Bem-vindo!",
            "explicacao": "Explicacao teste",
        })
        response = await client.get("/tutor/?pipe=inicio", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "descricao" in data
        assert "id" in data

    @pytest.mark.asyncio
    async def test_buscar_tutor_inicio_sem_explicacao(self, client, mock_db, auth_headers):
        mock_db["tutor"].find_one = AsyncMock(return_value={
            "_id": ObjectId(),
            "pipe": "inicio",
            "texto_pipe": "Bem-vindo!",
        })
        response = await client.get("/tutor/?pipe=inicio", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "Bem-vindo!" in data["descricao"]

    @pytest.mark.asyncio
    async def test_buscar_tutor_coleta_dado(self, client, mock_db, auth_headers):
        mock_db["tutor"].find_one = AsyncMock(return_value={
            "_id": ObjectId(),
            "pipe": "coleta-dado",
            "texto_pipe": "Coleta de Dados",
        })
        response = await client.get(
            "/tutor/?pipe=coleta-dado&textos=texto_pipe&textos=planilha_treino",
            headers=auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_buscar_tutor_com_textos_customizados(self, client, mock_db, auth_headers):
        mock_db["tutor"].find_one = AsyncMock(return_value={
            "_id": ObjectId(),
            "pipe": "inicio",
            "texto_pipe": "Texto pipe",
            "introducao": "Introducao teste",
            "objetivo": "Objetivo teste",
        })
        response = await client.get(
            "/tutor/?pipe=inicio&textos=texto_pipe&textos=introducao",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "Texto pipe" in data["descricao"]
        assert "Introducao teste" in data["descricao"]


class TestTutorEditar:
    @pytest.mark.asyncio
    async def test_buscar_tutor_editar(self, client, mock_db, auth_headers):
        mock_db["tutor"].aggregate = MagicMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=[{
                "_id": ObjectId(),
                "pipe": "inicio",
                "texto_pipe": "Teste",
            }])
        ))
        response = await client.get("/tutor/editar?pipe=inicio", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_atualizar_descricao(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        oid = ObjectId()
        response = await client.put(
            f"/tutor/{str(oid)}",
            headers=auth_headers,
            json={"contexto": {"texto_pipe": "Novo texto"}},
        )
        assert response.status_code == 200
        # regressão da união lossy: o campo de texto deve ser preservado
        assert response.json()["update_data"]["texto_pipe"] == "Novo texto"

    @pytest.mark.asyncio
    async def test_atualizar_descricao_aluno_403(self, client, mock_db, auth_headers):
        # auth_headers default = aluno; escrita do tutor é restrita a admin/professor
        response = await client.put(
            f"/tutor/{str(ObjectId())}",
            headers=auth_headers,
            json={"contexto": {"texto_pipe": "x"}},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_atualizar_descricao_id_invalido(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        response = await client.put(
            "/tutor/id-invalido",
            headers=auth_headers,
            json={"contexto": {"texto_pipe": "Novo texto"}},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_atualizar_modelos_preserva_supervisionado(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        response = await client.put(
            f"/tutor/editar-modelos/{str(ObjectId())}",
            headers=auth_headers,
            json={"contexto": {"supervisionado": {"classificacao": {"modelos": [{"valor": "knn"}]}}}},
        )
        assert response.status_code == 200
        # regressão: a união lossy descartava `supervisionado` → 400
        assert "supervisionado.classificacao.modelos" in response.json()["update_data"]

    @pytest.mark.asyncio
    async def test_atualizar_tipo_aprendizado_preserva_explicacao(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        response = await client.put(
            f"/tutor/editar-tipo-aprendizado/{str(ObjectId())}",
            headers=auth_headers,
            json={"contexto": {"supervisionado": {"classificacao": {"explicacao": "Classifica em categorias"}}}},
        )
        assert response.status_code == 200
        assert response.json()["update_data"]["supervisionado.classificacao.explicacao"] == "Classifica em categorias"


class TestAtualizarPorPipe:
    @pytest.mark.asyncio
    async def test_upsert_pipe_inicio(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        mock_db["tutor"].find_one = AsyncMock(return_value={"_id": ObjectId(), "pipe": "inicio"})
        response = await client.put(
            "/tutor/pipe/inicio",
            headers=auth_headers,
            json={"contexto": {"texto_pipe": "<h4>Bem-vindo!</h4>", "explicacao": "Como usar"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["update_data"]["texto_pipe"] == "<h4>Bem-vindo!</h4>"
        assert data["id"]
        # upsert por pipe: update_one deve ser chamado com upsert=True
        args, kwargs = mock_db["tutor"].update_one.call_args
        assert args[0] == {"pipe": "inicio"}
        assert kwargs.get("upsert") is True

    @pytest.mark.asyncio
    async def test_pipe_desconhecido_404(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        response = await client.put(
            "/tutor/pipe/nao-existe",
            headers=auth_headers,
            json={"contexto": {"texto_pipe": "x"}},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_pipe_aluno_403(self, client, mock_db, auth_headers):
        response = await client.put(
            "/tutor/pipe/inicio",
            headers=auth_headers,
            json={"contexto": {"texto_pipe": "x"}},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_pipe_sem_campos_400(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        response = await client.put(
            "/tutor/pipe/inicio",
            headers=auth_headers,
            json={"contexto": {"pipe": "inicio"}},
        )
        assert response.status_code == 400


class TestKbConfPipeline:
    @pytest.mark.asyncio
    async def test_get_conf_pipeline_fallback_versionado(self, client, mock_db, auth_headers):
        """Sem doc no banco, o pipe conf-pipeline responde com a KB versionada (não 404)."""
        mock_db["tutor"].find_one = AsyncMock(return_value=None)
        response = await client.get("/tutor/?pipe=conf-pipeline", headers=auth_headers)
        assert response.status_code == 200
        assert "GUIA DE PREENCHIMENTO" in response.json()["descricao"]

    @pytest.mark.asyncio
    async def test_get_conf_pipeline_do_banco(self, client, mock_db, auth_headers):
        mock_db["tutor"].find_one = AsyncMock(return_value={
            "_id": ObjectId(), "pipe": "conf-pipeline", "texto_pipe": "Guia custom do admin",
        })
        response = await client.get("/tutor/?pipe=conf-pipeline", headers=auth_headers)
        assert response.status_code == 200
        assert "Guia custom" in response.json()["descricao"]

    @pytest.mark.asyncio
    async def test_get_pipe_sem_doc_retorna_404(self, client, mock_db, auth_headers):
        """Regressão: o except genérico convertia o 404 em 400 (visto no log de prod)."""
        mock_db["tutor"].find_one = AsyncMock(return_value=None)
        response = await client.get("/tutor/?pipe=pre-processamento", headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_upsert_pipe_conf_pipeline_permitido(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        mock_db["tutor"].find_one = AsyncMock(return_value={"_id": ObjectId(), "pipe": "conf-pipeline"})
        response = await client.put(
            "/tutor/pipe/conf-pipeline",
            headers=auth_headers,
            json={"contexto": {"texto_pipe": "novo guia"}},
        )
        assert response.status_code == 200
