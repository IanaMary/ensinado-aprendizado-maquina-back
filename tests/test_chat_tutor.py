import pytest
from bson import ObjectId
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
    """O chip verde da tela promete "responde". Ele precisa medir GERAÇÃO, não conexão."""

    @staticmethod
    def _cliente(status: int, corpo: dict):
        resp = MagicMock()
        resp.status_code = status
        resp.json = MagicMock(return_value=corpo)
        cliente = MagicMock()
        cliente.post = AsyncMock(return_value=resp)
        return cliente

    @pytest.mark.asyncio
    async def test_modelo_que_responde(self):
        from app.routers.chat_tutor import _testar_modelo
        # O corpo precisa ser REAL: com um MagicMock cru, qualquer acesso devolve um mock
        # verdadeiro e o teste passava sem exercitar a leitura da resposta.
        cliente = self._cliente(200, {"choices": [{"message": {"content": "ok"}}]})
        out = await _testar_modelo(cliente, _PROVEDOR, "meta/llama-3.3-70b-instruct")
        assert out["responde"] is True
        assert "latencia_ms" in out

    @pytest.mark.asyncio
    async def test_200_sem_texto_nao_conta_como_resposta(self):
        """Um modelo que não é de chat aceita a chamada e devolve nada. Antes virava chip verde,
        e daí para a lista de reserva do admin era um passo."""
        from app.routers.chat_tutor import _testar_modelo
        for corpo in ({"choices": [{"message": {"content": ""}}]},
                      {"choices": [{"message": {}}]},
                      {"choices": []}):
            out = await _testar_modelo(self._cliente(200, corpo), _PROVEDOR, "modelo-mudo")
            assert out["responde"] is False
            assert "sem texto" in out["erro"]

    @pytest.mark.asyncio
    async def test_pede_tokens_suficientes_para_provar_geracao(self):
        """`max_tokens=1` mentia: o `minimax-m3` respondia esse ping em 628 ms e estourava 120 s
        numa resposta de 90 tokens — e entrou na lista de reserva por causa disso."""
        from app.routers.chat_tutor import _testar_modelo
        cliente = self._cliente(200, {"choices": [{"message": {"content": "ok"}}]})
        await _testar_modelo(cliente, _PROVEDOR, "qualquer")
        enviado = cliente.post.await_args.kwargs["json"]
        assert enviado["max_tokens"] > 1

    @pytest.mark.asyncio
    async def test_modelo_degradado(self):
        from app.routers.chat_tutor import _testar_modelo
        resp = MagicMock()
        resp.status_code = 400
        resp.json = MagicMock(return_value={"detail": "DEGRADED function cannot be invoked"})
        cliente = MagicMock()
        cliente.post = AsyncMock(return_value=resp)
        out = await _testar_modelo(cliente, _PROVEDOR, "nvidia/llama-3.3-nemotron-super-49b-v1.5")
        assert out["responde"] is False
        assert "DEGRADED" in out["erro"]


def _fixar_modelo_nvidia(monkeypatch, modelo: str):
    """Fixa o modelo ATIVO da NVIDIA. Não dá para usar `setenv("NVIDIA_MODEL", ...)`: o catálogo
    resolve o `modelo_padrao` na importação do módulo."""
    from app import tutor_provedores as prov
    base = dict(prov.CATALOGO[prov.NVIDIA])
    base["modelo_padrao"] = modelo
    monkeypatch.setitem(prov.CATALOGO, prov.NVIDIA, base)


def _mock_client_por_modelo(respostas: dict, registro: list):
    """AsyncClient falso que responde conforme o modelo pedido.

    `respostas` mapeia model_id -> (status, corpo). Cada chamada anota o modelo em `registro`,
    para o teste afirmar a ORDEM em que a cadeia foi tentada.
    """
    async def _post(url, headers=None, json=None, **kw):
        modelo = (json or {}).get("model")
        registro.append(modelo)
        status, corpo = respostas.get(modelo, (404, {"detail": "Not found for account"}))
        resp = MagicMock()
        resp.status_code = status
        resp.json = MagicMock(return_value=corpo)
        return resp

    client = MagicMock()
    client.post = _post

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


