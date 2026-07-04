"""Turmas (classes) e Atividades (assignments = pipelines parciais).

- Professor cria turmas, adiciona alunos (seleção ou código de entrada), cria
  atividades (um pipeline PARCIAL que o aluno abre e completa) e acompanha o
  progresso/ranking dos alunos.
- Aluno entra na turma por código, lista as atividades e as realiza (a submissão
  é um pipeline salvo com `atividade_id`/`turma_id`).

Escritas de professor: `exigir_admin_ou_professor`. O router é montado com o
`auth_dependency` global (todo mundo autenticado).
"""
import secrets
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.database import turmas, atividades, pipelines, colecao_usuario, atividade_usuario
from app.schemas.turmas import (
    TurmaCreate, TurmaUpdate, AdicionarAlunos, EntrarTurma,
    AtividadeCreate, AtividadeUpdate,
)
from app.security import get_usuario_atual, exigir_admin_ou_professor
from app.funcoes_genericas.validacao import validar_object_id
from app.funcoes_genericas.funcoes_genericas import converter_numpy

router = APIRouter(prefix="/turmas", tags=["Turmas"])

_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sem 0/O/1/I ambíguos


def _gerar_codigo(n: int = 6) -> str:
    return "".join(secrets.choice(_ALFABETO) for _ in range(n))


async def _codigo_unico() -> str:
    for _ in range(10):
        codigo = _gerar_codigo()
        if not await turmas.find_one({"codigo": codigo}):
            return codigo
    return _gerar_codigo(8)


def _turma_doc(t: dict) -> dict:
    return {
        "id": str(t["_id"]),
        "nome": t.get("nome"),
        "descricao": t.get("descricao"),
        "codigo": t.get("codigo"),
        "professor_id": t.get("professor_id"),
        "alunos": t.get("alunos", []),
        "total_alunos": len(t.get("alunos", [])),
        "criado_em": t.get("criado_em"),
    }


def _atividade_doc(a: dict) -> dict:
    return {
        "id": str(a["_id"]),
        "turma_id": a.get("turma_id"),
        "professor_id": a.get("professor_id"),
        "titulo": a.get("titulo"),
        "descricao": a.get("descricao"),
        "template": a.get("template", {}),
        "criterio": a.get("criterio", {"metrica": "accuracy_score", "ordem": "desc"}),
        "prazo": a.get("prazo"),
        "criado_em": a.get("criado_em"),
    }


async def _turma_do_professor(turma_id: str, professor_id: str) -> dict:
    oid = validar_object_id(turma_id, "turma_id")
    t = await turmas.find_one({"_id": oid, "professor_id": professor_id})
    if not t:
        raise HTTPException(status_code=404, detail="Turma não encontrada.")
    return t


async def _turma_membro(turma_id: str, user_id: str) -> dict:
    """Turma acessível pelo aluno (membro) ou pelo professor dono."""
    oid = validar_object_id(turma_id, "turma_id")
    t = await turmas.find_one({"_id": oid})
    if not t or (t.get("professor_id") != user_id and user_id not in t.get("alunos", [])):
        raise HTTPException(status_code=404, detail="Turma não encontrada.")
    return t


# ---------------------------------------------------------------- Professor: turmas
@router.post("")
@router.post("/")
async def criar_turma(body: TurmaCreate, usuario: dict = Depends(exigir_admin_ou_professor)):
    doc = {
        "professor_id": str(usuario["_id"]),
        "nome": body.nome,
        "descricao": body.descricao,
        "codigo": await _codigo_unico(),
        "alunos": [],
        "criado_em": datetime.now(timezone.utc),
    }
    r = await turmas.insert_one(doc)
    doc["_id"] = r.inserted_id
    return _turma_doc(doc)


@router.get("")
@router.get("/")
async def listar_turmas(usuario: dict = Depends(exigir_admin_ou_professor)):
    cur = turmas.find({"professor_id": str(usuario["_id"])}).sort("criado_em", -1)
    return [_turma_doc(t) async for t in cur]


@router.get("/minhas")
async def turmas_do_aluno(usuario: dict = Depends(get_usuario_atual)):
    """Turmas em que o usuário atual é aluno."""
    uid = str(usuario["_id"])
    cur = turmas.find({"alunos": uid}).sort("criado_em", -1)
    return [{
        "id": str(t["_id"]), "nome": t.get("nome"), "descricao": t.get("descricao"),
        "codigo": t.get("codigo"),
    } async for t in cur]


