from typing import List, Any, Dict
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel
from bson import ObjectId
from app.schemas.conf_pipeline import ItemColeta
from app.database import opcoes_coletas, opcoes_modelos, opcoes_metricas, opcoes_pre_processamento, opcoes_graficos, tutor_audit
from app.security import exigir_admin_ou_professor
from app.pre_processamento import PREFIXOS_MODULOS_PERMITIDOS, modulo_permitido

router = APIRouter(prefix="/conf_pipeline", tags=["Configuração Pipeline"])


# Campos imutaveis por colecao
_CAMPOS_IMUTAVEIS = {"_id", "id"}

# Allowlist de modulos Python que o admin pode declarar no bloco `execucao`.
# Canônica em app/pre_processamento/catalogo.py (reaplicada no caminho de treino).
# Qualquer modulo fora dela vira HTTP 400 — defesa contra execucao de codigo
# arbitrario via UI de admin comprometida.
_TIPOS_HIPERPARAM_VALIDOS = {"int", "float", "str", "bool", "enum"}


def _validar_execucao(execucao: Any) -> None:
    """Valida o bloco `execucao` enviado pelo admin. Lanca HTTPException(400)."""
    if execucao is None:
        return
    if not isinstance(execucao, dict):
        raise HTTPException(status_code=400, detail="execucao deve ser um objeto.")

    modulo = execucao.get("modulo")
    classe = execucao.get("classe")
    funcao = execucao.get("funcao")
    if not isinstance(modulo, str) or not modulo:
        raise HTTPException(status_code=400, detail="execucao.modulo é obrigatório.")
    # Modelos/pré-proc usam `classe`; métricas usam `funcao`. Exige exatamente um.
    tem_classe = isinstance(classe, str) and bool(classe)
    tem_funcao = isinstance(funcao, str) and bool(funcao)
    if tem_classe == tem_funcao:
        raise HTTPException(
            status_code=400,
            detail="execucao deve ter exatamente um de 'classe' (modelos/pré-proc) ou 'funcao' (métricas).",
        )

    if not modulo_permitido(modulo):
        permitidos = ", ".join(PREFIXOS_MODULOS_PERMITIDOS)
        raise HTTPException(
            status_code=400,
            detail=f"Módulo '{modulo}' não está na lista permitida. Permitidos: {permitidos}",
        )

    hiper = execucao.get("hiperparametros", [])
    if hiper is None:
        return
    if not isinstance(hiper, list):
        raise HTTPException(status_code=400, detail="execucao.hiperparametros deve ser uma lista.")

    nomes_vistos: set[str] = set()
    for i, h in enumerate(hiper):
        if not isinstance(h, dict):
            raise HTTPException(status_code=400, detail=f"hiperparametros[{i}] deve ser um objeto.")
        nome = h.get("nome") or h.get("nomeHiperparametro")
        if not isinstance(nome, str) or not nome:
            raise HTTPException(status_code=400, detail=f"hiperparametros[{i}].nome é obrigatório.")
        if nome in nomes_vistos:
            raise HTTPException(status_code=400, detail=f"hiperparametro '{nome}' duplicado.")
        nomes_vistos.add(nome)
        tipo = h.get("tipo")
        if tipo is not None and tipo not in _TIPOS_HIPERPARAM_VALIDOS:
            raise HTTPException(
                status_code=400,
                detail=f"hiperparametros[{i}].tipo inválido. Use: {sorted(_TIPOS_HIPERPARAM_VALIDOS)}",
            )
        if tipo == "enum":
            opcoes = h.get("opcoes")
            if not isinstance(opcoes, list) or not opcoes:
                raise HTTPException(
                    status_code=400,
                    detail=f"hiperparametros[{i}].opcoes obrigatório quando tipo='enum'.",
                )

# Mapa para CRUD generico (apenas colecoes com _id ObjectId)
_COLECOES_OID = {
  "coleta_dados": "opcoes_coletas",
  "modelos": "opcoes_modelos",
  "metricas": "opcoes_metricas",
}


