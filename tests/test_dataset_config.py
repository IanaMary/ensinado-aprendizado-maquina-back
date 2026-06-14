"""
Tests for the dataset configuration model.
"""
import pytest
from app.models.dataset_config import (
    DatasetConfig, DatasetType, PreSplitStatus,
    get_all_datasets, get_dataset_config, TOY_DATASETS, UCI_DATASETS, GENERATED_DATASETS
)


class TestDatasetConfig:
    """Test suite for DatasetConfig dataclass."""

    def test_create_basic_config(self):
        """Should create a basic DatasetConfig with required fields."""
        ds = DatasetConfig(
            id="test",
            nome="Test Dataset",
            descricao="A test dataset",
            fonte="test",
            tipo=DatasetType.CLASSIFICATION,
            n_amostras=100,
            n_features=5,
            target="target"
        )
        assert ds.id == "test"
        assert ds.nome == "Test Dataset"
        assert ds.tipo == DatasetType.CLASSIFICATION

    def test_default_values(self):
        """Should have correct default values."""
        ds = DatasetConfig(
            id="test",
            nome="Test",
            descricao="Test",
            fonte="test",
            tipo=DatasetType.CLASSIFICATION,
            n_amostras=100,
            n_features=5
        )
        assert ds.pre_split == PreSplitStatus.SINGLE
        assert ds.dificuldade == "iniciante"
        assert ds.target is None
        assert ds.colunas == []

    def test_to_dict(self):
        """to_dict should return a dictionary with all fields."""
        ds = DatasetConfig(
            id="iris",
            nome="Iris",
            descricao="Iris dataset",
            fonte="sklearn",
            tipo=DatasetType.CLASSIFICATION,
            n_amostras=150,
            n_features=4,
            target="species",
            dificuldade="iniciante"
        )
        result = ds.to_dict()
        assert result["id"] == "iris"
        assert result["nome"] == "Iris"
        assert result["tipo"] == "classificacao"
        assert result["n_amostras"] == 150
        assert result["dificuldade"] == "iniciante"

    def test_enum_values(self):
        """Enum values should serialize correctly."""
        assert DatasetType.CLASSIFICATION.value == "classificacao"
        assert DatasetType.REGRESSION.value == "regressao"
        assert DatasetType.CLUSTERING.value == "agrupamento"
        assert PreSplitStatus.SPLIT.value == "split"
        assert PreSplitStatus.SINGLE.value == "single"


class TestToyDatasets:
    """Test suite for toy dataset configurations."""

    def test_iris_config(self):
        """Iris dataset should have correct configuration."""
        iris = TOY_DATASETS["iris"]
        assert iris.id == "iris"
        assert iris.nome == "Iris"
        assert iris.tipo == DatasetType.CLASSIFICATION
        assert iris.n_amostras == 150
        assert iris.n_features == 4
        assert iris.target == "species"
        assert iris.fonte == "sklearn"

    def test_wine_config(self):
        """Wine dataset should have correct configuration."""
        wine = TOY_DATASETS["wine"]
        assert wine.tipo == DatasetType.CLASSIFICATION
        assert wine.n_amostras == 178
        assert wine.n_features == 13

    def test_diabetes_is_regression(self):
        """Diabetes dataset should be a regression dataset."""
        diabetes = TOY_DATASETS["diabetes"]
        assert diabetes.tipo == DatasetType.REGRESSION

    def test_california_housing_is_regression(self):
        """California Housing should be a regression dataset."""
        housing = TOY_DATASETS["california_housing"]
        assert housing.tipo == DatasetType.REGRESSION
        assert housing.n_amostras == 20640

    def test_all_toy_datasets_have_required_fields(self):
        """All toy datasets should have required fields."""
        for key, ds in TOY_DATASETS.items():
            assert ds.id is not None, f"{key} missing id"
            assert ds.nome is not None, f"{key} missing nome"
            assert ds.descricao is not None, f"{key} missing descricao"
            assert ds.tipo is not None, f"{key} missing tipo"
            assert ds.n_amostras > 0, f"{key} has invalid n_amostras"
            assert ds.n_features > 0, f"{key} has invalid n_features"


class TestUciDatasets:
    """Test suite for UCI dataset configurations."""

    def test_adult_config(self):
        """Adult dataset should have correct configuration."""
        adult = UCI_DATASETS["adult"]
        assert adult.tipo == DatasetType.CLASSIFICATION
        assert adult.pre_split == PreSplitStatus.SPLIT
        assert adult.n_treino == 32561
        assert adult.n_teste == 16281

    def test_abalone_is_regression(self):
        """Abalone dataset should be a regression dataset."""
        abalone = UCI_DATASETS["abalone"]
        assert abalone.tipo == DatasetType.REGRESSION

    def test_uci_datasets_have_correct_fonte(self):
        """All UCI datasets should have fonte='uci'."""
        for key, ds in UCI_DATASETS.items():
            assert ds.fonte == "uci", f"{key} has wrong fonte: {ds.fonte}"


class TestGetAllDatasets:
    """Test suite for get_all_datasets function."""

    def test_returns_all_datasets(self):
        """Should return both toy and UCI datasets."""
        all_ds = get_all_datasets()
        assert len(all_ds) == len(TOY_DATASETS) + len(UCI_DATASETS) + len(GENERATED_DATASETS)

    def test_includes_toy_datasets(self):
        """Should include all toy datasets."""
        all_ds = get_all_datasets()
        for key in TOY_DATASETS:
            assert key in all_ds

    def test_includes_uci_datasets(self):
        """Should include all UCI datasets."""
        all_ds = get_all_datasets()
        for key in UCI_DATASETS:
            assert key in all_ds


class TestGetDatasetConfig:
    """Test suite for get_dataset_config function."""

    def test_returns_existing_dataset(self):
        """Should return config for existing dataset."""
        ds = get_dataset_config("iris")
        assert ds is not None
        assert ds.nome == "Iris"

    def test_returns_none_for_missing(self):
        """Should return None for non-existent dataset."""
        ds = get_dataset_config("nonexistent")
        assert ds is None

    def test_returns_uci_dataset(self):
        """Should return UCI dataset config."""
        ds = get_dataset_config("adult")
        assert ds is not None
        assert ds.fonte == "uci"
