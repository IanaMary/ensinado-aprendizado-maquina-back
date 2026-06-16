import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from bson import ObjectId

from app.database import db, colecao_usuario, pipelines
from app.security import get_usuario_atual

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

admin_log = db["admin_log"]


async def registrar_log_admin(
    usuario: dict,
    acao: str,
    detalhes: str = "",
):
    try:
        await admin_log.insert_one({
            "usuario_id": str(usuario.get("_id") or usuario.get("id") or ""),
            "usuario_email": usuario.get("email", ""),
            "usuario_nome": usuario.get("nome") or usuario.get("name") or usuario.get("email", ""),
            "acao": acao,
            "detalhes": detalhes,
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.warning("Falha ao registrar log admin: %s", e)


@router.get("/log")
async def listar_log(
    limite: int = Query(50, ge=1, le=200),
    pagina: int = Query(1, ge=1),
    usuario: dict = Depends(get_usuario_atual),
):
    if usuario.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admins podem acessar o log")

    skip = (pagina - 1) * limite
    cursor = admin_log.find().sort("timestamp", -1).skip(skip).limit(limite)
    documentos = await cursor.to_list(length=limite)
    total = await admin_log.count_documents({})

    return {
        "items": [
            {
                "id": str(doc["_id"]),
                "usuario_id": doc.get("usuario_id", ""),
                "usuario_email": doc.get("usuario_email", ""),
                "usuario_nome": doc.get("usuario_nome", ""),
                "acao": doc.get("acao", ""),
                "detalhes": doc.get("detalhes", ""),
                "timestamp": doc.get("timestamp", ""),
            }
            for doc in documentos
        ],
        "total": total,
        "pagina": pagina,
        "limite": limite,
    }


@router.get("/export/usuarios")
async def exportar_usuarios(usuario: dict = Depends(get_usuario_atual)):
    if usuario.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admins podem exportar dados")

    await registrar_log_admin(usuario, "exportar_usuarios", "Exportação CSV de usuários")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "nome_usuario", "email", "role", "status", "criado_em", "ultimo_acesso"])

    async for user in colecao_usuario.find():
        writer.writerow([
            str(user.get("_id", "")),
            user.get("nome_usuario", ""),
            user.get("email", ""),
            user.get("role", ""),
            user.get("status", "ativo"),
            str(user.get("criado_em", "")),
            str(user.get("ultimo_acesso", "")),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=usuarios.csv"},
    )


@router.get("/export/pipelines")
async def exportar_pipelines(usuario: dict = Depends(get_usuario_atual)):
    if usuario.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admins podem exportar dados")

    await registrar_log_admin(usuario, "exportar_pipelines", "Exportação CSV de pipelines")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "nome", "criado_por", "criado_em", "modelo", "status"])

    async for p in pipelines.find():
        writer.writerow([
            str(p.get("_id", "")),
            p.get("nome", ""),
            p.get("criado_por", ""),
            str(p.get("criado_em", "")),
            p.get("modelo", ""),
            p.get("status", ""),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=pipelines.csv"},
    )
