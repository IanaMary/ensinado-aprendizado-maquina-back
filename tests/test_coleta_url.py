"""Testes da ingestão por URL — foco no anti-SSRF (segurança)."""
from unittest.mock import patch
import pytest
from fastapi import HTTPException

from app.coleta_dados.coleta_dados_url import validar_url_segura


def _gai(ip):
    return [(2, 1, 6, "", (ip, 443))]


def test_url_scheme_invalido():
    with pytest.raises(HTTPException) as e:
        validar_url_segura("ftp://exemplo/dados.csv")
    assert e.value.status_code == 400


def test_url_sem_host():
    with pytest.raises(HTTPException):
        validar_url_segura("http:///dados.csv")


@pytest.mark.parametrize("ip", ["10.0.0.5", "127.0.0.1", "192.168.1.10", "172.16.5.5", "169.254.169.254", "::1"])
def test_bloqueia_enderecos_internos(ip):
    with patch("app.coleta_dados.coleta_dados_url.socket.getaddrinfo", return_value=_gai(ip)):
        with pytest.raises(HTTPException) as e:
            validar_url_segura("http://alvo-interno/dados.csv")
        assert e.value.status_code == 400
        assert "permitido" in e.value.detail.lower() or "interno" in e.value.detail.lower()


def test_permite_endereco_publico():
    with patch("app.coleta_dados.coleta_dados_url.socket.getaddrinfo", return_value=_gai("93.184.216.34")):
        validar_url_segura("https://exemplo.com/dados.csv")  # não levanta


def test_dns_nao_resolve_400():
    with patch("app.coleta_dados.coleta_dados_url.socket.getaddrinfo", side_effect=OSError):
        with pytest.raises(HTTPException) as e:
            validar_url_segura("https://nao-existe.invalido/x.csv")
        assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_endpoint_rejeita_url_interna(client, mock_db, auth_headers):
    with patch("app.coleta_dados.coleta_dados_url.socket.getaddrinfo", return_value=_gai("169.254.169.254")):
        resp = await client.post(
            "/coleta_dados/url",
            json={"url": "http://169.254.169.254/latest/meta-data/"},
            headers=auth_headers,
        )
    assert resp.status_code == 400
