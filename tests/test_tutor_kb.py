"""Testes das funções puras da base de conhecimento do tutor (sem banco)."""
from app import tutor_kb
from app.tutor_kb import _resumo_compacto, _valores_no_contexto


def test_resumo_compacto_modelo_inclui_padroes_e_doc():
    c = {
        "titulo": "K Vizinhos",
        "resumo_basico": "Olha os vizinhos mais parecidos e copia a maioria.",
        "quandoUsar": ["poucos dados", "fronteiras irregulares"],
        "naoUsarQuando": ["muitas dimensões"],
        "hiperparametros_doc": [
            {"nome": "n_neighbors", "default": 5},
            {"nome": "weights", "default": "uniform"},
        ],
        "link_sklearn": "https://scikit-learn.org/x.html",
    }
    out = _resumo_compacto("knn", c, "modelo")
    assert "K Vizinhos" in out and "`knn`" in out
    assert "vizinhos mais parecidos" in out
    assert "n_neighbors=5" in out and "weights=uniform" in out
    assert "Quando usar:" in out and "Evitar quando:" in out
    assert "https://scikit-learn.org/x.html" in out


def test_resumo_compacto_metrica_inclui_formula():
    c = {"titulo": "Acurácia", "resumo_basico": "Porcentagem de acertos.",
         "formula": "acertos / total"}
    out = _resumo_compacto("accuracy_score", c, "métrica/classificacao")
    assert "Acurácia" in out and "Fórmula: acertos / total" in out


def test_valores_no_contexto_detecta_itens_citados():
    valores = {"knn", "random_forest", "accuracy_score", "svm"}
    contexto = {"modelo": {"valor": "random_forest"}, "metricas": ["accuracy_score"]}
    achados = _valores_no_contexto(contexto, valores)
    assert "random_forest" in achados and "accuracy_score" in achados
    assert "knn" not in achados and "svm" not in achados


def test_valores_no_contexto_vazio():
    assert _valores_no_contexto(None, {"knn"}) == []
    assert _valores_no_contexto({"x": 1}, set()) == []


# ------------------------------------------------------------------ nível do aluno
CONTEUDO_RICO = {
    "titulo": "k-NN",
    "resumo_basico": "Olha quem está por perto e copia a resposta da maioria.",
    "descricao": "Classificador não paramétrico baseado em instâncias: " + ("x" * 800),
    "formula": "argmax_c Σ_{i∈N_k(x)} 1[y_i = c]",
    "quandoUsar": ["Poucos dados", "Fronteiras irregulares"],
    "hiperparametros_doc": [
        {"nome": "n_neighbors", "default": 5, "tipo": "int", "faixa": "1–50",
         "efeito": "k baixo decora, k alto suaviza",
         "quando_ajustar": "quando o erro de treino e teste divergem"},
    ],
    "fundamentos": {
        "otimiza": "nada — memoriza o conjunto de treino",
        "pressupostos": ["Distância é significativa", "Atributos na mesma escala"],
        "complexidade": "treino O(1); predição O(n·d) por consulta",
    },
    "pratica": {
        "tuning": ["n_neighbors antes de weights"],
        "armadilhas": ["Sem escalar, a coluna de maior amplitude domina"],
        "diagnostico": ["Acurácia cai muito com k=1: memorização"],
    },
    "referencias": [{"titulo": "Cover & Hart (1967)", "autor": "T. Cover, P. Hart"}],
    "link_sklearn": "https://scikit-learn.org/stable/modules/generated/sklearn.neighbors.KNeighborsClassifier.html",
}


class TestNivelDaFicha:
    def test_basico_mantem_o_texto_simples_e_so_os_padroes(self):
        ficha = tutor_kb._resumo_compacto("knn", CONTEUDO_RICO, "modelo")
        assert "copia a resposta da maioria" in ficha
        assert "n_neighbors=5" in ficha
        # nada do material avançado vaza para o básico
        assert "Complexidade:" not in ficha and "Pressupostos:" not in ficha
        assert "quando o erro de treino e teste divergem" not in ficha

    def test_avancado_manda_o_conteudo_tecnico_ao_llm(self):
        """Era o furo: a descrição técnica nunca chegava ao modelo (o básico vencia sempre)."""
        ficha = tutor_kb._resumo_compacto("knn", CONTEUDO_RICO, "modelo", nivel="avancado")
        assert "Classificador não paramétrico" in ficha
        assert "Fórmula: argmax_c" in ficha
        assert "Complexidade: treino O(1)" in ficha
        assert "Pressupostos: Distância é significativa" in ficha
        assert "k baixo decora" in ficha and "1–50" in ficha
        assert "Armadilhas: Sem escalar" in ficha
        assert "Leitura: Cover & Hart (1967)" in ficha

    def test_avancado_nao_mutila_a_descricao_em_500_chars(self):
        ficha = tutor_kb._resumo_compacto("knn", CONTEUDO_RICO, "modelo", nivel="avancado")
        assert len(ficha) > 900, "a descrição técnica mediana (508) e a maior (936) precisam caber"

    def test_nivel_vem_do_contexto_e_o_padrao_e_basico(self):
        assert tutor_kb._nivel_do_contexto({"nivel": "avancado"}) == "avancado"
        assert tutor_kb._nivel_do_contexto({"nivel": "AVANCADO"}) == "avancado"
        assert tutor_kb._nivel_do_contexto({"nivel": "basico"}) == "basico"
        assert tutor_kb._nivel_do_contexto({}) == "basico"
        assert tutor_kb._nivel_do_contexto(None) == "basico"
        assert tutor_kb._nivel_do_contexto("texto solto") == "basico"
