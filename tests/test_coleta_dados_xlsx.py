import base64
from io import BytesIO

import pandas as pd
import pytest
from bson import ObjectId
from unittest.mock import AsyncMock


def _xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class TestUploadXLSX:
    @pytest.mark.asyncio
    async def test_upload_xlsx_treino_sucesso(self, client, mock_db, auth_headers):
        conteudo = _xlsx_bytes(pd.DataFrame({"col1": [1, 3, 5, 7], "col2": [2, 4, 6, 8]}))
        response = await client.post(
            "/coleta_dados/salvar_xlxs",
            headers=auth_headers,
            data={"tipo": "treino", "test_size": 0.5},
            files={"file": ("dados.xlsx", conteudo, XLSX_MIME)},
        )
        assert response.status_code == 200
        data = response.json()
        assert "id_coleta" in data
        assert data["num_linhas_treino"] == 2
        assert data["num_linhas_teste"] == 2

    @pytest.mark.asyncio
    async def test_upload_xlsx_teste_aceita_campo_file(self, client, mock_db, auth_headers):
        """Regressão: o frontend envia o arquivo de teste no campo 'file' (mesmo campo do CSV);
        o endpoint respondia 400 'file_teste obrigatório'."""
        df = pd.DataFrame({"col1": [1, 3], "col2": [2, 4]})
        conteudo = _xlsx_bytes(df)
        coleta_id = ObjectId()
        mock_db["arquivos"].find_one = AsyncMock(return_value={
            "_id": coleta_id,
            "content_completo_base64": base64.b64encode(conteudo).decode(),
            "arquivo_nome_treino": "treino.xlsx",
        })
        response = await client.post(
            "/coleta_dados/salvar_xlxs",
            headers=auth_headers,
            data={"tipo": "teste", "id_coleta": str(coleta_id)},
            files={"file": ("teste.xlsx", conteudo, XLSX_MIME)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tipo"] == "teste"
        assert data["arquivo_nome_teste"] == "teste.xlsx"

    @pytest.mark.asyncio
    async def test_upload_xlsx_teste_sem_arquivo_retorna_400(self, client, mock_db, auth_headers):
        response = await client.post(
            "/coleta_dados/salvar_xlxs",
            headers=auth_headers,
            data={"tipo": "teste", "id_coleta": str(ObjectId())},
        )
        assert response.status_code == 400
        assert "file_teste" in response.json()["detail"]
