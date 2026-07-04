from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

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
        "mediaMetricas": p.get("mediaMetricas", "weighted"),
        "preProcessamentoConfig": p.get("preProcessamentoConfig"),
        "resultadoTreinamento": p.get("resultadoTreinamento"),
        "resultadosDasAvaliacoes": p.get("resultadosDasAvaliacoes"),
        "dataCriacao": p.get("dataCriacao"),
        "dataModificacao": p.get("dataModificacao"),
        "status": p.get("status", "rascunho"),
        "is_public": p.get("is_public", False),
        "dificuldade": p.get("dificuldade", "iniciante"),
        "tags": p.get("tags", []),
        "professor_id": p.get("professor_id"),
        "atividade_id": p.get("atividade_id"),
        "turma_id": p.get("turma_id"),
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
        "mediaMetricas": body.mediaMetricas or "weighted",
        "preProcessamentoConfig": body.preProcessamentoConfig,
        "resultadoTreinamento": body.resultadoTreinamento,
        "resultadosDasAvaliacoes": body.resultadosDasAvaliacoes,
        "status": body.status or "rascunho",
        "is_public": body.is_public,
        "dificuldade": body.dificuldade,
        "tags": body.tags,
        "professor_id": body.professor_id,
        "atividade_id": body.atividade_id,
        "turma_id": body.turma_id,
        "dataCriacao": agora,
        "dataModificacao": agora,
    }
    result = await pipelines.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _pipeline_doc(doc)


@router.get("/")
async def listar_pipelines(
    current_user: dict = Depends(get_usuario_atual),
    limite: int = Query(200, ge=1, le=200),
    pagina: int = Query(1, ge=1),
):
    user_id = str(current_user["_id"])
    skip = (pagina - 1) * limite
    cursor = (
        pipelines.find({"user_id": user_id})
        .sort("dataModificacao", -1)
        .skip(skip)
        .limit(limite)
    )
    docs = await cursor.to_list(length=limite)
    return [_pipeline_doc(d) for d in docs]


@router.get("/galeria")
async def listar_galeria():
    cursor = pipelines.find({"is_public": True}).sort("dataModificacao", -1)
    docs = await cursor.to_list(length=100)
    return [_pipeline_doc(d) for d in docs]


@router.post("/{pipeline_id}/copiar")
async def copiar_pipeline(
    pipeline_id: str,
    current_user: dict = Depends(get_usuario_atual),
):
    user_id = str(current_user["_id"])
    try:
        oid = ObjectId(pipeline_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de pipeline inválido")

    original = await pipelines.find_one({"_id": oid})
    if not original:
        raise HTTPException(status_code=404, detail="Pipeline original não encontrado")
    if original.get("user_id") != user_id and not original.get("is_public", False):
        raise HTTPException(status_code=404, detail="Pipeline original não encontrado")

    agora = datetime.now(timezone.utc)
    novo_doc = original.copy()
    del novo_doc["_id"]
    novo_doc["user_id"] = user_id
    novo_doc["nome"] = f"Cópia de {original.get('nome')}"
    novo_doc["status"] = "rascunho"
    novo_doc["is_public"] = False
    novo_doc["dataCriacao"] = agora
    novo_doc["dataModificacao"] = agora

    result = await pipelines.insert_one(novo_doc)
    novo_doc["_id"] = result.inserted_id
    return _pipeline_doc(novo_doc)


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
