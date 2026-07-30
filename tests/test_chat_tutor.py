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

    @pytest.mark.asyncio
    async def test_put_modelo_nao_colide_com_catch_all(self, client, mock_db, auth_headers, mock_admin):
        """PUT /tutor/modelo (trocar o LLM) deve cair em definir_modelo, NÃO no
        catch-all PUT /tutor/{id} de tutor.py (que validaria AtualizarContextoRequest
        e devolveria 422). chat_tutor.router é registrado antes de tutor.router."""
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        response = await client.put(
            "/tutor/modelo",
            headers=auth_headers,
            json={"modelo": "meta/llama-3.3-70b-instruct"},
        )
        assert response.status_code == 200
        assert response.json()["modelo"] == "meta/llama-3.3-70b-instruct"


class _AsyncCursor:
    """Cursor mínimo: suporta .sort().limit() e iteração assíncrona."""
    def __init__(self, docs):
        self._docs = docs
    def sort(self, *a, **k):
        return self
    def limit(self, *a, **k):
        return self
    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()


class TestTetosDoChat:
    """Tetos de contexto e de resposta (`chat_tutor`).

    Existem porque o contexto vem no CORPO da requisição (o cliente decide o tamanho) e
    porque a resposta é paga por token. O que se cobra aqui é que o teto de saída siga o
    nível do aluno e que o corte do contexto não parta uma linha do JSON pela metade.
    """

    def test_teto_de_resposta_segue_o_nivel_do_aluno(self):
        from app.routers import chat_tutor as ct
        assert ct.max_tokens_resposta({"nivel": "avancado"}) == ct.MAX_TOKENS_RESPOSTA_AVANCADO
        assert ct.max_tokens_resposta({"nivel": "basico"}) == ct.MAX_TOKENS_RESPOSTA
        assert ct.max_tokens_resposta({}) == ct.MAX_TOKENS_RESPOSTA
        assert ct.max_tokens_resposta(None) == ct.MAX_TOKENS_RESPOSTA
        assert ct.MAX_TOKENS_RESPOSTA_AVANCADO > ct.MAX_TOKENS_RESPOSTA

    def test_avancado_pede_mais_tokens_na_chamada(self):
        """O nível tem de chegar ao payload, não só ao helper."""
        from app.routers import chat_tutor as ct
        assert ct.max_tokens_resposta({"nivel": "avancado", "modelo": "knn"}) > 1024

    def test_contexto_curto_passa_inteiro(self):
        from app.routers.chat_tutor import _montar_contexto
        texto = _montar_contexto({"modelo": "knn"})
        assert "knn" in texto and "truncado" not in texto

    def test_contexto_sem_pipeline(self):
        from app.routers.chat_tutor import _montar_contexto
        assert "Nenhum pipeline" in _montar_contexto(None)

    def test_corte_do_contexto_nao_parte_a_linha_e_diz_o_que_ficou_de_fora(self):
        """Regressão: `texto[:8000]` entregava campo partido (`"modelo": "random_fo`)."""
        from app.routers import chat_tutor as ct
        grande = {f"campo_{i}": "x" * 200 for i in range(200)}
        texto = ct._montar_contexto(grande)
        corpo, _, ultima = texto.rpartition("\n")
        assert ultima.startswith("... (contexto truncado:")
        assert "caracteres omitidos)" in ultima
        # nenhuma linha do corpo termina no meio de um valor entre aspas
        for linha in corpo.splitlines():
            assert linha.count('"') % 2 == 0, linha


