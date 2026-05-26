import os
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, status

from app.database import colecao_usuario
from app.schemas.login import LoginRequest
from app.schemas.usuarios import UsuarioResponse
from app.security import verificar_senha

# Carrega o .env apenas em ambiente local
if os.getenv("RENDER") is None:
    load_dotenv()

# =========================
# CONFIGURAÇÕES JWT
# =========================
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

TOKEN_EXPIRE_MINUTES = int(
    os.getenv("TOKEN_EXPIRE_MINUTES", 60)
)

if not SECRET_KEY:
    raise RuntimeError(
        "A variável de ambiente 'SECRET_KEY' não foi definida."
    )

# =========================
# ROUTER
# =========================
router = APIRouter()

# =========================
# LOGIN
# =========================
@router.post("/login")
async def login(request: LoginRequest):

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