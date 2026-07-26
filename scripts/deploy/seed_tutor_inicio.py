#!/usr/bin/env python
"""Semeia as boas-vindas do tutor (Área de Trabalho) no MongoDB: db.tutor, doc
{pipe: 'inicio'}, campo texto_pipe.

Idempotente e CONSERVADOR: só escreve quando o documento não existe ou quando o
texto atual é o legado de uma frase gravado pelo seed-mongodb.sh antigo. Se o
admin editou o texto em conf-tutor → Início, a edição é preservada (use --forcar
para sobrescrever de propósito).

Uso (na VM, dentro do backend, com o .env carregado):
    .venv/bin/python -m scripts.deploy.seed_tutor_inicio [--forcar]
"""
import asyncio
import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)


async def _main(forcar: bool) -> None:
    from app.database import tutor
    from app.conteudo.kb_tutor_inicio import TUTOR_INICIO_HTML, TUTOR_INICIO_LEGADO

    doc = await tutor.find_one({"pipe": "inicio"})
    atual = (doc or {}).get("texto_pipe") or ""

    if atual == TUTOR_INICIO_HTML:
        print("Boas-vindas do tutor: sem mudança")
        return
    if doc and atual.strip() not in ("", TUTOR_INICIO_LEGADO) and not forcar:
        print(
            "Boas-vindas do tutor: preservado (texto editado pelo admin — "
            f"{len(atual)} chars; use --forcar para sobrescrever)"
        )
        return

    resultado = await tutor.update_one(
        {"pipe": "inicio"},
        {"$set": {"texto_pipe": TUTOR_INICIO_HTML}, "$setOnInsert": {"pipe": "inicio"}},
        upsert=True,
    )
    acao = "inserido" if resultado.upserted_id else "atualizado"
    print(f"Boas-vindas do tutor: {acao} ({len(TUTOR_INICIO_HTML)} chars)")


if __name__ == "__main__":
    asyncio.run(_main("--forcar" in sys.argv[1:]))
