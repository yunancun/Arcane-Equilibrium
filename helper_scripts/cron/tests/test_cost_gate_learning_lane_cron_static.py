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


def test_wrapper_uses_guard_for_lock_and_outcome_review() -> None:
    src = _src(WRAPPER)
    assert 'source "$BASE/helper_scripts/cron/lib/research_workload_guard.sh"' in src
    assert "research_guard_acquire --lane cost" in src
    assert "research_guard_run_stage" in src
    assert "--memory-max-bytes 12884901888" in src
    assert "research_guard_complete" in src
    assert 'if [[ "$review_rc" == "0" && -f "$REVIEW_OUT" ]]; then' in src
    assert 'find "$LOCK_DIR"' not in src
    assert 'rmdir "$LOCK_DIR"' not in src


@pytest.mark.parametrize("script", [WRAPPER, INSTALLER], ids=["wrapper", "installer"])
def test_scripts_executable_and_strict_mode(script: Path) -> None:
    assert script.stat().st_mode & 0o111, f"{script.name} not executable"
    assert "set -euo pipefail" in _src(script)


def test_wrapper_readonly_pg_and_artifact_only_status() -> None:
    src = _src(WRAPPER)
    assert "basic_system_services.env" in src
    assert "POSTGRES_PASSWORD" in src
    assert 'PGOPTIONS="-c default_transaction_read_only=on"' in src
    # CRON-STALE-LOCK-FLOCK-1：mkdir-dir 鎖＋「stale 超時 rmdir 清鎖照跑」已廢止
    #（2026-07-15 OOM 疊加機），改共用 flock 正本：鎖檔常駐、超齡只 WARN 絕不接手。
    assert 'LOCK_FILE="${LOCK_ROOT}/cost_gate_learning_lane_cron.lock"' in src
    assert "cost_gate_learning_lane_cron.lock.d" not in src
    assert "cron_flock.sh" in src
    assert (
        'acquire_cron_flock "$LOCK_FILE" "$STALE_LOCK_MIN" "$LOG" "cost_gate_learning_lane" || exit 0'
        in src
    )
    assert 'rmdir "' not in src
    assert 'mkdir "$LOCK' not in src
    assert "release_lock()" not in src
    assert "trap release_lock" not in src
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
    assert "false_negative_candidate_packet_latest.json" in src
    assert "false_negative_operator_review_latest.json" in src
    assert "false_negative_candidate_friction_scorecard_latest.json" in src
    assert "learning_ssot_decision_latest.json" in src
    assert "autonomous_parameter_proposal_latest.json" in src
    assert "false_negative_bounded_probe_preflight_latest.json" in src
    assert "bounded_probe_touchability_preflight_latest.json" in src
    assert "bounded_probe_placement_repair_plan_latest.json" in src
    assert "bounded_probe_authority_patch_readiness_latest.json" in src
    assert "bounded_probe_operator_authorization_latest.json" in src
    assert "bounded_probe_shadow_placement_impact_latest.json" in src
    assert "bounded_probe_result_review_latest.json" in src
    assert "bounded_probe_execution_realism_review_latest.json" in src
    assert "historical_scorecard_review_latest.json" in src
    assert "reject_materializer_latest.json" in src
    assert "pipeline_snapshot.json" in src
    assert "cost_gate_reject_counterfactual.py" in src
    assert "demo_data_flow_monitor.py" in src
    assert "demo_order_to_fill_gap_audit.py" in src
    assert "cost_gate_learning_lane.decision_packet" in src
    assert "cost_gate_learning_lane.policy" in src
    assert "cost_gate_learning_lane.reject_materializer" in src
    assert "cost_gate_learning_lane.outcome_refresh" in src
    assert "cost_gate_learning_lane.outcome_review" in src
    assert "cost_gate_learning_lane.false_negative_candidate_packet" in src
    assert "cost_gate_learning_lane.false_negative_operator_review" in src
    assert "cost_gate_learning_lane.false_negative_candidate_friction_scorecard" in src
    assert "cost_gate_learning_lane.learning_ssot_decision" in src
    assert "cost_gate_learning_lane.autonomous_parameter_proposal" in src
    assert "cost_gate_learning_lane.false_negative_bounded_probe_preflight" in src
    assert "cost_gate_learning_lane.bounded_probe_touchability_preflight" in src
    assert "cost_gate_learning_lane.bounded_probe_placement_repair_plan" in src
    assert "cost_gate_learning_lane.bounded_probe_authority_patch_readiness" in src
    assert "cost_gate_learning_lane.bounded_probe_operator_authorization_cli" in src
    assert "cost_gate_learning_lane.bounded_probe_shadow_placement_impact" in src
    assert "cost_gate_learning_lane.bounded_probe_result_review" in src
    assert "cost_gate_learning_lane.bounded_probe_execution_realism_review" in src
    assert "cost_gate_learning_lane.historical_review" in src
    assert "materializer_materialized_record_count" in src
    assert "materializer_appended_record_count" in src
    assert "materializer_decision_counts" in src
    assert "materializer_snapshot_input_row_count" in src
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
    assert "false_negative_candidate_packet_status" in src
    assert "false_negative_candidate_packet_false_negative_count" in src
    assert "false_negative_candidate_packet_edge_amplification_count" in src
    assert "false_negative_candidate_packet_operator_review_ready" in src
    assert "false_negative_candidate_packet_global_cost_gate_lowering_recommended" in src
    assert "false_negative_operator_review_status" in src
    assert "false_negative_operator_review_decision" in src
    assert "false_negative_operator_review_approval_source" in src
    assert "false_negative_operator_review_approved_for_preflight" in src
    assert "false_negative_operator_review_bounded_demo_probe_preflight_approved" in src
    assert "false_negative_operator_review_review_grants_runtime_authority" in src
    assert "false_negative_operator_review_order_authority_granted" in src
    assert "false_negative_operator_review_standing_demo_authorization_valid" in src
    assert "false_negative_candidate_friction_scorecard_status" in src
    assert "false_negative_candidate_friction_scorecard_ranked_count" in src
    assert "false_negative_candidate_friction_scorecard_top_side_cell_key" in src
    assert "false_negative_candidate_friction_scorecard_top_next_action" in src
    assert "false_negative_candidate_friction_scorecard_bounded_demo_probe_authorized" in src
    assert "false_negative_candidate_friction_scorecard_operator_authorization_object_emitted" in src
    assert "false_negative_candidate_friction_scorecard_probe_authority_granted" in src
    assert "false_negative_candidate_friction_scorecard_order_authority_granted" in src
    assert "false_negative_candidate_friction_scorecard_promotion_evidence" in src
    assert "learning_ssot_decision_status" in src
    assert "learning_ssot_decision_current_ssot" in src
    assert "autonomous_parameter_proposal_status" in src
    assert "autonomous_parameter_proposal_reviewable" in src
    assert "false_negative_bounded_probe_preflight_status" in src
    assert "false_negative_bounded_probe_preflight_side_cell_key" in src
    assert "false_negative_bounded_probe_preflight_operator_review_approval_source" in src
    assert "false_negative_bounded_probe_preflight_standing_demo_authorization_valid" in src
    assert "false_negative_bounded_probe_preflight_order_authority_granted" in src
    assert "bounded_probe_preflight_source_path" in src
    assert "bounded_probe_result_review_status" in src
    assert "bounded_probe_result_review_skip_reason" in src
    assert "bounded_probe_result_review_execution_realism_gap" in src
    assert "bounded_probe_touchability_preflight_status" in src
    assert "bounded_probe_touchability_repair_required" in src
    assert "bounded_probe_placement_repair_plan_status" in src
    assert "bounded_probe_authority_patch_readiness_status" in src
    assert "bounded_probe_operator_authorization_status" in src
    assert "bounded_probe_operator_authorization_object_emitted" in src
    assert "bounded_probe_operator_authorization_active_runtime_order_authority" in src
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
    assert "--snapshot-json" in src
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
    assert "OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_CANDIDATE_PACKET" in src
    assert "OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_OPERATOR_REVIEW" in src
    assert "OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD" in src
    assert "OPENCLAW_COST_GATE_FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_MAX_ARTIFACT_AGE_HOURS" in src
    assert "OPENCLAW_COST_GATE_FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_TOP_LIMIT" in src
    assert "OPENCLAW_COST_GATE_REFRESH_LEARNING_SSOT_DECISION" in src
    assert "OPENCLAW_COST_GATE_REFRESH_AUTONOMOUS_PARAMETER_PROPOSAL" in src
    assert "OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_BOUNDED_PROBE_PREFLIGHT" in src
    assert "OPENCLAW_COST_GATE_PROFIT_EVIDENCE_QUALITY_STATUS" in src
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
    assert "OPENCLAW_COST_GATE_LEARNING_PIPELINE_SNAPSHOT_JSON" in src
    assert "OPENCLAW_COST_GATE_BOUNDED_PROBE_PREFLIGHT_JSON" in src
    assert "OPENCLAW_DEMO_ORDER_TO_FILL_GAP_AUDIT_JSON" in src
    assert "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT" in src
    assert "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN" in src
    assert "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS" in src
    assert "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_OPERATOR_AUTHORIZATION" in src
    assert "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT" in src
    assert "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_RESULT_REVIEW" in src
    assert "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW" in src
    assert "PYTHONDONTWRITEBYTECODE=1" in src
    assert "artifact_only_readonly_pg_jsonl_ledger_no_order_no_cost_gate_relaxation" in src
    assert src.rstrip().endswith("exit 0")


