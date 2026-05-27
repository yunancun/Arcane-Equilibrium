#!/usr/bin/env bash
# trading_ai_pg_dump_cron.sh — OPS-4 GAP-D: daily PG dump wrapper (cron target)
#
# Suggested cron entry (installed by install_pg_dump_cron.sh):
#   0 3 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       OPENCLAW_SECRETS_ROOT=$HOME/BybitOpenClaw/secrets OPENCLAW_BACKUP_ROOT=$HOME/pg_backups \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/trading_ai_pg_dump_cron.sh
#
# Mirrors style of outcome_backfiller_live_cron.sh (lock dir, ts(), log path).
# DRAFT for spec; operator installs via install_pg_dump_cron.sh.

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
BACKUP_ROOT="${OPENCLAW_BACKUP_ROOT:-$HOME/pg_backups}"
RETENTION_DAYS="${OPENCLAW_BACKUP_RETENTION_DAYS:-15}"

LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/trading_ai_pg_dump_cron.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/trading_ai_pg_dump_cron.lock.d"
JSONL="${LOG_DIR}/trading_ai_pg_dump_cron.jsonl"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$BACKUP_ROOT"

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[$(ts)] FATAL: env file missing: $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi

PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_USER=$(grep '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_DB=$(grep   '^POSTGRES_DB='       "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST=$(grep '^POSTGRES_HOST='     "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_PORT=$(grep '^POSTGRES_PORT='     "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-5432}"

if [[ -z "$PG_PASS" || -z "$PG_USER" || -z "$PG_DB" ]]; then
    echo "[$(ts)] FATAL: PG creds incomplete in $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi

export PGPASSWORD="$PG_PASS"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: trading_ai pg_dump already running (lock held)" >> "$LOG"
    exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

DATESTAMP=$(date -u '+%Y-%m-%d')
DUMP_FILE="$BACKUP_ROOT/trading_ai_${DATESTAMP}.dump"
SENTINEL="$BACKUP_ROOT/.last_pg_dump"

START_EPOCH=$(date -u +%s)
echo "[$(ts)] START pg_dump $PG_DB -> $DUMP_FILE" >> "$LOG"

# pg_dump custom format (-Fc) = compressed, parallel-restorable.
# --no-owner --no-privileges = portable across roles.
# Schemas explicitly listed to avoid backing up pg_temp_*.
if pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
        -Fc --no-owner --no-privileges \
        --schema=trading --schema=learning --schema=governance --schema=system \
        --schema=observability --schema=replay --schema=market --schema=public \
        -f "$DUMP_FILE" 2>>"$LOG"; then
    DUMP_RC=0
else
    DUMP_RC=$?
fi

END_EPOCH=$(date -u +%s)
DUR=$(( END_EPOCH - START_EPOCH ))

if [[ $DUMP_RC -eq 0 && -s "$DUMP_FILE" ]]; then
    SIZE_BYTES=$(stat -c '%s' "$DUMP_FILE" 2>/dev/null || echo 0)
    MD5=$(md5sum "$DUMP_FILE" | cut -d' ' -f1)
    echo "[$(ts)] OK  $DUMP_FILE size=$SIZE_BYTES md5=$MD5 dur=${DUR}s" >> "$LOG"
    printf '{"ts":"%s","status":"ok","dump_file":"%s","size_bytes":%s,"md5":"%s","duration_sec":%s,"retention_days":%s}\n' \
        "$(ts)" "$DUMP_FILE" "$SIZE_BYTES" "$MD5" "$DUR" "$RETENTION_DAYS" >> "$JSONL"
    # sentinel for healthcheck
    date -u '+%Y-%m-%dT%H:%M:%SZ' > "$SENTINEL"
else
    echo "[$(ts)] FAIL pg_dump rc=$DUMP_RC dur=${DUR}s" >> "$LOG"
    printf '{"ts":"%s","status":"fail","dump_file":"%s","rc":%s,"duration_sec":%s}\n' \
        "$(ts)" "$DUMP_FILE" "$DUMP_RC" "$DUR" >> "$JSONL"
    # remove zero-byte file
    [[ -f "$DUMP_FILE" && ! -s "$DUMP_FILE" ]] && rm -f "$DUMP_FILE"
    exit "$DUMP_RC"
fi

# ----- 15d retention -----
RETENTION_PRUNED=$(find "$BACKUP_ROOT" -maxdepth 1 -name 'trading_ai_*.dump' -mtime "+${RETENTION_DAYS}" -print -delete 2>/dev/null | wc -l)
if [[ "$RETENTION_PRUNED" -gt 0 ]]; then
    echo "[$(ts)] PRUNED $RETENTION_PRUNED dump(s) older than ${RETENTION_DAYS}d" >> "$LOG"
fi
