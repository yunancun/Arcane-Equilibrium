#!/usr/bin/env bash
# polymarket_leadlag_ic_cron.sh - read-only Polymarket -> Bybit IC refresh.
#
# Suggested Linux cron, after polymarket_axis hourly-topn at minute 7:
#   17 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/polymarket_leadlag_ic_cron.sh
#
# Hard boundary:
#   Artifact/report only. PG is readonly via libpq PGOPTIONS plus helper-side
#   readonly session. Writes are limited to local research artifacts, status
#   log, heartbeat, and lock files under OPENCLAW_DATA_DIR. No order, auth,
#   risk, strategy flag, engine, or runtime mutation.
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/polymarket_leadlag_ic_cron.log"
STATUS_LOG="${LOG_DIR}/polymarket_leadlag_ic.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/polymarket_leadlag_ic_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
ARTIFACT_DIR="${DATA}/research/polymarket_leadlag"

QUERY_SET="${OPENCLAW_POLYMARKET_LEADLAG_QUERY_SET:-${OPENCLAW_POLYMARKET_QUERY_SET:-v2}}"
MODE="${OPENCLAW_POLYMARKET_LEADLAG_MODE:-hourly-topn}"
SYMBOLS="${OPENCLAW_POLYMARKET_LEADLAG_SYMBOLS:-BTCUSDT,ETHUSDT}"
HORIZONS="${OPENCLAW_POLYMARKET_LEADLAG_HORIZONS_MINUTES:-15,60,240}"
MIN_POINTS="${OPENCLAW_POLYMARKET_LEADLAG_MIN_POINTS:-30}"
MAX_ALIGN_LAG="${OPENCLAW_POLYMARKET_LEADLAG_MAX_ALIGN_LAG_MINUTES:-10}"
PRICE_TIMEFRAME="${OPENCLAW_POLYMARKET_LEADLAG_PRICE_TIMEFRAME:-1m}"
STALE_LOCK_MIN="${OPENCLAW_POLYMARKET_LEADLAG_STALE_LOCK_MIN:-50}"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$HEARTBEAT_DIR" "$ARTIFACT_DIR"

ts() { date -u '+%Y-%m-%d %H:%M:%S'; }

validate_int() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[0-9]+$ ]]; then
        echo "[$(ts)] FATAL: ${name} must be an integer: ${value}" | tee -a "$LOG" >&2
        exit 2
    fi
}

validate_csv_ints() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
        echo "[$(ts)] FATAL: ${name} must be comma-separated integers: ${value}" | tee -a "$LOG" >&2
        exit 2
    fi
}

validate_symbols() {
    local value="$1"
    if [[ ! "$value" =~ ^[A-Z0-9]+(,[A-Z0-9]+)*$ ]]; then
        echo "[$(ts)] FATAL: OPENCLAW_POLYMARKET_LEADLAG_SYMBOLS invalid: ${value}" | tee -a "$LOG" >&2
        exit 2
    fi
}

case "$QUERY_SET" in
    v1|v2) ;;
    *)
        echo "[$(ts)] FATAL: OPENCLAW_POLYMARKET_LEADLAG_QUERY_SET must be v1 or v2: ${QUERY_SET}" | tee -a "$LOG" >&2
        exit 2
        ;;
esac
case "$MODE" in
    daily|hourly-topn) ;;
    *)
        echo "[$(ts)] FATAL: OPENCLAW_POLYMARKET_LEADLAG_MODE must be daily or hourly-topn: ${MODE}" | tee -a "$LOG" >&2
        exit 2
        ;;
esac
validate_symbols "$SYMBOLS"
validate_csv_ints "OPENCLAW_POLYMARKET_LEADLAG_HORIZONS_MINUTES" "$HORIZONS"
validate_int "OPENCLAW_POLYMARKET_LEADLAG_MIN_POINTS" "$MIN_POINTS"
validate_int "OPENCLAW_POLYMARKET_LEADLAG_MAX_ALIGN_LAG_MINUTES" "$MAX_ALIGN_LAG"
validate_int "OPENCLAW_POLYMARKET_LEADLAG_STALE_LOCK_MIN" "$STALE_LOCK_MIN"

PYBIN="${OPENCLAW_PYTHON_BIN:-}"
if [[ -z "$PYBIN" ]]; then
    if [[ -x "$HOME/.venv/bin/python" ]]; then
        PYBIN="$HOME/.venv/bin/python"
    else
        PYBIN="python3"
    fi
fi

touch "$HEARTBEAT_DIR/polymarket_leadlag_ic.last_fire" 2>/dev/null || true

