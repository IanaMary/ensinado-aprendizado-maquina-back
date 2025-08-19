from typing import List, Optional
from pydantic import BaseModel

class ItemColeta(BaseModel):
    label: str
    tipoItem: str = "coleta-dado"
    habilitado: bool = True
    movido: bool = False

class ItemColetaOut(ItemColeta):
    id: str
    tipo: Optional[str] = None
    valor: Optional[str] = None
    metricas: Optional[List[str]] = None
    resumo: Optional[str] = None
    hiperparametros: Optional[List[object]] = None
