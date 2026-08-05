#!/usr/bin/env bash
# backup_postgres.sh — Backup diário do Postgres de produção (Fase 2, Marco 12)
# pra LV de backup (vg_backup, HD 500GB) do servidor físico.
#
# Repartição via LVM em 2026-08-05 (ver [[project_migracao_servidor_local]]):
# SSD só com o SO, vg_data (HD 1TB) guarda o Postgres em si
# (/mnt/data/sistema_chamados/postgres), vg_backup (HD 500GB) guarda os
# dumps + reserva pra outros projetos.
#
# Roda no HOST, fora do Docker, mas o pg_dump em si executa DENTRO do
# container via `docker exec` — evita precisar de client Postgres instalado
# no host e reaproveita POSTGRES_USER/POSTGRES_DB/POSTGRES_PASSWORD que já
# existem no ambiente do próprio container (nenhuma credencial precisa ser
# duplicada neste script nem no crontab).
#
# Formato -Fc (custom, comprimido) — permite restore seletivo/paralelo via
# pg_restore, ao contrário de um dump SQL puro. Restore:
#   docker exec -i sistema_chamados-postgres-1 pg_restore -U sistema_chamados \
#     -d sistema_chamados --clean --if-exists < dump.pgcustom
#
# Uso (cron do host, não do container — ver crontab do root em produção):
#   30 1 * * * /caminho/para/sistema_chamados/scripts/backup_postgres.sh
#
# Variáveis de ambiente (opcionais, com default):
#   POSTGRES_CONTAINER           nome do container (default sistema_chamados-postgres-1)
#   POSTGRES_BACKUP_DIR          destino na LV de backup (default /mnt/backup/sistema_chamados/postgres_dumps)
#   POSTGRES_BACKUP_LOG          arquivo de log (default /var/log/backup_postgres_sistema_chamados.log)
#   POSTGRES_BACKUP_RETENCAO_DIAS retenção dos dumps em dias (default 14)

set -euo pipefail

CONTAINER="${POSTGRES_CONTAINER:-sistema_chamados-postgres-1}"
DESTINO="${POSTGRES_BACKUP_DIR:-/mnt/backup/sistema_chamados/postgres_dumps}"
LOG="${POSTGRES_BACKUP_LOG:-/var/log/backup_postgres_sistema_chamados.log}"
RETENCAO_DIAS="${POSTGRES_BACKUP_RETENCAO_DIAS:-14}"
DATA=$(date +%Y%m%d_%H%M%S)
ARQUIVO_FINAL="$DESTINO/sistema_chamados_$DATA.pgcustom"
ARQUIVO_TMP="$ARQUIVO_FINAL.tmp"

mkdir -p "$DESTINO"

# Dump direto pro arquivo .tmp — só vira o arquivo "de verdade" se o pg_dump
# terminar com sucesso, pra nunca deixar um dump corrompido/parcial na
# retenção como se fosse válido.
if docker exec "$CONTAINER" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  >"$ARQUIVO_TMP" 2>>"$LOG"; then
  mv "$ARQUIVO_TMP" "$ARQUIVO_FINAL"
  echo "$(date -Iseconds) backup_postgres: concluído ($ARQUIVO_FINAL, $(du -h "$ARQUIVO_FINAL" | cut -f1))" >>"$LOG"
else
  rm -f "$ARQUIVO_TMP"
  echo "$(date -Iseconds) backup_postgres: FALHOU (ver log acima)" >>"$LOG"
  exit 1
fi

find "$DESTINO" -maxdepth 1 -name '*.pgcustom' -mtime "+$RETENCAO_DIAS" -delete 2>>"$LOG" || true
