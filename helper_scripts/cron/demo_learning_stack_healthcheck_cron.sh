#!/usr/bin/env bash
# demo_learning_stack_healthcheck_cron.sh - refresh demo-learning stack health evidence.
#
# 硬邊界：
#   只讀 source/crontab/local artifacts，並只寫 OPENCLAW_DATA_DIR 下的
#   healthcheck JSON/status/heartbeat/lock/log。不得同步 source、改 crontab、
#   改 env、deploy/restart、寫 PG、連 Bybit、下單、啟 writer、降低 Cost Gate。
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
OUT_DIR="${DATA}/demo_learning_stack_healthcheck"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/demo_learning_stack_healthcheck_cron.log"
STATUS_LOG="${LOG_DIR}/demo_learning_stack_healthcheck.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/demo_learning_stack_healthcheck_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"

MAX_HEARTBEAT_AGE_MINUTES="${OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_MAX_HEARTBEAT_AGE_MINUTES:-90}"
MAX_STATUS_AGE_MINUTES="${OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_MAX_STATUS_AGE_MINUTES:-180}"
STALE_LOCK_MIN="${OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_STALE_LOCK_MIN:-20}"
EXPECTED_HEAD="${OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_EXPECTED_HEAD:-${OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD:-${OPENCLAW_EXPECTED_SOURCE_HEAD:-}}}"

mkdir -p "$OUT_DIR" "$LOG_DIR" "$LOCK_ROOT" "$HEARTBEAT_DIR"

ts() { date -u '+%Y-%m-%d %H:%M:%S'; }

validate_int() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[0-9]+$ ]]; then
        echo "[$(ts)] FATAL: ${name} must be an integer: ${value}" | tee -a "$LOG" >&2
        exit 2
    fi
}

validate_int "OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_MAX_HEARTBEAT_AGE_MINUTES" "$MAX_HEARTBEAT_AGE_MINUTES"
validate_int "OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_MAX_STATUS_AGE_MINUTES" "$MAX_STATUS_AGE_MINUTES"
validate_int "OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_STALE_LOCK_MIN" "$STALE_LOCK_MIN"

PYBIN="${OPENCLAW_PYTHON_BIN:-}"
if [[ -z "$PYBIN" ]]; then
    if [[ -x "$HOME/.venv/bin/python" ]]; then
        PYBIN="$HOME/.venv/bin/python"
    else
        PYBIN="python3"
    fi
fi

touch "$HEARTBEAT_DIR/demo_learning_stack_healthcheck.last_fire" 2>/dev/null || true

if [[ -d "$LOCK_DIR" ]] && [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +"$STALE_LOCK_MIN" 2>/dev/null)" ]]; then
    echo "[$(ts)] WARN: stale lock (>${STALE_LOCK_MIN}min) cleared: $LOCK_DIR" >> "$LOG"
    rmdir "$LOCK_DIR" 2>/dev/null || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: demo learning stack healthcheck already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
DATED_JSON="${OUT_DIR}/demo_learning_stack_healthcheck_${STAMP}.json"
LATEST_JSON="${OUT_DIR}/demo_learning_stack_healthcheck_latest.json"

ARGS=(
    "$BASE/helper_scripts/cron/demo_learning_stack_healthcheck.py"
    --data-dir "$DATA"
    --repo-root "$BASE"
    --max-heartbeat-age-minutes "$MAX_HEARTBEAT_AGE_MINUTES"
    --max-status-age-minutes "$MAX_STATUS_AGE_MINUTES"
    --json-output "$DATED_JSON"
)
if [[ -n "$EXPECTED_HEAD" ]]; then
    ARGS+=(--expected-head "$EXPECTED_HEAD")
fi

echo "[$(ts)] === Demo learning stack healthcheck start ===" >> "$LOG"
health_rc=0
(
    cd "$BASE"
    export PYTHONDONTWRITEBYTECODE=1
    "$PYBIN" "${ARGS[@]}"
) >> "$LOG" 2>&1 || health_rc=$?
if [[ -f "$DATED_JSON" ]]; then
    cp "$DATED_JSON" "$LATEST_JSON"
fi

STATUS_JSON=$(DATED_JSON="$DATED_JSON" LATEST_JSON="$LATEST_JSON" HEALTH_RC="$health_rc" "$PYBIN" - <<'PY' 2>>"$LOG" || true
import datetime
import hashlib
import json
import os
from pathlib import Path


def load_json(path_text):
    path = Path(path_text)
    try:
        raw = path.read_bytes()
        return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest(), None
    except FileNotFoundError:
        return {}, None, "missing"
    except Exception as exc:  # noqa: BLE001 - status logging must be fail-soft.
        return {}, None, f"{type(exc).__name__}:{exc}"


payload, digest, error = load_json(os.environ["DATED_JSON"])
answers = payload.get("answers") if isinstance(payload.get("answers"), dict) else {}
status = {
    "ts_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "check": "demo_learning_stack_healthcheck",
    "healthcheck_rc": int(os.environ["HEALTH_RC"]),
    "artifact_path": os.environ["DATED_JSON"],
    "latest_path": os.environ["LATEST_JSON"],
    "artifact_sha256": digest,
    "artifact_error": error,
    "schema_version": payload.get("schema_version"),
    "status": payload.get("status"),
    "reason": payload.get("reason"),
    "next_action": payload.get("next_action"),
    "source_ready": answers.get("source_ready"),
    "stack_installed": answers.get("stack_installed"),
    "heartbeats_recent": answers.get("heartbeats_recent"),
    "statuses_recent": answers.get("statuses_recent"),
    "latest_artifacts_present": answers.get("latest_artifacts_present"),
    "false_negative_review_chain_present": answers.get("false_negative_review_chain_present"),
    "false_negative_review_chain_recent": answers.get("false_negative_review_chain_recent"),
    "false_negative_candidate_packet_present": answers.get("false_negative_candidate_packet_present"),
    "false_negative_operator_review_present": answers.get("false_negative_operator_review_present"),
    "cost_gate_learning_ledger_rows_present": answers.get("cost_gate_learning_ledger_rows_present"),
    "blocked_signal_outcomes_present": answers.get("blocked_signal_outcomes_present"),
    "boundary": "artifact-only stack health status; no PG/Bybit/order/runtime mutation",
}
print(json.dumps(status, ensure_ascii=False, sort_keys=True))
PY
)
if [[ -n "$STATUS_JSON" ]]; then
    echo "$STATUS_JSON" >> "$STATUS_LOG"
fi
echo "[$(ts)] === Demo learning stack healthcheck end rc=${health_rc} ===" >> "$LOG"
exit "$health_rc"
