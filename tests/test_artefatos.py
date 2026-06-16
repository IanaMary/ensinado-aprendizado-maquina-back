"""Testes do endpoint GET /tutor/artefatos/{run_id}."""
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_503_quando_mlflow_desativado(client, mock_db, auth_headers, monkeypatch):
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    resp = await client.get("/tutor/artefatos/abc123", headers=auth_headers)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_404_quando_run_nao_existe(client, mock_db, auth_headers, monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://fake:5000")
    with patch("app.routers.artefatos.get_run_summary", return_value=None):
        resp = await client.get("/tutor/artefatos/abc123", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_200_devolve_summary(client, mock_db, auth_headers, monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://fake:5000")
    summary = {
        "run_id": "abc123",
        "params": {"n_estimators": "100"},
        "metrics": {"accuracy": 0.93},
        "tags": {"modelo": "random_forest"},
        "artifacts": [{"path": "model/model.joblib", "is_dir": False, "file_size": 4096}],
        "status": "FINISHED",
        "start_time": 1,
        "end_time": 2,
    }
    with patch("app.routers.artefatos.get_run_summary", return_value=summary):
        resp = await client.get("/tutor/artefatos/abc123", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "abc123"
    assert body["metrics"]["accuracy"] == 0.93
    assert body["artifacts"][0]["path"] == "model/model.joblib"


@pytest.mark.asyncio
async def test_400_run_id_invalido(client, mock_db, auth_headers, monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://fake:5000")
    resp = await client.get("/tutor/artefatos/" + "x" * 100, headers=auth_headers)
    assert resp.status_code == 400
