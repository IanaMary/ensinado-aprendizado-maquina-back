"""Modelo Pydantic do `conteudo` educacional dos elementos do pipeline.

Usado para **validar** os JSON canônicos versionados em `app/conteudo/*.json`
(falha em CI/teste se o repo tiver conteúdo malformado). NÃO é aplicado no
runtime das rotas: os consumidores (ex.: `app/tutor_kb.py`, o frontend) leem o
`conteudo` como dict de forma defensiva, então o schema é permissivo
(`extra="allow"`, todos os campos opcionais) para nunca rejeitar dados reais nem
quebrar com campos futuros.
"""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict


class Conceito(BaseModel):
    model_config = ConfigDict(extra="allow")
    nome: Optional[str] = None
    desc: Optional[str] = None


class HiperparametroDoc(BaseModel):
    model_config = ConfigDict(extra="allow")
    nome: Optional[str] = None
    descricao: Optional[str] = None
    tipo: Optional[str] = None
    default: Any = None
    efeito: Optional[str] = None
    quando_ajustar: Optional[str] = None
    opcoes: Optional[List[Any]] = None


class Midia(BaseModel):
    model_config = ConfigDict(extra="allow")
    tipo: Optional[str] = None
    url: Optional[str] = None
    legenda: Optional[str] = None
    fonte: Optional[str] = None


class Referencia(BaseModel):
    model_config = ConfigDict(extra="allow")
    titulo: Optional[str] = None
    autor: Optional[str] = None
    url: Optional[str] = None
    tipo: Optional[str] = None
    citacao: Optional[str] = None


class Conteudo(BaseModel):
    """Conteúdo educacional de um elemento do pipeline (modo Básico + Avançado)."""

    model_config = ConfigDict(extra="allow")

    titulo: Optional[str] = None
    # Avançado: descrição técnica
    descricao: Optional[str] = None
    # Básico: explicação simples/lúdica
    resumo_basico: Optional[str] = None
    intuicao: Optional[str] = None
    exemplo: Optional[str] = None
    # Avançado: código Python (renderizado colorido no front)
    exemplo_codigo: Optional[str] = None
    # Avançado: fórmula matemática
    formula: Optional[str] = None
    conceitos: Optional[List[Conceito]] = None
    quandoUsar: Optional[List[str]] = None
    naoUsarQuando: Optional[List[str]] = None
    vantagens: Optional[List[str]] = None
    desvantagens: Optional[List[str]] = None
    dicas: Optional[List[str]] = None
    hiperparametros_doc: Optional[List[HiperparametroDoc]] = None
    link_sklearn: Optional[str] = None
    # NOVO: link para a doc do Yellowbrick (gráficos e modelos com visualização)
    link_yellowbrick: Optional[str] = None
    midia: Optional[List[Midia]] = None
    referencias: Optional[List[Referencia]] = None
