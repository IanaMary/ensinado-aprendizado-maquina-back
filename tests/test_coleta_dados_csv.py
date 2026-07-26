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
    async def test_upload_csv_classe_unica_cai_para_divisao_simples(self, client, mock_db, auth_headers):
        """Classe com 1 exemplo: divide SEM estratificar em vez de recusar o upload.

        Antes isto era 400 (e antes disso, 500 do sklearn). Com estratificação ligada por
        padrão em classificação, recusar barraria dados reais de aluno por uma opção que ele
        nem escolheu — então caímos numa divisão simples e a resposta diz o que valeu.
        """
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
        assert response.status_code == 200
        assert response.json()["stratify"] is False   # não estratificou, e não mente sobre isso

    @pytest.mark.asyncio
    async def test_upload_csv_estratifica_quando_possivel(self, client, mock_db, auth_headers):
        csv_content = b"valor,classe\n1,A\n2,A\n3,B\n4,B\n"
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
        assert response.json()["stratify"] is True

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


class TestEstratificacaoPadrao:
    """Classificação estratifica por padrão: sem isso, uma categoria pouco frequente pode
    ficar fora do teste e a métrica engana o aluno."""

    def test_divide_estratificado_quando_pedido(self):
        import pandas as pd
        from app.coleta_dados.configuracao_treinamento import dividir_dataframe
        from app.schemas.schemas import ReDivisaoColetaRequest

        # 20 exemplos, 75% A / 25% B — sem estratificar, o teste pode sair sem nenhum B.
        df = pd.DataFrame({"x": range(20), "classe": ["A"] * 15 + ["B"] * 5})
        _treino, teste, estratificou = dividir_dataframe(
            df, ReDivisaoColetaRequest(test_size=0.4, shuffle=True, stratify=True, target="classe"))
        assert estratificou is True
        proporcao_b = (teste["classe"] == "B").mean()
        assert proporcao_b == pytest.approx(0.25, abs=0.01)   # mesma proporção do dataset

    def test_cai_para_divisao_simples_quando_impossivel(self):
        import pandas as pd
        from app.coleta_dados.configuracao_treinamento import dividir_dataframe
        from app.schemas.schemas import ReDivisaoColetaRequest

        df = pd.DataFrame({"x": range(4), "classe": ["A", "A", "A", "B"]})
        treino, teste, estratificou = dividir_dataframe(
            df, ReDivisaoColetaRequest(test_size=0.5, shuffle=True, stratify=True, target="classe"))
        assert estratificou is False
        assert len(treino) + len(teste) == 4      # dividiu mesmo assim

    def test_nao_estratifica_sem_embaralhar_nem_sem_alvo(self):
        import pandas as pd
        from app.coleta_dados.configuracao_treinamento import dividir_dataframe
        from app.schemas.schemas import ReDivisaoColetaRequest

        df = pd.DataFrame({"x": range(10), "classe": ["A"] * 5 + ["B"] * 5})
        # estratificar exige embaralhar (a divisão em ordem não pode reorganizar as classes)
        _t, _s, sem_shuffle = dividir_dataframe(
            df, ReDivisaoColetaRequest(test_size=0.4, shuffle=False, stratify=True, target="classe"))
        assert sem_shuffle is False
        # sem alvo não há o que estratificar
        _t, _s, sem_alvo = dividir_dataframe(
            df, ReDivisaoColetaRequest(test_size=0.4, shuffle=True, stratify=True, target=None))
        assert sem_alvo is False

    @pytest.mark.asyncio
    async def test_redivisao_estratifica_por_padrao_em_classificacao(self, client, mock_db, auth_headers):
        """O cliente não manda `stratify`; o servidor liga porque a config diz classificação."""
        import pandas as pd
        from unittest.mock import AsyncMock, MagicMock, patch
        from bson import ObjectId
        from app.funcoes_genericas.funcoes_genericas import df_para_base64

        df = pd.DataFrame({"x": range(20), "classe": ["A"] * 15 + ["B"] * 5})
        coleta_id = ObjectId()
        config_id = ObjectId()
        config_doc = {"_id": config_id, "id_coleta": coleta_id, "target": "classe",
                      "prever_categoria": True, "dados_rotulados": True, "atributos": {}}
        arquivo_doc = {"_id": coleta_id, "content_completo_base64": df_para_base64(df),
                       "arquivo_nome_treino": "d.xlsx", "colunas_detalhes": []}

        conf_m = MagicMock(find_one=AsyncMock(return_value=config_doc),
                           update_one=AsyncMock(return_value=MagicMock(modified_count=1)))
        arq_m = MagicMock(find_one=AsyncMock(return_value=arquivo_doc),
                          update_one=AsyncMock(return_value=MagicMock(modified_count=1)))
        with patch("app.coleta_dados.configuracao_treinamento.configuracoes_treinamento", conf_m), \
             patch("app.coleta_dados.configuracao_treinamento.arquivos", arq_m):
            r = await client.post(
                f"/configurar_treinamento/xlsx/{config_id}/redividir",
                headers=auth_headers,
                json={"test_size": 0.4, "shuffle": True, "target": "classe"},
            )
        assert r.status_code == 200
        assert r.json()["stratify"] is True
        assert r.json()["aviso_estratificacao"] is None
