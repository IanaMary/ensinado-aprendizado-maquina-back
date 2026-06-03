from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import pandas as pd

router = APIRouter(prefix="/toy_datasets", tags=["Toy Datasets"])


class ToyDatasetInfo(BaseModel):
    nome: str
    valor: str
    descricao: str
    fonte: str  # sklearn ou uci
    tipo: str  # classificacao ou regressao
    n_amostras: int
    n_features: int
    target: str


TOY_DATASETS = {
    # Sklearn Toy Datasets
    "iris": {
        "nome": "Iris",
        "valor": "iris",
        "descricao": "Dataset clássico com 150 flores iris, 4 atributos numéricos e 3 classes.",
        "fonte": "sklearn",
        "tipo": "classificacao",
        "n_amostras": 150,
        "n_features": 4,
        "target": "species"
    },
    "wine": {
        "nome": "Wine",
        "valor": "wine",
        "descricao": "Análise de vinhos com 13 atributos químicos e 3 classes de cultivares.",
        "fonte": "sklearn",
        "tipo": "classificacao",
        "n_amostras": 178,
        "n_features": 13,
        "target": "target"
    },
    "breast_cancer": {
        "nome": "Breast Cancer",
        "valor": "breast_cancer",
        "descricao": "Diagnóstico de câncer de mama com 30 atributos e 2 classes (maligno/benigno).",
        "fonte": "sklearn",
        "tipo": "classificacao",
        "n_amostras": 569,
        "n_features": 30,
        "target": "target"
    },
    "digits": {
        "nome": "Digits",
        "valor": "digits",
        "descricao": "Reconhecimento de dígitos manuscritos 8x8 pixels, 10 classes (0-9).",
        "fonte": "sklearn",
        "tipo": "classificacao",
        "n_amostras": 1797,
        "n_features": 64,
        "target": "target"
    },
    "diabetes": {
        "nome": "Diabetes",
        "valor": "diabetes",
        "descricao": "Progressão de diabetes com 10 atributos biométricos e target contínuo.",
        "fonte": "sklearn",
        "tipo": "regressao",
        "n_amostras": 442,
        "n_features": 10,
        "target": "target"
    },
    "california_housing": {
        "nome": "California Housing",
        "valor": "california_housing",
        "descricao": "Preços de imóveis na Califórnia com 8 atributos e target contínuo.",
        "fonte": "sklearn",
        "tipo": "regressao",
        "n_amostras": 20640,
        "n_features": 8,
        "target": "MedHouseVal"
    },
    # UCI Datasets (via ucimlrepo)
    "adult": {
        "nome": "Adult (Census Income)",
        "valor": "adult",
        "descricao": "Prever se renda anual excede $50K baseado em dados do censo. 14 atributos demográficos.",
        "fonte": "uci",
        "tipo": "classificacao",
        "n_amostras": 48842,
        "n_features": 14,
        "target": "income",
        "uci_id": 2
    },
    "iris_uci": {
        "nome": "Iris (UCI)",
        "valor": "iris_uci",
        "descricao": "Clássico dataset Iris do repositório UCI. 150 amostras, 4 atributos, 3 classes.",
        "fonte": "uci",
        "tipo": "classificacao",
        "n_amostras": 150,
        "n_features": 4,
        "target": "class",
        "uci_id": 53
    },
    "wine_uci": {
        "nome": "Wine Quality",
        "valor": "wine_uci",
        "descricao": "Qualidade de vinho tinto baseado em testes físico-químicos. 11 atributos, 6 classes de qualidade.",
        "fonte": "uci",
        "tipo": "classificacao",
        "n_amostras": 1599,
        "n_features": 11,
        "target": "quality",
        "uci_id": 186
    },
    "heart_disease": {
        "nome": "Heart Disease",
        "valor": "heart_disease",
        "descricao": "Diagnóstico de doença cardíaca. 13 atributos clínicos, classificação binária.",
        "fonte": "uci",
        "tipo": "classificacao",
        "n_amostras": 303,
        "n_features": 13,
        "target": "num",
        "uci_id": 45
    },
    "titanic": {
        "nome": "Titanic",
        "valor": "titanic",
        "descricao": "Prever sobrevivência no Titanic. Atributos como classe, sexo, idade, tarifa.",
        "fonte": "uci",
        "tipo": "classificacao",
        "n_amostras": 1309,
        "n_features": 7,
        "target": "Survived",
        "uci_id": 597
    },
    "abalone": {
        "nome": "Abalone",
        "valor": "abalone",
        "descricao": "Prever idade de abalone (molusco) baseado em medições físicas. 8 atributos.",
        "fonte": "uci",
        "tipo": "regressao",
        "n_amostras": 4177,
        "n_features": 8,
        "target": "Rings",
        "uci_id": 1
    },
    "housing": {
        "nome": "Boston Housing",
        "valor": "housing",
        "descricao": "Preços de casas em Boston com 13 atributos e target contínuo.",
        "fonte": "uci",
        "tipo": "regressao",
        "n_amostras": 506,
        "n_features": 13,
        "target": "MEDV",
        "uci_id": 601
    },
    "car_evaluation": {
        "nome": "Car Evaluation",
        "valor": "car_evaluation",
        "descricao": "Avaliação de carros baseado em 6 atributos categóricos. 4 classes de aceitabilidade.",
        "fonte": "uci",
        "tipo": "classificacao",
        "n_amostras": 1728,
        "n_features": 6,
        "target": "class",
        "uci_id": 19
    },
    "mushroom": {
        "nome": "Mushroom",
        "valor": "mushroom",
        "descricao": "Classificar cogumelos como comestíveis ou venenosos. 22 atributos categóricos.",
        "fonte": "uci",
        "tipo": "classificacao",
        "n_amostras": 8124,
        "n_features": 22,
        "target": "class",
        "uci_id": 73
    }
}


