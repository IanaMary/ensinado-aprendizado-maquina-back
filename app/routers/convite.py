from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import secrets
import os
from dotenv import load_dotenv

load_dotenv()

from app.schemas.usuarios import UserActivate
from app.security import get_senha_hash
from app.database import colecao_usuario

router = APIRouter(prefix="/convite", tags=["Convite"])


@router.get("/{token}")
async def verificar_convite(token: str):
    """Verifica se um token de convite é válido."""
    user = await colecao_usuario.find_one({
        "token_convite": token,
        "status": "pendente"
    })
    
    if not user:
        raise HTTPException(status_code=404, detail="Convite não encontrado ou já utilizado")
    
    # Verificar se o convite expirou (7 dias)
    data_convite = user.get("data_convite")
    if data_convite:
        # Make both timezone-aware or both naive
        if data_convite.tzinfo is None:
            data_convite = data_convite.replace(tzinfo=timezone.utc)
        dias_desde_convite = (datetime.now(timezone.utc) - data_convite).days
        if dias_desde_convite > 7:
            raise HTTPException(status_code=400, detail="Convite expirado")
    
    return {
        "nome": user["nome_usuario"],
        "email": user["email"],
        "tipo": user["role"],
        "valido": True
    }


@router.post("/{token}/ativar")
async def ativar_conta(token: str, dados: UserActivate):
    """Ativa a conta do usuário definindo a senha."""
    user = await colecao_usuario.find_one({
        "token_convite": token,
        "status": "pendente"
    })
    
    if not user:
        raise HTTPException(status_code=404, detail="Convite não encontrado ou já utilizado")
    
    # Verificar se o convite expirou (7 dias)
    data_convite = user.get("data_convite")
    if data_convite:
        # Make both timezone-aware or both naive
        if data_convite.tzinfo is None:
            data_convite = data_convite.replace(tzinfo=timezone.utc)
        dias_desde_convite = (datetime.now(timezone.utc) - data_convite).days
        if dias_desde_convite > 7:
            raise HTTPException(status_code=400, detail="Convite expirado")
    
    # Validar senhas
    if dados.senha != dados.confirmar_senha:
        raise HTTPException(status_code=400, detail="As senhas não coincidem")
    
    if len(dados.senha) < 6:
        raise HTTPException(status_code=400, detail="A senha deve ter pelo menos 6 caracteres")
    
    # Definir senha e ativar conta
    senha_hash = get_senha_hash(dados.senha)
    
    await colecao_usuario.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "senha": senha_hash,
                "status": "ativo",
                "data_ativacao": datetime.now(timezone.utc),
                "token_convite": None  # Invalidar token
            }
        }
    )
    
    return {"mensagem": "Conta ativada com sucesso", "email": user["email"]}
