"""Testes das funções puras da base de conhecimento do tutor (sem banco)."""
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