@router.get("/", response_model=List[ToyDatasetInfo])
async def listar_toy_datasets():
    """Lista todos os toy datasets disponíveis."""
    datasets = []
    for key, info in TOY_DATASETS.items():
        datasets.append(ToyDatasetInfo(
            nome=info["nome"],
            valor=info["valor"],
            descricao=info["descricao"],
            fonte=info["fonte"],
            tipo=info["tipo"],
            n_amostras=info["n_amostras"],
            n_features=info["n_features"],
            target=info["target"]
        ))
    return datasets


@router.get("/{dataset_name}")
async def carregar_toy_dataset(dataset_name: str):
    """Carrega um toy dataset específico e retorna no formato esperado pelo frontend."""
    if dataset_name not in TOY_DATASETS:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_name}' não encontrado")

    info = TOY_DATASETS[dataset_name]

    try:
        df = None

        # Carregar do sklearn
        if info["fonte"] == "sklearn":
            df = _carregar_sklearn(dataset_name)
        # Carregar do UCI
        elif info["fonte"] == "uci":
            df = _carregar_uci(info.get("uci_id"))

        if df is None:
            raise HTTPException(status_code=500, detail="Erro ao carregar dataset")

        # Preparar dados no formato esperado
        colunas = list(df.columns)
        colunas_detalhes = []
        for col in colunas:
            tipo = "Numérico" if df[col].dtype in ['int64', 'float64'] else "Texto"
            colunas_detalhes.append({
                "nome_coluna": col,
                "tipo_coluna": tipo
            })

        # Converter para lista de dicts (limitar a 50 linhas para preview)
        dados = df.head(50).to_dict(orient='records')

        # Determinar tipo de predicao
        target = info["target"]
        if target in df.columns:
            tipo_target = "number" if df[target].dtype in ['int64', 'float64'] else "string"
        else:
            tipo_target = "string"

        prever_categoria = info["tipo"] == "classificacao"

        return {
            "nome_dataset": info["nome"],
            "fonte": info["fonte"],
            "colunas": colunas,
            "colunas_detalhes": colunas_detalhes,
            "dados": dados,
            "total_dados": len(df),
            "target": target,
            "tipo_target": tipo_target,
            "prever_categoria": prever_categoria,
            "dados_rotulados": True,
            "n_amostras": info["n_amostras"],
            "n_features": info["n_features"]
        }

    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Biblioteca não instalada: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar dataset: {str(e)}")


def _carregar_sklearn(dataset_name: str):
    """Carrega um dataset do sklearn."""
    if dataset_name == "iris":
        from sklearn.datasets import load_iris
        return load_iris(as_frame=True).frame
    elif dataset_name == "wine":
        from sklearn.datasets import load_wine
        return load_wine(as_frame=True).frame
    elif dataset_name == "breast_cancer":
        from sklearn.datasets import load_breast_cancer
        return load_breast_cancer(as_frame=True).frame
    elif dataset_name == "digits":
        from sklearn.datasets import load_digits
        data = load_digits(as_frame=True)
        df = data.frame
        df['target'] = data.target
        return df
    elif dataset_name == "diabetes":
        from sklearn.datasets import load_diabetes
        return load_diabetes(as_frame=True).frame
    elif dataset_name == "california_housing":
        from sklearn.datasets import fetch_california_housing
        return fetch_california_housing(as_frame=True).frame
    return None


def _carregar_uci(uci_id: int):
    """Carrega um dataset do UCI via ucimlrepo."""
    try:
        from ucimlrepo import fetch_ucirepo
        dataset = fetch_ucirepo(id=uci_id)
        df = dataset.data.original
        return df
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="ucimlrepo não está instalado. Instale com: pip install ucimlrepo"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao carregar dataset UCI: {str(e)}"
        )
