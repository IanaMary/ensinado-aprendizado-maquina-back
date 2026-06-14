from fastapi import APIRouter
from sklearn.neural_network import MLPRegressor
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()


@router.post("/mlp_regressor")
async def treinar_mlp_regressor(request: DatasetRequest):
    return await treinar_modelo_generico(request, "Rede Neural (MLP) Regressora", MLPRegressor, max_iter=500)
