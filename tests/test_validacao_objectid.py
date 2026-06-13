import pytest
from unittest.mock import AsyncMock
from bson import ObjectId
from fastapi import HTTPException

from app.funcoes_genericas.validacao import validar_object_id


class TestValidarObjectId:
    def test_id_valido(self):
        oid = ObjectId()
        assert validar_object_id(str(oid), "campo") == oid

    def test_id_vazio(self):
        with pytest.raises(HTTPException) as exc:
            validar_object_id("", "campo")
        assert exc.value.status_code == 400

    def test_id_none(self):
        with pytest.raises(HTTPException) as exc:
            validar_object_id(None, "campo")
        assert exc.value.status_code == 400

    def test_id_curto(self):
        with pytest.raises(HTTPException) as exc:
            validar_object_id("a" * 23, "campo")
        assert exc.value.status_code == 400

    def test_id_nao_hex(self):
        with pytest.raises(HTTPException) as exc:
            validar_object_id("z" * 24, "campo")
        assert exc.value.status_code == 400

    def test_mensagem_inclui_nome_campo(self):
        with pytest.raises(HTTPException) as exc:
            validar_object_id("invalido", "id_modelo")
        assert "id_modelo" in exc.value.detail


class TestValidacaoEndpoints:
    @pytest.mark.asyncio
    async def test_avaliar_modelos_id_invalido_retorna_400(self, client, mock_db, auth_headers):
        """Regressão: id de modelo não-hex deve retornar 400 sem consultar o banco."""
        mock_db["modelos"].find_one = AsyncMock(return_value=None)
        response = await client.post(
            "/classificador/avaliar_modelos",
            headers=auth_headers,
            json={
                "modelos": [{"label": "KNN", "id": "not-hex-objectid"}],
                "metricas": [{"label": "Acurácia", "valor": "accuracy_score"}],
            },
        )
        assert response.status_code == 400
        mock_db["modelos"].find_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_upload_csv_teste_id_coleta_invalido_retorna_400(self, client, mock_db, auth_headers):
        """Regressão: id_coleta inválido no upload de teste retornava 500 (InvalidId)."""
        response = await client.post(
            "/coleta_dados/csv",
            headers=auth_headers,
            data={"tipo": "teste", "id_coleta": "garbage-id"},
            files={"file": ("dados.csv", b"col1,col2\n1,2", "text/csv")},
        )
        assert response.status_code == 400
        mock_db["arquivos"].update_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_treinamento_arquivo_id_invalido_retorna_400(self, client, mock_db, auth_headers):
        response = await client.post(
            "/classificador/treinamento/knn",
            headers=auth_headers,
            json={
                "arquivo_id": "invalido",
                "tipo_arquivo": "excel",
                "configuracao_id": str(ObjectId()),
                "modelo_id": str(ObjectId()),
            },
        )
        assert response.status_code == 400
        mock_db["arquivos"].find_one.assert_not_called()
