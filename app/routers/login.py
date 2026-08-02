import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from starlette.requests import Request

from app.database import colecao_usuario
from app.schemas.login import LoginRequest
from app.schemas.usuarios import UsuarioResponse
from app.security import verificar_senha, get_usuario_atual, SECRET_KEY, ALGORITHM

# Carrega o .env apenas em ambiente local
if os.getenv("RENDER") is None:
    load_dotenv()

# =========================
# CONFIGURAÇÕES JWT
# =========================
TOKEN_EXPIRE_MINUTES = int(
    os.getenv("TOKEN_EXPIRE_MINUTES", 60)
)

# =========================
# RATE LIMITING (Simples, em memória)
# =========================
# Estado por processo: cada worker uvicorn mantém sua própria contagem.
# Atrás de múltiplos workers o limite efetivo é multiplicado pelo número de
# workers; para um limite global use um backend compartilhado (ex.: Redis).
# Não há lock: a seção crítica abaixo não tem await, então roda de forma
# atômica dentro do event loop de um worker.
_request_log = defaultdict(list)


async def rate_limit(request: Request):
    """
    Limita para 20 requisições por minuto por IP.
    """
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    # Limpa registros antigos (> 60 segundos). Usa .get para não criar
    # uma entrada vazia só por consultar um IP novo.
    recentes = [t for t in _request_log.get(client_ip, []) if now - t < 60]

    # Verifica limite
    if len(recentes) >= 20:
        _request_log[client_ip] = recentes
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas de login. Tente novamente em 1 minuto."
        )

    # Registra a requisição
    recentes.append(now)
    _request_log[client_ip] = recentes

# =========================
# ROUTER
# =========================
router = APIRouter()

# =========================
# LOGIN
# =========================
def _emitir_token(email: str) -> str:
    """Assina um JWT com a validade padrão. Fonte única da regra de expiração — o `/renovar`
    precisa emitir exatamente como o login."""
    expira = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": email, "exp": expira}, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/login/renovar")
async def renovar_token(usuario: dict = Depends(get_usuario_atual)):
    """Estende a sessão de quem está usando o sistema.

    O token não era renovado: o aluno era deslogado no meio de uma atividade, sem aviso
    (apontado pela banca, Imagem 10). Com isto o front renova enquanto há interação, e a sessão
    só cai depois de inatividade de verdade.

    NÃO é um refresh token: exige um access token AINDA válido, então não amplia a janela de um
    token vazado — só evita a queda de quem está ativo.
    """
    email = usuario.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Sessão inválida.")
    return {"access_token": _emitir_token(email), "token_type": "bearer"}


@router.post("/login")
async def login(request: LoginRequest, req: Request):
    # Rate limiting
    await rate_limit(req)

    usuario = await colecao_usuario.find_one(
        {"email": request.email}
    )

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas."
        )

    senha_valida = verificar_senha(
        request.senha,
        usuario["senha"]
    )

    if not senha_valida:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas."
        )

    # Só contas ativas entram: antes o login ignorava `status`, então uma conta
    # marcada como 'inativo' no painel (ou 'pendente', ainda não ativada) continuava
    # autenticando — inclusive as contas de demonstração da banca. Contas legadas
    # sem o campo assumem 'ativo'. Mesma mensagem genérica (sem enumeração).
    if usuario.get("status", "ativo") != "ativo":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas."
        )

    # Registra o último acesso (exibido em "Gerenciar Usuários").
    agora = datetime.now(timezone.utc)
    await colecao_usuario.update_one(
        {"_id": usuario["_id"]},
        {"$set": {"ultimo_acesso": agora}}
    )
    usuario["ultimo_acesso"] = agora

    token = _emitir_token(request.email)

    usuario["_id"] = str(usuario["_id"])

    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": UsuarioResponse(**usuario)
    }