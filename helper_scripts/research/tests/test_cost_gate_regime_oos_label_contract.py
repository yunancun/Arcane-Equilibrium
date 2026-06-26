from __future__ import annotations

import datetime as dt
from pathlib import Path

from cost_gate_learning_lane.regime_oos_label_contract import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    CONTROL_IDENTITY_NOT_READY_STATUS,
    GAP_CLOSURE_NOT_READY_STATUS,
    READY_STATUS,
    REQUIRED_GAPS_MISSING_STATUS,
    SCHEMA_VERSION,
    build_regime_oos_label_contract,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 26, 14, 20, tzinfo=dt.timezone.utc)


def _candidate() -> dict:
    return {
        "side_cell_key": "grid_trading|AVAXUSDT|Sell",
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }


def _gap_closure(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_false_negative_evidence_floor_gap_closure_design_v1",
        "status": "EVIDENCE_FLOOR_GAP_CLOSURE_DESIGN_READY_NO_AUTHORITY",
        "candidate": _candidate(),
        "gap_closure_items": [
            {
                "gap_key": "regime_breadth_freshness_survivorship_labels",
                "lane": "source_only_data_design",
            },
            {
                "gap_key": "repeat_or_oos_path_before_any_promotion_claim",
                "lane": "source_only_validation_design",
            },
        ],
        "answers": {
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "cap_envelope_mutation_allowed": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def _control_identity(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_source_only_control_identity_contract_v1",
        "status": "SOURCE_ONLY_CONTROL_IDENTITY_CONTRACT_READY_NO_AUTHORITY",
        "candidate": _candidate(),
        "contract": {
            "candidate_identity": _candidate(),
        },
        "answers": {
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "cap_envelope_mutation_allowed": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def test_regime_oos_contract_ready_without_authority() -> None:
    packet = build_regime_oos_label_contract(
        gap_closure=_gap_closure(),
        control_identity=_control_identity(),
        selected_side_cell_key="grid_trading|AVAXUSDT|Sell",
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["summary"]["point_in_time_regime_required"] is True
    assert packet["summary"]["survivorship_labels_required"] is True
    assert packet["summary"]["repeat_or_oos_required_before_promotion"] is True
    assert packet["summary"]["runtime_or_pg_label_query_performed"] is False
    assert packet["answers"]["pg_query_performed"] is False
    assert packet["answers"]["order_authority_granted"] is False
    contract = packet["contract"]
    assert contract["candidate_identity"]["required_exact_fields"]["symbol"] == "AVAXUSDT"
    label_groups = contract["label_groups"]
    point_in_time = label_groups["point_in_time_regime"]
    assert "market_anchor_regime" in point_in_time["required_fields"]
    assert "overlay_flags" in point_in_time["required_fields"]
    assert "fixed before candidate scoring" in point_in_time["classifier_threshold_rule"]
    assert "raw input only" in point_in_time["bybit_market_data_role"]
    assert "breadth_survivorship" in label_groups
    assert "repeat_oos" in label_groups
    freshness = label_groups["freshness"]
    assert "freshness_bucket" in freshness["required_fields"]
    assert "recent_90d_net_bps" in freshness["required_fields"]
    assert "recent_180d_net_bps" in freshness["required_fields"]
    assert freshness["freshness_gate_lowering_allowed"] is False
    assert "survivorship_mode" in label_groups["breadth_survivorship"]["required_fields"]
    repeat_oos = label_groups["repeat_oos"]
    for field in [
        "purge_seconds",
        "embargo_seconds",
        "n_independent",
        "sample_unit",
        "final_verdict_label",
        "reject_reasons",
    ]:
        assert field in repeat_oos["required_fields"]
    assert "durable-alpha candidate" in repeat_oos["allowed_final_verdict_labels"]
    downgrades = contract["adr_0047_downgrade_rules"]
    assert downgrades["bull_heavy_or_rally_only_positive"] == (
        "regime-bet / learning-only"
    )
    assert downgrades["2024_dominated_or_stale_year_positive"] == (
        "stale-data artifact"
    )
    assert downgrades["current_survivor_only_or_narrow_breadth"] == (
        "breadth-limited"
    )
    assert "label_feature_ts_after_signal_ts" in contract["failure_conditions"]
    assert "missing_recent_90d_or_180d_net_fields" in contract["failure_conditions"]
    assert "classifier_thresholds_changed_after_scoring" in contract["failure_conditions"]
    assert "Regime/OOS Label Contract" in markdown


def test_authority_bearing_input_fails_closed() -> None:
    gap = _gap_closure()
    gap["answers"]["probe_authority_granted"] = True

    packet = build_regime_oos_label_contract(
        gap_closure=gap,
        control_identity=_control_identity(),
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["contract"] == {}
    assert packet["answers"]["probe_authority_granted"] is False


def test_authority_alias_and_nonempty_proof_fields_fail_closed() -> None:
    gap = _gap_closure()
    gap["answers"]["cost_gate_proof"] = True
    gap["answers"]["authorizationId"] = "auth-123"
    gap["answers"]["orderAdmissionReady"] = "present"

    packet = build_regime_oos_label_contract(
        gap_closure=gap,
        control_identity=_control_identity(),
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["contract"] == {}
    assert "cost_gate_proof_present" in packet["authority_contamination_reasons"]
    assert "authorization_id_present" in packet["authority_contamination_reasons"]
    assert "order_admission_ready_present" in packet["authority_contamination_reasons"]


def test_not_ready_gap_closure_fails_closed() -> None:
    packet = build_regime_oos_label_contract(
        gap_closure=_gap_closure(status="NOT_READY"),
        control_identity=_control_identity(),
        now_utc=NOW,
    )

    assert packet["status"] == GAP_CLOSURE_NOT_READY_STATUS
    assert packet["contract"] == {}


def test_not_ready_control_identity_fails_closed() -> None:
    packet = build_regime_oos_label_contract(
        gap_closure=_gap_closure(),
        control_identity=_control_identity(status="NOT_READY"),
        now_utc=NOW,
    )

    assert packet["status"] == CONTROL_IDENTITY_NOT_READY_STATUS
    assert packet["contract"] == {}


def test_required_regime_oos_gaps_must_be_present() -> None:
    gap = _gap_closure()
    gap["gap_closure_items"] = [
        {"gap_key": "candidate_matched_controls_present"},
    ]

    packet = build_regime_oos_label_contract(
        gap_closure=gap,
        control_identity=_control_identity(),
        now_utc=NOW,
    )

    assert packet["status"] == REQUIRED_GAPS_MISSING_STATUS
    assert set(packet["source_gap_closure"]["missing_required_gap_keys"]) == {
        "regime_breadth_freshness_survivorship_labels",
        "repeat_or_oos_path_before_any_promotion_claim",
    }


def test_candidate_mismatch_fails_closed() -> None:
    control = _control_identity()
    control["candidate"] = {
        **_candidate(),
        "side_cell_key": "grid_trading|SUIUSDT|Sell",
        "symbol": "SUIUSDT",
    }

    packet = build_regime_oos_label_contract(
        gap_closure=_gap_closure(),
        control_identity=control,
        selected_side_cell_key="grid_trading|AVAXUSDT|Sell",
        now_utc=NOW,
    )

    assert packet["status"] == "REGIME_OOS_CANDIDATE_MISMATCH"
    assert packet["candidate"] == {}


def test_incomplete_candidate_identity_fails_closed() -> None:
    incomplete_candidate = {"side_cell_key": "grid_trading|AVAXUSDT|Sell"}

    packet = build_regime_oos_label_contract(
        gap_closure=_gap_closure(candidate=incomplete_candidate),
        control_identity=_control_identity(candidate=incomplete_candidate),
        selected_side_cell_key="grid_trading|AVAXUSDT|Sell",
        now_utc=NOW,
    )

    assert packet["status"] == "REGIME_OOS_CANDIDATE_MISMATCH"
    assert packet["candidate"] == {}
    assert packet["contract"] == {}


def test_static_no_network_db_or_order_imports() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/regime_oos_label_contract.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "psycopg",
        "requests",
        "urllib",
        "ccxt",
        "pybit",
        "subprocess",
        "create_order",
        "cancel_order",
        "place_order",
    ]
    for needle in forbidden:
        assert needle not in source
