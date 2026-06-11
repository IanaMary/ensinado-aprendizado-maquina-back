"""
Dataset models for the Iana ML pipeline.

Base class DatasetConfig provides common fields.
Subclasses specialize for specific dataset types (toy, UCI, custom).
"""

import random
import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class DatasetType(str, Enum):
    CLASSIFICATION = "classificacao"
    REGRESSION = "regressao"
    CLUSTERING = "agrupamento"


class PreSplitStatus(str, Enum):
    SPLIT = "split"          # Dados ja vem separados em treino/teste
    SINGLE = "single"        # Dados vem em unico arquivo, precisa separar
    CROSS_VAL = "cross_val"  # Dados para validacao cruzada


@dataclass
class DatasetConfig:
    """Base configuration for any dataset."""
    
    # Identificacao
    id: str                          # ID unico (ex: "iris", "adult")
    nome: str                        # Nome amigavel
    descricao: str                   # Descricao educacional
    fonte: str                       # "sklearn", "uci", "csv", "xlsx"
    
    # Tipo e estrutura
    tipo: DatasetType                # classificacao, regressao, agrupamento
    n_amostras: int                  # Total de amostras
    n_features: int                  # Numero de features
    target: Optional[str] = None     # Nome da coluna target
    colunas: List[str] = field(default_factory=list)
    
    # Split status
    pre_split: PreSplitStatus = PreSplitStatus.SINGLE
    n_treino: Optional[int] = None   # Se pre-split, quantas amostras de treino
    n_teste: Optional[int] = None    # Se pre-split, quantas amostras de teste
    
    # Metadados educacionais
    dificuldade: str = "iniciante"   # iniciante, intermediario, avancado
    descricao_target: str = ""       # O que o target representa
    descricao_features: str = ""     # O que as features representam
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "valor": self.id, # Aliasing id to valor
            "nome": self.nome,
            "descricao": self.descricao,
            "fonte": self.fonte,
            "tipo": self.tipo.value,
            "n_amostras": self.n_amostras,
            "n_features": self.n_features,
            "target": self.target,
            "colunas": self.colunas,
            "pre_split": self.pre_split.value,
            "n_treino": self.n_treino,
            "n_teste": self.n_teste,
            "dificuldade": self.dificuldade,
            "descricao_target": self.descricao_target,
            "descricao_features": self.descricao_features,
        }


# ============================================================
# Configuracoes dos Toy Datasets do Sklearn
# ============================================================

