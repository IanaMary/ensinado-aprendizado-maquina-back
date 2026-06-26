"""Conteúdo educacional versionado dos elementos do pipeline.

A fonte da verdade são os JSON deste pacote (`modelos.json`, `metricas.json`,
`pre_processamento.json`, `coleta_dados.json`, `graficos.json`). O `loader`
semeia esse conteúdo no MongoDB de forma idempotente.
"""
from app.conteudo.loader import (
    CATEGORIAS,
    carregar_conteudo,
    montar_operacoes_upsert,
    seed_conteudo,
    validar_conteudo,
)
from app.conteudo.schema import Conteudo

__all__ = [
    "CATEGORIAS",
    "Conteudo",
    "carregar_conteudo",
    "montar_operacoes_upsert",
    "seed_conteudo",
    "validar_conteudo",
]
