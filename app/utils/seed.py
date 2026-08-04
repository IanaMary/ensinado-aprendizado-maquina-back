"""
Seed utility for reproducible ML experiments.

Sets the same random seed across all environments:
- Python random module
- NumPy
- scikit-learn (via random_state parameter)
- Environment variables
"""

import random
import os
import numpy as np
from typing import Optional


# Global seed storage
_global_seed: Optional[int] = None


def seed_everything(seed: int = 42) -> int:
    """
    Set random seed across all environments for reproducibility.
    
    Args:
        seed: The seed value to use (default: 42)
    
    Returns:
        The seed value that was set
    """
    global _global_seed
    _global_seed = seed
    
    # Python random
    random.seed(seed)
    
    # Environment variable for hash randomization
    os.environ['PYTHONHASHSEED'] = str(seed)
    
    # NumPy
    np.random.seed(seed)
    
    # scikit-learn uses numpy's random state internally
    # When we pass random_state=seed to sklearn estimators,
    # they will use np.random.RandomState(seed) internally
    
    return seed


def get_seed() -> Optional[int]:
    """Return the current global seed, or None if not set."""
    return _global_seed


def get_sklearn_random_state() -> Optional[int]:
    """
    Return the seed for use as sklearn's random_state parameter.
    Returns None if no seed is set (sklearn default behavior).
    """
    return _global_seed


# Semente usada quando não há semente global configurada. É o MESMO valor que o script exportado
# emite (`script-generator.service.ts`, `rsArg`), e é isso que faz a tela e o código baixado darem
# o mesmo número.
SEMENTE_PADRAO = 42


def random_state_efetivo() -> int:
    """`random_state` a usar no estimador — nunca `None`.

    Antes, o treino só recebia `random_state` se houvesse semente global, e em produção não há: cada
    treino de modelo estocástico (árvore, random forest, MLP, k-means) saía com um número diferente,
    e o script exportado — que fixa 42 — dava outro. O aluno comparava os dois e concluía que o
    código baixado estava errado. Medido antes da correção: 5 execuções do script entre 0.6159 e
    0.6280, contra 0.6402 na tela.

    Fixar aqui **não** esconde a variância: quem quiser mostrá-la troca a semente de propósito
    (`GET /toy_datasets/{id}?seed=N` chama `seed_everything`), e aí os dois lados mudam juntos.
    """
    return _global_seed if _global_seed is not None else SEMENTE_PADRAO
