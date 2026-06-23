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
#   outcome rows, review/data-flow/decision-packet artifacts, status log,
#   heartbeat, and lock files under OPENCLAW_DATA_DIR. No order, auth, risk,
#   strategy flag, engine, or runtime mutation.
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LANE_DIR="${DATA}/cost_gate_learning_lane"
COUNTERFACTUAL_DIR="${DATA}/cost_gate_counterfactual"
DATA_FLOW_DIR="${DATA}/demo_data_flow_monitor"
ORDER_TOUCHABILITY_DIR="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_AUDIT_DIR:-$DATA/demo_order_to_fill_gap}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/cost_gate_learning_lane_cron.log"
STATUS_LOG="${LOG_DIR}/cost_gate_learning_lane.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/cost_gate_learning_lane_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
LEDGER="${OPENCLAW_COST_GATE_LEARNING_LEDGER:-$LANE_DIR/probe_ledger.jsonl}"
SCORECARD_JSON="${OPENCLAW_COST_GATE_SCORECARD_JSON:-$DATA/cost_gate_counterfactual/cost_gate_reject_counterfactual_latest.json}"
SCORECARD_MD="${OPENCLAW_COST_GATE_SCORECARD_MD:-$DATA/cost_gate_counterfactual/cost_gate_reject_counterfactual_latest.md}"
PLAN_JSON="${OPENCLAW_COST_GATE_LEARNING_PLAN_JSON:-$LANE_DIR/demo_learning_lane_plan_latest.json}"
DATA_FLOW_JSON="${OPENCLAW_COST_GATE_DATA_FLOW_MONITOR_JSON:-$DATA_FLOW_DIR/demo_data_flow_monitor_latest.json}"
DATA_FLOW_MD="${OPENCLAW_COST_GATE_DATA_FLOW_MONITOR_MD:-$DATA_FLOW_DIR/demo_data_flow_monitor_latest.md}"
DECISION_PACKET_JSON="${OPENCLAW_COST_GATE_PROFIT_LEARNING_DECISION_PACKET_JSON:-$LANE_DIR/profit_learning_decision_packet_latest.json}"
DECISION_PACKET_MD="${OPENCLAW_COST_GATE_PROFIT_LEARNING_DECISION_PACKET_MD:-$LANE_DIR/profit_learning_decision_packet_latest.md}"
FALSE_NEGATIVE_CANDIDATE_PACKET_JSON="${OPENCLAW_COST_GATE_FALSE_NEGATIVE_CANDIDATE_PACKET_JSON:-$LANE_DIR/false_negative_candidate_packet_latest.json}"
FALSE_NEGATIVE_CANDIDATE_PACKET_MD="${OPENCLAW_COST_GATE_FALSE_NEGATIVE_CANDIDATE_PACKET_MD:-$LANE_DIR/false_negative_candidate_packet_latest.md}"
FALSE_NEGATIVE_OPERATOR_REVIEW_JSON="${OPENCLAW_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW_JSON:-$LANE_DIR/false_negative_operator_review_latest.json}"
FALSE_NEGATIVE_OPERATOR_REVIEW_MD="${OPENCLAW_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW_MD:-$LANE_DIR/false_negative_operator_review_latest.md}"
ACTIVATION_PREFLIGHT_JSON="${OPENCLAW_COST_GATE_ACTIVATION_PREFLIGHT_JSON:-$LANE_DIR/activation_preflight_latest.json}"
PIPELINE_SNAPSHOT_JSON="${OPENCLAW_COST_GATE_LEARNING_PIPELINE_SNAPSHOT_JSON:-$DATA/pipeline_snapshot.json}"
SEALED_LEARNING_EVIDENCE_JSON="${OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_JSON:-$LANE_DIR/sealed_horizon_learning_evidence_latest.json}"
SEALED_PREFLIGHT_JSON="${OPENCLAW_COST_GATE_BOUNDED_PROBE_PREFLIGHT_JSON:-$LANE_DIR/sealed_horizon_probe_preflight_latest.json}"
BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_JSON="${OPENCLAW_COST_GATE_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_JSON:-$LANE_DIR/bounded_probe_authority_patch_readiness_latest.json}"
BOUNDED_PROBE_OPERATOR_AUTHORIZATION_JSON="${OPENCLAW_COST_GATE_BOUNDED_PROBE_OPERATOR_AUTHORIZATION_JSON:-$LANE_DIR/bounded_probe_operator_authorization_latest.json}"
BOUNDED_PROBE_OPERATOR_AUTHORIZATION_MD="${OPENCLAW_COST_GATE_BOUNDED_PROBE_OPERATOR_AUTHORIZATION_MD:-$LANE_DIR/bounded_probe_operator_authorization_latest.md}"
ORDER_TOUCHABILITY_JSON="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_AUDIT_JSON:-$ORDER_TOUCHABILITY_DIR/demo_order_to_fill_gap_latest.json}"
ORDER_TOUCHABILITY_MD="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_AUDIT_MD:-$ORDER_TOUCHABILITY_DIR/demo_order_to_fill_gap_latest.md}"

REFRESH_SCORECARD="${OPENCLAW_COST_GATE_LEARNING_REFRESH_SCORECARD:-1}"
REFRESH_DATA_FLOW_MONITOR="${OPENCLAW_COST_GATE_REFRESH_DATA_FLOW_MONITOR:-1}"
REFRESH_ORDER_TOUCHABILITY_AUDIT="${OPENCLAW_COST_GATE_REFRESH_ORDER_TOUCHABILITY_AUDIT:-1}"
REFRESH_DECISION_PACKET="${OPENCLAW_COST_GATE_REFRESH_DECISION_PACKET:-1}"
REFRESH_FALSE_NEGATIVE_CANDIDATE_PACKET="${OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_CANDIDATE_PACKET:-1}"
REFRESH_FALSE_NEGATIVE_OPERATOR_REVIEW="${OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_OPERATOR_REVIEW:-1}"
DATA_FLOW_WINDOW_HOURS="${OPENCLAW_COST_GATE_DATA_FLOW_WINDOW_HOURS:-1,4,24}"
DATA_FLOW_TOP_LIMIT="${OPENCLAW_COST_GATE_DATA_FLOW_TOP_LIMIT:-10}"
ORDER_TOUCHABILITY_ENGINE_MODES="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_ENGINE_MODES:-demo,live_demo}"
ORDER_TOUCHABILITY_LOOKBACK_HOURS="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_LOOKBACK_HOURS:-48}"
ORDER_TOUCHABILITY_TOUCH_WINDOW_MINUTES="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_TOUCH_WINDOW_MINUTES:-1440}"
ORDER_TOUCHABILITY_PLACEMENT_WINDOW_SECONDS="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_PLACEMENT_WINDOW_SECONDS:-30}"
ORDER_TOUCHABILITY_TOP_LIMIT="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_TOP_LIMIT:-50}"
ORDER_TOUCHABILITY_DEEP_GAP_BPS="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_DEEP_GAP_BPS:-500.0}"
SCORECARD_LOOKBACK_HOURS="${OPENCLAW_COST_GATE_SCORECARD_LOOKBACK_HOURS:-168}"
SCORECARD_LIMIT="${OPENCLAW_COST_GATE_SCORECARD_LIMIT:-50000}"
REFRESH_PLAN="${OPENCLAW_COST_GATE_LEARNING_REFRESH_PLAN:-1}"
PREINSTALL_REFRESH_ONLY="${OPENCLAW_COST_GATE_LEARNING_PREINSTALL_REFRESH_ONLY:-0}"
PLAN_MAX_SCORECARD_AGE_HOURS="${OPENCLAW_COST_GATE_PLAN_MAX_SCORECARD_AGE_HOURS:-24}"
PLAN_MIN_CANDIDATE_SAMPLE="${OPENCLAW_COST_GATE_PLAN_MIN_CANDIDATE_SAMPLE:-100}"
REFRESH_SEALED_HORIZON_LEARNING_EVIDENCE="${OPENCLAW_COST_GATE_REFRESH_SEALED_HORIZON_LEARNING_EVIDENCE:-1}"
APPEND_SEALED_HORIZON_LEARNING_EVIDENCE="${OPENCLAW_COST_GATE_APPEND_SEALED_HORIZON_LEARNING_EVIDENCE:-1}"
SEALED_LEARNING_EVIDENCE_LOOKBACK_HOURS="${OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_LOOKBACK_HOURS:-72}"
SEALED_LEARNING_EVIDENCE_LIMIT="${OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_LIMIT:-5000}"
SEALED_LEARNING_EVIDENCE_MATURITY_BUFFER_MINUTES="${OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_MATURITY_BUFFER_MINUTES:-0}"
SEALED_LEARNING_EVIDENCE_MIN_REVIEW_OUTCOMES="${OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_MIN_REVIEW_OUTCOMES_PER_SIDE_CELL:-100}"
SEALED_LEARNING_EVIDENCE_MIN_REVIEW_AVG_NET_BPS="${OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_MIN_REVIEW_AVG_NET_BPS:-0.0}"
SEALED_LEARNING_EVIDENCE_MIN_REVIEW_NET_POSITIVE_PCT="${OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_MIN_REVIEW_NET_POSITIVE_PCT:-60.0}"
PG_TIMEFRAME="${OPENCLAW_COST_GATE_LEARNING_PG_TIMEFRAME:-1m}"
OUTCOME_HORIZON_MINUTES="${OPENCLAW_COST_GATE_LEARNING_OUTCOME_HORIZON_MINUTES:-60}"
SCORECARD_HORIZON_MINUTES_LIST="${OPENCLAW_COST_GATE_SCORECARD_HORIZON_MINUTES_LIST:-15,30,60,120,240}"
OUTCOME_COST_BPS="${OPENCLAW_COST_GATE_LEARNING_OUTCOME_COST_BPS:-4.0}"
MAX_ENTRY_DELAY_MS="${OPENCLAW_COST_GATE_LEARNING_MAX_ENTRY_DELAY_MS:-300000}"
PG_STATEMENT_TIMEOUT_MS="${OPENCLAW_COST_GATE_LEARNING_PG_STATEMENT_TIMEOUT_MS:-180000}"
HISTORICAL_MAX_SCORECARD_AGE_HOURS="${OPENCLAW_COST_GATE_HISTORICAL_MAX_SCORECARD_AGE_HOURS:-36}"
HISTORICAL_MIN_CANDIDATE_SAMPLE="${OPENCLAW_COST_GATE_HISTORICAL_MIN_CANDIDATE_SAMPLE:-100}"
MATERIALIZE_REJECTS="${OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS:-1}"
APPEND_MATERIALIZED_REJECTS="${OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS:-1}"
MATERIALIZER_LOOKBACK_HOURS="${OPENCLAW_COST_GATE_MATERIALIZER_LOOKBACK_HOURS:-4}"
MATERIALIZER_LIMIT="${OPENCLAW_COST_GATE_MATERIALIZER_LIMIT:-10000}"
APPEND_OUTCOMES="${OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES:-1}"
RECORD_PROBE_OUTCOMES="${OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES:-0}"
REFRESH_BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT:-1}"
REFRESH_BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN:-1}"
REFRESH_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS:-1}"
REFRESH_BOUNDED_PROBE_OPERATOR_AUTHORIZATION="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_OPERATOR_AUTHORIZATION:-1}"
REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT:-1}"
REFRESH_BOUNDED_PROBE_RESULT_REVIEW="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_RESULT_REVIEW:-1}"
REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW:-1}"
REVIEW_MIN_OUTCOMES="${OPENCLAW_COST_GATE_REVIEW_MIN_OUTCOMES_PER_SIDE_CELL:-3}"
REVIEW_MIN_AVG_NET_BPS="${OPENCLAW_COST_GATE_REVIEW_MIN_AVG_NET_BPS:-0.0}"
REVIEW_MIN_NET_POSITIVE_PCT="${OPENCLAW_COST_GATE_REVIEW_MIN_NET_POSITIVE_PCT:-60.0}"
TOUCHABILITY_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_TOUCHABILITY_MAX_ARTIFACT_AGE_HOURS:-24}"
TOUCHABILITY_MAX_INITIAL_PASSIVE_GAP_BPS="${OPENCLAW_COST_GATE_TOUCHABILITY_MAX_INITIAL_PASSIVE_GAP_BPS:-75.0}"
TOUCHABILITY_MAX_DEEP_NO_TOUCH_GAP_BPS="${OPENCLAW_COST_GATE_TOUCHABILITY_MAX_DEEP_NO_TOUCH_GAP_BPS:-500.0}"
PLACEMENT_REPAIR_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_PLACEMENT_REPAIR_MAX_ARTIFACT_AGE_HOURS:-24}"
PLACEMENT_REPAIR_MAX_FRESH_BBO_AGE_MS="${OPENCLAW_COST_GATE_PLACEMENT_REPAIR_MAX_FRESH_BBO_AGE_MS:-1000}"
AUTHORITY_PATCH_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_AUTHORITY_PATCH_MAX_ARTIFACT_AGE_HOURS:-24}"
OPERATOR_AUTHORIZATION_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_OPERATOR_AUTHORIZATION_MAX_ARTIFACT_AGE_HOURS:-24}"
FALSE_NEGATIVE_OPERATOR_REVIEW_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW_MAX_ARTIFACT_AGE_HOURS:-24}"
SHADOW_PLACEMENT_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_SHADOW_PLACEMENT_MAX_ARTIFACT_AGE_HOURS:-24}"
STALE_LOCK_MIN="${OPENCLAW_COST_GATE_LEARNING_STALE_LOCK_MIN:-30}"

