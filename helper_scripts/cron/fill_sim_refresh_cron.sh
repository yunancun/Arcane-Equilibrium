#!/usr/bin/env bash
# fill_sim_refresh_cron.sh — bounded read-only fill_sim artifact refresh.
#
# This cron keeps the MM verdict adverse-selection source fresh without putting
# the heavy fill_sim job inside recorder_mm_verdict_cron.sh. It writes only local
# artifacts/logs/heartbeat/alerts under OPENCLAW_DATA_DIR. Database access is
# read-only at libpq (PGOPTIONS) and in data_loader.connect().
#
# Suggested Linux cron, intentionally before recorder_mm_verdict_cron.sh:
#   5 6 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/fill_sim_refresh_cron.sh
#
# Operator knobs:
#   OPENCLAW_FILL_SIM_HOURS=2              recent window; 0 = full available data
#   OPENCLAW_FILL_SIM_MAX_AGE_H=60         skip refresh while report is younger
#   OPENCLAW_FILL_SIM_STALE_ALERT_H=72     alert if report remains too old
#   OPENCLAW_FILL_SIM_FORCE=1              run even if report is fresh
#   OPENCLAW_FILL_SIM_REPORT=<path>        output JSON; CSV is written beside it
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/fill_sim_refresh_cron.log"
STATUS_LOG="${LOG_DIR}/fill_sim_refresh.log"
ALERT_DIR="${DATA}/alerts"
ALERT_FILE="${ALERT_DIR}/alerts.jsonl"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/fill_sim_refresh_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
REPORT="${OPENCLAW_FILL_SIM_REPORT:-${DATA}/research/fillsim/fillsim_report.json}"

FILL_SIM_HOURS="${OPENCLAW_FILL_SIM_HOURS:-2}"
FILL_SIM_MAX_AGE_H="${OPENCLAW_FILL_SIM_MAX_AGE_H:-60}"
FILL_SIM_STALE_ALERT_H="${OPENCLAW_FILL_SIM_STALE_ALERT_H:-72}"
FILL_SIM_FORCE="${OPENCLAW_FILL_SIM_FORCE:-0}"
STALE_LOCK_MIN="${OPENCLAW_FILL_SIM_STALE_LOCK_MIN:-180}"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$HEARTBEAT_DIR" "$ALERT_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

PYBIN="${OPENCLAW_PYTHON_BIN:-}"
if [[ -z "$PYBIN" ]]; then
    if [[ -x "$HOME/.venv/bin/python" ]]; then
        PYBIN="$HOME/.venv/bin/python"
    else
        PYBIN="python3"
    fi
fi

touch "$HEARTBEAT_DIR/fill_sim_refresh.last_fire" 2>/dev/null || true

read_report_state() {
    "$PYBIN" - "$REPORT" "$FILL_SIM_MAX_AGE_H" "$FILL_SIM_FORCE" <<'PY'
import datetime
import json
import os
import sys

path = sys.argv[1]
max_age_h = float(sys.argv[2])
force = str(sys.argv[3]).lower() in {"1", "true", "yes", "y"}
now = datetime.datetime.now(datetime.timezone.utc)
info = {
    "path": path,
    "present": False,
    "parse_ok": False,
    "generated_at": None,
    "age_hours": None,
    "error": None,
}
try:
    with open(path, encoding="utf-8") as f:
        rep = json.load(f)
    info["present"] = True
    info["parse_ok"] = True
    gen = rep.get("generated_at")
    info["generated_at"] = gen
    gt = datetime.datetime.fromisoformat(str(gen))
    if gt.tzinfo is None:
        gt = gt.replace(tzinfo=datetime.timezone.utc)
    info["age_hours"] = round((now - gt).total_seconds() / 3600.0, 2)
except FileNotFoundError:
    info["error"] = "missing"
except Exception as exc:
    info["error"] = exc.__class__.__name__

action = "run"
if (
    not force
    and info["present"]
    and info["parse_ok"]
    and info["age_hours"] is not None
    and info["age_hours"] <= max_age_h
):
    action = "skip_fresh"
print(action)
print(json.dumps(info, separators=(",", ":"), sort_keys=True))
PY
}

