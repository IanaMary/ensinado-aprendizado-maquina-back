"""
Tests for the toy datasets API endpoint.
"""
import pytest

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


@pytest.mark.asyncio
class TestDatasetConteudo:
    """GET /toy_datasets/{name}/conteudo — bloco educacional, read-only."""

    async def test_conteudo_iris(self, client, mock_db):
        """Retorna o bloco conteudo sem auth e sem escrever no banco."""
        response = await client.get("/toy_datasets/iris/conteudo")
        assert response.status_code == 200
        data = response.json()
        assert data.get("titulo")
        assert data.get("descricao")
        # Não deve ter inserido nada em arquivos/configuracoes (rota read-only).
        mock_db["arquivos"].insert_one.assert_not_called()
        mock_db["configuracoes"].insert_one.assert_not_called()

    async def test_conteudo_404(self, client):
        response = await client.get("/toy_datasets/nao_existe/conteudo")
        assert response.status_code == 404

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

    async def test_gen_cachorro_regressao(self, client, mock_db, auth_headers):
        """Dataset lúdico de cachorro: regressão (altura -> peso)."""
        response = await client.get("/toy_datasets/gen_cachorro", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["fonte"] == "gerador"
        assert data["prever_categoria"] is False
        assert data["target"] == "target"
        assert "altura_cm" in data["colunas"] and "target" in data["colunas"]

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


@pytest.mark.asyncio
class TestCarregarDatasetPorFonte:
    """O endpoint que a tela usa para ABRIR o dataset tem de atender toda `fonte` do catálogo.

    O router tinha o seu próprio `if/elif` sobre `fonte`, separado do dos carregadores. Quando o
    Titanic virou `openml`, a lista do router não foi atualizada: `df` ficava `None` e o endpoint
    devolvia **500 "Erro ao carregar dataset"** — com o carregador novo funcionando e os testes de
    unidade verdes. Só um teste que passe PELO ENDPOINT pega isso.
    """

    async def test_toda_fonte_do_catalogo_e_atendida(self, client, mock_db, auth_headers, monkeypatch):
        import pandas as pd
        from app.models.dataset_config import get_all_datasets
        from app.models import dataset_loaders as dl

        # Um representante por fonte, para não baixar 25 datasets no teste.
        por_fonte = {}
        for nome, ds in get_all_datasets().items():
            por_fonte.setdefault(ds.fonte, nome)

        # Rede fora: cada carregador externo devolve um dataframe mínimo e coerente.
        monkeypatch.setattr(
            dl, "carregar_uci",
            lambda nome, ds=None: pd.DataFrame({"a": [1, 2, 3, 4], "target": [0, 1, 0, 1]}),
        )
        monkeypatch.setattr(
            dl, "carregar_openml",
            lambda nome: pd.DataFrame({"pclass": [1, 2, 3, 1], "survived": ["0", "1", "0", "1"]}),
        )

        assert "openml" in por_fonte, "o catálogo perdeu a fonte openml"
        for fonte, nome in sorted(por_fonte.items()):
            resp = await client.get(f"/toy_datasets/{nome}", headers=auth_headers)
            assert resp.status_code == 200, (
                f"fonte '{fonte}' (dataset '{nome}') respondeu {resp.status_code}: {resp.text[:200]}"
            )

    async def test_titanic_responde_e_nao_entrega_as_colunas_de_vazamento(self, client, mock_db, auth_headers, monkeypatch):
        import pandas as pd
        from app.models import dataset_loaders as dl

        # O que o `carregar_openml` real devolve: só as 7 features + alvo.
        monkeypatch.setattr(dl, "carregar_openml", lambda nome: pd.DataFrame({
            "pclass": [1, 3, 2, 1], "sex": ["female", "male", "female", "male"],
            "age": [29.0, 25.0, 40.0, 50.0], "sibsp": [0, 1, 0, 1], "parch": [0, 0, 2, 0],
            "fare": [211.3, 7.9, 26.0, 52.0], "embarked": ["S", "S", "C", "S"],
            "survived": ["1", "0", "1", "0"],
        }))

        resp = await client.get("/toy_datasets/titanic", headers=auth_headers)

        assert resp.status_code == 200, resp.text[:300]
        d = resp.json()
        colunas = d.get("colunas") or []
        nomes = [c["nome"] if isinstance(c, dict) else c for c in colunas]
        assert "survived" in nomes
        assert not ({"boat", "body", "name", "ticket", "cabin", "home.dest"} & set(nomes))

    async def test_dataset_com_celula_vazia_serializa(self, client, mock_db, auth_headers, monkeypatch):
        """Base do mundo real tem lacuna, e a resposta tem de sair como JSON válido.

        O Starlette serializa com `allow_nan=False`: um único NaN na amostra de `dados` derruba a
        resposta com **500**. Foi o segundo 500 do Titanic (`age` tem 263 nulos). O erro acontece
        DEPOIS do handler retornar — chamar a função direto funciona e só a requisição HTTP falha,
        o que faz o teste de unidade do handler passar batido.
        """
        import json
        import numpy as np
        import pandas as pd
        from app.models import dataset_loaders as dl

        monkeypatch.setattr(dl, "carregar_openml", lambda nome: pd.DataFrame({
            "pclass": [1, 3, 2, 1, 3, 2],
            "sex": ["female", "male", "female", "male", "female", "male"],
            "age": [29.0, np.nan, 40.0, np.nan, 22.0, 33.0],   # a lacuna
            "sibsp": [0, 1, 0, 1, 0, 1], "parch": [0, 0, 2, 0, 1, 0],
            "fare": [211.3, 7.9, np.nan, 52.0, 8.05, 26.0],
            "embarked": ["S", "S", "C", "S", None, "Q"],
            "survived": ["1", "0", "1", "0", "1", "0"],
        }))

        resp = await client.get("/toy_datasets/titanic", headers=auth_headers)

        assert resp.status_code == 200, resp.text[:300]
        # o corpo tem de ser JSON estrito: sem NaN/Infinity, que o `json` do Python aceitaria
        # de volta mas nenhum outro cliente aceita.
        json.loads(resp.text, parse_constant=lambda c: (_ for _ in ()).throw(
            AssertionError(f"resposta traz {c} literal, não é JSON válido")))
