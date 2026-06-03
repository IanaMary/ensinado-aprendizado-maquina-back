from fastapi import APIRouter
from sklearn.discriminant_analysis import QuadraticDiscriminantAnalysis
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()

@router.post("/qda")
async def treinar_qda(request: DatasetRequest):
    return await treinar_modelo_generico(
        request,
        "QDA",
        QuadraticDiscriminantAnalysis
    )
