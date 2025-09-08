from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from app.schemas.tutor import AtualizarDescricaoRequest, ContextoPipeInicio, ContextoPipeColetaDados, ContextoPipeSelecaoModelo, ContextoPipeTreinamento, ContextoPipeSelecaoMetricas
from app.funcoes_genericas.funcoes_genericas import serialize_doc, concatenar_campos
from app.database import tutor
from bson import ObjectId

router = APIRouter(prefix="/tutor", tags=["Tutor"])

@router.get("/")
async def buscar_tutor_descricao(
    pipe: str,
    textos: Optional[List[str]] = Query(None),
    valor_modelo: Optional[str] = None
):
    try:
        sep='<br>'
        texto = ''
        result = await tutor.find_one({"pipe": pipe})
        if(pipe == 'inicio'):
            chaves = textos  or list(ContextoPipeInicio.__fields__.keys())
            texto = concatenar_campos(result, chaves, sep=sep)
        elif(pipe == 'coleta-dado'):
            chaves = textos or list(ContextoPipeColetaDados.__fields__.keys())
            texto = concatenar_campos(result, chaves, sep=sep)
        elif(pipe == 'selecao-modelo'):
            chaves = textos or list(ContextoPipeSelecaoModelo.__fields__.keys())
            texto = concatenar_campos(result, chaves, sep=sep)
        elif(pipe == 'treinamento'):
            chaves = textos  or list(ContextoPipeTreinamento.__fields__.keys())
            texto = concatenar_campos(result, chaves, sep=sep)
        elif(pipe == 'selecao-metricas'):
            chaves = textos  or list(ContextoPipeSelecaoMetricas.__fields__.keys())
            texto = concatenar_campos(result, chaves, sep=sep)
        elif(pipe == 'avaliacao'):
            chaves = textos  or list(ContextoPipeSelecaoMetricas.__fields__.keys())
            texto = concatenar_campos(result, chaves, sep=sep)
        
        
        return {'descricao': texto, 'id': str(result['_id'])}
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


@router.put("/{id}")
async def atualizar_descricao(
    id: str,
    request: AtualizarDescricaoRequest,
    modelos: Optional[List[str]] = Query(None)  # ?modelos=supervisionado&modelos=classificacao
):
    try:
        filtro = {"_id": ObjectId(id)}
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")

    update_data = request.contexto.dict(exclude_none=True)
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

    return {"detail": "Contexto atualizado com sucesso", "update_data": set_data}


@router.put("/editar-modelos/{id}")
async def atualizar_modelos(id: str, request: AtualizarDescricaoRequest):
    """
    Atualiza apenas os campos de modelos nos subníveis fixos,
    ignorando listas vazias.
    """
    try:
        filtro = {"_id": ObjectId(id)}
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")

    update_data = request.contexto.dict(exclude_none=True)
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

    return {"detail": "Modelos atualizados com sucesso", "update_data": set_data}


    
@router.put("/editar-tipo-aprendizado/{id}")
async def atualizar_chaves_fixas(id: str, request: AtualizarDescricaoRequest):
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

    return {"detail": "Campos atualizados com sucesso", "update_data": set_data}
