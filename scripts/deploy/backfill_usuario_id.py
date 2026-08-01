#!/usr/bin/env python3
"""Backfill do campo `usuario_id` (dono) nas coleções que passaram a ser escopadas
por dono para fechar a família de IDOR (arquivos, configuracoes_treinamento,
modelos_treinados).

Contexto: essas coleções eram inseridas SEM dono e lidas só por `_id`, então
qualquer aluno autenticado lia/sobrescrevia o dataset/modelo de outro. A correção
passou a gravar `usuario_id` no insert e a filtrar as leituras por dono. Documentos
ANTIGOS não têm `usuario_id` e, com a leitura escopada, ficam inacessíveis
(fail-closed — o padrão seguro).

Recuperação de dono (por trilhas REAIS, nunca inventando):
  1. modelos_treinados: dono via `mlflow_runs` ({mlflow_run_id -> usuario_id}) E via
     `pipelines.resultadoTreinamento[*].id` (o pipeline salvo tem `user_id` e cita o
     id do modelo treinado).
  2. Propagação: para cada modelo com dono recuperado, propaga o mesmo dono para o
     dataset de origem (`arquivos._id == modelo.arquivo_id`) e a sua configuração
     (`configuracoes_treinamento.id_coleta == arquivo._id`). É a relação de treino,
     não um chute.
  3. Cria índices por `usuario_id`.
  4. Relata órfãos remanescentes (sem trilha de dono). NÃO inventa dono: um órfão
     fica inacessível até reatribuição/recoleta — é o padrão seguro.

Uso:
    MONGO_URL=... MONGO_DB=... python scripts/deploy/backfill_usuario_id.py [--apply]
Sem --apply é um dry-run (só relata). Idempotente: só grava onde `usuario_id` falta.
"""
import argparse
import asyncio
import os
import sys

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient


def _oid(v):
    """Converte para ObjectId quando possível; senão devolve o valor cru."""
    try:
        return ObjectId(v)
    except Exception:
        return v


async def _set_dono(db, colecao, filtro, dono, apply):
    """Grava usuario_id SÓ onde falta (não sobrescreve dono real). Retorna nº afetado."""
    cond = {**filtro, "$or": [{"usuario_id": {"$exists": False}}, {"usuario_id": ""}, {"usuario_id": None}]}
    if not apply:
        return await db[colecao].count_documents(cond)
    r = await db[colecao].update_many(cond, {"$set": {"usuario_id": str(dono)}})
    return r.modified_count


async def main(apply: bool) -> int:
    url = os.getenv("MONGO_URL")
    dbname = os.getenv("MONGO_DB")
    if not url or not dbname:
        print("Defina MONGO_URL e MONGO_DB.", file=sys.stderr)
        return 2
    db = AsyncIOMotorClient(url)[dbname]

    # ---- 1) monta o mapa modelo_id -> dono, por trilhas reais ----------------
    donos: dict = {}  # str(model _id) -> usuario_id

    # 1a) via mlflow_runs
    async for m in db["modelos_treinados"].find(
        {"$or": [{"usuario_id": {"$exists": False}}, {"usuario_id": ""}, {"usuario_id": None}]},
        {"mlflow_run_id": 1},
    ):
        run_id = m.get("mlflow_run_id")
        if not run_id:
            continue
        run = await db["mlflow_runs"].find_one({"mlflow_run_id": run_id}, {"usuario_id": 1})
        dono = (run or {}).get("usuario_id")
        if dono:
            donos[str(m["_id"])] = str(dono)
    via_mlflow = len(donos)

    # 1b) via pipelines salvos (têm user_id e citam o id do modelo treinado)
    async for p in db["pipelines"].find(
        {"user_id": {"$exists": True, "$ne": None, "$ne": ""}},
        {"user_id": 1, "resultadoTreinamento": 1},
    ):
        dono = str(p["user_id"])
        rt = p.get("resultadoTreinamento") or {}
        for k in rt:
            mid = (rt.get(k) or {}).get("id")
            if mid and str(mid) not in donos:
                donos[str(mid)] = dono
    via_pipeline = len(donos) - via_mlflow

    # ---- 2) grava dono nos modelos + propaga p/ arquivo e config -------------
    modelos_set = 0
    arquivos_set = 0
    configs_set = 0
    for mid, dono in donos.items():
        n = await _set_dono(db, "modelos_treinados", {"_id": _oid(mid)}, dono, apply)
        modelos_set += n
        # dataset de origem do modelo + sua configuração
        modelo = await db["modelos_treinados"].find_one({"_id": _oid(mid)}, {"arquivo_id": 1})
        arq_id = (modelo or {}).get("arquivo_id")
        if arq_id:
            arquivos_set += await _set_dono(db, "arquivos", {"_id": _oid(arq_id)}, dono, apply)
            configs_set += await _set_dono(db, "configuracoes_treinamento",
                                           {"id_coleta": _oid(arq_id)}, dono, apply)

    verbo = "gravaria" if not apply else "recuperou"
    print(f"modelos_treinados: {via_mlflow} donos via mlflow + {via_pipeline} via pipelines; "
          f"{verbo} dono em {modelos_set} modelos.")
    print(f"propagação p/ origem: {verbo} dono em {arquivos_set} arquivos e {configs_set} configs "
          f"(datasets/configs de treino dos modelos recuperados).")

    # ---- 3) relata órfãos remanescentes --------------------------------------
    for col in ("arquivos", "configuracoes_treinamento", "modelos_treinados"):
        n = await db[col].count_documents(
            {"$or": [{"usuario_id": {"$exists": False}}, {"usuario_id": ""}, {"usuario_id": None}]}
        )
        print(f"{col}: {n} órfãos remanescentes (sem trilha de dono; inacessíveis — fail-closed).")

    # ---- 4) índices ----------------------------------------------------------
    if apply:
        for col in ("arquivos", "configuracoes_treinamento", "modelos_treinados"):
            await db[col].create_index("usuario_id")
        print("Índices por usuario_id criados.")
    else:
        print("Dry-run: rode com --apply para gravar os donos recuperados e criar índices.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Grava as mudanças (senão é dry-run).")
    sys.exit(asyncio.run(main(ap.parse_args().apply)))
