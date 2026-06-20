#!/usr/bin/env bash
# flash_dip_l1_short_exit_replay_cron.sh - read-only FlashDip L1 short-exit replay.
#
# Suggested Linux cron:
#   31 6 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/flash_dip_l1_short_exit_replay_cron.sh
#
# Hard boundary:
#   read-only PG via libpq PGOPTIONS plus helper-side readonly session. Writes
#   are limited to local research artifacts, status logs, heartbeat, and lock
#   files under OPENCLAW_DATA_DIR. No order, auth, risk, strategy flag, or
#   runtime mutation.
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/flash_dip_l1_short_exit_replay_cron.log"
STATUS_LOG="${LOG_DIR}/flash_dip_l1_short_exit_replay.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/flash_dip_l1_short_exit_replay_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
ARTIFACT_DIR="${DATA}/research/tail_dislocation_meanrev"

K_PCT="${OPENCLAW_FLASH_DIP_L1_REPLAY_K_PCT:-6}"
HOLD="${OPENCLAW_FLASH_DIP_L1_REPLAY_HOLD:-2}"
CAP="${OPENCLAW_FLASH_DIP_L1_REPLAY_CAP:-3}"
NOTIONAL_FRAC="${OPENCLAW_FLASH_DIP_L1_REPLAY_NOTIONAL_FRAC:-0.005}"
HORIZON_MINUTES="${OPENCLAW_FLASH_DIP_L1_REPLAY_HORIZON_MINUTES:-15,60,240}"
QUEUE_AHEAD_FRACS="${OPENCLAW_FLASH_DIP_L1_REPLAY_QUEUE_AHEAD_FRACS:-0,0.5,1}"
GATE_QUEUE_AHEAD_FRAC="${OPENCLAW_FLASH_DIP_L1_REPLAY_GATE_QUEUE_AHEAD_FRAC:-1}"
GATE_HORIZON_MINUTES="${OPENCLAW_FLASH_DIP_L1_REPLAY_GATE_HORIZON_MINUTES:-240}"
MIN_FILLED="${OPENCLAW_FLASH_DIP_L1_REPLAY_MIN_FILLED:-30}"
MIN_DAYS="${OPENCLAW_FLASH_DIP_L1_REPLAY_MIN_DAYS:-20}"
MAKER_TIMEOUT_MINUTES="${OPENCLAW_FLASH_DIP_L1_REPLAY_MAKER_TIMEOUT_MINUTES:-1440}"
CLEAN_SINCE="${OPENCLAW_FLASH_DIP_L1_REPLAY_CLEAN_SINCE:-2026-06-17T14:25:00+02:00}"
STALE_LOCK_MIN="${OPENCLAW_FLASH_DIP_L1_REPLAY_STALE_LOCK_MIN:-180}"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$HEARTBEAT_DIR" "$ARTIFACT_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

PYBIN="${OPENCLAW_PYTHON_BIN:-}"
if [[ -z "$PYBIN" ]]; then
    if [[ -x "$HOME/.venv/bin/python" ]]; then
        PYBIN="$HOME/.venv/bin/python"
    else
        PYBIN="python3"
    fi
fi

touch "$HEARTBEAT_DIR/flash_dip_l1_short_exit_replay.last_fire" 2>/dev/null || true

validate_numeric() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
        echo "[$(ts)] FATAL: ${name} must be numeric: ${value}" | tee -a "$LOG" >&2
        exit 2
    fi
}

validate_int() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[0-9]+$ ]]; then
        echo "[$(ts)] FATAL: ${name} must be an integer: ${value}" | tee -a "$LOG" >&2
        exit 2
    fi
}

validate_csv_numeric() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[0-9]+([.][0-9]+)?(,[0-9]+([.][0-9]+)?)*$ ]]; then
        echo "[$(ts)] FATAL: ${name} must be comma-separated numeric values: ${value}" | tee -a "$LOG" >&2
        exit 2
    fi
}

validate_numeric "OPENCLAW_FLASH_DIP_L1_REPLAY_K_PCT" "$K_PCT"
validate_int "OPENCLAW_FLASH_DIP_L1_REPLAY_HOLD" "$HOLD"
if [[ "$CAP" != "none" && "$CAP" != "unlimited" && "$CAP" != "all" ]]; then
    validate_int "OPENCLAW_FLASH_DIP_L1_REPLAY_CAP" "$CAP"
