"""Motor de textos versionados aplicado aos documentos de `db.tutor`.

A garantia que importa é negativa — **o seed nunca sobrescreve o que o admin escreveu** — e ela tem
UMA exceção declarada: texto que nós mesmos publicamos antes (`legados`). Estes testes fixam as
duas coisas, além da regressão que estava viva em produção: o documento de boas-vindas com dois
caracteres de espaço a mais era lido como "editado pelo admin", e por isso nada era propagado.
"""
import pytest
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

from app.conteudo.kb_conf_pipeline import KB_CONF_PIPELINE
from app.conteudo.kb_tutor_inicio import TUTOR_INICIO_HTML, TUTOR_INICIO_LEGADO
from app.conteudo.textos_do_tutor import (
    ALVO_CONF_PIPELINE,
    ALVO_INICIO,
    ALVOS_POR_PIPE,
    resumo_legivel,
    semear_texto_do_tutor,
)
from app.conteudo.texto_versionado import (
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
    classificar_origem,
    decidir,
)

TEXTO_ADMIN = "Bem-vindo! Aqui a turma do 9º ano treina modelos."


def _doc(texto, origem=None, padrao_hash=None, pipe="inicio"):
    doc = {"pipe": pipe, "texto_pipe": texto, "versao": 1}
    if origem is not None:
        doc["origem"] = origem
    if padrao_hash is not None:
        doc["padrao_hash"] = padrao_hash
    return doc


class TestRegistroDosAlvos:
    def test_alvos_batem_com_os_pipes_conhecidos_do_router(self):
        """Um slug com typo nunca casaria com documento nenhum e o seed morreria em silêncio."""
        from app.routers.tutor import _PIPES_SCHEMA

        assert set(ALVOS_POR_PIPE) <= set(_PIPES_SCHEMA)

    def test_todo_alvo_tem_rotulo_e_aba_de_historico(self):
        for alvo in ALVOS_POR_PIPE.values():
            assert alvo.rotulo and alvo.sufixo and alvo.pipe_auditoria
            assert alvo.campo == "texto_pipe" and alvo.campo_identidade == "pipe"

    def test_legado_nunca_e_o_proprio_padrao_nem_vazio(self):
        """`legados` é a ÚNICA exceção ao 'não sobrescreve o admin' — não pode ser frouxo."""
        for alvo in ALVOS_POR_PIPE.values():
            for legado in alvo.legados:
                assert legado.strip()
                assert legado.strip() != alvo.padrao.strip()


class TestMatrizNosPipes:
    def test_doc_ausente_insere_no_pipe_certo(self):
        acao, ops = decidir(None, ALVO_CONF_PIPELINE)
        assert acao == ACAO_INSERIU
        assert ops["$set"]["pipe"] == "conf-pipeline"
        assert ops["$set"]["texto_pipe"] == KB_CONF_PIPELINE
        assert ops["$inc"] == {"versao": 1}
        # identidade no $set (não em $setOnInsert): um operador por path
        assert "$setOnInsert" not in ops

    def test_texto_versionado_antigo_recebe_o_novo(self):
        acao, ops = decidir(_doc("guia antigo", ORIGEM_VERSIONADO, "hashvelho123",
                                 pipe="conf-pipeline"), ALVO_CONF_PIPELINE)
        assert acao == ACAO_PROPAGOU
        assert ops["$set"]["texto_pipe"] == KB_CONF_PIPELINE

    def test_edicao_do_admin_e_preservada_nos_dois_pipes(self):
        for alvo in (ALVO_INICIO, ALVO_CONF_PIPELINE):
            acao, ops = decidir(_doc(TEXTO_ADMIN, ORIGEM_ADMIN, alvo.hash_padrao,
                                     pipe=alvo.identidade), alvo)
            assert (acao, ops) == (ACAO_PRESERVOU, None)

    def test_admin_com_padrao_novo_e_preservado_e_sinalizado(self):
        acao, ops = decidir(_doc(TEXTO_ADMIN, ORIGEM_ADMIN, "hashvelho123"), ALVO_INICIO)
        assert acao == ACAO_PRESERVOU_DESATUALIZADO
        assert ops is None      # o aviso é para a tela; o texto do admin não se toca

    def test_forcar_sobrescreve_o_admin(self):
        acao, ops = decidir(_doc(TEXTO_ADMIN, ORIGEM_ADMIN), ALVO_INICIO, forcar=True)
        assert acao == ACAO_FORCOU
        assert ops["$set"]["texto_pipe"] == TUTOR_INICIO_HTML


