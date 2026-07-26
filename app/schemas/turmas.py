from typing import Optional, List, Any  # noqa: F401 (Any usado por schemas históricos)
from pydantic import BaseModel


class TurmaCreate(BaseModel):
    nome: str
    descricao: Optional[str] = None


class TurmaUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None


class AdicionarAlunos(BaseModel):
    # aceita ids e/ou emails de alunos já cadastrados
    alunos: List[str] = []


class EntrarTurma(BaseModel):
    codigo: str


class CriterioRanking(BaseModel):
    metrica: str = "accuracy_score"   # nome da métrica principal da tarefa
    ordem: str = "desc"                # "desc" (maior é melhor) | "asc"


class DadosDesafio(BaseModel):
    """Características da base descritas no enunciado. São o que liga as regras
    condicionais da rubrica (imputação, codificação, escala) — o desafio não executa nada.

    Quando o desafio nasce de um dataset de exemplo (`GabaritoMontagem.dataset`), a tela do
    professor pré-preenche estas flags com a inspeção do dataframe real
    (`app/desafios/base_dados.py`); ele pode ajustar, porque é dele a decisão do que cobrar."""
    faltantes: bool = False
    texto: bool = False
    escalas_diferentes: bool = False


class GabaritoMontagem(BaseModel):
    """Requisitos do desafio — NUNCA sai para o aluno (só o professor vê/edita).

    Não é a solução: é o que a rubrica cobra. Vários pipelines diferentes podem
    satisfazer o mesmo gabarito, que é a realidade de aprendizado de máquina.
    """
    # Dataset de exemplo que origina o enunciado. Quando presente, o SERVIDOR deriva a
    # `tarefa` dele (o cliente não decide). Opcional para não invalidar desafios antigos.
    dataset: Optional[str] = None
    tarefa: str = "classificacao"                  # classificacao | regressao | agrupamento
    exige: List[str] = ["coleta", "modelo", "metrica"]
    dados: DadosDesafio = DadosDesafio()
    # True: o sistema sorteia as peças úteis (varia entre alunos e tentativas).
    # False: valem as peças escolhidas pelo professor em `fixar` — mais o mínimo que o
    # tabuleiro precisa para ter solução, que o sorteio garante de todo jeito.
    sortear_pecas: bool = True
    fixar: List[str] = []                          # peças que devem estar no tabuleiro
    vetar: List[str] = []                          # peças que nunca aparecem
    dificuldade: str = "medio"                     # facil | medio | dificil (nº de distratores)


class AtividadeCreate(BaseModel):
    titulo: str
    descricao: Optional[str] = None
    # "pipeline": o aluno completa um pipeline real e submete a execução (comportamento
    # histórico, default). "montagem": quebra-cabeça avaliado por rubrica, sem executar.
    tipo: str = "pipeline"
    # pipeline PARCIAL que o aluno abre e continua (ex.: só resultadoColetaDado)
    template: dict = {}
    gabarito: Optional[GabaritoMontagem] = None
    criterio: CriterioRanking = CriterioRanking()
    prazo: Optional[str] = None


class AtividadeUpdate(BaseModel):
    titulo: Optional[str] = None
    descricao: Optional[str] = None
    tipo: Optional[str] = None
    template: Optional[dict] = None
    gabarito: Optional[GabaritoMontagem] = None
    criterio: Optional[CriterioRanking] = None
    prazo: Optional[str] = None


class SubmeterMontagem(BaseModel):
    """Montagem do aluno: peças por lane, na ordem em que ele as colocou."""
    montagem: dict = {}
