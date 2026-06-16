"""Testes da execução com pré-processamento aplicado de verdade.

Garante o que estava quebrado antes: o pré-processamento montado no pipeline
gráfico agora vira um sklearn Pipeline serializado junto do modelo — então o
modelo treinado corresponde ao código gerado, e `predict()` aplica as
transformações sobre X cru.
"""
from __future__ import annotations

import io

import joblib
import numpy as np
import pandas as pd
import pytest

from app.pre_processamento import (
    PRE_PROCESSAMENTO_CATALOGO,
    catalogo_com_overrides,
    montar_specs_pre_processamento,
    normalizar_execucao_db,
    tem_imputer,
)
from app.sandbox import SandboxError, executar_treinamento


@pytest.fixture
def dados():
    X = pd.DataFrame(
        {
            "f1": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            "f2": [80.0, 70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0],
        }
    )
    y = pd.Series([0, 0, 0, 0, 1, 1, 1, 1], name="target")
    return X, y


# ----------------------------- catálogo -----------------------------

def test_montar_specs_filtra_encode_y_e_encoders_sem_colunas():
    itens = [
        {"valor": "standard_scaler"},
        {"valor": "label_encoder", "colunas": ["target"]},  # encode_y -> descartado
        {"valor": "onehot_encoder"},  # colunas_escolhidas sem colunas -> descartado
        {"valor": "inexistente"},  # desconhecido -> descartado
    ]
    specs = montar_specs_pre_processamento(itens)
    valores = [s["valor"] for s in specs]
    assert valores == ["standard_scaler"]
    assert specs[0]["modulo"] == "sklearn.preprocessing"
    assert specs[0]["classe"] == "StandardScaler"


def test_montar_specs_mantem_colunas_e_encoder_com_colunas():
    itens = [{"valor": "onehot_encoder", "colunas": ["cidade"]}]
    specs = montar_specs_pre_processamento(itens)
    assert len(specs) == 1
    assert specs[0]["classe"] == "OneHotEncoder"
    assert specs[0]["colunas"] == ["cidade"]


def test_tem_imputer():
    assert tem_imputer([{"valor": "simple_imputer"}]) is True
    assert tem_imputer([{"valor": "standard_scaler"}]) is False
    assert tem_imputer([]) is False


def test_normalizar_execucao_db_converte_lista_para_kwargs():
    norm = normalizar_execucao_db(
        {
            "modulo": "sklearn.impute",
            "classe": "SimpleImputer",
            "hiperparametros": [{"nome": "strategy", "valorPadrao": "median"}],
            "aplica_em": "todas",
            "trata_ausentes": True,
        }
    )
    assert norm["modulo"] == "sklearn.impute"
    assert norm["hiperparametros"] == {"strategy": "median"}
    assert norm["trata_ausentes"] is True


def test_normalizar_execucao_db_incompleta_retorna_none():
    assert normalizar_execucao_db({"classe": "X"}) is None
    assert normalizar_execucao_db(None) is None


def test_catalogo_com_overrides_db_tem_prioridade():
    docs = [
        {
            "valor": "standard_scaler",
            "execucao": {
                "modulo": "sklearn.preprocessing",
                "classe": "MaxAbsScaler",  # override troca a classe
                "hiperparametros": [],
                "aplica_em": "todas",
            },
        },
        {
            "valor": "novo_scaler",  # item só no DB
            "execucao": {
                "modulo": "sklearn.preprocessing",
                "classe": "QuantileTransformer",
                "hiperparametros": [],
                "aplica_em": "todas",
            },
        },
    ]
    catalogo = catalogo_com_overrides(docs)
    assert catalogo["standard_scaler"]["classe"] == "MaxAbsScaler"
    assert catalogo["novo_scaler"]["classe"] == "QuantileTransformer"
    # built-ins não sobrescritos permanecem
    assert catalogo["minmax_scaler"]["classe"] == "MinMaxScaler"


def test_montar_specs_usa_override_de_catalogo():
    catalogo = catalogo_com_overrides(
        [
            {
                "valor": "novo_scaler",
                "execucao": {
                    "modulo": "sklearn.preprocessing",
                    "classe": "MaxAbsScaler",
                    "hiperparametros": [],
                    "aplica_em": "todas",
                },
            }
        ]
    )
    specs = montar_specs_pre_processamento([{"valor": "novo_scaler"}], catalogo)
    assert len(specs) == 1
    assert specs[0]["classe"] == "MaxAbsScaler"


