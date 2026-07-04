"""F14(E4 2026-07-04 補審):probe_outcome fill 對賬誠實性標記測試。

probe_outcome 是 admission 時價的 markout proxy,admitted-but-unfilled 與真
filled 原本同權計入。本檔釘住修復後語義:writer 對每筆 probe outcome 附
`fill_reconciliation` 標記(filled / admitted_only / indeterminate,依 outcome
生成當下 ledger 內可見的 fill 執行證據判定),消費側(result review)分開計數。
標記是數據誠實性欄位,不改變 promotion/review 判準本身(QC P1-2 範圍)。
"""

from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane.bounded_probe_result_review import (
    build_bounded_demo_probe_result_review,
    render_markdown,
)
from cost_gate_learning_lane.contract import (
    ADMIT_DECISION,
    PROBE_ADMISSION_DECISION_RECORD_TYPE,
    PROBE_OUTCOME_RECORD_TYPE,
)
from cost_gate_learning_lane.outcome_writer import (
    ProbeOutcomeConfig,
    build_blocked_signal_outcome_records,
    build_probe_outcome_records,
)


UTC = dt.timezone.utc
EVENT_TS_MS = int(dt.datetime(2026, 6, 21, 11, 0, tzinfo=UTC).timestamp() * 1000)
EXIT_TS_MS = EVENT_TS_MS + 3_600_000
NOW = dt.datetime(2026, 6, 21, 12, 11, tzinfo=UTC)
SIDE_CELL = "ma_crossover|ETHUSDT|Sell"


def _admission(*, event_overrides: dict | None = None, drop_lineage: bool = False) -> dict:
    event = {
        "strategy_name": "ma_crossover",
        "symbol": "ETHUSDT",
        "side": "Sell",
        "ts_ms": EVENT_TS_MS,
        "context_id": "ctx-1",
        "signal_id": "sig-1",
    }
    if drop_lineage:
        event.pop("context_id")
        event.pop("signal_id")
    event.update(event_overrides or {})
    return {
        "record_type": PROBE_ADMISSION_DECISION_RECORD_TYPE,
        "decision": ADMIT_DECISION,
        "allowed_to_submit_order": True,
        "side_cell_key": SIDE_CELL,
        "event": event,
    }


def _observations() -> list[dict]:
    return [
        {"symbol": "ETHUSDT", "ts_ms": EVENT_TS_MS, "close": 2000.0},
        {"symbol": "ETHUSDT", "ts_ms": EXIT_TS_MS, "close": 1980.0},
    ]


def _build(ledger_rows: list[dict]) -> list[dict]:
    return build_probe_outcome_records(
        ledger_rows,
        _observations(),
        now_utc=NOW,
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )


def test_admitted_probe_without_fill_evidence_is_marked_admitted_only() -> None:
    outcomes = _build([_admission()])

    assert len(outcomes) == 1
    assert outcomes[0]["fill_reconciliation"] == "admitted_only"


def test_admitted_probe_with_matching_fill_evidence_is_marked_filled() -> None:
    fill_row = {
        "record_type": "bounded_probe_attempt",
        "context_id": "ctx-1",
        "fill_id": "fill-1",
    }
    outcomes = _build([_admission(), fill_row])

    assert len(outcomes) == 1
    assert outcomes[0]["fill_reconciliation"] == "filled"


def test_fill_evidence_matched_via_lineage_order_link_id() -> None:
    admission = _admission(event_overrides={"order_link_id": "oc_dm_1_1_000000001"})
    fill_row = {
        "record_type": "bounded_probe_attempt",
        "lineage": {
            "order_link_id": "oc_dm_1_1_000000001",
            "fill_id": "fill-9",
        },
    }
    outcomes = _build([admission, fill_row])

    assert len(outcomes) == 1
    assert outcomes[0]["fill_reconciliation"] == "filled"


def test_order_only_evidence_does_not_count_as_filled() -> None:
    # 為什麼:order_id 只證明曾下單,不證明成交;無 fill/exec id 不得標 filled。
    order_only_row = {
        "record_type": "bounded_probe_attempt",
        "context_id": "ctx-1",
        "order_id": "bybit-order-1",
    }
    outcomes = _build([_admission(), order_only_row])

    assert len(outcomes) == 1
    assert outcomes[0]["fill_reconciliation"] == "admitted_only"


