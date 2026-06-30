from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane import standing_demo_authorization_refresh_guardrail as mod


NOW = dt.datetime(2026, 6, 30, 21, 0, tzinfo=dt.timezone.utc)
GEN = dt.datetime(2026, 6, 30, 20, 58, tzinfo=dt.timezone.utc)
OLD_GEN = dt.datetime(2026, 6, 29, 17, 49, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|ETHUSDT|Buy"


def _candidate(**overrides) -> dict:
    payload = {
        "side_cell_key": SIDE_CELL,
        "strategy_name": "grid_trading",
        "symbol": "ETHUSDT",
        "side": "Buy",
        "outcome_horizon_minutes": 60,
    }
    payload.update(overrides)
    return payload


def _answers(**overrides) -> dict:
    payload = {
        "candidate_scoping_required": True,
        "demo_only": True,
        "active_runtime_probe_authority": False,
        "active_runtime_order_authority": False,
        "bounded_demo_probe_authorized": False,
        "operator_authorization_object_emitted": False,
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "order_submission_performed": False,
        "runtime_mutation_performed": False,
        "env_mutation_performed": False,
        "crontab_mutation_performed": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "live_authority_granted": False,
        "promotion_evidence": False,
        "promotion_proof": False,
    }
    payload.update(overrides)
    return payload


def _existing_authorization(**overrides) -> dict:
    payload = {
        "schema_version": "standing_demo_operator_authorization_v1",
        "generated_at_utc": OLD_GEN.isoformat(),
        "status": "STANDING_DEMO_AUTHORIZATION_ACTIVE",
        "standing_authorization_id": "standing-demo-current-candidate-old",
        "operator_id": "profit-first-fast-demo-loop",
        "environment": "demo",
        "scope": "demo_api_only_bounded_probe",
        "demo_only": True,
        "candidate_scoping_required": True,
        "candidate": _candidate(),
        "max_authorized_probe_orders_per_candidate": 2,
        "expires_at_utc": "2026-06-30T05:49:47.325473+00:00",
        "risk_cap_lineage": {
            "risk_source_of_truth": "GUI-backed Rust RiskConfig",
            "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
            "account_equity_usdt": 9545.2067901,
            "per_trade_risk_pct_fraction": 0.1,
            "per_trade_risk_pct_display": 10.0,
            "position_size_max_pct": 25.0,
            "single_position_budget_usdt": 2386.30169752,
            "resolved_cap_usdt": 954.52067901,
            "rounded_notional_usdt": 946.3396,
            "local_10_usdt_cap_is_global_risk_authority": False,
            "bounded_probe_local_cap_usdt_is_authority": False,
        },
        "source_refs": {
            "current_envelope_path": "/tmp/openclaw/current_candidate_no_order_refresh_envelope_eth.json",
        },
        "answers": _answers(),
    }
    payload.update(overrides)
    return payload


def _runtime_readiness(candidate: dict | None = None, **overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_runtime_readiness_v1",
        "generated_at_utc": GEN.isoformat(),
        "status": "BOUNDED_DEMO_RUNTIME_READY_FOR_FINAL_WINDOW_GATES",
        "candidate": candidate or _candidate(),
        "answers": _answers(),
    }
    payload.update(overrides)
    return payload


def _equity_artifact(
    *,
    equity: float = 9544.0,
    generated_at: dt.datetime = GEN,
    **overrides,
) -> dict:
    payload = {
        "schema_version": "demo_account_equity_artifact_v1",
        "status": "DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY",
        "generated_at_utc": generated_at.isoformat(),
        "environment": "demo",
        "source_endpoint": "/api/v1/strategy/demo/balance?fast=1",
        "payload": {
            "action_result": "success",
            "data": {
                "source": "rust_engine",
                "read_model": "rust_snapshot_fast",
                "pipeline_status": "connected",
                "totalEquity": equity,
                "total_equity": equity,
                "equity": equity,
                "balance": equity,
            },
            "is_simulated": True,
            "data_category": "paper_simulated",
        },
        "answers": _answers(),
    }
    payload.update(overrides)
    return payload


def _gui_risk_config(**limits_overrides) -> dict:
    limits = {
        "per_trade_risk_pct": 0.1,
        "position_size_max_pct": 25.0,
        "total_exposure_max_pct": 150.0,
        "correlated_exposure_max_pct": 65.0,
        "max_order_notional_usdt": 0.0,
    }
    limits.update(limits_overrides)
    return {"limits": limits}


def _review(**overrides) -> dict:
    kwargs = {
        "existing_authorization": _existing_authorization(),
        "runtime_readiness": _runtime_readiness(),
        "account_equity_artifact": _equity_artifact(),
        "gui_risk_config": _gui_risk_config(),
        "now_utc": NOW,
    }
    kwargs.update(overrides)
    return mod.build_standing_demo_authorization_refresh_guardrail(**kwargs)


def test_ready_refresh_builds_valid_preview_without_runtime_mutation() -> None:
    review = _review()

    assert review["schema_version"] == mod.SCHEMA_VERSION
    assert review["status"] == mod.READY_STATUS
    assert review["summary"]["old_authorization_expired"] is True
    assert review["summary"]["refreshed_resolved_cap_usdt"] == 954.4
    assert review["summary"]["cap_not_increased_from_prior_standing"] is True
    assert review["answers"]["runtime_mutation_performed"] is False
    assert review["answers"]["standing_envelope_materialized"] is False
    assert review["answers"]["bounded_demo_probe_authorized"] is False
    envelope = review["envelope_preview"]
    assert envelope["schema_version"] == "standing_demo_operator_authorization_v1"
    assert envelope["candidate"]["side_cell_key"] == SIDE_CELL
    assert envelope["risk_cap_lineage"]["resolved_cap_usdt"] == 954.4
    assert envelope["risk_cap_lineage"]["order_shape_must_be_rebuilt_after_refresh"] is True
    assert review["standing_demo_authorization_validation"][
        "valid_for_candidate_scoped_authorization"
    ] is True


def test_current_gui_cap_cannot_increase_prior_standing_cap() -> None:
    review = _review(account_equity_artifact=_equity_artifact(equity=20_000.0))

    assert review["status"] == mod.READY_STATUS
    assert review["current_gui_cap_resolution"]["current_gui_resolved_cap_usdt"] == 2000.0
    assert review["risk_cap_lineage"]["prior_standing_resolved_cap_usdt"] == 954.52067901
    assert review["risk_cap_lineage"]["resolved_cap_usdt"] == 954.52067901


def test_candidate_mismatch_blocks_refresh() -> None:
    review = _review(
        runtime_readiness=_runtime_readiness(
            _candidate(side_cell_key="grid_trading|AVAXUSDT|Sell", symbol="AVAXUSDT", side="Sell")
        )
    )

    assert review["status"] == mod.NOT_READY_STATUS
    assert "runtime_readiness_candidate_mismatch" in review["source_blockers"]
    assert review["envelope_preview"] == {}


def test_authority_contamination_blocks_refresh() -> None:
    review = _review(
        existing_authorization=_existing_authorization(
            answers=_answers(order_submission_performed=True)
        )
    )

    assert review["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert any(
        reason.endswith("answers.order_submission_performed_true")
        for reason in review["authority_contamination_reasons"]
    )
    assert review["envelope_preview"] == {}


def test_stale_equity_blocks_refresh() -> None:
    review = _review(
        account_equity_artifact=_equity_artifact(
            generated_at=NOW - dt.timedelta(minutes=20)
        )
    )

    assert review["status"] == mod.NOT_READY_STATUS
    assert "account_equity_artifact_stale" in review["source_blockers"]
    assert review["envelope_preview"] == {}


def test_probe_order_expansion_blocks_refresh() -> None:
    review = _review(max_authorized_probe_orders=3)

    assert review["status"] == mod.NOT_READY_STATUS
    assert "max_authorized_probe_orders_increases_prior_envelope" in review["source_blockers"]
    assert review["envelope_preview"] == {}
