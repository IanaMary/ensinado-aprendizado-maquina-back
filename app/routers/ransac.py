from fastapi import APIRouter
from sklearn.linear_model import RANSACRegressor
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()


@router.post("/ransac")
async def treinar_ransac(request: DatasetRequest):
    return await treinar_modelo_generico(request, "Regressão RANSAC", RANSACRegressor)
