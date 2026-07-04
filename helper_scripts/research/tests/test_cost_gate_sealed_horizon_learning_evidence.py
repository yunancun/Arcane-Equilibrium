"""Tests for sealed horizon cost-gate learning evidence packets."""

from __future__ import annotations

import datetime as dt

import pytest

from cost_gate_learning_lane.runtime_adapter import read_jsonl_ledger
from cost_gate_learning_lane.sealed_horizon_learning_evidence import (
    SEALED_HORIZON_LEARNING_EVIDENCE_SCHEMA_VERSION,
    SealedHorizonLearningEvidenceConfig,
    build_sealed_horizon_learning_evidence_from_rows,
    build_sealed_horizon_reject_feature_sql,
    find_sealed_horizon_candidate,
    select_default_sealed_horizon_candidate,
)


def _sealed_plan() -> dict:
    return {
        "schema_version": "cost_gate_demo_learning_lane_plan_v1",
        "generated_at_utc": "2026-06-22T04:00:00+00:00",
        "status": "READY_FOR_DEMO_LEARNING_PROBE",
        "gate_status": "OPERATOR_REVIEW",
        "main_cost_gate_adjustment": "NONE",
        "learning_gate_adjustment": "SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING",
        "order_authority": "NOT_GRANTED",
        "selected_probe_candidate_count": 1,
        "probe_candidates": [
            {
                "side_cell_key": "ma_crossover|BTCUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "reject_reason_code": "cost_gate_js_demo_negative_edge",
                "source_kind": "horizon_specific_sealed_replay",
                "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
                "learning_lane_reason": (
                    "sealed_horizon_replay_revalidated_retiming_candidate"
                ),
                "outcome_horizon_minutes": 240,
                "learning_outcome_horizon_minutes": 240,
                "sealed_horizon_replay": {
                    "schema_version": "horizon_specific_sealed_replay_packet_v1",
                    "status": "SEALED_HORIZON_REPLAY_READY_FOR_OPERATOR_REVIEW",
                    "side_cell_key": "ma_crossover|BTCUSDT|Sell",
                    "best_horizon_minutes": 240,
                    "best_avg_net_bps": 31.8707,
                    "best_net_positive_pct": 81.94,
                    "failed_gate_names": [],
                },
                "horizon_stability": {
                    "status": "MIXED_HORIZON_RESPONSE",
                    "best_horizon_minutes": 240,
                    "primary_horizon_minutes": 60,
                },
                "probe_proposal": {
                    "mode": "demo_only_learning_probe",
                    "max_probe_orders": 2,
                    "cooldown_minutes": 30,
                    "requires_runtime_policy_adapter": True,
                    "requires_probe_attempt_logging": True,
                    "requires_probe_outcome_logging": True,
                    "requires_candidate_horizon_outcome_logging": True,
                    "outcome_horizon_minutes": 240,
                    "learning_outcome_horizon_minutes": 240,
                },
                "guardrails": {
                    "main_cost_gate_adjustment": "NONE",
                    "may_bypass_main_live_gate": False,
                    "demo_only": True,
                    "notional_or_qty_not_granted_by_artifact": True,
                    "paper_not_promotion_evidence": True,
                },
            }
        ],
    }


def test_sealed_horizon_reject_sql_filters_exact_mature_side_cell() -> None:
    plan = _sealed_plan()
    candidate = find_sealed_horizon_candidate(plan, "ma_crossover|BTCUSDT|Sell")
    cfg = SealedHorizonLearningEvidenceConfig(
        engine_modes=("demo",),
        lookback_hours=12,
        limit=123,
        maturity_buffer_minutes=5,
    )

    sql, params = build_sealed_horizon_reject_feature_sql(candidate, cfg)

    assert "f.ts <= now() - (%s::int * interval '1 minute')" in sql
    assert params == [
        ["demo"],
        12,
        245,
        "cost_gate_js_demo_negative_edge",
        "ma_crossover",
        "BTCUSDT",
        -1,
        123,
    ]


