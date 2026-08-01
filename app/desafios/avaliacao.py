"""Aplicação da rubrica: montagem do aluno -> nota + regras avaliadas.

A nota é a fração dos pesos satisfeitos entre as regras APLICÁVEIS, escalada em 0–10 para
ser legível em sala. Devolvemos também `pontos`/`pontos_max` para o professor conseguir
explicar de onde veio a nota, e a lista completa de regras (certas e erradas) porque o
acerto também ensina.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.desafios.catalogo import LANES
from app.desafios.regras import Contexto, regras_aplicaveis

NOTA_MAXIMA = 10.0


def normalizar_montagem(bruta: Any) -> Dict[str, List[str]]:
    """Aceita só o formato esperado: {lane: [valor, ...]} com lanes conhecidas e strings.

    Entrada do aluno é entrada não confiável: qualquer coisa fora disso é descartada em vez
    de explodir na correção (e a regra `estrutura-minima` cobra a lane que ficou vazia).
    """
    montagem: Dict[str, List[str]] = {lane: [] for lane in LANES}
    if not isinstance(bruta, dict):
        return montagem
    for lane in LANES:
        valores = bruta.get(lane)
        if isinstance(valores, str):
            valores = [valores]
        if not isinstance(valores, list):
            continue
        montagem[lane] = [v for v in valores if isinstance(v, str) and v][:20]
    return montagem


def avaliar_montagem(
    montagem_bruta: Any,
    gabarito: Dict[str, Any],
    pecas: Dict[str, Dict[str, Any]],
    ofertadas: Dict[str, str],
) -> Dict[str, Any]:
    montagem = normalizar_montagem(montagem_bruta)

    # Submissão vazia não recebe o detalhamento das regras: várias regras têm
    # aplicabilidade decidida SÓ pelo gabarito (ex.: "há faltantes?", "há texto?")
    # e disparavam mesmo sem o aluno montar nada, vazando a forma do gabarito de
    # graça. Sem peça posta, devolve nota 0 e uma orientação genérica.
    if not any(valores for valores in montagem.values()):
        return {
            "nota": 0.0,
            "nota_max": NOTA_MAXIMA,
            "pontos": 0,
            "pontos_max": 0,
            "acertou_tudo": False,
            "regras": [],
            "montagem": montagem,
            "mensagem": "Monte as peças no tabuleiro para receber a avaliação por etapa.",
        }

    ctx = Contexto(montagem=montagem, gabarito=gabarito or {}, pecas=pecas, ofertadas=ofertadas or {})

    avaliadas: List[Dict[str, Any]] = []
    pontos = 0
    pontos_max = 0
    for regra in regras_aplicaveis(ctx):
        try:
            ok = bool(regra.checa(ctx))
        except Exception:
            continue  # regra que falha não vira ponto perdido do aluno
        pontos_max += regra.peso
        if ok:
            pontos += regra.peso
        avaliadas.append({
            "id": regra.id,
            "titulo": regra.titulo,
            "ok": ok,
            "peso": regra.peso,
            "texto": regra.texto_ok if ok else regra.texto_erro,
        })

    nota = round(NOTA_MAXIMA * pontos / pontos_max, 1) if pontos_max else 0.0
    return {
        "nota": nota,
        "nota_max": NOTA_MAXIMA,
        "pontos": pontos,
        "pontos_max": pontos_max,
        "acertou_tudo": pontos_max > 0 and pontos == pontos_max,
        "regras": avaliadas,
        "montagem": montagem,
    }
