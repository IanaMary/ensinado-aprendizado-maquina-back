"""Chatbot tutor: proxy seguro para a API da NVIDIA (OpenAI-compatible).

A chave NVIDIA_API_KEY fica SOMENTE no backend (variavel de ambiente / .env, nao
versionada). O frontend nunca a recebe — fala apenas com este endpoint. O chatbot
recebe o contexto do pipeline carregado (dataset, modelo, hiperparametros, metricas,
graficos, codigo Python gerado) e responde de forma pedagogica, em PT-BR, para alunos.
"""
import json
import logging
import os

import httpx
from fastapi import APIRouter, HTTPException

from app.schemas.chat import ChatTutorRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tutor", tags=["Tutor"])

NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "minimaxai/minimax-m3")
# Limite defensivo para nao mandar um contexto gigante ao modelo.
MAX_CONTEXTO_CHARS = 8000

SYSTEM_PROMPT = (
    "Você é o tutor de Aprendizado de Máquina da plataforma Iana (H2IA Tutor). "
    "Seu público são estudantes do ensino fundamental e médio. "
    "Explique de forma clara, concreta e amigável, em português do Brasil, com exemplos do dia a dia. "
    "Use o CONTEXTO DO PIPELINE abaixo para responder sobre os modelos usados, os pré-processamentos, "
    "os dados, as métricas, os gráficos e o código Python gerado. "
    "Se a pergunta for sobre algo que não está no contexto, explique o conceito mesmo assim. "
    "Seja conciso: respostas curtas e diretas, sem jargão desnecessário. Nunca invente resultados numéricos "
    "que não estejam no contexto."
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


@router.post("/chat")
async def chat_tutor(request: ChatTutorRequest):
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="O tutor por chat não está configurado no servidor (NVIDIA_API_KEY ausente).",
        )

    contexto_txt = _montar_contexto(request.contexto)
    mensagens = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n=== CONTEXTO DO PIPELINE ===\n" + contexto_txt},
    ]
    for m in request.mensagens:
        if m.role in ("user", "assistant") and m.content:
            mensagens.append({"role": m.role, "content": m.content})

    if len(mensagens) == 1:
        raise HTTPException(status_code=400, detail="Envie ao menos uma mensagem do usuário.")

    payload = {
        "model": NVIDIA_MODEL,
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