mkdir -p "$LANE_DIR" "$COUNTERFACTUAL_DIR" "$DATA_FLOW_DIR" "$ORDER_TOUCHABILITY_DIR" "$LOG_DIR" "$LOCK_ROOT" "$HEARTBEAT_DIR"

ts() { date -u '+%Y-%m-%d %H:%M:%S'; }

latest_matching_path() {
    local candidate
    local latest=""
    for candidate in "$@"; do
        if [[ -f "$candidate" ]]; then
            latest="$candidate"
        fi
    done
    printf '%s' "$latest"
}

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
validate_bool01 "OPENCLAW_COST_GATE_LEARNING_REFRESH_SCORECARD" "$REFRESH_SCORECARD"
validate_bool01 "OPENCLAW_COST_GATE_REFRESH_DATA_FLOW_MONITOR" "$REFRESH_DATA_FLOW_MONITOR"
validate_bool01 "OPENCLAW_COST_GATE_REFRESH_ORDER_TOUCHABILITY_AUDIT" "$REFRESH_ORDER_TOUCHABILITY_AUDIT"
validate_bool01 "OPENCLAW_COST_GATE_REFRESH_DECISION_PACKET" "$REFRESH_DECISION_PACKET"
validate_bool01 "OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_CANDIDATE_PACKET" "$REFRESH_FALSE_NEGATIVE_CANDIDATE_PACKET"
validate_bool01 "OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_OPERATOR_REVIEW" "$REFRESH_FALSE_NEGATIVE_OPERATOR_REVIEW"
if [[ ! "$DATA_FLOW_WINDOW_HOURS" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
    echo "[$(ts)] FATAL: OPENCLAW_COST_GATE_DATA_FLOW_WINDOW_HOURS must be comma-separated integers: ${DATA_FLOW_WINDOW_HOURS}" | tee -a "$LOG" >&2
    exit 2
fi
if [[ ! "$ORDER_TOUCHABILITY_ENGINE_MODES" =~ ^[[:alnum:]_]+(,[[:alnum:]_]+)*$ ]]; then
    echo "[$(ts)] FATAL: OPENCLAW_DEMO_ORDER_TO_FILL_GAP_ENGINE_MODES must be comma-separated engine modes: ${ORDER_TOUCHABILITY_ENGINE_MODES}" | tee -a "$LOG" >&2
    exit 2
fi
validate_int "OPENCLAW_COST_GATE_DATA_FLOW_TOP_LIMIT" "$DATA_FLOW_TOP_LIMIT"
validate_int "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_LOOKBACK_HOURS" "$ORDER_TOUCHABILITY_LOOKBACK_HOURS"
validate_int "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_TOUCH_WINDOW_MINUTES" "$ORDER_TOUCHABILITY_TOUCH_WINDOW_MINUTES"
validate_int "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_PLACEMENT_WINDOW_SECONDS" "$ORDER_TOUCHABILITY_PLACEMENT_WINDOW_SECONDS"
validate_int "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_TOP_LIMIT" "$ORDER_TOUCHABILITY_TOP_LIMIT"
validate_decimal "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_DEEP_GAP_BPS" "$ORDER_TOUCHABILITY_DEEP_GAP_BPS"
validate_int "OPENCLAW_COST_GATE_SCORECARD_LOOKBACK_HOURS" "$SCORECARD_LOOKBACK_HOURS"
validate_int "OPENCLAW_COST_GATE_SCORECARD_LIMIT" "$SCORECARD_LIMIT"
validate_bool01 "OPENCLAW_COST_GATE_LEARNING_REFRESH_PLAN" "$REFRESH_PLAN"
validate_bool01 "OPENCLAW_COST_GATE_LEARNING_PREINSTALL_REFRESH_ONLY" "$PREINSTALL_REFRESH_ONLY"
validate_int "OPENCLAW_COST_GATE_PLAN_MAX_SCORECARD_AGE_HOURS" "$PLAN_MAX_SCORECARD_AGE_HOURS"
validate_int "OPENCLAW_COST_GATE_PLAN_MIN_CANDIDATE_SAMPLE" "$PLAN_MIN_CANDIDATE_SAMPLE"
validate_bool01 "OPENCLAW_COST_GATE_REFRESH_SEALED_HORIZON_LEARNING_EVIDENCE" "$REFRESH_SEALED_HORIZON_LEARNING_EVIDENCE"
validate_bool01 "OPENCLAW_COST_GATE_APPEND_SEALED_HORIZON_LEARNING_EVIDENCE" "$APPEND_SEALED_HORIZON_LEARNING_EVIDENCE"
validate_int "OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_LOOKBACK_HOURS" "$SEALED_LEARNING_EVIDENCE_LOOKBACK_HOURS"
validate_int "OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_LIMIT" "$SEALED_LEARNING_EVIDENCE_LIMIT"
validate_int "OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_MATURITY_BUFFER_MINUTES" "$SEALED_LEARNING_EVIDENCE_MATURITY_BUFFER_MINUTES"
validate_int "OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_MIN_REVIEW_OUTCOMES_PER_SIDE_CELL" "$SEALED_LEARNING_EVIDENCE_MIN_REVIEW_OUTCOMES"
validate_decimal "OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_MIN_REVIEW_AVG_NET_BPS" "$SEALED_LEARNING_EVIDENCE_MIN_REVIEW_AVG_NET_BPS"
validate_decimal "OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_MIN_REVIEW_NET_POSITIVE_PCT" "$SEALED_LEARNING_EVIDENCE_MIN_REVIEW_NET_POSITIVE_PCT"
validate_int "OPENCLAW_COST_GATE_LEARNING_OUTCOME_HORIZON_MINUTES" "$OUTCOME_HORIZON_MINUTES"
if [[ ! "$SCORECARD_HORIZON_MINUTES_LIST" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
    echo "[$(ts)] FATAL: OPENCLAW_COST_GATE_SCORECARD_HORIZON_MINUTES_LIST must be comma-separated integers: ${SCORECARD_HORIZON_MINUTES_LIST}" | tee -a "$LOG" >&2
    exit 2
fi
validate_decimal "OPENCLAW_COST_GATE_LEARNING_OUTCOME_COST_BPS" "$OUTCOME_COST_BPS"
validate_int "OPENCLAW_COST_GATE_LEARNING_MAX_ENTRY_DELAY_MS" "$MAX_ENTRY_DELAY_MS"
validate_int "OPENCLAW_COST_GATE_LEARNING_PG_STATEMENT_TIMEOUT_MS" "$PG_STATEMENT_TIMEOUT_MS"
validate_int "OPENCLAW_COST_GATE_HISTORICAL_MAX_SCORECARD_AGE_HOURS" "$HISTORICAL_MAX_SCORECARD_AGE_HOURS"
validate_int "OPENCLAW_COST_GATE_HISTORICAL_MIN_CANDIDATE_SAMPLE" "$HISTORICAL_MIN_CANDIDATE_SAMPLE"
validate_bool01 "OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS" "$MATERIALIZE_REJECTS"
validate_bool01 "OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS" "$APPEND_MATERIALIZED_REJECTS"
validate_int "OPENCLAW_COST_GATE_MATERIALIZER_LOOKBACK_HOURS" "$MATERIALIZER_LOOKBACK_HOURS"
validate_int "OPENCLAW_COST_GATE_MATERIALIZER_LIMIT" "$MATERIALIZER_LIMIT"
validate_bool01 "OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES" "$APPEND_OUTCOMES"
validate_bool01 "OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES" "$RECORD_PROBE_OUTCOMES"
validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT" "$REFRESH_BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT"
validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN" "$REFRESH_BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN"
validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS" "$REFRESH_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS"
validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_OPERATOR_AUTHORIZATION" "$REFRESH_BOUNDED_PROBE_OPERATOR_AUTHORIZATION"
validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT" "$REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT"
validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_RESULT_REVIEW" "$REFRESH_BOUNDED_PROBE_RESULT_REVIEW"
validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW" "$REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW"
validate_int "OPENCLAW_COST_GATE_REVIEW_MIN_OUTCOMES_PER_SIDE_CELL" "$REVIEW_MIN_OUTCOMES"
validate_decimal "OPENCLAW_COST_GATE_REVIEW_MIN_AVG_NET_BPS" "$REVIEW_MIN_AVG_NET_BPS"
validate_decimal "OPENCLAW_COST_GATE_REVIEW_MIN_NET_POSITIVE_PCT" "$REVIEW_MIN_NET_POSITIVE_PCT"
validate_int "OPENCLAW_COST_GATE_TOUCHABILITY_MAX_ARTIFACT_AGE_HOURS" "$TOUCHABILITY_MAX_ARTIFACT_AGE_HOURS"
validate_decimal "OPENCLAW_COST_GATE_TOUCHABILITY_MAX_INITIAL_PASSIVE_GAP_BPS" "$TOUCHABILITY_MAX_INITIAL_PASSIVE_GAP_BPS"
validate_decimal "OPENCLAW_COST_GATE_TOUCHABILITY_MAX_DEEP_NO_TOUCH_GAP_BPS" "$TOUCHABILITY_MAX_DEEP_NO_TOUCH_GAP_BPS"
validate_int "OPENCLAW_COST_GATE_PLACEMENT_REPAIR_MAX_ARTIFACT_AGE_HOURS" "$PLACEMENT_REPAIR_MAX_ARTIFACT_AGE_HOURS"
validate_int "OPENCLAW_COST_GATE_PLACEMENT_REPAIR_MAX_FRESH_BBO_AGE_MS" "$PLACEMENT_REPAIR_MAX_FRESH_BBO_AGE_MS"
validate_int "OPENCLAW_COST_GATE_AUTHORITY_PATCH_MAX_ARTIFACT_AGE_HOURS" "$AUTHORITY_PATCH_MAX_ARTIFACT_AGE_HOURS"
validate_int "OPENCLAW_COST_GATE_OPERATOR_AUTHORIZATION_MAX_ARTIFACT_AGE_HOURS" "$OPERATOR_AUTHORIZATION_MAX_ARTIFACT_AGE_HOURS"
validate_int "OPENCLAW_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW_MAX_ARTIFACT_AGE_HOURS" "$FALSE_NEGATIVE_OPERATOR_REVIEW_MAX_ARTIFACT_AGE_HOURS"
validate_int "OPENCLAW_COST_GATE_SHADOW_PLACEMENT_MAX_ARTIFACT_AGE_HOURS" "$SHADOW_PLACEMENT_MAX_ARTIFACT_AGE_HOURS"
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

DEFAULT_HORIZON_SEALED_REPLAY_JSON="$(latest_matching_path \
    "$DATA"/cost_gate_learning_lane/horizon_specific_sealed_replay_latest.json \
    "$DATA"/profitability_refresh/*/horizon_specific_sealed_replay/horizon_specific_sealed_replay_latest.json)"
HORIZON_SEALED_REPLAY_JSON="${OPENCLAW_COST_GATE_HORIZON_SEALED_REPLAY_JSON:-$DEFAULT_HORIZON_SEALED_REPLAY_JSON}"

STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
SCORECARD_JSON_OUT="${COUNTERFACTUAL_DIR}/cost_gate_reject_counterfactual_${STAMP}.json"
SCORECARD_MD_OUT="${COUNTERFACTUAL_DIR}/cost_gate_reject_counterfactual_${STAMP}.md"
DATA_FLOW_JSON_OUT="${DATA_FLOW_DIR}/demo_data_flow_monitor_${STAMP}.json"
DATA_FLOW_MD_OUT="${DATA_FLOW_DIR}/demo_data_flow_monitor_${STAMP}.md"
ORDER_TOUCHABILITY_JSON_OUT="${ORDER_TOUCHABILITY_DIR}/demo_order_to_fill_gap_${STAMP}.json"
ORDER_TOUCHABILITY_MD_OUT="${ORDER_TOUCHABILITY_DIR}/demo_order_to_fill_gap_${STAMP}.md"
DECISION_PACKET_JSON_OUT="${LANE_DIR}/profit_learning_decision_packet_${STAMP}.json"
DECISION_PACKET_MD_OUT="${LANE_DIR}/profit_learning_decision_packet_${STAMP}.md"
REFRESH_OUT="${LANE_DIR}/outcome_refresh_${STAMP}.json"
REFRESH_LATEST="${LANE_DIR}/outcome_refresh_latest.json"
REVIEW_OUT="${LANE_DIR}/blocked_outcome_review_${STAMP}.json"
REVIEW_LATEST="${LANE_DIR}/blocked_outcome_review_latest.json"
FALSE_NEGATIVE_CANDIDATE_PACKET_OUT="${LANE_DIR}/false_negative_candidate_packet_${STAMP}.json"
FALSE_NEGATIVE_CANDIDATE_PACKET_MD_OUT="${LANE_DIR}/false_negative_candidate_packet_${STAMP}.md"
FALSE_NEGATIVE_CANDIDATE_PACKET_LATEST="$FALSE_NEGATIVE_CANDIDATE_PACKET_JSON"
FALSE_NEGATIVE_CANDIDATE_PACKET_MD_LATEST="$FALSE_NEGATIVE_CANDIDATE_PACKET_MD"
FALSE_NEGATIVE_OPERATOR_REVIEW_OUT="${LANE_DIR}/false_negative_operator_review_${STAMP}.json"
FALSE_NEGATIVE_OPERATOR_REVIEW_MD_OUT="${LANE_DIR}/false_negative_operator_review_${STAMP}.md"
FALSE_NEGATIVE_OPERATOR_REVIEW_LATEST="$FALSE_NEGATIVE_OPERATOR_REVIEW_JSON"
FALSE_NEGATIVE_OPERATOR_REVIEW_MD_LATEST="$FALSE_NEGATIVE_OPERATOR_REVIEW_MD"
SEALED_LEARNING_EVIDENCE_OUT="${LANE_DIR}/sealed_horizon_learning_evidence_${STAMP}.json"
SEALED_LEARNING_EVIDENCE_REVIEW_OUT="${LANE_DIR}/sealed_horizon_learning_evidence_review_${STAMP}.json"
SEALED_LEARNING_EVIDENCE_REVIEW_LATEST="${LANE_DIR}/sealed_horizon_learning_evidence_review_latest.json"
SEALED_LEARNING_EVIDENCE_SOURCE_ROWS_OUT="${LANE_DIR}/sealed_horizon_learning_evidence_source_rows_${STAMP}.jsonl"
SEALED_LEARNING_EVIDENCE_SOURCE_ROWS_LATEST="${LANE_DIR}/sealed_horizon_learning_evidence_source_rows_latest.jsonl"
BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT="${LANE_DIR}/bounded_probe_touchability_preflight_${STAMP}.json"
BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_MD_OUT="${LANE_DIR}/bounded_probe_touchability_preflight_${STAMP}.md"
BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_LATEST="${LANE_DIR}/bounded_probe_touchability_preflight_latest.json"
BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_MD_LATEST="${LANE_DIR}/bounded_probe_touchability_preflight_latest.md"
BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT="${LANE_DIR}/bounded_probe_placement_repair_plan_${STAMP}.json"
BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_MD_OUT="${LANE_DIR}/bounded_probe_placement_repair_plan_${STAMP}.md"
BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_LATEST="${LANE_DIR}/bounded_probe_placement_repair_plan_latest.json"
BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_MD_LATEST="${LANE_DIR}/bounded_probe_placement_repair_plan_latest.md"
BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT="${LANE_DIR}/bounded_probe_authority_patch_readiness_${STAMP}.json"
BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_MD_OUT="${LANE_DIR}/bounded_probe_authority_patch_readiness_${STAMP}.md"
BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_LATEST="$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_JSON"
BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_MD_LATEST="${LANE_DIR}/bounded_probe_authority_patch_readiness_latest.md"
BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT="${LANE_DIR}/bounded_probe_operator_authorization_${STAMP}.json"
BOUNDED_PROBE_OPERATOR_AUTHORIZATION_MD_OUT="${LANE_DIR}/bounded_probe_operator_authorization_${STAMP}.md"
BOUNDED_PROBE_OPERATOR_AUTHORIZATION_LATEST="$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_JSON"
BOUNDED_PROBE_OPERATOR_AUTHORIZATION_MD_LATEST="$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_MD"
BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT="${LANE_DIR}/bounded_probe_shadow_placement_impact_${STAMP}.json"
BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_MD_OUT="${LANE_DIR}/bounded_probe_shadow_placement_impact_${STAMP}.md"
BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_LATEST="${LANE_DIR}/bounded_probe_shadow_placement_impact_latest.json"
BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_MD_LATEST="${LANE_DIR}/bounded_probe_shadow_placement_impact_latest.md"
BOUNDED_PROBE_RESULT_REVIEW_OUT="${LANE_DIR}/bounded_probe_result_review_${STAMP}.json"
BOUNDED_PROBE_RESULT_REVIEW_MD_OUT="${LANE_DIR}/bounded_probe_result_review_${STAMP}.md"
BOUNDED_PROBE_RESULT_REVIEW_LATEST="${LANE_DIR}/bounded_probe_result_review_latest.json"
BOUNDED_PROBE_RESULT_REVIEW_MD_LATEST="${LANE_DIR}/bounded_probe_result_review_latest.md"
BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_OUT="${LANE_DIR}/bounded_probe_execution_realism_review_${STAMP}.json"
BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_MD_OUT="${LANE_DIR}/bounded_probe_execution_realism_review_${STAMP}.md"
BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_LATEST="${LANE_DIR}/bounded_probe_execution_realism_review_latest.json"
BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_MD_LATEST="${LANE_DIR}/bounded_probe_execution_realism_review_latest.md"
HISTORICAL_REVIEW_OUT="${LANE_DIR}/historical_scorecard_review_${STAMP}.json"
HISTORICAL_REVIEW_LATEST="${LANE_DIR}/historical_scorecard_review_latest.json"
MATERIALIZER_OUT="${LANE_DIR}/reject_materializer_${STAMP}.json"
MATERIALIZER_LATEST="${LANE_DIR}/reject_materializer_latest.json"
PLAN_OUT="${LANE_DIR}/demo_learning_lane_plan_${STAMP}.json"

SCORECARD_ARGS=(
    "$BASE/helper_scripts/db/audit/cost_gate_reject_counterfactual.py"
    --lookback-hours "$SCORECARD_LOOKBACK_HOURS"
    --horizon-minutes "$OUTCOME_HORIZON_MINUTES"
    --horizon-minutes-list "$SCORECARD_HORIZON_MINUTES_LIST"
    --limit "$SCORECARD_LIMIT"
    --friction-bps "$OUTCOME_COST_BPS"
    --min-probe-sample "$PLAN_MIN_CANDIDATE_SAMPLE"
    --output "$SCORECARD_MD_OUT"
    --json-output "$SCORECARD_JSON_OUT"
)

DATA_FLOW_ARGS=(
    "$BASE/helper_scripts/db/audit/demo_data_flow_monitor.py"
    --top-limit "$DATA_FLOW_TOP_LIMIT"
    --output "$DATA_FLOW_MD_OUT"
    --json-output "$DATA_FLOW_JSON_OUT"
)
IFS=',' read -r -a DATA_FLOW_WINDOWS <<< "$DATA_FLOW_WINDOW_HOURS"
for window in "${DATA_FLOW_WINDOWS[@]}"; do
    DATA_FLOW_ARGS+=(--window-hours "$window")
done

ORDER_TOUCHABILITY_ARGS=(
    "$BASE/helper_scripts/db/audit/demo_order_to_fill_gap_audit.py"
    --lookback-hours "$ORDER_TOUCHABILITY_LOOKBACK_HOURS"
    --touch-window-minutes "$ORDER_TOUCHABILITY_TOUCH_WINDOW_MINUTES"
    --placement-window-seconds "$ORDER_TOUCHABILITY_PLACEMENT_WINDOW_SECONDS"
    --top-limit "$ORDER_TOUCHABILITY_TOP_LIMIT"
    --deep-gap-bps "$ORDER_TOUCHABILITY_DEEP_GAP_BPS"
    --output "$ORDER_TOUCHABILITY_MD_OUT"
    --json-output "$ORDER_TOUCHABILITY_JSON_OUT"
)
IFS=',' read -r -a ORDER_TOUCHABILITY_ENGINE_MODE_ARRAY <<< "$ORDER_TOUCHABILITY_ENGINE_MODES"
for engine_mode in "${ORDER_TOUCHABILITY_ENGINE_MODE_ARRAY[@]}"; do
    ORDER_TOUCHABILITY_ARGS+=(--engine-mode "$engine_mode")
done

PLAN_ARGS=(
    -m cost_gate_learning_lane.policy
    --scorecard-json "$SCORECARD_JSON"
    --output "$PLAN_OUT"
    --max-scorecard-age-hours "$PLAN_MAX_SCORECARD_AGE_HOURS"
    --min-candidate-sample "$PLAN_MIN_CANDIDATE_SAMPLE"
)
if [[ -f "$HORIZON_SEALED_REPLAY_JSON" ]]; then
    PLAN_ARGS+=(--horizon-sealed-replay-json "$HORIZON_SEALED_REPLAY_JSON")
fi

HISTORICAL_REVIEW_ARGS=(
    -m cost_gate_learning_lane.historical_review
    --scorecard-json "$SCORECARD_JSON"
    --max-scorecard-age-hours "$HISTORICAL_MAX_SCORECARD_AGE_HOURS"
    --min-candidate-sample "$HISTORICAL_MIN_CANDIDATE_SAMPLE"
    --output "$HISTORICAL_REVIEW_OUT"
)

MATERIALIZER_ARGS=(
    -m cost_gate_learning_lane.reject_materializer
    --plan "$PLAN_JSON"
    --ledger "$LEDGER"
    --source-pg
    --engine-mode demo
    --engine-mode live_demo
    --lookback-hours "$MATERIALIZER_LOOKBACK_HOURS"
    --limit "$MATERIALIZER_LIMIT"
    --pg-statement-timeout-ms "$PG_STATEMENT_TIMEOUT_MS"
    --snapshot-json "$PIPELINE_SNAPSHOT_JSON"
    --output "$MATERIALIZER_OUT"
)
if [[ "$APPEND_MATERIALIZED_REJECTS" == "1" ]]; then
    MATERIALIZER_ARGS+=(--append-ledger)
fi

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

FALSE_NEGATIVE_CANDIDATE_PACKET_ARGS=(
    -m cost_gate_learning_lane.false_negative_candidate_packet
    --blocked-outcome-review-json "$REVIEW_OUT"
    --json-output "$FALSE_NEGATIVE_CANDIDATE_PACKET_OUT"
    --output "$FALSE_NEGATIVE_CANDIDATE_PACKET_MD_OUT"
)

FALSE_NEGATIVE_OPERATOR_REVIEW_ARGS=(
    -m cost_gate_learning_lane.false_negative_operator_review
    --false-negative-candidate-packet-json "$FALSE_NEGATIVE_CANDIDATE_PACKET_OUT"
    --decision defer
    --max-artifact-age-hours "$FALSE_NEGATIVE_OPERATOR_REVIEW_MAX_ARTIFACT_AGE_HOURS"
    --json-output "$FALSE_NEGATIVE_OPERATOR_REVIEW_OUT"
    --output "$FALSE_NEGATIVE_OPERATOR_REVIEW_MD_OUT"
)

SEALED_LEARNING_EVIDENCE_ARGS=(
    -m cost_gate_learning_lane.sealed_horizon_learning_evidence
    --plan "$PLAN_JSON"
    --ledger "$LEDGER"
    --source-pg
    --price-source-pg
    --engine-mode demo
    --engine-mode live_demo
    --lookback-hours "$SEALED_LEARNING_EVIDENCE_LOOKBACK_HOURS"
    --limit "$SEALED_LEARNING_EVIDENCE_LIMIT"
    --maturity-buffer-minutes "$SEALED_LEARNING_EVIDENCE_MATURITY_BUFFER_MINUTES"
    --horizon-minutes "$OUTCOME_HORIZON_MINUTES"
    --outcome-cost-bps "$OUTCOME_COST_BPS"
    --max-entry-delay-ms "$MAX_ENTRY_DELAY_MS"
    --pg-timeframe "$PG_TIMEFRAME"
    --pg-statement-timeout-ms "$PG_STATEMENT_TIMEOUT_MS"
    --min-review-outcomes-per-side-cell "$SEALED_LEARNING_EVIDENCE_MIN_REVIEW_OUTCOMES"
    --min-review-avg-net-bps "$SEALED_LEARNING_EVIDENCE_MIN_REVIEW_AVG_NET_BPS"
    --min-review-net-positive-pct "$SEALED_LEARNING_EVIDENCE_MIN_REVIEW_NET_POSITIVE_PCT"
    --output "$SEALED_LEARNING_EVIDENCE_OUT"
    --review-output "$SEALED_LEARNING_EVIDENCE_REVIEW_OUT"
    --source-rows-output "$SEALED_LEARNING_EVIDENCE_SOURCE_ROWS_OUT"
)
if [[ "$APPEND_SEALED_HORIZON_LEARNING_EVIDENCE" == "1" ]]; then
    SEALED_LEARNING_EVIDENCE_ARGS+=(--append-ledger)
fi

BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_ARGS=(
    -m cost_gate_learning_lane.bounded_probe_touchability_preflight
    --preflight-json "$SEALED_PREFLIGHT_JSON"
    --order-to-fill-gap-json "$ORDER_TOUCHABILITY_JSON"
    --max-artifact-age-hours "$TOUCHABILITY_MAX_ARTIFACT_AGE_HOURS"
    --max-initial-passive-gap-bps "$TOUCHABILITY_MAX_INITIAL_PASSIVE_GAP_BPS"
    --max-deep-no-touch-gap-bps "$TOUCHABILITY_MAX_DEEP_NO_TOUCH_GAP_BPS"
    --json-output "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT"
    --output "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_MD_OUT"
)

BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_ARGS=(
    -m cost_gate_learning_lane.bounded_probe_placement_repair_plan
    --touchability-preflight-json "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT"
    --max-artifact-age-hours "$PLACEMENT_REPAIR_MAX_ARTIFACT_AGE_HOURS"
    --max-fresh-bbo-age-ms "$PLACEMENT_REPAIR_MAX_FRESH_BBO_AGE_MS"
    --json-output "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT"
    --output "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_MD_OUT"
)

BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_ARGS=(
    -m cost_gate_learning_lane.bounded_probe_authority_patch_readiness
    --placement-repair-plan-json "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT"
    --repo-root "$BASE"
    --max-artifact-age-hours "$AUTHORITY_PATCH_MAX_ARTIFACT_AGE_HOURS"
    --json-output "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT"
    --output "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_MD_OUT"
)

BOUNDED_PROBE_OPERATOR_AUTHORIZATION_ARGS=(
    -m cost_gate_learning_lane.bounded_probe_operator_authorization_cli
    --preflight-json "$SEALED_PREFLIGHT_JSON"
    --placement-repair-plan-json "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT"
    --authority-patch-readiness-json "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT"
    --decision defer
    --max-artifact-age-hours "$OPERATOR_AUTHORIZATION_MAX_ARTIFACT_AGE_HOURS"
    --json-output "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT"
    --output "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_MD_OUT"
)

BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_ARGS=(
    -m cost_gate_learning_lane.bounded_probe_shadow_placement_impact
    --order-to-fill-gap-json "$ORDER_TOUCHABILITY_JSON"
    --placement-repair-plan-json "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT"
    --max-artifact-age-hours "$SHADOW_PLACEMENT_MAX_ARTIFACT_AGE_HOURS"
    --json-output "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT"
    --output "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_MD_OUT"
)

BOUNDED_PROBE_RESULT_REVIEW_ARGS=(
    -m cost_gate_learning_lane.bounded_probe_result_review
    --preflight-json "$SEALED_PREFLIGHT_JSON"
    --ledger "$LEDGER"
    --json-output "$BOUNDED_PROBE_RESULT_REVIEW_OUT"
    --output "$BOUNDED_PROBE_RESULT_REVIEW_MD_OUT"
)

BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_ARGS=(
    -m cost_gate_learning_lane.bounded_probe_execution_realism_review
    --result-review-json "$BOUNDED_PROBE_RESULT_REVIEW_OUT"
    --ledger "$LEDGER"
    --json-output "$BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_OUT"
    --output "$BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_MD_OUT"
)

DECISION_PACKET_ARGS=(
    -m cost_gate_learning_lane.decision_packet
    --data-flow-json "$DATA_FLOW_JSON"
    --counterfactual-json "$SCORECARD_JSON"
    --plan-json "$PLAN_JSON"
    --activation-preflight-json "$ACTIVATION_PREFLIGHT_JSON"
    --blocked-outcome-review-json "$REVIEW_LATEST"
    --sealed-horizon-learning-evidence-json "$SEALED_LEARNING_EVIDENCE_JSON"
    --output "$DECISION_PACKET_MD_OUT"
    --json-output "$DECISION_PACKET_JSON_OUT"
)

echo "[$(ts)] === Cost-gate learning lane refresh start append=${APPEND_OUTCOMES} ledger=${LEDGER} ===" >> "$LOG"
scorecard_rc=0
if [[ "$REFRESH_SCORECARD" == "1" ]]; then
    (
        cd "$BASE"
        export PYTHONPATH="$BASE${PYTHONPATH:+:$PYTHONPATH}"
        export PYTHONDONTWRITEBYTECODE=1
        "$PYBIN" "${SCORECARD_ARGS[@]}"
    ) >> "$LOG" 2>&1 || scorecard_rc=$?
    if [[ -f "$SCORECARD_JSON_OUT" ]]; then
        cp "$SCORECARD_JSON_OUT" "$SCORECARD_JSON"
    fi
    if [[ -f "$SCORECARD_MD_OUT" ]]; then
        cp "$SCORECARD_MD_OUT" "$SCORECARD_MD"
    fi
else
    echo "[$(ts)] SKIP: cost-gate counterfactual scorecard refresh disabled by OPENCLAW_COST_GATE_LEARNING_REFRESH_SCORECARD=0" >> "$LOG"
fi

data_flow_monitor_rc=0
if [[ "$REFRESH_DATA_FLOW_MONITOR" == "1" ]]; then
    (
        cd "$BASE"
        export PYTHONPATH="$BASE${PYTHONPATH:+:$PYTHONPATH}"
        export PYTHONDONTWRITEBYTECODE=1
        "$PYBIN" "${DATA_FLOW_ARGS[@]}"
    ) >> "$LOG" 2>&1 || data_flow_monitor_rc=$?
    if [[ -f "$DATA_FLOW_JSON_OUT" ]]; then
        cp "$DATA_FLOW_JSON_OUT" "$DATA_FLOW_JSON"
    fi
    if [[ -f "$DATA_FLOW_MD_OUT" ]]; then
        cp "$DATA_FLOW_MD_OUT" "$DATA_FLOW_MD"
    fi
else
    echo "[$(ts)] SKIP: demo data-flow monitor refresh disabled by OPENCLAW_COST_GATE_REFRESH_DATA_FLOW_MONITOR=0" >> "$LOG"
fi

plan_rc=0
if [[ "$REFRESH_PLAN" == "1" ]]; then
    (
        cd "$BASE"
        export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
        export PYTHONDONTWRITEBYTECODE=1
        "$PYBIN" "${PLAN_ARGS[@]}"
    ) >> "$LOG" 2>&1 || plan_rc=$?
    if [[ -f "$PLAN_OUT" ]]; then
        cp "$PLAN_OUT" "$PLAN_JSON"
    fi
else
    echo "[$(ts)] SKIP: cost-gate demo-learning plan refresh disabled by OPENCLAW_COST_GATE_LEARNING_REFRESH_PLAN=0" >> "$LOG"
fi

historical_review_rc=0
materializer_rc=0
refresh_rc=0
review_rc=0
false_negative_candidate_packet_rc=0
false_negative_operator_review_rc=0
sealed_horizon_learning_evidence_rc=0
order_touchability_audit_rc=0
bounded_probe_touchability_preflight_rc=0
bounded_probe_placement_repair_plan_rc=0
bounded_probe_authority_patch_readiness_rc=0
bounded_probe_operator_authorization_rc=0
bounded_probe_shadow_placement_impact_rc=0
bounded_probe_result_review_rc=0
bounded_probe_execution_realism_review_rc=0
bounded_probe_touchability_preflight_skip_reason=""
false_negative_candidate_packet_skip_reason=""
false_negative_operator_review_skip_reason=""
sealed_horizon_learning_evidence_skip_reason=""
order_touchability_audit_skip_reason=""
bounded_probe_placement_repair_plan_skip_reason=""
bounded_probe_authority_patch_readiness_skip_reason=""
bounded_probe_operator_authorization_skip_reason=""
bounded_probe_shadow_placement_impact_skip_reason=""
bounded_probe_result_review_skip_reason=""
bounded_probe_execution_realism_review_skip_reason=""
if [[ "$PREINSTALL_REFRESH_ONLY" == "1" ]]; then
    order_touchability_audit_skip_reason="preinstall_refresh_only"
    false_negative_candidate_packet_skip_reason="preinstall_refresh_only"
    false_negative_operator_review_skip_reason="preinstall_refresh_only"
    sealed_horizon_learning_evidence_skip_reason="preinstall_refresh_only"
    bounded_probe_touchability_preflight_skip_reason="preinstall_refresh_only"
    bounded_probe_placement_repair_plan_skip_reason="preinstall_refresh_only"
    bounded_probe_authority_patch_readiness_skip_reason="preinstall_refresh_only"
    bounded_probe_operator_authorization_skip_reason="preinstall_refresh_only"
    bounded_probe_shadow_placement_impact_skip_reason="preinstall_refresh_only"
    bounded_probe_result_review_skip_reason="preinstall_refresh_only"
    bounded_probe_execution_realism_review_skip_reason="preinstall_refresh_only"
    echo "[$(ts)] SKIP: preinstall refresh-only mode; refreshed scorecard/plan, skipped historical/materializer/outcome/review/false-negative packet/false-negative operator review/sealed evidence/bounded-probe stages" >> "$LOG"
else
    (
        cd "$BASE"
        export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
        export PYTHONDONTWRITEBYTECODE=1
        "$PYBIN" "${HISTORICAL_REVIEW_ARGS[@]}"
    ) >> "$LOG" 2>&1 || historical_review_rc=$?
    if [[ -f "$HISTORICAL_REVIEW_OUT" ]]; then
        cp "$HISTORICAL_REVIEW_OUT" "$HISTORICAL_REVIEW_LATEST"
    fi

    if [[ "$MATERIALIZE_REJECTS" == "1" ]]; then
        (
            cd "$BASE"
            export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
            export PYTHONDONTWRITEBYTECODE=1
            "$PYBIN" "${MATERIALIZER_ARGS[@]}"
        ) >> "$LOG" 2>&1 || materializer_rc=$?
        if [[ -f "$MATERIALIZER_OUT" ]]; then
            cp "$MATERIALIZER_OUT" "$MATERIALIZER_LATEST"
        fi
    else
        echo "[$(ts)] SKIP: cost-gate reject materializer disabled by OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS=0" >> "$LOG"
    fi

    (
        cd "$BASE"
        export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
        export PYTHONDONTWRITEBYTECODE=1
        "$PYBIN" "${REFRESH_ARGS[@]}"
    ) >> "$LOG" 2>&1 || refresh_rc=$?
    if [[ -f "$REFRESH_OUT" ]]; then
        cp "$REFRESH_OUT" "$REFRESH_LATEST"
    fi

    (
        cd "$BASE"
        export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
        export PYTHONDONTWRITEBYTECODE=1
        "$PYBIN" "${REVIEW_ARGS[@]}"
    ) >> "$LOG" 2>&1 || review_rc=$?
    if [[ -f "$REVIEW_OUT" ]]; then
        cp "$REVIEW_OUT" "$REVIEW_LATEST"
    fi

    if [[ "$REFRESH_FALSE_NEGATIVE_CANDIDATE_PACKET" == "1" ]]; then
        (
            cd "$BASE"
            export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
            export PYTHONDONTWRITEBYTECODE=1
            "$PYBIN" "${FALSE_NEGATIVE_CANDIDATE_PACKET_ARGS[@]}"
        ) >> "$LOG" 2>&1 || false_negative_candidate_packet_rc=$?
        if [[ -f "$FALSE_NEGATIVE_CANDIDATE_PACKET_OUT" ]]; then
            cp "$FALSE_NEGATIVE_CANDIDATE_PACKET_OUT" "$FALSE_NEGATIVE_CANDIDATE_PACKET_LATEST"
            if [[ -f "$FALSE_NEGATIVE_CANDIDATE_PACKET_MD_OUT" ]]; then
                cp "$FALSE_NEGATIVE_CANDIDATE_PACKET_MD_OUT" "$FALSE_NEGATIVE_CANDIDATE_PACKET_MD_LATEST"
            fi
        fi
    else
        false_negative_candidate_packet_skip_reason="disabled"
        echo "[$(ts)] SKIP: false-negative candidate packet disabled by OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_CANDIDATE_PACKET=0" >> "$LOG"
    fi

    if [[ "$REFRESH_FALSE_NEGATIVE_OPERATOR_REVIEW" == "1" ]]; then
        (
            cd "$BASE"
            export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
            export PYTHONDONTWRITEBYTECODE=1
            "$PYBIN" "${FALSE_NEGATIVE_OPERATOR_REVIEW_ARGS[@]}"
        ) >> "$LOG" 2>&1 || false_negative_operator_review_rc=$?
        if [[ -f "$FALSE_NEGATIVE_OPERATOR_REVIEW_OUT" ]]; then
            cp "$FALSE_NEGATIVE_OPERATOR_REVIEW_OUT" "$FALSE_NEGATIVE_OPERATOR_REVIEW_LATEST"
            if [[ -f "$FALSE_NEGATIVE_OPERATOR_REVIEW_MD_OUT" ]]; then
                cp "$FALSE_NEGATIVE_OPERATOR_REVIEW_MD_OUT" "$FALSE_NEGATIVE_OPERATOR_REVIEW_MD_LATEST"
            fi
        fi
    else
        false_negative_operator_review_skip_reason="disabled"
        echo "[$(ts)] SKIP: false-negative operator review disabled by OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_OPERATOR_REVIEW=0" >> "$LOG"
    fi

    if [[ "$REFRESH_SEALED_HORIZON_LEARNING_EVIDENCE" == "1" ]]; then
        if [[ -f "$HORIZON_SEALED_REPLAY_JSON" ]]; then
            (
                cd "$BASE"
                export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
                export PYTHONDONTWRITEBYTECODE=1
                "$PYBIN" "${SEALED_LEARNING_EVIDENCE_ARGS[@]}"
            ) >> "$LOG" 2>&1 || sealed_horizon_learning_evidence_rc=$?
            if [[ -f "$SEALED_LEARNING_EVIDENCE_OUT" ]]; then
                cp "$SEALED_LEARNING_EVIDENCE_OUT" "$SEALED_LEARNING_EVIDENCE_JSON"
            fi
            if [[ -f "$SEALED_LEARNING_EVIDENCE_REVIEW_OUT" ]]; then
                cp "$SEALED_LEARNING_EVIDENCE_REVIEW_OUT" "$SEALED_LEARNING_EVIDENCE_REVIEW_LATEST"
            fi
            if [[ -f "$SEALED_LEARNING_EVIDENCE_SOURCE_ROWS_OUT" ]]; then
                cp "$SEALED_LEARNING_EVIDENCE_SOURCE_ROWS_OUT" "$SEALED_LEARNING_EVIDENCE_SOURCE_ROWS_LATEST"
            fi
        else
            sealed_horizon_learning_evidence_skip_reason="horizon_sealed_replay_missing"
            echo "[$(ts)] SKIP: sealed horizon learning evidence refresh missing sealed replay artifact" >> "$LOG"
        fi
    else
        sealed_horizon_learning_evidence_skip_reason="disabled"
        echo "[$(ts)] SKIP: sealed horizon learning evidence refresh disabled by OPENCLAW_COST_GATE_REFRESH_SEALED_HORIZON_LEARNING_EVIDENCE=0" >> "$LOG"
    fi

    if [[ "$REFRESH_ORDER_TOUCHABILITY_AUDIT" == "1" ]]; then
        (
            cd "$BASE"
            export PYTHONPATH="$BASE${PYTHONPATH:+:$PYTHONPATH}"
            export PYTHONDONTWRITEBYTECODE=1
            "$PYBIN" "${ORDER_TOUCHABILITY_ARGS[@]}"
        ) >> "$LOG" 2>&1 || order_touchability_audit_rc=$?
        if [[ -f "$ORDER_TOUCHABILITY_JSON_OUT" ]]; then
            cp "$ORDER_TOUCHABILITY_JSON_OUT" "$ORDER_TOUCHABILITY_JSON"
            if [[ -f "$ORDER_TOUCHABILITY_MD_OUT" ]]; then
                cp "$ORDER_TOUCHABILITY_MD_OUT" "$ORDER_TOUCHABILITY_MD"
            fi
        fi
    else
        order_touchability_audit_skip_reason="disabled"
        echo "[$(ts)] SKIP: demo order-to-fill touchability audit disabled by OPENCLAW_COST_GATE_REFRESH_ORDER_TOUCHABILITY_AUDIT=0" >> "$LOG"
    fi

    if [[ "$REFRESH_BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT" == "1" ]]; then
        (
            cd "$BASE"
            export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
            export PYTHONDONTWRITEBYTECODE=1
            "$PYBIN" "${BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_ARGS[@]}"
        ) >> "$LOG" 2>&1 || bounded_probe_touchability_preflight_rc=$?
        if [[ -f "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT" ]]; then
            cp "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT" "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_LATEST"
            if [[ -f "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_MD_OUT" ]]; then
                cp "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_MD_OUT" "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_MD_LATEST"
            fi
        fi
    else
        bounded_probe_touchability_preflight_skip_reason="disabled"
        echo "[$(ts)] SKIP: bounded probe touchability preflight disabled by OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT=0" >> "$LOG"
    fi

    if [[ "$REFRESH_BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN" == "1" ]]; then
        (
            cd "$BASE"
            export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
            export PYTHONDONTWRITEBYTECODE=1
            "$PYBIN" "${BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_ARGS[@]}"
        ) >> "$LOG" 2>&1 || bounded_probe_placement_repair_plan_rc=$?
        if [[ -f "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT" ]]; then
            cp "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT" "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_LATEST"
            if [[ -f "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_MD_OUT" ]]; then
                cp "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_MD_OUT" "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_MD_LATEST"
            fi
        fi
    else
        bounded_probe_placement_repair_plan_skip_reason="disabled"
        echo "[$(ts)] SKIP: bounded probe placement repair plan disabled by OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN=0" >> "$LOG"
    fi

    if [[ "$REFRESH_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS" == "1" ]]; then
        (
            cd "$BASE"
            export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
            export PYTHONDONTWRITEBYTECODE=1
            "$PYBIN" "${BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_ARGS[@]}"
        ) >> "$LOG" 2>&1 || bounded_probe_authority_patch_readiness_rc=$?
        if [[ -f "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT" ]]; then
            cp "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT" "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_LATEST"
            if [[ -f "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_MD_OUT" ]]; then
                cp "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_MD_OUT" "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_MD_LATEST"
            fi
        fi
    else
        bounded_probe_authority_patch_readiness_skip_reason="disabled"
        echo "[$(ts)] SKIP: bounded probe authority patch readiness disabled by OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS=0" >> "$LOG"
    fi

    if [[ "$REFRESH_BOUNDED_PROBE_OPERATOR_AUTHORIZATION" == "1" ]]; then
        (
            cd "$BASE"
            export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
            export PYTHONDONTWRITEBYTECODE=1
            "$PYBIN" "${BOUNDED_PROBE_OPERATOR_AUTHORIZATION_ARGS[@]}"
        ) >> "$LOG" 2>&1 || bounded_probe_operator_authorization_rc=$?
        if [[ -f "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT" ]]; then
            cp "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT" "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_LATEST"
            if [[ -f "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_MD_OUT" ]]; then
                cp "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_MD_OUT" "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_MD_LATEST"
            fi
        fi
    else
        bounded_probe_operator_authorization_skip_reason="disabled"
        echo "[$(ts)] SKIP: bounded probe operator authorization packet disabled by OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_OPERATOR_AUTHORIZATION=0" >> "$LOG"
    fi

    if [[ "$REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT" == "1" ]]; then
        (
            cd "$BASE"
            export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
            export PYTHONDONTWRITEBYTECODE=1
            "$PYBIN" "${BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_ARGS[@]}"
        ) >> "$LOG" 2>&1 || bounded_probe_shadow_placement_impact_rc=$?
        if [[ -f "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT" ]]; then
            cp "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT" "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_LATEST"
            if [[ -f "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_MD_OUT" ]]; then
                cp "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_MD_OUT" "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_MD_LATEST"
            fi
        fi
    else
        bounded_probe_shadow_placement_impact_skip_reason="disabled"
        echo "[$(ts)] SKIP: bounded probe shadow placement impact disabled by OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT=0" >> "$LOG"
    fi

    if [[ "$REFRESH_BOUNDED_PROBE_RESULT_REVIEW" == "1" ]]; then
        if [[ -f "$SEALED_PREFLIGHT_JSON" ]]; then
            (
                cd "$BASE"
                export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
                export PYTHONDONTWRITEBYTECODE=1
                "$PYBIN" "${BOUNDED_PROBE_RESULT_REVIEW_ARGS[@]}"
            ) >> "$LOG" 2>&1 || bounded_probe_result_review_rc=$?
            if [[ -f "$BOUNDED_PROBE_RESULT_REVIEW_OUT" ]]; then
                cp "$BOUNDED_PROBE_RESULT_REVIEW_OUT" "$BOUNDED_PROBE_RESULT_REVIEW_LATEST"
                if [[ -f "$BOUNDED_PROBE_RESULT_REVIEW_MD_OUT" ]]; then
                    cp "$BOUNDED_PROBE_RESULT_REVIEW_MD_OUT" "$BOUNDED_PROBE_RESULT_REVIEW_MD_LATEST"
                fi
            fi
        else
            bounded_probe_result_review_skip_reason="sealed_horizon_probe_preflight_missing"
            echo "[$(ts)] SKIP: bounded probe result review missing sealed preflight: $SEALED_PREFLIGHT_JSON" >> "$LOG"
        fi
    else
        bounded_probe_result_review_skip_reason="disabled"
        echo "[$(ts)] SKIP: bounded probe result review disabled by OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_RESULT_REVIEW=0" >> "$LOG"
    fi

    if [[ "$REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW" == "1" ]]; then
        if [[ -f "$BOUNDED_PROBE_RESULT_REVIEW_OUT" ]]; then
            (
                cd "$BASE"
                export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
                export PYTHONDONTWRITEBYTECODE=1
                "$PYBIN" "${BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_ARGS[@]}"
            ) >> "$LOG" 2>&1 || bounded_probe_execution_realism_review_rc=$?
            if [[ -f "$BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_OUT" ]]; then
                cp "$BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_OUT" "$BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_LATEST"
                if [[ -f "$BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_MD_OUT" ]]; then
                    cp "$BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_MD_OUT" "$BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_MD_LATEST"
                fi
            fi
        else
            bounded_probe_execution_realism_review_skip_reason="bounded_probe_result_review_missing"
            echo "[$(ts)] SKIP: bounded probe execution-realism review missing result review: $BOUNDED_PROBE_RESULT_REVIEW_OUT" >> "$LOG"
        fi
    else
        bounded_probe_execution_realism_review_skip_reason="disabled"
        echo "[$(ts)] SKIP: bounded probe execution-realism review disabled by OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW=0" >> "$LOG"
    fi
fi

decision_packet_rc=0
if [[ "$REFRESH_DECISION_PACKET" == "1" ]]; then
    (
        cd "$BASE"
        export PYTHONPATH="$BASE/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
        export PYTHONDONTWRITEBYTECODE=1
        "$PYBIN" "${DECISION_PACKET_ARGS[@]}"
    ) >> "$LOG" 2>&1 || decision_packet_rc=$?
    if [[ -f "$DECISION_PACKET_JSON_OUT" ]]; then
        cp "$DECISION_PACKET_JSON_OUT" "$DECISION_PACKET_JSON"
    fi
    if [[ -f "$DECISION_PACKET_MD_OUT" ]]; then
        cp "$DECISION_PACKET_MD_OUT" "$DECISION_PACKET_MD"
    fi
else
    echo "[$(ts)] SKIP: profit-learning decision packet refresh disabled by OPENCLAW_COST_GATE_REFRESH_DECISION_PACKET=0" >> "$LOG"
fi

export FALSE_NEGATIVE_CANDIDATE_PACKET_OUT="$FALSE_NEGATIVE_CANDIDATE_PACKET_OUT"
export FALSE_NEGATIVE_CANDIDATE_PACKET_LATEST="$FALSE_NEGATIVE_CANDIDATE_PACKET_LATEST"
export FALSE_NEGATIVE_CANDIDATE_PACKET_RC="$false_negative_candidate_packet_rc"
export FALSE_NEGATIVE_CANDIDATE_PACKET_SKIP_REASON="$false_negative_candidate_packet_skip_reason"
export REFRESH_FALSE_NEGATIVE_CANDIDATE_PACKET="$REFRESH_FALSE_NEGATIVE_CANDIDATE_PACKET"
export FALSE_NEGATIVE_OPERATOR_REVIEW_OUT="$FALSE_NEGATIVE_OPERATOR_REVIEW_OUT"
export FALSE_NEGATIVE_OPERATOR_REVIEW_LATEST="$FALSE_NEGATIVE_OPERATOR_REVIEW_LATEST"
export FALSE_NEGATIVE_OPERATOR_REVIEW_RC="$false_negative_operator_review_rc"
export FALSE_NEGATIVE_OPERATOR_REVIEW_SKIP_REASON="$false_negative_operator_review_skip_reason"
export REFRESH_FALSE_NEGATIVE_OPERATOR_REVIEW="$REFRESH_FALSE_NEGATIVE_OPERATOR_REVIEW"
export BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT="$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT"
export BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_LATEST="$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_LATEST"
export BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_RC="$bounded_probe_shadow_placement_impact_rc"
export BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_SKIP_REASON="$bounded_probe_shadow_placement_impact_skip_reason"
export REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT="$REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT"
export BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT="$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT"
export BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_LATEST="$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_LATEST"
export BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_RC="$bounded_probe_authority_patch_readiness_rc"
export BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_SKIP_REASON="$bounded_probe_authority_patch_readiness_skip_reason"
export REFRESH_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS="$REFRESH_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS"
export BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT="$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT"
export BOUNDED_PROBE_OPERATOR_AUTHORIZATION_LATEST="$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_LATEST"
export BOUNDED_PROBE_OPERATOR_AUTHORIZATION_RC="$bounded_probe_operator_authorization_rc"
export BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SKIP_REASON="$bounded_probe_operator_authorization_skip_reason"
export REFRESH_BOUNDED_PROBE_OPERATOR_AUTHORIZATION="$REFRESH_BOUNDED_PROBE_OPERATOR_AUTHORIZATION"
export HORIZON_SEALED_REPLAY_JSON="$HORIZON_SEALED_REPLAY_JSON"
export SEALED_LEARNING_EVIDENCE_OUT="$SEALED_LEARNING_EVIDENCE_OUT"
export SEALED_LEARNING_EVIDENCE_JSON="$SEALED_LEARNING_EVIDENCE_JSON"
export SEALED_LEARNING_EVIDENCE_REVIEW_OUT="$SEALED_LEARNING_EVIDENCE_REVIEW_OUT"
export SEALED_LEARNING_EVIDENCE_REVIEW_LATEST="$SEALED_LEARNING_EVIDENCE_REVIEW_LATEST"
export SEALED_LEARNING_EVIDENCE_SOURCE_ROWS_OUT="$SEALED_LEARNING_EVIDENCE_SOURCE_ROWS_OUT"
export SEALED_LEARNING_EVIDENCE_SOURCE_ROWS_LATEST="$SEALED_LEARNING_EVIDENCE_SOURCE_ROWS_LATEST"
export SEALED_HORIZON_LEARNING_EVIDENCE_RC="$sealed_horizon_learning_evidence_rc"
export SEALED_HORIZON_LEARNING_EVIDENCE_SKIP_REASON="$sealed_horizon_learning_evidence_skip_reason"
export REFRESH_SEALED_HORIZON_LEARNING_EVIDENCE="$REFRESH_SEALED_HORIZON_LEARNING_EVIDENCE"
export APPEND_SEALED_HORIZON_LEARNING_EVIDENCE="$APPEND_SEALED_HORIZON_LEARNING_EVIDENCE"

STATUS_JSON=$(SCORECARD_JSON_OUT="$SCORECARD_JSON_OUT" SCORECARD_JSON="$SCORECARD_JSON" SCORECARD_RC="$scorecard_rc" REFRESH_SCORECARD="$REFRESH_SCORECARD" DATA_FLOW_JSON_OUT="$DATA_FLOW_JSON_OUT" DATA_FLOW_JSON="$DATA_FLOW_JSON" DATA_FLOW_MONITOR_RC="$data_flow_monitor_rc" REFRESH_DATA_FLOW_MONITOR="$REFRESH_DATA_FLOW_MONITOR" ORDER_TOUCHABILITY_JSON_OUT="$ORDER_TOUCHABILITY_JSON_OUT" ORDER_TOUCHABILITY_JSON="$ORDER_TOUCHABILITY_JSON" ORDER_TOUCHABILITY_AUDIT_RC="$order_touchability_audit_rc" ORDER_TOUCHABILITY_AUDIT_SKIP_REASON="$order_touchability_audit_skip_reason" REFRESH_ORDER_TOUCHABILITY_AUDIT="$REFRESH_ORDER_TOUCHABILITY_AUDIT" DECISION_PACKET_JSON_OUT="$DECISION_PACKET_JSON_OUT" DECISION_PACKET_JSON="$DECISION_PACKET_JSON" DECISION_PACKET_RC="$decision_packet_rc" REFRESH_DECISION_PACKET="$REFRESH_DECISION_PACKET" PLAN_OUT="$PLAN_OUT" PLAN_JSON="$PLAN_JSON" PLAN_RC="$plan_rc" REFRESH_PLAN="$REFRESH_PLAN" PREINSTALL_REFRESH_ONLY="$PREINSTALL_REFRESH_ONLY" HISTORICAL_REVIEW_OUT="$HISTORICAL_REVIEW_OUT" MATERIALIZER_OUT="$MATERIALIZER_OUT" REFRESH_OUT="$REFRESH_OUT" REVIEW_OUT="$REVIEW_OUT" BOUNDED_PROBE_PREFLIGHT_JSON="$SEALED_PREFLIGHT_JSON" ORDER_TOUCHABILITY_JSON="$ORDER_TOUCHABILITY_JSON" BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT="$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT" BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_LATEST="$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_LATEST" BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT="$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT" BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_LATEST="$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_LATEST" BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT="$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT" BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_LATEST="$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_LATEST" BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT="$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT" BOUNDED_PROBE_OPERATOR_AUTHORIZATION_LATEST="$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_LATEST" BOUNDED_PROBE_RESULT_REVIEW_OUT="$BOUNDED_PROBE_RESULT_REVIEW_OUT" BOUNDED_PROBE_RESULT_REVIEW_LATEST="$BOUNDED_PROBE_RESULT_REVIEW_LATEST" BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_OUT="$BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_OUT" BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_LATEST="$BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_LATEST" HISTORICAL_REVIEW_RC="$historical_review_rc" MATERIALIZER_RC="$materializer_rc" REFRESH_RC="$refresh_rc" REVIEW_RC="$review_rc" BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_RC="$bounded_probe_touchability_preflight_rc" BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_RC="$bounded_probe_placement_repair_plan_rc" BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_RC="$bounded_probe_authority_patch_readiness_rc" BOUNDED_PROBE_OPERATOR_AUTHORIZATION_RC="$bounded_probe_operator_authorization_rc" BOUNDED_PROBE_RESULT_REVIEW_RC="$bounded_probe_result_review_rc" BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_RC="$bounded_probe_execution_realism_review_rc" BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_SKIP_REASON="$bounded_probe_touchability_preflight_skip_reason" BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_SKIP_REASON="$bounded_probe_placement_repair_plan_skip_reason" BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_SKIP_REASON="$bounded_probe_authority_patch_readiness_skip_reason" BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SKIP_REASON="$bounded_probe_operator_authorization_skip_reason" BOUNDED_PROBE_RESULT_REVIEW_SKIP_REASON="$bounded_probe_result_review_skip_reason" BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_SKIP_REASON="$bounded_probe_execution_realism_review_skip_reason" REFRESH_BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT="$REFRESH_BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT" REFRESH_BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN="$REFRESH_BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN" REFRESH_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS="$REFRESH_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS" REFRESH_BOUNDED_PROBE_OPERATOR_AUTHORIZATION="$REFRESH_BOUNDED_PROBE_OPERATOR_AUTHORIZATION" REFRESH_BOUNDED_PROBE_RESULT_REVIEW="$REFRESH_BOUNDED_PROBE_RESULT_REVIEW" REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW="$REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW" LEDGER="$LEDGER" MATERIALIZE_REJECTS="$MATERIALIZE_REJECTS" APPEND_MATERIALIZED_REJECTS="$APPEND_MATERIALIZED_REJECTS" APPEND_OUTCOMES="$APPEND_OUTCOMES" "$PYBIN" - <<'PY' 2>>"$LOG" || true
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


scorecard, scorecard_sha, scorecard_err = load(os.environ["SCORECARD_JSON_OUT"])
data_flow, data_flow_sha, data_flow_err = load(os.environ["DATA_FLOW_JSON_OUT"])
order_touchability, order_touchability_sha, order_touchability_err = load(os.environ["ORDER_TOUCHABILITY_JSON_OUT"])
decision_packet, decision_packet_sha, decision_packet_err = load(os.environ["DECISION_PACKET_JSON_OUT"])
plan, plan_sha, plan_err = load(os.environ["PLAN_OUT"])
historical, historical_sha, historical_err = load(os.environ["HISTORICAL_REVIEW_OUT"])
materializer, materializer_sha, materializer_err = load(os.environ["MATERIALIZER_OUT"])
refresh, refresh_sha, refresh_err = load(os.environ["REFRESH_OUT"])
review, review_sha, review_err = load(os.environ["REVIEW_OUT"])
false_negative_packet, false_negative_packet_sha, false_negative_packet_err = load(
    os.environ["FALSE_NEGATIVE_CANDIDATE_PACKET_OUT"]
)
false_negative_operator_review, false_negative_operator_review_sha, false_negative_operator_review_err = load(
    os.environ["FALSE_NEGATIVE_OPERATOR_REVIEW_OUT"]
)
sealed_learning, sealed_learning_sha, sealed_learning_err = load(
    os.environ["SEALED_LEARNING_EVIDENCE_OUT"]
)
bounded_touchability, bounded_touchability_sha, bounded_touchability_err = load(
    os.environ["BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT"]
)
bounded_placement, bounded_placement_sha, bounded_placement_err = load(
    os.environ["BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT"]
)
bounded_authority, bounded_authority_sha, bounded_authority_err = load(
    os.environ["BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT"]
)
bounded_operator_auth, bounded_operator_auth_sha, bounded_operator_auth_err = load(
    os.environ["BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT"]
)
bounded_shadow, bounded_shadow_sha, bounded_shadow_err = load(
    os.environ["BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT"]
)
bounded_result, bounded_result_sha, bounded_result_err = load(os.environ["BOUNDED_PROBE_RESULT_REVIEW_OUT"])
bounded_exec, bounded_exec_sha, bounded_exec_err = load(os.environ["BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_OUT"])
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
    "scorecard_rc": int(os.environ["SCORECARD_RC"]),
    "data_flow_monitor_rc": int(os.environ["DATA_FLOW_MONITOR_RC"]),
    "order_touchability_audit_rc": int(os.environ["ORDER_TOUCHABILITY_AUDIT_RC"]),
    "decision_packet_rc": int(os.environ["DECISION_PACKET_RC"]),
    "plan_rc": int(os.environ["PLAN_RC"]),
    "historical_review_rc": int(os.environ["HISTORICAL_REVIEW_RC"]),
    "materializer_rc": int(os.environ["MATERIALIZER_RC"]),
    "refresh_rc": int(os.environ["REFRESH_RC"]),
    "review_rc": int(os.environ["REVIEW_RC"]),
    "false_negative_candidate_packet_rc": int(os.environ["FALSE_NEGATIVE_CANDIDATE_PACKET_RC"]),
    "false_negative_operator_review_rc": int(os.environ["FALSE_NEGATIVE_OPERATOR_REVIEW_RC"]),
    "sealed_horizon_learning_evidence_rc": int(os.environ["SEALED_HORIZON_LEARNING_EVIDENCE_RC"]),
    "bounded_probe_touchability_preflight_rc": int(os.environ["BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_RC"]),
    "bounded_probe_placement_repair_plan_rc": int(os.environ["BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_RC"]),
    "bounded_probe_authority_patch_readiness_rc": int(os.environ["BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_RC"]),
    "bounded_probe_operator_authorization_rc": int(os.environ["BOUNDED_PROBE_OPERATOR_AUTHORIZATION_RC"]),
    "bounded_probe_shadow_placement_impact_rc": int(os.environ["BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_RC"]),
    "bounded_probe_result_review_rc": int(os.environ["BOUNDED_PROBE_RESULT_REVIEW_RC"]),
    "bounded_probe_execution_realism_review_rc": int(os.environ["BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_RC"]),
    "refresh_scorecard": os.environ["REFRESH_SCORECARD"] == "1",
    "refresh_data_flow_monitor": os.environ["REFRESH_DATA_FLOW_MONITOR"] == "1",
    "refresh_order_touchability_audit": os.environ["REFRESH_ORDER_TOUCHABILITY_AUDIT"] == "1",
    "refresh_decision_packet": os.environ["REFRESH_DECISION_PACKET"] == "1",
    "refresh_false_negative_candidate_packet": os.environ["REFRESH_FALSE_NEGATIVE_CANDIDATE_PACKET"] == "1",
    "refresh_false_negative_operator_review": os.environ["REFRESH_FALSE_NEGATIVE_OPERATOR_REVIEW"] == "1",
    "refresh_plan": os.environ["REFRESH_PLAN"] == "1",
    "refresh_sealed_horizon_learning_evidence": os.environ["REFRESH_SEALED_HORIZON_LEARNING_EVIDENCE"] == "1",
    "append_sealed_horizon_learning_evidence": os.environ["APPEND_SEALED_HORIZON_LEARNING_EVIDENCE"] == "1",
    "refresh_bounded_probe_touchability_preflight": os.environ["REFRESH_BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT"] == "1",
    "refresh_bounded_probe_placement_repair_plan": os.environ["REFRESH_BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN"] == "1",
    "refresh_bounded_probe_authority_patch_readiness": os.environ["REFRESH_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS"] == "1",
    "refresh_bounded_probe_operator_authorization": os.environ["REFRESH_BOUNDED_PROBE_OPERATOR_AUTHORIZATION"] == "1",
    "refresh_bounded_probe_shadow_placement_impact": os.environ["REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT"] == "1",
    "refresh_bounded_probe_result_review": os.environ["REFRESH_BOUNDED_PROBE_RESULT_REVIEW"] == "1",
    "refresh_bounded_probe_execution_realism_review": os.environ["REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW"] == "1",
    "preinstall_refresh_only": os.environ["PREINSTALL_REFRESH_ONLY"] == "1",
    "materialize_rejects": os.environ["MATERIALIZE_REJECTS"] == "1",
    "append_materialized_rejects": os.environ["APPEND_MATERIALIZED_REJECTS"] == "1",
    "append_outcomes": os.environ["APPEND_OUTCOMES"] == "1",
    "ledger_path": str(ledger),
    "ledger_row_count": ledger_rows,
    "scorecard_artifact_path": os.environ["SCORECARD_JSON_OUT"],
    "scorecard_latest_path": os.environ["SCORECARD_JSON"],
    "scorecard_sha256": scorecard_sha,
    "scorecard_error": scorecard_err,
    "scorecard_status": (scorecard.get("learning_lane_scorecard") or {}).get("status"),
    "scorecard_probe_candidate_count": (
        (scorecard.get("learning_lane_scorecard") or {}).get("probe_candidate_count")
    ),
    "scorecard_horizon_stability_status": (
        ((scorecard.get("learning_lane_scorecard") or {}).get("horizon_stability_scorecard") or {}).get("status")
    ),
    "scorecard_horizon_stability_next_trigger": (
        ((scorecard.get("learning_lane_scorecard") or {}).get("horizon_stability_scorecard") or {}).get("next_trigger")
    ),
    "scorecard_horizon_stability_horizons": (
        ((scorecard.get("learning_lane_scorecard") or {}).get("horizon_stability_scorecard") or {}).get("horizons_minutes")
    ),
    "data_flow_monitor_artifact_path": os.environ["DATA_FLOW_JSON_OUT"],
    "data_flow_monitor_latest_path": os.environ["DATA_FLOW_JSON"],
    "data_flow_monitor_sha256": data_flow_sha,
    "data_flow_monitor_error": data_flow_err,
    "data_flow_monitor_status": (data_flow.get("summary") or {}).get("status"),
    "data_flow_monitor_reason": (data_flow.get("summary") or {}).get("reason"),
    "data_flow_monitor_next_action": (data_flow.get("summary") or {}).get("next_action"),
    "data_flow_monitor_key_counts": (data_flow.get("summary") or {}).get("key_counts"),
    "order_touchability_audit_artifact_path": os.environ["ORDER_TOUCHABILITY_JSON_OUT"],
    "order_touchability_audit_latest_path": os.environ["ORDER_TOUCHABILITY_JSON"],
    "order_touchability_audit_sha256": order_touchability_sha,
    "order_touchability_audit_error": order_touchability_err,
    "order_touchability_audit_skip_reason": os.environ["ORDER_TOUCHABILITY_AUDIT_SKIP_REASON"] or None,
    "order_touchability_audit_status": (order_touchability.get("summary") or {}).get("status"),
    "order_touchability_audit_reason": (order_touchability.get("summary") or {}).get("reason"),
    "order_touchability_audit_next_action": (order_touchability.get("summary") or {}).get("next_action"),
    "order_touchability_audit_counts": (order_touchability.get("summary") or {}).get("counts"),
    "order_touchability_audit_answers": (order_touchability.get("summary") or {}).get("answers"),
    "decision_packet_artifact_path": os.environ["DECISION_PACKET_JSON_OUT"],
    "decision_packet_latest_path": os.environ["DECISION_PACKET_JSON"],
    "decision_packet_sha256": decision_packet_sha,
    "decision_packet_error": decision_packet_err,
    "decision_packet_status": decision_packet.get("status"),
    "decision_packet_reason": decision_packet.get("reason"),
    "decision_packet_next_actions": decision_packet.get("next_actions"),
    "decision_packet_silent_drop_risk": (decision_packet.get("answers") or {}).get("silent_drop_risk"),
    "decision_packet_data_flow_status": (decision_packet.get("data_flow") or {}).get("status"),
    "plan_artifact_path": os.environ["PLAN_OUT"],
    "plan_latest_path": os.environ["PLAN_JSON"],
    "plan_sha256": plan_sha,
    "plan_error": plan_err,
    "plan_policy_status": plan.get("status"),
    "plan_gate_status": plan.get("gate_status"),
    "plan_selected_probe_candidate_count": plan.get("selected_probe_candidate_count"),
    "horizon_sealed_replay_path": os.environ["HORIZON_SEALED_REPLAY_JSON"] or None,
    "historical_review_artifact_path": os.environ["HISTORICAL_REVIEW_OUT"],
    "historical_review_sha256": historical_sha,
    "historical_review_error": historical_err,
    "historical_review_status": historical.get("status"),
    "historical_review_reason": historical.get("reason"),
    "historical_review_next_trigger": historical.get("next_trigger"),
    "historical_candidate_side_cell_count": historical.get("historical_candidate_side_cell_count"),
    "materializer_artifact_path": os.environ["MATERIALIZER_OUT"],
    "materializer_sha256": materializer_sha,
    "materializer_error": materializer_err,
    "materializer_status": materializer.get("status"),
    "materializer_input_feature_row_count": materializer.get("input_feature_row_count"),
    "materializer_materialized_record_count": materializer.get("materialized_record_count"),
    "materializer_appended_record_count": materializer.get("appended_record_count"),
    "materializer_decision_counts": materializer.get("decision_counts"),
    "materializer_source_counts": materializer.get("source_counts"),
    "materializer_snapshot_json_path": materializer.get("snapshot_json_path"),
    "materializer_snapshot_json_error": materializer.get("snapshot_json_error"),
    "materializer_snapshot_input_row_count": (
        (materializer.get("source_counts") or {}).get("snapshot_input_row_count")
        if isinstance(materializer.get("source_counts"), dict)
        else None
    ),
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
    "review_top_side_cell_key": review.get("top_side_cell_key"),
    "review_top_side_cell_status": review.get("top_side_cell_status"),
    "review_top_wrongful_block_score": review.get("top_side_cell_wrongful_block_score"),
    "review_top_net_cost_cushion_bps": review.get("top_side_cell_net_cost_cushion_bps"),
    "review_top_candidate_side_cell_key": review.get("top_review_candidate_side_cell_key"),
    "review_top_candidate_wrongful_block_score": review.get("top_review_candidate_wrongful_block_score"),
    "review_top_candidate_net_cost_cushion_bps": review.get("top_review_candidate_net_cost_cushion_bps"),
    "blocked_signal_outcome_count": review.get("blocked_signal_outcome_count"),
    "false_negative_candidate_packet_artifact_path": os.environ["FALSE_NEGATIVE_CANDIDATE_PACKET_OUT"],
    "false_negative_candidate_packet_latest_path": os.environ["FALSE_NEGATIVE_CANDIDATE_PACKET_LATEST"],
    "false_negative_candidate_packet_sha256": false_negative_packet_sha,
    "false_negative_candidate_packet_error": false_negative_packet_err,
    "false_negative_candidate_packet_skip_reason": os.environ["FALSE_NEGATIVE_CANDIDATE_PACKET_SKIP_REASON"] or None,
    "false_negative_candidate_packet_status": false_negative_packet.get("status"),
    "false_negative_candidate_packet_reason": false_negative_packet.get("reason"),
    "false_negative_candidate_packet_next_actions": false_negative_packet.get("next_actions"),
    "false_negative_candidate_packet_false_negative_count": (
        (false_negative_packet.get("summary") or {}).get("false_negative_candidate_count")
        if isinstance(false_negative_packet.get("summary"), dict)
        else None
    ),
    "false_negative_candidate_packet_edge_amplification_count": (
        (false_negative_packet.get("summary") or {}).get("edge_amplification_candidate_count")
        if isinstance(false_negative_packet.get("summary"), dict)
        else None
    ),
    "false_negative_candidate_packet_top_side_cell_key": (
        (false_negative_packet.get("summary") or {}).get("top_false_negative_side_cell_key")
        if isinstance(false_negative_packet.get("summary"), dict)
        else None
    ),
    "false_negative_candidate_packet_top_wrongful_block_score": (
        (false_negative_packet.get("summary") or {}).get("top_false_negative_wrongful_block_score")
        if isinstance(false_negative_packet.get("summary"), dict)
        else None
    ),
    "false_negative_candidate_packet_top_net_cost_cushion_bps": (
        (false_negative_packet.get("summary") or {}).get("top_false_negative_net_cost_cushion_bps")
        if isinstance(false_negative_packet.get("summary"), dict)
        else None
    ),
    "false_negative_candidate_packet_top_edge_amplification_side_cell_key": (
        (false_negative_packet.get("summary") or {}).get("top_edge_amplification_side_cell_key")
        if isinstance(false_negative_packet.get("summary"), dict)
        else None
    ),
    "false_negative_candidate_packet_operator_review_ready": (
        (false_negative_packet.get("answers") or {}).get("operator_review_ready")
        if isinstance(false_negative_packet.get("answers"), dict)
        else None
    ),
    "false_negative_candidate_packet_engineering_actionable": (
        (false_negative_packet.get("answers") or {}).get("engineering_actionable")
        if isinstance(false_negative_packet.get("answers"), dict)
        else None
    ),
    "false_negative_candidate_packet_global_cost_gate_lowering_recommended": (
        (false_negative_packet.get("answers") or {}).get("global_cost_gate_lowering_recommended")
        if isinstance(false_negative_packet.get("answers"), dict)
        else None
    ),
    "false_negative_candidate_packet_probe_authority_granted": (
        (false_negative_packet.get("answers") or {}).get("probe_authority_granted")
        if isinstance(false_negative_packet.get("answers"), dict)
        else None
    ),
    "false_negative_candidate_packet_order_authority_granted": (
        (false_negative_packet.get("answers") or {}).get("order_authority_granted")
        if isinstance(false_negative_packet.get("answers"), dict)
        else None
    ),
    "false_negative_candidate_packet_promotion_evidence": (
        (false_negative_packet.get("answers") or {}).get("promotion_evidence")
        if isinstance(false_negative_packet.get("answers"), dict)
        else None
    ),
    "false_negative_operator_review_artifact_path": os.environ["FALSE_NEGATIVE_OPERATOR_REVIEW_OUT"],
    "false_negative_operator_review_latest_path": os.environ["FALSE_NEGATIVE_OPERATOR_REVIEW_LATEST"],
    "false_negative_operator_review_sha256": false_negative_operator_review_sha,
    "false_negative_operator_review_error": false_negative_operator_review_err,
    "false_negative_operator_review_skip_reason": os.environ["FALSE_NEGATIVE_OPERATOR_REVIEW_SKIP_REASON"] or None,
    "false_negative_operator_review_status": false_negative_operator_review.get("status"),
    "false_negative_operator_review_reason": false_negative_operator_review.get("reason"),
    "false_negative_operator_review_decision": false_negative_operator_review.get("decision"),
    "false_negative_operator_review_next_actions": false_negative_operator_review.get("next_actions"),
    "false_negative_operator_review_selected_side_cell_key": false_negative_operator_review.get("selected_side_cell_key"),
    "false_negative_operator_review_selected_rank": false_negative_operator_review.get("selected_false_negative_rank"),
    "false_negative_operator_review_blocking_gate_count": false_negative_operator_review.get("blocking_gate_count"),
    "false_negative_operator_review_blocking_gates": false_negative_operator_review.get("blocking_gates"),
    "false_negative_operator_review_typed_confirm_expected": false_negative_operator_review.get("typed_confirm_expected"),
    "false_negative_operator_review_approved_for_preflight": (
        (false_negative_operator_review.get("answers") or {}).get("operator_review_approved_for_preflight")
        if isinstance(false_negative_operator_review.get("answers"), dict)
        else None
    ),
    "false_negative_operator_review_bounded_demo_probe_preflight_approved": (
        (false_negative_operator_review.get("answers") or {}).get("bounded_demo_probe_preflight_approved")
        if isinstance(false_negative_operator_review.get("answers"), dict)
        else None
    ),
    "false_negative_operator_review_review_grants_runtime_authority": (
        (false_negative_operator_review.get("answers") or {}).get("review_grants_runtime_authority")
        if isinstance(false_negative_operator_review.get("answers"), dict)
        else None
    ),
    "false_negative_operator_review_global_cost_gate_lowering_recommended": (
        (false_negative_operator_review.get("answers") or {}).get("global_cost_gate_lowering_recommended")
        if isinstance(false_negative_operator_review.get("answers"), dict)
        else None
    ),
    "false_negative_operator_review_probe_authority_granted": (
        (false_negative_operator_review.get("answers") or {}).get("probe_authority_granted")
        if isinstance(false_negative_operator_review.get("answers"), dict)
        else None
    ),
    "false_negative_operator_review_order_authority_granted": (
        (false_negative_operator_review.get("answers") or {}).get("order_authority_granted")
        if isinstance(false_negative_operator_review.get("answers"), dict)
        else None
    ),
    "false_negative_operator_review_promotion_evidence": (
        (false_negative_operator_review.get("answers") or {}).get("promotion_evidence")
        if isinstance(false_negative_operator_review.get("answers"), dict)
        else None
    ),
    "sealed_horizon_learning_evidence_artifact_path": os.environ["SEALED_LEARNING_EVIDENCE_OUT"],
    "sealed_horizon_learning_evidence_latest_path": os.environ["SEALED_LEARNING_EVIDENCE_JSON"],
    "sealed_horizon_learning_evidence_review_artifact_path": os.environ["SEALED_LEARNING_EVIDENCE_REVIEW_OUT"],
    "sealed_horizon_learning_evidence_review_latest_path": os.environ["SEALED_LEARNING_EVIDENCE_REVIEW_LATEST"],
    "sealed_horizon_learning_evidence_source_rows_artifact_path": os.environ["SEALED_LEARNING_EVIDENCE_SOURCE_ROWS_OUT"],
    "sealed_horizon_learning_evidence_source_rows_latest_path": os.environ["SEALED_LEARNING_EVIDENCE_SOURCE_ROWS_LATEST"],
    "sealed_horizon_learning_evidence_sha256": sealed_learning_sha,
    "sealed_horizon_learning_evidence_error": sealed_learning_err,
    "sealed_horizon_learning_evidence_skip_reason": os.environ["SEALED_HORIZON_LEARNING_EVIDENCE_SKIP_REASON"] or None,
    "sealed_horizon_learning_evidence_status": sealed_learning.get("status"),
    "sealed_horizon_learning_evidence_reason": sealed_learning.get("reason"),
    "sealed_horizon_learning_evidence_next_trigger": sealed_learning.get("next_trigger"),
    "sealed_horizon_learning_evidence_side_cell_key": sealed_learning.get("side_cell_key"),
    "sealed_horizon_learning_evidence_outcome_horizon_minutes": sealed_learning.get("outcome_horizon_minutes"),
    "sealed_horizon_learning_evidence_blocked_signal_outcome_count": (
        (sealed_learning.get("outcomes") or {}).get("blocked_signal_outcome_count")
        if isinstance(sealed_learning.get("outcomes"), dict)
        else None
    ),
    "sealed_horizon_learning_evidence_candidate_clears_operator_review_gate": (
        (sealed_learning.get("answers") or {}).get("candidate_clears_operator_review_gate")
        if isinstance(sealed_learning.get("answers"), dict)
        else None
    ),
    "bounded_probe_preflight_path": os.environ["BOUNDED_PROBE_PREFLIGHT_JSON"],
    "order_touchability_audit_path": os.environ["ORDER_TOUCHABILITY_JSON"],
    "bounded_probe_touchability_preflight_artifact_path": os.environ["BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT"],
    "bounded_probe_touchability_preflight_latest_path": os.environ["BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_LATEST"],
    "bounded_probe_touchability_preflight_sha256": bounded_touchability_sha,
    "bounded_probe_touchability_preflight_error": bounded_touchability_err,
    "bounded_probe_touchability_preflight_skip_reason": os.environ["BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_SKIP_REASON"] or None,
    "bounded_probe_touchability_preflight_status": bounded_touchability.get("status"),
    "bounded_probe_touchability_preflight_reason": bounded_touchability.get("reason"),
    "bounded_probe_touchability_audit_status": (
        (bounded_touchability.get("order_touchability") or {}).get("status")
        if isinstance(bounded_touchability.get("order_touchability"), dict)
        else None
    ),
    "bounded_probe_touchability_reviewed_orders": (
        (bounded_touchability.get("order_touchability") or {}).get("reviewed_orders")
        if isinstance(bounded_touchability.get("order_touchability"), dict)
        else None
    ),
    "bounded_probe_touchability_deep_no_touch_orders": (
        (bounded_touchability.get("order_touchability") or {}).get("deep_passive_no_touch_orders")
        if isinstance(bounded_touchability.get("order_touchability"), dict)
        else None
    ),
    "bounded_probe_touchability_max_best_touch_gap_bps": (
        (bounded_touchability.get("order_touchability") or {}).get("max_best_touch_gap_bps")
        if isinstance(bounded_touchability.get("order_touchability"), dict)
        else None
    ),
    "bounded_probe_touchability_repair_required": (
        (bounded_touchability.get("answers") or {}).get("touchability_repair_required")
        if isinstance(bounded_touchability.get("answers"), dict)
        else None
    ),
    "bounded_probe_placement_repair_plan_artifact_path": os.environ["BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT"],
    "bounded_probe_placement_repair_plan_latest_path": os.environ["BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_LATEST"],
    "bounded_probe_placement_repair_plan_sha256": bounded_placement_sha,
    "bounded_probe_placement_repair_plan_error": bounded_placement_err,
    "bounded_probe_placement_repair_plan_skip_reason": os.environ["BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_SKIP_REASON"] or None,
    "bounded_probe_placement_repair_plan_status": bounded_placement.get("status"),
    "bounded_probe_placement_repair_plan_reason": bounded_placement.get("reason"),
    "bounded_probe_placement_repair_order_mode": (
        (bounded_placement.get("placement_repair_plan") or {}).get("order_mode")
        if isinstance(bounded_placement.get("placement_repair_plan"), dict)
        else None
    ),
    "bounded_probe_placement_repair_ready": (
        (bounded_placement.get("answers") or {}).get("placement_repair_plan_ready_for_operator_review")
        if isinstance(bounded_placement.get("answers"), dict)
        else None
    ),
    "bounded_probe_placement_repair_max_fresh_bbo_age_ms": (
        (bounded_placement.get("placement_repair_plan") or {}).get("max_fresh_bbo_age_ms")
        if isinstance(bounded_placement.get("placement_repair_plan"), dict)
        else None
    ),
    "bounded_probe_placement_repair_max_initial_passive_gap_bps": (
        (bounded_placement.get("placement_repair_plan") or {}).get("max_initial_passive_gap_bps")
        if isinstance(bounded_placement.get("placement_repair_plan"), dict)
        else None
    ),
    "bounded_probe_authority_patch_readiness_artifact_path": os.environ["BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT"],
    "bounded_probe_authority_patch_readiness_latest_path": os.environ["BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_LATEST"],
    "bounded_probe_authority_patch_readiness_sha256": bounded_authority_sha,
    "bounded_probe_authority_patch_readiness_error": bounded_authority_err,
    "bounded_probe_authority_patch_readiness_skip_reason": os.environ["BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_SKIP_REASON"] or None,
    "bounded_probe_authority_patch_readiness_status": bounded_authority.get("status"),
    "bounded_probe_authority_patch_readiness_reason": bounded_authority.get("reason"),
    "bounded_probe_authority_patch_adapter_present": (
        (bounded_authority.get("answers") or {}).get("rust_near_touch_authority_adapter_present")
        if isinstance(bounded_authority.get("answers"), dict)
        else None
    ),
    "bounded_probe_authority_path_wiring_present": (
        (bounded_authority.get("answers") or {}).get("rust_authority_path_wiring_present")
        if isinstance(bounded_authority.get("answers"), dict)
        else None
    ),
    "bounded_probe_operator_authorization_artifact_path": os.environ["BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT"],
    "bounded_probe_operator_authorization_latest_path": os.environ["BOUNDED_PROBE_OPERATOR_AUTHORIZATION_LATEST"],
    "bounded_probe_operator_authorization_sha256": bounded_operator_auth_sha,
    "bounded_probe_operator_authorization_error": bounded_operator_auth_err,
    "bounded_probe_operator_authorization_skip_reason": os.environ["BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SKIP_REASON"] or None,
    "bounded_probe_operator_authorization_status": bounded_operator_auth.get("status"),
    "bounded_probe_operator_authorization_reason": bounded_operator_auth.get("reason"),
    "bounded_probe_operator_authorization_decision": bounded_operator_auth.get("decision"),
    "bounded_probe_operator_authorization_blocking_gate_count": bounded_operator_auth.get("blocking_gate_count"),
    "bounded_probe_operator_authorization_blocking_gates": bounded_operator_auth.get("blocking_gates"),
    "bounded_probe_operator_authorization_ready_for_review": (
        (bounded_operator_auth.get("answers") or {}).get("ready_for_operator_authorization_review")
        if isinstance(bounded_operator_auth.get("answers"), dict)
        else None
    ),
    "bounded_probe_operator_authorization_object_emitted": (
        (bounded_operator_auth.get("answers") or {}).get("operator_authorization_object_emitted")
        if isinstance(bounded_operator_auth.get("answers"), dict)
        else None
    ),
    "bounded_probe_operator_authorization_active_runtime_order_authority": (
        (bounded_operator_auth.get("answers") or {}).get("active_runtime_order_authority")
        if isinstance(bounded_operator_auth.get("answers"), dict)
        else None
    ),
    "bounded_probe_operator_authorization_typed_confirm_expected": bounded_operator_auth.get("typed_confirm_expected"),
    "bounded_probe_operator_authorization_source_candidate_max_probe_orders": bounded_operator_auth.get("source_candidate_max_probe_orders"),
    "bounded_probe_shadow_placement_impact_artifact_path": os.environ["BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT"],
    "bounded_probe_shadow_placement_impact_latest_path": os.environ["BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_LATEST"],
    "bounded_probe_shadow_placement_impact_sha256": bounded_shadow_sha,
    "bounded_probe_shadow_placement_impact_error": bounded_shadow_err,
    "bounded_probe_shadow_placement_impact_skip_reason": os.environ["BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_SKIP_REASON"] or None,
    "bounded_probe_shadow_placement_impact_status": bounded_shadow.get("status"),
    "bounded_probe_shadow_placement_impact_reason": bounded_shadow.get("reason"),
    "bounded_probe_shadow_placement_impact_sample_scope": (
        (bounded_shadow.get("shadow_summary") or {}).get("sample_scope")
        if isinstance(bounded_shadow.get("shadow_summary"), dict)
        else None
    ),
    "bounded_probe_shadow_placement_submit_count": (
        (bounded_shadow.get("shadow_summary") or {}).get("shadow_submit_count")
        if isinstance(bounded_shadow.get("shadow_summary"), dict)
        else None
    ),
    "bounded_probe_shadow_placement_skip_count": (
        (bounded_shadow.get("shadow_summary") or {}).get("shadow_skip_count")
        if isinstance(bounded_shadow.get("shadow_summary"), dict)
        else None
    ),
    "bounded_probe_shadow_placement_candidate_matched_order_count": (
        (bounded_shadow.get("shadow_summary") or {}).get("candidate_matched_order_count")
        if isinstance(bounded_shadow.get("shadow_summary"), dict)
        else None
    ),
    "bounded_probe_shadow_placement_max_shadow_initial_touch_gap_bps": (
        (bounded_shadow.get("shadow_summary") or {}).get("max_shadow_initial_touch_gap_bps")
        if isinstance(bounded_shadow.get("shadow_summary"), dict)
        else None
    ),
    "bounded_probe_shadow_placement_max_gap_reduction_bps": (
        (bounded_shadow.get("shadow_summary") or {}).get("max_gap_reduction_bps")
        if isinstance(bounded_shadow.get("shadow_summary"), dict)
        else None
    ),
    "bounded_probe_result_review_artifact_path": os.environ["BOUNDED_PROBE_RESULT_REVIEW_OUT"],
    "bounded_probe_result_review_latest_path": os.environ["BOUNDED_PROBE_RESULT_REVIEW_LATEST"],
    "bounded_probe_result_review_sha256": bounded_result_sha,
    "bounded_probe_result_review_error": bounded_result_err,
    "bounded_probe_result_review_skip_reason": os.environ["BOUNDED_PROBE_RESULT_REVIEW_SKIP_REASON"] or None,
    "bounded_probe_result_review_status": bounded_result.get("status"),
    "bounded_probe_result_review_reason": bounded_result.get("reason"),
    "bounded_probe_result_review_side_cell_key": bounded_result.get("side_cell_key"),
    "bounded_probe_result_review_completed_probe_outcome_count": (
        (bounded_result.get("probe_result_summary") or {}).get("completed_probe_outcome_count")
        if isinstance(bounded_result.get("probe_result_summary"), dict)
        else None
    ),
    "bounded_probe_result_review_avg_realized_net_bps": (
        (bounded_result.get("probe_result_summary") or {}).get("avg_realized_net_bps")
        if isinstance(bounded_result.get("probe_result_summary"), dict)
        else None
    ),
    "bounded_probe_result_review_evidence_quality_status": (
        (bounded_result.get("evidence_quality") or {}).get("status")
        if isinstance(bounded_result.get("evidence_quality"), dict)
        else None
    ),
    "bounded_probe_result_review_probe_execution_gap_bps": (
        (bounded_result.get("evidence_quality") or {}).get("probe_execution_gap_bps")
        if isinstance(bounded_result.get("evidence_quality"), dict)
        else None
    ),
    "bounded_probe_result_review_execution_realism_gap": (
        (bounded_result.get("evidence_quality") or {}).get("execution_realism_gap")
        if isinstance(bounded_result.get("evidence_quality"), dict)
        else None
    ),
    "bounded_probe_execution_realism_review_artifact_path": os.environ["BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_OUT"],
    "bounded_probe_execution_realism_review_latest_path": os.environ["BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_LATEST"],
    "bounded_probe_execution_realism_review_sha256": bounded_exec_sha,
    "bounded_probe_execution_realism_review_error": bounded_exec_err,
    "bounded_probe_execution_realism_review_skip_reason": os.environ["BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_SKIP_REASON"] or None,
    "bounded_probe_execution_realism_review_status": bounded_exec.get("status"),
    "bounded_probe_execution_realism_review_reason": bounded_exec.get("reason"),
    "bounded_probe_execution_realism_review_primary_hypothesis": (
        (bounded_exec.get("execution_gap_hypotheses") or [{}])[0].get("kind")
        if isinstance(bounded_exec.get("execution_gap_hypotheses"), list)
        and bounded_exec.get("execution_gap_hypotheses")
        and isinstance((bounded_exec.get("execution_gap_hypotheses") or [{}])[0], dict)
        else None
    ),
    "bounded_probe_execution_realism_review_net_capture_gap_bps": (
        (bounded_exec.get("gap_decomposition") or {}).get("net_capture_gap_bps")
        if isinstance(bounded_exec.get("gap_decomposition"), dict)
        else None
    ),
    "bounded_probe_execution_realism_review_probe_fill_backed_pct": (
        (bounded_exec.get("probe_execution_summary") or {}).get("fill_backed_pct")
        if isinstance(bounded_exec.get("probe_execution_summary"), dict)
        else None
    ),
    "bounded_probe_execution_realism_review_cost_gate_or_operator_review_allowed": (
        (bounded_exec.get("answers") or {}).get("cost_gate_or_operator_review_allowed")
        if isinstance(bounded_exec.get("answers"), dict)
        else None
    ),
    "boundary": "artifact_only_readonly_pg_jsonl_ledger_no_order_no_cost_gate_relaxation",
}
print(json.dumps(status, ensure_ascii=False, sort_keys=True))
PY
)
if [[ -n "$STATUS_JSON" ]]; then
    echo "$STATUS_JSON" >> "$STATUS_LOG"
fi

echo "[$(ts)] === Cost-gate learning lane refresh end scorecard_rc=${scorecard_rc} plan_rc=${plan_rc} historical_review_rc=${historical_review_rc} materializer_rc=${materializer_rc} refresh_rc=${refresh_rc} review_rc=${review_rc} false_negative_candidate_packet_rc=${false_negative_candidate_packet_rc} false_negative_operator_review_rc=${false_negative_operator_review_rc} sealed_horizon_learning_evidence_rc=${sealed_horizon_learning_evidence_rc} order_touchability_audit_rc=${order_touchability_audit_rc} bounded_probe_touchability_preflight_rc=${bounded_probe_touchability_preflight_rc} bounded_probe_placement_repair_plan_rc=${bounded_probe_placement_repair_plan_rc} bounded_probe_authority_patch_readiness_rc=${bounded_probe_authority_patch_readiness_rc} bounded_probe_operator_authorization_rc=${bounded_probe_operator_authorization_rc} bounded_probe_shadow_placement_impact_rc=${bounded_probe_shadow_placement_impact_rc} bounded_probe_result_review_rc=${bounded_probe_result_review_rc} bounded_probe_execution_realism_review_rc=${bounded_probe_execution_realism_review_rc} ===" >> "$LOG"

# fail-soft: rc/status are recorded; alpha-discovery reads artifacts and ledger
# state. Operator action is required for deploy, writer enablement, or probe authority.
exit 0
