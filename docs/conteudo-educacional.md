# Conteúdo educacional dos elementos do pipeline

Cada elemento utilizável no pipeline (modelos, métricas, pré-processadores, fontes de
coleta e gráficos de avaliação) tem um **card educacional** com dois modos:

- **Básico** — linguagem simples/lúdica (analogia, vocabulário de sala de aula);
- **Avançado** — descrição técnica, **Fundamentos** (fórmula, o que otimiza, pressupostos,
  complexidade, leitura de referência) e **Na prática** (pipeline sklearn completo, ordem de
  ajuste, armadilhas, diagnóstico), além do link para a documentação oficial.

O público vai do 8º ano do Fundamental ao primeiro ano do Superior (ONIA), e é o par
Básico/Avançado que atende os dois extremos. O nível é **preferência do perfil do aluno**
(`db.usuarios.nivel_tutor`), não estado de tela: vale nos três painéis do tutor, sobrevive ao
recarregar e **vai no contexto do chat**, então a ficha que o LLM recebe muda junto
(`app/tutor_kb.py`).

### Padrão editorial do Avançado

| Bloco | Exigido |
|---|---|
| `fundamentos` | `formula`, `otimiza`, `pressupostos[]`, `complexidade` (e `leitura[]` quando houver referência canônica) |
| `pratica` | `codigo` (com `sklearn`, mostrando o pipeline de verdade: divisão, CV ou busca), `tuning[]` na ordem em que se ajusta, `armadilhas[]` e `diagnostico[]` |

Regras de honestidade: `formula` do card espelha a de `fundamentos`; onde a complexidade depende
da implementação, o texto diz **de quê** depende em vez de cravar um número; defaults saem do
`hiperparametros_doc` já verificado contra o scikit-learn.

`tests/test_conteudo_loader.py` cobra esses campos por categoria (`EXIGENCIAS_AVANCADO`), porque
as exigências diferem: um gráfico não "otimiza" nada no sentido de um modelo e uma fonte de
coleta não tem fórmula. **Cobertura: 61/61 itens** — modelos 24, métricas 12, pré-processamento
10, gráficos 10 e coleta 5. O teste também exige que o código do bloco "Na prática" tenha
`import` (é para ser executável, não decorativo) e que a `formula` do card seja exatamente a de
`fundamentos`.

O que chega ao chat: `app/tutor_kb.py` monta o índice e as fichas de **modelos, métricas e
pré-processadores** (gráficos e coleta ficam fora para o índice não inchar). O corte por espaço
descarta **fichas inteiras**, nunca meia ficha.

## Fonte da verdade: versionada no repositório

O conteúdo é **dado versionado**, não código e não migração ad-hoc. Vive em
`app/conteudo/*.json` — um arquivo por categoria, cada um um mapa `{ valor: conteudo }`:

```
app/conteudo/
  schema.py                 # Pydantic Conteudo (valida o JSON em CI/teste)
  loader.py                 # carga + seed idempotente
  modelos.json              # 24
  metricas.json             # 12
  pre_processamento.json    # 10
  coleta_dados.json         #  5 (dados, xlsx, csv, json, dataset)
  graficos.json             # 10 (visualizações Yellowbrick/sklearn)
```

Campos de `conteudo` (todos opcionais; `extra="allow"`): `titulo`, `descricao` (Avançado),
`resumo_basico` (Básico), `intuicao`, `exemplo`, `exemplo_codigo` (Python), `formula`,
`conceitos[]`, `quandoUsar[]`, `naoUsarQuando[]`, `vantagens[]`, `desvantagens[]`,
`dicas[]`, `hiperparametros_doc[]`, `link_sklearn`, `link_yellowbrick`, `midia[]`,
`referencias[]`.

## Seed no MongoDB (idempotente e não-destrutivo)

`scripts/deploy/seed_conteudo.py` (→ `app/conteudo/loader.py::seed_conteudo`) aplica os
JSON nas coleções `db.modelos`/`db.metricas`/`db.pre_processamento`/`db.coleta_dados`/
`db.graficos`:

