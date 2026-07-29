"""Chatbot tutor: proxy seguro para o provedor de LLM ativo (dialeto OpenAI-compatible).

Qual provedor atende (NVIDIA NIM, OpenRouter ou um endpoint customizado), com que chave e que
modelo, é resolvido por `app/tutor_provedores.py`. **Nenhuma chave de API chega ao frontend**: a da
NVIDIA vive só no `.env`; as dos provedores configuráveis ficam no banco e a leitura só devolve os
últimos 4 caracteres. O chatbot
recebe o contexto do pipeline carregado (dataset, modelo, hiperparametros, metricas,
graficos, codigo Python gerado) e responde de forma pedagogica, em PT-BR, para alunos.
"""
import json
import logging
import asyncio
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import httpx
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.conteudo.kb_tutor_chat import (
    HASH_SYSTEM_PROMPT,
    MAX_SYSTEM_PROMPT_CHARS,
    SYSTEM_PROMPT_TUTOR,
    hash_prompt,
)
from app.conteudo.system_prompt_seed import ORIGEM_ADMIN, ORIGEM_VERSIONADO
from app import tutor_provedores as prov
from app.database import historico_chat, configuracoes_tutor, tutor_audit, turmas
from app.routers.atividade import registrar_atividade
from app.security import get_usuario_atual, exigir_admin_ou_professor
from app.tutor_kb import NIVEL_AVANCADO, bloco_kb, nivel_do_contexto
from app.schemas.chat import (
    ChatHistoricoListItem,
    ChatHistoricoResponse,
    ChatMensagem,
    ChatTutorRequest,
)
from app.schemas.tutor import DefinirSystemPromptRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tutor", tags=["Tutor"])


# ============================================================
# RATE LIMITING (in-memory, por usuario)
# ============================================================
RATE_LIMIT_MAX = int(os.getenv("CHAT_RATE_LIMIT_MAX", "20"))  # requests
RATE_LIMIT_WINDOW = int(os.getenv("CHAT_RATE_LIMIT_WINDOW", "60"))  # segundos

_rate_limits: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(user_id: str):
    agora = time.time()
    window_start = agora - RATE_LIMIT_WINDOW
    # Remove timestamps fora da janela
    _rate_limits[user_id] = [t for t in _rate_limits[user_id] if t > window_start]
    if len(_rate_limits[user_id]) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=f"Limite de {RATE_LIMIT_MAX} mensagens por {RATE_LIMIT_WINDOW}s atingido. Aguarde e tente novamente.",
        )
    _rate_limits[user_id].append(agora)

def _ultima_msg_usuario(request: "ChatTutorRequest") -> str:
    for m in reversed(request.mensagens):
        if m.role == "user" and m.content:
            return m.content
    return ""


def _preview(texto: Optional[str], n: int = 240) -> str:
    s = texto or ""
    return s if len(s) <= n else s[:n] + "…"


def _resumo_chat(mensagem: str, resposta: str, modelo: str, contexto, *, stream: bool = False,
                 finish_reason: Optional[str] = None) -> dict:
    """Resumo compacto para a telemetria do chat.

    Guarda apenas preview + tamanho da pergunta/resposta e um descritor leve do
    contexto (chaves + campos identificadores). O conteúdo completo da conversa já
    vive em `historico_chat`; aqui evitamos inflar `atividade_usuario` (~KBs/linha)."""
    resumo_ctx = None
    if isinstance(contexto, dict):
        campos = {
            k: contexto.get(k)
            for k in ("item", "modelo", "metrica", "dataset", "etapa")
            if isinstance(contexto.get(k), (str, int, float, bool))
        }
        resumo_ctx = {"chaves": sorted(contexto.keys())}
        if campos:
            resumo_ctx["campos"] = campos
    return {
        "mensagem_preview": _preview(mensagem),
        "mensagem_tamanho": len(mensagem or ""),
        "resposta_preview": _preview(resposta),
        "resposta_tamanho": len(resposta or ""),
        "modelo": modelo,
        "contexto": resumo_ctx,
        "stream": stream,
        # `length` = a resposta bateu no teto de tokens e terminou no meio. Sem registrar,
        # ninguém percebe que o tutor foi cortado — só o aluno, que fica sem o final.
        "truncada_no_teto": finish_reason == "length",
    }


