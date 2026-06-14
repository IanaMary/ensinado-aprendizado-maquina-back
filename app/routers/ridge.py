from fastapi import APIRouter
from sklearn.linear_model import Ridge
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()


@router.post("/ridge")
async def treinar_ridge(request: DatasetRequest):
    return await treinar_modelo_generico(request, "Ridge", Ridge)
