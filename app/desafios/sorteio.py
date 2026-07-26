"""Sorteio do tabuleiro: quais peças o aluno recebe embaralhadas.

Duas exigências moldam este módulo:

1. **Determinismo.** O tabuleiro é derivado de `(atividade_id, user_id, tentativa)` por
   uma semente estável, então a correção pode reconstruí-lo sem guardar estado de sessão —
   e o aluno que der F5 vê o mesmo tabuleiro.
2. **Re-sorteio por tentativa.** Cada nova tentativa troca as peças (mesma tarefa, outros
   distratores). Sem isso, o feedback por regra viraria tentativa-e-erro: bastava consertar
   o item apontado até fechar a nota, sem entender nada.

Os distratores saem do próprio catálogo (modelo de outra tarefa, métrica de outro grupo,
pré-processamento que este problema não pede), não de uma lista fixa.

3. **O tabuleiro sempre permite uma solução correta** (`_garantir_minimo`). O professor pode
   curar as peças (`gabarito.sortear_pecas: False`) ou deixar o sistema sortear; em qualquer
   caso, uma lane exigida sem peça — ou sem peça compatível com a tarefa — é completada, mesmo
   que isso contrarie um `vetar`. Sem essa garantia a regra `estrutura-minima` (peso 3) ficaria
   insatisfazível e o aluno perderia ponto por uma configuração que não é dele.
"""
from __future__ import annotations

import hashlib
import random
from typing import Any, Dict, List, Optional

from app.desafios.catalogo import LANES, carregar_pecas
from app.desafios.regras import MODELOS_SENSIVEIS_A_ESCALA

# Quantos distratores por dificuldade. Mais distratores = mais decisão de "o que NÃO usar".
DISTRATORES_POR_DIFICULDADE = {"facil": 2, "medio": 4, "dificil": 6}
DIFICULDADE_PADRAO = "medio"


def _semente(atividade_id: str, user_id: str, tentativa: int) -> int:
    bruto = f"{atividade_id}:{user_id}:{tentativa}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(bruto).digest()[:8], "big")


