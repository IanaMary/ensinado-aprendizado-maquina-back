from pydantic import BaseModel

class ItemColeta(BaseModel):
    label: str
    tipoItem: str = "coleta-dado"
    habilitado: bool = True
    movido: bool = False

class ItemColetaOut(ItemColeta):
    id: str