@router.post("/entrar")
async def entrar_turma(body: EntrarTurma, usuario: dict = Depends(get_usuario_atual)):
    codigo = (body.codigo or "").strip().upper()
    t = await turmas.find_one({"codigo": codigo})
    if not t:
        raise HTTPException(status_code=404, detail="Código de turma inválido.")
    uid = str(usuario["_id"])
    if uid == t.get("professor_id"):
        raise HTTPException(status_code=400, detail="Você é o professor desta turma.")
    await turmas.update_one({"_id": t["_id"]}, {"$addToSet": {"alunos": uid}})
    return {"id": str(t["_id"]), "nome": t.get("nome")}


@router.get("/{turma_id}")
async def obter_turma(turma_id: str, usuario: dict = Depends(get_usuario_atual)):
    t = await _turma_membro(turma_id, str(usuario["_id"]))
    doc = _turma_doc(t)
    # nomes dos alunos (só p/ o professor dono)
    if t.get("professor_id") == str(usuario["_id"]):
        alunos = []
        for aid in t.get("alunos", []):
            try:
                u = await colecao_usuario.find_one({"_id": ObjectId(aid)})
            except Exception:
                u = None
            alunos.append({"id": aid, "nome": (u or {}).get("nome_usuario") or (u or {}).get("nome"),
                           "email": (u or {}).get("email")})
        doc["alunos_detalhe"] = alunos
    return doc


@router.put("/{turma_id}")
async def atualizar_turma(turma_id: str, body: TurmaUpdate, usuario: dict = Depends(exigir_admin_ou_professor)):
    t = await _turma_do_professor(turma_id, str(usuario["_id"]))
    campos = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if campos:
        await turmas.update_one({"_id": t["_id"]}, {"$set": campos})
    return _turma_doc({**t, **campos})


@router.delete("/{turma_id}")
async def excluir_turma(turma_id: str, usuario: dict = Depends(exigir_admin_ou_professor)):
    t = await _turma_do_professor(turma_id, str(usuario["_id"]))
    await atividades.delete_many({"turma_id": str(t["_id"])})
    await turmas.delete_one({"_id": t["_id"]})
    return {"mensagem": "Turma excluída."}


# ---------------------------------------------------------------- Professor: alunos
@router.post("/{turma_id}/alunos")
async def adicionar_alunos(turma_id: str, body: AdicionarAlunos, usuario: dict = Depends(exigir_admin_ou_professor)):
    t = await _turma_do_professor(turma_id, str(usuario["_id"]))
    ids = []
    for ref in body.alunos:
        ref = (ref or "").strip()
        if not ref:
            continue
        u = None
        if "@" in ref:
            u = await colecao_usuario.find_one({"email": ref})
        else:
            try:
                u = await colecao_usuario.find_one({"_id": ObjectId(ref)})
            except Exception:
                u = None
        if u:
            ids.append(str(u["_id"]))
    if ids:
        await turmas.update_one({"_id": t["_id"]}, {"$addToSet": {"alunos": {"$each": ids}}})
    novo = await turmas.find_one({"_id": t["_id"]})
    return _turma_doc(novo)


@router.delete("/{turma_id}/alunos/{aluno_id}")
async def remover_aluno(turma_id: str, aluno_id: str, usuario: dict = Depends(exigir_admin_ou_professor)):
    t = await _turma_do_professor(turma_id, str(usuario["_id"]))
    await turmas.update_one({"_id": t["_id"]}, {"$pull": {"alunos": aluno_id}})
    return {"mensagem": "Aluno removido."}


# ---------------------------------------------------------------- Atividades
@router.post("/{turma_id}/atividades")
async def criar_atividade(turma_id: str, body: AtividadeCreate, usuario: dict = Depends(exigir_admin_ou_professor)):
    t = await _turma_do_professor(turma_id, str(usuario["_id"]))
    doc = {
        "turma_id": str(t["_id"]),
        "professor_id": str(usuario["_id"]),
        "titulo": body.titulo,
        "descricao": body.descricao,
        "template": body.template or {},
        "criterio": body.criterio.model_dump(),
        "prazo": body.prazo,
        "criado_em": datetime.now(timezone.utc),
    }
    r = await atividades.insert_one(doc)
    doc["_id"] = r.inserted_id
    return _atividade_doc(doc)


@router.get("/{turma_id}/atividades")
async def listar_atividades(turma_id: str, usuario: dict = Depends(get_usuario_atual)):
    t = await _turma_membro(turma_id, str(usuario["_id"]))
    cur = atividades.find({"turma_id": str(t["_id"])}).sort("criado_em", -1)
    return [_atividade_doc(a) async for a in cur]


@router.put("/{turma_id}/atividades/{atividade_id}")
async def atualizar_atividade(turma_id: str, atividade_id: str, body: AtividadeUpdate,
                              usuario: dict = Depends(exigir_admin_ou_professor)):
    await _turma_do_professor(turma_id, str(usuario["_id"]))
    aoid = validar_object_id(atividade_id, "atividade_id")
    campos = body.model_dump(exclude_none=True)
    if "criterio" in campos and campos["criterio"] is not None:
        campos["criterio"] = campos["criterio"]
    if campos:
        await atividades.update_one({"_id": aoid, "turma_id": turma_id}, {"$set": campos})
    a = await atividades.find_one({"_id": aoid})
    if not a:
        raise HTTPException(status_code=404, detail="Atividade não encontrada.")
    return _atividade_doc(a)


