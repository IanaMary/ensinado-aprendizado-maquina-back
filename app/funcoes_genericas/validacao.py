import re

from bson.objectid import ObjectId
from fastapi import HTTPException

HEX_24 = re.compile(r"^[0-9a-fA-F]{24}$")

# Limite do conteúdo base64 aceito para treino/avaliação (~50 MB)
MAX_ARQUIVO_BASE64 = 50 * 1024 * 1024


def validar_object_id(valor: str, nome_campo: str = "id") -> ObjectId:
    """Valida e converte uma string em ObjectId, retornando 400 em vez de 500 quando inválida."""
    if not valor or not isinstance(valor, str) or not HEX_24.match(valor):
        raise HTTPException(
            status_code=400,
            detail=f"Identificador inválido para '{nome_campo}'. É necessário um ObjectId de 24 caracteres hexadecimais."
        )
    return ObjectId(valor)
