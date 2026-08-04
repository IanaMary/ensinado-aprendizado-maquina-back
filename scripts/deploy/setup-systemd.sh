#!/bin/bash
# setup-systemd.sh - Cria e habilita o serviço systemd do backend
set -e

echo "=== Configurando serviço systemd h2ia-backend ==="

# O caminho vem do PRÓPRIO script, não hardcoded: o projeto já se mudou de diretório uma vez
# (para /home/ubuntu/servers/Iana em 03/08) e este heredoc reinjetava o caminho antigo na unit,
# derrubando o serviço na primeira vez que alguém rodasse o deploy depois da migração.
PROJETO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
echo "  projeto: $PROJETO"

sudo tee /etc/systemd/system/h2ia-backend.service > /dev/null << EOF
[Unit]
Description=H2IA Backend (FastAPI)
After=network.target mongod.service

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=${PROJETO}
Environment="PATH=${PROJETO}/venv/bin"
# `--host 127.0.0.1` e NÃO `0.0.0.0`: o nginx faz `proxy_pass http://127.0.0.1:8002/`, então
# escutar em todas as interfaces só serve para expor a API na internet em HTTP puro — medido em
# 03/08: `http://<ip>:8002/docs` respondia 200, com token e senha em claro para quem usasse o
# endereço direto, contornando o TLS e o nginx. Todos os vizinhos da VM usam 127.0.0.1.
ExecStart=${PROJETO}/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002 --workers 2
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