def test_admission_without_lineage_ids_is_marked_indeterminate() -> None:
    # 無 context_id/signal_id/order_link_id 可綁定執行 lineage → 無法對賬,誠實標 indeterminate。
    outcomes = _build([_admission(drop_lineage=True)])

    assert len(outcomes) == 1
    assert outcomes[0]["fill_reconciliation"] == "indeterminate"


def test_blocked_signal_outcomes_do_not_carry_fill_reconciliation() -> None:
    # blocked-signal 是 counterfactual(從未下單),fill 對賬語義不適用。
    blocked = {
        "record_type": PROBE_ADMISSION_DECISION_RECORD_TYPE,
        "decision": "ORDER_AUTHORITY_NOT_GRANTED",
        "allowed_to_submit_order": False,
        "side_cell_key": SIDE_CELL,
        "event": {
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "ts_ms": EVENT_TS_MS,
            "context_id": "ctx-blocked",
            "signal_id": "sig-blocked",
        },
    }
    outcomes = build_blocked_signal_outcome_records(
        [blocked],
        _observations(),
        now_utc=NOW,
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )

    assert len(outcomes) == 1
    assert "fill_reconciliation" not in outcomes[0]


REVIEW_SIDE_CELL = "ma_crossover|BTCUSDT|Sell"


def _review_preflight() -> dict:
    return {
        "side_cell_key": REVIEW_SIDE_CELL,
        "outcome_horizon_minutes": 240,
        "answers": {},
        "bounded_demo_probe_design": {
            "status": "OPERATOR_REVIEW_READY_FOR_BOUNDED_DEMO_PROBE_DESIGN",
            "candidate": {
                "side_cell_key": REVIEW_SIDE_CELL,
                "strategy_name": "ma_crossover",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "outcome_horizon_minutes": 240,
            },
        },
    }


def _review_outcome(i: int, net_bps: float, **overrides) -> dict:
    row = {
        "record_type": PROBE_OUTCOME_RECORD_TYPE,
        "generated_at_utc": f"2026-06-22T12:{i:02d}:00+00:00",
        "attempt_id": f"attempt-{i}",
        "side_cell_key": REVIEW_SIDE_CELL,
        "realized_net_bps": net_bps,
        "gross_bps": net_bps + 4.0,
    }
    row.update(overrides)
    return row


def test_result_review_splits_fill_reconciliation_counts() -> None:
    packet = build_bounded_demo_probe_result_review(
        preflight=_review_preflight(),
        ledger_rows=[
            _review_outcome(1, 2.0, fill_reconciliation="filled"),
            _review_outcome(2, 4.0, fill_reconciliation="admitted_only"),
            _review_outcome(3, 1.0, fill_reconciliation="admitted_only"),
            _review_outcome(4, 3.0, fill_reconciliation="indeterminate"),
            _review_outcome(5, 2.5),  # legacy 行無標記 → unmarked,不與 indeterminate 混同
        ],
        now_utc=dt.datetime(2026, 6, 22, 13, 0, tzinfo=UTC),
    )
    markdown = render_markdown(packet)

    summary = packet["probe_result_summary"]
    assert summary["fill_reconciliation_counts"] == {
        "admitted_only": 2,
        "filled": 1,
        "indeterminate": 1,
        "unmarked": 1,
    }
    # 判準不變性:標記只分開計數,completed 計數與 review 判定不因標記而改變。
    assert summary["completed_probe_outcome_count"] == 5
    assert packet["status"] == "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED"
    assert "Fill reconciliation" in markdown


def test_result_review_counts_are_empty_dict_without_outcomes() -> None:
    packet = build_bounded_demo_probe_result_review(
        preflight=_review_preflight(),
        ledger_rows=[],
        now_utc=dt.datetime(2026, 6, 22, 13, 0, tzinfo=UTC),
    )

    assert packet["probe_result_summary"]["fill_reconciliation_counts"] == {}
