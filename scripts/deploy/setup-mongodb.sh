#!/bin/bash
# setup-mongodb.sh - Instala e configura MongoDB 7.0
set -e

echo "=== Instalando MongoDB 7.0 ==="

# Importar chave GPG
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | sudo gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg

# Detectar versão do Ubuntu
UBUNTU_CODENAME=$(lsb_release -cs)
echo "Ubuntu codename: $UBUNTU_CODENAME"

# Adicionar repositório (usa jammy pois MongoDB 7.0 não tem pacotes para noble/24.04)
echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list

sudo apt update
sudo apt install -y mongodb-org

echo "=== Iniciando MongoDB ==="
sudo systemctl daemon-reload
sudo systemctl enable mongod
sudo systemctl start mongod

echo "=== Verificando MongoDB ==="
mongosh --eval "db.adminCommand('ping')"

echo "=== MongoDB 7.0 instalado e rodando ==="
