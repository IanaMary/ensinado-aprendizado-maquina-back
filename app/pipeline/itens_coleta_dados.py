from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import APIRouter
from typing import List
from pydantic import BaseModel
from typing import Literal

router = APIRouter()
client = AsyncIOMotorClient("mongodb://localhost:27017")
db = client["meubanco"]
colecao = db["itens"]

class Item(BaseModel):
    label: str
    tipoItem: str = "coleta-dado"
    habilitado: bool = True
    movido: bool = False

@router.post("/itens_coleta_dados/multiplos")
async def itens_coleta_dados(itens: List[Item]):
    documentos = [item.dict() for item in itens]
    resultado = await colecao.insert_many(documentos)
    return {"ids_inseridos": resultado.inserted_ids}
