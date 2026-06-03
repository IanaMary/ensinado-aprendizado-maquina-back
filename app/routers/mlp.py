from fastapi import APIRouter
from sklearn.neural_network import MLPClassifier
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()

@router.post("/mlp")
async def treinar_mlp(request: DatasetRequest):
    return await treinar_modelo_generico(
        request,
        "Rede Neural MLP",
        MLPClassifier,
        max_iter=500
    )
