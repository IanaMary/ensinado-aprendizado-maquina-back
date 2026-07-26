"""Divisão treino/teste: estratificação, vazamento e consistência da redivisão.

Três níveis, como pedido:
- **unidade**: `dividir_dataframe` (disjunção, proporções, fallback, casos degenerados);
- **regressão**: o vazamento dos datasets de exemplo (treino recebia o dataframe inteiro e
  o teste a cauda) não pode voltar;
- **integração**: carregar dataset → redividir duas vezes sem o dataset encolher, com o
  aviso e o valor efetivo chegando ao cliente.
"""
import base64
import io

import pandas as pd
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from app.coleta_dados.configuracao_treinamento import (
    AVISO_SEM_ESTRATIFICACAO, aviso_estratificacao, dividir_dataframe,
)
from app.funcoes_genericas.funcoes_genericas import df_para_base64
from app.schemas.schemas import ReDivisaoColetaRequest


def _df(n_a=15, n_b=5, coluna="classe"):
    return pd.DataFrame({"x": range(n_a + n_b), coluna: ["A"] * n_a + ["B"] * n_b})


def _ler(b64: str) -> pd.DataFrame:
    return pd.read_excel(io.BytesIO(base64.b64decode(b64)))


def _pedido(**kw):
    base = {"test_size": 0.25, "shuffle": True, "stratify": True, "target": "classe"}
    return ReDivisaoColetaRequest(**{**base, **kw})


