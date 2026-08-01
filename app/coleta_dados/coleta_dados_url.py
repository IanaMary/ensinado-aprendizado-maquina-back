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
from app.security import id_usuario_atual
from app.coleta_dados.configuracao_treinamento import aviso_estratificacao, dividir_dataframe
from app.schemas.schemas import ReDivisaoColetaRequest
from app.funcoes_genericas.funcoes_genericas import (
    converter_numpy,
    df_para_base64,
    gerar_colunas_detalhes,
)

router = APIRouter()

MAX_BYTES = 50 * 1024 * 1024  # 50 MB
TIMEOUT = 30.0


def _ip_bloqueado(ip: ipaddress._BaseAddress) -> bool:
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified)


def validar_url_segura(url: str) -> str:
    """Bloqueia SSRF: só http/https e endereços públicos. Lança HTTPException(400).

    Retorna o IP validado (string) para ser FIXADO na conexão — sem isto o httpx
    reresolvia o host por conta própria e um registro DNS de TTL baixo podia
    responder público na validação e 127.0.0.1/169.254.169.254 no fetch (rebind)."""
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
    ip_validado = None
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        # Rejeita se QUALQUER resolução for interna (defesa contra registros mistos).
        if _ip_bloqueado(ip):
            raise HTTPException(status_code=400, detail="Endereço não permitido (interno/privado).")
        if ip_validado is None:
            ip_validado = info[4][0]
    if ip_validado is None:
        raise HTTPException(status_code=400, detail="Não foi possível resolver o endereço da URL.")
    return ip_validado


def _cliente_com_ip_fixo(host: str, ip: str):
    """AsyncClient httpx que resolve `host` SEMPRE para o `ip` já validado (pin),
    fechando a janela de DNS rebinding entre a validação e o fetch. SNI/Host
    seguem o hostname original (TLS/vhost continuam corretos)."""
    async def _resolver_fixo(_):
        return ip

    class _TransportePinado(httpx.AsyncHTTPTransport):
        async def handle_async_request(self, request):
            if request.url.host == host:
                request.extensions = {**dict(request.extensions or {}),
                                      "sni_hostname": host}
                request.url = request.url.copy_with(host=ip)
                request.headers["Host"] = host
            return await super().handle_async_request(request)

    return httpx.AsyncClient(follow_redirects=False, timeout=TIMEOUT,
                             transport=_TransportePinado())


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

    ip_validado = validar_url_segura(url)
    host = urlparse(url).hostname

    # Download server-side: IP FIXADO no valor validado (anti-rebind), sem seguir
    # redirects (evita salto p/ alvo interno) e com teto de tamanho.
    try:
        async with _cliente_com_ip_fixo(host, ip_validado) as client:
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
    # Mesmo divisor das outras portas. Na ingestão por URL ainda não há alvo escolhido, então
    # a estratificação não se aplica aqui — antes o pedido era ignorado em silêncio e a config
    # gravava `stratify: true`, mentindo sobre o que aconteceu.
    df_treino, df_teste, estratificou = dividir_dataframe(
        df, ReDivisaoColetaRequest(test_size=test_size, shuffle=shuffle, stratify=stratify, target=None)
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
        "usuario_id": id_usuario_atual(),
    }
    result = await arquivos.insert_one(doc_arquivo)
    id_coleta = str(result.inserted_id)

    doc_config = {
        "id_coleta": ObjectId(id_coleta), "test_size": test_size, "shuffle": shuffle,
        "stratify": estratificou, "atributos": atributos, "tipo_target": None, "target": None,
        "prever_categoria": False, "dados_rotulados": False,
        "usuario_id": id_usuario_atual(),
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
        "prever_categoria": False, "dados_rotulados": False, "shuffle": shuffle,
        "stratify": estratificou,
        "aviso_estratificacao": aviso_estratificacao(bool(stratify), estratificou),
        "origem_url": url,
    })
