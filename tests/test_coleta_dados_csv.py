import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId
import io


class TestUploadCSV:
    @pytest.mark.asyncio
    async def test_upload_csv_sucesso(self, client, mock_db, auth_headers):
        csv_content = b"col1,col2\n1,2\n3,4"
        response = await client.post(
            "/coleta_dados/csv",
            headers=auth_headers,
            data={"tipo": "treino"},
            files={"file": ("dados.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "id_coleta" in data
        assert data["tipo"] == "treino"
        assert data["num_linhas"] == 2
        assert data["num_colunas"] == 2

    @pytest.mark.asyncio
    async def test_upload_csv_com_test_size(self, client, mock_db, auth_headers):
        csv_content = b"col1,col2\n1,2\n3,4"
        response = await client.post(
            "/coleta_dados/csv",
            headers=auth_headers,
            data={"tipo": "treino", "test_size": "0.2"},
            files={"file": ("dados.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_upload_csv_com_id_coleta(self, client, mock_db, auth_headers):
        csv_content = b"col1,col2\n1,2\n3,4"
        response = await client.post(
            "/coleta_dados/csv",
            headers=auth_headers,
            data={"tipo": "teste", "id_coleta": str(ObjectId())},
            files={"file": ("dados.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_upload_csv_arquivo_invalido(self, client, mock_db, auth_headers):
        response = await client.post(
            "/coleta_dados/csv",
            headers=auth_headers,
            data={"tipo": "treino"},
            files={"file": ("dados.txt", b"conteudo", "text/plain")},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_csv_sem_autenticacao(self, client):
        csv_content = b"col1,col2\n1,2"
        response = await client.post(
            "/coleta_dados/csv",
            data={"tipo": "treino"},
            files={"file": ("dados.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_csv_conteudo_preview(self, client, mock_db, auth_headers):
        csv_content = b"nome,idade\nAna,25\nBob,30\nCarlos,35"
        response = await client.post(
            "/coleta_dados/csv",
            headers=auth_headers,
            data={"tipo": "treino"},
            files={"file": ("dados.csv", csv_content, "text/csv")},
        )
        data = response.json()
        assert len(data["preview"]) == 3
        assert data["preview"][0]["nome"] == "Ana"