def test_wrapper_marks_cron_oom_victim_after_lock() -> None:
    # CRON-OOM-VICTIM-1：取到鎖的重活實例自標 OOM victim（oom_score_adj 往正、
    # 默認 800），使 OOM 時 kernel 優先殺 cron hog（probe_ledger 全量物化實測
    # 79–85GB）、而非繼承 DefaultOOMScoreAdjust=200 的交易引擎/watchdog（2026-07-15
    # 引擎因 adj=200 被連坐殺）。與 flock 互補、全 fail-soft、lib 缺失不擋跑。
    src = _src(WRAPPER)
    assert "cron_oom_victim.sh" in src
    assert (
        '[[ -f "$OOM_VICTIM_LIB" ]] && source "$OOM_VICTIM_LIB" && mark_cron_oom_victim || true'
        in src
    )
    # 放在取鎖之後：只有真正取到鎖、要跑重活的實例才需標 victim。
    assert src.index("acquire_cron_flock") < src.index("mark_cron_oom_victim")


def test_wrapper_fail_soft_defaults_match_learning_lane_review_policy() -> None:
    src = _src(WRAPPER)
    assert 'PG_TIMEFRAME="${OPENCLAW_COST_GATE_LEARNING_PG_TIMEFRAME:-1m}"' in src
    assert 'REFRESH_SCORECARD="${OPENCLAW_COST_GATE_LEARNING_REFRESH_SCORECARD:-1}"' in src
    assert 'REFRESH_DATA_FLOW_MONITOR="${OPENCLAW_COST_GATE_REFRESH_DATA_FLOW_MONITOR:-1}"' in src
    assert 'REFRESH_ORDER_TOUCHABILITY_AUDIT="${OPENCLAW_COST_GATE_REFRESH_ORDER_TOUCHABILITY_AUDIT:-1}"' in src
    assert 'REFRESH_DECISION_PACKET="${OPENCLAW_COST_GATE_REFRESH_DECISION_PACKET:-1}"' in src
    assert 'REFRESH_FALSE_NEGATIVE_CANDIDATE_PACKET="${OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_CANDIDATE_PACKET:-1}"' in src
    assert 'REFRESH_FALSE_NEGATIVE_OPERATOR_REVIEW="${OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_OPERATOR_REVIEW:-1}"' in src
    assert 'REFRESH_FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD="${OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD:-1}"' in src
    assert 'REFRESH_LEARNING_SSOT_DECISION="${OPENCLAW_COST_GATE_REFRESH_LEARNING_SSOT_DECISION:-1}"' in src
    assert 'REFRESH_AUTONOMOUS_PARAMETER_PROPOSAL="${OPENCLAW_COST_GATE_REFRESH_AUTONOMOUS_PARAMETER_PROPOSAL:-1}"' in src
    assert 'REFRESH_FALSE_NEGATIVE_BOUNDED_PROBE_PREFLIGHT="${OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_BOUNDED_PROBE_PREFLIGHT:-1}"' in src
    assert 'PROFIT_EVIDENCE_QUALITY_STATUS="${OPENCLAW_COST_GATE_PROFIT_EVIDENCE_QUALITY_STATUS:-DONE_WITH_CONCERNS}"' in src
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
    assert 'REFRESH_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS:-1}"' in src
    assert 'REFRESH_BOUNDED_PROBE_OPERATOR_AUTHORIZATION="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_OPERATOR_AUTHORIZATION:-1}"' in src
    assert 'STANDING_DEMO_AUTHORIZATION_JSON="${OPENCLAW_COST_GATE_STANDING_DEMO_AUTHORIZATION_JSON:-}"' in src
    assert 'BOUNDED_PROBE_OPERATOR_AUTHORIZATION_DECISION="${OPENCLAW_COST_GATE_BOUNDED_PROBE_OPERATOR_AUTHORIZATION_DECISION:-}"' in src
    assert 'BOUNDED_PROBE_OPERATOR_AUTHORIZATION_DECISION="defer"' in src
    assert 'BOUNDED_PROBE_OPERATOR_AUTHORIZATION_DECISION="authorize"' not in src
    assert 'if [[ -n "$STANDING_DEMO_AUTHORIZATION_JSON" && -f "$STANDING_DEMO_AUTHORIZATION_JSON" ]]; then\n        BOUNDED_PROBE_OPERATOR_AUTHORIZATION_DECISION="authorize"' not in src
    assert 'REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT:-1}"' in src
    assert 'REFRESH_BOUNDED_PROBE_RESULT_REVIEW="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_RESULT_REVIEW:-1}"' in src
    assert 'REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW="${OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW:-1}"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_CANDIDATE_PACKET"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_LEARNING_SSOT_DECISION"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_AUTONOMOUS_PARAMETER_PROPOSAL"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_BOUNDED_PROBE_PREFLIGHT"' in src
    assert "OPENCLAW_COST_GATE_PROFIT_EVIDENCE_QUALITY_STATUS invalid" in src
    assert 'REVIEW_MIN_OUTCOMES="${OPENCLAW_COST_GATE_REVIEW_MIN_OUTCOMES_PER_SIDE_CELL:-3}"' in src
    assert 'REVIEW_MIN_AVG_NET_BPS="${OPENCLAW_COST_GATE_REVIEW_MIN_AVG_NET_BPS:-0.0}"' in src
    assert 'REVIEW_MIN_NET_POSITIVE_PCT="${OPENCLAW_COST_GATE_REVIEW_MIN_NET_POSITIVE_PCT:-60.0}"' in src
    assert 'TOUCHABILITY_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_TOUCHABILITY_MAX_ARTIFACT_AGE_HOURS:-24}"' in src
    assert 'TOUCHABILITY_MAX_INITIAL_PASSIVE_GAP_BPS="${OPENCLAW_COST_GATE_TOUCHABILITY_MAX_INITIAL_PASSIVE_GAP_BPS:-75.0}"' in src
    assert 'TOUCHABILITY_MAX_DEEP_NO_TOUCH_GAP_BPS="${OPENCLAW_COST_GATE_TOUCHABILITY_MAX_DEEP_NO_TOUCH_GAP_BPS:-500.0}"' in src
    assert 'PLACEMENT_REPAIR_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_PLACEMENT_REPAIR_MAX_ARTIFACT_AGE_HOURS:-24}"' in src
    assert 'PLACEMENT_REPAIR_MAX_FRESH_BBO_AGE_MS="${OPENCLAW_COST_GATE_PLACEMENT_REPAIR_MAX_FRESH_BBO_AGE_MS:-1000}"' in src
    assert 'AUTHORITY_PATCH_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_AUTHORITY_PATCH_MAX_ARTIFACT_AGE_HOURS:-24}"' in src
    assert 'OPERATOR_AUTHORIZATION_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_OPERATOR_AUTHORIZATION_MAX_ARTIFACT_AGE_HOURS:-24}"' in src
    assert 'FALSE_NEGATIVE_OPERATOR_REVIEW_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW_MAX_ARTIFACT_AGE_HOURS:-24}"' in src
    assert 'FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_MAX_ARTIFACT_AGE_HOURS:-24}"' in src
    assert 'FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_TOP_LIMIT="${OPENCLAW_COST_GATE_FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_TOP_LIMIT:-16}"' in src
    assert 'SHADOW_PLACEMENT_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_COST_GATE_SHADOW_PLACEMENT_MAX_ARTIFACT_AGE_HOURS:-24}"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_LEARNING_REFRESH_SCORECARD"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_DATA_FLOW_MONITOR"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_ORDER_TOUCHABILITY_AUDIT"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_DECISION_PACKET"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_OPERATOR_REVIEW"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD"' in src
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
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_SEALED_HORIZON_LEARNING_EVIDENCE"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_APPEND_SEALED_HORIZON_LEARNING_EVIDENCE"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_LOOKBACK_HOURS"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_LIMIT"' in src
    assert 'SEALED_LEARNING_EVIDENCE_LIMIT="${OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_LIMIT:-5000}"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_MATURITY_BUFFER_MINUTES"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_MIN_REVIEW_OUTCOMES_PER_SIDE_CELL"' in src
    assert 'validate_decimal "OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_MIN_REVIEW_AVG_NET_BPS"' in src
    assert 'validate_decimal "OPENCLAW_COST_GATE_SEALED_HORIZON_LEARNING_EVIDENCE_MIN_REVIEW_NET_POSITIVE_PCT"' in src
    assert "OPENCLAW_COST_GATE_SCORECARD_HORIZON_MINUTES_LIST must be comma-separated integers" in src
    assert '^[0-9]+(,[0-9]+)*$' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_RESULT_REVIEW"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS"' in src
    assert 'validate_bool01 "OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_OPERATOR_AUTHORIZATION"' in src
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
    assert 'validate_int "OPENCLAW_COST_GATE_AUTHORITY_PATCH_MAX_ARTIFACT_AGE_HOURS"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_OPERATOR_AUTHORIZATION_MAX_ARTIFACT_AGE_HOURS"' in src
    assert "OPENCLAW_COST_GATE_BOUNDED_PROBE_OPERATOR_AUTHORIZATION_DECISION invalid" in src
    assert 'validate_int "OPENCLAW_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW_MAX_ARTIFACT_AGE_HOURS"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_MAX_ARTIFACT_AGE_HOURS"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_TOP_LIMIT"' in src
    assert 'validate_int "OPENCLAW_COST_GATE_SHADOW_PLACEMENT_MAX_ARTIFACT_AGE_HOURS"' in src


