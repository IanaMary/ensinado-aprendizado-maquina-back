from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

from typing import List, Tuple
import pandas as pd
from io import BytesIO
import base64

from app.database import coleta_collection
from app.deps import train_test_split
from app.models.schemas import ConfiguracaoColetaRequest


router = APIRouter()

def mapear_tipo(dtype_str: str) -> str:
    tipo = dtype_str.lower()
    if tipo in ("int64", "int32"):
        return "Número"
    elif tipo in ("float64", "float32"):
        return "Número"
    elif tipo in ("bool", "boolean"):
        return "Boolean"
    elif tipo in ("object", "string"):
        return "Texto"
    else:
        return dtype_str  # fallback: retorna como está


def validar_xlsx(file: UploadFile, nome: str):
    if not file or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, f"Arquivo de {nome} deve ser .xlsx")


async def ler_excel(file: UploadFile) -> Tuple[pd.DataFrame, bytes]:
    try:
        content = await file.read()
        df = pd.read_excel(BytesIO(content), engine='openpyxl')
        return df, content
    except Exception as e:
        raise HTTPException(400, f"Erro ao ler XLSX: {e}")
    
def decode_excel_base64(base64_string: str) -> List[dict]:
    try:
        binary = base64.b64decode(base64_string)
        df = pd.read_excel(BytesIO(binary))
        return df.head(5).to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao decodificar Excel: {e}")


def df_para_base64(df: pd.DataFrame) -> str:
    buffer = BytesIO()
    df.to_excel(buffer, index=False, engine='openpyxl')
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def gerar_colunas_detalhes(df: pd.DataFrame) -> List[dict]:
    return [
        {
            "nomeColuna": col,
            "tipoColuna": mapear_tipo(str(df[col].dtype)),
            "atributo": False
        }
        for col in df.columns
    ]


def montar_resposta_coleta(
    atributos,
    id_coleta,
    tipo,
    df_treino,
    df_teste,
    colunas_detalhes,
    arquivo_nome_treino=None,
    arquivo_nome_teste=None
):
    return {
        "id_coleta": id_coleta,
        "tipo": tipo,
        "arquivo_nome_treino": arquivo_nome_treino,
        "arquivo_nome_teste": arquivo_nome_teste,
        "num_linhas_treino": df_treino.shape[0],
        "num_linhas_teste": df_teste.shape[0],
        "num_colunas": df_treino.shape[1],
        "colunas_detalhes": colunas_detalhes,
        "atributos": atributos,
        "preview_treino": df_treino.head(5).to_dict(orient="records"),
        "preview_teste": df_teste.head(5).to_dict(orient="records")
    }


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

        doc = {
            "tipo": tipo,
            "arquivo_nome_treino": arquivo_nome_treino,
            "content_completo_base64": content_completo_b64,
            "content_treino_base64": content_treino_b64,
            "content_teste_base64": content_teste_b64,
            "num_linhas_total": df.shape[0],
            "num_colunas": df.shape[1],
            "atributos": {coluna: False for coluna in df.columns},  # salva no banco como dict
            "colunas_detalhes": colunas_detalhes,
            "config": {"test_size": test_size}
        }

        result = await coleta_collection.insert_one(doc)
        id_coleta = str(result.inserted_id)

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
            doc_original = await coleta_collection.find_one({"_id": ObjectId(id_coleta)})
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

        update_result = await coleta_collection.update_one(
            {"_id": ObjectId(id_coleta)},
            {
                "$set": {
                    "tipo": tipo,
                    "arquivo_nome_treino": arquivo_nome_treino,
                    "arquivo_nome_teste": arquivo_nome_teste,
                    "content_completo_base64": content_treino_b64,
                    "content_treino_base64": content_treino_b64,
                    "content_teste_base64": content_teste_b64,
                    "num_linhas_treino": df_treino.shape[0],
                    "num_linhas_teste": df_teste.shape[0],
                    "num_colunas": df_treino.shape[1],
                    "colunas_detalhes": colunas_detalhes,
                    "config": None
                }
            }
        )

        if update_result.modified_count == 0:
            raise HTTPException(404, "Documento com id_coleta não encontrado")

    # Aqui retornamos a lista simples de nomes das colunas para o front
    return montar_resposta_coleta(
        id_coleta=id_coleta,
        atributos={coluna: False for coluna in df_treino.columns},  # retorna dicionário com False  # RETORNO: lista simples
        tipo=tipo,
        arquivo_nome_treino=arquivo_nome_treino,
        arquivo_nome_teste=arquivo_nome_teste,
        df_treino=df_treino,
        df_teste=df_teste,
        colunas_detalhes=colunas_detalhes
    )

    
@router.get("/buscar_xlxs/{coleta_id}")
async def get_dados_por_coleta(coleta_id: str):
    try:
        doc = await coleta_collection.find_one({"_id": ObjectId(coleta_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido.")

    if not doc:
        raise HTTPException(status_code=404, detail="Coleta não encontrada.")

    def decode_excel_base64(base64_string: str) -> pd.DataFrame:
        try:
            binary = base64.b64decode(base64_string)
            df = pd.read_excel(BytesIO(binary))
            return df
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao decodificar Excel: {e}")

    df_treino = decode_excel_base64(doc.get("content_treino_base64", ""))
    df_teste = decode_excel_base64(doc.get("content_teste_base64", ""))

    preview_treino = df_treino.head(5).to_dict(orient="records")
    preview_teste = df_teste.head(5).to_dict(orient="records")

    # Garantir que "colunas" seja uma lista de nomes no retorno
    colunas = doc.get("colunas")
    if isinstance(colunas, dict):
        colunas = list(colunas.keys())
    elif colunas is None:
        colunas = []

    return {
        "id_coleta": str(doc["_id"]),
        "tipo": doc.get("tipo"),
        "arquivo_nome_treino": doc.get("arquivo_nome_treino"),
        "arquivo_nome_teste": doc.get("arquivo_nome_teste"),
        "target": doc.get("target"),              
        "atributos": doc.get("atributos"),    
        "preview_treino": preview_treino,
        "preview_teste": preview_teste,
        "colunas_detalhes": doc.get("colunas_detalhes"),
        "num_linhas_treino": df_treino.shape[0],
        "num_linhas_teste": df_teste.shape[0],
        "num_linhas_total": df_treino.shape[0] + df_teste.shape[0],
    }
    

@router.put("/configurar_coleta_xlxs/{coleta_id}")
async def configurar_coleta(coleta_id: str, config: ConfiguracaoColetaRequest):
    coleta = await coleta_collection.find_one({"_id": ObjectId(coleta_id)})
    
    if not coleta:
        raise HTTPException(status_code=404, detail="Coleta não encontrada.")

    update_data = {
        "target": config.target,
        "atributos": config.atributos
    }

    await coleta_collection.update_one(
        {"_id": ObjectId(coleta_id)},
        {"$set": update_data}
    )

    return {"mensagem": "Configuração salva com sucesso."}
    
@router.get("/unique")
async def get_unique_values(
    id_coleta: str = Query(..., description="ID da coleta para buscar os dados"),
    limit: int = Query(10, ge=1, le=100)
):
  if not ObjectId.is_valid(id_coleta):
    raise HTTPException(400, "ID da coleta inválido")

  doc = await coleta_collection.find_one({"_id": ObjectId(id_coleta)})
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


