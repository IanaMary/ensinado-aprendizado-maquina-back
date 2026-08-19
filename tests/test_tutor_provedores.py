"""Provedores de LLM: resolução do provedor ativo, gratuidade e as garantias sobre a chave.

Duas garantias negativas guiam o arquivo:

1. **a chave de API nunca sai em claro** por nenhuma leitura;
2. **trocar de provedor não herda o modelo do outro** — um id do OpenRouter não existe na NVIDIA, e
   um "modelo global" apontaria para o nada.
"""
import copy

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app import tutor_provedores as prov


def _colecao(docs: dict):
    """Coleção fake indexada por `chave`, com upsert que grava no próprio dicionário.

    Suporta `find({"chave": {"$in": [...]}})` porque `provedor_vigente` resolve tudo numa consulta
    só — uma fixture que só soubesse `find_one` mascararia a leitura em lote com o fallback.
    """
    async def find_one(filtro, *a, **k):
        return docs.get(filtro.get("chave"))

    class Cursor:
        def __init__(self, itens):
            self._itens = itens

        async def to_list(self, length=None):
            return self._itens

    def find(filtro, *a, **k):
        pedidas = ((filtro or {}).get("chave") or {}).get("$in") or list(docs)
        return Cursor([d for c, d in docs.items() if c in pedidas])

    def _gravar(doc, caminho, valor):
        """`$set` com caminho pontilhado, como o Mongo faz — `valor.nvidia.fallbacks` escreve só
        aquele campo em vez de trocar o documento inteiro."""
        partes = caminho.split(".")
        for parte in partes[:-1]:
            proximo = doc.get(parte)
            if not isinstance(proximo, dict):
                proximo = {}
                doc[parte] = proximo
            doc = proximo
        doc[partes[-1]] = valor

    def _remover(doc, caminho):
        partes = caminho.split(".")
        for parte in partes[:-1]:
            doc = doc.get(parte)
            if not isinstance(doc, dict):
                return
        doc.pop(partes[-1], None)

    async def update_one(filtro, update, **k):
        chave = filtro.get("chave")
        doc = copy.deepcopy(docs.get(chave) or {})   # fundo, senão a escrita aninhada vaza
        for caminho, valor in (update.get("$set") or {}).items():
            _gravar(doc, caminho, valor)
        for caminho in (update.get("$unset") or {}):
            _remover(doc, caminho)
        docs[chave] = doc
        return MagicMock(upserted_id=None, modified_count=1)

    return MagicMock(find_one=AsyncMock(side_effect=find_one),
                     find=MagicMock(side_effect=find),
                     update_one=AsyncMock(side_effect=update_one))


@pytest.fixture
def banco(monkeypatch):
    docs: dict = {}
    monkeypatch.setattr(prov, "_colecao", lambda: _colecao(docs))
    return docs


class TestNormalizarBaseUrl:
    def test_junta_a_porta_quando_vem_separada(self):
        assert prov.normalizar_base_url("http://127.0.0.1/v1", 11434) == "http://127.0.0.1:11434/v1"

    def test_porta_na_url_vence_o_campo(self):
        assert prov.normalizar_base_url("http://host:8000/v1", 11434) == "http://host:8000/v1"

    def test_sem_esquema_assume_http(self):
        assert prov.normalizar_base_url("localhost:11434/v1").startswith("http://localhost:11434")

    def test_endereco_privado_e_permitido(self):
        """É o caso de uso de \"endereço base e porta\": LLM self-hosted. O anti-SSRF da ingestão
        por URL não se aplica aqui — lá o dado vem do aluno, aqui a config vem do admin."""
        for url in ("http://127.0.0.1:11434/v1", "http://192.168.0.10:8000/v1",
                    "http://localhost:1234/v1"):
            assert prov.normalizar_base_url(url) == url.rstrip("/")

    @pytest.mark.parametrize("ruim", ["", "   ", "ftp://host/v1", "http:///v1"])
    def test_recusa_o_que_nao_daria_requisicao(self, ruim):
        with pytest.raises(prov.ProvedorInvalido):
            prov.normalizar_base_url(ruim)

    def test_recusa_porta_fora_da_faixa(self):
        with pytest.raises(prov.ProvedorInvalido):
            prov.normalizar_base_url("http://host/v1", 99999)


