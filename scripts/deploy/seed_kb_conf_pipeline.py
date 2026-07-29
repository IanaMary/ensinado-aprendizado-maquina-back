#!/usr/bin/env python
"""Semeia o guia de preenchimento do conf-pipeline: db.tutor, doc {pipe: 'conf-pipeline'},
campo texto_pipe. É o contexto que o assistente do admin recebe no chat.

Idempotente e CONSERVADOR: preserva o texto que o admin gravar (a decisão de escrever ou preservar
vive em `app/conteudo/texto_versionado.py`, com dez estados testados lá). Antes este script
sobrescrevia sem ler o que havia no banco — motivo de ele nunca ter entrado no `deploy.sh`.

O backend também semeia no boot (`app/main.py`); este CLI existe para rodar sem reiniciar, para o
`--forcar` e para o resultado aparecer no log do deploy.

Uso (na VM, dentro do backend, com o .env carregado):
    venv/bin/python -m scripts.deploy.seed_kb_conf_pipeline [--forcar]
"""
import asyncio
import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)


async def _main(forcar: bool) -> None:
    from app.conteudo.textos_do_tutor import ALVO_CONF_PIPELINE, resumo_legivel, semear_texto_do_tutor

    resultado = await semear_texto_do_tutor(ALVO_CONF_PIPELINE, forcar=forcar)
    print(resumo_legivel(resultado, ALVO_CONF_PIPELINE))


if __name__ == "__main__":
    asyncio.run(_main("--forcar" in sys.argv[1:]))
