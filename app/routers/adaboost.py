from fastapi import APIRouter
from sklearn.ensemble import AdaBoostClassifier
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()

@router.post("/adaboost")
async def treinar_adaboost(request: DatasetRequest):
    return await treinar_modelo_generico(
        request,
        "AdaBoost",
        AdaBoostClassifier
    )
