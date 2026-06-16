"""Testes da validação do bloco `execucao` em /conf_pipeline/catalogo."""
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
import pytest


@pytest.mark.asyncio
async def test_put_execucao_sklearn_passa(client, mock_db, auth_headers):
    from app.routers import conf_pipeline
    conf_pipeline.opcoes_modelos.update_one = AsyncMock(
        return_value=MagicMock(matched_count=1, modified_count=1)
    )
    conf_pipeline.tutor_audit.insert_one = AsyncMock()
    oid = str(ObjectId())
    resp = await client.put(
        f"/conf_pipeline/catalogo/modelos/{oid}",
        json={
            "execucao": {
                "modulo": "sklearn.ensemble",
                "classe": "RandomForestClassifier",
                "hiperparametros": [
                    {"nome": "n_estimators", "tipo": "int", "default": 100},
                    {"nome": "criterion", "tipo": "enum", "opcoes": ["gini", "entropy"], "default": "gini"},
                ],
            }
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_put_execucao_modulo_proibido_400(client, mock_db, auth_headers):
    from app.routers import conf_pipeline
    conf_pipeline.opcoes_modelos.update_one = AsyncMock(
        return_value=MagicMock(matched_count=1, modified_count=1)
    )
    oid = str(ObjectId())
    resp = await client.put(
        f"/conf_pipeline/catalogo/modelos/{oid}",
        json={"execucao": {"modulo": "os", "classe": "system"}},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "permitida" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_put_execucao_sem_modulo_400(client, mock_db, auth_headers):
    from app.routers import conf_pipeline
    conf_pipeline.opcoes_modelos.update_one = AsyncMock(
        return_value=MagicMock(matched_count=1, modified_count=1)
    )
    oid = str(ObjectId())
    resp = await client.put(
        f"/conf_pipeline/catalogo/modelos/{oid}",
        json={"execucao": {"classe": "RandomForestClassifier"}},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_put_execucao_enum_sem_opcoes_400(client, mock_db, auth_headers):
    from app.routers import conf_pipeline
    conf_pipeline.opcoes_modelos.update_one = AsyncMock(
        return_value=MagicMock(matched_count=1, modified_count=1)
    )
    oid = str(ObjectId())
    resp = await client.put(
        f"/conf_pipeline/catalogo/modelos/{oid}",
        json={
            "execucao": {
                "modulo": "sklearn.linear_model",
                "classe": "LogisticRegression",
                "hiperparametros": [{"nome": "solver", "tipo": "enum"}],
            }
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "opcoes" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_put_execucao_hiperparam_duplicado_400(client, mock_db, auth_headers):
    from app.routers import conf_pipeline
    conf_pipeline.opcoes_modelos.update_one = AsyncMock(
        return_value=MagicMock(matched_count=1, modified_count=1)
    )
    oid = str(ObjectId())
    resp = await client.put(
        f"/conf_pipeline/catalogo/modelos/{oid}",
        json={
            "execucao": {
                "modulo": "sklearn.ensemble",
                "classe": "RandomForestClassifier",
                "hiperparametros": [
                    {"nome": "n_estimators", "default": 100},
                    {"nome": "n_estimators", "default": 200},
                ],
            }
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "duplic" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_put_sem_execucao_continua_funcionando(client, mock_db, auth_headers):
    """Validação só dispara quando 'execucao' está no payload."""
    from app.routers import conf_pipeline
    conf_pipeline.opcoes_modelos.update_one = AsyncMock(
        return_value=MagicMock(matched_count=1, modified_count=1)
    )
    conf_pipeline.tutor_audit.insert_one = AsyncMock()
    oid = str(ObjectId())
    resp = await client.put(
        f"/conf_pipeline/catalogo/modelos/{oid}",
        json={"label": "Random Forest"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


# ---- pre_processamento: bloco execucao validado no PUT por valor ----

@pytest.mark.asyncio
async def test_put_pre_processamento_execucao_valida_passa(client, mock_db, auth_headers):
    from app.routers import conf_pipeline
    conf_pipeline.opcoes_pre_processamento.update_one = AsyncMock(
        return_value=MagicMock(matched_count=1, modified_count=1, upserted_id=None)
    )
    conf_pipeline.tutor_audit.insert_one = AsyncMock()
    resp = await client.put(
        "/conf_pipeline/pre_processamento_doc/standard_scaler",
        json={
            "label": "StandardScaler",
            "execucao": {
                "modulo": "sklearn.preprocessing",
                "classe": "StandardScaler",
                "hiperparametros": [],
            },
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_put_pre_processamento_modulo_proibido_400(client, mock_db, auth_headers):
    from app.routers import conf_pipeline
    conf_pipeline.opcoes_pre_processamento.update_one = AsyncMock(
        return_value=MagicMock(matched_count=1, modified_count=1)
    )
    resp = await client.put(
        "/conf_pipeline/pre_processamento_doc/malicioso",
        json={"execucao": {"modulo": "subprocess", "classe": "Popen"}},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "permitida" in resp.json()["detail"].lower()
