from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta, datetime
import jwt  # pyjwt
import os

from app.database import colecao_usuario
from app.security import verificar_senha  
from app.usuario.schemas.login import LoginRequest
from app.usuario.schemas.usuarios import UsuarioResponse

from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", 60))

router = APIRouter()

@router.post("/login")
async def login(request: LoginRequest):
  usuario = await colecao_usuario.find_one({"email": request.email})
  if not usuario:
    raise HTTPException(status_code=401, detail="Credenciais inválidas")

  if not verificar_senha(request.senha, usuario["senha"]):
    raise HTTPException(status_code=401, detail="Credenciais inválidas")

  expira = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
  payload = {"sub": request.email, "exp": expira}
  token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

  usuario["_id"] = str(usuario["_id"])

  return {
    "access_token": token,
    "token_type": "bearer",
    "usuario": UsuarioResponse(**usuario)
  }

