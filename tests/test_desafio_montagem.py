"""Testes do desafio de montagem (quebra-cabeça avaliado por rubrica).

Cobre as três coisas que podem quebrar de forma silenciosa e caríssima em sala:
1. a rubrica (cada regra isolada, os pesos e a nota),
2. o sorteio (determinismo por tentativa, re-sorteio, fixar/vetar),
3. o contrato das rotas — em especial que o **gabarito e o papel das peças nunca vazam**
   para o aluno, porque com eles o desafio se resolve lendo a resposta da API.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from app.desafios.avaliacao import avaliar_montagem, normalizar_montagem
from app.desafios.catalogo import familia_pre_processamento, grupo_da_metrica, tarefa_do_modelo
from app.desafios.regras import Contexto, regras_aplicaveis
from app.desafios.sorteio import montar_tabuleiro, papeis


class AsyncCursor:
    """Cursor Mongo assíncrono simples (mesmo helper de test_turmas_fixes)."""
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


PECAS = {
    "arquivo": {"valor": "arquivo", "lane": "coleta", "nome": "Arquivo"},
    "knn": {"valor": "knn", "lane": "modelo", "nome": "k-NN",
            "tarefa": "classificacao", "metricas": ["accuracy_score", "f1_score"]},
    "arvore_decisao": {"valor": "arvore_decisao", "lane": "modelo", "nome": "Árvore",
                       "tarefa": "classificacao", "metricas": ["accuracy_score"]},
    "regressao_linear": {"valor": "regressao_linear", "lane": "modelo", "nome": "Reg. Linear",
                         "tarefa": "regressao", "metricas": ["r2_score"]},
    "k_means": {"valor": "k_means", "lane": "modelo", "nome": "K-Means",
                "tarefa": "agrupamento", "metricas": ["silhouette_score"]},
    "accuracy_score": {"valor": "accuracy_score", "lane": "metrica", "nome": "Acurácia",
                       "grupo": "classificacao"},
    "r2_score": {"valor": "r2_score", "lane": "metrica", "nome": "R²", "grupo": "regressao"},
    "silhouette_score": {"valor": "silhouette_score", "lane": "metrica", "nome": "Silhueta",
                         "grupo": "agrupamento"},
    "minmax_scaler": {"valor": "minmax_scaler", "lane": "pre_processamento",
                      "nome": "MinMax", "familia": "escala"},
    "standard_scaler": {"valor": "standard_scaler", "lane": "pre_processamento",
                        "nome": "Standard", "familia": "escala"},
    "simple_imputer": {"valor": "simple_imputer", "lane": "pre_processamento",
                       "nome": "Imputação", "familia": "imputacao"},
    "one_hot_encoder": {"valor": "one_hot_encoder", "lane": "pre_processamento",
                        "nome": "One-Hot", "familia": "encoder"},
    "pca": {"valor": "pca", "lane": "pre_processamento", "nome": "PCA", "familia": "outro"},
}

GABARITO = {
    "tarefa": "classificacao",
    "exige": ["coleta", "modelo", "metrica"],
    "dados": {"faltantes": False, "texto": False, "escalas_diferentes": False},
    "dificuldade": "medio",
}


def _ctx(montagem, gabarito=None, ofertadas=None):
    return Contexto(
        montagem=normalizar_montagem(montagem),
        gabarito=gabarito or GABARITO,
        pecas=PECAS,
        ofertadas=ofertadas or {v: "util" for v in PECAS},
    )


def _regra(resultado, regra_id):
    return next((r for r in resultado["regras"] if r["id"] == regra_id), None)


def _avaliar(montagem, gabarito=None, ofertadas=None):
    return avaliar_montagem(montagem, gabarito or GABARITO, PECAS,
                            ofertadas or {v: "util" for v in PECAS})


# ------------------------------------------------------------------ normalização
class TestNormalizacao:
    def test_descarta_lane_e_tipo_invalidos(self):
        m = normalizar_montagem({"modelo": "knn", "inexistente": ["x"], "metrica": [1, None, "accuracy_score"]})
        assert m["modelo"] == ["knn"]           # string virou lista
        assert m["metrica"] == ["accuracy_score"]  # não-strings caíram
        assert "inexistente" not in m

    def test_entrada_nao_dict_nao_explode(self):
        assert normalizar_montagem(None)["modelo"] == []
        assert normalizar_montagem("knn")["modelo"] == []

    def test_limita_quantidade_por_lane(self):
        m = normalizar_montagem({"modelo": [f"m{i}" for i in range(50)]})
        assert len(m["modelo"]) == 20


# ------------------------------------------------------------------ regras isoladas
class TestRegras:
    def test_estrutura_minima_cobra_lane_vazia(self):
        r = _avaliar({"coleta": [], "modelo": ["knn"], "metrica": ["accuracy_score"]})
        assert _regra(r, "estrutura-minima")["ok"] is False
        r_ok = _avaliar({"coleta": ["arquivo"], "modelo": ["knn"], "metrica": ["accuracy_score"]})
        assert _regra(r_ok, "estrutura-minima")["ok"] is True

    def test_modelo_de_outra_tarefa_reprova(self):
        r = _avaliar({"coleta": ["arquivo"], "modelo": ["regressao_linear"], "metrica": ["accuracy_score"]})
        assert _regra(r, "modelo-compativel")["ok"] is False

    def test_metrica_de_outro_grupo_reprova(self):
        r = _avaliar({"coleta": ["arquivo"], "modelo": ["knn"], "metrica": ["r2_score"]})
        assert _regra(r, "metrica-compativel")["ok"] is False

    def test_metrica_sem_grupo_cai_na_lista_do_modelo(self):
        pecas = {**PECAS, "metrica_nova": {"valor": "metrica_nova", "lane": "metrica",
                                           "nome": "Nova", "grupo": None}}
        r = avaliar_montagem({"coleta": ["arquivo"], "modelo": ["knn"], "metrica": ["metrica_nova"]},
                             GABARITO, pecas, {v: "util" for v in pecas})
        assert _regra(r, "metrica-compativel")["ok"] is False

    def test_modelo_de_distancia_exige_escala(self):
        sem = _avaliar({"coleta": ["arquivo"], "modelo": ["knn"], "metrica": ["accuracy_score"]})
        assert _regra(sem, "escala-antes-de-distancia")["ok"] is False
        com = _avaliar({"coleta": ["arquivo"], "pre_processamento": ["minmax_scaler"],
                        "modelo": ["knn"], "metrica": ["accuracy_score"]})
        assert _regra(com, "escala-antes-de-distancia")["ok"] is True

    def test_arvore_nao_e_cobrada_por_escala(self):
        r = _avaliar({"coleta": ["arquivo"], "modelo": ["arvore_decisao"], "metrica": ["accuracy_score"]})
        assert _regra(r, "escala-antes-de-distancia") is None  # regra não se aplica

    def test_faltantes_exigem_imputacao(self):
        gab = {**GABARITO, "dados": {"faltantes": True}}
        sem = _avaliar({"coleta": ["arquivo"], "modelo": ["arvore_decisao"],
                        "metrica": ["accuracy_score"]}, gab)
        assert _regra(sem, "imputacao-quando-ha-faltantes")["ok"] is False
        com = _avaliar({"coleta": ["arquivo"], "pre_processamento": ["simple_imputer"],
                        "modelo": ["arvore_decisao"], "metrica": ["accuracy_score"]}, gab)
        assert _regra(com, "imputacao-quando-ha-faltantes")["ok"] is True

    def test_texto_exige_encoder(self):
        gab = {**GABARITO, "dados": {"texto": True}}
        sem = _avaliar({"coleta": ["arquivo"], "modelo": ["arvore_decisao"],
                        "metrica": ["accuracy_score"]}, gab)
        assert _regra(sem, "encoder-para-texto")["ok"] is False
        com = _avaliar({"coleta": ["arquivo"], "pre_processamento": ["one_hot_encoder"],
                        "modelo": ["arvore_decisao"], "metrica": ["accuracy_score"]}, gab)
        assert _regra(com, "encoder-para-texto")["ok"] is True

    def test_ordem_imputacao_antes_de_escala(self):
        errada = _avaliar({"coleta": ["arquivo"], "pre_processamento": ["minmax_scaler", "simple_imputer"],
                           "modelo": ["knn"], "metrica": ["accuracy_score"]})
        assert _regra(errada, "imputacao-antes-de-escala")["ok"] is False
        certa = _avaliar({"coleta": ["arquivo"], "pre_processamento": ["simple_imputer", "minmax_scaler"],
                          "modelo": ["knn"], "metrica": ["accuracy_score"]})
        assert _regra(certa, "imputacao-antes-de-escala")["ok"] is True

    def test_distrator_usado_reprova(self):
        ofertadas = {v: "util" for v in PECAS}
        ofertadas["pca"] = "distrator"
        com_distrator = _avaliar({"coleta": ["arquivo"], "pre_processamento": ["pca", "minmax_scaler"],
                                  "modelo": ["knn"], "metrica": ["accuracy_score"]}, ofertadas=ofertadas)
        assert _regra(com_distrator, "sem-distrator")["ok"] is False
        sem_distrator = _avaliar({"coleta": ["arquivo"], "pre_processamento": ["minmax_scaler"],
                                  "modelo": ["knn"], "metrica": ["accuracy_score"]}, ofertadas=ofertadas)
        assert _regra(sem_distrator, "sem-distrator")["ok"] is True

    def test_peca_fora_do_catalogo_e_ignorada_sem_quebrar(self):
        r = _avaliar({"coleta": ["arquivo"], "modelo": ["modelo_que_nao_existe"],
                      "metrica": ["accuracy_score"]})
        # não aplica modelo-compativel (sem metadados), mas a estrutura foi preenchida
        assert _regra(r, "estrutura-minima")["ok"] is True
        assert _regra(r, "modelo-compativel") is None


# ------------------------------------------------------------------ nota
class TestNota:
    def test_montagem_perfeita_tira_dez(self):
        gab = {**GABARITO, "dados": {"faltantes": True}}
        r = _avaliar({"coleta": ["arquivo"],
                      "pre_processamento": ["simple_imputer", "minmax_scaler"],
                      "modelo": ["knn"], "metrica": ["accuracy_score"]}, gab)
        assert r["nota"] == 10.0
        assert r["acertou_tudo"] is True
        assert r["pontos"] == r["pontos_max"]

    def test_montagem_vazia_tira_zero(self):
        r = _avaliar({})
        assert r["nota"] == 0.0
        assert r["acertou_tudo"] is False

    def test_entregar_vazio_nao_ganha_ponto_por_nao_usar_distrator(self):
        """Regressão: `sem-distrator` era satisfeita trivialmente por não montar nada,
        o que dava 4/10 para uma entrega em branco."""
        ofertadas = {**{v: "util" for v in PECAS}, "pca": "distrator"}
        r = _avaliar({}, ofertadas=ofertadas)
        assert r["nota"] == 0.0
        assert _regra(r, "sem-distrator") is None       # regra não se aplica a entrega vazia

    def test_pontos_max_conta_so_regras_aplicaveis(self):
        # sem faltantes/texto e com árvore: imputação, encoder e escala não entram no total
        r = _avaliar({"coleta": ["arquivo"], "modelo": ["arvore_decisao"], "metrica": ["accuracy_score"]})
        ids = {x["id"] for x in r["regras"]}
        assert ids == {"estrutura-minima", "modelo-compativel", "metrica-compativel"}
        assert r["pontos_max"] == 9

    def test_regras_aplicaveis_por_tarefa_de_agrupamento(self):
        gab = {"tarefa": "agrupamento", "exige": ["coleta", "modelo", "metrica"], "dados": {}}
        ctx = _ctx({"coleta": ["arquivo"], "modelo": ["k_means"], "metrica": ["silhouette_score"]}, gab)
        aplicaveis = {r.id for r in regras_aplicaveis(ctx)}
        assert "imputacao-quando-ha-faltantes" not in aplicaveis
        r = _avaliar({"coleta": ["arquivo"], "pre_processamento": ["minmax_scaler"],
                      "modelo": ["k_means"], "metrica": ["silhouette_score"]}, gab)
        assert r["nota"] == 10.0


# ------------------------------------------------------------------ sorteio
class TestSorteio:
    @pytest.mark.asyncio
    async def test_deterministico_por_tentativa(self):
        atividade = {"_id": ObjectId(), "gabarito": GABARITO}
        uid = str(ObjectId())
        a = await montar_tabuleiro(atividade, uid, 1, pecas_catalogo=PECAS)
        b = await montar_tabuleiro(atividade, uid, 1, pecas_catalogo=PECAS)
        assert [p["valor"] for p in a["pecas"]] == [p["valor"] for p in b["pecas"]]

    @pytest.mark.asyncio
    async def test_re_sorteio_muda_o_tabuleiro(self):
        atividade = {"_id": ObjectId(), "gabarito": GABARITO}
        uid = str(ObjectId())
        t1 = await montar_tabuleiro(atividade, uid, 1, pecas_catalogo=PECAS)
        t2 = await montar_tabuleiro(atividade, uid, 2, pecas_catalogo=PECAS)
        assert [p["valor"] for p in t1["pecas"]] != [p["valor"] for p in t2["pecas"]]

    @pytest.mark.asyncio
    async def test_alunos_diferentes_recebem_tabuleiros_diferentes(self):
        atividade = {"_id": ObjectId(), "gabarito": GABARITO}
        t1 = await montar_tabuleiro(atividade, str(ObjectId()), 1, pecas_catalogo=PECAS)
        t2 = await montar_tabuleiro(atividade, str(ObjectId()), 1, pecas_catalogo=PECAS)
        assert [p["valor"] for p in t1["pecas"]] != [p["valor"] for p in t2["pecas"]]

    @pytest.mark.asyncio
    async def test_vetar_remove_e_fixar_garante(self):
        gab = {**GABARITO, "vetar": ["knn"], "fixar": ["pca"]}
        t = await montar_tabuleiro({"_id": ObjectId(), "gabarito": gab}, str(ObjectId()), 1,
                                   pecas_catalogo=PECAS)
        valores = [p["valor"] for p in t["pecas"]]
        assert "knn" not in valores
        assert "pca" in valores

    @pytest.mark.asyncio
    async def test_pecas_uteis_sao_da_tarefa_do_desafio(self):
        t = await montar_tabuleiro({"_id": ObjectId(), "gabarito": GABARITO}, str(ObjectId()), 1,
                                   pecas_catalogo=PECAS)
        uteis_modelo = [p for p in t["pecas"] if p["papel"] == "util" and p["lane"] == "modelo"]
        assert uteis_modelo, "sorteio deveria ofertar ao menos um modelo útil"
        assert all(p["tarefa"] == "classificacao" for p in uteis_modelo)

    @pytest.mark.asyncio
    async def test_dificuldade_controla_quantidade_de_distratores(self):
        uid = str(ObjectId())
        oid = ObjectId()
        facil = await montar_tabuleiro({"_id": oid, "gabarito": {**GABARITO, "dificuldade": "facil"}},
                                       uid, 1, pecas_catalogo=PECAS)
        dificil = await montar_tabuleiro({"_id": oid, "gabarito": {**GABARITO, "dificuldade": "dificil"}},
                                         uid, 1, pecas_catalogo=PECAS)
        n_facil = sum(1 for p in facil["pecas"] if p["papel"] == "distrator")
        n_dificil = sum(1 for p in dificil["pecas"] if p["papel"] == "distrator")
        assert n_facil == 2
        assert n_dificil > n_facil

    @pytest.mark.asyncio
    async def test_familia_necessaria_nunca_entra_como_distrator(self):
        gab = {**GABARITO, "dados": {"faltantes": True, "texto": True}, "dificuldade": "dificil"}
        t = await montar_tabuleiro({"_id": ObjectId(), "gabarito": gab}, str(ObjectId()), 1,
                                   pecas_catalogo=PECAS)
        distratores = [p for p in t["pecas"] if p["papel"] == "distrator"]
        assert all(p.get("familia") not in ("imputacao", "encoder") for p in distratores)

    @pytest.mark.asyncio
    async def test_papeis_indexa_por_valor(self):
        t = await montar_tabuleiro({"_id": ObjectId(), "gabarito": GABARITO}, str(ObjectId()), 1,
                                   pecas_catalogo=PECAS)
        mapa = papeis(t)
        assert set(mapa.values()) <= {"util", "distrator"}
        assert len(mapa) == len(t["pecas"])


# ------------------------------------------------------------------ catálogo
class TestCatalogoHelpers:
    def test_familia_por_classe_sklearn(self):
        assert familia_pre_processamento("MinMaxScaler") == "escala"
        assert familia_pre_processamento("SimpleImputer") == "imputacao"
        assert familia_pre_processamento("OneHotEncoder") == "encoder"
        assert familia_pre_processamento("PCA") == "outro"
        assert familia_pre_processamento(None) == "outro"

    def test_tarefa_do_modelo_segue_convencao_do_catalogo(self):
        assert tarefa_do_modelo({"prever_categoria": True, "dados_rotulados": True}) == "classificacao"
        assert tarefa_do_modelo({"prever_categoria": False, "dados_rotulados": True}) == "regressao"
        assert tarefa_do_modelo({"dados_rotulados": False}) == "agrupamento"

    def test_grupo_da_metrica_com_fallback(self):
        assert grupo_da_metrica({"valor": "x", "grupo": "regressao"}) == "regressao"
        assert grupo_da_metrica({"valor": "silhouette_score"}) == "agrupamento"
        assert grupo_da_metrica({"valor": "r2_score"}) == "regressao"
        assert grupo_da_metrica({"valor": "desconhecida"}) is None


# ------------------------------------------------------------------ rotas
def _prof():
    return {"_id": ObjectId(), "nome_usuario": "prof", "email": "test@test.com", "role": "professor"}


def _catalogo_mock():
    """Coleções do catálogo devolvendo as peças de teste (carregar_pecas usa find())."""
    por_lane = {"coleta": [], "pre_processamento": [], "modelo": [], "metrica": []}
    for p in PECAS.values():
        if p["lane"] == "pre_processamento":
            classe = {"escala": "MinMaxScaler", "imputacao": "SimpleImputer",
                      "encoder": "OneHotEncoder"}.get(p.get("familia"), "PCA")
            por_lane["pre_processamento"].append(
                {"valor": p["valor"], "nome": p["nome"], "execucao": {"classe": classe}})
        elif p["lane"] == "modelo":
            por_lane["modelo"].append({
                "valor": p["valor"], "nome": p["nome"],
                "prever_categoria": p["tarefa"] == "classificacao",
                "dados_rotulados": p["tarefa"] != "agrupamento",
                "metricas": p.get("metricas", []),
            })
        elif p["lane"] == "metrica":
            por_lane["metrica"].append({"valor": p["valor"], "label": p["nome"], "grupo": p["grupo"]})
        else:
            por_lane["coleta"].append({"valor": p["valor"], "nome": p["nome"]})
    return {lane: MagicMock(find=MagicMock(return_value=AsyncCursor(docs)))
            for lane, docs in por_lane.items()}


class TestRotasDesafio:
    @pytest.mark.asyncio
    async def test_tabuleiro_nao_vaza_papel_nem_gabarito(self, client, mock_db, auth_headers, mock_user):
        turma = {"_id": ObjectId(), "professor_id": str(ObjectId()),
                 "alunos": [str(mock_user["_id"])]}
        atividade = {"_id": ObjectId(), "turma_id": str(turma["_id"]), "tipo": "montagem",
                     "titulo": "Prever espécie", "gabarito": GABARITO}
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
        body = r.json()
        assert body["tentativa"] == 1
        assert body["pecas"], "o aluno precisa receber peças"
        assert all(set(p.keys()) == {"valor", "nome", "lane"} for p in body["pecas"])
        assert "gabarito" not in body and "gabarito" not in body["atividade"]

    @pytest.mark.asyncio
    async def test_tabuleiro_404_para_atividade_de_pipeline(self, client, mock_db, auth_headers, mock_user):
        turma = {"_id": ObjectId(), "professor_id": str(ObjectId()), "alunos": [str(mock_user["_id"])]}
        atividade = {"_id": ObjectId(), "turma_id": str(turma["_id"]), "tipo": "pipeline"}
        with patch("app.routers.turmas.turmas", MagicMock(find_one=AsyncMock(return_value=turma))), \
             patch("app.routers.turmas.atividades", MagicMock(find_one=AsyncMock(return_value=atividade))):
            r = await client.get(
                f"/turmas/{turma['_id']}/atividades/{atividade['_id']}/tabuleiro",
                headers=auth_headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_tabuleiro_id_invalido_400(self, client, mock_db, auth_headers, mock_user):
        turma = {"_id": ObjectId(), "professor_id": str(ObjectId()), "alunos": [str(mock_user["_id"])]}
        with patch("app.routers.turmas.turmas", MagicMock(find_one=AsyncMock(return_value=turma))):
            r = await client.get(f"/turmas/{turma['_id']}/atividades/nao-e-objectid/tabuleiro",
                                 headers=auth_headers)
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_submeter_grava_e_devolve_nota(self, client, mock_db, auth_headers, mock_user):
        turma = {"_id": ObjectId(), "professor_id": str(ObjectId()), "alunos": [str(mock_user["_id"])]}
        atividade = {"_id": ObjectId(), "turma_id": str(turma["_id"]), "tipo": "montagem",
                     "gabarito": GABARITO}
        cat = _catalogo_mock()
        subm = MagicMock(count_documents=AsyncMock(return_value=0),
                         find=MagicMock(return_value=AsyncCursor([])),
                         insert_one=AsyncMock(return_value=MagicMock(inserted_id=ObjectId())))
        with patch("app.routers.turmas.turmas", MagicMock(find_one=AsyncMock(return_value=turma))), \
             patch("app.routers.turmas.atividades", MagicMock(find_one=AsyncMock(return_value=atividade))), \
             patch("app.routers.turmas.submissoes_montagem", subm), \
             patch("app.desafios.catalogo.opcoes_coletas", cat["coleta"]), \
             patch("app.desafios.catalogo.opcoes_pre_processamento", cat["pre_processamento"]), \
             patch("app.desafios.catalogo.opcoes_modelos", cat["modelo"]), \
             patch("app.desafios.catalogo.opcoes_metricas", cat["metrica"]):
            r = await client.post(
                f"/turmas/{turma['_id']}/atividades/{atividade['_id']}/submeter-montagem",
                headers=auth_headers,
                json={"montagem": {"coleta": [], "modelo": [], "metrica": []}})
        assert r.status_code == 200
        body = r.json()
        assert body["nota"] == 0.0                      # montagem vazia
        assert body["tentativa"] == 1
        assert any(not x["ok"] for x in body["regras"])
        assert "montagem" not in body                   # eco desnecessário fica de fora
        assert subm.insert_one.await_count == 1
        gravado = subm.insert_one.await_args[0][0]
        assert gravado["atividade_id"] == str(atividade["_id"])
        assert gravado["tentativa"] == 1
        assert gravado["regras"], "a explicação precisa ficar gravada para o tutor usar depois"

    @pytest.mark.asyncio
    async def test_submeter_incrementa_tentativa(self, client, mock_db, auth_headers, mock_user):
        turma = {"_id": ObjectId(), "professor_id": str(ObjectId()), "alunos": [str(mock_user["_id"])]}
        atividade = {"_id": ObjectId(), "turma_id": str(turma["_id"]), "tipo": "montagem",
                     "gabarito": GABARITO}
        cat = _catalogo_mock()
        subm = MagicMock(count_documents=AsyncMock(return_value=2),
                         find=MagicMock(return_value=AsyncCursor([{"nota": 6.0}])),
                         insert_one=AsyncMock(return_value=MagicMock(inserted_id=ObjectId())))
        with patch("app.routers.turmas.turmas", MagicMock(find_one=AsyncMock(return_value=turma))), \
             patch("app.routers.turmas.atividades", MagicMock(find_one=AsyncMock(return_value=atividade))), \
             patch("app.routers.turmas.submissoes_montagem", subm), \
             patch("app.desafios.catalogo.opcoes_coletas", cat["coleta"]), \
             patch("app.desafios.catalogo.opcoes_pre_processamento", cat["pre_processamento"]), \
             patch("app.desafios.catalogo.opcoes_modelos", cat["modelo"]), \
             patch("app.desafios.catalogo.opcoes_metricas", cat["metrica"]):
            r = await client.post(
                f"/turmas/{turma['_id']}/atividades/{atividade['_id']}/submeter-montagem",
                headers=auth_headers, json={"montagem": {}})
        body = r.json()
        assert body["tentativa"] == 3
        assert body["melhor_nota"] == 6.0   # tentativa pior não derruba a melhor nota

    @pytest.mark.asyncio
    async def test_recusa_peca_que_nao_esta_no_tabuleiro(self, client, mock_db, auth_headers, mock_user):
        """Sem isto o re-sorteio não protegeria nada: bastaria reenviar o pipeline ideal
        aprendido no feedback da tentativa anterior, ignorando as peças sorteadas agora."""
        turma = {"_id": ObjectId(), "professor_id": str(ObjectId()), "alunos": [str(mock_user["_id"])]}
        atividade = {"_id": ObjectId(), "turma_id": str(turma["_id"]), "tipo": "montagem",
                     "gabarito": {**GABARITO, "vetar": ["knn"]}}
        cat = _catalogo_mock()
        subm = MagicMock(count_documents=AsyncMock(return_value=0),
                         find=MagicMock(return_value=AsyncCursor([])),
                         insert_one=AsyncMock(return_value=MagicMock(inserted_id=ObjectId())))
        with patch("app.routers.turmas.turmas", MagicMock(find_one=AsyncMock(return_value=turma))), \
             patch("app.routers.turmas.atividades", MagicMock(find_one=AsyncMock(return_value=atividade))), \
             patch("app.routers.turmas.submissoes_montagem", subm), \
             patch("app.desafios.catalogo.opcoes_coletas", cat["coleta"]), \
             patch("app.desafios.catalogo.opcoes_pre_processamento", cat["pre_processamento"]), \
             patch("app.desafios.catalogo.opcoes_modelos", cat["modelo"]), \
             patch("app.desafios.catalogo.opcoes_metricas", cat["metrica"]):
            r = await client.post(
                f"/turmas/{turma['_id']}/atividades/{atividade['_id']}/submeter-montagem",
                headers=auth_headers,
                json={"montagem": {"modelo": ["knn"]}})   # vetada: nunca está no tabuleiro
        assert r.status_code == 400
        assert "não estão no seu tabuleiro" in r.json()["detail"]
        assert subm.insert_one.await_count == 0   # tentativa inválida não é gravada

    @pytest.mark.asyncio
    async def test_aluno_nao_membro_404(self, client, mock_db, auth_headers):
        turma = {"_id": ObjectId(), "professor_id": str(ObjectId()), "alunos": []}
        with patch("app.routers.turmas.turmas", MagicMock(find_one=AsyncMock(return_value=turma))):
            r = await client.get(f"/turmas/{turma['_id']}/atividades/{ObjectId()}/tabuleiro",
                                 headers=auth_headers)
        assert r.status_code == 404


class TestGabaritoNaListagem:
    @pytest.mark.asyncio
    async def test_aluno_nao_ve_gabarito(self, client, mock_db, auth_headers, mock_user):
        turma = {"_id": ObjectId(), "professor_id": str(ObjectId()), "alunos": [str(mock_user["_id"])]}
        atividade = {"_id": ObjectId(), "turma_id": str(turma["_id"]), "tipo": "montagem",
                     "titulo": "Desafio", "gabarito": GABARITO}
        with patch("app.routers.turmas.turmas", MagicMock(find_one=AsyncMock(return_value=turma))), \
             patch("app.routers.turmas.atividades",
                   MagicMock(find=MagicMock(return_value=AsyncCursor([atividade])))):
            r = await client.get(f"/turmas/{turma['_id']}/atividades", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()[0]["tipo"] == "montagem"
        assert "gabarito" not in r.json()[0]

    @pytest.mark.asyncio
    async def test_professor_ve_gabarito(self, client, mock_db, auth_headers):
        prof = _prof()
        mock_db["usuarios"].find_one = AsyncMock(return_value=prof)
        turma = {"_id": ObjectId(), "professor_id": str(prof["_id"]), "alunos": []}
        atividade = {"_id": ObjectId(), "turma_id": str(turma["_id"]), "tipo": "montagem",
                     "titulo": "Desafio", "gabarito": GABARITO}
        with patch("app.routers.turmas.turmas", MagicMock(find_one=AsyncMock(return_value=turma))), \
             patch("app.routers.turmas.atividades",
                   MagicMock(find=MagicMock(return_value=AsyncCursor([atividade])))):
            r = await client.get(f"/turmas/{turma['_id']}/atividades", headers=auth_headers)
        assert r.json()[0]["gabarito"]["tarefa"] == "classificacao"

    @pytest.mark.asyncio
    async def test_atividade_antiga_sem_tipo_continua_pipeline(self, client, mock_db, auth_headers, mock_user):
        turma = {"_id": ObjectId(), "professor_id": str(ObjectId()), "alunos": [str(mock_user["_id"])]}
        antiga = {"_id": ObjectId(), "turma_id": str(turma["_id"]), "titulo": "Antiga"}
        with patch("app.routers.turmas.turmas", MagicMock(find_one=AsyncMock(return_value=turma))), \
             patch("app.routers.turmas.atividades",
                   MagicMock(find=MagicMock(return_value=AsyncCursor([antiga])))):
            r = await client.get(f"/turmas/{turma['_id']}/atividades", headers=auth_headers)
        assert r.json()[0]["tipo"] == "pipeline"


class TestProgressoComDesafios:
    @pytest.mark.asyncio
    async def test_desafios_em_coluna_propria_sem_inflar_submissoes(self, client, mock_db, auth_headers):
        """`submissoes` continua significando pipelines submetidos — o professor já lia esse
        número nesta tela. Desafios aparecem em `desafios`/`melhor_nota_desafio`."""
        prof = _prof()
        mock_db["usuarios"].find_one = AsyncMock(return_value=prof)
        aluno = str(ObjectId())
        turma = {"_id": ObjectId(), "professor_id": str(prof["_id"]), "alunos": [aluno]}

        pipes = MagicMock(aggregate=MagicMock(return_value=MagicMock(to_list=AsyncMock(
            return_value=[{"_id": aluno, "atividades": ["a1"], "ultimo": None}]))))
        subm = MagicMock(aggregate=MagicMock(return_value=MagicMock(to_list=AsyncMock(
            return_value=[{"_id": aluno, "atividades": ["a2", "a3"], "melhor_nota": 9.5,
                           "ultimo": None}]))))
        user_m = MagicMock(find=MagicMock(return_value=AsyncCursor(
            [{"_id": ObjectId(aluno), "nome_usuario": "Ana"}])))
        ativ_m = MagicMock(count_documents=AsyncMock(return_value=3))

        with patch("app.routers.turmas.turmas", MagicMock(find_one=AsyncMock(return_value=turma))), \
             patch("app.routers.turmas.atividades", ativ_m), \
             patch("app.routers.turmas.pipelines", pipes), \
             patch("app.routers.turmas.submissoes_montagem", subm), \
             patch("app.routers.turmas.colecao_usuario", user_m), \
             patch("app.routers.turmas.atividade_usuario",
                   MagicMock(aggregate=MagicMock(return_value=MagicMock(
                       to_list=AsyncMock(return_value=[]))))):
            r = await client.get(f"/turmas/{turma['_id']}/progresso", headers=auth_headers)

        assert r.status_code == 200
        linha = r.json()["alunos"][0]
        assert linha["submissoes"] == 1              # só o pipeline, não somado
        assert linha["desafios"] == 2
        assert linha["melhor_nota_desafio"] == 9.5


class TestRankingMontagem:
    @pytest.mark.asyncio
    async def test_ordena_por_nota_e_desempata_por_tentativas(self, client, mock_db, auth_headers):
        prof = _prof()
        mock_db["usuarios"].find_one = AsyncMock(return_value=prof)
        turma = {"_id": ObjectId(), "professor_id": str(prof["_id"]), "alunos": []}
        atividade = {"_id": ObjectId(), "turma_id": str(turma["_id"]), "tipo": "montagem",
                     "gabarito": GABARITO}
        a1, a2, a3 = str(ObjectId()), str(ObjectId()), str(ObjectId())
        agregado = [
            {"_id": a1, "nota": 8.0, "tentativas": 1},
            {"_id": a2, "nota": 10.0, "tentativas": 4},
            {"_id": a3, "nota": 10.0, "tentativas": 2},
        ]
        subm = MagicMock(aggregate=MagicMock(
            return_value=MagicMock(to_list=AsyncMock(return_value=agregado))))
        user_m = MagicMock(find=MagicMock(return_value=AsyncCursor([
            {"_id": ObjectId(a1), "nome_usuario": "Ana"},
            {"_id": ObjectId(a2), "nome_usuario": "Bia"},
            {"_id": ObjectId(a3), "nome_usuario": "Caio"},
        ])))
        with patch("app.routers.turmas.turmas", MagicMock(find_one=AsyncMock(return_value=turma))), \
             patch("app.routers.turmas.atividades", MagicMock(find_one=AsyncMock(return_value=atividade))), \
             patch("app.routers.turmas.submissoes_montagem", subm), \
             patch("app.routers.turmas.colecao_usuario", user_m):
            r = await client.get(
                f"/turmas/{turma['_id']}/atividades/{atividade['_id']}/ranking",
                headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["tipo"] == "montagem"
        assert body["metrica"] == "nota"
        # 10 com 2 tentativas na frente de 10 com 4; 8 por último
        assert [l["aluno_nome"] for l in body["ranking"]] == ["Caio", "Bia", "Ana"]

    @pytest.mark.asyncio
    async def test_aluno_nao_acessa_ranking(self, client, mock_db, auth_headers):
        turma = {"_id": ObjectId(), "professor_id": str(ObjectId()), "alunos": []}
        with patch("app.routers.turmas.turmas", MagicMock(find_one=AsyncMock(return_value=turma))):
            r = await client.get(f"/turmas/{turma['_id']}/atividades/{ObjectId()}/ranking",
                                 headers=auth_headers)
        assert r.status_code == 403
