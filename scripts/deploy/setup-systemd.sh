#!/bin/bash
# setup-systemd.sh - Cria e habilita o serviço systemd do backend
set -e

echo "=== Configurando serviço systemd h2ia-backend ==="

sudo tee /etc/systemd/system/h2ia-backend.service > /dev/null << 'EOF'
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
EOF

sudo systemctl daemon-reload
sudo systemctl enable h2ia-backend
sudo systemctl start h2ia-backend

echo "=== Serviço h2ia-backend configurado e iniciado ==="
sudo systemctl status h2ia-backend --no-pager
