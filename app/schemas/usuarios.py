from pydantic import BaseModel, EmailStr, validator, Field
from typing import Optional
from bson import ObjectId

class UserCreate(BaseModel):
    nome_usuario: str
    email: EmailStr
    senha: str
    instituicao_ensino: str
    role: str
    verificador: Optional[str] = None

    @validator("verificador", always=True)
    def verificador_obrigatorio_para_professor(cls, v, values):
        if values.get("role") == "professor" and not v:
            raise ValueError("Verificador é obrigatório para role 'professor'")
        return v

    @validator("role")
    def proibir_admin_autocadastro(cls, role):
        if role == "admin":
            raise ValueError("Role 'admin' não pode ser usada em cadastro público")
        return role

class UserOut(BaseModel):
    id: str
    nome_usuario: str
    email: EmailStr
    role: str

class UsuarioResponse(BaseModel):
    id: str = Field(..., alias="_id")
    email: str
    nome_usuario: str  
    role: str

    class Config:
        populate_by_name = True
        json_encoders = {
            ObjectId: str
        }