class TestMascarar:
    def test_mostra_so_os_ultimos_quatro(self):
        assert prov.mascarar("sk-or-v1-abcdefgh1234") == "••••1234"

    def test_chave_curta_nao_vaza_nada(self):
        assert prov.mascarar("abc") == "••••"

    def test_vazio_continua_vazio(self):
        assert prov.mascarar("") == "" and prov.mascarar(None) == ""


class TestLeituraDoBanco:
    @pytest.mark.asyncio
    async def test_resolve_o_provedor_em_UMA_consulta(self, monkeypatch):
        """`provedor_vigente` roda em toda pergunta do chat: três `find_one` por mensagem eram três
        idas ao banco para montar um dicionário."""
        chamadas = {"find": 0, "find_one": 0}
        docs = {"llm_model": {"chave": "llm_model", "valor": "meta/llama-3.3-70b-instruct"}}

        class Cursor:
            async def to_list(self, length=None):
                return list(docs.values())

        def find(filtro, *a, **k):
            chamadas["find"] += 1
            return Cursor()

        async def find_one(filtro, *a, **k):
            chamadas["find_one"] += 1
            return docs.get(filtro.get("chave"))

        monkeypatch.setattr(prov, "_colecao", lambda: MagicMock(
            find=MagicMock(side_effect=find), find_one=AsyncMock(side_effect=find_one)))
        monkeypatch.setenv("NVIDIA_API_KEY", "x")
        p = await prov.provedor_vigente()
        assert p["modelo"] == "meta/llama-3.3-70b-instruct"
        assert (chamadas["find"], chamadas["find_one"]) == (1, 0)


