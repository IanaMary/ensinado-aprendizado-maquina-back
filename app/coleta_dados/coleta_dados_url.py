"""Ingestão de dados a partir de uma URL (download server-side, anti-SSRF).

O servidor baixa o recurso (evita CORS), valida o endereço contra alvos internos/
privados (defesa contra SSRF), faz o parse (CSV/TSV/JSON/Excel) e armazena no mesmo
formato dos uploads (`arquivos` + `configuracoes_treinamento`), devolvendo a mesma
resposta do `upload_csv` — para o front consumir igual a um arquivo enviado.
"""
import base64
import ipaddress
import socket
from io import BytesIO, StringIO
from typing import Any, Dict
from urllib.parse import urlparse

import httpx
import pandas as pd
from bson import ObjectId
from fastapi import APIRouter, Body, HTTPException

from app.database import arquivos, configuracoes_treinamento
from app.deps import train_test_split
from app.funcoes_genericas.funcoes_genericas import (
    converter_numpy,
    df_para_base64,
    gerar_colunas_detalhes,
)
from app.utils.seed import get_sklearn_random_state

router = APIRouter()

MAX_BYTES = 50 * 1024 * 1024  # 50 MB
TIMEOUT = 30.0


def validar_url_segura(url: str) -> None:
    """Bloqueia SSRF: só http/https e endereços públicos. Lança HTTPException(400)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="A URL deve usar http ou https.")
    host = p.hostname
    if not host:
        raise HTTPException(status_code=400, detail="URL inválida.")
    porta = p.port or (443 if p.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, porta, proto=socket.IPPROTO_TCP)
    except Exception:
        raise HTTPException(status_code=400, detail="Não foi possível resolver o endereço da URL.")
    if not infos:
        raise HTTPException(status_code=400, detail="Não foi possível resolver o endereço da URL.")
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise HTTPException(status_code=400, detail="Endereço não permitido (interno/privado).")


def parse_conteudo_df(content: bytes, url: str, content_type: str) -> pd.DataFrame:
    nome = (urlparse(url).path or "").lower()
    ct = (content_type or "").lower()
    if nome.endswith((".xlsx", ".xls")) or "spreadsheet" in ct or "excel" in ct:
        return pd.read_excel(BytesIO(content), engine="openpyxl")
    if nome.endswith(".json") or "json" in ct:
        return pd.read_json(BytesIO(content))
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    primeira = text.split("\n", 1)[0]
    sep = "\t" if nome.endswith(".tsv") else (";" if primeira.count(";") > primeira.count(",") else ",")
    return pd.read_csv(StringIO(text), sep=sep)


@router.post("/url")
async def ingerir_url(payload: Dict[str, Any] = Body(...)):
    url = ((payload or {}).get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Informe a URL.")
    test_size = payload.get("test_size", 0.2) or 0.2
    shuffle = bool(payload.get("shuffle", True))
    stratify = bool(payload.get("stratify", False))

    validar_url_segura(url)

    # Download server-side: sem seguir redirects (evita rebind p/ alvo interno) e com teto de tamanho.
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=TIMEOUT) as client:
            async with client.stream("GET", url) as resp:
                if resp.is_redirect:
                    raise HTTPException(status_code=400, detail="A URL redireciona; use o link direto do arquivo.")
                if resp.status_code >= 400:
                    raise HTTPException(status_code=400, detail=f"Falha ao baixar (HTTP {resp.status_code}).")
                content = b""
                async for chunk in resp.aiter_bytes():
                    content += chunk
                    if len(content) > MAX_BYTES:
                        raise HTTPException(status_code=413, detail="Arquivo muito grande (limite 50 MB).")
                content_type = resp.headers.get("content-type", "")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao baixar a URL: {e}")

    try:
        df = parse_conteudo_df(content, url, content_type)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Não foi possível ler os dados da URL: {e}")
    if df.empty or len(df.columns) == 0:
        raise HTTPException(status_code=400, detail="O conteúdo da URL não tem dados tabulares.")

    if not 0 < test_size < 1:
        test_size = 0.2
    colunas_detalhes = gerar_colunas_detalhes(df)
    atributos = {c: False for c in df.columns}
    df_treino, df_teste = train_test_split(
        df, test_size=test_size, random_state=get_sklearn_random_state() or 42, shuffle=shuffle
    )
    nome_arq = (urlparse(url).path.rsplit("/", 1)[-1]) or "dados_url"

    doc_arquivo = {
        "arquivo_nome_treino": nome_arq,
        "content_completo_base64": base64.b64encode(content).decode("utf-8"),
        "content_treino_base64": df_para_base64(df_treino),
        "content_teste_base64": df_para_base64(df_teste),
        "num_linhas_total": int(df.shape[0]),
        "num_colunas": int(df.shape[1]),
        "atributos": atributos,
        "colunas_detalhes": colunas_detalhes,
        "origem_url": url,
    }
    result = await arquivos.insert_one(doc_arquivo)
    id_coleta = str(result.inserted_id)

    doc_config = {
        "id_coleta": ObjectId(id_coleta), "test_size": test_size, "shuffle": shuffle,
        "stratify": stratify, "atributos": atributos, "tipo_target": None, "target": None,
        "prever_categoria": False, "dados_rotulados": False,
    }
    rconf = await configuracoes_treinamento.insert_one(doc_config)

    return converter_numpy({
        "id_coleta": id_coleta,
        "id_configuracoes_treinamento": str(rconf.inserted_id),
        "filename": nome_arq, "arquivo_nome_treino": nome_arq, "tipo": "treino",
        "num_linhas_total": df.shape[0], "num_linhas_treino": df_treino.shape[0], "num_linhas_teste": df_teste.shape[0],
        "num_colunas": df.shape[1], "colunas": df.columns.tolist(), "colunas_detalhes": colunas_detalhes,
        "atributos": atributos,
        "preview_treino": df_treino.head(5).to_dict(orient="records"),
        "preview_teste": df_teste.head(5).to_dict(orient="records"),
        "prever_categoria": False, "dados_rotulados": False, "shuffle": shuffle, "stratify": stratify,
        "origem_url": url,
    })