def test_wrapper_refreshes_plan_before_materializing_rejects() -> None:
    src = _src(WRAPPER)
    assert 'SCORECARD_ARGS=(' in src
    assert 'DATA_FLOW_ARGS=(' in src
    assert 'ORDER_TOUCHABILITY_ARGS=(' in src
    assert 'PLAN_ARGS=(' in src
    assert 'SEALED_LEARNING_EVIDENCE_ARGS=(' in src
    assert 'DECISION_PACKET_ARGS=(' in src
    assert 'FALSE_NEGATIVE_OPERATOR_REVIEW_ARGS=(' in src
    assert "FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_ARGS=(" in src
    assert "LEARNING_SSOT_DECISION_ARGS=(" in src
    assert "AUTONOMOUS_PARAMETER_PROPOSAL_ARGS=(" in src
    assert "cost_gate_reject_counterfactual.py" in src
    assert "demo_data_flow_monitor.py" in src
    assert "demo_order_to_fill_gap_audit.py" in src
    assert '--horizon-minutes-list "$SCORECARD_HORIZON_MINUTES_LIST"' in src
    assert '--engine-mode "$engine_mode"' in src
    assert "-m cost_gate_learning_lane.policy" in src
    assert "--horizon-sealed-replay-json" in src
    assert "-m cost_gate_learning_lane.sealed_horizon_learning_evidence" in src
    assert "-m cost_gate_learning_lane.decision_packet" in src
    assert "-m cost_gate_learning_lane.bounded_probe_touchability_preflight" in src
    assert "-m cost_gate_learning_lane.bounded_probe_placement_repair_plan" in src
    assert "-m cost_gate_learning_lane.bounded_probe_authority_patch_readiness" in src
    assert "-m cost_gate_learning_lane.bounded_probe_operator_authorization_cli" in src
    assert "-m cost_gate_learning_lane.false_negative_candidate_friction_scorecard" in src
    assert "-m cost_gate_learning_lane.bounded_probe_shadow_placement_impact" in src
    assert "-m cost_gate_learning_lane.bounded_probe_result_review" in src
    assert "-m cost_gate_learning_lane.bounded_probe_execution_realism_review" in src
    assert "-m cost_gate_learning_lane.false_negative_operator_review" in src
    assert "json_selected_candidate_side_cell_key()" in src
    assert "json_false_negative_packet_has_side_cell_key()" in src
    assert "OPENCLAW_COST_GATE_CAP_FEASIBLE_CANDIDATE_SELECTION_JSON" in src
    assert "OPENCLAW_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW_SELECTED_SIDE_CELL_KEY" in src
    assert "-m cost_gate_learning_lane.learning_ssot_decision" in src
    assert "-m cost_gate_learning_lane.autonomous_parameter_proposal" in src
    assert "-m cost_gate_learning_lane.false_negative_bounded_probe_preflight" in src
    assert '--false-negative-candidate-packet-json "$FALSE_NEGATIVE_CANDIDATE_PACKET_OUT"' in src
    assert '--selected-side-cell-key "$FALSE_NEGATIVE_OPERATOR_REVIEW_SELECTED_SIDE_CELL_KEY"' in src
    packet_copy_index = src.index('cp "$FALSE_NEGATIVE_CANDIDATE_PACKET_OUT"')
    selected_append_index = src.index(
        '--selected-side-cell-key "$FALSE_NEGATIVE_OPERATOR_REVIEW_SELECTED_SIDE_CELL_KEY"'
    )
    assert packet_copy_index < selected_append_index
    assert "stale false-negative selected side-cell ignored" in src
    assert '--touchability-preflight-json "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT"' in src
    assert '--placement-repair-plan-json "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT"' in src
    assert '--operator-authorization-json "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT"' in src
    assert "--existing-operator-review-json" in src
    assert '--decision "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_DECISION"' in src
    assert "--standing-demo-authorization-json" in src
    assert "--learning-ssot-decision-json" in src
    assert "--profit-evidence-quality-status" in src
    assert "--autonomous-parameter-proposal-json" in src
    assert "--false-negative-operator-review-json" in src
    assert 'cp "$SCORECARD_JSON_OUT" "$SCORECARD_JSON"' in src
    assert 'cp "$DATA_FLOW_JSON_OUT" "$DATA_FLOW_JSON"' in src
    assert 'cp "$ORDER_TOUCHABILITY_JSON_OUT" "$ORDER_TOUCHABILITY_JSON"' in src
    assert 'cp "$PLAN_OUT" "$PLAN_JSON"' in src
    assert 'cp "$DECISION_PACKET_JSON_OUT" "$DECISION_PACKET_JSON"' in src
    assert 'cp "$SEALED_LEARNING_EVIDENCE_OUT" "$SEALED_LEARNING_EVIDENCE_JSON"' in src
    assert 'cp "$FALSE_NEGATIVE_OPERATOR_REVIEW_OUT" "$FALSE_NEGATIVE_OPERATOR_REVIEW_LATEST"' in src
    assert 'cp "$LEARNING_SSOT_DECISION_OUT" "$LEARNING_SSOT_DECISION_LATEST"' in src
    assert 'cp "$AUTONOMOUS_PARAMETER_PROPOSAL_OUT" "$AUTONOMOUS_PARAMETER_PROPOSAL_LATEST"' in src
    assert 'cp "$FALSE_NEGATIVE_BOUNDED_PREFLIGHT_OUT" "$FALSE_NEGATIVE_BOUNDED_PREFLIGHT_LATEST"' in src
    assert 'cp "$SEALED_LEARNING_EVIDENCE_REVIEW_OUT" "$SEALED_LEARNING_EVIDENCE_REVIEW_LATEST"' in src
    assert 'cp "$SEALED_LEARNING_EVIDENCE_SOURCE_ROWS_OUT" "$SEALED_LEARNING_EVIDENCE_SOURCE_ROWS_LATEST"' in src
    assert 'cp "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT" "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_LATEST"' in src
    assert 'cp "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT" "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_LATEST"' in src
    assert 'cp "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT" "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_LATEST"' in src
    assert 'cp "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT" "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_LATEST"' in src
    assert 'cp "$FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_OUT" "$FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_LATEST"' in src
    assert 'cp "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT" "$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_LATEST"' in src
    assert 'cp "$BOUNDED_PROBE_RESULT_REVIEW_OUT" "$BOUNDED_PROBE_RESULT_REVIEW_LATEST"' in src
    assert 'cp "$BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_OUT" "$BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_LATEST"' in src
    assert 'SCORECARD_JSON_OUT="$SCORECARD_JSON_OUT" SCORECARD_JSON="$SCORECARD_JSON" SCORECARD_RC="$scorecard_rc" REFRESH_SCORECARD="$REFRESH_SCORECARD"' in src
    assert 'DATA_FLOW_JSON_OUT="$DATA_FLOW_JSON_OUT" DATA_FLOW_JSON="$DATA_FLOW_JSON" DATA_FLOW_MONITOR_RC="$data_flow_monitor_rc" REFRESH_DATA_FLOW_MONITOR="$REFRESH_DATA_FLOW_MONITOR"' in src
    assert 'ORDER_TOUCHABILITY_JSON_OUT="$ORDER_TOUCHABILITY_JSON_OUT" ORDER_TOUCHABILITY_JSON="$ORDER_TOUCHABILITY_JSON" ORDER_TOUCHABILITY_AUDIT_RC="$order_touchability_audit_rc"' in src
    assert 'DECISION_PACKET_JSON_OUT="$DECISION_PACKET_JSON_OUT" DECISION_PACKET_JSON="$DECISION_PACKET_JSON" DECISION_PACKET_RC="$decision_packet_rc" REFRESH_DECISION_PACKET="$REFRESH_DECISION_PACKET"' in src
    assert 'PLAN_OUT="$PLAN_OUT" PLAN_JSON="$PLAN_JSON" PLAN_RC="$plan_rc" REFRESH_PLAN="$REFRESH_PLAN"' in src
    assert 'export SEALED_LEARNING_EVIDENCE_OUT="$SEALED_LEARNING_EVIDENCE_OUT"' in src
    assert 'export SEALED_HORIZON_LEARNING_EVIDENCE_RC="$sealed_horizon_learning_evidence_rc"' in src
    assert 'export FALSE_NEGATIVE_OPERATOR_REVIEW_OUT="$FALSE_NEGATIVE_OPERATOR_REVIEW_OUT"' in src
    assert 'export FALSE_NEGATIVE_OPERATOR_REVIEW_RC="$false_negative_operator_review_rc"' in src
    assert 'export LEARNING_SSOT_DECISION_OUT="$LEARNING_SSOT_DECISION_OUT"' in src
    assert 'export AUTONOMOUS_PARAMETER_PROPOSAL_OUT="$AUTONOMOUS_PARAMETER_PROPOSAL_OUT"' in src
    assert 'export FALSE_NEGATIVE_BOUNDED_PREFLIGHT_OUT="$FALSE_NEGATIVE_BOUNDED_PREFLIGHT_OUT"' in src
    assert 'export BOUNDED_PROBE_PREFLIGHT_SOURCE_JSON="$BOUNDED_PROBE_PREFLIGHT_SOURCE_JSON"' in src
    assert '"sealed_horizon_learning_evidence_status": sealed_learning.get("status")' in src
    assert '"false_negative_operator_review_status": false_negative_operator_review.get("status")' in src
    assert '"learning_ssot_decision_status": learning_ssot_decision.get("status")' in src
    assert '"autonomous_parameter_proposal_status": autonomous_parameter_proposal.get("status")' in src
    assert '"false_negative_bounded_probe_preflight_status": false_negative_bounded_preflight.get("status")' in src
    assert 'sealed_horizon_learning_evidence_skip_reason="horizon_sealed_replay_missing"' in src
    assert '"horizon_sealed_replay_path": os.environ["HORIZON_SEALED_REPLAY_JSON"] or None' in src
    assert 'BOUNDED_PROBE_PREFLIGHT_JSON="$BOUNDED_PROBE_PREFLIGHT_SOURCE_JSON"' in src
    assert 'ORDER_TOUCHABILITY_JSON="$ORDER_TOUCHABILITY_JSON" BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT="$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT"' in src
    assert 'BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT="$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT" BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_LATEST="$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_LATEST"' in src
    assert 'BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT="$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT" BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_LATEST="$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_LATEST"' in src
    assert 'BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT="$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT" BOUNDED_PROBE_OPERATOR_AUTHORIZATION_LATEST="$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_LATEST"' in src
    assert 'FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_OUT="$FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_OUT" FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_LATEST="$FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_LATEST"' in src
    assert 'export BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT="$BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_OUT"' in src
    assert "scorecard_rc=" in src
    assert "data_flow_monitor_rc=" in src
    assert "order_touchability_audit_rc=" in src
    assert "decision_packet_rc=" in src
    assert "plan_rc=" in src
    assert "sealed_horizon_learning_evidence_rc=" in src
    assert "false_negative_operator_review_rc=" in src
    assert "learning_ssot_decision_rc=" in src
    assert "autonomous_parameter_proposal_rc=" in src
    assert "false_negative_bounded_preflight_rc=" in src
    assert "bounded_probe_placement_repair_plan_rc=" in src
    assert "bounded_probe_authority_patch_readiness_rc=" in src
    assert "bounded_probe_operator_authorization_rc=" in src
    assert "false_negative_candidate_friction_scorecard_rc=" in src
    assert "bounded_probe_shadow_placement_impact_rc=" in src
    scorecard_index = src.index('"$PYBIN" "${SCORECARD_ARGS[@]}"')
    data_flow_index = src.index('"$PYBIN" "${DATA_FLOW_ARGS[@]}"')
    order_touchability_index = src.index('"$PYBIN" "${ORDER_TOUCHABILITY_ARGS[@]}"')
    plan_index = src.index('"$PYBIN" "${PLAN_ARGS[@]}"')
    materializer_index = src.index('"$PYBIN" "${MATERIALIZER_ARGS[@]}"')
    refresh_index = src.index('"$PYBIN" "${REFRESH_ARGS[@]}"')
    review_index = src.index('"$PYBIN" "${REVIEW_ARGS[@]}"')
    false_negative_packet_index = src.index(
        '"$PYBIN" "${FALSE_NEGATIVE_CANDIDATE_PACKET_ARGS[@]}"'
    )
    false_negative_operator_review_index = src.index(
        '"$PYBIN" "${FALSE_NEGATIVE_OPERATOR_REVIEW_ARGS[@]}"'
    )
    learning_ssot_index = src.index("cost_gate_learning_lane.learning_ssot_decision")
    autonomous_proposal_index = src.index(
        "cost_gate_learning_lane.autonomous_parameter_proposal"
    )
    false_negative_preflight_index = src.index(
        "cost_gate_learning_lane.false_negative_bounded_probe_preflight"
    )
    sealed_evidence_index = src.index('"$PYBIN" "${SEALED_LEARNING_EVIDENCE_ARGS[@]}"')
    touchability_index = src.index('"$PYBIN" "${BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_ARGS[@]}"')
    placement_index = src.index('"$PYBIN" "${BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_ARGS[@]}"')
    authority_index = src.index('"$PYBIN" "${BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_ARGS[@]}"')
    operator_auth_index = src.index('"$PYBIN" "${BOUNDED_PROBE_OPERATOR_AUTHORIZATION_ARGS[@]}"')
    friction_scorecard_index = src.index(
        '"$PYBIN" "${FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_ARGS[@]}"'
    )
    shadow_index = src.index('"$PYBIN" "${BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_ARGS[@]}"')
    result_review_index = src.index('"$PYBIN" "${BOUNDED_PROBE_RESULT_REVIEW_ARGS[@]}"')
    execution_review_index = src.index('"$PYBIN" "${BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_ARGS[@]}"')
    decision_packet_index = src.index('"$PYBIN" "${DECISION_PACKET_ARGS[@]}"')
    assert scorecard_index < plan_index
    assert scorecard_index < data_flow_index < plan_index
    assert plan_index < materializer_index
    assert (
        materializer_index
        < refresh_index
        < review_index
        < false_negative_packet_index
        < false_negative_operator_review_index
        < learning_ssot_index
        < autonomous_proposal_index
        < false_negative_preflight_index
        < sealed_evidence_index
    )
    assert sealed_evidence_index < order_touchability_index < touchability_index < placement_index < authority_index < operator_auth_index < friction_scorecard_index < shadow_index < result_review_index < execution_review_index
    assert execution_review_index < decision_packet_index


