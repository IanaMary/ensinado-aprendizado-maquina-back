"""Testes do endpoint GET /tutor/artefatos/{run_id}."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _fake_run(run_id="abc123", exp_id="0"):
    return SimpleNamespace(
        info=SimpleNamespace(run_id=run_id, experiment_id=exp_id, status="FINISHED", start_time=1, end_time=2),
        data=SimpleNamespace(params={"n": "100"}, metrics={"acc": 0.9}, tags={"m": "rf"}),
    )


def _fi(path, is_dir=False, file_size=10):
    return SimpleNamespace(path=path, is_dir=is_dir, file_size=file_size)


class TestGetRunSummaryModelos:
    def test_inclui_modelos_logados(self, monkeypatch):
        import app.routers.artefatos as mod
        lm = SimpleNamespace(
            source_run_id="abc123", model_id="m1", name="rf",
            model_uri="models:/m1", model_type="sklearn", status="READY",
        )
        client = MagicMock()
        client.get_run.return_value = _fake_run()
        client.list_artifacts.return_value = [_fi("plot.png")]
        client.search_logged_models.return_value = [lm]
        client.list_logged_model_artifacts.return_value = [_fi("model.joblib", file_size=4096)]
        monkeypatch.setattr(mod, "MlflowClient", lambda: client)

        out = mod.get_run_summary("abc123")
        assert out["artifacts"][0]["path"] == "plot.png"
        assert len(out["models"]) == 1
        assert out["models"][0]["model_id"] == "m1"
        assert out["models"][0]["artifacts"][0]["path"] == "model.joblib"

    def test_exclui_modelo_de_outra_run(self, monkeypatch):
        import app.routers.artefatos as mod
        outro = SimpleNamespace(
            source_run_id="OUTRA", model_id="m9", name="x",
            model_uri="models:/m9", model_type=None, status=None,
        )
        client = MagicMock()
        client.get_run.return_value = _fake_run()
        client.list_artifacts.return_value = []
        client.search_logged_models.return_value = [outro]
        monkeypatch.setattr(mod, "MlflowClient", lambda: client)

        out = mod.get_run_summary("abc123")
        assert out["models"] == []  # filtrado por source_run_id

    def test_falha_em_modelos_nao_quebra_resumo(self, monkeypatch):
        import app.routers.artefatos as mod
        client = MagicMock()
        client.get_run.return_value = _fake_run()
        client.list_artifacts.return_value = [_fi("a.txt")]
        client.search_logged_models.side_effect = RuntimeError("indisponível")
        monkeypatch.setattr(mod, "MlflowClient", lambda: client)

        out = mod.get_run_summary("abc123")
        assert out["models"] == []
        assert out["artifacts"][0]["path"] == "a.txt"  # resumo segue íntegro


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
