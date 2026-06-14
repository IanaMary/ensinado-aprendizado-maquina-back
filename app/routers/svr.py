from fastapi import APIRouter
from sklearn.svm import SVR
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()


@router.post("/svr")
async def treinar_svr(request: DatasetRequest):
    return await treinar_modelo_generico(request, "SVR (Regressão SVM)", SVR)
