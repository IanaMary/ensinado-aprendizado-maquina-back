"""Testes do sandbox de execução (subprocess + setrlimit)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import joblib
import pandas as pd
import pytest

from app.sandbox import SandboxError, executar_treinamento
from app.sandbox import runner as runner_mod


@pytest.fixture
def iris_like():
    df = pd.DataFrame(
        {
            "f1": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            "f2": [8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0],
        }
    )
    y = pd.Series([0, 0, 0, 0, 1, 1, 1, 1], name="target")
    return df, y


def test_treina_modelo_supervisionado(iris_like):
    X, y = iris_like
    res = executar_treinamento(
        class_path="sklearn.linear_model.LogisticRegression",
        hiperparametros={"max_iter": 200},
        X_train=X,
        y_train=y,
        is_clustering=False,
    )
    assert res.model_bytes
    assert "LogisticRegression" in res.model_repr
    assert set(res.classes) == {"0", "1"}
    assert res.params.get("max_iter") == 200

    # Modelo serializado deve carregar com joblib no pai e prever.
    import io

    modelo = joblib.load(io.BytesIO(res.model_bytes))
    preds = modelo.predict(X)
    assert len(preds) == len(X)


def test_treina_clustering(iris_like):
    X, _ = iris_like
    res = executar_treinamento(
        class_path="sklearn.cluster.KMeans",
        hiperparametros={"n_clusters": 2, "n_init": 10, "random_state": 0},
        X_train=X,
        y_train=None,
        is_clustering=True,
    )
    assert set(res.classes) == {"0", "1"}


def test_classe_inexistente_vira_sandbox_error(iris_like):
    X, y = iris_like
    with pytest.raises(SandboxError) as exc:
        executar_treinamento(
            class_path="sklearn.linear_model.NaoExisteEsseClassificador",
            hiperparametros={},
            X_train=X,
            y_train=y,
            is_clustering=False,
        )
    assert exc.value.kind == "exception"


def test_hiperparametro_invalido_vira_sandbox_error(iris_like):
    X, y = iris_like
    with pytest.raises(SandboxError):
        executar_treinamento(
            class_path="sklearn.linear_model.LogisticRegression",
            hiperparametros={"param_que_nao_existe": 42},
            X_train=X,
            y_train=y,
            is_clustering=False,
        )


def test_y_train_obrigatorio_em_supervisionado(iris_like):
    X, _ = iris_like
    with pytest.raises(SandboxError) as exc:
        executar_treinamento(
            class_path="sklearn.linear_model.LogisticRegression",
            hiperparametros={},
            X_train=X,
            y_train=None,
            is_clustering=False,
        )
    assert exc.value.kind == "config"


def test_workdir_e_limpo_apos_execucao(iris_like, monkeypatch):
    """Garante que o tempdir é removido mesmo em caminho feliz."""
    X, y = iris_like
    criados: list[str] = []
    real_mkdtemp = tempfile.mkdtemp

    def spy_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        criados.append(path)
        return path

    monkeypatch.setattr(runner_mod.tempfile, "mkdtemp", spy_mkdtemp)
    executar_treinamento(
        class_path="sklearn.linear_model.LogisticRegression",
        hiperparametros={"max_iter": 50},
        X_train=X,
        y_train=y,
        is_clustering=False,
    )
    assert criados, "mkdtemp deveria ter sido chamado"
    for path in criados:
        assert not Path(path).exists(), f"tempdir não foi removido: {path}"


def test_workdir_e_limpo_apos_erro(iris_like, monkeypatch):
    X, y = iris_like
    criados: list[str] = []
    real_mkdtemp = tempfile.mkdtemp

    def spy_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        criados.append(path)
        return path

    monkeypatch.setattr(runner_mod.tempfile, "mkdtemp", spy_mkdtemp)
    with pytest.raises(SandboxError):
        executar_treinamento(
            class_path="sklearn.modulo_que_nao_existe.X",
            hiperparametros={},
            X_train=X,
            y_train=y,
            is_clustering=False,
        )
    for path in criados:
        assert not Path(path).exists(), f"tempdir não foi removido: {path}"


@pytest.mark.skipif(
    os.environ.get("ENABLE_SLOW_SANDBOX_TESTS") != "1",
    reason="teste lento; defina ENABLE_SLOW_SANDBOX_TESTS=1 para rodar",
)
def test_timeout_dispara_sandbox_error():
    """MLPClassifier com max_iter alto + dataset grande estoura o wall-clock."""
    import numpy as np

    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(2000, 20)))
    y = pd.Series(rng.integers(0, 2, size=2000))
    with pytest.raises(SandboxError) as exc:
        executar_treinamento(
            class_path="sklearn.neural_network.MLPClassifier",
            hiperparametros={"max_iter": 5000, "hidden_layer_sizes": (200, 200, 200)},
            X_train=X,
            y_train=y,
            is_clustering=False,
            max_wall_sec=2,
            max_cpu_sec=2,
        )
    assert exc.value.kind in ("timeout", "memory", "exception")
