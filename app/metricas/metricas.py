from fastapi import APIRouter
from app.models.schemas import AvaliacaoCompactaRequest
from app.deps import pd, mlflow, metricas_disponiveis

router = APIRouter()


@router.post("/avaliar-multiplos")
def avaliar_multiplos_modelos_compacto(request: AvaliacaoCompactaRequest):
    resultados_gerais = {}
    df_teste = pd.DataFrame(request.dados_teste)

    for col in request.atributos + [request.target]:
        if col not in df_teste.columns:
            return {"erro": f"Coluna '{col}' não encontrada nos dados de teste."}

    X_test = df_teste[request.atributos]
    y_test = df_teste[request.target]

    for avaliacao in request.avaliacoes:
        modelo_nome = avaliacao.get("modelo_nome", "modelo_desconhecido")
        run_id = avaliacao.get("mlflow_run_id_modelo")

        if not run_id:
            resultados_gerais[modelo_nome] = {"erro": "mlflow_run_id_modelo ausente na requisição."}
            continue

        try:
            
            if modelo_nome:
                model_uri = f"runs:/{run_id}/{modelo_nome}"
            else:
                resultados_gerais[modelo_nome] = {"erro": f"Modelo '{modelo_nome}' não suportado."}
                continue

            modelo = mlflow.sklearn.load_model(model_uri)

            y_pred = modelo.predict(X_test)
            resultados = {}

            with mlflow.start_run(run_name=f"Avaliacao_{modelo_nome}"):
                for metrica in avaliacao.get("metricas", []):
                    if metrica not in metricas_disponiveis:
                        resultados[metrica] = "Métrica não suportada"
                        continue

                    func = metricas_disponiveis.get(metrica)
                    if func is None:
                        resultados[metrica] = "Métrica não suportada"
                        continue

                    try:
                        if metrica == "roc_auc_score":
                            if len(set(y_test)) != 2:
                                resultados[metrica] = "ROC AUC requer problema binário"
                                continue
                            y_prob = modelo.predict_proba(X_test)[:, 1]
                            valor = func(y_test, y_prob)
                        else:
                            valor = func(y_test, y_pred, average='weighted')

                        resultados[metrica] = valor
                        mlflow.log_metric(metrica, valor)

                    except Exception as erro_metricas:
                        resultados[metrica] = f"Erro ao calcular: {erro_metricas}"

                mlflow.set_tag("tipo", "avaliacao_multipla")
                mlflow.set_tag("modelo", run_id)
                mlflow_run_avaliacao = mlflow.active_run().info.run_id

            resultados_gerais[modelo_nome] = {
                "status": "Avaliação concluída com sucesso",
                "resultados": resultados,
                "mlflow_run_id_avaliacao": mlflow_run_avaliacao
            }

        except Exception as e:
            resultados_gerais[modelo_nome] = {"erro": str(e)}

    return resultados_gerais