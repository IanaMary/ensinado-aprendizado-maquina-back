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


# ------------------------------------------------- pré-processamento: upsert e gate
# Estes dois endpoints não tinham teste, e um clique do admin aqui atinge TODOS os alunos ao mesmo
# tempo: `DashboardService.carregarItens*` filtra `habilitado === false` antes de propagar, então o
# item desaparece do pipeline de quem estiver com a tela aberta — sem sintoma nenhum do lado de quem
# clicou.

@pytest.mark.asyncio
async def test_patch_pre_processamento_habilitado_faz_upsert(client, mock_db, auth_headers):
  """O `upsert=True` é essencial: os 10 built-ins podem não ter doc em `db.pre_processamento`, e
  sem upsert desabilitar um deles não gravaria nada — a tela mostraria o toggle mudando e o item
  continuaria disponível para os alunos."""
  from app.routers import conf_pipeline
  conf_pipeline.opcoes_pre_processamento.update_one = AsyncMock(
    return_value=MagicMock(matched_count=0, upserted_id=ObjectId())
  )

  resp = await client.patch(
    "/conf_pipeline/pre_processamento/standard_scaler/habilitado",
    json={"habilitado": False}, headers=auth_headers,
  )

  assert resp.status_code == 200
  assert resp.json() == {"valor": "standard_scaler", "habilitado": False}
  chamada = conf_pipeline.opcoes_pre_processamento.update_one.await_args
  assert chamada[0][0] == {"valor": "standard_scaler"}
  assert chamada[0][1]["$set"] == {"valor": "standard_scaler", "habilitado": False}
  assert chamada[1]["upsert"] is True


@pytest.mark.asyncio
async def test_patch_pre_processamento_recusa_valor_invalido(client, mock_db, auth_headers):
  """Guarda de tamanho: `valor` é chave de documento e vai para o filtro do Mongo."""
  resp = await client.patch(
    f"/conf_pipeline/pre_processamento/{'x' * 101}/habilitado",
    json={"habilitado": True}, headers=auth_headers,
  )
  assert resp.status_code == 400


@pytest.mark.asyncio
async def test_pre_processamento_habilitado_exige_papel(client, mock_db, auth_headers):
  """Aluno não desabilita pré-processador — seria negação de serviço para a turma inteira."""
  mock_db["usuarios"].find_one = AsyncMock(
    return_value={"_id": ObjectId(), "email": "test@test.com", "role": "aluno", "nome": "Aluno"}
  )
  resp = await client.patch(
    "/conf_pipeline/pre_processamento/standard_scaler/habilitado",
    json={"habilitado": False}, headers=auth_headers,
  )
  assert resp.status_code == 403
