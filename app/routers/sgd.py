from fastapi import APIRouter
from sklearn.linear_model import SGDClassifier
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()


@router.post("/sgd")
async def treinar_sgd(request: DatasetRequest):
    return await treinar_modelo_generico(request, "SGD Classifier", SGDClassifier)
