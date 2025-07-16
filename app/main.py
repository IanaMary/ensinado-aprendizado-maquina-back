from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.knn import router as knn_router
from app.svm import router as svm_router
from app.metricas import router as metricas_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(knn_router, prefix="/classificador/treinamento")
app.include_router(svm_router, prefix="/classificador/treinamento")
app.include_router(metricas_router, prefix="/classificador")

