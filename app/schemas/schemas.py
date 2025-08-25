from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional 

class ModeloSelecionado(BaseModel):
    label: str
    id: str

class MetricaSelecionada(BaseModel):
    label: str
    valor: str

class AvaliacaoModelosRequest(BaseModel):
    modelos: List[ModeloSelecionado]
    metricas: List[MetricaSelecionada]

# Modelos Pydantic
class DatasetRequest(BaseModel):
    arquivo_id: str
    tipo_arquivo: str              
    configuracao_id: str   
    modelo_id: str           
    
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
    atributos: Dict[str, Any]
    prever_categoria: bool
    daods_rotulados: bool
    target: Optional[str]  = None
    
class Config:
    allow_population_by_field_name = True
    
class KnnRequestById(BaseModel):
    id_coleta: str
    hiperparametros: Optional[Dict[str, Any]] = {}
    