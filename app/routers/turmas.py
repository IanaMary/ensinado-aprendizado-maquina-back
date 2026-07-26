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
    turmas, atividades, pipelines, colecao_usuario, atividade_usuario,
    submissoes_montagem,
)
from app.desafios import avaliar_montagem, carregar_pecas, montar_tabuleiro
from app.desafios.avaliacao import normalizar_montagem
from app.desafios.sorteio import papeis
from app.metricas.resultado import chaves_metrica, valor_metrica
from app.schemas.turmas import (
    TurmaCreate, TurmaUpdate, AdicionarAlunos, EntrarTurma,
    AtividadeCreate, AtividadeUpdate, SubmeterMontagem, GabaritoMontagem,
)
from app.security import get_usuario_atual, exigir_admin_ou_professor
from app.funcoes_genericas.validacao import validar_object_id
from app.funcoes_genericas.funcoes_genericas import converter_numpy

router = APIRouter(prefix="/turmas", tags=["Turmas"])

_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sem 0/O/1/I ambíguos

# Tipos de atividade. `pipeline` é o histórico (aluno completa e executa um pipeline real);
# `montagem` é o desafio de quebra-cabeça, corrigido por rubrica sem executar nada.
TIPO_PIPELINE = "pipeline"
TIPO_MONTAGEM = "montagem"


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


# Leitura dos resultados vive em `app/metricas/resultado.py` (compartilhada com a evolução
# do aluno). Os aliases mantêm os nomes usados aqui e nos testes.
_chaves_metrica = chaves_metrica
_valor_metrica = valor_metrica


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


def _atividade_doc(a: dict, incluir_gabarito: bool = False) -> dict:
    """Atividade serializada. O `gabarito` do desafio SÓ sai com `incluir_gabarito`
    (professor/admin da turma): para o aluno ele é a resposta da prova."""
    doc = {
        "id": str(a["_id"]),
        "turma_id": a.get("turma_id"),
        "professor_id": a.get("professor_id"),
        "titulo": a.get("titulo"),
        "descricao": a.get("descricao"),
        "tipo": a.get("tipo") or TIPO_PIPELINE,
        "template": a.get("template", {}),
        "criterio": a.get("criterio", {"metrica": "accuracy_score", "ordem": "desc"}),
        "prazo": a.get("prazo"),
        "criado_em": a.get("criado_em"),
    }
    if incluir_gabarito:
        doc["gabarito"] = a.get("gabarito") or {}
    return doc


def _pode_gerenciar(t: dict, usuario: dict) -> bool:
    """Professor dono da turma ou admin — quem pode ver gabarito e ranking."""
    uid = str((usuario or {}).get("_id"))
    return (usuario or {}).get("role") == "admin" or t.get("professor_id") == uid


async def _turma_do_professor(turma_id: str, usuario: dict) -> dict:
    """Turma que o usuário pode gerenciar: o professor DONO ou qualquer ADMIN
    (supervisão global). Levanta 404 caso contrário."""
    oid = validar_object_id(turma_id, "turma_id")
    filtro = {"_id": oid}
    if (usuario or {}).get("role") != "admin":
        filtro["professor_id"] = str(usuario["_id"])
    t = await turmas.find_one(filtro)
    if not t:
        raise HTTPException(status_code=404, detail="Turma não encontrada.")
    return t


async def _turma_membro(turma_id: str, usuario: dict) -> dict:
    """Turma acessível pelo aluno (membro), pelo professor dono ou por admin."""
    oid = validar_object_id(turma_id, "turma_id")
    t = await turmas.find_one({"_id": oid})
    uid = str(usuario["_id"])
    if not t or not (usuario.get("role") == "admin"
                     or t.get("professor_id") == uid
                     or uid in t.get("alunos", [])):
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
    # Admin supervisiona TODAS as turmas; professor vê apenas as suas.
    filtro = {} if usuario.get("role") == "admin" else {"professor_id": str(usuario["_id"])}
    cur = turmas.find(filtro).sort("criado_em", -1)
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
    is_admin = usuario.get("role") == "admin"
    if is_admin:
        oid = validar_object_id(turma_id, "turma_id")
        t = await turmas.find_one({"_id": oid})
        if not t:
            raise HTTPException(status_code=404, detail="Turma não encontrada.")
    else:
        t = await _turma_membro(turma_id, usuario)
    doc = _turma_doc(t)
    # nomes dos alunos (professor dono ou admin) — 1 query em lote (evita N+1).
    if is_admin or t.get("professor_id") == str(usuario["_id"]):
        usuarios = await _mapa_usuarios(t.get("alunos", []))
        doc["alunos_detalhe"] = [
            {"id": aid, "nome": (usuarios.get(aid) or {}).get("nome_usuario") or (usuarios.get(aid) or {}).get("nome"),
             "email": (usuarios.get(aid) or {}).get("email")}
            for aid in t.get("alunos", [])
        ]
    return doc