if [[ -d "$LOCK_DIR" ]] && [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +"$STALE_LOCK_MIN" 2>/dev/null)" ]]; then
    echo "[$(ts)] WARN: stale lock (>${STALE_LOCK_MIN}min) cleared: $LOCK_DIR" >> "$LOG"
    rmdir "$LOCK_DIR" 2>/dev/null || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: Polymarket lead-lag IC already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

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
export OPENCLAW_BASE_DIR="$BASE"
export OPENCLAW_DATA_DIR="$DATA"

STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
OUT="${ARTIFACT_DIR}/polymarket_leadlag_${STAMP}.json"
LATEST="${ARTIFACT_DIR}/polymarket_leadlag_latest.json"

ARGS=(
    -m polymarket_leadlag.harness
    --query-set "$QUERY_SET"
    --mode "$MODE"
    --symbols "$SYMBOLS"
    --horizons-minutes "$HORIZONS"
    --min-points "$MIN_POINTS"
    --max-align-lag-minutes "$MAX_ALIGN_LAG"
    --price-timeframe "$PRICE_TIMEFRAME"
    --out "$OUT"
    --write-latest
)

echo "[$(ts)] === Polymarket lead-lag IC start query_set=${QUERY_SET} mode=${MODE} symbols=${SYMBOLS} min_points=${MIN_POINTS} ===" >> "$LOG"
rc=0
(
    cd "$BASE"
    export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
    export PYTHONDONTWRITEBYTECODE=1
    "$PYBIN" "${ARGS[@]}"
) >> "$LOG" 2>&1 || rc=$?

STATUS_JSON=$(LEADLAG_OUT="$OUT" LEADLAG_LATEST="$LATEST" LEADLAG_RC="$rc" "$PYBIN" - <<'PY' 2>>"$LOG" || true
import datetime
import hashlib
import json
import os

out = os.environ["LEADLAG_OUT"]
latest = os.environ["LEADLAG_LATEST"]
rc = int(os.environ["LEADLAG_RC"])
status = {
    "ts_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "check": "polymarket_leadlag_ic",
    "rc": rc,
    "artifact_path": out,
    "latest_path": latest,
    "boundary": "artifact_only_readonly_pg_no_signal_no_order",
}
try:
    with open(out, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    with open(out, "rb") as fh:
        status["sha256"] = hashlib.sha256(fh.read()).hexdigest()
    verdict = payload.get("verdict") or {}
    counts = payload.get("counts") or {}
    label_readiness = counts.get("label_readiness") or {}
    status.update({
        "verdict_status": verdict.get("status"),
        "reason": verdict.get("reason"),
        "candidate_count": verdict.get("candidate_count"),
        "preliminary_raw_candidate_count": verdict.get("preliminary_raw_candidate_count"),
        "max_bh_q": verdict.get("max_bh_q"),
        "query_set_version": payload.get("query_set_version"),
        "mode": payload.get("mode"),
        "symbols": payload.get("symbols"),
        "horizons_minutes": payload.get("horizons_minutes"),
        "snapshot_rows": counts.get("snapshot_rows"),
        "snapshot_distinct_timestamps": counts.get("snapshot_distinct_timestamps"),
        "delta_rows": counts.get("delta_rows"),
        "feature_points": counts.get("feature_points"),
        "joined_rows": counts.get("joined_rows"),
        "max_ic_points": counts.get("max_ic_points"),
        "max_overlap_adjusted_ic_points": counts.get("max_overlap_adjusted_ic_points"),
        "label_feature_horizon_pairs": label_readiness.get("feature_horizon_pairs"),
        "label_joinable_pairs": label_readiness.get("joinable_pairs"),
        "label_status_counts": label_readiness.get("status_counts"),
        "oldest_unmatured_exit_target_utc": label_readiness.get("oldest_unmatured_exit_target_utc"),
        "price_rows": counts.get("price_rows"),
        "price_source": payload.get("price_source"),
        "ic_result_count": len(payload.get("ic_results") or []),
    })
except Exception as exc:  # noqa: BLE001 - status log must survive failed report write.
    status.update({
        "verdict_status": "CRON_ERROR",
        "reason": f"{type(exc).__name__}:{exc}",
    })
print(json.dumps(status, ensure_ascii=False, sort_keys=True))
PY
)
if [[ -n "$STATUS_JSON" ]]; then
    echo "$STATUS_JSON" >> "$STATUS_LOG"
fi

echo "[$(ts)] === Polymarket lead-lag IC end rc=${rc} out=${OUT} ===" >> "$LOG"

# fail-soft: rc/status are recorded; cron should not page. Staleness is handled
# by alpha_discovery_throughput after this report stops refreshing.
exit 0
