from fastapi import APIRouter
from app.modelos_custom.regressao_polinomial import RegressaoPolinomial
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()


@router.post("/regressao_polinomial")
async def treinar_regressao_polinomial(request: DatasetRequest):
    return await treinar_modelo_generico(request, "Regressão Polinomial", RegressaoPolinomial)
