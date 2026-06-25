from fastapi import APIRouter, Depends, HTTPException
from typing import List
from datetime import datetime
from app.database import erros_sistema
from app.schemas.sistema import ErrorLogCreate, ErrorLogResponse
from app.security import get_usuario_atual

router = APIRouter(tags=["Sistema"])

@router.post("/erro", response_model=dict)
async def log_erro_frontend(erro: ErrorLogCreate):
    erro_dict = erro.model_dump()
    erro_dict["timestamp"] = datetime.utcnow()
    await erros_sistema.insert_one(erro_dict)
    return {"status": "success", "message": "Erro registrado."}

@router.get("/erros", response_model=List[ErrorLogResponse])
async def get_erros_frontend(current_user: dict = Depends(get_usuario_atual)):
    # Apenas admin pode ver os logs
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado.")
    
    erros = await erros_sistema.find().sort("timestamp", -1).limit(100).to_list(100)
    
    erros_lista = []
    for erro in erros:
        erro["id"] = str(erro["_id"])
        erros_lista.append(ErrorLogResponse(**erro))
        
    return erros_lista

@router.get("/logs-backend")
async def get_logs_backend(current_user: dict = Depends(get_usuario_atual)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado.")
    from app.logging_config import get_last_logs
    return get_last_logs(200)
