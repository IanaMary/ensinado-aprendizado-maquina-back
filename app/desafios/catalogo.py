"""Leitura e normalização das peças do desafio a partir do catálogo do pipeline.

As peças NÃO são uma lista nova a manter: saem de `db.modelos`, `db.metricas`,
`db.pre_processamento` e `db.coleta_dados` — os mesmos documentos que o dashboard usa.
Assim, um modelo novo cadastrado pelo admin já pode aparecer num desafio (como peça útil
ou como distrator) sem mudança de código.

Cada peça normalizada carrega o mínimo que a rubrica precisa para decidir
compatibilidade, sem reimplementar o conhecimento do catálogo:

- modelo:  `prever_categoria` / `dados_rotulados` (tarefa) e `metricas` (compatíveis)
- metrica: `grupo` (classificacao/regressao/agrupamento)
- pre_processamento: `familia` derivada da CLASSE sklearn do bloco `execucao`
  (escala/imputacao/encoder/outro) — derivar da classe evita uma lista paralela de
  slugs que envelheceria a cada item novo.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.database import (
    opcoes_coletas,
    opcoes_metricas,
    opcoes_modelos,
    opcoes_pre_processamento,
)
from app.pre_processamento.catalogo import PRE_PROCESSAMENTO_CATALOGO

# Lanes do quebra-cabeça — espelham as colunas do dashboard clássico
# (`execucoes.component.html`), para o aluno reconhecer o mesmo tabuleiro depois.
LANES = ("coleta", "pre_processamento", "modelo", "metrica")

# Famílias de pré-processamento, derivadas da classe sklearn do `execucao`.
CLASSES_ESCALA = {"StandardScaler", "MinMaxScaler", "RobustScaler", "MaxAbsScaler", "Normalizer"}
CLASSES_IMPUTACAO = {"SimpleImputer", "KNNImputer", "IterativeImputer"}
CLASSES_ENCODER = {"OneHotEncoder", "OrdinalEncoder", "LabelEncoder", "LabelBinarizer"}

# Métricas por tarefa quando o doc do catálogo não tem `grupo` (mesmo fallback que
# `app/metricas/metricas.py` usa nos gates de avaliação).
METRICAS_AGRUPAMENTO = {"silhouette_score", "calinski_harabasz_score", "davies_bouldin_score"}
METRICAS_REGRESSAO = {"r2_score", "mean_squared_error", "root_mean_squared_error", "mean_absolute_error"}

TAREFAS = ("classificacao", "regressao", "agrupamento")


def familia_pre_processamento(classe: Optional[str]) -> str:
    if classe in CLASSES_ESCALA:
        return "escala"
    if classe in CLASSES_IMPUTACAO:
        return "imputacao"
    if classe in CLASSES_ENCODER:
        return "encoder"
    return "outro"


def grupo_da_metrica(doc: Dict[str, Any]) -> Optional[str]:
    grupo = doc.get("grupo")
    if grupo in TAREFAS:
        return grupo
    valor = doc.get("valor")
    if valor in METRICAS_AGRUPAMENTO:
        return "agrupamento"
    if valor in METRICAS_REGRESSAO:
        return "regressao"
    return None


def tarefa_do_modelo(doc: Dict[str, Any]) -> str:
    """Tarefa que o modelo resolve, na convenção já usada pelo catálogo:
    `dados_rotulados=False` → agrupamento; senão `prever_categoria` decide."""
    if doc.get("dados_rotulados") is False:
        return "agrupamento"
    return "classificacao" if doc.get("prever_categoria", True) else "regressao"


def _habilitado(doc: Dict[str, Any]) -> bool:
    return doc.get("habilitado", True) is not False


def _nome(doc: Dict[str, Any], padrao: str) -> str:
    return doc.get("nome") or doc.get("label") or doc.get("titulo") or padrao


async def _listar(colecao, projecao: Dict[str, int]) -> List[Dict[str, Any]]:
    try:
        return [d async for d in colecao.find({}, projecao)]
    except Exception:
        return []


async def carregar_pecas() -> Dict[str, Dict[str, Any]]:
    """Todas as peças candidatas, indexadas por `valor` (a chave que o front envia).

    Defensivo por opção: se uma coleção falhar, as demais lanes seguem valendo — um
    desafio com menos peças é melhor que um erro 500 na aula.
    """
    pecas: Dict[str, Dict[str, Any]] = {}

    for doc in await _listar(opcoes_coletas, {"valor": 1, "nome": 1, "habilitado": 1}):
        if not _habilitado(doc) or not doc.get("valor"):
            continue
        pecas[doc["valor"]] = {
            "valor": doc["valor"],
            "lane": "coleta",
            "nome": _nome(doc, doc["valor"]),
        }

    for doc in await _listar(
        opcoes_pre_processamento,
        {"valor": 1, "nome": 1, "habilitado": 1, "execucao": 1, "grupo": 1},
    ):
        valor = doc.get("valor")
        if not _habilitado(doc) or not valor:
            continue
        execucao = doc.get("execucao") or {}
        classe = execucao.get("classe") or (PRE_PROCESSAMENTO_CATALOGO.get(valor) or {}).get("classe")
        pecas[valor] = {
            "valor": valor,
            "lane": "pre_processamento",
            "nome": _nome(doc, valor),
            "familia": familia_pre_processamento(classe),
        }

    for doc in await _listar(
        opcoes_modelos,
        {"valor": 1, "nome": 1, "habilitado": 1, "prever_categoria": 1,
         "dados_rotulados": 1, "metricas": 1},
    ):
        valor = doc.get("valor")
        if not _habilitado(doc) or not valor:
            continue
        pecas[valor] = {
            "valor": valor,
            "lane": "modelo",
            "nome": _nome(doc, valor),
            "tarefa": tarefa_do_modelo(doc),
            "metricas": [m for m in (doc.get("metricas") or []) if isinstance(m, str)],
        }

    for doc in await _listar(opcoes_metricas, {"valor": 1, "label": 1, "habilitado": 1, "grupo": 1}):
        valor = doc.get("valor")
        if not _habilitado(doc) or not valor:
            continue
        pecas[valor] = {
            "valor": valor,
            "lane": "metrica",
            "nome": _nome(doc, valor),
            "grupo": grupo_da_metrica(doc),
        }

    return pecas
