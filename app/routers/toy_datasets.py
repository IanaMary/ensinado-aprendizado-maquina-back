from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import pandas as pd

from app.models.dataset_config import (
    DatasetConfig, DatasetType, PreSplitStatus,
    get_all_datasets, get_dataset_config, TOY_DATASETS, UCI_DATASETS
)
from app.utils.seed import seed_everything, get_seed

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
    seed: Optional[int] = Query(None, description="Seed para reprodutibilidade (opcional)")
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
        
        # Carregar baseado na fonte
        if ds.fonte == "sklearn":
            df = _carregar_sklearn(dataset_name)
        elif ds.fonte == "uci":
            df = _carregar_uci(dataset_name, ds)
        
        if df is None:
            raise HTTPException(status_code=500, detail="Erro ao carregar dataset")
        
        # Preparar dados
        colunas = list(df.columns)
        colunas_detalhes = []
        for col in colunas:
            tipo = "Numerico" if df[col].dtype in ['int64', 'float64'] else "Texto"
            colunas_detalhes.append({
                "nome_coluna": col,
                "tipo_coluna": tipo
            })
        
        # Dados para preview (limitar a 50 linhas)
        dados = df.head(50).to_dict(orient='records')
        
        # Informacoes do target
        target = ds.target
        tipo_target = None
        if target and target in df.columns:
            tipo_target = "number" if df[target].dtype in ['int64', 'float64'] else "string"
        
        return {
            "nome_dataset": ds.nome,
            "fonte": ds.fonte,
            "colunas": colunas,
            "colunas_detalhes": colunas_detalhes,
            "dados": dados,
            "total_dados": len(df),
            "target": target,
            "tipo_target": tipo_target,
            "prever_categoria": ds.tipo == DatasetType.CLASSIFICATION,
            "dados_rotulados": target is not None,
            "n_amostras": ds.n_amostras,
            "n_features": ds.n_features,
            "pre_split": ds.pre_split.value,
            "n_treino": ds.n_treino,
            "n_teste": ds.n_teste,
            "dificuldade": ds.dificuldade,
            "descricao_target": ds.descricao_target,
            "descricao_features": ds.descricao_features,
            "seed": get_seed()
        }
    
    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Biblioteca nao instalada: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar dataset: {str(e)}")


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
        return df
    
    if dataset_name in loaders:
        data = loaders[dataset_name](as_frame=True)
        return data.frame
    
    return None


def _carregar_uci(dataset_name: str, ds: DatasetConfig):
    """Carrega um dataset do UCI via ucimlrepo."""
    from ucimlrepo import fetch_ucirepo
    
    # Mapeamento de dataset ID para UCI ID
    uci_ids = {
        "adult": 2,
        "wine_quality": 186,
        "heart_disease": 45,
        "titanic": 597,
        "abalone": 1,
        "housing": 601,
        "car_evaluation": 19,
        "mushroom": 73,
    }
    
    uci_id = uci_ids.get(dataset_name)
    if uci_id is None:
        raise HTTPException(status_code=400, detail=f"Dataset UCI '{dataset_name}' nao configurado")
    
    dataset = fetch_ucirepo(id=uci_id)
    df = dataset.data.original
    
    return df
