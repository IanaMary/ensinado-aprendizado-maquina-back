import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Carrega o .env apenas em ambiente local
if os.getenv("RENDER") is None:
    load_dotenv()

# Obtém as variáveis de ambiente
MONGO_URL = os.getenv("MONGO_URL")
MONGO_DB = os.getenv("MONGO_DB")

# Validação das variáveis obrigatórias
if not MONGO_URL:
    raise RuntimeError(
        "A variável de ambiente 'MONGO_URL' não foi definida."
    )

if not MONGO_DB:
    raise RuntimeError(
        "A variável de ambiente 'MONGO_DB' não foi definida."
    )

# Cria conexão com MongoDB
client = AsyncIOMotorClient(MONGO_URL)

# Seleciona banco de dados
db = client[MONGO_DB]

# =========================
# COLEÇÕES DE USUÁRIOS
# =========================
colecao_usuario = db["usuarios"]
verificadores_professor = db["verificadores_professor"]

# =========================
# COLEÇÕES DO PIPELINE
# =========================
opcoes_coletas = db["coleta_dados"]
opcoes_modelos = db["modelos"]
opcoes_metricas = db["metricas"]
opcoes_pre_processamento = db["pre_processamento"]

arquivos = db["arquivos"]
configuracoes_treinamento = db["configuracoes_treinamento"]

# =========================
# MODELOS TREINADOS
# =========================
modelos_treinados = db["modelos_treinados"]

# =========================
# TUTOR
# =========================
tutor = db["tutor"]
tutor_audit = db["tutor_audit"]

# =========================
# PIPELINES
# =========================
pipelines = db["pipelines"]

# =========================
# HISTÓRICO DE CHAT
# =========================
historico_chat = db["historico_chat"]