"""Instrução de sistema do chat do tutor: versionada, editável e à prova de falha.

O texto do `system` deixou de ser constante no código: o admin edita em conf-tutor → LLM e o
banco prevalece. Três coisas precisam continuar valendo:

1. sem doc (ou com falha de leitura) vale o texto VERSIONADO — o chat não pode quebrar por
   causa de uma configuração;
2. só admin escreve, e texto vazio volta ao padrão;
3. o `system` montado carrega o texto vigente, o contexto do pipeline e a base de conhecimento.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from app.conteudo.kb_tutor_chat import MAX_SYSTEM_PROMPT_CHARS, SYSTEM_PROMPT_TUTOR
from app.routers.chat_tutor import _montar_system, _system_prompt_vigente


def _config(valor=None, explode=False):
    """Coleção configuracoes_tutor simulada."""
    if explode:
        return MagicMock(find_one=AsyncMock(side_effect=RuntimeError("mongo fora")))
    doc = {"chave": "system_prompt", "valor": valor} if valor is not None else None
    return MagicMock(find_one=AsyncMock(return_value=doc))


class TestTextoVersionado:
    def test_texto_versionado_descreve_o_publico_da_onia(self):
        assert "ONIA" in SYSTEM_PROMPT_TUTOR and "IOAI" in SYSTEM_PROMPT_TUTOR
        assert "8º ano" in SYSTEM_PROMPT_TUTOR and "Ensino Superior" in SYSTEM_PROMPT_TUTOR

    def test_texto_versionado_distingue_professor_e_admin(self):
        """O assistente do conf-pipeline usa o MESMO prompt: não pode tratar admin como aluno."""
        assert "papel_do_usuario" in SYSTEM_PROMPT_TUTOR
        assert "sem tratar quem pergunta como aluno" in SYSTEM_PROMPT_TUTOR

    def test_sem_junçoes_grudadas(self):
        """Regressão de digitação: literais concatenados sem espaço colam duas frases."""
        for grudado in ("Superior.Explique", "aluno.Priorize", "catálogo.(nomes",
                        "geral.Se", "contexto.Quando"):
            assert grudado not in SYSTEM_PROMPT_TUTOR

    def test_cabe_no_limite_oferecido_ao_admin(self):
        assert len(SYSTEM_PROMPT_TUTOR) < MAX_SYSTEM_PROMPT_CHARS


class TestPromptVigente:
    @pytest.mark.asyncio
    async def test_sem_doc_usa_o_versionado(self):
        with patch("app.routers.chat_tutor.configuracoes_tutor", _config()):
            assert await _system_prompt_vigente() == SYSTEM_PROMPT_TUTOR

    @pytest.mark.asyncio
    async def test_doc_do_admin_prevalece(self):
        with patch("app.routers.chat_tutor.configuracoes_tutor", _config("Você é o tutor da ONIA.")):
            assert await _system_prompt_vigente() == "Você é o tutor da ONIA."

    @pytest.mark.asyncio
    async def test_doc_em_branco_nao_apaga_a_instrucao(self):
        with patch("app.routers.chat_tutor.configuracoes_tutor", _config("   ")):
            assert await _system_prompt_vigente() == SYSTEM_PROMPT_TUTOR

    @pytest.mark.asyncio
    async def test_falha_do_banco_nao_quebra_o_chat(self):
        with patch("app.routers.chat_tutor.configuracoes_tutor", _config(explode=True)):
            assert await _system_prompt_vigente() == SYSTEM_PROMPT_TUTOR


class TestSystemMontado:
    @pytest.mark.asyncio
    async def test_junta_prompt_contexto_e_base(self):
        with patch("app.routers.chat_tutor.configuracoes_tutor", _config("PROMPT CUSTOM")), \
             patch("app.routers.chat_tutor.bloco_kb", AsyncMock(return_value="ficha do knn")):
            system = await _montar_system({"modelo": "knn"})
        assert system.startswith("PROMPT CUSTOM")
        assert "=== CONTEXTO DO PIPELINE ===" in system and '"knn"' in system
        assert "=== BASE DE CONHECIMENTO (catálogo verificado) ===" in system

    @pytest.mark.asyncio
    async def test_sem_base_de_conhecimento_o_bloco_nao_aparece(self):
        with patch("app.routers.chat_tutor.configuracoes_tutor", _config()), \
             patch("app.routers.chat_tutor.bloco_kb", AsyncMock(return_value="")):
            system = await _montar_system(None)
        # O prompt CITA o nome do bloco; o que não deve existir é o bloco em si.
        assert "=== BASE DE CONHECIMENTO" not in system
        assert "Nenhum pipeline carregado no momento." in system


def _admin():
    return {"_id": ObjectId(), "email": "a@x.com", "nome_usuario": "Admin", "role": "admin"}


class TestRotas:
    @pytest.mark.asyncio
    async def test_get_indica_se_esta_personalizado(self, client, mock_db, auth_headers):
        with patch("app.routers.chat_tutor.configuracoes_tutor", _config()):
            r = await client.get("/tutor/system-prompt", headers=auth_headers)
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["texto"] == SYSTEM_PROMPT_TUTOR
        assert corpo["padrao"] == SYSTEM_PROMPT_TUTOR
        assert corpo["personalizado"] is False
        assert corpo["limite"] == MAX_SYSTEM_PROMPT_CHARS

        with patch("app.routers.chat_tutor.configuracoes_tutor", _config("Outro texto")):
            r = await client.put("/tutor/system-prompt", headers=auth_headers, json={})  # não-admin
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_grava_e_audita(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value=_admin())
        config = MagicMock(find_one=AsyncMock(return_value=None), update_one=AsyncMock(),
                           delete_one=AsyncMock())
        audit = MagicMock(insert_one=AsyncMock())
        with patch("app.routers.chat_tutor.configuracoes_tutor", config), \
             patch("app.routers.chat_tutor.tutor_audit", audit):
            r = await client.put("/tutor/system-prompt", headers=auth_headers,
                                 json={"texto": "Você é o tutor da ONIA."})
        assert r.status_code == 200
        assert r.json() == {"texto": "Você é o tutor da ONIA.", "personalizado": True}
        filtro, update = config.update_one.call_args[0][:2]
        assert filtro == {"chave": "system_prompt"}
        assert update["$set"]["valor"] == "Você é o tutor da ONIA."
        entrada = audit.insert_one.call_args[0][0]
        # A tela mostra o histórico da aba atual (LLM), então a entrada precisa cair nesse pipe.
        assert entrada["pipe"] == "llm"
        assert entrada["campos_alterados"] == ["system_prompt"]
        assert entrada["operacao"] == "editou"

    @pytest.mark.asyncio
    async def test_texto_vazio_restaura_o_padrao(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value=_admin())
        config = MagicMock(find_one=AsyncMock(return_value=None), update_one=AsyncMock(),
                           delete_one=AsyncMock())
        with patch("app.routers.chat_tutor.configuracoes_tutor", config), \
             patch("app.routers.chat_tutor.tutor_audit", MagicMock(insert_one=AsyncMock())):
            r = await client.put("/tutor/system-prompt", headers=auth_headers, json={"texto": "  "})
        assert r.status_code == 200
        assert r.json()["personalizado"] is False
        config.delete_one.assert_awaited_once()
        config.update_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_prompt_gigante_recusado(self, client, mock_db, auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value=_admin())
        with patch("app.routers.chat_tutor.configuracoes_tutor",
                   MagicMock(update_one=AsyncMock(), delete_one=AsyncMock())):
            r = await client.put("/tutor/system-prompt", headers=auth_headers,
                                 json={"texto": "x" * (MAX_SYSTEM_PROMPT_CHARS + 1)})
        assert r.status_code == 400
        assert str(MAX_SYSTEM_PROMPT_CHARS) in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_put_nao_e_engolido_pelo_catch_all_de_tutor(self, client, mock_db, auth_headers):
        """Regressão: `PUT /tutor/{id}` (app/routers/tutor.py) já roubou `PUT /tutor/modelo`.

        Se voltar a acontecer, esta rota responderia 400 de ObjectId inválido em vez de 403.
        """
        r = await client.put("/tutor/system-prompt", headers=auth_headers, json={"texto": "x"})
        assert r.status_code == 403
