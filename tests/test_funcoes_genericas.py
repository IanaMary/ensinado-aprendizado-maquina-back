import pytest
from app.funcoes_genericas.funcoes_genericas import (
    mapear_tipo,
    serialize_doc,
    concatenar_campos,
    get_nested,
    df_para_base64,
    decode_excel_base64_df,
    gerar_colunas_detalhes,
)
from bson import ObjectId
import pandas as pd


class TestMapearTipo:
    def test_inteiro(self):
        assert mapear_tipo("int64") == "Número"
        assert mapear_tipo("int32") == "Número"

    def test_float(self):
        assert mapear_tipo("float64") == "Número"
        assert mapear_tipo("float32") == "Número"

    def test_boolean(self):
        assert mapear_tipo("bool") == "Booleano"

    def test_string(self):
        assert mapear_tipo("object") == "Texto"
        assert mapear_tipo("string") == "Texto"

    def test_desconhecido(self):
        assert mapear_tipo("datetime64") == "datetime64"


class TestSerializeDoc:
    def test_com_objectid(self):
        oid = ObjectId()
        doc = {"_id": oid, "nome": "teste"}
        resultado = serialize_doc(doc)
        assert resultado["id"] == str(oid)
        assert "_id" not in resultado
        assert resultado["nome"] == "teste"

    def test_sem_id(self):
        doc = {"nome": "teste"}
        resultado = serialize_doc(doc)
        assert resultado == {"nome": "teste"}

    def test_none(self):
        assert serialize_doc(None) is None


class TestConcatenarCampos:
    def test_campos_simples(self):
        dados = {"a": "hello", "b": "world"}
        resultado = concatenar_campos(dados, "a", "b", sep=" ")
        assert resultado == "hello world"

    def test_com_separador_custom(self):
        dados = {"a": "hello", "b": "world"}
        resultado = concatenar_campos(dados, "a", "b", sep="<br>")
        assert resultado == "hello<br>world"

    def test_com_lista(self):
        dados = {"a": "hello", "b": "world"}
        resultado = concatenar_campos(dados, ["a", "b"], sep=" ")
        assert resultado == "hello world"

    def test_ignorar_faltantes(self):
        dados = {"a": "hello"}
        resultado = concatenar_campos(dados, "a", "b_inexistente", sep=" ", ignorar_faltantes=True)
        assert resultado == "hello"

    def test_campo_faltante_sem_ignore(self):
        dados = {"a": "hello"}
        with pytest.raises(KeyError):
            concatenar_campos(dados, "a", "b_inexistente", sep=" ")

    def test_campo_none_com_ignore(self):
        dados = {"a": "hello", "b": None}
        resultado = concatenar_campos(dados, "a", "b", sep=" ", ignorar_faltantes=True)
        assert resultado == "hello"


class TestGetNested:
    def test_caminho_simples(self):
        dados = {"a": {"b": "valor"}}
        assert get_nested(dados, "a.b") == "valor"

    def test_caminho_com_indice(self):
        dados = {"a": ["x", "y", "z"]}
        assert get_nested(dados, "a[1]") == "y"

    def test_caminho_com_filtro(self):
        dados = {"a": [{"id": "pca", "val": 1}, {"id": "tsne", "val": 2}]}
        assert get_nested(dados, "a[id=pca].val") == 1

    def test_caminho_inexistente_com_default(self):
        dados = {"a": "valor"}
        assert get_nested(dados, "b.c", default="padrao") == "padrao"

    def test_caminho_inexistente_sem_default(self):
        dados = {"a": "valor"}
        with pytest.raises(KeyError):
            get_nested(dados, "b.c")


class TestBase64:
    def test_df_para_base64_e_volta(self):
        df = pd.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
        b64 = df_para_base64(df)
        assert isinstance(b64, str)
        df_result = decode_excel_base64_df(b64)
        assert list(df_result.columns) == ["col1", "col2"]
        assert len(df_result) == 3


class TestGerarColunasDetalhes:
    def test_gera_detalhes(self):
        df = pd.DataFrame({"idade": [25, 30], "nome": ["Ana", "Bob"]})
        detalhes = gerar_colunas_detalhes(df)
        assert len(detalhes) == 2
        assert detalhes[0]["nome_coluna"] == "idade"
        assert detalhes[0]["tipo_coluna"] == "Número"
        assert detalhes[1]["nome_coluna"] == "nome"
        assert detalhes[1]["tipo_coluna"] == "Texto"