def test_default_sealed_horizon_candidate_selects_plan_replay_candidate() -> None:
    plan = _sealed_plan()
    plan["probe_candidates"].insert(
        0,
        {
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "source_kind": "legacy_scorecard_candidate",
        },
    )

    candidate = select_default_sealed_horizon_candidate(plan)

    assert candidate["side_cell_key"] == "ma_crossover|BTCUSDT|Sell"
    assert candidate["source_kind"] == "horizon_specific_sealed_replay"
    assert candidate["outcome_horizon_minutes"] == 240


def test_sealed_horizon_learning_evidence_records_240m_blocked_outcome(tmp_path) -> None:
    plan = _sealed_plan()
    event_ts = int(
        dt.datetime(2026, 6, 22, 0, 0, tzinfo=dt.timezone.utc).timestamp() * 1000
    )
    exit_ts = event_ts + 240 * 60_000
    feature_rows = [
        {
            "ts": "2026-06-22T00:00:00+00:00",
            "ts_ms": event_ts,
            "context_id": "ctx-demo-BTCUSDT-1",
            "engine_mode": "demo",
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "reject_reason_code": "cost_gate_js_demo_negative_edge",
            "last_price": 100.0,
        }
    ]
    price_rows = [
        {
            "symbol": "BTCUSDT",
            "ts_ms": exit_ts,
            "close": 99.0,
            "timeframe": "1m",
        }
    ]
    ledger = tmp_path / "sealed_ledger.jsonl"
    cfg = SealedHorizonLearningEvidenceConfig(
        min_review_outcomes_per_side_cell=1,
        min_review_net_positive_pct=1.0,
    )

    packet, materialized, outcome_batch, review = (
        build_sealed_horizon_learning_evidence_from_rows(
            plan=plan,
            side_cell_key="ma_crossover|BTCUSDT|Sell",
            feature_rows=feature_rows,
            price_rows=price_rows,
            ledger_path=ledger,
            cfg=cfg,
            append_ledger=True,
            now_utc=dt.datetime(2026, 6, 22, 5, tzinfo=dt.timezone.utc),
        )
    )

    assert packet["schema_version"] == SEALED_HORIZON_LEARNING_EVIDENCE_SCHEMA_VERSION
    assert packet["status"] == "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
    assert packet["answers"] == {
        "sealed_candidate_materialized": True,
        "blocked_signal_outcomes_recorded": True,
        "candidate_clears_operator_review_gate": True,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
    }
    assert materialized["decision_counts"] == {"ORDER_AUTHORITY_NOT_GRANTED": 1}
    assert outcome_batch["blocked_signal_outcome_count"] == 1
    outcome = outcome_batch["blocked_signal_outcomes"][0]
    assert outcome["horizon_minutes"] == 240
    assert outcome["default_horizon_minutes"] == 60
    assert outcome["gross_bps"] == pytest.approx(100.0)
    # P1-2a:舊 4.0 常數的淨值移到 net_bps_optimistic;realized_net_bps 為保守權威淨值
    # (無分位 artifact → toml_tier 30bps fallback → cost≈92.3 → net≈7.7)。
    assert outcome["net_bps_optimistic"] == pytest.approx(96.0)
    assert review["top_side_cell_key"] == "ma_crossover|BTCUSDT|Sell"
    assert len(read_jsonl_ledger(ledger)) == 2


def test_non_sealed_candidate_is_rejected() -> None:
    plan = _sealed_plan()
    plan["probe_candidates"][0]["source_kind"] = None

    with pytest.raises(ValueError, match="not a sealed horizon replay candidate"):
        find_sealed_horizon_candidate(plan, "ma_crossover|BTCUSDT|Sell")


def test_default_sealed_horizon_candidate_requires_sealed_replay() -> None:
    plan = _sealed_plan()
    plan["probe_candidates"][0]["source_kind"] = None

    with pytest.raises(ValueError, match="sealed horizon candidate not found"):
        select_default_sealed_horizon_candidate(plan)
