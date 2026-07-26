# Desafios de montagem de pipeline

Atividade em que o aluno monta um pipeline como quebra-cabeça e a montagem é avaliada **sem
executar nada**. Corrige por **rubrica de regras com peso**, não por gabarito de sequência
única — vários pipelines diferentes resolvem corretamente o mesmo problema.

Documento de arquitetura. A justificativa pedagógica e as telas estão em
`../../docs/dissertacao/04-desafios-avaliacao-e-divisao.md`.

## Onde fica

| Arquivo | Responsabilidade |
|---|---|
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
    "tarefa": "classificacao",        // classificacao | regressao | agrupamento
    "exige": ["coleta", "pre_processamento", "modelo", "metrica"],
    "dados": { "faltantes": true, "texto": false, "escalas_diferentes": true },
    "dificuldade": "medio",           // facil (2 distratores) | medio (4) | dificil (6)
    "fixar": ["minmax_scaler"],       // peças que sempre entram no tabuleiro
    "vetar": ["pca"]                  // peças que nunca aparecem
  }
}
```

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
| `estrutura-minima` | 3 | `gabarito.exige` |
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
  trivialmente e rendia 4/10.
- **Nota ≠ pontos.** `nota = 10 × pontos/pontos_max`, com `pontos_max` somando só as regras
  aplicáveis; ambos são devolvidos para o professor poder explicar de onde veio a nota.

## Lanes

`LANES = ("coleta", "pre_processamento", "modelo", "metrica")` — espelham as colunas do
dashboard clássico de propósito: o desafio prepara o aluno para a tela real. Consequência: não
há ramo X|y no tabuleiro, então regras que dependem dele (por exemplo, `encode_y` no ramo
errado) não são verificáveis aqui.

## Testes

`tests/test_desafio_montagem.py` (44): cada regra isolada, pesos e nota, normalização da
montagem (entrada não confiável), determinismo e re-sorteio, `fixar`/`vetar`, gabarito que não
vaza, peça fora do tabuleiro, ranking e gates de papel.