emit_status() {
    local action="$1"
    local rc="$2"
    local before_json="$3"
    local after_json="$4"
    STATUS_ACTION="$action" \
    STATUS_RC="$rc" \
    STATUS_BEFORE="$before_json" \
    STATUS_AFTER="$after_json" \
    STATUS_REPORT="$REPORT" \
    STATUS_HOURS="$FILL_SIM_HOURS" \
    STATUS_MAX_AGE_H="$FILL_SIM_MAX_AGE_H" \
    STATUS_STALE_ALERT_H="$FILL_SIM_STALE_ALERT_H" \
    STATUS_FORCE="$FILL_SIM_FORCE" \
    "$PYBIN" - <<'PY' >> "$STATUS_LOG"
import datetime
import json
import os

def _loads(name):
    raw = os.environ.get(name) or "{}"
    try:
        return json.loads(raw)
    except ValueError:
        return {"parse_error": True, "raw": raw}

row = {
    "ts_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "check": "fill_sim_refresh",
    "action": os.environ["STATUS_ACTION"],
    "rc": int(os.environ["STATUS_RC"]),
    "report": os.environ["STATUS_REPORT"],
    "hours": float(os.environ["STATUS_HOURS"]),
    "max_age_h": float(os.environ["STATUS_MAX_AGE_H"]),
    "stale_alert_h": float(os.environ["STATUS_STALE_ALERT_H"]),
    "force": os.environ["STATUS_FORCE"],
    "before": _loads("STATUS_BEFORE"),
    "after": _loads("STATUS_AFTER"),
}
print(json.dumps(row, separators=(",", ":"), sort_keys=True))
PY
}

append_alert() {
    local subject="$1"
    local severity="$2"
    local body="$3"
    ALERT_SUBJECT="$subject" ALERT_SEVERITY="$severity" ALERT_BODY="$body" \
    "$PYBIN" - <<'PY' >> "$ALERT_FILE"
import datetime
import json
import os

row = {
    "ts_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "subject": os.environ["ALERT_SUBJECT"],
    "severity": os.environ["ALERT_SEVERITY"],
    "body": os.environ["ALERT_BODY"],
    "channels_attempted": [],
    "channels_ok": None,
}
print(json.dumps(row, separators=(",", ":"), sort_keys=True))
PY
}

PRE_STATE="$(read_report_state)"
PRE_ACTION="$(printf '%s\n' "$PRE_STATE" | sed -n '1p')"
PRE_JSON="$(printf '%s\n' "$PRE_STATE" | sed -n '2p')"
PRE_ACTION="${PRE_ACTION:-run}"
if [[ -z "$PRE_JSON" ]]; then
    PRE_JSON="{}"
fi
if [[ "$PRE_ACTION" == "skip_fresh" ]]; then
    emit_status "skipped_fresh" 0 "$PRE_JSON" "$PRE_JSON"
    echo "[$(ts)] SKIP: fill_sim report fresh; state=${PRE_JSON}" >> "$LOG"
    exit 0
fi

if [[ -d "$LOCK_DIR" ]] && [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +"$STALE_LOCK_MIN" 2>/dev/null)" ]]; then
    echo "[$(ts)] WARN: stale lock (>${STALE_LOCK_MIN}min) cleared: $LOCK_DIR" >> "$LOG"
    rmdir "$LOCK_DIR" 2>/dev/null || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    emit_status "skipped_lock_held" 0 "$PRE_JSON" "$PRE_JSON"
    echo "[$(ts)] SKIP: fill_sim refresh already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

if [[ ! -d "$BASE/program_code/research/microstructure" ]]; then
    emit_status "base_missing" 2 "$PRE_JSON" "$PRE_JSON"
    echo "[$(ts)] FATAL: microstructure package not found under BASE=$BASE" | tee -a "$LOG" >&2
    exit 2
fi

SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"
if [[ ! -f "$ENV_FILE" ]]; then
    emit_status "env_missing" 2 "$PRE_JSON" "$PRE_JSON"
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
    emit_status "env_incomplete" 2 "$PRE_JSON" "$PRE_JSON"
    echo "[$(ts)] FATAL: PG creds incomplete in $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi

