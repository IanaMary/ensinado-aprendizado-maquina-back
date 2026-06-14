#!/bin/bash
# seed-mongodb.sh - Popula as coleções iniciais do MongoDB
# IMPORTANTE: Execute este script apenas uma vez, após a primeira instalação do MongoDB
set -e

echo "=== Populando coleções do MongoDB ==="

DB_NAME="ensinado_aprendizado_maquina"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SEED_DIR="$SCRIPT_DIR/seed"

# Verifica se mongosh está disponível
if ! command -v mongosh &> /dev/null; then
    echo "ERRO: mongosh não encontrado. Instale o MongoDB primeiro com setup-mongodb.sh"
    exit 1
fi

echo "Usando banco: $DB_NAME"

# ---- opcoes_coletas ----
echo "Populando coleção: coleta_dados"
mongosh --quiet "$DB_NAME" --eval '
db.coleta_dados.deleteMany({});
db.coleta_dados.insertMany([
    {
        label: "Excel",
        valor: "xlsx",
        tipoItem: "coleta-dado",
        habilitado: true,
        movido: false,
        icon: "coleta-dado",
        resumo: "Upload de arquivo Excel (.xlsx)"
    },
    {
        label: "CSV",
        valor: "csv",
        tipoItem: "coleta-dado",
        habilitado: true,
        movido: false,
        icon: "coleta-dado",
        resumo: "Upload de arquivo CSV"
    },
    {
        label: "JSON",
        valor: "json",
        tipoItem: "coleta-dado",
        habilitado: true,
        movido: false,
        icon: "coleta-dado",
        resumo: "Upload de arquivo JSON"
    },
    {
        label: "Dataset",
        valor: "dataset",
        tipoItem: "coleta-dado",
        habilitado: true,
        movido: false,
        icon: "coleta-dado",
        resumo: "Escolher um dataset pronto (sklearn ou UCI)"
    }
]);
print("  -> coleta_dados: OK (" + db.coleta_dados.countDocuments({}) + " documentos)");
'

