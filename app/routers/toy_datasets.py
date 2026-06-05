from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
import pandas as pd

from app.models.dataset_config import (
    DatasetConfig, DatasetType, PreSplitStatus,
    get_all_datasets, get_dataset_config, TOY_DATASETS, UCI_DATASETS
)
from app.utils.seed import seed_everything, get_seed
from app.database import arquivos, configuracoes_treinamento
from app.security import get_usuario_atual
from app.funcoes_genericas.funcoes_genericas import df_para_base64

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
        return df, None
    
    if dataset_name in loaders:
        data = loaders[dataset_name](as_frame=True)
        df = data.frame
        # Retornar target_names se existir (para mapear inteiros para labels)
        target_names = getattr(data, 'target_names', None)
        return df, target_names
    
    return None, None


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
