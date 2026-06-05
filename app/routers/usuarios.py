from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List, Optional
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

from app.schemas.usuarios import UserCreate, UserOut, UserInvite, UserInviteResponse
from app.security import get_senha_hash, verificar_senha, get_usuario_atual
from app.database import colecao_usuario, verificadores_professor

router = APIRouter(prefix="/usuario", tags=["Usuários"])

# Configurações de email (em produção, usar variáveis de ambiente)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@iana.com")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://absapt.tk/h2ia/tutor")


async def enviar_email(destinatario: str, assunto: str, corpo_html: str):
    """Envia email usando SMTP."""
    try:
        if not SMTP_USER or not SMTP_PASSWORD:
            print(f"[DEV] Email não enviado (SMTP não configurado): {destinatario}")
            print(f"[DEV] Assunto: {assunto}")
            return False  # Retorna False para indicar que email não foi enviado

        msg = MIMEMultipart('alternative')
        msg['Subject'] = assunto
        msg['From'] = EMAIL_FROM
        msg['To'] = destinatario

        html_part = MIMEText(corpo_html, 'html')
        msg.attach(html_part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        return True
    except Exception as e:
        print(f"Erro ao enviar email: {e}")
        return False


def gerar_email_convite(nome: str, token: str) -> str:
    """Gera o HTML do email de convite."""
    link_ativacao = f"{FRONTEND_URL}/ativar-conta?token={token}"
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #4A0E8F, #6A0DAD); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .header h1 {{ margin: 0; font-size: 24px; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .button {{ display: inline-block; background: #4A0E8F; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 20px 0; }}
            .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎓 Iana - Plataforma de ML</h1>
            </div>
            <div class="content">
                <h2>Olá, {nome}!</h2>
                <p>Você foi convidado a fazer parte da plataforma Iana, uma ferramenta interativa para aprendizado de Machine Learning.</p>
                <p>Para criar sua senha e começar a usar a plataforma, clique no botão abaixo:</p>
                <p style="text-align: center;">
                    <a href="{link_ativacao}" class="button">Criar Minha Senha</a>
                </p>
                <p>Ou copie e cole o link abaixo no seu navegador:</p>
                <p style="word-break: break-all; background: #eee; padding: 10px; border-radius: 4px; font-size: 12px;">
                    {link_ativacao}
                </p>
                <p><strong>Este link é válido por 7 dias.</strong></p>
                <p>Se você não esperava este convite, ignore este email.</p>
            </div>
            <div class="footer">
                <p>© 2024 Iana - Plataforma de Ensino de Machine Learning</p>
            </div>
        </div>
    </body>
    </html>
    """


@router.post("/gerar-verificador")
async def gerar_verificador(current_user=Depends(get_usuario_atual)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Apenas admins podem gerar verificadores")

    codigo = secrets.token_urlsafe(12)

    await verificadores_professor.insert_one({
        "codigo": codigo,
        "criado_por": current_user["nome_usuario"],
        "usado": False,
        "data_criacao": datetime.now(timezone.utc),
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
            {"$set": {"usado": True, "data_uso": datetime.now(timezone.utc)}}
        )

    senha_hash = get_senha_hash(user_data.senha)

    user_doc = {
        "nome_usuario": user_data.nome_usuario,
        "email": user_data.email,
        "instituicao_ensino": user_data.instituicao_ensino,
        "senha": senha_hash,
        "role": user_data.role,
        "criado_em": datetime.now(timezone.utc)
    }

    result = await colecao_usuario.insert_one(user_doc)
    user_doc["id"] = str(result.inserted_id)
    return UserOut(**user_doc)


@router.post("/convite", response_model=UserInviteResponse)
async def criar_convite(convite_data: UserInvite, current_user=Depends(get_usuario_atual)):
    """Cria um novo usuário e envia convite por email."""
    # Verificar se é admin
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Apenas admins podem criar convites")
    
    # Verificar se email já existe
    existing = await colecao_usuario.find_one({"email": convite_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    
    # Gerar token de convite
    token = secrets.token_urlsafe(32)
    
    # Criar usuário com status pendente
    user_doc = {
        "nome_usuario": convite_data.nome,
        "email": convite_data.email,
        "role": convite_data.tipo,
        "status": "pendente",
        "token_convite": token,
        "data_convite": datetime.now(timezone.utc),
        "data_ativacao": None,
        "ultimo_acesso": None,
        "senha": None,  # Senha será definida na ativação
        "criado_por": current_user["nome_usuario"],
        "criado_em": datetime.now(timezone.utc)
    }
    
    result = await colecao_usuario.insert_one(user_doc)
    
    # Enviar email de convite
    link_convite = f"{FRONTEND_URL}/ativar-conta?token={token}"
    corpo_html = gerar_email_convite(convite_data.nome, token)
    email_enviado = await enviar_email(
        convite_data.email,
        "Convite para a plataforma Iana",
        corpo_html
    )
    
    return UserInviteResponse(
        id=str(result.inserted_id),
        nome=convite_data.nome,
        email=convite_data.email,
        tipo=convite_data.tipo,
        status="pendente",
        data_convite=user_doc["data_convite"],
        email_enviado=email_enviado,
        link_convite=link_convite if not email_enviado else None
    )


@router.get("/", response_model=List[UserInviteResponse])
async def listar_usuarios(current_user=Depends(get_usuario_atual)):
    """Lista todos os usuários (apenas admin)."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Apenas admins podem listar usuários")
    
    usuarios = []
    async for user in colecao_usuario.find().sort("criado_em", -1):
        usuarios.append(UserInviteResponse(
            id=str(user["_id"]),
            nome=user["nome_usuario"],
            email=user["email"],
            tipo=user["role"],
            status=user.get("status", "ativo"),
            data_convite=user.get("data_convite"),
            data_ativacao=user.get("data_ativacao"),
            ultimo_acesso=user.get("ultimo_acesso"),
            email_enviado=True
        ))
    
    return usuarios


