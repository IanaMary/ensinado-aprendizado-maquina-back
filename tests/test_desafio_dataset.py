"""Desafio de montagem que nasce de um dataset de exemplo.

Cobre as três garantias novas:
1. o perfil da base é lido do dataframe REAL (não de caixas marcadas à mão);
2. a tarefa do desafio é derivada do dataset pelo SERVIDOR (o cliente não decide);
3. o tabuleiro sempre permite uma solução — inclusive quando o professor curou poucas peças,
   exigiu pré-processamento sem que a base peça, ou vetou tudo o que servia.
"""
import pandas as pd
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from app.desafios import base_dados
from app.desafios.base_dados import inspecionar_dados, perfil_do_dataset, tarefa_do_dataset
from app.desafios.sorteio import montar_tabuleiro, papeis

from tests.test_desafio_montagem import PECAS, GABARITO, AsyncCursor, _catalogo_mock


# ------------------------------------------------------------------ perfil da base
class TestInspecaoDaBase:
    def test_base_limpa_e_homogenea_nao_exige_nada(self):
        df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 3.0, 4.0], "target": [0, 1, 0]})
        assert inspecionar_dados(df, alvo="target") == {
            "faltantes": False, "texto": False, "escalas_diferentes": False,
        }

    def test_valor_faltando_liga_faltantes(self):
        df = pd.DataFrame({"a": [1.0, None, 3.0], "target": [0, 1, 0]})
        assert inspecionar_dados(df, alvo="target")["faltantes"] is True

    def test_coluna_de_texto_liga_texto(self):
        df = pd.DataFrame({"cidade": ["Pelotas", "Bagé", "Rio Grande"], "target": [0, 1, 0]})
        assert inspecionar_dados(df, alvo="target")["texto"] is True

    def test_alvo_de_texto_nao_conta_como_coluna_de_texto(self):
        """O alvo categórico é o normal em classificação: quem exige encoder são as ENTRADAS."""
        df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "especie": ["gato", "cao", "gato"]})
        assert inspecionar_dados(df, alvo="especie")["texto"] is False

    def test_amplitudes_muito_diferentes_ligam_escalas(self):
        df = pd.DataFrame({"prob": [0.1, 0.5, 0.9], "renda": [1000.0, 50000.0, 90000.0]})
        assert inspecionar_dados(df, alvo=None)["escalas_diferentes"] is True

    def test_amplitudes_parecidas_nao_ligam_escalas(self):
        df = pd.DataFrame({"a": [1.0, 5.0, 9.0], "b": [2.0, 6.0, 11.0]})
        assert inspecionar_dados(df, alvo=None)["escalas_diferentes"] is False

    def test_dataframe_vazio_ou_ausente_cai_no_conservador(self):
        assert inspecionar_dados(None) == {
            "faltantes": False, "texto": False, "escalas_diferentes": False,
        }
        assert inspecionar_dados(pd.DataFrame())["faltantes"] is False


class TestPerfilDoDataset:
    def setup_method(self):
        base_dados._cache.clear()

    def test_iris_traz_tarefa_textos_e_base_limpa(self):
        perfil = perfil_do_dataset("iris")
        assert perfil["tarefa"] == "classificacao"
        assert perfil["nome"] == "Iris"
        assert "espécie" in perfil["enunciado_sugerido"] or "especie" in perfil["enunciado_sugerido"]
        # iris não tem valores faltando nem coluna de texto
        assert perfil["dados"]["faltantes"] is False
        assert perfil["dados"]["texto"] is False

    def test_dataset_de_regressao_derivado(self):
        assert perfil_do_dataset("gen_sorvete")["tarefa"] == "regressao"
        assert perfil_do_dataset("gen_cardume")["tarefa"] == "agrupamento"

    def test_dataset_inexistente(self):
        assert perfil_do_dataset("nao-existe") is None
        assert tarefa_do_dataset("nao-existe") is None

    def test_falha_ao_carregar_nao_quebra_o_perfil(self):
        with patch.object(base_dados, "carregar_dataframe", side_effect=RuntimeError("sem rede")):
            perfil = perfil_do_dataset("titanic")
        assert perfil["tarefa"] == "classificacao"
        assert perfil["dados"] == {"faltantes": False, "texto": False, "escalas_diferentes": False}

    def test_cache_evita_recarregar(self):
        with patch.object(base_dados, "carregar_dataframe",
                          return_value=pd.DataFrame({"a": [1.0, 2.0], "target": [0, 1]})) as carga:
            perfil_do_dataset("wine")
            perfil_do_dataset("wine")
        assert carga.call_count == 1


