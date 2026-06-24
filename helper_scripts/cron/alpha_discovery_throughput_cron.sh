#!/usr/bin/env bash
# alpha_discovery_throughput_cron.sh — artifact-only alpha discovery killboard.
#
# Runs the read-only runtime artifact runner. It only writes local discovery
# artifacts/logs/heartbeat under OPENCLAW_DATA_DIR; it does not connect to DB,
# Bybit, auth, risk, or order paths.
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/alpha_discovery_throughput_cron.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/alpha_discovery_throughput_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$HEARTBEAT_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

export OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$BASE}"
export OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-$DATA}"

EXPECTED_SOURCE_HEAD="${OPENCLAW_EXPECTED_SOURCE_HEAD:-${OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD:-${OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD:-}}}"

if [[ -d "$LOCK_DIR" ]] && [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +20 2>/dev/null)" ]]; then
    echo "[$(ts)] WARN: stale lock (>20min) cleared: $LOCK_DIR" >> "$LOG"
    rmdir "$LOCK_DIR" 2>/dev/null || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: alpha discovery throughput already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

touch "$HEARTBEAT_DIR/alpha_discovery_throughput.last_fire"

if [[ ! -d "$BASE/helper_scripts/research/alpha_discovery_throughput" ]]; then
    echo "[$(ts)] ERROR: alpha_discovery_throughput package not found under BASE=$BASE" >> "$LOG"
    exit 0
fi

PYBIN="${OPENCLAW_PYTHON_BIN:-}"
if [[ -z "$PYBIN" ]]; then
    if [[ -x "$HOME/.venv/bin/python" ]]; then
        PYBIN="$HOME/.venv/bin/python"
    else
        PYBIN="python3"
    fi
fi

echo "[$(ts)] === alpha_discovery_throughput start ===" >> "$LOG"
PACKET_SCRIPT="$BASE/helper_scripts/cron/demo_learning_stack_activation_packet.py"
PACKET_DIR="$DATA/demo_learning_stack_activation_packet"
if [[ -f "$PACKET_SCRIPT" ]]; then
    mkdir -p "$PACKET_DIR"
    packet_rc=0
    "$PYBIN" "$PACKET_SCRIPT" \
        --data-dir "$DATA" \
        --repo-root "$BASE" \
        --python-bin "$PYBIN" \
        --json-output "$PACKET_DIR/demo_learning_stack_activation_packet_latest.json" \
        > "$PACKET_DIR/demo_learning_stack_activation_packet_stdout.json" 2>> "$LOG" || packet_rc=$?
    echo "[$(ts)] activation_packet_refresh rc=${packet_rc}" >> "$LOG"
else
    echo "[$(ts)] WARN: activation packet script not found: $PACKET_SCRIPT" >> "$LOG"
fi
DRY_RUN_SCRIPT="$BASE/helper_scripts/cron/demo_learning_stack_dry_run_review.py"
DRY_RUN_DIR="$DATA/demo_learning_stack_dry_run_review"
if [[ -f "$DRY_RUN_SCRIPT" ]]; then
    mkdir -p "$DRY_RUN_DIR"
    dry_run_rc=0
    "$PYBIN" "$DRY_RUN_SCRIPT" \
        --data-dir "$DATA" \
        --repo-root "$BASE" \
        --python-bin "$PYBIN" \
        --json-output "$DRY_RUN_DIR/demo_learning_stack_dry_run_review_latest.json" \
        > "$DRY_RUN_DIR/demo_learning_stack_dry_run_review_stdout.json" 2>> "$LOG" || dry_run_rc=$?
    echo "[$(ts)] dry_run_review_refresh rc=${dry_run_rc}" >> "$LOG"
else
    echo "[$(ts)] WARN: dry-run review script not found: $DRY_RUN_SCRIPT" >> "$LOG"
