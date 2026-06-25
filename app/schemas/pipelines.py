from pydantic import BaseModel
from typing import Optional, Dict, Any, List


class PipelineCreate(BaseModel):
    nome: str
    descricao: Optional[str] = None
    resultadoColetaDado: Optional[Dict[str, Any]] = None
    modeloSelecionado: Optional[Dict[str, Any]] = None
    metricasSelecionadas: Optional[List[Any]] = None
    mediaMetricas: Optional[str] = "weighted"
    preProcessamentoConfig: Optional[Dict[str, Any]] = None
    resultadoTreinamento: Optional[Dict[str, Any]] = None
    resultadosDasAvaliacoes: Optional[Dict[str, Any]] = None
    status: Optional[str] = "rascunho"
    is_public: Optional[bool] = False
    dificuldade: Optional[str] = "iniciante"
    tags: Optional[List[str]] = []
    professor_id: Optional[str] = None


class PipelineUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    resultadoColetaDado: Optional[Dict[str, Any]] = None
    modeloSelecionado: Optional[Dict[str, Any]] = None
    metricasSelecionadas: Optional[List[Any]] = None
    mediaMetricas: Optional[str] = None
    preProcessamentoConfig: Optional[Dict[str, Any]] = None
    resultadoTreinamento: Optional[Dict[str, Any]] = None
    resultadosDasAvaliacoes: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    is_public: Optional[bool] = None
    dificuldade: Optional[str] = None
    tags: Optional[List[str]] = None