@router.put("/{turma_id}")
async def atualizar_turma(turma_id: str, body: TurmaUpdate, usuario: dict = Depends(exigir_admin_ou_professor)):
    t = await _turma_do_professor(turma_id, usuario)
    campos = body.model_dump(exclude_none=True)
    if campos:
        await turmas.update_one({"_id": t["_id"]}, {"$set": campos})
    return _turma_doc({**t, **campos})


@router.delete("/{turma_id}")
async def excluir_turma(turma_id: str, usuario: dict = Depends(exigir_admin_ou_professor)):
    t = await _turma_do_professor(turma_id, usuario)
    await atividades.delete_many({"turma_id": str(t["_id"])})
    await turmas.delete_one({"_id": t["_id"]})
    return {"mensagem": "Turma excluída."}


# ---------------------------------------------------------------- Professor: alunos
@router.post("/{turma_id}/alunos")
async def adicionar_alunos(turma_id: str, body: AdicionarAlunos, usuario: dict = Depends(exigir_admin_ou_professor)):
    t = await _turma_do_professor(turma_id, usuario)
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
    t = await _turma_do_professor(turma_id, usuario)
    validar_object_id(aluno_id, "aluno_id")  # os ids em `alunos` são str(ObjectId)
    await turmas.update_one({"_id": t["_id"]}, {"$pull": {"alunos": aluno_id}})
    return {"mensagem": "Aluno removido."}


# ---------------------------------------------------------------- Atividades
@router.post("/{turma_id}/atividades")
async def criar_atividade(turma_id: str, body: AtividadeCreate, usuario: dict = Depends(exigir_admin_ou_professor)):
    t = await _turma_do_professor(turma_id, usuario)
    tipo = body.tipo if body.tipo in (TIPO_PIPELINE, TIPO_MONTAGEM) else TIPO_PIPELINE
    doc = {
        "turma_id": str(t["_id"]),
        "professor_id": str(usuario["_id"]),
        "titulo": body.titulo,
        "descricao": body.descricao,
        "tipo": tipo,
        "template": body.template or {},
        "criterio": body.criterio.model_dump(),
        "prazo": body.prazo,
        "criado_em": datetime.now(timezone.utc),
    }
    if tipo == TIPO_MONTAGEM:
        doc["gabarito"] = (body.gabarito.model_dump() if body.gabarito
                           else GabaritoMontagem().model_dump())
    r = await atividades.insert_one(doc)
    doc["_id"] = r.inserted_id
    return _atividade_doc(doc, incluir_gabarito=True)


@router.get("/{turma_id}/atividades")
async def listar_atividades(turma_id: str, usuario: dict = Depends(get_usuario_atual)):
    t = await _turma_membro(turma_id, usuario)
    gerencia = _pode_gerenciar(t, usuario)  # professor precisa do gabarito para editar
    cur = atividades.find({"turma_id": str(t["_id"])}).sort("criado_em", -1)
    return [_atividade_doc(a, incluir_gabarito=gerencia) async for a in cur]


@router.put("/{turma_id}/atividades/{atividade_id}")
async def atualizar_atividade(turma_id: str, atividade_id: str, body: AtividadeUpdate,
                              usuario: dict = Depends(exigir_admin_ou_professor)):
    await _turma_do_professor(turma_id, usuario)
    aoid = validar_object_id(atividade_id, "atividade_id")
    campos = body.model_dump(exclude_none=True)  # CriterioRanking já vira dict aqui
    if campos:
        await atividades.update_one({"_id": aoid, "turma_id": turma_id}, {"$set": campos})
    a = await atividades.find_one({"_id": aoid})
    if not a:
        raise HTTPException(status_code=404, detail="Atividade não encontrada.")
    return _atividade_doc(a, incluir_gabarito=True)


@router.delete("/{turma_id}/atividades/{atividade_id}")
async def excluir_atividade(turma_id: str, atividade_id: str, usuario: dict = Depends(exigir_admin_ou_professor)):
    await _turma_do_professor(turma_id, usuario)
    aoid = validar_object_id(atividade_id, "atividade_id")
    await atividades.delete_one({"_id": aoid, "turma_id": turma_id})
    return {"mensagem": "Atividade excluída."}


@router.get("/{turma_id}/atividades/{atividade_id}")
async def obter_atividade(turma_id: str, atividade_id: str, usuario: dict = Depends(get_usuario_atual)):
    """Aluno (membro) abre o template da atividade para realizá-la."""
    t = await _turma_membro(turma_id, usuario)
    aoid = validar_object_id(atividade_id, "atividade_id")
    a = await atividades.find_one({"_id": aoid, "turma_id": turma_id})
    if not a:
        raise HTTPException(status_code=404, detail="Atividade não encontrada.")
    return _atividade_doc(a, incluir_gabarito=_pode_gerenciar(t, usuario))


