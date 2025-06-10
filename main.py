from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import pandas as pd

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

# Rota para treinar o classificador KNN
@app.post("/classificador/treinamento/knn")
def treinar_knn(request: DatasetRequest):
    try:
        df_treino = pd.DataFrame(request.dados_treino)

        # Divide dados se dados_teste não for fornecido
        if request.dados_teste and len(request.dados_teste) > 0:
            df_teste = pd.DataFrame(request.dados_teste)
        else:
            df_treino, df_teste = train_test_split(df_treino, test_size=0.2, random_state=42)

        # Verifica se colunas existem
        for col in request.atributos + [request.target]:
            if col not in df_treino.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados de treino.")

        X_train = df_treino[request.atributos]
        y_train = df_treino[request.target]

        X_test = df_teste[request.atributos]
        y_test = df_teste[request.target]

        model = KNeighborsClassifier(**request.hiperparametros)
        model.fit(X_train, y_train)

        # Armazena modelo e atributos pelo nome 'knn'
        modelos_treinados['knn'] = model
        atributos_usados['knn'] = request.atributos

        # Cria um DataFrame juntando X_test e y_test
        df_teste_completo = X_test.copy()
        df_teste_completo[request.target] = y_test

        return {
            "status": "modelo knn treinado com sucesso",
            "total_amostras_treino": len(X_train),
            "total_amostras_teste": len(X_test),
            "atributos": request.atributos,
            "target": request.target,
            "teste": df_teste_completo.to_dict(orient='records'),  # lista de dicts com atributos + target
            "hiperparametros": model.get_params(),
            "classes": list(model.classes_),
            "modelo": "knn"
        }

    except Exception as e:
        return {"erro": str(e)}

# Rota para avaliar modelos
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

        for metrica in request.metricas:
            if metrica not in metricas_disponiveis:
                resultados[metrica] = "Métrica não suportada"
                continue

            func = globals().get(metrica)
            if func is None:
                resultados[metrica] = "Métrica não suportada"
                continue

            if metrica == "roc_auc_score":
                if len(set(y_test)) != 2:
                    resultados[metrica] = "ROC AUC requer problema binário"
                    continue
                y_prob = modelo.predict_proba(X_test)[:, 1]
                resultados[metrica] = func(y_test, y_prob)
            else:
                resultados[metrica] = func(y_test, y_pred, average='weighted')

        # Mapeando nomes bonitos
        nomes_metricas = {
            "f1_score": "F1-Score",
            "recall_score": "Recall",
            "precision_score": "Precisão",
            "accuracy_score": "Acurácia",
            "roc_auc_score": "ROC AUC"
        }

        resultados_legiveis = {nomes_metricas.get(k, k): v for k, v in resultados.items()}

        return {
            "status": "Avaliação concluída com sucesso",
            "resultados": resultados_legiveis
        }

    except Exception as e:
        return {"erro": str(e)}

# Rota para fazer previsões com KNN (pode ser extendido para outros modelos)
@app.post("/classificador/prever/knn")
def fazer_previsoes_knn(request: PrevisaoRequest):
    modelo_nome = request.modelo_nome
    modelo = modelos_treinados.get(modelo_nome)
    if modelo is None:
        return {"erro": f"Modelo '{modelo_nome}' não foi treinado ou não existe."}

    try:
        df_novo = pd.DataFrame(request.dados)

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
            "previsoes": preds.tolist()
        }

    except Exception as e:
        return {"erro": str(e)}
