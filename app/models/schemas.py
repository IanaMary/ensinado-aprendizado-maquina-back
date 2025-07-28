from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional 
class AvaliacaoCompactaRequest(BaseModel):
    dados_teste: List[Dict[str, Any]]
    target: str
    atributos: List[str]
    avaliacoes: List[Dict[str, Any]]

# Modelos Pydantic
class DatasetRequest(BaseModel):
    dados_treino: List[Dict[str, Any]]
    dados_teste: Optional[List[Dict[str, Any]]] = []
    atributos: List[str]
    target: str
    hiperparametros: Optional[Dict[str, Any]] = {}
    porcentagem_teste: float
    
class PrevisaoRequest(BaseModel):
    dados: List[Dict[str, Any]]
    modelo_nome: str

class AvaliacaoRequest(BaseModel):
    dados_teste: List[Dict[str, Any]]
    target: str
    atributos: List[str]
    metricas: Optional[List[str]] = []
    modelo_nome: Optional[Any]
    mlflow_run_id_modelo: str
class PrevisaoRequest(BaseModel):
    dados: List[Dict[str, Any]]
    modelo_nome: Optional[str] = None
    mlflow_run_id: Optional[str] = None  

class ConfiguracaoColetaRequest(BaseModel):
    target: str
    atributos: Dict[str, bool]
class Config:
    allow_population_by_field_name = True
    
class KnnRequestById(BaseModel):
    id_coleta: str
    hiperparametros: Optional[Dict[str, Any]] = {}
    