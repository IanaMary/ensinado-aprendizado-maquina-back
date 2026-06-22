from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# Limites defensivos contra payloads abusivos vindos do front.
MAX_EVENTOS_LOTE = 100

# Conjuntos conhecidos (mantêm as agregações por_tipo/por_acao/status limpas).
TIPOS_VALIDOS = {"chat", "pipeline", "navegacao", "http", "ui", "erro"}
STATUS_VALIDOS = {"sucesso", "erro", "interrompido"}
# Teto generoso de duração (7 dias) — evita lixo sem rejeitar sessões longas reais.
MAX_DURACAO_MS = 7 * 24 * 60 * 60 * 1000


class EventoAtividade(BaseModel):
    """Um evento de atividade do usuário enviado pelo front (ou montado no backend).

    O usuário NÃO é confiado a partir do corpo: é sempre derivado do JWT no servidor.
    """
    tipo: str
    acao: str = Field(min_length=1, max_length=120)
    detalhes: Optional[Dict[str, Any]] = None
    pipeline_id: Optional[str] = Field(default=None, max_length=64)
    duracao_ms: Optional[int] = Field(default=None, ge=0, le=MAX_DURACAO_MS)
    status: str = "sucesso"
    erro: Optional[str] = Field(default=None, max_length=500)
    timestamp_cliente: Optional[str] = None

    @field_validator("tipo")
    @classmethod
    def _validar_tipo(cls, v: str) -> str:
        if v not in TIPOS_VALIDOS:
            raise ValueError(f"tipo inválido: {v}")
        return v

    @field_validator("status")
    @classmethod
    def _validar_status(cls, v: str) -> str:
        if v not in STATUS_VALIDOS:
            raise ValueError(f"status inválido: {v}")
        return v

    @field_validator("timestamp_cliente")
    @classmethod
    def _validar_timestamp(cls, v: Optional[str]) -> Optional[str]:
        # ISO inválido é descartado (não derruba o evento — campo é só informativo).
        if not v:
            return v
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        except ValueError:
            return None


class EventoLote(BaseModel):
    eventos: List[EventoAtividade] = Field(default_factory=list)
