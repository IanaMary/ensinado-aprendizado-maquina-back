from typing import List, OrderedDict
from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from bson import ObjectId
from app.schemas.conf_pipeline import ItemColeta, ItemColetaOut
from app.database import opcoes_coletas, opcoes_modelos, opcoes_metricas

router = APIRouter(prefix="/conf_pipeline", tags=["Configuração Pipeline"])


class HabilitadoPayload(BaseModel):
  habilitado: bool


async def _patch_habilitado(colecao, item_id: str, habilitado: bool):
  if not ObjectId.is_valid(item_id):
    raise HTTPException(status_code=400, detail="ID inválido")
  resultado = await colecao.update_one(
    {"_id": ObjectId(item_id)},
    {"$set": {"habilitado": habilitado}}
  )
  if resultado.matched_count == 0:
    raise HTTPException(status_code=404, detail="Item não encontrado")
  return {"id": item_id, "habilitado": habilitado}


@router.patch("/coleta_dados/{item_id}/habilitado")
async def patch_coleta_habilitado(item_id: str, payload: HabilitadoPayload):
  return await _patch_habilitado(opcoes_coletas, item_id, payload.habilitado)


@router.patch("/modelos/{item_id}/habilitado")
async def patch_modelo_habilitado(item_id: str, payload: HabilitadoPayload):
  return await _patch_habilitado(opcoes_modelos, item_id, payload.habilitado)


@router.patch("/metricas/{item_id}/habilitado")
async def patch_metrica_habilitado(item_id: str, payload: HabilitadoPayload):
  return await _patch_habilitado(opcoes_metricas, item_id, payload.habilitado)

@router.post("/itens_coleta_dados/multiplos")
async def itens_coleta_dados(itens: List[ItemColeta]):
  documentos = [item.model_dump() for item in itens]
  resultado = await opcoes_coletas.insert_many(documentos)
  return {"ids_inseridos": [str(_id) for _id in resultado.inserted_ids]}

@router.get("/coleta_dados/todos", response_model=List)
async def get_all_coleta(
    limite: int = Query(10, ge=1, le=100),
    pagina: int = Query(1, ge=1),
    ordenar: Optional[str] = Query(None, description="Campo para ordenar, ex: 'label', 'tipoItem'"),
    direcao: Optional[str] = Query("asc", pattern="^(asc|desc)$", description="Direção da ordenação: 'asc' ou 'desc'")
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
    {
      **{k: v for k, v in doc.items() if k != "_id"},
      "id": str(doc["_id"]),
      "habilitado": doc.get("habilitado", True),
    }
    for doc in documentos
  ]

@router.get("/modelos/todos", response_model=List)
async def get_all_modelos(
    limite: int = Query(10, ge=1, le=100),
    pagina: int = Query(1, ge=1),
    ordenar: Optional[str] = Query(None, description="Campo para ordenar, ex: 'label', 'tipoItem'"),
    direcao: Optional[str] = Query("asc", pattern="^(asc|desc)$", description="Direção da ordenação: 'asc' ou 'desc'"),
    prever_categoria: Optional[bool] = Query(None, description=""),
    dados_rotulados: Optional[bool] = Query(None, description="")
):
  skip = (pagina - 1) * limite

  campo_ordenacao = ordenar if ordenar else "label"
  direcao_ordenacao = 1 if direcao == "asc" else -1
  

  filtro = {}
  if prever_categoria is not None:
    filtro["prever_categoria"] = prever_categoria
  if dados_rotulados is not None:
    filtro["dados_rotulados"] = dados_rotulados

  cursor = (
    opcoes_modelos.find(filtro)
    .sort(campo_ordenacao, direcao_ordenacao)
    .collation({"locale": "en", "strength": 1})
    .skip(skip)
    .limit(limite)
  )
  documentos = await cursor.to_list(length=limite)


  return [
    {
      **{k: v for k, v in doc.items() if k not in ["_id", "prever_categoria", "dados_rotulados"]},
      "id": str(doc["_id"]),
      "preverCategoria": doc["prever_categoria"],
      "dadosRotulados": doc["dados_rotulados"],
      "habilitado": doc.get("habilitado", True),
    }

    for doc in documentos
  ]
  
@router.get("/metricas/todos", response_model=List)
async def get_all_metricas(
    limite: int = Query(10, ge=1, le=100),
    pagina: int = Query(1, ge=1),
    ordenar: Optional[str] = Query(None, description="Campo para ordenar, ex: 'label', 'tipoItem'"),
    direcao: Optional[str] = Query("asc", pattern="^(asc|desc)$", description="Direção da ordenação: 'asc' ou 'desc'")
):
  skip = (pagina - 1) * limite

  campo_ordenacao = ordenar if ordenar else "label"
  direcao_ordenacao = 1 if direcao == "asc" else -1

  cursor = (
    opcoes_metricas.find()
    .sort(campo_ordenacao, direcao_ordenacao)
    .skip(skip)
    .limit(limite)
  )
  documentos = await cursor.to_list(length=limite)

  return [
    {
      **{k: v for k, v in doc.items() if k != "_id"},
      "id": str(doc["_id"]),
      "marcado": False,
      "habilitado": doc.get("habilitado", True),
    }
    for doc in documentos
  ]