# ---- opcoes_modelos ----
echo "Populando coleção: modelos"
mongosh --quiet "$DB_NAME" --eval '
db.modelos.deleteMany({});
db.modelos.insertMany([
    {
        label: "k-NN",
        valor: "knn",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: true,
        dados_rotulados: true,
        resumo: "K-Nearest Neighbors",
        hiperparametros: [
            { nomeHiperparametro: "n_neighbors", valorPadrao: 5 },
            { nomeHiperparametro: "weights", valorPadrao: "uniform" },
            { nomeHiperparametro: "algorithm", valorPadrao: "auto" }
        ],
        metricas: ["accuracy_score", "precision_score", "recall_score", "f1_score", "confusion_matrix"]
    },
    {
        label: "Árvore de Decisão",
        valor: "arvore_decisao",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: true,
        dados_rotulados: true,
        resumo: "Decision Tree Classifier",
        hiperparametros: [
            { nomeHiperparametro: "criterion", valorPadrao: "gini" },
            { nomeHiperparametro: "max_depth", valorPadrao: null },
            { nomeHiperparametro: "min_samples_split", valorPadrao: 2 }
        ],
        metricas: ["accuracy_score", "precision_score", "recall_score", "f1_score", "confusion_matrix"]
    },
    {
        label: "SVM",
        valor: "svm",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: true,
        dados_rotulados: true,
        resumo: "Support Vector Machine",
        hiperparametros: [
            { nomeHiperparametro: "C", valorPadrao: 1.0 },
            { nomeHiperparametro: "kernel", valorPadrao: "rbf" },
            { nomeHiperparametro: "gamma", valorPadrao: "scale" }
        ],
        metricas: ["accuracy_score", "precision_score", "recall_score", "f1_score", "confusion_matrix"]
    },
    {
        label: "Regressão Logística",
        valor: "regressao_logistica",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: true,
        dados_rotulados: true,
        resumo: "Logistic Regression",
        hiperparametros: [
            { nomeHiperparametro: "C", valorPadrao: 1.0 },
            { nomeHiperparametro: "penalty", valorPadrao: "l2" },
            { nomeHiperparametro: "solver", valorPadrao: "lbfgs" },
            { nomeHiperparametro: "max_iter", valorPadrao: 100 },
            { nomeHiperparametro: "fit_intercept", valorPadrao: true },
            { nomeHiperparametro: "tol", valorPadrao: 0.0001 }
        ],
        metricas: ["accuracy_score", "precision_score", "recall_score", "f1_score", "confusion_matrix"]
    },
    {
        label: "Regressão Linear",
        valor: "regressao_linear",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: false,
        dados_rotulados: true,
        resumo: "Linear Regression",
        hiperparametros: [
            { nomeHiperparametro: "fit_intercept", valorPadrao: true },
            { nomeHiperparametro: "positive", valorPadrao: false },
            { nomeHiperparametro: "copy_X", valorPadrao: true },
            { nomeHiperparametro: "n_jobs", valorPadrao: null }
        ],
        metricas: ["r2_score", "mean_squared_error", "root_mean_squared_error", "mean_absolute_error"]
    },
    {
        label: "K-means",
        valor: "k_means",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: false,
        dados_rotulados: false,
        resumo: "K-Means Clustering",
        hiperparametros: [
            { nomeHiperparametro: "n_clusters", valorPadrao: 3 },
            { nomeHiperparametro: "init", valorPadrao: "k-means++" },
            { nomeHiperparametro: "max_iter", valorPadrao: 300 }
        ],
        metricas: ["silhouette_score", "calinski_harabasz_score", "davies_bouldin_score"]
    },
    {
        label: "PCA",
        valor: "pca",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: false,
        dados_rotulados: false,
        resumo: "Principal Component Analysis",
        hiperparametros: [
            { nomeHiperparametro: "n_components", valorPadrao: 2 }
        ],
        metricas: ["silhouette_score", "calinski_harabasz_score", "davies_bouldin_score"]
    },
    {
        label: "SVM Linear",
        valor: "svm_linear",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: true,
        dados_rotulados: true,
        resumo: "SVM com kernel linear. Mais rápido para dados linearmente separáveis.",
        hiperparametros: [
            { nomeHiperparametro: "C", valorPadrao: 1.0 }
        ],
        metricas: ["accuracy_score", "precision_score", "recall_score", "f1_score", "confusion_matrix"]
    },
    {
        label: "Random Forest",
        valor: "random_forest",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: true,
        dados_rotulados: true,
        resumo: "Conjunto de árvores de decisão que votam na classe final.",
        hiperparametros: [
            { nomeHiperparametro: "n_estimators", valorPadrao: 100 },
            { nomeHiperparametro: "max_depth", valorPadrao: null },
            { nomeHiperparametro: "criterion", valorPadrao: "gini" }
        ],
        metricas: ["accuracy_score", "precision_score", "recall_score", "f1_score", "confusion_matrix"]
    },
    {
        label: "AdaBoost",
        valor: "adaboost",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: true,
        dados_rotulados: true,
        resumo: "Combina classificadores fracos em um classificador forte.",
        hiperparametros: [
            { nomeHiperparametro: "n_estimators", valorPadrao: 50 },
            { nomeHiperparametro: "learning_rate", valorPadrao: 1.0 }
        ],
        metricas: ["accuracy_score", "precision_score", "recall_score", "f1_score", "confusion_matrix"]
    },
    {
        label: "Naive Bayes",
        valor: "naive_bayes",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: true,
        dados_rotulados: true,
        resumo: "Classificador probabilístico baseado no Teorema de Bayes.",
        hiperparametros: [],
        metricas: ["accuracy_score", "precision_score", "recall_score", "f1_score", "confusion_matrix"]
    },
    {
        label: "Rede Neural (MLP)",
        valor: "mlp",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: true,
        dados_rotulados: true,
        resumo: "Multi-Layer Perceptron: rede neural com camadas ocultas.",
        hiperparametros: [
            { nomeHiperparametro: "hidden_layer_sizes", valorPadrao: 100 },
            { nomeHiperparametro: "activation", valorPadrao: "relu" },
            { nomeHiperparametro: "solver", valorPadrao: "adam" },
            { nomeHiperparametro: "alpha", valorPadrao: 0.0001 },
            { nomeHiperparametro: "learning_rate", valorPadrao: "constant" },
            { nomeHiperparametro: "learning_rate_init", valorPadrao: 0.001 },
            { nomeHiperparametro: "max_iter", valorPadrao: 500 },
            { nomeHiperparametro: "early_stopping", valorPadrao: false }
        ],
        metricas: ["accuracy_score", "precision_score", "recall_score", "f1_score", "confusion_matrix"]
    },
    {
        label: "QDA",
        valor: "qda",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: true,
        dados_rotulados: true,
        resumo: "Quadratic Discriminant Analysis: assume covariância diferente por classe.",
        hiperparametros: [],
        metricas: ["accuracy_score", "precision_score", "recall_score", "f1_score", "confusion_matrix"]
    },
    {
        label: "SGD Classifier",
        valor: "sgd",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: true,
        dados_rotulados: true,
        resumo: "Classificador linear treinado por gradiente descendente estocástico. Escala bem para muitos dados.",
        hiperparametros: [
            { nomeHiperparametro: "loss", valorPadrao: "hinge" },
            { nomeHiperparametro: "penalty", valorPadrao: "l2" },
            { nomeHiperparametro: "alpha", valorPadrao: 0.0001 },
            { nomeHiperparametro: "l1_ratio", valorPadrao: 0.15 },
            { nomeHiperparametro: "max_iter", valorPadrao: 1000 },
            { nomeHiperparametro: "tol", valorPadrao: 0.001 },
            { nomeHiperparametro: "learning_rate", valorPadrao: "optimal" },
            { nomeHiperparametro: "eta0", valorPadrao: 0.01 },
            { nomeHiperparametro: "fit_intercept", valorPadrao: true },
            { nomeHiperparametro: "early_stopping", valorPadrao: false }
        ],
        metricas: ["accuracy_score", "precision_score", "recall_score", "f1_score", "confusion_matrix"]
    },
    {
        label: "Perceptron",
        valor: "perceptron",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: true,
        dados_rotulados: true,
        resumo: "O classificador linear mais simples: ajusta uma reta separadora aprendendo com os erros.",
        hiperparametros: [
            { nomeHiperparametro: "penalty", valorPadrao: null },
            { nomeHiperparametro: "alpha", valorPadrao: 0.0001 },
            { nomeHiperparametro: "max_iter", valorPadrao: 1000 },
            { nomeHiperparametro: "tol", valorPadrao: 0.001 },
            { nomeHiperparametro: "eta0", valorPadrao: 1.0 },
            { nomeHiperparametro: "fit_intercept", valorPadrao: true },
            { nomeHiperparametro: "early_stopping", valorPadrao: false }
        ],
        metricas: ["accuracy_score", "precision_score", "recall_score", "f1_score", "confusion_matrix"]
    },
    {
        label: "Ridge",
        valor: "ridge",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: false,
        dados_rotulados: true,
        resumo: "Regressão Linear com regularização L2: penaliza coeficientes grandes para evitar overfitting.",
        hiperparametros: [
            { nomeHiperparametro: "alpha", valorPadrao: 1.0 },
            { nomeHiperparametro: "fit_intercept", valorPadrao: true },
            { nomeHiperparametro: "solver", valorPadrao: "auto" },
            { nomeHiperparametro: "max_iter", valorPadrao: null },
            { nomeHiperparametro: "tol", valorPadrao: 0.0001 },
            { nomeHiperparametro: "positive", valorPadrao: false },
            { nomeHiperparametro: "copy_X", valorPadrao: true }
        ],
        metricas: ["r2_score", "mean_squared_error", "root_mean_squared_error", "mean_absolute_error"]
    },
    {
        label: "Regressão Polinomial",
        valor: "regressao_polinomial",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: false,
        dados_rotulados: true,
        resumo: "Regressão Linear sobre atributos elevados a potências: ajusta curvas, não só retas.",
        hiperparametros: [
            { nomeHiperparametro: "degree", valorPadrao: 2 },
            { nomeHiperparametro: "include_bias", valorPadrao: true },
            { nomeHiperparametro: "interaction_only", valorPadrao: false },
            { nomeHiperparametro: "fit_intercept", valorPadrao: true },
            { nomeHiperparametro: "positive", valorPadrao: false }
        ],
        metricas: ["r2_score", "mean_squared_error", "root_mean_squared_error", "mean_absolute_error"]
    },
    {
        label: "Regressão Quantílica",
        valor: "quantile",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: false,
        dados_rotulados: true,
        resumo: "Prevê um quantil (ex.: a mediana) em vez da média. Útil quando há valores extremos.",
        hiperparametros: [
            { nomeHiperparametro: "quantile", valorPadrao: 0.5 },
            { nomeHiperparametro: "alpha", valorPadrao: 1.0 },
            { nomeHiperparametro: "fit_intercept", valorPadrao: true },
            { nomeHiperparametro: "solver", valorPadrao: "highs" }
        ],
        metricas: ["r2_score", "mean_squared_error", "root_mean_squared_error", "mean_absolute_error"]
    },
    {
        label: "Regressão de Huber",
        valor: "huber",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: false,
        dados_rotulados: true,
        resumo: "Regressão robusta: combina erro quadrático e absoluto para sofrer menos com outliers.",
        hiperparametros: [
            { nomeHiperparametro: "epsilon", valorPadrao: 1.35 },
            { nomeHiperparametro: "alpha", valorPadrao: 0.0001 },
            { nomeHiperparametro: "max_iter", valorPadrao: 100 },
            { nomeHiperparametro: "fit_intercept", valorPadrao: true },
            { nomeHiperparametro: "tol", valorPadrao: 0.00001 },
            { nomeHiperparametro: "warm_start", valorPadrao: false }
        ],
        metricas: ["r2_score", "mean_squared_error", "root_mean_squared_error", "mean_absolute_error"]
    },
    {
        label: "Regressão RANSAC",
        valor: "ransac",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: false,
        dados_rotulados: true,
        resumo: "Ajusta o modelo só nos pontos 'bons' (inliers), ignorando outliers automaticamente.",
        hiperparametros: [
            { nomeHiperparametro: "min_samples", valorPadrao: null },
            { nomeHiperparametro: "residual_threshold", valorPadrao: null },
            { nomeHiperparametro: "max_trials", valorPadrao: 100 },
            { nomeHiperparametro: "stop_probability", valorPadrao: 0.99 },
            { nomeHiperparametro: "loss", valorPadrao: "absolute_error" }
        ],
        metricas: ["r2_score", "mean_squared_error", "root_mean_squared_error", "mean_absolute_error"]
    },
    {
        label: "Regressão Theil-Sen",
        valor: "theilsen",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: false,
        dados_rotulados: true,
        resumo: "Regressão robusta baseada em medianas de inclinações. Resiste bem a outliers.",
        hiperparametros: [
            { nomeHiperparametro: "fit_intercept", valorPadrao: true },
            { nomeHiperparametro: "max_subpopulation", valorPadrao: 10000 },
            { nomeHiperparametro: "n_subsamples", valorPadrao: null },
            { nomeHiperparametro: "max_iter", valorPadrao: 300 },
            { nomeHiperparametro: "tol", valorPadrao: 0.001 },
            { nomeHiperparametro: "n_jobs", valorPadrao: null }
        ],
        metricas: ["r2_score", "mean_squared_error", "root_mean_squared_error", "mean_absolute_error"]
    },
    {
        label: "SVR (Regressão SVM)",
        valor: "svr",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: false,
        dados_rotulados: true,
        resumo: "Support Vector Regression: versão de regressão das máquinas de vetores de suporte.",
        hiperparametros: [
            { nomeHiperparametro: "C", valorPadrao: 1.0 },
            { nomeHiperparametro: "kernel", valorPadrao: "rbf" },
            { nomeHiperparametro: "gamma", valorPadrao: "scale" },
            { nomeHiperparametro: "epsilon", valorPadrao: 0.1 },
            { nomeHiperparametro: "degree", valorPadrao: 3 },
            { nomeHiperparametro: "coef0", valorPadrao: 0.0 },
            { nomeHiperparametro: "tol", valorPadrao: 0.001 },
            { nomeHiperparametro: "shrinking", valorPadrao: true },
            { nomeHiperparametro: "max_iter", valorPadrao: -1 }
        ],
        metricas: ["r2_score", "mean_squared_error", "root_mean_squared_error", "mean_absolute_error"]
    },
    {
        label: "Rede Neural (MLP) Regressora",
        valor: "mlp_regressor",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: false,
        dados_rotulados: true,
        resumo: "Rede neural com camadas ocultas para prever valores contínuos.",
        hiperparametros: [
            { nomeHiperparametro: "hidden_layer_sizes", valorPadrao: 100 },
            { nomeHiperparametro: "activation", valorPadrao: "relu" },
            { nomeHiperparametro: "solver", valorPadrao: "adam" },
            { nomeHiperparametro: "alpha", valorPadrao: 0.0001 },
            { nomeHiperparametro: "learning_rate", valorPadrao: "constant" },
            { nomeHiperparametro: "learning_rate_init", valorPadrao: 0.001 },
            { nomeHiperparametro: "max_iter", valorPadrao: 500 },
            { nomeHiperparametro: "early_stopping", valorPadrao: false }
        ],
        metricas: ["r2_score", "mean_squared_error", "root_mean_squared_error", "mean_absolute_error"]
    },
    {
        label: "k-NN Regressor",
        valor: "knn_regressor",
        tipoItem: "treino-validacao-teste",
        habilitado: true,
        movido: false,
        icon: "metrica",
        prever_categoria: false,
        dados_rotulados: true,
        resumo: "k vizinhos mais próximos para regressão: prevê a média dos vizinhos mais parecidos.",
        hiperparametros: [
            { nomeHiperparametro: "n_neighbors", valorPadrao: 5 },
            { nomeHiperparametro: "weights", valorPadrao: "uniform" },
            { nomeHiperparametro: "algorithm", valorPadrao: "auto" },
            { nomeHiperparametro: "leaf_size", valorPadrao: 30 },
            { nomeHiperparametro: "p", valorPadrao: 2 },
            { nomeHiperparametro: "metric", valorPadrao: "minkowski" }
        ],
        metricas: ["r2_score", "mean_squared_error", "root_mean_squared_error", "mean_absolute_error"]
    }
]);
print("  -> modelos: OK (" + db.modelos.countDocuments({}) + " documentos)");
'