export PGHOST="$PG_HOST" PGPORT="$PG_PORT" PGDATABASE="$PG_DB" PGUSER="$PG_USER" PGPASSWORD="$PG_PASS"
export PGOPTIONS="-c default_transaction_read_only=on"

ARGS=(
    -m program_code.research.microstructure.fill_sim
    --hours "$FILL_SIM_HOURS"
    --out "$REPORT"
)
if [[ -n "${OPENCLAW_FILL_SIM_SINCE:-}" ]]; then
    ARGS+=(--since "$OPENCLAW_FILL_SIM_SINCE")
fi
if [[ -n "${OPENCLAW_FILL_SIM_UNTIL:-}" ]]; then
    ARGS+=(--until "$OPENCLAW_FILL_SIM_UNTIL")
fi
if [[ -n "${OPENCLAW_FILL_SIM_CLEAN_SINCE:-}" ]]; then
    ARGS+=(--clean-since "$OPENCLAW_FILL_SIM_CLEAN_SINCE")
fi
if [[ -n "${OPENCLAW_FILL_SIM_CADENCE_S:-}" ]]; then
    ARGS+=(--cadence-s "$OPENCLAW_FILL_SIM_CADENCE_S")
fi
if [[ -n "${OPENCLAW_FILL_SIM_SKIP_QUANTILE:-}" ]]; then
    ARGS+=(--skip-quantile "$OPENCLAW_FILL_SIM_SKIP_QUANTILE")
fi
if [[ -n "${OPENCLAW_FILL_SIM_HORIZONS:-}" ]]; then
    ARGS+=(--horizons "$OPENCLAW_FILL_SIM_HORIZONS")
fi
if [[ -n "${OPENCLAW_FILL_SIM_MIN_L1_EVENTS:-}" ]]; then
    ARGS+=(--min-l1-events "$OPENCLAW_FILL_SIM_MIN_L1_EVENTS")
fi

echo "[$(ts)] === fill_sim refresh start (hours=${FILL_SIM_HOURS} max_age=${FILL_SIM_MAX_AGE_H}h stale_alert=${FILL_SIM_STALE_ALERT_H}h force=${FILL_SIM_FORCE}) ===" >> "$LOG"
rc=0
(
    cd "$BASE"
    export PYTHONPATH="$BASE${PYTHONPATH:+:$PYTHONPATH}"
    "$PYBIN" "${ARGS[@]}"
) >> "$LOG" 2>&1 || rc=$?

POST_STATE="$(read_report_state)"
POST_JSON="$(printf '%s\n' "$POST_STATE" | sed -n '2p')"
if [[ -z "$POST_JSON" ]]; then
    POST_JSON="{}"
fi

action="refreshed"
if [[ "$rc" -ne 0 ]]; then
    action="refresh_failed"
fi
emit_status "$action" "$rc" "$PRE_JSON" "$POST_JSON"

ALERT_NEEDED=$(POST_JSON="$POST_JSON" STALE_ALERT_H="$FILL_SIM_STALE_ALERT_H" RC="$rc" "$PYBIN" - <<'PY'
import json
import os

post = json.loads(os.environ["POST_JSON"])
stale_h = float(os.environ["STALE_ALERT_H"])
rc = int(os.environ["RC"])
age = post.get("age_hours")
bad = rc != 0 or not post.get("present") or not post.get("parse_ok")
if age is not None and float(age) > stale_h:
    bad = True
print("1" if bad else "0")
PY
)

if [[ "$ALERT_NEEDED" == "1" ]]; then
    append_alert \
        "[FILL-SIM] refresh failed or stale" \
        "warning" \
        "fill_sim refresh rc=${rc}; report=${REPORT}; before=${PRE_JSON}; after=${POST_JSON}. MM verdict adverse_selection may become unavailable."
    echo "[$(ts)] ALERT appended: fill_sim refresh rc=${rc} after=${POST_JSON}" >> "$LOG"
fi

echo "[$(ts)] === fill_sim refresh end rc=${rc} after=${POST_JSON} ===" >> "$LOG"
exit 0
