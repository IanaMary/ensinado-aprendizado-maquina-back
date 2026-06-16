"""Executa o fit() de um modelo em subprocesso isolado, com limites de recurso.

O processo pai (FastAPI) só prepara dados/spec e lê os artefatos produzidos pelo
filho. Falhas do filho (timeout, estouro de RAM, exceção do scikit-learn) não
derrubam o worker — viram `SandboxError` no pai.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


DEFAULT_MAX_RAM_MB = _env_int("SANDBOX_MAX_RAM_MB", 2048)
DEFAULT_MAX_CPU_SEC = _env_int("SANDBOX_MAX_CPU_SEC", 60)
DEFAULT_MAX_WALL_SEC = _env_int("SANDBOX_MAX_WALL_SEC", 120)

_REPO_ROOT = Path(__file__).resolve().parents[2]


class SandboxError(Exception):
    """Erro durante a execução do pipeline no sandbox."""

    def __init__(self, message: str, kind: str = "exception"):
        super().__init__(message)
        self.kind = kind


@dataclass
class TrainResult:
    model_bytes: bytes
    classes: list
    params: dict[str, Any]
    model_repr: str


def executar_treinamento(
    *,
    class_path: str,
    hiperparametros: dict[str, Any],
    X_train: pd.DataFrame,
    y_train: Optional[pd.Series],
    is_clustering: bool,
    pre_processamento: Optional[list[dict[str, Any]]] = None,
    max_ram_mb: int = DEFAULT_MAX_RAM_MB,
    max_cpu_sec: int = DEFAULT_MAX_CPU_SEC,
    max_wall_sec: int = DEFAULT_MAX_WALL_SEC,
) -> TrainResult:
    """Roda o fit em subprocesso isolado e devolve modelo serializado + metadados."""
    workdir = Path(tempfile.mkdtemp(prefix="iana_sandbox_"))
    try:
        X_train.to_pickle(workdir / "X_train.pkl")
        if not is_clustering:
            if y_train is None:
                raise SandboxError(
                    "y_train obrigatório para treino supervisionado.", "config"
                )
            y_train.to_pickle(workdir / "y_train.pkl")

        spec = {
            "class_path": class_path,
            "hiperparametros": hiperparametros,
            "is_clustering": is_clustering,
            "pre_processamento": pre_processamento or [],
            "max_ram_mb": max_ram_mb,
            "max_cpu_sec": max_cpu_sec,
        }
        (workdir / "spec.json").write_text(json.dumps(spec, default=str))

        cmd = [sys.executable, "-m", "app.sandbox.child", str(workdir)]
        env = os.environ.copy()
        # Garante que o filho encontre o pacote `app` mesmo se uvicorn alterou cwd.
        env["PYTHONPATH"] = str(_REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=max_wall_sec,
                cwd=str(_REPO_ROOT),
                env=env,
            )
        except subprocess.TimeoutExpired:
            raise SandboxError(
                f"Treinamento excedeu o tempo limite de {max_wall_sec}s.",
                "timeout",
            )

        result_path = workdir / "result.json"
        if not result_path.exists():
            stderr_tail = proc.stderr.decode("utf-8", errors="replace")[-2000:]
            raise SandboxError(
                f"Subprocesso terminou sem produzir result.json "
                f"(exit={proc.returncode}). stderr: {stderr_tail}",
                "crash",
            )

        result = json.loads(result_path.read_text())
        if not result.get("ok"):
            raise SandboxError(
                result.get("error", "erro desconhecido no subprocesso"),
                result.get("error_type", "exception"),
            )

        model_path = workdir / "model.joblib"
        if not model_path.exists():
            raise SandboxError("Modelo não foi gerado pelo subprocesso.", "crash")

        return TrainResult(
            model_bytes=model_path.read_bytes(),
            classes=result.get("classes", []),
            params=result.get("params", {}),
            model_repr=result.get("model_repr", ""),
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
