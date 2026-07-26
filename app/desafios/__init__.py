"""Desafios de montagem de pipeline (quebra-cabeça avaliado, sem execução).

O aluno recebe um enunciado e um tabuleiro de peças embaralhadas (úteis + distratoras)
e monta o pipeline nas mesmas lanes do dashboard. A correção é uma RUBRICA DE REGRAS
com peso — não um gabarito de sequência única — porque vários pipelines diferentes
resolvem corretamente o mesmo problema. Cada regra violada devolve um texto didático,
que é o material que o tutor usa depois para explicar o erro.

Nada aqui treina modelo nem toca em dados do aluno: é análise estrutural da montagem.

- `catalogo`: lê `db.modelos`/`db.metricas`/`db.pre_processamento` e normaliza as peças.
- `sorteio`: monta o tabuleiro (determinístico por atividade+aluno+tentativa).
- `regras`: biblioteca versionada de regras da rubrica.
- `avaliacao`: aplica as regras e devolve nota + regras avaliadas.
"""
from app.desafios.avaliacao import avaliar_montagem
from app.desafios.catalogo import LANES, carregar_pecas
from app.desafios.regras import REGRAS, regras_aplicaveis
from app.desafios.sorteio import montar_tabuleiro

__all__ = [
    "LANES",
    "REGRAS",
    "avaliar_montagem",
    "carregar_pecas",
    "montar_tabuleiro",
    "regras_aplicaveis",
]