- usa `update_one({valor}, {$set: {conteudo}, $setOnInsert: {...}}, upsert=True)`;
- o **`$set` contém apenas `conteudo`** — nunca toca `execucao` (campo allowlistado/
  sensível) nem `habilitado` (preservado via `$setOnInsert`). Travado por teste
  (`tests/test_conteudo_loader.py`);
- para `graficos` (docs não pré-existem) o `$setOnInsert` cria a identidade mínima
  (`valor`, `label`, `grupo`, `tipoItem`).

Roda automaticamente no `scripts/deploy/deploy.sh` (etapa 5b). É idempotente: rodar duas
vezes não muda nada na segunda.

### Bootstrap / re-sincronização

`scripts/deploy/export-conteudo.py` (read-only) exporta o `conteudo` atual do MongoDB de
volta para `app/conteudo/*.json` — usado uma vez para trazer o conteúdo legado da prod
para o repo, e disponível para re-sincronizar se necessário. **Ordem importa:** exportar/
revisar/commitar antes de rodar o seed (o `$set` é last-writer-wins).

## Gráficos como elementos de 1ª classe

As visualizações de avaliação (Yellowbrick/sklearn) passaram a ter conteúdo próprio:

- `app/metricas/metricas.py` define `GRAFICOS_IDS` (slug → título exibido) e anexa
  `grafico_id` a cada visualização gerada. O **título não muda** (é também o nome do
  artefato no MLflow);
- coleção `db.graficos` (em `app/database.py`), keyed por slug;
- endpoints em `app/routers/conf_pipeline.py`:
  `GET /conf_pipeline/graficos/todos`, `GET /conf_pipeline/graficos/{valor}` e
  `PUT /conf_pipeline/graficos_doc/{valor}` (admin).

O frontend usa o `grafico_id` para buscar o conteúdo e renderiza o mesmo card
Básico/Avançado (`<app-tutor>`) na "dica" do gráfico, com fallback ao texto antigo.

## Datasets

`app/models/dataset_config.py` ganhou um campo opcional `conteudo` e o método
`conteudo_card()` (deriva um bloco do texto educacional já existente quando não há
`conteudo` explícito). Exposto em `GET /toy_datasets/{name}/conteudo` (read-only — não
carrega o dataset nem escreve no banco).

## Espelho legível (documentação)

`scripts/gerar-espelho-conteudo.py` regenera o espelho humano em
`base_de_conhecimento/catalogo_tutor/` (catalogo_ml.json + INDEX.md + uma ficha `.md` por
item, nas 5 categorias) a partir de `app/conteudo/*.json`. É só leitura — não editar à
mão; rode o gerador após mudar o conteúdo.

## Consumo no frontend (resumo)

- O card lê `conteudo` do catálogo e mapeia para `TutorItemInfo` via o helper único
  `dashboard/tutor/conteudo-to-item-info.ts`.
- O **código Python é colorido** com highlight.js carregado lazy
  (`dashboard/tutor/highlight/`), com fallback a texto puro.
- O admin edita tudo (incl. `resumo_basico` e `link_yellowbrick`) no
  `conf-pipeline/components/conteudo-editor`.

## Testes

- `tests/test_conteudo_loader.py` — JSON parseia/valida; contagens por categoria;
  garantia de que o `$set` só toca `conteudo`; paridade `graficos.json == GRAFICOS_IDS` e
  `pre_processamento.json ⊆ PRE_PROCESSAMENTO_CATALOGO`; presença de Básico/Avançado/link.
- `tests/test_conf_pipeline_graficos.py` — endpoints de gráficos.
- `tests/test_metricas_avaliacao.py` — cada viz carrega `grafico_id`.
- `tests/test_toy_datasets.py` — `/{name}/conteudo` read-only.

## Boas-vindas do tutor (pipe `inicio`)

