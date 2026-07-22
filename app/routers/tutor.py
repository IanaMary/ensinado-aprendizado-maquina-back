from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, Depends
from app.schemas.tutor import AtualizarContextoRequest, AtualizarSelecaoModeloRequest, ContextoPipeInicio, ContextoPipeColetaDados, ContextoPipePreProcessamento, ContextoPipeSelecaoModelo, ContextoPipeTreinamento, ContextoPipeSelecaoMetricas
from app.funcoes_genericas.funcoes_genericas import serialize_doc, concatenar_campos
from app.database import tutor, tutor_audit
from app.security import exigir_admin_ou_professor
from bson import ObjectId

router = APIRouter(prefix="/tutor", tags=["Tutor"])


# Fonte única de verdade para pipes: slug -> (schema Pydantic, chaves_default opcionais).
# Alimenta tanto o GET /tutor/ quanto o PUT /tutor/pipe/{pipe} (validação).
_PIPES_SCHEMA = {
    "conf-pipeline": (None, ["texto_pipe", "explicacao"]),
    "inicio": (ContextoPipeInicio, None),
    "coleta-dado": (ContextoPipeColetaDados, None),
    "pre-processamento": (ContextoPipePreProcessamento, None),
    "selecao-modelo": (ContextoPipeSelecaoModelo, None),
    "treinamento": (ContextoPipeTreinamento, None),
    "selecao-metricas": (ContextoPipeSelecaoMetricas, None),
    "avaliacao": (ContextoPipeSelecaoMetricas, None),
}


async def _registrar_edicao(usuario: dict, doc_id: str, set_data: dict, operacao: str):
    """Registra uma edicao no tutor em db.tutor_audit (auditoria)."""
    try:
        doc = await tutor.find_one({"_id": ObjectId(doc_id)}, {"pipe": 1})
        pipe = (doc or {}).get("pipe", "desconhecido")
    except Exception:
        pipe = "desconhecido"

    entrada = {
        "pipe": pipe,
        "tutor_id": str(doc_id),
        "operacao": operacao,
        "campos_alterados": list((set_data or {}).keys()),
        "usuario_id": str(usuario.get("_id") or usuario.get("id") or ""),
        "usuario_email": usuario.get("email", ""),
        "usuario_nome": usuario.get("nome") or usuario.get("name") or usuario.get("email", ""),
        "timestamp": datetime.now(timezone.utc),
    }
    try:
        await tutor_audit.insert_one(entrada)
    except Exception:
        # Auditoria nao deve quebrar a edicao
        pass


@router.get("/audit")
async def listar_audit(
    pipe: Optional[str] = Query(None),
    limite: int = Query(20, ge=1, le=100),
):
    filtro = {"pipe": pipe} if pipe else {}
    cursor = tutor_audit.find(filtro).sort("timestamp", -1).limit(limite)
    documentos = await cursor.to_list(length=limite)
    return [
        {
            "id": str(d["_id"]),
            "pipe": d.get("pipe", ""),
            "operacao": d.get("operacao", ""),
            "campos_alterados": d.get("campos_alterados", []),
            "usuario_email": d.get("usuario_email", ""),
            "usuario_nome": d.get("usuario_nome", ""),
            "timestamp": d.get("timestamp").isoformat() if d.get("timestamp") else None,
        }
        for d in documentos
    ]

@router.get("/")
async def buscar_tutor_descricao(
    pipe: str,
    textos: Optional[List[str]] = Query(None),
    valor_modelo: Optional[str] = None
):
    try:
        sep='<br>'
        texto = ''
        # Validação e lookup via fonte única (_PIPES_SCHEMA)
        schema_info = _PIPES_SCHEMA.get(pipe)
        if schema_info is None:
            raise HTTPException(status_code=404, detail="Pipe desconhecido")

        result = await tutor.find_one({"pipe": pipe})
        if result is None:
            # Guia de preenchimento do admin: fallback versionado quando o doc
            # ainda não foi semeado (o chat do conf-pipeline depende dele).
            if pipe == 'conf-pipeline':
                from app.conteudo.kb_conf_pipeline import KB_CONF_PIPELINE
                return {'descricao': KB_CONF_PIPELINE, 'id': ''}
            raise HTTPException(status_code=404, detail="Documento do tutor não encontrado para o pipe informado.")

        schema_cls, default_keys = schema_info
        if schema_cls is not None:
            chaves = textos or list(schema_cls.model_fields.keys())
        else:
            chaves = textos or default_keys or []
        texto = concatenar_campos(result, *chaves, sep=sep, ignorar_faltantes=True)
        return {'descricao': texto, 'id': str(result['_id'])}
    except HTTPException:
        # Doc ausente deve responder 404 (o except genérico transformava em 400,
        # poluindo o log de erros do frontend).
        raise
    except Exception as e:
        raise HTTPException(400, f"Erro: {e}")
    