TOY_DATASETS: Dict[str, DatasetConfig] = {
    "iris": DatasetConfig(
        id="iris",
        nome="Iris",
        descricao="Classificação de 3 espécies de flores Iris (setosa, versicolor, virginica) com base em 4 medições das pétalas e sépalas.",
        fonte="sklearn",
        tipo=DatasetType.CLASSIFICATION,
        n_amostras=150,
        n_features=4,
        target="species",
        pre_split=PreSplitStatus.SINGLE,
        dificuldade="iniciante",
        descricao_target="Espécie da flor Iris (setosa, versicolor ou virginica)",
        descricao_features="Comprimento e largura das sépalas e pétalas em centímetros",
    ),
    "wine": DatasetConfig(
        id="wine",
        nome="Wine",
        descricao="Análise química de vinhos cultivados na mesma região da Itália, com 13 atributos e 3 classes de cultivares.",
        fonte="sklearn",
        tipo=DatasetType.CLASSIFICATION,
        n_amostras=178,
        n_features=13,
        target="target",
        pre_split=PreSplitStatus.SINGLE,
        dificuldade="intermediario",
        descricao_target="Cultivar do vinho (classe 0, 1 ou 2)",
        descricao_features="13 atributos químicos: álcool, ácido málico, cinzas, alcalinidade das cinzas, magnésio, fenóis totais, flavonoides, etc.",
    ),
    "breast_cancer": DatasetConfig(
        id="breast_cancer",
        nome="Breast Cancer",
        descricao="Diagnóstico de câncer de mama baseado em características dos núcleos celulares de imagens digitalizadas de aspirado por agulha fina.",
        fonte="sklearn",
        tipo=DatasetType.CLASSIFICATION,
        n_amostras=569,
        n_features=30,
        target="target",
        pre_split=PreSplitStatus.SINGLE,
        dificuldade="intermediario",
        descricao_target="Diagnóstico: maligno (M) ou benigno (B)",
        descricao_features="30 características calculadas: média, erro padrão e pior valor de raio, textura, perímetro, área, suavidade, compacidade, concavidade, pontos côncavos, simetria e dimensão fractal",
    ),
    "digits": DatasetConfig(
        id="digits",
        nome="Digits",
        descricao="Reconhecimento de dígitos manuscritos (0-9) representados como imagens 8x8 pixels.",
        fonte="sklearn",
        tipo=DatasetType.CLASSIFICATION,
        n_amostras=1797,
        n_features=64,
        target="target",
        pre_split=PreSplitStatus.SINGLE,
        dificuldade="intermediario",
        descricao_target="Dígito escrito (0 a 9)",
        descricao_features="64 valores de intensidade de pixel (0-16) de uma imagem 8x8",
    ),
    "diabetes": DatasetConfig(
        id="diabetes",
        nome="Diabetes",
        descricao="Progressão de diabetes após um ano, baseada em 10 variáveis biométricas medidas em 442 pacientes.",
        fonte="sklearn",
        tipo=DatasetType.REGRESSION,
        n_amostras=442,
        n_features=10,
        target="target",
        pre_split=PreSplitStatus.SINGLE,
        dificuldade="intermediario",
        descricao_target="Medida quantitativa da progressão do diabetes após 1 ano",
        descricao_features="10 variáveis: idade, sexo, IMC, pressão arterial, e 6 medidas sanguíneas (s1-s6)",
    ),
    "california_housing": DatasetConfig(
        id="california_housing",
        nome="California Housing",
        descricao="Preços de imóveis na Califórnia (1990) com base em 8 características do censo.",
        fonte="sklearn",
        tipo=DatasetType.REGRESSION,
        n_amostras=20640,
        n_features=8,
        target="MedHouseVal",
        pre_split=PreSplitStatus.SINGLE,
        dificuldade="iniciante",
        descricao_target="Valor mediano das casas em $100.000",
        descricao_features="Renda mediana, idade média das casas, média de cômodos, média de quartos, população, ocupação média, latitude, longitude",
    ),
}


# ============================================================
# Configuracoes dos Datasets UCI
# ============================================================

