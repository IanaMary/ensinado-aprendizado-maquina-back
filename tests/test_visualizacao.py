import base64
import pytest
from unittest.mock import AsyncMock, patch
from bson import ObjectId
import pandas as pd


def _csv_b64(df: pd.DataFrame) -> str:
    return base64.b64encode(df.to_csv(index=False).encode("utf-8")).decode("utf-8")


def _make_arquivo(df: pd.DataFrame, arquivo_id: ObjectId) -> dict:
    return {"_id": arquivo_id, "content_treino_base64": _csv_b64(df)}


def _make_config(atributos: list, target: str, config_id: ObjectId) -> dict:
    return {
        "_id": config_id,
        "atributos": {col: True for col in atributos},
        "target": target,
    }


@pytest.fixture
def iris_df():
    return pd.DataFrame({
        "sepal_length": [5.1, 4.9, 4.7, 6.4, 6.9, 5.5, 4.9, 6.7, 5.8, 7.1],
        "sepal_width":  [3.5, 3.0, 3.2, 3.2, 3.1, 2.3, 2.5, 3.1, 2.7, 3.0],
        "petal_length": [1.4, 1.4, 1.3, 4.5, 4.9, 4.0, 4.5, 5.6, 5.1, 5.9],
        "petal_width":  [0.2, 0.2, 0.2, 1.5, 1.5, 1.3, 1.7, 2.4, 1.9, 2.1],
        "species":      ["setosa", "setosa", "setosa", "versicolor", "versicolor",
                         "versicolor", "versicolor", "virginica", "virginica", "virginica"],
    })


class TestPairplot:
    @pytest.mark.asyncio
    async def test_pairplot_retorna_imagem_png(self, client, mock_db, auth_headers, iris_df):
        arquivo_id = ObjectId()
        config_id = ObjectId()
        atributos = ["sepal_length", "sepal_width", "petal_length", "petal_width"]

        with patch("app.routers.visualizacao.arquivos") as mock_arq, \
             patch("app.routers.visualizacao.configuracoes_treinamento") as mock_cfg:
            mock_arq.find_one = AsyncMock(return_value=_make_arquivo(iris_df, arquivo_id))
            mock_cfg.find_one = AsyncMock(return_value=_make_config(atributos, "species", config_id))

            response = await client.post(
                "/visualizacao/pairplot",
                headers=auth_headers,
                json={"arquivo_id": str(arquivo_id), "configuracao_id": str(config_id)},
            )

        assert response.status_code == 200
        data = response.json()
        assert "imagem" in data
        assert "colunas" in data
        assert "total_amostras" in data
        decoded = base64.b64decode(data["imagem"])
        assert decoded[:4] == b"\x89PNG"
        assert set(atributos).issubset(set(data["colunas"]))

    @pytest.mark.asyncio
    async def test_pairplot_usa_hue_explicito(self, client, mock_db, auth_headers, iris_df):
        arquivo_id = ObjectId()
        config_id = ObjectId()
        atributos = ["sepal_length", "sepal_width", "petal_length"]

        with patch("app.routers.visualizacao.arquivos") as mock_arq, \
             patch("app.routers.visualizacao.configuracoes_treinamento") as mock_cfg:
            mock_arq.find_one = AsyncMock(return_value=_make_arquivo(iris_df, arquivo_id))
            mock_cfg.find_one = AsyncMock(return_value=_make_config(atributos, "species", config_id))

            response = await client.post(
                "/visualizacao/pairplot",
                headers=auth_headers,
                json={
                    "arquivo_id": str(arquivo_id),
                    "configuracao_id": str(config_id),
                    "colunas": atributos,
                    "hue": "species",
                },
            )

        assert response.status_code == 200
        assert response.json()["hue"] == "species"

    @pytest.mark.asyncio
    async def test_pairplot_colunas_personalizadas(self, client, mock_db, auth_headers, iris_df):
        arquivo_id = ObjectId()
        config_id = ObjectId()
        atributos = ["sepal_length", "sepal_width", "petal_length", "petal_width"]

        with patch("app.routers.visualizacao.arquivos") as mock_arq, \
             patch("app.routers.visualizacao.configuracoes_treinamento") as mock_cfg:
            mock_arq.find_one = AsyncMock(return_value=_make_arquivo(iris_df, arquivo_id))
            mock_cfg.find_one = AsyncMock(return_value=_make_config(atributos, "species", config_id))

            response = await client.post(
                "/visualizacao/pairplot",
                headers=auth_headers,
                json={
                    "arquivo_id": str(arquivo_id),
                    "configuracao_id": str(config_id),
                    "colunas": ["sepal_length", "sepal_width"],
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["colunas"] == ["sepal_length", "sepal_width"]
        assert data["total_amostras"] == len(iris_df)

    @pytest.mark.asyncio
    async def test_pairplot_arquivo_nao_encontrado(self, client, mock_db, auth_headers):
        with patch("app.routers.visualizacao.arquivos") as mock_arq, \
             patch("app.routers.visualizacao.configuracoes_treinamento") as mock_cfg:
            mock_arq.find_one = AsyncMock(return_value=None)
            mock_cfg.find_one = AsyncMock(return_value=None)

            response = await client.post(
                "/visualizacao/pairplot",
                headers=auth_headers,
                json={"arquivo_id": str(ObjectId()), "configuracao_id": str(ObjectId())},
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_pairplot_configuracao_nao_encontrada(self, client, mock_db, auth_headers, iris_df):
        arquivo_id = ObjectId()

        with patch("app.routers.visualizacao.arquivos") as mock_arq, \
             patch("app.routers.visualizacao.configuracoes_treinamento") as mock_cfg:
            mock_arq.find_one = AsyncMock(return_value=_make_arquivo(iris_df, arquivo_id))
            mock_cfg.find_one = AsyncMock(return_value=None)

            response = await client.post(
                "/visualizacao/pairplot",
                headers=auth_headers,
                json={"arquivo_id": str(arquivo_id), "configuracao_id": str(ObjectId())},
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_pairplot_colunas_invalidas_retorna_400(self, client, mock_db, auth_headers, iris_df):
        arquivo_id = ObjectId()
        config_id = ObjectId()

        with patch("app.routers.visualizacao.arquivos") as mock_arq, \
             patch("app.routers.visualizacao.configuracoes_treinamento") as mock_cfg:
            mock_arq.find_one = AsyncMock(return_value=_make_arquivo(iris_df, arquivo_id))
            mock_cfg.find_one = AsyncMock(return_value=_make_config([], "", config_id))

            response = await client.post(
                "/visualizacao/pairplot",
                headers=auth_headers,
                json={
                    "arquivo_id": str(arquivo_id),
                    "configuracao_id": str(config_id),
                    "colunas": ["coluna_que_nao_existe"],
                },
            )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_pairplot_objectid_invalido_retorna_400(self, client, mock_db, auth_headers):
        # validar_object_id raises HTTPException(400), not Pydantic 422
        response = await client.post(
            "/visualizacao/pairplot",
            headers=auth_headers,
            json={"arquivo_id": "nao-e-um-objectid", "configuracao_id": "tambem-nao"},
        )
        assert response.status_code == 400
