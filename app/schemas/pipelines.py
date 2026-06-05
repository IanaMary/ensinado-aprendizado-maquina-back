from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime


class PipelineCreate(BaseModel):
    nome: str
    descricao: Optional[str] = None
    resultadoColetaDado: Optional[Dict[str, Any]] = None
    modeloSelecionado: Optional[Dict[str, Any]] = None
    metricasSelecionadas: Optional[List[Any]] = None
    preProcessamentoConfig: Optional[Dict[str, Any]] = None
    resultadoTreinamento: Optional[Dict[str, Any]] = None
    resultadosDasAvaliacoes: Optional[Dict[str, Any]] = None
    status: Optional[str] = "rascunho"


class PipelineUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    resultadoColetaDado: Optional[Dict[str, Any]] = None
    modeloSelecionado: Optional[Dict[str, Any]] = None
    metricasSelecionadas: Optional[List[Any]] = None
    preProcessamentoConfig: Optional[Dict[str, Any]] = None
    resultadoTreinamento: Optional[Dict[str, Any]] = None
    resultadosDasAvaliacoes: Optional[Dict[str, Any]] = None
    status: Optional[str] = None