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


class Fundamentos(BaseModel):
    """Bloco formal do modo Avançado: o que o método é, matematicamente.

    Existe porque a "descrição técnica" sozinha é um parágrafo — não sustenta um público que
    vai até o primeiro ano da graduação. Aqui entram fórmula, o que o algoritmo otimiza, os
    pressupostos que ele assume e o custo computacional.
    """

    model_config = ConfigDict(extra="allow")

    formula: Optional[str] = None
    otimiza: Optional[str] = None           # a função objetivo, em uma frase
    pressupostos: Optional[List[str]] = None
    complexidade: Optional[str] = None      # treino e predição, em n (amostras) e d (atributos)
    leitura: Optional[List[str]] = None     # referência canônica (autor, ano, título)


class Pratica(BaseModel):
    """Bloco operacional do modo Avançado: como usar isso sem se enganar."""

    model_config = ConfigDict(extra="allow")

    codigo: Optional[str] = None            # pipeline sklearn completo (CV / busca)
    tuning: Optional[List[str]] = None      # o que ajustar primeiro e por quê
    armadilhas: Optional[List[str]] = None
    diagnostico: Optional[List[str]] = None  # como perceber que deu errado


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
    # Avançado: os dois blocos que fazem o modo ser de fato avançado
    fundamentos: Optional[Fundamentos] = None
    pratica: Optional[Pratica] = None
    midia: Optional[List[Midia]] = None
    referencias: Optional[List[Referencia]] = None
