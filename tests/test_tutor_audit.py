"""`GET /tutor/audit` — histórico de edições do conteúdo do tutor.

O gate é admin/professor porque as entradas trazem nome e e-mail de quem editou (e, no caso da
instrução de sistema, o texto anterior). Daí o `find_one` de usuário devolver um professor nos
dois testes: o fixture padrão é aluno.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
import pytest


def _professor():
  return {"_id": ObjectId(), "email": "prof@exemplo.com", "nome_usuario": "Prof",
          "role": "professor"}


@pytest.mark.asyncio
async def test_listar_audit_vazio(client, mock_db, auth_headers):
  from app.routers import tutor as tutor_router
  mock_db["usuarios"].find_one = AsyncMock(return_value=_professor())
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
  mock_db["usuarios"].find_one = AsyncMock(return_value=_professor())
  ts = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
  doc = {
    "_id": ObjectId(),
    "pipe": "inicio",
    "operacao": "atualizar_descricao",
    "campos_alterados": ["texto_pipe"],
    "tamanho": 320,
    "texto_anterior": "não pode sair por esta rota",
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
  assert body[0]["tamanho"] == 320          # gravado desde sempre, agora chega à UI
  # A projeção é explícita: o texto anterior fica no banco (para a edição ser reversível), mas
  # não sai por esta rota.
  assert "texto_anterior" not in body[0]


@pytest.mark.asyncio
async def test_aluno_nao_le_o_historico(client, mock_db, auth_headers):
  """As entradas identificam admins/professores por nome e e-mail."""
  resp = await client.get("/tutor/audit?pipe=llm", headers=auth_headers)
  assert resp.status_code == 403
