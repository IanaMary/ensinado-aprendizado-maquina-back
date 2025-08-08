from fastapi import APIRouter
from app.usuario.schemas.tutor import Contexto
from app.usuario.models.tutor import obter_arvore, avaliar_condicoes

router = APIRouter(prefix="/tutor", tags=["Tutor"])

@router.post("/")
async def avaliar(contexto: Contexto):
    arvore = await obter_arvore() 
    contexto_dict = contexto.dict()  # Transforma p/ dict para passar p/ avaliar_condicoes

    descricao = avaliar_condicoes(arvore["start"], contexto_dict)

    return {
      "descricao": descricao
    }
