# Desafios de montagem de pipeline

Atividade em que o aluno monta um pipeline como quebra-cabeça e a montagem é avaliada **sem
executar nada**. Corrige por **rubrica de regras com peso**, não por gabarito de sequência
única — vários pipelines diferentes resolvem corretamente o mesmo problema.

Documento de arquitetura. A justificativa pedagógica e as telas estão em
`../../docs/dissertacao/04-desafios-avaliacao-e-divisao.md`.

## Onde fica

| Arquivo | Responsabilidade |
|---|---|
| `app/desafios/base_dados.py` | **Perfil do dataset de exemplo**: tarefa, textos do enunciado e as características da base lidas do dataframe. |
| `app/models/dataset_loaders.py` | Carregadores dos datasets em DataFrame (extraídos do router de toy datasets para poderem ser reusados aqui). |
| `app/desafios/catalogo.py` | Lê `db.modelos`/`db.metricas`/`db.pre_processamento`/`db.coleta_dados` e normaliza as **peças**. |
| `app/desafios/regras.py` | Biblioteca versionada de regras (peso + textos didáticos + predicados). |
| `app/desafios/sorteio.py` | Monta o **tabuleiro** da tentativa (determinístico; distratores do catálogo). |
| `app/desafios/avaliacao.py` | Aplica a rubrica → nota 0–10 + regras avaliadas. |
| `app/routers/turmas.py` | Rotas, persistência da submissão e ranking. |
| `app/schemas/turmas.py` | `tipo`, `GabaritoMontagem`, `SubmeterMontagem`. |

## Modelo de dados

`db.atividades` ganhou dois campos (sem migração — a leitura assume `pipeline` quando ausente):

```jsonc
{
  "tipo": "pipeline" | "montagem",   // 'pipeline' = comportamento histórico
  "gabarito": {                       // só em 'montagem'; NUNCA sai para o aluno
    "dataset": "iris",                // dataset de exemplo que origina o enunciado
    "tarefa": "classificacao",        // DERIVADA do dataset pelo servidor
    "exige": ["coleta", "pre_processamento", "modelo", "metrica"],
    "dados": { "faltantes": true, "texto": false, "escalas_diferentes": true },
    "dificuldade": "medio",           // facil (2 distratores) | medio (4) | dificil (6)
    "sortear_pecas": true,            // false = valem só as peças escolhidas (+ o mínimo)
    "fixar": ["minmax_scaler"],       // peças escolhidas pelo professor
    "vetar": ["pca"]                  // peças que nunca aparecem
  }
}
```

## O desafio nasce de uma base

O professor começa escolhendo um **dataset de exemplo**; o resto decorre dele:

| O que vem do dataset | Como |
|---|---|
| **Tarefa** | `DatasetType` usa exatamente o mesmo vocabulário do gabarito, então `ds.tipo.value` vai direto. O **servidor** faz essa derivação em `criar_atividade`/`atualizar_atividade` (`_gabarito_com_dataset`) — o cliente não decide, e um id inexistente é `400`. |
| **Enunciado sugerido** | `pergunta_guia` + `descricao` + `descricao_target` (`_enunciado`). A tela pré-preenche e o professor edita. |
| **O que a base exige** | Inspeção do dataframe real (`inspecionar_dados`): NaN → `faltantes`; coluna não numérica fora do alvo → `texto`; razão entre a maior e a menor amplitude ≥ 10× → `escalas_diferentes`. |
| **Peças compatíveis** | A tela só oferece modelos da tarefa e métricas do grupo. |

`GET /toy_datasets/{nome}/perfil-desafio` (professor/admin) devolve esse perfil. Carrega o
dataframe, então tem cache em memória e `try/except` amplo: falha de carga cai no conservador
(as três flags `False`) em vez de impedir a criação. O aluno recebe apenas o **nome** da base,
como um chip no tabuleiro (`dataset_nome`, resolvido sem carregar dados).

> Por que a inspeção importa: antes as três flags eram marcadas à mão e podiam **desmentir a
> base** — cobrar imputação de um dataset sem valores faltando torna a regra impossível de
> satisfazer, e o aluno perde ponto por algo que não existe.

`db.submissoes_montagem` — uma tentativa por documento, **sem TTL** (é registro de avaliação,
diferente da telemetria de `atividade_usuario`, que expira em 90 dias):

```jsonc
{
  "user_id": "...", "turma_id": "...", "atividade_id": "...",
  "tentativa": 2,
  "montagem": { "coleta": ["arquivo"], "pre_processamento": ["simple_imputer"], "modelo": ["knn"], "metrica": ["accuracy_score"] },
  "nota": 8.5, "nota_max": 10, "pontos": 11, "pontos_max": 13,
  "regras": [ { "id": "escala-antes-de-distancia", "titulo": "...", "ok": false, "peso": 2, "texto": "..." } ],
  "criado_em": "2026-07-26T…"
}
```

## Rotas

| Rota | Quem | Observações |
|---|---|---|
| `GET /turmas/{id}/atividades/{aid}/tabuleiro` | membro da turma | Peças da tentativa atual. **Não** devolve gabarito nem o `papel` (útil/distrator) das peças. |
| `POST /turmas/{id}/atividades/{aid}/submeter-montagem` | membro da turma | Corrige, grava e devolve nota + regras + textos. |
| `GET /turmas/{id}/atividades/{aid}/ranking` | professor/admin da turma | Ramifica por `tipo`: montagem ordena por nota e desempata por **menos tentativas**. |

