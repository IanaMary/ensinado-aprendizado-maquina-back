from unittest.mock import AsyncMock, MagicMock, patch


async def test_treinar_knn():
    with patch("app.routers.treinamento_base.arquivos") as mock_arquivos, \
         patch("app.routers.treinamento_base.configuracoes_treinamento") as mock_config, \
         patch("app.routers.treinamento_base.opcoes_modelos") as mock_opcoes, \
         patch("app.routers.treinamento_base.modelos_treinados") as mock_modelos, \
         patch("app.routers.treinamento_base.pd") as mock_pd:

        mock_arquivos.find_one = AsyncMock(return_value={
            "content_treino_base64": "Zm9vYmFy",
            "content_teste_base64": "Zm9vYmFy"
        })

        mock_config.find_one = AsyncMock(return_value={
            "atributos": {"feature1": True, "feature2": True},
            "target": "target"
        })

        mock_opcoes.find_one = AsyncMock(return_value={
            "hiperparametros": [],
            "valor": "knn",
            "label": "KNN"
        })

        mock_modelos.insert_one = AsyncMock(return_value=MagicMock(inserted_id="123"))

        mock_pd.read_csv.return_value = MagicMock()
        mock_pd.read_excel.return_value = MagicMock()
        mock_pd.read_json.return_value = MagicMock()

        from app.routers.treinamento_base import treinar_modelo_generico

        class FakeModel:
            def __init__(self, **kwargs):
                pass
            def fit(self, x, y):
                pass
            @property
            def classes_(self):
                return [1, 2]
            def get_params(self, deep=True):
                return {}

        result = await treinar_modelo_generico(
            MagicMock(tipo_arquivo="csv", arquivo_id="abc", configuracao_id="def", modelo_id="ghi"),
            "KNN",
            FakeModel
        )

        assert "status" in result
        assert "KNN" in result["nome_modelo"]


async def test_treinar_arvore_decisao():
    with patch("app.routers.treinamento_base.arquivos") as mock_arquivos, \
         patch("app.routers.treinamento_base.configuracoes_treinamento") as mock_config, \
         patch("app.routers.treinamento_base.opcoes_modelos") as mock_opcoes, \
         patch("app.routers.treinamento_base.modelos_treinados") as mock_modelos, \
         patch("app.routers.treinamento_base.pd") as mock_pd:

        mock_arquivos.find_one = AsyncMock(return_value={
            "content_treino_base64": "Zm9vYmFy",
            "content_teste_base64": "Zm9vYmFy"
        })

        mock_config.find_one = AsyncMock(return_value={
            "atributos": {"feature1": True},
            "target": "target"
        })

        mock_opcoes.find_one = AsyncMock(return_value={
            "hiperparametros": [],
            "valor": "arvore_decisao",
            "label": "Árvore de Decisão"
        })

        mock_modelos.insert_one = AsyncMock(return_value=MagicMock(inserted_id="456"))

        mock_pd.read_csv.return_value = MagicMock()

        from app.routers.treinamento_base import treinar_modelo_generico

        class FakeModel:
            def __init__(self, **kwargs):
                pass
            def fit(self, x, y):
                pass
            @property
            def classes_(self):
                return [0, 1]
            def get_params(self, deep=True):
                return {}

        result = await treinar_modelo_generico(
            MagicMock(tipo_arquivo="csv", arquivo_id="abc", configuracao_id="def", modelo_id="ghi"),
            "Árvore de Decisão",
            FakeModel
        )

        assert "status" in result
        assert "Árvore de Decisão" in result["nome_modelo"]
