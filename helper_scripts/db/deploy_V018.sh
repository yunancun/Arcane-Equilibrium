#!/usr/bin/env bash
# ============================================================
# deploy_V018.sh — paper_state_checkpoint deployment wrapper
# V018 部署腳本：pre-check + migration + 驗證 + 審計日誌
#
# MODULE_NOTE (EN): Operator-run wrapper for V018 (P1-5 A2 cross-restart
#   drawdown continuity). Validates DSN, runs pre-deployment schema check,
#   applies V018 (CREATE TABLE IF NOT EXISTS — idempotent), runs verification
#   SQL, and writes audit log to stderr + file. Safe to re-run.
# MODULE_NOTE (中): operator 執行的 V018 部署包裝器（P1-5 A2 跨重啟 drawdown
#   連續性）。驗證 DSN、部署前 schema 檢查、應用 V018（CREATE TABLE IF NOT EXISTS
#   冪等）、驗證 SQL、審計日誌。可重複執行。
#
# Usage / 用法:
#   source settings/environment_files/basic_system_services.env
#   bash helper_scripts/db/deploy_V018.sh
#
#   # 或使用無密碼 DSN + PGPASSFILE / Or use passwordless DSN + PGPASSFILE:
#   PGPASSFILE=/path/to/pgpass DSN=postgresql://openclaw@127.0.0.1/openclaw \
#     bash helper_scripts/db/deploy_V018.sh
#
# Rollback (僅在尚無寫入時):
#   DROP TABLE IF EXISTS trading.paper_state_checkpoint;
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MIGRATION_FILE="$REPO_ROOT/sql/migrations/V018__paper_state_checkpoint.sql"
AUDIT_LOG="$REPO_ROOT/trading_services/logs/v018_deploy_$(date -u +%Y%m%dT%H%M%SZ).log"

# ----- DB target parsing without password-bearing argv / DB 目標解析（避免密碼進 argv） -----
PGPASS_TMP=""
cleanup_pgpass() {
    [[ -n "$PGPASS_TMP" ]] && rm -f "$PGPASS_TMP"
}
trap cleanup_pgpass EXIT

if [[ -n "${DSN:-}" ]]; then
    if [[ "$DSN" =~ ://[^/@:]+:[^/@]+@ ]]; then
        echo "ERROR: password-bearing DSN would expose credentials in psql argv. Use POSTGRES_* vars or PGPASSFILE." >&2
        exit 1
    fi
    PSQL_ARGS=("$DSN")
    DB_LABEL="$(echo "$DSN" | sed -E 's|.*@([^/]+)/.*|\1|')"
else
    PG_HOST="${POSTGRES_HOST:-127.0.0.1}"
    PG_PORT="${POSTGRES_PORT:-5432}"
    PG_DB="${POSTGRES_DB:-openclaw}"
    PG_USER="${POSTGRES_USER:-openclaw}"
    PG_PASS="${POSTGRES_PASSWORD:-}"
    PGPASS_TMP="$(mktemp "${TMPDIR:-/tmp}/openclaw-v018-pgpass.XXXXXX")"
    chmod 600 "$PGPASS_TMP"
    printf '%s:%s:%s:%s:%s\n' "$PG_HOST" "$PG_PORT" "$PG_DB" "$PG_USER" "$PG_PASS" > "$PGPASS_TMP"
    PSQL_ARGS=(-h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB")
    DB_LABEL="$PG_HOST:$PG_PORT/$PG_DB"
fi

run_psql() {
    if [[ -n "$PGPASS_TMP" ]]; then
        PGPASSFILE="$PGPASS_TMP" psql "${PSQL_ARGS[@]}" "$@"
    else
        psql "${PSQL_ARGS[@]}" "$@"
    fi
}

mkdir -p "$(dirname "$AUDIT_LOG")"

log() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$AUDIT_LOG" >&2
}

log "V018 deployment starting"
log "  migration: $MIGRATION_FILE"
log "  audit log: $AUDIT_LOG"
log "  DB target: $DB_LABEL"

# ----- 前置檢查：file exists -----
if [[ ! -f "$MIGRATION_FILE" ]]; then
    log "ERROR: migration file missing: $MIGRATION_FILE"
    exit 1
fi

# ----- 前置檢查：連通性 + trading schema 存在 -----
log "Pre-check: connectivity + required schema 'trading'..."
run_psql -v ON_ERROR_STOP=1 -tA >>"$AUDIT_LOG" 2>&1 <<'EOF'
SELECT 'connectivity_ok' AS check;
SELECT 'schema_trading' AS check WHERE EXISTS (
    SELECT 1 FROM information_schema.schemata WHERE schema_name='trading'
);
EOF

# ----- 執行 migration -----
log "Applying V018 migration..."
run_psql -v ON_ERROR_STOP=1 -f "$MIGRATION_FILE" >>"$AUDIT_LOG" 2>&1

# ----- 驗證 DDL 落地 -----
log "Verifying post-deployment schema..."
VERIFY_OUT=$(run_psql -v ON_ERROR_STOP=1 -tA <<'EOF'
SELECT (to_regclass('trading.paper_state_checkpoint') IS NOT NULL)::int;
SELECT count(*) FROM information_schema.columns
    WHERE table_schema='trading' AND table_name='paper_state_checkpoint'
      AND column_name IN ('engine_mode','peak_balance','session_start_ts','updated_at');
SELECT count(*) FROM information_schema.constraint_column_usage
    WHERE table_schema='trading' AND table_name='paper_state_checkpoint';
EOF
)

mapfile -t VERIFY_LINES <<<"$VERIFY_OUT"
TABLE_EXISTS="${VERIFY_LINES[0]:-0}"
COLUMN_COUNT="${VERIFY_LINES[1]:-0}"
CONSTRAINT_COUNT="${VERIFY_LINES[2]:-0}"

log "  paper_state_checkpoint exists: $TABLE_EXISTS (expect 1)"
log "  expected columns present:      $COLUMN_COUNT (expect 4)"
log "  constraints installed:         $CONSTRAINT_COUNT (expect >=3 — PK + 2 CHECK)"

if [[ "$TABLE_EXISTS" != "1" || "$COLUMN_COUNT" != "4" ]]; then
    log "ERROR: verification FAILED — inspect audit log + consider rollback"
    exit 2
fi

log "V018 deployment SUCCESS"
log "  next step: restart engine (restart_all.sh --rebuild) so Rust checkpoint writer/reader activate"
