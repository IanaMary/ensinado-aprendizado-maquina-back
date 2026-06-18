import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException
from app.deps import pd, metricas_disponiveis
from app.database import modelos_treinados, arquivos, opcoes_metricas
from app.schemas.schemas import AvaliacaoModelosRequest
from app.funcoes_genericas.validacao import validar_object_id, MAX_ARQUIVO_BASE64
from bson import ObjectId
import importlib
import joblib
import base64
import io
import hashlib
import sys
import types
from typing import Optional
from sklearn.metrics import confusion_matrix, silhouette_score, calinski_harabasz_score, davies_bouldin_score, mean_squared_error
from sklearn.base import is_regressor

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# DejaVu Sans vem empacotada com o matplotlib (sempre disponível). O estilo do
# Yellowbrick troca font.sans-serif por Arial/Liberation Sans — ausentes no servidor —
# o que faz títulos, rótulos de eixos e legendas não renderizarem. Reafirmamos a fonte
# antes de cada savefig em _figura_para_base64.
_FONTE_SANS = ["DejaVu Sans", "Liberation Sans", "Arial", "sans-serif"]
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["font.sans-serif"] = _FONTE_SANS
try:
    from setuptools._distutils.version import LooseVersion
    distutils_module = types.ModuleType("distutils")
    version_module = types.ModuleType("distutils.version")
    version_module.LooseVersion = LooseVersion
    sys.modules.setdefault("distutils", distutils_module)
    sys.modules.setdefault("distutils.version", version_module)
except Exception:
    pass
from yellowbrick.classifier import ClassificationReport, ClassPredictionError, ConfusionMatrix
from yellowbrick.target import ClassBalance
from yellowbrick.cluster import SilhouetteVisualizer, InterclusterDistance, KElbowVisualizer
from yellowbrick.regressor import ResidualsPlot, PredictionError, CooksDistance
from matplotlib.colors import LinearSegmentedColormap

# ---- Esquema de cores das figuras alinhado ao tema roxo do sistema ----
# Mesmos tons usados na UI (roxo primário/secundário + acentos das fases da Trilha).
PALETA_TEMA = ["#7C3AED", "#A855F7", "#C026D3", "#3B82F6", "#EC4899", "#F59E0B", "#22C55E"]
# Colormap roxo (lavanda clara -> roxo -> roxo escuro) para mapas de calor
# (Matriz de confusão, Relatório de classificação). Registrado por nome porque o
# Yellowbrick espera uma string de colormap, não o objeto.
_CMAP_TEMA = LinearSegmentedColormap.from_list("iana_roxo", ["#F3EEFB", "#A855F7", "#4C1D95"])
try:
    matplotlib.colormaps.register(_CMAP_TEMA, force=True)
except Exception:
    pass
# "Purples" é um colormap sequencial roxo que o Yellowbrick reconhece (combina com o tema).
CMAP_NOME = "Purples"
COR_TREINO = "#7C3AED"   # roxo primário
COR_TESTE = "#C026D3"    # magenta (lane y)
COR_LINHA = "#A78BCA"    # roxo suave p/ linhas guia
_RC_TEMA = {
    "axes.titlecolor": "#4C1D95",
    "axes.labelcolor": "#5B4B78",
    "text.color": "#4C1D95",
    "xtick.color": "#8B7AA8",
    "ytick.color": "#8B7AA8",
    "axes.edgecolor": "#E0D3F2",
    "grid.color": "#ECE7F5",
}


def _aplicar_tema() -> None:
    """Aplica a paleta + cores do tema (texto/eixos/grade) + fonte. Reaplicado por
    figura porque o Yellowbrick redefine o estilo durante o render."""
    try:
        matplotlib.rcParams["axes.prop_cycle"] = matplotlib.cycler(color=PALETA_TEMA)
    except Exception:
        pass
    matplotlib.rcParams.update(_RC_TEMA)
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = _FONTE_SANS


_aplicar_tema()

router = APIRouter()

AVERAGES_PERMITIDAS = {"micro", "macro", "weighted"}
VISUALIZACOES_KEY = "_visualizacoes"

_metrica_fn_cache: dict[str, callable] = {}


