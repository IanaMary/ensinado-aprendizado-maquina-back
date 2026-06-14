from fastapi import APIRouter
from sklearn.linear_model import Perceptron
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()


@router.post("/perceptron")
async def treinar_perceptron(request: DatasetRequest):
    return await treinar_modelo_generico(request, "Perceptron", Perceptron)