def test_wrapper_bounded_probe_reviews_use_fresh_result_review_only() -> None:
    src = _src(WRAPPER)
    assert 'SEALED_PREFLIGHT_JSON="${OPENCLAW_COST_GATE_SEALED_HORIZON_BOUNDED_PROBE_PREFLIGHT_JSON:-$LANE_DIR/sealed_horizon_probe_preflight_latest.json}"' in src
    assert 'FALSE_NEGATIVE_BOUNDED_PREFLIGHT_JSON="${OPENCLAW_COST_GATE_FALSE_NEGATIVE_BOUNDED_PROBE_PREFLIGHT_JSON:-$LANE_DIR/false_negative_bounded_probe_preflight_latest.json}"' in src
    assert 'BOUNDED_PROBE_PREFLIGHT_SOURCE_JSON="${OPENCLAW_COST_GATE_BOUNDED_PROBE_PREFLIGHT_JSON:-$FALSE_NEGATIVE_BOUNDED_PREFLIGHT_JSON}"' in src
    assert 'BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_JSON="${OPENCLAW_COST_GATE_BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_JSON:-$LANE_DIR/bounded_probe_authority_patch_readiness_latest.json}"' in src
    assert 'BOUNDED_PROBE_OPERATOR_AUTHORIZATION_JSON="${OPENCLAW_COST_GATE_BOUNDED_PROBE_OPERATOR_AUTHORIZATION_JSON:-$LANE_DIR/bounded_probe_operator_authorization_latest.json}"' in src
    assert 'ORDER_TOUCHABILITY_DIR="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_AUDIT_DIR:-$DATA/demo_order_to_fill_gap}"' in src
    assert 'ORDER_TOUCHABILITY_JSON="${OPENCLAW_DEMO_ORDER_TO_FILL_GAP_AUDIT_JSON:-$ORDER_TOUCHABILITY_DIR/demo_order_to_fill_gap_latest.json}"' in src
    assert '--preflight-json "$BOUNDED_PROBE_PREFLIGHT_SOURCE_JSON"' in src
    assert '--order-to-fill-gap-json "$ORDER_TOUCHABILITY_JSON"' in src
    assert '--touchability-preflight-json "$BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT"' in src
    assert '--placement-repair-plan-json "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT"' in src
    assert '--authority-patch-readiness-json "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT"' in src
    assert '--result-review-json "$BOUNDED_PROBE_RESULT_REVIEW_OUT"' in src
    assert "BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_LATEST" in src
    assert "BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_MD_LATEST" in src
    assert "BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_LATEST" in src
    assert "BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_MD_LATEST" in src
    assert "BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_LATEST" in src
    assert "BOUNDED_PROBE_SHADOW_PLACEMENT_IMPACT_MD_LATEST" in src
    assert "BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_LATEST" in src
    assert "BOUNDED_PROBE_OPERATOR_AUTHORIZATION_LATEST" in src
    assert 'if [[ -f "$BOUNDED_PROBE_PREFLIGHT_SOURCE_JSON" ]]' in src
    assert 'bounded_probe_result_review_skip_reason="bounded_probe_preflight_missing"' in src
    assert 'if [[ -f "$BOUNDED_PROBE_RESULT_REVIEW_OUT" ]]' in src
    assert 'bounded_probe_execution_realism_review_skip_reason="bounded_probe_result_review_missing"' in src
    assert "BOUNDED_PROBE_RESULT_REVIEW_LATEST" in src
    assert "BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_LATEST" in src


