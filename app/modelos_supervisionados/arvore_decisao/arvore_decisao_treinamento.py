from sklearn.tree import DecisionTreeClassifier
from app.models.schemas import DatasetRequest
from app.deps import pd, mlflow, train_test_split
from fastapi import APIRouter
from typing import List, Dict, Any

router = APIRouter()

modelos_treinados: Dict[str, Any] = {}
atributos_usados: Dict[str, List[str]] = {}


@router.post("/arvore_decisao")
def treinar_arvore_decisao(request: DatasetRequest):
    try:
        df_treino = pd.DataFrame(request.dados_treino)

        if request.dados_teste and len(request.dados_teste) > 0:
            df_teste = pd.DataFrame(request.dados_teste)
        else:
            test_size = request.porcentagem_teste
            df_treino, df_teste = train_test_split(df_treino, test_size=test_size, random_state=42)

        for col in request.atributos + [request.target]:
            if col not in df_treino.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados de treino.")

        X_train = df_treino[request.atributos]
        y_train = df_treino[request.target]

        X_test = df_teste[request.atributos]
        y_test = df_teste[request.target]

        model = DecisionTreeClassifier(**request.hiperparametros)

        with mlflow.start_run(run_name="Decision Tree Model"):
            model.fit(X_train, y_train)
            mlflow.log_params(request.hiperparametros)
            mlflow.sklearn.log_model(model, "arvore_decisao")
            run_id = mlflow.active_run().info.run_id

        modelos_treinados['arvore_decisao'] = model
        atributos_usados['arvore_decisao'] = request.atributos

        df_teste_completo = X_test.copy()
        df_teste_completo[request.target] = y_test

        return {
            "status": "modelo árvore de decisão treinado com sucesso",
            "total_amostras_treino": len(X_train),
            "total_amostras_teste": len(X_test),
            "atributos": request.atributos,
            "target": request.target,
            "teste": df_teste_completo.to_dict(orient='records'),
            "hiperparametros": model.get_params(),
            "classes": list(model.classes_),
            "modelo": "arvore_decisao",
            "mlflow_run_id_modelo": run_id
        }

    except Exception as e:
        return {"erro": str(e)}