def test_catalogo_cobre_os_dez_pre_processadores():
    esperados = {
        "standard_scaler", "minmax_scaler", "robust_scaler", "normalizer",
        "onehot_encoder", "ordinal_encoder", "label_encoder", "simple_imputer",
        "polynomial_features", "power_transformer",
    }
    assert esperados <= set(PRE_PROCESSAMENTO_CATALOGO)


# ----------------------------- execução -----------------------------

def test_scaler_vira_pipeline_serializado(dados):
    X, y = dados
    specs = montar_specs_pre_processamento([{"valor": "standard_scaler"}])
    res = executar_treinamento(
        class_path="sklearn.linear_model.LogisticRegression",
        hiperparametros={"max_iter": 200},
        X_train=X,
        y_train=y,
        is_clustering=False,
        pre_processamento=specs,
    )
    assert "Pipeline" in res.model_repr
    assert "StandardScaler" in res.model_repr
    assert set(res.classes) == {"0", "1"}

    # O Pipeline serializado aplica o scaler internamente sobre X cru.
    modelo = joblib.load(io.BytesIO(res.model_bytes))
    from sklearn.pipeline import Pipeline

    assert isinstance(modelo, Pipeline)
    preds = modelo.predict(X)
    assert len(preds) == len(X)


def test_imputer_permite_treinar_com_valores_ausentes(dados):
    X, y = dados
    X = X.copy()
    X.loc[2, "f1"] = np.nan  # buraco que antes derrubava o treino
    specs = montar_specs_pre_processamento([{"valor": "simple_imputer"}])
    res = executar_treinamento(
        class_path="sklearn.linear_model.LogisticRegression",
        hiperparametros={"max_iter": 200},
        X_train=X,
        y_train=y,
        is_clustering=False,
        pre_processamento=specs,
    )
    modelo = joblib.load(io.BytesIO(res.model_bytes))
    # predict aceita X com NaN — o imputer dentro do Pipeline preenche.
    preds = modelo.predict(X)
    assert len(preds) == len(X)


def test_scaler_em_colunas_especificas_usa_column_transformer(dados):
    X, y = dados
    specs = montar_specs_pre_processamento(
        [{"valor": "standard_scaler", "colunas": ["f1"]}]
    )
    res = executar_treinamento(
        class_path="sklearn.linear_model.LogisticRegression",
        hiperparametros={"max_iter": 200},
        X_train=X,
        y_train=y,
        is_clustering=False,
        pre_processamento=specs,
    )
    assert "ColumnTransformer" in res.model_repr
    modelo = joblib.load(io.BytesIO(res.model_bytes))
    assert len(modelo.predict(X)) == len(X)


def test_duas_etapas_imputer_depois_scaler(dados):
    X, y = dados
    X = X.copy()
    X.loc[3, "f2"] = np.nan
    specs = montar_specs_pre_processamento(
        [{"valor": "simple_imputer"}, {"valor": "minmax_scaler"}]
    )
    res = executar_treinamento(
        class_path="sklearn.tree.DecisionTreeClassifier",
        hiperparametros={},
        X_train=X,
        y_train=y,
        is_clustering=False,
        pre_processamento=specs,
    )
    modelo = joblib.load(io.BytesIO(res.model_bytes))
    assert len(modelo.predict(X)) == len(X)


def test_sem_pre_processamento_continua_estimador_simples(dados):
    X, y = dados
    res = executar_treinamento(
        class_path="sklearn.linear_model.LogisticRegression",
        hiperparametros={"max_iter": 100},
        X_train=X,
        y_train=y,
        is_clustering=False,
        pre_processamento=[],
    )
    assert "Pipeline" not in res.model_repr
    assert "LogisticRegression" in res.model_repr


def test_clustering_com_scaler(dados):
    X, _ = dados
    specs = montar_specs_pre_processamento([{"valor": "standard_scaler"}])
    res = executar_treinamento(
        class_path="sklearn.cluster.KMeans",
        hiperparametros={"n_clusters": 2, "n_init": 10, "random_state": 0},
        X_train=X,
        y_train=None,
        is_clustering=True,
        pre_processamento=specs,
    )
    # classes vêm de labels_ do estimador final dentro do Pipeline.
    assert set(res.classes) == {"0", "1"}
