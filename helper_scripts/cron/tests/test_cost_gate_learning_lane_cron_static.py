"""Static contract tests for the cost-gate learning-lane cron wrapper."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

CRON_DIR = Path(__file__).resolve().parents[1]
WRAPPER = CRON_DIR / "cost_gate_learning_lane_cron.sh"
INSTALLER = CRON_DIR / "install_cost_gate_learning_lane_cron.sh"


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("script", [WRAPPER, INSTALLER], ids=["wrapper", "installer"])
def test_bash_syntax_ok(script: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("script", [WRAPPER, INSTALLER], ids=["wrapper", "installer"])
def test_scripts_executable_and_strict_mode(script: Path) -> None:
    assert script.stat().st_mode & 0o111, f"{script.name} not executable"
    assert "set -euo pipefail" in _src(script)


def test_wrapper_readonly_pg_and_artifact_only_status() -> None:
    src = _src(WRAPPER)
    assert "basic_system_services.env" in src
    assert "POSTGRES_PASSWORD" in src
    assert 'PGOPTIONS="-c default_transaction_read_only=on"' in src
    assert "cost_gate_learning_lane_cron.lock.d" in src
    assert "cost_gate_learning_lane.last_fire" in src
    assert "cost_gate_learning_lane_cron.log" in src
    assert "cost_gate_learning_lane.log" in src
    assert "probe_ledger.jsonl" in src
    assert "demo_data_flow_monitor_latest.json" in src
    assert "demo_data_flow_monitor_${STAMP}.json" in src
    assert "demo_order_to_fill_gap_${STAMP}.json" in src
    assert "profit_learning_decision_packet_latest.json" in src
    assert "profit_learning_decision_packet_${STAMP}.json" in src
    assert "cost_gate_reject_counterfactual_latest.json" in src
    assert "cost_gate_reject_counterfactual_${STAMP}.json" in src
    assert "demo_learning_lane_plan_latest.json" in src
    assert "demo_learning_lane_plan_${STAMP}.json" in src
    assert "sealed_horizon_probe_preflight_latest.json" in src
    assert "demo_order_to_fill_gap_latest.json" in src
    assert "outcome_refresh_latest.json" in src
    assert "blocked_outcome_review_latest.json" in src
    assert "bounded_probe_touchability_preflight_latest.json" in src
    assert "bounded_probe_placement_repair_plan_latest.json" in src
    assert "bounded_probe_shadow_placement_impact_latest.json" in src
    assert "bounded_probe_result_review_latest.json" in src
    assert "bounded_probe_execution_realism_review_latest.json" in src
    assert "historical_scorecard_review_latest.json" in src
    assert "reject_materializer_latest.json" in src
    assert "cost_gate_reject_counterfactual.py" in src
    assert "demo_data_flow_monitor.py" in src
    assert "demo_order_to_fill_gap_audit.py" in src
    assert "cost_gate_learning_lane.decision_packet" in src
    assert "cost_gate_learning_lane.policy" in src
    assert "cost_gate_learning_lane.reject_materializer" in src
    assert "cost_gate_learning_lane.outcome_refresh" in src
    assert "cost_gate_learning_lane.outcome_review" in src
    assert "cost_gate_learning_lane.bounded_probe_touchability_preflight" in src
    assert "cost_gate_learning_lane.bounded_probe_placement_repair_plan" in src
    assert "cost_gate_learning_lane.bounded_probe_shadow_placement_impact" in src
    assert "cost_gate_learning_lane.bounded_probe_result_review" in src
    assert "cost_gate_learning_lane.bounded_probe_execution_realism_review" in src
    assert "cost_gate_learning_lane.historical_review" in src
    assert "materializer_materialized_record_count" in src
    assert "materializer_appended_record_count" in src
    assert "materializer_decision_counts" in src
    assert "scorecard_status" in src
    assert "scorecard_probe_candidate_count" in src
    assert "scorecard_horizon_stability_status" in src
    assert "scorecard_horizon_stability_next_trigger" in src
    assert "scorecard_horizon_stability_horizons" in src
    assert "data_flow_monitor_status" in src
    assert "data_flow_monitor_key_counts" in src
    assert "order_touchability_audit_status" in src
    assert "order_touchability_audit_counts" in src
    assert "order_touchability_audit_answers" in src
    assert "decision_packet_status" in src
    assert "decision_packet_silent_drop_risk" in src
    assert "decision_packet_data_flow_status" in src
    assert "plan_policy_status" in src
    assert "plan_selected_probe_candidate_count" in src
    assert "preinstall_refresh_only" in src
    assert "review_top_side_cell_key" in src
    assert "review_top_wrongful_block_score" in src
    assert "review_top_net_cost_cushion_bps" in src
    assert "review_top_candidate_side_cell_key" in src
    assert "review_top_candidate_wrongful_block_score" in src
    assert "bounded_probe_result_review_status" in src
    assert "bounded_probe_result_review_skip_reason" in src
    assert "bounded_probe_result_review_execution_realism_gap" in src
    assert "bounded_probe_touchability_preflight_status" in src
    assert "bounded_probe_touchability_repair_required" in src
    assert "bounded_probe_placement_repair_plan_status" in src
    assert "bounded_probe_placement_repair_order_mode" in src
    assert "bounded_probe_placement_repair_ready" in src
    assert "bounded_probe_placement_repair_max_fresh_bbo_age_ms" in src
    assert "bounded_probe_placement_repair_max_initial_passive_gap_bps" in src
    assert "bounded_probe_shadow_placement_impact_status" in src
    assert "bounded_probe_shadow_placement_submit_count" in src
    assert "bounded_probe_shadow_placement_candidate_matched_order_count" in src
    assert "bounded_probe_shadow_placement_max_gap_reduction_bps" in src
    assert "bounded_probe_execution_realism_review_status" in src
    assert "bounded_probe_execution_realism_review_skip_reason" in src
    assert "bounded_probe_execution_realism_review_primary_hypothesis" in src
    assert "bounded_probe_execution_realism_review_cost_gate_or_operator_review_allowed" in src
    assert "--source-pg" in src
    assert "--record-blocked-outcomes" in src
    assert "--data-flow-json" in src
    assert "--counterfactual-json" in src
    assert "--blocked-outcome-review-json" in src
    assert "--preflight-json" in src
    assert "--order-to-fill-gap-json" in src
    assert "--result-review-json" in src
    assert "--append-ledger" in src
    assert "OPENCLAW_COST_GATE_LEARNING_REFRESH_SCORECARD" in src
    assert "OPENCLAW_COST_GATE_REFRESH_DATA_FLOW_MONITOR" in src
    assert "OPENCLAW_COST_GATE_REFRESH_ORDER_TOUCHABILITY_AUDIT" in src
    assert "OPENCLAW_COST_GATE_REFRESH_DECISION_PACKET" in src
    assert "OPENCLAW_COST_GATE_DATA_FLOW_WINDOW_HOURS" in src
    assert "OPENCLAW_COST_GATE_DATA_FLOW_TOP_LIMIT" in src
    assert "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_ENGINE_MODES" in src
    assert "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_LOOKBACK_HOURS" in src
    assert "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_TOUCH_WINDOW_MINUTES" in src
    assert "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_PLACEMENT_WINDOW_SECONDS" in src
    assert "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_TOP_LIMIT" in src
    assert "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_DEEP_GAP_BPS" in src
    assert "OPENCLAW_COST_GATE_LEARNING_REFRESH_PLAN" in src
    assert "OPENCLAW_COST_GATE_LEARNING_PREINSTALL_REFRESH_ONLY" in src
    assert "OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS" in src
    assert "OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS" in src
    assert "OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES" in src
    assert "OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES" in src
    assert "OPENCLAW_COST_GATE_BOUNDED_PROBE_PREFLIGHT_JSON" in src
    assert "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_AUDIT_JSON" in src
    assert "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT" in src
    assert "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN" in src
    assert "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT" in src
    assert "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_RESULT_REVIEW" in src
    assert "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW" in src
    assert "PYTHONDONTWRITEBYTECODE=1" in src
    assert "artifact_only_readonly_pg_jsonl_ledger_no_order_no_cost_gate_relaxation" in src
    assert src.rstrip().endswith("exit 0")


def test_wrapper_fail_soft_defaults_match_learning_lane_review_policy() -> None:
    src = _src(WRAPPER)
    assert 'PG_TIMEFRAME="${OPENCLAW_COST_GATE_LEARNING_PG_TIMEFRAME:-1m}"' in src
    assert 'REFRESH_SCORECARD="${OPENCLAW_COST_GATE_LEARNING_REFRESH_SCORECARD:-1}"' in src
    assert 'REFRESH_DATA_FLOW_MONITOR="${OPENCLAW_COST_GATE_REFRESH_DATA_FLOW_MONITOR:-1}"' in src
    assert 'REFRESH_ORDER_TOUCHABILITY_AUDIT="${OPENCLAW_COST_GATE_REFRESH_ORDER_TOUCHABILITY_AUDIT:-1}"' in src
    assert 'REFRESH_DECISION_PACKET="${OPENCLAW_COST_GATE_REFRESH_DECISION_PACKET:-1}"' in src
    assert 'DATA_FLOW_WINDOW_HOURS="${OPENCLAW_COST_GATE_DATA_FLOW_WINDOW_HOURS:-1,4,24}"' in src
    assert 'DATA_FLOW_TOP_LIMIT="${OPENCLAW_COST_GATE_DATA_FLOW_TOP_LIMIT:-10}"' in src
    assert 'ORDER_TOUCHABILITY_ENGINE_MODES="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_ENGINE_MODES:-demo,live_demo}"' in src
    assert 'ORDER_TOUCHABILITY_LOOKBACK_HOURS="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_LOOKBACK_HOURS:-48}"' in src
    assert 'ORDER_TOUCHABILITY_TOUCH_WINDOW_MINUTES="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_TOUCH_WINDOW_MINUTES:-1440}"' in src
    assert 'ORDER_TOUCHABILITY_PLACEMENT_WINDOW_SECONDS="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_PLACEMENT_WINDOW_SECONDS:-30}"' in src
    assert 'ORDER_TOUCHABILITY_TOP_LIMIT="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_TOP_LIMIT:-50}"' in src
    assert 'ORDER_TOUCHABILITY_DEEP_GAP_BPS="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_DEEP_GAP_BPS:-500.0}"' in src
    assert 'SCORECARD_LOOKBACK_HOURS="${OPENCLAW_COST_GATE_SCORECARD_LOOKBACK_HOURS:-168}"' in src
    assert 'SCORECARD_LIMIT="${OPENCLAW_COST_GATE_SCORECARD_LIMIT:-50000}"' in src
    assert 'REFRESH_PLAN="${OPENCLAW_COST_GATE_LEARNING_REFRESH_PLAN:-1}"' in src
    assert 'PREINSTALL_REFRESH_ONLY="${OPENCLAW_COST_GATE_LEARNING_PREINSTALL_REFRESH_ONLY:-0}"' in src
    assert 'PLAN_MAX_SCORECARD_AGE_HOURS="${OPENCLAW_COST_GATE_PLAN_MAX_SCORECARD_AGE_HOURS:-24}"' in src
    assert 'PLAN_MIN_CANDIDATE_SAMPLE="${OPENCLAW_COST_GATE_PLAN_MIN_CANDIDATE_SAMPLE:-100}"' in src
    assert 'OUTCOME_HORIZON_MINUTES="${OPENCLAW_COST_GATE_LEARNING_OUTCOME_HORIZON_MINUTES:-60}"' in src
    assert 'SCORECARD_HORIZON_MINUTES_LIST="${OPENCLAW_COST_GATE_SCORECARD_HORIZON_MINUTES_LIST:-15,30,60,120,240}"' in src
    assert 'OUTCOME_COST_BPS="${OPENCLAW_COST_GATE_LEARNING_OUTCOME_COST_BPS:-4.0}"' in src
    assert 'MAX_ENTRY_DELAY_MS="${OPENCLAW_COST_GATE_LEARNING_MAX_ENTRY_DELAY_MS:-300000}"' in src
    assert 'HISTORICAL_MAX_SCORECARD_AGE_HOURS="${OPENCLAW_COST_GATE_HISTORICAL_MAX_SCORECARD_AGE_HOURS:-36}"' in src
    assert 'HISTORICAL_MIN_CANDIDATE_SAMPLE="${OPENCLAW_COST_GATE_HISTORICAL_MIN_CANDIDATE_SAMPLE:-100}"' in src
    assert 'MATERIALIZE_REJECTS="${OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS:-1}"' in src
    assert 'APPEND_MATERIALIZED_REJECTS="${OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS:-1}"' in src
    assert 'MATERIALIZER_LOOKBACK_HOURS="${OPENCLAW_COST_GATE_MATERIALIZER_LOOKBACK_HOURS:-4}"' in src
    assert 'MATERIALIZER_LIMIT="${OPENCLAW_COST_GATE_MATERIALIZER_LIMIT:-10000}"' in src
    assert 'APPEND_OUTCOMES="${OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES:-1}"' in src
    assert 'RECORD_PROBE_OUTCOMES="${OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES:-0}"' in src
    assert 'REFRESH_BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT:-1}"' in src
    assert 'REFRESH_BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN:-1}"' in src
    assert 'REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT:-1}"' in src
    assert 'REFRESH_BOUNDED_PROBE_RESULT_REVIEW="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_RESULT_REVIEW:-1}"' in src
    assert 'REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW:-1}"' in src
    assert 'REVIEW_MIN_OUTCOMES="${OPENCLAW_COST_GATE_REVIEW_MIN_OUTCOMES_PER_SIDE_CELL:-3}"' in src
    assert 'REVIEW_MIN_AVG_NET_BPS="${OPENCLAW_COST_GATE_REVIEW_MIN_AVG_NET_BPS:-0.0}"' in src
    assert 'REVIEW_MIN_NET_POSITIVE_PCT="${OPENCLAW_COST_GATE_REVIEW_MIN_NET_POSITIVE_PCT:-60.0}"' in src
    assert 'TOUCHABILITY_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_TOUCHABILITY_MAX_ARTIFACT_AGE_HOURS:-24}"' in src
    assert 'TOUCHABILITY_MAX_INITIAL_PASSIVE_GAP_BPS="${OPENCLAW_COST_GATE_TOUCHABILITY_MAX_INITIAL_PASSIVE_GAP_BPS:-75.0}"' in src
    assert 'TOUCHABILITY_MAX_DEEP_NO_TOUCH_GAP_BPS="${OPENCLAW_COST_GATE_TOUCHABILITY_MAX_DEEP_NO_TOUCH_GAP_BPS:-500.0}"' in src
    assert 'PLACEMENT_REPAIR_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_PLACEMENT_REPAIR_MAX_ARTIFACT_AGE_HOURS:-24}"' in src
    assert 'PLACEMENT_REPAIR_MAX_FRESH_BBO_AGE_MS="${OPENCLAW_COST_GATE_PLACEMENT_REPAIR_MAX_FRESH_BBO_AGE_MS:-1000}"' in src
    assert 'SHADOW_PLACEMENT_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_SHADOW_PLACEMENT_MAX_ARTIFACT_AGE_HOURS:-24}"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_LEARNING_REFRESH_SCORECARD"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_DATA_FLOW_MONITOR"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_ORDER_TOUCHABILITY_AUDIT"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_DECISION_PACKET"' in src
    assert "OPENCLAW_COST_GATE_DATA_FLOW_WINDOW_HOURS must be comma-separated integers" in src
    assert "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_ENGINE_MODES must be comma-separated engine modes" in src
    assert 'validate_int "OPENCLAW_COST_GATE_DATA_FLOW_TOP_LIMIT"' in src
    assert 'validate_int "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_LOOKBACK_HOURS"' in src
    assert 'validate_int "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_TOUCH_WINDOW_MINUTES"' in src
    assert 'validate_int "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_PLACEMENT_WINDOW_SECONDS"' in src
    assert 'validate_int "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_TOP_LIMIT"' in src
    assert 'validate_decimal "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_DEEP_GAP_BPS"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_SCORECARD_LOOKBACK_HOURS"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_SCORECARD_LIMIT"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_LEARNING_REFRESH_PLAN"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_LEARNING_PREINSTALL_REFRESH_ONLY"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_PLAN_MAX_SCORECARD_AGE_HOURS"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_PLAN_MIN_CANDIDATE_SAMPLE"' in src
    assert "OPENCLAW_COST_GATE_SCORECARD_HORIZON_MINUTES_LIST must be comma-separated integers" in src
    assert '^[0-9]+(,[0-9]+)*$' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_RESULT_REVIEW"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_MATERIALIZER_LOOKBACK_HOURS"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_MATERIALIZER_LIMIT"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_HISTORICAL_MAX_SCORECARD_AGE_HOURS"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_HISTORICAL_MIN_CANDIDATE_SAMPLE"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_TOUCHABILITY_MAX_ARTIFACT_AGE_HOURS"' in src
    assert 'validate_decimal "OPENCLAW_COST_GATE_TOUCHABILITY_MAX_INITIAL_PASSIVE_GAP_BPS"' in src
    assert 'validate_decimal "OPENCLAW_COST_GATE_TOUCHABILITY_MAX_DEEP_NO_TOUCH_GAP_BPS"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_PLACEMENT_REPAIR_MAX_ARTIFACT_AGE_HOURS"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_PLACEMENT_REPAIR_MAX_FRESH_BBO_AGE_MS"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_SHADOW_PLACEMENT_MAX_ARTIFACT_AGE_HOURS"' in src


def test_wrapper_refreshes_plan_before_materializing_rejects() -> None:
    src = _src(WRAPPER)
    assert 'SCORECARD_ARGS=(' in src
    assert 'DATA_FLOW_ARGS=(' in src
    assert 'ORDER_TOUCHABILITY_ARGS=(' in src
    assert 'PLAN_ARGS=(' in src
    assert 'DECISION_PACKET_ARGS=(' in src
    assert "cost_gate_reject_counterfactual.py" in src
    assert "demo_data_flow_monitor.py" in src
    assert "demo_order_to_fill_gap_audit.py" in src
    assert '--horizon-minutes-list "$SCORECARD_HORIZON_MINUTES_LIST"' in src
    assert '--engine-mode "$engine_mode"' in src
    assert "-m cost_gate_learning_lane.policy" in src
    assert "-m cost_gate_learning_lane.decision_packet" in src
    assert "-m cost_gate_learning_lane.bounded_probe_touchability_preflight" in src
    assert "-m cost_gate_learning_lane.bounded_probe_placement_repair_plan" in src
    assert "-m cost_gate_learning_lane.bounded_probe_shadow_placement_impact" in src
    assert "-m cost_gate_learning_lane.bounded_probe_result_review" in src
    assert "-m cost_gate_learning_lane.bounded_probe_execution_realism_review" in src
    assert 'cp "$SCORECARD_JSON_OUT" "$SCORECARD_JSON"' in src
    assert 'cp "$DATA_FLOW_JSON_OUT" "$DATA_FLOW_JSON"' in src
    assert 'cp "$ORDER_TOUCHABILITY_JSON_OUT" "$ORDER_TOUCHABILITY_JSON"' in src
    assert 'cp "$PLAN_OUT" "$PLAN_JSON"' in src
    assert 'cp "$DECISION_PACKET_JSON_OUT" "$DECISION_PACKET_JSON"' in src
    assert 'cp "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT" "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_LATEST"' in src
    assert 'cp "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT" "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_LATEST"' in src
    assert 'cp "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT" "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_LATEST"' in src
    assert 'cp "$BOUNDED_PROBE_RESULT_REVIEW_OUT" "$BOUNDED_PROBE_RESULT_REVIEW_LATEST"' in src
    assert 'cp "$BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_OUT" "$BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_LATEST"' in src
    assert 'SCORECARD_JSON_OUT="$SCORECARD_JSON_OUT" SCORECARD_JSON="$SCORECARD_JSON" SCORECARD_RC="$scorecard_rc" REFRESH_SCORECARD="$REFRESH_SCORECARD"' in src
    assert 'DATA_FLOW_JSON_OUT="$DATA_FLOW_JSON_OUT" DATA_FLOW_JSON="$DATA_FLOW_JSON" DATA_FLOW_MONITOR_RC="$data_flow_monitor_rc" REFRESH_DATA_FLOW_MONITOR="$REFRESH_DATA_FLOW_MONITOR"' in src
    assert 'ORDER_TOUCHABILITY_JSON_OUT="$ORDER_TOUCHABILITY_JSON_OUT" ORDER_TOUCHABILITY_JSON="$ORDER_TOUCHABILITY_JSON" ORDER_TOUCHABILITY_AUDIT_RC="$order_touchability_audit_rc"' in src
    assert 'DECISION_PACKET_JSON_OUT="$DECISION_PACKET_JSON_OUT" DECISION_PACKET_JSON="$DECISION_PACKET_JSON" DECISION_PACKET_RC="$decision_packet_rc" REFRESH_DECISION_PACKET="$REFRESH_DECISION_PACKET"' in src
    assert 'PLAN_OUT="$PLAN_OUT" PLAN_JSON="$PLAN_JSON" PLAN_RC="$plan_rc" REFRESH_PLAN="$REFRESH_PLAN"' in src
    assert 'ORDER_TOUCHABILITY_JSON="$ORDER_TOUCHABILITY_JSON" BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT="$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT"' in src
    assert 'BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT="$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT" BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_LATEST="$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_LATEST"' in src
    assert 'export BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT="$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT"' in src
    assert "scorecard_rc=" in src
    assert "data_flow_monitor_rc=" in src
    assert "order_touchability_audit_rc=" in src
    assert "decision_packet_rc=" in src
    assert "plan_rc=" in src
    assert "bounded_probe_placement_repair_plan_rc=" in src
    assert "bounded_probe_shadow_placement_impact_rc=" in src
    scorecard_index = src.index('"$PYBIN" "${SCORECARD_ARGS[@]}"')
    data_flow_index = src.index('"$PYBIN" "${DATA_FLOW_ARGS[@]}"')
    order_touchability_index = src.index('"$PYBIN" "${ORDER_TOUCHABILITY_ARGS[@]}"')
    plan_index = src.index('"$PYBIN" "${PLAN_ARGS[@]}"')
    materializer_index = src.index('"$PYBIN" "${MATERIALIZER_ARGS[@]}"')
    refresh_index = src.index('"$PYBIN" "${REFRESH_ARGS[@]}"')
    review_index = src.index('"$PYBIN" "${REVIEW_ARGS[@]}"')
    touchability_index = src.index('"$PYBIN" "${BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_ARGS[@]}"')
    placement_index = src.index('"$PYBIN" "${BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_ARGS[@]}"')
    shadow_index = src.index('"$PYBIN" "${BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_ARGS[@]}"')
    result_review_index = src.index('"$PYBIN" "${BOUNDED_PROBE_RESULT_REVIEW_ARGS[@]}"')
    execution_review_index = src.index('"$PYBIN" "${BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_ARGS[@]}"')
    decision_packet_index = src.index('"$PYBIN" "${DECISION_PACKET_ARGS[@]}"')
    assert scorecard_index < plan_index
    assert scorecard_index < data_flow_index < plan_index
    assert plan_index < materializer_index
    assert materializer_index < refresh_index < review_index
    assert review_index < order_touchability_index < touchability_index < placement_index < shadow_index < result_review_index < execution_review_index
    assert execution_review_index < decision_packet_index


def test_wrapper_bounded_probe_reviews_use_fresh_result_review_only() -> None:
    src = _src(WRAPPER)
    assert 'SEALED_PREFLIGHT_JSON="${OPENCLAW_COST_GATE_BOUNDED_PROBE_PREFLIGHT_JSON:-$LANE_DIR/sealed_horizon_probe_preflight_latest.json}"' in src
    assert 'ORDER_TOUCHABILITY_DIR="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_AUDIT_DIR:-$DATA/demo_order_to_fill_gap}"' in src
    assert 'ORDER_TOUCHABILITY_JSON="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_AUDIT_JSON:-$ORDER_TOUCHABILITY_DIR/demo_order_to_fill_gap_latest.json}"' in src
    assert '--preflight-json "$SEALED_PREFLIGHT_JSON"' in src
    assert '--order-to-fill-gap-json "$ORDER_TOUCHABILITY_JSON"' in src
    assert '--touchability-preflight-json "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT"' in src
    assert '--placement-repair-plan-json "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT"' in src
    assert '--result-review-json "$BOUNDED_PROBE_RESULT_REVIEW_OUT"' in src
    assert "BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_LATEST" in src
    assert "BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_MD_LATEST" in src
    assert "BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_LATEST" in src
    assert "BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_MD_LATEST" in src
    assert "BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_LATEST" in src
    assert "BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_MD_LATEST" in src
    assert 'if [[ -f "$SEALED_PREFLIGHT_JSON" ]]' in src
    assert 'bounded_probe_result_review_skip_reason="sealed_horizon_probe_preflight_missing"' in src
    assert 'if [[ -f "$BOUNDED_PROBE_RESULT_REVIEW_OUT" ]]' in src
    assert 'bounded_probe_execution_realism_review_skip_reason="bounded_probe_result_review_missing"' in src
    assert "BOUNDED_PROBE_RESULT_REVIEW_LATEST" in src
    assert "BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_LATEST" in src


def test_wrapper_has_preinstall_refresh_only_cutoff_after_plan_refresh() -> None:
    src = _src(WRAPPER)
    assert 'if [[ "$PREINSTALL_REFRESH_ONLY" == "1" ]]' in src
    assert "preinstall refresh-only mode" in src
    assert "skipped historical/materializer/outcome/review/bounded-probe stages" in src
    assert 'PREINSTALL_REFRESH_ONLY="$PREINSTALL_REFRESH_ONLY"' in src
    assert '"preinstall_refresh_only": os.environ["PREINSTALL_REFRESH_ONLY"] == "1"' in src
    assert 'order_touchability_audit_skip_reason="preinstall_refresh_only"' in src
    assert 'bounded_probe_touchability_preflight_skip_reason="preinstall_refresh_only"' in src
    assert 'bounded_probe_placement_repair_plan_skip_reason="preinstall_refresh_only"' in src
    assert 'bounded_probe_shadow_placement_impact_skip_reason="preinstall_refresh_only"' in src
    assert 'bounded_probe_result_review_skip_reason="preinstall_refresh_only"' in src
    assert 'bounded_probe_execution_realism_review_skip_reason="preinstall_refresh_only"' in src
    plan_copy_index = src.index('cp "$PLAN_OUT" "$PLAN_JSON"')
    preinstall_index = src.index('if [[ "$PREINSTALL_REFRESH_ONLY" == "1" ]]')
    historical_index = src.index('"$PYBIN" "${HISTORICAL_REVIEW_ARGS[@]}"')
    materializer_index = src.index('"$PYBIN" "${MATERIALIZER_ARGS[@]}"')
    refresh_index = src.index('"$PYBIN" "${REFRESH_ARGS[@]}"')
    review_index = src.index('"$PYBIN" "${REVIEW_ARGS[@]}"')
    order_touchability_index = src.index('"$PYBIN" "${ORDER_TOUCHABILITY_ARGS[@]}"')
    touchability_index = src.index('"$PYBIN" "${BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_ARGS[@]}"')
    placement_index = src.index('"$PYBIN" "${BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_ARGS[@]}"')
    shadow_index = src.index('"$PYBIN" "${BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_ARGS[@]}"')
    result_review_index = src.index('"$PYBIN" "${BOUNDED_PROBE_RESULT_REVIEW_ARGS[@]}"')
    execution_review_index = src.index('"$PYBIN" "${BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_ARGS[@]}"')
    assert plan_copy_index < preinstall_index
    assert (
        preinstall_index
        < historical_index
        < materializer_index
        < refresh_index
        < review_index
        < order_touchability_index
        < touchability_index
        < placement_index
        < shadow_index
        < result_review_index
        < execution_review_index
    )


def test_installer_dry_run_apply_gate_and_reversible_entry() -> None:
    src = _src(INSTALLER)
    assert 'OPENCLAW_COST_GATE_LEARNING_CRON_MINUTES="${OPENCLAW_COST_GATE_LEARNING_CRON_MINUTES:-27}"' in src
    assert 'OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS="${OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS:-1}"' in src
    assert 'OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS="${OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS:-1}"' in src
    assert 'OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES="${OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES:-1}"' in src
    assert 'OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES="${OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES:-0}"' in src
    assert 'OPENCLAW_COST_GATE_LEARNING_INSTALL_PREFLIGHT="${OPENCLAW_COST_GATE_LEARNING_INSTALL_PREFLIGHT:-1}"' in src
    assert 'OPENCLAW_COST_GATE_LEARNING_REQUIRE_EXPECTED_HEAD="${OPENCLAW_COST_GATE_LEARNING_REQUIRE_EXPECTED_HEAD:-1}"' in src
    assert "OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD" in src
    assert 'ENTRY="${OPENCLAW_COST_GATE_LEARNING_CRON_MINUTES} * * * *' in src
    assert '_validate_cron_minute_list "OPENCLAW_COST_GATE_LEARNING_CRON_MINUTES"' in src
    assert '_validate_bool01 "OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS"' in src
    assert '_validate_bool01 "OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS"' in src
    assert '_validate_bool01 "OPENCLAW_COST_GATE_LEARNING_INSTALL_PREFLIGHT"' in src
    assert '_validate_bool01 "OPENCLAW_COST_GATE_LEARNING_REQUIRE_EXPECTED_HEAD"' in src
    assert "_validate_bool01" in src
    assert "OPENCLAW_COST_GATE_LEARNING_CRON_APPLY" in src
    assert "DRY-RUN: not modifying crontab." in src
    assert "--remove" in src
    assert 'MARKER="cost_gate_learning_lane_cron.sh"' in src
    assert 'grep -q "$MARKER"' in src
    assert "cost_gate_learning_lane_cron.cron.log" in src
    assert "Boundary: artifact-only JSONL/JSON refresh; readonly PG; no order authority or Cost Gate relaxation" in src


def test_installer_apply_requires_readonly_activation_preflight_before_crontab_write() -> None:
    src = _src(INSTALLER)
    assert "build_cost_gate_learning_lane_activation_preflight" in src
    assert "Running read-only cost-gate learning activation preflight" in src
    assert "OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD or OPENCLAW_EXPECTED_SOURCE_HEAD is required" in src
    assert "required_source_files_not_ready" in src
    assert "source_activation_ready" in src
    assert "expected_head_matches" in src
    assert "plan_status" in src
    assert "read-only installer preflight; no crontab edit performed by this check" in src
    assert "exit 7" in src
    preflight_index = src.index('if [[ "$OPENCLAW_COST_GATE_LEARNING_INSTALL_PREFLIGHT" == "1" ]]')
    install_index = src.index('( crontab -l 2>/dev/null; echo "$ENTRY" ) | crontab -')
    assert preflight_index < install_index


@pytest.mark.parametrize("script", [WRAPPER, INSTALLER], ids=["wrapper", "installer"])
def test_no_hardcoded_user_paths_or_trading_tokens(script: Path) -> None:
    src = _src(script)
    forbidden = (
        "/home/ncyu",
        "/Users/",
        "OPENCLAW_ALLOW_MAINNET",
        "authorization.json",
        "create_order",
        "place_order",
        "cancel_order",
        "live_authorization",
        "restart_all.sh",
        "systemctl",
    )
    for token in forbidden:
        assert token not in src
