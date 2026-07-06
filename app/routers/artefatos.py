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

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import mlflow_runs
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
    return {"modelos": sorted(modelos), "papeis": sorted(papeis)}


@router.get("")
async def listar_runs(
    usuario_id: Optional[str] = Query(None),
    modelo: Optional[str] = Query(None),
    papel: Optional[str] = Query(None),
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
