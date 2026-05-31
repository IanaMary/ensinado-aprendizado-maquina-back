import pytest
from httpx import AsyncClient
from main import app


@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_login_com_credenciais_corretas(client):
    response = await client.post("/login", json={
        "email": "test@example.com",
        "senha": "senha123"
    })
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_login_com_senha_incorreta(client):
    response = await client.post("/login", json={
        "email": "test@example.com",
        "senha": "senha_errada"
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_rota_protegida_sem_token(client):
    response = await client.get("/conf_pipeline/coleta_dados/todos")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_rota_protegida_com_token_invalido(client):
    response = await client.get(
        "/conf_pipeline/coleta_dados/todos",
        headers={"Authorization": "Bearer token_invalido"}
    )
    assert response.status_code == 401
