from typing import Optional, Union, List, Dict, Any
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


# ---------------------- Pre-processamento ----------------------
class ContextoPipePreProcessamento(BaseModel):
    texto_pipe: str
    explicacao: Optional[str] = None


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
    classificacao: Optional[SubTipo] = None
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
    # Usado por /editar-modelos e /editar-tipo-aprendizado, que acessam o contexto
    # tipado por atributo (supervisionado.classificacao, etc.). Mantido como Union.
    contexto: Union[
        Contexto,
        ContextoPipeInicio,
        ContextoPipeColetaDados,
        ContextoPipeSelecaoModelo,
        ContextoPipeTreinamento,
        ContextoPipeSelecaoMetricas,
        ContextoPipeAvaliacao,
    ]


class AtualizarContextoRequest(BaseModel):
    # Para o PUT /{id} (editor de texto genérico da etapa): contexto livre. A Union
    # tipada era lossy — membros "todos opcionais" casavam errado e descartavam
    # campos como `texto_pipe` → 400. Dict preserva o que foi enviado para o $set.
    contexto: Dict[str, Any]


class AtualizarSelecaoModeloRequest(BaseModel):
    # Para /editar-modelos e /editar-tipo-aprendizado: o contexto é sempre a forma
    # de seleção de modelo (texto + supervisionado/nao_supervisionado aninhados).
    # Tipar direto (sem Union) evita a resolução lossy que caía no `Contexto` genérico
    # e descartava `supervisionado`/`texto_pipe` → 400.
    contexto: ContextoPipeSelecaoModelo
