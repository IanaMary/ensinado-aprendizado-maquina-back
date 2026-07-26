"""Testes da evolução do aluno na mesma base (Fase 2).

O que precisa ficar travado: a leitura é sempre RELATIVA (chute burro + tentativa anterior),
o agrupamento é por base+alvo, e "melhorou" tem o mesmo sinal em métrica de maior-é-melhor
e de menor-é-melhor — errar esse sinal ensinaria o contrário do que se quer.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from app.metricas.resultado import baseline_trivial, ordem_da_metrica, valor_metrica
from app.pipelines_evolucao import chave_da_base, montar_evolucao, tarefa_do_pipeline


class AsyncCursor:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        self._it = iter(self._items)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration

    async def to_list(self, length=None):
        return list(self._items)

    def sort(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def skip(self, *a, **k):
        return self


def _pipeline(nome, data, valor=None, *, dataset="titanic.csv", target="Survived",
              modelo="knn", pre=(), matriz=None, metrica_label="Acurácia",
              prever_categoria=True, atividade_id=None, treino=80):
    resultados = {}
    if valor is not None:
        resultados[metrica_label] = {"Modelo": valor}
    if matriz:
        resultados["Matriz de confusão"] = {"Modelo": matriz}
    return {
        "_id": ObjectId(),
        "nome": nome,
        "dataCriacao": data,
        "atividade_id": atividade_id,
        "modeloSelecionado": {"valor": modelo},
        "preProcessamentoConfig": {"itens": [{"valor": p} for p in pre]},
        "resultadosDasAvaliacoes": resultados,
        "resultadoColetaDado": {
            "nomeDataset": dataset, "target": target,
            "preverCategoria": prever_categoria, "dadosRotulados": True,
            "porcentagemTreino": treino,
        },
    }


class TestIdentidadeDaBase:
    def test_prefere_nome_estavel_ao_id_do_arquivo(self):
        """`datasetId` é o id do arquivo criado a cada carregamento — se ele viesse antes do
        nome, recarregar o mesmo dataset criaria uma base nova e a evolução nunca apareceria."""
        assert chave_da_base({"datasetId": "6a65d2df7653272876ceef2d", "nomeDataset": "Iris",
                              "target": "target"}) == ("Iris", "target")
        assert chave_da_base({"nomeDataset": "titanic.csv", "target": "Survived"}) == ("titanic.csv", "Survived")
        assert chave_da_base({"treino": {"nomeArquivo": "casas.csv"}, "target": "preco"}) == ("casas.csv", "preco")
        # só o id: melhor agrupar por ele do que descartar a tentativa
        assert chave_da_base({"datasetId": "abc", "target": "y"}) == ("abc", "y")

    def test_sem_dados_nao_tem_base(self):
        assert chave_da_base({}) is None
        assert chave_da_base(None) is None

    def test_mesmo_dataset_com_alvo_diferente_sao_bases_diferentes(self):
        a = chave_da_base({"nomeDataset": "d.csv", "target": "x"})
        b = chave_da_base({"nomeDataset": "d.csv", "target": "y"})
        assert a != b

    def test_tarefa_segue_a_convencao_do_catalogo(self):
        assert tarefa_do_pipeline({"preverCategoria": True, "dadosRotulados": True}) == "classificacao"
        assert tarefa_do_pipeline({"preverCategoria": False, "dadosRotulados": True}) == "regressao"
        assert tarefa_do_pipeline({"dadosRotulados": False}) == "agrupamento"


class TestChuteBurro:
    def test_acuracia_sai_da_matriz_de_confusao(self):
        # 60 de uma classe, 40 da outra: chutar sempre a maior acerta 60%.
        resultados = {"Matriz de confusão": {"M": {"matriz": [[50, 10], [15, 25]],
                                                   "classes": ["não", "sim"], "total": 100}}}
        assert baseline_trivial(resultados, "accuracy_score") == 0.6

    def test_r2_tem_baseline_zero_por_definicao(self):
        assert baseline_trivial({}, "r2_score") == 0.0

    def test_sem_baseline_barato_devolve_none(self):
        assert baseline_trivial({}, "accuracy_score") is None          # sem matriz
        assert baseline_trivial({}, "mean_absolute_error") is None     # precisaria dos dados
        assert baseline_trivial({}, "silhouette_score") is None        # não faz sentido

    def test_matriz_malformada_nao_quebra(self):
        assert baseline_trivial({"Matriz de confusão": {"M": {"matriz": "nada"}}}, "accuracy_score") is None
        assert baseline_trivial({"Matriz de confusão": {"M": {"matriz": [[0, 0], [0, 0]]}}},
                                "accuracy_score") is None

    def test_ordem_da_metrica(self):
        assert ordem_da_metrica("accuracy_score") == "desc"
        assert ordem_da_metrica("mean_absolute_error") == "asc"
        assert ordem_da_metrica("davies_bouldin_score") == "asc"

    def test_valor_metrica_ignora_texto_e_bool(self):
        assert valor_metrica({"Acurácia": {"a": "Erro: x", "b": True, "c": 0.7}}, ["Acurácia"], "desc") == 0.7


@pytest.mark.asyncio
class TestEvolucao:
    async def _montar(self, docs, criterios=None):
        # `chaves_metrica` consulta db.metricas para resolver o rótulo da métrica.
        metr = MagicMock(find_one=AsyncMock(return_value={"valor": "accuracy_score", "label": "Acurácia"}))
        with patch("app.metricas.resultado.opcoes_metricas", metr):
            return await montar_evolucao(docs, criterios or {})

    async def test_agrupa_por_base_e_ordena_cronologicamente(self):
        docs = [
            _pipeline("terceiro", "2026-07-21", 0.781, modelo="random_forest"),
            _pipeline("primeiro", "2026-07-10", 0.701),
            _pipeline("outro dataset", "2026-07-12", 0.95, dataset="iris.csv", target="especie"),
        ]
        bases = await self._montar(docs)
        assert len(bases) == 2
        titanic = next(b for b in bases if b["dataset"] == "titanic.csv")
        assert [t["nome"] for t in titanic["tentativas"]] == ["primeiro", "terceiro"]

    async def test_delta_positivo_quando_melhora_em_metrica_de_maior_e_melhor(self):
        docs = [_pipeline("#1", "2026-07-10", 0.70), _pipeline("#2", "2026-07-14", 0.78)]
        base = (await self._montar(docs))[0]
        assert base["ultima"] == 0.78
        assert base["melhor"] == 0.78
        assert base["delta_vs_anterior"] == pytest.approx(0.08)

    async def test_delta_negativo_quando_piora(self):
        docs = [_pipeline("#1", "2026-07-10", 0.78), _pipeline("#2", "2026-07-14", 0.70)]
        base = (await self._montar(docs))[0]
        assert base["delta_vs_anterior"] == pytest.approx(-0.08)
        assert base["melhor"] == 0.78     # a melhor continua sendo a anterior

    async def test_metrica_de_menor_e_melhor_tem_delta_positivo_ao_melhorar(self):
        """MAE caindo é melhora: o sinal do delta precisa refletir isso."""
        # MAE não é a métrica padrão da regressão (é R²), então vem do critério da atividade.
        docs = [
            _pipeline("#1", "2026-07-10", 12.0, metrica_label="MAE",
                      prever_categoria=False, atividade_id="a1"),
            _pipeline("#2", "2026-07-14", 8.0, metrica_label="MAE",
                      prever_categoria=False, atividade_id="a1"),
        ]
        metr = MagicMock(find_one=AsyncMock(return_value={"valor": "mean_absolute_error", "label": "MAE"}))
        with patch("app.metricas.resultado.opcoes_metricas", metr):
            bases = await montar_evolucao(docs, {"a1": {"metrica": "mean_absolute_error", "ordem": "asc"}})
        base = bases[0]
        assert base["metrica"] == "mean_absolute_error"
        assert base["ordem"] == "asc"
        assert base["melhor"] == 8.0                       # menor é melhor
        assert base["delta_vs_anterior"] == pytest.approx(4.0)   # positivo = melhorou

    async def test_compara_com_o_chute_burro(self):
        matriz = {"matriz": [[50, 10], [15, 25]], "total": 100}
        docs = [_pipeline("#1", "2026-07-10", 0.75, matriz=matriz)]
        base = (await self._montar(docs))[0]
        assert base["baseline"] == 0.6
        assert base["delta_vs_baseline"] == pytest.approx(0.15)

    async def test_lista_o_que_mudou_entre_tentativas(self):
        docs = [
            _pipeline("#1", "2026-07-10", 0.70, modelo="knn", pre=[]),
            _pipeline("#2", "2026-07-14", 0.76, modelo="knn", pre=["minmax_scaler"]),
            _pipeline("#3", "2026-07-20", 0.78, modelo="random_forest", pre=["minmax_scaler"], treino=70),
        ]
        base = (await self._montar(docs))[0]
        assert base["tentativas"][0]["mudancas"] == []                       # primeira não compara
        assert base["tentativas"][1]["mudancas"] == ["acrescentou pré-processamento"]
        assert set(base["tentativas"][2]["mudancas"]) == {"trocou o modelo", "mudou a divisão treino/teste"}

    async def test_criterio_da_atividade_prevalece_sobre_o_padrao(self):
        docs = [_pipeline("#1", "2026-07-10", 0.7, metrica_label="F1-Score", atividade_id="a1")]
        metr = MagicMock(find_one=AsyncMock(return_value={"valor": "f1_score", "label": "F1-Score"}))
        with patch("app.metricas.resultado.opcoes_metricas", metr):
            bases = await montar_evolucao(docs, {"a1": {"metrica": "f1_score", "ordem": "desc"}})
        assert bases[0]["metrica"] == "f1_score"
        assert bases[0]["ultima"] == 0.7

    async def test_base_so_com_rascunho_fica_de_fora(self):
        docs = [_pipeline("rascunho", "2026-07-10", None)]
        assert await self._montar(docs) == []

    async def test_pipeline_sem_dados_e_ignorado(self):
        doc = _pipeline("sem base", "2026-07-10", 0.9)
        doc["resultadoColetaDado"] = {}
        assert await self._montar([doc]) == []


class TestRotaEvolucao:
    @pytest.mark.asyncio
    async def test_devolve_bases_do_proprio_usuario(self, client, mock_db, auth_headers):
        docs = [_pipeline("#1", "2026-07-10", 0.70), _pipeline("#2", "2026-07-14", 0.78)]
        pipe = MagicMock(find=MagicMock(return_value=AsyncCursor(docs)))
        ativ = MagicMock(find=MagicMock(return_value=AsyncCursor([])))
        metr = MagicMock(find_one=AsyncMock(return_value={"valor": "accuracy_score", "label": "Acurácia"}))
        with patch("app.routers.pipelines.pipelines", pipe), \
             patch("app.routers.pipelines.atividades", ativ), \
             patch("app.metricas.resultado.opcoes_metricas", metr):
            r = await client.get("/pipelines/evolucao", headers=auth_headers)
        assert r.status_code == 200
        bases = r.json()["bases"]
        assert len(bases) == 1
        assert bases[0]["dataset"] == "titanic.csv"
        assert bases[0]["delta_vs_anterior"] == pytest.approx(0.08)
        # a consulta é escopada ao usuário autenticado
        assert "user_id" in pipe.find.call_args[0][0]

    @pytest.mark.asyncio
    async def test_exige_autenticacao(self, client, mock_db):
        r = await client.get("/pipelines/evolucao")
        assert r.status_code in (401, 403)


class TestFiltroDaBase:
    """O cliente manda os nomes que conhece e o servidor escolhe a base — assim a regra de
    identidade não vive duplicada no front (foi o que quebrou o bloco na 1ª versão)."""

    @pytest.mark.asyncio
    async def test_filtra_por_nome_candidato_e_alvo(self, client, mock_db, auth_headers):
        docs = [
            _pipeline("iris #1", "2026-07-10", 0.86, dataset="Iris", target="target"),
            _pipeline("titanic", "2026-07-11", 0.70),
        ]
        pipe = MagicMock(find=MagicMock(return_value=AsyncCursor(docs)))
        ativ = MagicMock(find=MagicMock(return_value=AsyncCursor([])))
        metr = MagicMock(find_one=AsyncMock(return_value={"valor": "accuracy_score", "label": "Acurácia"}))
        with patch("app.routers.pipelines.pipelines", pipe), \
             patch("app.routers.pipelines.atividades", ativ), \
             patch("app.metricas.resultado.opcoes_metricas", metr):
            # manda vários candidatos (nome do dataset, nome do arquivo, id) — casa o que existir
            r = await client.get(
                "/pipelines/evolucao?dataset=Iris&dataset=Iris.xlsx&dataset=abc123&alvo=target",
                headers=auth_headers)
        assert r.status_code == 200
        bases = r.json()["bases"]
        assert [b["dataset"] for b in bases] == ["Iris"]

    @pytest.mark.asyncio
    async def test_sem_filtro_devolve_todas_as_bases(self, client, mock_db, auth_headers):
        docs = [
            _pipeline("iris", "2026-07-10", 0.86, dataset="Iris", target="target"),
            _pipeline("titanic", "2026-07-11", 0.70),
        ]
        pipe = MagicMock(find=MagicMock(return_value=AsyncCursor(docs)))
        ativ = MagicMock(find=MagicMock(return_value=AsyncCursor([])))
        metr = MagicMock(find_one=AsyncMock(return_value={"valor": "accuracy_score", "label": "Acurácia"}))
        with patch("app.routers.pipelines.pipelines", pipe), \
             patch("app.routers.pipelines.atividades", ativ), \
             patch("app.metricas.resultado.opcoes_metricas", metr):
            r = await client.get("/pipelines/evolucao", headers=auth_headers)
        assert len(r.json()["bases"]) == 2

    @pytest.mark.asyncio
    async def test_alvo_diferente_nao_casa(self, client, mock_db, auth_headers):
        docs = [_pipeline("iris", "2026-07-10", 0.86, dataset="Iris", target="target")]
        pipe = MagicMock(find=MagicMock(return_value=AsyncCursor(docs)))
        ativ = MagicMock(find=MagicMock(return_value=AsyncCursor([])))
        metr = MagicMock(find_one=AsyncMock(return_value={"valor": "accuracy_score", "label": "Acurácia"}))
        with patch("app.routers.pipelines.pipelines", pipe), \
             patch("app.routers.pipelines.atividades", ativ), \
             patch("app.metricas.resultado.opcoes_metricas", metr):
            r = await client.get("/pipelines/evolucao?dataset=Iris&alvo=species", headers=auth_headers)
        assert r.json()["bases"] == []
