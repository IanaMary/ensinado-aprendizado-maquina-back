from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import secrets

from app.usuario.schemas.usuarios import UserCreate, UserOut
from app.security import get_senha_hash, verificar_senha
from app.database import colecao_usuario, verificadores_professor

router = APIRouter(prefix="/usuario", tags=["Usuários"])

@router.post("/gerar-verificador")
async def gerar_verificador(current_user=Depends(verificar_senha)):
  if current_user["role"] != "admin":
    raise HTTPException(status_code=403, detail="Apenas admins podem gerar verificadores")

  codigo = secrets.token_urlsafe(12)

  await verificadores_professor.insert_one({
    "codigo": codigo,
    "criado_por": current_user["nome_usuario"],
    "usado": False,
    "data_criacao": datetime.utcnow(),
    "data_uso": None
  })

  return {"verificador": codigo}
  

@router.post("/", response_model=UserOut)
async def create_user(user_data: UserCreate):
  existing = await colecao_usuario.find_one({"email": user_data.email})
  if existing:
    raise HTTPException(status_code=400, detail="Email já cadastrado")

  # Verificação de role professor e verificador
  if user_data.role == "professor":
    verificador_doc = await verificadores_professor.find_one({
      "codigo": user_data.verificador,
      "usado": False
    })
    if not verificador_doc:
      raise HTTPException(status_code=400, detail="Verificador inválido ou já usado")
    
    await verificadores_professor.update_one(
      {"_id": verificador_doc["_id"]},
      {"$set": {"usado": True, "data_uso": datetime.utcnow()}}
    )

  senha_hash = get_senha_hash(user_data.senha)

  user_doc = {
    "nome_usuario": user_data.nome_usuario,
    "email": user_data.email,
    "instituicao_ensino": user_data.instituicao_ensino,
    "senha": senha_hash,
    "role": user_data.role,
    "criado_em": datetime.utcnow()
  }

  result = await colecao_usuario.insert_one(user_doc)
  user_doc["id"] = str(result.inserted_id)
  return UserOut(**user_doc)
