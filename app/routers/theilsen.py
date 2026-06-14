from fastapi import APIRouter
from sklearn.linear_model import TheilSenRegressor
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()


@router.post("/theilsen")
async def treinar_theilsen(request: DatasetRequest):
    return await treinar_modelo_generico(request, "Regressão Theil-Sen", TheilSenRegressor)
