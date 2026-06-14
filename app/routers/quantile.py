from fastapi import APIRouter
from sklearn.linear_model import QuantileRegressor
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()


@router.post("/quantile")
async def treinar_quantile(request: DatasetRequest):
    return await treinar_modelo_generico(request, "Regressão Quantílica", QuantileRegressor)