def test_wrapper_atomically_publishes_candidate_board_to_service_rendezvous() -> None:
    src = _src(WRAPPER)
    assert (
        'ALR_CANDIDATE_EVIDENCE_DIR="${ALR_CANDIDATE_EVIDENCE_DIR:-$HOME/.local/share/openclaw/alr-candidate-evidence}"'
        in src
    )
    assert 'ALR_CANDIDATE_EVIDENCE_RETENTION="${ALR_CANDIDATE_EVIDENCE_RETENTION:-128}"' in src
    assert 'ALR_CANDIDATE_EVIDENCE_MAX_BYTES="${ALR_CANDIDATE_EVIDENCE_MAX_BYTES:-67108864}"' in src
    assert 'validate_bounded_int "ALR_CANDIDATE_EVIDENCE_RETENTION" "$ALR_CANDIDATE_EVIDENCE_RETENTION" 1 128' in src
    assert 'validate_bounded_int "ALR_CANDIDATE_EVIDENCE_MAX_BYTES" "$ALR_CANDIDATE_EVIDENCE_MAX_BYTES" 1 67108864' in src
    assert "-m cost_gate_learning_lane.candidate_board_publisher" in src
    assert '--source "$REVIEW_OUT"' in src
    assert '--destination "$ALR_CANDIDATE_EVIDENCE_DIR"' in src
    assert '--retention-limit "$ALR_CANDIDATE_EVIDENCE_RETENTION"' in src
    assert '--max-total-bytes "$ALR_CANDIDATE_EVIDENCE_MAX_BYTES"' in src
    review_index = src.index('"$PYBIN" "${REVIEW_ARGS[@]}"')
    publish_index = src.index('"$PYBIN" "${CANDIDATE_BOARD_PUBLISH_ARGS[@]}"')
    latest_index = src.index('cp "$REVIEW_OUT" "$REVIEW_LATEST"')
    decision_index = src.index('"$PYBIN" "${DECISION_PACKET_ARGS[@]}"')
    complete_index = src.index('research_guard_complete "${guard_complete_args[@]}"')
    assert review_index < latest_index < decision_index < complete_index < publish_index
    assert 'candidate_board_publish_status="DEFERRED_PENDING_RUN_COMPLETION"' in src
    assert 'guard_state_status="$(_research_guard_state_status' in src
    assert 'if [[ "$guard_complete_rc" == "0" && "$guard_state_status" == "COMPLETE"' in src
    assert 'cp "$REVIEW_OUT" "$ALR_CANDIDATE_EVIDENCE_DIR/' not in src
    assert "blocked_outcome_review_latest.json" not in src[
        src.index("CANDIDATE_BOARD_PUBLISH_ARGS=(") : publish_index
    ]
    assert 'candidate_board_publish_status="PUBLISHED_OR_ALREADY_PUBLISHED"' in src
    assert 'candidate_board_publish_status="FAILED"' in src
    assert 'candidate_board_publish_status="SKIPPED"' in src
    assert 'candidate_board_publish_skip_reason="run_incomplete"' in src
    assert 'candidate_board_publish_skip_reason="preinstall_refresh_only"' in src
    assert '"candidate_board_publish_rc": int(os.environ["CANDIDATE_BOARD_PUBLISH_RC"])' in src
    assert '"candidate_board_publish_status": os.environ["CANDIDATE_BOARD_PUBLISH_STATUS"]' in src
    assert '"candidate_board_publish_skip_reason": os.environ["CANDIDATE_BOARD_PUBLISH_SKIP_REASON"] or None' in src
    assert '"candidate_board_publish_source_content_sha256": (' in src
    assert '"candidate_board_publish_artifact_sha256": (' in src
    assert 'candidate_board_publish_sha' in src


