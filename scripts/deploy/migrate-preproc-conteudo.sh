#!/usr/bin/env bash
# Migração NÃO-destrutiva (idempotente) para as frentes de:
#  - pré-processamento como elemento de 1ª classe (bloco `execucao` em db.pre_processamento)
#  - conteúdo educacional de amostra (campo `conteudo`)
#
# Diferente do seed-mongodb.sh, este script NÃO faz deleteMany: usa upsert/$set e
# preserva o `habilitado` já configurado pelo professor (via $setOnInsert). Seguro
# para rodar em produção sem perder customizações ou o catálogo existente.
set -e
DB_NAME="ensinado_aprendizado_maquina"

if ! command -v mongosh &> /dev/null; then
    echo "ERRO: mongosh não encontrado." >&2
    exit 1
fi

echo "Migrando pre_processamento (execucao) — upsert idempotente em $DB_NAME"
mongosh --quiet "$DB_NAME" --eval '
const itens = [
  { valor: "standard_scaler", label: "StandardScaler", grupo: "scalers", resumo: "Remove a média e escala para variância unitária. Z = (X - μ) / σ", execucao: { modulo: "sklearn.preprocessing", classe: "StandardScaler", hiperparametros: [], aplica_em: "todas", escopo: "transform_X" } },
  { valor: "minmax_scaler", label: "MinMaxScaler", grupo: "scalers", resumo: "Escala os dados para um intervalo fixo (padrão 0-1).", execucao: { modulo: "sklearn.preprocessing", classe: "MinMaxScaler", hiperparametros: [], aplica_em: "todas", escopo: "transform_X" } },
  { valor: "robust_scaler", label: "RobustScaler", grupo: "scalers", resumo: "Escala usando estatísticas robustas a outliers (mediana e IQR).", execucao: { modulo: "sklearn.preprocessing", classe: "RobustScaler", hiperparametros: [], aplica_em: "todas", escopo: "transform_X" } },
  { valor: "normalizer", label: "Normalizer", grupo: "scalers", resumo: "Normaliza amostras individualmente para norma unitária (L1 ou L2).", execucao: { modulo: "sklearn.preprocessing", classe: "Normalizer", hiperparametros: [ { nome: "norm", valorPadrao: "l2" } ], aplica_em: "todas", escopo: "transform_X" } },
  { valor: "onehot_encoder", label: "OneHotEncoder", grupo: "encoders", resumo: "Codifica features categóricas como array numérico one-hot.", execucao: { modulo: "sklearn.preprocessing", classe: "OneHotEncoder", hiperparametros: [ { nome: "sparse_output", valorPadrao: false }, { nome: "handle_unknown", valorPadrao: "ignore" } ], aplica_em: "colunas_escolhidas", escopo: "transform_X" } },
  { valor: "ordinal_encoder", label: "OrdinalEncoder", grupo: "encoders", resumo: "Codifica features categóricas como inteiros ordinais.", execucao: { modulo: "sklearn.preprocessing", classe: "OrdinalEncoder", hiperparametros: [ { nome: "handle_unknown", valorPadrao: "use_encoded_value" }, { nome: "unknown_value", valorPadrao: -1 } ], aplica_em: "colunas_escolhidas", escopo: "transform_X" } },
  { valor: "label_encoder", label: "LabelEncoder", grupo: "encoders", resumo: "Codifica rótulos de target entre 0 e n_classes-1.", execucao: { modulo: "sklearn.preprocessing", classe: "LabelEncoder", hiperparametros: [], aplica_em: "target", escopo: "encode_y" } },
  { valor: "simple_imputer", label: "SimpleImputer", grupo: "imputers", resumo: "Completa valores faltantes usando estratégia (média, mediana, moda, constante).", execucao: { modulo: "sklearn.impute", classe: "SimpleImputer", hiperparametros: [ { nome: "strategy", valorPadrao: "mean" } ], aplica_em: "todas", escopo: "transform_X", trata_ausentes: true } },
  { valor: "polynomial_features", label: "PolynomialFeatures", grupo: "transformers", resumo: "Gera features polinomiais e de interação.", execucao: { modulo: "sklearn.preprocessing", classe: "PolynomialFeatures", hiperparametros: [ { nome: "degree", valorPadrao: 2 }, { nome: "include_bias", valorPadrao: false } ], aplica_em: "colunas_escolhidas", escopo: "transform_X" } },
  { valor: "power_transformer", label: "PowerTransformer", grupo: "transformers", resumo: "Aplica transformação de potência para tornar os dados mais Gaussianos.", execucao: { modulo: "sklearn.preprocessing", classe: "PowerTransformer", hiperparametros: [ { nome: "method", valorPadrao: "yeo-johnson" } ], aplica_em: "todas", escopo: "transform_X" } }
];
let novos = 0, atualizados = 0;
for (const it of itens) {
  const r = db.pre_processamento.updateOne(
    { valor: it.valor },
    { $set: { label: it.label, grupo: it.grupo, resumo: it.resumo, tipoItem: "pre-processamento", movido: false, execucao: it.execucao },
      $setOnInsert: { habilitado: true } },
    { upsert: true }
  );
  if (r.upsertedCount) novos++; else atualizados++;
}
print("  -> pre_processamento: " + novos + " inseridos, " + atualizados + " atualizados (habilitado preservado)");
'

