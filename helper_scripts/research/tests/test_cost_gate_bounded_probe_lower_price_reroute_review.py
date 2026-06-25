from __future__ import annotations

import datetime as dt
import json
import sys

from cost_gate_learning_lane.bounded_probe_lower_price_reroute_review import (
    LOWER_PRICE_REROUTE_REVIEW_SCHEMA_VERSION,
    READY_STATUS,
    build_lower_price_reroute_review,
    main,
)


NOW = dt.datetime(2026, 6, 24, 17, 30, tzinfo=dt.timezone.utc)
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


def _order_repair(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_order_construction_repair_v1",
        "generated_at_utc": "2026-06-24T17:18:00+00:00",
        "status": "ORDER_CONSTRUCTION_REPAIR_REQUIRED",
        "source_candidate_universe": {"valid_for_reroute_screen": True},
        "repair_options": [
            {"option_id": "lower_price_candidate_reroute_screen", "status": "AVAILABLE"}
        ],
        "candidate_universe_screen": {
            "fits_current_cap_count": 2,
            "rows": [
                {
                    **_candidate(),
                    "false_negative_rank": 1,
                    "friction_rank": 1,
                    "avg_net_bps": 73.5511,
                    "net_positive_pct": 100.0,
                    "outcome_count": 48,
                    "current_cap_usdt": 10.0,
                    "minimum_required_demo_notional_usdt_per_order": 5.0,
                    "spread_bps": 0.0,
                    "instrument_status": "Trading",
                    "fits_current_cap": True,
                },
                {
                    "side_cell_key": "grid_trading|ETCUSDT|Sell",
                    "strategy_name": "grid_trading",
                    "symbol": "ETCUSDT",
                    "side": "Sell",
                    "outcome_horizon_minutes": 60,
                    "false_negative_rank": 3,
                    "instrument_status": "Trading",
                    "fits_current_cap": True,
                },
            ],
        },
        "answers": {
            "global_cost_gate_lowering_recommended": False,
            "order_submission_performed": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _cap_selection(candidate=None, **overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_cap_feasible_candidate_selection_review_v1",
        "generated_at_utc": "2026-06-24T17:18:00+00:00",
        "status": "CAP_FEASIBLE_CANDIDATE_SELECTED_FOR_PREFLIGHT_REVIEW",
        "selected_candidate": candidate
        or {
            **_candidate(),
            "false_negative_rank": 2,
            "friction_rank": 2,
            "avg_net_bps": 73.5511,
            "net_positive_pct": 100.0,
            "outcome_count": 48,
            "current_cap_usdt": 10.0,
            "minimum_required_demo_notional_usdt_per_order": 5.0,
            "instrument_status": "Trading",
            "fits_current_cap": True,
        },
        "answers": {
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "order_authority_granted": False,
            "pg_query_performed": True,
            "pg_write_performed": False,
            "probe_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _preflight(candidate=None, **overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_false_negative_bounded_demo_probe_preflight_v1",
        "generated_at_utc": "2026-06-24T17:18:00+00:00",
        "status": "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION",
        "candidate": candidate or _candidate(),
        "answers": {
            "bounded_demo_probe_authorized": False,
            "global_cost_gate_lowering_recommended": False,
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _review(candidate=None, **overrides) -> dict:
    base = candidate or {
        "side_cell_key": SIDE_CELL,
        "strategy_names": ["grid_trading"],
        "symbols": ["AVAXUSDT"],
        "sides": ["Sell"],
        "dominant_horizon_minutes": 60,
        "false_negative_rank": 1,
        "avg_net_bps": 73.5511,
        "net_positive_pct": 100.0,
        "outcome_count": 48,
        "global_cost_gate_lowering_recommended": False,
        "order_authority_granted": False,
        "probe_authority_granted": False,
        "promotion_evidence": False,
    }
    payload = {
        "schema_version": "cost_gate_false_negative_operator_review_v1",
        "generated_at_utc": "2026-06-24T17:18:00+00:00",
        "status": "APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT",
        "selected_side_cell_key": SIDE_CELL,
        "candidate": base,
        "answers": {
            "bounded_demo_probe_authorized": False,
            "global_cost_gate_lowering_recommended": False,
            "order_authority_granted": False,
            "operator_review_approved_for_preflight": True,
            "probe_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _placement(candidate=None, **overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_placement_repair_plan_v1",
        "generated_at_utc": "2026-06-24T17:18:00+00:00",
        "status": "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW",
        "candidate": candidate or _candidate(),
        "answers": {
            "global_cost_gate_lowering_recommended": False,
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _authorization(candidate=None, **overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_operator_authorization_packet_v1",
        "generated_at_utc": "2026-06-24T17:18:00+00:00",
        "status": "READY_FOR_OPERATOR_AUTHORIZATION_REVIEW",
        "candidate": candidate or _candidate(),
        "answers": {
            "active_runtime_order_authority": False,
            "active_runtime_probe_authority": False,
            "bounded_demo_probe_authorized": False,
            "global_cost_gate_lowering_recommended": False,
            "operator_authorization_object_emitted": False,
            "order_submission_performed": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _readiness(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_authority_patch_readiness_v1",
        "generated_at_utc": "2026-06-24T17:18:00+00:00",
        "status": "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW",
        "answers": {
            "global_cost_gate_lowering_recommended": False,
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "promotion_evidence": False,
            "rust_patch_required": False,
        },
    }
    payload.update(overrides)
    return payload


def _touchability(candidate=None, **overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_touchability_preflight_v1",
        "generated_at_utc": "2026-06-24T17:18:00+00:00",
        "status": "TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE",
        "candidate": candidate or _candidate(),
        "answers": {
            "global_cost_gate_lowering_recommended": False,
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _build(**overrides) -> dict:
    args = {
        "order_construction_repair": _order_repair(),
        "false_negative_preflight": _preflight(),
        "false_negative_operator_review": _review(),
        "placement_repair_plan": _placement(),
        "operator_authorization": _authorization(),
        "authority_patch_readiness": _readiness(),
        "touchability_preflight": _touchability(),
        "demo_operational_authorization_available": True,
        "selected_side_cell_key": SIDE_CELL,
        "now_utc": NOW,
    }
    args.update(overrides)
    return build_lower_price_reroute_review(**args)


def test_ready_reroute_packet_selects_top_cap_feasible_candidate() -> None:
    packet = _build()

    assert packet["schema_version"] == LOWER_PRICE_REROUTE_REVIEW_SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["selected_candidate"]["side_cell_key"] == SIDE_CELL
    assert packet["selected_candidate"]["avg_net_bps"] == 73.5511
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["demo_operational_authorization_available_from_thread"] is True
    assert packet["readiness"]["blocking_gate_count"] == 0


def test_ready_reroute_packet_can_use_fresh_cap_feasible_selection() -> None:
    packet = _build(
        order_construction_repair=None,
        cap_feasible_selection=_cap_selection(),
    )

    assert packet["status"] == READY_STATUS
    assert packet["selected_candidate"]["side_cell_key"] == SIDE_CELL
    assert packet["candidate_selection"]["candidate_source"] == "cap_feasible_selection"
    assert packet["candidate_selection"]["feasible_candidate_count"] == 1
    assert packet["readiness"]["repair_ready"] is False
    assert packet["readiness"]["cap_feasible_selection_ready"] is True
    assert packet["readiness"]["candidate_source_ready"] is True
    assert packet["answers"]["pg_write_performed"] is False
    assert packet["authority_preserved"] is True


def test_fresh_cap_feasible_selection_replaces_stale_repair_packet() -> None:
    repair = _order_repair(generated_at_utc="2026-06-20T17:18:00+00:00")

    packet = _build(
        order_construction_repair=repair,
        cap_feasible_selection=_cap_selection(),
    )

    assert packet["status"] == READY_STATUS
    assert packet["readiness"]["repair_ready"] is False
    assert packet["readiness"]["cap_feasible_selection_ready"] is True
    assert "order_construction_repair_ready" not in packet["blocking_gates"]


def test_authority_contamination_fails_closed() -> None:
    packet = _build(
        operator_authorization=_authorization(
            answers={
                "order_submission_performed": "true",
                "global_cost_gate_lowering_recommended": False,
            }
        )
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert "order_submission_performed_contaminating" in packet[
        "authority_contamination_reasons"
    ]
    assert packet["answers"]["order_submission_performed"] is False


def test_cap_feasible_selection_authority_contamination_fails_closed() -> None:
    packet = _build(
        order_construction_repair=None,
        cap_feasible_selection=_cap_selection(
            answers={
                "global_cost_gate_lowering_recommended": False,
                "main_cost_gate_adjustment": "NONE",
                "order_authority_granted": True,
                "pg_query_performed": True,
                "pg_write_performed": False,
                "probe_authority_granted": False,
                "promotion_evidence": False,
            }
        ),
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert "order_authority_granted_contaminating" in packet[
        "authority_contamination_reasons"
    ]
    assert "pg_query_performed_contaminating" not in packet[
        "authority_contamination_reasons"
    ]


def test_cap_feasible_selection_pg_query_exception_is_answers_scoped() -> None:
    candidate = _cap_selection()["selected_candidate"]
    candidate["pg_query_performed"] = True

    packet = _build(
        order_construction_repair=None,
        cap_feasible_selection=_cap_selection(
            candidate=candidate,
            pg_query_performed=True,
        ),
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert "pg_query_performed_contaminating" in packet[
        "authority_contamination_reasons"
    ]


def test_candidate_mismatch_blocks_alignment() -> None:
    packet = _build(
        false_negative_preflight=_preflight(
            candidate=_candidate(side_cell_key="grid_trading|ETCUSDT|Sell", symbol="ETCUSDT")
        )
    )

    assert packet["status"] == "LOWER_PRICE_REROUTE_ALIGNMENT_BLOCKED"
    assert "false_negative_preflight_ready" in packet["blocking_gates"]


def test_horizon_mismatch_blocks_alignment() -> None:
    packet = _build(
        placement_repair_plan=_placement(candidate=_candidate(outcome_horizon_minutes=240))
    )

    assert packet["status"] == "LOWER_PRICE_REROUTE_ALIGNMENT_BLOCKED"
    assert "placement_repair_plan_ready" in packet["blocking_gates"]


def test_fractional_horizon_blocks_alignment() -> None:
    packet = _build(
        placement_repair_plan=_placement(candidate=_candidate(outcome_horizon_minutes=60.4))
    )

    assert packet["status"] == "LOWER_PRICE_REROUTE_ALIGNMENT_BLOCKED"
    assert "placement_repair_plan_ready" in packet["blocking_gates"]


def test_incomplete_candidate_identity_blocks_alignment() -> None:
    packet = _build(
        false_negative_preflight=_preflight(
            candidate={"side_cell_key": SIDE_CELL}
        )
    )

    assert packet["status"] == "LOWER_PRICE_REROUTE_ALIGNMENT_BLOCKED"
    assert "false_negative_preflight_ready" in packet["blocking_gates"]


def test_non_trading_candidate_is_not_feasible_even_when_upstream_fit_true() -> None:
    repair = _order_repair()
    repair["candidate_universe_screen"]["rows"][0]["instrument_status"] = "PreLaunch"

    packet = _build(order_construction_repair=repair)

    assert packet["status"] == "LOWER_PRICE_REROUTE_CANDIDATE_NOT_FEASIBLE"
    assert packet["answers"]["selected_candidate_fits_current_cap"] is False


def test_auto_selection_requires_explicit_side_cell_when_multiple_feasible() -> None:
    packet = _build(selected_side_cell_key=None)

    assert packet["status"] == "LOWER_PRICE_REROUTE_CANDIDATE_NOT_FEASIBLE"
    assert (
        "explicit_side_cell_key_required_when_multiple_feasible_candidates"
        in packet["blocking_gates"]
    )


def test_explicit_non_feasible_selection_fails_closed() -> None:
    packet = _build(selected_side_cell_key="ma_crossover|BTCUSDT|Sell")

    assert packet["status"] == "LOWER_PRICE_REROUTE_CANDIDATE_NOT_FEASIBLE"
    assert packet["answers"]["selected_candidate_fits_current_cap"] is False


def test_stale_repair_packet_is_input_required() -> None:
    repair = _order_repair(generated_at_utc="2026-06-20T17:18:00+00:00")
    packet = _build(order_construction_repair=repair)

    assert packet["status"] == "LOWER_PRICE_REROUTE_INPUT_REQUIRED"
    assert "order_construction_repair_ready" in packet["blocking_gates"]


def test_stale_cap_feasible_selection_is_input_required_without_repair() -> None:
    selection = _cap_selection(generated_at_utc="2026-06-20T17:18:00+00:00")

    packet = _build(
        order_construction_repair=None,
        cap_feasible_selection=selection,
    )

    assert packet["status"] == "LOWER_PRICE_REROUTE_INPUT_REQUIRED"
    assert "cap_feasible_candidate_selection_ready" in packet["blocking_gates"]
    assert packet["readiness"]["candidate_source_ready"] is False


def test_stale_cap_feasible_selection_cannot_borrow_repair_readiness() -> None:
    stale_candidate = {
        **_candidate(
            side_cell_key="ma_crossover|BTCUSDT|Sell",
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
        ),
        "false_negative_rank": 1,
        "friction_rank": 1,
        "avg_net_bps": 41.0,
        "net_positive_pct": 100.0,
        "outcome_count": 12,
        "current_cap_usdt": 10.0,
        "minimum_required_demo_notional_usdt_per_order": 5.0,
        "instrument_status": "Trading",
        "fits_current_cap": True,
    }

    packet = _build(
        cap_feasible_selection=_cap_selection(
            candidate=stale_candidate,
            generated_at_utc="2026-06-20T17:18:00+00:00",
        ),
        false_negative_preflight=_preflight(candidate=stale_candidate),
        false_negative_operator_review=_review(candidate=stale_candidate),
        placement_repair_plan=_placement(candidate=stale_candidate),
        operator_authorization=_authorization(candidate=stale_candidate),
        touchability_preflight=_touchability(candidate=stale_candidate),
        selected_side_cell_key=stale_candidate["side_cell_key"],
    )

    assert packet["status"] == "LOWER_PRICE_REROUTE_INPUT_REQUIRED"
    assert packet["candidate_selection"]["candidate_source"] == "cap_feasible_selection"
    assert packet["readiness"]["repair_ready"] is True
    assert packet["readiness"]["cap_feasible_selection_ready"] is False
    assert "cap_feasible_candidate_selection_ready" in packet["blocking_gates"]


def test_cli_records_input_hashes_and_demo_auth_flag(tmp_path, monkeypatch) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    paths = {
        "repair": tmp_path / "repair.json",
        "preflight": tmp_path / "preflight.json",
        "review": tmp_path / "review.json",
        "placement": tmp_path / "placement.json",
        "authorization": tmp_path / "authorization.json",
        "readiness": tmp_path / "readiness.json",
        "touchability": tmp_path / "touchability.json",
        "out": tmp_path / "out.json",
    }
    payloads = {
        "repair": _order_repair(generated_at_utc=now.isoformat()),
        "preflight": _preflight(generated_at_utc=now.isoformat()),
        "review": _review(generated_at_utc=now.isoformat()),
        "placement": _placement(generated_at_utc=now.isoformat()),
        "authorization": _authorization(generated_at_utc=now.isoformat()),
        "readiness": _readiness(generated_at_utc=now.isoformat()),
        "touchability": _touchability(generated_at_utc=now.isoformat()),
    }
    for key, payload in payloads.items():
        paths[key].write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bounded_probe_lower_price_reroute_review",
            "--order-construction-repair-json",
            str(paths["repair"]),
            "--false-negative-preflight-json",
            str(paths["preflight"]),
            "--false-negative-operator-review-json",
            str(paths["review"]),
            "--placement-repair-plan-json",
            str(paths["placement"]),
            "--operator-authorization-json",
            str(paths["authorization"]),
            "--authority-patch-readiness-json",
            str(paths["readiness"]),
            "--touchability-preflight-json",
            str(paths["touchability"]),
            "--selected-side-cell-key",
            SIDE_CELL,
            "--demo-operational-authorization-available",
            "--json-output",
            str(paths["out"]),
        ],
    )

    assert main() == 0
    packet = json.loads(paths["out"].read_text(encoding="utf-8"))

    assert packet["status"] == READY_STATUS
    assert packet["artifacts"]["order_construction_repair"]["sha256"]
    assert packet["answers"]["demo_operational_authorization_available_from_thread"] is True


def test_cli_accepts_cap_feasible_selection_without_repair(tmp_path, monkeypatch) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    paths = {
        "selection": tmp_path / "selection.json",
        "preflight": tmp_path / "preflight.json",
        "review": tmp_path / "review.json",
        "placement": tmp_path / "placement.json",
        "authorization": tmp_path / "authorization.json",
        "readiness": tmp_path / "readiness.json",
        "touchability": tmp_path / "touchability.json",
        "out": tmp_path / "out.json",
    }
    payloads = {
        "selection": _cap_selection(generated_at_utc=now.isoformat()),
        "preflight": _preflight(generated_at_utc=now.isoformat()),
        "review": _review(generated_at_utc=now.isoformat()),
        "placement": _placement(generated_at_utc=now.isoformat()),
        "authorization": _authorization(generated_at_utc=now.isoformat()),
        "readiness": _readiness(generated_at_utc=now.isoformat()),
        "touchability": _touchability(generated_at_utc=now.isoformat()),
    }
    for key, payload in payloads.items():
        paths[key].write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bounded_probe_lower_price_reroute_review",
            "--cap-feasible-selection-json",
            str(paths["selection"]),
            "--false-negative-preflight-json",
            str(paths["preflight"]),
            "--false-negative-operator-review-json",
            str(paths["review"]),
            "--placement-repair-plan-json",
            str(paths["placement"]),
            "--operator-authorization-json",
            str(paths["authorization"]),
            "--authority-patch-readiness-json",
            str(paths["readiness"]),
            "--touchability-preflight-json",
            str(paths["touchability"]),
            "--selected-side-cell-key",
            SIDE_CELL,
            "--json-output",
            str(paths["out"]),
        ],
    )

    assert main() == 0
    packet = json.loads(paths["out"].read_text(encoding="utf-8"))

    assert packet["status"] == READY_STATUS
    assert packet["artifacts"]["cap_feasible_selection"]["sha256"]
    assert packet["artifacts"]["order_construction_repair"]["present"] is False