fi
PROFITABILITY_DIR="$DATA/alpha_discovery_throughput"
PROFITABILITY_JSON="$PROFITABILITY_DIR/profitability_path_scorecard_latest.json"
PROFITABILITY_MD="$PROFITABILITY_DIR/profitability_path_scorecard_latest.md"
MM_CURRENT_FEE_CONFIRMATION_JSON="$PROFITABILITY_DIR/mm_current_fee_confirmation_latest.json"
MM_CURRENT_FEE_CONFIRMATION_MD="$PROFITABILITY_DIR/mm_current_fee_confirmation_latest.md"
MM_CURRENT_FEE_CONFIRMATION_STDOUT="$PROFITABILITY_DIR/mm_current_fee_confirmation_stdout.json"
MM_MOTIF_AMPLIFICATION_JSON="$PROFITABILITY_DIR/mm_motif_amplification_latest.json"
MM_MOTIF_AMPLIFICATION_MD="$PROFITABILITY_DIR/mm_motif_amplification_latest.md"
MM_MOTIF_AMPLIFICATION_STDOUT="$PROFITABILITY_DIR/mm_motif_amplification_stdout.json"
mkdir -p "$PROFITABILITY_DIR"
PROFITABILITY_ARGS=()
add_profitability_json_arg() {
    local flag="$1"
    local path="$2"
    if [[ -f "$path" ]]; then
        PROFITABILITY_ARGS+=("$flag" "$path")
    fi
}
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
canonical_or_latest_matching_path() {
    local canonical="$1"
    shift
    if [[ -f "$canonical" ]]; then
        printf '%s' "$canonical"
        return
    fi
    latest_matching_path "$@"
}
HORIZON_SEALED_REPLAY_JSON="$(canonical_or_latest_matching_path \
    "$DATA"/cost_gate_learning_lane/horizon_specific_sealed_replay_latest.json \
    "$DATA"/profitability_refresh/*/horizon_specific_sealed_replay/horizon_specific_sealed_replay_latest.json)"
HORIZON_LEARNING_EVIDENCE_JSON="$(canonical_or_latest_matching_path \
    "$DATA"/cost_gate_learning_lane/sealed_horizon_learning_evidence_latest.json \
    "$DATA"/profitability_refresh/*/sealed_horizon_learning_evidence*/sealed_horizon_learning_evidence_latest.json)"
SEALED_OPERATOR_REVIEW_DIR="$DATA/cost_gate_learning_lane"
SEALED_OPERATOR_REVIEW_JSON="$SEALED_OPERATOR_REVIEW_DIR/sealed_horizon_operator_review_latest.json"
SEALED_OPERATOR_REVIEW_MD="$SEALED_OPERATOR_REVIEW_DIR/sealed_horizon_operator_review_latest.md"
SEALED_OPERATOR_REVIEW_STDOUT="$SEALED_OPERATOR_REVIEW_DIR/sealed_horizon_operator_review_stdout.json"
SEALED_OPERATOR_REVIEW_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_SEALED_OPERATOR_REVIEW_MAX_ARTIFACT_AGE_HOURS:-24}"
SEALED_PREFLIGHT_SCRIPT="$BASE/helper_scripts/cron/sealed_horizon_probe_preflight_cron.sh"
BOUNDED_REVIEW_CHAIN_DIR="$DATA/cost_gate_learning_lane"
BOUNDED_REVIEW_CHAIN_STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
REFRESH_BOUNDED_REVIEW_CHAIN="${OPENCLAW_ALPHA_REFRESH_BOUNDED_PROBE_REVIEW_CHAIN:-1}"
ORDER_TOUCHABILITY_JSON="${OPENCLAW_ALPHA_ORDER_TO_FILL_GAP_AUDIT_JSON:-${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_AUDIT_JSON:-$DATA/demo_order_to_fill_gap/demo_order_to_fill_gap_latest.json}}"
SEALED_PREFLIGHT_JSON="$DATA/cost_gate_learning_lane/sealed_horizon_probe_preflight_latest.json"
FALSE_NEGATIVE_BOUNDED_PREFLIGHT_JSON="$DATA/cost_gate_learning_lane/false_negative_bounded_probe_preflight_latest.json"
if [[ -n "${OPENCLAW_ALPHA_BOUNDED_PROBE_PREFLIGHT_JSON:-}" ]]; then
    BOUNDED_PROBE_PREFLIGHT_JSON="$OPENCLAW_ALPHA_BOUNDED_PROBE_PREFLIGHT_JSON"
