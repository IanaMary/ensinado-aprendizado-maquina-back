"""Leitura dos resultados de avaliação já gravados em `db.pipelines`.

Extraído de `app/routers/turmas.py` (ranking) para ser usado também pela evolução do aluno:
as duas telas precisam responder "qual foi o valor da métrica X neste pipeline?" e a
resposta tem sutilezas (rótulo × slug, valores não numéricos, vários modelos por pipeline)
que não devem existir em duas cópias.

Aqui também mora o **chute burro** — a régua honesta para dizer se um modelo é bom, já que
métrica crua não é comparável entre bases (acurácia 0,92 é fraca no iris e ótima no titanic).
Ele é derivado do que JÁ está gravado, sem reprocessar dados:

- classificação: proporção da classe majoritária, lida das somas das linhas da matriz de
  confusão (o que um "modelo" que sempre chuta a classe mais comum acertaria);
- R²: 0 por definição — prever a média dá exatamente R² = 0;
- demais (MAE/MSE/RMSE, agrupamento): sem baseline barato e honesto, devolve None.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.database import opcoes_metricas

# Métrica que define "melhorou" quando o aluno escolheu várias fora de uma atividade.
METRICA_PADRAO_POR_TAREFA = {
    "classificacao": "accuracy_score",
    "regressao": "r2_score",
    "agrupamento": "silhouette_score",
}

# Métricas em que MENOR é melhor.
METRICAS_ASCENDENTES = {
    "mean_squared_error", "root_mean_squared_error", "mean_absolute_error",
    "davies_bouldin_score",
}

_LABEL_MATRIZ_CONFUSAO = "Matriz de confusão"


def ordem_da_metrica(slug: str) -> str:
    return "asc" if slug in METRICAS_ASCENDENTES else "desc"


async def chaves_metrica(slug: str) -> List[str]:
    """Chaves candidatas p/ ler `resultadosDasAvaliacoes`.

    A avaliação indexa o dict pelo RÓTULO da métrica (ex.: 'Acurácia'), mas o critério da
    atividade guarda o `valor`/slug (ex.: 'accuracy_score'). Resolvemos o rótulo em
    `db.metricas` e tentamos ambos, para ser robusto a como a submissão foi salva.
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


def valor_metrica(resultados: dict, chaves: list, ordem: str):
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


def _matrizes_confusao(resultados: dict) -> List[Dict[str, Any]]:
    por_modelo = (resultados or {}).get(_LABEL_MATRIZ_CONFUSAO) or {}
    return [v for v in por_modelo.values()
            if isinstance(v, dict) and isinstance(v.get("matriz"), list)]


def baseline_trivial(resultados: dict, metrica: str) -> Optional[float]:
    """Quanto o "chute burro" faria nesta base, na métrica pedida (None se não dá para
    saber sem reprocessar os dados)."""
    if metrica == "r2_score":
        # Prever sempre a média do alvo dá R² = 0. É a referência natural da regressão:
        # R² negativo significa que o modelo é PIOR que chutar a média.
        return 0.0

    if metrica != "accuracy_score":
        return None

    for cm in _matrizes_confusao(resultados):
        try:
            linhas = [sum(l) for l in cm["matriz"] if isinstance(l, list)]
            total = sum(linhas)
            if total > 0:
                # Sempre chutar a classe mais frequente acerta a fração dela no teste.
                return round(max(linhas) / total, 4)
        except Exception:
            continue
    return None
