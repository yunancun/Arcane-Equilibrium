from __future__ import annotations

import copy
import datetime as dt
import json
import sys

from cost_gate_learning_lane import current_candidate_order_enablement_review as mod


NOW = dt.datetime(2026, 6, 27, 12, 30, tzinfo=dt.timezone.utc)
GEN = dt.datetime(2026, 6, 27, 12, 25, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|AVAXUSDT|Sell"


def _candidate(**overrides) -> dict:
    payload = {
        "side_cell_key": SIDE_CELL,
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }
    payload.update(overrides)
    return payload


def _readiness(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_probe_authority_patch_readiness_v1",
        "generated_at_utc": GEN.isoformat(),
        "status": mod.READINESS_READY_STATUS,
        "candidate": _candidate(),
        "active_caller_enablement_review": {
            "status": mod.ACTIVE_CALLER_READY_STATUS,
            "active_caller_source_ready_for_review": True,
            "evidence": {
                "runtime_active_order_request_supplier_present": True,
                "runtime_active_order_request_supplier_contract_missing": [],
                "suspicious_hardcoded_local_10_usdt_cap_matches": [],
            },
        },
        "answers": {
            "allowed_to_submit_order": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def _admission(**overrides) -> dict:
    payload = {
        "schema_version": "current_candidate_bounded_demo_admission_envelope_review_v1",
        "generated_at_utc": GEN.isoformat(),
        "status": mod.ADMISSION_READY_STATUS,
        "candidate": _candidate(),
        "failed_gates": [],
        "runtime_blockers": [],
        "source_blockers": [],
        "authority_contamination_reasons": [],
        "risk_semantics": {
            "gui_risk_config_is_source_of_truth": True,
            "risk_source_of_truth": mod.GUI_RISK_SOURCE,
            "gui_p1_risk_trade_pct": 10.0,
            "per_trade_risk_pct_fraction": 0.1,
            "position_size_max_pct": 25.0,
            "per_trade_budget_usdt": 955.24342626,
            "resolved_cap_usdt": 955.24342626,
            "local_10_usdt_cap_is_global_risk_authority": False,
            "bounded_probe_local_cap_usdt_is_authority": False,
        },
        "admission_envelope_preview": {
            "candidate": _candidate(),
            "risk_limits": {
                "risk_source_of_truth": mod.GUI_RISK_SOURCE,
                "per_trade_risk_pct_fraction": 0.1,
                "per_trade_risk_pct_display": 10.0,
                "position_size_max_pct": 25.0,
                "per_trade_budget_usdt": 955.24342626,
                "bounded_probe_local_cap_usdt_is_authority": False,
            },
            "runtime_admission_ready": False,
            "order_admission_ready": False,
        },
        "answers": {
            "review_contract_ready": True,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "allowed_to_submit_order": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def _governance(**overrides) -> dict:
    payload = {
        "schema_version": "runtime_governance_ipc_readonly_snapshot_v1",
        "generated_at_utc": GEN.isoformat(),
        "status": mod.GOVERNANCE_READY_STATUS,
        "summary": {
            "risk_level": "NORMAL",
            "position_size_multiplier": 1.0,
            "lease_live_count": 0,
            "lease_count": 0,
        },
        "runtime_blockers": [],
        "answers": {
            "runtime_readonly_ipc_call_performed": True,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "pg_write_performed": False,
            "service_restart_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
        },
    }
    payload.update(overrides)
    return payload


def _deploy(**overrides) -> dict:
    payload = {
        "schema_version": "runtime_deploy_manifest_v1",
        "generated_at_utc": GEN.isoformat(),
        "status": mod.DEPLOY_READY_STATUS,
        "runtime_source": {
            "head": "e8b5c77b171547f0660765cd6e4a9c77f391d70a",
        },
        "deploy": {
            "new_engine_pid": 3944810,
            "atomic_sha_verified": True,
            "running_proc_sha256": "abc123",
            "disk_sha256": "abc123",
        },
        "runtime_posture": {
            "OPENCLAW_ALLOW_MAINNET": "0",
            "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED": "",
            "OPENCLAW_DEMO_LEARNING_LANE_WRITER": "",
        },
    }
    payload.update(overrides)
    return payload


def _packet(**overrides) -> dict:
    kwargs = {
        "readiness_packet": _readiness(),
        "admission_review": _admission(),
        "governance_snapshot": _governance(),
        "deploy_manifest": _deploy(),
        "candidate_side_cell_key": SIDE_CELL,
        "now_utc": NOW,
    }
    kwargs.update(overrides)
    return mod.build_current_candidate_order_enablement_review(**kwargs)


def test_ready_packet_is_only_ready_for_e3_bb_review_no_order() -> None:
    packet = _packet()

    assert packet["status"] == mod.READY_FOR_E3_BB_STATUS
    assert packet["loss_control_blockers"] == []
    assert packet["authority_boundary_violation"] is None
    assert packet["answers"]["e3_bb_enablement_review_ready"] is True
    assert packet["answers"]["order_capable_action_allowed"] is False
    assert packet["answers"]["allowed_to_submit_order"] is False
    assert packet["admission_review"]["per_trade_risk_pct_fraction"] == 0.1
    assert packet["admission_review"]["gui_p1_risk_trade_pct"] == 10.0
    assert packet["admission_review"]["per_trade_budget_usdt"] > 10.0
    assert "active_bounded_demo_decision_lease" in packet[
        "required_same_window_gates_before_order_capable_action"
    ]
    assert "fresh_actual_admission_bbo_and_instrument_snapshot" in packet[
        "required_same_window_gates_before_order_capable_action"
    ]


def test_admission_authority_contamination_fails_closed() -> None:
    admission = _admission()
    admission["answers"]["allowed_to_submit_order"] = True

    packet = _packet(admission_review=admission)

    assert packet["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["authority_boundary_violation"].endswith(".allowed_to_submit_order")
    assert packet["answers"]["order_capable_action_allowed"] is False
    assert packet["answers"]["allowed_to_submit_order"] is False


def test_gui_ten_percent_must_not_be_treated_as_ten_usdt() -> None:
    admission = _admission()
    admission["risk_semantics"]["per_trade_risk_pct_fraction"] = 10.0
    admission["risk_semantics"]["per_trade_budget_usdt"] = 10.0
    admission["admission_envelope_preview"]["risk_limits"][
        "per_trade_risk_pct_fraction"
    ] = 10.0
    admission["admission_envelope_preview"]["risk_limits"][
        "per_trade_budget_usdt"
    ] = 10.0

    packet = _packet(admission_review=admission)

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "per_trade_risk_pct_fraction_not_0_1" in packet["loss_control_blockers"]
    assert "per_trade_budget_not_equity_resolved" in packet["loss_control_blockers"]
    assert packet["answers"]["order_capable_action_allowed"] is False


def test_deploy_runtime_posture_blocks_adapter_or_writer_enabled() -> None:
    deploy = _deploy()
    deploy["runtime_posture"]["OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED"] = "1"
    deploy["runtime_posture"]["OPENCLAW_DEMO_LEARNING_LANE_WRITER"] = "1"

    packet = _packet(deploy_manifest=deploy)

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "bounded_probe_adapter_enabled_before_review" in packet[
        "loss_control_blockers"
    ]
    assert "demo_learning_lane_writer_enabled_before_review" in packet[
        "loss_control_blockers"
    ]
    assert packet["answers"]["adapter_enabled_by_this_packet"] is False


def test_governance_blocks_non_normal_guardian_and_live_leases() -> None:
    governance = _governance()
    governance["summary"]["risk_level"] = "CAUTIOUS"
    governance["summary"]["position_size_multiplier"] = 0.7
    governance["summary"]["lease_live_count"] = 1
    governance["summary"]["lease_count"] = 1

    packet = _packet(governance_snapshot=governance)

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "guardian_not_normal" in packet["loss_control_blockers"]
    assert "guardian_multiplier_not_one" in packet["loss_control_blockers"]
    assert "lease_live_count_nonzero_before_enablement" in packet[
        "loss_control_blockers"
    ]
    assert packet["answers"]["decision_lease_acquire_performed"] is False


def test_stale_artifacts_block_loss_control() -> None:
    packet = _packet(
        now_utc=NOW + dt.timedelta(hours=1),
        max_artifact_age_seconds=60,
    )

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "readiness_stale" in packet["loss_control_blockers"]
    assert "admission_stale" in packet["loss_control_blockers"]
    assert "governance_stale" in packet["loss_control_blockers"]
    assert "deploy_stale" in packet["loss_control_blockers"]
    assert packet["answers"]["order_capable_action_allowed"] is False


def test_cli_writes_json_and_markdown_no_order(tmp_path, monkeypatch) -> None:
    readiness_path = tmp_path / "readiness.json"
    admission_path = tmp_path / "admission.json"
    governance_path = tmp_path / "governance.json"
    deploy_path = tmp_path / "deploy.json"
    json_output = tmp_path / "review.json"
    md_output = tmp_path / "review.md"

    readiness_path.write_text(json.dumps(_readiness()), encoding="utf-8")
    admission_path.write_text(json.dumps(_admission()), encoding="utf-8")
    governance_path.write_text(json.dumps(_governance()), encoding="utf-8")
    deploy_path.write_text(json.dumps(_deploy()), encoding="utf-8")

    argv = [
        "current_candidate_order_enablement_review",
        "--readiness-json",
        str(readiness_path),
        "--admission-review-json",
        str(admission_path),
        "--governance-snapshot-json",
        str(governance_path),
        "--deploy-manifest-json",
        str(deploy_path),
        "--candidate-side-cell-key",
        SIDE_CELL,
        "--now-utc",
        NOW.isoformat(),
        "--json-output",
        str(json_output),
        "--output",
        str(md_output),
    ]
    monkeypatch.setattr(sys, "argv", copy.deepcopy(argv))

    assert mod.main() == 0
    packet = json.loads(json_output.read_text(encoding="utf-8"))

    assert packet["status"] == mod.READY_FOR_E3_BB_STATUS
    assert packet["answers"]["order_capable_action_allowed"] is False
    assert "Order-capable action allowed: `False`" in md_output.read_text(
        encoding="utf-8"
    )
