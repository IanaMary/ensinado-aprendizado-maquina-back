from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# Limites defensivos contra payloads abusivos vindos do front.
MAX_EVENTOS_LOTE = 100


class EventoAtividade(BaseModel):
    """Um evento de atividade do usuário enviado pelo front (ou montado no backend).

    O usuário NÃO é confiado a partir do corpo: é sempre derivado do JWT no servidor.
    """
    tipo: str  # "chat" | "pipeline" | "navegacao" | "http" | "ui" | "erro"
    acao: str  # ex.: "enviou_mensagem", "treinou_modelo", "escolheu_dataset"
    detalhes: Optional[Dict[str, Any]] = None
    pipeline_id: Optional[str] = None
    duracao_ms: Optional[int] = None
    status: str = "sucesso"  # "sucesso" | "erro"
    erro: Optional[str] = None
    timestamp_cliente: Optional[str] = None  # ISO enviado pelo cliente


class EventoLote(BaseModel):
    eventos: List[EventoAtividade] = Field(default_factory=list)
