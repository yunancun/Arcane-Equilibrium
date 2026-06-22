from __future__ import annotations

import pytest

from helper_scripts.db.audit.demo_data_flow_monitor import (
    build_monitor_payload,
    parse_windows,
    render_markdown,
    summarize_windows,
)


def _window(
    hours: int,
    *,
    status: str = "NO_RECENT_PIPELINE_DATA",
    data_status: str = "NOT_ACCUMULATING_RECENT_DATA",
    decisions: int = 0,
    risk: int = 0,
    rejected_risk: int = 0,
    intents: int = 0,
    orders: int = 0,
    fills: int = 0,
    cost_gate_rejects: int = 0,
    stale: bool = False,
) -> dict:
    risk_rows = []
    if cost_gate_rejects:
        risk_rows.append(
            {
                "reason": "cost_gate(JS-demo): estimated=-6.01bps < 0",
                "n": cost_gate_rejects,
                "rejected_n": cost_gate_rejects,
                "approved_n": 0,
            }
        )
    return {
        "lookback_hours": hours,
        "classification": {
            "status": status,
            "data_accumulation_status": data_status,
            "primary_blocker_stage": "risk_to_intents",
            "dominant_risk_category": {
                "category": "cost_gate" if cost_gate_rejects else None,
                "pct": 99.0 if cost_gate_rejects else None,
            },
            "data_flow_freshness": {
                "status": (
                    "LEARNING_DATA_FLOW_STALE"
                    if stale
                    else "LEARNING_DATA_FLOW_FRESH"
                ),
                "latest_learning_stage": "risk_verdicts" if risk else None,
                "latest_learning_ts_utc": "2026-06-22T00:00:00+00:00"
                if risk
                else None,
                "latest_learning_age_seconds": 7200 if stale else 30,
            },
            "answers": {"learning_data_flow_stale": stale},
        },
        "counts": {
            "decision_context_snapshots": 0,
            "candidate_evaluations": 0,
            "decision_features": decisions,
            "rejected_decision_features": decisions,
            "risk_verdicts": risk,
            "approved_risk_verdicts": 0,
            "rejected_risk_verdicts": rejected_risk,
            "intents": intents,
            "orders": orders,
            "fills": fills,
        },
        "risk_reason_top": risk_rows,
    }


def test_recent_empty_window_with_prior_orders_no_fills_is_explicit() -> None:
    summary = summarize_windows(
        [
            _window(1),
            _window(
                4,
                status="ORDER_TO_FILL_GAP",
                data_status="REJECT_OR_CANDIDATE_DATA_ACCUMULATING",
                decisions=2699,
                risk=2699,
                rejected_risk=2696,
                intents=3,
                orders=3,
                cost_gate_rejects=2696,
            ),
        ]
    )

    assert summary["status"] == "RECENT_WINDOW_EMPTY_PRIOR_ORDER_FLOW_NO_FILLS"
    assert summary["answers"]["short_window_empty"] is True
    assert summary["answers"]["cost_gate_rejects_recorded"] is True
    assert summary["answers"]["orders_present"] is True
    assert summary["answers"]["fills_present"] is False
    assert summary["answers"]["global_cost_gate_lowering_recommended"] is False
    assert summary["key_counts"]["broad_orders"] == 3
    assert summary["key_counts"]["broad_cost_gate_rejects"] == 2696


def test_recent_empty_window_with_cost_gate_reject_wall_no_orders() -> None:
    summary = summarize_windows(
        [
            _window(1),
            _window(
                24,
                status="COST_GATE_REJECTING_ALL_RECENT_ATTEMPTS",
                data_status="REJECT_OR_CANDIDATE_DATA_ACCUMULATING",
                decisions=10_000,
                risk=10_000,
                rejected_risk=10_000,
                cost_gate_rejects=10_000,
            ),
        ]
    )

    assert summary["status"] == "RECENT_WINDOW_EMPTY_COST_GATE_REJECT_WALL"
    assert summary["next_action"] == (
        "restore_fresh_demo_flow_then_continue_cost_gate_learning_lane"
    )


def test_no_data_any_window_and_fill_present_branches() -> None:
    empty = summarize_windows([_window(1), _window(4)])
    assert empty["status"] == "NO_DEMO_DATA_ANY_WINDOW"

    filled = summarize_windows(
        [
            _window(
                1,
                status="RECENT_FILL_FLOW_PRESENT",
                orders=2,
                fills=1,
            ),
            _window(
                24,
                status="RECENT_FILL_FLOW_PRESENT",
                orders=10,
                fills=4,
            ),
        ]
    )
    assert filled["status"] == "DEMO_FILL_FLOW_PRESENT"
    assert filled["answers"]["fills_present"] is True


def test_build_payload_and_markdown_surface_compact_windows() -> None:
    payload = build_monitor_payload(
        engine_modes=("demo", "live_demo"),
        windows=[
            _window(1),
            _window(
                4,
                status="ORDER_TO_FILL_GAP",
                data_status="REJECT_OR_CANDIDATE_DATA_ACCUMULATING",
                decisions=2699,
                risk=2699,
                rejected_risk=2696,
                intents=3,
                orders=3,
                cost_gate_rejects=2696,
            ),
        ],
        generated="2026-06-22T01:00:00+00:00",
    )
    markdown = render_markdown(payload)

    assert payload["schema_version"] == "demo_data_flow_monitor_v1"
    assert payload["summary"]["status"] == (
        "RECENT_WINDOW_EMPTY_PRIOR_ORDER_FLOW_NO_FILLS"
    )
    assert payload["windows"][1]["counts"]["risk_verdicts"] == 2699
    assert "Demo Data Flow Monitor" in markdown
    assert "RECENT_WINDOW_EMPTY_PRIOR_ORDER_FLOW_NO_FILLS" in markdown
    assert "cost_gate(JS-demo)" in markdown


def test_parse_windows_dedupes_and_validates_bounds() -> None:
    assert parse_windows([24, 1, 4, 4]) == [1, 4, 24]

    with pytest.raises(ValueError):
        parse_windows([])
    with pytest.raises(ValueError):
        parse_windows([0])
    with pytest.raises(ValueError):
        parse_windows([721])
