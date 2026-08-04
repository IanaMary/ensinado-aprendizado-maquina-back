"""
Tests for the seed utility module.
"""
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


class TestRandomStateEfetivo:
    """`random_state_efetivo` nunca devolve None — é o que faz a tela e o script exportado darem o
    MESMO número.

    Antes, o treino só recebia `random_state` quando havia semente global, e em produção não há: cada
    treino de modelo estocástico (árvore, random forest, MLP, k-means) saía diferente, enquanto o
    script exportado fixa 42. O aluno comparava os dois e concluía que o código baixado estava
    errado. Medido antes da correção: 5 execuções do script entre 0.6159 e 0.6280, contra 0.6402 na
    tela.
    """

    def setup_method(self):
        from app.utils import seed
        seed._global_seed = None

    def teardown_method(self):
        from app.utils import seed
        seed._global_seed = None

    def test_sem_semente_global_usa_a_mesma_do_script_exportado(self):
        from app.utils.seed import random_state_efetivo, SEMENTE_PADRAO, get_sklearn_random_state

        # o caso de produção: nenhuma semente configurada
        assert get_sklearn_random_state() is None
        assert random_state_efetivo() == SEMENTE_PADRAO == 42

    def test_semente_global_tem_precedencia(self):
        """Escolher a semente (`?seed=N` ao carregar o dataset) muda os DOIS lados juntos — é assim
        que se mostra a variância de propósito, sem que os números deixem de casar."""
        from app.utils.seed import seed_everything, random_state_efetivo

        seed_everything(7)
        assert random_state_efetivo() == 7

    def test_nunca_devolve_none(self):
        """A garantia que o treino depende: `hiperparametros["random_state"]` não pode receber None,
        senão o estimador volta a ser não determinístico."""
        from app.utils.seed import random_state_efetivo, seed_everything
        from app.utils import seed

        assert random_state_efetivo() is not None
        seed_everything(0)                      # 0 é semente válida e NÃO deve virar o default
        assert random_state_efetivo() == 0
        seed._global_seed = None
        assert random_state_efetivo() is not None


class TestTreinoRecebeSementeSempre:
    """O treino precisa injetar `random_state` mesmo sem semente global — a ponta que o aluno vê."""

    def test_o_treino_usa_random_state_efetivo(self):
        """Guarda de regressão: se alguém voltar a condicionar a injeção a `is not None`, o número da
        tela descola do script outra vez, sem erro nenhum aparecendo."""
        import inspect
        from app.routers import treinamento_base

        fonte = inspect.getsource(treinamento_base)
        assert "random_state_efetivo()" in fonte
        # o padrão antigo era `if random_state is not None: hiperparametros[...] = random_state`
        assert "if random_state is not None" not in fonte
