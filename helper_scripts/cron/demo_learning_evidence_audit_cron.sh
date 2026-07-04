#!/usr/bin/env bash
# demo_learning_evidence_audit_cron.sh - demo learning evidence heartbeat.
#
# 建議 Linux cron：
#   7,37 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/demo_learning_evidence_audit_cron.sh
#
# 硬邊界：
#   只產出只讀 evidence packet。PG 由 libpq PGOPTIONS 與 helper-side readonly
#   session 雙重限制；寫入僅限 OPENCLAW_DATA_DIR 下的本地 Markdown/JSON audit
#   artifacts、status log、heartbeat、lock files。不得下單、改 auth/risk/strategy
#   flag、engine、runtime 或 Cost Gate。
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
OUT_DIR="${DATA}/demo_learning_evidence"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/demo_learning_evidence_audit_cron.log"
STATUS_LOG="${LOG_DIR}/demo_learning_evidence_audit.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/demo_learning_evidence_audit_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"

ENGINE_MODES="${OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_MODES:-demo,live_demo}"
LOOKBACK_HOURS="${OPENCLAW_DEMO_LEARNING_EVIDENCE_LOOKBACK_HOURS:-24}"
TOP_LIMIT="${OPENCLAW_DEMO_LEARNING_EVIDENCE_TOP_LIMIT:-20}"
PG_STATEMENT_TIMEOUT_MS="${OPENCLAW_DEMO_LEARNING_EVIDENCE_PG_STATEMENT_TIMEOUT_MS:-180000}"
STALE_LOCK_MIN="${OPENCLAW_DEMO_LEARNING_EVIDENCE_STALE_LOCK_MIN:-20}"
EXPECTED_HEAD="${OPENCLAW_DEMO_LEARNING_EVIDENCE_EXPECTED_HEAD:-${OPENCLAW_EXPECTED_SOURCE_HEAD:-}}"
REQUIRE_WRITER_ENABLED="${OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_WRITER_ENABLED:-0}"
REQUIRE_PROCESS_WRITER_ENABLED="${OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_PROCESS_WRITER_ENABLED:-0}"
AUTO_DETECT_ENGINE_PID="${OPENCLAW_DEMO_LEARNING_EVIDENCE_AUTO_DETECT_ENGINE_PID:-0}"
ENGINE_PID="${OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_PID:-}"
RUNTIME_PROC_ENVIRON="${OPENCLAW_DEMO_LEARNING_EVIDENCE_RUNTIME_PROC_ENVIRON:-}"

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

validate_bool01() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[01]$ ]]; then
        echo "[$(ts)] FATAL: ${name} must be 0 or 1: ${value}" | tee -a "$LOG" >&2
        exit 2
    fi
}

validate_int "OPENCLAW_DEMO_LEARNING_EVIDENCE_LOOKBACK_HOURS" "$LOOKBACK_HOURS"
validate_int "OPENCLAW_DEMO_LEARNING_EVIDENCE_TOP_LIMIT" "$TOP_LIMIT"
validate_int "OPENCLAW_DEMO_LEARNING_EVIDENCE_PG_STATEMENT_TIMEOUT_MS" "$PG_STATEMENT_TIMEOUT_MS"
validate_int "OPENCLAW_DEMO_LEARNING_EVIDENCE_STALE_LOCK_MIN" "$STALE_LOCK_MIN"
validate_bool01 "OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_WRITER_ENABLED" "$REQUIRE_WRITER_ENABLED"
validate_bool01 "OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_PROCESS_WRITER_ENABLED" "$REQUIRE_PROCESS_WRITER_ENABLED"
validate_bool01 "OPENCLAW_DEMO_LEARNING_EVIDENCE_AUTO_DETECT_ENGINE_PID" "$AUTO_DETECT_ENGINE_PID"

if [[ ! "$ENGINE_MODES" =~ ^[A-Za-z0-9_.,-]+$ ]]; then
    echo "[$(ts)] FATAL: OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_MODES invalid: ${ENGINE_MODES}" | tee -a "$LOG" >&2
    exit 2