async def _get_metrica_fn_dynamic(valor: str) -> Optional[callable]:
    if valor in _metrica_fn_cache:
        return _metrica_fn_cache[valor]
    fn = metricas_disponiveis.get(valor)
    if fn:
        _metrica_fn_cache[valor] = fn
        return fn
    try:
        doc = await opcoes_metricas.find_one({"valor": valor})
    except Exception:
        return None
    if not doc:
        return None
    execucao = doc.get("execucao", {})
    modulo = execucao.get("modulo")
    funcao = execucao.get("funcao")
    if not modulo or not funcao:
        return None
    from app.pre_processamento import modulo_permitido
    if not modulo_permitido(modulo):
        logger.warning("Metrica %s com modulo fora da allowlist: %s", valor, modulo)
        return None
    try:
        mod = importlib.import_module(modulo)
        fn = getattr(mod, funcao)
        _metrica_fn_cache[valor] = fn
        return fn
    except Exception as e:
        logger.warning("Falha ao importar metrica dinamica %s.%s: %s", modulo, funcao, e)
        return None


_metrica_grupo_cache: dict[str, Optional[str]] = {}


async def _grupo_da_metrica(valor: str) -> Optional[str]:
    """Grupo da métrica (classificacao/regressao/agrupamento) do catálogo, cacheado.
    Permite gatear métricas NOVAS por grupo em vez de listas hardcoded."""
    if valor in _metrica_grupo_cache:
        return _metrica_grupo_cache[valor]
    try:
        doc = await opcoes_metricas.find_one({"valor": valor})
    except Exception:
        return None
    grupo = (doc or {}).get("grupo")
    _metrica_grupo_cache[valor] = grupo
    return grupo


def normalizar_media_metrica(average: Optional[str]) -> str:
    return average if average in AVERAGES_PERMITIDAS else "weighted"


def calcular_metrica(metrica_valor: str, metrica_fn, y_test, y_pred, average: Optional[str] = None) -> float:
    if metrica_valor in {"precision_score", "recall_score", "f1_score"}:
        return float(metrica_fn(y_test, y_pred, average=normalizar_media_metrica(average), zero_division=0))
    return float(metrica_fn(y_test, y_pred))


def _figura_para_base64(fig) -> str:
    # Reafirma a fonte logo antes de salvar: o Yellowbrick reseta font.sans-serif
    # durante o render, então garantimos a DejaVu Sans (disponível) na hora do savefig.
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = _FONTE_SANS
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", dpi=120)
    plt.close(fig)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def _ler_df_de_base64(b64: Optional[str]):
    """Lê um DataFrame de um conteúdo base64 (Excel ou CSV). Retorna None em falha."""
    if not b64:
        return None
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return None
    try:
        return pd.read_excel(io.BytesIO(raw), engine="openpyxl")
    except Exception:
        try:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
            sep = ";" if ";" in text.split("\n")[0] else ","
            return pd.read_csv(io.StringIO(text), sep=sep)
        except Exception:
            return None


def _logar_avaliacao_mlflow(
    run_id: Optional[str],
    label_modelo: str,
    metricas_pedidas: list,
    resultados_formatados: dict,
) -> None:
    """Loga métricas escalares + visualizações PNG no run MLflow do modelo.

    No-op silencioso quando MLflow está desativado ou o run não existe.
    Falhas individuais são engolidas — avaliação no Mongo é a fonte de verdade.
    """
    from app.mlflow_client import log_bytes_artifact, log_metrics

    if not run_id:
        return

    # Coleta métricas escalares (ignora dicts da confusion matrix e mensagens de erro).
    escalares: dict[str, float] = {}
    for metrica in metricas_pedidas:
        valor = resultados_formatados.get(metrica.label, {}).get(label_modelo)
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            chave = str(metrica.valor or metrica.label).replace(" ", "_")
            escalares[chave] = float(valor)
    if escalares:
        log_metrics(escalares, run_id=run_id)

    # Loga cada visualização PNG como artifact.
    visualizacoes = resultados_formatados.get(VISUALIZACOES_KEY, {}).get(label_modelo, []) or []
    for viz in visualizacoes:
        b64 = (viz or {}).get("base64")
        titulo = (viz or {}).get("titulo") or "viz"
        if not b64:
            continue
        try:
            payload = base64.b64decode(b64)
            nome_arquivo = "".join(c if c.isalnum() else "_" for c in titulo).strip("_") + ".png"
            log_bytes_artifact(
                payload,
                run_id=run_id,
                filename=nome_arquivo or "viz.png",
                artifact_path="visualizacoes",
            )
        except Exception as e:
            logger.warning("Falha ao logar artefato de viz '%s': %s", titulo, e)


