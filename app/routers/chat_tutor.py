"""Chatbot tutor: proxy seguro para a API da NVIDIA (OpenAI-compatible).

A chave NVIDIA_API_KEY fica SOMENTE no backend (variavel de ambiente / .env, nao
versionada). O frontend nunca a recebe — fala apenas com este endpoint. O chatbot
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
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.database import historico_chat, configuracoes_tutor
from app.security import get_usuario_atual
from app.tutor_kb import bloco_kb
from app.schemas.chat import (
    ChatHistoricoListItem,
    ChatHistoricoResponse,
    ChatMensagem,
    ChatTutorRequest,
)

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

NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
# Default sane: um modelo de chat estável. O env e o config no banco têm prioridade.
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
# Limite defensivo para nao mandar um contexto gigante ao modelo.
MAX_CONTEXTO_CHARS = 8000


# ============================================================
# CONFIGURAÇÃO DO MODELO LLM
# ============================================================

@router.get("/modelos")
async def listar_modelos(usuario=Depends(get_usuario_atual)):
    """Lista os modelos LLM disponíveis na NVIDIA."""
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="NVIDIA_API_KEY não configurada no servidor.",
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{NVIDIA_BASE_URL}/models",
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout ao listar modelos.")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Erro ao conectar com a NVIDIA.")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Erro ao listar modelos da NVIDIA.")

    try:
        data = resp.json()
        modelos = [
            {"id": m["id"], "owned_by": m.get("owned_by", "")}
            for m in data.get("data", [])
        ]
    except (KeyError, ValueError):
        raise HTTPException(status_code=502, detail="Resposta inesperada ao listar modelos.")

    # Busca o modelo configurado atualmente
    config = await configuracoes_tutor.find_one({"chave": "llm_model"})
    modelo_atual = config.get("valor", NVIDIA_MODEL) if config else NVIDIA_MODEL

    return {"modelos": modelos, "modelo_atual": modelo_atual}


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


async def _testar_modelo(client: httpx.AsyncClient, api_key: str, model_id: str) -> dict:
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
            f"{NVIDIA_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
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


async def _rodar_health_check(api_key: str, modelos: list[str]):
    """Testa todos os modelos com concorrência limitada, preenchendo o cache à medida
    que cada um responde (a UI mostra o progresso)."""
    sem = asyncio.Semaphore(8)
    _saude_cache["total"] = len(modelos)
    _saude_cache["concluidos"] = 0
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            async def worker(mid: str):
                async with sem:
                    res = await _testar_modelo(client, api_key, mid)
                _saude_cache["resultados"][mid] = res
                _saude_cache["concluidos"] += 1
            await asyncio.gather(*(worker(m) for m in modelos), return_exceptions=True)
    finally:
        _saude_cache["atualizado_em"] = time.time()
        _saude_cache["em_andamento"] = False


@router.get("/modelos/saude")
async def saude_modelos(usuario=Depends(get_usuario_atual), forcar: bool = Query(False)):
    """Status de resposta de cada modelo LLM. Retorna o cache atual de imediato e
    dispara o teste em segundo plano quando o cache está velho (ou forcar=True)."""
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="NVIDIA_API_KEY não configurada no servidor.")

    fresco = (time.time() - _saude_cache["atualizado_em"]) < _SAUDE_TTL
    async with _saude_lock:
        if (forcar or not fresco) and not _saude_cache["em_andamento"]:
            ids: list[str] = []
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(
                        f"{NVIDIA_BASE_URL}/models",
                        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                    )
                if resp.status_code == 200:
                    ids = [m["id"] for m in resp.json().get("data", []) if m.get("id")]
            except Exception:
                ids = []
            if ids:
                _saude_cache["em_andamento"] = True
                if forcar:
                    _saude_cache["resultados"] = {}
                asyncio.create_task(_rodar_health_check(api_key, ids))

    return {
        "resultados": _saude_cache["resultados"],
        "atualizado_em": _saude_cache["atualizado_em"],
        "em_andamento": _saude_cache["em_andamento"],
        "total": _saude_cache["total"],
        "concluidos": _saude_cache["concluidos"],
    }


@router.get("/modelo")
async def obter_modelo(usuario=Depends(get_usuario_atual)):
    """Retorna o modelo LLM atualmente selecionado."""
    config = await configuracoes_tutor.find_one({"chave": "llm_model"})
    modelo = config.get("valor", NVIDIA_MODEL) if config else NVIDIA_MODEL
    return {"modelo": modelo}


@router.put("/modelo")
async def definir_modelo(body: dict, usuario=Depends(get_usuario_atual)):
    """Define o modelo LLM a ser utilizado pelo tutor."""
    if usuario.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admins podem alterar o modelo do tutor.")

    modelo = body.get("modelo")
    if not modelo or not isinstance(modelo, str):
        raise HTTPException(status_code=400, detail="Campo 'modelo' é obrigatório.")

    await configuracoes_tutor.update_one(
        {"chave": "llm_model"},
        {"$set": {"chave": "llm_model", "valor": modelo, "atualizado_por": str(usuario.get("_id", ""))}},
        upsert=True,
    )
    return {"modelo": modelo}

SYSTEM_PROMPT = (
    "Você é o tutor de Aprendizado de Máquina da plataforma Iana (H2IA Tutor). "
    "Seu público são estudantes do ensino fundamental e médio. "
    "Explique de forma clara, concreta e amigável, em português do Brasil, com exemplos do dia a dia. "
    "Use o CONTEXTO DO PIPELINE abaixo para responder sobre os modelos usados, os pré-processamentos, "
    "os dados, as métricas, os gráficos e o código Python gerado. "
    "Se a pergunta for sobre algo que não está no contexto, explique o conceito mesmo assim. "
    "Seja conciso: respostas curtas e diretas, sem jargão desnecessário. Nunca invente resultados numéricos "
    "que não estejam no contexto. "
    "Quando houver uma BASE DE CONHECIMENTO abaixo, use-a como fonte sobre os modelos e métricas do catálogo "
    "(nomes, para que servem, quando usar/evitar, hiperparâmetros e seus valores padrão, fórmulas); "
    "não invente hiperparâmetros nem valores padrão diferentes dos que estão lá."
)


def _montar_contexto(contexto) -> str:
    if not contexto:
        return "Nenhum pipeline carregado no momento."
    try:
        texto = json.dumps(contexto, ensure_ascii=False, indent=1, default=str)
    except Exception:
        texto = str(contexto)
    if len(texto) > MAX_CONTEXTO_CHARS:
        texto = texto[:MAX_CONTEXTO_CHARS] + "\n... (contexto truncado)"
    return texto


async def _montar_system(contexto) -> str:
    """System prompt + contexto do pipeline + base de conhecimento do catálogo."""
    partes = [
        SYSTEM_PROMPT,
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
async def chat_tutor(request: ChatTutorRequest, req: Request):
    # Rate limit: usa o token JWT como identificador
    user_id = req.state.user_id if hasattr(req.state, "user_id") else "anonymous"
    _check_rate_limit(user_id)

    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="O tutor por chat não está configurado no servidor (NVIDIA_API_KEY ausente).",
        )

    # Busca o modelo configurado
    config = await configuracoes_tutor.find_one({"chave": "llm_model"})
    modelo = config.get("valor", NVIDIA_MODEL) if config else NVIDIA_MODEL

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
        "temperature": 0.4,
        "max_tokens": 1024,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{NVIDIA_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                json=payload,
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="O tutor demorou demais para responder. Tente de novo.")
    except httpx.HTTPError as e:
        logger.warning("Falha de rede ao chamar NVIDIA: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="Não consegui falar com o tutor agora. Tente novamente.")

    if resp.status_code != 200:
        # Nao propagar corpo bruto do provedor (pode conter detalhes sensiveis).
        logger.warning("NVIDIA respondeu %s", resp.status_code)
        raise HTTPException(status_code=502, detail="O tutor retornou um erro. Tente novamente em instantes.")

    try:
        data = resp.json()
        resposta = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        raise HTTPException(status_code=502, detail="Resposta do tutor em formato inesperado.")

    return {"resposta": resposta}


async def _stream_nvidia(api_key: str, payload: dict):
    """Gera tokens SSE a partir do streaming da NVIDIA."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{NVIDIA_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    logger.warning("NVIDIA stream respondeu %s", resp.status_code)
                    yield f"data: {json.dumps({'error': 'O tutor retornou um erro.'})}\n\n"
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        yield "data: [DONE]\n\n"
                        return
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            yield f"data: {json.dumps({'token': token})}\n\n"
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
    except httpx.TimeoutException:
        yield f"data: {json.dumps({'error': 'O tutor demorou demais para responder.'})}\n\n"
    except httpx.HTTPError:
        yield f"data: {json.dumps({'error': 'Não consegui falar com o tutor agora.'})}\n\n"


@router.post("/chat/stream")
async def chat_tutor_stream(request: ChatTutorRequest, req: Request):
    """Versao streaming (SSE) do chat tutor."""
    user_id = req.state.user_id if hasattr(req.state, "user_id") else "anonymous"
    _check_rate_limit(user_id)

    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="O tutor por chat não está configurado no servidor (NVIDIA_API_KEY ausente).",
        )

    # Busca o modelo configurado
    config = await configuracoes_tutor.find_one({"chave": "llm_model"})
    modelo = config.get("valor", NVIDIA_MODEL) if config else NVIDIA_MODEL

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
        "temperature": 0.4,
        "max_tokens": 1024,
        "stream": True,
    }

    return StreamingResponse(
        _stream_nvidia(api_key, payload),
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
