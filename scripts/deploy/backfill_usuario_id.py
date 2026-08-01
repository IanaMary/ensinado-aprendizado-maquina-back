#!/usr/bin/env python3
"""Backfill do campo `usuario_id` (dono) nas coleções que passaram a ser escopadas
por dono para fechar a família de IDOR (arquivos, configuracoes_treinamento,
modelos_treinados).

Contexto: essas coleções eram inseridas SEM dono e lidas só por `_id`, então
qualquer aluno autenticado lia/sobrescrevia o dataset/modelo de outro. A correção
passou a gravar `usuario_id` no insert e a filtrar as leituras por dono. Documentos
ANTIGOS não têm `usuario_id` e, com a leitura escopada, ficam inacessíveis
(fail-closed — o padrão seguro).

Este script:
  1. Recupera o dono de `modelos_treinados` a partir de `mlflow_runs`
     (que guarda {mlflow_run_id -> usuario_id}) — recuperação REAL do dono.
  2. Cria índices por `usuario_id` (desempenho das leituras escopadas).
  3. Relata quantos `arquivos`/`configuracoes_treinamento` ficaram órfãos (sem
     trilha de dono recuperável). NÃO inventa dono: um órfão fica inacessível até
     um admin reatribuí-lo ou o usuário recoletar os dados.

Uso:
    MONGO_URL=... MONGO_DB=... python scripts/deploy/backfill_usuario_id.py [--apply]
Sem --apply é um dry-run (só relata).
"""
import argparse
import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient


async def main(apply: bool) -> int:
    url = os.getenv("MONGO_URL")
    dbname = os.getenv("MONGO_DB")
    if not url or not dbname:
        print("Defina MONGO_URL e MONGO_DB.", file=sys.stderr)
        return 2
    db = AsyncIOMotorClient(url)[dbname]

    # 1) modelos_treinados: recupera dono via mlflow_runs
    recuperados = 0
    sem_run = 0
    cursor = db["modelos_treinados"].find(
        {"$or": [{"usuario_id": {"$exists": False}}, {"usuario_id": ""}]},
        {"mlflow_run_id": 1},
    )
    async for doc in cursor:
        run_id = doc.get("mlflow_run_id")
        dono = None
        if run_id:
            run = await db["mlflow_runs"].find_one({"mlflow_run_id": run_id}, {"usuario_id": 1})
            dono = (run or {}).get("usuario_id")
        if dono:
            recuperados += 1
            if apply:
                await db["modelos_treinados"].update_one(
                    {"_id": doc["_id"]}, {"$set": {"usuario_id": str(dono)}}
                )
        else:
            sem_run += 1
    print(f"modelos_treinados: {recuperados} donos recuperados via mlflow_runs, "
          f"{sem_run} órfãos (sem run/usuario) — ficam inacessíveis até reatribuição.")

    # 2) órfãos em arquivos/configuracoes (sem trilha de dono)
    for col in ("arquivos", "configuracoes_treinamento"):
        n = await db[col].count_documents(
            {"$or": [{"usuario_id": {"$exists": False}}, {"usuario_id": ""}]}
        )
        print(f"{col}: {n} documentos órfãos (sem usuario_id). "
              f"Não há trilha de dono; permanecem inacessíveis (fail-closed).")

    # 3) índices por usuario_id
    if apply:
        for col in ("arquivos", "configuracoes_treinamento", "modelos_treinados"):
            await db[col].create_index("usuario_id")
        print("Índices por usuario_id criados.")
    else:
        print("Dry-run: rode com --apply para gravar donos recuperados e criar índices.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Grava as mudanças (senão é dry-run).")
    sys.exit(asyncio.run(main(ap.parse_args().apply)))
