import os

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError
from passlib.context import CryptContext

# Workaround para compatibilidade do passlib com bcrypt 4.0+ no Python 3.13
import passlib.handlers.bcrypt
passlib.handlers.bcrypt.detect_wrap_bug = lambda ident: False

from app.database import colecao_usuario

# Carrega o .env apenas em ambiente local
if os.getenv("RENDER") is None:
    load_dotenv()

# =========================
# CONFIGURAÇÕES JWT
# =========================
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

if not SECRET_KEY:
    raise RuntimeError(
        "A variável de ambiente 'SECRET_KEY' não foi definida."
    )

# =========================
# CONFIGURAÇÃO DE SENHAS
# =========================
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# =========================
# OAUTH2
# =========================
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="login"
)

# =========================
# FUNÇÕES DE SENHA
# =========================
def get_senha_hash(password: str) -> str:
    return pwd_context.hash(password)


def verificar_senha(
    plain_password: str,
    hashed_password: str
) -> bool:
    return pwd_context.verify(
        plain_password,
        hashed_password
    )

# =========================
# USUÁRIO AUTENTICADO
# =========================
async def get_usuario_atual(
    token: str = Depends(oauth2_scheme)
):
    print(f"[PRINT] get_usuario_atual called with token: {token[:20]}...")
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        print(f"[PRINT] JWT decoded successfully: {payload}")

        email: str | None = payload.get("sub")
        print(f"[PRINT] Email from token: {email}")

        if email is None:
            print("[PRINT] No email in token")
            raise credentials_exception

    except PyJWTError as e:
        print(f"[PRINT] JWT decode error: {e}")
        raise credentials_exception

    user_doc = await colecao_usuario.find_one(
        {"email": email}
    )
    print(f"[PRINT] User found: {user_doc is not None}")

    if user_doc is None:
        print("[PRINT] User not found in database")
        raise credentials_exception

    return user_doc