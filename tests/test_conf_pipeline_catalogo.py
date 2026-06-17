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
async def test_get_modelos_sem_flags_nao_quebra(client, mock_db, auth_headers):
    """Modelo novo sem prever_categoria/dados_rotulados não pode derrubar a lane (B3)."""
    from app.routers import conf_pipeline
    doc = {"_id": ObjectId(), "valor": "extra_trees", "label": "Extra Trees",
           "execucao": {"modulo": "sklearn.ensemble", "classe": "ExtraTreesClassifier"}}
    cursor = conf_pipeline.opcoes_modelos.find.return_value
    cursor.to_list = AsyncMock(return_value=[doc])
    resp = await client.get("/conf_pipeline/modelos/todos?limite=100", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    item = resp.json()[0]
    assert item["valor"] == "extra_trees"
    assert item["preverCategoria"] is None  # ausente -> None, não KeyError 500


@pytest.mark.asyncio
async def test_post_item_aluno_403(client, mock_db, auth_headers):
  """Aluno autenticado NÃO pode criar item de catálogo (gate de papel)."""
  mock_db["usuarios"].find_one = AsyncMock(
    return_value={"_id": ObjectId(), "email": "test@test.com", "role": "aluno", "nome": "Aluno"}
  )
  resp = await client.post(
    "/conf_pipeline/catalogo/modelos",
    json={"valor": "x", "label": "X"},
    headers=auth_headers,
  )
  assert resp.status_code == 403


@pytest.mark.asyncio
async def test_put_item_atualiza_e_audita(client, mock_db, auth_headers):
  from app.routers import conf_pipeline
  conf_pipeline.opcoes_modelos.update_one = AsyncMock(
    return_value=MagicMock(matched_count=1, modified_count=1)
  )
  conf_pipeline.tutor_audit.insert_one = AsyncMock()
  oid = str(ObjectId())
  resp = await client.put(
    f"/conf_pipeline/catalogo/modelos/{oid}",
    json={"descricao_aluno": "Novo texto", "label": "Random Forest"},
    headers=auth_headers,
  )
  assert resp.status_code == 200
  body = resp.json()
  assert body["id"] == oid
  assert set(body["campos_alterados"]) == {"descricao_aluno", "label"}
  conf_pipeline.tutor_audit.insert_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_item_exige_valor_e_label(client, mock_db, auth_headers):
  from app.routers import conf_pipeline
  conf_pipeline.opcoes_metricas.find_one = AsyncMock(return_value=None)
  resp = await client.post(
    "/conf_pipeline/catalogo/metricas",
    json={"label": "F1"},
    headers=auth_headers,
  )
  assert resp.status_code == 400


@pytest.mark.asyncio
async def test_post_item_cria(client, mock_db, auth_headers):
  from app.routers import conf_pipeline
  conf_pipeline.opcoes_metricas.find_one = AsyncMock(return_value=None)
  novo_id = ObjectId()
  conf_pipeline.opcoes_metricas.insert_one = AsyncMock(
    return_value=MagicMock(inserted_id=novo_id)
  )
  conf_pipeline.tutor_audit.insert_one = AsyncMock()
  resp = await client.post(
    "/conf_pipeline/catalogo/metricas",
    json={"label": "F1 Score", "valor": "f1", "descricao_aluno": "ok",
          "execucao": {"modulo": "sklearn.metrics", "funcao": "f1_score", "hiperparametros": []}},
    headers=auth_headers,
  )
  assert resp.status_code == 200
  body = resp.json()
  assert body["id"] == str(novo_id)


@pytest.mark.asyncio
async def test_delete_item(client, mock_db, auth_headers):
  from app.routers import conf_pipeline
  conf_pipeline.opcoes_coletas.delete_one = AsyncMock(
    return_value=MagicMock(deleted_count=1)
  )
  conf_pipeline.tutor_audit.insert_one = AsyncMock()
  oid = str(ObjectId())
  resp = await client.delete(
    f"/conf_pipeline/catalogo/coleta_dados/{oid}",
    headers=auth_headers,
  )
  assert resp.status_code == 200
  assert resp.json()["removido"] is True


@pytest.mark.asyncio
async def test_put_pre_processamento_doc_upsert(client, mock_db, auth_headers):
  from app.routers import conf_pipeline
  conf_pipeline.opcoes_pre_processamento.update_one = AsyncMock(
    return_value=MagicMock(matched_count=1, modified_count=1, upserted_id=None)
  )
  conf_pipeline.tutor_audit.insert_one = AsyncMock()
  resp = await client.put(
    "/conf_pipeline/pre_processamento_doc/standard_scaler",
    json={"label": "Standard Scaler", "descricao_aluno": "padroniza"},
    headers=auth_headers,
  )
  assert resp.status_code == 200
  body = resp.json()
  assert body["valor"] == "standard_scaler"