class TestHistoricoChat:
    @pytest.mark.asyncio
    async def test_listar_historico_usa_id_do_usuario(self, client, mock_db, auth_headers):
        """Regressão: o endpoint usava usuario['id'] (inexistente) -> 500 KeyError."""
        hist = MagicMock()
        hist.find = MagicMock(return_value=_AsyncCursor([]))
        with patch("app.routers.chat_tutor.historico_chat", hist):
            resp = await client.get("/tutor/chat/historico", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []
        # confirma que filtrou pelo _id do usuário (não estourou KeyError)
        assert hist.find.called


class TestTruncamentoRegistrado:
    """`finish_reason: length` = o tutor terminou no meio da frase. Tem de ficar no registro:
    sem isso, só o aluno percebe (ficando sem o final) e ninguém mais."""

    @pytest.mark.asyncio
    async def test_resposta_cortada_no_teto_vai_para_a_telemetria(
            self, client, mock_db, auth_headers, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-de-teste")
        body = {"choices": [{"message": {"content": "A fórmula do gradiente é"},
                             "finish_reason": "length"}]}
        registrados = []

        async def _registrar(usuario, tipo, acao, **kw):
            registrados.append(kw.get("detalhes") or {})

        with patch("app.routers.chat_tutor.httpx.AsyncClient", _mock_async_client(200, body)), \
             patch("app.routers.chat_tutor.registrar_atividade", _registrar):
            r = await client.post("/tutor/chat", headers=auth_headers,
                                  json={"mensagens": [{"role": "user", "content": "explica"}]})
        assert r.status_code == 200
        assert registrados and registrados[0]["truncada_no_teto"] is True

    @pytest.mark.asyncio
    async def test_resposta_completa_nao_e_marcada(
            self, client, mock_db, auth_headers, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-de-teste")
        body = {"choices": [{"message": {"content": "Pronto."}, "finish_reason": "stop"}]}
        registrados = []

        async def _registrar(usuario, tipo, acao, **kw):
            registrados.append(kw.get("detalhes") or {})

        with patch("app.routers.chat_tutor.httpx.AsyncClient", _mock_async_client(200, body)), \
             patch("app.routers.chat_tutor.registrar_atividade", _registrar):
            r = await client.post("/tutor/chat", headers=auth_headers,
                                  json={"mensagens": [{"role": "user", "content": "oi"}]})
        assert r.status_code == 200
        assert registrados and registrados[0]["truncada_no_teto"] is False


_PROVEDOR = {"id": "nvidia", "nome": "NVIDIA NIM", "api_key": "chave",
             "base_url": "https://integrate.api.nvidia.com/v1", "modelo": "modelo-x",
             "todos_gratuitos": True, "exige_chave": True}


class TestGatesDosModelos:
    """As duas rotas de modelo são ferramentas de admin — e o teste de saúde faz chamada REAL de
    completion no provedor, com id de modelo arbitrário. Sem gate, um aluno autenticado escolheria
    o modelo mais caro e o servidor pagaria a conta."""

    @pytest.mark.asyncio
    async def test_aluno_nao_lista_modelos(self, client, mock_db, auth_headers, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "x")
        r = await client.get("/tutor/modelos", headers=auth_headers)
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_aluno_nao_dispara_teste_de_saude(self, client, mock_db, auth_headers, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "x")
        r = await client.get("/tutor/modelos/saude", headers=auth_headers)
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_aluno_nao_testa_um_modelo_escolhido_por_ele(self, client, mock_db, auth_headers,
                                                              monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "x")
        r = await client.get("/tutor/modelos/saude?modelo=openai/o3-pro", headers=auth_headers)
        assert r.status_code == 403


class TestSaudeModelos:
    @pytest.mark.asyncio
    async def test_modelo_que_responde(self):
        from app.routers.chat_tutor import _testar_modelo
        resp = MagicMock()
        resp.status_code = 200
        cliente = MagicMock()
        cliente.post = AsyncMock(return_value=resp)
        out = await _testar_modelo(cliente, _PROVEDOR, "meta/llama-3.3-70b-instruct")
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
        out = await _testar_modelo(cliente, _PROVEDOR, "minimaxai/minimax-m3")
        assert out["responde"] is False
        assert "DEGRADED" in out["erro"]
