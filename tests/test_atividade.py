import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_async_client(status_code=200, json_body=None, raise_exc=None):
    """Substituto de httpx.AsyncClient usavel como `async with`."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_body or {})

    client = MagicMock()
    if raise_exc is not None:
        client.post = AsyncMock(side_effect=raise_exc)
    else:
        client.post = AsyncMock(return_value=resp)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


class _AsyncCursor:
    """Cursor mínimo: suporta .sort().skip().limit() e iteração assíncrona."""
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


class TestRegistrarAtividade:
    @pytest.mark.asyncio
    async def test_lote_grava_eventos(self, client, mock_db, auth_headers):
        body = {
            "eventos": [
                {"tipo": "pipeline", "acao": "treinou_modelo", "duracao_ms": 1200},
                {"tipo": "navegacao", "acao": "trocou_pagina", "detalhes": {"url": "/trilha"}},
            ]
        }
        resp = await client.post("/atividades/lote", headers=auth_headers, json=body)
        assert resp.status_code == 200
        assert resp.json()["gravados"] == 2
        # lote usa um único insert_many
        assert mock_db["atividade"].insert_many.call_count == 1
        docs = mock_db["atividade"].insert_many.call_args.args[0]
        assert len(docs) == 2
        assert all(d["origem"] == "frontend" for d in docs)

    @pytest.mark.asyncio
    async def test_lote_acima_do_limite_retorna_413(self, client, mock_db, auth_headers):
        from app.schemas.atividade import MAX_EVENTOS_LOTE
        eventos = [{"tipo": "ui", "acao": "clique"} for _ in range(MAX_EVENTOS_LOTE + 1)]
        resp = await client.post("/atividades/lote", headers=auth_headers, json={"eventos": eventos})
        assert resp.status_code == 413
        assert mock_db["atividade"].insert_many.call_count == 0

    @pytest.mark.asyncio
    async def test_lote_exige_autenticacao(self, client, mock_db):
        resp = await client.post("/atividades/lote", json={"eventos": []})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_evento_unico(self, client, mock_db, auth_headers):
        resp = await client.post(
            "/atividades", headers=auth_headers, json={"tipo": "ui", "acao": "abriu_modal"}
        )
        assert resp.status_code == 200
        assert resp.json()["gravados"] == 1
        # usuário derivado do JWT, não do corpo
        doc = mock_db["atividade"].insert_one.call_args.args[0]
        assert doc["usuario_email"] == "test@test.com"
        assert doc["origem"] == "frontend"


class TestRateLimit:
    @pytest.mark.asyncio
    async def test_excesso_retorna_429(self, client, mock_db, auth_headers, monkeypatch):
        import app.routers.atividade as mod
        mod._rate.clear()
        monkeypatch.setattr(mod, "_RATE_MAX", 2, raising=False)
        body = {"eventos": [{"tipo": "ui", "acao": "a"}, {"tipo": "ui", "acao": "b"}, {"tipo": "ui", "acao": "c"}]}
        resp = await client.post("/atividades/lote", headers=auth_headers, json=body)
        assert resp.status_code == 429
        assert mock_db["atividade"].insert_many.call_count == 0

    @pytest.mark.asyncio
    async def test_dentro_do_limite_grava(self, client, mock_db, auth_headers, monkeypatch):
        import app.routers.atividade as mod
        mod._rate.clear()
        monkeypatch.setattr(mod, "_RATE_MAX", 10, raising=False)
        body = {"eventos": [{"tipo": "ui", "acao": "a"}, {"tipo": "ui", "acao": "b"}]}
        resp = await client.post("/atividades/lote", headers=auth_headers, json=body)
        assert resp.status_code == 200
        assert resp.json()["gravados"] == 2


class TestValidacaoSchema:
    @pytest.mark.asyncio
    async def test_status_invalido_422(self, client, mock_db, auth_headers):
        resp = await client.post(
            "/atividades", headers=auth_headers, json={"tipo": "ui", "acao": "x", "status": "qualquer"}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_tipo_invalido_422(self, client, mock_db, auth_headers):
        resp = await client.post(
            "/atividades", headers=auth_headers, json={"tipo": "hackerman", "acao": "x"}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_duracao_negativa_422(self, client, mock_db, auth_headers):
        resp = await client.post(
            "/atividades", headers=auth_headers, json={"tipo": "ui", "acao": "x", "duracao_ms": -5}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_timestamp_invalido_e_descartado(self, client, mock_db, auth_headers):
        resp = await client.post(
            "/atividades", headers=auth_headers,
            json={"tipo": "ui", "acao": "x", "timestamp_cliente": "não-iso"},
        )
        assert resp.status_code == 200
        doc = mock_db["atividade"].insert_one.call_args.args[0]
        assert doc["timestamp_cliente"] is None


class TestTruncamento:
    def test_poda_string_longa_preservando_estrutura(self):
        from app.routers.atividade import _truncar_detalhes, _MAX_STR_LEAF
        d = {"resposta": "x" * (_MAX_STR_LEAF + 500), "modelo": "knn", "n": 3}
        out = _truncar_detalhes(d)
        assert out["modelo"] == "knn"  # estrutura preservada
        assert out["n"] == 3
        assert len(out["resposta"]) <= _MAX_STR_LEAF + 1  # truncado (+ "…")
        assert out["resposta"].endswith("…")

    def test_curto_passa_intacto(self):
        from app.routers.atividade import _truncar_detalhes
        d = {"a": "ok", "b": [1, 2, 3]}
        assert _truncar_detalhes(d) == d


class TestConsultaAtividades:
    @pytest.mark.asyncio
    async def test_aluno_nao_pode_listar(self, client, mock_db, auth_headers):
        # mock_user (default) tem role "aluno"
        resp = await client.get("/atividades", headers=auth_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_lista(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        mock_db["atividade"].count_documents = AsyncMock(return_value=1)
        mock_db["atividade"].find = MagicMock(
            return_value=_AsyncCursor([{"_id": "abc", "tipo": "chat", "acao": "resposta_tutor"}])
        )
        resp = await client.get("/atividades?tipo=chat", headers=auth_headers)
        assert resp.status_code == 200
        dados = resp.json()
        assert dados["total"] == 1
        assert dados["itens"][0]["tipo"] == "chat"
        assert dados["itens"][0]["id"] == "abc"

    @pytest.mark.asyncio
    async def test_admin_resumo(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        # resumo agora roda um único $facet — mock retorna o doc agregado
        facet = {
            "por_tipo": [{"_id": "chat", "total": 3}],
            "por_acao": [{"_id": "resposta_tutor", "total": 3, "duracao_media_ms": 1200.0}],
            "total": [{"n": 5}],
            "total_erros": [{"n": 1}],
            "usuarios": [{"n": 2}],
        }
        mock_db["atividade"].aggregate = MagicMock(return_value=_AsyncCursor([facet]))
        resp = await client.get("/atividades/resumo", headers=auth_headers)
        assert resp.status_code == 200
        dados = resp.json()
        assert dados["total"] == 5
        assert dados["total_erros"] == 1
        assert dados["usuarios_ativos"] == 2
        assert dados["por_tipo"][0] == {"tipo": "chat", "total": 3}
        assert dados["por_acao"][0]["duracao_media_ms"] == 1200.0

    @pytest.mark.asyncio
    async def test_resumo_vazio_nao_quebra(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        mock_db["atividade"].aggregate = MagicMock(return_value=_AsyncCursor([]))
        resp = await client.get("/atividades/resumo", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["usuarios_ativos"] == 0

    @pytest.mark.asyncio
    async def test_listar_sem_total(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        mock_db["atividade"].find = MagicMock(return_value=_AsyncCursor([]))
        resp = await client.get("/atividades?incluir_total=false", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] is None
        # não deve contar quando incluir_total=false
        assert mock_db["atividade"].count_documents.call_count == 0

    @pytest.mark.asyncio
    async def test_listar_data_invalida_400(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        resp = await client.get("/atividades?data_inicio=nao-e-data", headers=auth_headers)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_tempo_preso(self, client, mock_db, auth_headers, mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        agg = [{"_id": "rodou_trilha", "total": 4, "duracao_media_ms": 5000.0, "duracao_max_ms": 9000, "erros": 1}]
        mock_db["atividade"].aggregate = MagicMock(return_value=_AsyncCursor(agg))
        resp = await client.get("/atividades/tempo-preso", headers=auth_headers)
        assert resp.status_code == 200
        item = resp.json()["itens"][0]
        assert item["acao"] == "rodou_trilha"
        assert item["taxa_erro"] == 0.25
        assert item["duracao_max_ms"] == 9000

    @pytest.mark.asyncio
    async def test_tempo_preso_aluno_403(self, client, mock_db, auth_headers):
        resp = await client.get("/atividades/tempo-preso", headers=auth_headers)
        assert resp.status_code == 403


class TestIndiceTTL:
    @pytest.mark.asyncio
    async def test_cria_indice_ttl_no_timestamp(self, monkeypatch):
        import app.main as main
        col = MagicMock()
        col.create_index = AsyncMock()
        monkeypatch.setattr("app.database.atividade_usuario", col, raising=False)
        monkeypatch.setattr(main, "ATIVIDADE_TTL_DIAS", 30, raising=False)
        await main.criar_indices_atividade()
        # 1º índice = timestamp com TTL (retenção); demais sem expireAfterSeconds
        primeira = col.create_index.call_args_list[0]
        assert primeira.args[0] == [("timestamp", -1)]
        assert primeira.kwargs.get("expireAfterSeconds") == 30 * 86400
        assert col.create_index.call_count == 3

    @pytest.mark.asyncio
    async def test_ttl_desativado_quando_zero(self, monkeypatch):
        import app.main as main
        col = MagicMock()
        col.create_index = AsyncMock()
        monkeypatch.setattr("app.database.atividade_usuario", col, raising=False)
        monkeypatch.setattr(main, "ATIVIDADE_TTL_DIAS", 0, raising=False)
        await main.criar_indices_atividade()
        primeira = col.create_index.call_args_list[0]
        assert "expireAfterSeconds" not in primeira.kwargs


class TestChatRegistraAtividade:
    @pytest.mark.asyncio
    async def test_chat_sucesso_registra(self, client, mock_db, auth_headers, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-de-teste")
        body = {"choices": [{"message": {"content": "Resposta do tutor."}}]}
        with patch("app.routers.chat_tutor.httpx.AsyncClient", _mock_async_client(200, body)):
            resp = await client.post(
                "/tutor/chat",
                headers=auth_headers,
                json={"mensagens": [{"role": "user", "content": "oi"}]},
            )
        assert resp.status_code == 200
        assert mock_db["atividade"].insert_one.called
        doc = mock_db["atividade"].insert_one.call_args.args[0]
        assert doc["tipo"] == "chat"
        assert doc["status"] == "sucesso"
        # payload compacto: preview/tamanho, não o conteúdo completo
        assert doc["detalhes"]["resposta_preview"] == "Resposta do tutor."
        assert doc["detalhes"]["resposta_tamanho"] == len("Resposta do tutor.")
        assert "resposta" not in doc["detalhes"]

    @pytest.mark.asyncio
    async def test_chat_erro_registra_e_propaga(self, client, mock_db, auth_headers, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-de-teste")
        with patch("app.routers.chat_tutor.httpx.AsyncClient", _mock_async_client(500, {})):
            resp = await client.post(
                "/tutor/chat",
                headers=auth_headers,
                json={"mensagens": [{"role": "user", "content": "oi"}]},
            )
        assert resp.status_code == 502
        doc = mock_db["atividade"].insert_one.call_args.args[0]
        assert doc["status"] == "erro"

    @pytest.mark.asyncio
    async def test_falha_ao_registrar_nao_quebra_chat(self, client, mock_db, auth_headers, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-de-teste")
        mock_db["atividade"].insert_one = AsyncMock(side_effect=RuntimeError("db down"))
        body = {"choices": [{"message": {"content": "ok"}}]}
        with patch("app.routers.chat_tutor.httpx.AsyncClient", _mock_async_client(200, body)):
            resp = await client.post(
                "/tutor/chat",
                headers=auth_headers,
                json={"mensagens": [{"role": "user", "content": "oi"}]},
            )
        # registro é fire-and-forget: o chat continua respondendo 200
        assert resp.status_code == 200