@router.get("/editar")
async def buscar_tutor_pipe(
    pipe: str,
    modelos: Optional[List[str]] = Query(None)  # espera algo como ?modelos=supervisionado&modelos=classificacao
):
    try:
        pipeline = [{"$match": {"pipe": pipe}}]

        if modelos and len(modelos) == 2:
            tipoAprendizado, subTipoAprendizado = modelos
            campo_modelos = f"${tipoAprendizado}.{subTipoAprendizado}.modelos"

            pipeline.append({
                "$project": {
                    "_id": 1,
                    "modelos": campo_modelos
                }
            })

        cursor = tutor.aggregate(pipeline)
        result = await cursor.to_list(length=1)


        if result:
            return serialize_doc(result[0])
        return {"modelos": []}

    except Exception as e:
        raise HTTPException(400, f"Erro: {e}")


@router.put("/pipe/{pipe}")
async def atualizar_por_pipe(
    pipe: str,
    request: AtualizarContextoRequest,
    usuario: dict = Depends(exigir_admin_ou_professor),
):
    """Atualiza (com upsert) o conteúdo de um pipe pelo slug — dispensa conhecer o
    _id e cobre o caso do documento ainda não existir (ex.: pipe 'inicio')."""
    if pipe not in _PIPES_SCHEMA:
        raise HTTPException(status_code=404, detail="Pipe desconhecido")

    set_data = {
        k: v for k, v in (request.contexto or {}).items()
        if v is not None and k not in {"pipe", "_id", "id"}
    }
    if not set_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    await tutor.update_one(
        {"pipe": pipe},
        {"$set": set_data, "$setOnInsert": {"pipe": pipe}},
        upsert=True,
    )
    doc = await tutor.find_one({"pipe": pipe}, {"_id": 1})
    doc_id = str(doc["_id"]) if doc else ""

    await _registrar_edicao(usuario, doc_id, set_data, "atualizar_por_pipe")

    return {"detail": "Contexto atualizado com sucesso", "id": doc_id, "update_data": set_data}


@router.put("/{id}")
async def atualizar_descricao(
    id: str,
    request: AtualizarContextoRequest,
    modelos: Optional[List[str]] = Query(None),  # ?modelos=supervisionado&modelos=classificacao
    usuario: dict = Depends(exigir_admin_ou_professor),
):
    try:
        filtro = {"_id": ObjectId(id)}
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")

    update_data = {k: v for k, v in (request.contexto or {}).items() if v is not None}
    set_data = {}

    if modelos and len(modelos) == 2:
        tipoAprendizado, subTipoAprendizado = modelos
        # Extrai os modelos do contexto
        modelos_valor = update_data.get(tipoAprendizado, {}) \
                                  .get(subTipoAprendizado, {}) \
                                  .get("modelos", [])
        # Monta o caminho de $set corretamente
        caminho = f"{tipoAprendizado}.{subTipoAprendizado}.modelos"
        set_data[caminho] = modelos_valor
    else:
        # Atualiza todo o contexto normalmente
        set_data = update_data

    if not set_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    resultado = await tutor.update_one(filtro, {"$set": set_data})

    if resultado.matched_count == 0:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    await _registrar_edicao(usuario, id, set_data, "atualizar_descricao")

    return {"detail": "Contexto atualizado com sucesso", "update_data": set_data}


