"""Provedores de LLM do tutor: qual serviço responde ao chat, com que chave e que modelo.

Todos os provedores suportados falam o dialeto **OpenAI-compatible** (`/models` e
`/chat/completions`), então o que muda entre eles é só `base_url` + chave + modelo — e é
exatamente isso que este módulo resolve. O resto do backend continua fazendo uma chamada só.

Onde o estado vive (`db.configuracoes_tutor`, admin-only para escrever):

```
{ chave: "llm_provedor",   valor: "nvidia" | "openrouter" | "custom" }
{ chave: "llm_provedores", valor: { "<id>": {nome?, base_url?, api_key?, modelo?, fallbacks?} } }
{ chave: "llm_model",      valor: "…" }   # legado: o modelo de quando só havia NVIDIA
```

Três decisões que valem explicar:

- **O modelo é por provedor** — e a lista de reserva (`fallbacks`) também, pela mesma razão. Um id
  de modelo do OpenRouter não existe na NVIDIA; guardar um "modelo ativo" global faria a troca de
  provedor apontar para um modelo inexistente.
- **A chave da NVIDIA continua só no `.env`** (`NVIDIA_API_KEY`) — o invariante de que ela nunca
  toca o banco nem o frontend não muda. Os provedores configuráveis pela tela guardam a chave no
  banco porque é o que permite ao admin ligá-los sem deploy; a leitura devolve só os últimos 4
  caracteres, nunca o valor.
- **`base_url` privada é permitida** para o provedor customizado (admin-only). É deliberado: o caso
  de uso é um LLM self-hosted (Ollama, vLLM, LM Studio) em `localhost` ou na rede interna. Por isso
  aqui NÃO se aplica o anti-SSRF da ingestão por URL, que existe para dado vindo de aluno.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

CHAVE_ATIVO = "llm_provedor"
CHAVE_PROVEDORES = "llm_provedores"
CHAVE_MODELO_LEGADO = "llm_model"

NVIDIA = "nvidia"
OPENROUTER = "openrouter"
CUSTOM = "custom"

# `todos_gratuitos`: a plataforma de build da NVIDIA é de uso livre com limite de taxa, então
# marcar tudo como gratuito descreve a realidade — e é o que o admin espera ver ao comparar com o
# OpenRouter, onde o preço vem na resposta da API.
CATALOGO: Dict[str, Dict[str, Any]] = {
    NVIDIA: {
        "nome": "NVIDIA NIM",
        "base_url": os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        "env_chave": "NVIDIA_API_KEY",
        "modelo_padrao": os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct"),
        # Rede de segurança quando o modelo escolhido não atende: o catálogo `/models` da NVIDIA
        # lista modelos que a CONTA pode não ter liberado, e aí a inferência devolve
        # `404 Function ... Not found for account` — foi o que derrubou o tutor em 01/08 com o
        # `moonshotai/kimi-k2.6`. O `deepseek-ai/deepseek-v4-flash` saiu daqui em 18/08: atingiu
        # FIM DE VIDA em 07/08 e responde `410 Gone`.
        #
        # **Medidos GERANDO texto** (90 tokens), 19/08 — não por ping: o `minimaxai/minimax-m3`
        # saiu daqui no mesmo dia porque respondia um ping em 628 ms e **estourava 120 s** numa
        # resposta de verdade. Ping mede se o endpoint aceita a chamada, não se o modelo serve.
        "fallbacks": [
            "nvidia/llama-3.3-nemotron-super-49b-v1.5",   # 200 em 2,1 s
            "meta/llama-3.1-8b-instruct",                 # 200 em 0,7 s
        ],
        "todos_gratuitos": True,
        "editavel": False,      # base_url e chave vêm do .env
        "exige_chave": True,
    },
    OPENROUTER: {
        "nome": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "env_chave": "OPENROUTER_API_KEY",
        "modelo_padrao": "",
        "todos_gratuitos": False,   # o preço vem em `pricing` na resposta de /models
        "editavel": True,
        "exige_chave": True,
    },
    CUSTOM: {
        "nome": "Outro provedor (OpenAI-compatible)",
        "base_url": "",
        "env_chave": "",
        "modelo_padrao": "",
        # Um provedor arbitrário pode ser pago; sem informação de preço, não afirmamos nada.
        "todos_gratuitos": None,
        "editavel": True,
        # Um endpoint self-hosted (Ollama, vLLM, LM Studio) normalmente não pede chave — e ele é
        # justamente o motivo de existirem os campos de URL base e porta.
        "exige_chave": False,
    },
}

ORDEM = (NVIDIA, OPENROUTER, CUSTOM)


class ProvedorInvalido(ValueError):
    """Configuração recusada — a mensagem vai direto para o admin na tela."""


def normalizar_base_url(base_url: str, porta: Optional[int] = None) -> str:
    """Valida a URL base e junta a porta, se vier separada.

    Aceita endereço privado de propósito (LLM self-hosted é o caso de uso); o que se recusa é o
    que não daria uma requisição HTTP válida.
    """
    bruto = (base_url or "").strip().rstrip("/")
    if not bruto:
        raise ProvedorInvalido("Informe a URL base do provedor (ex.: http://127.0.0.1:11434/v1).")
    if "://" not in bruto:
        bruto = f"http://{bruto}"
    p = urlparse(bruto)
    if p.scheme not in ("http", "https"):
        raise ProvedorInvalido("A URL base precisa começar com http:// ou https://.")
    if not p.hostname:
        raise ProvedorInvalido("A URL base não tem um endereço válido.")
    if porta:
        if not 1 <= int(porta) <= 65535:
            raise ProvedorInvalido("Porta fora da faixa (1–65535).")
        if not p.port:      # porta explícita na URL vence a do campo separado
            p = p._replace(netloc=f"{p.hostname}:{int(porta)}")
    return urlunparse(p).rstrip("/")


# ---------------------------------------------------------------- lista de reserva (fallbacks)
# Teto de itens na cadeia. NÃO é estética: cada tentativa morta é um round-trip antes de o aluno
# ver qualquer coisa, e o cliente do caminho não-stream espera até 60 s por tentativa. 404/410
# voltam rápido (~200 ms); timeout é o que dói. 5 reservas = 6 tentativas, pior caso contido.
MAX_FALLBACKS = 5


def normalizar_fallbacks(modelos: Any) -> List[str]:
    """Limpa a lista que veio da tela: descarta o que não é texto útil, tira repetido preservando
    a ordem (a ordem É a configuração) e aplica os tetos."""
    if not isinstance(modelos, list):
        return []
    vistos, saida = set(), []
    for m in modelos:
        if not isinstance(m, str):
            continue
        m = m.strip()[:200]     # mesmo teto por id que `modelo`
        if not m or m in vistos:
            continue
        vistos.add(m)
        saida.append(m)
        if len(saida) >= MAX_FALLBACKS:
            break
    return saida


def fallbacks_efetivos(pid: str, salvo: Dict[str, Any]) -> tuple[List[str], str]:
    """`(lista, origem)` — `origem` é `'admin'` ou `'catalogo'`.

    **`isinstance`, não `or`, e isso importa.** O resto do módulo usa o idioma
    `(salvo.get(x) or padrão)`, que com uma LISTA colapsa `[]` em "não configurado" e devolveria o
    padrão do código justamente a quem pediu para não ter reserva nenhuma. Ausente (ou lixo de
    outro formato) = padrão do catálogo; lista presente, mesmo vazia = decisão do admin.
    """
    bruto = salvo.get("fallbacks")
    if not isinstance(bruto, list):
        return list((CATALOGO.get(pid) or {}).get("fallbacks") or []), "catalogo"
    return normalizar_fallbacks(bruto), "admin"


def mascarar(chave: str) -> str:
    """Últimos 4 caracteres, para o admin reconhecer qual chave está lá sem poder lê-la."""
    limpa = (chave or "").strip()
    if not limpa:
        return ""
    return f"••••{limpa[-4:]}" if len(limpa) > 4 else "••••"


def _colecao():
    """Resolve a coleção na hora do uso (import tardio, como nos seeds): mantém o módulo
    importável sem `MONGO_URL` e deixa um patch em `app.database` valer aqui também."""
    from app import database

    return database.configuracoes_tutor


def tem_chave(pid: str, salvo: Dict[str, Any]) -> bool:
    """Há chave utilizável para este provedor (gravada pelo admin ou vinda do ambiente)?"""
    base = CATALOGO.get(pid) or {}
    do_env = os.getenv(base.get("env_chave") or "", "") if base.get("env_chave") else ""
    return bool((salvo.get("api_key") or "").strip() or do_env)


async def _ler(chave: str) -> Any:
    try:
        doc = await _colecao().find_one({"chave": chave})
    except Exception:
        return None
    return (doc or {}).get("valor")


async def _ler_muitas(*chaves: str) -> Dict[str, Any]:
    """Lê várias configurações numa consulta só — `provedor_vigente` roda em TODA pergunta do chat,
    e três `find_one` por mensagem eram três idas ao banco para montar um dicionário."""
    try:
        cursor = _colecao().find({"chave": {"$in": list(chaves)}})
        docs = await cursor.to_list(length=len(chaves))
    except Exception:
        return {}
    return {d.get("chave"): d.get("valor") for d in docs if d.get("chave")}


async def _configs() -> Dict[str, Dict[str, Any]]:
    valor = await _ler(CHAVE_PROVEDORES)
    return valor if isinstance(valor, dict) else {}


async def id_ativo() -> str:
    valor = await _ler(CHAVE_ATIVO)
    return valor if valor in CATALOGO else NVIDIA


async def provedor_vigente() -> Dict[str, Any]:
    """O provedor que atende o chat AGORA: `{id, nome, base_url, api_key, modelo, gratuitos_apenas}`.

    Nunca levanta: sem configuração, cai na NVIDIA com o `.env` — o mesmo comportamento de antes de
    existirem provedores.
    """
    lidas = await _ler_muitas(CHAVE_ATIVO, CHAVE_PROVEDORES, CHAVE_MODELO_LEGADO)
    pid = lidas.get(CHAVE_ATIVO) if lidas.get(CHAVE_ATIVO) in CATALOGO else NVIDIA
    base = CATALOGO[pid]
    configs = lidas.get(CHAVE_PROVEDORES)
    salvo = (configs.get(pid) if isinstance(configs, dict) else None) or {}

    api_key = ""
    if base["env_chave"]:
        api_key = os.getenv(base["env_chave"], "")
    # A chave gravada pelo admin prevalece sobre a do ambiente (é a que ele acabou de testar).
    api_key = (salvo.get("api_key") or api_key or "").strip()

    modelo = (salvo.get("modelo") or "").strip()
    if not modelo and pid == NVIDIA:
        # Legado: antes de existirem provedores, o modelo ativo vivia em `llm_model`.
        modelo = (lidas.get(CHAVE_MODELO_LEGADO) or base["modelo_padrao"] or "").strip()

    return {
        "id": pid,
        "nome": salvo.get("nome") or base["nome"],
        "base_url": (salvo.get("base_url") or base["base_url"] or "").rstrip("/"),
        "api_key": api_key,
        "modelo": modelo,
        # Modelos a tentar se o escolhido não atender. Vem do banco quando o admin configurou
        # (conf-tutor → LLM); senão, do CATALOGO. Modelo de LLM tem validade: uma lista fixa no
        # código envelhece sozinha e só um deploy a conserta — foi o que custou 11 dias em 08/08.
        "fallbacks": fallbacks_efetivos(pid, salvo)[0],
        "todos_gratuitos": base["todos_gratuitos"],
        "exige_chave": base["exige_chave"],
    }


async def listar_para_tela() -> Dict[str, Any]:
    """Visão para o admin — **sem chave em claro**, só o mascarado e de onde ela vem."""
    ativo = await id_ativo()
    salvos = await _configs()
    legado = await _ler(CHAVE_MODELO_LEGADO)

    provedores: List[Dict[str, Any]] = []
    for pid in ORDEM:
        base = CATALOGO[pid]
        salvo = salvos.get(pid) or {}
        chave_env = os.getenv(base["env_chave"], "") if base["env_chave"] else ""
        chave_banco = (salvo.get("api_key") or "").strip()
        modelo = (salvo.get("modelo") or "").strip()
        if not modelo and pid == NVIDIA:
            modelo = (legado or base["modelo_padrao"] or "").strip()
        reservas, reservas_origem = fallbacks_efetivos(pid, salvo)
        provedores.append({
            "id": pid,
            "nome": salvo.get("nome") or base["nome"],
            "base_url": (salvo.get("base_url") or base["base_url"] or "").rstrip("/"),
            "modelo": modelo,
            # A ordem de tentativa quando o modelo escolhido não atende, e se ela é do admin ou
            # o padrão do código (a tela mostra "Voltar ao padrão do sistema" só no primeiro caso).
            "fallbacks": reservas,
            "fallbacks_origem": reservas_origem,
            "editavel": base["editavel"],
            "todos_gratuitos": base["todos_gratuitos"],
            # De onde sai a chave que será usada: 'banco' (o admin gravou), 'env' (.env do
            # servidor) ou 'ausente' (o provedor não vai funcionar até alguém informar).
            "chave_fonte": "banco" if chave_banco else ("env" if chave_env else "ausente"),
            "chave_mascarada": mascarar(chave_banco or chave_env),
            "env_chave": base["env_chave"] or None,
            # Pronto para ser ativado: URL base sempre; chave só quando o provedor a exige.
            "configurado": bool((salvo.get("base_url") or base["base_url"])
                                and (not base["exige_chave"] or chave_banco or chave_env)),
            "exige_chave": base["exige_chave"],
        })
    return {"ativo": ativo, "provedores": provedores}


async def salvar_provedor(pid: str, dados: Dict[str, Any], usuario_id: str = "") -> None:
    """Grava a configuração de um provedor editável. Chave vazia = manter a que está lá."""
    if pid not in CATALOGO:
        raise ProvedorInvalido("Provedor desconhecido.")
    base = CATALOGO[pid]
    if not base["editavel"]:
        raise ProvedorInvalido(
            f"{base['nome']} é configurado pelo .env do servidor ({base['env_chave']}), não pela tela.")

    salvos = await _configs()
    atual = dict(salvos.get(pid) or {})
    url_antiga = atual.get("base_url")

    # base_url livre SÓ no provedor customizado (self-hosted). Provedores hospedados
    # (ex.: openrouter) têm URL fixa do catálogo — antes, mudar a base_url deles
    # redirecionava a chave já armazenada para um host arbitrário (exfiltração).
    if pid == CUSTOM:
        if "base_url" in dados or "porta" in dados:
            atual["base_url"] = normalizar_base_url(
                dados.get("base_url") or atual.get("base_url") or base["base_url"],
                dados.get("porta"),
            )
    else:
        atual["base_url"] = base["base_url"]
    if dados.get("nome"):
        atual["nome"] = str(dados["nome"])[:80]
    if dados.get("modelo") is not None:
        atual["modelo"] = str(dados["modelo"] or "")[:200]
    chave = (dados.get("api_key") or "").strip()
    if chave:
        # Só sobrescreve quando o admin digita algo: assim ele edita outros campos sem redigitar a chave.
        atual["api_key"] = chave
    elif url_antiga is not None and atual.get("base_url") != url_antiga:
        # base_url mudou e não veio chave nova: NÃO manda a chave antiga para o novo
        # host — exige que o admin redigite a chave para o endereço novo.
        atual.pop("api_key", None)

    if pid == CUSTOM and not atual.get("base_url"):
        raise ProvedorInvalido("Informe a URL base do provedor customizado.")

    salvos[pid] = atual
    await _colecao().update_one(
        {"chave": CHAVE_PROVEDORES},
        {"$set": {"chave": CHAVE_PROVEDORES, "valor": salvos,
                  "atualizado_por": usuario_id}},
        upsert=True,
    )


async def definir_ativo(pid: str, usuario_id: str = "") -> None:
    if pid not in CATALOGO:
        raise ProvedorInvalido("Provedor desconhecido.")
    salvos = await _configs()
    salvo = salvos.get(pid) or {}
    base = CATALOGO[pid]
    if not (salvo.get("base_url") or base["base_url"]):
        raise ProvedorInvalido("Configure a URL base antes de ativar este provedor.")
    if base["exige_chave"] and not tem_chave(pid, salvo):
        raise ProvedorInvalido(
            f"{salvo.get('nome') or base['nome']} ainda não tem chave de API configurada.")
    await _colecao().update_one(
        {"chave": CHAVE_ATIVO},
        {"$set": {"chave": CHAVE_ATIVO, "valor": pid, "atualizado_por": usuario_id}},
        upsert=True,
    )


async def definir_modelo(pid: str, modelo: str, usuario_id: str = "") -> None:
    """Modelo ativo DO provedor. Também atualiza `llm_model` quando é a NVIDIA, para um rollback
    do código continuar encontrando o modelo onde ele sempre esteve."""
    if pid not in CATALOGO:
        raise ProvedorInvalido("Provedor desconhecido.")
    salvos = await _configs()
    atual = dict(salvos.get(pid) or {})
    atual["modelo"] = (modelo or "").strip()[:200]
    salvos[pid] = atual
    await _colecao().update_one(
        {"chave": CHAVE_PROVEDORES},
        {"$set": {"chave": CHAVE_PROVEDORES, "valor": salvos, "atualizado_por": usuario_id}},
        upsert=True,
    )
    if pid == NVIDIA:
        await _colecao().update_one(
            {"chave": CHAVE_MODELO_LEGADO},
            {"$set": {"chave": CHAVE_MODELO_LEGADO, "valor": atual["modelo"],
                      "atualizado_por": usuario_id}},
            upsert=True,
        )


async def definir_fallbacks(pid: str, modelos: List[str], usuario_id: str = "") -> List[str]:
    """Lista de reserva DO provedor, na ordem de tentativa. Devolve o que ficou gravado.

    Como `definir_modelo`, grava mesmo em provedor não editável: `editavel` diz que URL e chave
    vêm do `.env` (é o caso da NVIDIA), não que a escolha de modelos seja imutável — e a NVIDIA é
    justamente quem mais precisa de reserva.

    Escreve no CAMINHO pontual (`valor.<pid>.fallbacks`) em vez de reler e regravar o documento
    inteiro: assim duas edições simultâneas de provedores diferentes não se sobrescrevem. `pid`
    vem da allowlist do `CATALOGO`, então não há como injetar caminho.
    """
    if pid not in CATALOGO:
        raise ProvedorInvalido("Provedor desconhecido.")
    lista = normalizar_fallbacks(modelos)
    await _colecao().update_one(
        {"chave": CHAVE_PROVEDORES},
        {"$set": {"chave": CHAVE_PROVEDORES, f"valor.{pid}.fallbacks": lista,
                  "atualizado_por": usuario_id}},
        upsert=True,
    )
    return lista


async def limpar_fallbacks(pid: str, usuario_id: str = "") -> List[str]:
    """Descarta a lista do admin e volta ao padrão do catálogo. Devolve o padrão que passa a valer.

    É `$unset`, não `$set` de `[]`: gravar lista vazia significa "não quero reserva nenhuma", que é
    uma escolha diferente de "use o que o sistema recomenda".
    """
    if pid not in CATALOGO:
        raise ProvedorInvalido("Provedor desconhecido.")
    await _colecao().update_one(
        {"chave": CHAVE_PROVEDORES},
        {"$unset": {f"valor.{pid}.fallbacks": ""},
         "$set": {"atualizado_por": usuario_id}},
    )
    return list(CATALOGO[pid].get("fallbacks") or [])


def eh_gratuito(modelo: Dict[str, Any], provedor: Dict[str, Any]) -> Optional[bool]:
    """`True`/`False` quando se sabe; `None` quando não há informação de preço.

    OpenRouter manda `pricing` em cada modelo — gratuito é preço 0 de entrada E de saída (o que
    também pega os poucos gratuitos cujo id não termina em `:free`). Para a NVIDIA vale a convenção
    do catálogo; para um provedor arbitrário, não afirmamos nada.
    """
    if provedor.get("todos_gratuitos") is True:
        return True
    preco = modelo.get("pricing")
    if isinstance(preco, dict):
        try:
            return (float(preco.get("prompt") or 0) == 0.0
                    and float(preco.get("completion") or 0) == 0.0)
        except (TypeError, ValueError):
            return None
    return None


def cabecalhos(provedor: Dict[str, Any]) -> Dict[str, str]:
    """Cabeçalhos da chamada. O OpenRouter usa `X-Title`/`HTTP-Referer` para atribuir o uso."""
    h = {"Accept": "application/json"}
    # Sem chave (endpoint local), não manda `Authorization` vazio: alguns servidores recusam o
    # cabeçalho malformado em vez de ignorá-lo.
    if provedor.get("api_key"):
        h["Authorization"] = f"Bearer {provedor['api_key']}"
    if provedor["id"] == OPENROUTER:
        h["X-Title"] = "H2IA Tutor"
        h["HTTP-Referer"] = os.getenv("FRONTEND_URL", "https://absapt.tk/h2ia/tutor")
    return h