elif [[ -f "$FALSE_NEGATIVE_BOUNDED_PREFLIGHT_JSON" ]]; then
    BOUNDED_PROBE_PREFLIGHT_JSON="$FALSE_NEGATIVE_BOUNDED_PREFLIGHT_JSON"
else
    BOUNDED_PROBE_PREFLIGHT_JSON="$SEALED_PREFLIGHT_JSON"
fi
BOUNDED_REVIEW_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_ALPHA_BOUNDED_REVIEW_MAX_ARTIFACT_AGE_HOURS:-24}"
TOUCHABILITY_MAX_INITIAL_PASSIVE_GAP_BPS="${OPENCLAW_ALPHA_TOUCHABILITY_MAX_INITIAL_PASSIVE_GAP_BPS:-75.0}"
TOUCHABILITY_MAX_DEEP_NO_TOUCH_GAP_BPS="${OPENCLAW_ALPHA_TOUCHABILITY_MAX_DEEP_NO_TOUCH_GAP_BPS:-500.0}"
PLACEMENT_REPAIR_MAX_FRESH_BBO_AGE_MS="${OPENCLAW_ALPHA_PLACEMENT_REPAIR_MAX_FRESH_BBO_AGE_MS:-1000}"
BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_touchability_preflight_${BOUNDED_REVIEW_CHAIN_STAMP}.json"
BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_MD_OUT="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_touchability_preflight_${BOUNDED_REVIEW_CHAIN_STAMP}.md"
BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_LATEST="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_touchability_preflight_latest.json"
BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_MD_LATEST="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_touchability_preflight_latest.md"
BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_STDOUT="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_touchability_preflight_stdout.json"
BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_placement_repair_plan_${BOUNDED_REVIEW_CHAIN_STAMP}.json"
BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_MD_OUT="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_placement_repair_plan_${BOUNDED_REVIEW_CHAIN_STAMP}.md"
BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_LATEST="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_placement_repair_plan_latest.json"
BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_MD_LATEST="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_placement_repair_plan_latest.md"
BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_STDOUT="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_placement_repair_plan_stdout.json"
BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_authority_patch_readiness_${BOUNDED_REVIEW_CHAIN_STAMP}.json"
BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_MD_OUT="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_authority_patch_readiness_${BOUNDED_REVIEW_CHAIN_STAMP}.md"
BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_LATEST="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_authority_patch_readiness_latest.json"
BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_MD_LATEST="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_authority_patch_readiness_latest.md"
BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_STDOUT="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_authority_patch_readiness_stdout.json"
BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_operator_authorization_${BOUNDED_REVIEW_CHAIN_STAMP}.json"
BOUNDED_PROBE_OPERATOR_AUTHORIZATION_MD_OUT="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_operator_authorization_${BOUNDED_REVIEW_CHAIN_STAMP}.md"
BOUNDED_PROBE_OPERATOR_AUTHORIZATION_LATEST="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_operator_authorization_latest.json"
BOUNDED_PROBE_OPERATOR_AUTHORIZATION_MD_LATEST="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_operator_authorization_latest.md"
BOUNDED_PROBE_OPERATOR_AUTHORIZATION_STDOUT="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_operator_authorization_stdout.json"
BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_shadow_placement_impact_${BOUNDED_REVIEW_CHAIN_STAMP}.json"
BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_MD_OUT="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_shadow_placement_impact_${BOUNDED_REVIEW_CHAIN_STAMP}.md"
BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_LATEST="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_shadow_placement_impact_latest.json"
BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_MD_LATEST="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_shadow_placement_impact_latest.md"
BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_STDOUT="${BOUNDED_REVIEW_CHAIN_DIR}/bounded_probe_shadow_placement_impact_stdout.json"
sealed_operator_review_rc=0
if [[ -n "$HORIZON_LEARNING_EVIDENCE_JSON" && -f "$HORIZON_LEARNING_EVIDENCE_JSON" ]]; then
    mkdir -p "$SEALED_OPERATOR_REVIEW_DIR"
    SEALED_OPERATOR_REVIEW_ARGS=(
        -m cost_gate_learning_lane.sealed_horizon_operator_review
        --sealed-horizon-learning-evidence-json "$HORIZON_LEARNING_EVIDENCE_JSON"
        --decision defer
        --max-artifact-age-hours "$SEALED_OPERATOR_REVIEW_MAX_ARTIFACT_AGE_HOURS"
        --json-output "$SEALED_OPERATOR_REVIEW_JSON"
        --output "$SEALED_OPERATOR_REVIEW_MD"
    )
    if [[ -f "$DATA/cost_gate_learning_lane/sealed_horizon_probe_preflight_latest.json" ]]; then
        SEALED_OPERATOR_REVIEW_ARGS+=(
            --preflight-json "$DATA/cost_gate_learning_lane/sealed_horizon_probe_preflight_latest.json"
        )
    fi
    (
        cd "$BASE/helper_scripts/research"
        "$PYBIN" "${SEALED_OPERATOR_REVIEW_ARGS[@]}"
    ) > "$SEALED_OPERATOR_REVIEW_STDOUT" 2>> "$LOG" || sealed_operator_review_rc=$?
    echo "[$(ts)] sealed_horizon_operator_review_refresh rc=${sealed_operator_review_rc}" >> "$LOG"
