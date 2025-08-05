from typing import List
from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime
from typing import List, Optional
from app.usuario.schemas.conf_pipeline import ItemColeta, ItemColetaOut
from app.database import opcoes_coletas

router = APIRouter(prefix="/conf_pipeline", tags=["Configuração Pipeline"])

@router.post("/itens_coleta_dados/multiplos")
async def itens_coleta_dados(itens: List[ItemColeta]):
  documentos = [item.dict() for item in itens]
  resultado = await opcoes_coletas.insert_many(documentos)
  return {"ids_inseridos": [str(_id) for _id in resultado.inserted_ids]}

@router.get("/itens_coleta_dados/todos", response_model=List[ItemColetaOut])
async def get_all_itens_coleta(
    limite: int = Query(10, ge=1, le=100),
    pagina: int = Query(1, ge=1),
    ordenar: Optional[str] = Query(None, description="Campo para ordenar, ex: 'label', 'tipoItem'"),
    direcao: Optional[str] = Query("asc", regex="^(asc|desc)$", description="Direção da ordenação: 'asc' ou 'desc'")
):
  skip = (pagina - 1) * limite

  campo_ordenacao = ordenar if ordenar else "label"
  direcao_ordenacao = 1 if direcao == "asc" else -1

  cursor = (
    opcoes_coletas.find()
    .sort(campo_ordenacao, direcao_ordenacao)
    .skip(skip)
    .limit(limite)
  )
  documentos = await cursor.to_list(length=limite)

  return [
    ItemColetaOut(
      id=str(doc["_id"]),
      label=doc.get("label", ""),
      tipoItem=doc.get("tipoItem", "coleta-dado"),
      habilitado=doc.get("habilitado", True),
      movido=doc.get("movido", False),
    )
    for doc in documentos
  ]