def _colecao_por_tipo(tipo: str):
  if tipo == "coleta_dados":
    return opcoes_coletas
  if tipo == "modelos":
    return opcoes_modelos
  if tipo == "metricas":
    return opcoes_metricas
  return None


async def _registrar_audit_catalogo(usuario: dict, tipo: str, item_id: str, operacao: str, campos: List[str]):
  entrada = {
    "pipe": tipo,
    "tutor_id": item_id,
    "operacao": operacao,
    "campos_alterados": campos,
    "usuario_id": str(usuario.get("_id") or usuario.get("id") or ""),
    "usuario_email": usuario.get("email", ""),
    "usuario_nome": usuario.get("nome") or usuario.get("name") or usuario.get("email", ""),
    "timestamp": datetime.now(timezone.utc),
  }
  try:
    await tutor_audit.insert_one(entrada)
  except Exception:
    pass
  try:
    from app.routers.admin import registrar_log_admin
    await registrar_log_admin(usuario, f"catalogo_{operacao}", f"{tipo}/{item_id}: {', '.join(campos)}")
  except Exception:
    pass


class HabilitadoPayload(BaseModel):
  habilitado: bool


async def _patch_habilitado(colecao, item_id: str, habilitado: bool):
  if not ObjectId.is_valid(item_id):
    raise HTTPException(status_code=400, detail="ID inválido")
  resultado = await colecao.update_one(
    {"_id": ObjectId(item_id)},
    {"$set": {"habilitado": habilitado}}
  )
  if resultado.matched_count == 0:
    raise HTTPException(status_code=404, detail="Item não encontrado")
  return {"id": item_id, "habilitado": habilitado}


@router.patch("/coleta_dados/{item_id}/habilitado")
async def patch_coleta_habilitado(item_id: str, payload: HabilitadoPayload, _perfil: dict = Depends(exigir_admin_ou_professor)):
  return await _patch_habilitado(opcoes_coletas, item_id, payload.habilitado)


@router.patch("/modelos/{item_id}/habilitado")
async def patch_modelo_habilitado(item_id: str, payload: HabilitadoPayload, _perfil: dict = Depends(exigir_admin_ou_professor)):
  return await _patch_habilitado(opcoes_modelos, item_id, payload.habilitado)


@router.patch("/metricas/{item_id}/habilitado")
async def patch_metrica_habilitado(item_id: str, payload: HabilitadoPayload, _perfil: dict = Depends(exigir_admin_ou_professor)):
  return await _patch_habilitado(opcoes_metricas, item_id, payload.habilitado)


# Pre-processamento — chave eh "valor". Os documentos guardam o bloco `execucao`
# (modulo/classe/hiperparametros/aplica_em) usado tanto pelo treino quanto pela
# geracao de codigo, alem de habilitado e conteudo educacional.
@router.get("/pre_processamento/todos", response_model=List)
async def get_all_pre_processamento():
  cursor = opcoes_pre_processamento.find()
  documentos = await cursor.to_list(length=None)
  return [
    {
      **{k: v for k, v in doc.items() if k != "_id"},
      "id": str(doc["_id"]) if doc.get("_id") is not None else None,
      "habilitado": doc.get("habilitado", True),
    }
    for doc in documentos if doc.get("valor")
  ]


@router.get("/pre_processamento_doc/{valor}")
async def get_pre_processamento_doc(valor: str):
  if not valor or len(valor) > 100:
    raise HTTPException(status_code=400, detail="Valor inválido")
  doc = await opcoes_pre_processamento.find_one({"valor": valor})
  if not doc:
    raise HTTPException(status_code=404, detail="Item não encontrado")
  return {
    **{k: v for k, v in doc.items() if k != "_id"},
    "id": str(doc["_id"]),
    "habilitado": doc.get("habilitado", True),
  }


async def _serialize_doc(d: dict) -> dict:
  out = {k: v for k, v in d.items() if k not in {"_id"}}
  out["id"] = str(d["_id"])
  return out


