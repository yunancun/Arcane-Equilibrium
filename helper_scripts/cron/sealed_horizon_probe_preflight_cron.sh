#!/usr/bin/env bash
# sealed_horizon_probe_preflight_cron.sh - artifact-only sealed horizon preflight refresh.
#
# Suggested Linux cron:
#   39 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/sealed_horizon_probe_preflight_cron.sh
#
# Hard boundary:
#   Artifact-only refresh. Writes are limited to local preflight JSON/Markdown,
#   status log, heartbeat, and lock files under OPENCLAW_DATA_DIR. No PG,
#   Bybit, order, auth, risk, runtime, config, Cost Gate lowering, probe
#   authority, order authority, or promotion proof.
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LANE_DIR="${DATA}/cost_gate_learning_lane"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/sealed_horizon_probe_preflight_cron.log"
STATUS_LOG="${LOG_DIR}/sealed_horizon_probe_preflight.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/sealed_horizon_probe_preflight_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
STALE_LOCK_MIN="${OPENCLAW_SEALED_HORIZON_PREFLIGHT_STALE_LOCK_MIN:-20}"

SEALED_EVIDENCE_JSON="${OPENCLAW_SEALED_HORIZON_LEARNING_EVIDENCE_JSON:-$LANE_DIR/sealed_horizon_learning_evidence_latest.json}"
DECISION_PACKET_JSON="${OPENCLAW_SEALED_HORIZON_DECISION_PACKET_JSON:-$LANE_DIR/profit_learning_decision_packet_latest.json}"
DECISION_PACKET_SEARCH_ROOT="${OPENCLAW_SEALED_HORIZON_DECISION_PACKET_SEARCH_ROOT:-$DATA}"
ACTIVATION_PREFLIGHT_JSON="${OPENCLAW_SEALED_HORIZON_ACTIVATION_PREFLIGHT_JSON:-$LANE_DIR/activation_preflight_latest.json}"
STACK_HEALTH_JSON="${OPENCLAW_SEALED_HORIZON_STACK_HEALTH_JSON:-$DATA/demo_learning_stack_healthcheck/demo_learning_stack_healthcheck_latest.json}"
OPERATOR_REVIEW_JSON="${OPENCLAW_SEALED_HORIZON_OPERATOR_REVIEW_JSON:-$LANE_DIR/sealed_horizon_operator_review_latest.json}"
MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_SEALED_HORIZON_PREFLIGHT_MAX_ARTIFACT_AGE_HOURS:-24}"

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

validate_int "OPENCLAW_SEALED_HORIZON_PREFLIGHT_STALE_LOCK_MIN" "$STALE_LOCK_MIN"
validate_int "OPENCLAW_SEALED_HORIZON_PREFLIGHT_MAX_ARTIFACT_AGE_HOURS" "$MAX_ARTIFACT_AGE_HOURS"
if (( MAX_ARTIFACT_AGE_HOURS < 1 || MAX_ARTIFACT_AGE_HOURS > 336 )); then
    echo "[$(ts)] FATAL: OPENCLAW_SEALED_HORIZON_PREFLIGHT_MAX_ARTIFACT_AGE_HOURS must be in [1, 336]: ${MAX_ARTIFACT_AGE_HOURS}" | tee -a "$LOG" >&2
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

touch "$HEARTBEAT_DIR/sealed_horizon_probe_preflight.last_fire" 2>/dev/null || true

if [[ -d "$LOCK_DIR" ]] && [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +"$STALE_LOCK_MIN" 2>/dev/null)" ]]; then
    echo "[$(ts)] WARN: stale lock (>${STALE_LOCK_MIN}min) cleared: $LOCK_DIR" >> "$LOG"
    rmdir "$LOCK_DIR" 2>/dev/null || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: sealed horizon preflight already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

export OPENCLAW_BASE_DIR="$BASE"
export OPENCLAW_DATA_DIR="$DATA"

STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
DATED_JSON="${LANE_DIR}/sealed_horizon_probe_preflight_${STAMP}.json"
DATED_MD="${LANE_DIR}/sealed_horizon_probe_preflight_${STAMP}.md"
LATEST_JSON="${LANE_DIR}/sealed_horizon_probe_preflight_latest.json"
LATEST_MD="${LANE_DIR}/sealed_horizon_probe_preflight_latest.md"
STATUS_OVERRIDE=""
preflight_rc=0

write_status() {
    local status_override="$1"
    STATUS_JSON=$(STATUS_OVERRIDE="$status_override" PREFLIGHT_RC="$preflight_rc" PREFLIGHT_JSON="$DATED_JSON" PREFLIGHT_MD="$DATED_MD" LATEST_JSON="$LATEST_JSON" LATEST_MD="$LATEST_MD" SEALED_EVIDENCE_JSON="$SEALED_EVIDENCE_JSON" DECISION_PACKET_JSON="$DECISION_PACKET_JSON" DECISION_PACKET_SEARCH_ROOT="$DECISION_PACKET_SEARCH_ROOT" ACTIVATION_PREFLIGHT_JSON="$ACTIVATION_PREFLIGHT_JSON" STACK_HEALTH_JSON="$STACK_HEALTH_JSON" OPERATOR_REVIEW_JSON="$OPERATOR_REVIEW_JSON" MAX_ARTIFACT_AGE_HOURS="$MAX_ARTIFACT_AGE_HOURS" "$PYBIN" - <<'PY' 2>>"$LOG" || true
import datetime
import hashlib
import json
import os
from pathlib import Path


def load(path_text):
    path = Path(path_text)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return payload if isinstance(payload, dict) else {}, digest, None
    except FileNotFoundError:
        return {}, None, "missing"
    except Exception as exc:  # noqa: BLE001 - cron status must survive malformed artifacts.
        return {}, None, f"{type(exc).__name__}:{exc}"


payload, sha256, error = load(os.environ["PREFLIGHT_JSON"])
answers = payload.get("answers") if isinstance(payload.get("answers"), dict) else {}
artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
decision_artifact = artifacts.get("decision_packet") if isinstance(artifacts.get("decision_packet"), dict) else {}
status_override = os.environ["STATUS_OVERRIDE"]
status = payload.get("status") or status_override or ("ERROR" if int(os.environ["PREFLIGHT_RC"]) != 0 else "MISSING_OUTPUT")
row = {
    "schema_version": "sealed_horizon_probe_preflight_refresh_status_v1",
    "ts_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "check": "sealed_horizon_probe_preflight",
    "rc": int(os.environ["PREFLIGHT_RC"]),
    "status": status,
    "side_cell_key": payload.get("side_cell_key"),
    "outcome_horizon_minutes": payload.get("outcome_horizon_minutes"),
    "blocking_gate_count": payload.get("blocking_gate_count"),
    "blocking_gates": payload.get("blocking_gates") or [],
    "decision_packet_aligned": answers.get("decision_packet_aligned"),
    "operator_review_recorded": answers.get("operator_review_recorded"),
    "production_learning_lane_accumulating": answers.get("production_learning_lane_accumulating"),
    "ready_for_operator_bounded_demo_probe_authorization": answers.get("ready_for_operator_bounded_demo_probe_authorization"),
    "global_cost_gate_lowering_recommended": answers.get("global_cost_gate_lowering_recommended", False),
    "main_cost_gate_adjustment": answers.get("main_cost_gate_adjustment", "NONE"),
    "probe_authority_granted": answers.get("probe_authority_granted", False),
    "order_authority_granted": answers.get("order_authority_granted", False),
    "promotion_evidence": answers.get("promotion_evidence", False),
    "selected_decision_packet_path": decision_artifact.get("path"),
    "preflight_artifact_path": os.environ["PREFLIGHT_JSON"],
    "preflight_markdown_path": os.environ["PREFLIGHT_MD"],
    "preflight_latest_path": os.environ["LATEST_JSON"],
    "preflight_latest_markdown_path": os.environ["LATEST_MD"],
    "preflight_sha256": sha256,
    "preflight_error": error,
    "sealed_horizon_learning_evidence_path": os.environ["SEALED_EVIDENCE_JSON"],
    "decision_packet_path": os.environ["DECISION_PACKET_JSON"],
    "decision_packet_search_root": os.environ["DECISION_PACKET_SEARCH_ROOT"],
    "activation_preflight_path": os.environ["ACTIVATION_PREFLIGHT_JSON"],
    "stack_health_path": os.environ["STACK_HEALTH_JSON"],
    "operator_review_path": os.environ["OPERATOR_REVIEW_JSON"],
    "max_artifact_age_hours": int(os.environ["MAX_ARTIFACT_AGE_HOURS"]),
    "boundary": "artifact_only_no_pg_bybit_order_auth_risk_runtime_cost_gate_or_probe_authority",
}
print(json.dumps(row, ensure_ascii=False, sort_keys=True))
PY
)
    if [[ -n "$STATUS_JSON" ]]; then
        echo "$STATUS_JSON" >> "$STATUS_LOG"
    fi
}

