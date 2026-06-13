import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException
from app.deps import pd, metricas_disponiveis
from app.database import modelos_treinados, arquivos
from app.schemas.schemas import AvaliacaoModelosRequest
from app.funcoes_genericas.validacao import validar_object_id, MAX_ARQUIVO_BASE64
from bson import ObjectId
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

router = APIRouter()

AVERAGES_PERMITIDAS = {"micro", "macro", "weighted"}
VISUALIZACOES_KEY = "_visualizacoes"


def normalizar_media_metrica(average: Optional[str]) -> str:
    return average if average in AVERAGES_PERMITIDAS else "weighted"


def calcular_metrica(metrica_valor: str, metrica_fn, y_test, y_pred, average: Optional[str] = None) -> float:
    if metrica_valor in {"precision_score", "recall_score", "f1_score"}:
        return float(metrica_fn(y_test, y_pred, average=normalizar_media_metrica(average), zero_division=0))
    return float(metrica_fn(y_test, y_pred))


def _figura_para_base64(fig) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", dpi=120)
    plt.close(fig)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def _renderizar_visualizacao(nome: str, factory) -> Optional[dict]:
    try:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        factory(ax)
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
        ("Matriz de confusão", lambda ax: ConfusionMatrix(modelo_treinado, classes=classes_str, ax=ax).score(X_test, y_test)),
        ("Relatório de classificação", lambda ax: ClassificationReport(modelo_treinado, classes=classes_str, support=True, ax=ax).score(X_test, y_test)),
        ("Erros de predição por classe", lambda ax: ClassPredictionError(modelo_treinado, classes=classes_str, ax=ax).score(X_test, y_test)),
        ("Balanceamento das classes", lambda ax: ClassBalance(labels=classes_str, ax=ax).fit(y_test)),
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
        ("Silhouette", lambda ax: SilhouetteVisualizer(modelo_treinado, ax=ax).fit(X_test)),
        ("Distância entre Clusters", lambda ax: InterclusterDistance(modelo_treinado, ax=ax).fit(X_test)),
        ("Método do Cotovelo", lambda ax: KElbowVisualizer(modelo_treinado, k=(2, max_k), ax=ax, timings=False).fit(X_test)),
    ]

    for titulo, factory in visualizadores:
        visualizacao = _renderizar_visualizacao(titulo, factory)
        if visualizacao:
            visualizacoes.append(visualizacao)

    return visualizacoes


REGRESSION_METRICS = {"r2_score", "mean_squared_error", "root_mean_squared_error", "mean_absolute_error"}


def gerar_visualizacoes_regressao(modelo_treinado, X_test, y_test) -> list[dict]:
    import numpy as np

    y_real = np.asarray(y_test, dtype=float).ravel()
    y_pred = np.asarray(modelo_treinado.predict(X_test), dtype=float).ravel()
    residuos = y_real - y_pred

    def _previsto_vs_real(ax):
        ax.scatter(y_real, y_pred, alpha=0.6, color="#6c4ed9", edgecolors="none")
        lim_min = float(min(y_real.min(), y_pred.min()))
        lim_max = float(max(y_real.max(), y_pred.max()))
        ax.plot([lim_min, lim_max], [lim_min, lim_max], "--", color="#999999", linewidth=1)
        ax.set_xlabel("Valor real")
        ax.set_ylabel("Valor previsto")
        ax.set_title("Quanto mais perto da linha tracejada, melhor a previsão")

    def _residuos(ax):
        ax.scatter(y_pred, residuos, alpha=0.6, color="#6c4ed9", edgecolors="none")
        ax.axhline(0, linestyle="--", color="#999999", linewidth=1)
        ax.set_xlabel("Valor previsto")
        ax.set_ylabel("Resíduo (real - previsto)")
        ax.set_title("Resíduos: o ideal é ficarem espalhados perto do zero")

    visualizacoes = []
    for titulo, factory in [("Previsto vs. Real", _previsto_vs_real), ("Resíduos", _residuos)]:
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
                    if metrica.valor in CLUSTERING_METRICS:
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

            resultados_formatados[VISUALIZACOES_KEY][nome_modelo] = gerar_visualizacoes_regressao(
                modelo_treinado, X_test, y_test
            )

            for metrica in request.metricas:
                try:
                    if metrica.valor not in REGRESSION_METRICS:
                        resultados_formatados[metrica.label][nome_modelo] = "N/A para regressão"
                        continue

                    if metrica.valor == "root_mean_squared_error":
                        valor_metrica = float(mean_squared_error(y_test, y_pred) ** 0.5)
                    else:
                        metrica_fn = metricas_disponiveis.get(metrica.valor)
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
                    if metrica.valor == "confusion_matrix":
                        labels_cm = classes_doc if classes_doc else sorted(list(set(y_test) | set(y_pred)))
                        cm = confusion_matrix(y_test, y_pred, labels=labels_cm)
                        resultados_formatados[metrica.label][nome_modelo] = {
                            "matriz": cm.tolist(),
                            "classes": labels_cm,
                            "total": int(len(y_test))
                        }
                        continue

                    metrica_fn = metricas_disponiveis.get(metrica.valor)
                    if not metrica_fn:
                        resultados_formatados[metrica.label][nome_modelo] = "Métrica não suportada"
                        continue

                    valor_metrica = calcular_metrica(metrica.valor, metrica_fn, y_test, y_pred, metrica.average)
                    resultados_formatados[metrica.label][nome_modelo] = valor_metrica
                except Exception as e:
                    logger.warning(f"Erro ao calcular métrica {metrica.label}: {e}")
                    resultados_formatados[metrica.label][nome_modelo] = f"Erro: {str(e)}"

    return resultados_formatados
