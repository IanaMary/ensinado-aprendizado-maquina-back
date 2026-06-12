import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException
from app.deps import pd, metricas_disponiveis
from app.database import modelos_treinados, arquivos
from app.schemas.schemas import AvaliacaoModelosRequest
from bson import ObjectId
import joblib
import base64
import io
import hashlib
import sys
import types
from typing import Optional
from sklearn.metrics import confusion_matrix

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


@router.post("/avaliar_modelos")
async def avaliar_modelos(request: AvaliacaoModelosRequest):
    print(f"[PRINT] avaliar_modelos called with {len(request.modelos)} modelos and {len(request.metricas)} metricas")
    logger.info(f"avaliar_modelos called with {len(request.modelos)} modelos and {len(request.metricas)} metricas")

    if not request.modelos:
        print("[WARN] avaliar_modelos called with empty modelos list")
        logger.warning("avaliar_modelos called with empty modelos list")
    
    # estrutura: {nome_metrica: {label_modelo: valor}}
    resultados_formatados = {
        metrica.label: {} for metrica in request.metricas
    }
    resultados_formatados[VISUALIZACOES_KEY] = {}

    for modelo in request.modelos:
        print(f"[PRINT] Processing modelo: {modelo}")
        id_modelo = modelo.id
        nome_modelo = modelo.label
        print(f"[PRINT] id_modelo: {id_modelo}, nome_modelo: {nome_modelo}")

        try:
            doc = await modelos_treinados.find_one({"_id": ObjectId(id_modelo)})
        except Exception as e:
            print(f"[PRINT] Exception finding model: {e}")
            raise HTTPException(status_code=400, detail=f"ID de modelo inválido: {id_modelo}")

        if not doc:
            print(f"[PRINT] Modelo não encontrado: {id_modelo}")
            logger.warning(f"Modelo não encontrado: {id_modelo}")
            for metrica in request.metricas:
                resultados_formatados[metrica.label][nome_modelo] = "Modelo não encontrado"
            continue

        modelo_treinado_bytes = bytes(doc["modelo_treinado"])
        print(f"[PRINT] Modelo bytes length: {len(modelo_treinado_bytes)}")
        logger.debug(f"Modelo bytes length: {len(modelo_treinado_bytes)}")

        # Recupera o checksum esperado
        checksum_esperado = doc.get("checksum")
        if checksum_esperado:
            checksum_atual = hashlib.sha256(modelo_treinado_bytes).hexdigest()
            if checksum_atual != checksum_esperado:
                print(f"[PRINT] Checksum mismatch for model {id_modelo}")
                logger.error(f"Checksum mismatch for model {id_modelo}")
                raise HTTPException(status_code=400, detail="Erro de integridade: checksum do modelo não corresponde.")

        # Desserializa o modelo com joblib
        modelo_treinado = joblib.load(io.BytesIO(modelo_treinado_bytes))
        print("[PRINT] Modelo deserializado com sucesso")
        logger.debug("Modelo deserializado com sucesso")

        atributos = doc["atributos"]
        target = doc["target"]
        print(f"[PRINT] Atributos: {atributos}, Target: {target}")
        logger.debug(f"Atributos: {atributos}, Target: {target}")
        
        # Busca o arquivo de teste pelo ID (separado do documento do modelo)
        arquivo_id = doc.get("arquivo_id")
        base64_str = None
        
        print(f"[PRINT] arquivo_id: {arquivo_id}")
        
        if arquivo_id:
            try:
                arquivo_doc = await arquivos.find_one({"_id": ObjectId(arquivo_id)})
                print(f"[PRINT] arquivo_doc found: {arquivo_doc is not None}")
                if arquivo_doc:
                    base64_str = arquivo_doc.get("content_teste_base64")
                    print(f"[PRINT] content_teste_base64 from arquivo: {base64_str is not None}")
            except Exception as e:
                print(f"[PRINT] Erro ao buscar arquivo_id {arquivo_id}: {e}")
        
        # Fallback: usa o arq_teste do próprio modelo se não encontrou no arquivo
        if not base64_str:
            base64_str = doc.get("arq_teste")
            print(f"[PRINT] Using arq_teste from model: {base64_str is not None}")
        
        if not base64_str:
            raise HTTPException(status_code=400, detail="Conteúdo do arquivo de teste ausente.")
        
        print(f"[PRINT] base64_str length: {len(base64_str) if base64_str else 0}")
        
        arquivo_bytes = base64.b64decode(base64_str)
        print(f"[PRINT] arquivo_bytes length: {len(arquivo_bytes)}")
        
        try:
            df_teste = pd.read_excel(io.BytesIO(arquivo_bytes), engine="openpyxl")
            print(f"[PRINT] df_teste shape: {df_teste.shape}, columns: {list(df_teste.columns)}")
        except Exception as e:
            print(f"[PRINT] Excel read error: {e}")
            try:
                # Tenta CSV se falhar Excel
                text = arquivo_bytes.decode("utf-8")
                sep = ";" in text.split("\n")[0] and ";" or ","
                df_teste = pd.read_csv(io.StringIO(text), sep=sep)
            except Exception as e2:
                print(f"[PRINT] CSV read error: {e2}")
                raise HTTPException(status_code=400, detail=f"Erro ao processar arquivo de teste: {e} | {e2}")

        # Valida colunas
        for col in atributos + [target]:
            if col not in df_teste.columns:
                print(f"[PRINT] Coluna ausente: {col}")
                raise HTTPException(status_code=400, detail=f"Coluna '{col}' não encontrada no arquivo de teste.")

        X_test = df_teste[atributos]
        y_test = df_teste[target]

        y_pred = modelo_treinado.predict(X_test)
        print(f"[PRINT] Predições realizadas: {len(y_pred)}")

        classes_doc = doc.get("classes")
        if not classes_doc:
            try:
                classes_doc = [str(c) for c in modelo_treinado.classes_]
            except:
                classes_doc = [str(c) for c in sorted(list(set(y_test) | set(y_pred)))]

        if hasattr(modelo_treinado, "classes_"):
            resultados_formatados[VISUALIZACOES_KEY][nome_modelo] = gerar_visualizacoes_classificacao(
                modelo_treinado,
                X_test,
                y_test,
                classes_doc,
            )

        for metrica in request.metricas:
            try:
                # Trata matriz de confusão separadamente
                if metrica.valor == "confusion_matrix":
                    cm = confusion_matrix(y_test, y_pred)
                    
                    resultados_formatados[metrica.label][nome_modelo] = {
                        "matriz": cm.tolist(),
                        "classes": classes_doc,
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
                print(f"[PRINT] Erro ao calcular métrica {metrica.label}: {e}")
                resultados_formatados[metrica.label][nome_modelo] = f"Erro: {str(e)}"

    return resultados_formatados
