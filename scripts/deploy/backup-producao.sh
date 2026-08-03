#!/bin/bash
# backup-producao.sh — snapshot de pré-deploy: frontend, backend, nginx e a unit do systemd.
#
# Substitui o `cp -a` inline que estava documentado no CLAUDE.md, por dois motivos medidos em
# 03/08 na VM (disco a 72%, `/home/ubuntu/backups` com **15G em 212 diretórios**):
#
#  1. **O backup copiava a `venv`.** De 838M por snapshot, **751M eram `venv/`** — reinstalável a
#     partir do `requirements.txt`, e o próprio deploy a reinstala. O que se quer guardar (`app/`)
#     são 2,2M. Ou seja, ~99% do espaço era desperdício. As exclusões abaixo derrubam o snapshot
#     para a casa dos 10M, o que também o torna rápido.
#  2. **Não havia nenhuma limpeza.** Todo deploy criava mais um e nada saía. Agora há retenção.
#
# Uso:  ./backup-producao.sh            # mantém os últimos 10
#       MANTER_BACKUPS=20 ./backup-producao.sh
#       MANTER_BACKUPS=0  ./backup-producao.sh   # não remove nada
set -euo pipefail

RAIZ_BACKUP="${RAIZ_BACKUP:-$HOME/backups}"
MANTER_BACKUPS="${MANTER_BACKUPS:-10}"
BACKEND_DIR="${BACKEND_DIR:-$HOME/ensinado-aprendizado-maquina-back}"
FRONTEND_DIR="${FRONTEND_DIR:-/var/www/h2ia/tutor}"

TS="$(date +%Y%m%d-%H%M%S)"
DESTINO="$RAIZ_BACKUP/deploy-$TS"
mkdir -p "$DESTINO"

# O que NÃO entra: reinstalável (venv), regenerável (cache de dataset, __pycache__), volumoso e
# já rotacionado em outro lugar (logs), e o histórico do git (que está no remoto).
EXCLUIR=(
  --exclude=venv
  --exclude=.venv
  --exclude=dataset_cache
  --exclude=__pycache__
  --exclude='*.pyc'
  --exclude=.git
  --exclude=logs
  --exclude=node_modules
  --exclude=.pytest_cache
)

if [ -d "$BACKEND_DIR" ]; then
  # `tar | tar` em vez de `cp -a`: é o jeito simples de aplicar --exclude preservando permissões.
  sudo tar -C "$(dirname "$BACKEND_DIR")" -cf - "${EXCLUIR[@]}" "$(basename "$BACKEND_DIR")" \
    | tar -C "$DESTINO" -xf -
  mv "$DESTINO/$(basename "$BACKEND_DIR")" "$DESTINO/backend"
  echo "  backend:  $(du -sh "$DESTINO/backend" | cut -f1)"
fi

if [ -d "$FRONTEND_DIR" ]; then
  sudo cp -a "$FRONTEND_DIR" "$DESTINO/frontend"
  echo "  frontend: $(du -sh "$DESTINO/frontend" | cut -f1)"
fi

[ -d /etc/nginx/sites-available ] && sudo cp -a /etc/nginx/sites-available "$DESTINO/nginx-sites-available"
[ -d /etc/nginx/sites-enabled ] && sudo cp -a /etc/nginx/sites-enabled "$DESTINO/nginx-sites-enabled"
[ -f /etc/systemd/system/h2ia-backend.service ] && sudo cp -a /etc/systemd/system/h2ia-backend.service "$DESTINO/"

# Deixa registrado o que este snapshot representa, para não depender do nome da pasta.
if [ -d "$BACKEND_DIR/.git" ]; then
  git -C "$BACKEND_DIR" rev-parse HEAD > "$DESTINO/COMMIT-backend.txt" 2>/dev/null || true
fi

# As VERSÕES exatas do ambiente, já que a `venv` não entra no snapshot. Sem isto, restaurar
# depende de resolver o `requirements.txt` de novo — e ali só 22 das 120 dependências têm versão
# fixa, então o `pip install` traria versões mais novas. Custa alguns KB e é o que permite
# reconstruir o mesmo ambiente (`pip install -r PIP-FREEZE-backend.txt`). O `scikit-learn` está
# pinado no requirements, mas é só ele: os pickles dos modelos dependem dele, o resto do
# comportamento depende dos outros 98.
for PY in "$BACKEND_DIR/venv/bin/pip" "$BACKEND_DIR/.venv/bin/pip"; do
  if [ -x "$PY" ]; then
    "$PY" freeze > "$DESTINO/PIP-FREEZE-backend.txt" 2>/dev/null || true
    break
  fi
done

echo "  total:    $(du -sh "$DESTINO" | cut -f1)"
echo "$DESTINO"

# ---- Retenção ----
# Só toca em `deploy-*`, o padrão que ESTE script cria. Os `auto-*`, `dbdump-*`, `frontend-*` e
# `absapt.tk.bak.*` são de outras ferramentas e não são meus para apagar.
if [ "$MANTER_BACKUPS" -gt 0 ]; then
  mapfile -t antigos < <(find "$RAIZ_BACKUP" -maxdepth 1 -type d -name 'deploy-*' -printf '%f\n' \
                         | sort -r | tail -n "+$((MANTER_BACKUPS + 1))")
  if [ "${#antigos[@]}" -gt 0 ]; then
    echo "  retenção: mantendo $MANTER_BACKUPS, removendo ${#antigos[@]}"
    for velho in "${antigos[@]}"; do
      sudo rm -rf "$RAIZ_BACKUP/$velho"
      echo "    removido $velho"
    done
  fi
fi
