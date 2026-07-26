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


def _uteis(rng: random.Random, pecas: List[Dict[str, Any]], gabarito: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Peças que permitem montar uma solução correta do enunciado."""
    tarefa = gabarito.get("tarefa") or "classificacao"
    dados = gabarito.get("dados") if isinstance(gabarito.get("dados"), dict) else {}
    exige = gabarito.get("exige") if isinstance(gabarito.get("exige"), list) else list(LANES)

    por_lane: Dict[str, List[Dict[str, Any]]] = {lane: [] for lane in LANES}
    for peca in pecas:
        por_lane[peca["lane"]].append(peca)

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
    uteis = _uteis(rng, disponiveis, gabarito)
    # Peça fixada pelo professor conta como útil (ele a quer no tabuleiro de propósito).
    for peca in fixadas:
        if peca["valor"] not in {p["valor"] for p in uteis}:
            uteis.append(peca)

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
