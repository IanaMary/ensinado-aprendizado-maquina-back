"""Testes do wrapper app/mlflow_client.py."""
from unittest.mock import MagicMock, patch

import pytest

from app import mlflow_client


def test_disabled_quando_uri_ausente(monkeypatch):
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    assert mlflow_client.mlflow_enabled() is False
    with mlflow_client.log_run(run_name="x", params={"a": 1}) as run_id:
        assert run_id is None
    # Métricas e artefatos viram no-op silencioso.
    mlflow_client.log_metrics({"acc": 0.9}, run_id=None)
    mlflow_client.log_bytes_artifact(b"x", run_id=None, filename="x.png")
    assert mlflow_client.get_run_summary("any") is None


def test_log_run_chama_sdk_quando_ativado(monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://fake-mlflow:5000")
    fake_mlflow = MagicMock()
    fake_mlflow.start_run.return_value.info.run_id = "fake-run-123"

    with patch.object(mlflow_client, "_import_mlflow", return_value=fake_mlflow):
        with mlflow_client.log_run(
            run_name="run-x",
            params={"n_estimators": 100, "criterion": "gini"},
            tags={"modelo": "random_forest"},
        ) as run_id:
            assert run_id == "fake-run-123"

    fake_mlflow.set_tracking_uri.assert_called_with("http://fake-mlflow:5000")
    fake_mlflow.start_run.assert_called_once()
    fake_mlflow.log_params.assert_called_once()
    fake_mlflow.set_tags.assert_called_once()
    fake_mlflow.end_run.assert_called_once()


def test_log_run_swallows_start_run_error(monkeypatch):
    """Tracking server fora do ar não pode derrubar o treinamento."""
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://broken:5000")
    fake_mlflow = MagicMock()
    fake_mlflow.start_run.side_effect = RuntimeError("connection refused")

    with patch.object(mlflow_client, "_import_mlflow", return_value=fake_mlflow):
        with mlflow_client.log_run(run_name="x", params={"a": 1}) as run_id:
            assert run_id is None


def test_get_run_summary(monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://fake:5000")
    fake_mlflow = MagicMock()
    run = MagicMock()
    run.data.params = {"n_estimators": "100"}
    run.data.metrics = {"accuracy": 0.91}
    run.data.tags = {"modelo": "random_forest", "mlflow.runName": "rf-run"}
    run.info.status = "FINISHED"
    run.info.start_time = 1
    run.info.end_time = 2
    fake_mlflow.tracking.MlflowClient.return_value.get_run.return_value = run
    artifact = MagicMock(path="visualizacoes/cm.png", is_dir=False, file_size=1234)
    fake_mlflow.tracking.MlflowClient.return_value.list_artifacts.return_value = [artifact]

    with patch.object(mlflow_client, "_import_mlflow", return_value=fake_mlflow):
        summary = mlflow_client.get_run_summary("rid")

    assert summary["run_id"] == "rid"
    assert summary["params"] == {"n_estimators": "100"}
    assert summary["metrics"] == {"accuracy": 0.91}
    assert summary["tags"] == {"modelo": "random_forest"}  # tags mlflow.* filtradas
    assert summary["artifacts"] == [
        {"path": "visualizacoes/cm.png", "is_dir": False, "file_size": 1234}
    ]
