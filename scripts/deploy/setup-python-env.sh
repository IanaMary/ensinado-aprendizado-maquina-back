#!/bin/bash
# setup-python-env.sh - Cria venv e instala dependências Python
set -e

echo "=== Instalando dependências Python ==="

cd /home/ubuntu/ensinado-aprendizado-maquina-back

# Instalar pacotes de sistema necessários
sudo apt install -y python3 python3-pip python3-venv python3-dev build-essential

# Criar venv
python3 -m venv venv
source venv/bin/activate

# Atualizar pip
pip install --upgrade pip

# Instalar dependências
pip install -r requirements.txt

echo "=== Dependências Python instaladas ==="
python --version
