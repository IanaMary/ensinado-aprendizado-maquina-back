import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.database import client
from app.routers import usuarios
from app.routers import login
from app.routers import convite
from app.routers import conf_pipeline
from app.routers import tutor
from app.routers import chat_tutor
from app.routers import artefatos
from app.routers import treinamento_base
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
from app.routers import turmas
from app.routers import visualizacao
from app.routers import admin
from app.routers import atividade
from app.routers import sistema
from app.coleta_dados import coleta_dados_csv_router, coleta_dados_xlxs_router, coleta_dados_url_router, configuracao_treinamento_router
from app.metricas import router as metricas_router
from app.security import definir_usuario_atual
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.logging_config import setup_logging
from loguru import logger

setup_logging()
logger.info("Iniciando H2IA Tutor API")

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
app.include_router(sistema.router, prefix="/sistema")

# Rotas protegidas (requer JWT). definir_usuario_atual autentica E publica o usuário
# no ContextVar (para o registro run↔usuário no treino), preservando o comportamento.
auth_dependency = [Depends(definir_usuario_atual)]

app.include_router(usuarios.router, dependencies=auth_dependency)
app.include_router(conf_pipeline.router, dependencies=auth_dependency)
# chat_tutor ANTES de tutor: ambos têm prefixo /tutor, e tutor.router define um
# catch-all PUT /tutor/{id}. Registrado depois, ele "roubava" PUT /tutor/modelo
# (id="modelo") e validava o corpo como AtualizarContextoRequest → 422 ao trocar
# o LLM. Com chat_tutor primeiro, suas rotas exatas (/modelo, /modelos) vencem.
app.include_router(chat_tutor.router, dependencies=auth_dependency)
app.include_router(tutor.router, dependencies=auth_dependency)
app.include_router(artefatos.router, dependencies=auth_dependency)

app.include_router(coleta_dados_xlxs_router, prefix="/coleta_dados", dependencies=auth_dependency)
app.include_router(coleta_dados_csv_router, prefix="/coleta_dados", dependencies=auth_dependency)
app.include_router(coleta_dados_url_router, prefix="/coleta_dados", dependencies=auth_dependency)
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
# Rota genérica data-driven (por último: os routers literais acima têm prioridade).
# Treina modelos NOVOS cadastrados pelo admin lendo modelo_doc.execucao.
app.include_router(treinamento_base.router, prefix="/classificador", dependencies=auth_dependency)
app.include_router(metricas_router, prefix="/classificador", dependencies=auth_dependency)
app.include_router(pipelines.router, dependencies=auth_dependency)
app.include_router(turmas.router, dependencies=auth_dependency)
app.include_router(admin.router, dependencies=auth_dependency)
app.include_router(atividade.router, dependencies=auth_dependency)
app.include_router(visualizacao.router, prefix="/visualizacao", dependencies=auth_dependency)

# Retenção da telemetria: documentos de atividade_usuario expiram após N dias
# (TTL). Configurável por env; default 90 dias. 0/negativo desativa o TTL.
ATIVIDADE_TTL_DIAS = int(os.getenv("ATIVIDADE_TTL_DIAS", "90"))


@app.on_event("startup")
async def criar_indices_atividade():
    # A coleção de telemetria é a de maior volume de escrita (1 evento por chamada
    # HTTP por usuário). Sem índices, listar/resumo viram full scan e o sort por
    # timestamp pode estourar o limite de sort em memória do MongoDB. O índice de
    # timestamp também é TTL: expira docs antigos (retenção + privacidade) e ainda
    # serve ao sort por timestamp. create_index é idempotente.
    try:
        from app.database import atividade_usuario
        if ATIVIDADE_TTL_DIAS > 0:
            await atividade_usuario.create_index(
                [("timestamp", -1)], expireAfterSeconds=ATIVIDADE_TTL_DIAS * 86400
            )
        else:
            await atividade_usuario.create_index([("timestamp", -1)])
        await atividade_usuario.create_index([("usuario_id", 1), ("timestamp", -1)])
        await atividade_usuario.create_index([("tipo", 1), ("timestamp", -1)])
    except Exception:
        # Se já houver um índice de timestamp com opções diferentes (ex.: criado sem
        # TTL por uma versão anterior), ajusta o expireAfterSeconds via collMod.
        if ATIVIDADE_TTL_DIAS > 0:
            try:
                from app.database import db
                await db.command({
                    "collMod": "atividade_usuario",
                    "index": {
                        "keyPattern": {"timestamp": -1},
                        "expireAfterSeconds": ATIVIDADE_TTL_DIAS * 86400,
                    },
                })
            except Exception:
                pass


@app.on_event("startup")
async def criar_indices_mlflow_runs():
    # Associação run↔usuário (artefatos): consulta por usuário + data, ordenada por
    # criado_em. create_index é idempotente.
    try:
        from app.database import mlflow_runs
        await mlflow_runs.create_index("mlflow_run_id", unique=True)
        await mlflow_runs.create_index([("usuario_id", 1), ("criado_em", -1)])
        await mlflow_runs.create_index([("criado_em", -1)])
    except Exception:
        pass


@app.on_event("startup")
async def criar_indices_turmas():
    # Índices para os novos padrões de consulta de Turmas & Atividades.
    # create_index é idempotente. codigo é único (usado no join por código).
    try:
        from app.database import turmas, atividades, pipelines
        await turmas.create_index("codigo", unique=True)
        await turmas.create_index([("professor_id", 1), ("criado_em", -1)])
        await turmas.create_index([("alunos", 1)])
        await atividades.create_index([("turma_id", 1), ("criado_em", -1)])
        await pipelines.create_index([("atividade_id", 1)])
        await pipelines.create_index([("turma_id", 1), ("user_id", 1)])
    except Exception:
        pass


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
