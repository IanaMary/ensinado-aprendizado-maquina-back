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

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.database import (
    turmas, atividades, pipelines, colecao_usuario, atividade_usuario, opcoes_metricas,
)
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


def _nome_usuario(u: dict | None) -> str:
    """Nome de exibição do aluno, com fallback consistente."""
    u = u or {}
    return u.get("nome_usuario") or u.get("nome") or "—"


async def _mapa_usuarios(ids: list) -> dict:
    """Busca vários usuários por id em UMA query (evita N+1). Retorna {id_str: doc}."""
    oids = []
    for aid in ids or []:
        try:
            oids.append(ObjectId(aid))
        except Exception:
            continue
    if not oids:
        return {}
    mapa = {}
    async for u in colecao_usuario.find({"_id": {"$in": oids}}):
        mapa[str(u["_id"])] = u
    return mapa


async def _chaves_metrica(slug: str) -> list:
    """Chaves candidatas p/ ler `resultadosDasAvaliacoes`.

    A avaliação (app/metricas/metricas.py) indexa o dict pelo RÓTULO da métrica
    (ex.: 'Acurácia'), mas o critério da atividade guarda o `valor`/slug
    (ex.: 'accuracy_score'). Resolvemos o rótulo em `db.metricas` e tentamos
    ambos, para ser robusto a como a submissão foi salva.
    """
    chaves = [slug]
    try:
        doc = await opcoes_metricas.find_one({"valor": slug})
        rotulo = (doc or {}).get("label")
        if rotulo and rotulo not in chaves:
            chaves.append(rotulo)
    except Exception:
        pass
    return chaves


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
    # nomes dos alunos (só p/ o professor dono) — 1 query em lote (evita N+1).
    if t.get("professor_id") == str(usuario["_id"]):
        usuarios = await _mapa_usuarios(t.get("alunos", []))
        doc["alunos_detalhe"] = [
            {"id": aid, "nome": (usuarios.get(aid) or {}).get("nome_usuario") or (usuarios.get(aid) or {}).get("nome"),
             "email": (usuarios.get(aid) or {}).get("email")}
            for aid in t.get("alunos", [])
        ]
    return doc


@router.put("/{turma_id}")
async def atualizar_turma(turma_id: str, body: TurmaUpdate, usuario: dict = Depends(exigir_admin_ou_professor)):
    t = await _turma_do_professor(turma_id, str(usuario["_id"]))
    campos = body.model_dump(exclude_none=True)
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
    validar_object_id(aluno_id, "aluno_id")  # os ids em `alunos` são str(ObjectId)
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
    campos = body.model_dump(exclude_none=True)  # CriterioRanking já vira dict aqui
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


def _valor_metrica(resultados: dict, chaves: list, ordem: str):
    """Melhor valor escalar da métrica (por qualquer uma das `chaves`) entre os
    modelos avaliados, escolhido por `ordem` (desc = maior é melhor)."""
    resultados = resultados or {}
    por_modelo = {}
    for chave in chaves:
        por_modelo = resultados.get(chave) or {}
        if por_modelo:
            break
    valores = [v for v in por_modelo.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
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
    chaves = await _chaves_metrica(metrica)

    # projeção: não trazer resultadoColetaDado (pode ser enorme) — só o necessário.
    proj = {"resultadosDasAvaliacoes": 1, "user_id": 1, "nome": 1}
    # melhor submissão POR ALUNO (evita linhas duplicadas quando o aluno salva várias vezes).
    melhor: dict = {}
    async for p in pipelines.find({"atividade_id": atividade_id}, proj):
        aluno_id = p.get("user_id")
        valor = _valor_metrica(p.get("resultadosDasAvaliacoes"), chaves, ordem)
        atual = melhor.get(aluno_id)
        linha = {"aluno_id": aluno_id, "pipeline_id": str(p["_id"]),
                 "pipeline_nome": p.get("nome"), "valor": valor}
        if atual is None:
            melhor[aluno_id] = linha
        elif valor is not None and (atual["valor"] is None or
                                    (valor > atual["valor"] if ordem != "asc" else valor < atual["valor"])):
            melhor[aluno_id] = linha

    usuarios = await _mapa_usuarios(list(melhor.keys()))
    linhas = []
    for aluno_id, l in melhor.items():
        l["aluno_nome"] = _nome_usuario(usuarios.get(aluno_id))
        linhas.append(l)
    com_valor = [l for l in linhas if l["valor"] is not None]
    com_valor.sort(key=lambda l: l["valor"], reverse=(ordem != "asc"))
    sem_valor = [l for l in linhas if l["valor"] is None]
    return converter_numpy({"metrica": metrica, "ordem": ordem, "ranking": com_valor + sem_valor})


@router.get("/{turma_id}/progresso")
async def progresso_turma(turma_id: str, usuario: dict = Depends(exigir_admin_ou_professor)):
    t = await _turma_do_professor(turma_id, str(usuario["_id"]))
    tid = str(t["_id"])
    alunos = t.get("alunos", [])
    total_atividades = await atividades.count_documents({"turma_id": tid})

    usuarios = await _mapa_usuarios(alunos)

    # Submissões e último acesso ESCOPADOS À TURMA (via pipelines desta turma), 1 agregação.
    # submissoes = nº de atividades DISTINTAS submetidas (não conta re-salvamentos).
    por_aluno: dict = {}
    try:
        cur = pipelines.aggregate([
            {"$match": {"turma_id": tid, "user_id": {"$in": alunos}}},
            {"$group": {"_id": "$user_id",
                        "atividades": {"$addToSet": "$atividade_id"},
                        "ultimo": {"$max": "$dataModificacao"}}},
        ])
        for row in await cur.to_list(length=None):
            por_aluno[row["_id"]] = {
                "submissoes": len([a for a in (row.get("atividades") or []) if a]),
                "ultimo_acesso": row.get("ultimo"),
            }
    except Exception:
        por_aluno = {}

    # Uso do tutor (chat) por aluno da turma, 1 agregação. É o total do aluno (a
    # telemetria não guarda turma no evento); serve como sinal de engajamento.
    chats_por_aluno: dict = {}
    try:
        cur = atividade_usuario.aggregate([
            {"$match": {"usuario_id": {"$in": alunos}, "tipo": "chat"}},
            {"$group": {"_id": "$usuario_id", "chats": {"$sum": 1}}},
        ])
        for row in await cur.to_list(length=None):
            chats_por_aluno[row["_id"]] = row.get("chats", 0)
    except Exception:
        chats_por_aluno = {}

    linhas = []
    for aid in alunos:
        u = usuarios.get(aid)
        agg = por_aluno.get(aid, {})
        linhas.append({
            "aluno_id": aid,
            "aluno_nome": _nome_usuario(u),
            "email": (u or {}).get("email"),
            "submissoes": agg.get("submissoes", 0),
            "total_atividades": total_atividades,
            "chats": chats_por_aluno.get(aid, 0),
            "ultimo_acesso": agg.get("ultimo_acesso"),
        })
    return converter_numpy({"turma": _turma_doc(t), "total_atividades": total_atividades, "alunos": linhas})
