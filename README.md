# Iana / H2IA Tutor - Backend (FastAPI)

Este é o repositório backend da plataforma educacional H2IA Tutor, construído com **FastAPI** e **MongoDB**.

Produção: <https://absapt.tk/h2ia/tutor/api/docs> · Frontend: [`ensinado-aprendizado-maquina`](https://github.com/IanaMary/ensinado-aprendizado-maquina)

## O que a API faz

- **Coleta de dados**: upload de CSV/TSV/XLSX/JSON, ingestão por URL (com proteção anti-SSRF) e
  datasets de exemplo; divisão treino/teste com **estratificação por padrão em classificação**.
- **Treinamento real** de modelos scikit-learn em processo isolado (sandbox), montando um
  `Pipeline` com os pré-processadores escolhidos e registrando a execução no MLflow.
- **Avaliação**: métricas por tarefa e visualizações Yellowbrick renderizadas no tema do
  sistema.
- **Catálogo administrável**: modelos, métricas, pré-processadores, fontes de coleta e gráficos
  em coleções do MongoDB, com bloco `execucao` (como roda) e `conteudo` (o que o tutor ensina),
  ambos versionados em `app/conteudo/` e semeados por scripts idempotentes.
- **Tutor**: conteúdo didático por item e proxy de chat com LLM (NVIDIA), com contexto do
  pipeline e base de conhecimento do catálogo (CAG).
- **Turmas e avaliação da aprendizagem**: atividades de pipeline, **desafios de montagem**
  corrigidos por rubrica, ranking, progresso e evolução do aluno na mesma base.
- **Telemetria** da jornada do aluno com retenção por TTL (LGPD — público menor de idade).

## Tecnologias Principais
- **FastAPI**: Framework web de alta performance
- **Motor**: Driver assíncrono para MongoDB
- **Pydantic**: Validação de dados rigorosa
- **scikit-learn & Yellowbrick**: Pipelines de Machine Learning e visualizações
- **JWT**: Autenticação e autorização
- **Pytest**: Suíte de testes funcionais

## 🚀 Como iniciar o projeto localmente

### 1. Requisitos
- Python 3.12+
- MongoDB rodando localmente (ou uma URI do MongoDB Atlas)

### 2. Configuração do Ambiente
Crie um ambiente virtual e instale as dependências:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Variáveis de Ambiente
Copie o arquivo de exemplo e configure suas variáveis:
```bash
cp .env.example .env
```
Edite o arquivo `.env` gerado com a sua `MONGO_URL` e um `SECRET_KEY` seguro.

### 4. Executando a API
```bash
uvicorn app.main:app --reload --port 8000
```
A API estará disponível em `http://localhost:8000`.
A documentação interativa (Swagger) estará em `http://localhost:8000/docs`.

## 🧪 Executando Testes
A suíte de testes funcionais pode ser executada com o `pytest`:
```bash
PYTHONPATH=. pytest
```

## 🌱 Seeds (idempotentes)

O catálogo e os textos do tutor têm **fonte versionada no repo** e são gravados no MongoDB por
scripts que podem rodar quantas vezes for necessário (o `deploy.sh` roda os dois primeiros):

```bash
PYTHONPATH=. python -m scripts.deploy.seed_conteudo          # conteúdo educacional do catálogo
PYTHONPATH=. python -m scripts.deploy.seed_tutor_inicio       # boas-vindas do tutor
PYTHONPATH=. python -m scripts.deploy.seed_kb_conf_pipeline   # guia do assistente do admin
PYTHONPATH=. python -m scripts.deploy.seed_usuarios_demo      # contas de demonstração
```

> `scripts/deploy/seed-mongodb.sh` é a semente da **primeira** instalação e é **destrutiva**
> (`deleteMany`) — não rode em produção.

## 📜 Documentação

| Documento | Assunto |
|---|---|
| [`docs/DOCUMENTACAO.md`](docs/DOCUMENTACAO.md) | Visão geral da API, modelo de dados e fluxos. |
| [`docs/conteudo-educacional.md`](docs/conteudo-educacional.md) | Conteúdo do catálogo (Básico/Avançado) e as boas-vindas do tutor. |
| [`docs/desafios-montagem.md`](docs/desafios-montagem.md) | Desafio de montagem: rubrica, sorteio do tabuleiro e ranking. |
| [`docs/evolucao-aluno.md`](docs/evolucao-aluno.md) | Evolução na mesma base: chute burro e tentativas anteriores. |
| [`docs/divisao-treino-teste.md`](docs/divisao-treino-teste.md) | Divisão treino/teste, estratificação e o vazamento corrigido. |
| [`docs/contas-demo-banca.md`](docs/contas-demo-banca.md) | Contas de demonstração (e como removê-las). |
| [`CHANGELOG.md`](CHANGELOG.md) | Histórico de cada publicação em produção. |

A `main` deste repositório contém apenas o README; o código vive na branch **`master`**, que é
a implantada em produção.
