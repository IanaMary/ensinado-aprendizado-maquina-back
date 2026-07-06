"""Testes dos endpoints de artefatos (lista por usuário/data + detalhe da run)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _fake_run(run_id="abc123", exp_id="0"):
    return SimpleNamespace(
        info=SimpleNamespace(run_id=run_id, experiment_id=exp_id, status="FINISHED", start_time=1, end_time=2),
        data=SimpleNamespace(params={"n": "100"}, metrics={"acc": 0.9}, tags={"m": "rf", "mlflow.runName": "rf"}),
    )


def _fi(path, is_dir=False, file_size=10):
    return SimpleNamespace(path=path, is_dir=is_dir, file_size=file_size)


def _fake_mlflow(client):
    fake = MagicMock()
    fake.tracking.MlflowClient.return_value = client
    return fake


class _AsyncCursor:
    def __init__(self, docs):
        self._docs = docs
    def sort(self, *a, **k):
        return self
    def skip(self, *a, **k):
        return self
    def limit(self, *a, **k):
        return self
    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()


class TestGetRunSummary:
    """get_run_summary consolidado em app.mlflow_client (modelos + recursão + filtro de tags)."""

    def test_inclui_modelos_e_filtra_tags_internas(self, monkeypatch):
        import app.mlflow_client as mc
        monkeypatch.setenv("MLFLOW_TRACKING_URI", "sqlite:///x")
        lm = SimpleNamespace(
            source_run_id="abc123", model_id="m1", name="rf",
            model_uri="models:/m1", model_type="sklearn", status="READY",
        )
        client = MagicMock()
        client.get_run.return_value = _fake_run()
        client.list_artifacts.return_value = [_fi("plot.png")]
        client.search_logged_models.return_value = [lm]
        client.list_logged_model_artifacts.return_value = [_fi("model.joblib", file_size=4096)]
        monkeypatch.setattr(mc, "_import_mlflow", lambda: _fake_mlflow(client))

        out = mc.get_run_summary("abc123")
        assert out["artifacts"][0]["path"] == "plot.png"
        assert out["models"][0]["model_id"] == "m1"
        assert out["models"][0]["artifacts"][0]["path"] == "model.joblib"
        assert "mlflow.runName" not in out["tags"]  # tag interna filtrada
        assert out["tags"]["m"] == "rf"

    def test_desativado_retorna_none(self, monkeypatch):
        import app.mlflow_client as mc
        monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
        assert mc.get_run_summary("abc123") is None


class TestListarModelos:
    def test_exclui_modelo_de_outra_run(self):
        from app.mlflow_client import _listar_modelos
        client = MagicMock()
        client.search_logged_models.return_value = [
            SimpleNamespace(source_run_id="OUTRA", model_id="m9", name="x", model_uri="u", model_type=None, status=None)
        ]
        assert _listar_modelos(client, _fake_run()) == []  # filtrado por source_run_id

    def test_falha_retorna_vazio(self):
        from app.mlflow_client import _listar_modelos
        client = MagicMock()
        client.search_logged_models.side_effect = RuntimeError("indisponível")
        assert _listar_modelos(client, _fake_run()) == []


class TestListarRuns:
    @pytest.mark.asyncio
    async def test_admin_lista_por_usuario(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        mock_db["mlflow_runs"].count_documents = AsyncMock(return_value=1)
        mock_db["mlflow_runs"].find = MagicMock(return_value=_AsyncCursor([
            {"_id": "x", "mlflow_run_id": "abc123", "usuario_nome": "Ana", "modelo": "knn"}
        ]))
        resp = await client.get("/tutor/artefatos?usuario_id=u1", headers=auth_headers)
        assert resp.status_code == 200
        dados = resp.json()
        assert dados["total"] == 1
        assert dados["itens"][0]["run_id"] == "abc123"

    @pytest.mark.asyncio
    async def test_filtra_por_modelo_e_papel(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        cd = AsyncMock(return_value=0)
        mock_db["mlflow_runs"].count_documents = cd
        mock_db["mlflow_runs"].find = MagicMock(return_value=_AsyncCursor([]))
        resp = await client.get("/tutor/artefatos?modelo=knn&papel=professor&dataset=iris", headers=auth_headers)
        assert resp.status_code == 200
        filtro = cd.call_args[0][0]
        assert filtro["modelo"] == "knn"
        assert filtro["usuario_role"] == "professor"
        assert filtro["dataset_nome"] == "iris"

    @pytest.mark.asyncio
    async def test_facetas(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        mock_db["mlflow_runs"].distinct = AsyncMock(side_effect=[
            ["random_forest", "knn", None], ["professor", "aluno"], ["wine", "iris"]])
        resp = await client.get("/tutor/artefatos/facetas", headers=auth_headers)
        assert resp.status_code == 200
        dados = resp.json()
        assert dados["modelos"] == ["knn", "random_forest"]   # sem None, ordenado
        assert dados["papeis"] == ["aluno", "professor"]
        assert dados["datasets"] == ["iris", "wine"]

    @pytest.mark.asyncio
    async def test_contexto_liga_run_a_atividade_e_turma(self, client, mock_db, auth_headers, mock_admin):
        from bson import ObjectId
        from unittest.mock import patch
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        aid, tid = ObjectId(), ObjectId()
        sub = {"_id": ObjectId(), "nome": "Sub do aluno", "atividade_id": str(aid), "turma_id": str(tid)}
        pipes = MagicMock(aggregate=MagicMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=[sub]))))
        ativs = MagicMock(find_one=AsyncMock(return_value={"_id": aid, "titulo": "Classificar flores", "turma_id": str(tid)}))
        turms = MagicMock(find_one=AsyncMock(return_value={"_id": tid, "nome": "9A"}))
        with patch("app.routers.artefatos.pipelines", pipes), \
             patch("app.routers.artefatos.atividades", ativs), \
             patch("app.routers.artefatos.turmas", turms):
            resp = await client.get("/tutor/artefatos/abc123def456/contexto", headers=auth_headers)
        assert resp.status_code == 200
        v = resp.json()["vinculos"]
        assert len(v) == 1
        assert v[0]["atividade_titulo"] == "Classificar flores"
        assert v[0]["turma_nome"] == "9A"

    @pytest.mark.asyncio
    async def test_aluno_nao_pode_listar(self, client, mock_db, auth_headers):
        resp = await client.get("/tutor/artefatos", headers=auth_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_lista_data_invalida_400(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        resp = await client.get("/tutor/artefatos?data_inicio=nao-e-data", headers=auth_headers)
        assert resp.status_code == 400


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
