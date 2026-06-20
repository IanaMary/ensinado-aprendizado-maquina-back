"""Cria (ou atualiza) um usuário admin para login no ambiente Docker.

Uso dentro do container:
    docker compose exec backend python scripts/docker/criar_admin.py
Variáveis opcionais: ADMIN_EMAIL, ADMIN_SENHA, ADMIN_NOME.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

# Permite rodar como `python scripts/docker/criar_admin.py` (adiciona a raiz do app ao path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.database import colecao_usuario
from app.security import get_senha_hash


async def main():
    email = os.getenv("ADMIN_EMAIL", "admin@iana.local")
    senha = os.getenv("ADMIN_SENHA", "admin123")
    nome = os.getenv("ADMIN_NOME", "Admin")
    doc = {
        "nome_usuario": nome,
        "email": email,
        "instituicao_ensino": "Docker",
        "senha": get_senha_hash(senha),
        "role": "admin",
        "status": "ativo",
        "criado_em": datetime.now(timezone.utc),
    }
    await colecao_usuario.update_one({"email": email}, {"$set": doc}, upsert=True)
    print(f"Admin pronto -> login: {email} | senha: {senha}")


if __name__ == "__main__":
    asyncio.run(main())
