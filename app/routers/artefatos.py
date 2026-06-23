"""Artefatos do MLflow: resumo de uma run (params/métricas/tags/artefatos).

Reimplementa `GET /tutor/artefatos/{run_id}` (antes era um stub). Gated por
autenticação; quando o MLflow não está configurado (sem `MLFLOW_TRACKING_URI`)
responde 503. Padrões de API verificados para MLflow 3.14 (deep research):
- `MlflowClient.get_run` → `run.info.*` + `run.data.params/metrics/tags`;
- `MlflowClient.list_artifacts` é raso (1 nível, `file_size=None` em diretórios) →
  recursão manual;
- `MlflowException.error_code` é string: `RESOURCE_DOES_NOT_EXIST`→404,
  `INVALID_PARAMETER_VALUE`→400 (a regex do MLflow aceita até 256 chars, por isso
  aplicamos um limite próprio mais estrito antes de consultar o store).
"""
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

import mlflow.config
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from app.security import get_usuario_atual

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tutor/artefatos", tags=["Artefatos"])

# run_id do MLflow é tipicamente hex de 32 chars; aceitamos alfanumérico/_/- até 64.
_RUN_ID_RE = re.compile(r"^[a-zA-Z0-9][\w-]{0,63}$")
_MAX_PROFUNDIDADE = 10


def _coletar_recursivo(lister, path: Optional[str] = None, profundidade: int = 0) -> list[dict]:
    """Enumera artefatos recursivamente. `lister(path)` devolve list[FileInfo] de UM
    nível (a API do MLflow é rasa; `file_size` é None em diretórios)."""
    if profundidade > _MAX_PROFUNDIDADE:
        return []
    itens: list[dict] = []
    for fi in lister(path):
        itens.append({"path": fi.path, "is_dir": fi.is_dir, "file_size": fi.file_size})
        if fi.is_dir:
            itens.extend(_coletar_recursivo(lister, fi.path, profundidade + 1))
    return itens


def _listar_modelos(client: MlflowClient, run) -> list[dict]:
    """Modelos logados da run. No MLflow 3.x os modelos viraram entidades LoggedModel
    e NÃO aparecem em list_artifacts(run_id) — daí buscar via search_logged_models."""
    run_id = run.info.run_id
    exp_ids = [run.info.experiment_id]
    try:
        encontrados = client.search_logged_models(
            experiment_ids=exp_ids,
            filter_string=f"source_run_id = '{run_id}'",
            max_results=100,
        )
    except Exception:
        # Filtro indisponível/incompatível: busca por experimento e filtra em Python.
        try:
            encontrados = client.search_logged_models(experiment_ids=exp_ids, max_results=100)
        except Exception as e:  # pragma: no cover - defensivo
            logger.warning("Falha ao buscar modelos logados: %s", e)
            return []
    modelos: list[dict] = []
    for lm in (encontrados or []):
        # Garante o escopo da run mesmo se o filtro não tiver sido aplicado pelo store.
        if getattr(lm, "source_run_id", None) != run_id:
            continue
        try:
            artifacts = _coletar_recursivo(
                lambda p, mid=lm.model_id: client.list_logged_model_artifacts(mid, p)
            )
        except Exception:  # pragma: no cover - defensivo
            artifacts = []
        modelos.append({
            "model_id": lm.model_id,
            "name": lm.name,
            "model_uri": lm.model_uri,
            "model_type": lm.model_type,
            "status": str(lm.status) if lm.status is not None else None,
            "artifacts": artifacts,
        })
    return modelos


def get_run_summary(run_id: str) -> Optional[dict]:
    """Resumo de uma run do MLflow. Retorna None se a run não existe."""
    client = MlflowClient()
    try:
        run = client.get_run(run_id)
    except MlflowException as e:
        if e.error_code == "RESOURCE_DOES_NOT_EXIST":
            return None
        raise
    return {
        "run_id": run.info.run_id,
        "params": dict(run.data.params),
        "metrics": dict(run.data.metrics),
        "tags": dict(run.data.tags),
        # Artefatos de run (log_artifact) — no MLflow 3.x NÃO incluem modelos logados.
        "artifacts": _coletar_recursivo(lambda p: client.list_artifacts(run_id, p)),
        # Modelos logados (entidades LoggedModel da run), com seus próprios artefatos.
        "models": _listar_modelos(client, run),
        "status": run.info.status,
        "start_time": run.info.start_time,
        "end_time": run.info.end_time,
    }


@router.get("/{run_id}")
async def obter_resumo_run(run_id: str, usuario: dict = Depends(get_usuario_atual)):
    # 503: MLflow não configurado (sem MLFLOW_TRACKING_URI / set_tracking_uri).
    if not mlflow.config.is_tracking_uri_set():
        raise HTTPException(status_code=503, detail="MLflow não está configurado no servidor.")
    # 400: run_id sintaticamente inválido / muito longo (antes de consultar o store).
    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail="run_id inválido.")
    try:
        summary = get_run_summary(run_id)
    except MlflowException as e:
        # Traduz o erro do MLflow direto para o status HTTP equivalente.
        raise HTTPException(status_code=e.get_http_status_code(), detail=str(e))
    if summary is None:
        raise HTTPException(status_code=404, detail="Run não encontrada.")
    return summary
