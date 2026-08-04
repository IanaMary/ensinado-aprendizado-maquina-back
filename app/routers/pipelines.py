from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import pipelines, turmas, atividades
from app.pipelines_evolucao import montar_evolucao, normalizar_nome_base
from app.schemas.pipelines import PipelineCreate, PipelineUpdate
from app.security import get_usuario_atual, id_usuario_atual
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


async def _turmas_do_usuario(user_id: str) -> dict:
    """`{turma_id: {"nome", "professor_id"}}` das turmas do usuário — onde ele é aluno OU professor.

    **Difere de propósito do `_e_membro` acima**, que trata admin como membro de qualquer turma: lá
    isso é certo, porque a pergunta é "pode ligar submissão a esta turma?". Aqui a pergunta é "quais
    turmas são SUAS?", e admin-é-membro-de-tudo transformaria o filtro da galeria em ruído para ele —
    "minha turma" passaria a significar "todas".
    """
    if not user_id:
        return {}
    cur = turmas.find(
        {"$or": [{"alunos": user_id}, {"professor_id": user_id}]},
        {"nome": 1, "professor_id": 1},
    )
    return {str(t["_id"]): {"nome": t.get("nome"), "professor_id": t.get("professor_id")}
            async for t in cur}


def _pode_ver(doc: dict, user_id: str, minhas_turmas: dict) -> bool:
    """O usuário pode ver este pipeline? É o MESMO critério da galeria e da cópia.

    Existe como função para os dois não divergirem: a galeria passou a mostrar material da turma que
    não é público, e sem espelhar a regra aqui o botão "Copiar" desses cartões daria 404.
    """
    if doc.get("user_id") == user_id or doc.get("is_public", False):
        return True
    return _e_material_de_turma(doc, minhas_turmas)


def _e_material_de_turma(doc: dict, minhas_turmas: dict) -> bool:
    """Material que o professor da MINHA turma deixou para a turma, sem estar público.

    Dois recortes, e os dois importam:

    - **`user_id` tem de ser o professor daquela turma.** `turma_id` não marca só material do
      professor: marca **submissão de aluno a atividade** (é assim que o ranking sabe de quem é cada
      entrega — ver `_validar_vinculo_atividade`). Sem este recorte, a galeria mostraria o trabalho de
      cada colega para a turma inteira, com resultados e métricas, numa plataforma de menores de idade
      e com atividades pontuadas. Medido em 04/08: das 7 pipelines em produção, as 2 com `turma_id`
      não-públicas eram submissões de aluno.
    - **`atividade_id` tem de ser vazio.** Um pipeline do professor amarrado a uma atividade é, na
      prática, a resposta esperada; mostrá-lo antes da entrega vazaria o gabarito.
    """
    if doc.get("atividade_id"):
        return False
    t = minhas_turmas.get(doc.get("turma_id") or "")
    return bool(t and t.get("professor_id") and doc.get("user_id") == t["professor_id"])


@router.get("/galeria")
async def listar_galeria():
    """Pipelines públicos + o material que o professor deixou nas turmas do usuário.

    O usuário sai de `id_usuario_atual()` (padrão do projeto para handler sem `Depends`): a rota já
    exige token, porque o router é registrado com `dependencies=auth_dependency` e
    `definir_usuario_atual` depende de `get_usuario_atual`.
    """
    user_id = id_usuario_atual()
    minhas = await _turmas_do_usuario(user_id)

    # Um clause por turma, e não `turma_id: {$in: [...]}`: o `user_id` exigido é o professor DAQUELA
    # turma. Um `$in` solto deixaria passar submissão de colega — ver `_e_material_de_turma`.
    material_da_turma = [
        {"turma_id": tid, "user_id": t["professor_id"], "atividade_id": None}
        for tid, t in minhas.items() if t.get("professor_id")
    ]
    filtro = {"$or": [{"is_public": True}, *material_da_turma]} if material_da_turma else {"is_public": True}

    cursor = pipelines.find(filtro).sort("dataModificacao", -1)
    docs = await cursor.to_list(length=100)

    saida = []
    for d in docs:
        item = _pipeline_doc(d)
        tid = item.get("turma_id")
        item["da_minha_turma"] = bool(tid and tid in minhas)
        # O NOME só sai para quem é membro: um pipeline público de outra turma não deve revelar como
        # ela se chama.
        item["turma_nome"] = (minhas.get(tid) or {}).get("nome") if item["da_minha_turma"] else None
        saida.append(item)
    return saida


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
    # O MESMO critério da galeria (`_pode_ver`): o que aparece lá tem de poder ser copiado, senão o
    # botão "Copiar" do material da turma devolveria 404. As turmas só são consultadas quando o
    # atalho (meu, ou público) não resolve — para não pagar uma query no caso comum.
    if not (original.get("user_id") == user_id or original.get("is_public", False)):
        if not _pode_ver(original, user_id, await _turmas_do_usuario(user_id)):
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