# ======================================================
# CRUD generico para colecoes do catalogo (coleta_dados,
# modelos, metricas) — usado pelo admin em conf-tutor.
# ======================================================
@router.get("/catalogo/{tipo}/{item_id}")
async def get_item(tipo: str, item_id: str):
  colecao = _colecao_por_tipo(tipo)
  if colecao is None:
    raise HTTPException(status_code=404, detail="Tipo inválido")
  if not ObjectId.is_valid(item_id):
    raise HTTPException(status_code=400, detail="ID inválido")
  doc = await colecao.find_one({"_id": ObjectId(item_id)})
  if not doc:
    raise HTTPException(status_code=404, detail="Item não encontrado")
  return await _serialize_doc(doc)


@router.put("/catalogo/{tipo}/{item_id}")
async def put_item(
  tipo: str,
  item_id: str,
  payload: Dict[str, Any] = Body(...),
  usuario: dict = Depends(exigir_admin_ou_professor),
):
  colecao = _colecao_por_tipo(tipo)
  if colecao is None:
    raise HTTPException(status_code=404, detail="Tipo inválido")
  if not ObjectId.is_valid(item_id):
    raise HTTPException(status_code=400, detail="ID inválido")
  set_data = {k: v for k, v in (payload or {}).items() if k not in _CAMPOS_IMUTAVEIS}
  if not set_data:
    raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
  if "execucao" in set_data:
    _validar_execucao(set_data["execucao"])
  resultado = await colecao.update_one({"_id": ObjectId(item_id)}, {"$set": set_data})
  if resultado.matched_count == 0:
    raise HTTPException(status_code=404, detail="Item não encontrado")
  await _registrar_audit_catalogo(usuario, tipo, item_id, "catalogo_atualizar", list(set_data.keys()))
  return {"id": item_id, "campos_alterados": list(set_data.keys())}


@router.post("/catalogo/{tipo}")
async def post_item(
  tipo: str,
  payload: Dict[str, Any] = Body(...),
  usuario: dict = Depends(exigir_admin_ou_professor),
):
  colecao = _colecao_por_tipo(tipo)
  if colecao is None:
    raise HTTPException(status_code=404, detail="Tipo inválido")
  if not payload or not payload.get("valor") or not payload.get("label"):
    raise HTTPException(status_code=400, detail="Campos 'valor' e 'label' são obrigatórios")
  # Garante valor unico (e impede colisao quando reusado por outros codigos)
  existente = await colecao.find_one({"valor": payload["valor"]})
  if existente:
    raise HTTPException(status_code=409, detail="Já existe um item com este valor")
  doc = {k: v for k, v in payload.items() if k not in _CAMPOS_IMUTAVEIS}
  if "execucao" in doc:
    _validar_execucao(doc["execucao"])
  # Modelos só são funcionais (treino + codegen) com execucao e categorização.
  if tipo == "modelos":
    if not isinstance(doc.get("execucao"), dict) or not doc["execucao"].get("classe"):
      raise HTTPException(status_code=400, detail="Modelo exige bloco 'execucao' com modulo e classe.")
    doc.setdefault("prever_categoria", True)
    doc.setdefault("dados_rotulados", True)
  if tipo == "metricas":
    if not isinstance(doc.get("execucao"), dict) or not doc["execucao"].get("funcao"):
      raise HTTPException(status_code=400, detail="Métrica exige bloco 'execucao' com modulo e funcao.")
  doc.setdefault("habilitado", True)
  resultado = await colecao.insert_one(doc)
  novo_id = str(resultado.inserted_id)
  await _registrar_audit_catalogo(usuario, tipo, novo_id, "catalogo_criar", list(doc.keys()))
  return {"id": novo_id}


@router.delete("/catalogo/{tipo}/{item_id}")
async def delete_item(
  tipo: str,
  item_id: str,
  usuario: dict = Depends(exigir_admin_ou_professor),
):
  colecao = _colecao_por_tipo(tipo)
  if colecao is None:
    raise HTTPException(status_code=404, detail="Tipo inválido")
  if not ObjectId.is_valid(item_id):
    raise HTTPException(status_code=400, detail="ID inválido")
  resultado = await colecao.delete_one({"_id": ObjectId(item_id)})
  if resultado.deleted_count == 0:
    raise HTTPException(status_code=404, detail="Item não encontrado")
  await _registrar_audit_catalogo(usuario, tipo, item_id, "catalogo_remover", [])
  return {"id": item_id, "removido": True}


