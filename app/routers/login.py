import os
import asyncio
import functools
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, status
from starlette.requests import Request

from app.database import colecao_usuario
from app.schemas.login import LoginRequest
from app.schemas.usuarios import UsuarioResponse
from app.security import verificar_senha, SECRET_KEY, ALGORITHM

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
import threading
_request_log = defaultdict(list)
_log_lock = threading.Lock()

async def rate_limit(request: Request):
    """
    Limita para 20 requisições por minuto por IP.
    """
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    with _log_lock:
        # Limpa registros antigos (> 60 segundos)
        _request_log[client_ip] = [t for t in _request_log[client_ip] if now - t < 60]
        
        # Verifica limite
        if len(_request_log[client_ip]) >= 20:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Muitas tentativas de login. Tente novamente em 1 minuto."
            )
        
        # Registra a requisição
        _request_log[client_ip].append(now)

# =========================
# ROUTER
# =========================
router = APIRouter()

# =========================
# LOGIN
# =========================
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

    # Registra o último acesso (exibido em "Gerenciar Usuários").
    agora = datetime.now(timezone.utc)
    await colecao_usuario.update_one(
        {"_id": usuario["_id"]},
        {"$set": {"ultimo_acesso": agora}}
    )
    usuario["ultimo_acesso"] = agora

    expira = datetime.now(
        timezone.utc
    ) + timedelta(
        minutes=TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": request.email,
        "exp": expira
    }

    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    usuario["_id"] = str(usuario["_id"])

    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": UsuarioResponse(**usuario)
    }