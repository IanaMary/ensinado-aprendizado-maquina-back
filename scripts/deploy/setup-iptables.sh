#!/bin/bash
# setup-iptables.sh - Abre porta 8000 no firewall da VM (iptables)
# ATENÇÃO: Execute este script após configurar o backend
set -e

echo "=== Configurando firewall (iptables) ==="

# Verificar se a porta 8000 já está aberta
if sudo iptables -L INPUT -n | grep -q "dpt:8000"; then
    echo "Porta 8000 já está aberta no iptables."
else
    echo "Abrindo porta 8000..."
    sudo iptables -I INPUT -p tcp --dport 8000 -j ACCEPT

    # Persistir regras
    if command -v netfilter-persistent &> /dev/null; then
        sudo netfilter-persistent save
    elif command -v iptables-save &> /dev/null; then
        sudo iptables-save | sudo tee /etc/iptables/rules.v4 > /dev/null 2>&1 || true
    fi

    echo "Porta 8002 aberta e regras persistidas."
fi

echo "=== Firewall configurado. Regras atuais para porta 8000: ==="
sudo iptables -L INPUT -n | grep "dpt:8000" || echo "Nenhuma regra encontrada."