def _viz_score(viz, X, y):
    """Pontua o visualizador (desenha os dados) e o devolve para o finalize()."""
    viz.score(X, y)
    return viz


def _viz_fit(viz, X, y=None):
    """Ajusta o visualizador (desenha os dados) e o devolve para o finalize()."""
    viz.fit(X) if y is None else viz.fit(X, y)
    return viz


def _renderizar_visualizacao(nome: str, factory) -> Optional[dict]:
    try:
        _aplicar_tema()  # paleta/cores do tema antes de desenhar (cores são fixadas no draw)
        fig, ax = plt.subplots(figsize=(7, 4.5))
        viz = factory(ax)
        # Yellowbrick só desenha título, rótulos de eixos e legenda em finalize();
        # sem isso o gráfico sai "pelado". score()/fit() apenas plotam os dados.
        if viz is not None and hasattr(viz, "finalize"):
            try:
                viz.finalize()
            except Exception as e:
                logger.debug("finalize() falhou para '%s': %s", nome, e)
        return {
            "titulo": nome,
            "mime": "image/png",
            "base64": _figura_para_base64(fig),
        }
    except Exception as e:
        logger.warning("Falha ao gerar visualização Yellowbrick '%s': %s", nome, e)
        plt.close("all")
        return None


def gerar_visualizacoes_classificacao(modelo_treinado, X_test, y_test, classes) -> list[dict]:
    classes_str = [str(c) for c in classes]
    if not getattr(modelo_treinado, "_estimator_type", None):
        modelo_treinado._estimator_type = "classifier"
    visualizacoes = []

    visualizadores = [
        ("Matriz de confusão", lambda ax: _viz_score(ConfusionMatrix(modelo_treinado, classes=classes_str, ax=ax, cmap=CMAP_NOME), X_test, y_test)),
        ("Relatório de classificação", lambda ax: _viz_score(ClassificationReport(modelo_treinado, classes=classes_str, support=True, ax=ax, cmap=CMAP_NOME), X_test, y_test)),
        ("Erros de predição por classe", lambda ax: _viz_score(ClassPredictionError(modelo_treinado, classes=classes_str, ax=ax), X_test, y_test)),
        ("Balanceamento das classes", lambda ax: _viz_fit(ClassBalance(labels=classes_str, ax=ax), y_test)),
    ]

    for titulo, factory in visualizadores:
        visualizacao = _renderizar_visualizacao(titulo, factory)
        if visualizacao:
            visualizacoes.append(visualizacao)

    return visualizacoes


CLUSTERING_METRICS = {"silhouette_score", "calinski_harabasz_score", "davies_bouldin_score"}


