# Evolução do aluno na mesma base

Responde "melhorei?" **sem dar nota absoluta ao modelo**. Métrica crua não é comparável entre
bases (acurácia 0,92 é fraca no Iris e ótima no Titanic), então a leitura é sempre relativa a
duas réguas: o **chute burro** da base e as **tentativas anteriores do próprio aluno**.

Justificativa pedagógica e telas: `../../docs/dissertacao/04-desafios-avaliacao-e-divisao.md`.

## Onde fica

| Arquivo | Responsabilidade |
|---|---|
| `app/metricas/resultado.py` | Leitura dos resultados gravados (rótulo × slug) + **chute burro** + métrica padrão por tarefa. **Extraído de `turmas.py`** — ranking e evolução usam a mesma implementação. |
| `app/pipelines_evolucao.py` | Agrupa por base, ordena cronologicamente, calcula deltas e o que mudou entre tentativas. |
| `app/routers/pipelines.py` | `GET /pipelines/evolucao`. |
| `.../modals/metrica-avaliacao/` (frontend) | Bloco "Sua evolução nesta base" no resultado da avaliação. |

## Rota

```
GET /pipelines/evolucao?dataset=Iris&dataset=Iris.xlsx&dataset=iris&alvo=target&limite=200
```

Só lê os **próprios** pipelines do usuário autenticado (professor não vê os de aluno por aqui —
para isso existe o ranking da atividade, escopado à turma).

`dataset` é **repetível**: o cliente manda todos os nomes que conhece da base atual e **o
servidor decide** qual corresponde. Essa inversão é deliberada — calcular a identidade no
cliente foi o que fez o bloco não casar com o histórico na primeira versão.

Resposta (uma entrada por base, mais recente primeiro):

```jsonc
{
  "bases": [{
    "dataset": "Iris.xlsx", "alvo": "target", "tarefa": "classificacao",
    "metrica": "accuracy_score", "ordem": "desc",
    "baseline": 0.3514,            // chute burro (null quando não há referência barata)
    "melhor": 0.91, "ultima": 0.8947,
    "delta_vs_anterior": -0.0153,  // sinal positivo = melhorou, sempre
    "delta_vs_baseline": 0.5433,
    "tentativas": [{
      "pipeline_id": "...", "nome": "...", "data": "...", "valor": 0.86,
      "modelos": ["knn"], "pre_processamento": [], "divisao_treino": 70,
      "mudancas": ["acrescentou pré-processamento"]
    }]
  }]
}
```

## Identidade da base

`chave_da_base` = `(nomeDataset || treino.nomeArquivo || datasetId, target)`.

A **ordem importa**: `datasetId` é o id do arquivo criado **a cada carregamento**
(`coleta-dado.component.ts` faz `datasetId = resultado.id`). Se viesse primeiro, cada
recarregamento do mesmo dataset criaria uma base nova e o aluno nunca veria evolução.

Na filtragem, os nomes são comparados **normalizados** (`normalizar_nome_base`: minúsculas, sem
extensão), porque o mesmo dataset chega como `Iris` pelo assistente de coleta e como
`Iris.xlsx` por outros caminhos.

## Chute burro

Derivado do que **já está gravado**, sem reprocessar dados:

| Métrica | Referência | Como |
|---|---|---|
| `accuracy_score` | proporção da classe majoritária | somas das linhas da **matriz de confusão** já gravada |
| `r2_score` | `0.0` | prever a média dá R² = 0 por definição |
| MAE / MSE / RMSE / silhueta | `None` | não há referência barata e honesta; a comparação é omitida |

Omitir é melhor que inventar: um baseline errado ensinaria a coisa errada.

## Métrica que define "melhorou"

1. o `criterio.metrica` da **atividade de turma**, quando a base tem pipelines ligados a uma;
2. senão, a padrão da tarefa (`METRICA_PADRAO_POR_TAREFA`: acurácia / R² / silhueta).

Métricas em que menor é melhor (`METRICAS_ASCENDENTES`) têm o sinal do delta invertido, para
que **positivo signifique sempre melhora**.

## Frontend

O bloco é buscado no `ngOnChanges` quando a **coleta chega** — não no `ngOnInit`: o modal é
criado no início do assistente, quando o aluno ainda não escolheu os dados, e buscar no init
deixava o bloco sempre vazio. Uma guarda por base evita refetch a cada ciclo de mudança
(consequência: dentro da mesma sessão do modal, um resultado vazio não é reconsultado).

`valorAtual` vem da avaliação **aberta** (ainda não salva), lida de `resultadosDasAvaliacoes`
pelo rótulo da métrica; por isso o bloco pode mostrar ganho sobre a melhor tentativa salva.

## Testes

`tests/test_pipelines_evolucao.py` (26): identidade da base, chute burro (inclusive matriz
malformada), agrupamento e ordem cronológica, deltas nos dois sentidos, métrica de
menor-é-melhor, critério da atividade prevalecendo, nome normalizado, filtro por candidatos,
bases só com rascunho e escopo por usuário.
