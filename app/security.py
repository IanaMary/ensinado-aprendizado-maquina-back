import os
from dotenv import load_dotenv

from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
import jwt  # pyjwt
from jwt import PyJWTError

from app.database import colecao_usuario
from app.usuario.schemas.usuarios import UserOut  # ou seu schema de usuário

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def get_senha_hash(password: str) -> str:
  return pwd_context.hash(password)

def verificar_senha(plain_password: str, hashed_password: str) -> bool:
  return pwd_context.verify(plain_password, hashed_password)

async def get_usuario_atual(token: str = Depends(oauth2_scheme)):
  credentials_exception = HTTPException(
    status_code=401,
    detail="Não foi possível validar as credenciais",
    headers={"WWW-Authenticate": "Bearer"},
  )
  try:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    email: str = payload.get("sub")
    if email is None:
        raise credentials_exception
  except PyJWTError:
    raise credentials_exception

  user_doc = await colecao_usuario.find_one({"email": email})
  if user_doc is None:
    raise credentials_exception

  return user_doc
