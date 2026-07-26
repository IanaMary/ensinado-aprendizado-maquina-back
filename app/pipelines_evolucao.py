"""Evolução do aluno numa mesma base de dados.

Responde "melhorei em relação à minha última tentativa?" sem cair na armadilha de dar nota
absoluta: métrica crua não é comparável entre bases (acurácia 0,92 é fraca no iris e ótima
no titanic). Por isso a leitura é sempre **relativa** a duas réguas:

1. o **chute burro** da própria base (ver `app/metricas/resultado.py`);
2. as **tentativas anteriores do próprio aluno** na mesma base.

Agrupa por `(dataset, alvo)` — a identidade já persistida em `resultadoColetaDado` — e
atravessa atividades e projetos livres, porque o aluno normalmente volta à mesma base em
momentos diferentes do semestre.

Só agrega o que já está gravado em `db.pipelines`: nada é retreinado nem recalculado.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.metricas.resultado import (
    METRICA_PADRAO_POR_TAREFA,
    baseline_trivial,
    chaves_metrica,
    ordem_da_metrica,
    valor_metrica,
)


def tarefa_do_pipeline(coleta: dict) -> str:
    """Mesma convenção do catálogo: sem rótulo é agrupamento; senão o tipo do alvo decide."""
    coleta = coleta or {}
    if coleta.get("dadosRotulados") is False:
        return "agrupamento"
    return "classificacao" if coleta.get("preverCategoria", True) else "regressao"


def chave_da_base(coleta: dict) -> Optional[tuple]:
    """Identidade da base: dataset + alvo. `None` quando o pipeline não tem dados
    (rascunho), caso em que não há o que comparar.

    A ordem importa: `nomeDataset` (ex.: "Iris") e o nome do arquivo são ESTÁVEIS entre
    sessões, enquanto `datasetId` é o id do arquivo criado a cada carregamento
    (`coleta-dado.component.ts` faz `datasetId = resultado.id`). Preferir o id
    fragmentaria a história — cada vez que o aluno recarregasse o mesmo dataset viraria
    uma "base" nova e ele nunca veria evolução.
    """
    coleta = coleta or {}
    dataset = (coleta.get("nomeDataset") or (coleta.get("treino") or {}).get("nomeArquivo")
               or coleta.get("datasetId"))
    if not dataset:
        return None
    return (str(dataset), str(coleta.get("target") or ""))


def _resumo_do_pipeline(doc: dict) -> Dict[str, Any]:
    """O que mudou entre tentativas — é isso que explica a variação da métrica."""
    modelo = (doc.get("modeloSelecionado") or {}).get("valor")
    modelos = [m.get("valor") for m in (doc.get("modelosSelecionados") or [])
               if isinstance(m, dict) and m.get("valor")]
    pre_proc = [p.get("valor") for p in ((doc.get("preProcessamentoConfig") or {}).get("itens") or [])
                if isinstance(p, dict) and p.get("valor")]
    return {
        "modelos": modelos or ([modelo] if modelo else []),
        "pre_processamento": pre_proc,
        "divisao_treino": (doc.get("resultadoColetaDado") or {}).get("porcentagemTreino"),
    }


def _mudancas(anterior: Dict[str, Any], atual: Dict[str, Any]) -> List[str]:
    """Diferenças em linguagem de sala de aula, para o aluno ligar causa e efeito."""
    mudancas = []
    if set(anterior["modelos"]) != set(atual["modelos"]):
        mudancas.append("trocou o modelo")
    novos = set(atual["pre_processamento"]) - set(anterior["pre_processamento"])
    sairam = set(anterior["pre_processamento"]) - set(atual["pre_processamento"])
    if novos:
        mudancas.append("acrescentou pré-processamento")
    if sairam:
        mudancas.append("tirou pré-processamento")
    if anterior["divisao_treino"] != atual["divisao_treino"]:
        mudancas.append("mudou a divisão treino/teste")
    return mudancas


async def montar_evolucao(docs: List[dict],
                          criterio_por_atividade: Dict[str, dict] | None = None) -> List[Dict[str, Any]]:
    """Agrupa os pipelines por base e devolve a trajetória de cada uma (mais antiga → recente).

    `criterio_por_atividade` traz o `criterio` das atividades de turma: dentro de uma
    atividade vale a métrica que o professor escolheu; fora dela, a métrica padrão da tarefa.
    """
    criterio_por_atividade = criterio_por_atividade or {}
    grupos: Dict[tuple, List[dict]] = {}
    for doc in docs:
        chave = chave_da_base(doc.get("resultadoColetaDado"))
        if chave:
            grupos.setdefault(chave, []).append(doc)

    bases = []
    for (dataset, alvo), pipelines_da_base in grupos.items():
        # Mais antigo → mais recente: a trajetória só faz sentido em ordem cronológica.
        ordenados = sorted(pipelines_da_base, key=lambda d: d.get("dataCriacao") or d.get("dataModificacao"))
        tarefa = tarefa_do_pipeline((ordenados[-1].get("resultadoColetaDado") or {}))

        criterio = next((criterio_por_atividade[d["atividade_id"]]
                         for d in reversed(ordenados)
                         if d.get("atividade_id") in criterio_por_atividade), None)
        metrica = (criterio or {}).get("metrica") or METRICA_PADRAO_POR_TAREFA.get(tarefa, "accuracy_score")
        ordem = (criterio or {}).get("ordem") or ordem_da_metrica(metrica)
        chaves = await chaves_metrica(metrica)

        tentativas, baseline = [], None
        anterior_resumo = None
        for doc in ordenados:
            resultados = doc.get("resultadosDasAvaliacoes") or {}
            valor = valor_metrica(resultados, chaves, ordem)
            if baseline is None:
                baseline = baseline_trivial(resultados, metrica)
            resumo = _resumo_do_pipeline(doc)
            tentativas.append({
                "pipeline_id": str(doc["_id"]),
                "nome": doc.get("nome"),
                "data": doc.get("dataCriacao") or doc.get("dataModificacao"),
                "valor": valor,
                "mudancas": _mudancas(anterior_resumo, resumo) if anterior_resumo else [],
                **resumo,
            })
            anterior_resumo = resumo

        avaliadas = [t for t in tentativas if t["valor"] is not None]
        if not avaliadas:
            continue  # base só com rascunhos: nada a comparar

        melhor = (max(t["valor"] for t in avaliadas) if ordem != "asc"
                  else min(t["valor"] for t in avaliadas))
        ultima = avaliadas[-1]["valor"]
        anteriores = [t["valor"] for t in avaliadas[:-1]]
        melhor_anterior = None
        if anteriores:
            melhor_anterior = max(anteriores) if ordem != "asc" else min(anteriores)

        bases.append({
            "dataset": dataset,
            "alvo": alvo,
            "tarefa": tarefa,
            "metrica": metrica,
            "ordem": ordem,
            "baseline": baseline,
            "melhor": melhor,
            "ultima": ultima,
            # Positivo = melhorou, seja a métrica de maior-é-melhor ou menor-é-melhor.
            "delta_vs_anterior": (None if melhor_anterior is None else
                                  round((ultima - melhor_anterior) * (1 if ordem != "asc" else -1), 4)),
            "delta_vs_baseline": (None if baseline is None else
                                  round((ultima - baseline) * (1 if ordem != "asc" else -1), 4)),
            "tentativas": tentativas,
        })

    bases.sort(key=lambda b: b["tentativas"][-1]["data"] or "", reverse=True)
    return bases
