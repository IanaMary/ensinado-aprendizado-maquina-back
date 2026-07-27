"""Testes do conteúdo versionado e do loader idempotente (app/conteudo)."""
import pytest

from app.conteudo.loader import (
    CATEGORIAS,
    carregar_conteudo,
    montar_operacoes_upsert,
    validar_conteudo,
)
from app.metricas.metricas import GRAFICOS_IDS
from app.pre_processamento.catalogo import PRE_PROCESSAMENTO_CATALOGO


# Contagem esperada por categoria (gate de completude do conteúdo versionado).
_CONTAGEM_ESPERADA = {
    "modelos": 24,
    "metricas": 12,
    "pre_processamento": 10,
    "coleta_dados": 5,
    "graficos": 10,
}


@pytest.mark.parametrize("categoria", list(CATEGORIAS))
def test_json_parseia_e_valida(categoria):
    """Todo item de cada JSON parseia e valida contra o schema Conteudo."""
    docs = carregar_conteudo(categoria)
    assert isinstance(docs, dict)
    for valor, conteudo in docs.items():
        assert conteudo, f"{categoria}/{valor} tem conteudo vazio"
        validar_conteudo(conteudo)  # lança se malformado


@pytest.mark.parametrize("categoria,esperado", list(_CONTAGEM_ESPERADA.items()))
def test_contagem_por_categoria(categoria, esperado):
    docs = carregar_conteudo(categoria)
    assert len(docs) == esperado, f"{categoria}: {len(docs)} itens, esperado {esperado}"


def test_upsert_set_apenas_conteudo():
    """Garantia de segurança: o $set do loader NUNCA toca execucao/habilitado —
    só `conteudo`. Campos de identidade vão em $setOnInsert."""
    for categoria in CATEGORIAS:
        docs = carregar_conteudo(categoria)
        for filtro, update in montar_operacoes_upsert(categoria, docs):
            assert set(update["$set"].keys()) == {"conteudo"}
            assert "execucao" not in update["$set"]
            assert "habilitado" not in update["$set"]
            assert filtro.get("valor")
            assert "execucao" not in update["$setOnInsert"]


def test_graficos_casam_com_GRAFICOS_IDS():
    docs = carregar_conteudo("graficos")
    assert set(docs.keys()) == set(GRAFICOS_IDS.keys())


def test_pre_processamento_subset_do_catalogo():
    docs = carregar_conteudo("pre_processamento")
    for valor in docs:
        assert valor in PRE_PROCESSAMENTO_CATALOGO, f"pré-proc desconhecido: {valor}"


@pytest.mark.parametrize("categoria", ["modelos", "graficos"])
def test_modelos_e_graficos_tem_link(categoria):
    """Modelos e gráficos devem ter link (sklearn ou yellowbrick)."""
    docs = carregar_conteudo(categoria)
    for valor, c in docs.items():
        assert c.get("link_sklearn") or c.get("link_yellowbrick"), f"{categoria}/{valor} sem link"


@pytest.mark.parametrize("categoria", ["modelos", "metricas", "pre_processamento"])
def test_tem_basico_e_avancado(categoria):
    """Todo item tem modo Básico (resumo_basico) e Avançado (descricao)."""
    docs = carregar_conteudo(categoria)
    for valor, c in docs.items():
        assert c.get("resumo_basico"), f"{categoria}/{valor} sem resumo_basico (Básico)"
        assert c.get("descricao"), f"{categoria}/{valor} sem descricao (Avançado)"


# ------------------------------------------------------------------ modo Avançado
# O que cada categoria precisa entregar no modo Avançado. Fica explícito por categoria porque
# as exigências diferem: um gráfico não "otimiza" nada no sentido de um modelo, e uma fonte de
# coleta não tem fórmula. Deixar genérico esconderia buraco.
EXIGENCIAS_AVANCADO = {
    "modelos": {
        "fundamentos": ["formula", "otimiza", "pressupostos", "complexidade"],
        "pratica": ["codigo", "tuning", "armadilhas", "diagnostico"],
    },
    "metricas": {
        "fundamentos": ["formula", "otimiza", "pressupostos", "complexidade", "leitura"],
        "pratica": ["codigo", "armadilhas", "diagnostico"],
    },
    "pre_processamento": {
        "fundamentos": ["formula", "otimiza", "pressupostos", "complexidade"],
        "pratica": ["codigo", "armadilhas", "diagnostico"],
    },
    "graficos": {
        "fundamentos": ["otimiza", "pressupostos", "complexidade", "leitura"],
        "pratica": ["codigo", "armadilhas", "diagnostico"],
    },
    "coleta_dados": {
        "fundamentos": ["otimiza", "pressupostos", "complexidade", "leitura"],
        "pratica": ["codigo", "armadilhas", "diagnostico"],
    },
}


@pytest.mark.parametrize("categoria", list(EXIGENCIAS_AVANCADO))
def test_blocos_do_avancado_completos(categoria):
    """O Avançado prometia mais do que entregava: 0/24 modelos tinham fórmula, embora a
    documentação dissesse 'descrição técnica, fórmula, código e link'. Agora é cobrado."""
    exigido = EXIGENCIAS_AVANCADO[categoria]
    for valor, c in carregar_conteudo(categoria).items():
        for bloco, campos in exigido.items():
            dados = c.get(bloco) or {}
            assert dados, f"{categoria}/{valor}: bloco '{bloco}' ausente"
            for campo in campos:
                assert dados.get(campo), f"{categoria}/{valor}: {bloco}.{campo} vazio"


@pytest.mark.parametrize("categoria", list(EXIGENCIAS_AVANCADO))
def test_codigo_do_avancado_e_executavel_de_verdade(categoria):
    """O bloco 'Na prática' existe para mostrar o caminho real, não um trecho decorativo."""
    for valor, c in carregar_conteudo(categoria).items():
        codigo = (c.get("pratica") or {}).get("codigo", "")
        assert "import" in codigo, f"{categoria}/{valor}: código sem import"


@pytest.mark.parametrize("categoria", list(EXIGENCIAS_AVANCADO))
def test_formula_do_card_espelha_fundamentos(categoria):
    """O card lê `formula`; o bloco Fundamentos também a tem. Se divergirem, o aluno vê uma
    fórmula no topo e outra embaixo."""
    for valor, c in carregar_conteudo(categoria).items():
        do_bloco = (c.get("fundamentos") or {}).get("formula")
        if c.get("formula") or do_bloco:
            assert c.get("formula") == do_bloco, f"{categoria}/{valor}: fórmulas divergentes"
