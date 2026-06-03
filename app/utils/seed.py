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
