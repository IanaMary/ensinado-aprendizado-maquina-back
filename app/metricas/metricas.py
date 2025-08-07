from fastapi import APIRouter
from app.deps import pd, mlflow, metricas_disponiveis
from app.database import modelos_treinados
from app.models.schemas import AvaliacaoModelosRequest
from bson import ObjectId
import pickle
import base64
import io

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

            modelo_treinado = pickle.loads(doc["modelo_treinado"])

            atributos = doc["atributos"]
            target = doc["target"]
            base64_str = doc["arq_teste"]
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