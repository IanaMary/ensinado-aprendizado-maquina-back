"""Seed da instrução de sistema: a matriz de decisão e o que ela escreve no banco.

O valor deste arquivo está na função PURA `decidir_seed`: são dez estados, e a garantia que
importa é negativa — **o seed nunca sobrescreve o texto que o admin gravou** (exceto com
`--forcar`, que é o operador assumindo a responsabilidade). Testar isso por mock de coleção
custaria dez fixtures; aqui custa um dicionário.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.conteudo.kb_tutor_chat import HASH_SYSTEM_PROMPT, SYSTEM_PROMPT_TUTOR, hash_prompt
from app.conteudo.system_prompt_seed import (
    ACAO_CUROU,
    ACAO_FORCOU,
    ACAO_INSERIU,
    ACAO_NORMALIZOU_ADMIN,
    ACAO_NORMALIZOU_VERSIONADO,
    ACAO_PRESERVOU,
    ACAO_PRESERVOU_DESATUALIZADO,
    ACAO_PROPAGOU,
    ACAO_SEM_MUDANCA,
    ORIGEM_ADMIN,
    ORIGEM_VERSIONADO,
    decidir_seed,
    resumo_legivel,
    semear_system_prompt,
)

H = HASH_SYSTEM_PROMPT
TEXTO_ADMIN = "Você é um tutor. Responda curto."


def _doc(valor, origem=None, padrao_hash=None, versao=1):
    doc = {"chave": "system_prompt", "valor": valor, "versao": versao}
    if origem is not None:
        doc["origem"] = origem
    if padrao_hash is not None:
        doc["padrao_hash"] = padrao_hash
    return doc


class TestMatrizDeDecisao:
    def test_a_doc_ausente_insere_o_padrao(self):
        acao, ops = decidir_seed(None)
        assert acao == ACAO_INSERIU
        assert ops["$set"]["valor"] == SYSTEM_PROMPT_TUTOR
        assert ops["$set"]["origem"] == ORIGEM_VERSIONADO
        assert ops["$set"]["padrao_hash"] == H
        assert ops["$inc"] == {"versao": 1}

    def test_inc_sem_setoninsert_no_mesmo_campo(self):
        """`$inc` e `$setOnInsert` no mesmo path é erro do Mongo — e no upsert que insere,
        `$inc` já cria o campo com 1."""
        _, ops = decidir_seed(None)
        assert "$setOnInsert" not in ops
        assert "versao" not in ops["$set"]

    def test_b_em_dia_nao_escreve(self):
        acao, ops = decidir_seed(_doc(SYSTEM_PROMPT_TUTOR, ORIGEM_VERSIONADO, H))
        assert acao == ACAO_SEM_MUDANCA
        assert ops is None

    def test_c_texto_versionado_antigo_recebe_o_novo(self):
        """É o que significa 'versionado com o sistema': quem nunca editou recebe o texto novo."""
        acao, ops = decidir_seed(_doc("texto do seed antigo", ORIGEM_VERSIONADO, "hashvelho123"))
        assert acao == ACAO_PROPAGOU
        assert ops["$set"]["valor"] == SYSTEM_PROMPT_TUTOR

    def test_d_edicao_do_admin_em_dia_e_preservada(self):
        acao, ops = decidir_seed(_doc(TEXTO_ADMIN, ORIGEM_ADMIN, H))
        assert acao == ACAO_PRESERVOU
        assert ops is None

    def test_e_edicao_do_admin_com_padrao_novo_e_preservada_e_sinalizada(self):
        acao, ops = decidir_seed(_doc(TEXTO_ADMIN, ORIGEM_ADMIN, "hashvelho123"))
        assert acao == ACAO_PRESERVOU_DESATUALIZADO
        assert ops is None      # o aviso é para a tela; o texto do admin não se toca

    def test_f_legado_igual_ao_padrao_vira_versionado(self):
        acao, ops = decidir_seed(_doc(SYSTEM_PROMPT_TUTOR))
        assert acao == ACAO_NORMALIZOU_VERSIONADO
        assert ops["$set"] == {"origem": ORIGEM_VERSIONADO, "padrao_hash": H}
        assert "valor" not in ops["$set"]        # só metadado

    def test_g_legado_diferente_do_padrao_vira_admin_sem_baseline(self):
        """Conservador: na dúvida o texto é do admin. E `padrao_hash` fica AUSENTE — não sabemos
        de que padrão ele veio, e inventar um baseline acenderia um aviso insolúvel."""
        acao, ops = decidir_seed(_doc(TEXTO_ADMIN))
        assert acao == ACAO_NORMALIZOU_ADMIN
        assert ops["$set"] == {"origem": ORIGEM_ADMIN}
        assert "padrao_hash" not in ops["$set"]

    @pytest.mark.parametrize("valor", ["", "   ", "\n\t "])
    def test_h_valor_vazio_e_curado(self, valor):
        """Não é destruição: sem texto o chat já responderia com o padrão (fallback)."""
        acao, ops = decidir_seed(_doc(valor, ORIGEM_ADMIN, H))
        assert acao == ACAO_CUROU
        assert ops["$set"]["valor"] == SYSTEM_PROMPT_TUTOR

    def test_i_forcar_sobrescreve_o_admin(self):
        acao, ops = decidir_seed(_doc(TEXTO_ADMIN, ORIGEM_ADMIN, H), forcar=True)
        assert acao == ACAO_FORCOU
        assert ops["$set"]["valor"] == SYSTEM_PROMPT_TUTOR

    def test_j_admin_que_colou_o_padrao_volta_a_ser_versionado(self):
        """Senão ele ficaria congelado fora das próximas atualizações do repo sem ter um texto
        próprio a proteger."""
        acao, ops = decidir_seed(_doc(SYSTEM_PROMPT_TUTOR, ORIGEM_ADMIN, "hashvelho123"))
        assert acao == ACAO_NORMALIZOU_VERSIONADO
        assert ops["$set"]["origem"] == ORIGEM_VERSIONADO

    def test_espaco_nas_pontas_nao_conta_como_diferenca(self):
        acao, _ = decidir_seed(_doc(f"\n{SYSTEM_PROMPT_TUTOR}\n ", ORIGEM_VERSIONADO, H))
        assert acao == ACAO_SEM_MUDANCA

    def test_padrao_injetado_e_respeitado(self):
        """A pureza permite testar a propagação sem depender do texto real do repo."""
        acao, ops = decidir_seed(_doc("antigo", ORIGEM_VERSIONADO, "x"), padrao="NOVO PADRÃO")
        assert acao == ACAO_PROPAGOU
        assert ops["$set"]["valor"] == "NOVO PADRÃO"
        assert ops["$set"]["padrao_hash"] == hash_prompt("NOVO PADRÃO")


def _colecao(doc):
    return MagicMock(find_one=AsyncMock(return_value=doc), update_one=AsyncMock())


class TestAplicacaoNoBanco:
    @pytest.mark.asyncio
    async def test_insere_e_audita_quando_nao_havia_doc(self):
        col, audit = _colecao(None), MagicMock(insert_one=AsyncMock())
        r = await semear_system_prompt(col, audit)
        assert r["acao"] == ACAO_INSERIU and r["escreveu"] is True
        assert col.update_one.await_args[0][0] == {"chave": "system_prompt"}
        assert col.update_one.await_args[1]["upsert"] is True
        entrada = audit.insert_one.await_args[0][0]
        assert entrada["pipe"] == "llm"            # é a aba onde o histórico aparece
        assert entrada["operacao"] == "seed_padrao"
        assert entrada["usuario_email"] == "sistema"
        assert entrada["hash_novo"] == H

    @pytest.mark.asyncio
    async def test_propaga_guardando_o_texto_que_saiu_do_ar(self):
        col, audit = _colecao(_doc("texto antigo", ORIGEM_VERSIONADO, "velho")), MagicMock(insert_one=AsyncMock())
        r = await semear_system_prompt(col, audit)
        assert r["acao"] == ACAO_PROPAGOU
        assert audit.insert_one.await_args[0][0]["texto_anterior"] == "texto antigo"

    @pytest.mark.asyncio
    async def test_preserva_sem_escrever_nem_auditar(self):
        col, audit = _colecao(_doc(TEXTO_ADMIN, ORIGEM_ADMIN, "velho")), MagicMock(insert_one=AsyncMock())
        r = await semear_system_prompt(col, audit)
        assert r["acao"] == ACAO_PRESERVOU_DESATUALIZADO and r["escreveu"] is False
        col.update_one.assert_not_awaited()
        audit.insert_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_normalizacao_nao_vira_entrada_no_historico(self):
        """Ajuste de metadado não é mudança de texto: auditar encheria o histórico do admin de
        ruído a cada reinício do serviço."""
        col, audit = _colecao(_doc(SYSTEM_PROMPT_TUTOR)), MagicMock(insert_one=AsyncMock())
        r = await semear_system_prompt(col, audit)
        assert r["acao"] == ACAO_NORMALIZOU_VERSIONADO and r["escreveu"] is True
        col.update_one.assert_awaited_once()
        audit.insert_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_forcar_relata_quantos_chars_do_admin_foram_descartados(self):
        col, audit = _colecao(_doc(TEXTO_ADMIN, ORIGEM_ADMIN, H)), MagicMock(insert_one=AsyncMock())
        r = await semear_system_prompt(col, audit, forcar=True)
        assert r["acao"] == ACAO_FORCOU
        assert r["chars_anteriores"] == len(TEXTO_ADMIN)
        assert "descartados" in resumo_legivel(r)

    @pytest.mark.asyncio
    async def test_falha_da_auditoria_nao_derruba_o_seed(self):
        col = _colecao(None)
        audit = MagicMock(insert_one=AsyncMock(side_effect=RuntimeError("mongo fora")))
        r = await semear_system_prompt(col, audit)
        assert r["escreveu"] is True     # o texto foi gravado mesmo sem o registro


class TestResumoLegivel:
    def test_preservado_desatualizado_explica_o_que_fazer(self):
        col = {"acao": ACAO_PRESERVOU_DESATUALIZADO, "chars_anteriores": 500,
               "hash_novo": H, "chars": 2221, "hash_anterior": "x", "escreveu": False}
        texto = resumo_legivel(col)
        assert "preservada" in texto and "--forcar" in texto
