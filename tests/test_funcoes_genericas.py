import pytest
import json
import math
import numpy as np
from app.funcoes_genericas.funcoes_genericas import (
    mapear_tipo,
    serialize_doc,
    concatenar_campos,
    get_nested,
    df_para_base64,
    decode_excel_base64_df,
    gerar_colunas_detalhes,
    validar_xlsx,
    converter_numpy,
)
from bson import ObjectId
import pandas as pd
from fastapi import HTTPException


class TestConverterNumpy:
    def test_converte_tipos_numpy(self):
        out = converter_numpy({"a": np.int64(3), "b": np.float64(1.5), "c": [np.int32(2)]})
        assert out == {"a": 3, "b": 1.5, "c": [2]}
        assert isinstance(out["a"], int) and isinstance(out["b"], float)

    def test_nan_e_infinito_viram_none(self):
        """NaN/Infinity não são JSON-compatíveis (Starlette usa allow_nan=False)."""
        out = converter_numpy({
            "nan_np": np.float64("nan"),
            "inf_np": np.float64("inf"),
            "nan_py": float("nan"),
            "neg_inf": float("-inf"),
            "ok": 2.0,
        })
        assert out["nan_np"] is None
        assert out["inf_np"] is None
        assert out["nan_py"] is None
        assert out["neg_inf"] is None
        assert out["ok"] == 2.0
        # Serializável com allow_nan=False, igual ao Starlette
        json.dumps(out, allow_nan=False)


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

    def test_filtro_sem_match_sem_default(self):
        dados = {"a": [{"id": "pca", "val": 1}]}
        with pytest.raises(KeyError, match="Nenhum item corresponde ao filtro"):
            get_nested(dados, "a[id=tsne].val")

    def test_filtro_sem_match_com_default(self):
        dados = {"a": [{"id": "pca", "val": 1}]}
        assert get_nested(dados, "a[id=tsne].val", default="padrao") == "padrao"


class TestBase64:
    def test_df_para_base64_e_volta(self):
        df = pd.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
        b64 = df_para_base64(df)
        assert isinstance(b64, str)
        df_result = decode_excel_base64_df(b64)
        assert list(df_result.columns) == ["col1", "col2"]
        assert len(df_result) == 3


class TestValidarExcel:
    def test_aceita_xls_e_xlsx(self):
        class FakeFile:
            def __init__(self, filename):
                self.filename = filename

        validar_xlsx(FakeFile("dados.xls"), "treino")
        validar_xlsx(FakeFile("dados.xlsx"), "treino")

    def test_rejeita_extensao_invalida(self):
        class FakeFile:
            filename = "dados.csv"

        with pytest.raises(HTTPException):
            validar_xlsx(FakeFile(), "treino")


class TestGerarColunasDetalhes:
    def test_gera_detalhes(self):
        df = pd.DataFrame({"idade": [25, 30], "nome": ["Ana", "Bob"]})
        detalhes = gerar_colunas_detalhes(df)
        assert len(detalhes) == 2
        assert detalhes[0]["nome_coluna"] == "idade"
        assert detalhes[0]["tipo_coluna"] == "Número"
        assert detalhes[1]["nome_coluna"] == "nome"
        assert detalhes[1]["tipo_coluna"] == "Texto"