# ------------------------------------------------------------------ garantia do mínimo
def _gab(**extra):
    return {**GABARITO, **extra}


async def _tabuleiro(gabarito, tentativa=1):
    atividade = {"_id": ObjectId(), "gabarito": gabarito}
    return await montar_tabuleiro(atividade, "aluno-1", tentativa, pecas_catalogo=PECAS)


class TestMinimoGarantido:
    @pytest.mark.asyncio
    async def test_professor_curou_so_um_modelo_e_ainda_ha_solucao(self):
        gab = _gab(sortear_pecas=False, fixar=["knn"])
        t = await _tabuleiro(gab)
        lanes = {p["lane"] for p in t["pecas"] if p["papel"] == "util"}
        assert {"coleta", "modelo", "metrica"} <= lanes
        # métrica útil compatível com classificação
        metricas = [p for p in t["pecas"] if p["papel"] == "util" and p["lane"] == "metrica"]
        assert any(PECAS[p["valor"]]["grupo"] == "classificacao" for p in metricas)

    @pytest.mark.asyncio
    async def test_modo_curado_nao_sorteia_extras(self):
        gab = _gab(sortear_pecas=False, fixar=["arquivo", "arvore_decisao", "accuracy_score"])
        t = await _tabuleiro(gab)
        uteis = sorted(p["valor"] for p in t["pecas"] if p["papel"] == "util")
        assert uteis == ["accuracy_score", "arquivo", "arvore_decisao"]

    @pytest.mark.asyncio
    async def test_exigir_pre_processamento_sem_flags_ganha_peca(self):
        """Regressão: a caixa 'Exigir a etapa de pré-processamento' criava um tabuleiro em que
        `estrutura-minima` era impossível — a lane exigida não recebia peça nenhuma."""
        gab = _gab(exige=["coleta", "pre_processamento", "modelo", "metrica"])
        t = await _tabuleiro(gab)
        assert any(p["lane"] == "pre_processamento" and p["papel"] == "util" for p in t["pecas"])

    @pytest.mark.asyncio
    async def test_vetar_todas_as_metricas_nao_torna_o_desafio_impossivel(self):
        gab = _gab(vetar=["accuracy_score", "r2_score", "silhouette_score"])
        t = await _tabuleiro(gab)
        metricas = [p for p in t["pecas"] if p["lane"] == "metrica" and p["papel"] == "util"]
        assert metricas, "o mínimo vence o veto: sem métrica não há solução"
        assert PECAS[metricas[0]["valor"]]["grupo"] == "classificacao"

    @pytest.mark.asyncio
    async def test_base_com_faltantes_garante_imputacao(self):
        gab = _gab(sortear_pecas=False, fixar=["arquivo", "arvore_decisao", "accuracy_score"],
                   dados={"faltantes": True, "texto": False, "escalas_diferentes": False})
        t = await _tabuleiro(gab)
        familias = {PECAS[p["valor"]].get("familia") for p in t["pecas"]
                    if p["lane"] == "pre_processamento" and p["papel"] == "util"}
        assert "imputacao" in familias

    @pytest.mark.asyncio
    async def test_determinismo_preservado(self):
        gab = _gab(sortear_pecas=False, fixar=["knn"])
        atividade = {"_id": ObjectId(), "gabarito": gab}
        a = await montar_tabuleiro(atividade, "aluno-1", 1, pecas_catalogo=PECAS)
        b = await montar_tabuleiro(atividade, "aluno-1", 1, pecas_catalogo=PECAS)
        assert [p["valor"] for p in a["pecas"]] == [p["valor"] for p in b["pecas"]]
        assert papeis(a) == papeis(b)


