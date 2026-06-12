from fastapi import APIRouter, HTTPException
from bson import ObjectId

from app.database import arquivos, configuracoes_treinamento
from app.deps import train_test_split
from app.funcoes_genericas.funcoes_genericas import df_para_base64, converter_numpy
from app.schemas.schemas import ConfiguracaoColetaRequest, ReDivisaoColetaRequest
from app.utils.seed import get_sklearn_random_state
import pandas as pd
import base64
from io import BytesIO, StringIO

router = APIRouter()


def validar_object_id(valor: str) -> ObjectId:
    if not ObjectId.is_valid(valor):
        raise HTTPException(status_code=400, detail="ID inválido.")
    return ObjectId(valor)


def decode_base64_df(base64_string: str) -> pd.DataFrame:
    if not base64_string:
        return pd.DataFrame()
    try:
        binary = base64.b64decode(base64_string)
        try:
            return pd.read_excel(BytesIO(binary), engine="openpyxl")
        except Exception:
            text = binary.decode("utf-8")
            sep = ";" if ";" in text.split("\n")[0] else ","
            return pd.read_csv(StringIO(text), sep=sep)
    except Exception:
        return pd.DataFrame()


def dividir_dataframe(df: pd.DataFrame, config: ReDivisaoColetaRequest) -> tuple[pd.DataFrame, pd.DataFrame]:
    stratify = None
    if config.stratify and config.target and config.target in df.columns:
        stratify = df[config.target]

    try:
        return train_test_split(
            df,
            test_size=config.test_size,
            random_state=get_sklearn_random_state() or 42,
            shuffle=config.shuffle,
            stratify=stratify if config.shuffle else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Não foi possível dividir os dados com essa configuração: {exc}")


@router.put("/{tipo}/{configurar_treinamento_id}")
async def configurar_treinamento(configurar_treinamento_id: str, config: ConfiguracaoColetaRequest):
    config_oid = validar_object_id(configurar_treinamento_id)
    config_doc = await configuracoes_treinamento.find_one({"_id": config_oid})

    if not config_doc:
        raise HTTPException(status_code=404, detail="Configuração não encontrada.")

    id_coleta = config_doc.get("id_coleta")
    tipo_target = None

    if id_coleta and config.target:
        resultado = await arquivos.find_one(
            {
                "_id": ObjectId(id_coleta),
                "colunas_detalhes.nome_coluna": config.target
            },
            {
                "colunas_detalhes.$": 1
            }
        )
        if resultado and "colunas_detalhes" in resultado:
            coluna_encontrada = resultado["colunas_detalhes"][0]
            tipo_target = coluna_encontrada.get("tipo_coluna")

    update_data = {
        "target": config.target,
        "atributos": config.atributos,
        "tipo_target": tipo_target,
        "prever_categoria": config.prever_categoria,
        "dados_rotulados": config.dados_rotulados,
        "shuffle": config.shuffle,
        "stratify": config.stratify,
    }

    await configuracoes_treinamento.update_one(
        {"_id": config_oid},
        {"$set": update_data}
    )

    return {
        "mensagem": "Configuração salva com sucesso.",
        "tipo_target": tipo_target
    }


@router.get("/{tipo}/{configurar_treinamento_id}")
async def get_configuracoe(configurar_treinamento_id: str):
    config_oid = validar_object_id(configurar_treinamento_id)
    config_doc = await configuracoes_treinamento.find_one({"_id": config_oid})

    if not config_doc:
        raise HTTPException(status_code=404, detail="Configuração de treinamento não encontrada.")

    id_coleta = config_doc.get("id_coleta")
    if not id_coleta:
        raise HTTPException(status_code=400, detail="Campo 'id_coleta' não encontrado na configuração.")

    try:
        coleta_doc = await arquivos.find_one({"_id": ObjectId(id_coleta)})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao buscar coleta: {str(e)}")

    if not coleta_doc:
        raise HTTPException(status_code=404, detail="Documento de coleta não encontrado.")

    df_treino = decode_base64_df(coleta_doc.get("content_treino_base64", ""))
    df_teste = decode_base64_df(coleta_doc.get("content_teste_base64", ""))

    preview_treino = df_treino.head(5).to_dict(orient="records")
    preview_teste = df_teste.head(5).to_dict(orient="records")

    colunas = coleta_doc.get("colunas")
    if isinstance(colunas, dict):
        colunas = list(colunas.keys())
    elif colunas is None:
        colunas = []

    return {
        "id_coleta": str(coleta_doc["_id"]),
        "tipo": coleta_doc.get("tipo"),
        "arquivo_nome_treino": coleta_doc.get("arquivo_nome_treino"),
        "arquivo_nome_teste": coleta_doc.get("arquivo_nome_teste"),
        "target": config_doc.get("target"),
        "tipo_target": config_doc.get("tipo_target"),
        "atributos": config_doc.get("atributos"),
        "preview_treino": preview_treino,
        "preview_teste": preview_teste,
        "colunas_detalhes": coleta_doc.get("colunas_detalhes"),
        "num_linhas_treino": df_treino.shape[0],
        "num_linhas_teste": df_teste.shape[0],
        "num_linhas_total": df_treino.shape[0] + df_teste.shape[0],
        "prever_categoria": config_doc.get("prever_categoria"),
        "dados_rotulados": config_doc.get("dados_rotulados"),
        "shuffle": config_doc.get("shuffle", True),
        "stratify": config_doc.get("stratify", False),
    }


@router.post("/{tipo}/{configurar_treinamento_id}/redividir")
async def redividir_coleta(configurar_treinamento_id: str, config: ReDivisaoColetaRequest):
    if not 0 < config.test_size < 1:
        raise HTTPException(status_code=400, detail="test_size deve estar entre 0 e 1.")

    config_oid = validar_object_id(configurar_treinamento_id)
    config_doc = await configuracoes_treinamento.find_one({"_id": config_oid})
    if not config_doc:
        raise HTTPException(status_code=404, detail="Configuração não encontrada.")

    id_coleta = config_doc.get("id_coleta")
    coleta_doc = await arquivos.find_one({"_id": ObjectId(id_coleta)})
    if not coleta_doc:
        raise HTTPException(status_code=404, detail="Documento de coleta não encontrado.")

    df_completo = decode_base64_df(coleta_doc.get("content_completo_base64") or coleta_doc.get("content_treino_base64", ""))
    if df_completo.empty:
        raise HTTPException(status_code=400, detail="Conteúdo completo da coleta não encontrado.")

    df_treino, df_teste = dividir_dataframe(df_completo, config)
    content_treino_b64 = df_para_base64(df_treino)
    content_teste_b64 = df_para_base64(df_teste)

    await arquivos.update_one(
        {"_id": ObjectId(id_coleta)},
        {"$set": {
            "content_treino_base64": content_treino_b64,
            "content_teste_base64": content_teste_b64,
            "num_linhas_treino": int(df_treino.shape[0]),
            "num_linhas_teste": int(df_teste.shape[0]),
        }},
    )

    update_config = {
        "test_size": config.test_size,
        "shuffle": config.shuffle,
        "stratify": config.stratify,
    }
    if config.target is not None:
        update_config["target"] = config.target

    await configuracoes_treinamento.update_one(
        {"_id": config_oid},
        {"$set": update_config},
    )

    return converter_numpy({
        "id_coleta": str(id_coleta),
        "id_configuracoes_treinamento": str(config_oid),
        "arquivo_nome_treino": coleta_doc.get("arquivo_nome_treino"),
        "arquivo_nome_teste": "",
        "num_linhas_total": int(df_completo.shape[0]),
        "num_linhas_treino": int(df_treino.shape[0]),
        "num_linhas_teste": int(df_teste.shape[0]),
        "num_colunas": int(df_completo.shape[1]),
        "colunas": df_completo.columns.tolist(),
        "colunas_detalhes": coleta_doc.get("colunas_detalhes"),
        "atributos": config_doc.get("atributos"),
        "preview_treino": df_treino.head(5).to_dict(orient="records"),
        "preview_teste": df_teste.head(5).to_dict(orient="records"),
        "target": config.target if config.target is not None else config_doc.get("target"),
        "tipo_target": config_doc.get("tipo_target"),
        "prever_categoria": config_doc.get("prever_categoria", False),
        "dados_rotulados": config_doc.get("dados_rotulados", False),
        "shuffle": config.shuffle,
        "stratify": config.stratify,
    })
