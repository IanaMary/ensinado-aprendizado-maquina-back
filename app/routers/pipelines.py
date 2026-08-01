from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import pipelines, turmas, atividades
from app.pipelines_evolucao import montar_evolucao, normalizar_nome_base
from app.schemas.pipelines import PipelineCreate, PipelineUpdate
from app.security import get_usuario_atual
from app.funcoes_genericas.validacao import validar_object_id

router = APIRouter(prefix="/pipelines", tags=["Pipelines"])


def _pode_publicar(usuario: dict) -> bool:
    """Só professor/admin publicam na galeria. Enforcement no servidor (o
    checkbox do front é só conveniência)."""
    return (usuario or {}).get("role") in ("professor", "admin")


async def _validar_vinculo_atividade(user_id: str, role: str, atividade_id, turma_id):
    """Valida que o usuário pode ligar a submissão à atividade/turma informadas.

    Impede um aluno de injetar sua submissão no ranking de uma turma da qual não
    participa. Retorna (atividade_id, turma_id) canônicos; a `turma_id` vem da
    própria atividade (não confia na informada pelo cliente). 403 se não for membro.
    """
    if not atividade_id and not turma_id:
        return None, None

    async def _e_membro(turma_id_alvo: str) -> bool:
        if role == "admin":
            return True
        oid = validar_object_id(turma_id_alvo, "turma_id")
        t = await turmas.find_one({"_id": oid})
        return bool(t and (t.get("professor_id") == user_id or user_id in t.get("alunos", [])))

    if atividade_id:
        aoid = validar_object_id(atividade_id, "atividade_id")
        a = await atividades.find_one({"_id": aoid})
        if not a:
            raise HTTPException(status_code=404, detail="Atividade não encontrada.")
        turma_real = a.get("turma_id")
        if not await _e_membro(turma_real):
            raise HTTPException(status_code=403, detail="Você não participa desta turma.")
        return atividade_id, turma_real

    if not await _e_membro(turma_id):
        raise HTTPException(status_code=403, detail="Você não participa desta turma.")
    return None, turma_id


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

    # Só professor/admin publicam; e a submissão só liga a atividades de turmas do usuário.
    is_public = bool(body.is_public) and _pode_publicar(current_user)
    atividade_id, turma_id = await _validar_vinculo_atividade(
        user_id, current_user.get("role"), body.atividade_id, body.turma_id)

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
        "is_public": is_public,
        "dificuldade": body.dificuldade,
        "tags": body.tags,
        "professor_id": body.professor_id,
        "atividade_id": atividade_id,
        "turma_id": turma_id,
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


@router.get("/evolucao")
async def evolucao_do_aluno(
    current_user: dict = Depends(get_usuario_atual),
    limite: int = Query(200, ge=1, le=500),
    dataset: List[str] = Query(default=[], description="Nomes candidatos da base (filtro)"),
    alvo: Optional[str] = Query(default=None, description="Coluna alvo (filtro)"),
):
    """Trajetória do usuário em cada base que ele já usou (mais recente primeiro).

    `dataset`/`alvo` filtram para a base de um pipeline que o cliente tem em mãos (pode
    estar aberto e ainda não salvo). O cliente manda os NOMES que conhece — nome do
    dataset, do arquivo, id — e quem decide a identidade é aqui, para a regra não viver
    duplicada nas duas pontas (foi o que fez o bloco de evolução não casar em 2026-07-26).

    Só lê os próprios pipelines — professor não vê os de aluno por aqui (para isso existe o
    ranking da atividade, escopado à turma). Projeção enxuta: `resultadoColetaDado` inteiro
    pode ser enorme, mas precisamos dele para identificar a base, então trazemos apenas os
    campos de identidade e divisão.
    """
    user_id = str(current_user["_id"])
    projecao = {
        "nome": 1, "dataCriacao": 1, "dataModificacao": 1, "atividade_id": 1,
        "modeloSelecionado": 1, "modelosSelecionados": 1, "preProcessamentoConfig": 1,
        "resultadosDasAvaliacoes": 1,
        "resultadoColetaDado.datasetId": 1, "resultadoColetaDado.nomeDataset": 1,
        "resultadoColetaDado.treino.nomeArquivo": 1, "resultadoColetaDado.target": 1,
        "resultadoColetaDado.preverCategoria": 1, "resultadoColetaDado.dadosRotulados": 1,
        "resultadoColetaDado.porcentagemTreino": 1,
    }
    cursor = pipelines.find({"user_id": user_id}, projecao).sort("dataCriacao", -1).limit(limite)
    docs = await cursor.to_list(length=limite)

    # Dentro de uma atividade vale a métrica escolhida pelo professor; fora dela, a padrão
    # da tarefa. Uma consulta só para todas as atividades citadas.
    criterios: dict = {}
    ids = {d.get("atividade_id") for d in docs if d.get("atividade_id")}
    oids = []
    for aid in ids:
        try:
            oids.append(ObjectId(aid))
        except Exception:
            continue
    if oids:
        try:
            async for a in atividades.find({"_id": {"$in": oids}}, {"criterio": 1}):
                if a.get("criterio"):
                    criterios[str(a["_id"])] = a["criterio"]
        except Exception:
            criterios = {}

    bases = await montar_evolucao(docs, criterios)
    if dataset or alvo:
        # Compara por nome normalizado: o mesmo dataset chega como "Iris" ou "Iris.xlsx"
        # dependendo da porta de entrada (ver `normalizar_nome_base`).
        candidatos = {normalizar_nome_base(d) for d in dataset if d}
        bases = [b for b in bases
                 if (not candidatos or normalizar_nome_base(b["dataset"]) in candidatos)
                 and (alvo is None or b["alvo"] == alvo)]
    return {"bases": bases}


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
    # Não herda o vínculo de atividade/turma do pipeline de origem (que pode ser
    # público, de outro professor): copiar um pipeline público carregava
    # atividade_id/turma_id/professor_id e registrava submissão numa turma/atividade
    # em que o aluno não está matriculado, driblando _validar_vinculo_atividade.
    for campo in ("atividade_id", "turma_id", "professor_id"):
        novo_doc.pop(campo, None)

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

    # is_public só por professor/admin (senão remove a flag do update, sem falhar).
    if "is_public" in update and update["is_public"] and not _pode_publicar(current_user):
        update["is_public"] = False
    # Vínculo com atividade/turma validado contra a participação do usuário.
    if "atividade_id" in update or "turma_id" in update:
        atividade_id, turma_id = await _validar_vinculo_atividade(
            user_id, current_user.get("role"), update.get("atividade_id"), update.get("turma_id"))
        if "atividade_id" in update:
            update["atividade_id"] = atividade_id
        update["turma_id"] = turma_id

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