class TestPlaceholderLegado:
    """O `seed-mongodb.sh` insere uma frase única como texto de boas-vindas. Ela é NOSSA."""

    @pytest.mark.parametrize("origem", [None, ORIGEM_VERSIONADO, ORIGEM_ADMIN])
    def test_placeholder_recebe_o_texto_novo_em_qualquer_origem(self, origem):
        # Inclusive com `origem: admin`: é o caso realista de o admin abrir a tela, ver a frase
        # única e clicar em Salvar sem escrever nada seu — congelá-la seria o pior resultado.
        acao, ops = decidir(_doc(TUTOR_INICIO_LEGADO, origem), ALVO_INICIO)
        assert acao == ACAO_PROPAGOU
        assert ops["$set"]["texto_pipe"] == TUTOR_INICIO_HTML

    def test_sem_legados_o_mesmo_texto_seria_preservado(self):
        """Prova que é o registro de `legados` que muda o resultado, não outra coisa: mesmo alvo,
        mesmo documento, só sem a lista."""
        acao, _ = decidir(_doc(TUTOR_INICIO_LEGADO), replace(ALVO_INICIO, legados=()))
        assert acao == ACAO_NORMALIZOU_ADMIN


class TestRegressaoDoisEspacos:
    """Produção tinha `TUTOR_INICIO_HTML` + 2 espaços e sem `origem`. O seed antigo comparava com
    `==` de string bruta, caía no ramo de preservação e reportava "editado pelo admin" — então as
    boas-vindas não recebiam atualização nenhuma, sem sintoma visível."""

    def test_espaco_extra_e_reconhecido_como_o_padrao(self):
        acao, ops = decidir(_doc(TUTOR_INICIO_HTML + "  "), ALVO_INICIO)
        assert acao == ACAO_NORMALIZOU_VERSIONADO
        # Só metadado: reescrever o texto criaria entrada de histórico para uma não-mudança.
        assert "texto_pipe" not in ops["$set"]
        assert ops["$set"]["origem"] == ORIGEM_VERSIONADO

    def test_e_depois_de_normalizado_volta_a_receber_atualizacao(self):
        acao, ops = decidir(_doc("HTML de uma versão anterior", ORIGEM_VERSIONADO,
                                 ALVO_INICIO.hash_padrao), ALVO_INICIO)
        assert acao == ACAO_PROPAGOU

    def test_doc_legado_diferente_do_padrao_vira_admin_sem_baseline(self):
        acao, ops = decidir(_doc(TEXTO_ADMIN), ALVO_INICIO)
        assert acao == ACAO_NORMALIZOU_ADMIN
        assert ops["$set"] == {"origem": ORIGEM_ADMIN}
        assert "padrao_hash" not in ops["$set"]   # ausente = "não sei", e não acende aviso


class TestClassificarOrigem:
    def test_texto_igual_ao_padrao_e_versionado(self):
        assert classificar_origem(TUTOR_INICIO_HTML, ALVO_INICIO) == ORIGEM_VERSIONADO
        assert classificar_origem(f"\n{TUTOR_INICIO_HTML}  ", ALVO_INICIO) == ORIGEM_VERSIONADO

    def test_texto_proprio_e_admin(self):
        assert classificar_origem(TEXTO_ADMIN, ALVO_INICIO) == ORIGEM_ADMIN

    def test_padroes_diferentes_nao_se_confundem(self):
        assert classificar_origem(KB_CONF_PIPELINE, ALVO_INICIO) == ORIGEM_ADMIN
        assert classificar_origem(KB_CONF_PIPELINE, ALVO_CONF_PIPELINE) == ORIGEM_VERSIONADO