def test_wrapper_operator_authorization_stage_uses_standing_env_without_raw_auth_fields() -> None:
    src = _src(WRAPPER)
    assert "BOUNDED_PROBE_OPERATOR_AUTHORIZATION_ARGS=(" in src
    assert "-m cost_gate_learning_lane.bounded_probe_operator_authorization_cli" in src
    assert '--decision "$BOUNDED_PROBE_OPERATOR_AUTHORIZATION_DECISION"' in src
    assert 'STANDING_DEMO_AUTHORIZATION_JSON="${OPENCLAW_COST_GATE_STANDING_DEMO_AUTHORIZATION_JSON:-}"' in src
    assert "--standing-demo-authorization-json" in src
    assert "--operator-id" not in src
    assert "--authorization-id" not in src
    assert "--typed-confirm" not in src
    assert "bounded_probe_operator_authorization_ready_for_review" in src
    assert "bounded_probe_operator_authorization_object_emitted" in src
    assert "bounded_probe_operator_authorization_active_runtime_order_authority" in src
    assert "operator_authorization_object_emitted" in src
    assert "active_runtime_order_authority" in src


def test_wrapper_false_negative_default_defer_preserves_existing_review_input() -> None:
    src = _src(WRAPPER)
    assert "--existing-operator-review-json" in src
    assert '--existing-operator-review-json "$FALSE_NEGATIVE_OPERATOR_REVIEW_LATEST"' in src
    assert "--decision defer" in src
    assert 'cp "$FALSE_NEGATIVE_OPERATOR_REVIEW_OUT" "$FALSE_NEGATIVE_OPERATOR_REVIEW_LATEST"' in src


