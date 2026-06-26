"""Carrega o `conteudo` educacional versionado (`app/conteudo/*.json`) e o semeia
no MongoDB de forma **idempotente e não-destrutiva**.

Fonte da verdade = os arquivos JSON do repo (1 por categoria, mapa keyed por
`valor`). O seed só faz `$set: {conteudo}` (mais `$setOnInsert` de campos de
identidade quando o doc não existe). **Nunca** toca `execucao` (campo
allowlistado/sensível) nem `habilitado` de itens já existentes.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.conteudo.schema import Conteudo

_DIR = Path(__file__).resolve().parent

# Categorias versionadas e a coleção MongoDB correspondente.
CATEGORIAS = ("modelos", "metricas", "pre_processamento", "coleta_dados", "graficos")

# Categorias cujos documentos NÃO pré-existem no catálogo: o seed precisa criar o
# doc inteiro (identidade) via $setOnInsert, não só anexar `conteudo`.
_CATEGORIAS_CRIA_DOC = {"graficos"}


@lru_cache(maxsize=None)
def carregar_conteudo(categoria: str) -> Dict[str, dict]:
    """Lê `app/conteudo/<categoria>.json` → {valor: conteudo}. Cacheado."""
    if categoria not in CATEGORIAS:
        raise ValueError(f"Categoria inválida: {categoria!r}. Use: {CATEGORIAS}")
    caminho = _DIR / f"{categoria}.json"
    if not caminho.exists():
        return {}
    with caminho.open(encoding="utf-8") as f:
        dados = json.load(f)
    if not isinstance(dados, dict):
        raise ValueError(f"{caminho.name} deve ser um objeto {{valor: conteudo}}.")
    return dados


def validar_conteudo(conteudo: dict) -> Conteudo:
    """Valida um bloco `conteudo` contra o schema. Lança em conteúdo malformado."""
    return Conteudo.model_validate(conteudo)


def montar_operacoes_upsert(categoria: str, docs: Dict[str, dict]) -> List[Tuple[dict, dict]]:
    """Monta as operações de upsert (filtro, update) por `valor`.

    Garantia-chave: o `$set` contém **apenas** `conteudo`. Campos de identidade
    (e `habilitado`) vão só em `$setOnInsert`, preservando o que já existe no DB.
    """
    operacoes: List[Tuple[dict, dict]] = []
    cria_doc = categoria in _CATEGORIAS_CRIA_DOC
    for valor, conteudo in docs.items():
        if not conteudo:
            continue
        filtro = {"valor": valor}
        set_on_insert: Dict[str, Any] = {"valor": valor, "habilitado": True}
        if cria_doc:
            # gráficos: o doc não existe; semeia identidade mínima.
            titulo = conteudo.get("titulo") if isinstance(conteudo, dict) else None
            set_on_insert.update({
                "label": titulo or valor,
                "tipoItem": "grafico",
            })
        update = {"$set": {"conteudo": conteudo}, "$setOnInsert": set_on_insert}
        operacoes.append((filtro, update))
    return operacoes


async def seed_conteudo(db=None, categorias: Optional[List[str]] = None) -> Dict[str, Dict[str, int]]:
    """Semeia o `conteudo` versionado nas coleções. Idempotente e não-destrutivo.

    Retorna {categoria: {inseridos, atualizados}}.
    """
    if db is None:
        from app.database import db as _db
        db = _db
    cats = categorias or list(CATEGORIAS)
    resultado: Dict[str, Dict[str, int]] = {}
    for categoria in cats:
        docs = carregar_conteudo(categoria)
        colecao = db[_nome_colecao(categoria)]
        inseridos = atualizados = 0
        for filtro, update in montar_operacoes_upsert(categoria, docs):
            r = await colecao.update_one(filtro, update, upsert=True)
            if getattr(r, "upserted_id", None) is not None:
                inseridos += 1
            elif r.modified_count:
                atualizados += 1
        resultado[categoria] = {"inseridos": inseridos, "atualizados": atualizados}
    return resultado


def _nome_colecao(categoria: str) -> str:
    """Categoria → nome da coleção MongoDB."""
    # As coleções têm o mesmo nome da categoria.
    return categoria