# base_url/chave/modelo de cada provedor vivem em `app/tutor_provedores.py` (CATALOGO).
# ------------------------------------------------------------------ tetos do chat
# O contexto vem no CORPO da requisição (o cliente o monta, e no modal ele inclui o script
# Python gerado): sem teto, quem chama decide quanto o servidor gasta em tokens. 12k chars
# ≈ 3–4k tokens, folgado na janela do modelo (128k no llama-3.3-70b) e ainda barato.
MAX_CONTEXTO_CHARS = int(os.getenv("CHAT_MAX_CONTEXTO_CHARS", "12000"))
# Teto da RESPOSTA. No avançado o tutor tem de caber fórmula, formalismo e leitura de
# referência — 1024 tokens (~3 mil caracteres em português) cortavam no meio da frase.
MAX_TOKENS_RESPOSTA = int(os.getenv("CHAT_MAX_TOKENS", "1536"))
MAX_TOKENS_RESPOSTA_AVANCADO = int(os.getenv("CHAT_MAX_TOKENS_AVANCADO", "3072"))
# Temperatura NÃO é configurável de propósito: subir aqui não compra profundidade, compra
# invenção — e o público é de estudantes que não têm como conferir um default inventado.
TEMPERATURA = 0.4


def max_tokens_resposta(contexto) -> int:
    """Teto de tokens da resposta, pelo nível que o aluno escolheu no perfil."""
    if nivel_do_contexto(contexto) == NIVEL_AVANCADO:
        return MAX_TOKENS_RESPOSTA_AVANCADO
    return MAX_TOKENS_RESPOSTA


# ============================================================
# CONFIGURAÇÃO DO MODELO LLM
# ============================================================

