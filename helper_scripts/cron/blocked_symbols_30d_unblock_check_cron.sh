#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# blocked_symbols_30d_unblock_check_cron.sh — 30d unblock cycle wrapper
# 30d 動態解封 cycle cron 包裝（W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1）
#
# MODULE_NOTE：
#   QC v3 NEW-ISSUE-V3-4 揭露 freeze 是 one-way street；本 cron 跑 30d
#   window paper engine evidence audit + verdict logic + 寫入
#   governance.unblock_candidates。每週日 04:00 UTC 一次。
#
#   配對 healthcheck `[64] unblock_candidates_drift`（每週日 05:00 UTC，
#   1h 後跑 — 給 cron 寫入有時間 land）。
#
#   Spec: docs/execution_plan/2026-05-10--p1_dynamic_unblock_check_1_spec.md §2.3
#   Writer: helper_scripts/db/audit/blocked_symbols_30d_unblock_check.py
#   V###: V090__governance_unblock_candidates.sql
#
# Suggested cron entry（operator `crontab -e` 加；server local UTC 假設）：
#   0 4 * * 0 "$OPENCLAW_BASE_DIR/helper_scripts/cron/blocked_symbols_30d_unblock_check_cron.sh"
#
# Suggested env vars（crontab 不會展開 shell var，operator 寫 literal 路徑）：
#   OPENCLAW_BASE_DIR=<repo root>           # e.g. $HOME/BybitOpenClaw/srv on Linux
#   OPENCLAW_DATA_DIR=<runtime root>        # e.g. /tmp/openclaw on Linux
#   OPENCLAW_SECRETS_ROOT=<secrets root>    # 可選，預設 $HOME/BybitOpenClaw/secrets
#
# Healthcheck 覆蓋：
#   `[64] unblock_candidates_drift` 在 1h 後跑，驗 cron 寫入結果 +
#   yo-yo / sign-off completeness violation。silent cron death 由
#   stale_n > 0 (14d 無新 cycle) 偵測。
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ─── Configuration ──────────────────────────────────────────────────
BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/blocked_symbols_30d_unblock_check_cron.log"

mkdir -p "$LOG_DIR"

# Cron heartbeat sentinel — P1-CRON-INSTALL-WAVE-1（2026-05-18）。
# touch-at-start：「cron 被排程觸發」的證據，由 healthcheck [79] 監測 mtime。
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
mkdir -p "$HEARTBEAT_DIR" 2>/dev/null || true
touch "$HEARTBEAT_DIR/blocked_symbols_30d_unblock_check.last_fire" 2>/dev/null || true

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# ─── PG creds sourcing（mirror edge_label_backfill_cron.sh 樣板）─────
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[$(ts)] FATAL: env file missing: $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi
PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_USER=$(grep '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_DB=$(grep '^POSTGRES_DB=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST=$(grep '^POSTGRES_HOST=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_PORT=$(grep '^POSTGRES_PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-5432}"
if [[ -z "$PG_PASS" || -z "$PG_USER" || -z "$PG_DB" ]]; then
    echo "[$(ts)] FATAL: PG creds incomplete in $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi
export OPENCLAW_DATABASE_URL="postgresql://redacted@${PG_HOST}:${PG_PORT}/${PG_DB}"
export POSTGRES_USER="$PG_USER"
export POSTGRES_PASSWORD="$PG_PASS"
export POSTGRES_DB="$PG_DB"
export POSTGRES_HOST="$PG_HOST"
export POSTGRES_PORT="$PG_PORT"

# ─── Overlap lock ───────────────────────────────────────────────────
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/blocked_symbols_30d_unblock_check_cron.lock.d"
mkdir -p "$LOCK_ROOT"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: 30d unblock cron already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

# ─── Sanity ─────────────────────────────────────────────────────────
WRITER="${BASE}/helper_scripts/db/audit/blocked_symbols_30d_unblock_check.py"
if [[ ! -f "$WRITER" ]]; then
    echo "[$(ts)] ERROR: writer not found: $WRITER" >> "$LOG"
    exit 1
fi

cd "$BASE"

echo "[$(ts)] === 30d unblock cycle start (BASE=$BASE) ===" >> "$LOG"

# ─── Markdown 報告輸出位置（per cycle 一份檔） ────────────────────────
MD_OUT="${DATA}/reports/blocked_symbols_30d_unblock_$(date '+%Y%m%d_%H%M%S').md"
mkdir -p "$(dirname "$MD_OUT")"

# ─── 跑 writer：--commit 真實寫 governance.unblock_candidates ───────
RC=0
if ! python3 -m helper_scripts.db.audit.blocked_symbols_30d_unblock_check \
        --days 30 \
        --evaluation-path cron_30d_cycle \
        --commit \
        --output "$MD_OUT" >> "$LOG" 2>&1; then
    echo "[$(ts)] ERROR: 30d unblock cycle writer failed (non-zero exit)" >> "$LOG"
    RC=1
fi

if [[ $RC -eq 0 ]]; then
    echo "[$(ts)] === cron end OK; markdown: $MD_OUT ===" >> "$LOG"
else
    echo "[$(ts)] === cron end FAIL (rc=$RC) ===" >> "$LOG"
fi

exit $RC
