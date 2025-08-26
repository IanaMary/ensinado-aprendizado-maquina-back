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
    textos: Optional[List[str]] = Query(None)
):
    try:
        sep='<br><br>'
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
            # chaves = ['tipos.nao_supervisionado.explicacao', 'tipos.nao_supervisionado.reducao_dimensionalidade.explicacao',
            #         'tipos.nao_supervisionado.reducao_dimensionalidade.modelos[0].explicacao']
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
    tipos: Optional[List[str]] = Query(None)
):
    try:
        print('pipe ', tipos)
        result = await tutor.find_one({"pipe": pipe})
        return serialize_doc(result)
    except Exception as e:
        raise HTTPException(400, f"Erro: {e}")
    
    
@router.put("/{id}")
async def atualizar_descricao(id: str, request: AtualizarDescricaoRequest):
    try:
        filtro = {"_id": ObjectId(id)}
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")

    # Atualiza os campos do contexto diretamente no documento
    update_data = request.contexto.dict(exclude_none=True)

    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    resultado = await tutor.update_one(filtro, {"$set": update_data})

    if resultado.matched_count == 0:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    return {"detail": "Contexto atualizado com sucesso", "update_data": update_data}