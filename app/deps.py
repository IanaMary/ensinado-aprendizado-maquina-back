# app/deps.py

import pandas as pd
import mlflow
import mlflow.sklearn
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score
)

# Bibliotecas compartilhadas
__all__ = [
  'pd',
  'mlflow',
  'train_test_split',
  'KNeighborsClassifier',
  'SVC'
  'metricas_disponiveis',
]

# Dicionário de métricas suportadas
metricas_disponiveis = {
  'accuracy_score': accuracy_score,
  'precision_score': precision_score,
  'recall_score': recall_score,
  'f1_score': f1_score,
  'roc_auc_score': roc_auc_score
}
