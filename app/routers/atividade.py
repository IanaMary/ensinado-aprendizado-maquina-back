"""Registro de atividades dos usuários (telemetria pedagógica).

Grava, numa coleção única (`atividade_usuario`), eventos da jornada do aluno:
ações do pipeline, navegação, chamadas HTTP, erros e o uso do chatbot. Inclui
duração das ações ("tempo preso") para diagnosticar onde os alunos travam.

O padrão de gravação é fire-and-forget (espelha `registrar_log_admin` em
`app/routers/admin.py`): nunca pode quebrar a operação principal. O usuário é
sempre derivado do JWT no servidor — o corpo enviado pelo front nunca é confiado
como identidade.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import atividade_usuario
from app.funcoes_genericas.funcoes_genericas import converter_numpy, serialize_doc
from app.schemas.atividade import EventoAtividade, EventoLote, MAX_EVENTOS_LOTE
from app.security import get_usuario_atual

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/atividades", tags=["Atividades"])

# Teto de tamanho do bloco `detalhes` (após serialização) e de cada string-folha.
_MAX_DETALHES_CHARS = 20000
_MAX_STR_LEAF = 2000


async def exigir_admin_ou_professor(usuario: dict = Depends(get_usuario_atual)) -> dict:
    if (usuario or {}).get("role") not in ("admin", "professor"):
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores e professores.")
    return usuario


def _podar(obj: Any) -> Any:
    """Trunca strings-folha longas preservando a estrutura do objeto."""
    if isinstance(obj, str):
        return obj if len(obj) <= _MAX_STR_LEAF else obj[:_MAX_STR_LEAF] + "…"
    if isinstance(obj, dict):
        return {k: _podar(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_podar(i) for i in obj]
    return obj


def _truncar_detalhes(detalhes: Optional[dict]) -> Optional[dict]:
    """Limita o tamanho do bloco `detalhes` sem perder estrutura: poda strings longas
    e, só se o total ainda exceder o teto, cai para um resumo colapsado."""
    if not detalhes:
        return detalhes
    try:
        podado = _podar(detalhes)
        if len(json.dumps(podado, default=str, ensure_ascii=False)) <= _MAX_DETALHES_CHARS:
            return podado
        bruto = json.dumps(podado, default=str, ensure_ascii=False)
        return {"_truncado": True, "_resumo": bruto[:_MAX_DETALHES_CHARS]}
    except Exception:
        return {"_truncado": True}


def _doc_atividade(
    usuario: dict,
    tipo: str,
    acao: str,
    *,
    detalhes: Optional[dict] = None,
    pipeline_id: Optional[str] = None,
    duracao_ms: Optional[int] = None,
    status: str = "sucesso",
    erro: Optional[str] = None,
    origem: str = "backend",
    timestamp_cliente: Optional[str] = None,
) -> dict:
    """Monta o documento de atividade (usuário sempre derivado do servidor)."""
    return {
        "usuario_id": str((usuario or {}).get("_id") or (usuario or {}).get("id") or ""),
        "usuario_email": (usuario or {}).get("email", ""),
        "usuario_nome": (usuario or {}).get("nome_usuario")
        or (usuario or {}).get("nome")
        or (usuario or {}).get("name")
        or (usuario or {}).get("email", ""),
        "usuario_role": (usuario or {}).get("role", ""),
        "tipo": tipo,
        "acao": acao,
        "detalhes": converter_numpy(_truncar_detalhes(detalhes)),
        "pipeline_id": pipeline_id,
        "duracao_ms": duracao_ms,
        "status": status,
        "erro": erro,
        "origem": origem,
        "timestamp": datetime.now(timezone.utc),
        "timestamp_cliente": timestamp_cliente,
    }


async def registrar_atividade(
    usuario: dict,
    tipo: str,
    acao: str,
    *,
    detalhes: Optional[dict] = None,
    pipeline_id: Optional[str] = None,
    duracao_ms: Optional[int] = None,
    status: str = "sucesso",
    erro: Optional[str] = None,
    origem: str = "backend",
    timestamp_cliente: Optional[str] = None,
) -> None:
    """Grava um evento de atividade. Fire-and-forget: erros são apenas logados."""
    try:
        doc = _doc_atividade(
            usuario, tipo, acao,
            detalhes=detalhes, pipeline_id=pipeline_id, duracao_ms=duracao_ms,
            status=status, erro=erro, origem=origem, timestamp_cliente=timestamp_cliente,
        )
        await atividade_usuario.insert_one(doc)
    except Exception as e:  # pragma: no cover - defensivo
        logger.warning("Falha ao registrar atividade: %s", e)


@router.post("/lote")
async def registrar_lote(lote: EventoLote, usuario: dict = Depends(get_usuario_atual)):
    """Recebe um lote de eventos do front e grava todos num único insert_many."""
    eventos = lote.eventos or []
    if len(eventos) > MAX_EVENTOS_LOTE:
        raise HTTPException(
            status_code=413,
            detail=f"Lote acima do limite de {MAX_EVENTOS_LOTE} eventos.",
        )
    if eventos:
        docs = [
            _doc_atividade(
                usuario, ev.tipo, ev.acao,
                detalhes=ev.detalhes, pipeline_id=ev.pipeline_id, duracao_ms=ev.duracao_ms,
                status=ev.status, erro=ev.erro, origem="frontend", timestamp_cliente=ev.timestamp_cliente,
            )
            for ev in eventos
        ]
        try:
            await atividade_usuario.insert_many(docs)
        except Exception as e:  # pragma: no cover - defensivo
            logger.warning("Falha ao registrar lote de atividades: %s", e)
    return {"gravados": len(eventos)}


@router.post("")
async def registrar_unico(evento: EventoAtividade, usuario: dict = Depends(get_usuario_atual)):
    """Conveniência para gravar um evento único."""
    await registrar_atividade(
        usuario,
        evento.tipo,
        evento.acao,
        detalhes=evento.detalhes,
        pipeline_id=evento.pipeline_id,
        duracao_ms=evento.duracao_ms,
        status=evento.status,
        erro=evento.erro,
        origem="frontend",
        timestamp_cliente=evento.timestamp_cliente,
    )
    return {"gravados": 1}


def _parse_data(valor: Optional[str]) -> Optional[datetime]:
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Data inválida: {valor}")
    # Datas sem offset (ex.: chamada direta à API) são interpretadas como UTC,
    # alinhando com o `timestamp` armazenado (tz-aware UTC). O front envia ISO/UTC.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _faixa_tempo(inicio: Optional[datetime], fim: Optional[datetime]) -> Optional[dict]:
    faixa: dict[str, Any] = {}
    if inicio:
        faixa["$gte"] = inicio
    if fim:
        faixa["$lte"] = fim
    return faixa or None


@router.get("")
async def listar_atividades(
    usuario_id: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    acao: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    incluir_total: bool = Query(True),
    _: dict = Depends(exigir_admin_ou_professor),
):
    """Lista atividades com filtros e paginação (admin/professor).

    `incluir_total=false` pula a contagem — o front pede o total só ao (re)filtrar e
    o reaproveita ao paginar, evitando um scan de contagem a cada página."""
    filtro: dict[str, Any] = {}
    if usuario_id:
        filtro["usuario_id"] = usuario_id
    if tipo:
        filtro["tipo"] = tipo
    if acao:
        filtro["acao"] = acao
    if status:
        filtro["status"] = status
    faixa = _faixa_tempo(_parse_data(data_inicio), _parse_data(data_fim))
    if faixa:
        filtro["timestamp"] = faixa

    total = None
    if incluir_total:
        # Sem filtro, usa a contagem estimada (metadados, O(1)); com filtro, conta o subconjunto.
        total = (
            await atividade_usuario.count_documents(filtro)
            if filtro
            else await atividade_usuario.estimated_document_count()
        )

    cursor = atividade_usuario.find(filtro).sort("timestamp", -1).skip(skip).limit(limit)
    itens = []
    async for doc in cursor:
        d = serialize_doc(doc)
        ts = d.get("timestamp")
        if isinstance(ts, datetime):
            d["timestamp"] = ts.isoformat()
        itens.append(d)
    return {"total": total, "skip": skip, "limit": limit, "itens": itens}


@router.get("/resumo")
async def resumo_atividades(
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    _: dict = Depends(exigir_admin_ou_professor),
):
    """Agregações para os cards da tela admin, em um único passe via $facet."""
    match: dict[str, Any] = {}
    faixa = _faixa_tempo(_parse_data(data_inicio), _parse_data(data_fim))
    if faixa:
        match["timestamp"] = faixa

    pipeline: list = []
    if match:
        pipeline.append({"$match": match})
    pipeline.append({
        "$facet": {
            "por_tipo": [{"$group": {"_id": "$tipo", "total": {"$sum": 1}}}, {"$sort": {"total": -1}}],
            "por_acao": [
                {"$group": {"_id": "$acao", "total": {"$sum": 1}, "duracao_media_ms": {"$avg": "$duracao_ms"}}},
                {"$sort": {"total": -1}},
                {"$limit": 20},
            ],
            "total": [{"$count": "n"}],
            "total_erros": [{"$match": {"status": "erro"}}, {"$count": "n"}],
            "usuarios": [{"$group": {"_id": "$usuario_id"}}, {"$count": "n"}],
        }
    })

    facet: dict[str, Any] = {}
    async for doc in atividade_usuario.aggregate(pipeline):
        facet = doc
        break

    def _n(arr) -> int:
        return arr[0]["n"] if arr else 0

    return {
        "total": _n(facet.get("total", [])),
        "total_erros": _n(facet.get("total_erros", [])),
        "usuarios_ativos": _n(facet.get("usuarios", [])),
        "por_tipo": [{"tipo": r["_id"], "total": r["total"]} for r in facet.get("por_tipo", [])],
        "por_acao": [
            {"acao": r["_id"], "total": r["total"], "duracao_media_ms": r.get("duracao_media_ms")}
            for r in facet.get("por_acao", [])
        ],
    }
