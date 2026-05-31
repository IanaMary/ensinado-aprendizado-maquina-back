from fastapi import APIRouter, HTTPException
from app.deps import pd, metricas_disponiveis
from app.database import modelos_treinados, arquivos
from app.schemas.schemas import AvaliacaoModelosRequest
from bson import ObjectId
import joblib
import base64
import io
import hashlib

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

            if not doc:
                for metrica in request.metricas:
                    resultados_formatados[metrica.label][nome_modelo] = "Modelo não encontrado"
                continue

            # Validação de checksum
            modelo_treinado_bytes = doc["modelo_treinado"]
            if isinstance(modelo_treinado_bytes, bytes):
                modelo_treinado_bytes = modelo_treinado_bytes
            else:
                modelo_treinado_bytes = bytes(modelo_treinado_bytes)

            # Recupera o checksum esperado
            checksum_esperado = doc.get("checksum")
            if checksum_esperado:
                checksum_atual = hashlib.sha256(modelo_treinado_bytes).hexdigest()
                if checksum_atual != checksum_esperado:
                    raise HTTPException(status_code=400, detail="Erro de integridade: checksum do modelo não corresponde.")

            # Desserializa o modelo com joblib
            modelo_treinado = joblib.loads(modelo_treinado_bytes)

            atributos = doc["atributos"]
            target = doc["target"]
            
            # Busca o arquivo de teste pelo ID (separado do documento do modelo)
            arquivo_id = doc.get("arquivo_id")
            if not arquivo_id:
                base64_str = doc.get("arq_teste")
            else:
                arquivo_doc = await arquivos.find_one({"_id": ObjectId(arquivo_id)})
                if not arquivo_doc:
                    raise HTTPException(status_code=404, detail="Arquivo de teste não encontrado.")
                base64_str = arquivo_doc.get("content_teste_base64")

            if not base64_str:
                raise HTTPException(status_code=400, detail="Conteúdo do arquivo de teste ausente.")

            arquivo_bytes = base64.b64decode(base64_str)
            df_teste = pd.read_excel(io.BytesIO(arquivo_bytes))

            X_teste = df_teste[atributos]
            y_teste = df_teste[target]
            y_pred = modelo_treinado.predict(X_teste)

            for metrica in request.metricas:
                nome_metrica = metrica.label
                func_key = metrica.valor
                func = metricas_disponiveis.get(func_key)

                if not func:
                    resultados_formatados[nome_metrica][nome_modelo] = "Métrica não suportada"
                    continue

                try:
                    if func_key == "roc_auc_score":
                        if len(set(y_teste)) != 2:
                            resultados_formatados[nome_metrica][nome_modelo] = "ROC AUC requer problema binário"
                            continue
                        y_prob = modelo_treinado.predict_proba(X_teste)[:, 1]
                        valor = func(y_teste, y_prob)

                    elif func_key in {"precision_score", "recall_score", "f1_score"}:
                        valor = func(y_teste, y_pred, average="weighted", zero_division=0)

                    elif func_key in {"accuracy_score", "confusion_matrix"}:
                        valor = func(y_teste, y_pred)

                    else:
                        # tentativa genérica: com average, e fallback sem average
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