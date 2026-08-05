#!/usr/bin/env bash
# backup_anexos.sh — Backup diário do diretório de anexos (Fase 1 on-premise,
# ver [[project_plano_fase1_fase2_firestore_r2]]) da LV de dados (vg_data,
# HD 1TB) pra LV de backup (vg_backup, HD 500GB) do servidor físico.
#
# Repartição via LVM em 2026-08-05 (ver [[project_migracao_servidor_local]]):
# SSD só com o SO, vg_data (HD 1TB) guarda Postgres/anexos, vg_backup
# (HD 500GB) guarda backups + reserva pra outros projetos. Caminhos antigos
# (/var/anexos_chamados, /srv/backup_anexos_chamados) não existem mais.
#
# Roda no HOST, fora do Docker — evita depender do container estar de pé e
# acessa as duas LVs diretamente como filesystems do host.
#
# Uso (cron do host, não do container — ver crontab do root em produção):
#   0 2 * * * /caminho/para/sistema_chamados/scripts/backup_anexos.sh
#
# Variáveis de ambiente (opcionais, com default):
#   ANEXO_LOCAL_DIR            origem (default /mnt/data/sistema_chamados/anexos)
#   ANEXO_BACKUP_DIR           destino na LV de backup (default /mnt/backup/sistema_chamados/anexos_snapshots)
#   ANEXO_BACKUP_LOG           arquivo de log (default /var/log/backup_anexos_chamados.log)
#   ANEXO_BACKUP_RETENCAO_DIAS retenção dos snapshots em dias (default 7)

set -euo pipefail

ORIGEM="${ANEXO_LOCAL_DIR:-/mnt/data/sistema_chamados/anexos}/"
DESTINO_BASE="${ANEXO_BACKUP_DIR:-/mnt/backup/sistema_chamados/anexos_snapshots}"
LOG="${ANEXO_BACKUP_LOG:-/var/log/backup_anexos_chamados.log}"
RETENCAO_DIAS="${ANEXO_BACKUP_RETENCAO_DIAS:-7}"
DATA=$(date +%Y%m%d_%H%M%S)

mkdir -p "$DESTINO_BASE/atual" "$DESTINO_BASE/snapshots"

# Sync incremental (rsync) — espelha o estado atual da origem
rsync -a --delete "$ORIGEM" "$DESTINO_BASE/atual/" >>"$LOG" 2>&1

# Snapshot com hardlinks (barato em espaço) + retenção
cp -al "$DESTINO_BASE/atual" "$DESTINO_BASE/snapshots/$DATA" 2>>"$LOG" || true
find "$DESTINO_BASE/snapshots" -maxdepth 1 -mindepth 1 -type d -mtime "+$RETENCAO_DIAS" -exec rm -rf {} \; 2>>"$LOG" || true

echo "$(date -Iseconds) backup_anexos: concluído (origem=$ORIGEM destino=$DESTINO_BASE)" >>"$LOG"
