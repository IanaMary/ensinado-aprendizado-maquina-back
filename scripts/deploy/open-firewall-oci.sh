#!/bin/bash
# open-firewall-oci.sh - Abre porta 8000 no Oracle Cloud Security List
# Execute este script LOCALMENTE (não na VM), usando OCI CLI configurado
# Pré-requisito: oci CLI instalado e configurado (oci setup)
set -e

echo "=== Configurando Security List da Oracle Cloud ==="

# ============================================================
# ATENÇÃO: Substitua os OCIDs abaixo pelos valores reais do
# seu compartimento e VCN. Para obter:
#   oci iam compartment list
#   oci network vcn list --compartment-id <COMPARTMENT_OCID>
# ============================================================

COMPARTMENT_OCID="${COMPARTMENT_OCID:-}"
VCN_OCID="${VCN_OCID:-}"

if [ -z "$COMPARTMENT_OCID" ]; then
    echo "--- Compartimentos disponíveis ---"
    oci iam compartment list --query "data[?\"lifecycle-state\"=='ACTIVE'].{Nome:name, OCID:id}" --output table
    echo ""
    read -p "Digite o OCID do Compartment: " COMPARTMENT_OCID
fi

if [ -z "$VCN_OCID" ]; then
    echo ""
    echo "--- VCNs disponíveis ---"
    oci network vcn list --compartment-id "$COMPARTMENT_OCID" --query "data[?\"lifecycle-state\"=='AVAILABLE'].{Nome:\"display-name\", OCID:id}" --output table
    echo ""
    read -p "Digite o OCID da VCN: " VCN_OCID
fi

echo ""
echo "Buscando Security Lists na VCN..."
SECURITY_LIST=$(oci network security-list list --compartment-id "$COMPARTMENT_OCID" --vcn-id "$VCN_OCID" --query "data[0].id" --raw-output)

if [ -z "$SECURITY_LIST" ] || [ "$SECURITY_LIST" = "null" ]; then
    echo "ERRO: Nenhum Security List encontrado na VCN."
    exit 1
fi

echo "Security List OCID: $SECURITY_LIST"

# Obter regras existentes
echo ""
echo "Obtendo regras de ingresso atuais..."
EXISTING_RULES=$(oci network security-list get --security-list-id "$SECURITY_LIST" --query "data.\"ingress-security-rules\"")

# Verificar se porta 8000 já existe
if echo "$EXISTING_RULES" | grep -q '"tcp-options".*8000'; then
    echo "Porta 8000 já está no Security List."
    exit 0
fi

# Origem e porta parametrizadas. Em produção o backend fica ATRÁS do nginx (443/TLS),
# que fala com ele em 127.0.0.1 — NÃO exponha a porta do backend à internet. Por isso
# não há mais default 0.0.0.0/0: é preciso declarar ALLOWED_SOURCE explicitamente, e
# a porta segue a que o serviço realmente usa (8002).
ALLOWED_SOURCE="${ALLOWED_SOURCE:-}"
BACKEND_PORT="${BACKEND_PORT:-8002}"
if [ -z "$ALLOWED_SOURCE" ]; then
    echo "RECUSADO: defina ALLOWED_SOURCE (CIDR) — ex.: ALLOWED_SOURCE=10.0.0.0/16 $0"
    echo "Não abrimos a porta do backend para 0.0.0.0/0: ela deve ficar atrás do nginx."
    exit 1
fi
if [ "$ALLOWED_SOURCE" = "0.0.0.0/0" ] && [ "${FORCE_PUBLIC:-}" != "yes" ]; then
    echo "RECUSADO: ALLOWED_SOURCE=0.0.0.0/0 expõe o backend em texto puro à internet."
    echo "Se realmente for intencional, rode com FORCE_PUBLIC=yes."
    exit 1
fi

echo "Adicionando regra para porta ${BACKEND_PORT}/TCP (origem ${ALLOWED_SOURCE})..."

# Construir nova regra como JSON
NEW_RULE="[{\"source\": \"${ALLOWED_SOURCE}\", \"protocol\": \"6\", \"tcpOptions\": {\"destinationPortRange\": {\"min\": ${BACKEND_PORT}, \"max\": ${BACKEND_PORT}}}, \"description\": \"H2IA Backend API\"}]"

# Merge com regras existentes
if [ "$EXISTING_RULES" = "null" ] || [ -z "$EXISTING_RULES" ]; then
    ALL_RULES="$NEW_RULE"
else
    # Remove colchetes externos do JSON existente e junta
    EXISTING_CLEAN=$(echo "$EXISTING_RULES" | sed 's/^\[//;s/\]$//')
    ALL_RULES="[$EXISTING_CLEAN,${NEW_RULE:1}"
fi

echo "Atualizando Security List..."
oci network security-list update \
    --security-list-id "$SECURITY_LIST" \
    --ingress-security-rules "$ALL_RULES" \
    --force

echo ""
echo "=== Security List atualizado. Porta ${BACKEND_PORT}/TCP liberada para ${ALLOWED_SOURCE} ==="
