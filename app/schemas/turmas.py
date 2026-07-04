from typing import Optional, List, Any
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


class AtividadeCreate(BaseModel):
    titulo: str
    descricao: Optional[str] = None
    # pipeline PARCIAL que o aluno abre e continua (ex.: só resultadoColetaDado)
    template: dict = {}
    criterio: CriterioRanking = CriterioRanking()
    prazo: Optional[str] = None


class AtividadeUpdate(BaseModel):
    titulo: Optional[str] = None
    descricao: Optional[str] = None
    template: Optional[dict] = None
    criterio: Optional[CriterioRanking] = None
    prazo: Optional[str] = None
