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

# ---- Autenticação ----
# Sem auth, qualquer processo local (inclusive o que a plataforma executa para os
# pipelines de ML dos alunos) tem read/write/drop no banco de produção. Habilite a
# autorização criando um usuário da aplicação. Guardado por MONGO_APP_PASSWORD para
# ser uma decisão explícita: ligar auth exige que o MONGO_URL do .env passe a incluir
# as credenciais, senão o backend para de conectar.
DB_NAME="${MONGO_DB:-ensinado_aprendizado_maquina}"
if [ -n "${MONGO_APP_PASSWORD:-}" ]; then
    echo "=== Habilitando autenticação do MongoDB ==="
    mongosh --quiet <<EOF
use $DB_NAME
db.createUser({
  user: "h2ia_app",
  pwd: "$MONGO_APP_PASSWORD",
  roles: [{ role: "readWrite", db: "$DB_NAME" }]
})
EOF
    # Liga a autorização e mantém o bind em localhost.
    if ! grep -q "authorization: enabled" /etc/mongod.conf; then
        sudo sed -i 's/^#\?security:.*/security:\n  authorization: enabled/' /etc/mongod.conf 2>/dev/null || \
        printf '\nsecurity:\n  authorization: enabled\n' | sudo tee -a /etc/mongod.conf >/dev/null
    fi
    sudo systemctl restart mongod
    echo "  Auth habilitada. Atualize o .env:"
    echo "  MONGO_URL=mongodb://h2ia_app:<senha>@127.0.0.1:27017/$DB_NAME?authSource=$DB_NAME"
else
    echo "AVISO: MongoDB SEM autenticação (MONGO_APP_PASSWORD não definido)."
    echo "  Mantenha o mongod ligado apenas a 127.0.0.1 (padrão) e nunca exponha a 27017."
    echo "  Para habilitar auth: MONGO_APP_PASSWORD='...' MONGO_DB='...' $0"
fi

echo "=== MongoDB 7.0 instalado e rodando ==="