fi

PYBIN="${OPENCLAW_PYTHON_BIN:-}"
if [[ -z "$PYBIN" ]]; then
    if [[ -x "$HOME/.venv/bin/python" ]]; then
        PYBIN="$HOME/.venv/bin/python"
    else
        PYBIN="python3"
    fi
fi

touch "$HEARTBEAT_DIR/demo_learning_evidence_audit.last_fire" 2>/dev/null || true

if [[ -d "$LOCK_DIR" ]] && [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +"$STALE_LOCK_MIN" 2>/dev/null)" ]]; then
    echo "[$(ts)] WARN: stale lock (>${STALE_LOCK_MIN}min) cleared: $LOCK_DIR" >> "$LOG"
    rmdir "$LOCK_DIR" 2>/dev/null || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: demo learning evidence audit already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
ENV_FILE="${OPENCLAW_DEMO_LEARNING_EVIDENCE_RUNTIME_ENV_FILE:-$SECRETS_ROOT/environment_files/basic_system_services.env}"
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

export PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=${PG_STATEMENT_TIMEOUT_MS}"
export OPENCLAW_BASE_DIR="$BASE"
export OPENCLAW_DATA_DIR="$DATA"

STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
REPORT_OUT="${OUT_DIR}/demo_learning_evidence_audit_${STAMP}.md"
JSON_OUT="${OUT_DIR}/demo_learning_evidence_audit_${STAMP}.json"
REPORT_LATEST="${OUT_DIR}/demo_learning_evidence_audit_latest.md"
JSON_LATEST="${OUT_DIR}/demo_learning_evidence_audit_latest.json"

AUDIT_ARGS=(
    "$BASE/helper_scripts/db/audit/demo_learning_evidence_audit.py"
    --lookback-hours "$LOOKBACK_HOURS"
    --top-limit "$TOP_LIMIT"
    --data-dir "$DATA"
    --repo-root "$BASE"
    --output "$REPORT_OUT"
    --json-output "$JSON_OUT"
)

IFS=',' read -r -a ENGINE_MODE_ARRAY <<< "$ENGINE_MODES"
for mode in "${ENGINE_MODE_ARRAY[@]}"; do
    if [[ -n "$mode" ]]; then
        AUDIT_ARGS+=(--engine-mode "$mode")
    fi
done
# P1-4 世代判準：把 raw pin（env 鏈或 pin 檔）過公共庫轉成 effective head。
# docs/tests/.codex 前進→回當前 HEAD（不凍 lane）；rust src 等真漂移→回原 pin
# 使下游 mismatch fail-close；pin 檔壞/git 失敗→非 hex sentinel 必紅。
# lib 檔缺失時降級為 passthrough（沿用 raw expected），不因缺 helper 硬崩 cron。
SG_LIB="$BASE/helper_scripts/cron/lib/source_generation_gate.sh"
if [[ -f "$SG_LIB" ]]; then
    source "$SG_LIB"
else
    resolve_effective_expected_head() { printf '%s' "$4"; }
fi
EXPECTED_HEAD="$(resolve_effective_expected_head "$BASE" "$DATA" "demo_learning_evidence_audit" "$EXPECTED_HEAD")"
if [[ -n "$EXPECTED_HEAD" ]]; then
    AUDIT_ARGS+=(--expected-head "$EXPECTED_HEAD")
fi
if [[ -f "$ENV_FILE" ]]; then
    AUDIT_ARGS+=(--runtime-env-file "$ENV_FILE")
fi
if [[ -n "$ENGINE_PID" ]]; then
    validate_int "OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_PID" "$ENGINE_PID"
    AUDIT_ARGS+=(--engine-pid "$ENGINE_PID")
fi
if [[ -n "$RUNTIME_PROC_ENVIRON" ]]; then
    AUDIT_ARGS+=(--runtime-proc-environ "$RUNTIME_PROC_ENVIRON")
