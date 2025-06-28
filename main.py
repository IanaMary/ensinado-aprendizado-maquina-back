from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sklearn.neighbors import KNeighborsClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import pandas as pd
import mlflow
import mlflow.sklearn
from sklearn.svm import SVC

app = FastAPI()

# Middleware CORS para aceitar requisições de qualquer origem
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dicionários para manter modelos treinados e atributos usados
modelos_treinados: Dict[str, Any] = {}
atributos_usados: Dict[str, List[str]] = {}

# Métricas disponíveis
metricas_disponiveis = [
    'accuracy_score',
    'precision_score',
    'recall_score',
    'f1_score',
    'roc_auc_score'
]

class AvaliacaoCompactaRequest(BaseModel):
    dados_teste: List[Dict[str, Any]]
    target: str
    atributos: List[str]
    avaliacoes: List[Dict[str, Any]]

# Modelos Pydantic
class DatasetRequest(BaseModel):
    dados_treino: List[Dict[str, Any]]
    dados_teste: Optional[List[Dict[str, Any]]] = []
    atributos: List[str]
    target: str
    hiperparametros: Optional[Dict[str, Any]] = {}

class PrevisaoRequest(BaseModel):
    dados: List[Dict[str, Any]]
    modelo_nome: str

class AvaliacaoRequest(BaseModel):
    dados_teste: List[Dict[str, Any]]
    target: str
    atributos: List[str]
    metricas: Optional[List[str]] = []
    modelo_nome: Optional[Any]
    mlflow_run_id_modelo: str
class PrevisaoRequest(BaseModel):
    dados: List[Dict[str, Any]]
    modelo_nome: Optional[str] = None
    mlflow_run_id: Optional[str] = None  


@app.post("/classificador/treinamento/knn")
def treinar_knn(request: DatasetRequest):
    try:
        df_treino = pd.DataFrame(request.dados_treino)

        if request.dados_teste and len(request.dados_teste) > 0:
            df_teste = pd.DataFrame(request.dados_teste)
        else:
            df_treino, df_teste = train_test_split(df_treino, test_size=0.2, random_state=42)

        for col in request.atributos + [request.target]:
            if col not in df_treino.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados de treino.")

        X_train = df_treino[request.atributos]
        y_train = df_treino[request.target]

        X_test = df_teste[request.atributos]
        y_test = df_teste[request.target]

        model = KNeighborsClassifier(**request.hiperparametros)

        with mlflow.start_run(run_name="KNN Model"):
            model.fit(X_train, y_train)

            mlflow.log_params(request.hiperparametros)

            mlflow.sklearn.log_model(model, "knn_model")
            
            run_id = mlflow.active_run().info.run_id

        modelos_treinados['knn'] = model
        atributos_usados['knn'] = request.atributos

        df_teste_completo = X_test.copy()
        df_teste_completo[request.target] = y_test

        return {
            "status": "modelo knn treinado com sucesso",
            "total_amostras_treino": len(X_train),
            "total_amostras_teste": len(X_test),
            "atributos": request.atributos,
            "target": request.target,
            "teste": df_teste_completo.to_dict(orient='records'),
            "hiperparametros": model.get_params(),
            "classes": list(model.classes_),
            "modelo": "knn",
            "mlflow_run_id_modelo": run_id
        }

    except Exception as e:
        return {"erro": str(e)}