fi
validate_numeric "OPENCLAW_FLASH_DIP_L1_REPLAY_NOTIONAL_FRAC" "$NOTIONAL_FRAC"
validate_csv_numeric "OPENCLAW_FLASH_DIP_L1_REPLAY_HORIZON_MINUTES" "$HORIZON_MINUTES"
validate_csv_numeric "OPENCLAW_FLASH_DIP_L1_REPLAY_QUEUE_AHEAD_FRACS" "$QUEUE_AHEAD_FRACS"
validate_numeric "OPENCLAW_FLASH_DIP_L1_REPLAY_GATE_QUEUE_AHEAD_FRAC" "$GATE_QUEUE_AHEAD_FRAC"
validate_int "OPENCLAW_FLASH_DIP_L1_REPLAY_GATE_HORIZON_MINUTES" "$GATE_HORIZON_MINUTES"
validate_int "OPENCLAW_FLASH_DIP_L1_REPLAY_MIN_FILLED" "$MIN_FILLED"
validate_int "OPENCLAW_FLASH_DIP_L1_REPLAY_MIN_DAYS" "$MIN_DAYS"
validate_int "OPENCLAW_FLASH_DIP_L1_REPLAY_MAKER_TIMEOUT_MINUTES" "$MAKER_TIMEOUT_MINUTES"

if [[ -d "$LOCK_DIR" ]] && [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +"$STALE_LOCK_MIN" 2>/dev/null)" ]]; then
    echo "[$(ts)] WARN: stale lock (>${STALE_LOCK_MIN}min) cleared: $LOCK_DIR" >> "$LOG"
    rmdir "$LOCK_DIR" 2>/dev/null || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: FlashDip L1 short-exit replay already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

SCRIPT="$BASE/helper_scripts/research/tail_dislocation_meanrev/shallow_retune_l1_short_exit_replay.py"
if [[ ! -f "$SCRIPT" ]]; then
    echo "[$(ts)] FATAL: L1 replay helper missing: $SCRIPT" | tee -a "$LOG" >&2
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

STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
OUT="${ARTIFACT_DIR}/shallow_retune_l1_short_exit_replay_${STAMP}.json"
LATEST="${ARTIFACT_DIR}/shallow_retune_l1_short_exit_replay_latest.json"

ARGS=(
    "$SCRIPT"
    --out "$OUT"
    --k-pct "$K_PCT"
    --hold "$HOLD"
    --cap "$CAP"
    --notional-frac "$NOTIONAL_FRAC"
    --horizon-minutes "$HORIZON_MINUTES"
    --queue-ahead-fracs "$QUEUE_AHEAD_FRACS"
    --gate-queue-ahead-frac "$GATE_QUEUE_AHEAD_FRAC"
    --gate-horizon-minutes "$GATE_HORIZON_MINUTES"
    --min-filled "$MIN_FILLED"
    --min-days "$MIN_DAYS"
    --maker-timeout-minutes "$MAKER_TIMEOUT_MINUTES"
    --clean-since "$CLEAN_SINCE"
)

echo "[$(ts)] === FlashDip L1 short-exit replay start (k_pct=${K_PCT} hold=${HOLD} cap=${CAP} gate=${GATE_QUEUE_AHEAD_FRAC}/${GATE_HORIZON_MINUTES}m) ===" >> "$LOG"
rc=0
(
    cd "$BASE"
    export PYTHONPATH="$BASE/helper_scripts/research/tail_dislocation_meanrev${PYTHONPATH:+:$PYTHONPATH}"
    "$PYBIN" "${ARGS[@]}"
) >> "$LOG" 2>&1 || rc=$?

