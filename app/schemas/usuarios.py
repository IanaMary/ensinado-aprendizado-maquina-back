from pydantic import BaseModel, EmailStr, validator, Field
from typing import Optional
from datetime import datetime
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

class UserInvite(BaseModel):
    nome: str
    email: EmailStr
    tipo: str = "aluno"

    @validator("tipo")
    def validar_tipo(cls, v):
        if v not in ["aluno", "professor", "admin"]:
            raise ValueError("Tipo deve ser 'aluno', 'professor' ou 'admin'")
        return v

class UserInviteResponse(BaseModel):
    id: str
    nome: str
    email: str
    tipo: str
    status: str
    data_convite: Optional[datetime] = None
    data_ativacao: Optional[datetime] = None
    ultimo_acesso: Optional[datetime] = None
    email_enviado: bool = False
    link_convite: Optional[str] = None  # Link para compartilhar manualmente

class UserActivate(BaseModel):
    senha: str
    confirmar_senha: str

    @validator("confirmar_senha")
    def senhas_devem_iguais(cls, v, values):
        if "senha" in values and v != values["senha"]:
            raise ValueError("As senhas não coincidem")
        return v
