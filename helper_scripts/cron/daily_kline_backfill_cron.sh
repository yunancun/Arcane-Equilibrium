#!/usr/bin/env bash
# daily_kline_backfill_cron.sh — 每日 1d K 線回填 runtime apply wrapper
#                                （FLASH-DIP-SEED-FIX / DB-freshness 2026-06-18）
#
# Suggested cron entry, installed manually by the operator:
#   29 5 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/daily_kline_backfill_cron.sh
#
# 為什麼需要這支：market.klines 1d 此前「沒有任何 daily cron」維護 → 只靠人工 run，
#   實測曾漂到 9-17 日 stale。flash_dip_buy demo pilot 的 boot prior_close seed 改讀
#   market.klines 1d（bootstrap.rs，FLASH-DIP-SEED-FIX），其正確性依賴 1d 表新鮮；
#   2 日 staleness fail-safe 會在 DB 過期時讓 pilot 當日 inert（fail-safe 但靜默）。
#   本 wrapper 每日把固定流動標的集（settings/backfill_universe.toml）的 1d OHLCV 從
#   Bybit public REST 取數並 UPSERT/append market.klines（1d）+ append provenance ledger，
#   保持表新鮮，是 seed 正確性的上游維護。
#
# 本 wrapper 刻意狹窄：以 OPENCLAW_DAILY_KLINE_BACKFILL_APPLY=1 跑 Rust daily_kline_backfill，
#   絕不帶 CLI --apply/--i-understand/--force/--yes flag。binary 在無此 env gate 時仍預設 dry-run。
#   backfill 唯讀 Bybit market REST + 寫 market.klines（timeframe='1d'，ON CONFLICT，與 live
#   1m-1h disjoint）+ research.alpha_klines_provenance（append-only）；不下單/不碰 auth/lease/
#   system_mode/risk。V125 preflight 缺表即 fail-closed。
#
# 硬邊界：不啟任何 strategy flag、不重啟引擎、不部署、不碰硬邊界欄位。唯一 DB 寫入面 =
#   market.klines(1d) + provenance（皆 backfill binary 經 env-gate 的既有狹窄寫路徑）；
#   檔案寫入面 = <DATA>/logs/daily_kline_backfill_cron.log + coverage 全失敗時 alerts.jsonl。
# PG 憑證走 basic_system_services.env grep-parse（鏡像 recorder_health_cron.sh，禁硬編 trading_admin）。
# 配對 healthcheck sentinel：<DATA>/cron_heartbeat/daily_kline_backfill.last_fire。

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/daily_kline_backfill_cron.log"
ALERT_DIR="${DATA}/alerts"
ALERT_FILE="${ALERT_DIR}/alerts.jsonl"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/daily_kline_backfill_cron.lock.d"

# 回填窗口（日）：預設 7（覆蓋多日 cron 漏跑 + ON CONFLICT 冪等補洞）；可覆寫。
LOOKBACK_DAYS="${OPENCLAW_DAILY_KLINE_BACKFILL_LOOKBACK_DAYS:-7}"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$ALERT_DIR"

# Cron heartbeat sentinel — FLASH-DIP-SEED-FIX（2026-06-18）。
# touch-at-start：「cron 被排程觸發」的證據，由配對 healthcheck 監測 mtime。
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
mkdir -p "$HEARTBEAT_DIR" 2>/dev/null || true
touch "$HEARTBEAT_DIR/daily_kline_backfill.last_fire" 2>/dev/null || true

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

# backfill binary 讀 OPENCLAW_DATABASE_URL（或 _FILE）。此處走 URL（憑證來自 env-file grep）。
# 刻意「不」放 read-only PGOPTIONS：本 wrapper 的目的就是 apply 寫入 market.klines(1d)+provenance；
# read-only 只用於純讀監測 cron（recorder_health 等），與此處寫入語意衝突。
export OPENCLAW_DATABASE_URL="postgresql://${PG_USER}:${PG_PASS}@${PG_HOST}:${PG_PORT}/${PG_DB}"
# env-gate apply：binary 無此 env 時仍預設 dry-run（雙保險，與 CLI ack flag 互斥）。
export OPENCLAW_DAILY_KLINE_BACKFILL_APPLY=1
# universe TOML 解析根（settings/backfill_universe.toml）+ alert sink 根。
export OPENCLAW_BASE_DIR="$BASE"
export OPENCLAW_DATA_DIR="$DATA"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: daily kline backfill already running (lock held)" >> "$LOG"
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

