from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

from typing import List, Tuple
import pandas as pd
from io import BytesIO
import base64

from app.database import arquivos, configuracoes_treinamento
from app.deps import train_test_split
from app.models.schemas import ConfiguracaoColetaRequest
from app.models.funcoes_genericas import validar_xlsx, ler_excel, df_para_base64, gerar_colunas_detalhes, montar_resposta_coleta


router = APIRouter()

@router.post("/salvar_xlxs")
async def upload_xlsx(
    tipo: str = Form(...),
    test_size: float = Form(0.2),
    file: UploadFile = File(None),
    file_treino: UploadFile = File(None),
    file_teste: UploadFile = File(None),
    id_coleta: str = Form(None)
):
    if tipo not in {"treino", "teste"}:
        raise HTTPException(400, "Tipo deve ser 'treino' ou 'teste'")

    arquivo_nome_treino = None
    arquivo_nome_teste = None

    if tipo == "treino":
        if file is None:
            raise HTTPException(400, "Arquivo 'file' obrigatório para tipo 'treino'")

        validar_xlsx(file, "treino")
        df, _ = await ler_excel(file)
        arquivo_nome_treino = file.filename

        content_completo_b64 = df_para_base64(df)

        df_treino, df_teste = train_test_split(df, test_size=test_size, random_state=42)

        content_treino_b64 = df_para_base64(df_treino)
        content_teste_b64 = df_para_base64(df_teste)

        colunas_detalhes = gerar_colunas_detalhes(df)
        
        atributos = {coluna: False for coluna in df.columns}

        doc_arquivo = {
            "arquivo_nome_treino": arquivo_nome_treino,
            "content_completo_base64": content_completo_b64,
            "content_treino_base64": content_treino_b64,
            "content_teste_base64": content_teste_b64,
            "num_linhas_total": df.shape[0],
            "num_colunas": df.shape[1],
            "atributos": atributos,  # salva no banco como dict
            "colunas_detalhes": colunas_detalhes,
        }
        
        result = await arquivos.insert_one(doc_arquivo)
        id_coleta = str(result.inserted_id)
        
        doc_configuracoes_treinamento = {
            "id_coleta" : ObjectId(result.inserted_id),
            "test_size": test_size,
            "atributos": atributos,
            "tipo_target": None,
            "target": None
        }

        result = await configuracoes_treinamento.insert_one(doc_configuracoes_treinamento)
        id_configuracoes_treinamento = str(result.inserted_id)
       

    elif tipo == "teste":
        if not id_coleta:
            raise HTTPException(400, "id_coleta é obrigatório para tipo 'teste'")

        if file_teste is None:
            raise HTTPException(400, "Arquivo 'file_teste' obrigatório para tipo 'teste'")

        validar_xlsx(file_teste, "teste")
        df_teste, content_teste = await ler_excel(file_teste)
        content_teste_b64 = base64.b64encode(content_teste).decode("utf-8")
        arquivo_nome_teste = file_teste.filename

        if file_treino is not None:
            validar_xlsx(file_treino, "treino")
            df_treino, content_treino = await ler_excel(file_treino)
            content_treino_b64 = base64.b64encode(content_treino).decode("utf-8")
            arquivo_nome_treino = file_treino.filename
        else:
            doc_original = await arquivos.find_one({"_id": ObjectId(id_coleta)})
            if not doc_original:
                raise HTTPException(404, "Documento com id_coleta não encontrado")

            content_completo_b64 = doc_original.get("content_completo_base64")
            if content_completo_b64 is None:
                raise HTTPException(400, "Conteúdo completo do treino não encontrado no banco")

            bytes_treino = base64.b64decode(content_completo_b64)
            df_treino = pd.read_excel(BytesIO(bytes_treino))
            content_treino_b64 = content_completo_b64
            arquivo_nome_treino = doc_original.get("arquivo_nome_treino", None)

        colunas_detalhes = gerar_colunas_detalhes(df_treino)

        update_result = await arquivos.update_one(
            {"_id": ObjectId(id_coleta)},
            {
                "$set": {
                    "arquivo_nome_treino": arquivo_nome_treino,
                    "arquivo_nome_teste": arquivo_nome_teste,
                    "content_completo_base64": content_treino_b64,
                    "content_treino_base64": content_treino_b64,
                    "content_teste_base64": content_teste_b64,
                    "num_linhas_treino": df_treino.shape[0],
                    "num_linhas_teste": df_teste.shape[0],
                    "num_colunas": df_treino.shape[1],
                    "colunas_detalhes": colunas_detalhes,
                }
            }
        )

        if update_result.modified_count == 0:
            raise HTTPException(404, "Documento com id_coleta não encontrado")

    # Aqui retornamos a lista simples de nomes das colunas para o front
    return montar_resposta_coleta(
        id_configuracoes_treinamento=id_configuracoes_treinamento,
        id_coleta=id_coleta,
        atributos={coluna: False for coluna in df_treino.columns},  # retorna dicionário com False  # RETORNO: lista simples
        tipo=tipo,
        arquivo_nome_treino=arquivo_nome_treino,
        arquivo_nome_teste=arquivo_nome_teste,
        df_treino=df_treino,
        df_teste=df_teste,
        colunas_detalhes=colunas_detalhes
    )

    
@router.get("/unique")
async def get_unique_values(
    id_coleta: str = Query(..., description="ID da coleta para buscar os dados"),
    limit: int = Query(10, ge=1, le=100)
):
  if not ObjectId.is_valid(id_coleta):
    raise HTTPException(400, "ID da coleta inválido")

  doc = await arquivos.find_one({"_id": ObjectId(id_coleta)})
  if not doc:
    raise HTTPException(404, "Coleta não encontrada")

  try:
    content_bytes = base64.b64decode(doc["content_base64"])
    df = pd.read_excel(BytesIO(content_bytes), engine='openpyxl')
  except Exception as e:
    raise HTTPException(500, f"Erro ao processar dados: {e}")

  valores_unicos = {}
  for col in df.columns:
    unique_vals = df[col].dropna().unique()[:limit].tolist()
    unique_vals = [None if (isinstance(v, float) and pd.isna(v)) else v for v in unique_vals]
    valores_unicos[col] = unique_vals

  return {
    "id_coleta": id_coleta,
    "filename": doc["filename"],
    "num_linhas": doc["num_linhas"],
    "num_colunas": doc["num_colunas"],
    "valores_unicos": valores_unicos
  }


