"""Biblioteca versionada de regras da rubrica.

Cada regra tem `aplica` (a regra faz sentido NESTE desafio?) e `checa` (a montagem a
satisfaz?). A nota só considera as regras aplicáveis, então um desafio de agrupamento não
perde ponto por não imputar valores faltantes que não existem.

Os textos são o produto mais importante daqui: é o que o aluno lê ao errar e o que o tutor
reusa depois para explicar. Escreva-os em linguagem de sala de aula (ensino fundamental /
médio), dizendo o PORQUÊ e não só o que faltou.

Regras novas entram nesta lista; nada no router precisa mudar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.desafios.catalogo import LANES

# Modelos cuja qualidade depende da escala das colunas (distância ou gradiente).
# Árvores e ensembles de árvore ficam de fora de propósito: para eles escalar não muda nada.
MODELOS_SENSIVEIS_A_ESCALA = {
    "knn", "knn_regressor", "svm", "svm_linear", "svr",
    "mlp", "mlp_regressor", "perceptron", "sgd", "k_means",
}


@dataclass
class Contexto:
    """Tudo que as regras podem olhar. Nada aqui vem direto do corpo da requisição:
    `montagem` já chega normalizada (só lanes conhecidas, só strings)."""
    montagem: Dict[str, List[str]]
    gabarito: Dict[str, Any]
    pecas: Dict[str, Dict[str, Any]]
    ofertadas: Dict[str, str] = field(default_factory=dict)  # valor -> "util" | "distrator"

    # ------------------------------------------------------------------ helpers
    @property
    def tarefa(self) -> str:
        tarefa = (self.gabarito or {}).get("tarefa")
        return tarefa if isinstance(tarefa, str) else "classificacao"

    @property
    def dados(self) -> Dict[str, Any]:
        dados = (self.gabarito or {}).get("dados")
        return dados if isinstance(dados, dict) else {}

    @property
    def exige(self) -> List[str]:
        exige = (self.gabarito or {}).get("exige")
        if not isinstance(exige, list):
            return ["coleta", "modelo", "metrica"]
        return [lane for lane in exige if lane in LANES]

    def usadas(self, lane: str) -> List[str]:
        return list(self.montagem.get(lane) or [])

    def metas(self, lane: str) -> List[Dict[str, Any]]:
        """Metadados das peças que o aluno colocou na lane E pertencem a ela, na ordem
        escolhida por ele.

        A peça posta na etapa errada NÃO entra: senão uma métrica largada na coluna do
        modelo satisfazia `modelo-compativel` (ela não declara `tarefa`, logo "nada
        incompatível") e o aluno ganhava ponto por um pipeline que não existe.
        Peça desconhecida (fora do catálogo) segue ignorada — `sem-distrator` já cobre
        peça indevida, e uma regra não deve quebrar por dado velho.
        """
        return [self.pecas[v] for v in self.usadas(lane)
                if v in self.pecas and self.pecas[v].get("lane") == lane]

    def familias(self) -> List[str]:
        return [m.get("familia", "outro") for m in self.metas("pre_processamento")]

    def tem_familia(self, familia: str) -> bool:
        return familia in self.familias()

    def todas_usadas(self) -> List[str]:
        return [v for lane in LANES for v in self.usadas(lane)]


@dataclass(frozen=True)
class Regra:
    id: str
    peso: int
    titulo: str
    texto_ok: str
    texto_erro: str
    aplica: Callable[[Contexto], bool]
    checa: Callable[[Contexto], bool]


def _preencheu(ctx: Contexto, lane: str) -> bool:
    """A etapa recebeu peça DELA. Uma métrica na coluna do modelo não preenche a etapa do
    modelo — o pipeline continua sem quem aprende. Peça desconhecida (dado velho) conta:
    a dúvida não é do aluno."""
    return any(ctx.pecas.get(v, {}).get("lane", lane) == lane for v in ctx.usadas(lane))


def _lanes_vazias(ctx: Contexto) -> List[str]:
    return [lane for lane in ctx.exige if not _preencheu(ctx, lane)]


def _pecas_fora_de_lane(ctx: Contexto) -> List[str]:
    """Peças que o aluno colocou numa etapa que não é a delas. O sistema não impede o erro
    (é justamente o que se quer medir), então quem o registra é a rubrica."""
    return [v for lane in LANES for v in ctx.usadas(lane)
            if v in ctx.pecas and ctx.pecas[v].get("lane") != lane]


def _modelos_incompativeis(ctx: Contexto) -> List[Dict[str, Any]]:
    return [m for m in ctx.metas("modelo") if m.get("tarefa") and m["tarefa"] != ctx.tarefa]


def _metricas_incompativeis(ctx: Contexto) -> List[Dict[str, Any]]:
    """Métrica incompatível = grupo declarado diferente da tarefa. Quando o catálogo não
    declara o grupo, cai na lista de métricas compatíveis dos modelos usados (e, se nem
    isso existir, damos o benefício da dúvida em vez de punir por dado incompleto)."""
    compativeis_do_modelo = {
        valor
        for m in ctx.metas("modelo")
        for valor in (m.get("metricas") or [])
    }
    ruins = []
    for m in ctx.metas("metrica"):
        grupo = m.get("grupo")
        if grupo:
            if grupo != ctx.tarefa:
                ruins.append(m)
        elif compativeis_do_modelo and m["valor"] not in compativeis_do_modelo:
            ruins.append(m)
    return ruins


def _modelos_que_pedem_escala(ctx: Contexto) -> List[Dict[str, Any]]:
    return [m for m in ctx.metas("modelo") if m["valor"] in MODELOS_SENSIVEIS_A_ESCALA]


def _distratores_usados(ctx: Contexto) -> List[str]:
    return [v for v in ctx.todas_usadas() if ctx.ofertadas.get(v) == "distrator"]


def _indice_familia(ctx: Contexto, familia: str) -> Optional[int]:
    familias = ctx.familias()
    return familias.index(familia) if familia in familias else None


def _imputa_antes_de_escalar(ctx: Contexto) -> bool:
    i_imputacao = _indice_familia(ctx, "imputacao")
    i_escala = _indice_familia(ctx, "escala")
    if i_imputacao is None or i_escala is None:
        return True  # sem os dois blocos não há ordem para julgar
    return i_imputacao < i_escala


REGRAS: List[Regra] = [
    Regra(
        id="estrutura-minima",
        peso=3,
        titulo="O pipeline está completo",
        texto_ok="Teu pipeline tem todas as etapas que o problema pedia.",
        texto_erro=(
            "Faltou etapa no pipeline: ou a coluna ficou vazia, ou ela recebeu uma peça de "
            "outro tipo — e aí a etapa continua sem quem faz o trabalho dela. Sem todas as "
            "etapas o computador não consegue aprender e depois mostrar como se saiu: os "
            "dados entram, o modelo aprende e a métrica diz se ele acertou."
        ),
        aplica=lambda ctx: bool(ctx.exige),
        checa=lambda ctx: not _lanes_vazias(ctx),
    ),
    Regra(
        id="peca-na-etapa-certa",
        peso=2,
        titulo="Cada peça na etapa dela",
        texto_ok="Cada peça que usaste está na etapa a que pertence.",
        texto_erro=(
            "Alguma peça ficou numa coluna que não é dela. Cada coluna é uma etapa com um "
            "papel: a coleta traz os dados, o pré-processamento os prepara, o modelo aprende "
            "e a métrica mede o resultado. Reconhecer a que etapa cada bloco pertence é o "
            "primeiro passo para montar um pipeline que funciona."
        ),
        # Mesma guarda de `sem-distrator`: entregar o tabuleiro vazio não "acerta" a regra.
        aplica=lambda ctx: bool(ctx.todas_usadas()),
        checa=lambda ctx: not _pecas_fora_de_lane(ctx),
    ),
    Regra(
        id="modelo-compativel",
        peso=3,
        titulo="O modelo serve para esta tarefa",
        texto_ok="O modelo que escolheste é do tipo certo para este problema.",
        texto_erro=(
            "O modelo escolhido resolve outro tipo de problema. Modelo de classificação "
            "responde 'qual categoria?', de regressão responde 'qual número?' e de "
            "agrupamento acha grupos sem resposta certa combinada."
        ),
        aplica=lambda ctx: bool(ctx.metas("modelo")),
        checa=lambda ctx: not _modelos_incompativeis(ctx),
    ),
    Regra(
        id="metrica-compativel",
        peso=3,
        titulo="A métrica mede esta tarefa",
        texto_ok="A métrica que escolheste consegue avaliar este tipo de modelo.",
        texto_erro=(
            "A métrica escolhida não mede este tipo de problema. Acurácia conta acertos "
            "de categoria; R² e os erros médios medem distância até um número; silhueta "
            "avalia grupos. Trocar isso faz a avaliação não querer dizer nada."
        ),
        aplica=lambda ctx: bool(ctx.metas("metrica")),
        checa=lambda ctx: not _metricas_incompativeis(ctx),
    ),
    Regra(
        id="escala-antes-de-distancia",
        peso=2,
        titulo="Colunas na mesma escala para modelos de distância",
        texto_ok="Colocaste um bloco de escala, que é o que este modelo precisa.",
        texto_erro=(
            "Este modelo compara distâncias entre os exemplos, então a coluna com números "
            "maiores manda no resultado (idade 0–100 domina nota 0–10). Um bloco de escala "
            "põe todas as colunas no mesmo tamanho antes do modelo."
        ),
        aplica=lambda ctx: bool(_modelos_que_pedem_escala(ctx)),
        checa=lambda ctx: ctx.tem_familia("escala"),
    ),
    Regra(
        id="imputacao-quando-ha-faltantes",
        peso=2,
        titulo="Valores faltantes tratados",
        texto_ok="Trataste os valores faltantes antes de treinar.",
        texto_erro=(
            "Esta base tem células vazias, e o modelo não sabe o que fazer com vazio. "
            "Um bloco de preenchimento (imputação) completa esses buracos, por exemplo "
            "com a média ou o valor mais comum da coluna."
        ),
        aplica=lambda ctx: bool(ctx.dados.get("faltantes")),
        checa=lambda ctx: ctx.tem_familia("imputacao"),
    ),
    Regra(
        id="encoder-para-texto",
        peso=2,
        titulo="Colunas de texto convertidas em número",
        texto_ok="Converteste as colunas de texto em números, como o modelo precisa.",
        texto_erro=(
            "Esta base tem colunas de texto (como cidade ou cor) e os modelos só fazem "
            "conta com número. Um bloco de codificação transforma cada categoria em "
            "número sem inventar uma ordem que não existe."
        ),
        aplica=lambda ctx: bool(ctx.dados.get("texto")),
        checa=lambda ctx: ctx.tem_familia("encoder"),
    ),
    Regra(
        id="imputacao-antes-de-escala",
        peso=1,
        titulo="Ordem do pré-processamento",
        texto_ok="A ordem do pré-processamento está certa: primeiro preencher, depois escalar.",
        texto_erro=(
            "Escalar antes de preencher os vazios faz a conta da escala sair errada, porque "
            "ela é calculada sem parte dos dados. Primeiro preenche, depois escala."
        ),
        aplica=lambda ctx: ctx.tem_familia("imputacao") and ctx.tem_familia("escala"),
        checa=_imputa_antes_de_escalar,
    ),
    Regra(
        id="sem-distrator",
        peso=2,
        titulo="Só as peças que fazem sentido",
        texto_ok="Não usaste nenhuma peça desnecessária.",
        texto_erro=(
            "Entraram peças que este problema não pedia. Nem todo bloco disponível ajuda: "
            "escolher o que NÃO usar faz parte de montar um pipeline bom."
        ),
        # Só vale se o aluno montou ALGO: sem isto, entregar o tabuleiro vazio
        # "satisfaria" a regra (não usou distrator porque não usou nada) e ganharia ponto.
        aplica=lambda ctx: "distrator" in ctx.ofertadas.values() and bool(ctx.todas_usadas()),
        checa=lambda ctx: not _distratores_usados(ctx),
    ),
]

REGRAS_POR_ID: Dict[str, Regra] = {r.id: r for r in REGRAS}


def regras_aplicaveis(ctx: Contexto) -> List[Regra]:
    """Regras que valem para ESTE desafio (as demais nem entram no total de pontos)."""
    aplicaveis = []
    for regra in REGRAS:
        try:
            if regra.aplica(ctx):
                aplicaveis.append(regra)
        except Exception:
            continue  # regra defeituosa não invalida a correção inteira
    return aplicaveis