if [[ ! -d "$BASE/helper_scripts/research/cost_gate_learning_lane" ]]; then
    echo "[$(ts)] ERROR: cost_gate_learning_lane package not found under BASE=$BASE" >> "$LOG"
    preflight_rc=2
    write_status "PREFLIGHT_PACKAGE_MISSING"
    exit 0
fi

if [[ ! -f "$SEALED_EVIDENCE_JSON" ]]; then
    echo "[$(ts)] SKIP: sealed horizon learning evidence missing: $SEALED_EVIDENCE_JSON" >> "$LOG"
    preflight_rc=0
    write_status "SEALED_HORIZON_EVIDENCE_MISSING"
    exit 0
fi

PREFLIGHT_ARGS=(
    -m cost_gate_learning_lane.sealed_horizon_probe_preflight
    --sealed-horizon-learning-evidence-json "$SEALED_EVIDENCE_JSON"
    --max-artifact-age-hours "$MAX_ARTIFACT_AGE_HOURS"
    --json-output "$DATED_JSON"
    --output "$DATED_MD"
)

if [[ -f "$DECISION_PACKET_JSON" ]]; then
    PREFLIGHT_ARGS+=(--decision-packet-json "$DECISION_PACKET_JSON")
fi
if [[ -e "$DECISION_PACKET_SEARCH_ROOT" ]]; then
    PREFLIGHT_ARGS+=(--decision-packet-search-root "$DECISION_PACKET_SEARCH_ROOT")
else
    echo "[$(ts)] WARN: decision packet search root missing: $DECISION_PACKET_SEARCH_ROOT" >> "$LOG"
fi
if [[ -f "$ACTIVATION_PREFLIGHT_JSON" ]]; then
    PREFLIGHT_ARGS+=(--activation-preflight-json "$ACTIVATION_PREFLIGHT_JSON")
fi
if [[ -f "$STACK_HEALTH_JSON" ]]; then
    PREFLIGHT_ARGS+=(--stack-health-json "$STACK_HEALTH_JSON")
fi
if [[ -f "$OPERATOR_REVIEW_JSON" ]]; then
    PREFLIGHT_ARGS+=(--operator-review-json "$OPERATOR_REVIEW_JSON")
fi

echo "[$(ts)] === sealed horizon probe preflight refresh start evidence=${SEALED_EVIDENCE_JSON} ===" >> "$LOG"
(
    cd "$BASE/helper_scripts/research"
    export PYTHONDONTWRITEBYTECODE=1
    "$PYBIN" "${PREFLIGHT_ARGS[@]}"
) >> "$LOG" 2>&1 || preflight_rc=$?

if [[ "$preflight_rc" == "0" && -f "$DATED_JSON" ]]; then
    cp "$DATED_JSON" "$LATEST_JSON"
    if [[ -f "$DATED_MD" ]]; then
        cp "$DATED_MD" "$LATEST_MD"
    fi
fi

write_status ""

echo "[$(ts)] === sealed horizon probe preflight refresh end rc=${preflight_rc} latest=${LATEST_JSON} ===" >> "$LOG"

# fail-soft: rc/status are recorded; no runtime mutation, order authority, or
# Cost Gate relaxation is implied by this refresh wrapper.
exit 0