def gerar_visualizacoes_clustering(modelo_treinado, X_test) -> list[dict]:
    visualizacoes = []

    n_clusters = getattr(modelo_treinado, 'n_clusters', None)
    n_unique = len(set(getattr(modelo_treinado, 'labels_', [])))
    max_k = min(10, len(X_test) // 5) if len(X_test) > 50 else max(n_unique, 3)
    max_k = max(max_k, 2)

    visualizadores = [
        ("Silhouette", lambda ax: _viz_fit(SilhouetteVisualizer(modelo_treinado, ax=ax), X_test)),
        ("Distância entre Clusters", lambda ax: _viz_fit(InterclusterDistance(modelo_treinado, ax=ax), X_test)),
        ("Método do Cotovelo", lambda ax: _viz_fit(KElbowVisualizer(modelo_treinado, k=(2, max_k), ax=ax, timings=False), X_test)),
    ]

    for titulo, factory in visualizadores:
        visualizacao = _renderizar_visualizacao(titulo, factory)
        if visualizacao:
            visualizacoes.append(visualizacao)

    return visualizacoes


REGRESSION_METRICS = {"r2_score", "mean_squared_error", "root_mean_squared_error", "mean_absolute_error"}


def gerar_visualizacoes_regressao(modelo_treinado, X_test, y_test, X_train=None, y_train=None) -> list[dict]:
    if not getattr(modelo_treinado, "_estimator_type", None):
        modelo_treinado._estimator_type = "regressor"
    visualizacoes = []
    tem_treino = X_train is not None and y_train is not None

    def _prediction_error(ax):
        # bestfit + identity desenham a linha de melhor ajuste e a diagonal y=ŷ;
        # is_fitted='auto' não re-treina o pipeline já ajustado.
        viz = PredictionError(modelo_treinado, ax=ax, bestfit=True, identity=True, is_fitted="auto")
        viz.fit(X_train, y_train) if tem_treino else viz.fit(X_test, y_test)
        viz.score(X_test, y_test)
        return viz

    def _residuals(ax):
        # fit(treino) desenha os resíduos de TREINO; score(teste) os de TESTE.
        viz = ResidualsPlot(
            modelo_treinado, ax=ax, is_fitted="auto",
            train_color=COR_TREINO, test_color=COR_TESTE, line_color=COR_LINHA,
        )
        viz.fit(X_train, y_train) if tem_treino else viz.fit(X_test, y_test)
        viz.score(X_test, y_test)
        return viz

    visualizadores = [
        ("Prediction Error", _prediction_error),
        ("Residuals Plot", _residuals),
    ]
    # Distância de Cook precisa dos dados (X, y) numéricos para ajustar seu próprio
    # OLS — usa o conjunto de treino quando disponível.
    def _cooks(ax):
        # Compat matplotlib >=3.8: ax.stem() não aceita mais 'use_line_collection',
        # que o CooksDistance ainda passa. Neutraliza só neste ax.
        _stem_orig = ax.stem
        def _stem(*args, **kwargs):
            kwargs.pop("use_line_collection", None)
            return _stem_orig(*args, **kwargs)
        ax.stem = _stem
        # "C0" = primeira cor do prop_cycle (roxo do tema, via set_palette).
        return _viz_fit(CooksDistance(ax=ax, linefmt="C0-", markerfmt="C0o"), X_train, y_train)

    if tem_treino:
        visualizadores.append(("Distância de Cook", _cooks))

    for titulo, factory in visualizadores:
        visualizacao = _renderizar_visualizacao(titulo, factory)
        if visualizacao:
            visualizacoes.append(visualizacao)

    return visualizacoes


def calcular_metricas_clustering(X_test, labels) -> dict:
    resultados = {}
    try:
        resultados["Silhouette Score"] = float(silhouette_score(X_test, labels))
    except Exception as e:
        logger.warning("Erro ao calcular silhouette_score: %s", e)
        resultados["Silhouette Score"] = f"Erro: {e}"
    try:
        resultados["Calinski-Harabasz"] = float(calinski_harabasz_score(X_test, labels))
    except Exception as e:
        logger.warning("Erro ao calcular calinski_harabasz_score: %s", e)
        resultados["Calinski-Harabasz"] = f"Erro: {e}"
    try:
        resultados["Davies-Bouldin"] = float(davies_bouldin_score(X_test, labels))
    except Exception as e:
        logger.warning("Erro ao calcular davies_bouldin_score: %s", e)
        resultados["Davies-Bouldin"] = f"Erro: {e}"
    return resultados


@router.post("/avaliar_modelos")
async def avaliar_modelos(request: AvaliacaoModelosRequest):
    logger.info(f"avaliar_modelos called with {len(request.modelos)} modelos and {len(request.metricas)} metricas")

    if not request.modelos:
        logger.warning("avaliar_modelos called with empty modelos list")
    
    # estrutura: {nome_metrica: {label_modelo: valor}}
    resultados_formatados = {
        metrica.label: {} for metrica in request.metricas
    }
    resultados_formatados[VISUALIZACOES_KEY] = {}

    for modelo in request.modelos:
        id_modelo = modelo.id
        nome_modelo = modelo.label
        logger.debug(f"Processando modelo {nome_modelo} (id {id_modelo})")

        modelo_oid = validar_object_id(id_modelo, "id_modelo")
        doc = await modelos_treinados.find_one({"_id": modelo_oid})

        if not doc:
            logger.warning(f"Modelo não encontrado: {id_modelo}")
            for metrica in request.metricas:
                resultados_formatados[metrica.label][nome_modelo] = "Modelo não encontrado"
            continue

        modelo_treinado_bytes = bytes(doc["modelo_treinado"])
        logger.debug(f"Modelo bytes length: {len(modelo_treinado_bytes)}")

        # Recupera o checksum esperado
        checksum_esperado = doc.get("checksum")
        if checksum_esperado:
            checksum_atual = hashlib.sha256(modelo_treinado_bytes).hexdigest()
            if checksum_atual != checksum_esperado:
                logger.error(f"Checksum mismatch for model {id_modelo}")
                raise HTTPException(status_code=400, detail="Erro de integridade: checksum do modelo não corresponde.")

        # Desserializa o modelo com joblib
        modelo_treinado = joblib.load(io.BytesIO(modelo_treinado_bytes))
        logger.debug("Modelo deserializado com sucesso")

        atributos = doc["atributos"]
        target = doc["target"]
        logger.debug(f"Atributos: {atributos}, Target: {target}")

        # Busca o arquivo de teste pelo ID (separado do documento do modelo)
        arquivo_id = doc.get("arquivo_id")
        base64_str = None
        arquivo_doc = None

        if arquivo_id:
            if ObjectId.is_valid(str(arquivo_id)):
                arquivo_doc = await arquivos.find_one({"_id": ObjectId(str(arquivo_id))})
                if arquivo_doc:
                    base64_str = arquivo_doc.get("content_teste_base64")
            else:
                logger.warning(f"arquivo_id inválido no modelo {id_modelo}: {arquivo_id}")
        
        # Fallback: usa o arq_teste do próprio modelo se não encontrou no arquivo
        if not base64_str:
            base64_str = doc.get("arq_teste")

        if not base64_str:
            raise HTTPException(status_code=400, detail="Conteúdo do arquivo de teste ausente.")

        if len(base64_str) > MAX_ARQUIVO_BASE64:
            raise HTTPException(status_code=413, detail="Arquivo de teste muito grande. O limite é de 50 MB.")

        arquivo_bytes = base64.b64decode(base64_str)

        try:
            df_teste = pd.read_excel(io.BytesIO(arquivo_bytes), engine="openpyxl")
        except Exception as e:
            logger.debug(f"Falha ao ler arquivo de teste como Excel: {e}")
            try:
                # Tenta CSV se falhar Excel
                text = arquivo_bytes.decode("utf-8")
                sep = ";" in text.split("\n")[0] and ";" or ","
                df_teste = pd.read_csv(io.StringIO(text), sep=sep)
            except Exception as e2:
                logger.warning(f"Falha ao ler arquivo de teste como CSV: {e2}")
                raise HTTPException(status_code=400, detail=f"Erro ao processar arquivo de teste: {e} | {e2}")

        # Valida colunas
        colunas_necessarias = atributos.copy()
        if target:
            colunas_necessarias.append(target)
        for col in colunas_necessarias:
            if col not in df_teste.columns:
                raise HTTPException(status_code=400, detail=f"Coluna '{col}' não encontrada no arquivo de teste.")

        X_test = df_teste[atributos]
        is_clustering = not target or target == ""

        if is_clustering:
            # Avaliação de clustering
            labels = modelo_treinado.predict(X_test)

            resultados_formatados[VISUALIZACOES_KEY][nome_modelo] = gerar_visualizacoes_clustering(
                modelo_treinado, X_test
            )

            clustering_vals = calcular_metricas_clustering(X_test, labels)
            for metrica in request.metricas:
                try:
                    eh_agrup = metrica.valor in CLUSTERING_METRICS or (await _grupo_da_metrica(metrica.valor)) == "agrupamento"
                    if eh_agrup:
                        resultados_formatados[metrica.label][nome_modelo] = clustering_vals.get(
                            metrica.label, "Métrica não calculada"
                        )
                    else:
                        resultados_formatados[metrica.label][nome_modelo] = "N/A para agrupamento"
                except Exception as e:
                    logger.warning(f"Erro ao calcular métrica {metrica.label}: {e}")
                    resultados_formatados[metrica.label][nome_modelo] = f"Erro: {str(e)}"
        elif is_regressor(modelo_treinado):
            # Avaliação de regressão
            y_test = df_teste[target]
            y_pred = modelo_treinado.predict(X_test)

            # Carrega o conjunto de treino (quando disponível) para desenhar os resíduos
            # de treino no ResidualsPlot e calcular a Distância de Cook.
            X_train = y_train = None
            df_treino = _ler_df_de_base64(arquivo_doc.get("content_treino_base64") if arquivo_doc else None)
            if (df_treino is not None and target in df_treino.columns
                    and all(c in df_treino.columns for c in atributos)):
                X_train = df_treino[atributos]
                y_train = df_treino[target]

            resultados_formatados[VISUALIZACOES_KEY][nome_modelo] = gerar_visualizacoes_regressao(
                modelo_treinado, X_test, y_test, X_train, y_train
            )

            for metrica in request.metricas:
                try:
                    eh_regr = metrica.valor in REGRESSION_METRICS or (await _grupo_da_metrica(metrica.valor)) == "regressao"
                    if not eh_regr:
                        resultados_formatados[metrica.label][nome_modelo] = "N/A para regressão"
                        continue

                    if metrica.valor == "root_mean_squared_error":
                        valor_metrica = float(mean_squared_error(y_test, y_pred) ** 0.5)
                    else:
                        metrica_fn = await _get_metrica_fn_dynamic(metrica.valor)
                        if not metrica_fn:
                            resultados_formatados[metrica.label][nome_modelo] = "Métrica não suportada"
                            continue
                        valor_metrica = float(metrica_fn(y_test, y_pred))

                    resultados_formatados[metrica.label][nome_modelo] = valor_metrica
                except Exception as e:
                    logger.warning(f"Erro ao calcular métrica {metrica.label}: {e}")
                    resultados_formatados[metrica.label][nome_modelo] = f"Erro: {str(e)}"
        else:
            # Avaliação de classificação
            y_test = df_teste[target]
            y_pred = modelo_treinado.predict(X_test)

            classes_doc = doc.get("classes")
            if not classes_doc:
                try:
                    classes_doc = [str(c) for c in modelo_treinado.classes_]
                except AttributeError:
                    classes_doc = [str(c) for c in sorted(list(set(y_test) | set(y_pred)))]

            if hasattr(modelo_treinado, "classes_"):
                resultados_formatados[VISUALIZACOES_KEY][nome_modelo] = gerar_visualizacoes_classificacao(
                    modelo_treinado, X_test, y_test, classes_doc
                )

            for metrica in request.metricas:
                try:
                    # Gate por grupo (simétrico a regressão/clustering): uma métrica de
                    # outro grupo forçada contra um classificador retorna N/A.
                    grupo_m = await _grupo_da_metrica(metrica.valor)
                    if grupo_m in ("regressao", "agrupamento"):
                        resultados_formatados[metrica.label][nome_modelo] = "N/A para classificação"
                        continue

                    if metrica.valor == "confusion_matrix":
                        labels_cm = classes_doc if classes_doc else sorted(list(set(y_test) | set(y_pred)))
                        cm = confusion_matrix(y_test, y_pred, labels=labels_cm)
                        resultados_formatados[metrica.label][nome_modelo] = {
                            "matriz": cm.tolist(),
                            "classes": labels_cm,
                            "total": int(len(y_test))
                        }
                        continue

                    metrica_fn = await _get_metrica_fn_dynamic(metrica.valor)
                    if not metrica_fn:
                        resultados_formatados[metrica.label][nome_modelo] = "Métrica não suportada"
                        continue

                    valor_metrica = calcular_metrica(metrica.valor, metrica_fn, y_test, y_pred, metrica.average)
                    resultados_formatados[metrica.label][nome_modelo] = valor_metrica
                except Exception as e:
                    logger.warning(f"Erro ao calcular métrica {metrica.label}: {e}")
                    resultados_formatados[metrica.label][nome_modelo] = f"Erro: {str(e)}"

        # MLflow: anexa métricas + visualizações ao run que treinou esse modelo.
        _logar_avaliacao_mlflow(
            run_id=doc.get("mlflow_run_id"),
            label_modelo=nome_modelo,
            metricas_pedidas=request.metricas,
            resultados_formatados=resultados_formatados,
        )

    return resultados_formatados