class TestCadeiaDeFallback:
    """O modelo escolhido pode não estar liberado para a conta: a listagem `/models` passa, mas a
    inferência devolve 404. Foi o que derrubou o tutor em 01/08 (Imagem 13 da revisão)."""

    def setup_method(self):
        from app.routers import chat_tutor
        chat_tutor._modelos_ruins.clear()   # o cache de 10 min não pode vazar entre testes

    @pytest.mark.asyncio
    async def test_cai_para_o_proximo_quando_o_modelo_nao_esta_liberado(
            self, client, mock_db, auth_headers, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-de-teste")
        _fixar_modelo_nvidia(monkeypatch, "moonshotai/kimi-k2.6")
        tentados: list = []
        factory = _mock_client_por_modelo(
            {
                "moonshotai/kimi-k2.6": (404, {"detail": "Not found for account"}),
                "nvidia/llama-3.3-nemotron-super-49b-v1.5": (200, {"choices": [{"message": {"content": "olá"}}]}),
            },
            tentados,
        )

        with patch("app.routers.chat_tutor.httpx.AsyncClient", factory):
            r = await client.post("/tutor/chat", headers=auth_headers,
                                  json={"mensagens": [{"role": "user", "content": "oi"}]})

        assert r.status_code == 200
        assert r.json()["resposta"] == "olá"
        # respondeu, e diz QUEM respondeu — não é o configurado
        assert r.json()["modelo"] == "nvidia/llama-3.3-nemotron-super-49b-v1.5"
        assert tentados[0] == "moonshotai/kimi-k2.6"          # tenta o escolhido primeiro
        assert tentados[1] == "nvidia/llama-3.3-nemotron-super-49b-v1.5"

    @pytest.mark.asyncio
    async def test_chave_invalida_nao_percorre_a_cadeia(
            self, client, mock_db, auth_headers, monkeypatch):
        # 401 é da CHAVE, e a chave é a mesma para todos: tentar outro modelo só esconderia o
        # problema real e gastaria o tempo do aluno.
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-de-teste")
        _fixar_modelo_nvidia(monkeypatch, "moonshotai/kimi-k2.6")
        tentados: list = []
        factory = _mock_client_por_modelo(
            {"moonshotai/kimi-k2.6": (401, {"detail": "Unauthorized"})}, tentados
        )

        with patch("app.routers.chat_tutor.httpx.AsyncClient", factory):
            r = await client.post("/tutor/chat", headers=auth_headers,
                                  json={"mensagens": [{"role": "user", "content": "oi"}]})

        assert r.status_code == 502
        assert tentados == ["moonshotai/kimi-k2.6"]

    @pytest.mark.asyncio
    async def test_cadeia_esgotada_devolve_erro_claro(
            self, client, mock_db, auth_headers, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-de-teste")
        _fixar_modelo_nvidia(monkeypatch, "moonshotai/kimi-k2.6")
        tentados: list = []
        factory = _mock_client_por_modelo({}, tentados)   # tudo 404

        with patch("app.routers.chat_tutor.httpx.AsyncClient", factory):
            r = await client.post("/tutor/chat", headers=auth_headers,
                                  json={"mensagens": [{"role": "user", "content": "oi"}]})

        assert r.status_code == 502
        assert "Nenhum modelo" in r.json()["detail"]
        assert len(tentados) == 3   # o escolhido + os dois fallbacks da NVIDIA

    @pytest.mark.asyncio
    async def test_modelo_aposentado_410_nao_mata_a_cadeia(
            self, client, mock_db, auth_headers, monkeypatch):
        """410 Gone = o modelo saiu do ar de vez (fim de vida). Isso é do MODELO, não da conta
        nem da pergunta: tem de cair para o próximo, como o 404.

        Regressão de 18/08: o fallback `deepseek-v4-flash` atingiu fim de vida em 07/08 e passou
        a responder 410. Sem 410 em `_vale_tentar_outro`, a cadeia parava nele e o aluno via
        "O tutor retornou um erro" — com o fallback seguinte respondendo 200."""
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-de-teste")
        _fixar_modelo_nvidia(monkeypatch, "modelo-escolhido")
        tentados: list = []
        factory = _mock_client_por_modelo(
            {
                "modelo-escolhido": (410, {"detail": "end of life"}),
                "nvidia/llama-3.3-nemotron-super-49b-v1.5": (200, {"choices": [{"message": {"content": "olá"}}]}),
            },
            tentados,
        )

        with patch("app.routers.chat_tutor.httpx.AsyncClient", factory):
            r = await client.post("/tutor/chat", headers=auth_headers,
                                  json={"mensagens": [{"role": "user", "content": "oi"}]})

        assert r.status_code == 200
        assert r.json()["modelo"] == "nvidia/llama-3.3-nemotron-super-49b-v1.5"
        assert tentados == ["modelo-escolhido", "nvidia/llama-3.3-nemotron-super-49b-v1.5"]

    def test_status_que_valem_outra_tentativa(self):
        from app.routers.chat_tutor import _vale_tentar_outro
        # do MODELO: trocar de modelo pode resolver. 402 = sem crédito para ESTE modelo no
        # OpenRouter, e cair para um `:free` resolve.
        assert all(_vale_tentar_outro(s) for s in (402, 404, 410, 500, 503))
        # da CHAVE, da conta ou da pergunta: trocar de modelo só esconderia o problema.
        # 429 fica fora de propósito — ver a docstring da função.
        assert not any(_vale_tentar_outro(s) for s in (400, 401, 403, 429))

    @pytest.mark.asyncio
    async def test_402_cai_para_o_proximo(self, client, mock_db, auth_headers, monkeypatch):
        """Sem crédito para o modelo pago: o `:free` da reserva atende."""
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-de-teste")
        _fixar_modelo_nvidia(monkeypatch, "modelo-pago")
        tentados: list = []
        factory = _mock_client_por_modelo(
            {"modelo-pago": (402, {"detail": "insufficient credits"}),
             "nvidia/llama-3.3-nemotron-super-49b-v1.5": (200, {"choices": [{"message": {"content": "olá"}}]})},
            tentados,
        )

        with patch("app.routers.chat_tutor.httpx.AsyncClient", factory):
            r = await client.post("/tutor/chat", headers=auth_headers,
                                  json={"mensagens": [{"role": "user", "content": "oi"}]})

        assert r.status_code == 200
        assert tentados == ["modelo-pago", "nvidia/llama-3.3-nemotron-super-49b-v1.5"]

    def test_cadeia_poe_o_escolhido_primeiro_e_nao_repete(self):
        from app.routers.chat_tutor import cadeia_de_modelos
        prov = {"base_url": "http://x", "modelo": "a", "fallbacks": ["a", "b", "c"]}
        assert cadeia_de_modelos(prov) == ["a", "b", "c"]

    def test_modelo_que_acabou_de_falhar_vai_para_o_fim_mas_nao_some(self):
        from app.routers import chat_tutor
        prov = {"base_url": "http://x", "modelo": "a", "fallbacks": ["b"]}
        chat_tutor._marcar_ruim("http://x", "a")
        # 'a' continua na lista: se 'b' também estiver ruim, ainda vale tentar alguma coisa.
        assert chat_tutor.cadeia_de_modelos(prov) == ["b", "a"]


def _colecao_de_config(docs: dict):
    """Coleção `configuracoes_tutor` falsa, só com o que `provedor_vigente` usa: o `find` em lote.

    O conftest patcheia `app.database.configuracoes_tutor` com um mock que devolve lista vazia, o
    que faz todo teste cair no CATALOGO. Para provar que a lista do BANCO chega até a cadeia é
    preciso servir documentos de verdade.
    """
    class Cursor:
        def __init__(self, itens):
            self._itens = itens

        async def to_list(self, length=None):
            return self._itens

    def find(filtro, *a, **k):
        pedidas = ((filtro or {}).get("chave") or {}).get("$in") or list(docs)
        return Cursor([{"chave": c, "valor": v} for c, v in docs.items() if c in pedidas])

    return MagicMock(find=MagicMock(side_effect=find),
                     find_one=AsyncMock(return_value=None),
                     update_one=AsyncMock())


class TestListaDeReservaConfigurada:
    """A lista de reserva mora no banco e é editável pelo admin (19/08).

    Antes vivia só no `CATALOGO`: quando o `deepseek-v4-flash` morreu, só um deploy consertava.
    """

    def setup_method(self):
        from app.routers import chat_tutor
        chat_tutor._modelos_ruins.clear()

    @pytest.mark.asyncio
    async def test_a_cadeia_obedece_a_lista_do_banco_e_nao_a_do_catalogo(
            self, client, mock_db, auth_headers, monkeypatch):
        """O teste que prova o pedido inteiro: sem isto, não há caminho do banco até a rotação."""
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-de-teste")
        colecao = _colecao_de_config({
            "llm_provedor": "nvidia",
            "llm_provedores": {"nvidia": {"modelo": "escolhido",
                                          "fallbacks": ["reserva-do-admin"]}},
        })
        tentados: list = []
        factory = _mock_client_por_modelo(
            {"reserva-do-admin": (200, {"choices": [{"message": {"content": "olá"}}]})},
            tentados,
        )

        with patch("app.routers.chat_tutor.prov._colecao", lambda: colecao), \
             patch("app.routers.chat_tutor.httpx.AsyncClient", factory):
            r = await client.post("/tutor/chat", headers=auth_headers,
                                  json={"mensagens": [{"role": "user", "content": "oi"}]})

        assert r.status_code == 200
        assert r.json()["modelo"] == "reserva-do-admin"
        assert tentados == ["escolhido", "reserva-do-admin"]
        # e NENHUM dos fallbacks fixos do código foi tentado
        assert "meta/llama-3.1-8b-instruct" not in tentados

    @pytest.mark.asyncio
    async def test_lista_vazia_do_admin_significa_sem_reserva(
            self, client, mock_db, auth_headers, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-de-teste")
        colecao = _colecao_de_config({
            "llm_provedor": "nvidia",
            "llm_provedores": {"nvidia": {"modelo": "escolhido", "fallbacks": []}},
        })
        tentados: list = []
        factory = _mock_client_por_modelo({}, tentados)   # tudo 404

        with patch("app.routers.chat_tutor.prov._colecao", lambda: colecao), \
             patch("app.routers.chat_tutor.httpx.AsyncClient", factory):
            r = await client.post("/tutor/chat", headers=auth_headers,
                                  json={"mensagens": [{"role": "user", "content": "oi"}]})

        assert r.status_code == 502
        assert tentados == ["escolhido"]   # o padrão do código NÃO volta pela porta dos fundos

    @pytest.mark.asyncio
    async def test_aluno_e_professor_nao_mexem_na_lista(self, client, mock_db, auth_headers,
                                                        mock_user):
        for papel in ("aluno", "professor"):
            mock_db["usuarios"].find_one = AsyncMock(return_value={**mock_user, "role": papel})
            r = await client.put("/tutor/provedores/nvidia/fallbacks", headers=auth_headers,
                                 json={"modelos": ["x"]})
            assert r.status_code == 403
            r = await client.delete("/tutor/provedores/nvidia/fallbacks", headers=auth_headers)
            assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_grava_e_a_auditoria_registra(self, client, mock_db, auth_headers,
                                                      mock_admin):
        from app.routers import chat_tutor
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        with patch.object(chat_tutor.prov, "definir_fallbacks",
                          AsyncMock(return_value=["a", "b"])) as definir, \
             patch.object(chat_tutor.prov, "listar_para_tela", AsyncMock(return_value={})), \
             patch.object(chat_tutor, "_auditar_llm", AsyncMock()) as auditar:
            r = await client.put("/tutor/provedores/nvidia/fallbacks", headers=auth_headers,
                                 json={"modelos": ["a", "b"]})

        assert r.status_code == 200
        assert definir.await_args[0][:2] == ("nvidia", ["a", "b"])
        assert auditar.await_args[0][1] == "definiu_fallbacks"

    @pytest.mark.asyncio
    async def test_delete_volta_ao_padrao_do_sistema(self, client, mock_db, auth_headers,
                                                     mock_admin):
        from app.routers import chat_tutor
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        with patch.object(chat_tutor.prov, "limpar_fallbacks",
                          AsyncMock(return_value=["padrao"])) as limpar, \
             patch.object(chat_tutor.prov, "listar_para_tela", AsyncMock(return_value={})), \
             patch.object(chat_tutor, "_auditar_llm", AsyncMock()) as auditar:
            r = await client.delete("/tutor/provedores/nvidia/fallbacks", headers=auth_headers)

        assert r.status_code == 200
        assert limpar.await_args[0][0] == "nvidia"
        assert auditar.await_args[0][1] == "restaurou_fallbacks"

    @pytest.mark.asyncio
    async def test_corpo_fora_do_formato_e_recusado(self, client, mock_db, auth_headers,
                                                    mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        r = await client.put("/tutor/provedores/nvidia/fallbacks", headers=auth_headers,
                             json={"modelos": "não é lista"})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_provedor_desconhecido_devolve_400(self, client, mock_db, auth_headers,
                                                     mock_admin):
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        r = await client.put("/tutor/provedores/inexistente/fallbacks", headers=auth_headers,
                             json={"modelos": ["x"]})
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_a_rota_nao_e_roubada_pelo_catch_all(self, client, mock_db, auth_headers,
                                                       mock_admin):
        """Terceira vez que essa armadilha aparece: `PUT /tutor/{id}` de `tutor.py` é catch-all e
        já roubou `/tutor/modelo` uma vez. Se roubasse esta, viria 422 do outro schema."""
        from app.routers import chat_tutor
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        with patch.object(chat_tutor.prov, "definir_fallbacks", AsyncMock(return_value=[])), \
             patch.object(chat_tutor.prov, "listar_para_tela", AsyncMock(return_value={})), \
             patch.object(chat_tutor, "_auditar_llm", AsyncMock()):
            r = await client.put("/tutor/provedores/nvidia/fallbacks", headers=auth_headers,
                                 json={"modelos": []})
        assert r.status_code == 200


class TestProvedoresDeLLM:
    """`GET /tutor/provedores` e `PUT /tutor/provedores/{pid}` não tinham teste, e são os dois
    endpoints que lidam com **chave de API do LLM**.

    Dois riscos: a chave sair para a tela (vazamento de credencial) e o admin **perder** a chave ao
    corrigir só a URL — é para isso que existe a regra "`api_key` vazio mantém a atual", e ela só se
    sustenta com teste.
    """

    @pytest.mark.asyncio
    async def test_listar_exige_papel_e_nao_devolve_chave_em_claro(
        self, client, mock_db, auth_headers, mock_admin,
    ):
        from app.routers import chat_tutor
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        with patch.object(chat_tutor.prov, "listar_para_tela", AsyncMock(return_value={
            "ativo": "openrouter",
            "provedores": {"openrouter": {"nome": "OpenRouter", "chave_final": "cd12",
                                          "origem_chave": "banco", "modelo": "x/y"}},
        })):
            resp = await client.get("/tutor/provedores", headers=auth_headers)

        assert resp.status_code == 200
        corpo = resp.text
        # o contrato é devolver só os últimos 4 caracteres
        assert "chave_final" in corpo
        assert "api_key" not in corpo and "sk-" not in corpo

    @pytest.mark.asyncio
    async def test_aluno_nao_lista_provedores(self, client, mock_db, auth_headers):
        resp = await client.get("/tutor/provedores", headers=auth_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_aluno_e_professor_nao_gravam_provedor(self, client, mock_db, auth_headers):
        """Gravar é só admin (gate no corpo, não dependency): professor também recebe 403."""
        for papel in ("aluno", "professor"):
            mock_db["usuarios"].find_one = AsyncMock(return_value={
                "_id": ObjectId(), "email": "x@test.com", "role": papel, "nome": papel})
            resp = await client.put("/tutor/provedores/openrouter", headers=auth_headers,
                                    json={"api_key": "nova-chave"})
            assert resp.status_code == 403, f"{papel} conseguiu gravar provedor"

    @pytest.mark.asyncio
    async def test_api_key_vazio_nao_chega_como_chave_nova(
        self, client, mock_db, auth_headers, mock_admin,
    ):
        """O admin corrige a URL sem redigitar o segredo. Se um `api_key: ""` fosse tratado como
        chave nova, o chat cairia para todos os alunos no próximo pedido."""
        from app.routers import chat_tutor
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        salvar = AsyncMock()
        with patch.object(chat_tutor.prov, "salvar_provedor", salvar), \
             patch.object(chat_tutor.prov, "listar_para_tela", AsyncMock(return_value={})), \
             patch.object(chat_tutor, "_auditar_llm", AsyncMock()):
            resp = await client.put("/tutor/provedores/openrouter", headers=auth_headers,
                                    json={"base_url": "https://novo.exemplo/v1", "api_key": ""})

        assert resp.status_code == 200
        enviado = salvar.await_args[0][1]
        assert enviado["base_url"] == "https://novo.exemplo/v1"
        # `salvar_provedor` só sobrescreve quando a chave vem preenchida — string vazia é "manter"
        assert enviado.get("api_key", "") == ""

    @pytest.mark.asyncio
    async def test_a_chave_nunca_entra_na_auditoria(
        self, client, mock_db, auth_headers, mock_admin,
    ):
        """A auditoria (`pipe: 'llm'`) registra QUE mudou, não o segredo."""
        from app.routers import chat_tutor
        mock_db["usuarios"].find_one = AsyncMock(return_value=mock_admin)
        auditar = AsyncMock()
        with patch.object(chat_tutor.prov, "salvar_provedor", AsyncMock()), \
             patch.object(chat_tutor.prov, "listar_para_tela", AsyncMock(return_value={})), \
             patch.object(chat_tutor, "_auditar_llm", auditar):
            await client.put("/tutor/provedores/openrouter", headers=auth_headers,
                             json={"api_key": "sk-segredo-que-nao-pode-aparecer"})

        assert auditar.await_count == 1
        assert "sk-segredo-que-nao-pode-aparecer" not in str(auditar.await_args)


# ============================================================
# CAMINHO SSE (`_stream_llm`) — é o que o aluno usa de verdade
# ============================================================
# Até 19/08 a cadeia de modelos só tinha teste pelo handler NÃO-stream. O incidente do
# `410 Gone` aconteceu no stream, e nenhum teste o teria pego. Estes casos exercitam o
# gerador direto: ele é um async generator, então não precisa de HTTP para ser acionado.

def _mock_stream_client(respostas: dict, registro: list):
    """AsyncClient falso cujo `.stream()` segue o roteiro de cada modelo.

    `respostas` mapeia `model_id -> (status, [linhas])`; quem não está no dict responde 404
    (o mesmo default do `_mock_client_por_modelo`, que é o caso "não liberado para a conta").
    Uma exceção no lugar de uma linha é LEVANTADA naquele ponto da iteração — é assim que se
    simula a falha que chega **depois** do primeiro byte.
    """
    def _stream(metodo, url, headers=None, json=None, **kw):
        modelo = (json or {}).get("model")
        registro.append(modelo)
        status, linhas = respostas.get(modelo, (404, []))

        resp = MagicMock()
        resp.status_code = status

        async def _aiter_lines():
            for linha in linhas:
                if isinstance(linha, Exception):
                    raise linha
                yield linha

        resp.aiter_lines = _aiter_lines

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    client = MagicMock()
    client.stream = _stream

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


def _linha_token(texto: str) -> str:
    return 'data: {"choices": [{"delta": {"content": "%s"}}]}' % texto


_PROVEDOR_STREAM = {"id": "nvidia", "nome": "NVIDIA NIM", "base_url": "http://provedor",
                    "api_key": "chave-de-teste", "modelo": "escolhido"}


async def _coletar(gerador) -> list:
    return [pedaco async for pedaco in gerador]


class TestStreamLlm:
    """Caracterização do gerador SSE, escrita contra o comportamento de hoje."""

    def setup_method(self):
        from app.routers import chat_tutor
        chat_tutor._modelos_ruins.clear()

    @pytest.mark.asyncio
    async def test_404_no_escolhido_deixa_o_proximo_responder(self):
        from app.routers import chat_tutor
        tentados: list = []
        factory = _mock_stream_client(
            {"reserva": (200, [_linha_token("olá"), "data: [DONE]"])}, tentados)

        with patch("app.routers.chat_tutor.httpx.AsyncClient", factory):
            saida = await _coletar(chat_tutor._stream_llm(
                _PROVEDOR_STREAM, {"stream": True}, cadeia=["escolhido", "reserva"],
                modelo="escolhido"))

        assert tentados == ["escolhido", "reserva"]
        assert '{"token": "ol\\u00e1"}' in "".join(saida)
        assert "data: [DONE]\n\n" in saida
        assert not any("error" in p for p in saida)

    @pytest.mark.asyncio
    async def test_410_no_escolhido_deixa_o_proximo_responder(self):
        """A regressão do `deepseek-v4-flash`, agora no caminho que o aluno usa."""
        from app.routers import chat_tutor
        tentados: list = []
        factory = _mock_stream_client(
            {"escolhido": (410, []), "reserva": (200, [_linha_token("ok"), "data: [DONE]"])},
            tentados)

        with patch("app.routers.chat_tutor.httpx.AsyncClient", factory):
            saida = await _coletar(chat_tutor._stream_llm(
                _PROVEDOR_STREAM, {"stream": True}, cadeia=["escolhido", "reserva"],
                modelo="escolhido"))

        assert tentados == ["escolhido", "reserva"]
        assert '{"token": "ok"}' in "".join(saida)
        assert not any("error" in p for p in saida)

    @pytest.mark.asyncio
    async def test_401_nao_percorre_a_cadeia(self):
        # A chave é a mesma para todos os modelos: tentar outro só gastaria o tempo do aluno.
        from app.routers import chat_tutor
        tentados: list = []
        factory = _mock_stream_client({"escolhido": (401, [])}, tentados)

        with patch("app.routers.chat_tutor.httpx.AsyncClient", factory):
            saida = await _coletar(chat_tutor._stream_llm(
                _PROVEDOR_STREAM, {"stream": True}, cadeia=["escolhido", "reserva"],
                modelo="escolhido"))

        assert tentados == ["escolhido"]
        assert len([p for p in saida if "error" in p]) == 1

    @pytest.mark.asyncio
    async def test_cadeia_esgotada_emite_um_erro_e_nenhum_done(self):
        from app.routers import chat_tutor
        tentados: list = []
        factory = _mock_stream_client({}, tentados)   # tudo 404

        with patch("app.routers.chat_tutor.httpx.AsyncClient", factory):
            saida = await _coletar(chat_tutor._stream_llm(
                _PROVEDOR_STREAM, {"stream": True}, cadeia=["a", "b", "c"], modelo="a"))

        assert tentados == ["a", "b", "c"]
        assert len([p for p in saida if "error" in p]) == 1
        # Sem [DONE]: o cliente não pode concluir que a resposta terminou bem.
        assert not any("[DONE]" in p for p in saida)

    @pytest.mark.asyncio
    async def test_falha_depois_do_primeiro_byte_nao_troca_de_modelo(self):
        """Invariante: começou a emitir, não recomeça com outro modelo — a resposta sairia
        remendada, metade de cada um."""
        import httpx
        from app.routers import chat_tutor
        tentados: list = []
        factory = _mock_stream_client(
            {"escolhido": (200, [_linha_token("come"), httpx.TimeoutException("lento")]),
             "reserva": (200, [_linha_token("inteiro"), "data: [DONE]"])},
            tentados)

        with patch("app.routers.chat_tutor.httpx.AsyncClient", factory):
            saida = await _coletar(chat_tutor._stream_llm(
                _PROVEDOR_STREAM, {"stream": True}, cadeia=["escolhido", "reserva"],
                modelo="escolhido"))

        assert tentados == ["escolhido"]          # o reserva NÃO é acionado
        texto = "".join(saida)
        assert '{"token": "come"}' in texto        # o que já saiu, saiu
        assert "demorou demais" in texto

    @pytest.mark.asyncio
    async def test_telemetria_do_sucesso_e_da_desconexao(self):
        from app.routers import chat_tutor
        usuario = {"_id": ObjectId(), "email": "a@b.c", "role": "aluno"}
        registrado: list = []

        async def _fake_registrar(u, tipo, acao, **kw):
            registrado.append({"acao": acao, **kw})

        # Sucesso: o stream vai até o fim.
        factory = _mock_stream_client(
            {"escolhido": (200, [_linha_token("oi"), "data: [DONE]"])}, [])
        with patch("app.routers.chat_tutor.httpx.AsyncClient", factory), \
             patch("app.routers.chat_tutor.registrar_atividade", _fake_registrar):
            await _coletar(chat_tutor._stream_llm(
                _PROVEDOR_STREAM, {"stream": True}, cadeia=["escolhido"],
                usuario=usuario, modelo="escolhido"))
        assert registrado[-1]["status"] == "sucesso"

        # Desconexão: o consumidor desiste no meio do stream.
        registrado.clear()
        factory = _mock_stream_client(
            {"escolhido": (200, [_linha_token("oi"), _linha_token("mais"), "data: [DONE]"])}, [])
        with patch("app.routers.chat_tutor.httpx.AsyncClient", factory), \
             patch("app.routers.chat_tutor.registrar_atividade", _fake_registrar):
            gerador = chat_tutor._stream_llm(
                _PROVEDOR_STREAM, {"stream": True}, cadeia=["escolhido"],
                usuario=usuario, modelo="escolhido")
            await gerador.__anext__()      # consome só o primeiro token
            await gerador.aclose()
        assert registrado[-1]["status"] == "interrompido"
