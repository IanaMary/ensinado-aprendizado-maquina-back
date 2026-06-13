from fastapi import APIRouter
from sklearn.cluster import KMeans
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()

@router.post("/k_means")
async def treinar_kmeans(request: DatasetRequest):
    return await treinar_modelo_generico(
        request,
        "K-Means",
        KMeans
    )