@app.post("/classificador/treinamento/svm")
def treinar_svm(request: DatasetRequest):
    try:
        df_treino = pd.DataFrame(request.dados_treino)

        if request.dados_teste and len(request.dados_teste) > 0:
            df_teste = pd.DataFrame(request.dados_teste)
        else:
            df_treino, df_teste = train_test_split(df_treino, test_size=0.2, random_state=42)

        for col in request.atributos + [request.target]:
            if col not in df_treino.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados de treino.")

        X_train = df_treino[request.atributos]
        y_train = df_treino[request.target]

        X_test = df_teste[request.atributos]
        y_test = df_teste[request.target]

        model = SVC(**request.hiperparametros)

        with mlflow.start_run(run_name="SVM Model"):
            model.fit(X_train, y_train)      
            
            mlflow.log_params(request.hiperparametros)
            mlflow.sklearn.log_model(model, "svm_model")

            run_id = mlflow.active_run().info.run_id

        modelos_treinados['svm'] = model
        atributos_usados['svm'] = request.atributos

        df_teste_completo = X_test.copy()
        df_teste_completo[request.target] = y_test

        return {
            "status": "modelo svm treinado com sucesso",
            "total_amostras_treino": len(X_train),
            "total_amostras_teste": len(X_test),
            "atributos": request.atributos,
            "target": request.target,
            "teste": df_teste_completo.to_dict(orient='records'),
            "hiperparametros": model.get_params(),
            "classes": list(model.classes_),
            "modelo": "svm",
            "mlflow_run_id_modelo": run_id
        }

    except Exception as e:
        return {"erro": str(e)}
    
    
@app.post("/classificador/avaliar")
def avaliar_modelo(request: AvaliacaoRequest):
    modelo = modelos_treinados.get(request.modelo_nome)
    if modelo is None:
        return {"erro": f"Modelo '{request.modelo_nome}' não foi treinado ou não existe."}

    try:
        df_teste = pd.DataFrame(request.dados_teste)

        for col in request.atributos + [request.target]:
            if col not in df_teste.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados de teste.")

        X_test = df_teste[request.atributos]
        y_test = df_teste[request.target]
        y_pred = modelo.predict(X_test)

        resultados = {}

        with mlflow.start_run(run_name=f"Avaliacao_{request.modelo_nome}"):
            for metrica in request.metricas:
                if metrica not in metricas_disponiveis:
                    resultados[metrica] = "Métrica não suportada"
                    continue

                func = globals().get(metrica)
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

            mlflow.set_tag("tipo", "avaliacao")
            mlflow.set_tag("modelo", request.modelo_nome)

            run_id = mlflow.active_run().info.run_id

        return {
            "status": "Avaliação concluída com sucesso",
            "resultados": resultados,
            "mlflow_run_id_avaliacao": run_id
        }

    except Exception as e:
        return {"erro": str(e)}

@app.post("/classificador/avaliar-multiplos")
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
            
            if modelo_nome.lower() == "knn":
                model_uri = f"runs:/{run_id}/knn_model"
            elif modelo_nome.lower() == "svm":
                model_uri = f"runs:/{run_id}/svm_model"
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

                    func = globals().get(metrica)
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
                mlflow.set_tag("modelo", modelo_nome)
                mlflow_run_avaliacao = mlflow.active_run().info.run_id

            resultados_gerais[modelo_nome] = {
                "status": "Avaliação concluída com sucesso",
                "resultados": resultados,
                "mlflow_run_id_avaliacao": mlflow_run_avaliacao
            }

        except Exception as e:
            resultados_gerais[modelo_nome] = {"erro": str(e)}

    return resultados_gerais

@app.post("/classificador/prever/knn")
def fazer_previsoes_knn(request: PrevisaoRequest):
    try:
        df_novo = pd.DataFrame(request.dados)
        
        if request.mlflow_run_id:
            model_uri = f"runs:/{request.mlflow_run_id}/knn_model"
            modelo = mlflow.sklearn.load_model(model_uri)
            atributos = list(df_novo.columns)
        else:
            modelo_nome = request.modelo_nome
            modelo = modelos_treinados.get(modelo_nome)
            if modelo is None:
                return {"erro": f"Modelo '{modelo_nome}' não foi treinado ou não existe."}

            atributos = atributos_usados.get(modelo_nome)
            if not atributos:
                return {"erro": f"Atributos para o modelo '{modelo_nome}' não encontrados."}

            for col in atributos:
                if col not in df_novo.columns:
                    raise ValueError(f"Atributo '{col}' ausente nos dados enviados.")

        X_novo = df_novo[atributos]
        preds = modelo.predict(X_novo)

        return {
            "status": "previsões realizadas",
            "fonte_modelo": "mlflow" if request.mlflow_run_id else "memória",
            "previsoes": preds.tolist()
        }

    except Exception as e:
        return {"erro": str(e)}