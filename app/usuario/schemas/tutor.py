from typing import Optional
from pydantic import BaseModel

class Contexto(BaseModel):
  tamanho_arq: Optional[int] = None
  prever_categoria: Optional[bool]=  None  
