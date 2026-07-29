"""Instrução de sistema do chat do tutor: persistida, versionada, editável e à prova de falha.

O texto do `system` vive no banco (semeado a partir da fonte versionada — ver
`tests/test_seed_system_prompt.py`) e o admin edita em conf-tutor → LLM. Quatro coisas precisam
continuar valendo:

1. sem doc (ou com falha de leitura) vale o texto VERSIONADO — o chat não pode quebrar por
   causa de uma configuração;
2. só admin escreve; só admin/professor lê (o prompt é a regra que o tutor segue);
3. voltar ao padrão **grava** o padrão e guarda o texto anterior no histórico — não apaga;
4. o `system` montado carrega o texto vigente, o contexto do pipeline e a base de conhecimento.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from app.conteudo.kb_tutor_chat import (
    HASH_SYSTEM_PROMPT,
    MAX_SYSTEM_PROMPT_CHARS,
    SYSTEM_PROMPT_TUTOR,
    hash_prompt,
)
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
        mock_db["usuarios"].find_one = AsyncMock(return_value=_admin())
        with patch("app.routers.chat_tutor.configuracoes_tutor", _config()):
            r = await client.get("/tutor/system-prompt", headers=auth_headers)
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["texto"] == SYSTEM_PROMPT_TUTOR
        assert corpo["padrao"] == SYSTEM_PROMPT_TUTOR
        assert corpo["personalizado"] is False
        assert corpo["limite"] == MAX_SYSTEM_PROMPT_CHARS
        # Sem documento, o chat cai no versionado — e a tela precisa poder DIZER isso.
        assert corpo["fonte"] == "versionado"
        assert corpo["padrao_desatualizado"] is False

    @pytest.mark.asyncio
    async def test_get_expoe_o_estado_de_versao_do_documento(self, client, mock_db, auth_headers):
        """O aviso de 'padrão novo' só acende quando SABEMOS de que padrão a edição derivou."""
        mock_db["usuarios"].find_one = AsyncMock(return_value=_admin())
        doc = {"chave": "system_prompt", "valor": "Texto do admin", "origem": "admin",
               "padrao_hash": "hashvelho123", "versao": 4}
        with patch("app.routers.chat_tutor.configuracoes_tutor",
                   MagicMock(find_one=AsyncMock(return_value=doc))):
            corpo = (await client.get("/tutor/system-prompt", headers=auth_headers)).json()
        assert corpo["fonte"] == "banco" and corpo["origem"] == "admin"
        assert corpo["versao"] == 4
        assert corpo["padrao_hash"] == HASH_SYSTEM_PROMPT
        assert corpo["padrao_hash_base"] == "hashvelho123"
        assert corpo["padrao_desatualizado"] is True

    @pytest.mark.asyncio
    async def test_baseline_desconhecido_nao_acende_aviso(self, client, mock_db, auth_headers):
        """Doc legado adotado como 'admin' fica sem `padrao_hash`: avisar aí daria ao admin um
        alarme que ele não tem como resolver."""
        mock_db["usuarios"].find_one = AsyncMock(return_value=_admin())
        doc = {"chave": "system_prompt", "valor": "Texto do admin", "origem": "admin"}
        with patch("app.routers.chat_tutor.configuracoes_tutor",
                   MagicMock(find_one=AsyncMock(return_value=doc))):
            corpo = (await client.get("/tutor/system-prompt", headers=auth_headers)).json()
        assert corpo["padrao_hash_base"] is None
        assert corpo["padrao_desatualizado"] is False

    @pytest.mark.asyncio
    async def test_aluno_nao_le_a_instrucao_de_sistema(self, client, mock_db, auth_headers):
        """O prompt é a regra que o tutor segue: entregá-la ao aluno é entregar o mapa para
        contorná-la. (O fixture `mock_user` tem role 'aluno'.)"""
        with patch("app.routers.chat_tutor.configuracoes_tutor", _config()):
            r = await client.get("/tutor/system-prompt", headers=auth_headers)
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_put_exige_admin(self, client, mock_db, auth_headers):
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
        assert update["$set"]["origem"] == "admin"
        # Baseline: o padrão que o admin tinha à frente ao gravar (não o hash do que ele escreveu).
        assert update["$set"]["padrao_hash"] == HASH_SYSTEM_PROMPT
        assert update["$inc"] == {"versao": 1}
        entrada = audit.insert_one.call_args[0][0]
        # A tela mostra o histórico da aba atual (LLM), então a entrada precisa cair nesse pipe.
        assert entrada["pipe"] == "llm"
        assert entrada["campos_alterados"] == ["system_prompt"]
        assert entrada["operacao"] == "editou"
        assert entrada["hash_novo"] == hash_prompt("Você é o tutor da ONIA.")

    @pytest.mark.asyncio
    async def test_texto_vazio_grava_o_padrao_sem_destruir_o_anterior(self, client, mock_db,
                                                                     auth_headers):
        """Antes isto fazia `delete_one` e o texto do admin era perdido sem cópia (a auditoria
        guardava só o tamanho). Agora o padrão é GRAVADO — o estado 'padrão' passa a ser um fato
        persistido, não a ausência de fato — e o texto que saiu do ar fica no histórico."""
        mock_db["usuarios"].find_one = AsyncMock(return_value=_admin())
        doc = {"chave": "system_prompt", "valor": "Texto do admin", "origem": "admin",
               "padrao_hash": HASH_SYSTEM_PROMPT, "versao": 2}
        config = MagicMock(find_one=AsyncMock(return_value=doc), update_one=AsyncMock(),
                           delete_one=AsyncMock())
        audit = MagicMock(insert_one=AsyncMock())
        with patch("app.routers.chat_tutor.configuracoes_tutor", config), \
             patch("app.routers.chat_tutor.tutor_audit", audit):
            r = await client.put("/tutor/system-prompt", headers=auth_headers, json={"texto": "  "})
        assert r.status_code == 200
        assert r.json()["personalizado"] is False
        config.delete_one.assert_not_called()
        update = config.update_one.call_args[0][1]
        assert update["$set"]["valor"] == SYSTEM_PROMPT_TUTOR
        assert update["$set"]["origem"] == "versionado"
        entrada = audit.insert_one.call_args[0][0]
        assert entrada["operacao"] == "restaurou_padrao"
        assert entrada["texto_anterior"] == "Texto do admin"

    @pytest.mark.asyncio
    async def test_colar_o_padrao_nao_marca_como_edicao_do_admin(self, client, mock_db,
                                                                auth_headers):
        """Senão o admin ficaria congelado fora das próximas atualizações do repo sem ter um texto
        próprio a proteger."""
        mock_db["usuarios"].find_one = AsyncMock(return_value=_admin())
        config = MagicMock(find_one=AsyncMock(return_value=None), update_one=AsyncMock(),
                           delete_one=AsyncMock())
        with patch("app.routers.chat_tutor.configuracoes_tutor", config), \
             patch("app.routers.chat_tutor.tutor_audit", MagicMock(insert_one=AsyncMock())):
            r = await client.put("/tutor/system-prompt", headers=auth_headers,
                                 json={"texto": SYSTEM_PROMPT_TUTOR})
        assert r.status_code == 200 and r.json()["personalizado"] is False
        assert config.update_one.call_args[0][1]["$set"]["origem"] == "versionado"

    @pytest.mark.asyncio
    async def test_salvar_o_mesmo_texto_duas_vezes_nao_gera_entrada_fantasma(self, client, mock_db,
                                                                            auth_headers):
        mock_db["usuarios"].find_one = AsyncMock(return_value=_admin())
        doc = {"chave": "system_prompt", "valor": "Texto do admin", "origem": "admin",
               "padrao_hash": HASH_SYSTEM_PROMPT, "versao": 3}
        config = MagicMock(find_one=AsyncMock(return_value=doc), update_one=AsyncMock(),
                           delete_one=AsyncMock())
        audit = MagicMock(insert_one=AsyncMock())
        with patch("app.routers.chat_tutor.configuracoes_tutor", config), \
             patch("app.routers.chat_tutor.tutor_audit", audit):
            r = await client.put("/tutor/system-prompt", headers=auth_headers,
                                 json={"texto": "Texto do admin"})
        assert r.status_code == 200
        config.update_one.assert_not_called()
        audit.insert_one.assert_not_called()

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
