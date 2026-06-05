from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.database import pipelines
from app.schemas.pipelines import PipelineCreate, PipelineUpdate
from app.security import get_usuario_atual

router = APIRouter(prefix="/pipelines", tags=["Pipelines"])


def _pipeline_doc(p: dict) -> dict:
    return {
        "id": str(p["_id"]),
        "nome": p.get("nome"),
        "descricao": p.get("descricao"),
        "resultadoColetaDado": p.get("resultadoColetaDado"),
        "modeloSelecionado": p.get("modeloSelecionado"),
        "metricasSelecionadas": p.get("metricasSelecionadas"),
        "preProcessamentoConfig": p.get("preProcessamentoConfig"),
        "resultadoTreinamento": p.get("resultadoTreinamento"),
        "resultadosDasAvaliacoes": p.get("resultadosDasAvaliacoes"),
        "dataCriacao": p.get("dataCriacao"),
        "dataModificacao": p.get("dataModificacao"),
        "status": p.get("status", "rascunho"),
    }


@router.post("/")
async def criar_pipeline(
    body: PipelineCreate,
    current_user: dict = Depends(get_usuario_atual),
):
    user_id = str(current_user["_id"])
    agora = datetime.now(timezone.utc)

    doc = {
        "user_id": user_id,
        "nome": body.nome,
        "descricao": body.descricao,
        "resultadoColetaDado": body.resultadoColetaDado,
        "modeloSelecionado": body.modeloSelecionado,
        "metricasSelecionadas": body.metricasSelecionadas,
        "preProcessamentoConfig": body.preProcessamentoConfig,
        "resultadoTreinamento": body.resultadoTreinamento,
        "resultadosDasAvaliacoes": body.resultadosDasAvaliacoes,
        "status": body.status or "rascunho",
        "dataCriacao": agora,
        "dataModificacao": agora,
    }
    result = await pipelines.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _pipeline_doc(doc)


@router.get("/")
async def listar_pipelines(
    current_user: dict = Depends(get_usuario_atual),
):
    user_id = str(current_user["_id"])
    cursor = pipelines.find({"user_id": user_id}).sort("dataModificacao", -1)
    docs = await cursor.to_list(length=200)
    return [_pipeline_doc(d) for d in docs]


@router.get("/galeria")
async def listar_galeria():
    return []


@router.get("/{pipeline_id}")
async def obter_pipeline(
    pipeline_id: str,
    current_user: dict = Depends(get_usuario_atual),
):
    user_id = str(current_user["_id"])
    try:
        oid = ObjectId(pipeline_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de pipeline inválido")

    doc = await pipelines.find_one({"_id": oid, "user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Pipeline não encontrado")
    return _pipeline_doc(doc)


@router.put("/{pipeline_id}")
async def atualizar_pipeline(
    pipeline_id: str,
    body: PipelineUpdate,
    current_user: dict = Depends(get_usuario_atual),
):
    user_id = str(current_user["_id"])
    try:
        oid = ObjectId(pipeline_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de pipeline inválido")

    update = body.model_dump(exclude_none=True)
    if not update:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    update["dataModificacao"] = datetime.now(timezone.utc)

    result = await pipelines.update_one(
        {"_id": oid, "user_id": user_id},
        {"$set": update},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pipeline não encontrado")

    doc = await pipelines.find_one({"_id": oid})
    return _pipeline_doc(doc)


@router.delete("/{pipeline_id}")
async def excluir_pipeline(
    pipeline_id: str,
    current_user: dict = Depends(get_usuario_atual),
):
    user_id = str(current_user["_id"])
    try:
        oid = ObjectId(pipeline_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de pipeline inválido")

    result = await pipelines.delete_one({"_id": oid, "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Pipeline não encontrado")

    return {"mensagem": "Pipeline excluído com sucesso"}