# ------------------------------------------------- Desafio de montagem (quebra-cabeça)
async def _atividade_de_montagem(turma_id: str, atividade_id: str, usuario: dict) -> tuple[dict, dict]:
    """Turma (como membro) + atividade do tipo `montagem`. 404 se não for desse tipo, para
    não vazar a existência de outra atividade por mensagem de erro."""
    t = await _turma_membro(turma_id, usuario)
    aoid = validar_object_id(atividade_id, "atividade_id")
    a = await atividades.find_one({"_id": aoid, "turma_id": turma_id})
    if not a or (a.get("tipo") or TIPO_PIPELINE) != TIPO_MONTAGEM:
        raise HTTPException(status_code=404, detail="Desafio não encontrado.")
    return t, a


async def _historico_montagem(atividade_id: str, user_id: str) -> dict:
    """Tentativas anteriores do aluno neste desafio: quantas e a melhor nota."""
    filtro = {"atividade_id": atividade_id, "user_id": user_id}
    try:
        total = await submissoes_montagem.count_documents(filtro)
    except Exception:
        total = 0
    melhor = None
    try:
        cur = submissoes_montagem.find(filtro, {"nota": 1}).sort("nota", -1).limit(1)
        docs = await cur.to_list(length=1)
        if docs:
            melhor = docs[0].get("nota")
    except Exception:
        melhor = None
    return {"tentativas": total, "melhor_nota": melhor}


@router.get("/{turma_id}/atividades/{atividade_id}/tabuleiro")
async def obter_tabuleiro(turma_id: str, atividade_id: str, usuario: dict = Depends(get_usuario_atual)):
    """Peças embaralhadas da tentativa atual do aluno.

    O tabuleiro é derivado de (atividade, aluno, tentativa), então recarregar a página
    devolve o mesmo — e a próxima tentativa devolve outro. Nunca inclui `papel` (útil ou
    distrator) nem o gabarito: com esses campos o desafio se resolveria lendo a resposta.
    """
    _t, a = await _atividade_de_montagem(turma_id, atividade_id, usuario)
    user_id = str(usuario["_id"])
    hist = await _historico_montagem(atividade_id, user_id)
    tabuleiro = await montar_tabuleiro(a, user_id, hist["tentativas"] + 1)
    return {
        "atividade": {"id": str(a["_id"]), "titulo": a.get("titulo"),
                      "descricao": a.get("descricao"), "tipo": TIPO_MONTAGEM},
        "tentativa": tabuleiro["tentativa"],
        "lanes": tabuleiro["lanes"],
        "pecas": [{"valor": p["valor"], "nome": p["nome"], "lane": p["lane"]}
                  for p in tabuleiro["pecas"]],
        **hist,
    }


@router.post("/{turma_id}/atividades/{atividade_id}/submeter-montagem")
async def submeter_montagem(turma_id: str, atividade_id: str, body: SubmeterMontagem,
                            usuario: dict = Depends(get_usuario_atual)):
    """Corrige a montagem pela rubrica, grava a tentativa e devolve nota + explicações."""
    _t, a = await _atividade_de_montagem(turma_id, atividade_id, usuario)
    user_id = str(usuario["_id"])
    hist = await _historico_montagem(atividade_id, user_id)
    tentativa = hist["tentativas"] + 1

    pecas = await carregar_pecas()
    # Mesmo tabuleiro que o GET devolveu para esta tentativa (determinístico).
    tabuleiro = await montar_tabuleiro(a, user_id, tentativa, pecas_catalogo=pecas)
    ofertadas = papeis(tabuleiro)

    # Só valem as peças DESTE tabuleiro. Sem esta checagem o re-sorteio não protegeria nada:
    # bastaria reenviar o pipeline ideal aprendido no feedback da tentativa anterior,
    # ignorando as peças sorteadas agora.
    montagem = normalizar_montagem(body.montagem)
    fora = sorted({v for valores in montagem.values() for v in valores if v not in ofertadas})
    if fora:
        raise HTTPException(
            status_code=400,
            detail=("Estas peças não estão no seu tabuleiro desta tentativa: "
                    f"{', '.join(fora)}. Recarregue o desafio e monte com as peças da tela."),
        )

    resultado = avaliar_montagem(montagem, a.get("gabarito") or {}, pecas, ofertadas)

    doc = {
        "user_id": user_id,
        "turma_id": turma_id,
        "atividade_id": atividade_id,
        "tentativa": tentativa,
        "montagem": resultado["montagem"],
        "nota": resultado["nota"],
        "nota_max": resultado["nota_max"],
        "pontos": resultado["pontos"],
        "pontos_max": resultado["pontos_max"],
        "regras": resultado["regras"],
        "criado_em": datetime.now(timezone.utc),
    }
    r = await submissoes_montagem.insert_one(doc)
    return converter_numpy({
        "id": str(r.inserted_id),
        "tentativa": tentativa,
        "melhor_nota": max([n for n in (resultado["nota"], hist["melhor_nota"]) if n is not None]),
        **{k: v for k, v in resultado.items() if k != "montagem"},
    })