def _colecao(doc):
    return MagicMock(find_one=AsyncMock(return_value=doc), update_one=AsyncMock())


class TestAplicacaoNoBanco:
    @pytest.mark.asyncio
    async def test_insere_e_audita_na_aba_do_pipe(self):
        col, audit = _colecao(None), MagicMock(insert_one=AsyncMock())
        r = await semear_texto_do_tutor(ALVO_CONF_PIPELINE, col, audit)
        assert r["acao"] == ACAO_INSERIU
        assert col.update_one.await_args[0][0] == {"pipe": "conf-pipeline"}
        assert col.update_one.await_args[1]["upsert"] is True
        entrada = audit.insert_one.await_args[0][0]
        assert entrada["pipe"] == "conf-pipeline"
        assert entrada["campos_alterados"] == ["texto_pipe"]
        assert entrada["usuario_nome"] == "Seed do deploy"

    @pytest.mark.asyncio
    async def test_propagar_guarda_o_texto_que_saiu_do_ar(self):
        col, audit = _colecao(_doc(TUTOR_INICIO_LEGADO)), MagicMock(insert_one=AsyncMock())
        r = await semear_texto_do_tutor(ALVO_INICIO, col, audit)
        assert r["acao"] == ACAO_PROPAGOU
        assert audit.insert_one.await_args[0][0]["texto_anterior"] == TUTOR_INICIO_LEGADO

    @pytest.mark.asyncio
    async def test_preservar_nao_escreve_nem_audita(self):
        col, audit = _colecao(_doc(TEXTO_ADMIN, ORIGEM_ADMIN, "velho")), MagicMock(insert_one=AsyncMock())
        r = await semear_texto_do_tutor(ALVO_INICIO, col, audit)
        assert r["acao"] == ACAO_PRESERVOU_DESATUALIZADO and r["escreveu"] is False
        col.update_one.assert_not_awaited()
        audit.insert_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_normalizacao_escreve_metadado_sem_encher_o_historico(self):
        col, audit = _colecao(_doc(TUTOR_INICIO_HTML + "  ")), MagicMock(insert_one=AsyncMock())
        r = await semear_texto_do_tutor(ALVO_INICIO, col, audit)
        assert r["acao"] == ACAO_NORMALIZOU_VERSIONADO and r["escreveu"] is True
        col.update_one.assert_awaited_once()
        audit.insert_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_segunda_rodada_nao_faz_nada(self):
        col, audit = _colecao(_doc(TUTOR_INICIO_HTML, ORIGEM_VERSIONADO, ALVO_INICIO.hash_padrao)), \
            MagicMock(insert_one=AsyncMock())
        r = await semear_texto_do_tutor(ALVO_INICIO, col, audit)
        assert r["acao"] == ACAO_SEM_MUDANCA
        col.update_one.assert_not_awaited()


class TestResumoConcorda:
    """Sem concordância o log diria "Guia do conf-pipeline: preservada"."""

    def test_genero_e_numero_por_alvo(self):
        base = {"acao": ACAO_PRESERVOU, "chars_anteriores": 40, "chars": 100,
                "hash_novo": "x", "hash_anterior": None, "escreveu": False}
        assert "preservadas" in resumo_legivel(base, ALVO_INICIO)
        assert "preservado" in resumo_legivel(base, ALVO_CONF_PIPELINE)
        assert "Boas-vindas do tutor" in resumo_legivel(base, ALVO_INICIO)
        assert "Guia do conf-pipeline" in resumo_legivel(base, ALVO_CONF_PIPELINE)
