from fastapi import UploadFile, HTTPException
from typing import List, Tuple
import pandas as pd
from io import BytesIO
import base64



def mapear_tipo(dtype_str: str) -> str:
  tipo = dtype_str.lower()
  if tipo in ("int64", "int32"):
    return "number"
  elif tipo in ("float64", "float32"):
    return "number"
  elif tipo in ("bool", "boolean"):
    return "boolean"
  elif tipo in ("object", "string"):
    return "string"
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
    
def decode_excel_base64_df(base64_string: str) -> pd.DataFrame:
  try:
    binary = base64.b64decode(base64_string)
    df = pd.read_excel(BytesIO(binary))
    return df
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
      "nome_coluna": col,
      "tipo_coluna": mapear_tipo(str(df[col].dtype)),
      "atributo": False
    }
    for col in df.columns
  ]
  
def montar_resposta_coleta(
  id_configuracoes_treinamento,
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
    "id_configuracoes_treinamento": id_configuracoes_treinamento,
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
    "preview_teste": df_teste.head(5).to_dict(orient="records"),
    "tipo_target": None
  }