O texto que o aluno lê no painel do tutor **antes de clicar em qualquer coisa** segue a
mesma ideia: fonte versionada no repo → semeada no banco → editável pelo admin.

| Onde | O quê |
|---|---|
| `app/conteudo/kb_tutor_inicio.py` | `TUTOR_INICIO_HTML` — fonte da verdade. Resume o Manual do Aluno (Carregar Dados → Pré-processamento → Treinar e Avaliar → Exportar) e diz onde ficam turmas/desafios, projetos e o manual. |
| `scripts/deploy/seed_tutor_inicio.py` | Semeia `db.tutor {pipe:'inicio'}.texto_pipe`. Roda no `deploy.sh` (etapa 5b). |
| `GET /tutor/?pipe=inicio` | Devolve o doc; **sem doc, devolve o texto versionado** (nunca 404 para o aluno). |
| conf-tutor → aba **Início** | O admin edita `texto_pipe`/`explicacao` (`PUT /tutor/pipe/inicio`). |
| `execucoes.component.ts` (`TUTOR_BOAS_VINDAS`) | Fallback **curto** para servidor fora do ar. Mantido curto de propósito: duas cópias longas divergem. |

O seed usa o **motor compartilhado** (`app/conteudo/texto_versionado.py`, seção abaixo): preserva o
texto editado pelo admin, propaga padrão novo para quem nunca editou, e reconhece o placeholder de
uma frase do `seed-mongodb.sh` como texto NOSSO (`legados`), substituindo-o. `--forcar` impõe o
padrão. Roda **no boot do backend e no `deploy.sh`**.

> **Era esse o segundo bug.** A comparação era `==` de string bruta, e o documento de produção tinha
> o HTML + 2 caracteres de espaço: o seed relatava "preservado (texto editado pelo admin)" a cada
> deploy, para um texto que ninguém editou, e as boas-vindas nunca eram atualizadas. Comparar por
> hash (que faz `strip`) resolve — e o estado vira só ajuste de metadado, sem reescrever o texto.

> **Era esse o bug.** O `seed-mongodb.sh` gravava `texto_pipe: "Bem-vindo ao tutor de
> Aprendizado de Máquina!"`, e como o banco vence o fallback, em produção o aluno lia uma
> única frase — o texto rico que existia no frontend nunca aparecia.

Formato: **HTML** (`h4/p/b/i/ul/ol/li`). O front renderiza com `[innerHTML]` sob o
sanitizer do Angular, que remove `style`, `script` e handlers.

## Instrução de sistema do chat (`db.configuracoes_tutor {chave:'system_prompt'}`)

O texto enviado ao modelo em **toda** pergunta segue o mesmo caminho (fonte versionada → semeada
no banco → editável pelo admin), com uma diferença: aqui o seed sabe **de qual padrão** a edição
do admin derivou, e por isso consegue propagar um padrão novo sem atropelar quem editou.

| Onde | O quê |
|---|---|
| `app/conteudo/kb_tutor_chat.py` | `SYSTEM_PROMPT_TUTOR` (fonte da verdade), `MAX_SYSTEM_PROMPT_CHARS` (6000) e `hash_prompt()`/`HASH_SYSTEM_PROMPT` — a identidade do padrão é **computada**, não um número mantido à mão. |
| `app/conteudo/system_prompt_seed.py` | `decidir_seed` (pura, dez estados) + `semear_system_prompt` (coleção injetável). |
| `app/main.py` (startup) | Cria o índice único em `chave` e semeia. **Roda no boot**, não só no `deploy.sh`: produção é atualizada pelos dois caminhos, e reiniciar o serviço é o que eles têm em comum. |
| `scripts/deploy/seed_system_prompt.py` | CLI (`--forcar`) para rodar sem reiniciar e para o log do deploy. |
| `GET /tutor/system-prompt` | Estado completo (texto, padrão, `fonte`, `origem`, `versao`, `padrao_desatualizado`). **Gate admin/professor**: o prompt é a regra que o tutor segue. |
| `PUT /tutor/system-prompt` | Admin. Texto vazio **grava** o padrão (não apaga) e o texto anterior fica em `db.tutor_audit.texto_anterior`. |
| conf-tutor → aba **LLM** | Editor, selos (`personalizado`/`padrão do sistema`/`não persistido`) e o aviso de padrão novo. |

