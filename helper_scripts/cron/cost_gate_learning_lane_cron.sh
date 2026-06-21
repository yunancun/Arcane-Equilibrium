#!/usr/bin/env bash
# cost_gate_learning_lane_cron.sh - artifact-only cost-gate demo-learning refresh.
#
# Suggested Linux cron:
#   27 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/cost_gate_learning_lane_cron.sh
#
# Hard boundary:
#   Artifact/ledger feedback only. PG is readonly via libpq PGOPTIONS plus the
#   helper-side readonly session. Writes are limited to local JSONL ledger
#   outcome rows, review artifacts, status log, heartbeat, and lock files under
#   OPENCLAW_DATA_DIR. No order, auth, risk, strategy flag, engine, or runtime
#   mutation.
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LANE_DIR="${DATA}/cost_gate_learning_lane"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/cost_gate_learning_lane_cron.log"
STATUS_LOG="${LOG_DIR}/cost_gate_learning_lane.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/cost_gate_learning_lane_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
LEDGER="${OPENCLAW_COST_GATE_LEARNING_LEDGER:-$LANE_DIR/probe_ledger.jsonl}"
SCORECARD_JSON="${OPENCLAW_COST_GATE_SCORECARD_JSON:-$DATA/cost_gate_counterfactual/cost_gate_reject_counterfactual_latest.json}"

PG_TIMEFRAME="${OPENCLAW_COST_GATE_LEARNING_PG_TIMEFRAME:-1m}"
OUTCOME_HORIZON_MINUTES="${OPENCLAW_COST_GATE_LEARNING_OUTCOME_HORIZON_MINUTES:-60}"
OUTCOME_COST_BPS="${OPENCLAW_COST_GATE_LEARNING_OUTCOME_COST_BPS:-4.0}"
MAX_ENTRY_DELAY_MS="${OPENCLAW_COST_GATE_LEARNING_MAX_ENTRY_DELAY_MS:-300000}"
PG_STATEMENT_TIMEOUT_MS="${OPENCLAW_COST_GATE_LEARNING_PG_STATEMENT_TIMEOUT_MS:-180000}"
HISTORICAL_MAX_SCORECARD_AGE_HOURS="${OPENCLAW_COST_GATE_HISTORICAL_MAX_SCORECARD_AGE_HOURS:-36}"
HISTORICAL_MIN_CANDIDATE_SAMPLE="${OPENCLAW_COST_GATE_HISTORICAL_MIN_CANDIDATE_SAMPLE:-100}"
APPEND_OUTCOMES="${OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES:-1}"
RECORD_PROBE_OUTCOMES="${OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES:-0}"
REVIEW_MIN_OUTCOMES="${OPENCLAW_COST_GATE_REVIEW_MIN_OUTCOMES_PER_SIDE_CELL:-3}"
REVIEW_MIN_AVG_NET_BPS="${OPENCLAW_COST_GATE_REVIEW_MIN_AVG_NET_BPS:-0.0}"
REVIEW_MIN_NET_POSITIVE_PCT="${OPENCLAW_COST_GATE_REVIEW_MIN_NET_POSITIVE_PCT:-60.0}"
STALE_LOCK_MIN="${OPENCLAW_COST_GATE_LEARNING_STALE_LOCK_MIN:-30}"

mkdir -p "$LANE_DIR" "$LOG_DIR" "$LOCK_ROOT" "$HEARTBEAT_DIR"

ts() { date -u '+%Y-%m-%d %H:%M:%S'; }

validate_int() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[0-9]+$ ]]; then
        echo "[$(ts)] FATAL: ${name} must be an integer: ${value}" | tee -a "$LOG" >&2
        exit 2
    fi
}

validate_bool01() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[01]$ ]]; then
        echo "[$(ts)] FATAL: ${name} must be 0 or 1: ${value}" | tee -a "$LOG" >&2
        exit 2
    fi
}