STATUS_JSON=$(REPLAY_OUT="$OUT" REPLAY_RC="$rc" REPLAY_LATEST="$LATEST" "$PYBIN" - <<'PY' 2>>"$LOG" || true
import datetime
import hashlib
import json
import os
import shutil

out = os.environ["REPLAY_OUT"]
latest = os.environ["REPLAY_LATEST"]
rc = int(os.environ["REPLAY_RC"])
status = {
    "ts_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "check": "flash_dip_l1_short_exit_replay",
    "rc": rc,
    "artifact_path": out,
    "latest_path": latest,
    "parse_ok": False,
    "verdict_status": None,
    "fail_reasons": [],
    "candidate_events": None,
    "candidate_days": None,
    "candidate_symbols": [],
    "l1_rows_post_filter": None,
    "trade_rows": None,
    "symbols_with_l1": [],
    "symbols_missing_l1": [],
    "event_window_maker_timeout_minutes": None,
    "events_with_l1_in_event_window": None,
    "events_missing_l1_in_event_window": None,
    "days_with_l1_in_event_window": None,
    "days_missing_l1_in_event_window": None,
    "event_window_l1_relation_counts": {},
    "dominant_missing_event_window_l1_relation": None,
    "gate_exit_measured": None,
    "gate_distinct_exit_days": None,
    "gate_annret": None,
    "gate_maxdd": None,
    "boundary": "counterfactual_only_not_promotion_evidence",
}
try:
    with open(out, "rb") as f:
        blob = f.read()
    report = json.loads(blob.decode("utf-8"))
    sha = hashlib.sha256(blob).hexdigest()
    status["sha256"] = sha
    verdict = report.get("verdict") or {}
    overlap = report.get("candidate_overlap") or {}
    l1_meta = report.get("loaded_l1_meta") or {}
    trades_meta = report.get("trades_meta") or {}
    coverage = report.get("l1_candidate_coverage") or {}
    relation_counts = coverage.get("event_window_l1_relation_counts") or {}
    missing_relation_counts = {
        str(k): int(v)
        for k, v in relation_counts.items()
        if str(k) != "covered"
    }
    dominant_missing_relation = None
    if missing_relation_counts:
        dominant_missing_relation = max(
            missing_relation_counts.items(),
            key=lambda kv: (kv[1], kv[0]),
        )[0]
    status.update({
        "parse_ok": True,
        "version": report.get("version"),
        "generated_utc": report.get("generated_utc"),
        "verdict_status": verdict.get("status"),
        "fail_reasons": verdict.get("fail_reasons") or [],
        "candidate_events": overlap.get("n_events_l1_window"),
        "candidate_days": overlap.get("n_distinct_days_l1_window"),
        "candidate_symbols": overlap.get("symbols") or [],
        "l1_rows_post_filter": l1_meta.get("n_rows_post_filter"),
        "trade_rows": trades_meta.get("n_rows"),
        "symbols_with_l1": coverage.get("symbols_with_l1") or [],
        "symbols_missing_l1": coverage.get("symbols_missing_l1") or [],
        "event_window_maker_timeout_minutes": coverage.get("event_window_maker_timeout_minutes"),
        "events_with_l1_in_event_window": coverage.get("n_events_with_l1_in_event_window"),
        "events_missing_l1_in_event_window": coverage.get("n_events_missing_l1_in_event_window"),
        "days_with_l1_in_event_window": coverage.get("n_distinct_days_with_l1_in_event_window"),
        "days_missing_l1_in_event_window": coverage.get("n_distinct_days_missing_l1_in_event_window"),
        "event_window_l1_relation_counts": relation_counts,
        "dominant_missing_event_window_l1_relation": dominant_missing_relation,
    })
    gate_q = verdict.get("gate_queue_ahead_frac")
    gate_h = f"{verdict.get('gate_horizon_minutes')}m"
    for row in report.get("queue_horizon_summary") or []:
        try:
            if abs(float(row.get("queue_ahead_frac")) - float(gate_q)) > 1e-12:
                continue
        except (TypeError, ValueError):
            continue
        h = (row.get("horizons") or {}).get(gate_h) or {}
        fn = h.get("fixed_notional") or {}
        status["gate_exit_measured"] = h.get("n_exit_measured")
        status["gate_distinct_exit_days"] = h.get("n_distinct_exit_days")
        status["gate_annret"] = fn.get("annualized_return")
        status["gate_maxdd"] = fn.get("max_drawdown")
        break
    shutil.copyfile(out, latest)
    with open(latest + ".sha256", "w", encoding="utf-8") as f:
        f.write(f"{sha}  {os.path.basename(latest)}\n")
except FileNotFoundError:
    status["error"] = "artifact_missing"
except Exception as exc:
    status["error"] = exc.__class__.__name__

print(json.dumps(status, separators=(",", ":"), sort_keys=True))
PY
)

if [[ -z "$STATUS_JSON" ]]; then
    echo "[$(ts)] === FlashDip L1 short-exit replay end FAIL rc=${rc} (status synthesis empty) ===" >> "$LOG"
    exit 1
fi

echo "$STATUS_JSON" >> "$STATUS_LOG"
echo "[$(ts)] status: $STATUS_JSON" >> "$LOG"
echo "[$(ts)] === FlashDip L1 short-exit replay end rc=${rc} ===" >> "$LOG"
exit "$rc"
