#!/usr/bin/env python
"""Semeia o `conteudo` educacional versionado (app/conteudo/*.json) no MongoDB.

Idempotente e NÃO-destrutivo: só faz $set de `conteudo` (e $setOnInsert da
identidade de gráficos), preservando `execucao`/`habilitado` já existentes.
Substitui o bloco `conteudo` do antigo migrate-preproc-conteudo.sh.

Uso (na VM, dentro do backend, com o .env carregado):
    venv/bin/python -m scripts.deploy.seed_conteudo
ou
    PYTHONPATH=. venv/bin/python scripts/deploy/seed_conteudo.py
"""
import asyncio
import os
import sys

# Garante que `app` seja importável quando rodado como arquivo.
_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)


async def _main() -> None:
    from app.conteudo.loader import seed_conteudo

    resultado = await seed_conteudo()
    print("Seed de conteúdo concluído:")
    for categoria, contagem in resultado.items():
        print(f"  {categoria}: inseridos={contagem['inseridos']} atualizados={contagem['atualizados']}")


if __name__ == "__main__":
    asyncio.run(_main())