def _escolher(rng: random.Random, candidatas: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    if n <= 0 or not candidatas:
        return []
    return rng.sample(candidatas, min(n, len(candidatas)))


def _por_lane(pecas: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    agrupadas: Dict[str, List[Dict[str, Any]]] = {lane: [] for lane in LANES}
    for peca in pecas:
        agrupadas[peca["lane"]].append(peca)
    return agrupadas


def _uteis(rng: random.Random, pecas: List[Dict[str, Any]], gabarito: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Peças que permitem montar uma solução correta do enunciado.

    Quando o professor curou as peças (`sortear_pecas: False`), este sorteio não acontece: as
    peças escolhidas por ele são as úteis, e `_garantir_minimo` cobre o que faltar.
    """
    tarefa = gabarito.get("tarefa") or "classificacao"
    dados = gabarito.get("dados") if isinstance(gabarito.get("dados"), dict) else {}
    exige = gabarito.get("exige") if isinstance(gabarito.get("exige"), list) else list(LANES)

    por_lane = _por_lane(pecas)

    escolhidas: List[Dict[str, Any]] = []

    if "coleta" in exige:
        escolhidas += _escolher(rng, por_lane["coleta"], 1)

    modelos_ok = [p for p in por_lane["modelo"] if p.get("tarefa") == tarefa]
    if "modelo" in exige:
        escolhidas += _escolher(rng, modelos_ok, 2)

    metricas_ok = [p for p in por_lane["metrica"] if p.get("grupo") == tarefa]
    if "metrica" in exige:
        escolhidas += _escolher(rng, metricas_ok, 2)

    # Pré-processamento útil é o que as regras vão cobrar: preencher faltantes, converter
    # texto e escalar quando o modelo sorteado depende de distância.
    familias_necessarias = []
    if dados.get("faltantes"):
        familias_necessarias.append("imputacao")
    if dados.get("texto"):
        familias_necessarias.append("encoder")
    precisa_escala = dados.get("escalas_diferentes") or any(
        p["valor"] in MODELOS_SENSIVEIS_A_ESCALA for p in escolhidas if p["lane"] == "modelo"
    )
    if precisa_escala:
        familias_necessarias.append("escala")

    for familia in familias_necessarias:
        candidatas = [p for p in por_lane["pre_processamento"] if p.get("familia") == familia]
        escolhidas += _escolher(rng, candidatas, 1)

    return escolhidas


def _garantir_minimo(
    rng: random.Random,
    catalogo: List[Dict[str, Any]],
    gabarito: Dict[str, Any],
    uteis: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Completa o tabuleiro até que exista UMA solução correta possível.

    Sem isto o desafio pode ser impossível de acertar sem que ninguém perceba: se a lane
    exigida não recebeu peça (professor curou só um modelo, vetou todas as métricas do grupo,
    ou pediu a etapa de pré-processamento sem que a base exija nenhuma família), a regra
    `estrutura-minima` (peso 3) fica insatisfazível e o aluno perde ponto por uma configuração
    que não é dele.

    Trabalha sobre o catálogo INTEIRO de propósito: se o `vetar` do professor é o que impede a
    solução, o mínimo vence o veto — em silêncio, porque a alternativa (recusar a criação)
    deixaria a turma sem atividade.
    """
    tarefa = gabarito.get("tarefa") or "classificacao"
    dados = gabarito.get("dados") if isinstance(gabarito.get("dados"), dict) else {}
    exige = gabarito.get("exige") if isinstance(gabarito.get("exige"), list) else list(LANES)
    por_lane = _por_lane(catalogo)

    escolhidas = list(uteis)
    valores = {p["valor"] for p in escolhidas}

    def acrescentar(candidatas: List[Dict[str, Any]]) -> None:
        candidatas = [p for p in candidatas if p["valor"] not in valores]
        for peca in _escolher(rng, candidatas, 1):
            escolhidas.append(peca)
            valores.add(peca["valor"])

    def tem(lane: str, filtro=None) -> bool:
        return any(p["lane"] == lane and (filtro is None or filtro(p)) for p in escolhidas)

    if "coleta" in exige and not tem("coleta"):
        acrescentar(por_lane["coleta"])

    if "modelo" in exige and not tem("modelo", lambda p: p.get("tarefa") == tarefa):
        acrescentar([p for p in por_lane["modelo"] if p.get("tarefa") == tarefa])

    if "metrica" in exige and not tem("metrica", lambda p: p.get("grupo") == tarefa):
        acrescentar([p for p in por_lane["metrica"] if p.get("grupo") == tarefa])

    # Famílias que a rubrica vai cobrar por causa da base descrita no enunciado.
    familias = []
    if dados.get("faltantes"):
        familias.append("imputacao")
    if dados.get("texto"):
        familias.append("encoder")
    if dados.get("escalas_diferentes") or any(
        p["valor"] in MODELOS_SENSIVEIS_A_ESCALA for p in escolhidas if p["lane"] == "modelo"
    ):
        familias.append("escala")
    for familia in familias:
        if not tem("pre_processamento", lambda p, f=familia: p.get("familia") == f):
            acrescentar([p for p in por_lane["pre_processamento"] if p.get("familia") == familia])

    # A etapa pode ser exigida sem que a base peça família nenhuma (era o furo da caixa
    # "Exigir a etapa de pré-processamento"): então qualquer peça de pré-proc serve.
    if "pre_processamento" in exige and not tem("pre_processamento"):
        acrescentar(por_lane["pre_processamento"])

    return escolhidas


def _distratores(
    rng: random.Random,
    pecas: List[Dict[str, Any]],
    gabarito: Dict[str, Any],
    ja_escolhidas: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Peças plausíveis mas erradas para ESTE enunciado, tiradas do catálogo."""
    tarefa = gabarito.get("tarefa") or "classificacao"
    dados = gabarito.get("dados") if isinstance(gabarito.get("dados"), dict) else {}
    usados = {p["valor"] for p in ja_escolhidas}
    familias_uteis = {p.get("familia") for p in ja_escolhidas if p["lane"] == "pre_processamento"}

    candidatas: List[Dict[str, Any]] = []
    for peca in pecas:
        if peca["valor"] in usados:
            continue
        lane = peca["lane"]
        if lane == "modelo" and peca.get("tarefa") and peca["tarefa"] != tarefa:
            candidatas.append(peca)
        elif lane == "metrica" and peca.get("grupo") and peca["grupo"] != tarefa:
            candidatas.append(peca)
        elif lane == "pre_processamento":
            familia = peca.get("familia")
            # Distrator de pré-proc: família que este enunciado não pede. Uma família
            # necessária nunca entra como distrator (senão a regra correta puniria o aluno).
            if familia in familias_uteis:
                continue
            if familia == "imputacao" and dados.get("faltantes"):
                continue
            if familia == "encoder" and dados.get("texto"):
                continue
            candidatas.append(peca)

    dificuldade = gabarito.get("dificuldade")
    quantidade = DISTRATORES_POR_DIFICULDADE.get(dificuldade, DISTRATORES_POR_DIFICULDADE[DIFICULDADE_PADRAO])
    return _escolher(rng, candidatas, quantidade)


async def montar_tabuleiro(
    atividade: Dict[str, Any],
    user_id: str,
    tentativa: int,
    pecas_catalogo: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Tabuleiro da tentativa: peças embaralhadas + papel de cada uma.

    O `papel` ("util"/"distrator") é interno da correção — o router NÃO devolve esse campo
    ao aluno, senão o desafio se resolve olhando a resposta da API.
    """
    pecas = pecas_catalogo if pecas_catalogo is not None else await carregar_pecas()
    gabarito = atividade.get("gabarito") if isinstance(atividade.get("gabarito"), dict) else {}

    vetar = {v for v in (gabarito.get("vetar") or []) if isinstance(v, str)}
    disponiveis = [p for p in pecas.values() if p["valor"] not in vetar]

    rng = random.Random(_semente(str(atividade.get("_id") or atividade.get("id") or ""), user_id, tentativa))

    fixadas = [pecas[v] for v in (gabarito.get("fixar") or []) if isinstance(v, str) and v in pecas]
    # `sortear_pecas: False` = o professor curou as peças; o sistema não acrescenta variedade,
    # só o mínimo. Ausente (desafios antigos) significa sortear, como sempre foi.
    sortear = gabarito.get("sortear_pecas", True) is not False
    uteis = _uteis(rng, disponiveis, gabarito) if sortear else []
    # Peça escolhida pelo professor conta como útil (ele a quer no tabuleiro de propósito).
    for peca in fixadas:
        if peca["valor"] not in {p["valor"] for p in uteis}:
            uteis.append(peca)

    # Invariante do módulo: o tabuleiro sempre permite uma solução correta.
    uteis = _garantir_minimo(rng, list(pecas.values()), gabarito, uteis)

    distratores = _distratores(rng, disponiveis, gabarito, uteis)

    tabuleiro = [{**p, "papel": "util"} for p in uteis] + [{**p, "papel": "distrator"} for p in distratores]
    rng.shuffle(tabuleiro)
    return {
        "tentativa": tentativa,
        "pecas": tabuleiro,
        "lanes": list(LANES),
    }


def papeis(tabuleiro: Dict[str, Any]) -> Dict[str, str]:
    """{valor: papel} — o que a rubrica usa para julgar a regra `sem-distrator`."""
    return {p["valor"]: p.get("papel", "util") for p in (tabuleiro.get("pecas") or [])}
