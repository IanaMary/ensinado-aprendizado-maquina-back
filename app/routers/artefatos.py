"""Artefatos do MLflow.

- `GET /tutor/artefatos` (admin/professor): lista runs associadas a usuários
  (coleção `mlflow_runs`), com filtro por usuário e data — fim da busca "no escuro".
- `GET /tutor/artefatos/{run_id}` (autenticado): resumo da run (params/métricas/tags/
  artefatos/modelos), via `app.mlflow_client.get_run_summary` (lar canônico).

A associação run↔usuário é gravada por `registrar_run_usuario` no treino
(`treinar_modelo_generico`), em padrão fire-and-forget.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import mlflow_runs, pipelines, atividades, turmas, colecao_usuario
from app.funcoes_genericas.funcoes_genericas import serialize_doc
from app.mlflow_client import get_run_summary, mlflow_enabled
from app.security import get_usuario_atual, exigir_admin_ou_professor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tutor/artefatos", tags=["Artefatos"])

# run_id do MLflow é tipicamente hex de 32 chars; aceitamos alfanumérico/_/- até 64.
_RUN_ID_RE = re.compile(r"^[a-zA-Z0-9][\w-]{0,63}$")


async def registrar_run_usuario(
    usuario: Optional[dict],
    *,
    run_id: Optional[str],
    modelo_id: Optional[str] = None,
    modelo: Optional[str] = None,
    arquivo_id: Optional[str] = None,
    configuracao_id: Optional[str] = None,
    dataset_nome: Optional[str] = None,
) -> None:
    """Associa uma run do MLflow ao usuário. Fire-and-forget: nunca quebra o treino."""
    if not run_id:
        return
    try:
        await mlflow_runs.insert_one({
            "mlflow_run_id": run_id,
            "modelo_id": modelo_id,
            "usuario_id": str((usuario or {}).get("_id") or (usuario or {}).get("id") or ""),
            "usuario_email": (usuario or {}).get("email", ""),
            "usuario_nome": (usuario or {}).get("nome_usuario")
            or (usuario or {}).get("nome")
            or (usuario or {}).get("name")
            or (usuario or {}).get("email", ""),
            "usuario_role": (usuario or {}).get("role", ""),
            "modelo": modelo,
            "dataset_nome": dataset_nome,
            "arquivo_id": arquivo_id,
            "configuracao_id": configuracao_id,
            "criado_em": datetime.now(timezone.utc),
        })
    except Exception as e:  # pragma: no cover - defensivo
        logger.warning("Falha ao registrar run↔usuário: %s", e)


def _parse_data(valor: Optional[str]) -> Optional[datetime]:
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Data inválida: {valor}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _faixa_tempo(inicio: Optional[datetime], fim: Optional[datetime]) -> Optional[dict]:
    faixa: dict[str, Any] = {}
    if inicio:
        faixa["$gte"] = inicio
    if fim:
        faixa["$lte"] = fim
    return faixa or None


@router.get("/facetas")
async def facetas_runs(_: dict = Depends(exigir_admin_ou_professor)):
    """Valores distintos p/ popular os filtros (modelo, papel do usuário)."""
    modelos = [m for m in await mlflow_runs.distinct("modelo") if m]
    papeis = [p for p in await mlflow_runs.distinct("usuario_role") if p]
    datasets = [d for d in await mlflow_runs.distinct("dataset_nome") if d]
    return {"modelos": sorted(modelos), "papeis": sorted(papeis), "datasets": sorted(datasets)}


@router.get("/usuarios")
async def buscar_usuarios(
    q: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    _: dict = Depends(exigir_admin_ou_professor),
):
    """Busca leve de usuários (id/nome/email) p/ o autocomplete do filtro — escala p/
    milhares de alunos (regex no servidor, resultado limitado)."""
    filtro: dict[str, Any] = {}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        filtro = {"$or": [{"nome_usuario": rx}, {"nome": rx}, {"email": rx}]}
    proj = {"nome_usuario": 1, "nome": 1, "email": 1}
    cur = colecao_usuario.find(filtro, proj).sort("nome_usuario", 1).limit(limit)
    return [
        {"id": str(u["_id"]),
         "nome": u.get("nome_usuario") or u.get("nome") or u.get("email"),
         "email": u.get("email")}
        async for u in cur
    ]


@router.get("")
async def listar_runs(
    usuario_id: Optional[str] = Query(None),
    modelo: Optional[str] = Query(None),
    papel: Optional[str] = Query(None),
    dataset: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: dict = Depends(exigir_admin_ou_professor),
):
    """Lista runs (artefatos) associadas a usuários, com filtro por usuário, modelo,
    papel do usuário e data."""
    filtro: dict[str, Any] = {}
    if usuario_id:
        filtro["usuario_id"] = usuario_id
    if modelo:
        filtro["modelo"] = modelo
    if papel:
        filtro["usuario_role"] = papel
    if dataset:
        filtro["dataset_nome"] = dataset
    faixa = _faixa_tempo(_parse_data(data_inicio), _parse_data(data_fim))
    if faixa:
        filtro["criado_em"] = faixa

    total = await mlflow_runs.count_documents(filtro)
    cursor = mlflow_runs.find(filtro).sort("criado_em", -1).skip(skip).limit(limit)
    itens = []
    async for doc in cursor:
        d = serialize_doc(doc)
        ce = d.get("criado_em")
        if isinstance(ce, datetime):
            d["criado_em"] = ce.isoformat()
        d["run_id"] = d.get("mlflow_run_id")
        itens.append(d)
    return {"total": total, "skip": skip, "limit": limit, "itens": itens}


@router.get("/{run_id}")
async def obter_resumo_run(run_id: str, usuario: dict = Depends(get_usuario_atual)):
    # 503: MLflow não configurado (sem MLFLOW_TRACKING_URI).
    if not mlflow_enabled():
        raise HTTPException(status_code=503, detail="O MLflow não está configurado no servidor.")
    # 400: run_id sintaticamente inválido / muito longo.
    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail="run_id inválido.")
    summary = get_run_summary(run_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Run não encontrada.")
    return summary


@router.get("/{run_id}/contexto")
async def contexto_run(run_id: str, _: dict = Depends(exigir_admin_ou_professor)):
    """Submissões de atividade que usaram esta run (liga a run à atividade/turma).

    O pipeline salvo guarda `resultadoTreinamento[modelo].mlflow_run_id`; achamos as
    submissões (com `atividade_id`) cujo treino referencia esta run, via `$objectToArray`.
    """
    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail="run_id inválido.")
    cur = pipelines.aggregate([
        {"$match": {"atividade_id": {"$nin": [None, ""]}}},
        {"$addFields": {"_tr": {"$objectToArray": {"$ifNull": ["$resultadoTreinamento", {}]}}}},
        {"$match": {"_tr.v.mlflow_run_id": run_id}},
        {"$project": {"atividade_id": 1, "turma_id": 1, "nome": 1, "user_id": 1}},
        {"$limit": 10},
    ])
    subs = await cur.to_list(length=10)

    async def _doc(col, _id):
        try:
            return await col.find_one({"_id": ObjectId(_id)}) if _id else None
        except Exception:
            return None

    vinculos = []
    for s in subs:
        atv = await _doc(atividades, s.get("atividade_id"))
        tid = s.get("turma_id") or (atv or {}).get("turma_id")
        turma = await _doc(turmas, tid)
        vinculos.append({
            "pipeline_id": str(s["_id"]),
            "pipeline_nome": s.get("nome"),
            "atividade_id": s.get("atividade_id"),
            "atividade_titulo": (atv or {}).get("titulo"),
            "turma_id": tid,
            "turma_nome": (turma or {}).get("nome"),
        })
    return {"vinculos": vinculos}
