from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
import pytest


@pytest.mark.asyncio
async def test_listar_audit_vazio(client, mock_db, auth_headers):
  from app.routers import tutor as tutor_router
  cursor = MagicMock()
  cursor.sort = MagicMock(return_value=cursor)
  cursor.limit = MagicMock(return_value=cursor)
  cursor.to_list = AsyncMock(return_value=[])
  tutor_router.tutor_audit.find = MagicMock(return_value=cursor)

  resp = await client.get("/tutor/audit?pipe=inicio", headers=auth_headers)
  assert resp.status_code == 200
  assert resp.json() == []


@pytest.mark.asyncio
async def test_listar_audit_com_entradas(client, mock_db, auth_headers):
  from app.routers import tutor as tutor_router
  ts = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
  doc = {
    "_id": ObjectId(),
    "pipe": "inicio",
    "operacao": "atualizar_descricao",
    "campos_alterados": ["texto_pipe"],
    "usuario_email": "prof@exemplo.com",
    "usuario_nome": "Prof",
    "timestamp": ts,
  }
  cursor = MagicMock()
  cursor.sort = MagicMock(return_value=cursor)
  cursor.limit = MagicMock(return_value=cursor)
  cursor.to_list = AsyncMock(return_value=[doc])
  tutor_router.tutor_audit.find = MagicMock(return_value=cursor)

  resp = await client.get("/tutor/audit?pipe=inicio", headers=auth_headers)
  assert resp.status_code == 200
  body = resp.json()
  assert len(body) == 1
  assert body[0]["pipe"] == "inicio"
  assert body[0]["usuario_email"] == "prof@exemplo.com"
  assert body[0]["campos_alterados"] == ["texto_pipe"]
  assert body[0]["timestamp"].startswith("2026-06-15")
