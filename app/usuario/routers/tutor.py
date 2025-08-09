from typing import Optional
from fastapi import APIRouter, HTTPException
from app.usuario.schemas.tutor import AtualizarDescricaoRequest
from app.usuario.models.tutor import obter_arvore, avaliar_condicoes, tem_condicoes_validas
from app.database import tutor


router = APIRouter(prefix="/tutor", tags=["Tutor"])

@router.get("/")
async def avaliar(
    tamanho_arq: Optional[int] = None,
    prever_categoria: Optional[bool] = None,
    dados_rotulados: Optional[bool] = None,
    prever_quantidade: Optional[bool] =  None,
    num_categorias_conhecidas: Optional[bool] =  None,
    apenas_olhando: Optional[bool]=  None  
):
    arvore = await obter_arvore()

    # Monta o dicionário no formato esperado por avaliar_condicoes
    contexto_dict = {
        "tamanho_arq": tamanho_arq,
        "prever_categoria": prever_categoria,
        "dados_rotulados": dados_rotulados,
        "num_categorias_conhecidas": num_categorias_conhecidas,
        "apenas_olhando": apenas_olhando,
        "prever_quantidade": prever_quantidade,
        
    }

    descricao = avaliar_condicoes(arvore["start"], contexto_dict)

    return {
        "descricao": descricao
    }
    
    
@router.put("/")
async def atualizar_descricao(request: AtualizarDescricaoRequest):
    arvore = await obter_arvore()
    
    contexto_dict = request.contexto.dict(exclude_none=True)
    nova_descricao = request.nova_descricao

    # Função para buscar e atualizar a descrição do nó que casa com o contexto
    def atualizar_no(lista_condicoes):
        for item in lista_condicoes:
            cond = item.get("condicao", "")
            try:
                if eval(cond, {}, contexto_dict):
                    # Atualiza a descrição aqui
                    item["descricao"] = nova_descricao

                    # Se tem subcondições (resultado é lista), tenta atualizar lá também
                    resultado = item.get("resultado")
                    if isinstance(resultado, list) and tem_condicoes_validas(resultado):
                        atualizar_no(resultado)
                    return True
                else:
                    # Tenta na lista interna (resultado), se for lista com condições
                    resultado = item.get("resultado")
                    if isinstance(resultado, list) and tem_condicoes_validas(resultado):
                        if atualizar_no(resultado):
                            return True
            except Exception:
                continue
        return False

    encontrou = atualizar_no(arvore["start"])

    if not encontrou:
        return {"detail": "Nenhuma condição satisfeita para o contexto fornecido."}

    # Salva a árvore atualizada no banco
    await tutor.update_one({}, {"$set": {"start": arvore["start"]}})

    return {"detail": "Descrição atualizada com sucesso."}
