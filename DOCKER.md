# Rodar o Iana em Docker (branch `docker-compose-teste`)

Sobe o sistema inteiro em containers: **MongoDB + backend (FastAPI) + frontend (Angular/nginx)**.

## Pré-requisitos
- Docker + Docker Compose.
- Os **dois repositórios lado a lado** (layout padrão de dev), porque o compose constrói o frontend a partir de `../ensinado-aprendizado-maquina`:
  ```
  Projetos/Iana/
  ├── ensinado-aprendizado-maquina/        # frontend (branch docker-compose-teste)
  └── ensinado-aprendizado-maquina-back/   # backend  (branch docker-compose-teste)  <- rode o compose aqui
  ```

## Subir
```bash
cd ensinado-aprendizado-maquina-back
cp .env.docker.example .env.docker            # ajuste se quiser (gere um SECRET_KEY próprio)
docker compose up --build                     # -d para rodar em background
```

Acesso:
- Frontend: http://localhost:8080
- API (Swagger): http://localhost:8000/docs
- MongoDB: localhost:27017

O nginx do frontend faz proxy de `/api/` para o backend, então o navegador fala só com `localhost:8080` (mesmo origin).

## Primeiro login
O banco sobe vazio. Crie um admin:
```bash
docker compose exec backend python scripts/docker/criar_admin.py
# login: admin@iana.local | senha: admin123  (mude via ADMIN_EMAIL/ADMIN_SENHA)
```

## Catálogo (modelos/métricas)
O banco começa sem o catálogo, então o pipeline aparece vazio. Opções:
- Importar um dump de outro ambiente: `mongorestore --uri mongodb://localhost:27017 --db iana <dump>`.
- Ou popular pelas telas de admin (`conf-pipeline`).

## Serviços opcionais
- **Chatbot tutor**: defina `NVIDIA_API_KEY` no `.env.docker`. Sem ela, o chat responde 503 e o resto funciona.
- **Convite por e-mail**: preencha os `SMTP_*` (App Password do Gmail). Sem isso, o convite não envia e-mail e a API devolve o link na resposta.

## Comandos úteis
```bash
docker compose logs -f backend        # logs
docker compose down                   # parar (mantém o volume mongo_data)
docker compose down -v                # parar e apagar o banco
```
