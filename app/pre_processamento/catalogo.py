"""Catálogo canônico de pré-processadores.

Fonte de verdade no backend para *como* cada pré-processador roda: módulo/classe
sklearn, hiperparâmetros de instanciação e em quais colunas atua. É consumido por
`treinamento_base` para montar os specs enviados ao sandbox, e serve de base para o
seed de `db.pre_processamento`.

Mantém paridade com o código gerado no front
(`script-generator.service.ts:generatePreprocessingFunction`): os mesmos transformers,
os mesmos defaults. Assim, o que o aluno vê no script é o que o backend executa.

Campos de cada entrada:
- modulo / classe: caminho sklearn instanciado via importlib no sandbox.
- hiperparametros: kwargs passados ao construtor do transformer.
- escopo: "transform_X" (entra no Pipeline de X) ou "encode_y" (atua no target).
- aplica_em: "todas" (aplica a todas as features quando nenhuma coluna é escolhida)
  ou "colunas_escolhidas" (só roda se o aluno indicar colunas — ex.: encoders).
- trata_ausentes: True quando o transformer preenche NaN (libera a checagem dura
  de valores ausentes no treino).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Allowlist canônica de módulos Python aceitos no bloco `execucao` (modelos,
# métricas e pré-processamento). Validada nos writers (conf_pipeline) E reaplicada
# no caminho de treino (normalizar_execucao_db) como defesa em profundidade: um
# doc malicioso inserido fora da API não pode rodar módulo arbitrário no sandbox.
PREFIXOS_MODULOS_PERMITIDOS = ("sklearn.", "xgboost", "lightgbm", "yellowbrick.", "app.modelos_custom.")


def modulo_permitido(modulo: Any) -> bool:
    """True se `modulo` casa exatamente um prefixo permitido ou é um submódulo dele.
    Estrito: 'xgboost' e 'xgboost.sklearn' passam; 'xgboost_evil'/'sklearnx' não."""
    if not isinstance(modulo, str) or not modulo:
        return False
    for p in PREFIXOS_MODULOS_PERMITIDOS:
        base = p.rstrip(".")
        if modulo == base or modulo.startswith(base + "."):
            return True
    return False

# valor -> spec de execução
PRE_PROCESSAMENTO_CATALOGO: Dict[str, Dict[str, Any]] = {
    "standard_scaler": {
        "modulo": "sklearn.preprocessing",
        "classe": "StandardScaler",
        "hiperparametros": {},
        "escopo": "transform_X",
        "aplica_em": "todas",
    },
    "minmax_scaler": {
        "modulo": "sklearn.preprocessing",
        "classe": "MinMaxScaler",
        "hiperparametros": {},
        "escopo": "transform_X",
        "aplica_em": "todas",
    },
    "robust_scaler": {
        "modulo": "sklearn.preprocessing",
        "classe": "RobustScaler",
        "hiperparametros": {},
        "escopo": "transform_X",
        "aplica_em": "todas",
    },
    "normalizer": {
        "modulo": "sklearn.preprocessing",
        "classe": "Normalizer",
        "hiperparametros": {"norm": "l2"},
        "escopo": "transform_X",
        "aplica_em": "todas",
    },
    "onehot_encoder": {
        "modulo": "sklearn.preprocessing",
        "classe": "OneHotEncoder",
        # sparse_output=False mantém saída densa (compatível com ColumnTransformer +
        # set_output pandas); handle_unknown ignora categorias inéditas no teste.
        "hiperparametros": {"sparse_output": False, "handle_unknown": "ignore"},
        "escopo": "transform_X",
        "aplica_em": "colunas_escolhidas",
    },
    "ordinal_encoder": {
        "modulo": "sklearn.preprocessing",
        "classe": "OrdinalEncoder",
        "hiperparametros": {"handle_unknown": "use_encoded_value", "unknown_value": -1},
        "escopo": "transform_X",
        "aplica_em": "colunas_escolhidas",
    },
    "label_encoder": {
        "modulo": "sklearn.preprocessing",
        "classe": "LabelEncoder",
        "hiperparametros": {},
        # Atua no target. No backend é um no-op de execução: os classificadores do
        # sklearn aceitam rótulos string nativamente e `classes_` já os preserva.
        # Mantido no catálogo para paridade com o script gerado e edição no admin.
        "escopo": "encode_y",
        "aplica_em": "target",
    },
    "simple_imputer": {
        "modulo": "sklearn.impute",
        "classe": "SimpleImputer",
        "hiperparametros": {"strategy": "mean"},
        "escopo": "transform_X",
        "aplica_em": "todas",
        "trata_ausentes": True,
    },
    "polynomial_features": {
        "modulo": "sklearn.preprocessing",
        "classe": "PolynomialFeatures",
        "hiperparametros": {"degree": 2, "include_bias": False},
        "escopo": "transform_X",
        "aplica_em": "colunas_escolhidas",
    },
    "power_transformer": {
        "modulo": "sklearn.preprocessing",
        "classe": "PowerTransformer",
        "hiperparametros": {"method": "yeo-johnson"},
        "escopo": "transform_X",
        "aplica_em": "todas",
    },
}


def _hiper_para_dict(hiper: Any) -> Dict[str, Any]:
    """Normaliza hiperparâmetros vindos do DB (lista ``[{nome, valorPadrao}]`` no
    padrão dos modelos) para um dict de kwargs do construtor. Aceita dict direto."""
    if isinstance(hiper, dict):
        return dict(hiper)
    kwargs: Dict[str, Any] = {}
    for h in hiper or []:
        if not isinstance(h, dict):
            continue
        nome = h.get("nome") or h.get("nomeHiperparametro")
        if not nome:
            continue
        if "valorPadrao" in h:
            kwargs[nome] = h["valorPadrao"]
        elif "default" in h:
            kwargs[nome] = h["default"]
    return kwargs


def normalizar_execucao_db(execucao: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Converte um bloco ``execucao`` de ``db.pre_processamento`` no formato interno
    do catálogo. Retorna ``None`` quando incompleto (cai no fallback estático)."""
    if not isinstance(execucao, dict):
        return None
    modulo = execucao.get("modulo")
    classe = execucao.get("classe")
    if not modulo or not classe:
        return None
    # Defesa em profundidade: rejeita módulo fora da allowlist mesmo vindo do DB.
    if not modulo_permitido(modulo):
        return None
    return {
        "modulo": modulo,
        "classe": classe,
        "hiperparametros": _hiper_para_dict(execucao.get("hiperparametros", {})),
        "escopo": execucao.get("escopo", "transform_X"),
        "aplica_em": execucao.get("aplica_em", "todas"),
        "trata_ausentes": bool(execucao.get("trata_ausentes", False)),
    }


