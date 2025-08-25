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
    texto_pipe: Optional[str] = None,
    explicacao: Optional[str] = None,
    
class ContextoPipeColetaDados(BaseModel):
    texto_pipe: Optional[str] = None
    planilha_treino: Optional[str] = None  
    planilha_teste: Optional[str] = None  
    divisao_entre_treino_teste: Optional[str] = None  
    target: Optional[str] = None  
    atributos: Optional[str] = None  

class ContextoPipeSelecaoModelo(BaseModel):
    texto_pipe: Optional[str] = None
    aprendizado_supervisionado: Optional[str] = None  
    classficacao: Optional[str] = None  
    regressao: Optional[str] = None  
    aprendizado_nao_supervisionado: Optional[str] = None  
    reducao_dimensionalidade: Optional[str] = None  
    agrupamento: Optional[str] = None  
    
class ContextoTreinamento(BaseModel):
    texto_pipe: Optional[str] = None,
    explicacao: Optional[str] = None,
    
class AtualizarDescricaoRequest(BaseModel):
    contexto: Union[Contexto, ContextoPipeInicio, ContextoPipeColetaDados, ContextoPipeSelecaoModelo, ContextoTreinamento] 
    


