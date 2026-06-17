"""Testes da validação do bloco `execucao` em /conf_pipeline/catalogo."""
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
import pytest


@pytest.fixture(autouse=True)
def _como_admin(mock_db):
    """Escrita do catálogo exige admin/professor; eleva o usuário de teste."""
    mock_db["usuarios"].find_one = AsyncMock(
        return_value={"_id": ObjectId(), "email": "test@test.com", "role": "admin", "nome": "Admin"}
    )


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
async def test_put_execucao_metrica_com_funcao_passa(client, mock_db, auth_headers):
    """Métrica usa execucao.funcao (não classe) — deve passar na validação."""
    from app.routers import conf_pipeline
    conf_pipeline.opcoes_metricas.update_one = AsyncMock(
        return_value=MagicMock(matched_count=1, modified_count=1)
    )
    conf_pipeline.tutor_audit.insert_one = AsyncMock()
    oid = str(ObjectId())
    resp = await client.put(
        f"/conf_pipeline/catalogo/metricas/{oid}",
        json={"execucao": {"modulo": "sklearn.metrics", "funcao": "balanced_accuracy_score", "hiperparametros": []}},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_put_execucao_classe_e_funcao_juntas_400(client, mock_db, auth_headers):
    from app.routers import conf_pipeline
    conf_pipeline.opcoes_modelos.update_one = AsyncMock(
        return_value=MagicMock(matched_count=1, modified_count=1)
    )
    oid = str(ObjectId())
    resp = await client.put(
        f"/conf_pipeline/catalogo/modelos/{oid}",
        json={"execucao": {"modulo": "sklearn.metrics", "classe": "X", "funcao": "y"}},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "exatamente um" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_modelo_sem_execucao_400(client, mock_db, auth_headers):
    """Criar modelo sem execucao deve ser barrado (item inerte: 404 no treino, codegen quebrado)."""
    from app.routers import conf_pipeline
    conf_pipeline.opcoes_modelos.find_one = AsyncMock(return_value=None)
    conf_pipeline.opcoes_modelos.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    resp = await client.post(
        "/conf_pipeline/catalogo/modelos",
        json={"valor": "extra_trees", "label": "Extra Trees"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "execucao" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_modelo_com_execucao_seta_flags(client, mock_db, auth_headers):
    from app.routers import conf_pipeline
    conf_pipeline.opcoes_modelos.find_one = AsyncMock(return_value=None)
    captured = {}
    async def _insert(doc):
        captured.update(doc)
        return MagicMock(inserted_id=ObjectId())
    conf_pipeline.opcoes_modelos.insert_one = AsyncMock(side_effect=_insert)
    conf_pipeline.tutor_audit.insert_one = AsyncMock()
    resp = await client.post(
        "/conf_pipeline/catalogo/modelos",
        json={"valor": "extra_trees", "label": "Extra Trees",
              "execucao": {"modulo": "sklearn.ensemble", "classe": "ExtraTreesClassifier", "hiperparametros": []}},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert captured.get("prever_categoria") is True
    assert captured.get("dados_rotulados") is True


@pytest.mark.asyncio
async def test_put_execucao_prefixo_imitacao_400(client, mock_db, auth_headers):
    """'xgboost_evil' não deve passar (fix do startswith sem ponto final)."""
    from app.routers import conf_pipeline
    conf_pipeline.opcoes_modelos.update_one = AsyncMock(
        return_value=MagicMock(matched_count=1, modified_count=1)
    )
    oid = str(ObjectId())
    resp = await client.put(
        f"/conf_pipeline/catalogo/modelos/{oid}",
        json={"execucao": {"modulo": "xgboost_evil", "classe": "Boom"}},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "permitida" in resp.json()["detail"].lower()


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
