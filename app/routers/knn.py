from fastapi import APIRouter
from sklearn.neighbors import KNeighborsClassifier
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()

@router.post("/knn")
async def treinar_knn(request: DatasetRequest):
    return await treinar_modelo_generico(
        request,
        "KNN",
        KNeighborsClassifier
    )
