import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.database import db, client
from app.routers import usuarios
from app.routers import login
from app.routers import conf_pipeline
from app.routers import tutor
from app.routers import knn
from app.routers import arvore_decisao
from app.routers import regressao_logistica
from app.routers import svm
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

# Rotas protegidas (requer JWT)
auth_dependency = [Depends(get_usuario_atual)]

app.include_router(usuarios.router, dependencies=auth_dependency)
app.include_router(conf_pipeline.router, dependencies=auth_dependency)
app.include_router(tutor.router, dependencies=auth_dependency)

app.include_router(coleta_dados_xlxs_router, prefix="/coleta_dados", dependencies=auth_dependency)
app.include_router(coleta_dados_csv_router, prefix="/coleta_dados", dependencies=auth_dependency)
app.include_router(configuracao_treinamento_router, prefix="/configurar_treinamento", dependencies=auth_dependency)

app.include_router(knn.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(arvore_decisao.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(regressao_logistica.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(svm.router, prefix="/classificador/treinamento", dependencies=auth_dependency)
app.include_router(metricas_router, prefix="/classificador", dependencies=auth_dependency)

@app.get("/healthcheck")
async def healthcheck():
    try:
        # Lista bancos disponíveis
        databases = await client.list_database_names()

        # Lista coleções do banco atual
        collections = await db.list_collection_names()

        return {
            "status": "ok",
            "database_atual": db.name,
            "databases_disponiveis": databases,
            "collections": collections,
        }

    except Exception as e:
        return {
            "status": "erro",
            "detalhe": str(e),
        }