echo "Migrando conteudo educacional (amostra) — $set não-destrutivo"
mongosh --quiet "$DB_NAME" --eval '
db.modelos.updateOne({ valor: "knn" }, { $set: { conteudo: {
    titulo: "k-Nearest Neighbors (k-NN)",
    descricao: "Classifica um exemplo novo olhando para os k vizinhos mais próximos no conjunto de treino e escolhendo a classe mais comum entre eles.",
    intuicao: "Quem se parece anda junto: se os vizinhos mais próximos são da classe A, provavelmente o novo ponto também é A.",
    exemplo: "Para classificar uma flor, comparamos suas medidas com as flores conhecidas mais parecidas e usamos a espécie da maioria.",
    conceitos: [ { nome: "Vizinho", desc: "Exemplo de treino mais próximo segundo uma distância (ex.: euclidiana)." }, { nome: "k", desc: "Quantos vizinhos votam. k pequeno = sensível a ruído; k grande = fronteiras mais suaves." }, { nome: "Distância", desc: "Medida de quão parecidos dois exemplos são; por isso a escala das features importa." } ],
    quandoUsar: ["Poucos dados e fronteiras irregulares", "Quando interpretabilidade por similaridade ajuda"],
    naoUsarQuando: ["Muitos atributos (maldição da dimensionalidade)", "Bases muito grandes (predição fica lenta)"],
    vantagens: ["Simples e sem treino explícito", "Naturalmente multiclasse"],
    desvantagens: ["Sensível à escala das features", "Predição custosa em bases grandes"],
    hiperparametros_doc: [ { nome: "n_neighbors", descricao: "Número de vizinhos que votam.", tipo: "int", default: 5, efeito: "Valores baixos captam detalhes (overfit); altos suavizam.", quando_ajustar: "Aumente se houver ruído nos dados." }, { nome: "weights", descricao: "Peso dos vizinhos no voto.", tipo: "enum", opcoes: ["uniform", "distance"], default: "uniform", efeito: "distance dá mais peso aos vizinhos mais próximos." } ],
    midia: [ { tipo: "diagrama", url: "https://upload.wikimedia.org/wikipedia/commons/e/e7/KnnClassification.svg", legenda: "Decisão do k-NN: o ponto novo recebe a classe da maioria dos k vizinhos.", fonte: "Wikimedia Commons" } ],
    referencias: [ { titulo: "scikit-learn: Nearest Neighbors", autor: "scikit-learn", url: "https://scikit-learn.org/stable/modules/neighbors.html", tipo: "doc" }, { titulo: "An Introduction to Statistical Learning", autor: "James, Witten, Hastie, Tibshirani", url: "https://www.statlearning.com/", tipo: "livro", citacao: "Capítulo sobre métodos baseados em vizinhança." } ]
} } });

db.metricas.updateOne({ valor: "accuracy_score" }, { $set: { conteudo: {
    titulo: "Acurácia",
    descricao: "Proporção de previsões corretas sobre o total de exemplos avaliados.",
    intuicao: "De cada 100 exemplos de teste, quantos o modelo acertou?",
    exemplo: "Acertou 90 de 100 amostras -> acurácia de 90%.",
    formula: "acuracia = acertos / total",
    conceitos: [ { nome: "Acerto", desc: "Quando a classe prevista é igual à classe real." }, { nome: "Classe desbalanceada", desc: "Quando uma classe é muito mais frequente; aí a acurácia engana." } ],
    quandoUsar: ["Classes equilibradas", "Visão geral rápida do desempenho"],
    naoUsarQuando: ["Classes muito desbalanceadas (prefira F1, precisão, recall)"],
    referencias: [ { titulo: "scikit-learn: accuracy_score", autor: "scikit-learn", url: "https://scikit-learn.org/stable/modules/generated/sklearn.metrics.accuracy_score.html", tipo: "doc" } ]
} } });

db.pre_processamento.updateOne({ valor: "standard_scaler" }, { $set: { conteudo: {
    titulo: "StandardScaler",
    descricao: "Padroniza cada feature para média 0 e desvio-padrão 1, removendo diferenças de escala entre colunas.",
    intuicao: "Coloca todas as features na mesma régua, para que nenhuma domine só por ter números maiores.",
    exemplo: "Idade (0-100) e salário (0-10000) na mesma escala evitam que o salário pese mais por engano.",
    formula: "z = (x - média) / desvio_padrão",
    conceitos: [ { nome: "Média", desc: "Valor central da coluna, subtraído de cada valor." }, { nome: "Desvio-padrão", desc: "Espalhamento dos dados; divide para normalizar a variância." }, { nome: "Vazamento de dados", desc: "Ajuste (fit) só no treino; aplique (transform) no teste para não vazar informação." } ],
    quandoUsar: ["Modelos sensíveis à escala (k-NN, SVM, redes neurais)", "Features com unidades muito diferentes"],
    naoUsarQuando: ["Modelos de árvore, que não dependem de escala", "Dados muito esparsos (considere MaxAbsScaler)"],
    hiperparametros_doc: [ { nome: "with_mean", descricao: "Centraliza subtraindo a média.", tipo: "bool", default: true }, { nome: "with_std", descricao: "Escala para desvio-padrão unitário.", tipo: "bool", default: true } ],
    referencias: [ { titulo: "scikit-learn: Preprocessing data", autor: "scikit-learn", url: "https://scikit-learn.org/stable/modules/preprocessing.html", tipo: "doc" } ]
} } });
print("  -> conteudo educacional: OK");
'

echo ""
echo "=== Migração concluída (não-destrutiva) ==="
