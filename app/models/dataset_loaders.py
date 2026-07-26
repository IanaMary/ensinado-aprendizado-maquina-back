"""Carregamento dos datasets de exemplo em DataFrame.

Extraído de `app/routers/toy_datasets.py` (onde eram funções privadas do router) para poder
ser reusado fora do fluxo de coleta — o desafio de montagem precisa **inspecionar** a base
(valores faltando, colunas de texto, escalas) sem criar coleta nem escrever no banco.

As três funções são puras: recebem o nome do dataset e devolvem o DataFrame. Quem persiste é
o router.
"""
from pathlib import Path
from typing import Optional, Tuple
import logging
import os

import pandas as pd

from app.models.dataset_config import DatasetConfig, DatasetType
from app.utils.seed import get_sklearn_random_state

logger = logging.getLogger("uvicorn")

# Cache em disco dos datasets UCI (ucimlrepo nao faz cache proprio).
# Fica na raiz do backend; sobrevive a restarts e ao git pull (nao versionado).
# Sobrescrevivel via DATASET_CACHE_DIR (usado nos testes para isolar o cache).
CACHE_DIR = Path(os.getenv("DATASET_CACHE_DIR") or (Path(__file__).resolve().parents[2] / "dataset_cache"))

# Mapeamento de dataset ID -> UCI ID
UCI_IDS = {
    "adult": 2,
    "wine_quality": 186,
    "heart_disease": 45,
    "titanic": 597,
    "abalone": 1,
    "housing": 601,
    "car_evaluation": 19,
    "mushroom": 73,
    # Datasets de Clustering
    "wholesale_customers": 292,
    "obesity_levels": 544,
    "online_shoppers": 468,
    "heart_failure": 519,
}


class DatasetNaoConfigurado(Exception):
    """Dataset UCI sem id mapeado em UCI_IDS."""