def test_wrapper_false_negative_stages_use_standing_env_without_raw_auth_fields() -> None:
    src = _src(WRAPPER)
    review_index = src.index("FALSE_NEGATIVE_OPERATOR_REVIEW_ARGS=(")
    auth_index = src.index("BOUNDED_PROBE_OPERATOR_AUTHORIZATION_ARGS=(")
    preflight_index = src.index('if [[ "$REFRESH_FALSE_NEGATIVE_BOUNDED_PROBE_PREFLIGHT" == "1" ]]')
    preflight_end = src.index('cp "$FALSE_NEGATIVE_BOUNDED_PREFLIGHT_OUT"', preflight_index)
    review_block = src[review_index:auth_index]
    preflight_block = src[preflight_index:preflight_end]

    assert 'STANDING_DEMO_AUTHORIZATION_JSON="${OPENCLAW_COST_GATE_STANDING_DEMO_AUTHORIZATION_JSON:-}"' in src
    assert '--standing-demo-authorization-json "$STANDING_DEMO_AUTHORIZATION_JSON"' in review_block
    assert '--standing-demo-authorization-json "$STANDING_DEMO_AUTHORIZATION_JSON"' in preflight_block
    assert "--operator-id" not in review_block
    assert "--authorization-id" not in review_block
    assert "--typed-confirm" not in review_block
    assert "--operator-id" not in preflight_block
    assert "--authorization-id" not in preflight_block
    assert "--typed-confirm" not in preflight_block


