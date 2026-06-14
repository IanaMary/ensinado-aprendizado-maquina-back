from fastapi import APIRouter
from sklearn.linear_model import HuberRegressor
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()


@router.post("/huber")
async def treinar_huber(request: DatasetRequest):
    return await treinar_modelo_generico(request, "Regressão de Huber", HuberRegressor)
