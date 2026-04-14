#!/usr/bin/env bash
# ============================================================
# deploy_V017.sh — Edge Predictor Tables deployment wrapper
# V017 部署腳本：pre-check + 原子交易 + 驗證 + 審計日誌
#
# MODULE_NOTE (EN): Operator-run wrapper for V017 migration. Validates DSN,
#   runs pre-deployment schema check, applies V017 inside a BEGIN/COMMIT
#   block, runs verification SQL, and writes audit log to stderr + file.
#   Safe to re-run (migration uses IF NOT EXISTS throughout).
# MODULE_NOTE (中): operator 執行的 V017 部署包裝器。驗證 DSN、執行部署前
#   schema 檢查、BEGIN/COMMIT 原子執行、驗證 SQL、審計日誌寫 stderr + 檔案。
#   可重複執行（migration 全部 IF NOT EXISTS）。
#
# Usage / 用法:
#   source settings/environment_files/basic_system_services.env
#   bash helper_scripts/db/deploy_V017.sh
#
#   # 或顯式 DSN:
#   DSN=postgresql://redacted@127.0.0.1/openclaw \
#     bash helper_scripts/db/deploy_V017.sh
#
# Rollback (僅在尚無生產寫入時):
#   psql "$DSN" -v ON_ERROR_STOP=1 -f sql/migrations/V017_rollback.sql
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MIGRATION_FILE="$REPO_ROOT/sql/migrations/V017__edge_predictor_tables.sql"
AUDIT_LOG="$REPO_ROOT/trading_services/logs/v017_deploy_$(date -u +%Y%m%dT%H%M%SZ).log"

# ----- DSN 解析 / Resolve DSN -----
if [[ -z "${DSN:-}" ]]; then
    DSN="postgresql://redacted@${POSTGRES_HOST:-127.0.0.1}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-openclaw}"
fi

mkdir -p "$(dirname "$AUDIT_LOG")"

log() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$AUDIT_LOG" >&2
}

log "V017 deployment starting"
log "  migration: $MIGRATION_FILE"
log "  audit log: $AUDIT_LOG"
log "  DSN host: $(echo "$DSN" | sed -E 's|.*@([^/]+)/.*|\1|')"

# ----- 前置檢查：file exists -----
if [[ ! -f "$MIGRATION_FILE" ]]; then
    log "ERROR: migration file missing: $MIGRATION_FILE"
    exit 1
fi

# ----- 前置檢查：連通性 + 必要 schema 存在 -----
log "Pre-check: connectivity + required schemas..."
psql "$DSN" -v ON_ERROR_STOP=1 -tA >>"$AUDIT_LOG" 2>&1 <<'EOF'
SELECT 'connectivity_ok' AS check;
SELECT 'schema_trading' AS check WHERE EXISTS (
    SELECT 1 FROM information_schema.schemata WHERE schema_name='trading'
);
SELECT 'schema_learning' AS check WHERE EXISTS (
    SELECT 1 FROM information_schema.schemata WHERE schema_name='learning'
);
SELECT 'hypertable_dcs' AS check WHERE EXISTS (
    SELECT 1 FROM timescaledb_information.hypertables
    WHERE hypertable_schema='trading' AND hypertable_name='decision_context_snapshots'
);
EOF

# ----- 執行 migration（migration 本身包含 ALTER/CREATE；不額外包 BEGIN，
#       因 TimescaleDB 某些 ALTER 禁止在顯式 transaction 中；ON_ERROR_STOP
#       保證任何失敗即中止）-----
log "Applying V017 migration..."
psql "$DSN" -v ON_ERROR_STOP=1 -f "$MIGRATION_FILE" >>"$AUDIT_LOG" 2>&1

# ----- 驗證 DDL 落地 -----
log "Verifying post-deployment schema..."
VERIFY_OUT=$(psql "$DSN" -v ON_ERROR_STOP=1 -tA <<'EOF'
SELECT count(*) FROM information_schema.columns
    WHERE table_schema='trading' AND table_name='decision_context_snapshots'
      AND column_name IN ('predicted_q10','predicted_q50','predicted_q90',
                          'predictor_decision','shrinkage_decision',
                          'disagreed','predict_latency_us');
SELECT count(*) FROM information_schema.columns
    WHERE table_schema='trading' AND table_name='fills'
      AND column_name='entry_context_id';
SELECT (to_regclass('learning.decision_features') IS NOT NULL)::int
     + (to_regclass('learning.decision_shadow_fills') IS NOT NULL)::int;
EOF
)

mapfile -t VERIFY_LINES <<<"$VERIFY_OUT"
DCS_NEW_COLS="${VERIFY_LINES[0]:-0}"
FILLS_NEW_COL="${VERIFY_LINES[1]:-0}"
LEARNING_TABLES="${VERIFY_LINES[2]:-0}"

log "  decision_context_snapshots new columns: $DCS_NEW_COLS (expect 7)"
log "  fills.entry_context_id:                 $FILLS_NEW_COL (expect 1)"
log "  learning.* new tables:                  $LEARNING_TABLES (expect 2)"

if [[ "$DCS_NEW_COLS" != "7" || "$FILLS_NEW_COL" != "1" || "$LEARNING_TABLES" != "2" ]]; then
    log "ERROR: verification FAILED — inspect audit log + consider rollback"
    exit 2
fi

log "V017 deployment SUCCESS"
log "  next step: restart engine (restart_all.sh) so Rust consumer begins writing new columns"
