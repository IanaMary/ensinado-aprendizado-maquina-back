"""Wrapper fino sobre o SDK do MLflow.

Quando `MLFLOW_TRACKING_URI` não está definido, todas as funções viram no-op
(devolvem `None` ou listas vazias). Isso permite que o backend Iana rode sem
um tracking server em desenvolvimento e nos testes.

Falhas de rede contra o tracking server são engolidas: o treinamento principal
não pode quebrar porque o MLflow caiu.
"""
from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

_EXPERIMENT_DEFAULT = os.environ.get("MLFLOW_EXPERIMENT", "iana-treinamento")


def mlflow_enabled() -> bool:
    return bool(os.environ.get("MLFLOW_TRACKING_URI"))


def _import_mlflow():
    """Importa o módulo mlflow só quando necessário (lazy)."""
    try:
        import mlflow  # type: ignore
        return mlflow
    except ImportError:
        logger.warning("Pacote 'mlflow' não instalado; logging desativado.")
        return None


@contextlib.contextmanager
def log_run(
    *,
    run_name: str,
    params: Optional[dict[str, Any]] = None,
    tags: Optional[dict[str, Any]] = None,
    experiment: Optional[str] = None,
) -> Iterator[Optional[str]]:
    """Context manager que abre um run e devolve seu `run_id` (ou None).

    Uso típico:

        with log_run(run_name="random_forest", params=hp) as run_id:
            # ... treinar ...
            log_metrics({"acc": 0.92}, run_id=run_id)
    """
    if not mlflow_enabled():
        yield None
        return

    mlflow = _import_mlflow()
    if mlflow is None:
        yield None
        return

    try:
        mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
        mlflow.set_experiment(experiment or _EXPERIMENT_DEFAULT)
        active = mlflow.start_run(run_name=run_name)
    except Exception as e:
        logger.warning(f"mlflow.start_run falhou: {e}; seguindo sem logging.")
        yield None
        return

    run_id = active.info.run_id
    try:
        if params:
            try:
                mlflow.log_params(_coagir_params(params))
            except Exception as e:
                logger.warning(f"mlflow.log_params falhou: {e}")
        if tags:
            try:
                mlflow.set_tags({str(k): str(v) for k, v in tags.items()})
            except Exception as e:
                logger.warning(f"mlflow.set_tags falhou: {e}")
        yield run_id
    finally:
        try:
            mlflow.end_run()
        except Exception as e:
            logger.warning(f"mlflow.end_run falhou: {e}")


def log_metrics(metrics: dict[str, float], *, run_id: Optional[str]) -> None:
    if run_id is None or not mlflow_enabled():
        return
    mlflow = _import_mlflow()
    if mlflow is None:
        return
    try:
        with mlflow.start_run(run_id=run_id, nested=False):
            mlflow.log_metrics({k: float(v) for k, v in metrics.items() if _is_number(v)})
    except Exception as e:
        logger.warning(f"mlflow.log_metrics falhou: {e}")


def log_bytes_artifact(
    payload: bytes, *, run_id: Optional[str], filename: str, artifact_path: Optional[str] = None
) -> None:
    """Loga `payload` como artifact (escrevendo em tempfile primeiro)."""
    if run_id is None or not mlflow_enabled():
        return
    mlflow = _import_mlflow()
    if mlflow is None:
        return
    try:
        with tempfile.TemporaryDirectory(prefix="mlflow_artifact_") as tmp:
            path = Path(tmp) / filename
            path.write_bytes(payload)
            with mlflow.start_run(run_id=run_id, nested=False):
                mlflow.log_artifact(str(path), artifact_path=artifact_path)
    except Exception as e:
        logger.warning(f"mlflow.log_artifact falhou: {e}")


def _coagir_params(params: dict[str, Any]) -> dict[str, str]:
    """MLflow exige params str-serializável e ≤500 chars."""
    out: dict[str, str] = {}
    for k, v in params.items():
        if v is None:
            continue
        s = str(v)
        if len(s) > 500:
            s = s[:497] + "..."
        out[str(k)] = s
    return out


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ============================================================
# Leitura de runs (usado pelo endpoint /tutor/artefatos/{run_id})
# ============================================================
def get_run_summary(run_id: str) -> Optional[dict[str, Any]]:
    """Devolve dict {params, metrics, artifacts, tags} ou None se MLflow desativado."""
    if not mlflow_enabled():
        return None
    mlflow = _import_mlflow()
    if mlflow is None:
        return None
    try:
        mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
        client = mlflow.tracking.MlflowClient()
        run = client.get_run(run_id)
        artifacts = client.list_artifacts(run_id)
        return {
            "run_id": run_id,
            "params": dict(run.data.params),
            "metrics": dict(run.data.metrics),
            "tags": {k: v for k, v in run.data.tags.items() if not k.startswith("mlflow.")},
            "artifacts": [
                {"path": a.path, "is_dir": a.is_dir, "file_size": a.file_size}
                for a in artifacts
            ],
            "status": run.info.status,
            "start_time": run.info.start_time,
            "end_time": run.info.end_time,
        }
    except Exception as e:
        logger.warning(f"get_run_summary falhou para {run_id}: {e}")
        return None