def test_wrapper_has_preinstall_refresh_only_cutoff_after_plan_refresh() -> None:
    src = _src(WRAPPER)
    assert 'if [[ "$PREINSTALL_REFRESH_ONLY" == "1" ]]' in src
    assert "preinstall refresh-only mode" in src
    assert (
        "skipped historical/materializer/outcome/review/false-negative "
        "packet/false-negative operator review/learning ssot/autonomous proposal/"
        "false-negative preflight/sealed evidence/bounded-probe/friction-scorecard stages"
    ) in src
    assert 'PREINSTALL_REFRESH_ONLY="$PREINSTALL_REFRESH_ONLY"' in src
    assert '"preinstall_refresh_only": os.environ["PREINSTALL_REFRESH_ONLY"] == "1"' in src
    assert 'order_touchability_audit_skip_reason="preinstall_refresh_only"' in src
    assert 'false_negative_candidate_packet_skip_reason="preinstall_refresh_only"' in src
    assert 'false_negative_operator_review_skip_reason="preinstall_refresh_only"' in src
    assert 'learning_ssot_decision_skip_reason="preinstall_refresh_only"' in src
    assert 'autonomous_parameter_proposal_skip_reason="preinstall_refresh_only"' in src
    assert 'false_negative_bounded_preflight_skip_reason="preinstall_refresh_only"' in src
    assert 'sealed_horizon_learning_evidence_skip_reason="preinstall_refresh_only"' in src
    assert 'bounded_probe_touchability_preflight_skip_reason="preinstall_refresh_only"' in src
    assert 'bounded_probe_placement_repair_plan_skip_reason="preinstall_refresh_only"' in src
    assert 'bounded_probe_authority_patch_readiness_skip_reason="preinstall_refresh_only"' in src
    assert 'bounded_probe_operator_authorization_skip_reason="preinstall_refresh_only"' in src
    assert 'false_negative_candidate_friction_scorecard_skip_reason="preinstall_refresh_only"' in src
    assert 'bounded_probe_shadow_placement_impact_skip_reason="preinstall_refresh_only"' in src
    assert 'bounded_probe_result_review_skip_reason="preinstall_refresh_only"' in src
    assert 'bounded_probe_execution_realism_review_skip_reason="preinstall_refresh_only"' in src
    plan_copy_index = src.index('cp "$PLAN_OUT" "$PLAN_JSON"')
    preinstall_index = src.index('if [[ "$PREINSTALL_REFRESH_ONLY" == "1" ]]')
    historical_index = src.index('"$PYBIN" "${HISTORICAL_REVIEW_ARGS[@]}"')
    materializer_index = src.index('"$PYBIN" "${MATERIALIZER_ARGS[@]}"')
    refresh_index = src.index('"$PYBIN" "${REFRESH_ARGS[@]}"')
    review_index = src.index('"$PYBIN" "${REVIEW_ARGS[@]}"')
    false_negative_packet_index = src.index(
        '"$PYBIN" "${FALSE_NEGATIVE_CANDIDATE_PACKET_ARGS[@]}"'
    )
    false_negative_operator_review_index = src.index(
        '"$PYBIN" "${FALSE_NEGATIVE_OPERATOR_REVIEW_ARGS[@]}"'
    )
    learning_ssot_index = src.index("cost_gate_learning_lane.learning_ssot_decision")
    autonomous_proposal_index = src.index(
        "cost_gate_learning_lane.autonomous_parameter_proposal"
    )
    false_negative_preflight_index = src.index(
        "cost_gate_learning_lane.false_negative_bounded_probe_preflight"
    )
    sealed_evidence_index = src.index('"$PYBIN" "${SEALED_LEARNING_EVIDENCE_ARGS[@]}"')
    order_touchability_index = src.index('"$PYBIN" "${ORDER_TOUCHABILITY_ARGS[@]}"')
    touchability_index = src.index('"$PYBIN" "${BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_ARGS[@]}"')
    placement_index = src.index('"$PYBIN" "${BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_ARGS[@]}"')
    authority_index = src.index('"$PYBIN" "${BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_ARGS[@]}"')
    operator_auth_index = src.index('"$PYBIN" "${BOUNDED_PROBE_OPERATOR_AUTHORIZATION_ARGS[@]}"')
    friction_scorecard_index = src.index(
        '"$PYBIN" "${FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_ARGS[@]}"'
    )
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
        < false_negative_packet_index
        < false_negative_operator_review_index
        < learning_ssot_index
        < autonomous_proposal_index
        < false_negative_preflight_index
        < sealed_evidence_index
        < order_touchability_index
        < touchability_index
        < placement_index
        < authority_index
        < operator_auth_index
        < friction_scorecard_index
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
