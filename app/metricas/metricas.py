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
from sklearn.metrics import confusion_matrix

router = APIRouter()


@router.post("/avaliar_modelos")
async def avaliar_modelos(request: AvaliacaoModelosRequest):
    # estrutura: {nome_metrica: {label_modelo: valor}}
    resultados_formatados = {
        metrica.label: {} for metrica in request.metricas
    }

    for modelo in request.modelos:
        id_modelo = modelo.id
        nome_modelo = modelo.label

        try:
            doc = await modelos_treinados.find_one({"_id": ObjectId(id_modelo)})
        except Exception:
            raise HTTPException(status_code=400, detail=f"ID de modelo inválido: {id_modelo}")

            if not doc:
                for metrica in request.metricas:
                    resultados_formatados[metrica.label][nome_modelo] = "Modelo não encontrado"
                continue

            modelo_treinado_bytes = bytes(doc["modelo_treinado"])

            # Recupera o checksum esperado
            checksum_esperado = doc.get("checksum")
            if checksum_esperado:
                checksum_atual = hashlib.sha256(modelo_treinado_bytes).hexdigest()
                if checksum_atual != checksum_esperado:
                    raise HTTPException(status_code=400, detail="Erro de integridade: checksum do modelo não corresponde.")

            # Desserializa o modelo com joblib
            modelo_treinado = joblib.load(io.BytesIO(modelo_treinado_bytes))

            atributos = doc["atributos"]
            target = doc["target"]
            
            # Busca o arquivo de teste pelo ID (separado do documento do modelo)
            arquivo_id = doc.get("arquivo_id")
            base64_str = None
            
            if arquivo_id:
                arquivo_doc = await arquivos.find_one({"_id": ObjectId(arquivo_id)})
                if arquivo_doc:
                    base64_str = arquivo_doc.get("content_teste_base64")
            
            # Fallback: usa o arq_teste do próprio modelo se não encontrou no arquivo
            if not base64_str:
                base64_str = doc.get("arq_teste")
            
            if not base64_str:
                raise HTTPException(status_code=400, detail="Conteúdo do arquivo de teste ausente.")
            
            logger.debug(f"DEBUG: base64_str length: {len(base64_str) if base64_str else 0}")
            
            arquivo_bytes = base64.b64decode(base64_str)
            logger.debug(f"DEBUG: arquivo_bytes length: {len(arquivo_bytes)}")
            
            try:
                df_teste = pd.read_excel(io.BytesIO(arquivo_bytes), engine="openpyxl")
                logger.debug(f"DEBUG: df_teste shape: {df_teste.shape}, columns: {list(df_teste.columns)}")
            except Exception as e:
                logger.debug(f"DEBUG: Excel read error: {e}")
                try:
                    text = arquivo_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    text = arquivo_bytes.decode("latin-1")
                sep = ";" if ";" in text.split("\n")[0] else ","
                df_teste = pd.read_csv(pd.io.common.StringIO(text), sep=sep)
                logger.debug(f"DEBUG: CSV df_teste shape: {df_teste.shape}, columns: {list(df_teste.columns)}")

            X_teste = df_teste[atributos]
            y_teste = df_teste[target]
            y_pred = modelo_treinado.predict(X_teste)

            for metrica in request.metricas:
                nome_metrica = metrica.label
                func_key = metrica.valor

                try:
                    if func_key == "confusion_matrix":
                        cm = confusion_matrix(y_teste, y_pred)
                        classes = sorted(set(y_teste) | set(y_pred))
                        valor = {
                            "matriz": cm.tolist(),
                            "classes": classes,
                            "total": int(cm.sum())
                        }

                    elif func_key == "roc_auc_score":
                        func = metricas_disponiveis.get(func_key)
                        if not func:
                            resultados_formatados[nome_metrica][nome_modelo] = "Métrica não suportada"
                            continue
                        if len(set(y_teste)) != 2:
                            resultados_formatados[nome_metrica][nome_modelo] = "ROC AUC requer problema binário"
                            continue
                        y_prob = modelo_treinado.predict_proba(X_teste)[:, 1]
                        valor = func(y_teste, y_prob)

                    else:
                        func = metricas_disponiveis.get(func_key)
                        if not func:
                            resultados_formatados[nome_metrica][nome_modelo] = "Métrica não suportada"
                            continue

                        if func_key in {"precision_score", "recall_score", "f1_score"}:
                            valor = func(y_teste, y_pred, average="weighted", zero_division=0)
                        elif func_key == "accuracy_score":
                            valor = func(y_teste, y_pred)
                        else:
                            try:
                                valor = func(y_teste, y_pred, average="weighted")
                            except TypeError:
                                valor = func(y_teste, y_pred)

                    resultados_formatados[nome_metrica][nome_modelo] = valor

                except Exception as e:
                    resultados_formatados[nome_metrica][nome_modelo] = f"Erro ao calcular: {str(e)}"

        except Exception as erro_geral:
            for metrica in request.metricas:
                resultados_formatados[metrica.label][nome_modelo] = f"Erro geral: {str(erro_geral)}"

    return resultados_formatados