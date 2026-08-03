# Changelog — H2IA Tutor

Histórico de deploys em produção (`https://absapt.tk/h2ia/`). Formato inspirado em
[Keep a Changelog](https://keepachangelog.com); datas em AAAA-MM-DD. Cada entrada cita os
commits (frontend/backend) e o bundle publicado. Fonte: `CLAUDE.md` → _Historical Production Reference_.

> Frontend: `IanaMary/ensinado-aprendizado-maquina` · Backend: `IanaMary/ensinado-aprendizado-maquina-back`.

---

## 2026-08-03b (o dataset "Titanic" não era o Titanic)

> Suíte **642** passed, 1 skipped.

### Corrigido
- **`Titanic` apontava para o UCI `id=597`, que não é o Titanic**: é o _Productivity Prediction of
  Garment Employees_ (1197 linhas, colunas `date`/`quarter`/`department`/`team`/…), sem nenhuma
  coluna `Survived`. O aluno que escolhesse "Titanic" recebia dados de produção têxtil e um alvo
  inexistente. Verificado carregando os dois: `fetch_ucirepo(id=597)` devolve `(1197, 15)` com
  aquelas colunas.
- Agora vem do **OpenML pelo `fetch_openml` do sklearn** (`fonte="openml"`, nova
  `carregar_openml` com o mesmo cache em disco do `carregar_uci`, e `OPENML_SPECS` no
  `dataset_loaders.py`). São **1309 linhas × 7 features + alvo**, batendo exatamente com o que o
  catálogo já declarava (`n_amostras=1309`, `n_features=7`) — o catálogo estava certo, o
  carregador não. O alvo passou a ser `survived` (o nome real da coluna), no lugar de `Survived`.
- **As colunas de vazamento ficaram de fora, de propósito:** o OpenML entrega 13 colunas,
  incluindo `boat` (número do bote salva-vidas) e `body` (número do corpo recuperado), que
  **determinam** a sobrevivência — oferecidas ao aluno dariam acerto quase perfeito e nenhum
  aprendizado. Junto saíram `name`, `ticket`, `cabin` e `home.dest` (texto de altíssima
  cardinalidade). Sobram as 7 features clássicas: `pclass`, `sex`, `age`, `sibsp`, `parch`,
  `fare`, `embarked`.
- O `prewarm` do startup agora aquece o cache do OpenML também, não só o do UCI.

### Notas
- **`OPENML_SPECS` é espelho de `getToyDatasetLoader` no `script-generator.service.ts`** — o
  script exportado precisa aplicar o MESMO recorte de colunas, senão treina com o vazamento e
  devolve outra métrica. Verificado: o `X` do script e o dataframe da plataforma são
  **idênticos** (`DataFrame.equals`), e o script roda até o fim (981/328 na divisão 75/25).
- O teste que quebrou (`test_uci_datasets_have_correct_fonte`, um `assert fonte == "uci"` sobre o
  grupo inteiro) foi trocado por um que **pega a classe do bug**: exige que a `fonte` tenha
  carregador de fato e que o dataset esteja no registro dele. Mais um teste fixa o contrato do
  Titanic (origem, alvo e ausência das colunas de vazamento). Igualdade de string não pegaria
  um id apontando para o dataset errado — só conferir o conteúdo pega.
- `age` tem **263** nulos, `fare` 1 e `embarked` 2: é um bom caso para o `SimpleImputer`, e
  `sex`/`embarked` são categóricas (o treino ensina, com 400, que precisam de codificador).

---

## 2026-08-03 (a resposta do dataset de exemplo conta a divisão que o servidor fez)

> Achado testando o **código exportado**: o script baixado reproduzia uma divisão diferente da que
> treinou o modelo. Suíte **638** passed, 1 skipped.

### Corrigido — `GET /toy_datasets/{id}` não dizia como dividiu os dados

O endpoint divide o dataset de exemplo em **75/25** (constante `TEST_SIZE_PADRAO`, antes literal
repetido em dois pontos), mas a resposta não trazia essa informação. A tela, sem ter como saber,
presumia 70/30 e anunciava `Total disponível: 442 | Treino: 442 (70%) | Teste: 0 (30%)` — três
números errados de uma vez, para uma divisão que na verdade foi 331/111 (o que o próprio painel de
treinamento confirmava). O script exportado herdava a mesma suposição e imprimia outra acurácia.

A resposta passa a devolver `test_size`, `num_linhas_treino` e `num_linhas_teste` — os valores
reais, os mesmos que já eram gravados em `db.arquivos`. Aditivo: nenhum campo mudou de significado.

---

## 2026-08-03b (o zip do aluno não leva metadados do servidor + alvo contínuo virando texto)

> Achados na varredura por agentes do código exportado. Suíte **641** passed, 1 skipped.

### Corrigido — o download do modelo levava metadados do servidor de treino

O zip de `GET /classificador/modelo/{id}/artefato` copiava o diretório do MLflow inteiro, e ali vêm
`environment_variables.txt` (a lista de variáveis de ambiente do servidor, com `NVIDIA_API_KEY` —
só o nome, nunca o valor) e um `MLmodel` com `env_vars` e `artifact_path:
file:///home/ubuntu/mlflow/...`. Isso vai para um aluno, que pode repassar o arquivo, e nenhum dos
`usar_modelo_*.py` lê variável de ambiente.

Agora o `environment_variables.txt` fica fora e o `MLmodel` é saneado (`_sanear_mlmodel`), de forma
conservadora: só a lista `env_vars` de nível superior e o `artifact_path` do topo. O `artifact_path`
**aninhado** em `saved_input_example_info` é preservado — ele aponta para dentro do próprio zip e é
o que o MLflow usa para achar o exemplo. Verificado com o artefato real de produção: o modelo
saneado carrega e devolve a mesma previsão.

### Corrigido — `california_housing` tinha o alvo contínuo convertido em texto

A troca do alvo numérico por rótulo de classe rodava sempre que o dataset tivesse `target_names`.
Em regressão esse campo é o **nome da coluna**, não uma lista de rótulos: com
`target_names == ['MedHouseVal']`, o `else str(x)` transformava a coluna inteira em strings. A tela
então deduzia **"Exploratório"** para um dataset de regressão, e o script exportado (que usa o alvo
numérico) media outra coisa. Agora a conversão só acontece em classificação.

---

## 2026-08-02d (o aviso do aluno mostra o dataset sugerido de verdade)

> Defeito encontrado **testando com conta de professor**: criei uma atividade de pipeline com o
> Wine e o campo chegava vazio ao aviso. Suíte 637 passed, 1 skipped.

### Corrigido
`GET /turmas/minhas/desafios` devolvia `dataset` lendo `a["dataset"]` — **campo que não existe** nos
documentos de atividade. O dataset sugerido mora em **`template.datasetNome`** (é de lá que o
`entrar-turma` já lia ao abrir a atividade), então o aviso do aluno nunca mostraria a sugestão do
professor. Agora lê `template.datasetNome` com fallback para `dataset`.

O teste que eu havia escrito em 02c passava porque **eu mesmo montei o mock com o campo errado** —
ele confirmava a minha suposição, não o formato real do documento. Corrigido para
`template: {datasetNome: "Wine"}`.

## 2026-08-02c (tutor com cadeia de fallback + renovação de sessão + pipeline do professor)

> 2ª leva da revisão da banca (Imagens 10, 13 e 14). Suíte **637** passed, 1 skipped.

### Corrigido — o tutor estava fora do ar (Imagem 13)
Provedor NVIDIA com o modelo `moonshotai/kimi-k2.6`: ele **aparece** em `/models`, mas a inferência
devolve **`404 Function … Not found for account`** — não liberado para a chave. Toda pergunta virava
"O tutor retornou erro".

Agora existe **cadeia de modelos**: `[modelo escolhido, *fallbacks do provedor]`, nos **dois**
caminhos (stream e não-stream). NVIDIA → `deepseek-ai/deepseek-v4-flash` e
`meta/llama-3.1-8b-instruct` (ambos medidos respondendo 200 nesta conta).
- **Só troca de modelo em falha de disponibilidade** (404/5xx/timeout/rede). Em **401/403 não
  troca**: a chave é a mesma para todos, e cair para o próximo esconderia o problema real.
- No streaming a troca só é possível **antes do primeiro byte** — depois, recomeçar daria resposta
  remendada. Dá certo porque o 404 vem no status, antes de qualquer chunk.
- Cache de 10 min por modelo que falhou (não paga o timeout a cada pergunta). Um modelo marcado vai
  para o **fim** da fila, não sai dela: se todos falharam, ainda vale tentar.
- A resposta passa a dizer **qual modelo atendeu** (`{"resposta", "modelo"}`).

### Adicionado — renovação de sessão (Imagem 10)
`POST /login/renovar`: com um access token **ainda válido**, emite outro com nova expiração. O token
durava 60 min sem renovação e o aluno caía no meio da atividade. **Não é refresh token** — exige
token vivo, então não amplia a janela de um token vazado. A regra de expiração virou função única
(`_emitir_token`), para o `/renovar` não divergir do `/login`.

### Alterado — pipeline sugerido chega ao aviso do aluno (Imagem 14)
`GET /turmas/minhas/desafios` filtrava `tipo: montagem`, então a **atividade de pipeline** do
professor nunca aparecia no aviso da Área de Trabalho — o aluno só a achava pelo avatar → Turmas.
Agora traz `{"$in": [montagem, pipeline]}`, com `tipo` e `dataset` na resposta e histórico por tipo
(`_historico_pipeline` conta os pipelines salvos do aluno na atividade). Continua **uma chamada só**:
o endpoint serve a tela mais crítica e 1+N requisições ali atrasariam o pipeline.

## 2026-08-02b (treinamento: K-Means, KNN, Árvore e PCA voltam a treinar)

> Imagem 9 da revisão da banca: "só o AdaBoost executa". Não era impressão — os logs de produção
> de 01/08 (18:20–18:36) registram as falhas. São **três defeitos distintos**, e os três foram
> reproduzidos localmente com o Wine, no mesmo caminho de código, antes de qualquer correção.
> Suíte 628 passed, 1 skipped (5 casos novos).
>
> **Não são regressão da auditoria de segurança:** as falhas são das 18h e aquele deploy foi às
> 20h35. São defeitos antigos que a banca encontrou por testar caminhos que a suíte não cobria.

### Corrigido — coluna de texto chegando ao estimador (era 500)
`ValueError: could not convert string to float: 'class_2'`, no K-Means. Sem alvo (modo
exploratório) **todas** as colunas marcadas viram atributos, inclusive a coluna categórica.
Agora `treinamento_base` recusa com **400 que ensina**: nomeia a coluna e dá as duas saídas
(desmarcar o atributo ou aplicar OneHot/Ordinal sobre ela). A checagem consulta o novo
`colunas_codificadas` (`app/pre_processamento/catalogo.py`), que espelha o `tem_imputer`: só é
problema se **ninguém** codificar a coluna.

### Corrigido — pré-processador apontando para coluna fora de X (era 500)
`ValueError: A given column is not a column of the dataframe`, no KNN e na Árvore. Acontece quando
o aluno configura a etapa e depois desmarca o atributo, ou escolhe o alvo (que não entra em X).
Agora o servidor descarta a coluna, pula a etapa que ficar vazia, **treina** e devolve
`aviso_pre_processamento` — mesmo contrato do `aviso_estratificacao` da divisão. No front, o alvo
deixou de ser ofertado nos **dois** ramos de `carregarColunas` (antes só um filtrava).

### Corrigido — PCA sem caminho de execução (era 400)
Único dos 24 modelos sem router literal: caía na rota genérica, que exige o bloco `execucao` no
documento — ausente nos modelos semeados em produção. Novo `app/routers/pca.py`, no formato do
`kmeans.py`. Router em código, e **não** backfill de `execucao` no banco: é determinístico e não
depende do estado do Mongo (o `CLAUDE.md` já adverte contra backfillar `execucao` às cegas).

### Corrigido — modelo não supervisionado sobre base rotulada
`is_clustering` era derivado só da ausência de alvo. Escolher K-Means ou PCA sobre uma base com
alvo levava o treino pelo caminho supervisionado. Agora também considera o modelo: o catálogo já
declara `dados_rotulados: false` para os dois. Ausente = supervisionado (o padrão dos outros 22).

### Corrigido — avaliação do PCA (seria o próximo 500)
O PCA tem `transform`, não `predict`: as métricas de agrupamento que o catálogo oferecia a ele
quebrariam logo depois do treino. Guarda em `metricas.py` devolve **400 explicando** que o modelo
transforma em vez de agrupar, e o seed passou a dar ao PCA `metricas: []`.

### Preparo (sem efeito hoje)
Entrada de PCA no catálogo canônico de pré-processamento (`sklearn.decomposition.PCA`, escopo
`transform_X`), para no futuro ser oferecido como redução de dimensionalidade antes do estimador.

### Testes — lacuna do harness fechada
`tests/conftest.py` não mockava `treinamento_base.opcoes_pre_processamento`: **todo** teste que
enviasse `pre_processamento` no payload consultava o Mongo **real** e a suíte tentava conectar em
`localhost:27017`. Por isso não havia teste de rota com pré-processamento.

## 2026-08-02 (acentuação de mensagens visíveis ao usuário)

> Continuação da varredura ortográfica pedida na revisão da banca (ver changelog do frontend).
> Suíte 623 passed, 1 skipped.

### Corrigido
- **4 mensagens de erro sem acento** em `app/routers/toy_datasets.py`: `"Dataset '…' nao
  encontrado"` (3×, HTTP 404) e `"Biblioteca nao instalada"` (HTTP 500) → **`não`**. O `detail`
  destas exceções chega ao aluno como toast pelo `ErrorInterceptor`, então é texto de interface.
- **Não** foram tocadas as mensagens que citam nomes de campo do contrato JSON — `execucao`,
  `execucao.modulo`, `funcao`, `hiperparametros` em `conf_pipeline.py` e `treinamento_base.py`.
  Ali a palavra sem acento **é o nome da chave** que o cliente precisa enviar; acentuar tornaria a
  mensagem errada.

## 2026-08-01 (auditoria de segurança Mantis — 26 correções + 3 cadeias quebradas)

> Campanha defensiva completa (plan → research → review → critic → calibrate → reproduce →
> chain → report → patch). 52 achados brutos → 26 confirmados (24 falsos-positivos filtrados,
> incluindo um oráculo de enumeração de login **medido** falso e um XSS neutralizado pelo
> sanitizador do Angular). **Todos os 26 corrigidos.** Suíte: backend 623 / frontend 217, build ok.

### ⚠️ Pré-requisito de deploy — backfill obrigatório
- As correções de IDOR passaram a escopar leituras por dono (**fail-closed**). Documentos antigos de
  `arquivos`/`configuracoes_treinamento`/`modelos_treinados` não têm `usuario_id` e ficam
  inacessíveis até o backfill. Rode **`scripts/deploy/backfill_usuario_id.py --apply`** (recupera o
  dono dos modelos via `mlflow_runs`, cria índices, relata órfãos). Datasets órfãos precisam ser
  recoletados pelos donos.

### Corrigido — segurança (crítico/alto)
- **Escalada não-autenticada → RCE (cadeia CRÍTICA, quebrada).** Três elos, todos fechados:
  - **Senha de admin fixa no repositório** (`seed_usuarios_demo.py`): removido o default
    `h2ia-banca-2026` (também retirado da doc); a senha agora vem só de `SENHA_DEMO` e nunca é
    impressa. **`login` passou a recusar contas não-ativas** (`status != 'ativo'`) — antes ignorava
    `status`, então desativar a conta não bloqueava o login.
  - **Allowlist do sandbox só validava o módulo** (`sandbox/child.py`): o nome da classe ia direto ao
    `getattr`, aceitando funções utilitárias (ex.: `sklearn.utils._testing.check_output`) que
    executam comando. Agora exige **classe de estimador com `fit`** e nome público simples.
  - **Bytes do modelo do filho desserializados no processo pai** (`treinamento_base.py`,
    `metricas.py`): `prever` passou a **verificar o checksum antes do `joblib.load`**.
- **Família de IDOR — coleções sem campo de dono.** `arquivos`, `configuracoes_treinamento` e
  `modelos_treinados` eram lidos só por `_id`. Agora todo insert grava `usuario_id` e toda
  leitura/escrita filtra pelo dono do JWT: coleta CSV/XLSX/URL, configuração de treino, pairplot
  (`visualizacao`), treino (`treinamento_base`) e previsão/download/avaliação (`metricas`).
- **Gabarito de outra turma vazava** (`turmas.py:atualizar_atividade`): releitura escopada por
  `turma_id` (verificado ponta-a-ponta em stack ao vivo).
- **Telemetria de qualquer aluno por `usuario_id`** (`atividade.py`): escopada aos alunos das turmas
  do professor (espelha `_autorizar_ver_aluno`); admin mantém visão global.
- **Injeção de prompt no tutor** (`chat_tutor.py`): o papel de quem pergunta passou a ser decidido
  pelo **servidor** (JWT), não pelo `contexto` do cliente; contexto e base de conhecimento cercados
  no system prompt como **dados, não instruções** (fecha também a injeção via conteúdo de catálogo
  editável por professor).
- **SSRF por reresolução de DNS** (`coleta_dados_url.py`): o IP validado é **fixado** na conexão
  (transport httpx com SNI preservado), fechando a janela de rebinding.
- **`base_url` de provedor redirecionava a chave** (`tutor_provedores.py`): URL livre só no provedor
  `custom`; hospedados usam a URL do catálogo; a chave é descartada se a URL muda sem rechave.

### Corrigido — segurança (médio/baixo)
- **Vazamento do gabarito por submissão vazia** (`desafios/avaliacao.py`): montagem vazia não recebe
  o detalhamento das regras (várias tinham aplicabilidade decidida só pelo gabarito) + **cap de
  tentativas** (`turmas.py`).
- **Tabuleiro reconstruível offline** (`desafios/sorteio.py`): segredo do servidor na semente
  (mitigação — fechamento total exige não expor metadados de correção no catálogo semi-público).
- **Cópia de pipeline herdava vínculo de atividade/turma** (`pipelines.py`): descartado na cópia.
- **Healthcheck vazava a exceção crua do driver** (`main.py`): mensagem genérica; detalhe só no log.

### Corrigido — scripts de deploy
- **MongoDB sem autenticação** (`setup-mongodb.sh`): bloco de auth guardado por `MONGO_APP_PASSWORD`.
- **`.env` legível por todos** (`deploy.sh`): `chmod 600` antes de escrever segredos.
- **Seed destrutivo sem guarda** (`seed-mongodb.sh`): exige `SEED_CONFIRM=yes` (faz `deleteMany`).
- **Firewall aberto para `0.0.0.0/0`** (`open-firewall-oci.sh`): sem default público, porta corrigida
  para 8002, origem parametrizada por `ALLOWED_SOURCE`.

### Corrigido — frontend
- **Token de convite no log de erros** (`error.interceptor.ts`): a URL enviada ao `/sistema/erro` é
  sanitizada (sem query string; token do path `/convite/…` redigido).

---

## 2026-07-30 (correções da revisão: gate dos endpoints de modelo, provedor local)

> **Implantado em 30/07/2026 12h10.** Backend `master` **`fafb7ac`**.
> Backup `/home/ubuntu/backups/deploy-20260730-121006`. Frontend: ver changelog do frontend.

### Corrigido — segurança
- **`GET /tutor/modelos` e `GET /tutor/modelos/saude` exigiam apenas estar logado.** O segundo aceita
  `?modelo=<id>` e faz uma chamada **real** de completion no provedor: um aluno autenticado podia
  escolher o modelo mais caro e o servidor pagava. Ambas passam a exigir **admin/professor** (só a
  tela de configuração as consome). Estava no ar desde 29/07c.

### Corrigido
- **Provedor sem chave não ativava.** `exige_chave` no catálogo: um endpoint self-hosted (Ollama,
  vLLM, LM Studio) não tem chave — e era o caso de uso dos campos de URL base e porta. Sem chave, a
  chamada também não manda `Authorization: Bearer ` vazio.
- `PUT /tutor/provedores/{id}` e `PUT /tutor/provedor-ativo` ganham schema Pydantic (eram
  `body: dict`, o outlier do projeto — e o `/system-prompt` fora corrigido no mesmo ciclo).
- `HTTP-Referer` do OpenRouter vem de `FRONTEND_URL` em vez de hardcode.
- `provedor_vigente()` resolve em **uma** consulta (eram três `find_one` por pergunta do chat);
  leitura morta (`del vigente`) removida.
- `.env.example` documenta `OPENROUTER_API_KEY`, `HEALTHCHECK_TIMEOUT`, os tetos do chat e o MLflow —
  nomes apenas.
- Documentação normativa que ficou falsa: `CLAUDE.md` afirmava "chave NVIDIA APENAS no `.env`" e
  "conf-tutor só tem Início e LLM". Corrigido, e a decisão sobre chave no banco + URL base privada
  virou **`docs/adr/0003-provedores-de-llm-e-chave-no-banco.md`**.

### Verificação
**623 passed, 1 skipped** (8 novos: os três 403, provedor local sem chave, cabeçalho sem
`Authorization`, referer por env, leitura em uma consulta). Exercitado contra a API local: aluno 403
nas três rotas, provedor local ativando sem chave, corpo inválido 422.

---

## 2026-07-29c (provedores de LLM: OpenRouter, endpoint customizado, selo de gratuito)

> **Implantado em 29/07/2026 17h53.** Backend `master` **`6778c20`**.
> Backup `/home/ubuntu/backups/deploy-20260729-175349`. Frontend: ver changelog do frontend.

### Adicionado
- `app/tutor_provedores.py`: o chat deixa de falar só com a NVIDIA. Provedores suportados: **NVIDIA
  NIM**, **OpenRouter** e **qualquer endpoint OpenAI-compatible** (URL base + porta) — o caso de uso
  desta última é modelo self-hosted (Ollama, vLLM, LM Studio).
- Rotas `GET /tutor/provedores`, `PUT /tutor/provedores/{id}`, `PUT /tutor/provedor-ativo`
  (admin-only para escrever). `GET /tutor/modelos` passa a devolver `gratuito` por modelo e a lista
  **com os gratuitos primeiro**; `GET /tutor/modelos/saude?modelo=<id>` testa um modelo isolado.
- Trocar provedor/modelo passou a ser **auditado** em `db.tutor_audit` (`pipe: 'llm'`) — era a única
  mudança da tela sem histórico. A chave de API **nunca** entra na auditoria.

### Decisões
- **Chave:** a da NVIDIA continua só no `.env`. As dos provedores configuráveis pela tela ficam em
  `db.configuracoes_tutor`, porque é o que permite ligá-los sem deploy; a leitura devolve apenas os
  últimos 4 caracteres (`chave_mascarada`) e de onde ela vem (`banco`/`env`/`ausente`). PUT com
  `api_key` vazio **mantém** a chave — o admin corrige a URL sem redigitar o segredo.
- **Modelo é por provedor.** Um id do OpenRouter não existe na NVIDIA. O `llm_model` legado continua
  valendo para a NVIDIA, então produção não sente a migração; a NVIDIA também continua gravando lá,
  para um rollback encontrar o modelo onde ele sempre esteve.
- **URL base privada é permitida** (admin-only), de propósito: o anti-SSRF de
  `POST /coleta_dados/url` existe para dado vindo de aluno, não para configuração de admin.
- **Gratuidade vem do preço**, não do nome: o OpenRouter manda `pricing` em cada modelo, e 3 dos 17
  gratuitos não terminam em `:free`. A NVIDIA é marcada como toda gratuita por convenção do catálogo
  (a plataforma de build é de uso livre com limite de taxa); provedor arbitrário fica sem afirmação
  (`null` ≠ `false`).
- **Teste de saúde automático só nos gratuitos + o em uso.** No OpenRouter são 367 modelos: testar
  todos seriam centenas de requisições por rodada — algumas cobradas — só para montar a tela.

### Verificação
**615 passed, 1 skipped** (30 novos: normalização de URL com porta, mascaramento, modelo por
provedor, chave vazia que mantém, gratuidade por preço). Verificado contra a API real do OpenRouter:
367 modelos, 17 gratuitos, gratuitos primeiro.

---

## 2026-07-29b (guia do conf-pipeline entra no deploy + marca única H2IA Tutor)

> Backend `master` **`76ef813`**. Frontend: ver changelog do repo do frontend.
> **Exige renomear o experimento MLflow em produção** (ver Alterado).

### Adicionado
- **O guia do conf-pipeline passou a ser semeado com guarda.** `seed_kb_conf_pipeline.py` fazia
  `$set` de `texto_pipe` sem ler o banco, e por isso estava fora do `deploy.sh`: ligá-lo apagaria em
  silêncio a edição do admin. Agora os dois textos de `db.tutor` (boas-vindas e guia) usam o mesmo
  motor versionado da instrução de sistema, semeados **no boot e no `deploy.sh`**, ambos com
  `--forcar`.
- `app/conteudo/texto_versionado.py`: o motor (matriz de decisão + `TextoVersionado`, que descreve o
  alvo uma vez em vez de repetir nove parâmetros por chamada) — extraído de
  `system_prompt_seed.py`, que ficou como fachada fina. Os 22 testes dele passam **verbatim**.
- Estado novo na matriz: `legados`. Texto que NÓS publicamos antes (o placeholder de uma frase do
  `seed-mongodb.sh`) não é edição do admin e pode receber o padrão novo. É a única exceção ao "o
  seed nunca sobrescreve o admin", e existe porque o caso realista é o admin abrir a tela, ver a
  frase e clicar em Salvar sem escrever nada seu.
- As rotas que gravam `texto_pipe` (`PUT /tutor/pipe/{pipe}`, o catch-all `PUT /tutor/{id}` e
  `/editar-tipo-aprendizado/{id}`) marcam `origem`/`padrao_hash`/`versao`. **Pré-requisito**, não
  complemento: sem isso o seed classificaria a edição do admin como "versionado" e propagaria por
  cima dela — pior que não ter guarda, porque escondido atrás de um mecanismo que diz proteger.
- Índice único em `tutor.pipe` (dois workers poderiam duplicar o documento).

### Corrigido
- **Bug ativo em produção:** o doc `{pipe:'inicio'}` tinha o HTML versionado **+ 2 caracteres de
  espaço**, e a comparação era `==` de string bruta — então o seed vinha relatando "preservado
  (texto editado pelo admin)" a cada deploy, para um texto que ninguém editou, e as boas-vindas não
  recebiam atualização nenhuma. Comparando por hash (que faz `strip`), isso se autocorrige no
  primeiro boot como ajuste de metadado, sem reescrever o texto.
- **Os logs dos seeds não apareciam em lugar nenhum.** `setup_logging` só encaminha os loggers do
  uvicorn/FastAPI para o loguru, então o `logging.getLogger(__name__).info` do hook de ontem era
  descartado — nem `journalctl`, nem painel de logs do admin. Passaram a usar o loguru.
- `_CAMPOS_DO_SEED` sai do `contexto` que o cliente manda: uma `versao` string faria todo `$inc`
  posterior naquele documento estourar 500, para sempre.

### Alterado
- **Marca:** "Iana" deixa de ser nome da plataforma em docstrings, README, documentação e nos
  defaults de infra. `MLFLOW_EXPERIMENT` → **`h2ia-treinamento`**, com o experimento **renomeado no
  MLflow de produção na mesma janela** (trocar só o default criaria um experimento novo e orfanaria
  os runs históricos na tela de Artefatos; um rollback sem renomear de volta tem o mesmo efeito).
  `EMAIL_FROM` default → `noreply@h2ia.ufpel.edu.br`. **Preservados:** o nome da autora, o usuário
  `IanaMary`, a branch `mestrado-iana` e as entradas que narram a própria mudança de marca.

### Verificação
**585 passed, 1 skipped** (32 novos; **nenhum teste existente alterado**). E2E contra um Mongo real:
placeholder legado → propagou (auditoria guarda o texto anterior); texto do admin salvo pela API →
`origem: admin` e preservado no restart; HTML com 2 espaços → normalizado sem reescrever.

---

## 2026-07-29 (instrução de sistema persistida e versionada + healthcheck honesto)

> Backend `master` **`f4ae2fc`**. Frontend: ver changelog do repo do frontend.

### Adicionado
- **A instrução de sistema do chat passou a viver no banco.** Antes a constante
  `SYSTEM_PROMPT_TUTOR` era padrão E fallback, e `db.configuracoes_tutor {chave:'system_prompt'}`
  só existia se um admin gravasse: em produção não havia documento nenhum, então "o que está
  rodando" não era observável — a ausência de doc era indistinguível de "nunca semeado".
- `app/conteudo/system_prompt_seed.py`: `decidir_seed` **pura** (dez estados) + `semear_system_prompt`
  com coleção injetável. O documento carrega `origem: 'versionado'|'admin'`, `padrao_hash`
  (**baseline**: o padrão vigente no momento da gravação — não checksum de `valor`) e `versao`
  (`$inc`). Com isso o deploy **propaga** um padrão novo para quem nunca editou e **preserva** a
  edição do admin, avisando na tela quando o padrão mudou desde ela.
- Seed no **startup** do backend + CLI `scripts/deploy/seed_system_prompt.py [--forcar]` + etapa 5b
  do `deploy.sh`. O gatilho primário é o boot porque produção é atualizada tanto pelo `deploy.sh`
  quanto por `git pull` + `systemctl restart`; amarrar o seed a um só deixaria o documento ausente
  **sem sintoma** (o fallback esconde).
- `GET /tutor/system-prompt` devolve `fonte` (`banco`/`versionado`), `origem`, `versao`,
  `padrao_hash_base` e `padrao_desatualizado`. `hash_prompt`/`HASH_SYSTEM_PROMPT` em
  `kb_tutor_chat.py` — identidade computada, não um `VERSAO = 3` que alguém precisa lembrar de
  incrementar.
- Índice **único** em `configuracoes_tutor.chave`: sem ele, os dois workers do uvicorn podiam
  inserir dois docs `system_prompt` e o `find_one` passaria a devolver um deles arbitrariamente.

### Corrigido
- **"Voltar ao padrão" deixou de destruir.** O texto vazio no PUT fazia `delete_one` e a auditoria
  guardava só o tamanho: uma instrução de 5000 chars se perdia num clique. Agora grava o padrão
  (o estado "padrão" passa a ser um fato persistido) e o texto anterior fica em
  `db.tutor_audit.texto_anterior`.
- **`/healthcheck` responde 503** quando o Mongo não responde (antes: 200 sempre, com a distinção
  só no corpo — qualquer probe por código HTTP via serviço saudável). A espera pelo ping é limitada
  a `HEALTHCHECK_TIMEOUT` (3s): sem isso o driver segurava 30s e o 503 nunca chegava a ser visto.
- **O healthcheck do `deploy.sh` testava a porta 8000**, e o serviço que o próprio script cria
  escuta na **8002** — era um `AVISO: Healthcheck falhou` em todo deploy, com o serviço saudável.
  Agora a porta vem de variável (default 8002), confere código HTTP **e** o campo `status`, e o
  script sai diferente de zero quando termina doente (antes o aviso ia para o meio do log e o
  deploy se declarava concluído).
- Gate de papel nas leituras: `GET /tutor/system-prompt` (o prompt é a regra que o tutor segue —
  entregá-la ao aluno é entregar o mapa para contorná-la) e `GET /tutor/audit` (traz nome e e-mail
  de quem editou) passam a exigir admin/professor. O `tamanho`, gravado desde sempre e nunca lido,
  entrou na projeção da auditoria.

### Verificação
**553 passed, 1 skipped** (eram 522; 31 novos, incluindo os dez estados do seed e os dois casos do
healthcheck). **E2E local** com Mongo em Docker: o doc nasce no boot, e cada estado foi forçado à
mão e reconciliado pelo CLI (propagou / preservou / curou / normalizou legado / forçou). Tela do
admin conferida no navegador; bloco do healthcheck exercitado com a porta certa e com a errada.

---

## 2026-07-28b (tetos do chat: resposta por nível, corte de contexto e truncamento registrado)

> Backend `master` **`0ab7f26`**. Frontend inalterado.

### Alterado
- **Teto da resposta segue o nível do aluno**: `max_tokens` 1024 → **1536** (básico) /
  **3072** (avançado), via `max_tokens_resposta(contexto)` reusando `nivel_do_contexto`. O 1024
  foi fixado antes de existir o modo Avançado, que pede fórmula e formalismo — ~3 mil
  caracteres em português, ou seja, a resposta terminava no meio da frase.
- **Contexto do pipeline**: 8000 → **12000 caracteres**. O teto existe porque o contexto vem no
  corpo da requisição (o cliente o monta e, no modal, inclui o script gerado): sem ele, quem
  chama decide quanto o servidor gasta em tokens.
- Ambos passam a aceitar env (`CHAT_MAX_CONTEXTO_CHARS`, `CHAT_MAX_TOKENS`,
  `CHAT_MAX_TOKENS_AVANCADO`), no padrão que o rate limit já usava. **Temperatura segue 0,4 e
  NÃO é configurável**: subir não compra profundidade, compra invenção.
- `nivel_do_contexto` virou público no `tutor_kb` (o chat também decide pelo nível).

### Corrigido
- **O corte do contexto partia uma linha do JSON** (`texto[:8000]`), entregando ao modelo campo
  pela metade (`"modelo": "random_fo`) — pior que a ausência do campo. Agora corta em fim de
  linha e informa quantos caracteres ficaram de fora, como já se fazia por ficha inteira na KB.
- **O corte da resposta era invisível**: `finish_reason: "length"` era ignorado. Agora vira
  `truncada_no_teto` na telemetria do chat + warning no log, nos dois caminhos (stream e não).
  O teto passa a ser mensurável em vez de virar reclamação.

### Nota de método
Os valores (antigos e novos) são folgas conservadoras, **não** calibração empírica. O registro
de truncamento existe justamente para que o próximo ajuste use dado.

### Verificação
**522 passed, 1 skipped** (7 testes novos: teto por nível, corte que não parte linha,
`finish_reason` na telemetria). Relato para a escrita: `handoffs/2026-07-28-tetos-do-chat-tutor.md`.

---

## 2026-07-28 (o desafio não corrige mais a raia errada)

> **Implantado em 28/07/2026 14h57** (junto com a leva 07-28b). Backend `master` **`1898d2d`**.
> Frontend: ver changelog do repo do frontend.

### Corrigido
- **O tabuleiro do aluno deixou de receber `lane`** (`GET …/tabuleiro`). A etapa a que a peça
  pertence é justamente o que o desafio pergunta: enviá-la deixava a resposta na resposta da
  API — e era o que permitia o clique único da tela acertar a coluna sozinho.
- **A rubrica passou a enxergar a peça fora de lugar**, que antes era ignorada:
  `Contexto.metas(lane)` só considera peça DAQUELA etapa e `estrutura-minima` só conta a etapa
  como preenchida quando ela recebe peça do tipo certo. Sem isso, uma métrica largada na coluna
  do modelo satisfazia `modelo-compativel` (métrica não declara `tarefa`, logo "nada
  incompatível") e um pipeline com modelo e métrica trocados de coluna tirava **10,0**
  (verificado contra a revisão anterior); hoje tira 4,4.

### Adicionado
- Regra `peca-na-etapa-certa` (peso 2), com texto que explica o papel de cada etapa. Mesma
  guarda de `sem-distrator`: entrega em branco não "acerta" a regra.
- 4 testes de rubrica (peça na etapa errada, na certa, métrica na coluna do modelo sem ganhar
  ponto, pré-processador fora de lane que não conta como família) e o contrato do tabuleiro sem
  `lane`. Suíte: **515 passed, 1 skipped**.

---

## 2026-07-27b (conteúdo avançado nas 61 fichas + pré-processamento no chat)

> Backend `master` **`ee69abf`**. Frontend inalterado. Exige rodar `seed_conteudo`.

### Adicionado
- **Fundamentos e Na prática nas 4 categorias que faltavam**: métricas (12), pré-processadores
  (10), gráficos (10) e fontes de coleta (5) — com a leitura adaptada a cada uma (num gráfico,
  `otimiza` é a pergunta que a figura responde; coleta não tem fórmula). Cobertura: **61/61**.
- `formula` nos três encoders e nos gráficos que não tinham; a do card passou a ser
  exatamente a do bloco (7 pré-processadores e 5 gráficos sincronizados).
- **Pré-processamento entrou na base de conhecimento do chat** (`app/tutor_kb.py`): o aluno
  pergunta "por que escalar?" tanto quanto pergunta sobre o modelo.

### Corrigido
- O corte por espaço da base de conhecimento descartava **meia ficha** (corte por caractere).
  Agora descarta fichas inteiras e avisa quantas ficaram de fora. Tetos ampliados (8000 básico
  / 14000 avançado) porque só o índice ocupa ~4,5 mil caracteres — com o teto antigo cabia
  pouco mais de uma ficha.

### Notas
- CI passou a cobrar os blocos **por categoria** (`EXIGENCIAS_AVANCADO`), incluindo `import` no
  código do bloco prático e espelho da fórmula.
- Testes: 511 passed, 1 skipped.

---

## 2026-07-27 (modo Avançado de verdade: nível no perfil, no chat e conteúdo à altura)

> Backend `master` **`a9c2eba`** / Frontend `mestrado-iana` `8e4e774`. Sem migração
> (`nivel_tutor` ausente = básico); exige rodar `seed_conteudo` para o conteúdo novo.

### Alterado
- **O nível virou preferência do perfil.** `db.usuarios.nivel_tutor` + `GET/PUT
  /usuario/preferencias` (o id vem do JWT: ninguém muda o de outro) e o campo volta no login.
  Antes o toggle Básico/Avançado era estado de tela: cada painel nascia em Básico e a escolha
  se perdia no F5.
- **O conteúdo avançado passou a chegar ao LLM.** `_resumo_compacto` recebe o nível: no básico
  segue a explicação simples (500 chars); no avançado vai a **descrição técnica inteira**
  (1200), o **efeito** e o **quando ajustar** de cada hiperparâmetro, fundamentos, armadilhas e
  a leitura de referência. Antes o texto técnico era inalcançável — `resumo_basico` vencia
  sempre. O teto do bloco sobe para 9000 chars no avançado (com 6000, o corte caía no meio da
  primeira ficha).
- A instrução de sistema ganhou a regra de profundidade por `nivel`.

### Adicionado
- **Blocos `fundamentos` e `pratica`** no schema do conteúdo, no card (só em Avançado), no
  editor do admin e na base de conhecimento do chat.
- **24/24 modelos** com Fundamentos (fórmula, o que otimiza, pressupostos, complexidade,
  leitura) e Na prática (pipeline sklearn com CV/busca, ordem de ajuste, armadilhas,
  diagnóstico). **`formula` saiu de 0/24 para 24/24** — a documentação prometia fórmula no modo
  Avançado desde sempre.
- CI cobra os dois blocos nas categorias já convertidas (`tests/test_conteudo_loader.py`).

### Notas
- Faltam métricas (12), pré-processamento (10), gráficos (10) e coleta (5) — mesma receita.
- Testes: 498 passed, 1 skipped.

---

## 2026-07-26k (instrução do tutor: público da ONIA e edição sem deploy)

> Backend `master` **`7d40bed`** / Frontend `mestrado-iana` `53f1853`. Sem migração
> (a personalização é uma chave nova em `db.configuracoes_tutor`, opcional).

### Alterado
- **Público do tutor**: o `system` do chat passou a descrever estudantes da **ONIA** (Olimpíada
  Nacional de Inteligência Artificial, que seleciona quem representa o Brasil na **IOAI**), do
  **8º ano do Fundamental ao 1º ano do Superior** — antes dizia "ensino fundamental e médio".
- O texto saiu de uma constante no router para `app/conteudo/kb_tutor_chat.py`
  (`SYSTEM_PROMPT_TUTOR`), mesma ideia das boas-vindas: fonte versionada + override no banco.
- Nova frase para **distinguir quem pergunta**: o assistente de preenchimento do catálogo
  (conf-pipeline, professor/admin) usa o MESMO endpoint e recebia respostas escritas para aluno.

### Adicionado
- `GET /tutor/system-prompt` (autenticado) e `PUT /tutor/system-prompt` (**admin**): editar a
  instrução sem deploy. Texto vazio remove a personalização; teto de
  `MAX_SYSTEM_PROMPT_CHARS = 6000` porque o `system` divide a janela com o contexto do pipeline
  (8000) e a base de conhecimento (6000). Cada escrita é auditada em `db.tutor_audit`
  (`pipe: 'llm'`, o mesmo histórico que a aba mostra).
- `_system_prompt_vigente` resolve o texto por requisição com `try/except`: falha de leitura da
  configuração cai no versionado em vez de derrubar o chat.

### Notas
- Documentação alinhada: `docs/dissertacao/03-chatbot-tutor-cag.md` (a transcrição do prompt
  estava **desatualizada**) e `docs/DOCUMENTACAO.md`.
- Testes: 488 passed, 1 skipped (novo `tests/test_tutor_system_prompt.py`, 15 casos — inclui
  regressão de rota, já que `PUT /tutor/{id}` é catch-all e uma vez roubou `/tutor/modelo`).

---

## 2026-07-26j (desafio de montagem nasce de um dataset de exemplo)

> Backend `master` **`a1f6f61`** / Frontend `mestrado-iana` `09b419e`. Sem migração
> (campos novos do gabarito são opcionais; desafios antigos seguem valendo).

### Adicionado
- **A criação do desafio começa pela base.** `app/desafios/base_dados.py` monta o perfil de um
  dataset de exemplo: **tarefa** derivada de `DatasetType` (mesmo vocabulário do gabarito),
  **enunciado sugerido** (pergunta-guia + descrição + alvo) e as três características da base
  (`faltantes`/`texto`/`escalas_diferentes`) **lidas do dataframe real** — antes eram caixas
  marcadas à mão que podiam desmentir a base e tornar uma regra impossível de satisfazer.
  Servido por `GET /toy_datasets/{id}/perfil-desafio` (professor/admin; carrega dataframe, com
  cache e fallback conservador).
- `gabarito.dataset` e `gabarito.sortear_pecas` (`app/schemas/turmas.py`). Com `dataset`
  preenchido, o **servidor** deriva a `tarefa` (`_gabarito_com_dataset`) e recusa id
  inexistente com `400`. Com `sortear_pecas: false`, valem as peças escolhidas pelo professor.
- **`_garantir_minimo`** em `app/desafios/sorteio.py`: o tabuleiro sempre permite uma solução.
  Completa lane exigida sem peça — ou sem peça compatível com a tarefa —, as famílias de
  pré-processamento que a base exige, e a etapa de pré-proc quando exigida sem que a base peça
  família nenhuma. Ignora `vetar` se o veto é o que impede a solução (em silêncio).
- `GET .../tabuleiro` devolve `dataset_nome`: o aluno vê a base como chip no tabuleiro.

### Corrigido
- Marcar "Exigir a etapa de pré-processamento" numa base sem faltantes/texto produzia um
  tabuleiro **sem nenhuma peça de pré-processamento** — `estrutura-minima` (peso 3) ficava
  insatisfazível.

### Refatorado
- Carregadores de dataset (sklearn/UCI/geradores) saíram do router para
  `app/models/dataset_loaders.py`, sem mudança de comportamento (o `400` do UCI não configurado
  é preservado via `DatasetNaoConfigurado`). É o que permite inspecionar a base fora da coleta.

### Notas
- Testes: 473 passed, 1 skipped (novo `tests/test_desafio_dataset.py`, 24 casos).

---

## 2026-07-26h (boas-vindas do tutor + entrada dos desafios + contas da banca)

> Backend `master` **`c3faae2`** / Frontend `mestrado-iana` `ac512ff`.
> Sem migração de dados; dois seeds idempotentes novos.

### Corrigido
- **O tutor não recebia quem chegava.** O `seed-mongodb.sh` gravava em
  `db.tutor {pipe:'inicio'}` um `texto_pipe` de uma frase, e o banco vence o fallback do
  frontend — em produção o aluno lia só "Bem-vindo ao tutor de Aprendizado de Máquina!". As
  boas-vindas agora são versionadas em `app/conteudo/kb_tutor_inicio.py` (resumo do Manual
  do Aluno: 4 passos, onde pedir ajuda, onde ficam turmas/desafios/projetos/manual),
  semeadas por `scripts/deploy/seed_tutor_inicio.py` (roda no `deploy.sh`) e devolvidas
  como fallback pelo `GET /tutor/?pipe=inicio`. O seed **preserva** texto editado pelo
  admin (só substitui o legado de uma frase; `--forcar` sobrescreve).
- **Peças do desafio mostravam o slug** (`mlp_regressor`, `robust_scaler`) em vez do nome
  legível: `_nome` já tentava `nome → label → titulo`, mas a projeção do Mongo em
  `app/desafios/catalogo.py` não trazia `label`/`titulo` — o fallback nunca tinha o que ler.
- **`/atividades` mostrava "Acesso negado" ao abrir** como professor: a tela chamava
  `GET /usuario/` (admin-only) só para preencher o seletor de usuário; agora só o admin
  chama, e o professor segue filtrando por usuário clicando na linha.

### Adicionado
- `GET /turmas/minhas/desafios` — desafios de montagem de todas as turmas do aluno **numa
  chamada**, com tentativas e melhor nota (sem gabarito). A Área de Trabalho mostra um aviso
  quando há desafio nunca tentado, indo direto a ele quando é o único; a lista de turmas
  ("Turmas e desafios") passa a mostrar os desafios primeiro, com o histórico do aluno.
- `scripts/deploy/seed_usuarios_demo.py` — contas de demonstração (admin/professor/aluno) com
  turma, dois desafios e histórico real (submissões corrigidas pela rubrica + duas
  submissões de pipeline no Iris). Idempotente, aborta se o e-mail já for de conta real, e
  `--remover` apaga tudo. Doc: `docs/contas-demo-banca.md`.

### Notas
- `ShellComponent` (barra lateral com Home/Pipeline/Resultados) é **código morto** nesta
  branch: `InternoComponent` nunca é roteado. Por isso a entrada dos desafios foi para o
  aviso da Área de Trabalho e para o menu do avatar (renomeado "Turmas e desafios").
- Testes: backend 449 passed/1 skipped; frontend 153/153.

---

## 2026-07-26g (documentação de arquitetura + nome de base normalizado)

> Backend `master` **`a7c133e`** / Frontend `mestrado-iana` `11888e4` (bundle `main-EDMYYQK2.js`).
> Backup `/home/ubuntu/backups/deploy-20260726-125237`. Sem migração.

### Adicionado
- `docs/desafios-montagem.md`, `docs/evolucao-aluno.md`, `docs/divisao-treino-teste.md` —
  arquitetura, decisões não óbvias e onde estão os testes de cada funcionalidade.
- `docs/DOCUMENTACAO.md`: pasta `desafios/`, seções **3.8** (divisão/estratificação) e **3.9**
  (avaliação da aprendizagem), coleções `atividades` (`tipo`/`gabarito`) e `submissoes_montagem`.

### Corrigido
- `/pipelines/evolucao` comparava o nome da base cru: o mesmo dataset chega como `Iris` pelo
  assistente de coleta e `Iris.xlsx` por outros caminhos, o que **fragmentava a história do
  aluno** em duas bases. `normalizar_nome_base` (minúsculas, sem extensão) resolve. 2 testes
  novos; suíte **443 passed, 1 skipped**.

---

## 2026-07-26f (aviso efetivo de estratificação + testes da divisão em 3 níveis)

> Backend `master` **`bf91612`** / Frontend `mestrado-iana` `3cec11c` (bundle `main-PTQJ6V2W.js`).
> Backup `/home/ubuntu/backups/deploy-20260726-115357`. Sem migração.

### Adicionado
- `aviso_estratificacao(pedido, estratificou)` em `configuracao_treinamento`: uma única
  mensagem para as quatro portas de entrada. CSV, XLSX, URL e dataset de exemplo passam a
  devolver `stratify` **efetivo** + `aviso_estratificacao` (antes só a redivisão avisava; o
  upload corrigia o valor em silêncio).

### Corrigido
- **Ingestão por URL:** o `stratify` pedido era ignorado e a config gravava `stratify: true`
  mesmo assim. Agora usa `dividir_dataframe` e grava o efetivo (sem alvo escolhido na
  ingestão, não estratifica).

### Testes
- Novo `tests/test_divisao_treino_teste.py` (16), em três níveis:
  - **unidade** (`dividir_dataframe`): treino/teste disjuntos e somando o total, proporções
    preservadas quando estratifica, fallback da categoria com 1 exemplo, sem alvo/sem
    embaralhar não estratifica, override do servidor, 400 quando a divisão é impossível;
  - **regressão do vazamento** (datasets de exemplo): o treino não é mais o dataframe
    inteiro, nenhuma linha de teste aparece no treino, proporções de classe preservadas nos
    dois lados, `content_completo_base64` gravado e `shuffle/stratify` na config;
  - **integração** (redivisão): redividir duas vezes não encolhe o dataset, aviso e valor
    efetivo chegam ao cliente, regressão não estratifica, escolha explícita do aluno vence.
- Suíte: **441 passed, 1 skipped**.

---

## 2026-07-26e (estratificação por padrão + fim do vazamento nos datasets de exemplo)

> Backend `master` **`4a6ef48`** / Frontend `mestrado-iana` `de8301b` (bundle `main-OP3WGDPI.js`).
> Backup `/home/ubuntu/backups/deploy-20260726-110345`. Sem migração.

### Alterado
- `dividir_dataframe` devolve também **se estratificou** e, quando o dataset não permite
  (categoria com um único exemplo), cai numa divisão simples em vez de recusar a operação —
  com o padrão ligado, um erro duro barraria dados reais de aluno (antes: 400 no upload).
- `POST /configurar_treinamento/{tipo}/{id}/redividir`: `stratify` virou `Optional[bool]`;
  `None` = "o cliente não opinou" e o servidor liga quando a config diz classificação.
  A resposta traz o valor **efetivo** e `aviso_estratificacao` quando pediu e não deu.
- Uploads CSV/XLSX passaram a usar o mesmo divisor (removida a duplicação e o 400 duro).

### Corrigido
- **Vazamento treino/teste nos datasets de exemplo** (`toy_datasets`): `content_treino`
  recebia o dataframe inteiro e `content_teste` a cauda de 25% — o teste era subconjunto do
  treino e, sem embaralhar, a cauda de um dataset ordenado por classe só tinha uma categoria.
  Agora há divisão real (estratificada em classificação) e o doc guarda
  `content_completo_base64`, que é o que a redivisão relê. Verificado no iris: 112/38, 0 linha
  de teste dentro do treino, proporções preservadas.

### Testes
- 8 novos (`TestEstratificacaoPadrao` + upload). **425 passed, 1 skipped.** Dois testes que
  codificavam o contrato antigo (400 da classe única; default `False` do schema) foram
  atualizados com o motivo no docstring.

---

## 2026-07-26d (Fase 2: evolução do aluno na mesma base)

> Backend `master` **`4204bc0`** / Frontend `mestrado-iana` `bda1294` (bundle `main-5OWPTQIF.js`).
> Backup `/home/ubuntu/backups/deploy-20260726-102325`. Sem migração.

### Adicionado
- **`app/pipelines_evolucao.py`** — trajetória do aluno em cada base que ele já usou. Agrupa
  por `(dataset, alvo)` atravessando atividades e projetos livres, em ordem cronológica, com
  delta vs melhor anterior e vs chute burro (**sinal positivo = melhorou**, inclusive em
  métricas de menor-é-melhor) e o que mudou entre tentativas.
- **`app/metricas/resultado.py`** — leitura dos resultados gravados, EXTRAÍDA de `turmas.py`
  (ranking e evolução precisam da mesma resolução rótulo × slug), mais o **chute burro**
  derivado do que já está no banco: classe majoritária das somas das linhas da matriz de
  confusão; R² = 0 por definição; `None` quando não há baseline barato e honesto.
- **`GET /pipelines/evolucao`** (só os próprios pipelines): aceita `dataset` (repetível) e
  `alvo` — o cliente manda os nomes que conhece e **quem decide a identidade é o servidor**,
  para a regra não viver duplicada nas duas pontas.

### Notas
- Identidade da base **não** começa por `datasetId`: ele é o id do arquivo criado a cada
  carregamento (`coleta-dado.component.ts:261`), então preferi-lo fragmentaria a história.
- Métrica que define "melhorou": a do `criterio` da atividade quando há uma; fora dela, a
  padrão da tarefa (acurácia / R² / silhueta).
- Testes: 24 novos em `tests/test_pipelines_evolucao.py`. Suíte **420 passed, 1 skipped**.
  O patch de `opcoes_metricas` em `test_turmas_fixes.py` mudou de alvo junto com a extração.

---

## 2026-07-26b (desafio: simplificação da rubrica + progresso sem soma)

> Backend `master` **`f17dfb8`** / Frontend `mestrado-iana` `0260394` (bundle `main-7ZCANP7T.js`).
> Backup `/home/ubuntu/backups/deploy-20260726-052138`. Sem migração.

Revisão do que subiu horas antes, contra as *karpathy-guidelines*.

### Removido
- `gabarito.regras` (seleção e repesagem de regras por atividade): nenhuma tela alcançava e
  a rubrica sempre usou o conjunto completo — flexibilidade sem consumidor. Os pesos seguem
  na biblioteca versionada de `app/desafios/regras.py`. `fixar`/`vetar` ficaram (decisão
  explícita do professor, agora com UI).

### Alterado
- `progresso`: `submissoes` volta a significar **pipelines submetidos** — a Fase 1 tinha
  somado os desafios nesse campo, mudando um número que o professor já lia. Desafios seguem
  em `desafios`/`melhor_nota_desafio`, agora em coluna própria na tela.

### Testes
- Novo teste do contrato do progresso (pipelines e desafios não se somam). 396 passed, 1 skipped.

---

## 2026-07-26 (desafio de montagem de pipeline — Fase 1)

> Backend `master` **`e6e90a5`** / Frontend `mestrado-iana` `a440695` (bundle `main-GT47M2MG.js`).
> Backup `/home/ubuntu/backups/deploy-20260726-044207`. Sem migração.

### Backend
- **Novo pacote `app/desafios/`** — desafio de montagem: o aluno monta o pipeline como
  quebra-cabeça e a montagem é avaliada **sem executar nada**.
  - `catalogo.py`: normaliza as peças a partir de `db.modelos`/`db.metricas`/
    `db.pre_processamento`/`db.coleta_dados` (família do pré-proc **derivada da classe
    sklearn** do bloco `execucao`, para não manter uma lista paralela de slugs).
  - `regras.py`: 8 regras com peso e **texto didático** (estrutura mínima, modelo↔tarefa,
    métrica↔tarefa, escala p/ modelo de distância, imputação quando há faltantes, encoder
    para texto, ordem imputação→escala, sem distrator).
  - `sorteio.py`: tabuleiro **determinístico** por `(atividade, aluno, tentativa)` — o F5
    devolve o mesmo, a próxima tentativa devolve outro; distratores vindos do catálogo.
  - `avaliacao.py`: nota 0–10 pelos pesos das regras **aplicáveis**.
- `db.atividades` ganhou `tipo: 'pipeline' | 'montagem'` (default `pipeline`, sem migração) e
  `gabarito`. `_atividade_doc` só devolve o gabarito para professor/admin da turma.
- Rotas: `GET /turmas/{id}/atividades/{aid}/tabuleiro` (sem gabarito nem o papel das peças)
  e `POST .../submeter-montagem`. `ranking` ramifica por tipo (montagem ordena por nota e
  desempata por **menos tentativas**); `progresso` passa a contar desafios e a melhor nota.
- `db.submissoes_montagem`: coleção própria **sem TTL** (é registro de avaliação, diferente
  da telemetria de `atividade_usuario`, que expira em 90 dias).

### Corrigido (achados da própria verificação)
- `sem-distrator` era satisfeita trivialmente por não montar nada — entrega em branco tirava
  4/10. A regra passou a exigir que o aluno tenha montado algo.
- A submissão aceitava peças **fora do tabuleiro** da tentativa, o que anulava o re-sorteio
  (bastava reenviar o pipeline ideal aprendido no feedback anterior). Agora é 400.

### Testes
- `tests/test_desafio_montagem.py`: 44 testes (regras isoladas, pesos, determinismo do
  sorteio, gabarito não vaza, gates de papel). Suíte: **396 passed, 1 skipped**.

---

## 2026-07-22 (e-mail de convite: marca H2IA Tutor + Aprendizado de Máquina)

### Backend
- `app/routers/usuarios.py`: o e-mail de convite/reenvio deixou de usar a marca antiga
  "Iana / Plataforma de ML" e passa a usar **"H2IA Tutor"** no cabeçalho, corpo, rodapé e
  nos dois assuntos; "Machine Learning" → "Aprendizado de Máquina" no corpo/rodapé.
- Inclui também alterações em andamento em `conf_pipeline.py` e `tutor.py` (publicadas junto).

---

## 2026-07-09 (KB do assistente do admin + fix 404 do GET /tutor)

### Backend `30f47a5`
- Guia de preenchimento do conf-pipeline **versionado** (`app/conteudo/kb_conf_pipeline.py`),
  semeado em `db.tutor {pipe:'conf-pipeline'}` (`scripts/deploy/seed_kb_conf_pipeline.py`,
  idempotente); `GET /tutor/?pipe=conf-pipeline` com fallback no guia versionado; pipe no
  allowlist do upsert. Contexto do chat do admin no conf-pipeline.
- **Fix:** `GET /tutor/?pipe=` devolvia **400** quando o doc não existia (except genérico engolia
  o 404) — visto no log de prod com `pipe=pre-processamento`. 4 testes novos; suíte **353 passed**.

## 2026-07-08 (tutor: upsert de conteúdo por pipe)

### Backend `4ed7562`
- Novo `PUT /tutor/pipe/{pipe}`: upsert do conteúdo de uma etapa pelo slug (allowlist de pipes,
  gate admin/professor, auditoria em `tutor_audit`). Usado pela aba "Início" do conf-tutor para o
  texto de boas-vindas do tutor (pipe `inicio`), mesmo sem doc pré-existente. 4 testes novos;
  suíte **349 passed**.

## 2026-07-08 (upload xlsx de teste + escopo do tutor LLM)

### Backend `3c5043a`
- `POST /coleta_dados/salvar_xlxs` tipo `teste` aceita o arquivo no campo `file` (o frontend usa
  o mesmo campo do CSV); antes 400 "file_teste obrigatório". Testes novos
  (`tests/test_coleta_dados_xlsx.py`, 3).
- `SYSTEM_PROMPT` do chat tutor: responde **somente** sobre ML/plataforma/pipeline do aluno,
  priorizando o pipeline atual (dataset, modelos, hiperparâmetros, métricas); recusa educadamente
  assuntos fora do escopo (antes instruía a responder mesmo fora do contexto). Suíte **342 passed**.

## 2026-07-06 (Artefatos: busca de usuários p/ autocomplete)

### Backend `07c9fa3`
- `GET /artefatos/usuarios?q=&limit=` — regex (nome/email) no servidor, limitado (escala p/
  milhares), gated admin/professor. Teste incluído. Suíte **342 passed**.

## 2026-07-06 (Artefatos: /contexto liga run à atividade/turma)

### Backend `b7b320a`
- `GET /artefatos/{run_id}/contexto`: acha as submissões (pipelines com `atividade_id`) cujo
  `resultadoTreinamento` referencia a run (`$objectToArray` → `_tr.v.mlflow_run_id`) e resolve
  atividade + turma. Sem tocar no treino. Teste incluído. Suíte **341 passed**.

## 2026-07-06 (Artefatos: dataset_nome gravado na run)

### Backend `0dbd5b5`
- `DatasetRequest.dataset_nome` (opcional) → `registrar_run_usuario` grava na run;
  `listar_runs` filtra por `dataset`; `/facetas` expõe `datasets`. Não retroativo.
  Testes: filtro + faceta. Suíte **340 passed**.

## 2026-07-06 (Artefatos: filtros modelo/papel + /facetas)

### Backend `b1f6831`
- `listar_runs` aceita `modelo` e `papel` (usuario_role); novo `GET /artefatos/facetas`
  (modelos/papéis distintos p/ os selects). dataset/professor/turma não são gravados na run.
  Testes: filtro + facetas. Suíte **340 passed**.

## 2026-07-05 (admin: supervisão global de turmas)

### Backend `77aeeda`
- Admin passa a **ver e gerenciar TODAS as turmas** (de qualquer professor): `listar_turmas`
  sem filtro de dono para admin; `_turma_do_professor`/`_turma_membro`/`obter_turma` liberam
  admin em qualquer turma (atividades, ranking, progresso, alunos). Professor segue restrito
  ao que é seu. +3 testes de regressão. Suíte **338 passed**.

## 2026-07-05 (correções da revisão de código — Turmas)

### Backend `14746d0`
- **Ranking consertado (bug crítico):** buscava a métrica pelo slug (`accuracy_score`), mas
  `resultadosDasAvaliacoes` é indexado pelo **rótulo** (`Acurácia`) → ranking sempre vazio.
  Agora resolve o rótulo em `db.metricas` e tenta ambas as chaves; **deduplica por aluno**
  (mantém a melhor submissão) e usa projeção (não puxa `resultadoColetaDado`).
- **Chat do aluno gated por turma:** professor só lê o histórico de alunos das **suas** turmas
  (admin vê todos) — LGPD/menores.
- **`is_public` no servidor:** só professor/admin publicam (antes o gate era só no front → aluno
  podia `POST is_public:true`).
- **`atividade_id`/`turma_id` validados** contra participação na turma (impede injeção no ranking);
  `turma_id` canônico vem da atividade.
- **`progresso` escopado à turma** (submissões/último acesso) + N+1 → agregações e `$in`.
- **Índices** novos (turmas.codigo único, atividades.turma_id, pipelines.atividade_id/turma_id);
  valida `aluno_id`; remove no-ops. Testes: `test_turmas_fixes.py` (13). Suíte **334 passed**.

## 2026-07-04 (Turmas & Atividades + chat do aluno + fix de logs)

### Backend `aec30b7` (+ `e786757` logs)

- **Turmas & Atividades:** novo `app/routers/turmas.py` (montado `/turmas`) + `app/schemas/turmas.py`;
  coleções `db.turmas`/`db.atividades`. Endpoints: criar/gerir turma, adicionar/remover alunos,
  **entrar por código** (aluno), criar/listar/excluir atividades (template = pipeline parcial),
  **ranking** por métrica (lê pipelines por `atividade_id`), **progresso** da turma. Escritas gated
  `exigir_admin_ou_professor`; `ObjectId` validado.
- **Submissão:** `PipelineCreate/Update` + doc ganham `atividade_id`/`turma_id` (a submissão do aluno
  é um pipeline ligado à atividade → alimenta o ranking).
- **Chat do aluno (professor):** `GET /tutor/chat/aluno/{id}/historico[/{chat_id}]` gated
  professor/admin (transcript completo), com auditoria via `registrar_atividade` (LGPD).
- **Logs do backend:** `get_last_logs` passou a **achatar** o formato do Loguru (`{text, record}`) para
  `{time, level, module, function, message, exception}` — o painel admin renderizava células vazias.
- Testes: `tests/test_turmas.py` (4). Suíte: **321 passed** (317+4), 1 skipped.

## 2026-07-04 (modelo como flavor mlflow.sklearn + endpoint de download)

### Modelo logado no MLflow (configs + exemplo de uso) e baixável. Backend `b94ca13`

- **`app/mlflow_client.py`:** novo `log_sklearn_model` — loga o modelo como **flavor
  `mlflow.sklearn`** (gera `MLmodel`, `requirements.txt`, `python_env.yaml`, `input_example`).
  Loga no **run já ativo** (não recria `start_run`, que dava "Run already active"); usa
  `serialization_format="cloudpickle"` (o default **skops** do MLflow 3.x recusa tipos "não
  confiáveis" como o `KDTree` do KNN). No-op se MLflow off; best-effort.
- **`treinamento_base.py`:** no treino, desserializa os bytes do sandbox e loga o flavor
  (substitui o `log_bytes_artifact` de `model.joblib`). Os bytes em `db.modelos_treinados`
  seguem intactos — `/prever` e `/avaliar_modelos` inalterados.
- **`metricas.py`:** novo **`GET /classificador/modelo/{id}/artefato`** → `.zip` do dir `model/`
  do MLflow (fallback: `model.pkl` + `requirements.txt` fixo com as versões do treino). `ObjectId`
  validado; auth herdada do prefixo `/classificador`.
- Testes: download no fallback (zip com `model.pkl`+`requirements`) e 404. Suíte: **317 passed, 1 skipped**.
- **Atenção:** modelos treinados **antes** deste deploy não têm o flavor → o endpoint usa o fallback
  joblib (funciona). Novos treinos geram o modelo MLflow completo.

## 2026-07-04 (legenda "Erros de Predição por Classe" fora das barras)

### `_desenhar_erros_predicao`: legenda posicionada à direita. Backend `32ac226`

- **Bug:** a legenda `classe prevista` (setosa/versicolor/virginica) do gráfico **Erros de Predição
  por Classe** era desenhada com `ax.legend(...)` sem `loc`, caindo em `loc='best'` **por cima das
  barras** e deixando o gráfico ilegível.
- **Fix (`app/metricas/metricas.py`):** `ax.legend(..., loc='upper left', bbox_to_anchor=(1.02, 1),
  borderaxespad=0)` — legenda fora da área de plotagem; o `bbox_inches='tight'` do `savefig` já a
  inclui na imagem. Sem migração.
- **Atenção:** os PNGs são "queimados" em base64 no momento da avaliação → **re-rodar a avaliação**
  para regenerar (resultados antigos seguem com a legenda sobreposta).
- Verificação: `pytest tests/test_metricas_avaliacao.py` 10 passed; legenda validada por render.

## 2026-07-03 (fix 404 intermitente + API sob `/h2ia/tutor/api/`)

### Sem mudança de código — infra (nginx + systemd). Backend segue em `1a964a5`

- **Bug (404 intermitente em prod):** dois serviços systemd escutavam a **porta 8002** ao mesmo
  tempo (SO_REUSEPORT) — `h2ia-backend.service` (código atual, `/home/ubuntu/ensinado-aprendizado-maquina-back`)
  e uma cópia ANTIGA `h2ia-tutor.service` (`/home/ubuntu/servers/h2ia_tutor/backend`, `2a31d00`,
  11/06). O kernel balanceava conexões entre os dois → parte das requisições caía no backend velho,
  dando **404 aleatório** em rotas adicionadas depois de 11/06 (`conf_pipeline/pre_processamento/todos`,
  `atividades/lote`, `sistema/erro`, `configurar_treinamento/.../redividir`), enquanto `/docs`
  respondia 200. Fix: parado/desabilitado o `h2ia-tutor.service`, reiniciado o `h2ia-backend.service`.
  Depois o unit e a cópia de 1.3G foram **removidos** (limpeza) — só `h2ia-backend.service` na 8002.
- **API movida `/h2ia/api/` → `/h2ia/tutor/api/`:** o app do tutor agora vive todo sob `/h2ia/tutor/`;
  nada fica solto direto em `/h2ia/`. Mudança em nginx (renomeia a `location`, proxy segue p/ 8002)
  + `environment.prod.ts` (front). Path antigo `/h2ia/api/` **removido**.
- Verificação ao vivo: novo path 401/405/422 (rota existe), path antigo 404, docs 200, front 200.
  Backups: frontend/nginx `deploy-20260703-232436`, unit `h2ia-tutor.service.disabled-20260703-231826`.

## 2026-07-01 (Último Acesso em Gerenciar Usuários)

### Login passa a registrar `ultimo_acesso`. Back `5cc55e8` (deploy só backend)
- **Bug:** a coluna **"Último Acesso"** na tela **Gerenciar Usuários** exibia `-` para todos
  os usuários. O wiring frontend→schema→endpoint (`ultimoAcesso` ← `ultimo_acesso`) já estava
  correto; a causa era que o valor **nunca era gravado** — `criar_convite()` inicializava
  `ultimo_acesso: None` e nada o atualizava (nem `login.py`, nem `convite.ativar_conta`).
- **Fix (`app/routers/login.py`):** após validar a senha, `login()` faz
  `colecao_usuario.update_one({"_id": ...}, {"$set": {"ultimo_acesso": datetime.now(utc)}})`
  (antes de serializar `_id`) e reflete o valor na resposta. Aditivo, sem migração.
- **Caveat esperado:** usuários existentes seguem com `-` até o **próximo login** (não há como
  saber o último login real retroativamente); telemetria em `atividade_usuario` poderia lastrear
  um backfill no futuro, mas não foi feito.
- Prod estava em `33a71d8` (já incluía o fix `1208973` da **matriz de confusão zerada**); este
  deploy subiu apenas o fix de login `5cc55e8`, o script de docs `fb192db` e este changelog.
- **Fix propagado para todos os branches de código** (cherry-pick `-x` do `5cc55e8`): `master`,
  `docker-compose-teste`, `feat/catalogo-modelos-tutor-chatbot`, `feat/pipeline-modal-refactor`
  (pushados) + `refactor/security-jwt-dry`, `scripts-deploy` (locais, sem remote). `origin/main`
  é branch órfão só-README (sem código) — não se aplica.
- Verificação: `test_autenticacao.py` **8 passed** (inclui `test_login_sucesso`); login/usuario
  **19 passed**. Front **inalterado**. Backup `/home/ubuntu/backups/deploy-20260701-142638`.
- **Revisão de segurança (`/security-review`): sem achados.** Filtro do `update_one` usa `ObjectId`
  do servidor (não input do usuário), valor é timestamp do servidor, roda só após `verificar_senha`,
  grava só `ultimo_acesso`, e `UsuarioResponse` descarta a chave nova (`extra="ignore"`).

## 2026-06-26 (conteúdo educacional versionado + Básico/Avançado para todos os elementos)

### Conteúdo versionado no repo + seed idempotente + gráficos/datasets como elementos. Front `76dc145` (bundle `main-DR46LGHV.js`) · Back `9b9265c`
- **Conteúdo educacional agora é dado versionado no repositório** (`app/conteudo/*.json`), não
  mais migrado ad-hoc na prod. Fonte canônica → `seed_conteudo.py` (idempotente, não-destrutivo:
  só `$set conteudo`, nunca toca `execucao`/`habilitado`) → MongoDB. Schema Pydantic
  (`app/conteudo/schema.py`) valida o JSON em CI. Bootstrap inicial exportado da prod
  (`export-conteudo.py`). Bloco `conteudo` do `migrate-preproc-conteudo.sh` marcado superseded.
- **Todos os elementos do pipeline com modo Básico (lúdico) + Avançado (fórmula/código) + link:**
  - **24 modelos** e **12 métricas**: enriquecidos com `exemplo_codigo` (Python real, verificado
    rodando) — modelos (24) + métricas (12); `link_yellowbrick` onde há viz (12 modelos + 2 métricas).
    Campos originais preservados byte-a-byte (aditivo).
  - **10 pré-processadores**: conteúdo completo novo (defaults verificados na doc sklearn).
  - **5 fontes de coleta** (dados/xlsx/csv/json/dataset): conteúdo novo.
  - **10 gráficos Yellowbrick**: nova coleção **`db.graficos`** (elementos de 1ª classe), com
    Básico/Avançado/`link_yellowbrick`. `GRAFICOS_IDS` + `grafico_id` em cada viz gerada
    (`metricas.py`, título inalterado p/ não quebrar artefatos MLflow). Endpoints
    `GET /conf_pipeline/graficos/{todos,valor}` + `PUT /graficos_doc/{valor}`.
  - **Datasets**: `GET /toy_datasets/{name}/conteudo` (read-only) + `conteudo_card()` derivado.
- **Seed em prod:** 24+12+10 atualizados, 5 coleta, 10 gráficos inseridos; 2ª rodada = 0 (idempotente).
- Testes: **315 passed, 1 skipped** (+`test_conteudo_loader`, +`test_conf_pipeline_graficos`,
  +`grafico_id`/dataset conteudo). Backup `/home/ubuntu/backups/deploy-20260626-075927`.

## 2026-06-23

### Tutor drawer na área de trabalho, itens da trilha e correção do seletor de LLM. Front `1697078` (bundle `main-4XBKEVN2.js`) · Back `9b3bac5`
- **Seletor de LLM (conf-tutor):** corrigido o **422 ao trocar o modelo** — era colisão de rota: `PUT /tutor/{id}` (catch-all de `tutor.py`) capturava `PUT /tutor/modelo` como `id="modelo"` e validava o corpo como `AtualizarContextoRequest`. `chat_tutor.router` passou a ser registrado **antes** de `tutor.router` em `app/main.py`, fazendo a rota exata `PUT /tutor/modelo` vencer o catch-all. Teste de regressão em `tests/test_chat_tutor.py`. `pytest`: **290 passed** (1 skipped).
- **Frontend (sem mudança de backend nestes itens):** painel do tutor da área de trabalho virou **drawer lateral**; corrigida a sobreposição de textos no chat; UX do seletor de LLM (bloqueio com progresso durante o health-check + listas Ativos/Inativos); itens da trilha (`.pipeline-item`) re-estilizados via `styles.scss` global.

### Artefatos por usuário + UX do modal. Front `fe4ce52` (bundle `main-A7ZA3RLS.js`) · Back `262bab9`
- **Backend:** runs do MLflow agora são **associadas ao usuário** (coleção `mlflow_runs`, gravada no treino via `ContextVar`); `GET /tutor/artefatos` lista por **usuário** e **data** (admin/professor). `get_run_summary` consolidado em `mlflow_client.py`. `pytest`: 289 passed.
- **Admin:** tela `/view-admin/artefatos` reescrita como **tabela de runs** (usuário/data/paginação) → clica e vê o resumo; fim da busca por `run_id` "no escuro".
- **Modal:** tutor virou **drawer lateral** (FAB centralizado na altura; conteúdo em cima, chatbot embaixo); **ℹ️ por item** (métricas/modelos/pré-proc) abre a explicação no tutor e o chat fica ciente do item; etapa de métricas em **2 colunas com subcards** (alinhamento + ícone corrigidos, inline removido); **scroll volta ao topo** ao trocar de etapa; cabeçalho fixo da tabela de atributos sem overlap. Front: 106/106.

### Corrigido — Endpoint de artefatos do MLflow (backend-only). Back `60198bb`
- `GET /tutor/artefatos/{run_id}` reimplementado (era um stub): resumo de run do MLflow 3.x (params/metrics/tags + artefatos com recursão), com **503** (MLflow não configurado), **400** (run_id inválido/longo), **404** (run inexistente). Os 4 testes de `tests/test_artefatos.py` (antes rotulados "falhas de MLflow") eram, na verdade, **testes obsoletos de uma feature removida** — agora passam contra código real. API verificada contra MLflow 3.14. **Suíte do backend: 282 passed, 0 failed** (1 skipped).

### Limpeza — `exigir_admin_ou_professor` consolidado (backend-only). Back `28b413c`
- As 3 cópias idênticas do gate (em `conf_pipeline`/`atividade`/`tutor`) foram unificadas num único helper em `app/security.py`. Comportamento inalterado (282 passed).

### Enhancement — Modelos logados no resumo de artefatos (backend-only). Back `85d1e8d`
- `GET /tutor/artefatos/{run_id}` agora inclui uma chave **`models`** com os modelos logados da run (no MLflow 3.x os modelos viraram entidades `LoggedModel` e não aparecem mais em `list_artifacts`). Busca via `search_logged_models` (filtro `source_run_id`, com fallback + filtro em Python) e degradação graciosa (não quebra o resumo se a busca falhar). **Suíte: 285 passed.**

### UI — Tela admin de artefatos do MLflow (frontend). Front `09055c9` (bundle `main-VEB2T2R6.js`)
- Nova tela admin **`/view-admin/artefatos`** (card no painel) que consome `GET /tutor/artefatos/{run_id}`: busca por `run_id` e exibe status/período, parâmetros, métricas, tags, artefatos e **modelos logados**. Trata 503/404/400 com mensagens amigáveis. Frontend **104/104**.

### Configuração de produção — MLflow ativado (não-código)
- Definido `MLFLOW_TRACKING_URI=sqlite:////home/ubuntu/mlflow/mlflow.db` no `.env` do backend da VM (backup `.env.bak-*`); experimento **`iana-treinamento`** criado com artefatos em `file:///home/ubuntu/mlflow/artifacts`; serviço reiniciado. A partir de agora o treino/avaliação **logam runs no MLflow** (`app/mlflow_client.py`, já existente) e o endpoint/tela de artefatos ficam funcionais (deixam de responder 503). Validado ponta a ponta (run de smoke: params/métricas/artefato lidos pelo endpoint e removido). Store SQLite local, sem porta exposta.

## 2026-06-22

### Adicionado — Telemetria de atividades dos usuários
- Registro da jornada do aluno em `db.atividade_usuario` (ações do pipeline, navegação, chamadas HTTP, erros e uso do tutor) com duração das ações ("tempo preso"). Tela admin/professor em `/atividades` (filtros, paginação, cards de resumo). Front `0a4c7b4` (bundle `main-XMEH6BLD.js`) · Back `9379cf5`.
- Chat: evento canônico no backend com **resumo compacto** (preview + tamanho, sem conteúdo completo) e status `sucesso`/`erro`/`interrompido`; o histórico completo segue em `db.historico_chat`.
- Retenção: índice **TTL** em `atividade_usuario` (env `ATIVIDADE_TTL_DIAS`, default 90 dias); acesso restrito a admin/professor. Política em `CLAUDE.md`.

### Infra
- venv do backend reconstruída com **Python 3.12** (3.13 removido do sistema). `pytest`: 261 passed (5 falhas pré-existentes — 4 MLflow + 1 `test_tutor`).

### Melhorias — Telemetria (P2). Front `502fb4a` (bundle `main-YCVLMARW.js`) · Back `a03e574`
- Backend: validação do `EventoAtividade` (enums `tipo`/`status`, faixas de `duracao_ms`, ISO; **422** em abuso); `GET /atividades` não conta por página (`incluir_total`); `/resumo` em um único `$facet`; truncamento de `detalhes` por campo (preserva estrutura). `pytest`: 270 passed.
- Frontend: interceptor amostra GETs 2xx (25%, sempre logando mutações e erros) e deduplica navegação; `flush` re-tenta só em erro transitório (descarta 4xx); paginação reaproveita o total; `treine-robo` registra `previu`/`desafio_palpite`. 99 testes.

### Análise & UX (P2/P3). Front `ac3de3f` (bundle `main-SWV5IFX5.js`) · Back `d681ae9`
- Backend: rate-limit da ingestão por usuário/janela (`ATIVIDADE_RATE_MAX`/`_WINDOW`; excesso → 429); `GET /atividades/tempo-preso` (ranking de ações por duração média/máx + taxa de erro). `pytest`: 274 passed.
- Frontend: tela do professor/admin com seletor de usuário, **Exportar CSV**, **auto-atualização** (30s), acessibilidade (caption/scope, `aria-live`, badges rotulados), painel **"Onde os alunos demoram/travam"** e atalho **"Ver jornada"**. Acesso de `professor` à tela já liberado no lote anterior.

### Correção — Editor de conteúdo do tutor (backend-only). Back `afa55bb`
- Os PUT de conteúdo do tutor descartavam campos por uma `Union` de Pydantic "lossy" (caía no `Contexto` genérico) → `400 "Nenhum campo para atualizar"`. `PUT /tutor/{id}` agora usa contexto livre (Dict); `/editar-modelos` e `/editar-tipo-aprendizado` usam o modelo tipado de seleção (preservando `supervisionado`/`texto_pipe`).
- **Segurança:** escrita do conteúdo do tutor restrita a **admin/professor** (antes qualquer autenticado podia escrever). `pytest`: 278 passed (só 4 falhas pré-existentes de MLflow). Descoberto ao reativar a suíte após reconstruir o venv (Python 3.12).

---

## 2026-06-21

### Documentação
- Documentação completa do projeto atualizada (`docs/DOCUMENTACAO.md` + PDF) — inclui Léo no Mundo Real, Desafiar o Léo, missão Cachorros e WebGPU/câmera. Front `b4a0658` · Back `bfdd923`.
- Adicionado este `CHANGELOG.md`.

---

## 2026-06-20 — Léo no Mundo Real (classificação de imagens no navegador)

### Added
- **Léo no Mundo Real** (`/leo-mundo-real`, 4º card no `/inicio`): a criança cria categorias, sobe/tira fotos e o Léo aprende por **transfer learning 100% no navegador** (MobileNet + KNN, TF.js), prevendo a categoria de uma foto nova, com barras de confiança, placar e a lição "a IA só sabe o que ensinamos". **Sem backend.** Front `81dc1c0` · bundle `main-BKBSFI7T.js`.
- **WebGPU** com fallback automático para WebGL/CPU (chip na topbar mostra o motor ativo). Front `7e69844` · bundle `main-IQ5AQN7L.js`.
- **Câmera ao vivo** (`getUserMedia`) — botão "📷 Tirar foto" (desktop e celular; exige HTTPS), com "🖼️ Da galeria" como alternativa. Front `fb7b7f3` · bundle `main-NPDWV6GI.js`.

### Notas
- TF.js isolado no **chunk lazy** da rota (bundle inicial inalterado); modelo MobileNet (~16 MB) baixado em runtime na 1ª visita.

---

## 2026-06-20 — Treine seu Robô: Desafiar o Léo + Cachorros; fix Trilha

### Added
- **"🎲 Desafiar o Léo"** (criança × robô): após treinar um dataset de classificação, deck de 5 exemplos reais; a criança chuta a categoria e o robô responde com o **modelo real** (`POST /classificador/prever`); placar 🧒×🤖.
- **Missão 🐶 Cachorros** (regressão altura→peso): pontos viram emojis de cachorro que crescem com o valor previsto, com a reta de tendência por cima. Dataset lúdico **`gen_cachorro`** no backend (`b415d65`).

### Fixed
- **Trilha**: `.bus-slot.add` (span vazio do barramento) virou pseudo-elemento `::after` — mesmo alinhamento, sem nó vazio no DOM.

Front `ee9c092` · bundle `main-K22OL6D6.js` · Back `b415d65`.

---

## 2026-06-20 — Correções do tutor

### Fixed
- **Histórico do chat (500)**: os endpoints usavam `usuario["id"]` (inexistente) → `KeyError`; trocado por `_id`. Back `13da397` (+ teste de regressão).

### Changed
- **Chat compacto** no painel do tutor (rola junto com o conteúdo; ocupa menos espaço). Front `d270664` · bundle `main-WQCLDCK5.js`.

---

## 2026-06-19 — Conteúdo didático verificado + aba Básico + base de conhecimento no chatbot

### Added
- Campo **`conteudo.resumo_basico`** (aba **Básico** em linguagem simples; **Avançado** mantém descrição técnica + fórmula + hiperparâmetros). Front `520e40f` · bundle `main-TC4MVBSP.js`.
- **Chatbot usa a base de conhecimento**: `app/tutor_kb.py` lê o `conteudo` do catálogo e injeta no system prompt (índice do catálogo + fichas dos itens em contexto). Back `1be0437`.
- `base_de_conhecimento/catalogo_tutor/` — espelho legível do catálogo (JSON + 36 fichas .md).

### Changed
- **24 modelos + 12 métricas** com `conteudo` reescrito a partir da doc oficial do scikit-learn (correções de versão: `multi_class`/`penalty`, `n_init='auto'`, `root_mean_squared_error`, AdaBoost; 3 métricas de agrupamento corrigidas). Migração não-destrutiva no DB.

---

## 2026-06-18 — "Treine seu Robô"

### Added
- **Usar o robô — "🔮 Mostra que eu adivinho!"**: sliders por característica + Surpresa + Adivinha → `POST /classificador/prever` (Back `6aeb2f4`). Front bundle `main-Q5E472NZ.js`.
- **Fase B (regressão + agrupamento)**: datasets lúdicos `gen_sorvete` (regressão) e `gen_cardume` (agrupamento); wizard ciente do tipo de tarefa. Back `e6e7791` · Front bundle `main-4NLPZGNG.js`.
- **Fase A + seletor `/inicio`**: nova entrada lúdica `treine-robo` com treino real (classificação); `AuthGuard` com `ROTAS_POR_PAPEL`. Front `0d5aa59` · bundle `main-56NLZGNY.js`.

---

## 2026-06-17 — Trilha de ML + correções

### Added
- **Trilha de ML** (`/trilha`): nova UI do aluno em ramos paralelos (multi-modelo), inspetor didático, código por ramo, exportação. Front `e58750f` · bundle `main-HXCL2M74.js`.
- **Persistência + ingestão por URL**: salvar/abrir projetos; `POST /coleta_dados/url` com anti-SSRF. Front `df89aae` · bundle `main-S264QYC6.js` · Back `7e4c131`.
- **Cadastro consistente de elementos** (conf-pipeline data-driven via `execucao`). Front `cc03bfb` · Back `60204d2`.

### Fixed
- **Treino 500**: `converter_numpy` sanitiza `NaN/Inf → None` (SimpleImputer). Back `8075e54` · Front `2feb021` (`main-GHXLXGBH.js`).
- **Visualizações Yellowbrick**: rótulos/legendas (`finalize()` + fonte DejaVu Sans, `778c68b`/`fcdf9fa`), cores no tema roxo (`3e3822a`), e valores corretos com rótulos string (render via sklearn, `c431019` + `a2fd962`).
- **UX da Trilha**: conectores X|y, modal só-coleta, salvar com barra final, viz comparada. Front `2c4c840` (`main-KY6B66XI.js`).

### Changed
- **Tutor LLM**: health-check dos modelos (`57bd7e7`); estratificação + chip de saúde (Front `GYFHBO3U`/`OBOV3YRB`). LLM em prod → `meta/llama-3.3-70b-instruct` (config no DB).

---

## 2026-06-16 — Pré-processamento fiel + conteúdo educacional

### Added
- Pré-processamento aplicado de verdade no treino (`sklearn.Pipeline` no sandbox); `db.pre_processamento` com `execucao`; campo `conteudo` no catálogo. Front `66b034c` · Back `3615da6`.

---

## 2026-06-15 — Base

### Added
- FAB do tutor + chat NVIDIA + catálogo de modelos expandido. Front `b8e3e0b` · Back `51bdfed`.

---

_Sempre confirme os commits atuais antes de qualquer decisão de produção. O `CLAUDE.md` (raiz do backend) tem o detalhamento completo de cada deploy, backups e notas de migração._