def carregar_gerador(dataset_name, ds, n_amostras=None, n_features=None, ruido=None,
                     n_classes=None, n_clusters=None) -> Tuple[Optional[pd.DataFrame], None]:
    """Gera um dataset sintetico com os make_* do sklearn. Retorna (df, target_names)."""
    from sklearn.datasets import (
        make_classification, make_blobs, make_moons, make_circles, make_regression
    )
    rs = get_sklearn_random_state()
    n = n_amostras or ds.n_amostras

    if dataset_name == "gen_classification":
        import math
        nf = n_features or ds.n_features
        nc = n_classes or 2
        # n_clusters_per_class=1 e n_informative suficiente p/ separar nc classes (2**n_inf >= nc).
        n_inf = min(nf, max(2, nf // 2, math.ceil(math.log2(nc))))
        X, y = make_classification(
            n_samples=n, n_features=nf, n_informative=n_inf, n_redundant=0,
            n_classes=nc, n_clusters_per_class=1, random_state=rs,
        )
        cols = [f"atributo_{i + 1}" for i in range(nf)]
    elif dataset_name == "gen_blobs":
        nf = n_features or 2
        X, y = make_blobs(n_samples=n, n_features=nf, centers=n_clusters or 3, random_state=rs)
        cols = [f"atributo_{i + 1}" for i in range(nf)]
    elif dataset_name == "gen_moons":
        X, y = make_moons(n_samples=n, noise=ruido if ruido is not None else 0.1, random_state=rs)
        cols = ["atributo_1", "atributo_2"]
    elif dataset_name == "gen_circles":
        X, y = make_circles(
            n_samples=n, noise=ruido if ruido is not None else 0.05, factor=0.5, random_state=rs
        )
        cols = ["atributo_1", "atributo_2"]
    elif dataset_name == "gen_regression":
        nf = n_features or ds.n_features
        X, y = make_regression(
            n_samples=n, n_features=nf, noise=ruido if ruido is not None else 10.0, random_state=rs
        )
        cols = [f"atributo_{i + 1}" for i in range(nf)]
    elif dataset_name == "gen_sorvete":
        # Regressão lúdica: prever vendas de sorvete a partir do calor e do movimento.
        # Valores em faixas amigáveis (não padronizados) p/ fazer sentido para crianças:
        # temperatura 15–40 °C, pessoas 0–500, vendas sempre >= 0.
        import numpy as np
        rng = np.random.RandomState(rs)
        temperatura = rng.uniform(15, 40, n)
        pessoas = rng.uniform(0, 500, n)
        rv = ruido if ruido is not None else 1.0
        y = np.clip(3.0 * (temperatura - 15) + 0.2 * pessoas + rng.normal(0, 12 * rv, n), 0, None).round()
        X = np.column_stack([temperatura.round(1), pessoas.round()])
        cols = ["temperatura", "pessoas_na_praia"]
    elif dataset_name == "gen_cardume":
        # Agrupamento lúdico: separar peixinhos em cardumes (sem target).
        X, y = make_blobs(n_samples=n, n_features=2, centers=n_clusters or 3, random_state=rs)
        cols = ["velocidade", "direcao"]
    elif dataset_name == "gen_cachorro":
        # Regressão lúdica: descobrir o PESO do cachorro pela ALTURA dele.
        # Faixas amigáveis: altura 20–70 cm, peso sempre >= 1 kg, com correlação
        # positiva (cachorro mais alto tende a ser mais pesado) + um pouco de ruído.
        import numpy as np
        rng = np.random.RandomState(rs)
        altura = rng.uniform(20, 70, n)
        rv = ruido if ruido is not None else 1.0
        peso = np.clip(0.6 * (altura - 15) + rng.normal(0, 3 * rv, n), 1, None).round(1)
        X = altura.round(1).reshape(-1, 1)
        y = peso
        cols = ["altura_cm"]
    else:
        return None, None

    df = pd.DataFrame(X, columns=cols)
    # Clustering (blobs) nao expoe target; os demais sim.
    if ds.tipo != DatasetType.CLUSTERING:
        df["target"] = y
    return df, None


def carregar_sklearn(dataset_name: str):
    """Carrega um dataset do sklearn. Retorna (df, target_names)."""
    from sklearn.datasets import (
        load_iris, load_wine, load_breast_cancer, load_digits,
        load_diabetes, fetch_california_housing
    )

    loaders = {
        "iris": load_iris,
        "wine": load_wine,
        "breast_cancer": load_breast_cancer,
        "diabetes": load_diabetes,
        "california_housing": fetch_california_housing,
    }

    if dataset_name == "digits":
        data = load_digits(as_frame=True)
        df = data.frame
        df['target'] = data.target
        return df, None

    if dataset_name in loaders:
        data = loaders[dataset_name](as_frame=True)
        df = data.frame
        # Retornar target_names se existir (para mapear inteiros para labels)
        target_names = getattr(data, 'target_names', None)
        return df, target_names

    return None, None


def carregar_uci(dataset_name: str, ds: DatasetConfig = None) -> pd.DataFrame:
    """Carrega um dataset do UCI via ucimlrepo, com cache em disco."""
    uci_id = UCI_IDS.get(dataset_name)
    if uci_id is None:
        raise DatasetNaoConfigurado(f"Dataset UCI '{dataset_name}' nao configurado")

    cache_path = CACHE_DIR / f"{dataset_name}.pkl"
    if cache_path.exists():
        try:
            return pd.read_pickle(cache_path)
        except Exception:
            # Cache corrompido: ignora e rebaixa abaixo.
            pass

    from ucimlrepo import fetch_ucirepo
    dataset = fetch_ucirepo(id=uci_id)
    df = dataset.data.original

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_pickle(cache_path)
    except Exception:
        # Falha ao gravar cache nao deve quebrar o request.
        pass

    return df


def prewarm_uci_cache():
    """Pre-baixa todos os datasets UCI para o cache em disco.

    Pensado para rodar no startup do servidor: na primeira execucao baixa tudo;
    nos restarts seguintes vira no-op rapido (cache ja em disco). Failsafe: uma
    falha de rede em um dataset apenas registra log e segue para o proximo.
    """
    for nome in UCI_IDS:
        cache_path = CACHE_DIR / f"{nome}.pkl"
        if cache_path.exists():
            continue
        try:
            carregar_uci(nome)
            logger.info("[cache UCI] dataset baixado para o cache: %s", nome)
        except Exception as exc:
            logger.warning("[cache UCI] falha ao pre-baixar '%s': %s", nome, exc)


def carregar_dataframe(dataset_name: str, ds: DatasetConfig) -> Optional[pd.DataFrame]:
    """DataFrame de um dataset de exemplo, escolhendo o carregador pela `fonte`."""
    if ds.fonte == "sklearn":
        df, _ = carregar_sklearn(dataset_name)
        return df
    if ds.fonte == "uci":
        return carregar_uci(dataset_name, ds)
    if ds.fonte == "gerador":
        df, _ = carregar_gerador(dataset_name, ds)
        return df
    return None
