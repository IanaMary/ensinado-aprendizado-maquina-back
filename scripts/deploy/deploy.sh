#!/bin/bash
# deploy.sh - Script principal de deploy do backend
# Uso: ./deploy.sh [--seed]
#   --seed  Executa o seed do MongoDB (apenas primeira instalação)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
BACKUP_DIR="$HOME/backups/deploy-$(date +%Y%m%d-%H%M%S)"

echo "=========================================="
echo "  Deploy H2IA Backend"
echo "  $(date)"
echo "=========================================="

# ---- Backup ----
echo ""
echo "=== [1/6] Fazendo backup das configurações ==="
mkdir -p "$BACKUP_DIR"

if [ -f /etc/nginx/nginx.conf ]; then
    sudo cp /etc/nginx/nginx.conf "$BACKUP_DIR/nginx.conf"
    echo "  Backup: /etc/nginx/nginx.conf"
fi

if [ -d /etc/nginx/sites-available ]; then
    sudo cp -r /etc/nginx/sites-available "$BACKUP_DIR/sites-available"
    echo "  Backup: /etc/nginx/sites-available/"
fi

if [ -d /etc/nginx/sites-enabled ]; then
    sudo cp -r /etc/nginx/sites-enabled "$BACKUP_DIR/sites-enabled"
    echo "  Backup: /etc/nginx/sites-enabled/"
fi

if [ -d /etc/systemd/system ]; then
    sudo cp -r /etc/systemd/system "$BACKUP_DIR/systemd-system"
    echo "  Backup: /etc/systemd/system/"
fi

if crontab -l &>/dev/null; then
    crontab -l > "$BACKUP_DIR/crontab.txt"
    echo "  Backup: crontab"
fi

echo "  Backups salvos em: $BACKUP_DIR"

# ---- Atualizar código ----
echo ""
echo "=== [2/6] Atualizando código do repositório ==="
cd "$PROJECT_DIR"
git pull origin main || git pull origin master

# ---- Configurar .env ----
echo ""
echo "=== [3/6] Configurando .env ==="
if [ ! -f "$PROJECT_DIR/.env" ]; then
    if [ -f "$PROJECT_DIR/.env.example" ]; then
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        # Restringe o modo ANTES de escrever segredos: o .env guarda SECRET_KEY (JWT),
        # SMTP_PASSWORD e chaves de LLM; com o umask padrão ele nascia 0644 (legível por
        # qualquer conta local da VM, que poderia forjar tokens de admin).
        chmod 600 "$PROJECT_DIR/.env"
        # Gerar SECRET_KEY
        SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        sed -i "s/CHANGE_ME/$SECRET_KEY/" "$PROJECT_DIR/.env"
        echo "  .env criado (modo 600) com SECRET_KEY gerada automaticamente."
    else
        echo "  AVISO: .env.example não encontrado. Crie o .env manualmente."
    fi
else
    echo "  .env já existe, mantendo configuração atual."
fi

# ---- Instalar dependências Python ----
echo ""
echo "=== [4/6] Instalando dependências Python ==="
cd "$PROJECT_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  Dependências instaladas."

# ---- Seed MongoDB (apenas com --seed) ----
if [ "$1" = "--seed" ]; then
    echo ""
    echo "=== [5/6] Executando seed do MongoDB ==="
    bash "$SCRIPT_DIR/seed-mongodb.sh"
else
    echo ""
    echo "=== [5/6] Seed do MongoDB ignorado (use --seed para popular) ==="
fi

# ---- Seed do conteúdo educacional (sempre; idempotente e não-destrutivo) ----
echo ""
echo "=== [5b/6] Semeando conteúdo educacional (app/conteudo/*.json) ==="
cd "$PROJECT_DIR"
PYTHONPATH="$PROJECT_DIR" python -m scripts.deploy.seed_conteudo || echo "  AVISO: seed de conteúdo falhou"
# Os três textos versionados também são semeados no boot do backend (app/main.py) — aqui é para o
# resultado (propagou? preservou a edição do admin?) ficar visível no log do deploy.
PYTHONPATH="$PROJECT_DIR" python -m scripts.deploy.seed_tutor_inicio || echo "  AVISO: seed das boas-vindas do tutor falhou"
PYTHONPATH="$PROJECT_DIR" python -m scripts.deploy.seed_kb_conf_pipeline || echo "  AVISO: seed do guia do conf-pipeline falhou"
PYTHONPATH="$PROJECT_DIR" python -m scripts.deploy.seed_system_prompt || echo "  AVISO: seed da instrução do tutor falhou"

# ---- Reiniciar serviço ----
echo ""
echo "=== [6/6] Reiniciando serviço ==="

# Se o serviço não existe, criar
if ! sudo systemctl list-unit-files | grep -q h2ia-backend; then
    echo "  Serviço h2ia-backend não encontrado, criando..."
    sudo tee /etc/systemd/system/h2ia-backend.service > /dev/null << 'SERVICEEOF'
[Unit]
Description=H2IA Backend (FastAPI)
After=network.target mongod.service

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/ensinado-aprendizado-maquina-back
Environment="PATH=/home/ubuntu/ensinado-aprendizado-maquina-back/venv/bin"
ExecStart=/home/ubuntu/ensinado-aprendizado-maquina-back/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8002 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICEEOF
    sudo systemctl daemon-reload
    sudo systemctl enable h2ia-backend
fi

sudo systemctl restart h2ia-backend
sleep 2
sudo systemctl status h2ia-backend --no-pager

# ---- Healthcheck ----
# A porta vem de variável porque o serviço acima escuta na 8002: apontar para a 8000 (como este
# passo fazia) dava AVISO de falha em TODO deploy, com o serviço saudável. E não basta olhar o
# corpo: `{"status":"erro"}` é JSON válido, então `| json.tool` saía 0 e o deploy se declarava
# bem-sucedido com o Mongo fora. Agora conferimos o código HTTP (a rota devolve 503 quando o ping
# ao Mongo falha) E o campo `status`.
PORTA_BACKEND="${PORTA_BACKEND:-8002}"
echo ""
echo "=== Testando healthcheck (porta $PORTA_BACKEND) ==="
sleep 1
HEALTH_BODY=$(curl -s -m 10 -w '\n%{http_code}' "http://localhost:$PORTA_BACKEND/healthcheck" || true)
HEALTH_CODE=$(printf '%s' "$HEALTH_BODY" | tail -n1)
HEALTH_JSON=$(printf '%s' "$HEALTH_BODY" | sed '$d')
echo "  HTTP $HEALTH_CODE — $HEALTH_JSON"
if [ "$HEALTH_CODE" = "200" ] && printf '%s' "$HEALTH_JSON" | grep -q '"status": *"ok"'; then
    echo "  Healthcheck OK"
    HEALTH_OK=1
else
    echo "  FALHA: o backend não respondeu saudável em http://localhost:$PORTA_BACKEND/healthcheck"
    echo "         verifique: sudo journalctl -u h2ia-backend -n 50 --no-pager"
    HEALTH_OK=0
fi

echo ""
echo "=========================================="
if [ "$HEALTH_OK" = "1" ]; then
    echo "  Deploy do backend concluído!"
else
    # Sai diferente de zero: um deploy que termina com o serviço doente não pode reportar sucesso
    # (era o que acontecia — o aviso ia para o meio do log e o script saía 0).
    echo "  Deploy do backend concluído COM FALHA NO HEALTHCHECK"
fi
echo "  Backups: $BACKUP_DIR"
echo "  Logs: sudo journalctl -u h2ia-backend -f"
echo "=========================================="
[ "$HEALTH_OK" = "1" ] || exit 1
