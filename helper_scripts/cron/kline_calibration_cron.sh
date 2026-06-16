#!/usr/bin/env bash
# kline_calibration_cron.sh — intraday kline 真值校準 / drift guardrail runtime apply wrapper
#                             （INTRADAY-KLINES-PERMANENT-FIX R3）
#
# Suggested cron entry, installed manually by the operator:
#   17 5 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/kline_calibration_cron.sh
#
# 本 wrapper 刻意狹窄：以 OPENCLAW_KLINE_CALIBRATION_APPLY=1 跑 Rust kline_calibration_checker，
# 絕不帶 CLI apply/force flag。checker 在無此 env gate 時仍預設 dry-run。
# checker 唯讀 market.klines + Bybit REST，只寫 research.kline_calibration（V141）+ drift 時
# 落 alerts.jsonl；不下單/不碰 auth/lease。配對 healthcheck [91]（sentinel kline_calibration.last_fire）。

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/kline_calibration_cron.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/kline_calibration_cron.lock.d"

mkdir -p "$LOG_DIR" "$LOCK_ROOT"

# Cron heartbeat sentinel — INTRADAY-KLINES-PERMANENT-FIX R3（2026-06-16）。
# touch-at-start：「cron 被排程觸發」的證據，由 healthcheck [91] 監測 mtime。
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
mkdir -p "$HEARTBEAT_DIR" 2>/dev/null || true
touch "$HEARTBEAT_DIR/kline_calibration.last_fire" 2>/dev/null || true

ts() { date '+%Y-%m-%d %H:%M:%S'; }

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

export PG_HOST PG_PORT PG_DB PG_USER PG_PASSWORD="$PG_PASS"
export OPENCLAW_DATABASE_URL="postgresql://${PG_USER}:${PG_PASS}@${PG_HOST}:${PG_PORT}/${PG_DB}"
export OPENCLAW_KLINE_CALIBRATION_APPLY=1
# alert sink 根目錄（drift 落 <DATA>/alerts/alerts.jsonl，與 alert_sink.py 同 schema）。
export OPENCLAW_DATA_DIR="$DATA"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: kline calibration checker already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

if [[ ! -d "$BASE/rust" ]]; then
    echo "[$(ts)] ERROR: rust workspace not found under BASE=${BASE}" >> "$LOG"
    exit 1
fi

ARGS=(
    --sample-size "${OPENCLAW_KLINE_CALIBRATION_SAMPLE_SIZE:-30}"
    --lookback-hours "${OPENCLAW_KLINE_CALIBRATION_LOOKBACK_HOURS:-48}"
)

echo "[$(ts)] === kline calibration checker start (BASE=$BASE sample=${OPENCLAW_KLINE_CALIBRATION_SAMPLE_SIZE:-30}) ===" >> "$LOG"

CHECKER_RELEASE="$BASE/rust/target/release/kline_calibration_checker"
CHECKER_DEBUG="$BASE/rust/target/debug/kline_calibration_checker"
# checker 以 if 條件執行：非零退出不觸發 set -e 提前中止，rc 才能被捕捉供 FAIL 日誌
# （鏡像 feature_baseline_writer_cron.sh 的 rc-capture 模式；E2/E4 2026-06-16 return 修正）。
rc=0
if [[ -x "$CHECKER_RELEASE" ]]; then
    if "$CHECKER_RELEASE" "${ARGS[@]}" >> "$LOG" 2>&1; then rc=0; else rc=$?; fi
elif [[ -x "$CHECKER_DEBUG" ]]; then
    if "$CHECKER_DEBUG" "${ARGS[@]}" >> "$LOG" 2>&1; then rc=0; else rc=$?; fi
else
    if ( cd "$BASE/rust" && cargo run -q -p openclaw_engine --bin kline_calibration_checker -- "${ARGS[@]}" ) >> "$LOG" 2>&1; then rc=0; else rc=$?; fi
fi

if [[ "$rc" -eq 0 ]]; then
    echo "[$(ts)] === kline calibration checker end OK ===" >> "$LOG"
    exit 0
fi
echo "[$(ts)] === kline calibration checker end FAIL rc=${rc} ===" >> "$LOG"
exit "$rc"