@router.put("/{user_id}/status")
async def alterar_status_usuario(user_id: str, novo_status: str, current_user=Depends(get_usuario_atual)):
    """Altera o status de um usuário (apenas admin)."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Apenas admins podem alterar status")
    
    if novo_status not in ["ativo", "inativo", "pendente"]:
        raise HTTPException(status_code=400, detail="Status inválido")
    
    from bson import ObjectId
    
    try:
        result = await colecao_usuario.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"status": novo_status}}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
        return {"mensagem": f"Status alterado para {novo_status}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="ID inválido")


@router.post("/{user_id}/reenviar-convite")
async def reenviar_convite(user_id: str, current_user=Depends(get_usuario_atual)):
    """Reenvia o convite por email (apenas admin). Mantém o mesmo token e data_convite originais."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Apenas admins podem reenviar convites")

    from bson import ObjectId

    try:
        user = await colecao_usuario.find_one({"_id": ObjectId(user_id)})

        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        if user.get("status") != "pendente":
            raise HTTPException(status_code=400, detail="Usuário já está ativo")

        token = user.get("token_convite")
        if not token:
            raise HTTPException(status_code=400, detail="Token de convite não encontrado")

        # Enviar email com o mesmo token (data_convite original é mantida)
        corpo_html = gerar_email_convite(user["nome_usuario"], token)
        email_enviado = await enviar_email(
            user["email"],
            "Convite para a plataforma Iana - Reenvio",
            corpo_html
        )

        return {"mensagem": "Convite reenviado", "email_enviado": email_enviado}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail="ID inválido")


@router.delete("/{user_id}")
async def excluir_usuario(user_id: str, current_user=Depends(get_usuario_atual)):
    """Exclui um usuário (apenas admin)."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Apenas admins podem excluir usuários")
    
    from bson import ObjectId
    
    try:
        result = await colecao_usuario.delete_one({"_id": ObjectId(user_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
        return {"mensagem": "Usuário excluído com sucesso"}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail="ID inválido")