validate_decimal() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^-?[0-9]+([.][0-9]+)?$ ]]; then
        echo "[$(ts)] FATAL: ${name} must be decimal: ${value}" | tee -a "$LOG" >&2
        exit 2
    fi
}

if [[ ! "$PG_TIMEFRAME" =~ ^[[:alnum:]]{1,16}$ ]]; then
    echo "[$(ts)] FATAL: OPENCLAW_COST_GATE_LEARNING_PG_TIMEFRAME invalid: ${PG_TIMEFRAME}" | tee -a "$LOG" >&2
    exit 2
fi
validate_int "OPENCLAW_COST_GATE_LEARNING_OUTCOME_HORIZON_MINUTES" "$OUTCOME_HORIZON_MINUTES"
validate_decimal "OPENCLAW_COST_GATE_LEARNING_OUTCOME_COST_BPS" "$OUTCOME_COST_BPS"
validate_int "OPENCLAW_COST_GATE_LEARNING_MAX_ENTRY_DELAY_MS" "$MAX_ENTRY_DELAY_MS"
validate_int "OPENCLAW_COST_GATE_LEARNING_PG_STATEMENT_TIMEOUT_MS" "$PG_STATEMENT_TIMEOUT_MS"
validate_int "OPENCLAW_COST_GATE_HISTORICAL_MAX_SCORECARD_AGE_HOURS" "$HISTORICAL_MAX_SCORECARD_AGE_HOURS"
validate_int "OPENCLAW_COST_GATE_HISTORICAL_MIN_CANDIDATE_SAMPLE" "$HISTORICAL_MIN_CANDIDATE_SAMPLE"
validate_bool01 "OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES" "$APPEND_OUTCOMES"
validate_bool01 "OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES" "$RECORD_PROBE_OUTCOMES"
validate_int "OPENCLAW_COST_GATE_REVIEW_MIN_OUTCOMES_PER_SIDE_CELL" "$REVIEW_MIN_OUTCOMES"
validate_decimal "OPENCLAW_COST_GATE_REVIEW_MIN_AVG_NET_BPS" "$REVIEW_MIN_AVG_NET_BPS"
validate_decimal "OPENCLAW_COST_GATE_REVIEW_MIN_NET_POSITIVE_PCT" "$REVIEW_MIN_NET_POSITIVE_PCT"
validate_int "OPENCLAW_COST_GATE_LEARNING_STALE_LOCK_MIN" "$STALE_LOCK_MIN"

PYBIN="${OPENCLAW_PYTHON_BIN:-}"
if [[ -z "$PYBIN" ]]; then
    if [[ -x "$HOME/.venv/bin/python" ]]; then
        PYBIN="$HOME/.venv/bin/python"
    else
        PYBIN="python3"
    fi
fi

touch "$HEARTBEAT_DIR/cost_gate_learning_lane.last_fire" 2>/dev/null || true

