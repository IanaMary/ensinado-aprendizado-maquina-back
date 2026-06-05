import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars!")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB", "test_db")

TEST_USER_ID = ObjectId()
TEST_USER_EMAIL = "test@test.com"


@pytest.fixture
def mock_user():
    return {
        "_id": TEST_USER_ID,
        "nome_usuario": "testuser",
        "email": TEST_USER_EMAIL,
        "role": "aluno",
        "instituicao_ensino": "Teste",
    }


@pytest.fixture
def mock_admin():
    return {
        "_id": ObjectId(),
        "nome_usuario": "admin",
        "email": "admin@test.com",
        "role": "admin",
        "instituicao_ensino": "Teste",
    }


@pytest.fixture
def valid_token():
    import jwt
    payload = {"sub": TEST_USER_EMAIL, "exp": 9999999999}
    return jwt.encode(payload, os.environ["SECRET_KEY"], algorithm="HS256")


@pytest.fixture
def expired_token():
    import jwt
    payload = {"sub": TEST_USER_EMAIL, "exp": 1}
    return jwt.encode(payload, os.environ["SECRET_KEY"], algorithm="HS256")


@pytest.fixture
def auth_headers(valid_token):
    return {"Authorization": f"Bearer {valid_token}"}


def _make_mock_collection():
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))
    col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    col.aggregate = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    col.count_documents = AsyncMock(return_value=0)
    return col


@pytest_asyncio.fixture
async def client():
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_db(mock_user):
    mock_user_col = _make_mock_collection()
    mock_arquivos = _make_mock_collection()
    mock_tutor = _make_mock_collection()
    mock_config = _make_mock_collection()
    mock_modelos = _make_mock_collection()
    mock_verif = _make_mock_collection()
    mock_pipeline = _make_mock_collection()

    # By default, return the test user for auth lookups
    mock_user_col.find_one = AsyncMock(return_value=mock_user)

    patches = [
        patch("app.database.colecao_usuario", mock_user_col),
        patch("app.database.arquivos", mock_arquivos),
        patch("app.database.tutor", mock_tutor),
        patch("app.database.configuracoes_treinamento", mock_config),
        patch("app.database.modelos_treinados", mock_modelos),
        patch("app.database.verificadores_professor", mock_verif),
        patch("app.routers.login.colecao_usuario", mock_user_col),
        patch("app.routers.usuarios.colecao_usuario", mock_user_col),
        patch("app.routers.usuarios.verificadores_professor", mock_verif),
        patch("app.security.colecao_usuario", mock_user_col),
        patch("app.routers.tutor.tutor", mock_tutor),
        patch("app.coleta_dados.coleta_dados_csv.arquivos", mock_arquivos),
        patch("app.coleta_dados.coleta_dados_xlxs.arquivos", mock_arquivos),
        patch("app.coleta_dados.coleta_dados_xlxs.configuracoes_treinamento", mock_config),
        patch("app.coleta_dados.configuracao_treinamento.arquivos", mock_arquivos),
        patch("app.coleta_dados.configuracao_treinamento.configuracoes_treinamento", mock_config),
        patch("app.metricas.metricas.modelos_treinados", mock_modelos),
        patch("app.metricas.metricas.arquivos", mock_arquivos),
        patch("app.database.pipelines", mock_pipeline),
        patch("app.routers.pipelines.pipelines", mock_pipeline),
    ]

    for p in patches:
        p.start()

    yield {
        "usuarios": mock_user_col,
        "arquivos": mock_arquivos,
        "tutor": mock_tutor,
        "configuracoes": mock_config,
        "modelos": mock_modelos,
        "verificadores": mock_verif,
        "pipelines": mock_pipeline,
    }

    for p in patches:
        p.stop()
