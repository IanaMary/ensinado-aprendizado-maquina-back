import os
from contextvars import ContextVar
from typing import Optional

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

        email: str | None = payload.get("sub")

        if email is None:
            raise credentials_exception

    except PyJWTError:
        raise credentials_exception

    user_doc = await colecao_usuario.find_one(
        {"email": email}
    )

    if user_doc is None:
        raise credentials_exception

    return user_doc


# =========================
# USUÁRIO ATUAL POR REQUEST (ContextVar)
# =========================
# Disponibiliza o usuário autenticado para código fora da assinatura do handler
# (ex.: treinar_modelo_generico, chamado pelos 24 routers de modelo) sem ter que
# propagar `Depends` em todos eles. Starlette roda cada request em seu próprio
# contexto, então o valor é isolado por requisição.
usuario_atual_ctx: ContextVar[Optional[dict]] = ContextVar("usuario_atual", default=None)


async def definir_usuario_atual(usuario: dict = Depends(get_usuario_atual)) -> dict:
    """Autentica (como get_usuario_atual) e ainda publica o usuário no ContextVar."""
    usuario_atual_ctx.set(usuario)
    return usuario


# =========================
# AUTORIZAÇÃO POR PAPEL
# =========================
async def exigir_admin_ou_professor(
    usuario: dict = Depends(get_usuario_atual)
) -> dict:
    """Restringe a rota a admin/professor (escrita de catálogo/tutor, telemetria etc.).
    Os GETs abertos seguem usando apenas `get_usuario_atual`."""
    if (usuario or {}).get("role") not in ("admin", "professor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores e professores.",
        )
    return usuario
