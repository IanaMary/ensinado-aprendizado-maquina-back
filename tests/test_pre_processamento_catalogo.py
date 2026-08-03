

class TestOverridesPreservamMetadado:
    """O `execucao` do banco não pode apagar metadado que só existe no catálogo em código."""

    def test_encoder_com_execucao_no_banco_continua_codificando_categoricas(self):
        """Foi o que impedia o aluno de treinar o Titanic.

        Os 10 built-ins têm `execucao` em `db.pre_processamento`, e o bloco não carrega
        `codifica_categoricas`. Substituindo a entrada inteira, a flag sumia,
        `colunas_codificadas` devolvia `set()` e o treino recusava coluna de texto **mesmo com o
        codificador aplicado** — exatamente o que a mensagem de erro manda fazer.
        """
        from app.pre_processamento import catalogo_com_overrides, colunas_codificadas

        docs_db = [{
            "valor": "ordinal_encoder",
            "execucao": {
                "modulo": "sklearn.preprocessing", "classe": "OrdinalEncoder",
                "hiperparametros": {"handle_unknown": "use_encoded_value", "unknown_value": -1},
                "escopo": "transform_X", "aplica_em": "colunas_escolhidas",
            },
        }]

        cat = catalogo_com_overrides(docs_db)

        assert cat["ordinal_encoder"]["codifica_categoricas"] is True
        # e o banco continua tendo prioridade no que ele define
        assert cat["ordinal_encoder"]["classe"] == "OrdinalEncoder"
        assert colunas_codificadas(
            [{"valor": "ordinal_encoder", "colunas": ["sex", "embarked"]}], cat
        ) == {"sex", "embarked"}

    def test_execucao_do_banco_vence_no_que_define(self):
        """Mesclar não enfraquece a prioridade do banco: a chave que ele define, ele manda.

        O módulo tem de estar na allowlist — `normalizar_execucao_db` descarta o resto, e é por
        isso que o teste troca a CLASSE dentro de `sklearn.preprocessing` em vez de inventar um
        módulo (que seria recusado por segurança, não pela mesclagem).
        """
        from app.pre_processamento import catalogo_com_overrides

        docs_db = [{
            "valor": "standard_scaler",
            "execucao": {
                "modulo": "sklearn.preprocessing", "classe": "MaxAbsScaler",
                "escopo": "transform_X", "aplica_em": "todas_numericas",
            },
        }]

        cat = catalogo_com_overrides(docs_db)

        assert cat["standard_scaler"]["classe"] == "MaxAbsScaler"
        assert cat["standard_scaler"]["aplica_em"] == "todas_numericas"