@router.delete("/{turma_id}/atividades/{atividade_id}")
async def excluir_atividade(turma_id: str, atividade_id: str, usuario: dict = Depends(exigir_admin_ou_professor)):
    await _turma_do_professor(turma_id, str(usuario["_id"]))
    aoid = validar_object_id(atividade_id, "atividade_id")
    await atividades.delete_one({"_id": aoid, "turma_id": turma_id})
    return {"mensagem": "Atividade excluída."}


@router.get("/{turma_id}/atividades/{atividade_id}")
async def obter_atividade(turma_id: str, atividade_id: str, usuario: dict = Depends(get_usuario_atual)):
    """Aluno (membro) abre o template da atividade para realizá-la."""
    await _turma_membro(turma_id, str(usuario["_id"]))
    aoid = validar_object_id(atividade_id, "atividade_id")
    a = await atividades.find_one({"_id": aoid, "turma_id": turma_id})
    if not a:
        raise HTTPException(status_code=404, detail="Atividade não encontrada.")
    return _atividade_doc(a)


def _valor_metrica(resultados: dict, metrica: str, ordem: str):
    """Melhor valor escalar da `metrica` entre os modelos avaliados (por `ordem`)."""
    por_modelo = (resultados or {}).get(metrica) or {}
    valores = [v for v in por_modelo.values() if isinstance(v, (int, float))]
    if not valores:
        return None
    return max(valores) if ordem != "asc" else min(valores)


@router.get("/{turma_id}/atividades/{atividade_id}/ranking")
async def ranking_atividade(turma_id: str, atividade_id: str, usuario: dict = Depends(exigir_admin_ou_professor)):
    await _turma_do_professor(turma_id, str(usuario["_id"]))
    aoid = validar_object_id(atividade_id, "atividade_id")
    a = await atividades.find_one({"_id": aoid, "turma_id": turma_id})
    if not a:
        raise HTTPException(status_code=404, detail="Atividade não encontrada.")
    criterio = a.get("criterio") or {}
    metrica = criterio.get("metrica", "accuracy_score")
    ordem = criterio.get("ordem", "desc")

    linhas = []
    async for p in pipelines.find({"atividade_id": atividade_id}):
        valor = _valor_metrica(p.get("resultadosDasAvaliacoes"), metrica, ordem)
        aluno_id = p.get("user_id")
        u = None
        try:
            u = await colecao_usuario.find_one({"_id": ObjectId(aluno_id)}) if aluno_id else None
        except Exception:
            u = None
        linhas.append({
            "aluno_id": aluno_id,
            "aluno_nome": (u or {}).get("nome_usuario") or (u or {}).get("nome") or "—",
            "pipeline_id": str(p["_id"]),
            "pipeline_nome": p.get("nome"),
            "valor": valor,
        })
    com_valor = [l for l in linhas if l["valor"] is not None]
    com_valor.sort(key=lambda l: l["valor"], reverse=(ordem != "asc"))
    sem_valor = [l for l in linhas if l["valor"] is None]
    return converter_numpy({"metrica": metrica, "ordem": ordem, "ranking": com_valor + sem_valor})


@router.get("/{turma_id}/progresso")
async def progresso_turma(turma_id: str, usuario: dict = Depends(exigir_admin_ou_professor)):
    t = await _turma_do_professor(turma_id, str(usuario["_id"]))
    total_atividades = await atividades.count_documents({"turma_id": str(t["_id"])})
    linhas = []
    for aid in t.get("alunos", []):
        u = None
        try:
            u = await colecao_usuario.find_one({"_id": ObjectId(aid)})
        except Exception:
            u = None
        submissoes = await pipelines.count_documents({"turma_id": str(t["_id"]), "user_id": aid})
        chats = await atividade_usuario.count_documents({"usuario_id": aid, "tipo": "chat"})
        ultimo = await atividade_usuario.find({"usuario_id": aid}).sort("timestamp", -1).limit(1).to_list(1)
        linhas.append({
            "aluno_id": aid,
            "aluno_nome": (u or {}).get("nome_usuario") or (u or {}).get("nome") or "—",
            "email": (u or {}).get("email"),
            "submissoes": submissoes,
            "total_atividades": total_atividades,
            "chats": chats,
            "ultimo_acesso": ultimo[0]["timestamp"] if ultimo else None,
        })
    return converter_numpy({"turma": _turma_doc(t), "total_atividades": total_atividades, "alunos": linhas})
