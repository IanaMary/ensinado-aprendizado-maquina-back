"""Marcação de `origem` nas rotas que gravam texto em `db.tutor`.

Isto é pré-requisito do seed versionado, não enfeite: se o admin salva pela tela e o documento não
registra que o texto passou a ser dele, o seed do próximo deploy classifica a edição como
"versionado" e propaga o padrão por cima — pior que não ter guarda, porque escondido atrás de um
mecanismo que diz proteger.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId

from app.conteudo.kb_tutor_inicio import TUTOR_INICIO_HTML, TUTOR_INICIO_LEGADO
from app.conteudo.textos_do_tutor import ALVO_INICIO


def _prof():
    return {"_id": ObjectId(), "email": "prof@x.com", "nome_usuario": "Prof", "role": "professor"}


def _ops(mock_db):
    """Operações passadas ao Mongo na última escrita (o conftest aponta `tutor` e `tutor_audit`
    para o mesmo mock, então `update_one` é o da rota)."""
    return mock_db["tutor"].update_one.call_args[0][1]


class TestMarcacaoPorPipe:
    @pytest.mark.asyncio
    async def test_texto_proprio_do_admin_e_marcado_como_admin(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value=_prof())
        mock_db["tutor"].update_one = AsyncMock()
        mock_db["tutor"].find_one = AsyncMock(return_value={"_id": ObjectId()})
        r = await client.put("/tutor/pipe/inicio", headers=auth_headers,
                             json={"contexto": {"texto_pipe": "<h4>Oi, turma do 9º ano!</h4>"}})
        assert r.status_code == 200
        ops = _ops(mock_db)
        assert ops["$set"]["origem"] == "admin"
        # Baseline: o padrão que ele tinha à frente ao gravar (não o hash do que escreveu).
        assert ops["$set"]["padrao_hash"] == ALVO_INICIO.hash_padrao
        assert ops["$inc"] == {"versao": 1}
        assert ops["$setOnInsert"] == {"pipe": "inicio"}

    @pytest.mark.asyncio
    async def test_metadado_nao_aparece_no_historico_nem_na_resposta(self, client, mock_db,
                                                                    auth_headers):
        """`update_data` é o corpo da resposta E a fonte de `campos_alterados` do histórico: se a
        marcação vazasse para lá, a tela do admin diria "campos alterados: texto_pipe, origem…"."""
        mock_db["usuarios"].find_one = AsyncMock(return_value=_prof())
        mock_db["tutor"].update_one = AsyncMock()
        mock_db["tutor"].find_one = AsyncMock(return_value={"_id": ObjectId()})
        r = await client.put("/tutor/pipe/inicio", headers=auth_headers,
                             json={"contexto": {"texto_pipe": "meu texto"}})
        assert set(r.json()["update_data"]) == {"texto_pipe"}

    @pytest.mark.asyncio
    async def test_colar_o_padrao_nao_marca_como_admin(self, client, mock_db, auth_headers):
        """Senão o admin ficaria congelado fora das próximas atualizações do repo sem ter texto
        próprio a proteger."""
        mock_db["usuarios"].find_one = AsyncMock(return_value=_prof())
        mock_db["tutor"].update_one = AsyncMock()
        mock_db["tutor"].find_one = AsyncMock(return_value={"_id": ObjectId()})
        r = await client.put("/tutor/pipe/inicio", headers=auth_headers,
                             json={"contexto": {"texto_pipe": TUTOR_INICIO_HTML}})
        assert r.status_code == 200
        assert _ops(mock_db)["$set"]["origem"] == "versionado"

    @pytest.mark.asyncio
    async def test_salvar_o_placeholder_legado_tambem_conta_como_versionado(self, client, mock_db,
                                                                           auth_headers):
        """Fecha o ciclo com o estado `legados` do seed: o admin abre a tela, vê a frase única e
        clica em Salvar; no próximo boot o texto novo entra em vez de congelar."""
        mock_db["usuarios"].find_one = AsyncMock(return_value=_prof())
        mock_db["tutor"].update_one = AsyncMock()
        mock_db["tutor"].find_one = AsyncMock(return_value={"_id": ObjectId()})
        await client.put("/tutor/pipe/inicio", headers=auth_headers,
                         json={"contexto": {"texto_pipe": TUTOR_INICIO_LEGADO}})
        # O texto do placeholder não é o padrão, então a rota marca 'admin'…
        assert _ops(mock_db)["$set"]["origem"] == "admin"
        # …e é o `legados` do seed que desfaz isso (ver tests/test_seed_texto_versionado.py).

    @pytest.mark.asyncio
    async def test_pipe_sem_padrao_versionado_nao_ganha_metadado(self, client, mock_db,
                                                                auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value=_prof())
        mock_db["tutor"].update_one = AsyncMock()
        mock_db["tutor"].find_one = AsyncMock(return_value={"_id": ObjectId()})
        r = await client.put("/tutor/pipe/coleta-dado", headers=auth_headers,
                             json={"contexto": {"texto_pipe": "Sobre a coleta"}})
        assert r.status_code == 200
        ops = _ops(mock_db)
        assert "origem" not in ops["$set"] and "$inc" not in ops

    @pytest.mark.asyncio
    async def test_campos_do_seed_vindos_do_cliente_sao_descartados(self, client, mock_db,
                                                                   auth_headers):
        """`contexto` é um dict sem validação: uma `versao` string faria TODO `$inc` seguinte
        naquele documento estourar 500, para sempre."""
        mock_db["usuarios"].find_one = AsyncMock(return_value=_prof())
        mock_db["tutor"].update_one = AsyncMock()
        mock_db["tutor"].find_one = AsyncMock(return_value={"_id": ObjectId()})
        r = await client.put("/tutor/pipe/inicio", headers=auth_headers, json={"contexto": {
            "texto_pipe": "meu texto", "versao": "9", "origem": "versionado",
            "padrao_hash": "deadbeef", "atualizado_por": "eu",
        }})
        assert r.status_code == 200
        assert set(r.json()["update_data"]) == {"texto_pipe"}
        ops = _ops(mock_db)
        assert ops["$set"]["origem"] == "admin"          # computada, não a que o cliente mandou
        assert ops["$set"]["padrao_hash"] == ALVO_INICIO.hash_padrao
        assert ops["$inc"] == {"versao": 1}


class TestMarcacaoPorId:
    @pytest.mark.asyncio
    async def test_catch_all_marca_quando_o_doc_e_de_um_pipe_versionado(self, client, mock_db,
                                                                       auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value=_prof())
        mock_db["tutor"].update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        mock_db["tutor"].find_one = AsyncMock(return_value={"pipe": "inicio"})
        r = await client.put(f"/tutor/{ObjectId()}", headers=auth_headers,
                             json={"contexto": {"texto_pipe": "outro texto"}})
        assert r.status_code == 200
        assert _ops(mock_db)["$set"]["origem"] == "admin"

    @pytest.mark.asyncio
    async def test_catch_all_sem_pipe_conhecido_nao_marca(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value=_prof())
        mock_db["tutor"].update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        mock_db["tutor"].find_one = AsyncMock(return_value=None)
        r = await client.put(f"/tutor/{ObjectId()}", headers=auth_headers,
                             json={"contexto": {"texto_pipe": "texto solto"}})
        assert r.status_code == 200
        assert "origem" not in _ops(mock_db)["$set"]