fi
if [[ "$AUTO_DETECT_ENGINE_PID" == "1" ]]; then
    AUDIT_ARGS+=(--auto-detect-engine-pid)
fi
if [[ "$REQUIRE_WRITER_ENABLED" == "1" ]]; then
    AUDIT_ARGS+=(--require-writer-enabled)
fi
if [[ "$REQUIRE_PROCESS_WRITER_ENABLED" == "1" ]]; then
    AUDIT_ARGS+=(--require-process-writer-enabled)
fi

echo "[$(ts)] === Demo learning evidence audit start modes=${ENGINE_MODES} lookback=${LOOKBACK_HOURS} ===" >> "$LOG"
audit_rc=0
(
    cd "$BASE"
    export PYTHONDONTWRITEBYTECODE=1
    "$PYBIN" "${AUDIT_ARGS[@]}"
) >> "$LOG" 2>&1 || audit_rc=$?
if [[ -f "$REPORT_OUT" ]]; then
    cp "$REPORT_OUT" "$REPORT_LATEST"
fi
if [[ -f "$JSON_OUT" ]]; then
    cp "$JSON_OUT" "$JSON_LATEST"
fi

STATUS_JSON=$(JSON_OUT="$JSON_OUT" REPORT_OUT="$REPORT_OUT" AUDIT_RC="$audit_rc" ENGINE_MODES="$ENGINE_MODES" "$PYBIN" - <<'PY' 2>>"$LOG" || true
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


payload, digest, error = load_json(os.environ["JSON_OUT"])
classification = payload.get("classification") or {}
answers = classification.get("answers") or {}
counts = classification.get("key_counts") or {}
order_scorecard = payload.get("order_stall_scorecard") or {}
order_classification = order_scorecard.get("classification") or {}
preflight = payload.get("cost_gate_learning_preflight") or {}
status = {
    "ts_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "check": "demo_learning_evidence_audit",
    "audit_rc": int(os.environ["AUDIT_RC"]),
    "engine_modes": os.environ["ENGINE_MODES"],
    "artifact_path": os.environ["JSON_OUT"],
    "report_path": os.environ["REPORT_OUT"],
    "artifact_sha256": digest,
    "artifact_error": error,
    "schema_version": payload.get("schema_version"),
    "classification_status": classification.get("status"),
    "classification_reason": classification.get("reason"),
    "next_action": classification.get("next_action"),
    "cost_gate_rejects_recorded_in_pg": answers.get("cost_gate_rejects_recorded_in_pg"),
    "learning_lane_ledger_rows_present": answers.get("learning_lane_ledger_rows_present"),
    "blocked_outcome_review_candidate_present": answers.get("blocked_outcome_review_candidate_present"),
    "order_flow_silent_drop_risk": answers.get("order_flow_silent_drop_risk"),
    "demo_observation_only_contexts_active": answers.get("demo_observation_only_contexts_active"),
    "risk_verdicts": counts.get("risk_verdicts"),
    "orders": counts.get("orders"),
    "fills": counts.get("fills"),
    "learning_ledger_rows": counts.get("learning_ledger_rows"),
    "order_stall_status": order_classification.get("status"),
    "cost_gate_learning_preflight_status": preflight.get("status"),
    "boundary": "demo_learning_evidence_readonly_pg_artifact_source_proc_no_order_no_cost_gate_relaxation",
}
print(json.dumps(status, ensure_ascii=False, sort_keys=True))
PY
)
if [[ -n "$STATUS_JSON" ]]; then
    echo "$STATUS_JSON" >> "$STATUS_LOG"
fi

echo "[$(ts)] === Demo learning evidence audit end rc=${audit_rc} ===" >> "$LOG"

# fail-soft：status/log/latest artifacts 會記錄 rc。PG/env/source evidence
# 暫時不可用時，cron 不應改 runtime state，也不應反覆觸發服務抖動。
exit 0
