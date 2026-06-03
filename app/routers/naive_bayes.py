from fastapi import APIRouter
from sklearn.naive_bayes import GaussianNB
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()

@router.post("/naive_bayes")
async def treinar_naive_bayes(request: DatasetRequest):
    return await treinar_modelo_generico(
        request,
        "Naive Bayes",
        GaussianNB
    )
