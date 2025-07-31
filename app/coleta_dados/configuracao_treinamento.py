from fastapi import APIRouter, HTTPException
from bson import ObjectId

from app.database import arquivos_xlxs, configuracoes_treinamento
from app.models.schemas import ConfiguracaoColetaRequest
from app.models.funcoes_genericas import decode_excel_base64_df

router = APIRouter()

@router.put("/{tipo}/{configurar_treinamento_id}")
async def configurar_treinamento(configurar_treinamento_id: str, config: ConfiguracaoColetaRequest):
  coleta = await configuracoes_treinamento.find_one({"_id": ObjectId(configurar_treinamento_id)})
  
  if not coleta:
    raise HTTPException(status_code=404, detail="Coleta não encontrada.")

  update_data = {
    "target": config.target,
    "atributos": config.atributos
  }

  await configuracoes_treinamento.update_one(
    {"_id": ObjectId(configurar_treinamento_id)},
    {"$set": update_data}
  )

  return {"mensagem": "Configuração salva com sucesso."}

@router.get("/{tipo}/{configurar_treinamento_id}")
async def get_configuracoe(configurar_treinamento_id: str):
  try:
    config_doc = await configuracoes_treinamento.find_one({"_id": ObjectId(configurar_treinamento_id)})
  except Exception:
    raise HTTPException(status_code=400, detail="ID inválido.")

  if not config_doc:
    raise HTTPException(status_code=404, detail="Configuração de treinamento não encontrada.")

  id_coleta = config_doc.get("id_coleta")
  if not id_coleta:
    raise HTTPException(status_code=400, detail="Campo 'id_coleta' não encontrado na configuração.")

  try:
    coleta_doc = await arquivos_xlxs.find_one({"_id": ObjectId(id_coleta)})
  except Exception as e:
    raise HTTPException(status_code=400, detail=f"Erro ao buscar coleta: {str(e)}")

  if not coleta_doc:
    raise HTTPException(status_code=404, detail="Documento de coleta não encontrado.")

  # Decodifica planilhas completas
  df_treino = decode_excel_base64_df(coleta_doc.get("content_treino_base64", ""))
  df_teste = decode_excel_base64_df(coleta_doc.get("content_teste_base64", ""))

  # Extrai preview (5 primeiras linhas como lista de dicts)
  preview_treino = df_treino.head(5).to_dict(orient="records")
  preview_teste = df_teste.head(5).to_dict(orient="records")

  colunas = coleta_doc.get("colunas")
  if isinstance(colunas, dict):
    colunas = list(colunas.keys())
  elif colunas is None:
    colunas = []

  atributos = config_doc.get("atributos")
  if isinstance(atributos, list) and len(atributos) > 0:
    atributos = atributos[0]

  return {
    "id_coleta": str(coleta_doc["_id"]),
    "tipo": coleta_doc.get("tipo"),
    "arquivo_nome_treino": coleta_doc.get("arquivo_nome_treino"),
    "arquivo_nome_teste": coleta_doc.get("arquivo_nome_teste"),
    "target": config_doc.get("target"),
    "atributos": atributos,
    "preview_treino": preview_treino,
    "preview_teste": preview_teste,
    "colunas_detalhes": coleta_doc.get("colunas_detalhes"),
    "num_linhas_treino": df_treino.shape[0],
    "num_linhas_teste": df_teste.shape[0],
    "num_linhas_total": df_treino.shape[0] + df_teste.shape[0],
  }