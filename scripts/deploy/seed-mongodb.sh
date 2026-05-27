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
        label: "Arquivo XLSX",
        valor: "xlsx",
        tipoItem: "coleta-dado",
        habilitado: true,
        movido: false,
        icon: "coleta-dado",
        resumo: "Upload de arquivo Excel (.xlsx)"
    },
    {
        label: "Arquivo CSV",
        valor: "csv",
        tipoItem: "coleta-dado",
        habilitado: true,
        movido: false,
        icon: "coleta-dado",
        resumo: "Upload de arquivo CSV"
    },
    {
        label: "Arquivo JSON",
        valor: "json",
        tipoItem: "coleta-dado",
        habilitado: true,
        movido: false,
        icon: "coleta-dado",
        resumo: "Upload de arquivo JSON"
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
        ]
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
        ]
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
        ]
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
            { nomeHiperparametro: "solver", valorPadrao: "lbfgs" },
            { nomeHiperparametro: "max_iter", valorPadrao: 100 }
        ]
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
        resumo: "Linear Regression"
    },
    {
        label: "K-means",
        valor: "kmeans",
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
        ]
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
        ]
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
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Proporção de previsões corretas"
    },
    {
        label: "Precisão",
        valor: "precision_score",
        tipoItem: "metrica",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Proporção de positivos corretos"
    },
    {
        label: "Recall",
        valor: "recall_score",
        tipoItem: "metrica",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Proporção de positivos detectados"
    },
    {
        label: "F1-Score",
        valor: "f1_score",
        tipoItem: "metrica",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Média harmônica entre precisão e recall"
    },
    {
        label: "Matriz de Confusão",
        valor: "confusion_matrix",
        tipoItem: "metrica",
        habilitado: true,
        movido: false,
        icon: "metrica",
        resumo: "Matriz de verdadeiros/falsos positivos e negativos"
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
            agrupamento: { explicacao: "Agrupa dados similares.", modelos: ["kmeans"] }
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
