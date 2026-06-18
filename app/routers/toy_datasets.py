from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from pathlib import Path
import os
import logging
import pandas as pd

from app.models.dataset_config import (
    DatasetConfig, DatasetType, PreSplitStatus,
    get_all_datasets, get_dataset_config, TOY_DATASETS, UCI_DATASETS
)
from app.utils.seed import seed_everything, get_seed, get_sklearn_random_state
from app.database import arquivos, configuracoes_treinamento
from app.security import get_usuario_atual
from app.funcoes_genericas.funcoes_genericas import df_para_base64

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

router = APIRouter(prefix="/toy_datasets", tags=["Toy Datasets"])


@router.get("/")
async def listar_datasets(
    tipo: Optional[str] = Query(None, description="Filtrar por tipo: classificacao, regressao, agrupamento"),
    fonte: Optional[str] = Query(None, description="Filtrar por fonte: sklearn, uci")
):
    """Lista todos os datasets disponiveis com informacoes detalhadas."""
    datasets = get_all_datasets()
    
    result = []
    for ds in datasets.values():
        # Aplicar filtros
        if tipo and ds.tipo.value != tipo:
            continue
        if fonte and ds.fonte != fonte:
            continue
        result.append(ds.to_dict())
    
    return result


@router.get("/{dataset_name}")
async def carregar_dataset(
    dataset_name: str,
    seed: Optional[int] = Query(None, description="Seed para reprodutibilidade (opcional)"),
    n_amostras: Optional[int] = Query(None, ge=10, le=5000, description="(geradores) número de amostras"),
    n_features: Optional[int] = Query(None, ge=1, le=50, description="(geradores) número de atributos"),
    ruido: Optional[float] = Query(None, ge=0.0, le=10.0, description="(geradores) nível de ruído"),
    n_classes: Optional[int] = Query(None, ge=2, le=10, description="(geradores) número de classes"),
    n_clusters: Optional[int] = Query(None, ge=2, le=10, description="(geradores) número de grupos"),
    current_user: dict = Depends(get_usuario_atual),
):
    """Carrega um dataset e retorna no formato esperado pelo frontend."""
    ds = get_dataset_config(dataset_name)
    if ds is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_name}' nao encontrado")

    # Aplicar seed se fornecido
    if seed is not None:
        seed_everything(seed)

    try:
        df = None
        target_names = None

        # Carregar baseado na fonte
        if ds.fonte == "sklearn":
            df, target_names = _carregar_sklearn(dataset_name)
        elif ds.fonte == "uci":
            df = _carregar_uci(dataset_name, ds)
        elif ds.fonte == "gerador":
            df, target_names = _carregar_gerador(
                dataset_name, ds, n_amostras, n_features, ruido, n_classes, n_clusters
            )
        
        if df is None:
            raise HTTPException(status_code=500, detail="Erro ao carregar dataset")
        
        # Substituir target numerico por labels de texto se disponivel
        # O target real no dataframe e sempre "target" para sklearn datasets
        target_col = "target" if "target" in df.columns else ds.target
        
        if target_names is not None and target_col in df.columns:
            if df[target_col].dtype in ['int64', 'float64']:
                # Mapear inteiros para labels de texto
                df[target_col] = df[target_col].apply(lambda x: target_names[int(x)] if int(x) < len(target_names) else str(x))
        
        # Preparar dados
        colunas = list(df.columns)
        colunas_detalhes = []
        for col in colunas:
            tipo_col = "Número" if df[col].dtype in ['int64', 'float64'] else "Texto"
            colunas_detalhes.append({
                "nome_coluna": col,
                "tipo_coluna": tipo_col
            })

        # Dados para preview (limitar a 50 linhas)
        dados = df.head(50).to_dict(orient='records')

        # Informacoes do target
        tipo_target = None
        if target_col and target_col in df.columns:
            tipo_target = "Número" if df[target_col].dtype in ['int64', 'float64'] else "Texto"

        # Persistir no MongoDB para que o pipeline de treinamento encontre os IDs
        # - Salva o dataframe completo em 'arquivos' (content_treino_base64/content_teste_base64)
        # - Salva configuração inicial em 'configuracoes_treinamento'
        content_treino_b64 = df_para_base64(df)
        content_teste_b64 = df_para_base64(df.tail(max(1, len(df) // 4)))

        atributos_iniciais = {c: True for c in colunas}
        if target_col and target_col in colunas:
            atributos_iniciais[target_col] = False

        doc_arquivo = {
            "arquivo_nome_treino": f"{ds.nome}.xlsx",
            "arquivo_nome_teste": f"{ds.nome}_teste.xlsx",
            "content_treino_base64": content_treino_b64,
            "content_teste_base64": content_teste_b64,
            "fonte": "toy_dataset",
            "dataset_nome": ds.nome,
            "num_linhas_total": len(df),
            "num_linhas_treino": len(df),
            "num_linhas_teste": max(1, len(df) // 4),
            "num_colunas": len(colunas),
            "atributos": atributos_iniciais,
            "colunas_detalhes": colunas_detalhes,
            "usuario_id": str(current_user.get("_id", "")),
        }
        result_arquivo = await arquivos.insert_one(doc_arquivo)
        id_coleta = str(result_arquivo.inserted_id)

        doc_config = {
            "id_coleta": result_arquivo.inserted_id,
            "test_size": 0.25,
            "atributos": atributos_iniciais,
            "tipo_target": tipo_target,
            "target": target_col,
            "prever_categoria": ds.tipo == DatasetType.CLASSIFICATION,
            "dados_rotulados": target_col is not None,
            "fonte": "toy_dataset",
            "dataset_nome": ds.nome,
        }
        result_config = await configuracoes_treinamento.insert_one(doc_config)
        id_configuracoes_treinamento = str(result_config.inserted_id)

        return {
            "id_coleta": id_coleta,
            "id_configuracoes_treinamento": id_configuracoes_treinamento,
            "id": ds.id,
            "nome_dataset": ds.nome,
            "fonte": ds.fonte,
            "colunas": colunas,
            "colunas_detalhes": colunas_detalhes,
            "dados": dados,
            "total_dados": len(df),
            "target": target_col,
            "tipo_target": tipo_target,
            "prever_categoria": ds.tipo == DatasetType.CLASSIFICATION,
            "dados_rotulados": target_col is not None,
            "n_amostras": ds.n_amostras,
            "n_features": ds.n_features,
            "pre_split": ds.pre_split.value,
            "n_treino": ds.n_treino,
            "n_teste": ds.n_teste,
            "dificuldade": ds.dificuldade,
            "descricao_target": ds.descricao_target,
            "descricao_features": ds.descricao_features,
            "missao": ds.to_dict().get("missao"),
            "seed": get_seed()
        }
    
    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Biblioteca nao instalada: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar dataset: {str(e)}")


def _carregar_gerador(dataset_name, ds, n_amostras, n_features, ruido, n_classes, n_clusters):
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
    else:
        return None, None

    df = pd.DataFrame(X, columns=cols)
    # Clustering (blobs) nao expoe target; os demais sim.
    if ds.tipo != DatasetType.CLUSTERING:
        df["target"] = y
    return df, None


def _carregar_sklearn(dataset_name: str):
    """Carrega um dataset do sklearn."""
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


def _carregar_uci(dataset_name: str, ds: DatasetConfig = None):
    """Carrega um dataset do UCI via ucimlrepo, com cache em disco."""
    uci_id = UCI_IDS.get(dataset_name)
    if uci_id is None:
        raise HTTPException(status_code=400, detail=f"Dataset UCI '{dataset_name}' nao configurado")

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
            _carregar_uci(nome)
            logger.info("[cache UCI] dataset baixado para o cache: %s", nome)
        except Exception as exc:
            logger.warning("[cache UCI] falha ao pre-baixar '%s': %s", nome, exc)
