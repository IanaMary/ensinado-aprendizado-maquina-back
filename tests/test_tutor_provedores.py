"""Provedores de LLM: resolução do provedor ativo, gratuidade e as garantias sobre a chave.

Duas garantias negativas guiam o arquivo:

1. **a chave de API nunca sai em claro** por nenhuma leitura;
2. **trocar de provedor não herda o modelo do outro** — um id do OpenRouter não existe na NVIDIA, e
   um "modelo global" apontaria para o nada.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app import tutor_provedores as prov


def _colecao(docs: dict):
    """Coleção fake indexada por `chave`, com upsert que grava no próprio dicionário."""
    async def find_one(filtro, *a, **k):
        return docs.get(filtro.get("chave"))

    async def update_one(filtro, update, **k):
        chave = filtro.get("chave")
        doc = dict(docs.get(chave) or {})
        doc.update((update.get("$set") or {}))
        docs[chave] = doc
        return MagicMock(upserted_id=None, modified_count=1)

    return MagicMock(find_one=AsyncMock(side_effect=find_one),
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
        assert [p["id"] for p in vista["provedores"]] == ["nvidia", "openrouter", "custom"]
        assert vista["ativo"] == "nvidia"


class TestDefinirAtivo:
    @pytest.mark.asyncio
    async def test_recusa_provedor_sem_chave(self, banco, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises(prov.ProvedorInvalido) as e:
            await prov.definir_ativo("openrouter")
        assert "chave" in str(e.value).lower()

    @pytest.mark.asyncio
    async def test_recusa_custom_sem_url(self, banco):
        with pytest.raises(prov.ProvedorInvalido):
            await prov.definir_ativo("custom")


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
