from fastapi import APIRouter
from sklearn.decomposition import PCA
from app.routers.treinamento_base import treinar_modelo_generico
from app.schemas.schemas import DatasetRequest

router = APIRouter()


# Único dos 24 modelos sem router literal: caía na rota genérica, que exige o bloco
# `execucao` no documento — ausente nos modelos semeados em produção — e devolvia 400.
# O PCA é aprendizado NÃO SUPERVISIONADO: treina só com X, sem alvo (o documento já
# declara `dados_rotulados: false`, e é isso que leva o treino ao caminho sem y).
@router.post("/pca")
async def treinar_pca(request: DatasetRequest):
    return await treinar_modelo_generico(
        request,
        "PCA",
        PCA
    )