class TestProvedorVigente:
    @pytest.mark.asyncio
    async def test_sem_configuracao_cai_na_nvidia_com_o_env(self, banco, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-do-env")
        p = await prov.provedor_vigente()
        assert p["id"] == "nvidia" and p["api_key"] == "chave-do-env"
        assert p["todos_gratuitos"] is True

    @pytest.mark.asyncio
    async def test_modelo_legado_continua_valendo_para_a_nvidia(self, banco, monkeypatch):
        """Migração: antes de existirem provedores, o modelo ativo vivia em `llm_model`."""
        monkeypatch.setenv("NVIDIA_API_KEY", "x")
        banco["llm_model"] = {"chave": "llm_model", "valor": "deepseek-ai/deepseek-v4-flash"}
        p = await prov.provedor_vigente()
        assert p["modelo"] == "deepseek-ai/deepseek-v4-flash"

    @pytest.mark.asyncio
    async def test_cada_provedor_guarda_o_seu_modelo(self, banco, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "x")
        banco["llm_model"] = {"chave": "llm_model", "valor": "meta/llama-3.3-70b-instruct"}
        await prov.salvar_provedor("openrouter", {"api_key": "sk-or-1234"})
        await prov.definir_modelo("openrouter", "z-ai/glm-4.5-air:free")
        await prov.definir_ativo("openrouter")

        p = await prov.provedor_vigente()
        assert p["id"] == "openrouter" and p["modelo"] == "z-ai/glm-4.5-air:free"
        assert p["base_url"] == "https://openrouter.ai/api/v1"

        await prov.definir_ativo("nvidia")
        p = await prov.provedor_vigente()
        # Voltar para a NVIDIA traz o modelo DELA, não o do OpenRouter.
        assert p["modelo"] == "meta/llama-3.3-70b-instruct"


class TestSalvarProvedor:
    @pytest.mark.asyncio
    async def test_chave_vazia_mantem_a_atual(self, banco):
        """Deixa o admin corrigir a URL sem redigitar o segredo — a tela nem o conhece."""
        await prov.salvar_provedor("openrouter", {"api_key": "sk-or-abcd"})
        await prov.salvar_provedor("openrouter", {"base_url": "https://openrouter.ai/api/v1",
                                                 "api_key": ""})
        vista = await prov.listar_para_tela()
        openrouter = next(p for p in vista["provedores"] if p["id"] == "openrouter")
        assert openrouter["chave_fonte"] == "banco"
        assert openrouter["chave_mascarada"] == "••••abcd"

    @pytest.mark.asyncio
    async def test_nvidia_nao_e_editavel_pela_tela(self, banco):
        with pytest.raises(prov.ProvedorInvalido) as e:
            await prov.salvar_provedor("nvidia", {"api_key": "outra"})
        assert "NVIDIA_API_KEY" in str(e.value)

    @pytest.mark.asyncio
    async def test_custom_exige_url_base(self, banco):
        with pytest.raises(prov.ProvedorInvalido):
            await prov.salvar_provedor("custom", {"api_key": "k"})

    @pytest.mark.asyncio
    async def test_provedor_desconhecido_e_recusado(self, banco):
        with pytest.raises(prov.ProvedorInvalido):
            await prov.salvar_provedor("hackerman", {"base_url": "http://x/v1"})


class TestListarParaTela:
    @pytest.mark.asyncio
    async def test_nunca_devolve_a_chave_em_claro(self, banco, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "chave-secreta-do-env")
        await prov.salvar_provedor("openrouter", {"api_key": "sk-or-v1-supersecreta"})
        await prov.salvar_provedor("custom", {"base_url": "http://127.0.0.1:11434/v1",
                                             "api_key": "ollama-secreta"})
        vista = await prov.listar_para_tela()
        bruto = repr(vista)
        for segredo in ("chave-secreta-do-env", "sk-or-v1-supersecreta", "ollama-secreta"):
            assert segredo not in bruto
        assert all("api_key" not in p for p in vista["provedores"])

    @pytest.mark.asyncio
    async def test_diz_de_onde_a_chave_vem(self, banco, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "do-env")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        vista = await prov.listar_para_tela()
        por_id = {p["id"]: p for p in vista["provedores"]}
        assert por_id["nvidia"]["chave_fonte"] == "env"
        assert por_id["openrouter"]["chave_fonte"] == "ausente"
        assert por_id["custom"]["chave_fonte"] == "ausente"

    @pytest.mark.asyncio
    async def test_ordem_estavel_e_ativo_declarado(self, banco, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "x")
        vista = await prov.listar_para_tela()
        # A ordem é a do `ORDEM`, e o `custom` fica por último de propósito: é o único que exige
        # o admin digitar uma URL, então não deve abrir a lista.
        assert [p["id"] for p in vista["provedores"]] == list(prov.ORDEM)
        assert vista["provedores"][-1]["id"] == prov.CUSTOM
        assert vista["ativo"] == "nvidia"


class TestDefinirAtivo:
    @pytest.mark.asyncio
    async def test_recusa_provedor_que_exige_chave_e_nao_tem(self, banco, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises(prov.ProvedorInvalido) as e:
            await prov.definir_ativo("openrouter")
        assert "chave" in str(e.value).lower()

    @pytest.mark.asyncio
    async def test_recusa_custom_sem_url(self, banco):
        with pytest.raises(prov.ProvedorInvalido):
            await prov.definir_ativo("custom")

    @pytest.mark.asyncio
    async def test_custom_ativa_SEM_chave(self, banco):
        """Era o caso de uso declarado dos campos de URL base e porta: um LLM self-hosted (Ollama,
        vLLM, LM Studio) não tem chave de API. Exigir chave inviabilizava exatamente isso."""
        await prov.salvar_provedor("custom", {"base_url": "http://127.0.0.1:11434/v1",
                                             "nome": "Ollama local"})
        await prov.definir_ativo("custom")
        p = await prov.provedor_vigente()
        assert p["id"] == "custom" and p["api_key"] == ""
        assert p["exige_chave"] is False

    @pytest.mark.asyncio
    async def test_custom_sem_chave_aparece_configurado(self, banco):
        await prov.salvar_provedor("custom", {"base_url": "http://localhost:1234/v1"})
        vista = await prov.listar_para_tela()
        custom = next(p for p in vista["provedores"] if p["id"] == "custom")
        assert custom["configurado"] is True and custom["exige_chave"] is False


class TestGratuidade:
    def test_nvidia_marca_tudo_como_gratuito(self):
        """Por convenção do catálogo (a plataforma de build é de uso livre com limite de taxa) e
        por consistência com o OpenRouter, onde o preço vem na resposta."""
        p = {"id": "nvidia", "todos_gratuitos": True}
        assert prov.eh_gratuito({"id": "meta/llama-3.3-70b-instruct"}, p) is True

    def test_openrouter_decide_pelo_preco(self):
        p = {"id": "openrouter", "todos_gratuitos": False}
        assert prov.eh_gratuito({"pricing": {"prompt": "0", "completion": "0"}}, p) is True
        assert prov.eh_gratuito({"pricing": {"prompt": "0.0000001", "completion": "0"}}, p) is False

    def test_preco_ausente_ou_ilegivel_nao_afirma_nada(self):
        """`None` ≠ `False`: a tela mostra o modelo sem selo em vez de mentir que é pago."""
        p = {"id": "custom", "todos_gratuitos": None}
        assert prov.eh_gratuito({"id": "x"}, p) is None
        assert prov.eh_gratuito({"pricing": {"prompt": "grátis"}}, p) is None

    def test_gratuito_sem_sufixo_free_tambem_e_pego(self):
        """3 dos 17 gratuitos do OpenRouter não terminam em `:free` — por isso a regra é o preço,
        não o nome."""
        p = {"id": "openrouter", "todos_gratuitos": False}
        assert prov.eh_gratuito({"id": "algum/modelo", "pricing": {"prompt": "0",
                                                                   "completion": "0"}}, p) is True


class TestCabecalhos:
    def test_openrouter_recebe_atribuicao(self):
        h = prov.cabecalhos({"id": "openrouter", "api_key": "k"})
        assert h["Authorization"] == "Bearer k"
        assert h["X-Title"] == "H2IA Tutor"

    def test_nvidia_nao_leva_cabecalho_extra(self):
        h = prov.cabecalhos({"id": "nvidia", "api_key": "k"})
        assert "X-Title" not in h

    def test_sem_chave_nao_manda_authorization_vazio(self):
        """`Authorization: Bearer ` é cabeçalho malformado; alguns servidores locais recusam em
        vez de ignorar."""
        h = prov.cabecalhos({"id": "custom", "api_key": ""})
        assert "Authorization" not in h

    def test_referer_do_openrouter_vem_do_ambiente(self, monkeypatch):
        monkeypatch.setenv("FRONTEND_URL", "https://exemplo.test/app")
        assert prov.cabecalhos({"id": "openrouter", "api_key": "k"})["HTTP-Referer"] \
            == "https://exemplo.test/app"


class TestFallbacks:
    """A lista de reserva deixou de ser fixa no código (19/08).

    O que motivou: o fallback `deepseek-v4-flash` atingiu fim de vida em 07/08 e a lista, presa no
    `CATALOGO`, só podia ser corrigida por deploy. Modelo de LLM tem validade.
    """

    @pytest.mark.asyncio
    async def test_sem_nada_gravado_vale_o_padrao_do_catalogo(self, banco, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "chave")
        p = await prov.provedor_vigente()
        assert p["fallbacks"] == prov.CATALOGO[prov.NVIDIA]["fallbacks"]

        tela = await prov.listar_para_tela()
        nvidia = next(x for x in tela["provedores"] if x["id"] == prov.NVIDIA)
        assert nvidia["fallbacks_origem"] == "catalogo"

    @pytest.mark.asyncio
    async def test_a_lista_do_admin_vence_o_catalogo_na_ordem_gravada(self, banco, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "chave")
        await prov.definir_fallbacks(prov.NVIDIA, ["reserva-b", "reserva-a"])

        p = await prov.provedor_vigente()
        assert p["fallbacks"] == ["reserva-b", "reserva-a"]   # ordem É a configuração

        tela = await prov.listar_para_tela()
        nvidia = next(x for x in tela["provedores"] if x["id"] == prov.NVIDIA)
        assert nvidia["fallbacks"] == ["reserva-b", "reserva-a"]
        assert nvidia["fallbacks_origem"] == "admin"

    @pytest.mark.asyncio
    async def test_lista_vazia_gravada_significa_SEM_reserva(self, banco, monkeypatch):
        """A armadilha do falsy: com `(salvo.get(x) or padrão)`, `[]` viraria "não configurado" e
        o admin que pediu para não ter reserva receberia a lista do código de volta."""
        monkeypatch.setenv("NVIDIA_API_KEY", "chave")
        await prov.definir_fallbacks(prov.NVIDIA, [])

        p = await prov.provedor_vigente()
        assert p["fallbacks"] == []
        assert p["fallbacks"] != prov.CATALOGO[prov.NVIDIA]["fallbacks"]

    @pytest.mark.asyncio
    async def test_limpar_volta_ao_padrao_do_sistema(self, banco, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "chave")
        await prov.definir_fallbacks(prov.NVIDIA, [])
        assert (await prov.provedor_vigente())["fallbacks"] == []

        await prov.limpar_fallbacks(prov.NVIDIA)
        p = await prov.provedor_vigente()
        assert p["fallbacks"] == prov.CATALOGO[prov.NVIDIA]["fallbacks"]
        tela = await prov.listar_para_tela()
        assert next(x for x in tela["provedores"]
                    if x["id"] == prov.NVIDIA)["fallbacks_origem"] == "catalogo"

    def test_normalizacao(self):
        assert prov.normalizar_fallbacks([" a ", "a", "", "  ", None, 7, "b"]) == ["a", "b"]
        assert prov.normalizar_fallbacks(["a", "b", "c", "d", "e", "f"]) == list("abcde")
        assert len(prov.normalizar_fallbacks(["x" * 500])[0]) == 200
        assert prov.normalizar_fallbacks("nem é lista") == []

    @pytest.mark.asyncio
    async def test_nvidia_aceita_reserva_mas_segue_nao_editavel(self, banco):
        """`editavel: False` diz que URL e chave vêm do `.env`, não que a escolha de modelos seja
        imutável. A guarda de `salvar_provedor` NÃO pode ter sido relaxada de lado nenhum."""
        await prov.definir_fallbacks(prov.NVIDIA, ["reserva"])
        assert (await prov._configs())[prov.NVIDIA]["fallbacks"] == ["reserva"]

        with pytest.raises(prov.ProvedorInvalido):
            await prov.salvar_provedor(prov.NVIDIA, {"base_url": "http://malicioso"})

    @pytest.mark.asyncio
    async def test_gravar_reserva_nao_apaga_modelo_nem_chave(self, banco):
        await prov.salvar_provedor(prov.OPENROUTER, {"api_key": "sk-or-secreta"})
        await prov.definir_modelo(prov.OPENROUTER, "google/gemma-4-26b-a4b-it:free")
        await prov.definir_fallbacks(prov.OPENROUTER, ["outro:free"])

        salvo = (await prov._configs())[prov.OPENROUTER]
        assert salvo["api_key"] == "sk-or-secreta"
        assert salvo["modelo"] == "google/gemma-4-26b-a4b-it:free"
        assert salvo["fallbacks"] == ["outro:free"]

    @pytest.mark.asyncio
    async def test_reserva_de_um_provedor_nao_vaza_para_o_outro(self, banco, monkeypatch):
        # Um id do OpenRouter não existe na NVIDIA: lista global apontaria para o nada.
        monkeypatch.setenv("NVIDIA_API_KEY", "chave")
        await prov.definir_fallbacks(prov.OPENROUTER, ["moonshotai/kimi-k2"])
        assert (await prov.provedor_vigente())["fallbacks"] == \
            prov.CATALOGO[prov.NVIDIA]["fallbacks"]

    @pytest.mark.asyncio
    async def test_openrouter_e_custom_passam_a_poder_ter_reserva(self, banco):
        # Antes, `fallbacks` só existia no CATALOGO da NVIDIA: os outros rodavam sem rede nenhuma.
        await prov.definir_fallbacks(prov.CUSTOM, ["local-1", "local-2"])
        tela = await prov.listar_para_tela()
        custom = next(x for x in tela["provedores"] if x["id"] == prov.CUSTOM)
        assert custom["fallbacks"] == ["local-1", "local-2"]

    @pytest.mark.asyncio
    async def test_pid_desconhecido_e_recusado(self, banco):
        with pytest.raises(prov.ProvedorInvalido):
            await prov.definir_fallbacks("inexistente", ["x"])
        with pytest.raises(prov.ProvedorInvalido):
            await prov.limpar_fallbacks("inexistente")

    @pytest.mark.asyncio
    async def test_a_tela_continua_sem_chave_em_claro(self, banco):
        await prov.salvar_provedor(prov.OPENROUTER, {"api_key": "sk-or-secreta"})
        await prov.definir_fallbacks(prov.OPENROUTER, ["a"])
        assert "sk-or-secreta" not in repr(await prov.listar_para_tela())


class TestProvedoresNovos:
    """OrcaRouter e Google AI Studio (Gemini), acrescentados em 19/08.

    Os dois entram sem código próprio porque falam o dialeto OpenAI. No caso do Gemini isso só
    vale pela **camada de compatibilidade** (`/v1beta/openai`) — a API nativa tem outro formato.
    """

    def test_gemini_aponta_para_a_camada_de_compatibilidade(self):
        url = prov.CATALOGO[prov.GEMINI]["base_url"]
        assert url.endswith("/v1beta/openai"), \
            "sem o sufixo openai a URL cai na API nativa do Gemini, que não fala este dialeto"
        assert not url.endswith("/"), "o código concatena '/chat/completions'; barra dupla quebra"

    def test_todas_as_base_urls_do_catalogo_seguem_a_mesma_regra(self):
        # O código monta `f"{base_url}/chat/completions"`: barra no fim vira `//` no caminho.
        for pid, base in prov.CATALOGO.items():
            assert not (base["base_url"] or "").endswith("/"), pid

    def test_gemini_nao_afirma_gratuidade(self):
        """Flash é gratuito, Pro não (04/2026), e a camada OpenAI não devolve `pricing`.
        Marcar tudo como gratuito mentiria — e ainda faria o teste de saúde varrer a lista
        inteira, queimando a cota diária do nível gratuito."""
        assert prov.CATALOGO[prov.GEMINI]["todos_gratuitos"] is None
        assert prov.eh_gratuito({"id": "gemini-3.7-flash"},
                                {"todos_gratuitos": None}) is None

    def test_orcarouter_tem_preco_por_modelo_como_o_openrouter(self):
        assert prov.CATALOGO[prov.ORCAROUTER]["todos_gratuitos"] is False

    def test_nenhum_dos_novos_nasce_com_reserva_fixa_no_codigo(self):
        """Lista de reserva de provedor novo nasce VAZIA: id de modelo tem validade (foi o que
        custou 11 dias em 08/08), e agora o admin monta a dele na tela, com o chip de saúde."""
        for pid in (prov.ORCAROUTER, prov.GEMINI):
            assert prov.CATALOGO[pid].get("fallbacks", []) == []

    def test_so_o_openrouter_manda_cabecalho_de_atribuicao(self):
        for pid in (prov.ORCAROUTER, prov.GEMINI):
            h = prov.cabecalhos({"id": pid, "api_key": "k"})
            assert h["Authorization"] == "Bearer k"
            assert "X-Title" not in h and "HTTP-Referer" not in h

    @pytest.mark.asyncio
    async def test_a_chave_dos_novos_vem_do_banco_ou_do_env(self, banco, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "do-env")
        await prov.definir_ativo(prov.GEMINI)
        assert (await prov.provedor_vigente())["api_key"] == "do-env"

        await prov.salvar_provedor(prov.GEMINI, {"api_key": "do-banco"})
        assert (await prov.provedor_vigente())["api_key"] == "do-banco"

    @pytest.mark.asyncio
    async def test_url_dos_hospedados_nao_e_redirecionavel(self, banco, monkeypatch):
        """Guarda de exfiltração: só o `custom` aceita URL livre. Sem isto, apontar a base_url
        para um host arbitrário levaria a chave já gravada junto."""
        monkeypatch.setenv("GEMINI_API_KEY", "segredo")
        await prov.salvar_provedor(prov.GEMINI, {"base_url": "http://host-do-atacante"})
        # `provedor_vigente()` devolve o ATIVO (nvidia aqui); quem guarda a URL do gemini é a
        # configuração salva — é lá que a guarda tem de aparecer.
        assert (await prov._configs())[prov.GEMINI]["base_url"] \
            == prov.CATALOGO[prov.GEMINI]["base_url"]

    @pytest.mark.asyncio
    async def test_os_novos_aparecem_na_tela_sem_chave_em_claro(self, banco):
        await prov.salvar_provedor(prov.ORCAROUTER, {"api_key": "sk-orca-secreta"})
        vista = await prov.listar_para_tela()
        ids = [p["id"] for p in vista["provedores"]]
        assert prov.ORCAROUTER in ids and prov.GEMINI in ids
        assert "sk-orca-secreta" not in repr(vista)
        orca = next(p for p in vista["provedores"] if p["id"] == prov.ORCAROUTER)
        assert orca["chave_fonte"] == "banco" and orca["chave_mascarada"].endswith("reta")


class TestVariasChaves:
    """Uma chave por provedor não bastava: o limite de taxa é POR CHAVE (19/08).

    O gatilho concreto é o nível gratuito do Google AI Studio — ~500 requisições/dia, que uma
    turma inteira consome numa aula.
    """

    @pytest.mark.asyncio
    async def test_sem_nada_no_banco_vale_a_chave_do_env(self, banco, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "do-env")
        p = await prov.provedor_vigente()
        assert p["api_keys"] == ["do-env"]
        assert p["api_key"] == "do-env"          # a primeira, para quem só sabe ler uma

    @pytest.mark.asyncio
    async def test_a_chave_unica_antiga_continua_valendo(self, banco, monkeypatch):
        """Formato anterior (`api_key`): quem já tinha configurado não pode quebrar no deploy."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        await prov.salvar_provedor(prov.OPENROUTER, {"api_key": "sk-antiga"})
        await prov.definir_ativo(prov.OPENROUTER)
        assert (await prov.provedor_vigente())["api_keys"] == ["sk-antiga"]

    @pytest.mark.asyncio
    async def test_adicionar_migra_o_formato_antigo_e_acumula(self, banco, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        await prov.salvar_provedor(prov.OPENROUTER, {"api_key": "sk-antiga"})
        assert await prov.adicionar_chave(prov.OPENROUTER, "sk-nova") == 2

        salvo = (await prov._configs())[prov.OPENROUTER]
        assert salvo["api_keys"] == ["sk-antiga", "sk-nova"]
        # o campo antigo SOME: duas fontes divergiriam na primeira edição
        assert "api_key" not in salvo

    @pytest.mark.asyncio
    async def test_nvidia_aceita_chave_pela_tela_mesmo_nao_sendo_editavel(self, banco):
        """`editavel: False` diz que URL e nome vêm do `.env`, não que a chave seja imutável.
        Isto reverte, por decisão do dono, o invariante original do ADR 0003."""
        assert await prov.adicionar_chave(prov.NVIDIA, "nvapi-1") == 1
        assert await prov.adicionar_chave(prov.NVIDIA, "nvapi-2") == 2
        p = await prov.provedor_vigente()
        assert p["api_keys"] == ["nvapi-1", "nvapi-2"]

    @pytest.mark.asyncio
    async def test_o_banco_vence_o_env_inteiro_e_nao_mistura(self, banco, monkeypatch):
        """Se o admin gravou chave pela tela, é dela que ele está falando. Misturar traria de
        volta, em silêncio, uma chave que ele pode ter acabado de tirar."""
        monkeypatch.setenv("NVIDIA_API_KEY", "do-env")
        await prov.adicionar_chave(prov.NVIDIA, "da-tela")
        assert (await prov.provedor_vigente())["api_keys"] == ["da-tela"]

    @pytest.mark.asyncio
    async def test_recusa_repetida_e_respeita_o_teto(self, banco):
        await prov.adicionar_chave(prov.GEMINI, "k1")
        with pytest.raises(prov.ProvedorInvalido):
            await prov.adicionar_chave(prov.GEMINI, "k1")
        for i in range(2, prov.MAX_CHAVES + 1):
            await prov.adicionar_chave(prov.GEMINI, f"k{i}")
        with pytest.raises(prov.ProvedorInvalido):
            await prov.adicionar_chave(prov.GEMINI, "excedente")

    @pytest.mark.asyncio
    async def test_recusa_chave_vazia(self, banco):
        with pytest.raises(prov.ProvedorInvalido):
            await prov.adicionar_chave(prov.GEMINI, "   ")

    @pytest.mark.asyncio
    async def test_remover_por_indice(self, banco):
        for k in ("k1", "k2", "k3"):
            await prov.adicionar_chave(prov.GEMINI, k)
        assert await prov.remover_chave(prov.GEMINI, 1) == 2
        assert (await prov._configs())[prov.GEMINI]["api_keys"] == ["k1", "k3"]
        with pytest.raises(prov.ProvedorInvalido):
            await prov.remover_chave(prov.GEMINI, 9)

    @pytest.mark.asyncio
    async def test_a_tela_recebe_as_chaves_mascaradas_e_indexadas(self, banco):
        await prov.adicionar_chave(prov.GEMINI, "AIzaSyPRIMEIRA")
        await prov.adicionar_chave(prov.GEMINI, "AIzaSySEGUNDA")
        vista = await prov.listar_para_tela()
        g = next(p for p in vista["provedores"] if p["id"] == prov.GEMINI)
        assert [c["indice"] for c in g["chaves"]] == [0, 1]
        assert all(c["mascarada"].startswith("••••") for c in g["chaves"])
        assert "AIzaSyPRIMEIRA" not in repr(vista) and "AIzaSySEGUNDA" not in repr(vista)

    @pytest.mark.asyncio
    async def test_provedor_com_chave_conta_como_configurado(self, banco, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        vista = await prov.listar_para_tela()
        assert not next(p for p in vista["provedores"] if p["id"] == prov.GEMINI)["configurado"]
        await prov.adicionar_chave(prov.GEMINI, "k")
        vista = await prov.listar_para_tela()
        assert next(p for p in vista["provedores"] if p["id"] == prov.GEMINI)["configurado"]

    def test_cabecalhos_usam_a_chave_pedida(self):
        p = {"id": "gemini", "api_key": "primeira"}
        assert prov.cabecalhos(p)["Authorization"] == "Bearer primeira"
        assert prov.cabecalhos(p, "segunda")["Authorization"] == "Bearer segunda"
        # endpoint self-hosted sem chave: nada de `Authorization` vazio
        assert "Authorization" not in prov.cabecalhos({"id": "custom", "api_key": ""}, "")