UCI_DATASETS: Dict[str, DatasetConfig] = {
    "adult": DatasetConfig(
        id="adult",
        nome="Adult (Census Income)",
        descricao="Prever se a renda anual de uma pessoa excede $50K com base em dados do censo dos EUA.",
        fonte="uci",
        tipo=DatasetType.CLASSIFICATION,
        n_amostras=48842,
        n_features=14,
        target="income",
        pre_split=PreSplitStatus.SPLIT,
        n_treino=32561,
        n_teste=16281,
        dificuldade="intermediario",
        descricao_target="Renda: >50K ou <=50K",
        descricao_features="Idade, classe trabalhadora, educação, estado civil, ocupação, relação, raça, sexo, ganho de capital, perda de capital, horas por semana, país",
    ),
    "wine_quality": DatasetConfig(
        id="wine_quality",
        nome="Wine Quality",
        descricao="Prever qualidade de vinho tinto com base em testes físico-químicos.",
        fonte="uci",
        tipo=DatasetType.CLASSIFICATION,
        n_amostras=1599,
        n_features=11,
        target="quality",
        pre_split=PreSplitStatus.SINGLE,
        dificuldade="intermediario",
        descricao_target="Qualidade do vinho (escala 0-10)",
        descricao_features="Acidez fixa, acidez volátil, ácido cítro, açúcar residual, cloretos, dióxido de enxofre livre/total, densidade, pH, sulfatos, álcool",
    ),
    "heart_disease": DatasetConfig(
        id="heart_disease",
        nome="Heart Disease",
        descricao="Diagnóstico de doença cardíaca baseado em exames clínicos.",
        fonte="uci",
        tipo=DatasetType.CLASSIFICATION,
        n_amostras=303,
        n_features=13,
        target="num",
        pre_split=PreSplitStatus.SINGLE,
        dificuldade="intermediario",
        descricao_target="Presença de doença cardíaca (0=sim, 1-4=graus)",
        descricao_features="Idade, sexo, tipo de dor torácica, pressão arterial, colesterol, açúcar no sangue, ECG, frequência cardíaca máxima, angina induzida por exercício, declive ST, número de vasos principais coloridos, talassemia",
    ),
    "titanic": DatasetConfig(
        id="titanic",
        nome="Titanic",
        descricao="Prever sobrevivência no naufrágio do Titanic com base em dados dos passageiros.",
        fonte="uci",
        tipo=DatasetType.CLASSIFICATION,
        n_amostras=1309,
        n_features=7,
        target="Survived",
        pre_split=PreSplitStatus.SINGLE,
        dificuldade="iniciante",
        descricao_target="Sobreviveu (1) ou não (0)",
        descricao_features="Classe social, sexo, idade, tarifa, número de irmãos/cônjuge a bordo, número de pais/filhos a bordo, porto de embarque",
    ),
    "abalone": DatasetConfig(
        id="abalone",
        nome="Abalone",
        descricao="Prever idade de abalone (molusco) com base em medições físicas.",
        fonte="uci",
        tipo=DatasetType.REGRESSION,
        n_amostras=4177,
        n_features=8,
        target="Rings",
        pre_split=PreSplitStatus.SINGLE,
        dificuldade="intermediario",
        descricao_target="Número de anéis (indica idade)",
        descricao_features="Sexo, comprimento, diâmetro, altura, peso inteiro, peso descascado, peso vísceras, peso casca",
    ),
    "car_evaluation": DatasetConfig(
        id="car_evaluation",
        nome="Car Evaluation",
        descricao="Avaliação de aceitabilidade de carros com base em características.",
        fonte="uci",
        tipo=DatasetType.CLASSIFICATION,
        n_amostras=1728,
        n_features=6,
        target="class",
        pre_split=PreSplitStatus.SINGLE,
        dificuldade="iniciante",
        descricao_target="Aceitabilidade: unacc, acc, good, vgood",
        descricao_features="Preço de compra, preço de manutenção, número de portas, capacidade de pessoas, tamanho do porta-malas, segurança",
    ),
    "mushroom": DatasetConfig(
        id="mushroom",
        nome="Mushroom",
        descricao="Classificar cogumelos como comestíveis ou venenosos com base em características visuais.",
        fonte="uci",
        tipo=DatasetType.CLASSIFICATION,
        n_amostras=8124,
        n_features=22,
        target="class",
        pre_split=PreSplitStatus.SINGLE,
        dificuldade="iniciante",
        descricao_target="Classe: comestível (e) ou venenoso (p)",
        descricao_features="22 atributos categóricos: formato do chapéu, superfície do chapéu, cor do chapéu, hematomas, odor, tipo de guelra, etc.",
    ),
}


def get_all_datasets() -> Dict[str, DatasetConfig]:
    """Retorna todos os datasets disponiveis."""
    all_datasets = {}
    all_datasets.update(TOY_DATASETS)
    all_datasets.update(UCI_DATASETS)
    return all_datasets


def get_dataset_config(dataset_id: str) -> Optional[DatasetConfig]:
    """Retorna a configuracao de um dataset especifico."""
    all_datasets = get_all_datasets()
    return all_datasets.get(dataset_id)