else
    echo "[$(ts)] SKIP: sealed horizon operator review refresh missing learning evidence" >> "$LOG"
fi
sealed_preflight_rc=0
if [[ -x "$SEALED_PREFLIGHT_SCRIPT" && -n "$HORIZON_LEARNING_EVIDENCE_JSON" && -f "$HORIZON_LEARNING_EVIDENCE_JSON" ]]; then
    (
        cd "$BASE"
        OPENCLAW_SEALED_HORIZON_LEARNING_EVIDENCE_JSON="$HORIZON_LEARNING_EVIDENCE_JSON" \
        OPENCLAW_SEALED_HORIZON_OPERATOR_REVIEW_JSON="$SEALED_OPERATOR_REVIEW_JSON" \
        OPENCLAW_SEALED_HORIZON_DECISION_PACKET_JSON="$DATA/cost_gate_learning_lane/profit_learning_decision_packet_latest.json" \
        "$SEALED_PREFLIGHT_SCRIPT"
    ) >> "$LOG" 2>&1 || sealed_preflight_rc=$?
    echo "[$(ts)] sealed_horizon_probe_preflight_refresh rc=${sealed_preflight_rc}" >> "$LOG"
else
    echo "[$(ts)] SKIP: sealed horizon probe preflight refresh missing script or learning evidence" >> "$LOG"
