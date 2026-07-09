#!/usr/bin/env python
"""Semeia a base de conhecimento do assistente do admin (guia de preenchimento
da Configuração do Pipeline) no MongoDB: db.tutor, doc {pipe: 'conf-pipeline'}.

Idempotente: upsert com $set só de texto_pipe (a fonte versionada em
app/conteudo/kb_conf_pipeline.py sobrescreve o texto; demais campos do doc,
se existirem, são preservados).

Uso (na VM, dentro do backend, com o .env carregado):
    .venv/bin/python -m scripts.deploy.seed_kb_conf_pipeline
"""
import asyncio
import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)


async def _main() -> None:
    from app.database import tutor
    from app.conteudo.kb_conf_pipeline import KB_CONF_PIPELINE

    resultado = await tutor.update_one(
        {"pipe": "conf-pipeline"},
        {"$set": {"texto_pipe": KB_CONF_PIPELINE}, "$setOnInsert": {"pipe": "conf-pipeline"}},
        upsert=True,
    )
    acao = "inserido" if resultado.upserted_id else ("atualizado" if resultado.modified_count else "sem mudança")
    print(f"KB conf-pipeline: {acao} ({len(KB_CONF_PIPELINE)} chars)")


if __name__ == "__main__":
    asyncio.run(_main())
