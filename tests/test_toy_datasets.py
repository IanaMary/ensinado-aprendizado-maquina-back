"""
Tests for the toy datasets API endpoint.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np


@pytest.fixture
def mock_sklearn_data():
    """Mock sklearn dataset loading."""
    df = pd.DataFrame({
        'feature1': [1.0, 2.0, 3.0, 4.0, 5.0],
        'feature2': [0.1, 0.2, 0.3, 0.4, 0.5],
        'target': [0, 1, 0, 1, 0]
    })
    return df


class TestListToyDatasets:
    """Test suite for GET /toy_datasets/ endpoint."""

    def test_list_all_datasets(self, client):
        """Should return all available datasets."""
        response = client.get("/toy_datasets/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_dataset_has_required_fields(self, client):
        """Each dataset should have required fields."""
        response = client.get("/toy_datasets/")
        data = response.json()
        for ds in data:
            assert "nome" in ds
            assert "valor" in ds
            assert "descricao" in ds
            assert "fonte" in ds
            assert "tipo" in ds
            assert "n_amostras" in ds
            assert "n_features" in ds

    def test_filter_by_type(self, client):
        """Should filter datasets by type."""
        response = client.get("/toy_datasets/?tipo=classificacao")
        data = response.json()
        for ds in data:
            assert ds["tipo"] == "classificacao"

    def test_filter_by_fonte(self, client):
        """Should filter datasets by source."""
        response = client.get("/toy_datasets/?fonte=sklearn")
        data = response.json()
        for ds in data:
            assert ds["fonte"] == "sklearn"

    def test_iris_in_list(self, client):
        """Iris dataset should be in the list."""
        response = client.get("/toy_datasets/")
        data = response.json()
        iris = next((d for d in data if d["valor"] == "iris"), None)
        assert iris is not None
        assert iris["nome"] == "Iris"
        assert iris["tipo"] == "classificacao"


class TestLoadToyDataset:
    """Test suite for GET /toy_datasets/{name} endpoint."""

    def test_load_iris(self, client):
        """Should load Iris dataset successfully."""
        response = client.get("/toy_datasets/iris")
        assert response.status_code == 200
        data = response.json()
        assert data["nome_dataset"] == "Iris"
        assert data["fonte"] == "sklearn"
        assert data["prever_categoria"] is True
        assert data["dados_rotulados"] is True
        assert "colunas" in data
        assert "dados" in data
        assert "total_dados" in data

    def test_load_wine(self, client):
        """Should load Wine dataset successfully."""
        response = client.get("/toy_datasets/wine")
        assert response.status_code == 200
        data = response.json()
        assert data["nome_dataset"] == "Wine"

    def test_load_breast_cancer(self, client):
        """Should load Breast Cancer dataset successfully."""
        response = client.get("/toy_datasets/breast_cancer")
        assert response.status_code == 200
        data = response.json()
        assert data["nome_dataset"] == "Breast Cancer"
        assert data["prever_categoria"] is True

    def test_load_diabetes(self, client):
        """Should load Diabetes dataset (regression)."""
        response = client.get("/toy_datasets/diabetes")
        assert response.status_code == 200
        data = response.json()
        assert data["prever_categoria"] is False  # regression
        assert data["tipo_target"] == "number"

    def test_load_nonexistent_dataset(self, client):
        """Should return 404 for non-existent dataset."""
        response = client.get("/toy_datasets/nonexistent")
        assert response.status_code == 404

    def test_dataset_has_dados(self, client):
        """Loaded dataset should have data rows."""
        response = client.get("/toy_datasets/iris")
        data = response.json()
        assert len(data["dados"]) > 0
        assert data["total_dados"] > 0

    def test_dataset_has_colunas_detalhes(self, client):
        """Loaded dataset should have column details."""
        response = client.get("/toy_datasets/iris")
        data = response.json()
        assert "colunas_detalhes" in data
        assert len(data["colunas_detalhes"]) > 0
        for col in data["colunas_detalhes"]:
            assert "nome_coluna" in col
            assert "tipo_coluna" in col

    def test_with_seed_parameter(self, client):
        """Should accept seed parameter."""
        response = client.get("/toy_datasets/iris?seed=42")
        assert response.status_code == 200
        data = response.json()
        assert data["seed"] == 42

    def test_dataset_has_metadata(self, client):
        """Dataset should include educational metadata."""
        response = client.get("/toy_datasets/iris")
        data = response.json()
        assert "dificuldade" in data
        assert "descricao_target" in data
        assert "descricao_features" in data


class TestLoadUciDataset:
    """Test suite for UCI datasets."""

    def test_load_adult(self, client):
        """Should load Adult dataset from UCI."""
        response = client.get("/toy_datasets/adult")
        assert response.status_code == 200
        data = response.json()
        assert data["nome_dataset"] == "Adult (Census Income)"
        assert data["fonte"] == "uci"
        assert data["pre_split"] == "split"

    def test_adult_has_split_info(self, client):
        """Adult dataset should have train/test split info."""
        response = client.get("/toy_datasets/adult")
        data = response.json()
        assert data["n_treino"] == 32561
        assert data["n_teste"] == 16281


@pytest.fixture
def client():
    """Create a test client."""
    from app.main import app
    return TestClient(app)
