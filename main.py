from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
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

# Variáveis globais para manter o modelo treinado e os atributos usados
modelo_treinado = None
atributos_usados = []

# Modelos Pydantic
class DatasetRequest(BaseModel):
    dados_treino: List[Dict[str, Any]]
    dados_teste: Optional[List[Dict[str, Any]]] = []
    atributos: List[str]
    target: str

class PrevisaoRequest(BaseModel):
    dados: List[Dict[str, Any]]

# Rota para treinar o classificador
@app.post("/classificador/treinamento/knn")
def processar_dataset(request: DatasetRequest):
    global modelo_treinado, atributos_usados

    try:
        df_treino = pd.DataFrame(request.dados_treino)

        # Divide automaticamente se dados_teste estiver vazio ou não fornecido
        if request.dados_teste and len(request.dados_teste) > 0:
            df_teste = pd.DataFrame(request.dados_teste)
        else:
            df_treino, df_teste = train_test_split(df_treino, test_size=0.2, random_state=42)

        # Verifica se as colunas fornecidas realmente existem
        for col in request.atributos + [request.target]:
            if col not in df_treino.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados de treino.")

        X_train = df_treino[request.atributos]
        y_train = df_treino[request.target]

        X_test = df_teste[request.atributos]
        y_test = df_teste[request.target]

        model = KNeighborsClassifier()
        model.fit(X_train, y_train)

        acc_train = accuracy_score(y_train, model.predict(X_train))
        acc_test = accuracy_score(y_test, model.predict(X_test))

        modelo_treinado = model
        atributos_usados = request.atributos

        return {
            "status": "modelo treinado com sucesso",
            "total_amostras_treino": len(X_train),
            "total_amostras_teste": len(X_test),
            "atributos": request.atributos,
            "target": request.target,
            "classes": list(model.classes_),
            "acuracia_treino": acc_train,
            "acuracia_teste": acc_test,
        }

    except Exception as e:
        return {"erro": str(e)}

# Rota para fazer previsões
@app.post("/classificador/prever/knn")
def fazer_previsoes(request: PrevisaoRequest):
    global modelo_treinado, atributos_usados

    if modelo_treinado is None:
        return {"erro": "Modelo ainda não foi treinado"}

    try:
        df_novo = pd.DataFrame(request.dados)

        # Verifica se os atributos estão presentes nos dados
        for col in atributos_usados:
            if col not in df_novo.columns:
                raise ValueError(f"Atributo '{col}' ausente nos dados enviados.")

        X_novo = df_novo[atributos_usados]
        preds = modelo_treinado.predict(X_novo)

        return {
            "status": "previsões realizadas",
            "previsoes": preds.tolist()
        }

    except Exception as e:
        return {"erro": str(e)}
