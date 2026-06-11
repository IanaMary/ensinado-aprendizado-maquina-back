from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing_extensions import Annotated
from typing import Optional, List
from bson.errors import InvalidId
from app.schemas.schemas import ConfiguracaoColetaRequest
import pandas as pd
import base64
from io import StringIO, BytesIO
from bson import ObjectId
from app.database import arquivos, configuracoes_treinamento
from app.deps import train_test_split
from app.funcoes_genericas.funcoes_genericas import gerar_colunas_detalhes, df_para_base64, decode_excel_base64_df, converter_numpy
from app.utils.seed import get_sklearn_random_state

router = APIRouter()

SEPARADORES = {
    "virgula": ",",
    "ponto_virgula": ";",
    "tab": "\t",
    "pipe": "|",
}


@router.post("/csv/preview")
async def preview_csv(
    file: Annotated[UploadFile, File()],
    separador: Annotated[str, Form()] = "virgula",
    encoding: Annotated[str, Form()] = "utf-8",
    linhas: Annotated[int, Form()] = 10,
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Arquivo deve ser CSV")

    content = await file.read()
    sep = SEPARADORES.get(separador, ",")

    try:
        text = content.decode(encoding)
        df = pd.read_csv(StringIO(text), sep=sep, nrows=linhas)
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
            df = pd.read_csv(StringIO(text), sep=sep, nrows=linhas)
            encoding = "latin-1"
        except Exception as e:
            raise HTTPException(400, f"Erro ao decodificar arquivo: {e}")
    except Exception as e:
        raise HTTPException(400, f"Erro ao ler CSV: {e}")

    colunas = df.columns.tolist()
    preview = df.head(linhas).to_dict(orient="records")
    colunas_detalhes = gerar_colunas_detalhes(df)

    return {
        "colunas": colunas,
        "colunas_detalhes": colunas_detalhes,
        "preview": preview,
        "num_linhas_preview": len(preview),
        "separador_usado": separador,
        "encoding_usado": encoding,
    }


@router.post("/csv")
async def upload_csv(
    tipo: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    test_size: Optional[float] = Form(0.2),
    id_coleta: Optional[str] = Form(None),
    separador: Annotated[str, Form()] = "virgula",
    encoding: Annotated[str, Form()] = "utf-8",
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Arquivo deve ser CSV")

    content = await file.read()
    sep = SEPARADORES.get(separador, ",")

    try:
        text = content.decode(encoding)
        df = pd.read_csv(StringIO(text), sep=sep)
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
            df = pd.read_csv(StringIO(text), sep=sep)
        except Exception as e:
            raise HTTPException(400, f"Erro ao decodificar arquivo: {e}")
    except Exception as e:
        raise HTTPException(400, f"Erro ao ler CSV: {e}")

    content_b64 = base64.b64encode(content).decode("utf-8")

    if tipo == "teste" and id_coleta:
        await arquivos.update_one(
            {"_id": ObjectId(id_coleta)},
            {"$set": {
                "arquivo_nome_teste": file.filename,
                "content_teste_base64": content_b64,
            }}
        )

        doc = await arquivos.find_one({"_id": ObjectId(id_coleta)})
        config = await configuracoes_treinamento.find_one({"id_coleta": ObjectId(id_coleta)})

        df_treino = decode_excel_base64_df(doc.get("content_treino_base64", ""))
        df_teste = df

        atributos = doc.get("atributos", {})
        colunas_detalhes = doc.get("colunas_detalhes", [])

        return converter_numpy({
            "id_coleta": str(id_coleta),
            "id_configuracoes_treinamento": str(config["_id"]) if config else None,
            "filename": file.filename,
            "arquivo_nome_treino": doc.get("arquivo_nome_treino"),
            "arquivo_nome_teste": file.filename,
            "tipo": tipo,
            "num_linhas_total": int(df_treino.shape[0] + df_teste.shape[0]),
            "num_linhas_treino": int(df_treino.shape[0]),
            "num_linhas_teste": int(df_teste.shape[0]),
            "num_colunas": int(df.shape[1]),
            "colunas": df.columns.tolist(),
            "colunas_detalhes": colunas_detalhes,
            "atributos": atributos,
            "preview_treino": df_treino.head(5).to_dict(orient="records"),
            "preview_teste": df_teste.head(5).to_dict(orient="records"),
            "target": config.get("target") if config else None,
            "tipo_target": config.get("tipo_target") if config else None,
            "prever_categoria": config.get("prever_categoria", False) if config else False,
            "dados_rotulados": config.get("dados_rotulados", False) if config else False,
        })

    colunas_detalhes = gerar_colunas_detalhes(df)
    atributos = {coluna: False for coluna in df.columns}

    content_completo_b64 = content_b64

    df_treino, df_teste = train_test_split(df, test_size=test_size or 0.2, random_state=get_sklearn_random_state() or 42)

    content_treino_b64 = df_para_base64(df_treino)
    content_teste_b64 = df_para_base64(df_teste)

    doc_arquivo = {
        "arquivo_nome_treino": file.filename,
        "content_completo_base64": content_completo_b64,
        "content_treino_base64": content_treino_b64,
        "content_teste_base64": content_teste_b64,
        "num_linhas_total": df.shape[0],
        "num_colunas": df.shape[1],
        "atributos": atributos,
        "colunas_detalhes": colunas_detalhes,
    }

    result = await arquivos.insert_one(doc_arquivo)
    id_coleta_novo = str(result.inserted_id)

    doc_config = {
        "id_coleta": ObjectId(id_coleta_novo),
        "test_size": test_size or 0.2,
        "atributos": atributos,
        "tipo_target": None,
        "target": None,
        "prever_categoria": False,
        "dados_rotulados": False,
    }

    result_config = await configuracoes_treinamento.insert_one(doc_config)
    id_configuracoes_treinamento = str(result_config.inserted_id)

    return converter_numpy({
        "id_coleta": id_coleta_novo,
        "id_configuracoes_treinamento": id_configuracoes_treinamento,
        "filename": file.filename,
        "arquivo_nome_treino": file.filename,
        "tipo": tipo,
        "num_linhas_total": df.shape[0],
        "num_linhas_treino": df_treino.shape[0],
        "num_linhas_teste": df_teste.shape[0],
        "num_colunas": df.shape[1],
        "colunas": df.columns.tolist(),
        "colunas_detalhes": colunas_detalhes,
        "atributos": atributos,
        "preview_treino": df_treino.head(5).to_dict(orient="records"),
        "preview_teste": df_teste.head(5).to_dict(orient="records"),
        "prever_categoria": False,
        "dados_rotulados": False,
    })
