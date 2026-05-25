#!/usr/bin/env bash
# ac19_alt_bucket_daily_cron.sh — AC-19 ALT bucket 14d 監測 daily cron wrapper
# Owner: E1 IMPL（per QA W1-G SOP §3.1 / §8 handoff，2026-05-25）
# Fire:  daily 08:00 UTC；window 2026-05-19 ~ 2026-06-02
# Spec:  docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--ac19_alt_bucket_14d_monitor_sop.md
#
# 流程：
#   1. 讀 secret env file 取 PG creds（對齊 panel_aggregator_health_cron.sh 範式）。
#   2. psql --csv 跑 ac19_alt_bucket_daily_query.sql 把 bucket-split 結果寫 CSV。
#   3. ac19_alt_bucket_jsonl_writer.py 將 CSV append 至累積 JSONL summary。
#   4. 印 day_index / log path / JSONL path 至 daily log。
#
# Exit code（聚合 verdict，cron MTA / monitor 依此分級）:
#   0 — 所有 bucket PASS（或 INSUFFICIENT_DATA）
#   1 — 任一 bucket MARGINAL
#   2 — 任一 bucket FAIL（或 setup error / psql 失敗）
#
# Suggested crontab entry（operator paste-ready, single-line）:
#   0 8 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/cron/ac19_alt_bucket_daily_cron.sh >>/tmp/openclaw/logs/ac19_alt_bucket_daily_cron.cron.log 2>&1

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
DATE_UTC=$(date -u +%Y-%m-%d)
TS_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
DAILY_LOG="${LOG_DIR}/ac19_alt_bucket_daily_${DATE_UTC}.log"
CSV_FILE="${DAILY_LOG}.csv"
JSONL_FILE="${DATA}/ac19_alt_bucket_14d_summary.jsonl"
SQL_FILE="${BASE}/helper_scripts/cron/ac19_alt_bucket_daily_query.sql"
WRITER_PY="${BASE}/helper_scripts/cron/ac19_alt_bucket_jsonl_writer.py"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/ac19_alt_bucket_daily_cron.lock.d"

mkdir -p "$LOG_DIR" "$LOCK_ROOT"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# Heartbeat sentinel（per P1-CRON-INSTALL-WAVE-1 範式）。
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
mkdir -p "$HEARTBEAT_DIR" 2>/dev/null || true
touch "$HEARTBEAT_DIR/ac19_alt_bucket_daily.last_fire" 2>/dev/null || true

# 鎖：防 cron overrun 重覆 append（同日多次 fire 例外時必須擋住）。
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: ac19_alt_bucket_daily_cron already running (lock held)" >> "$DAILY_LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

# 1. 14d window expiry idempotent skip。
DAY_INDEX=$(python3 -c "from datetime import date; print((date.today() - date(2026,5,19)).days + 1)" 2>/dev/null || echo 0)
if [[ "$DAY_INDEX" -gt 14 ]]; then
    echo "[$(ts)] 14d window expired (day_index=${DAY_INDEX}/14); skipping. QA final verdict pending." >> "$DAILY_LOG"
    exit 0
fi
if [[ "$DAY_INDEX" -lt 1 ]]; then
    echo "[$(ts)] window not yet started (day_index=${DAY_INDEX}); skipping." >> "$DAILY_LOG"
    exit 0
fi

# 2. 環境檔 + PG creds（對齊 panel_aggregator_health_cron.sh）。
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[$(ts)] FATAL: env file missing: $ENV_FILE" | tee -a "$DAILY_LOG" >&2
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
    echo "[$(ts)] FATAL: PG creds incomplete in $ENV_FILE" | tee -a "$DAILY_LOG" >&2
    exit 2
fi

export PGPASSWORD="$PG_PASS"

# 3. SQL / writer 存在性檢查。
if [[ ! -f "$SQL_FILE" ]]; then
    echo "[$(ts)] FATAL: SQL file missing: $SQL_FILE" | tee -a "$DAILY_LOG" >&2
    exit 2
fi
if [[ ! -f "$WRITER_PY" ]]; then
    echo "[$(ts)] FATAL: writer script missing: $WRITER_PY" | tee -a "$DAILY_LOG" >&2
    exit 2
fi

echo "[$(ts)] === ac19_alt_bucket_daily_cron start day=${DAY_INDEX}/14 ===" >> "$DAILY_LOG"

# 4. 跑 psql --csv 寫 bucket-split 結果。
if ! psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -P pager=off \
        --csv -f "$SQL_FILE" > "$CSV_FILE" 2>>"$DAILY_LOG"; then
    echo "[$(ts)] FATAL: psql failed (see $DAILY_LOG)" | tee -a "$DAILY_LOG" >&2
    exit 2
fi

# 5. CSV → JSONL append + sanity verify。
set +e
python3 "$WRITER_PY" \
    --input "$CSV_FILE" \
    --ts "$TS_UTC" \
    --output "$JSONL_FILE" \
    >> "$DAILY_LOG" 2>&1
rc=$?
set -e

echo "[$(ts)] day=${DAY_INDEX}/14 csv=${CSV_FILE} jsonl=${JSONL_FILE} writer_rc=${rc}" >> "$DAILY_LOG"
echo "[$(ts)] === ac19_alt_bucket_daily_cron end rc=${rc} ===" >> "$DAILY_LOG"
exit "$rc"
