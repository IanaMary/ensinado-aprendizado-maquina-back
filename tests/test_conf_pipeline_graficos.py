from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
import pytest


@pytest.fixture(autouse=True)
def _como_admin(mock_db):
  mock_db["usuarios"].find_one = AsyncMock(
    return_value={"_id": ObjectId(), "email": "test@test.com", "role": "admin", "nome": "Admin"}
  )


@pytest.mark.asyncio
async def test_get_all_graficos(client, mock_db, auth_headers):
  from app.routers import conf_pipeline
  doc = {"_id": ObjectId(), "valor": "matriz_confusao", "label": "Matriz de confusão",
         "conteudo": {"titulo": "Matriz de confusão", "resumo_basico": "..."}}
  cursor = conf_pipeline.opcoes_graficos.find.return_value
  cursor.to_list = AsyncMock(return_value=[doc])
  resp = await client.get("/conf_pipeline/graficos/todos", headers=auth_headers)
  assert resp.status_code == 200, resp.text
  item = resp.json()[0]
  assert item["valor"] == "matriz_confusao"
  assert item["habilitado"] is True


@pytest.mark.asyncio
async def test_get_grafico_doc(client, mock_db, auth_headers):
  from app.routers import conf_pipeline
  conf_pipeline.opcoes_graficos.find_one = AsyncMock(
    return_value={"_id": ObjectId(), "valor": "silhouette",
                  "conteudo": {"titulo": "Silhouette"}}
  )
  resp = await client.get("/conf_pipeline/graficos/silhouette", headers=auth_headers)
  assert resp.status_code == 200
  assert resp.json()["valor"] == "silhouette"


@pytest.mark.asyncio
async def test_get_grafico_doc_404(client, mock_db, auth_headers):
  from app.routers import conf_pipeline
  conf_pipeline.opcoes_graficos.find_one = AsyncMock(return_value=None)
  resp = await client.get("/conf_pipeline/graficos/inexistente", headers=auth_headers)
  assert resp.status_code == 404


@pytest.mark.asyncio
async def test_put_grafico_doc_aluno_403(client, mock_db, auth_headers):
  mock_db["usuarios"].find_one = AsyncMock(
    return_value={"_id": ObjectId(), "email": "a@a.com", "role": "aluno", "nome": "Aluno"}
  )
  resp = await client.put(
    "/conf_pipeline/graficos_doc/silhouette",
    json={"conteudo": {"titulo": "X"}},
    headers=auth_headers,
  )
  assert resp.status_code == 403


@pytest.mark.asyncio
async def test_put_grafico_doc_upsert(client, mock_db, auth_headers):
  from app.routers import conf_pipeline
  conf_pipeline.opcoes_graficos.update_one = AsyncMock(
    return_value=MagicMock(matched_count=1, modified_count=1, upserted_id=None)
  )
  conf_pipeline.tutor_audit.insert_one = AsyncMock()
  resp = await client.put(
    "/conf_pipeline/graficos_doc/silhouette",
    json={"conteudo": {"titulo": "Silhouette", "resumo_basico": "..."}},
    headers=auth_headers,
  )
  assert resp.status_code == 200
  assert resp.json()["valor"] == "silhouette"
