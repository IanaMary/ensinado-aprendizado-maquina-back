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
async def test_patch_habilitado_aluno_403(client, mock_db, auth_headers):
  """Aluno autenticado NÃO pode habilitar/desabilitar (gate de papel)."""
  mock_db["usuarios"].find_one = AsyncMock(
    return_value={"_id": ObjectId(), "email": "test@test.com", "role": "aluno", "nome": "Aluno"}
  )
  resp = await client.patch(
    f"/conf_pipeline/modelos/{ObjectId()}/habilitado",
    json={"habilitado": False},
    headers=auth_headers,
  )
  assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_modelo_habilitado_ok(client, mock_db, auth_headers):
  from app.routers import conf_pipeline
  conf_pipeline.opcoes_modelos.update_one = AsyncMock(
    return_value=MagicMock(matched_count=1, modified_count=1)
  )
  oid = str(ObjectId())
  resp = await client.patch(
    f"/conf_pipeline/modelos/{oid}/habilitado",
    json={"habilitado": False},
    headers=auth_headers,
  )
  assert resp.status_code == 200
  body = resp.json()
  assert body["id"] == oid
  assert body["habilitado"] is False


@pytest.mark.asyncio
async def test_patch_metrica_habilitado_id_invalido(client, mock_db, auth_headers):
  resp = await client.patch(
    "/conf_pipeline/metricas/nao-eh-objectid/habilitado",
    json={"habilitado": True},
    headers=auth_headers,
  )
  assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_coleta_habilitado_nao_encontrado(client, mock_db, auth_headers):
  from app.routers import conf_pipeline
  conf_pipeline.opcoes_coletas.update_one = AsyncMock(
    return_value=MagicMock(matched_count=0, modified_count=0)
  )
  oid = str(ObjectId())
  resp = await client.patch(
    f"/conf_pipeline/coleta_dados/{oid}/habilitado",
    json={"habilitado": True},
    headers=auth_headers,
  )
  assert resp.status_code == 404