# ---- opcoes_metricas ----
echo "Populando coleção: metricas"
mongosh --quiet "$DB_NAME" --eval '
db.metricas.deleteMany({});
db.metricas.insertMany([
    {
        label: "Acurácia",
        valor: "accuracy_score",
        tipoItem: "metrica",
        grupo: "classificacao",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Proporção de previsões corretas",
        explicacao: "Das 100 amostras de teste, quantas o modelo acertou? É a métrica mais simples: acertos dividido pelo total. Pode enganar quando as classes são desbalanceadas — um modelo que sempre prevê a classe majoritária pode ter acurácia alta sem ser útil."
    },
    {
        label: "Precisão",
        valor: "precision_score",
        tipoItem: "metrica",
        grupo: "classificacao",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Das previsões positivas, quantas estavam corretas",
        explicacao: "Se o modelo disse \"é spam\" 10 vezes e 8 realmente eram spam, a precisão é 80%. Importante quando o custo de um falso positivo é alto — por exemplo, marcar um e-mail legítimo como spam."
    },
    {
        label: "Recall",
        valor: "recall_score",
        tipoItem: "metrica",
        grupo: "classificacao",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Dos positivos reais, quantos o modelo detectou",
        explicacao: "Se existem 100 e-mails spam e o modelo detectou 70, o recall é 70%. Importante quando o custo de um falso negativo é alto — por exemplo, deixar passar um spam perigoso ou não detectar uma doença."
    },
    {
        label: "F1-Score",
        valor: "f1_score",
        tipoItem: "metrica",
        grupo: "classificacao",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Média harmônica entre precisão e recall",
        explicacao: "Resume precisão e recall em um único número. Se um dos dois for baixo, o F1 cai bastante. Útil quando as classes estão desbalanceadas e você precisa equilibrar os dois tipos de erro."
    },
    {
        label: "Matriz de Confusão",
        valor: "confusion_matrix",
        tipoItem: "metrica",
        grupo: "classificacao",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Tabela de acertos e erros por classe",
        explicacao: "Mostra exatamente onde o modelo acerta e onde erra. A diagonal principal mostra os acertos; os números fora da diagonal mostram os erros — por exemplo, quantos gatos foram confundidos com cachorros."
    },
    {
        label: "Silhouette Score",
        valor: "silhouette_score",
        tipoItem: "metrica",
        grupo: "agrupamento",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Quão bem definidos estão os clusters (-1 a 1)",
        explicacao: "Mede o quão parecido cada ponto é com seu próprio cluster comparado aos outros clusters. Valores próximos de 1 indicam clusters bem separados; próximos de 0 indicam sobreposição; negativos indicam pontos possivelmente no cluster errado."
    },
    {
        label: "Calinski-Harabasz",
        valor: "calinski_harabasz_score",
        tipoItem: "metrica",
        grupo: "agrupamento",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Razão entre separação e coesão dos clusters",
        explicacao: "Compara a dispersão entre os clusters (quão distantes estão entre si) com a dispersão dentro de cada cluster (quão compactos são). Valores maiores indicam clusters mais definidos e separados."
    },
    {
        label: "Davies-Bouldin",
        valor: "davies_bouldin_score",
        tipoItem: "metrica",
        grupo: "agrupamento",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Similaridade média entre clusters (quanto menor, melhor)",
        explicacao: "Para cada cluster, calcula o quão parecido ele é com o cluster mais próximo. A média desses valores é o Davies-Bouldin. Zero significaria clusters perfeitamente separados. Valores baixos indicam boa separação."
    },
    {
        label: "R² (Coef. de Determinação)",
        valor: "r2_score",
        tipoItem: "metrica",
        grupo: "regressao",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Quanto da variação o modelo explica (0 a 1)",
        explicacao: "Indica o quanto o modelo explica a variação dos valores reais. R² = 1 é uma previsão perfeita; R² = 0 equivale a sempre chutar a média dos valores. Pode ser negativo quando o modelo é pior do que esse chute."
    },
    {
        label: "Erro Quadrático Médio (MSE)",
        valor: "mean_squared_error",
        tipoItem: "metrica",
        grupo: "regressao",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Média dos erros ao quadrado (quanto menor, melhor)",
        explicacao: "Eleva cada erro ao quadrado e tira a média. Como eleva ao quadrado, pune mais os erros grandes. Fica na unidade ao quadrado do alvo, por isso costuma ser difícil de interpretar diretamente."
    },
    {
        label: "Raiz do Erro Quadrático (RMSE)",
        valor: "root_mean_squared_error",
        tipoItem: "metrica",
        grupo: "regressao",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Erro típico na mesma unidade do alvo (menor é melhor)",
        explicacao: "É a raiz quadrada do MSE, então volta para a mesma unidade do valor previsto. Se você prevê preços em reais, o RMSE também fica em reais — fácil de ler como o erro típico do modelo."
    },
    {
        label: "Erro Absoluto Médio (MAE)",
        valor: "mean_absolute_error",
        tipoItem: "metrica",
        grupo: "regressao",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Média do tamanho dos erros (quanto menor, melhor)",
        explicacao: "Tira a média do tamanho dos erros, sem elevar ao quadrado. É menos sensível a erros muito grandes do que o RMSE. Se o MAE é 5, em média o modelo erra 5 unidades para cima ou para baixo."
    }
]);
print("  -> metricas: OK (" + db.metricas.countDocuments({}) + " documentos)");
'

