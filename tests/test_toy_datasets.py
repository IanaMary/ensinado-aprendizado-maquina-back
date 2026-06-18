"""
Tests for the toy datasets API endpoint.
"""
import pytest
from bson import ObjectId

@pytest.mark.asyncio
class TestListToyDatasets:
    """Test suite for GET /toy_datasets/ endpoint."""

    async def test_list_all_datasets(self, client):
        """Should return all available datasets."""
        response = await client.get("/toy_datasets/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    async def test_dataset_has_required_fields(self, client):
        """Each dataset should have required fields."""
        response = await client.get("/toy_datasets/")
        data = response.json()
        for ds in data:
            assert "nome" in ds
            assert "valor" in ds
            assert "descricao" in ds
            assert "fonte" in ds
            assert "tipo" in ds
            assert "n_amostras" in ds
            assert "n_features" in ds

    async def test_filter_by_type(self, client):
        """Should filter datasets by type."""
        response = await client.get("/toy_datasets/?tipo=classificacao")
        data = response.json()
        for ds in data:
            assert ds["tipo"] == "classificacao"

    async def test_filter_by_fonte(self, client):
        """Should filter datasets by source."""
        response = await client.get("/toy_datasets/?fonte=sklearn")
        data = response.json()
        for ds in data:
            assert ds["fonte"] == "sklearn"

    async def test_iris_in_list(self, client):
        """Iris dataset should be in the list."""
        response = await client.get("/toy_datasets/")
        data = response.json()
        iris = next((d for d in data if d["valor"] == "iris"), None)
        assert iris is not None
        assert iris["nome"] == "Iris"
        assert iris["tipo"] == "classificacao"
        assert iris["missao"]["modelo_recomendado"] == "Árvore de Decisão"


@pytest.mark.asyncio
class TestLoadToyDataset:
    """Test suite for GET /toy_datasets/{name} endpoint."""

    async def test_load_iris(self, client, mock_db, auth_headers):
        """Should load Iris dataset successfully."""
        response = await client.get("/toy_datasets/iris", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["nome_dataset"] == "Iris"
        assert data["fonte"] == "sklearn"
        assert data["prever_categoria"] is True
        assert data["dados_rotulados"] is True
        assert "colunas" in data
        assert "dados" in data
        assert "total_dados" in data
        assert data["missao"]["pergunta"].startswith("Será que")

    async def test_load_wine(self, client, mock_db, auth_headers):
        """Should load Wine dataset successfully."""
        response = await client.get("/toy_datasets/wine", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["nome_dataset"] == "Wine"

    async def test_gerar_classificacao(self, client, mock_db, auth_headers):
        """Gerador de classificacao retorna dataset com target e parametros aplicados."""
        response = await client.get(
            "/toy_datasets/gen_classification?n_amostras=120&n_features=5&n_classes=3",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["fonte"] == "gerador"
        assert data["prever_categoria"] is True
        assert data["total_dados"] == 120
        assert "target" in data["colunas"]

    async def test_gerar_blobs_sem_target(self, client, mock_db, auth_headers):
        """Gerador de blobs e clustering: sem target, dados nao rotulados."""
        response = await client.get("/toy_datasets/gen_blobs?n_clusters=4", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["dados_rotulados"] is False
        assert "target" not in data["colunas"]

    async def test_gen_sorvete_regressao(self, client, mock_db, auth_headers):
        """Dataset lúdico de sorvete: regressão com target contínuo."""
        response = await client.get("/toy_datasets/gen_sorvete", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["fonte"] == "gerador"
        assert data["prever_categoria"] is False
        assert data["target"] == "target"
        assert "temperatura" in data["colunas"] and "target" in data["colunas"]

    async def test_gen_cardume_clustering(self, client, mock_db, auth_headers):
        """Dataset lúdico de cardume: agrupamento sem target."""
        response = await client.get("/toy_datasets/gen_cardume?n_clusters=3", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["dados_rotulados"] is False
        assert "target" not in data["colunas"]
        assert "velocidade" in data["colunas"]

    async def test_load_breast_cancer(self, client, mock_db, auth_headers):
        """Should load Breast Cancer dataset successfully."""
        response = await client.get("/toy_datasets/breast_cancer", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["nome_dataset"] == "Breast Cancer"
        assert data["prever_categoria"] is True

    async def test_load_diabetes(self, client, mock_db, auth_headers):
        """Should load Diabetes dataset (regression)."""
        response = await client.get("/toy_datasets/diabetes", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["prever_categoria"] is False  # regression
        assert data["tipo_target"] == "Número"

    async def test_load_nonexistent_dataset(self, client, mock_db, auth_headers):
        """Should return 404 for non-existent dataset."""
        response = await client.get("/toy_datasets/nonexistent", headers=auth_headers)
        assert response.status_code == 404

    async def test_dataset_has_dados(self, client, mock_db, auth_headers):
        """Loaded dataset should have data rows."""
        response = await client.get("/toy_datasets/iris", headers=auth_headers)
        data = response.json()
        assert len(data["dados"]) > 0
        assert data["total_dados"] > 0

    async def test_dataset_has_colunas_detalhes(self, client, mock_db, auth_headers):
        """Loaded dataset should have column details."""
        response = await client.get("/toy_datasets/iris", headers=auth_headers)
        data = response.json()
        assert "colunas_detalhes" in data
        assert len(data["colunas_detalhes"]) > 0
        for col in data["colunas_detalhes"]:
            assert "nome_coluna" in col
            assert "tipo_coluna" in col

    async def test_with_seed_parameter(self, client, mock_db, auth_headers):
        """Should accept seed parameter."""
        response = await client.get("/toy_datasets/iris?seed=42", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["seed"] == 42

    async def test_dataset_has_metadata(self, client, mock_db, auth_headers):
        """Dataset should include educational metadata."""
        response = await client.get("/toy_datasets/iris", headers=auth_headers)
        data = response.json()
        assert "dificuldade" in data
        assert "descricao_target" in data
        assert "descricao_features" in data


@pytest.mark.asyncio
class TestLoadUciDataset:
    """Test suite for UCI datasets."""

    async def test_load_adult(self, client, mock_db, auth_headers):
        """Should load Adult dataset from UCI."""
        response = await client.get("/toy_datasets/adult", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["nome_dataset"] == "Adult (Census Income)"
        assert data["fonte"] == "uci"

    async def test_adult_has_split_info(self, client, mock_db, auth_headers):
        """Adult dataset should have train/test split info."""
        response = await client.get("/toy_datasets/adult", headers=auth_headers)
        data = response.json()
        assert "n_treino" in data
        assert "n_teste" in data
