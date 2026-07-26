# Divisão treino/teste e estratificação

Como a plataforma separa treino e teste, por que **classificação estratifica por padrão** e o
que acontece quando o dataset não permite estratificar.

Justificativa pedagógica e telas: `../../docs/dissertacao/04-desafios-avaliacao-e-divisao.md`.

## Um único divisor

`dividir_dataframe(df, config, estratificar=None) -> (treino, teste, estratificou)` em
`app/coleta_dados/configuracao_treinamento.py` é o **único** lugar que divide dados. Usam-no:

| Porta de entrada | Arquivo |
|---|---|
| Upload CSV/TSV | `app/coleta_dados/coleta_dados_csv.py` |
| Upload XLSX | `app/coleta_dados/coleta_dados_xlxs.py` |
| Ingestão por URL | `app/coleta_dados/coleta_dados_url.py` |
| Dataset de exemplo | `app/routers/toy_datasets.py` |
| Redivisão (mudar proporção/alvo) | `app/coleta_dados/configuracao_treinamento.py` |

O terceiro elemento do retorno diz se a estratificação **realmente aconteceu** — é o que cada
porta grava na configuração e devolve ao cliente.

## O padrão

- **Classificação estratifica.** Sem isso, uma categoria pouco frequente pode ficar de fora do
  teste e a métrica engana o aluno.
- **Regressão e exploratório não** (não há categorias a preservar).
- O aluno **pode desmarcar**; o assistente explica por que a opção vem ligada.

No servidor, `ReDivisaoColetaRequest.stratify` é `Optional[bool]`: `None` significa "o cliente
não opinou" e a redivisão liga a estratificação quando a configuração diz classificação
(`prever_categoria and dados_rotulados`). Distinguir "não quero" de "não disse" é o que permite
o padrão valer também para clientes antigos.

Estratificar exige `shuffle` — uma divisão em ordem não pode reorganizar as categorias — e um
alvo escolhido. Na ingestão por URL o alvo ainda não existe, então lá nunca estratifica (o
valor gravado reflete isso; antes o pedido era ignorado em silêncio e a config gravava `true`).

## Quando estratificar é impossível

Categoria com **menos de dois exemplos** — comum em planilhas trazidas por alunos — torna a
estratificação matematicamente impossível. O comportamento:

1. divide **sem estratificar** (não recusa a operação — antes era `400`, o que com o padrão
   ligado barraria dados reais por uma escolha que o aluno não fez);
2. grava e devolve `stratify: false` — o **efetivo**, para que o pipeline salvo e o código
   Python exportado não afirmem uma estratificação que não houve;
3. devolve `aviso_estratificacao` (texto único em `AVISO_SEM_ESTRATIFICACAO`), que a tela usa
   para **desmarcar a caixa** e explicar o motivo.

No frontend o aviso é disparado em **um** ponto — `preencherDados`, por onde passam as
respostas de todas as portas — e não em cada chamada.

`400` continua existindo para divisão genuinamente impossível (dataframe vazio, `test_size`
fora de `(0,1)`).

## Vazamento corrigido nos datasets de exemplo

Antes de julho/2026, `toy_datasets` gravava:

```python
content_treino_base64 = df_para_base64(df)                      # dataframe INTEIRO
content_teste_base64  = df_para_base64(df.tail(len(df) // 4))    # cauda, sem embaralhar
```

Duas consequências invisíveis ao aluno: o teste era **subconjunto do treino** (vazamento — daí
acurácias de 100%) e, em datasets ordenados por classe (Iris, Wine), a cauda tinha uma única
categoria. Agora há divisão real via `dividir_dataframe`, estratificada em classificação.

O documento passou a guardar **`content_completo_base64`**: é dele que a redivisão relê os
dados. Sem esse campo, redividir usaria o treino já dividido e o dataset **encolheria a cada
mudança de proporção**.

> **Coletas antigas.** Documentos gravados antes da correção mantêm a divisão da época
> (inclusive o vazamento). Passam a ficar corretos quando o aluno recarrega os dados ou
> redivide. Não há script de reprocessamento — mexeria em dados de produção.

## Testes

`tests/test_divisao_treino_teste.py` (16), em três níveis:

- **unidade** de `dividir_dataframe`: treino/teste disjuntos e somando o total, proporções
  preservadas ao estratificar, fallback da categoria rara, sem alvo/sem embaralhar não
  estratifica, override do servidor, `400` quando a divisão é impossível, regra do aviso;
- **regressão do vazamento**: o treino não é mais o dataframe inteiro, nenhuma linha de teste
  aparece no treino, proporções preservadas nas duas partes, `content_completo_base64` gravado;
- **integração** da redivisão: redividir duas vezes não encolhe o dataset, aviso e valor
  efetivo chegam ao cliente, regressão não estratifica, escolha explícita do aluno prevalece.

Complementam `tests/test_coleta_dados_csv.py` (fallback e estratificação no upload) e
`tests/test_toy_datasets.py`.
