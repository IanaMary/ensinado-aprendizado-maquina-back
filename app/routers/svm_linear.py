from fastapi import APIRouter
from sklearn.svm import SVC
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()

@router.post("/svm_linear")
async def treinar_svm_linear(request: DatasetRequest):
    return await treinar_modelo_generico(
        request,
        "SVM Linear",
        SVC,
        kernel="linear"
    )
