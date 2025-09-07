from typing import Optional, Union, List
from pydantic import BaseModel

# ---------------------- Inicio ----------------------
class ContextoPipeInicio(BaseModel):
    texto_pipe: str
    explicacao: Optional[str] = None


# ---------------------- Coleta de dados ----------------------
class ContextoPipeColetaDados(BaseModel):
    texto_pipe: str
    planilha_treino: Optional[str] = None
    planilha_teste: Optional[str] = None
    divisao_entre_treino_teste: Optional[str] = None
    target: Optional[str] = None
    atributos: Optional[str] = None


# ---------------------- Seleção de modelo ----------------------
class Hiperparametro(BaseModel):
    nome: Optional[str] = None
    explicacao: Optional[str] = None
    
class Modelo(BaseModel):
    label: Optional[str] = None
    valor: Optional[str] = None
    explicacao: Optional[str] = None
    hiperparametros: Optional[List[Hiperparametro]] = None
    
class SubTipo(BaseModel):
    explicacao: Optional[str] = None
    modelos: Optional[List[Modelo]] = None
    
class Supervisionado(BaseModel):
    explicacao: Optional[str] = None
    classficacao: Optional[SubTipo] = None
    regressao: Optional[SubTipo] = None
    
class NaoSupervisionado(BaseModel):
    explicacao:  Optional[str] = None
    reducao_dimensionalidade:  Optional[SubTipo] = None
    agrupamento: Optional[SubTipo] = None
    
class TiposSelecaoModelo(BaseModel):
    supervisionado: Optional[Supervisionado]  = None
    nao_supervisionado: Optional[NaoSupervisionado] = None
    
class ContextoPipeSelecaoModelo(BaseModel):
    texto_pipe:  Optional[str] = None
    explicacao: Optional[str] = None
    supervisionado: Optional[Supervisionado]  = None
    nao_supervisionado: Optional[NaoSupervisionado] = None


# ---------------------- Treinamento ----------------------
class ContextoPipeTreinamento(BaseModel):
    texto_pipe: str
    explicacao: Optional[str] = None


# ---------------------- Seleção de métricas ----------------------
class TipoMetrica(BaseModel):
    label: str
    explicacao: str
    valor: str

class ContextoPipeSelecaoMetricas(BaseModel):
    texto_pipe: str
    explicacao: Optional[str] = None
    tipos: List[TipoMetrica]


# ---------------------- Avaliação ----------------------
class ContextoPipeAvaliacao(BaseModel):
    texto_pipe: str
    explicacao: Optional[str] = None


# ---------------------- Contexto genérico ----------------------
class Contexto(BaseModel):
    tamanho_arq: Optional[int] = None
    prever_categoria: Optional[bool] = None
    prever_quantidade: Optional[bool] = None
    dados_rotulados: Optional[bool] = None
    num_categorias_conhecidas: Optional[bool] = None
    apenas_olhando: Optional[bool] = None


# ---------------------- Request ----------------------
class AtualizarDescricaoRequest(BaseModel):
    contexto: Union[
        Contexto,
        ContextoPipeInicio,
        ContextoPipeColetaDados,
        ContextoPipeSelecaoModelo,
        ContextoPipeTreinamento,
        ContextoPipeSelecaoMetricas,
        ContextoPipeAvaliacao,
    ]
