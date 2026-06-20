#!/usr/bin/env bash
# flash_dip_touchability_cron.sh — flash_dip_buy open-order touchability monitor
#                                  （daily / read-only / no trading side effect）
#
# Suggested cron entry:
#   17 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/flash_dip_touchability_cron.sh
#
# Why this exists:
#   death-rate only moves after a fill+close. During the current deep-K pilot,
#   orders can be live for hours with zero closed slots. This monitor measures
#   whether flash_dip_buy orders ever touch their intended limit before timeout.
#   It is evidence for "no-touch/deep-K" vs "fill path broken".
#
# Hard boundary:
#   read-only PG only, enforced by PGOPTIONS. Writes are limited to local logs,
#   status JSONL, and heartbeat/lock files under OPENCLAW_DATA_DIR. No order,
#   auth, risk, strategy flag, or runtime mutation.

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/flash_dip_touchability_cron.log"
STATUS_LOG="${LOG_DIR}/flash_dip_touchability.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/flash_dip_touchability_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"

LOOKBACK_HOURS="${OPENCLAW_FLASH_DIP_TOUCH_LOOKBACK_HOURS:-72}"
ENGINE_MODE="${OPENCLAW_FLASH_DIP_TOUCH_ENGINE_MODE:-demo}"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$HEARTBEAT_DIR"
touch "$HEARTBEAT_DIR/flash_dip_touchability.last_fire" 2>/dev/null || true

ts() { date '+%Y-%m-%d %H:%M:%S'; }

