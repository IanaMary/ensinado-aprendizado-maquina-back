import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL")
MONGO_DB = os.getenv("MONGO_DB")

if not MONGO_URL or not MONGO_DB:
    raise RuntimeError("MONGO_URL e MONGO_DB precisam estar definidos no .env")

client = AsyncIOMotorClient(MONGO_URL)
db = client[MONGO_DB]

# USUARIOS
colecao_usuario = db["usuarios"] 
verificadores_professor = db["verificadores_professor"]

# PIPELINE
opcoes_coletas = db["coleta_dados"] 

arquivos_xlxs = db["arquivos_xlxs"] 
configuracoes_treinamento = db["configuracoes_treinamento"] 