fi
bounded_probe_touchability_preflight_rc=0
bounded_probe_placement_repair_plan_rc=0
bounded_probe_authority_patch_readiness_rc=0
bounded_probe_operator_authorization_rc=0
bounded_probe_shadow_placement_impact_rc=0
if [[ "$REFRESH_BOUNDED_REVIEW_CHAIN" == "1" ]]; then
    if [[ -f "$BOUNDED_PROBE_PREFLIGHT_JSON" && -f "$ORDER_TOUCHABILITY_JSON" ]]; then
        mkdir -p "$BOUNDED_REVIEW_CHAIN_DIR"
        (
            cd "$BASE/helper_scripts/research"
            "$PYBIN" -m cost_gate_learning_lane.bounded_probe_touchability_preflight \
                --preflight-json "$BOUNDED_PROBE_PREFLIGHT_JSON" \
                --order-to-fill-gap-json "$ORDER_TOUCHABILITY_JSON" \
                --max-artifact-age-hours "$BOUNDED_REVIEW_MAX_ARTIFACT_AGE_HOURS" \
                --max-initial-passive-gap-bps "$TOUCHABILITY_MAX_INITIAL_PASSIVE_GAP_BPS" \
                --max-deep-no-touch-gap-bps "$TOUCHABILITY_MAX_DEEP_NO_TOUCH_GAP_BPS" \
                --json-output "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT" \
                --output "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_MD_OUT"
        ) > "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_STDOUT" 2>> "$LOG" || bounded_probe_touchability_preflight_rc=$?
        if [[ -f "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT" ]]; then
            cp "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT" "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_LATEST"
            if [[ -f "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_MD_OUT" ]]; then
                cp "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_MD_OUT" "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_MD_LATEST"
            fi
        fi
        echo "[$(ts)] bounded_probe_touchability_preflight_refresh rc=${bounded_probe_touchability_preflight_rc}" >> "$LOG"

        if [[ -f "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT" ]]; then
            (
                cd "$BASE/helper_scripts/research"
                "$PYBIN" -m cost_gate_learning_lane.bounded_probe_placement_repair_plan \
                    --touchability-preflight-json "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT" \
                    --max-artifact-age-hours "$BOUNDED_REVIEW_MAX_ARTIFACT_AGE_HOURS" \
                    --max-fresh-bbo-age-ms "$PLACEMENT_REPAIR_MAX_FRESH_BBO_AGE_MS" \
                    --json-output "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT" \
                    --output "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_MD_OUT"
            ) > "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_STDOUT" 2>> "$LOG" || bounded_probe_placement_repair_plan_rc=$?
            if [[ -f "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT" ]]; then
                cp "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT" "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_LATEST"
                if [[ -f "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_MD_OUT" ]]; then
                    cp "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_MD_OUT" "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_MD_LATEST"
                fi
            fi
            echo "[$(ts)] bounded_probe_placement_repair_plan_refresh rc=${bounded_probe_placement_repair_plan_rc}" >> "$LOG"
        else
            echo "[$(ts)] SKIP: bounded probe placement repair plan missing touchability preflight output" >> "$LOG"
        fi

        if [[ -f "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT" ]]; then
            (
                cd "$BASE/helper_scripts/research"
                "$PYBIN" -m cost_gate_learning_lane.bounded_probe_authority_patch_readiness \
                    --placement-repair-plan-json "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT" \
                    --repo-root "$BASE" \
                    --max-artifact-age-hours "$BOUNDED_REVIEW_MAX_ARTIFACT_AGE_HOURS" \
                    --json-output "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT" \
                    --output "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_MD_OUT"
            ) > "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_STDOUT" 2>> "$LOG" || bounded_probe_authority_patch_readiness_rc=$?
            if [[ -f "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT" ]]; then
                cp "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT" "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_LATEST"
                if [[ -f "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_MD_OUT" ]]; then
                    cp "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_MD_OUT" "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_MD_LATEST"
                fi
            fi
            echo "[$(ts)] bounded_probe_authority_patch_readiness_refresh rc=${bounded_probe_authority_patch_readiness_rc}" >> "$LOG"

            (
                cd "$BASE/helper_scripts/research"
                "$PYBIN" -m cost_gate_learning_lane.bounded_probe_operator_authorization_cli \
                    --preflight-json "$BOUNDED_PROBE_PREFLIGHT_JSON" \
                    --placement-repair-plan-json "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT" \
                    --authority-patch-readiness-json "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT" \
                    --decision defer \
                    --max-artifact-age-hours "$BOUNDED_REVIEW_MAX_ARTIFACT_AGE_HOURS" \
                    --json-output "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT" \
                    --output "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_MD_OUT"
            ) > "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_STDOUT" 2>> "$LOG" || bounded_probe_operator_authorization_rc=$?
            if [[ -f "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT" ]]; then
                cp "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT" "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_LATEST"
                if [[ -f "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_MD_OUT" ]]; then
                    cp "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_MD_OUT" "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_MD_LATEST"
                fi
            fi
            echo "[$(ts)] bounded_probe_operator_authorization_refresh rc=${bounded_probe_operator_authorization_rc}" >> "$LOG"

            (
                cd "$BASE/helper_scripts/research"
                "$PYBIN" -m cost_gate_learning_lane.bounded_probe_shadow_placement_impact \
                    --order-to-fill-gap-json "$ORDER_TOUCHABILITY_JSON" \
                    --placement-repair-plan-json "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT" \
                    --authority-patch-readiness-json "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT" \
                    --max-artifact-age-hours "$BOUNDED_REVIEW_MAX_ARTIFACT_AGE_HOURS" \
                    --json-output "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT" \
                    --output "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_MD_OUT"
            ) > "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_STDOUT" 2>> "$LOG" || bounded_probe_shadow_placement_impact_rc=$?
            if [[ -f "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT" ]]; then
                cp "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT" "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_LATEST"
                if [[ -f "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_MD_OUT" ]]; then
                    cp "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_MD_OUT" "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_MD_LATEST"
                fi
            fi
            echo "[$(ts)] bounded_probe_shadow_placement_impact_refresh rc=${bounded_probe_shadow_placement_impact_rc}" >> "$LOG"
        else
            echo "[$(ts)] SKIP: bounded probe authority/operator/shadow refresh missing placement repair plan output" >> "$LOG"
        fi
    else
        echo "[$(ts)] SKIP: bounded probe review chain missing bounded preflight (${BOUNDED_PROBE_PREFLIGHT_JSON}) or order-to-fill audit" >> "$LOG"
    fi