# ------------------------------------------------------------------ unidade
class TestDividirDataframe:
    def test_treino_e_teste_sao_disjuntos_e_somam_o_total(self):
        df = _df()
        treino, teste, _ = dividir_dataframe(df, _pedido())
        assert len(treino) + len(teste) == len(df)
        assert set(treino["x"]).isdisjoint(set(teste["x"]))          # nada de vazamento
        assert set(treino["x"]) | set(teste["x"]) == set(df["x"])    # nem linha perdida

    def test_estratificado_preserva_a_proporcao_das_categorias(self):
        df = _df(n_a=60, n_b=20)          # 75% / 25%
        treino, teste, estratificou = dividir_dataframe(df, _pedido(test_size=0.4))
        assert estratificou is True
        for parte in (treino, teste):
            assert (parte["classe"] == "B").mean() == pytest.approx(0.25, abs=0.02)

    def test_sem_estratificar_a_proporcao_pode_fugir(self):
        """Contraste do teste acima: é por isso que classificação estratifica por padrão."""
        df = _df(n_a=60, n_b=20)
        _t, teste, estratificou = dividir_dataframe(df, _pedido(test_size=0.4, stratify=False))
        assert estratificou is False
        assert len(teste) == 32

    def test_categoria_com_um_exemplo_cai_para_divisao_simples(self):
        df = pd.DataFrame({"x": range(4), "classe": ["A", "A", "A", "B"]})
        treino, teste, estratificou = dividir_dataframe(df, _pedido(test_size=0.5))
        assert estratificou is False
        assert len(treino) + len(teste) == 4
        assert set(treino["x"]).isdisjoint(set(teste["x"]))

    def test_nao_estratifica_sem_embaralhar(self):
        _t, _s, estratificou = dividir_dataframe(_df(), _pedido(shuffle=False))
        assert estratificou is False

    def test_nao_estratifica_sem_alvo_ou_com_alvo_inexistente(self):
        assert dividir_dataframe(_df(), _pedido(target=None))[2] is False
        assert dividir_dataframe(_df(), _pedido(target="nao_existe"))[2] is False

    def test_parametro_estratificar_sobrepoe_o_pedido_do_cliente(self):
        # é assim que o servidor aplica o padrão da tarefa sem o cliente mandar nada
        _t, _s, ligado = dividir_dataframe(_df(), _pedido(stratify=False), estratificar=True)
        assert ligado is True
        _t, _s, desligado = dividir_dataframe(_df(), _pedido(stratify=True), estratificar=False)
        assert desligado is False

    def test_divisao_impossivel_ainda_e_erro_claro(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            dividir_dataframe(pd.DataFrame({"x": []}), _pedido(target=None))
        assert exc.value.status_code == 400

    def test_aviso_so_quando_pediu_e_nao_deu(self):
        assert aviso_estratificacao(True, False) == AVISO_SEM_ESTRATIFICACAO
        assert aviso_estratificacao(True, True) is None
        assert aviso_estratificacao(False, False) is None


# ------------------------------------------------------------------ regressão do vazamento
class TestVazamentoDatasetExemplo:
    """Antes: `content_treino` = dataframe INTEIRO e `content_teste` = cauda de 25% — o teste
    era subconjunto do treino, e num dataset ordenado por classe a cauda tinha só uma
    categoria (era a origem das acurácias 1.00 no iris)."""

    @pytest.mark.asyncio
    async def test_iris_treino_e_teste_disjuntos_e_estratificados(self, client, mock_db, auth_headers):
        arq_m = MagicMock(insert_one=AsyncMock(return_value=MagicMock(inserted_id=ObjectId())))
        cfg_m = MagicMock(insert_one=AsyncMock(return_value=MagicMock(inserted_id=ObjectId())))
        with patch("app.routers.toy_datasets.arquivos", arq_m), \
             patch("app.routers.toy_datasets.configuracoes_treinamento", cfg_m):
            r = await client.get("/toy_datasets/iris", headers=auth_headers)
        assert r.status_code == 200

        doc = arq_m.insert_one.await_args[0][0]
        completo, treino, teste = (_ler(doc["content_completo_base64"]),
                                   _ler(doc["content_treino_base64"]),
                                   _ler(doc["content_teste_base64"]))

        assert len(completo) == 150
        assert len(treino) + len(teste) == 150          # antes: 150 + 37
        assert len(treino) < len(completo)               # antes o treino era o dataframe todo
        # disjunção por conteúdo (não há índice depois do to_excel/read_excel)
        assert len(pd.merge(treino, teste, how="inner")) == 0
        # proporção de classes preservada nos dois lados (estratificado)
        for parte in (treino, teste):
            assert parte["target"].value_counts(normalize=True).round(2).to_dict() == {
                "setosa": pytest.approx(0.33, abs=0.02),
                "versicolor": pytest.approx(0.33, abs=0.02),
                "virginica": pytest.approx(0.33, abs=0.02),
            }
        assert r.json()["stratify"] is True
        assert r.json()["aviso_estratificacao"] is None

    @pytest.mark.asyncio
    async def test_guarda_o_conteudo_completo_para_a_redivisao(self, client, mock_db, auth_headers):
        """Sem `content_completo_base64`, a redivisão releria o treino já dividido e o
        dataset encolheria a cada mudança de proporção."""
        arq_m = MagicMock(insert_one=AsyncMock(return_value=MagicMock(inserted_id=ObjectId())))
        cfg_m = MagicMock(insert_one=AsyncMock(return_value=MagicMock(inserted_id=ObjectId())))
        with patch("app.routers.toy_datasets.arquivos", arq_m), \
             patch("app.routers.toy_datasets.configuracoes_treinamento", cfg_m):
            await client.get("/toy_datasets/iris", headers=auth_headers)

        doc = arq_m.insert_one.await_args[0][0]
        assert len(_ler(doc["content_completo_base64"])) == 150
        cfg = cfg_m.insert_one.await_args[0][0]
        assert cfg["shuffle"] is True and cfg["stratify"] is True

    @pytest.mark.asyncio
    async def test_regressao_nao_estratifica_e_nao_vaza(self, client, mock_db, auth_headers):
        """Dataset de regressão não estratifica (não há categorias), mas a divisão tem de ser
        disjunta do mesmo jeito."""
        arq_m = MagicMock(insert_one=AsyncMock(return_value=MagicMock(inserted_id=ObjectId())))
        cfg_m = MagicMock(insert_one=AsyncMock(return_value=MagicMock(inserted_id=ObjectId())))
        with patch("app.routers.toy_datasets.arquivos", arq_m), \
             patch("app.routers.toy_datasets.configuracoes_treinamento", cfg_m):
            r = await client.get("/toy_datasets/diabetes", headers=auth_headers)
        if r.status_code == 404:
            pytest.skip("dataset de regressão indisponível neste ambiente")
        doc = arq_m.insert_one.await_args[0][0]
        treino, teste = _ler(doc["content_treino_base64"]), _ler(doc["content_teste_base64"])
        assert len(pd.merge(treino, teste, how="inner")) == 0
        assert r.json()["stratify"] is False


# ------------------------------------------------------------------ integração
class TestIntegracaoRedivisao:
    def _mocks(self, df, *, prever_categoria=True):
        coleta_id, config_id = ObjectId(), ObjectId()
        arquivo = {"_id": coleta_id, "content_completo_base64": df_para_base64(df),
                   "arquivo_nome_treino": "d.xlsx", "colunas_detalhes": []}
        config = {"_id": config_id, "id_coleta": coleta_id, "target": "classe",
                  "prever_categoria": prever_categoria, "dados_rotulados": True, "atributos": {}}
        gravado = {}

        async def _update_arquivo(_filtro, update):
            gravado.update(update["$set"])
            return MagicMock(modified_count=1)

        arq_m = MagicMock(find_one=AsyncMock(return_value=arquivo), update_one=AsyncMock(side_effect=_update_arquivo))
        cfg_m = MagicMock(find_one=AsyncMock(return_value=config),
                          update_one=AsyncMock(return_value=MagicMock(modified_count=1)))
        return config_id, arq_m, cfg_m, gravado

    @pytest.mark.asyncio
    async def test_redividir_duas_vezes_nao_encolhe_o_dataset(self, client, mock_db, auth_headers):
        df = _df(n_a=60, n_b=20)
        config_id, arq_m, cfg_m, gravado = self._mocks(df)
        with patch("app.coleta_dados.configuracao_treinamento.arquivos", arq_m), \
             patch("app.coleta_dados.configuracao_treinamento.configuracoes_treinamento", cfg_m):
            for proporcao in (0.2, 0.4):
                r = await client.post(
                    f"/configurar_treinamento/xlsx/{config_id}/redividir",
                    headers=auth_headers,
                    json={"test_size": proporcao, "shuffle": True, "target": "classe"},
                )
                assert r.status_code == 200
                corpo = r.json()
                assert corpo["num_linhas_total"] == 80
                assert corpo["num_linhas_treino"] + corpo["num_linhas_teste"] == 80
                assert corpo["stratify"] is True          # padrão da classificação
            # o que foi gravado continua somando o total (não releu um treino já dividido)
            assert len(_ler(gravado["content_treino_base64"])) + len(_ler(gravado["content_teste_base64"])) == 80

    @pytest.mark.asyncio
    async def test_avisa_e_desliga_quando_nao_da_para_estratificar(self, client, mock_db, auth_headers):
        df = pd.DataFrame({"x": range(6), "classe": ["A", "A", "A", "A", "A", "B"]})
        config_id, arq_m, cfg_m, _ = self._mocks(df)
        with patch("app.coleta_dados.configuracao_treinamento.arquivos", arq_m), \
             patch("app.coleta_dados.configuracao_treinamento.configuracoes_treinamento", cfg_m):
            r = await client.post(
                f"/configurar_treinamento/xlsx/{config_id}/redividir",
                headers=auth_headers,
                json={"test_size": 0.5, "shuffle": True, "target": "classe"},
            )
        corpo = r.json()
        assert corpo["stratify"] is False                       # a tela desmarca a caixa
        assert corpo["aviso_estratificacao"] == AVISO_SEM_ESTRATIFICACAO   # e explica
        # grava o efetivo, não o pedido: o código exportado não pode dizer que estratificou
        assert cfg_m.update_one.await_args[0][1]["$set"]["stratify"] is False

    @pytest.mark.asyncio
    async def test_regressao_nao_estratifica_por_padrao(self, client, mock_db, auth_headers):
        df = pd.DataFrame({"x": range(20), "classe": [i * 1.5 for i in range(20)]})
        config_id, arq_m, cfg_m, _ = self._mocks(df, prever_categoria=False)
        with patch("app.coleta_dados.configuracao_treinamento.arquivos", arq_m), \
             patch("app.coleta_dados.configuracao_treinamento.configuracoes_treinamento", cfg_m):
            r = await client.post(
                f"/configurar_treinamento/xlsx/{config_id}/redividir",
                headers=auth_headers,
                json={"test_size": 0.3, "shuffle": True, "target": "classe"},
            )
        assert r.json()["stratify"] is False
        assert r.json()["aviso_estratificacao"] is None    # não pediu, não avisa

    @pytest.mark.asyncio
    async def test_escolha_explicita_do_aluno_prevalece(self, client, mock_db, auth_headers):
        config_id, arq_m, cfg_m, _ = self._mocks(_df())
        with patch("app.coleta_dados.configuracao_treinamento.arquivos", arq_m), \
             patch("app.coleta_dados.configuracao_treinamento.configuracoes_treinamento", cfg_m):
            r = await client.post(
                f"/configurar_treinamento/xlsx/{config_id}/redividir",
                headers=auth_headers,
                json={"test_size": 0.25, "shuffle": True, "target": "classe", "stratify": False},
            )
        assert r.json()["stratify"] is False   # classificação, mas o aluno desmarcou
