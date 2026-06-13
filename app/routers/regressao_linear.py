from fastapi import APIRouter
from sklearn.linear_model import LinearRegression
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()

@router.post("/regressao_linear")
async def treinar_regressao_linear(request: DatasetRequest):
    return await treinar_modelo_generico(
        request,
        "Regressão Linear",
        LinearRegression
    )