@router.put("/editar-modelos/{id}")
async def atualizar_modelos(
    id: str,
    request: AtualizarSelecaoModeloRequest,
    usuario: dict = Depends(exigir_admin_ou_professor),
):
    """
    Atualiza apenas os campos de modelos nos subníveis fixos,
    ignorando listas vazias.
    """
    try:
        filtro = {"_id": ObjectId(id)}
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")

    update_data = request.contexto.model_dump(exclude_none=True)
    set_data = {}

    # supervisionado
    supervisionado = update_data.get("supervisionado", {})
    if "classificacao" in supervisionado:
        modelos = supervisionado["classificacao"].get("modelos", [])
        if modelos:  # só atualiza se não estiver vazio
            set_data["supervisionado.classificacao.modelos"] = modelos
    if "regressao" in supervisionado:
        modelos = supervisionado["regressao"].get("modelos", [])
        if modelos:
            set_data["supervisionado.regressao.modelos"] = modelos

    # nao_supervisionado
    nao_supervisionado = update_data.get("nao_supervisionado", {})
    if "reducao_dimensionalidade" in nao_supervisionado:
        modelos = nao_supervisionado["reducao_dimensionalidade"].get("modelos", [])
        if modelos:
            set_data["nao_supervisionado.reducao_dimensionalidade.modelos"] = modelos
    if "agrupamento" in nao_supervisionado:
        modelos = nao_supervisionado["agrupamento"].get("modelos", [])
        if modelos:
            set_data["nao_supervisionado.agrupamento.modelos"] = modelos

    if not set_data:
        raise HTTPException(status_code=400, detail="Nenhum modelo para atualizar")

    resultado = await tutor.update_one(filtro, {"$set": set_data})

    if resultado.matched_count == 0:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    await _registrar_edicao(usuario, id, set_data, "atualizar_modelos")

    return {"detail": "Modelos atualizados com sucesso", "update_data": set_data}



@router.put("/editar-tipo-aprendizado/{id}")
async def atualizar_chaves_fixas(
    id: str,
    request: AtualizarSelecaoModeloRequest,
    usuario: dict = Depends(exigir_admin_ou_professor),
):
    """
    Atualiza apenas as chaves fixas definidas manualmente no $set.
    """
    try:
        filtro = {"_id": ObjectId(id)}
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")

    set_data = {}

    # texto_pipe
    if hasattr(request.contexto, "texto_pipe") and request.contexto.texto_pipe is not None:
        set_data["texto_pipe"] = request.contexto.texto_pipe

    # supervisionado.explicacao
    if hasattr(request.contexto, "supervisionado") and request.contexto.supervisionado:
        if getattr(request.contexto.supervisionado, "explicacao", None) is not None:
            set_data["supervisionado.explicacao"] = request.contexto.supervisionado.explicacao

        # supervisionado.classificacao.explicacao
        if getattr(request.contexto.supervisionado, "classificacao", None):
            classificacao = request.contexto.supervisionado.classificacao
            if getattr(classificacao, "explicacao", None) is not None:
                set_data["supervisionado.classificacao.explicacao"] = classificacao.explicacao

        # supervisionado.regressao.explicacao
        if getattr(request.contexto.supervisionado, "regressao", None):
            regressao = request.contexto.supervisionado.regressao
            if getattr(regressao, "explicacao", None) is not None:
                set_data["supervisionado.regressao.explicacao"] = regressao.explicacao

    # nao_supervisionado.explicacao
    if hasattr(request.contexto, "nao_supervisionado") and request.contexto.nao_supervisionado:
        if getattr(request.contexto.nao_supervisionado, "explicacao", None) is not None:
            set_data["nao_supervisionado.explicacao"] = request.contexto.nao_supervisionado.explicacao

        # nao_supervisionado.reducao_dimensionalidade.explicacao
        if getattr(request.contexto.nao_supervisionado, "reducao_dimensionalidade", None):
            reducao = request.contexto.nao_supervisionado.reducao_dimensionalidade
            if getattr(reducao, "explicacao", None) is not None:
                set_data["nao_supervisionado.reducao_dimensionalidade.explicacao"] = reducao.explicacao

        # nao_supervisionado.agrupamento.explicacao
        if getattr(request.contexto.nao_supervisionado, "agrupamento", None):
            agrupamento = request.contexto.nao_supervisionado.agrupamento
            if getattr(agrupamento, "explicacao", None) is not None:
                set_data["nao_supervisionado.agrupamento.explicacao"] = agrupamento.explicacao

    if not set_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    resultado = await tutor.update_one(filtro, {"$set": set_data})

    if resultado.matched_count == 0:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    await _registrar_edicao(usuario, id, set_data, "atualizar_chaves_fixas")

    return {"detail": "Campos atualizados com sucesso", "update_data": set_data}
