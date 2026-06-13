from app.schemas.schemas import (
    DatasetRequest,
    AvaliacaoRequest,
    ReDivisaoColetaRequest,
    KnnRequestById,
)


class TestDefaultsIndependentes:
    def test_hiperparametros_nao_compartilhados_entre_instancias(self):
        kwargs = {
            "arquivo_id": "a", "tipo_arquivo": "csv",
            "configuracao_id": "b", "modelo_id": "c",
        }
        r1 = DatasetRequest(**kwargs)
        r2 = DatasetRequest(**kwargs)
        r1.hiperparametros["k"] = 5
        assert r2.hiperparametros == {}

    def test_knn_request_hiperparametros_independentes(self):
        r1 = KnnRequestById(id_coleta="a")
        r2 = KnnRequestById(id_coleta="a")
        r1.hiperparametros["x"] = 1
        assert r2.hiperparametros == {}


class TestAvaliacaoRequest:
    def test_constroi_sem_modelo_nome(self):
        """Regressão: modelo_nome era Optional sem default, o que o tornava obrigatório no Pydantic v2."""
        req = AvaliacaoRequest(
            dados_teste=[{"a": 1}],
            target="alvo",
            atributos=["a"],
            mlflow_run_id_modelo="run-1",
        )
        assert req.modelo_nome is None
        assert req.metricas == []


class TestReDivisaoColetaRequest:
    def test_round_trip(self):
        req = ReDivisaoColetaRequest(test_size=0.3)
        assert req.test_size == 0.3
        assert req.shuffle is True
        assert req.stratify is False
        assert req.target is None
