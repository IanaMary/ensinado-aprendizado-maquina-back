from typing import Optional, Union, List
from pydantic import BaseModel


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
    nome: str
    explicacao: str

class Modelo(BaseModel):
    label: str
    valor: str
    explicacao: str
    hiperparametros: List[Hiperparametro]

class SubTipo(BaseModel):
    explicacao: str
    modelos: List[Modelo]

class Supervisionado(BaseModel):
    explicacao: str
    classficacao: SubTipo  
    regressao: SubTipo

class NaoSupervisionado(BaseModel):
    explicacao: str
    reducao_dimensionalidade: SubTipo
    agrupamento: SubTipo

class TiposSelecaoModelo(BaseModel):
    supervisionado: Supervisionado
    nao_supervisionado: NaoSupervisionado

class ContextoPipeSelecaoModelo(BaseModel):
    texto_pipe: str
    explicacao: Optional[str] = None
    tipos: Optional[TiposSelecaoModelo]


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
