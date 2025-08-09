from typing import Optional
from pydantic import BaseModel

class Contexto(BaseModel):
  tamanho_arq: Optional[int] = None
  prever_categoria: Optional[bool]=  None  
  prever_quantidade: Optional[bool]=  None  
  dados_rotulados: Optional[bool]=  None  
  num_categorias_conhecidas: Optional[bool]=  None  
  apenas_olhando: Optional[bool]=  None  

class AtualizarDescricaoRequest(BaseModel):
  contexto: Contexto
  nova_descricao: str