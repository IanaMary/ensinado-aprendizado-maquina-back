from fastapi import APIRouter
from sklearn.ensemble import RandomForestClassifier
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()

@router.post("/random_forest")
async def treinar_random_forest(request: DatasetRequest):
    return await treinar_modelo_generico(
        request,
        "Random Forest",
        RandomForestClassifier
    )
