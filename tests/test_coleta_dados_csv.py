import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId
import io
import base64


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
        # 2 data rows
        assert data["num_linhas_total"] == 2
        assert data["num_colunas"] == 2

    @pytest.mark.asyncio
    async def test_upload_csv_com_test_size(self, client, mock_db, auth_headers):
        csv_content = b"col1,col2\n1,2\n3,4\n5,6\n7,8" # 4 rows
        response = await client.post(
            "/coleta_dados/csv",
            headers=auth_headers,
            data={"tipo": "treino", "test_size": 0.5},
            files={"file": ("dados.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["num_linhas_treino"] == 2
        assert data["num_linhas_teste"] == 2

    @pytest.mark.asyncio
    async def test_upload_csv_com_id_coleta(self, client, mock_db, auth_headers):
        csv_content = b"col1,col2\n1,2\n3,4"
        coleta_id = ObjectId()
        # Mock the find_one to return a valid doc for the NameError-prone section
        mock_db["arquivos"].find_one = AsyncMock(return_value={
            "_id": coleta_id,
            "content_treino_base64": base64.b64encode(csv_content).decode(),
        })
        response = await client.post(
            "/coleta_dados/csv",
            headers=auth_headers,
            data={"tipo": "teste", "id_coleta": str(coleta_id)},
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
        csv_content = b"nome,idade\nAna,25\nBob,30\nCarlos,35\nDiego,40\nElisa,45" # 5 rows
        response = await client.post(
            "/coleta_dados/csv",
            headers=auth_headers,
            data={"tipo": "treino"},
            files={"file": ("dados.csv", csv_content, "text/csv")},
        )
        data = response.json()
        # 5 rows, 0.2 split -> 4 train, 1 test
        assert len(data["preview_treino"]) == 4
        nomes_no_preview = [row["nome"] for row in data["preview_treino"]]
        assert "Ana" in nomes_no_preview