ARGS=(--lookback-days "$LOOKBACK_DAYS")

echo "[$(ts)] === daily kline backfill start (BASE=$BASE lookback_days=${LOOKBACK_DAYS}) ===" >> "$LOG"

BIN_RELEASE="$BASE/rust/target/release/daily_kline_backfill"
BIN_DEBUG="$BASE/rust/target/debug/daily_kline_backfill"
# binary 以 if 條件執行：非零退出不觸發 set -e 提前中止，rc 才能被捕捉供 FAIL 日誌
# （鏡像 kline_calibration_cron.sh 的 rc-capture 模式）。stdout 同時 tee 到專屬 capture
# 供下方 coverage 檢查（binary 即便全 symbol fetch 失敗仍退 EXIT_OK，故須另檢 observed）。
RUN_OUT="${DATA}/logs/daily_kline_backfill_lastrun.out"
rc=0
if [[ -x "$BIN_RELEASE" ]]; then
    if "$BIN_RELEASE" "${ARGS[@]}" > "$RUN_OUT" 2>>"$LOG"; then rc=0; else rc=$?; fi
elif [[ -x "$BIN_DEBUG" ]]; then
    if "$BIN_DEBUG" "${ARGS[@]}" > "$RUN_OUT" 2>>"$LOG"; then rc=0; else rc=$?; fi
else
    if ( cd "$BASE/rust" && cargo run -q -p openclaw_engine --bin daily_kline_backfill -- "${ARGS[@]}" ) > "$RUN_OUT" 2>>"$LOG"; then rc=0; else rc=$?; fi
fi
cat "$RUN_OUT" >> "$LOG"

if [[ "$rc" -ne 0 ]]; then
    echo "[$(ts)] === daily kline backfill end FAIL rc=${rc} ===" >> "$LOG"
    exit "$rc"
fi

# coverage 檢查：binary 退 EXIT_OK 但若 demo slot 憑證缺失 / Bybit 全失敗，total_observed=0
#   （全 symbol failed coverage）。此時 market.klines 1d 不會新鮮 → 落 critical 告警，
#   避免 seed 上游靜默腐爛（這正是先前 9-17 日 stale 沒人發現的失敗模式）。
TOTAL_OBSERVED=$(grep -E '^# total_observed = ' "$RUN_OUT" 2>/dev/null | tail -1 | awk '{print $NF}')
TOTAL_INSERTED=$(grep -E '^# total_inserted = ' "$RUN_OUT" 2>/dev/null | tail -1 | awk '{print $NF}')
echo "[$(ts)] status: total_observed=${TOTAL_OBSERVED:-?} total_inserted=${TOTAL_INSERTED:-?}" >> "$LOG"

if [[ -z "$TOTAL_OBSERVED" || "$TOTAL_OBSERVED" == "0" ]]; then
    ALERT_TS=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    BODY="daily 1d kline backfill observed 0 bars (rc=0); market.klines 1d will go stale. check demo slot credentials / Bybit reachability. flash_dip seed depends on 1d freshness."
    printf '{"ts_utc":"%s","subject":"%s","severity":"%s","body":"%s","channels_attempted":[],"channels_ok":null}\n' \
        "$ALERT_TS" "[DAILY-KLINE-BACKFILL] 1d backfill observed 0 bars" "critical" "$BODY" >> "$ALERT_FILE"
    echo "[$(ts)] ALERT appended: total_observed=0" >> "$LOG"
fi

echo "[$(ts)] === daily kline backfill end OK ===" >> "$LOG"
exit 0