# ======================================================
# Pre-processamento — chave eh "valor" (sem ObjectId);
# o documento eh upsertado/atualizado por valor.
# ======================================================
@router.put("/pre_processamento_doc/{valor}")
async def put_pre_processamento_doc(
  valor: str,
  payload: Dict[str, Any] = Body(...),
  usuario: dict = Depends(exigir_admin_ou_professor),
):
  if not valor or len(valor) > 100:
    raise HTTPException(status_code=400, detail="Valor inválido")
  set_data = {k: v for k, v in (payload or {}).items() if k not in _CAMPOS_IMUTAVEIS and k != "valor"}
  set_data["valor"] = valor
  if len(set_data) <= 1:
    raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
  if "execucao" in set_data:
    _validar_execucao(set_data["execucao"])
  await opcoes_pre_processamento.update_one(
    {"valor": valor},
    {"$set": set_data},
    upsert=True
  )
  await _registrar_audit_catalogo(usuario, "pre_processamento", valor, "catalogo_atualizar", list(set_data.keys()))
  return {"valor": valor, "campos_alterados": list(set_data.keys())}


# ======================================================
# Gráficos (visualizações Yellowbrick/sklearn) — chave eh
# "valor" (slug estável, ver metricas.GRAFICOS_IDS). Guardam
# o `conteudo` educacional (Básico/Avançado) exibido no card.
# ======================================================
@router.get("/graficos/todos", response_model=List)
async def get_all_graficos():
  cursor = opcoes_graficos.find()
  documentos = await cursor.to_list(length=None)
  return [
    {
      **{k: v for k, v in doc.items() if k != "_id"},
      "id": str(doc["_id"]) if doc.get("_id") is not None else None,
      "habilitado": doc.get("habilitado", True),
    }
    for doc in documentos if doc.get("valor")
  ]


@router.get("/graficos/{valor}")
async def get_grafico_doc(valor: str):
  if not valor or len(valor) > 100:
    raise HTTPException(status_code=400, detail="Valor inválido")
  doc = await opcoes_graficos.find_one({"valor": valor})
  if not doc:
    raise HTTPException(status_code=404, detail="Item não encontrado")
  return {
    **{k: v for k, v in doc.items() if k != "_id"},
    "id": str(doc["_id"]),
    "habilitado": doc.get("habilitado", True),
  }


@router.put("/graficos_doc/{valor}")
async def put_grafico_doc(
  valor: str,
  payload: Dict[str, Any] = Body(...),
  usuario: dict = Depends(exigir_admin_ou_professor),
):
  if not valor or len(valor) > 100:
    raise HTTPException(status_code=400, detail="Valor inválido")
  set_data = {k: v for k, v in (payload or {}).items() if k not in _CAMPOS_IMUTAVEIS and k != "valor"}
  set_data["valor"] = valor
  if len(set_data) <= 1:
    raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
  await opcoes_graficos.update_one(
    {"valor": valor},
    {"$set": set_data, "$setOnInsert": {"habilitado": True, "tipoItem": "grafico"}},
    upsert=True,
  )
  await _registrar_audit_catalogo(usuario, "graficos", valor, "catalogo_atualizar", list(set_data.keys()))
  return {"valor": valor, "campos_alterados": list(set_data.keys())}


@router.patch("/pre_processamento/{valor}/habilitado")
async def patch_pre_processamento_habilitado(valor: str, payload: HabilitadoPayload, _perfil: dict = Depends(exigir_admin_ou_professor)):
  if not valor or len(valor) > 100:
    raise HTTPException(status_code=400, detail="Valor inválido")
  await opcoes_pre_processamento.update_one(
    {"valor": valor},
    {"$set": {"valor": valor, "habilitado": payload.habilitado}},
    upsert=True
  )
  return {"valor": valor, "habilitado": payload.habilitado}

