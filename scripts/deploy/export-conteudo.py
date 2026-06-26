#!/usr/bin/env python
"""Bootstrap one-time: exporta o `conteudo` do MongoDB → app/conteudo/*.json.

READ-ONLY no banco. Usado UMA vez para trazer o conteúdo migrado ad-hoc na
produção para o repositório (a fonte da verdade passa a ser o repo). Depois disso,
o fluxo é repo → loader → DB; este script só serve para re-sincronizar se preciso.

Uso (na VM, com o .env do backend carregado):
    venv/bin/python -m scripts.deploy.export_conteudo
"""
import asyncio
import json
import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

_CATEGORIAS = ("modelos", "metricas", "pre_processamento", "coleta_dados", "graficos")
_DESTINO = os.path.join(_RAIZ, "app", "conteudo")


async def _main() -> None:
    from app.database import db

    for categoria in _CATEGORIAS:
        mapa = {}
        async for doc in db[categoria].find({}, {"valor": 1, "conteudo": 1, "_id": 0}):
            valor = doc.get("valor")
            conteudo = doc.get("conteudo")
            if valor and conteudo:
                mapa[valor] = conteudo
        caminho = os.path.join(_DESTINO, f"{categoria}.json")
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(mapa, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        print(f"  {categoria}.json: {len(mapa)} itens")


if __name__ == "__main__":
    asyncio.run(_main())
