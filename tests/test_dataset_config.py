"""
Tests for the dataset configuration model.
"""
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

    def test_uci_datasets_tem_carregador_configurado(self):
        """Todo dataset do grupo (baixados da internet) precisa de carregador configurado.

        O grupo era 100% UCI, mas o Titanic passou para o OpenML (`fetch_openml` do sklearn):
        o id 597 que ele usava **nao e o Titanic**, e o "Productivity Prediction of Garment
        Employees". Checar so a string `fonte` nao pegaria isso; o que pega e exigir que a
        `fonte` tenha um carregador de fato e que o id/spec exista nele.
        """
        from app.models.dataset_loaders import OPENML_SPECS, UCI_IDS

        registros = {"uci": UCI_IDS, "openml": OPENML_SPECS}
        for key, ds in UCI_DATASETS.items():
            assert ds.fonte in registros, f"{key} tem fonte sem carregador: {ds.fonte}"
            assert key in registros[ds.fonte], f"{key} nao esta no registro de {ds.fonte}"

    def test_titanic_vem_do_openml_com_as_13_colunas(self):
        """O Titanic e do OpenML e entrega o dataset INTEIRO — decisao do usuario (03/08).

        `boat` (numero do bote salva-vidas) e `body` (numero do corpo recuperado) sao vazamento:
        praticamente determinam a sobrevivencia. Ficam expostas de proposito, para que o aluno
        possa cair na armadilha e aprender o que e data leakage — e o texto do dataset tem de
        avisar, senao a armadilha nao ensina, so engana.
        """
        from app.models.dataset_loaders import OPENML_SPECS

        ds = UCI_DATASETS["titanic"]
        spec = OPENML_SPECS["titanic"]

        assert ds.fonte == "openml"
        assert ds.target == spec["target"] == "survived"
        # `colunas: None` = sem recorte, as 13 do OpenML
        assert spec.get("colunas") is None
        assert ds.n_features == 13
        # o aviso e parte do contrato: expor sem explicar seria so uma pegadinha
        texto = (ds.descricao_features + " " + ds.reflexao_final).lower()
        for termo in ("boat", "body", "vazamento"):
            assert termo in texto, f"o texto do dataset nao menciona '{termo}'"


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


class TestCacheDoOpenml:
    """O cache em disco tem de invalidar quando a FONTE do dataset muda."""

    def test_cache_do_uci_nao_e_lido_como_openml(self, tmp_path, monkeypatch):
        """Pickle antigo do UCI nao pode ser servido pelo carregador do OpenML.

        Foi o que aconteceu no primeiro deploy da troca do Titanic: o `carregar_uci` havia
        gravado `titanic.pkl` (dados de fabrica textil) e o `carregar_openml`, lendo o mesmo
        nome de arquivo, servia aquele pickle para sempre — a producao continuou entregando o
        dataset errado mesmo com o codigo novo no ar.
        """
        import pandas as pd
        from app.models import dataset_loaders as dl

        monkeypatch.setattr(dl, "CACHE_DIR", tmp_path)
        # O pickle "velho", do UCI: sem a coluna `survived`.
        antigo = pd.DataFrame({"date": ["1/1/2015"], "quarter": ["Quarter1"], "team": [8]})
        antigo.to_pickle(tmp_path / "titanic.pkl")

        chamou = {"openml": False}

        def fake_fetch_openml(nome, version=None, as_frame=None):
            chamou["openml"] = True
            import types
            data = pd.DataFrame({
                "pclass": [1], "sex": ["female"], "age": [29.0], "sibsp": [0],
                "parch": [0], "fare": [211.3], "embarked": ["S"],
                "boat": ["2"], "body": [None], "name": ["X"], "ticket": ["1"],
                "cabin": ["B5"], "home.dest": ["Y"],
            })
            return types.SimpleNamespace(data=data, target=pd.Series(["1"], name="survived"))

        monkeypatch.setattr("sklearn.datasets.fetch_openml", fake_fetch_openml)

        df = dl.carregar_openml("titanic")

        assert chamou["openml"], "leu o cache do UCI em vez de baixar do OpenML"
        assert "survived" in df.columns
        # veio do OpenML, nao do pickle textil
        assert "quarter" not in df.columns
        assert "pclass" in df.columns

    def test_cache_de_outro_recorte_nao_e_reaproveitado(self, tmp_path, monkeypatch):
        """Mudar o SPEC (recorte/versao/alvo) tem de gerar outro arquivo de cache.

        Ao trocar o recorte de 7 colunas para as 13, o pickle de 8 colunas ainda tinha o alvo:
        passava pela guarda e voltaria recortado. Em producao isso so nao aconteceu porque apaguei
        o arquivo na mao no deploy — o que ninguem vai lembrar de fazer na proxima vez.
        """
        import pandas as pd
        from app.models import dataset_loaders as dl

        monkeypatch.setattr(dl, "CACHE_DIR", tmp_path)
        # cache do recorte ANTIGO (7 features + alvo), gravado sob a assinatura daquele spec
        spec_antigo = {"nome": "titanic", "version": 1,
                       "colunas": ["pclass", "sex", "age", "sibsp", "parch", "fare", "embarked"],
                       "target": "survived"}
        pd.DataFrame({c: [1] for c in spec_antigo["colunas"] + ["survived"]}).to_pickle(
            dl._caminho_cache_openml("titanic", spec_antigo))
        # o spec vigente (colunas: None) tem outra assinatura, então o arquivo acima é ignorado
        assert dl._caminho_cache_openml("titanic", dl.OPENML_SPECS["titanic"]).name != \
            dl._caminho_cache_openml("titanic", spec_antigo).name

        chamou = {"openml": False}

        def fake_fetch_openml(nome, version=None, as_frame=None):
            chamou["openml"] = True
            import types
            data = pd.DataFrame({
                "pclass": [1], "sex": ["female"], "age": [29.0], "sibsp": [0],
                "parch": [0], "fare": [211.3], "embarked": ["S"],
            })
            return types.SimpleNamespace(data=data, target=pd.Series(["1"], name="survived"))

        monkeypatch.setattr("sklearn.datasets.fetch_openml", fake_fetch_openml)

        df = dl.carregar_openml("titanic")

        assert chamou["openml"]
        assert "survived" in df.columns
