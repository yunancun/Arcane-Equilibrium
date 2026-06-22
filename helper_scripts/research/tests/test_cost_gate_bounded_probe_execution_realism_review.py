from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane.bounded_probe_execution_realism_review import (
    BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_SCHEMA_VERSION,
    build_bounded_probe_execution_realism_review,
    render_markdown,
)
from cost_gate_learning_lane.bounded_probe_result_review import (
    build_bounded_demo_probe_result_review,
)
from cost_gate_learning_lane.contract import (
    BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
    PROBE_OUTCOME_RECORD_TYPE,
)


NOW = dt.datetime(2026, 6, 22, 14, 0, tzinfo=dt.timezone.utc)
SIDE_CELL = "ma_crossover|BTCUSDT|Sell"


def _preflight() -> dict:
    return {
        "schema_version": "sealed_horizon_bounded_demo_probe_preflight_v1",
        "generated_at_utc": "2026-06-22T13:55:00+00:00",
        "status": "OPERATOR_REVIEW_REQUIRED",
        "side_cell_key": SIDE_CELL,
        "outcome_horizon_minutes": 240,
        "answers": {
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "bounded_demo_probe_design": {
            "schema_version": "bounded_demo_probe_design_v1",
            "status": "OPERATOR_REVIEW_READY_FOR_BOUNDED_DEMO_PROBE_DESIGN",
            "candidate": {
                "side_cell_key": SIDE_CELL,
                "strategy_name": "ma_crossover",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "outcome_horizon_minutes": 240,
            },
            "suggested_initial_probe_limits": {
                "max_filled_probe_outcomes_before_review": 3,
            },
            "success_criteria": {
                "min_filled_probe_outcomes_for_first_review": 3,
                "min_filled_probe_outcomes_for_learning_review": 10,
                "min_realized_avg_net_bps": 0.0,
                "min_realized_net_positive_pct": 60.0,
                "promotion_evidence": False,
            },
            "authority_boundary": {
                "global_cost_gate_lowering_recommended": False,
                "main_cost_gate_adjustment": "NONE",
                "probe_authority_granted": False,
                "order_authority_granted": False,
                "promotion_evidence": False,
            },
        },
    }


def _outcome(
    record_type: str,
    i: int,
    *,
    net_bps: float,
    gross_bps: float,
    cost_bps: float,
    fill_backed: bool = False,
    entry_delay_ms: int = 0,
) -> dict:
    prefix = "probe" if record_type == PROBE_OUTCOME_RECORD_TYPE else "control"
    source = "demo_fill_execution" if fill_backed else "market_markout_proxy"
    row = {
        "record_type": record_type,
        "generated_at_utc": f"2026-06-22T13:{i:02d}:00+00:00",
        "attempt_id": f"{prefix}-{i}",
        "side_cell_key": SIDE_CELL,
        "strategy_name": "ma_crossover",
        "symbol": "BTCUSDT",
        "side": "Sell",
        "event_ts_ms": i * 1_000_000,
        "entry_ts_ms": i * 1_000_000 + entry_delay_ms,
        "exit_ts_ms": i * 1_000_000 + 240 * 60_000,
        "horizon_minutes": 240,
        "gross_bps": gross_bps,
        "cost_bps": cost_bps,
        "realized_net_bps": net_bps,
        "outcome_source": source,
        "promotion_evidence": False,
    }
    if fill_backed:
        row["fill_id"] = f"fill-{prefix}-{i}"
    return row


def _result_review(ledger_rows: list[dict]) -> dict:
    return build_bounded_demo_probe_result_review(
        preflight=_preflight(),
        ledger_rows=ledger_rows,
        now_utc=NOW,
    )


def test_under_capture_proxy_rows_require_fill_backed_execution_review() -> None:
    ledger_rows = [
        _outcome(PROBE_OUTCOME_RECORD_TYPE, 1, net_bps=1.0, gross_bps=5.0, cost_bps=4.0),
        _outcome(PROBE_OUTCOME_RECORD_TYPE, 2, net_bps=2.0, gross_bps=6.0, cost_bps=4.0),
        _outcome(PROBE_OUTCOME_RECORD_TYPE, 3, net_bps=3.0, gross_bps=7.0, cost_bps=4.0),
        _outcome(BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE, 1, net_bps=3.0, gross_bps=7.0, cost_bps=4.0),
        _outcome(BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE, 2, net_bps=3.0, gross_bps=7.0, cost_bps=4.0),
        _outcome(BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE, 3, net_bps=3.0, gross_bps=7.0, cost_bps=4.0),
    ]
    result_review = _result_review(ledger_rows)

    packet = build_bounded_probe_execution_realism_review(
        result_review=result_review,
        ledger_rows=ledger_rows,
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == (
        BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_SCHEMA_VERSION
    )
    assert result_review["evidence_quality"]["status"] == (
        "PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP"
    )
    assert packet["status"] == "EXECUTION_REALISM_GAP_DIAGNOSED_REPAIR_REQUIRED"
    assert packet["gap_decomposition"]["net_capture_gap_bps"] == 1.0
    assert packet["gap_decomposition"]["gross_capture_gap_bps"] == 1.0
    assert packet["gap_decomposition"]["cost_or_slippage_gap_bps"] == 0.0
    assert packet["probe_execution_summary"]["fill_backed_pct"] == 0.0
    assert packet["execution_gap_hypotheses"][0]["kind"] == (
        "fill_backed_execution_missing"
    )
    assert {
        row["kind"] for row in packet["execution_gap_hypotheses"]
    } >= {
        "fill_backed_execution_missing",
        "horizon_or_signal_timing_gross_edge_gap",
        "matched_control_fill_backed_execution_missing",
    }
    assert packet["next_actions"][0] == (
        "record_fill_backed_probe_execution_rows_or_l1_replay_before_cost_gate_review"
    )
    assert packet["answers"]["cost_gate_or_operator_review_allowed"] is False
    assert "Probe fill-backed pct" in markdown


def test_under_capture_fill_backed_rows_can_identify_cost_slippage_gap() -> None:
    ledger_rows = [
        _outcome(
            PROBE_OUTCOME_RECORD_TYPE,
            i,
            net_bps=2.0,
            gross_bps=6.0,
            cost_bps=4.0,
            fill_backed=True,
        )
        for i in range(1, 4)
    ] + [
        _outcome(
            BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
            i,
            net_bps=4.0,
            gross_bps=6.0,
            cost_bps=2.0,
            fill_backed=True,
        )
        for i in range(1, 4)
    ]
    result_review = _result_review(ledger_rows)

    packet = build_bounded_probe_execution_realism_review(
        result_review=result_review,
        ledger_rows=ledger_rows,
        now_utc=NOW,
    )

    assert packet["status"] == "EXECUTION_REALISM_GAP_DIAGNOSED_REPAIR_REQUIRED"
    assert packet["gap_decomposition"]["net_capture_gap_bps"] == 2.0
    assert packet["gap_decomposition"]["gross_capture_gap_bps"] == 0.0
    assert packet["gap_decomposition"]["cost_or_slippage_gap_bps"] == 2.0
    assert packet["probe_execution_summary"]["fill_backed_pct"] == 100.0
    assert packet["execution_gap_hypotheses"][0]["kind"] == (
        "fee_slippage_or_fill_cost_gap"
    )
    assert packet["next_actions"][0] == (
        "inspect_probe_fee_slippage_and_fill_quality_against_controls"
    )


def test_no_under_capture_result_review_is_noop() -> None:
    ledger_rows = [
        _outcome(PROBE_OUTCOME_RECORD_TYPE, 1, net_bps=3.0, gross_bps=7.0, cost_bps=4.0),
        _outcome(PROBE_OUTCOME_RECORD_TYPE, 2, net_bps=4.0, gross_bps=8.0, cost_bps=4.0),
        _outcome(PROBE_OUTCOME_RECORD_TYPE, 3, net_bps=5.0, gross_bps=9.0, cost_bps=4.0),
        _outcome(BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE, 1, net_bps=1.0, gross_bps=5.0, cost_bps=4.0),
        _outcome(BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE, 2, net_bps=1.0, gross_bps=5.0, cost_bps=4.0),
        _outcome(BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE, 3, net_bps=1.0, gross_bps=5.0, cost_bps=4.0),
    ]
    result_review = _result_review(ledger_rows)

    packet = build_bounded_probe_execution_realism_review(
        result_review=result_review,
        ledger_rows=ledger_rows,
        now_utc=NOW,
    )

    assert result_review["evidence_quality"]["status"] == (
        "FIRST_REVIEW_WITH_MATCHED_CONTROL_COMPARISON"
    )
    assert packet["status"] == "NO_EXECUTION_REALISM_GAP_TO_REVIEW"
    assert packet["execution_gap_hypotheses"] == []
    assert packet["next_actions"] == ["continue_standard_bounded_probe_result_review_path"]
