# Iana / H2IA Tutor - Backend (FastAPI)

Este é o repositório backend da plataforma educacional H2IA Tutor, construído com **FastAPI** e **MongoDB**.

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

## 📜 Mais Documentação
Para documentação detalhada sobre o funcionamento do ecossistema, fluxo de dados, e procedimentos operacionais (como deploy em produção), consulte a pasta `docs/` e os arquivos consolidados `CLAUDE.md`, `AGENTS.md` e `README.md` no nível raiz do projeto.