# ------------------------------------------------------------------ criação da atividade
class TestCriacaoComDataset:
    @pytest.mark.asyncio
    async def test_servidor_deriva_a_tarefa_do_dataset(self, client, mock_db, auth_headers):
        prof = {"_id": ObjectId(), "email": "p@x.com", "nome_usuario": "Prof", "role": "professor"}
        mock_db["usuarios"].find_one = AsyncMock(return_value=prof)
        turma = {"_id": ObjectId(), "professor_id": str(prof["_id"]), "alunos": []}
        inserido = MagicMock(inserted_id=ObjectId())
        ativ_m = MagicMock(insert_one=AsyncMock(return_value=inserido))
        with patch("app.routers.turmas.turmas", MagicMock(find_one=AsyncMock(return_value=turma))), \
             patch("app.routers.turmas.atividades", ativ_m):
            r = await client.post(
                f"/turmas/{turma['_id']}/atividades",
                headers=auth_headers,
                json={"titulo": "Sorvetes", "tipo": "montagem",
                      # cliente manda a tarefa ERRADA de propósito: o dataset é de regressão
                      "gabarito": {"dataset": "gen_sorvete", "tarefa": "classificacao"}},
            )
        assert r.status_code == 200
        assert r.json()["gabarito"]["tarefa"] == "regressao"
        assert r.json()["gabarito"]["dataset"] == "gen_sorvete"

    @pytest.mark.asyncio
    async def test_dataset_inexistente_recusado(self, client, mock_db, auth_headers):
        prof = {"_id": ObjectId(), "email": "p@x.com", "nome_usuario": "Prof", "role": "professor"}
        mock_db["usuarios"].find_one = AsyncMock(return_value=prof)
        turma = {"_id": ObjectId(), "professor_id": str(prof["_id"]), "alunos": []}
        with patch("app.routers.turmas.turmas", MagicMock(find_one=AsyncMock(return_value=turma))), \
             patch("app.routers.turmas.atividades", MagicMock(insert_one=AsyncMock())):
            r = await client.post(
                f"/turmas/{turma['_id']}/atividades",
                headers=auth_headers,
                json={"titulo": "X", "tipo": "montagem", "gabarito": {"dataset": "nao-existe"}},
            )
        assert r.status_code == 400
        assert "não existe" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_tabuleiro_informa_a_base_ao_aluno(self, client, mock_db, auth_headers, mock_user):
        turma = {"_id": ObjectId(), "professor_id": str(ObjectId()),
                 "alunos": [str(mock_user["_id"])]}
        atividade = {"_id": ObjectId(), "turma_id": str(turma["_id"]), "tipo": "montagem",
                     "titulo": "Prever espécie",
                     "gabarito": {**GABARITO, "dataset": "iris"}}
        cat = _catalogo_mock()
        subm = MagicMock(count_documents=AsyncMock(return_value=0),
                         find=MagicMock(return_value=AsyncCursor([])))
        with patch("app.routers.turmas.turmas", MagicMock(find_one=AsyncMock(return_value=turma))), \
             patch("app.routers.turmas.atividades", MagicMock(find_one=AsyncMock(return_value=atividade))), \
             patch("app.routers.turmas.submissoes_montagem", subm), \
             patch("app.desafios.catalogo.opcoes_coletas", cat["coleta"]), \
             patch("app.desafios.catalogo.opcoes_pre_processamento", cat["pre_processamento"]), \
             patch("app.desafios.catalogo.opcoes_modelos", cat["modelo"]), \
             patch("app.desafios.catalogo.opcoes_metricas", cat["metrica"]):
            r = await client.get(
                f"/turmas/{turma['_id']}/atividades/{atividade['_id']}/tabuleiro",
                headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["dataset_nome"] == "Iris"
        assert "gabarito" not in r.json()


class TestPerfilEndpoint:
    @pytest.mark.asyncio
    async def test_professor_obtem_o_perfil(self, client, mock_db, auth_headers):
        prof = {"_id": ObjectId(), "email": "p@x.com", "nome_usuario": "Prof", "role": "professor"}
        mock_db["usuarios"].find_one = AsyncMock(return_value=prof)
        r = await client.get("/toy_datasets/iris/perfil-desafio", headers=auth_headers)
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["tarefa"] == "classificacao" and corpo["nome"] == "Iris"
        assert set(corpo["dados"]) == {"faltantes", "texto", "escalas_diferentes"}

    @pytest.mark.asyncio
    async def test_aluno_nao_obtem_o_perfil(self, client, mock_db, auth_headers):
        r = await client.get("/toy_datasets/iris/perfil-desafio", headers=auth_headers)
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_dataset_inexistente_404(self, client, mock_db, auth_headers):
        prof = {"_id": ObjectId(), "email": "p@x.com", "nome_usuario": "Prof", "role": "professor"}
        mock_db["usuarios"].find_one = AsyncMock(return_value=prof)
        r = await client.get("/toy_datasets/nao-existe/perfil-desafio", headers=auth_headers)
        assert r.status_code == 404
