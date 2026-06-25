import pytest
from unittest.mock import AsyncMock
from bson import ObjectId
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
    async def test_upload_tsv_sucesso(self, client, mock_db, auth_headers):
        tsv_content = b"col1\tcol2\n1\t2\n3\t4"
        response = await client.post(
            "/coleta_dados/csv",
            headers=auth_headers,
            data={"tipo": "treino"},
            files={"file": ("dados.tsv", tsv_content, "text/tab-separated-values")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["num_linhas_total"] == 2
        assert data["num_colunas"] == 2
        assert data["colunas"] == ["col1", "col2"]

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
    async def test_upload_csv_com_shuffle_e_estratificacao(self, client, mock_db, auth_headers):
        csv_content = (
            b"valor,classe\n"
            b"1,A\n2,A\n3,A\n4,A\n"
            b"5,B\n6,B\n7,B\n8,B\n"
        )
        response = await client.post(
            "/coleta_dados/csv",
            headers=auth_headers,
            data={
                "tipo": "treino",
                "test_size": 0.5,
                "shuffle": "true",
                "stratify": "true",
                "stratify_column": "classe",
            },
            files={"file": ("dados.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["num_linhas_treino"] == 4
        assert data["num_linhas_teste"] == 4
        assert sorted(row["classe"] for row in data["preview_treino"]) == ["A", "A", "B", "B"]
        assert sorted(row["classe"] for row in data["preview_teste"]) == ["A", "A", "B", "B"]

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
    async def test_upload_csv_test_size_invalido_retorna_400(self, client, mock_db, auth_headers):
        """Regressão: test_size fora de (0, 1) deve falhar com 400, não estourar no sklearn."""
        csv_content = b"col1,col2\n1,2\n3,4"
        response = await client.post(
            "/coleta_dados/csv",
            headers=auth_headers,
            data={"tipo": "treino", "test_size": 1.5},
            files={"file": ("dados.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 400
        assert "test_size" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_csv_estratificacao_classe_unica_retorna_400(self, client, mock_db, auth_headers):
        """Regressão: estratificar com classe de 1 exemplo retornava 500 do sklearn."""
        csv_content = b"valor,classe\n1,A\n2,A\n3,A\n4,B\n"
        response = await client.post(
            "/coleta_dados/csv",
            headers=auth_headers,
            data={
                "tipo": "treino",
                "test_size": 0.5,
                "shuffle": "true",
                "stratify": "true",
                "stratify_column": "classe",
            },
            files={"file": ("dados.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 400
        assert "estratificar" in response.json()["detail"]

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
