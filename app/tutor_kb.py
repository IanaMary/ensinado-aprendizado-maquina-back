"""Base de conhecimento do tutor (chatbot LLM).

Monta, a partir do catálogo no banco (``db.modelos`` e ``db.metricas``), um resumo
compacto por item — título, explicação simples, quando usar/evitar, hiperparâmetros
com seus padrões, fórmula e link da documentação. Esse material é injetado no
contexto enviado ao modelo de linguagem, para que as respostas fiquem ancoradas no
conteúdo verificado do catálogo (mesma fonte que alimenta os cards do tutor).

A leitura do banco é cacheada em memória com TTL para não consultar a cada mensagem.
Tudo é defensivo: qualquer falha resulta em bloco vazio (o chat continua funcionando).
"""
import asyncio
import json
import time

from app import database

# Tamanhos defensivos para não estourar o contexto do modelo.
_TTL = 600  # 10 min
_MAX_ITENS_DETALHADOS = 8
_MAX_BLOCO_CHARS = 6000

_cache: dict = {"itens": {}, "indice": "", "valores": set(), "ts": 0.0}
_lock = asyncio.Lock()


def _resumo_compacto(valor: str, c: dict, grupo: str) -> str:
    """Transforma o `conteudo` de um item numa ficha curta em markdown."""
    linhas = [f"### {c.get('titulo') or valor}  (`{valor}` — {grupo})"]
    texto = c.get("resumo_basico") or c.get("descricao") or ""
    if texto:
        linhas.append(str(texto).strip()[:500])
    qu = c.get("quandoUsar") or []
    if qu:
        linhas.append("Quando usar: " + "; ".join(str(x) for x in qu[:4]))
    nu = c.get("naoUsarQuando") or []
    if nu:
        linhas.append("Evitar quando: " + "; ".join(str(x) for x in nu[:4]))
    hp = c.get("hiperparametros_doc") or []
    if hp:
        pares = []
        for h in hp[:6]:
            nome = h.get("nome")
            if not nome:
                continue
            pares.append(f"{nome}={h.get('default')}")
        if pares:
            linhas.append("Hiperparâmetros (padrão): " + ", ".join(pares))
    if c.get("formula"):
        linhas.append("Fórmula: " + str(c["formula"]))
    if c.get("link_sklearn"):
        linhas.append("Doc oficial: " + str(c["link_sklearn"]))
    return "\n".join(linhas)


async def _carregar() -> dict:
    """Lê o catálogo do banco e monta as fichas compactas (cacheado por TTL)."""
    agora = time.time()
    if _cache["itens"] and (agora - _cache["ts"]) < _TTL:
        return _cache
    async with _lock:
        if _cache["itens"] and (time.time() - _cache["ts"]) < _TTL:
            return _cache
        itens: dict = {}
        indice: list = []
        try:
            async for x in database.opcoes_modelos.find({}, {"valor": 1, "conteudo": 1}):
                c = x.get("conteudo")
                valor = x.get("valor")
                if c and valor:
                    itens[valor] = _resumo_compacto(valor, c, "modelo")
                    indice.append(f"- {c.get('titulo') or valor} (`{valor}`, modelo)")
            async for x in database.opcoes_metricas.find({}, {"valor": 1, "grupo": 1, "conteudo": 1}):
                c = x.get("conteudo")
                valor = x.get("valor")
                if c and valor:
                    grupo = f"métrica/{x.get('grupo')}" if x.get("grupo") else "métrica"
                    itens[valor] = _resumo_compacto(valor, c, grupo)
                    indice.append(f"- {c.get('titulo') or valor} (`{valor}`, {grupo})")
        except Exception:
            # Falha de banco: devolve o que tiver (possivelmente vazio).
            pass
        _cache.update(
            itens=itens,
            indice="\n".join(indice),
            valores=set(itens.keys()),
            ts=time.time(),
        )
    return _cache


def _valores_no_contexto(contexto, valores: set) -> list:
    """Detecta quais itens do catálogo aparecem no contexto do pipeline."""
    if not contexto or not valores:
        return []
    try:
        texto = json.dumps(contexto, ensure_ascii=False, default=str).lower()
    except Exception:
        texto = str(contexto).lower()
    achados = [v for v in valores if v.lower() in texto]
    # Ordem estável e limitada.
    return sorted(achados)[:_MAX_ITENS_DETALHADOS]


async def bloco_kb(contexto) -> str:
    """Bloco de markdown com a base de conhecimento relevante ao contexto.

    Inclui um índice de todo o catálogo e as fichas detalhadas dos itens citados
    no contexto. Devolve string vazia se não houver catálogo carregado.
    """
    try:
        kb = await _carregar()
    except Exception:
        return ""
    if not kb["itens"]:
        return ""

    partes = [
        "Catálogo de modelos e métricas disponíveis na plataforma "
        "(use estes nomes e padrões; não invente hiperparâmetros):",
        kb["indice"],
    ]
    detalhados = _valores_no_contexto(contexto, kb["valores"])
    if detalhados:
        partes.append("\nDetalhes dos itens em uso agora:")
        for v in detalhados:
            partes.append(kb["itens"][v])

    bloco = "\n".join(partes)
    if len(bloco) > _MAX_BLOCO_CHARS:
        bloco = bloco[:_MAX_BLOCO_CHARS] + "\n... (base de conhecimento truncada)"
    return bloco