`404` (não `403`) quando a atividade existe mas não é do tipo `montagem`, para não vazar a
existência de outra atividade pela mensagem de erro.

## As regras

Cada `Regra` tem `aplica(ctx)` (a regra vale para este desafio?) e `checa(ctx)` (a montagem a
satisfaz?). A nota considera **apenas as regras aplicáveis** — um desafio de agrupamento não
perde ponto por não imputar faltantes que não existem.

| id | Peso | De onde vem a verificação |
|---|---|---|
| `estrutura-minima` | 3 | `gabarito.exige` (etapa preenchida = tem peça DAQUELA etapa) |
| `peca-na-etapa-certa` | 2 | `lane` da peça no catálogo |
| `modelo-compativel` | 3 | catálogo: `prever_categoria` / `dados_rotulados` |
| `metrica-compativel` | 3 | catálogo: `grupo` da métrica; lista `metricas` do modelo como reserva |
| `escala-antes-de-distancia` | 2 | `MODELOS_SENSIVEIS_A_ESCALA` (distância/gradiente) |
| `imputacao-quando-ha-faltantes` | 2 | `gabarito.dados.faltantes` |
| `encoder-para-texto` | 2 | `gabarito.dados.texto` |
| `imputacao-antes-de-escala` | 1 | ordem das famílias na lane |
| `sem-distrator` | 2 | papéis do tabuleiro sorteado |

A **família** de um pré-processador (escala/imputação/encoder) é derivada da **classe sklearn**
do bloco `execucao` do catálogo, não de uma lista de slugs — assim um item novo cadastrado pelo
admin é classificado sem alteração de código.

Para acrescentar uma regra: adicione um `Regra(...)` em `REGRAS`. Nada no router muda. Os
textos são o produto mais importante — linguagem de sala de aula, dizendo o **porquê**.

## Decisões que não são óbvias

- **Rubrica, não gabarito.** Vários pipelines resolvem o mesmo problema; um gabarito de
  sequência puniria soluções válidas e daria retorno pobre.
- **Tabuleiro determinístico + re-sorteio por tentativa.** A semente é
  `sha256(atividade:aluno:tentativa)`, então a correção reconstrói o mesmo tabuleiro sem
  guardar estado de sessão, e recarregar a página não troca as peças. Cada nova tentativa
  troca — sem isso, o retorno por regra permitiria tentativa-e-erro até 10/10 sem compreensão.
- **Só valem as peças do tabuleiro.** A submissão recusa (`400`) peça que não foi ofertada
  naquela tentativa; sem essa checagem o re-sorteio não protegeria nada (bastaria reenviar o
  pipeline ideal aprendido no retorno anterior).
- **A regra `sem-distrator` exige ter montado algo.** Antes, entregar em branco a satisfazia
  trivialmente e rendia 4/10. `peca-na-etapa-certa` tem a mesma guarda, pela mesma razão.
- **A tela NÃO corrige a peça posta na coluna errada** — saber a que etapa cada bloco pertence
  é parte do que se mede. Por isso o tabuleiro do aluno **não recebe `lane`** (era o que
  permitia o clique único acertar a coluna sozinho e o realce apontar o erro na hora), e a
  alternativa ao arrastar virou de dois toques: peça, depois coluna.
- **A rubrica é quem enxerga o erro de posição.** `Contexto.metas(lane)` ignora peça de outra
  etapa: sem isso, uma métrica na coluna do modelo satisfazia `modelo-compativel` (métrica não
  declara `tarefa`, logo "nada incompatível") e o aluno ganhava ponto por um pipeline sem
  modelo. O mesmo vale para `estrutura-minima`: coluna cheia de peça errada segue vazia.
- **O tabuleiro sempre permite uma solução** (`_garantir_minimo`). O professor pode curar as
  peças (`sortear_pecas: false`) ou deixar o sorteio; em qualquer caso, lane exigida sem peça —
  ou sem peça compatível com a tarefa — é completada, **mesmo contra um `vetar`**, em silêncio.
  Sem isso `estrutura-minima` (peso 3) ficava insatisfazível por configuração do professor: era
  o que acontecia ao marcar "Exigir a etapa de pré-processamento" numa base que não pedia
  nenhuma família — o sorteio não colocava peça de pré-proc alguma.
- **Nota ≠ pontos.** `nota = 10 × pontos/pontos_max`, com `pontos_max` somando só as regras
  aplicáveis; ambos são devolvidos para o professor poder explicar de onde veio a nota.

## Lanes

`LANES = ("coleta", "pre_processamento", "modelo", "metrica")` — espelham as colunas do
dashboard clássico de propósito: o desafio prepara o aluno para a tela real. Consequência: não
há ramo X|y no tabuleiro, então regras que dependem dele (por exemplo, `encode_y` no ramo
errado) não são verificáveis aqui.

## Testes

`tests/test_desafio_montagem.py` (52): cada regra isolada, pesos e nota, normalização da
montagem (entrada não confiável), determinismo e re-sorteio, `fixar`/`vetar`, gabarito que não
vaza, peça fora do tabuleiro, ranking, gates de papel e nome legível das peças.

`tests/test_desafio_dataset.py` (24): inspeção da base (NaN, coluna de texto, alvo categórico
que **não** conta como texto, amplitudes), perfil com cache e com falha de carga, tarefa
derivada sobrepondo o cliente, dataset inexistente (`400`/`404`), modo curado sem extras,
mínimo garantido nos quatro casos (coleta/métrica/pré-proc exigido/veto conflitante),
determinismo preservado e o chip da base chegando ao aluno.
