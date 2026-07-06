# Changelog — Iana / H2IA Tutor

Histórico de deploys em produção (`https://absapt.tk/h2ia/`). Formato inspirado em
[Keep a Changelog](https://keepachangelog.com); datas em AAAA-MM-DD. Cada entrada cita os
commits (frontend/backend) e o bundle publicado. Fonte: `CLAUDE.md` → _Historical Production Reference_.

> Frontend: `IanaMary/ensinado-aprendizado-maquina` · Backend: `IanaMary/ensinado-aprendizado-maquina-back`.

---

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
