import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.database import db, client
from app.routers import usuarios
from app.routers import login
from app.routers import convite
from app.routers import conf_pipeline
from app.routers import tutor
from app.routers import chat_tutor
from app.routers import artefatos
from app.routers import knn
from app.routers import arvore_decisao
from app.routers import regressao_logistica
from app.routers import regressao_linear
from app.routers import svm
from app.routers import svm_linear
from app.routers import random_forest
from app.routers import adaboost
from app.routers import naive_bayes
from app.routers import mlp
from app.routers import qda
from app.routers import kmeans
from app.routers import ridge
from app.routers import regressao_polinomial
from app.routers import quantile
from app.routers import huber
from app.routers import ransac
from app.routers import theilsen
from app.routers import svr
from app.routers import mlp_regressor
from app.routers import knn_regressor
from app.routers import sgd
from app.routers import perceptron
from app.routers import toy_datasets
from app.routers import pipelines
from app.routers import visualizacao
from app.routers import admin
from app.coleta_dados import coleta_dados_csv_router, coleta_dados_xlxs_router, configuracao_treinamento_router
from app.metricas import router as metricas_router
from app.security import get_usuario_atual

app = FastAPI()

# Configuração de CORS segura por ambiente
allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:4200")
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rotas públicas (sem autenticação)
app.include_router(login.router)
app.include_router(toy_datasets.router)
app.include_router(convite.router)

# Rotas protegidas (requer JWT)
auth_dependency = [Depends(get_usuario_atual)]

app.include_router(usuarios.router, dependencies=auth_dependency)
app.include_router(conf_pipeline.router, dependencies=auth_dependency)
app.include_router(tutor.router, dependencies=auth_dependency)
app.include_router(chat_tutor.router, dependencies=auth_dependency)
app.include_router(artefatos.router, dependencies=auth_dependency)

app.include_router(coleta_dados_xlxs_router, prefix="/coleta_dados", dependencies=auth_dependency)
app.include_router(coleta_dados_csv_router, prefix="/coleta_dados", dependencies=auth_dependency)
app.include_router(configuracao_treinamento_router, prefix="/configurar_treinamento", dependencies=auth_dependency)

app.include_router(knn.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(arvore_decisao.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(regressao_logistica.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(regressao_linear.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(svm.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(svm_linear.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(random_forest.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(adaboost.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(naive_bayes.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(mlp.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(qda.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(kmeans.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(ridge.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(regressao_polinomial.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(quantile.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(huber.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(ransac.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(theilsen.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(svr.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(mlp_regressor.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(knn_regressor.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(sgd.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(perceptron.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(metricas_router, prefix="/classificador", dependencies=auth_dependency)
app.include_router(pipelines.router, dependencies=auth_dependency)
app.include_router(admin.router, dependencies=auth_dependency)
app.include_router(visualizacao.router, prefix="/visualizacao", dependencies=auth_dependency)

@app.on_event("startup")
def prewarm_datasets():
    # Pre-baixa os datasets UCI para o cache em disco em background, sem bloquear
    # o boot. Na primeira execucao baixa tudo; nos restarts seguintes e no-op.
    import threading
    threading.Thread(
        target=toy_datasets.prewarm_uci_cache, daemon=True, name="prewarm-uci-cache"
    ).start()


@app.get("/healthcheck")
async def healthcheck():
    try:
        await client.admin.command('ping')
        return {"status": "ok"}
    except Exception as e:
        return {
            "status": "erro",
            "detalhe": str(e),
        }
