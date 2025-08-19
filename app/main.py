from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(usuarios.router)
app.include_router(login.router)
app.include_router(conf_pipeline.router)
app.include_router(tutor.router)


app.include_router(coleta_dados_xlxs_router, prefix="/coleta_dados")
app.include_router(coleta_dados_csv_router, prefix="/coleta_dados")
app.include_router(configuracao_treinamento_router, prefix="/configurar_treinamento")


app.include_router(knn.router, prefix="/classificador/treinamento")
app.include_router(arvore_decisao.router, prefix="/classificador/treinamento")
app.include_router(regressao_logistica.router, prefix="/classificador/treinamento")
app.include_router(svm.router, prefix="/classificador/treinamento")

app.include_router(metricas_router, prefix="/classificador")






@app.get("/healthcheck")
async def healthcheck():
    try:
        # consulta simples para checar a conexão
        collections = await db.list_collection_names()
        return {"status": "ok", "collections": collections}
    except Exception as e:
        return {"status": "erro", "detalhe": str(e)}