if [[ -d "$LOCK_DIR" ]] && [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +"$STALE_LOCK_MIN" 2>/dev/null)" ]]; then
    echo "[$(ts)] WARN: stale lock (>${STALE_LOCK_MIN}min) cleared: $LOCK_DIR" >> "$LOG"
    rmdir "$LOCK_DIR" 2>/dev/null || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: cost-gate learning lane already running (lock held)" >> "$LOG"
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
if [[ -f "$ENV_FILE" ]]; then
    PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_USER=$(grep '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_DB=$(grep '^POSTGRES_DB=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_HOST=$(grep '^POSTGRES_HOST=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_PORT=$(grep '^POSTGRES_PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$PG_PASS}"
    export POSTGRES_USER="${POSTGRES_USER:-$PG_USER}"
    export POSTGRES_DB="${POSTGRES_DB:-$PG_DB}"
    export POSTGRES_HOST="${POSTGRES_HOST:-${PG_HOST:-127.0.0.1}}"
    export POSTGRES_PORT="${POSTGRES_PORT:-${PG_PORT:-5432}}"
fi

export PGOPTIONS="-c default_transaction_read_only=on"
export OPENCLAW_BASE_DIR="$BASE"
export OPENCLAW_DATA_DIR="$DATA"

STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
REFRESH_OUT="${LANE_DIR}/outcome_refresh_${STAMP}.json"
REFRESH_LATEST="${LANE_DIR}/outcome_refresh_latest.json"
REVIEW_OUT="${LANE_DIR}/blocked_outcome_review_${STAMP}.json"
REVIEW_LATEST="${LANE_DIR}/blocked_outcome_review_latest.json"
HISTORICAL_REVIEW_OUT="${LANE_DIR}/historical_scorecard_review_${STAMP}.json"
HISTORICAL_REVIEW_LATEST="${LANE_DIR}/historical_scorecard_review_latest.json"

HISTORICAL_REVIEW_ARGS=(
    -m cost_gate_learning_lane.historical_review
    --scorecard-json "$SCORECARD_JSON"
    --max-scorecard-age-hours "$HISTORICAL_MAX_SCORECARD_AGE_HOURS"
    --min-candidate-sample "$HISTORICAL_MIN_CANDIDATE_SAMPLE"
    --output "$HISTORICAL_REVIEW_OUT"
)

REFRESH_ARGS=(
    -m cost_gate_learning_lane.outcome_refresh
    --ledger "$LEDGER"
    --source-pg
    --record-blocked-outcomes
    --horizon-minutes "$OUTCOME_HORIZON_MINUTES"
    --outcome-cost-bps "$OUTCOME_COST_BPS"
    --max-entry-delay-ms "$MAX_ENTRY_DELAY_MS"
    --pg-timeframe "$PG_TIMEFRAME"
    --pg-statement-timeout-ms "$PG_STATEMENT_TIMEOUT_MS"
    --output "$REFRESH_OUT"
)
if [[ "$APPEND_OUTCOMES" == "1" ]]; then
    REFRESH_ARGS+=(--append-ledger)
fi
if [[ "$RECORD_PROBE_OUTCOMES" == "1" ]]; then
    REFRESH_ARGS+=(--record-probe-outcomes)
fi

REVIEW_ARGS=(
    -m cost_gate_learning_lane.outcome_review
    --ledger "$LEDGER"
    --min-outcomes-per-side-cell "$REVIEW_MIN_OUTCOMES"
    --min-avg-net-bps "$REVIEW_MIN_AVG_NET_BPS"
    --min-net-positive-pct "$REVIEW_MIN_NET_POSITIVE_PCT"
    --output "$REVIEW_OUT"
)

echo "[$(ts)] === Cost-gate learning lane refresh start append=${APPEND_OUTCOMES} ledger=${LEDGER} ===" >> "$LOG"
historical_review_rc=0
(
    cd "$BASE"
    export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
    export PYTHONDONTWRITEBYTECODE=1
    "$PYBIN" "${HISTORICAL_REVIEW_ARGS[@]}"
) >> "$LOG" 2>&1 || historical_review_rc=$?
if [[ -f "$HISTORICAL_REVIEW_OUT" ]]; then
    cp "$HISTORICAL_REVIEW_OUT" "$HISTORICAL_REVIEW_LATEST"
fi

refresh_rc=0
(
    cd "$BASE"
    export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
    export PYTHONDONTWRITEBYTECODE=1
    "$PYBIN" "${REFRESH_ARGS[@]}"
) >> "$LOG" 2>&1 || refresh_rc=$?
if [[ -f "$REFRESH_OUT" ]]; then
    cp "$REFRESH_OUT" "$REFRESH_LATEST"
fi

review_rc=0
(
    cd "$BASE"
    export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
    export PYTHONDONTWRITEBYTECODE=1
    "$PYBIN" "${REVIEW_ARGS[@]}"
) >> "$LOG" 2>&1 || review_rc=$?
if [[ -f "$REVIEW_OUT" ]]; then
    cp "$REVIEW_OUT" "$REVIEW_LATEST"
fi

STATUS_JSON=$(HISTORICAL_REVIEW_OUT="$HISTORICAL_REVIEW_OUT" REFRESH_OUT="$REFRESH_OUT" REVIEW_OUT="$REVIEW_OUT" HISTORICAL_REVIEW_RC="$historical_review_rc" REFRESH_RC="$refresh_rc" REVIEW_RC="$review_rc" LEDGER="$LEDGER" APPEND_OUTCOMES="$APPEND_OUTCOMES" "$PYBIN" - <<'PY' 2>>"$LOG" || true
import datetime
import hashlib
import json
import os
from pathlib import Path


def load(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        with open(path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        return payload, digest, None
    except FileNotFoundError:
        return {}, None, "missing"
    except Exception as exc:  # noqa: BLE001 - status log must survive failures.
        return {}, None, f"{type(exc).__name__}:{exc}"


historical, historical_sha, historical_err = load(os.environ["HISTORICAL_REVIEW_OUT"])
refresh, refresh_sha, refresh_err = load(os.environ["REFRESH_OUT"])
review, review_sha, review_err = load(os.environ["REVIEW_OUT"])
ledger = Path(os.environ["LEDGER"])
ledger_rows = None
try:
    ledger_rows = sum(1 for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip())
except FileNotFoundError:
    ledger_rows = 0
except OSError:
    ledger_rows = None

status = {
    "ts_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "check": "cost_gate_learning_lane",
    "historical_review_rc": int(os.environ["HISTORICAL_REVIEW_RC"]),
    "refresh_rc": int(os.environ["REFRESH_RC"]),
    "review_rc": int(os.environ["REVIEW_RC"]),
    "append_outcomes": os.environ["APPEND_OUTCOMES"] == "1",
    "ledger_path": str(ledger),
    "ledger_row_count": ledger_rows,
    "historical_review_artifact_path": os.environ["HISTORICAL_REVIEW_OUT"],
    "historical_review_sha256": historical_sha,
    "historical_review_error": historical_err,
    "historical_review_status": historical.get("status"),
    "historical_review_reason": historical.get("reason"),
    "historical_review_next_trigger": historical.get("next_trigger"),
    "historical_candidate_side_cell_count": historical.get("historical_candidate_side_cell_count"),
    "refresh_artifact_path": os.environ["REFRESH_OUT"],
    "refresh_sha256": refresh_sha,
    "refresh_error": refresh_err,
    "review_artifact_path": os.environ["REVIEW_OUT"],
    "review_sha256": review_sha,
    "review_error": review_err,
    "refresh_window_count": refresh.get("window_count"),
    "refresh_price_observation_count": refresh.get("price_observation_count"),
    "refresh_outcome_count": refresh.get("outcome_count"),
    "refresh_appended_outcome_count": refresh.get("appended_outcome_count"),
    "review_status": review.get("status"),
    "review_reason": review.get("reason"),
    "review_next_trigger": review.get("next_trigger"),
    "review_candidate_side_cell_count": review.get("review_candidate_side_cell_count"),
    "blocked_signal_outcome_count": review.get("blocked_signal_outcome_count"),
    "boundary": "artifact_only_readonly_pg_jsonl_ledger_no_order_no_cost_gate_relaxation",
}
print(json.dumps(status, ensure_ascii=False, sort_keys=True))
PY
)
if [[ -n "$STATUS_JSON" ]]; then
    echo "$STATUS_JSON" >> "$STATUS_LOG"
fi

echo "[$(ts)] === Cost-gate learning lane refresh end historical_review_rc=${historical_review_rc} refresh_rc=${refresh_rc} review_rc=${review_rc} ===" >> "$LOG"

# fail-soft: rc/status are recorded; alpha-discovery reads artifacts and ledger
# state. Operator action is required for deploy, writer enablement, or probe authority.
exit 0