@router.post("/itens_coleta_dados/multiplos")
async def itens_coleta_dados(itens: List[ItemColeta], _perfil: dict = Depends(exigir_admin_ou_professor)):
  documentos = [item.model_dump() for item in itens]
  resultado = await opcoes_coletas.insert_many(documentos)
  return {"ids_inseridos": [str(_id) for _id in resultado.inserted_ids]}

@router.get("/coleta_dados/todos", response_model=List)
async def get_all_coleta(
    limite: int = Query(10, ge=1, le=100),
    pagina: int = Query(1, ge=1),
    ordenar: Optional[str] = Query(None, description="Campo para ordenar, ex: 'label', 'tipoItem'"),
    direcao: Optional[str] = Query("asc", pattern="^(asc|desc)$", description="Direção da ordenação: 'asc' ou 'desc'")
):
  skip = (pagina - 1) * limite

  campo_ordenacao = ordenar if ordenar else "label"
  direcao_ordenacao = 1 if direcao == "asc" else -1

  cursor = (
    opcoes_coletas.find()
    .sort(campo_ordenacao, direcao_ordenacao)
    .skip(skip)
    .limit(limite)
  )
  documentos = await cursor.to_list(length=limite)

  return [
    {
      **{k: v for k, v in doc.items() if k != "_id"},
      "id": str(doc["_id"]),
      "habilitado": doc.get("habilitado", True),
    }
    for doc in documentos
  ]

@router.get("/modelos/todos", response_model=List)
async def get_all_modelos(
    limite: int = Query(10, ge=1, le=100),
    pagina: int = Query(1, ge=1),
    ordenar: Optional[str] = Query(None, description="Campo para ordenar, ex: 'label', 'tipoItem'"),
    direcao: Optional[str] = Query("asc", pattern="^(asc|desc)$", description="Direção da ordenação: 'asc' ou 'desc'"),
    prever_categoria: Optional[bool] = Query(None, description=""),
    dados_rotulados: Optional[bool] = Query(None, description="")
):
  skip = (pagina - 1) * limite

  campo_ordenacao = ordenar if ordenar else "label"
  direcao_ordenacao = 1 if direcao == "asc" else -1
  

  filtro = {}
  if prever_categoria is not None:
    filtro["prever_categoria"] = prever_categoria
  if dados_rotulados is not None:
    filtro["dados_rotulados"] = dados_rotulados

  cursor = (
    opcoes_modelos.find(filtro)
    .sort(campo_ordenacao, direcao_ordenacao)
    .collation({"locale": "en", "strength": 1})
    .skip(skip)
    .limit(limite)
  )
  documentos = await cursor.to_list(length=limite)


  return [
    {
      **{k: v for k, v in doc.items() if k not in ["_id", "prever_categoria", "dados_rotulados"]},
      "id": str(doc["_id"]),
      "preverCategoria": doc.get("prever_categoria"),
      "dadosRotulados": doc.get("dados_rotulados"),
      "habilitado": doc.get("habilitado", True),
    }

    for doc in documentos
  ]
  
@router.get("/metricas/todos", response_model=List)
async def get_all_metricas(
    limite: int = Query(10, ge=1, le=100),
    pagina: int = Query(1, ge=1),
    ordenar: Optional[str] = Query(None, description="Campo para ordenar, ex: 'label', 'tipoItem'"),
    direcao: Optional[str] = Query("asc", pattern="^(asc|desc)$", description="Direção da ordenação: 'asc' ou 'desc'")
):
  skip = (pagina - 1) * limite

  campo_ordenacao = ordenar if ordenar else "label"
  direcao_ordenacao = 1 if direcao == "asc" else -1

  cursor = (
    opcoes_metricas.find()
    .sort(campo_ordenacao, direcao_ordenacao)
    .skip(skip)
    .limit(limite)
  )
  documentos = await cursor.to_list(length=limite)

  return [
    {
      **{k: v for k, v in doc.items() if k != "_id"},
      "id": str(doc["_id"]),
      "marcado": False,
      "habilitado": doc.get("habilitado", True),
    }
    for doc in documentos
  ]