@router.get("/{turma_id}/atividades/{atividade_id}/ranking")
async def ranking_atividade(turma_id: str, atividade_id: str, usuario: dict = Depends(exigir_admin_ou_professor)):
    await _turma_do_professor(turma_id, usuario)
    aoid = validar_object_id(atividade_id, "atividade_id")
    a = await atividades.find_one({"_id": aoid, "turma_id": turma_id})
    if not a:
        raise HTTPException(status_code=404, detail="Atividade não encontrada.")
    if (a.get("tipo") or TIPO_PIPELINE) == TIPO_MONTAGEM:
        return await _ranking_montagem(atividade_id)
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


async def _ranking_montagem(atividade_id: str) -> dict:
    """Ranking do desafio: melhor nota por aluno, desempatando por MENOS tentativas
    (quem entendeu antes fica na frente de quem chegou lá por insistência)."""
    por_aluno: dict = {}
    try:
        cur = submissoes_montagem.aggregate([
            {"$match": {"atividade_id": atividade_id}},
            {"$group": {"_id": "$user_id",
                        "nota": {"$max": "$nota"},
                        "tentativas": {"$sum": 1},
                        "ultima": {"$max": "$criado_em"}}},
        ])
        for row in await cur.to_list(length=None):
            por_aluno[row["_id"]] = {
                "aluno_id": row["_id"],
                "valor": row.get("nota"),
                "tentativas": row.get("tentativas", 0),
                "ultima": row.get("ultima"),
            }
    except Exception:
        por_aluno = {}

    usuarios = await _mapa_usuarios(list(por_aluno.keys()))
    linhas = []
    for aluno_id, linha in por_aluno.items():
        linha["aluno_nome"] = _nome_usuario(usuarios.get(aluno_id))
        linhas.append(linha)
    com_valor = [l for l in linhas if l["valor"] is not None]
    com_valor.sort(key=lambda l: (-l["valor"], l["tentativas"]))
    sem_valor = [l for l in linhas if l["valor"] is None]
    return converter_numpy({
        "tipo": TIPO_MONTAGEM,
        "metrica": "nota",
        "ordem": "desc",
        "ranking": com_valor + sem_valor,
    })


@router.get("/{turma_id}/progresso")
async def progresso_turma(turma_id: str, usuario: dict = Depends(exigir_admin_ou_professor)):
    t = await _turma_do_professor(turma_id, usuario)
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

    # Desafios entram em coluna PRÓPRIA: `submissoes` continua significando pipelines
    # submetidos (é o número que o professor já lia nesta tela).
    desafios_por_aluno: dict = {}
    try:
        cur = submissoes_montagem.aggregate([
            {"$match": {"turma_id": tid, "user_id": {"$in": alunos}}},
            {"$group": {"_id": "$user_id",
                        "atividades": {"$addToSet": "$atividade_id"},
                        "melhor_nota": {"$max": "$nota"},
                        "ultimo": {"$max": "$criado_em"}}},
        ])
        for row in await cur.to_list(length=None):
            desafios_por_aluno[row["_id"]] = {
                "submissoes": len([a for a in (row.get("atividades") or []) if a]),
                "melhor_nota": row.get("melhor_nota"),
                "ultimo_acesso": row.get("ultimo"),
            }
    except Exception:
        desafios_por_aluno = {}

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
        desafio = desafios_por_aluno.get(aid, {})
        # Último acesso é o mais recente entre pipeline salvo e desafio submetido.
        acessos = [d for d in (agg.get("ultimo_acesso"), desafio.get("ultimo_acesso")) if d]
        linhas.append({
            "aluno_id": aid,
            "aluno_nome": _nome_usuario(u),
            "email": (u or {}).get("email"),
            "submissoes": agg.get("submissoes", 0),
            "desafios": desafio.get("submissoes", 0),
            "melhor_nota_desafio": desafio.get("melhor_nota"),
            "total_atividades": total_atividades,
            "chats": chats_por_aluno.get(aid, 0),
            "ultimo_acesso": max(acessos) if acessos else None,
        })
    return converter_numpy({"turma": _turma_doc(t), "total_atividades": total_atividades, "alunos": linhas})
