from fastapi import APIRouter
from sklearn.tree import DecisionTreeClassifier
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()

@router.post("/arvore_decisao")
async def treinar_arvore_decisao(request: DatasetRequest):
    return await treinar_modelo_generico(
        request,
        "Árvore de Decisão",
        DecisionTreeClassifier
    )