# ---- tutor ----
echo "Populando coleção: tutor"
mongosh --quiet "$DB_NAME" --eval '
db.tutor.deleteMany({});
db.tutor.insertMany([
    {
        pipe: "inicio",
        texto_pipe: "Bem-vindo ao tutor de Aprendizado de Máquina!",
        introducao: "Este tutor vai guiar você pelos conceitos fundamentais de aprendizado de máquina.",
        objetivo: "Ao final, você será capaz de construir seu próprio pipeline de ML."
    },
    {
        pipe: "coleta-dado",
        texto_pipe: "Coleta de Dados é o primeiro passo do pipeline de ML.",
        introducao: "Os dados são a matéria-prima do aprendizado de máquina.",
        explicacao: "Escolha o formato do seu arquivo de dados.",
        tipos: "Formatos suportados: XLSX, CSV e JSON.",
        importancia: "A qualidade dos dados determina a qualidade do modelo."
    },
    {
        pipe: "selecao-modelo",
        texto_pipe: "Seleção de Modelo é a escolha do algoritmo de ML.",
        introducao: "Existem diferentes tipos de aprendizado: supervisionado e não supervisionado.",
        supervisionado: {
            explicacao: "Aprendizado supervisionado usa dados rotulados para treinar o modelo.",
            classificacao: { explicacao: "Classificação prevê categorias discretas.", modelos: ["knn", "arvore_decisao", "svm", "regressao_logistica"] },
            regressao: { explicacao: "Regressão prevê valores contínuos.", modelos: ["regressao_linear"] }
        },
        nao_supervisionado: {
            explicacao: "Aprendizado não supervisionado encontra padrões sem rótulos.",
            reducao_dimensionalidade: { explicacao: "Reduz dimensionalidade preservando informação.", modelos: ["pca"] },
            agrupamento: { explicacao: "Agrupa dados similares.", modelos: ["k_means"] }
        }
    },
    {
        pipe: "treinamento",
        texto_pipe: "Treinamento é onde o modelo aprende com os dados.",
        introducao: "O modelo ajusta seus parâmetros para minimizar o erro.",
        explicacao: "Configure os hiperparâmetros e execute o treinamento.",
        divisao: "Os dados são divididos em treino e teste para avaliar o modelo."
    },
    {
        pipe: "selecao-metricas",
        texto_pipe: "Métricas avaliam o desempenho do modelo.",
        introducao: "Escolha as métricas adequadas ao seu problema.",
        explicacao: "Métricas diferentes revelam aspectos diferentes do desempenho.",
        metricas: ["accuracy_score", "precision_score", "recall_score", "f1_score", "confusion_matrix"]
    },
    {
        pipe: "avaliacao",
        texto_pipe: "Avaliação mostra os resultados do modelo treinado.",
        introducao: "Analise as métricas para entender o desempenho do modelo.",
        explicacao: "Compare modelos e escolha o melhor para seu problema."
    }
]);
print("  -> tutor: OK (" + db.tutor.countDocuments({}) + " documentos)");
'

echo ""
echo "=== Seed concluído com sucesso ==="
