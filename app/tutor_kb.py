"""Base de conhecimento do tutor (chatbot LLM).

Monta, a partir do catálogo no banco (``db.modelos``, ``db.metricas`` e
``db.pre_processamento``), um resumo
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
# A ficha avançada é bem maior (descrição técnica inteira + efeito dos hiperparâmetros +
# fundamentos/prática), então o teto do bloco acompanha: com 6000 o corte caía no meio da
# primeira ficha e o aluno avançado recebia menos contexto que o básico.
# O índice sozinho (61 itens do catálogo, dos quais 46 entram aqui) já ocupa ~4,5 mil
# caracteres: com o teto antigo sobrava espaço para uma ficha e meia. Ampliado — mesmo o teto
# avançado equivale a ~4 mil tokens, folgado para a janela do modelo em uso.
_MAX_BLOCO_CHARS = 8000
_MAX_BLOCO_CHARS_AVANCADO = 14000
# O texto básico é curto por natureza (mediana ~310 chars); o técnico chega a 936, então
# cortá-lo em 500 mutilava justamente o que o aluno avançado veio buscar.
_MAX_TEXTO_BASICO = 500
_MAX_TEXTO_AVANCADO = 1200

NIVEL_AVANCADO = "avancado"

_cache: dict = {"itens": {}, "indice": "", "valores": set(), "ts": 0.0}
_lock = asyncio.Lock()


def _lista(valores, limite: int) -> str:
    return "; ".join(str(x) for x in (valores or [])[:limite])


def _resumo_compacto(valor: str, c: dict, grupo: str, nivel: str = "basico") -> str:
    """Ficha curta em markdown de um item do catálogo, no nível pedido.

    O nível não muda só o tom: muda **o que** o modelo recebe. No básico vai a explicação
    simples; no avançado vai a descrição técnica inteira, o efeito de cada hiperparâmetro e os
    blocos Fundamentos/Na prática — que é o material que o aluno avançado está lendo no card.
    """
    avancado = nivel == NIVEL_AVANCADO
    linhas = [f"### {c.get('titulo') or valor}  (`{valor}` — {grupo})"]

    if avancado:
        texto = c.get("descricao") or c.get("resumo_basico") or ""
        limite = _MAX_TEXTO_AVANCADO
    else:
        texto = c.get("resumo_basico") or c.get("descricao") or ""
        limite = _MAX_TEXTO_BASICO
    if texto:
        linhas.append(str(texto).strip()[:limite])

    if c.get("quandoUsar"):
        linhas.append("Quando usar: " + _lista(c["quandoUsar"], 4))
    if c.get("naoUsarQuando"):
        linhas.append("Evitar quando: " + _lista(c["naoUsarQuando"], 4))

    hp = c.get("hiperparametros_doc") or []
    if hp:
        if avancado:
            for h in hp[:6]:
                nome = h.get("nome")
                if not nome:
                    continue
                partes = [f"- {nome} (padrão {h.get('default')}"]
                faixa = h.get("faixa") or (", ".join(str(o) for o in (h.get("opcoes") or [])) or None)
                partes.append(f"; {faixa})" if faixa else ")")
                detalhe = " — ".join(str(x) for x in (h.get("efeito"), h.get("quando_ajustar")) if x)
                if detalhe:
                    partes.append(" " + detalhe)
                linhas.append("".join(partes))
        else:
            pares = [f"{h.get('nome')}={h.get('default')}" for h in hp[:6] if h.get("nome")]
            if pares:
                linhas.append("Hiperparâmetros (padrão): " + ", ".join(pares))

    fund = c.get("fundamentos") or {}
    pratica = c.get("pratica") or {}
    formula = c.get("formula") or fund.get("formula")
    if formula:
        linhas.append("Fórmula: " + str(formula))
    if avancado and fund:
        if fund.get("otimiza"):
            linhas.append("Otimiza: " + str(fund["otimiza"]))
        if fund.get("pressupostos"):
            linhas.append("Pressupostos: " + _lista(fund["pressupostos"], 4))
        if fund.get("complexidade"):
            linhas.append("Complexidade: " + str(fund["complexidade"]))
    if avancado and pratica:
        if pratica.get("tuning"):
            linhas.append("O que ajustar primeiro: " + _lista(pratica["tuning"], 3))
        if pratica.get("armadilhas"):
            linhas.append("Armadilhas: " + _lista(pratica["armadilhas"], 3))
        if pratica.get("diagnostico"):
            linhas.append("Diagnóstico: " + _lista(pratica["diagnostico"], 3))

    if avancado:
        ref = (c.get("referencias") or [{}])[0]
        if ref.get("titulo"):
            autor = f" ({ref['autor']})" if ref.get("autor") else ""
            linhas.append(f"Leitura: {ref['titulo']}{autor}")

    if c.get("link_sklearn"):
        linhas.append("Doc oficial: " + str(c["link_sklearn"]))
    return "\n".join(linhas)


def _nivel_do_contexto(contexto) -> str:
    """Nível pedido pelo aluno (preferência do perfil, enviada pelo front)."""
    if isinstance(contexto, dict) and str(contexto.get("nivel") or "").lower() == NIVEL_AVANCADO:
        return NIVEL_AVANCADO
    return "basico"


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
                    # Guarda o conteúdo CRU: a ficha é montada por nível a cada pergunta
                    # (renderizar é barato; ler o banco é que não é).
                    itens[valor] = {"conteudo": c, "grupo": "modelo"}
                    indice.append(f"- {c.get('titulo') or valor} (`{valor}`, modelo)")
            async for x in database.opcoes_metricas.find({}, {"valor": 1, "grupo": 1, "conteudo": 1}):
                c = x.get("conteudo")
                valor = x.get("valor")
                if c and valor:
                    grupo = f"métrica/{x.get('grupo')}" if x.get("grupo") else "métrica"
                    itens[valor] = {"conteudo": c, "grupo": grupo}
                    indice.append(f"- {c.get('titulo') or valor} (`{valor}`, {grupo})")
            # Pré-processamento entrou depois: o aluno pergunta "por que escalar?" tanto quanto
            # pergunta sobre o modelo, e agora esses itens também têm Fundamentos/Na prática.
            # Gráficos e fontes de coleta seguem fora para não inchar o índice, que vai inteiro.
            async for x in database.opcoes_pre_processamento.find({}, {"valor": 1, "conteudo": 1}):
                c = x.get("conteudo")
                valor = x.get("valor")
                if c and valor:
                    itens[valor] = {"conteudo": c, "grupo": "pré-processamento"}
                    indice.append(f"- {c.get('titulo') or valor} (`{valor}`, pré-processamento)")
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

    nivel = _nivel_do_contexto(contexto)
    teto = _MAX_BLOCO_CHARS_AVANCADO if nivel == NIVEL_AVANCADO else _MAX_BLOCO_CHARS
    partes = [
        "Catálogo de modelos, métricas e pré-processadores disponíveis na plataforma "
        "(use estes nomes e padrões; não invente hiperparâmetros):",
        kb["indice"],
    ]
    detalhados = _valores_no_contexto(contexto, kb["valores"])
    if detalhados:
        partes.append("\nDetalhes dos itens em uso agora:")
        # Corta por FICHA INTEIRA, não por caractere: meia ficha entrega ao modelo uma frase
        # pela metade — e a ficha avançada é justamente a mais longa.
        omitidos = 0
        tamanho = sum(len(p) + 1 for p in partes)
        for v in detalhados:
            item = kb["itens"][v]
            ficha = _resumo_compacto(v, item["conteudo"], item["grupo"], nivel)
            if tamanho + len(ficha) + 1 > teto:
                omitidos += 1
                continue
            partes.append(ficha)
            tamanho += len(ficha) + 1
        if omitidos:
            partes.append(f"(+{omitidos} item(ns) do contexto omitidos por espaço)")

    bloco = "\n".join(partes)
    if len(bloco) > teto:
        # Só chega aqui se o índice sozinho estourar o teto.
        bloco = bloco[:teto] + "\n... (base de conhecimento truncada)"
    return bloco
