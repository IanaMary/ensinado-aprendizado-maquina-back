from typing import Optional, Union
from pydantic import BaseModel

class Contexto(BaseModel):
    tamanho_arq: Optional[int] = None
    prever_categoria: Optional[bool] = None  
    prever_quantidade: Optional[bool] = None  
    dados_rotulados: Optional[bool] = None  
    num_categorias_conhecidas: Optional[bool] = None  
    apenas_olhando: Optional[bool] = None  

class ContextoPipeInicio(BaseModel):
    explicacao: Optional[str] = None 
    
class ContextoPipeColetaDados(BaseModel):
    planilha_treino: Optional[str] = None  
    planilha_teste: Optional[str] = None  
    divisao_treino_teste: Optional[str] = None  
    target: Optional[str] = None  
    atributos: Optional[str] = None  
    
class AtualizarDescricaoRequest(BaseModel):
    contexto: Union[Contexto, ContextoPipeInicio, ContextoPipeColetaDados] 