Documento:

```jsonc
{ chave: "system_prompt", valor: "<texto vigente>",
  origem: "versionado" | "admin",
  padrao_hash: "<12 hex>",   // BASELINE: o padrão vigente no momento da gravação.
                             // NÃO é checksum de `valor`; ausente = baseline desconhecido.
  versao: 3, atualizado_por: "<user_id>|seed", atualizado_em: <utc> }
```

Matriz do seed, em uma frase cada: doc ausente → **insere**; `origem:'versionado'` com texto
diferente → **propaga** (é o que "versionado com o sistema" significa); `origem:'admin'` →
**preserva** (e, se o `padrao_hash` ficou para trás, a tela avisa); doc legado sem `origem` →
classifica conservadoramente (texto igual ao padrão = versionado; qualquer outro = admin, sem
baseline); `valor` vazio → **cura** com o padrão; `--forcar` → impõe o padrão.

> **Por que hash e não `VERSAO = 3`.** Um contador no fonte depende de alguém lembrar de
> incrementar — e é justamente isso que se esquece. O `versao` do documento existe só para humano
> ler o histórico, e é `$inc` a cada gravação.

> **Por que o fallback à constante permanece.** Persistir muda onde a verdade é *editada*, não o
> que acontece quando a leitura falha: Mongo fora, doc ausente ou doc vazio não podem deixar o
> tutor sem instrução. O selo "não persistido" na tela existe para esse estado não passar batido.


## Motor de textos versionados (`app/conteudo/texto_versionado.py`)

Três textos seguem o mesmo caminho — fonte versionada no repo → semeada no banco → editável pelo
admin — e a disciplina de sincronizar é uma só:

| Alvo | Documento | Editor |
|---|---|---|
| Instrução de sistema do chat | `db.configuracoes_tutor {chave:'system_prompt'}.valor` | conf-tutor → LLM |
| Boas-vindas do tutor | `db.tutor {pipe:'inicio'}.texto_pipe` | conf-tutor → Início |
| Guia do conf-pipeline | `db.tutor {pipe:'conf-pipeline'}.texto_pipe` | (ainda sem tela) |

`TextoVersionado` descreve o alvo (coleção, identidade, campo, padrão, rótulo, aba da auditoria e
`legados`); `decidir` é **pura** e cobre doze estados; `semear` aplica e audita. Os alvos de
`db.tutor` estão em `app/conteudo/textos_do_tutor.py` (`ALVOS_POR_PIPE`), que é também o que permite
às rotas marcarem `origem`.

Em uma frase por estado: doc ausente → **insere**; `origem:'versionado'` com texto diferente →
**propaga**; `origem:'admin'` → **preserva** (e, se o `padrao_hash` ficou para trás, a tela avisa);
texto igual a um `legado` → **propaga** (é nosso); doc sem `origem` → classifica conservadoramente
(igual ao padrão = versionado; diferente = admin, sem baseline); `valor` vazio → **cura**;
`--forcar` → impõe.

> **Marcar `origem` nas rotas é pré-requisito do seed, não complemento.** Se o admin salva pela tela
> e o documento não registra que o texto passou a ser dele, o seed do próximo deploy o classifica
> como "versionado" e propaga o padrão por cima — pior que não ter guarda nenhuma. Por isso
> `PUT /tutor/pipe/{pipe}` (e os outros dois caminhos que gravam `texto_pipe`) calculam `origem` por
> hash e gravam o baseline. Os metadados **não** entram no `update_data` da resposta: aquele dict é
> também a fonte de `campos_alterados` do histórico do admin.
