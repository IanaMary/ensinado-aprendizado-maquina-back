from typing import List, OrderedDict
from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime
from typing import List, Optional
from app.schemas.conf_pipeline import ItemColeta, ItemColetaOut
from app.database import opcoes_coletas, opcoes_modelos, opcoes_metricas

router = APIRouter(prefix="/conf_pipeline", tags=["Configuração Pipeline"])

@router.post("/itens_coleta_dados/multiplos")
async def itens_coleta_dados(itens: List[ItemColeta]):
  documentos = [item.dict() for item in itens]
  resultado = await opcoes_coletas.insert_many(documentos)
  return {"ids_inseridos": [str(_id) for _id in resultado.inserted_ids]}

@router.get("/coleta_dados/todos", response_model=List)
async def get_all_coleta(
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
    {
      **{k: v for k, v in doc.items() if k != "_id"},
      "id": str(doc["_id"])
    }
    for doc in documentos
  ]
  
@router.get("/modelos/todos", response_model=List)
async def get_all_modelos(
    limite: int = Query(10, ge=1, le=100),
    pagina: int = Query(1, ge=1),
    ordenar: Optional[str] = Query(None, description="Campo para ordenar, ex: 'label', 'tipoItem'"),
    direcao: Optional[str] = Query("asc", regex="^(asc|desc)$", description="Direção da ordenação: 'asc' ou 'desc'"),
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
      "dadosRotulados": doc["dados_rotulados"]
    }
    
    for doc in documentos
  ]
  
@router.get("/metricas/todos", response_model=List)
async def get_all_modelos(
    limite: int = Query(10, ge=1, le=100),
    pagina: int = Query(1, ge=1),
    ordenar: Optional[str] = Query(None, description="Campo para ordenar, ex: 'label', 'tipoItem'"),
    direcao: Optional[str] = Query("asc", regex="^(asc|desc)$", description="Direção da ordenação: 'asc' ou 'desc'")
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
    }
    for doc in documentos
  ]