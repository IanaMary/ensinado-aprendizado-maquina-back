from fastapi import APIRouter
from sklearn.linear_model import LogisticRegression
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()

@router.post("/regressao_logistica")
async def treinar_regressao_logistica(request: DatasetRequest):
    return await treinar_modelo_generico(
        request,
        "Regressão Logística",
        LogisticRegression,
        max_iter=1000
    )
