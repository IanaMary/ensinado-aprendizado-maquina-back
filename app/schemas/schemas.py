from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional 

class ModeloSelecionado(BaseModel):
    label: str
    id: str

class MetricaSelecionada(BaseModel):
    label: str
    valor: str
    average: Optional[str] = "weighted"

class AvaliacaoModelosRequest(BaseModel):
    modelos: List[ModeloSelecionado]
    metricas: List[MetricaSelecionada]

class PreProcStep(BaseModel):
    """Etapa de pré-processamento escolhida no pipeline gráfico.

    ``valor`` casa com uma entrada de ``PRE_PROCESSAMENTO_CATALOGO``; ``colunas``
    (opcional) restringe a transformação a colunas específicas.
    """
    valor: str
    colunas: Optional[List[str]] = Field(default_factory=list)

# Modelos Pydantic
class DatasetRequest(BaseModel):
    arquivo_id: str
    tipo_arquivo: str
    configuracao_id: str
    modelo_id: str
    hiperparametros: Optional[Dict[str, Any]] = Field(default_factory=dict)
    pre_processamento: Optional[List[PreProcStep]] = Field(default_factory=list)

class AvaliacaoRequest(BaseModel):
    dados_teste: List[Dict[str, Any]]
    target: str
    atributos: List[str]
    metricas: Optional[List[str]] = Field(default_factory=list)
    modelo_nome: Optional[Any] = None
    mlflow_run_id_modelo: str
class PrevisaoRequest(BaseModel):
    dados: List[Dict[str, Any]]
    modelo_nome: Optional[str] = None
    mlflow_run_id: Optional[str] = None  

class ConfiguracaoColetaRequest(BaseModel):
    atributos: Dict[str, Any]
    prever_categoria: bool
    dados_rotulados: bool
    target: Optional[str]  = None
    shuffle: Optional[bool] = True
    stratify: Optional[bool] = False


class ReDivisaoColetaRequest(BaseModel):
    test_size: float = 0.2
    shuffle: bool = True
    stratify: bool = False
    target: Optional[str] = None

class KnnRequestById(BaseModel):
    id_coleta: str
    hiperparametros: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
