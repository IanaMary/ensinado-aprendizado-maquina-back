"""Perfil de um dataset de exemplo, para o desafio de montagem nascer de uma base real.

O desafio **não executa nada** — a rubrica decide o que cobrar a partir das flags do gabarito
(`dados.faltantes`, `dados.texto`, `dados.escalas_diferentes`). Antes elas eram três caixas que
o professor marcava à mão, o que permitia um enunciado que **desmentia a base**: cobrar
imputação de uma base sem valores faltando torna a regra correspondente impossível de
satisfazer, e o aluno perde ponto por algo que não existe.

Aqui essas flags são lidas do **dataframe de verdade**, junto do texto que descreve a tarefa
(que a plataforma já mantém em `dataset_config`). O professor ainda pode ajustar as flags na
tela — é ele quem decide o que quer cobrar.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.models.dataset_config import get_dataset_config
from app.models.dataset_loaders import carregar_dataframe

# Acima de quantas vezes a diferença entre a maior e a menor amplitude conta como
# "escalas bem diferentes". 10× é conservador: separa (0–1 × 0–10.000) de variações
# normais entre colunas parecidas, que não justificam cobrar um scaler.
RAZAO_ESCALAS = 10.0

# Perfil é estável por dataset (o gerador usa seed fixa), então vale cachear: a inspeção
# carrega um dataframe e a tela do professor consulta a cada troca de dataset.
_cache: Dict[str, Dict[str, Any]] = {}

DADOS_CONSERVADOR = {"faltantes": False, "texto": False, "escalas_diferentes": False}


def inspecionar_dados(df, alvo: Optional[str] = None) -> Dict[str, bool]:
    """As três características que a rubrica sabe cobrar, lidas do dataframe.

    Conservador por opção: qualquer dúvida devolve `False` — cobrar uma etapa que a base não
    pede é pior que deixar de cobrar (a regra ficaria impossível).
    """
    if df is None or getattr(df, "empty", True):
        return dict(DADOS_CONSERVADOR)

    colunas_x = [c for c in df.columns if c != alvo]

    faltantes = bool(df[colunas_x].isnull().any().any()) if colunas_x else False

    numericas = [c for c in colunas_x if str(df[c].dtype) in ("int64", "float64", "int32", "float32")]
    texto = len(numericas) < len(colunas_x)

    escalas_diferentes = False
    amplitudes = []
    for coluna in numericas:
        serie = df[coluna].dropna()
        if serie.empty:
            continue
        amplitude = float(serie.max()) - float(serie.min())
        if amplitude > 0:
            amplitudes.append(amplitude)
    if len(amplitudes) >= 2:
        escalas_diferentes = (max(amplitudes) / min(amplitudes)) >= RAZAO_ESCALAS

    return {"faltantes": faltantes, "texto": texto, "escalas_diferentes": escalas_diferentes}


def _enunciado(ds) -> str:
    """Enunciado sugerido: a pergunta-guia (linguagem de sala de aula) mais a descrição."""
    partes = [p for p in (ds.pergunta_guia, ds.descricao) if p]
    if ds.descricao_target:
        partes.append(f"O que se quer prever: {ds.descricao_target}.")
    return " ".join(partes)


def perfil_do_dataset(dataset_id: str) -> Optional[Dict[str, Any]]:
    """Tudo o que a criação do desafio precisa de um dataset. `None` se o id não existe."""
    if dataset_id in _cache:
        return _cache[dataset_id]

    ds = get_dataset_config(dataset_id)
    if ds is None:
        return None

    # A carga é a única parte que pode falhar (rede do UCI, biblioteca ausente). Falhar aqui
    # não pode impedir a criação do desafio: cai no conservador e o professor ajusta.
    dados = dict(DADOS_CONSERVADOR)
    try:
        df = carregar_dataframe(dataset_id, ds)
        dados = inspecionar_dados(df, alvo=ds.target or "target")
    except Exception:
        pass

    perfil = {
        "dataset": ds.id,
        "nome": ds.nome,
        "tarefa": ds.tipo.value,
        "fonte": ds.fonte,
        "n_amostras": ds.n_amostras,
        "pergunta": ds.pergunta_guia,
        "descricao": ds.descricao,
        "alvo": ds.descricao_target,
        "atributos": ds.descricao_features,
        "modelo_recomendado": ds.modelo_recomendado,
        "enunciado_sugerido": _enunciado(ds),
        "dados": dados,
    }
    _cache[dataset_id] = perfil
    return perfil


def tarefa_do_dataset(dataset_id: str) -> Optional[str]:
    """Tarefa (`classificacao`/`regressao`/`agrupamento`) do dataset, sem carregar dados.

    O vocabulário de `DatasetType` é o MESMO do gabarito, então não há tradução — é por isso
    que o servidor pode derivar a tarefa do dataset sem confiar no cliente.
    """
    ds = get_dataset_config(dataset_id)
    return ds.tipo.value if ds else None


def nome_do_dataset(dataset_id: str) -> Optional[str]:
    ds = get_dataset_config(dataset_id)
    return ds.nome if ds else None
