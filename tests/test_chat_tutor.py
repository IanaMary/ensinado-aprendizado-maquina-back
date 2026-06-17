import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_async_client(status_code=200, json_body=None):
    """Cria um substituto de httpx.AsyncClient usavel como `async with`."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_body or {})

    client = MagicMock()
    client.post = AsyncMock(return_value=resp)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=cm)
    return factory


class TestChatTutor:
    @pytest.mark.asyncio
    async def test_chat_responde_com_contexto(self, client, mock_db, auth_headers, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-de-teste")
        body = {"choices": [{"message": {"content": "A Árvore de Decisão separa os dados por perguntas."}}]}
        factory = _mock_async_client(200, body)

        with patch("app.routers.chat_tutor.httpx.AsyncClient", factory):
            response = await client.post(
                "/tutor/chat",
                headers=auth_headers,
                json={
                    "mensagens": [{"role": "user", "content": "O que é uma árvore de decisão?"}],
                    "contexto": {"modelo": "arvore_decisao"},
                },
            )
        assert response.status_code == 200
        assert "Árvore de Decisão" in response.json()["resposta"]

    @pytest.mark.asyncio
    async def test_chat_sem_chave_retorna_503(self, client, mock_db, auth_headers, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        response = await client.post(
            "/tutor/chat",
            headers=auth_headers,
            json={"mensagens": [{"role": "user", "content": "oi"}]},
        )
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_chat_sem_mensagem_usuario_retorna_400(self, client, mock_db, auth_headers, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-de-teste")
        response = await client.post(
            "/tutor/chat",
            headers=auth_headers,
            json={"mensagens": []},
        )
        assert response.status_code == 400


class TestSaudeModelos:
    @pytest.mark.asyncio
    async def test_modelo_que_responde(self):
        from app.routers.chat_tutor import _testar_modelo
        resp = MagicMock()
        resp.status_code = 200
        cliente = MagicMock()
        cliente.post = AsyncMock(return_value=resp)
        out = await _testar_modelo(cliente, "chave", "meta/llama-3.3-70b-instruct")
        assert out["responde"] is True
        assert "latencia_ms" in out

    @pytest.mark.asyncio
    async def test_modelo_degradado(self):
        from app.routers.chat_tutor import _testar_modelo
        resp = MagicMock()
        resp.status_code = 400
        resp.json = MagicMock(return_value={"detail": "DEGRADED function cannot be invoked"})
        cliente = MagicMock()
        cliente.post = AsyncMock(return_value=resp)
        out = await _testar_modelo(cliente, "chave", "minimaxai/minimax-m3")
        assert out["responde"] is False
        assert "DEGRADED" in out["erro"]
