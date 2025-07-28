from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing_extensions import Annotated
from typing import Optional
from fastapi import Form, File, UploadFile
from bson.errors import InvalidId
from app.models.schemas import ConfiguracaoColetaRequest
import pandas as pd
import base64
from io import StringIO
from app.database import coleta_collection

router = APIRouter()

@router.post("/csv")
async def upload_csv(
    tipo: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Arquivo deve ser CSV")

    content = await file.read()
    try:
        df = pd.read_csv(StringIO(content.decode("utf-8")))
    except Exception as e:
        raise HTTPException(400, f"Erro ao ler CSV: {e}")

    content_b64 = base64.b64encode(content).decode("utf-8")

    doc = {
        "tipo": tipo,
        "filename": file.filename,
        "content_base64": content_b64,
        "num_linhas": df.shape[0],
        "num_colunas": df.shape[1],
        "colunas": df.columns.tolist(),
        "config": None
    }

    result = await coleta_collection.insert_one(doc)

    return {
        "id_coleta": str(result.inserted_id),
        "filename": file.filename,
        "tipo": tipo,
        "num_linhas": df.shape[0],
        "num_colunas": df.shape[1],
        "colunas": df.columns.tolist(),
        "preview": df.head(5).to_dict(orient="records")
    }



@router.post("/configurar-treino")
async def configurar_treino(config: ConfiguracaoColetaRequest):
    try:
        oid = ObjectId(config.id_coleta)
    except InvalidId:
        raise HTTPException(status_code=400, detail="id_coleta inválido")

    update_result = await coleta_collection.update_one(
        {"_id": oid},
        {"$set": {
            "config": {
                "atributos": config.atributos,
                "target": config.target,
                "percentual_treino": config.percentual_treino
            }
        }},
        upsert=False
    )

    if update_result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Se quiser, pode checar modified_count, mas matched_count já garante existência

    return {"status": "configuração salva com sucesso", "id_coleta": config.id_coleta}

