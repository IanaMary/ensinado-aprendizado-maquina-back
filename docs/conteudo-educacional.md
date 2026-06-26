# Conteúdo educacional dos elementos do pipeline

Cada elemento utilizável no pipeline (modelos, métricas, pré-processadores, fontes de
coleta e gráficos de avaliação) tem um **card educacional** com dois modos:

- **Básico** — linguagem simples/lúdica (público-alvo: adolescentes da olimpíada de IA);
- **Avançado** — descrição técnica, fórmula, **exemplo de código Python colorido** e link
  para a documentação oficial (scikit-learn ou Yellowbrick).

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