def catalogo_com_overrides(
    docs_db: Optional[List[Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    """Mescla o catálogo estático com os blocos ``execucao`` de ``db.pre_processamento``.
    O DB tem prioridade, permitindo que um pré-processador editado/registrado pelo
    admin seja de fato executado. Itens só no DB também entram."""
    catalogo = {k: dict(v) for k, v in PRE_PROCESSAMENTO_CATALOGO.items()}
    for doc in docs_db or []:
        valor = (doc or {}).get("valor")
        if not valor:
            continue
        norm = normalizar_execucao_db(doc.get("execucao"))
        if norm:
            catalogo[valor] = norm
    return catalogo


def montar_specs_pre_processamento(
    itens: Optional[List[Dict[str, Any]]],
    catalogo: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Resolve os itens escolhidos pelo aluno (``[{valor, colunas?}]``) em specs de
    execução prontos para o sandbox.

    ``catalogo`` permite injetar overrides do DB (ver ``catalogo_com_overrides``);
    por padrão usa o catálogo estático dos 10 built-ins.

    Itens com escopo ``encode_y`` e itens ``colunas_escolhidas`` sem colunas são
    descartados (não têm efeito), espelhando o comportamento do script gerado.
    Itens com ``valor`` desconhecido são ignorados.
    """
    catalogo = catalogo if catalogo is not None else PRE_PROCESSAMENTO_CATALOGO
    specs: List[Dict[str, Any]] = []
    for item in itens or []:
        valor = (item or {}).get("valor")
        base = catalogo.get(valor)
        if not base:
            continue
        if base["escopo"] != "transform_X":
            continue
        colunas = [c for c in (item.get("colunas") or []) if c]
        if base.get("aplica_em") == "colunas_escolhidas" and not colunas:
            # Encoders/polynomial sem colunas não fazem nada (igual ao front).
            continue
        specs.append(
            {
                "valor": valor,
                "modulo": base["modulo"],
                "classe": base["classe"],
                "hiperparametros": dict(base.get("hiperparametros", {})),
                "colunas": colunas,
            }
        )
    return specs


def tem_imputer(
    itens: Optional[List[Dict[str, Any]]],
    catalogo: Optional[Dict[str, Dict[str, Any]]] = None,
) -> bool:
    """True se algum item escolhido trata valores ausentes (libera a checagem de NaN)."""
    catalogo = catalogo if catalogo is not None else PRE_PROCESSAMENTO_CATALOGO
    for item in itens or []:
        base = catalogo.get((item or {}).get("valor"))
        if base and base.get("trata_ausentes"):
            return True
    return False