async def _buscar_modelos(provedor: dict) -> list[dict]:
    """Modelos do provedor vigente, com `gratuito` resolvido e os gratuitos na frente.

    Ordenar aqui (e não na tela) mantém a mesma ordem no seletor e em qualquer outro consumidor.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{provedor['base_url']}/models",
                                    headers=prov.cabecalhos(provedor))
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout ao listar modelos.")
    except httpx.HTTPError:
        raise HTTPException(status_code=502,
                            detail=f"Erro ao conectar com {provedor['nome']}.")

    if resp.status_code != 200:
        raise HTTPException(status_code=502,
                            detail=f"Erro ao listar modelos de {provedor['nome']} "
                                   f"(HTTP {resp.status_code}).")
    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Resposta inesperada ao listar modelos.")

    modelos = []
    for m in data.get("data", []):
        if not m.get("id"):
            continue
        modelos.append({
            "id": m["id"],
            "owned_by": m.get("owned_by") or (m.get("name") or ""),
            "gratuito": prov.eh_gratuito(m, provedor),
            "contexto": m.get("context_length"),
        })
    # Gratuitos primeiro; depois os de preço desconhecido; pagos por último. Alfabético dentro
    # de cada faixa, para a lista não dançar entre recarregamentos.
    ordem = {True: 0, None: 1, False: 2}
    modelos.sort(key=lambda m: (ordem.get(m["gratuito"], 1), m["id"]))
    return modelos


@router.get("/modelos")
async def listar_modelos(usuario=Depends(get_usuario_atual)):
    """Modelos disponíveis no provedor ativo (NVIDIA NIM, OpenRouter ou customizado)."""
    provedor = await prov.provedor_vigente()
    if not provedor["api_key"]:
        raise HTTPException(
            status_code=503,
            detail=f"{provedor['nome']} está sem chave de API configurada.",
        )
    modelos = await _buscar_modelos(provedor)
    return {
        "modelos": modelos,
        "modelo_atual": provedor["modelo"],
        "provedor": {"id": provedor["id"], "nome": provedor["nome"],
                     "todos_gratuitos": provedor["todos_gratuitos"]},
    }


# ============================================================
# HEALTH-CHECK DOS MODELOS LLM (testa em segundo plano + cache)
# ============================================================
_SAUDE_TTL = 1800  # 30 min: evita re-testar a cada abertura da tela
_saude_cache: dict = {
    "resultados": {},        # { model_id: {"responde": bool, "latencia_ms"?: int, "erro"?: str} }
    "atualizado_em": 0.0,
    "em_andamento": False,
    "total": 0,
    "concluidos": 0,
}
_saude_lock = asyncio.Lock()


async def _testar_modelo(client: httpx.AsyncClient, provedor: dict, model_id: str) -> dict:
    """Faz um ping mínimo (max_tokens=1) para saber se o modelo responde a chat."""
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "temperature": 0,
        "stream": False,
    }
    inicio = time.time()
    try:
        resp = await client.post(
            f"{provedor['base_url']}/chat/completions",
            headers=prov.cabecalhos(provedor),
            json=payload,
        )
        if resp.status_code == 200:
            return {"responde": True, "latencia_ms": int((time.time() - inicio) * 1000)}
        detalhe = f"HTTP {resp.status_code}"
        try:
            corpo = resp.json()
            detalhe = (corpo.get("detail") or corpo.get("title") or detalhe)
        except Exception:
            pass
        return {"responde": False, "erro": str(detalhe)[:140]}
    except Exception as e:
        return {"responde": False, "erro": str(e)[:140] or "falha de conexão"}


async def _rodar_health_check(provedor: dict, modelos: list[str]):
    """Testa todos os modelos com concorrência limitada, preenchendo o cache à medida
    que cada um responde (a UI mostra o progresso)."""
    sem = asyncio.Semaphore(8)
    _saude_cache["total"] = len(modelos)
    _saude_cache["concluidos"] = 0
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            async def worker(mid: str):
                async with sem:
                    res = await _testar_modelo(client, provedor, mid)
                _saude_cache["resultados"][mid] = res
                _saude_cache["concluidos"] += 1
            await asyncio.gather(*(worker(m) for m in modelos), return_exceptions=True)
    finally:
        _saude_cache["atualizado_em"] = time.time()
        _saude_cache["em_andamento"] = False


def _modelos_a_testar(modelos: list[dict], modelo_atual: str) -> list[str]:
    """Quais modelos entram no teste automático.

    Só os **gratuitos** e o **que está em uso**: no OpenRouter são 367 modelos, e testar todos
    significaria centenas de requisições por rodada — algumas cobradas — só para montar a tela. Os
    pagos aparecem na lista sem selo e podem ser testados um a um sob demanda.

    Quando o provedor é todo gratuito (NVIDIA), isso naturalmente vira "todos", preservando o
    comportamento que a tela já tinha.
    """
    ids = [m["id"] for m in modelos if m.get("gratuito") is True]
    if modelo_atual and modelo_atual not in ids:
        ids.append(modelo_atual)
    return ids


@router.get("/modelos/saude")
async def saude_modelos(usuario=Depends(get_usuario_atual), forcar: bool = Query(False),
                        modelo: Optional[str] = Query(None)):
    """Status de resposta dos modelos. Devolve o cache de imediato e dispara o teste em segundo
    plano quando ele está velho (ou `forcar=True`). Com `modelo=<id>`, testa só aquele — é o
    "testar este" dos modelos pagos, que ficam fora do teste automático."""
    provedor = await prov.provedor_vigente()
    if not provedor["api_key"]:
        raise HTTPException(status_code=503,
                            detail=f"{provedor['nome']} está sem chave de API configurada.")

    if modelo:
        async with httpx.AsyncClient(timeout=15.0) as client:
            _saude_cache["resultados"][modelo] = await _testar_modelo(client, provedor, modelo)
        return {
            "resultados": _saude_cache["resultados"],
            "atualizado_em": _saude_cache["atualizado_em"],
            "em_andamento": _saude_cache["em_andamento"],
            "total": _saude_cache["total"],
            "concluidos": _saude_cache["concluidos"],
        }

    fresco = (time.time() - _saude_cache["atualizado_em"]) < _SAUDE_TTL
    async with _saude_lock:
        if (forcar or not fresco) and not _saude_cache["em_andamento"]:
            try:
                modelos = await _buscar_modelos(provedor)
            except HTTPException:
                modelos = []
            ids = _modelos_a_testar(modelos, provedor["modelo"])
            if ids:
                _saude_cache["em_andamento"] = True
                if forcar:
                    _saude_cache["resultados"] = {}
                asyncio.create_task(_rodar_health_check(provedor, ids))

    return {
        "resultados": _saude_cache["resultados"],
        "atualizado_em": _saude_cache["atualizado_em"],
        "em_andamento": _saude_cache["em_andamento"],
        "total": _saude_cache["total"],
        "concluidos": _saude_cache["concluidos"],
    }


async def _auditar_prompt(usuario: dict, operacao: str, tamanho: int, *,
                          texto_anterior: str = "", hash_anterior: Optional[str] = None,
                          hash_novo: Optional[str] = None,
                          origem: Optional[str] = None) -> None:
    """Registra a edição do prompt em db.tutor_audit (a mesma tela mostra o histórico).

    Inserção própria em vez de reusar `_registrar_edicao` de app/routers/tutor.py: aquele
    helper deriva o `pipe` de um documento de `db.tutor`, e o prompt vive em
    `db.configuracoes_tutor`.

    `pipe: "llm"` porque a tela mostra o histórico da ABA atual e o editor do prompt vive na aba
    LLM — gravar com outro slug esconderia a entrada de quem acabou de editar.

    Guarda o `texto_anterior` INTEIRO (≤ MAX_SYSTEM_PROMPT_CHARS): é o que torna "Voltar ao padrão"
    uma operação reversível. Antes, a auditoria gravava só o tamanho e o texto do admin era
    destruído pelo `delete_one`. A projeção de `GET /tutor/audit` não devolve este campo.
    """
    try:
        await tutor_audit.insert_one({
            "pipe": "llm",
            "tutor_id": "",
            "operacao": operacao,
            "campos_alterados": ["system_prompt"],
            "tamanho": tamanho,
            "tamanho_anterior": len(texto_anterior or ""),
            "texto_anterior": texto_anterior or "",
            "hash_anterior": hash_anterior,
            "hash_novo": hash_novo,
            "origem": origem,
            "usuario_id": str(usuario.get("_id") or usuario.get("id") or ""),
            "usuario_email": usuario.get("email", ""),
            "usuario_nome": usuario.get("nome") or usuario.get("name") or usuario.get("email", ""),
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception:
        # Auditoria nao deve quebrar a edicao.
        pass


async def _auditar_llm(usuario: dict, operacao: str, detalhe: str) -> None:
    """Registra mudanças de provedor/modelo em `db.tutor_audit`, na aba LLM.

    Antes, trocar o modelo do tutor não deixava rastro nenhum — a única mudança da tela sem
    histórico. **A chave de API nunca entra aqui**: só o provedor e o modelo.
    """
    try:
        await tutor_audit.insert_one({
            "pipe": "llm",
            "tutor_id": "",
            "operacao": operacao,
            "campos_alterados": [detalhe],
            "usuario_id": str(usuario.get("_id") or ""),
            "usuario_email": usuario.get("email", ""),
            "usuario_nome": usuario.get("nome") or usuario.get("name") or usuario.get("email", ""),
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception:
        pass


@router.get("/system-prompt")
async def obter_system_prompt(usuario=Depends(exigir_admin_ou_professor)):
    """Estado da instrução de sistema: texto vigente, padrão versionado e metadados de versão.

    Gate de papel porque o prompt é a regra que o tutor segue: entregá-lo ao aluno é entregar o
    mapa para contorná-la.
    """
    estado = await _estado_system_prompt()
    baseline = estado.get("padrao_hash")
    return {
        "texto": estado["texto"],
        "padrao": SYSTEM_PROMPT_TUTOR,
        "personalizado": hash_prompt(estado["texto"]) != HASH_SYSTEM_PROMPT,
        "limite": MAX_SYSTEM_PROMPT_CHARS,
        # `fonte` distingue "banco" (persistido, regime normal) de "versionado" (caiu no fallback:
        # o seed não rodou ou a leitura falhou) — é o que torna a persistência observável na tela.
        "fonte": estado["fonte"],
        "origem": estado.get("origem"),
        "padrao_hash": HASH_SYSTEM_PROMPT,
        "padrao_hash_base": baseline,
        # Só avisa quando SABEMOS de que padrão a edição derivou: baseline ausente é "não sei",
        # e alarmar aí daria ao admin um aviso que ele não tem como resolver.
        "padrao_desatualizado": bool(
            estado.get("origem") == ORIGEM_ADMIN and baseline and baseline != HASH_SYSTEM_PROMPT
        ),
        "versao": estado.get("versao"),
        "atualizado_em": estado.get("atualizado_em"),
    }


@router.put("/system-prompt")
async def definir_system_prompt(body: DefinirSystemPromptRequest,
                                usuario=Depends(get_usuario_atual)):
    """Grava a instrução de sistema do chat. Texto vazio volta ao padrão versionado."""
    if usuario.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admins podem alterar o prompt do tutor.")

    texto = (body.texto or "").strip()

    if len(texto) > MAX_SYSTEM_PROMPT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=(f"O prompt tem {len(texto)} caracteres e o limite é {MAX_SYSTEM_PROMPT_CHARS}: "
                    "o contexto do pipeline e a base de conhecimento também ocupam a janela do modelo."),
        )

    estado = await _estado_system_prompt()
    anterior = estado["texto"] if estado["fonte"] == "banco" else ""
    restaurando = not texto
    # Texto vazio = voltar ao padrão. Isso agora GRAVA o padrão em vez de apagar o documento: o
    # estado "padrão" passa a ser um fato persistido, não a ausência de fato.
    novo = SYSTEM_PROMPT_TUTOR if restaurando else texto
    hash_novo = hash_prompt(novo)
    # Quem colou exatamente o padrão não é "admin": marcá-lo assim o congelaria fora das próximas
    # atualizações do repo sem que ele tenha um texto próprio a proteger.
    origem = ORIGEM_VERSIONADO if hash_novo == HASH_SYSTEM_PROMPT else ORIGEM_ADMIN

    if (hash_prompt(anterior) == hash_novo and estado["fonte"] == "banco"
            and estado.get("origem") == origem):
        # Nada mudou (duplo clique em Salvar): não grava nem audita, para o histórico não encher
        # de entradas idênticas.
        return {"texto": novo, "personalizado": origem == ORIGEM_ADMIN, "versao": estado.get("versao")}

    await configuracoes_tutor.update_one(
        {"chave": "system_prompt"},
        {"$set": {"chave": "system_prompt", "valor": novo,
                  "origem": origem,
                  # Baseline: o padrão que o admin tinha à frente ao gravar. Não é hash de `valor`.
                  "padrao_hash": HASH_SYSTEM_PROMPT,
                  "atualizado_por": str(usuario.get("_id", "")),
                  "atualizado_em": datetime.now(timezone.utc)},
         "$inc": {"versao": 1}},
        upsert=True,
    )
    await _auditar_prompt(
        usuario,
        "restaurou_padrao" if restaurando else "editou",
        len(novo),
        texto_anterior=anterior,
        hash_anterior=hash_prompt(anterior) if anterior else None,
        hash_novo=hash_novo,
        origem=origem,
    )
    return {"texto": novo, "personalizado": origem == ORIGEM_ADMIN}


@router.get("/modelo")
async def obter_modelo(usuario=Depends(get_usuario_atual)):
    """Modelo em uso, com o provedor a que ele pertence."""
    provedor = await prov.provedor_vigente()
    return {"modelo": provedor["modelo"],
            "provedor": {"id": provedor["id"], "nome": provedor["nome"]}}


@router.put("/modelo")
async def definir_modelo(body: dict, usuario=Depends(get_usuario_atual)):
    """Define o modelo do tutor **no provedor ativo** (cada provedor guarda o seu: um id do
    OpenRouter não existe na NVIDIA, e um "modelo global" apontaria para o nada ao trocar)."""
    if usuario.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admins podem alterar o modelo do tutor.")

    modelo = body.get("modelo")
    if not modelo or not isinstance(modelo, str):
        raise HTTPException(status_code=400, detail="Campo 'modelo' é obrigatório.")

    pid = await prov.id_ativo()
    await prov.definir_modelo(pid, modelo, str(usuario.get("_id", "")))
    await _auditar_llm(usuario, "definiu_modelo", f"{pid}: {modelo}")
    return {"modelo": modelo, "provedor": pid}


# ============================================================
# PROVEDORES DE LLM (aba "Provedores" do conf-tutor)
# ============================================================

@router.get("/provedores")
async def listar_provedores(usuario=Depends(exigir_admin_ou_professor)):
    """Provedores e como cada um está configurado. **Nunca devolve chave em claro** — só os
    últimos 4 caracteres e de onde ela vem (`banco`/`env`/`ausente`)."""
    return await prov.listar_para_tela()


@router.put("/provedores/{pid}")
async def salvar_provedor(pid: str, body: dict, usuario=Depends(get_usuario_atual)):
    """Grava URL base, porta, nome e chave de um provedor editável.

    Campo `api_key` vazio mantém a chave atual — assim o admin corrige a URL sem redigitar o
    segredo (e sem que a tela precise conhecê-lo).
    """
    if usuario.get("role") != "admin":
        raise HTTPException(status_code=403,
                            detail="Apenas admins podem configurar provedores de LLM.")
    try:
        await prov.salvar_provedor(pid, body or {}, str(usuario.get("_id", "")))
    except prov.ProvedorInvalido as e:
        raise HTTPException(status_code=400, detail=str(e))
    # A chave em si nunca entra na auditoria; o que se registra é que houve mudança e onde.
    await _auditar_llm(usuario, "configurou_provedor", pid)
    return await prov.listar_para_tela()


@router.put("/provedor-ativo")
async def definir_provedor_ativo(body: dict, usuario=Depends(get_usuario_atual)):
    """Troca o provedor que atende o chat."""
    if usuario.get("role") != "admin":
        raise HTTPException(status_code=403,
                            detail="Apenas admins podem trocar o provedor de LLM.")
    pid = (body or {}).get("provedor")
    try:
        await prov.definir_ativo(str(pid or ""), str(usuario.get("_id", "")))
    except prov.ProvedorInvalido as e:
        raise HTTPException(status_code=400, detail=str(e))
    # O teste de saúde é por provedor: manter o cache mostraria o resultado do provedor antigo.
    _saude_cache["resultados"] = {}
    _saude_cache["atualizado_em"] = 0.0
    _saude_cache["total"] = 0
    _saude_cache["concluidos"] = 0
    await _auditar_llm(usuario, "trocou_provedor", str(pid))
    return await prov.listar_para_tela()



def _montar_contexto(contexto) -> str:
    if not contexto:
        return "Nenhum pipeline carregado no momento."
    try:
        texto = json.dumps(contexto, ensure_ascii=False, indent=1, default=str)
    except Exception:
        texto = str(contexto)
    if len(texto) > MAX_CONTEXTO_CHARS:
        # Corta em fim de LINHA (o JSON sai indentado, então cada linha é um campo) e diz
        # quanto ficou de fora. Cortar no meio de uma linha entregava ao modelo um campo
        # partido, do tipo `"modelo": "random_fo` — pior que a ausência do campo.
        corte = texto[:MAX_CONTEXTO_CHARS]
        fim = corte.rfind("\n")
        if fim > 0:
            corte = corte[:fim]
        omitidos = len(texto) - len(corte)
        texto = f"{corte}\n... (contexto truncado: {omitidos} caracteres omitidos)"
    return texto


async def _estado_system_prompt() -> dict:
    """Estado completo da instrução de sistema: texto + de onde ele veio.

    `fonte: 'banco'` é o regime normal (o seed persistiu o texto); `fonte: 'versionado'` significa
    que caímos no fallback — documento ausente, vazio ou ilegível.

    `try/except` amplo de propósito: uma falha de leitura da configuração não pode derrubar o
    chat — o pior caso aceitável é responder com o prompt versionado.
    """
    try:
        config = await configuracoes_tutor.find_one({"chave": "system_prompt"})
        texto = ((config or {}).get("valor") or "").strip()
        if texto:
            return {
                "texto": texto,
                "fonte": "banco",
                "origem": (config or {}).get("origem"),
                "padrao_hash": (config or {}).get("padrao_hash"),
                "versao": (config or {}).get("versao"),
                "atualizado_em": (config or {}).get("atualizado_em"),
            }
    except Exception:
        pass
    return {"texto": SYSTEM_PROMPT_TUTOR, "fonte": "versionado", "origem": None,
            "padrao_hash": None, "versao": None, "atualizado_em": None}


async def _system_prompt_vigente() -> str:
    """Só o texto do `system` — é o que o chat precisa em cada pergunta."""
    return (await _estado_system_prompt())["texto"]


async def _montar_system(contexto) -> str:
    """System prompt + contexto do pipeline + base de conhecimento do catálogo."""
    partes = [
        await _system_prompt_vigente(),
        "=== CONTEXTO DO PIPELINE ===\n" + _montar_contexto(contexto),
    ]
    try:
        kb = await bloco_kb(contexto)
    except Exception:
        kb = ""
    if kb:
        partes.append("=== BASE DE CONHECIMENTO (catálogo verificado) ===\n" + kb)
    return "\n\n".join(partes)


@router.post("/chat")
async def chat_tutor(request: ChatTutorRequest, usuario: dict = Depends(get_usuario_atual)):
    # Rate limit: usa o id do usuário autenticado como identificador
    user_id = str(usuario.get("_id") or "anonymous")
    _check_rate_limit(user_id)

    provedor = await prov.provedor_vigente()
    if not provedor["api_key"]:
        raise HTTPException(
            status_code=503,
            detail=("O tutor por chat não está configurado no servidor "
                    f"({provedor['nome']} sem chave de API)."),
        )
    if not provedor["modelo"]:
        raise HTTPException(
            status_code=503,
            detail=f"Nenhum modelo escolhido para {provedor['nome']} (conf-tutor → LLM).",
        )
    modelo = provedor["modelo"]

    mensagens = [
        {"role": "system", "content": await _montar_system(request.contexto)},
    ]
    for m in request.mensagens:
        if m.role in ("user", "assistant") and m.content:
            mensagens.append({"role": m.role, "content": m.content})

    if len(mensagens) == 1:
        raise HTTPException(status_code=400, detail="Envie ao menos uma mensagem do usuário.")

    payload = {
        "model": modelo,
        "messages": mensagens,
        "temperature": TEMPERATURA,
        "max_tokens": max_tokens_resposta(request.contexto),
        "stream": False,
    }

    inicio = time.perf_counter()

    async def _logar(status: str, resposta: str = "", erro: Optional[str] = None,
                     finish_reason: Optional[str] = None):
        await registrar_atividade(
            usuario,
            "chat",
            "resposta_tutor",
            detalhes=_resumo_chat(_ultima_msg_usuario(request), resposta, modelo, request.contexto,
                                  finish_reason=finish_reason),
            duracao_ms=int((time.perf_counter() - inicio) * 1000),
            status=status,
            erro=erro,
        )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{provedor['base_url']}/chat/completions",
                headers=prov.cabecalhos(provedor),
                json=payload,
            )
    except httpx.TimeoutException:
        await _logar("erro", erro="timeout")
        raise HTTPException(status_code=504, detail="O tutor demorou demais para responder. Tente de novo.")
    except httpx.HTTPError as e:
        logger.warning("Falha de rede ao chamar o provedor de LLM: %s", type(e).__name__)
        await _logar("erro", erro=f"rede: {type(e).__name__}")
        raise HTTPException(status_code=502, detail="Não consegui falar com o tutor agora. Tente novamente.")

    if resp.status_code != 200:
        # Nao propagar corpo bruto do provedor (pode conter detalhes sensiveis).
        logger.warning("Provedor de LLM respondeu %s", resp.status_code)
        await _logar("erro", erro=f"http {resp.status_code}")
        raise HTTPException(status_code=502, detail="O tutor retornou um erro. Tente novamente em instantes.")

    try:
        data = resp.json()
        resposta = data["choices"][0]["message"]["content"]
        finish_reason = data["choices"][0].get("finish_reason")
    except (KeyError, IndexError, ValueError):
        await _logar("erro", erro="resposta em formato inesperado")
        raise HTTPException(status_code=502, detail="Resposta do tutor em formato inesperado.")

    if finish_reason == "length":
        logger.warning("Resposta do tutor cortada no teto de tokens (modelo=%s, %d chars)",
                       modelo, len(resposta))
    await _logar("sucesso", resposta=resposta, finish_reason=finish_reason)
    return {"resposta": resposta}


async def _stream_llm(provedor: dict, payload: dict, *, usuario=None, modelo="", request=None):
    """Gera tokens SSE a partir do streaming do provedor ativo.

    Acumula a resposta para registrar a atividade (fire-and-forget) ao final,
    com sucesso (resposta completa) ou erro (motivo)."""
    acumulado: list[str] = []
    status_final = "sucesso"
    erro_final: Optional[str] = None
    finish_reason: Optional[str] = None
    completou = False  # vira True só quando o stream termina normalmente
    inicio = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{provedor['base_url']}/chat/completions",
                headers=prov.cabecalhos(provedor),
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    logger.warning("Stream do provedor de LLM respondeu %s", resp.status_code)
                    status_final, erro_final = "erro", f"http {resp.status_code}"
                    yield f"data: {json.dumps({'error': 'O tutor retornou um erro.'})}\n\n"
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        completou = True
                        yield "data: [DONE]\n\n"
                        return
                    try:
                        chunk = json.loads(data_str)
                        finish_reason = chunk["choices"][0].get("finish_reason") or finish_reason
                        delta = chunk["choices"][0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            acumulado.append(token)
                            yield f"data: {json.dumps({'token': token})}\n\n"
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                completou = True  # o stream terminou sem [DONE] explícito
    except httpx.TimeoutException:
        status_final, erro_final = "erro", "timeout"
        yield f"data: {json.dumps({'error': 'O tutor demorou demais para responder.'})}\n\n"
    except httpx.HTTPError as e:
        status_final, erro_final = "erro", f"rede: {type(e).__name__}"
        yield f"data: {json.dumps({'error': 'Não consegui falar com o tutor agora.'})}\n\n"
    finally:
        # Cliente desconectou no meio do stream (GeneratorExit): não foi sucesso.
        if status_final == "sucesso" and not completou:
            status_final, erro_final = "interrompido", "cliente desconectou"
        if usuario is not None:
            try:
                await registrar_atividade(
                    usuario,
                    "chat",
                    "resposta_tutor",
                    detalhes=_resumo_chat(
                        _ultima_msg_usuario(request) if request else "",
                        "".join(acumulado),
                        modelo,
                        getattr(request, "contexto", None),
                        stream=True,
                        finish_reason=finish_reason,
                    ),
                    duracao_ms=int((time.perf_counter() - inicio) * 1000),
                    status=status_final,
                    erro=erro_final,
                )
            except Exception:  # pragma: no cover - teardown defensivo
                pass


@router.post("/chat/stream")
async def chat_tutor_stream(request: ChatTutorRequest, usuario: dict = Depends(get_usuario_atual)):
    """Versao streaming (SSE) do chat tutor."""
    user_id = str(usuario.get("_id") or "anonymous")
    _check_rate_limit(user_id)

    provedor = await prov.provedor_vigente()
    if not provedor["api_key"]:
        raise HTTPException(
            status_code=503,
            detail=("O tutor por chat não está configurado no servidor "
                    f"({provedor['nome']} sem chave de API)."),
        )
    if not provedor["modelo"]:
        raise HTTPException(
            status_code=503,
            detail=f"Nenhum modelo escolhido para {provedor['nome']} (conf-tutor → LLM).",
        )
    modelo = provedor["modelo"]

    mensagens = [
        {"role": "system", "content": await _montar_system(request.contexto)},
    ]
    for m in request.mensagens:
        if m.role in ("user", "assistant") and m.content:
            mensagens.append({"role": m.role, "content": m.content})

    if len(mensagens) == 1:
        raise HTTPException(status_code=400, detail="Envie ao menos uma mensagem do usuário.")

    payload = {
        "model": modelo,
        "messages": mensagens,
        "temperature": TEMPERATURA,
        "max_tokens": max_tokens_resposta(request.contexto),
        "stream": True,
    }

    return StreamingResponse(
        _stream_llm(provedor, payload, usuario=usuario, modelo=modelo, request=request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================
# HISTÓRICO DE CONVERSAS
# ============================================================

def _serializar_hist(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    for campo in ("criado_em", "atualizado_em"):
        if isinstance(doc.get(campo), datetime):
            doc[campo] = doc[campo].isoformat()
    return doc


@router.get("/chat/historico", response_model=list[ChatHistoricoListItem])
async def listar_historico(
    pipeline_id: Optional[str] = Query(None),
    usuario=Depends(get_usuario_atual),
):
    filtro = {"usuario_id": str(usuario["_id"])}
    if pipeline_id:
        filtro["pipeline_id"] = pipeline_id
    cursor = historico_chat.find(filtro).sort("atualizado_em", -1).limit(50)
    resultados = []
    async for doc in cursor:
        resultados.append(ChatHistoricoListItem(**_serializar_hist(doc)))
    return resultados


@router.get("/chat/historico/{chat_id}", response_model=ChatHistoricoResponse)
async def obter_historico(chat_id: str, usuario=Depends(get_usuario_atual)):
    if not ObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="ID inválido.")
    doc = await historico_chat.find_one(
        {"_id": ObjectId(chat_id), "usuario_id": str(usuario["_id"])}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return ChatHistoricoResponse(**_serializar_hist(doc))


async def _autorizar_ver_aluno(usuario: dict, aluno_id: str) -> None:
    """LGPD (menores): além do papel, o professor só lê o chat de alunos das SUAS
    turmas. Admin vê qualquer aluno. Levanta 403 caso contrário."""
    if (usuario or {}).get("role") == "admin":
        return
    vinculo = await turmas.find_one({"professor_id": str(usuario["_id"]), "alunos": aluno_id})
    if not vinculo:
        raise HTTPException(status_code=403, detail="Aluno não pertence a nenhuma turma sua.")


@router.get("/chat/aluno/{aluno_id}/historico", response_model=list[ChatHistoricoListItem])
async def listar_historico_aluno(aluno_id: str, usuario=Depends(exigir_admin_ou_professor)):
    """Professor/admin lê as conversas de um aluno. LGPD (menores): acesso gated por
    papel + vínculo de turma e registrado na auditoria; use com parcimônia."""
    if not ObjectId.is_valid(aluno_id):
        raise HTTPException(status_code=400, detail="ID inválido.")
    await _autorizar_ver_aluno(usuario, aluno_id)
    await registrar_atividade(usuario, "auditoria", "leu_chats_aluno",
                              detalhes={"aluno_id": aluno_id})
    cursor = historico_chat.find({"usuario_id": aluno_id}).sort("atualizado_em", -1).limit(50)
    return [ChatHistoricoListItem(**_serializar_hist(d)) async for d in cursor]


@router.get("/chat/aluno/{aluno_id}/historico/{chat_id}", response_model=ChatHistoricoResponse)
async def obter_historico_aluno(aluno_id: str, chat_id: str, usuario=Depends(exigir_admin_ou_professor)):
    if not (ObjectId.is_valid(aluno_id) and ObjectId.is_valid(chat_id)):
        raise HTTPException(status_code=400, detail="ID inválido.")
    await _autorizar_ver_aluno(usuario, aluno_id)
    doc = await historico_chat.find_one({"_id": ObjectId(chat_id), "usuario_id": aluno_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    await registrar_atividade(usuario, "auditoria", "leu_chat_aluno",
                              detalhes={"aluno_id": aluno_id, "chat_id": chat_id})
    return ChatHistoricoResponse(**_serializar_hist(doc))


@router.post("/chat/historico", response_model=ChatHistoricoResponse)
async def criar_historico(
    pipeline_id: Optional[str] = None,
    titulo: str = "Nova conversa",
    usuario=Depends(get_usuario_atual),
):
    agora = datetime.now(timezone.utc)
    doc = {
        "usuario_id": str(usuario["_id"]),
        "pipeline_id": pipeline_id,
        "titulo": titulo,
        "mensagens": [],
        "criado_em": agora,
        "atualizado_em": agora,
    }
    result = await historico_chat.insert_one(doc)
    doc["_id"] = result.inserted_id
    return ChatHistoricoResponse(**_serializar_hist(doc))


@router.put("/chat/historico/{chat_id}")
async def atualizar_historico(
    chat_id: str,
    mensagens: list[ChatMensagem],
    titulo: Optional[str] = None,
    usuario=Depends(get_usuario_atual),
):
    if not ObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="ID inválido.")

    atualizacoes = {
        "mensagens": [m.model_dump() for m in mensagens],
        "atualizado_em": datetime.now(timezone.utc),
    }
    if titulo:
        atualizacoes["titulo"] = titulo

    result = await historico_chat.update_one(
        {"_id": ObjectId(chat_id), "usuario_id": str(usuario["_id"])},
        {"$set": atualizacoes},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"ok": True}


@router.delete("/chat/historico/{chat_id}")
async def deletar_historico(chat_id: str, usuario=Depends(get_usuario_atual)):
    if not ObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="ID inválido.")
    result = await historico_chat.delete_one(
        {"_id": ObjectId(chat_id), "usuario_id": str(usuario["_id"])}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"ok": True}
