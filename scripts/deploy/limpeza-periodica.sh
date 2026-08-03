#!/bin/bash
# limpeza-periodica.sh — faxina de disco da VM, para rodar por cron.
#
# Existe porque em 03/08 o disco estava em 72% (139G de 193G) e **nada nunca era removido**:
# `/home/ubuntu/backups` tinha 15G em 212 diretórios. O `backup-producao.sh` já aplica retenção
# quando roda, mas ele só roda em deploy — e deploy é irregular. Isto garante o piso: mesmo sem
# nenhum deploy, o disco não cresce sozinho.
#
# É IDEMPOTENTE e conservador: só mexe no que esta automação cria, e nunca no que é de outro
# projeto (a VM hospeda doodle, hut8, vlp, corretor, reviewer, enade, checker…).
#
# Uso:  ./limpeza-periodica.sh              # aplica
#       DRY_RUN=1 ./limpeza-periodica.sh    # só mostra o que faria
set -uo pipefail

RAIZ_BACKUP="${RAIZ_BACKUP:-$HOME/backups}"
MANTER_BACKUPS="${MANTER_BACKUPS:-10}"
FRONTEND_DIR="${FRONTEND_DIR:-/var/www/h2ia/tutor}"
DIAS_CHUNK="${DIAS_CHUNK:-14}"
DRY_RUN="${DRY_RUN:-0}"

echo "=== limpeza H2IA — $(date -Is) ==="
antes_livre="$(df -h / | awk 'NR==2 {print $4}')"
echo "  disco antes: $(df -h / | awk 'NR==2 {print $5" usado, "$4" livre"}')"

remover() {  # remover <caminho> <rótulo>
  if [ "$DRY_RUN" = "1" ]; then
    echo "    [dry-run] removeria $2"
  else
    sudo rm -rf "$1" && echo "    removido $2"
  fi
}

# ---- 1. Backups de deploy: mantém os N mais recentes ----
# Só o padrão `deploy-*`, que é o que o backup-producao.sh cria. Os `auto-*`, `dbdump-*`,
# `frontend-*` e `absapt.tk.bak.*` são de outras ferramentas e NÃO são nossos para apagar.
#
# **`preservados/` é intocável, e existe por um motivo concreto.** Na primeira limpeza (03/08)
# dois diretórios `deploy-*` NÃO eram cópia redundante de código: `deploy-20260729-123615` tinha
# o **store do MLflow** (`mlflow.db`, snapshot deliberado feito antes de renomear o experimento,
# com 45 runs) e `deploy-epico-20260615-000543` tinha um **`mongodump`**. A retenção os teria
# levado. Snapshot de BANCO não se recupera de um `git pull`: quando aparecer um, mova para
# `preservados/` (que não casa com `deploy-*`) em vez de deixar a retenção decidir.
if [ -d "$RAIZ_BACKUP" ] && [ "$MANTER_BACKUPS" -gt 0 ]; then
  # Ordena por MTIME, nao por nome: os nomes nao sao todos datados (`deploy-conf-tutor-audit`,
  # `deploy-chat-edu`, `deploy-busca-conf`...), e `sort` lexicografico punha essas letras acima de
  # `deploy-2026...` — a retencao apagaria os backups de HOJE e manteria os antigos. Pego no
  # dry-run, antes de rodar de verdade.
  mapfile -t velhos < <(find "$RAIZ_BACKUP" -maxdepth 1 -type d -name 'deploy-*' \
                        -printf '%T@\t%f\n' 2>/dev/null | sort -rn | cut -f2 \
                        | tail -n "+$((MANTER_BACKUPS + 1))")
  echo "  backups deploy-*: $(find "$RAIZ_BACKUP" -maxdepth 1 -type d -name 'deploy-*' | wc -l) encontrados, mantendo $MANTER_BACKUPS"
  for v in "${velhos[@]:-}"; do
    [ -n "$v" ] && remover "$RAIZ_BACKUP/$v" "$v"
  done
fi

# ---- 2. Bundles hasheados órfãos do frontend ----
# O deploy publica POR CIMA (de propósito: aba aberta continua achando o chunk dela), então os
# arquivos antigos acumulam. Depois de `DIAS_CHUNK` nenhuma aba razoável ainda os pede.
if [ -d "$FRONTEND_DIR" ]; then
  n=$(sudo find "$FRONTEND_DIR" -maxdepth 1 -type f \
        \( -name 'chunk-*.js' -o -name 'main-*.js' -o -name 'polyfills-*.js' -o -name 'styles-*.css' \) \
        -mtime "+$DIAS_CHUNK" | wc -l)
  echo "  chunks do frontend com mais de $DIAS_CHUNK dias: $n"
  if [ "$n" -gt 0 ] && [ "$DRY_RUN" != "1" ]; then
    sudo find "$FRONTEND_DIR" -maxdepth 1 -type f \
      \( -name 'chunk-*.js' -o -name 'main-*.js' -o -name 'polyfills-*.js' -o -name 'styles-*.css' \) \
      -mtime "+$DIAS_CHUNK" -delete
    echo "    removidos"
  fi
fi

# ---- 3. Relatório ----
# O cache de dataset se limpa sozinho no código (`_limpar_geracoes_antigas`), então aqui é só
# conferência: se passar de uma geração por dataset, algo regrediu.
CACHE_DS="$HOME/ensinado-aprendizado-maquina-back/dataset_cache"
if [ -d "$CACHE_DS" ]; then
  dup=$(ls "$CACHE_DS" 2>/dev/null | sed -n 's/^\(.*\)\.openml.*\.pkl$/\1/p' | sort | uniq -d | wc -l)
  echo "  dataset_cache: $(du -sh "$CACHE_DS" | cut -f1)$([ "$dup" -gt 0 ] && echo "  ATENÇÃO: $dup dataset(s) com mais de uma geração")"
fi

echo "  disco depois: $(df -h / | awk 'NR==2 {print $5" usado, "$4" livre"}') (antes livre: $antes_livre)"
echo "=== fim ==="