if [[ ! "$LOOKBACK_HOURS" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "[$(ts)] FATAL: OPENCLAW_FLASH_DIP_TOUCH_LOOKBACK_HOURS must be numeric: $LOOKBACK_HOURS" | tee -a "$LOG" >&2
    exit 2
fi
if [[ ! "$ENGINE_MODE" =~ ^[A-Za-z0-9_-]+$ ]]; then
    echo "[$(ts)] FATAL: OPENCLAW_FLASH_DIP_TOUCH_ENGINE_MODE contains unsafe characters: $ENGINE_MODE" | tee -a "$LOG" >&2
    exit 2
fi

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

export PGHOST="$PG_HOST" PGPORT="$PG_PORT" PGDATABASE="$PG_DB" PGUSER="$PG_USER" PGPASSWORD="$PG_PASS"
export PGOPTIONS="-c default_transaction_read_only=on"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: flash_dip touchability check already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

echo "[$(ts)] === flash_dip touchability check start (lookback_h=${LOOKBACK_HOURS} engine_mode=${ENGINE_MODE}) ===" >> "$LOG"

read -r -d '' TOUCH_SQL <<SQL || true
WITH fd_labeled AS (
  SELECT o.ts AS order_ts,
         o.order_id,
         o.symbol,
         o.status,
         o.intent_id,
         o.strategy_name AS order_strategy,
         COALESCE(i.strategy_name, i.details->>'strategy') AS intent_strategy,
         i.price::double precision AS ref_price,
         NULLIF(i.details->>'limit_price', '')::double precision AS limit_price,
         COALESCE(NULLIF(i.details->>'maker_timeout_ms', '')::bigint, 86400000) AS timeout_ms
  FROM trading.orders o
  LEFT JOIN trading.intents i ON i.intent_id = o.intent_id
  WHERE o.strategy_name = 'flash_dip_buy'
    AND o.engine_mode = '${ENGINE_MODE}'
    AND o.ts >= now() - (${LOOKBACK_HOURS}::double precision * interval '1 hour')
),
scored AS (
  SELECT fd.*,
         lows.n_1m,
         lows.min_low,
         lows.min_low_ts,
         lows.last_1m_ts,
         CASE
           WHEN fd.ref_price > 0 AND fd.limit_price > 0
           THEN ((fd.ref_price / fd.limit_price) - 1.0) * 10000.0
           ELSE NULL
         END AS ref_to_limit_bps,
         CASE
           WHEN lows.min_low > 0 AND fd.limit_price > 0
           THEN ((lows.min_low / fd.limit_price) - 1.0) * 10000.0
           ELSE NULL
         END AS closest_miss_bps,
         (lows.min_low <= fd.limit_price) AS touched
  FROM fd_labeled fd
  LEFT JOIN LATERAL (
    SELECT count(*) AS n_1m,
           min(k.low)::double precision AS min_low,
           (array_agg(k.ts ORDER BY k.low ASC, k.ts ASC))[1] AS min_low_ts,
           max(k.ts) AS last_1m_ts
    FROM market.klines k
    WHERE k.symbol = fd.symbol
      AND k.timeframe = '1m'
      AND k.ts >= fd.order_ts
      AND k.ts <= LEAST(
        fd.order_ts + (fd.timeout_ms::double precision / 1000.0) * interval '1 second',
        now()
      )
  ) lows ON TRUE
),
true_fd AS (
  SELECT * FROM scored
  WHERE intent_strategy = 'flash_dip_buy'
    AND limit_price IS NOT NULL
),
miss_examples AS (
  SELECT COALESCE(json_agg(row_to_json(x)), '[]'::json) AS j
  FROM (
    SELECT symbol,
           to_char(order_ts, 'YYYY-MM-DD"T"HH24:MI:SSOF') AS order_ts,
           round(ref_price::numeric, 8) AS ref_price,
           round(limit_price::numeric, 8) AS limit_price,
           round(ref_to_limit_bps::numeric, 2) AS ref_to_limit_bps,
           round(min_low::numeric, 8) AS min_low_after,
           round(closest_miss_bps::numeric, 2) AS closest_miss_bps,
           n_1m
    FROM true_fd
    WHERE touched IS NOT TRUE
    ORDER BY closest_miss_bps DESC NULLS LAST
    LIMIT 8
  ) x
),
mismatch_examples AS (
  SELECT COALESCE(json_agg(row_to_json(x)), '[]'::json) AS j
  FROM (
    SELECT symbol,
           order_id,
           intent_id,
           intent_strategy,
           to_char(order_ts, 'YYYY-MM-DD"T"HH24:MI:SSOF') AS order_ts
    FROM scored
    WHERE intent_strategy IS DISTINCT FROM 'flash_dip_buy'
    LIMIT 8
  ) x
)
SELECT json_build_object(
  'order_labeled_count', (SELECT count(*) FROM scored),
  'true_order_count', (SELECT count(*) FROM true_fd),
  'strategy_mismatch_count', (
    SELECT count(*) FROM scored WHERE intent_strategy IS DISTINCT FROM 'flash_dip_buy'
  ),
  'missing_limit_count', (
    SELECT count(*) FROM scored
    WHERE intent_strategy = 'flash_dip_buy' AND limit_price IS NULL
  ),
  'touched_count', (SELECT count(*) FROM true_fd WHERE touched IS TRUE),
  'no_touch_count', (SELECT count(*) FROM true_fd WHERE touched IS NOT TRUE),
  'touch_rate_pct', (
    SELECT CASE WHEN count(*) > 0
      THEN round(100.0 * count(*) FILTER (WHERE touched IS TRUE) / count(*), 4)
      ELSE NULL END
    FROM true_fd
  ),
  'median_ref_to_limit_bps', (
    SELECT round((percentile_cont(0.5) WITHIN GROUP (ORDER BY ref_to_limit_bps))::numeric, 2)
    FROM true_fd
  ),
  'median_closest_miss_bps', (
    SELECT round((percentile_cont(0.5) WITHIN GROUP (ORDER BY closest_miss_bps))::numeric, 2)
    FROM true_fd
  ),
  'max_closest_miss_bps', (
    SELECT round(max(closest_miss_bps)::numeric, 2) FROM true_fd
  ),
  'min_closest_miss_bps', (
    SELECT round(min(closest_miss_bps)::numeric, 2) FROM true_fd
  ),
  'latest_order_ts', (
    SELECT to_char(max(order_ts), 'YYYY-MM-DD"T"HH24:MI:SSOF') FROM true_fd
  ),
  'miss_examples', (SELECT j FROM miss_examples),
  'mismatch_examples', (SELECT j FROM mismatch_examples)
);
SQL

rc=0
TOUCH_JSON=""
if TOUCH_JSON=$(psql -X -A -t -v ON_ERROR_STOP=1 -c "$TOUCH_SQL" 2>>"$LOG"); then rc=0; else rc=$?; fi

if [[ "$rc" -ne 0 || -z "$TOUCH_JSON" ]]; then
    [[ "$rc" -eq 0 ]] && rc=1
    echo "[$(ts)] === flash_dip touchability check end FAIL rc=${rc} (psql query failed/empty) ===" >> "$LOG"
    exit "$rc"
fi

PY_OUT=$(TOUCH_JSON="$TOUCH_JSON" \
    LOOKBACK_HOURS="$LOOKBACK_HOURS" \
    ENGINE_MODE="$ENGINE_MODE" \
    python3 - <<'PY' 2>>"$LOG" || true
import datetime
import json
import os

d = json.loads(os.environ["TOUCH_JSON"])
true_n = int(d.get("true_order_count") or 0)
touched = int(d.get("touched_count") or 0)
status = {
    "ts_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "check": "flash_dip_touchability",
    "engine_mode": os.environ["ENGINE_MODE"],
    "lookback_hours": float(os.environ["LOOKBACK_HOURS"]),
    "model": (
        "true FlashDip touchability = trading.orders rows labeled flash_dip_buy "
        "whose joined intent.strategy is flash_dip_buy, then min market.klines 1m low "
        "from order_ts to maker timeout <= intent.details.limit_price"
    ),
    **d,
    "no_touch_detected": true_n > 0 and touched == 0,
    "note": "read-only diagnostic; not promotion evidence and no trading action is taken",
}
print(json.dumps(status, separators=(",", ":"), default=str))
PY
)

if [[ -z "$PY_OUT" ]]; then
    echo "[$(ts)] === flash_dip touchability check end FAIL (python3 synthesis empty) ===" >> "$LOG"
    exit 1
fi

echo "$PY_OUT" >> "$STATUS_LOG"
echo "[$(ts)] status: $PY_OUT" >> "$LOG"
echo "[$(ts)] === flash_dip touchability check end OK ===" >> "$LOG"
exit 0
