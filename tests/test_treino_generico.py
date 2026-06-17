"""Treino data-driven: rota genérica treina um MODELO NOVO via modelo_doc.execucao.

Garante o desbloqueio principal — um modelo cadastrado pelo admin (sem router
dedicado) treina lendo execucao.{modulo,classe}, sem 404.
"""
import base64
import io

import pandas as pd
import pytest
from bson import ObjectId
from unittest.mock import AsyncMock


def _df():
    return pd.DataFrame({
        "f1": [1, 2, 3, 4, 5, 6, 7, 8],
        "f2": [8, 7, 6, 5, 4, 3, 2, 1],
        "target": [0, 0, 0, 0, 1, 1, 1, 1],
    })


def _mock_treino(mock_db, modelo_doc):
    buffer = io.BytesIO()
    _df().to_excel(buffer, index=False, engine="openpyxl")
    b64 = base64.b64encode(buffer.getvalue()).decode()
    coleta_id, config_id = ObjectId(), ObjectId()
    mock_db["configuracoes"].find_one = AsyncMock(return_value={
        "_id": config_id, "id_coleta": str(coleta_id), "target": "target",
        "atributos": {"f1": True, "f2": True}, "tipo_target": "Número",
    })
    mock_db["arquivos"].find_one = AsyncMock(return_value={
        "_id": coleta_id, "content_treino_base64": b64, "content_teste_base64": b64,
    })
    mock_db["modelos"].find_one = AsyncMock(return_value=modelo_doc)
    return coleta_id, config_id


@pytest.mark.asyncio
async def test_rota_generica_treina_modelo_novo_via_execucao(client, mock_db, auth_headers):
    """extra_trees (sem router dedicado) treina pela rota genérica lendo execucao."""
    modelo_doc = {
        "_id": ObjectId(),
        "valor": "extra_trees",
        "label": "Extra Trees",
        "execucao": {
            "modulo": "sklearn.ensemble",
            "classe": "ExtraTreesClassifier",
            "hiperparametros": [{"nome": "n_estimators", "default": 10}],
        },
    }
    coleta_id, config_id = _mock_treino(mock_db, modelo_doc)
    resp = await client.post(
        "/classificador/treinamento/extra_trees",
        headers=auth_headers,
        json={
            "arquivo_id": str(coleta_id), "tipo_arquivo": "excel",
            "configuracao_id": str(config_id), "modelo_id": str(ObjectId()),
            "hiperparametros": {},
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["modelo"] == "extra_trees"
    assert "ExtraTreesClassifier" in data["modelo_treinado"]
    # default do execucao aplicado
    assert str(data["hiperparametros"].get("n_estimators")) == "10"


@pytest.mark.asyncio
async def test_rota_generica_modelo_inexistente_404(client, mock_db, auth_headers):
    mock_db["modelos"].find_one = AsyncMock(return_value=None)
    resp = await client.post(
        "/classificador/treinamento/nao_existe",
        headers=auth_headers,
        json={"arquivo_id": str(ObjectId()), "tipo_arquivo": "excel",
              "configuracao_id": str(ObjectId()), "modelo_id": str(ObjectId())},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_treino_recusa_modulo_proibido_no_execucao(client, mock_db, auth_headers):
    """Defesa em profundidade: execucao com módulo fora da allowlist é barrada (400)."""
    modelo_doc = {
        "_id": ObjectId(), "valor": "malicioso", "label": "X",
        "execucao": {"modulo": "os", "classe": "system", "hiperparametros": []},
    }
    coleta_id, config_id = _mock_treino(mock_db, modelo_doc)
    resp = await client.post(
        "/classificador/treinamento/malicioso",
        headers=auth_headers,
        json={"arquivo_id": str(coleta_id), "tipo_arquivo": "excel",
              "configuracao_id": str(config_id), "modelo_id": str(ObjectId())},
    )
    assert resp.status_code == 400
    assert "permitida" in resp.json()["detail"].lower()
