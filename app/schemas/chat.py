from typing import List, Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field


class ChatMensagem(BaseModel):
    role: str  # "user" ou "assistant"
    content: str


class ChatTutorRequest(BaseModel):
    mensagens: List[ChatMensagem] = Field(default_factory=list)
    # Contexto do pipeline carregado (dataset, modelo, hiperparametros, metricas,
    # graficos, codigo python gerado...). Opcional e de tamanho limitado.
    contexto: Optional[Dict[str, Any]] = None


class ChatHistoricoResponse(BaseModel):
    id: str
    pipeline_id: Optional[str] = None
    titulo: str
    mensagens: List[ChatMensagem]
    criado_em: datetime
    atualizado_em: datetime


class ChatHistoricoListItem(BaseModel):
    id: str
    pipeline_id: Optional[str] = None
    titulo: str
    criado_em: datetime
    atualizado_em: datetime
