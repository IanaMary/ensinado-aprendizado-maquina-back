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
        # Gerar SECRET_KEY
        SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        sed -i "s/CHANGE_ME/$SECRET_KEY/" "$PROJECT_DIR/.env"
        echo "  .env criado com SECRET_KEY gerada automaticamente."
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
echo ""
echo "=== Testando healthcheck ==="
sleep 1
curl -s http://localhost:8000/healthcheck | python3 -m json.tool || echo "AVISO: Healthcheck falhou"

echo ""
echo "=========================================="
echo "  Deploy do backend concluído!"
echo "  Backups: $BACKUP_DIR"
echo "  Logs: sudo journalctl -u h2ia-backend -f"
echo "=========================================="
