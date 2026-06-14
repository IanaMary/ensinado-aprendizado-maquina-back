from fastapi import APIRouter
from sklearn.neighbors import KNeighborsRegressor
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()


@router.post("/knn_regressor")
async def treinar_knn_regressor(request: DatasetRequest):
    return await treinar_modelo_generico(request, "k-NN Regressor", KNeighborsRegressor)