else
    echo "[$(ts)] SKIP: bounded probe review chain disabled by OPENCLAW_ALPHA_REFRESH_BOUNDED_PROBE_REVIEW_CHAIN=${REFRESH_BOUNDED_REVIEW_CHAIN}" >> "$LOG"
fi
MM_CURRENT_FEE_CONFIRMATION_ARGS=()
if [[ -f "$DATA/research/fillsim/fillsim_report.json" ]]; then
    MM_CURRENT_FEE_CONFIRMATION_ARGS+=(
        --fillsim-json "$DATA/research/fillsim/fillsim_report.json"
    )
fi
if [[ -f "$DATA/research/fillsim/fillsim_history_scorecard.json" ]]; then
    MM_CURRENT_FEE_CONFIRMATION_ARGS+=(
        --fillsim-history-json "$DATA/research/fillsim/fillsim_history_scorecard.json"
    )
fi
mm_current_fee_confirmation_rc=0
if (( ${#MM_CURRENT_FEE_CONFIRMATION_ARGS[@]} > 0 )); then
    (
        cd "$BASE/helper_scripts/research"
        "$PYBIN" -m alpha_discovery_throughput.mm_current_fee_confirmation \
            "${MM_CURRENT_FEE_CONFIRMATION_ARGS[@]}" \
            --json-output "$MM_CURRENT_FEE_CONFIRMATION_JSON" \
            --output "$MM_CURRENT_FEE_CONFIRMATION_MD"
    ) > "$MM_CURRENT_FEE_CONFIRMATION_STDOUT" 2>> "$LOG" || mm_current_fee_confirmation_rc=$?
    echo "[$(ts)] mm_current_fee_confirmation_refresh rc=${mm_current_fee_confirmation_rc}" >> "$LOG"
else
    echo "[$(ts)] SKIP: mm current-fee confirmation refresh missing fillsim inputs" >> "$LOG"
fi
mm_motif_amplification_rc=0
if [[ -f "$DATA/research/fillsim/fillsim_history_scorecard.json" ]]; then
    (
        cd "$BASE/helper_scripts/research"
        "$PYBIN" -m alpha_discovery_throughput.mm_motif_amplification \
            --fillsim-history-json "$DATA/research/fillsim/fillsim_history_scorecard.json" \
            --json-output "$MM_MOTIF_AMPLIFICATION_JSON" \
            --output "$MM_MOTIF_AMPLIFICATION_MD"
    ) > "$MM_MOTIF_AMPLIFICATION_STDOUT" 2>> "$LOG" || mm_motif_amplification_rc=$?
    echo "[$(ts)] mm_motif_amplification_refresh rc=${mm_motif_amplification_rc}" >> "$LOG"
else
    echo "[$(ts)] SKIP: mm motif amplification refresh missing fillsim history scorecard" >> "$LOG"
fi
add_profitability_json_arg "--cost-gate-counterfactual-json" "$DATA/cost_gate_counterfactual/cost_gate_reject_counterfactual_latest.json"
add_profitability_json_arg "--profit-learning-packet-json" "$DATA/cost_gate_learning_lane/profit_learning_decision_packet_latest.json"
add_profitability_json_arg "--learning-plan-json" "$DATA/cost_gate_learning_lane/demo_learning_lane_plan_latest.json"
add_profitability_json_arg "--activation-preflight-json" "$DATA/cost_gate_learning_lane/activation_preflight_latest.json"
add_profitability_json_arg "--demo-learning-stack-activation-packet-json" "$DATA/demo_learning_stack_activation_packet/demo_learning_stack_activation_packet_latest.json"
add_profitability_json_arg "--demo-learning-stack-dry-run-review-json" "$DATA/demo_learning_stack_dry_run_review/demo_learning_stack_dry_run_review_latest.json"
add_profitability_json_arg "--horizon-sealed-replay-json" "$HORIZON_SEALED_REPLAY_JSON"
add_profitability_json_arg "--horizon-learning-evidence-json" "$HORIZON_LEARNING_EVIDENCE_JSON"
add_profitability_json_arg "--sealed-horizon-operator-review-json" "$SEALED_OPERATOR_REVIEW_JSON"
add_profitability_json_arg "--sealed-horizon-probe-preflight-json" "$SEALED_PREFLIGHT_JSON"
add_profitability_json_arg "--bounded-probe-preflight-json" "$BOUNDED_PROBE_PREFLIGHT_JSON"
add_profitability_json_arg "--bounded-probe-shadow-placement-impact-json" "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_LATEST"
add_profitability_json_arg "--bounded-probe-operator-authorization-json" "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_LATEST"
add_profitability_json_arg "--bounded-probe-result-review-json" "$DATA/cost_gate_learning_lane/bounded_probe_result_review_latest.json"
add_profitability_json_arg "--bounded-probe-execution-realism-review-json" "$DATA/cost_gate_learning_lane/bounded_probe_execution_realism_review_latest.json"
add_profitability_json_arg "--fillsim-json" "$DATA/research/fillsim/fillsim_report.json"
add_profitability_json_arg "--fillsim-history-json" "$DATA/research/fillsim/fillsim_history_scorecard.json"
add_profitability_json_arg "--polymarket-leadlag-json" "$DATA/research/polymarket_leadlag/polymarket_leadlag_latest.json"
add_profitability_json_arg "--gate-b-watch-json" "$DATA/gate_b_watch/gate_b_watch_latest.json"
profitability_rc=0
(
    cd "$BASE/helper_scripts/research"
    if (( ${#PROFITABILITY_ARGS[@]} > 0 )); then
        "$PYBIN" -m alpha_discovery_throughput.profitability_path_scorecard \
            "${PROFITABILITY_ARGS[@]}" \
            --json-output "$PROFITABILITY_JSON" \
            --output "$PROFITABILITY_MD"
    else
        "$PYBIN" -m alpha_discovery_throughput.profitability_path_scorecard \
            --json-output "$PROFITABILITY_JSON" \
            --output "$PROFITABILITY_MD"
    fi
) > "$PROFITABILITY_DIR/profitability_path_scorecard_stdout.json" 2>> "$LOG" || profitability_rc=$?
echo "[$(ts)] profitability_path_scorecard_refresh rc=${profitability_rc}" >> "$LOG"
rc=0
(
    cd "$BASE/helper_scripts/research"
    if [[ -n "$EXPECTED_SOURCE_HEAD" ]]; then
        "$PYBIN" -m alpha_discovery_throughput.runtime_runner \
            --data-dir "$DATA" \
            --repo-root "$BASE" \
            --expected-head "$EXPECTED_SOURCE_HEAD" \
            --print-json
    else
        "$PYBIN" -m alpha_discovery_throughput.runtime_runner \
            --data-dir "$DATA" \
            --repo-root "$BASE" \
            --print-json
    fi
) >> "$LOG" 2>&1 || rc=$?
echo "[$(ts)] === alpha_discovery_throughput end rc=${rc} ===" >> "$LOG"

exit 0
