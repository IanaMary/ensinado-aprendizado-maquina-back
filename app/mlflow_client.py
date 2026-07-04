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


def log_sklearn_model(
    modelo: Any,
    *,
    run_id: Optional[str],
    artifact_path: str = "model",
    input_example: Any = None,
) -> None:
    """Loga `modelo` como um modelo `mlflow.sklearn` (gera MLmodel, requirements.txt,
    python_env.yaml e — com `input_example` — o exemplo de entrada/uso).

    No-op quando o MLflow está desativado; best-effort (uma falha aqui não pode
    quebrar o treinamento). A inferência de assinatura roda um `predict` no
    `input_example`, então é embrulhada no try/except.
    """
    if run_id is None or not mlflow_enabled():
        return
    mlflow = _import_mlflow()
    if mlflow is None:
        return
    try:
        import mlflow.sklearn  # type: ignore

        def _logar():
            # cloudpickle (formato sklearn tradicional): serializa qualquer estimador.
            # O default do MLflow 3.x (skops) recusa tipos "não confiáveis" como o
            # KDTree do KNN, quebrando o log_model.
            mlflow.sklearn.log_model(
                modelo, artifact_path=artifact_path, input_example=input_example,
                serialization_format="cloudpickle",
            )

        # Normalmente este helper roda DENTRO do `log_run` (run já ativo). Só reata
        # o run se não houver um ativo com o mesmo id — senão o start_run duplicado
        # dá "Run already active".
        ativo = mlflow.active_run()
        if ativo is not None and ativo.info.run_id == run_id:
            _logar()
        else:
            with mlflow.start_run(run_id=run_id, nested=False):
                _logar()
    except Exception as e:
        logger.warning(f"mlflow.sklearn.log_model falhou: {e}")


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


def _listar_modelos(client, run) -> list[dict]:
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
        try:
            encontrados = client.search_logged_models(experiment_ids=exp_ids, max_results=100)
        except Exception as e:  # pragma: no cover - defensivo
            logger.warning("Falha ao buscar modelos logados: %s", e)
            return []
    modelos: list[dict] = []
    for lm in (encontrados or []):
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


def get_run_summary(run_id: str) -> Optional[dict[str, Any]]:
    """Resumo da run: params/metrics/tags (sem tags internas mlflow.*), artefatos
    (recursivo) e modelos logados. None se MLflow desativado, run inexistente ou erro
    (o endpoint mapeia None → 404)."""
    if not mlflow_enabled():
        return None
    mlflow = _import_mlflow()
    if mlflow is None:
        return None
    try:
        mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
        client = mlflow.tracking.MlflowClient()
        run = client.get_run(run_id)
        return {
            "run_id": run_id,
            "params": dict(run.data.params),
            "metrics": dict(run.data.metrics),
            "tags": {k: v for k, v in run.data.tags.items() if not k.startswith("mlflow.")},
            "artifacts": _coletar_recursivo(lambda p: client.list_artifacts(run_id, p)),
            "models": _listar_modelos(client, run),
            "status": run.info.status,
            "start_time": run.info.start_time,
            "end_time": run.info.end_time,
        }
    except Exception as e:
        logger.warning(f"get_run_summary falhou para {run_id}: {e}")
        return None
