"""
Tests for the seed utility module.
"""
import pytest
import random
import os
import numpy as np
from app.utils.seed import seed_everything, get_seed, get_sklearn_random_state


class TestSeedEverything:
    """Test suite for seed_everything function."""

    def setup_method(self):
        """Reset global state before each test."""
        from app.utils import seed
        seed._global_seed = None

    def test_seed_returns_value(self):
        """seed_everything should return the seed value."""
        result = seed_everything(42)
        assert result == 42

    def test_seed_stores_globally(self):
        """seed_everything should store the seed globally."""
        seed_everything(42)
        assert get_seed() == 42

    def test_random_module_seeded(self):
        """seed_everything should seed Python's random module."""
        seed_everything(42)
        val1 = random.random()
        seed_everything(42)
        val2 = random.random()
        assert val1 == val2

    def test_numpy_seeded(self):
        """seed_everything should seed NumPy's random module."""
        seed_everything(42)
        val1 = np.random.rand()
        seed_everything(42)
        val2 = np.random.rand()
        assert val1 == val2

    def test_pythonhashseed_set(self):
        """seed_everything should set PYTHONHASHSEED environment variable."""
        seed_everything(42)
        assert os.environ.get('PYTHONHASHSEED') == '42'

    def test_different_seeds_different_results(self):
        """Different seeds should produce different random sequences."""
        seed_everything(42)
        val1 = random.random()
        seed_everything(123)
        val2 = random.random()
        assert val1 != val2

    def test_default_seed(self):
        """seed_everything should use 42 as default seed."""
        result = seed_everything()
        assert result == 42
        assert get_seed() == 42


class TestGetSeed:
    """Test suite for get_seed function."""

    def setup_method(self):
        """Reset global state before each test."""
        from app.utils import seed
        seed._global_seed = None

    def test_get_seed_returns_none_when_not_set(self):
        """get_seed should return None when no seed is set."""
        assert get_seed() is None

    def test_get_seed_returns_set_value(self):
        """get_seed should return the seed that was set."""
        seed_everything(42)
        assert get_seed() == 42


class TestGetSklearnRandomState:
    """Test suite for get_sklearn_random_state function."""

    def setup_method(self):
        """Reset global state before each test."""
        from app.utils import seed
        seed._global_seed = None

    def test_returns_none_when_not_set(self):
        """get_sklearn_random_state should return None when no seed is set."""
        assert get_sklearn_random_state() is None

    def test_returns_seed_when_set(self):
        """get_sklearn_random_state should return the seed that was set."""
        seed_everything(42)
        assert get_sklearn_random_state() == 42

    def test_can_be_used_as_random_state(self):
        """The returned value should work as sklearn's random_state parameter."""
        seed_everything(42)
        rs = get_sklearn_random_state()
        assert isinstance(rs, int)
        assert rs == 42
