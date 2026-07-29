"""Semeadura versionada da instrução de sistema do chat (`db.configuracoes_tutor`).

O texto do `system` mora no banco para que "o que está rodando" seja um fato observável, e não a
ausência de um documento. A disciplina de sincronizar (preservar a edição do admin, propagar padrão
novo para quem nunca editou) é genérica e vive em `app/conteudo/texto_versionado.py`; aqui fica só
a descrição DESTE alvo e os nomes que o resto do backend já importa.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Optional, Tuple

from app.conteudo.kb_tutor_chat import SYSTEM_PROMPT_TUTOR
from app.conteudo.texto_versionado import (  # noqa: F401 - re-export: superfície pública deste módulo
    ACAO_CUROU,
    ACAO_FORCOU,
    ACAO_INSERIU,
    ACAO_NORMALIZOU_ADMIN,
    ACAO_NORMALIZOU_VERSIONADO,
    ACAO_PRESERVOU,
    ACAO_PRESERVOU_DESATUALIZADO,
    ACAO_PROPAGOU,
    ACAO_SEM_MUDANCA,
    ACOES_QUE_ESCREVEM_TEXTO,
    ORIGEM_ADMIN,
    ORIGEM_VERSIONADO,
    TextoVersionado,
    decidir,
    resumir,
    semear,
)

CHAVE = "system_prompt"

ALVO_SYSTEM_PROMPT = TextoVersionado(
    campo_identidade="chave",
    identidade=CHAVE,
    campo="valor",
    padrao=SYSTEM_PROMPT_TUTOR,
    rotulo="Instrução do tutor",
    sufixo="a",
    # A tela mostra o histórico da ABA atual, e o editor do prompt vive na aba LLM.
    pipe_auditoria="llm",
    campo_auditado="system_prompt",
    # Sem legados: este texto nasceu já com o mecanismo de origem/hash.
    legados=(),
)


def decidir_seed(
    doc: Optional[Dict[str, Any]],
    padrao: str = SYSTEM_PROMPT_TUTOR,
    forcar: bool = False,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Matriz de decisão aplicada à instrução de sistema (ver `texto_versionado.decidir`)."""
    return decidir(doc, replace(ALVO_SYSTEM_PROMPT, padrao=padrao), forcar=forcar)


async def semear_system_prompt(
    colecao=None,
    auditoria=None,
    *,
    padrao: str = SYSTEM_PROMPT_TUTOR,
    forcar: bool = False,
) -> Dict[str, Any]:
    """Sincroniza `db.configuracoes_tutor {chave:'system_prompt'}` com o texto versionado.

    Coleções injetáveis por parâmetro (default: as de `app.database`) para que os testes não
    precisem patchar globais de módulo. Import tardio pelo mesmo motivo dos outros seeds: manter o
    módulo importável sem `MONGO_URL` definida.
    """
    if colecao is None or auditoria is None:
        from app.database import configuracoes_tutor, tutor_audit

        colecao = colecao if colecao is not None else configuracoes_tutor
        auditoria = auditoria if auditoria is not None else tutor_audit

    return await semear(replace(ALVO_SYSTEM_PROMPT, padrao=padrao), colecao, auditoria,
                        forcar=forcar)


def resumo_legivel(resultado: Dict[str, Any]) -> str:
    """Uma linha para o log do deploy."""
    return resumir(resultado, ALVO_SYSTEM_PROMPT)
