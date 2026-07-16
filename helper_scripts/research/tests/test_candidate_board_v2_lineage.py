"""Candidate board v2 prospective-lineage 與審計分離攻擊測試。

MODULE_NOTE
模塊用途：驗證 blocked outcome 必須先通過 immutable raw/evaluation lineage，
才可進入 cohort 統計與 arbiter selection；legacy/invalid rows 僅能影響審計面。
主要接口：``build_blocked_signal_outcome_review``。
依賴：``candidate_lineage_v2_test_support`` 公開 fixture factory。
硬邊界：測試不得從目前 config/HEAD 回填 lineage，也不得把 audit volume 洗入 n_eff。
"""

from __future__ import annotations

import copy
import datetime as dt
import json

import pytest

from helper_scripts.research.tests.candidate_lineage_v2_test_support import (
    attach_candidate_lineage_v2,
)
from cost_gate_learning_lane import candidate_board as candidate_board_module
from cost_gate_learning_lane import outcome_review as outcome_review_module
from cost_gate_learning_lane import runtime_adapter as runtime_adapter_module
from cost_gate_learning_lane.outcome_review import (
    build_blocked_signal_outcome_review,
    build_research_compatibility_blocked_signal_outcome_review_no_authority,
    read_candidate_board_ledger_projection,
)
from cost_gate_learning_lane.candidate_board_validation import (
    validate_learning_candidate_board_v2,
)
from cost_gate_learning_lane.candidate_evaluation_context import canonical_sha256
from cost_gate_learning_lane.runtime_adapter import (
    read_candidate_evidence_jsonl_ledger,
    read_jsonl_ledger,
)


NOW = dt.datetime(2026, 7, 10, 18, tzinfo=dt.timezone.utc)


def _outcome(*, attempt_id: str, realized_net_bps: float = -1.0) -> dict[str, object]:
    return {
        "record_type": "blocked_signal_outcome",
        "attempt_id": attempt_id,
        "side_cell_key": "ma_crossover|BTCUSDT|Buy",
        "strategy_name": "ma_crossover",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "horizon_minutes": 60,
        "entry_ts_ms": int(
            dt.datetime(2026, 7, 9, 12, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
        "gross_bps": realized_net_bps + 12.0,
        "realized_net_bps": realized_net_bps,
        "net_bps_optimistic": realized_net_bps + 8.0,
        "cost_bps": 12.0,
        "cost_model_version": "conservative_v1",
    }


def _qualified(
    *, context_id: str = "ctx-board-v2-001", **kwargs: object
) -> dict[str, object]:
    outcome = _outcome(attempt_id=context_id)
    if "captured_at_ms" in kwargs:
        outcome["entry_ts_ms"] = kwargs["captured_at_ms"]
    return attach_candidate_lineage_v2(
        outcome,
        context_id=context_id,
        as_of_utc_date=NOW.date().isoformat(),
        **kwargs,
    )


def _ledger_source_row(row: dict[str, object]) -> dict[str, object]:
    source = copy.deepcopy(row)
    context = copy.deepcopy(
        source["candidate_summary"]["candidate_event_context"]
    )
    source["event"] = {
        "strategy_name": context["strategy_name"],
        "symbol": context["symbol"],
        "side": context["side"],
        "context_id": context["context_id"],
        "signal_id": context["signal_id"],
        "engine_mode": context["evidence_engine_mode"],
        "ts_ms": context["captured_at_ms"],
        "candidate_event_context": context,
    }
    return source


def _board(rows: list[dict[str, object]]) -> dict[str, object]:
    return build_blocked_signal_outcome_review(rows, now_utc=NOW)[
        "learning_candidate_board"
    ]


def _eligible_cohort_rows(
    context_prefix: str,
    *,
    stable_projection_overrides: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    rows = []
    day_effects = (-3.0, -2.0, -1.0, 1.0, 2.0, 3.0)
    for index in range(30):
        captured_at = dt.datetime(2026, 7, 3 + index // 5, index % 5,
                                  tzinfo=dt.timezone.utc)
        row = _qualified(
            context_id=f"{context_prefix}-{index:02d}",
            captured_at_ms=int(captured_at.timestamp() * 1_000),
            stable_projection_overrides=stable_projection_overrides,
        )
        net = 10.0 + day_effects[index // 5] + (index % 5) * 0.1
        row.update({"realized_net_bps": net, "gross_bps": net + 12.0})
        rows.append(row)
    return rows


def _expected_cost_artifact() -> dict[str, object]:
    return {
        "schema_version": "cost_gate_slippage_quantile_artifact_v2",
        "asof": NOW.isoformat(),
        "window_days": 90,
        "n_total_global": 500,
        "symbols": [{
            "symbol": "BTCUSDT",
            "n": 500,
            "mean_abs": 2.0,
            "mean_signed": 1.0,
            "q50": 1.0,
            "q75": 4.0,
            "q90": 8.0,
            "cvar90": 8.0,
            "thin_sample": False,
        }],
        "global": {
            "n": 500,
            "mean_abs": 2.0,
            "mean_signed": 1.0,
            "q50": 1.0,
            "q75": 4.0,
            "q90": 8.0,
            "cvar90": 8.0,
            "thin_sample": False,
        },
        "boundary": (
            "slippage quantile artifact only; PG source is read-only SELECT-only; "
            "no PG write, Bybit call, order, config, risk, auth, or runtime mutation"
        ),
    }


def _rehash_selection_and_board(board: dict[str, object]) -> None:
    semantic_rows = [
        {field: row[field] for field in candidate_board_module._SELECTION_FIELDS}
        for row in board["candidate_rows"]
    ]
    semantic_rows.sort(key=lambda row: (row["candidate_id"], canonical_sha256(row)))
    board["selection_hash"] = canonical_sha256({
        "schema_version": "cost_gate_learning_candidate_selection_v2",
        "candidate_rows": semantic_rows,
    })
    board["board_hash"] = canonical_sha256({
        key: value for key, value in board.items() if key != "board_hash"
    })


def test_legacy_rows_are_audit_only_and_cannot_change_qualified_selection() -> None:
    qualified = _qualified()
    baseline = _board([qualified])
    legacy = _outcome(attempt_id="legacy-no-prospective-lineage")

    attacked = _board([legacy, qualified])

    assert attacked["schema_version"] == "cost_gate_learning_candidate_board_v2"
    assert attacked["raw_blocked_outcome_row_count"] == 2
    assert attacked["qualified_lineage_outcome_row_count"] == 1
    assert attacked["unqualified_lineage_outcome_row_count"] == 1
    assert attacked["invalid_lineage_outcome_row_count"] == 0
    assert attacked["lineage_partition_complete"] is True
    assert attacked["candidate_rows"] == baseline["candidate_rows"]
    assert attacked["selection_hash"] == baseline["selection_hash"]
    assert attacked["audit_hash"] != baseline["audit_hash"]
    assert attacked["board_hash"] != baseline["board_hash"]


def test_evidence_reader_quarantines_intentional_capture_blocked_row(
    tmp_path,
) -> None:
    complete = _qualified(context_id="ctx-evidence-reader-complete")
    complete_context = copy.deepcopy(
        complete["candidate_summary"]["candidate_event_context"]
    )
    complete["candidate_summary"] = None
    complete["event"] = {
        "strategy_name": complete_context["strategy_name"],
        "symbol": complete_context["symbol"],
        "side": complete_context["side"],
        "context_id": complete_context["context_id"],
        "signal_id": complete_context["signal_id"],
        "engine_mode": complete_context["evidence_engine_mode"],
        "ts_ms": complete_context["captured_at_ms"],
        "candidate_event_context": complete_context,
    }
    blocked = _qualified(context_id="ctx-evidence-reader-capture-blocked")
    blocked_context = copy.deepcopy(
        blocked["candidate_summary"]["candidate_event_context"]
    )
    blocked_context["capture_status"] = "CAPTURE_BLOCKED"
    blocked_context["capture_blockers"] = ["BBO_MISSING_OR_INVALID"]
    blocked_body = {
        key: value
        for key, value in blocked_context.items()
        if key != "event_hash"
    }
    blocked_context["event_hash"] = canonical_sha256(blocked_body)
    blocked["candidate_summary"] = None
    blocked["event"] = {
        "strategy_name": blocked_context["strategy_name"],
        "symbol": blocked_context["symbol"],
        "side": blocked_context["side"],
        "context_id": blocked_context["context_id"],
        "signal_id": blocked_context["signal_id"],
        "engine_mode": blocked_context["evidence_engine_mode"],
        "ts_ms": blocked_context["captured_at_ms"],
        "candidate_event_context": blocked_context,
    }
    ledger = tmp_path / "candidate_evidence_mixed.jsonl"
    ledger.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True)
            for row in (complete, blocked)
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="EVENT_CONTEXT_CAPTURE_INCOMPLETE"):
        read_jsonl_ledger(ledger)

    evidence_rows = read_candidate_evidence_jsonl_ledger(ledger)
    assert evidence_rows[0]["candidate_summary"][
        "candidate_event_context_status"
    ] == "VALID"
    assert evidence_rows[0]["candidate_summary"][
        "candidate_event_context"
    ] == evidence_rows[0]["event"]["candidate_event_context"]
    assert evidence_rows[0]["candidate_summary"][
        "candidate_event_context"
    ] is not evidence_rows[0]["event"]["candidate_event_context"]
    assert evidence_rows[1]["candidate_summary"][
        "candidate_event_context_status"
    ] == "CAPTURE_BLOCKED"
    review = build_blocked_signal_outcome_review(
        evidence_rows,
        now_utc=NOW,
    )
    board = review["learning_candidate_board"]

    assert review["schema_version"] == (
        "cost_gate_demo_learning_lane_blocked_outcome_review_v6"
    )
    assert board["schema_version"] == "cost_gate_learning_candidate_board_v2"
    assert board["qualified_lineage_outcome_row_count"] == 0
    assert board["unqualified_lineage_outcome_row_count"] == 1
    assert board["unqualified_raw_valid_evaluation_missing_row_count"] == 1
    assert board["invalid_lineage_outcome_row_count"] == 1
    assert board["unassigned_invalid_lineage_outcome_row_count"] == 1
    assert board["lineage_exclusion_reason_counts"] == {
        "INVALID_LINEAGE_RAW_CONTEXT_INVALID": 1,
        "UNQUALIFIED_RAW_VALID_EVALUATION_MISSING": 1,
    }
    assert board["candidate_rows"] == []
    assert validate_learning_candidate_board_v2(board) == board


def test_evidence_reader_quarantines_summary_event_conflict_without_aborting(
    tmp_path,
) -> None:
    qualified = _qualified(context_id="ctx-evidence-reader-qualified")
    qualified_context = copy.deepcopy(
        qualified["candidate_summary"]["candidate_event_context"]
    )
    qualified["event"] = {
        "strategy_name": qualified_context["strategy_name"],
        "symbol": qualified_context["symbol"],
        "side": qualified_context["side"],
        "context_id": qualified_context["context_id"],
        "signal_id": qualified_context["signal_id"],
        "engine_mode": qualified_context["evidence_engine_mode"],
        "ts_ms": qualified_context["captured_at_ms"],
        "candidate_event_context": qualified_context,
    }
    conflicted = _qualified(context_id="ctx-evidence-reader-conflicted")
    conflicted_context = copy.deepcopy(
        conflicted["candidate_summary"]["candidate_event_context"]
    )
    conflicted["event"] = {
        "strategy_name": conflicted_context["strategy_name"],
        "symbol": conflicted_context["symbol"],
        "side": conflicted_context["side"],
        "context_id": conflicted_context["context_id"],
        "signal_id": conflicted_context["signal_id"],
        "engine_mode": conflicted_context["evidence_engine_mode"],
        "ts_ms": conflicted_context["captured_at_ms"],
        "candidate_event_context": conflicted_context,
    }
    conflicted["candidate_summary"]["candidate_event_context"] = copy.deepcopy(
        qualified_context
    )
    conflicted_source_summary = copy.deepcopy(conflicted["candidate_summary"])
    conflicted_source_event = copy.deepcopy(conflicted["event"])
    ledger = tmp_path / "candidate_evidence_conflict.jsonl"
    ledger.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True)
            for row in (qualified, conflicted)
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="CANDIDATE_EVENT_CONTEXT_SUMMARY_CONFLICT",
    ):
        read_jsonl_ledger(ledger)

    evidence_rows = read_candidate_evidence_jsonl_ledger(ledger)
    assert evidence_rows[0]["candidate_summary"][
        "candidate_event_context_status"
    ] == "VALID"
    assert evidence_rows[1]["candidate_summary"][
        "candidate_event_context_status"
    ] == "INVALID_LINEAGE_CONFLICT"
    assert evidence_rows[1]["candidate_lineage_conflict_audit"] == {
        "status": "INVALID_LINEAGE_CONFLICT",
        "source_candidate_summary": conflicted_source_summary,
        "source_event": conflicted_source_event,
    }
    board = build_blocked_signal_outcome_review(
        evidence_rows,
        now_utc=NOW,
    )["learning_candidate_board"]

    assert board["qualified_lineage_outcome_row_count"] == 1
    assert board["invalid_lineage_outcome_row_count"] == 1
    assert board["lineage_exclusion_reason_counts"] == {
        "INVALID_LINEAGE_EXACT_COHORT": 1
    }
    assert all(row["selection_eligible"] is False for row in board["candidate_rows"])
    assert validate_learning_candidate_board_v2(board) == board


def test_pure_candidate_evidence_projection_matches_path_and_does_not_mutate(
    tmp_path,
) -> None:
    qualified = _qualified(context_id="ctx-pure-projection-qualified")
    qualified_context = copy.deepcopy(
        qualified["candidate_summary"]["candidate_event_context"]
    )
    qualified["event"] = {
        "strategy_name": qualified_context["strategy_name"],
        "symbol": qualified_context["symbol"],
        "side": qualified_context["side"],
        "context_id": qualified_context["context_id"],
        "signal_id": qualified_context["signal_id"],
        "engine_mode": qualified_context["evidence_engine_mode"],
        "ts_ms": qualified_context["captured_at_ms"],
        "candidate_event_context": qualified_context,
    }
    conflicted = _qualified(context_id="ctx-pure-projection-conflicted")
    conflicted_context = copy.deepcopy(
        conflicted["candidate_summary"]["candidate_event_context"]
    )
    conflicted["event"] = {
        "strategy_name": conflicted_context["strategy_name"],
        "symbol": conflicted_context["symbol"],
        "side": conflicted_context["side"],
        "context_id": conflicted_context["context_id"],
        "signal_id": conflicted_context["signal_id"],
        "engine_mode": conflicted_context["evidence_engine_mode"],
        "ts_ms": conflicted_context["captured_at_ms"],
        "candidate_event_context": conflicted_context,
    }
    conflicted["event"]["candidate_event_context"]["symbol"] = "ETHUSDT"
    source_rows = [qualified, conflicted]
    source_before = copy.deepcopy(source_rows)
    ledger_path = tmp_path / "pure_projection_parity.jsonl"
    ledger_path.write_text(
        "".join(json.dumps(row) + "\n" for row in source_rows),
        encoding="utf-8",
    )

    projected = runtime_adapter_module.project_candidate_evidence_rows(
        source_rows
    )
    path_projected = read_candidate_evidence_jsonl_ledger(ledger_path)

    assert projected == path_projected
    assert source_rows == source_before
    assert projected is not source_rows
    assert projected[0] is not source_rows[0]
    assert projected[0]["event"] is not source_rows[0]["event"]


def test_type_strict_bool_int_summary_conflict_is_rejected_and_quarantined(
    tmp_path,
) -> None:
    row = _qualified(context_id="ctx-evidence-reader-bool-int-conflict")
    event_context = copy.deepcopy(
        row["candidate_summary"]["candidate_event_context"]
    )
    row["candidate_summary"]["candidate_event_context"]["scanner_inputs"][
        "legacy_would_block"
    ] = 0
    row["event"] = {
        "strategy_name": event_context["strategy_name"],
        "symbol": event_context["symbol"],
        "side": event_context["side"],
        "context_id": event_context["context_id"],
        "signal_id": event_context["signal_id"],
        "engine_mode": event_context["evidence_engine_mode"],
        "ts_ms": event_context["captured_at_ms"],
        "candidate_event_context": event_context,
    }
    ledger = tmp_path / "candidate_evidence_bool_int_conflict.jsonl"
    ledger.write_text(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="CANDIDATE_EVENT_CONTEXT_SUMMARY_CONFLICT",
    ):
        read_jsonl_ledger(ledger)

    evidence_rows = read_candidate_evidence_jsonl_ledger(ledger)
    assert evidence_rows[0]["candidate_summary"][
        "candidate_event_context_status"
    ] == "INVALID_LINEAGE_CONFLICT"
    assert "candidate_lineage_conflict_audit" in evidence_rows[0]
    board = build_blocked_signal_outcome_review(
        evidence_rows,
        now_utc=NOW,
    )["learning_candidate_board"]

    assert board["qualified_lineage_outcome_row_count"] == 0
    assert board["invalid_lineage_outcome_row_count"] == 1
    assert board["lineage_exclusion_reason_counts"] == {
        "INVALID_LINEAGE_EXACT_COHORT": 1
    }
    assert board["candidate_rows"]
    assert all(row["selection_eligible"] is False for row in board["candidate_rows"])
    assert validate_learning_candidate_board_v2(board) == board


def test_type_strict_int_float_blocked_conflict_is_rejected_and_quarantined(
    tmp_path,
) -> None:
    row = _qualified(context_id="ctx-evidence-reader-int-float-conflict")
    blocked_context = copy.deepcopy(
        row["candidate_summary"]["candidate_event_context"]
    )
    blocked_context["capture_status"] = "CAPTURE_BLOCKED"
    blocked_context["capture_blockers"] = ["BBO_MISSING_OR_INVALID"]
    blocked_context["event_hash"] = canonical_sha256(
        {
            key: value
            for key, value in blocked_context.items()
            if key != "event_hash"
        }
    )
    summary_context = copy.deepcopy(blocked_context)
    summary_context["captured_at_ms"] = float(summary_context["captured_at_ms"])
    row["candidate_summary"]["candidate_event_context"] = summary_context
    row["candidate_summary"][
        "candidate_event_context_status"
    ] = "CAPTURE_BLOCKED"
    row["event"] = {
        "strategy_name": blocked_context["strategy_name"],
        "symbol": blocked_context["symbol"],
        "side": blocked_context["side"],
        "context_id": blocked_context["context_id"],
        "signal_id": blocked_context["signal_id"],
        "engine_mode": blocked_context["evidence_engine_mode"],
        "ts_ms": blocked_context["captured_at_ms"],
        "candidate_event_context": blocked_context,
    }
    ledger = tmp_path / "candidate_evidence_int_float_conflict.jsonl"
    ledger.write_text(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="EVENT_CONTEXT_CAPTURE_INCOMPLETE"):
        read_jsonl_ledger(ledger)

    evidence_rows = read_candidate_evidence_jsonl_ledger(ledger)
    assert evidence_rows[0]["candidate_summary"][
        "candidate_event_context_status"
    ] == "INVALID_LINEAGE_CONFLICT"
    assert "candidate_lineage_conflict_audit" in evidence_rows[0]
    board = build_blocked_signal_outcome_review(
        evidence_rows,
        now_utc=NOW,
    )["learning_candidate_board"]

    assert board["qualified_lineage_outcome_row_count"] == 0
    assert board["invalid_lineage_outcome_row_count"] == 1
    assert not any(row["selection_eligible"] for row in board["candidate_rows"])
    assert validate_learning_candidate_board_v2(board) == board


@pytest.mark.parametrize(
    ("include_event", "event_value"),
    (
        (False, None),
        (True, "not-an-object"),
    ),
)
def test_evidence_reader_quarantines_valid_summary_without_object_event(
    tmp_path,
    include_event: bool,
    event_value: object,
) -> None:
    row = _qualified(context_id="ctx-evidence-reader-no-object-event")
    if include_event:
        row["event"] = event_value
    ledger = tmp_path / "candidate_evidence_no_object_event.jsonl"
    ledger.write_text(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="CANDIDATE_EVENT_CONTEXT_SUMMARY_CONFLICT",
    ):
        read_jsonl_ledger(ledger)

    evidence_rows = read_candidate_evidence_jsonl_ledger(ledger)
    assert evidence_rows[0]["candidate_summary"][
        "candidate_event_context_status"
    ] == "INVALID_LINEAGE_EVENT_MISSING_OR_INVALID"
    board = build_blocked_signal_outcome_review(
        evidence_rows,
        now_utc=NOW,
    )["learning_candidate_board"]

    assert board["qualified_lineage_outcome_row_count"] == 0
    assert board["invalid_lineage_outcome_row_count"] == 1
    assert board["lineage_exclusion_reason_counts"] == {
        "INVALID_LINEAGE_EXACT_COHORT": 1
    }
    assert board["candidate_rows"]
    assert all(row["selection_eligible"] is False for row in board["candidate_rows"])
    assert validate_learning_candidate_board_v2(board) == board


def test_evidence_reader_quarantines_valid_summary_when_event_lacks_context(
    tmp_path,
) -> None:
    row = _qualified(context_id="ctx-evidence-reader-context-less-event")
    context = row["candidate_summary"]["candidate_event_context"]
    row["event"] = {
        "strategy_name": context["strategy_name"],
        "symbol": context["symbol"],
        "side": context["side"],
        "context_id": context["context_id"],
        "signal_id": context["signal_id"],
        "engine_mode": context["evidence_engine_mode"],
        "ts_ms": context["captured_at_ms"],
    }
    ledger = tmp_path / "candidate_evidence_context_less_event.jsonl"
    ledger.write_text(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="CANDIDATE_EVENT_CONTEXT_SUMMARY_CONFLICT",
    ):
        read_jsonl_ledger(ledger)

    evidence_rows = read_candidate_evidence_jsonl_ledger(ledger)
    assert evidence_rows[0]["candidate_summary"][
        "candidate_event_context_status"
    ] == "INVALID_LINEAGE_EVENT_CONTEXT_MISSING"
    board = build_blocked_signal_outcome_review(
        evidence_rows,
        now_utc=NOW,
    )["learning_candidate_board"]

    assert board["qualified_lineage_outcome_row_count"] == 0
    assert board["invalid_lineage_outcome_row_count"] == 1
    assert board["lineage_exclusion_reason_counts"] == {
        "INVALID_LINEAGE_EXACT_COHORT": 1
    }
    assert board["candidate_rows"]
    assert all(row["selection_eligible"] is False for row in board["candidate_rows"])
    assert validate_learning_candidate_board_v2(board) == board


def test_evidence_reader_quarantines_outer_binding_mismatch_and_preserves_audit(
    tmp_path,
) -> None:
    row = _qualified(context_id="ctx-evidence-reader-outer-binding-mismatch")
    context = copy.deepcopy(
        row["candidate_summary"]["candidate_event_context"]
    )
    row["event"] = {
        "strategy_name": context["strategy_name"],
        "symbol": "ETHUSDT",
        "side": context["side"],
        "context_id": context["context_id"],
        "signal_id": context["signal_id"],
        "engine_mode": context["evidence_engine_mode"],
        "ts_ms": context["captured_at_ms"],
        "candidate_event_context": context,
    }
    source_summary = copy.deepcopy(row["candidate_summary"])
    source_event = copy.deepcopy(row["event"])
    ledger = tmp_path / "candidate_evidence_outer_binding_mismatch.jsonl"
    ledger.write_text(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="CANDIDATE_EVENT_CONTEXT_OUTER_BINDING_MISMATCH:symbol",
    ):
        read_jsonl_ledger(ledger)

    evidence_rows = read_candidate_evidence_jsonl_ledger(ledger)
    evidence_row = evidence_rows[0]
    assert evidence_row["candidate_summary"][
        "candidate_event_context_status"
    ] == "INVALID_LINEAGE_CONFLICT"
    assert evidence_row["candidate_lineage_conflict_audit"] == {
        "status": "INVALID_LINEAGE_CONFLICT",
        "source_candidate_summary": source_summary,
        "source_event": source_event,
    }
    board = build_blocked_signal_outcome_review(
        evidence_rows,
        now_utc=NOW,
    )["learning_candidate_board"]

    assert board["qualified_lineage_outcome_row_count"] == 0
    assert board["invalid_lineage_outcome_row_count"] == 1
    assert board["lineage_exclusion_reason_counts"] == {
        "INVALID_LINEAGE_EXACT_COHORT": 1
    }
    assert board["candidate_rows"]
    assert all(row["selection_eligible"] is False for row in board["candidate_rows"])
    assert validate_learning_candidate_board_v2(board) == board


def test_raw_valid_missing_evaluation_and_outside_window_are_unqualified() -> None:
    raw_only = _qualified(context_id="ctx-raw-only")
    raw_summary = copy.deepcopy(raw_only["candidate_summary"])
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
    ):
        raw_summary.pop(field)
    raw_only["candidate_summary"] = raw_summary
    outside_ts = int(
        dt.datetime(2026, 7, 2, 12, tzinfo=dt.timezone.utc).timestamp() * 1_000
    )
    outside = attach_candidate_lineage_v2(
        _outcome(attempt_id="ctx-outside-window"),
        context_id="ctx-outside-window",
        captured_at_ms=outside_ts,
        as_of_utc_date=NOW.date().isoformat(),
        require_event_in_window=False,
    )

    board = _board([outside, raw_only])

    assert board["candidate_rows"] == []
    assert board["raw_blocked_outcome_row_count"] == 2
    assert board["qualified_lineage_outcome_row_count"] == 0
    assert board["unqualified_lineage_outcome_row_count"] == 2
    assert board["invalid_lineage_outcome_row_count"] == 0
    assert board["unqualified_raw_valid_evaluation_missing_row_count"] == 1
    assert board["unqualified_event_outside_evaluation_window_row_count"] == 1
    assert board["lineage_exclusion_reason_counts"] == {
        "UNQUALIFIED_EVENT_OUTSIDE_EVALUATION_WINDOW": 1,
        "UNQUALIFIED_RAW_VALID_EVALUATION_MISSING": 1,
    }


def test_recorded_date_invalid_exact_row_remains_addressable_and_board_validates() -> None:
    event_ts_ms = int(
        dt.datetime(2026, 7, 9, 12, tzinfo=dt.timezone.utc).timestamp() * 1_000
    )
    stale = attach_candidate_lineage_v2(
        _outcome(attempt_id="ctx-stale-invalid-exact-only"),
        context_id="ctx-stale-invalid-exact-only",
        captured_at_ms=event_ts_ms,
        as_of_utc_date="2026-07-17",
        require_event_in_window=False,
    )
    stale["side_cell_key"] = "ma_crossover|BTCUSDT|Sell"

    board = build_blocked_signal_outcome_review(
        [stale], now_utc=dt.datetime(2026, 7, 17, 18, tzinfo=dt.timezone.utc)
    )["learning_candidate_board"]

    assert len(board["candidate_rows"]) == 1
    assert board["invalid_lineage_outcome_row_count"] == 1
    assert board["invalid_exact_cohort_row_count"] == 1
    assert board["lineage_exclusion_reason_counts"] == {
        "INVALID_LINEAGE_EXACT_COHORT": 1
    }
    candidate = board["candidate_rows"][0]
    assert candidate["invalid_lineage_exact_cohort_row_count"] == 1
    assert candidate["selection_eligible"] is False
    assert validate_learning_candidate_board_v2(board) == board


def test_recorded_date_qualified_lineage_is_not_demoted_by_review_date() -> None:
    event_ts_ms = int(
        dt.datetime(2026, 7, 8, 12, tzinfo=dt.timezone.utc).timestamp() * 1_000
    )
    stale = attach_candidate_lineage_v2(
        _outcome(attempt_id="ctx-stale-qualified-lineage"),
        context_id="ctx-stale-qualified-lineage",
        captured_at_ms=event_ts_ms,
        as_of_utc_date="2026-07-09",
    )

    board = _board([stale])

    assert len(board["candidate_rows"]) == 1
    assert board["qualified_lineage_outcome_row_count"] == 1
    assert board["invalid_lineage_outcome_row_count"] == 0
    assert board["invalid_exact_cohort_row_count"] == 0
    assert board["lineage_exclusion_reason_counts"] == {}
    assert validate_learning_candidate_board_v2(board) == board


def test_stale_invalid_exact_hash_quarantines_addressable_current_cohort() -> None:
    context_id = "ctx-stale-invalid-exact-addressable"
    event_ts_ms = int(
        dt.datetime(2026, 7, 9, 12, tzinfo=dt.timezone.utc).timestamp() * 1_000
    )
    qualified = _qualified(context_id=context_id, captured_at_ms=event_ts_ms)
    stale = attach_candidate_lineage_v2(
        _outcome(attempt_id=context_id),
        context_id=context_id,
        captured_at_ms=event_ts_ms,
        as_of_utc_date="2026-07-17",
        require_event_in_window=False,
    )
    stale["side_cell_key"] = "ma_crossover|BTCUSDT|Sell"

    board = build_blocked_signal_outcome_review(
        [stale, qualified],
        now_utc=dt.datetime(2026, 7, 17, 18, tzinfo=dt.timezone.utc),
    )["learning_candidate_board"]

    assert board["invalid_exact_cohort_row_count"] == 1
    assert board["conflicting_duplicate_event_hash_row_count"] == 2
    assert len(board["candidate_rows"]) == 2
    assert all(
        candidate["qualified_evaluator_input_count"] == 0
        and candidate["conflicting_event_hash_row_count"] == 1
        and "DUPLICATE_EVENT_HASH_COHORT_CONFLICT" in candidate["blockers"]
        for candidate in board["candidate_rows"]
    )
    assert sorted(
        candidate["invalid_lineage_exact_cohort_row_count"]
        for candidate in board["candidate_rows"]
    ) == [0, 1]
    assert validate_learning_candidate_board_v2(board) == board


def test_raw_valid_unqualified_outcome_conflict_quarantines_qualified_copy() -> None:
    qualified = _qualified(context_id="ctx-qualified-raw-only-conflict")
    raw_only = copy.deepcopy(qualified)
    raw_only["realized_net_bps"] = qualified["realized_net_bps"] + 1.0
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
    ):
        raw_only["candidate_summary"].pop(field)

    board = _board([qualified, raw_only])

    assert board["qualified_lineage_outcome_row_count"] == 1
    assert board["unqualified_lineage_outcome_row_count"] == 1
    assert board["unqualified_raw_valid_evaluation_missing_row_count"] == 1
    assert board["conflicting_duplicate_event_hash_row_count"] == 2
    assert board["conflicting_duplicate_event_hash_attribution_row_count"] == 2
    candidate = board["candidate_rows"][0]
    assert candidate["qualified_raw_outcome_count"] == 1
    assert candidate["qualified_evaluator_input_count"] == 0
    assert candidate["n_eff"] == 0
    assert candidate["conflicting_event_hash_row_count"] == 2
    assert candidate["duplicate_event_hash_outcome_conflict_row_count"] == 2
    assert candidate["lineage_blocker_reason_counts"] == {
        "DUPLICATE_EVENT_HASH_OUTCOME_CONFLICT": 2
    }
    assert "DUPLICATE_EVENT_HASH_OUTCOME_CONFLICT" in candidate["blockers"]


def test_outside_window_unqualified_conflict_maps_to_existing_finite_window() -> None:
    captured_at_ms = int(
        dt.datetime(2026, 7, 9, 12, tzinfo=dt.timezone.utc).timestamp() * 1_000
    )
    context_id = "ctx-qualified-outside-window-conflict"
    qualified = _qualified(
        context_id=context_id,
        captured_at_ms=captured_at_ms,
    )
    outside = attach_candidate_lineage_v2(
        _outcome(attempt_id=context_id),
        context_id=context_id,
        captured_at_ms=captured_at_ms,
        as_of_utc_date="2026-07-17",
        require_event_in_window=False,
    )
    outside["realized_net_bps"] = qualified["realized_net_bps"] + 2.0

    board = _board([outside, qualified])

    assert board["qualified_lineage_outcome_row_count"] == 1
    assert board["unqualified_event_outside_evaluation_window_row_count"] == 1
    assert board["conflicting_duplicate_event_hash_row_count"] == 2
    assert board["conflicting_duplicate_event_hash_attribution_row_count"] == 2
    assert len(board["candidate_rows"]) == 1
    candidate = board["candidate_rows"][0]
    assert candidate["qualified_raw_outcome_count"] == 1
    assert candidate["qualified_evaluator_input_count"] == 0
    assert candidate["n_eff"] == 0
    assert candidate["duplicate_event_hash_outcome_conflict_row_count"] == 2


def test_consistent_raw_only_unqualified_copy_does_not_poison_denominator() -> None:
    qualified = _qualified(context_id="ctx-qualified-raw-only-consistent")
    raw_only = copy.deepcopy(qualified)
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
    ):
        raw_only["candidate_summary"].pop(field)

    baseline = _board([qualified])
    board = _board([raw_only, qualified])

    assert board["unqualified_raw_valid_evaluation_missing_row_count"] == 1
    assert board["conflicting_duplicate_event_hash_row_count"] == 0
    assert board["consistent_duplicate_event_hash_extra_row_count"] == 0
    assert board["candidate_rows"] == baseline["candidate_rows"]
    assert board["candidate_rows"][0]["qualified_evaluator_input_count"] == 1
    assert board["candidate_rows"][0]["n_eff"] == 1


def test_missing_raw_status_has_one_exact_unqualified_exception() -> None:
    absent = _outcome(attempt_id="ctx-raw-absent")
    explicit_missing = {
        **_outcome(attempt_id="ctx-raw-explicit-missing"),
        "candidate_summary": {
            "candidate_event_context_status": "UNQUALIFIED_CONTEXT_MISSING"
        },
    }
    legacy_only = {
        **_outcome(attempt_id="ctx-legacy-only"),
        "candidate_summary": {"candidate_learning_context": {"legacy": True}},
    }
    invalid_valid_status = {
        **_outcome(attempt_id="ctx-raw-status-valid-without-payload"),
        "candidate_summary": {"candidate_event_context_status": "VALID"},
    }
    invalid_other_status = {
        **_outcome(attempt_id="ctx-raw-status-other-without-payload"),
        "candidate_summary": {"candidate_event_context_status": "BROKEN"},
    }

    board = _board(
        [
            invalid_other_status,
            legacy_only,
            explicit_missing,
            invalid_valid_status,
            absent,
        ]
    )

    assert board["candidate_rows"] == []
    assert board["raw_blocked_outcome_row_count"] == 5
    assert board["unqualified_lineage_outcome_row_count"] == 3
    assert board["invalid_lineage_outcome_row_count"] == 2
    assert board["unassigned_invalid_lineage_outcome_row_count"] == 2
    assert board["lineage_exclusion_reason_counts"] == {
        "INVALID_LINEAGE_RAW_CONTEXT_INVALID": 2,
        "UNQUALIFIED_CONTEXT_MISSING": 2,
        "UNQUALIFIED_LEGACY_PROJECTION_ONLY": 1,
    }


def test_unassigned_invalid_changes_only_audit_and_full_board_hash() -> None:
    qualified = _qualified(context_id="ctx-unassigned-baseline")
    poison = {
        **_outcome(attempt_id="ctx-unassigned-invalid"),
        "candidate_summary": {
            "candidate_event_context_status": "VALID",
            "candidate_evaluation_context_status": "VALID",
        },
    }

    baseline = _board([qualified])
    attacked = _board([poison, qualified])
    reversed_board = _board([qualified, poison])

    assert attacked == reversed_board
    assert attacked["candidate_rows"] == baseline["candidate_rows"]
    assert attacked["selection_hash"] == baseline["selection_hash"]
    assert attacked["audit_hash"] != baseline["audit_hash"]
    assert attacked["board_hash"] != baseline["board_hash"]
    assert attacked["invalid_lineage_outcome_row_count"] == 1
    assert attacked["unassigned_invalid_lineage_outcome_row_count"] == 1
    assert attacked["invalid_exact_cohort_row_count"] == 0
    assert attacked["invalid_identity_family_row_count"] == 0
    assert (
        attacked["raw_blocked_outcome_row_count"]
        == attacked["qualified_lineage_outcome_row_count"]
        + attacked["unqualified_lineage_outcome_row_count"]
        + attacked["invalid_lineage_outcome_row_count"]
    )


def test_per_event_hash_and_regime_label_churn_do_not_split_stable_cohort() -> None:
    first = _qualified(
        context_id="ctx-regime-bear",
        captured_at_ms=int(
            dt.datetime(2026, 7, 8, 12, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
        evidence_regime_label="bear|low_vol|liquid",
    )
    second = _qualified(
        context_id="ctx-regime-bull",
        captured_at_ms=int(
            dt.datetime(2026, 7, 9, 12, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
        evidence_regime_label="bull|high_vol|thin",
    )

    board = _board([second, first])

    assert len(board["candidate_rows"]) == 1
    candidate = board["candidate_rows"][0]
    assert candidate["qualified_raw_outcome_count"] == 2
    assert candidate["regime_entry_counts"]["bear|low_vol|liquid"] == 1
    assert candidate["regime_entry_counts"]["bull|high_vol|thin"] == 1
    assert candidate["n_eff"] == 2


def test_stable_projection_split_requires_unique_candidate_id_context_hash() -> None:
    baseline = _qualified(context_id="ctx-stable-a")
    collision = _qualified(
        context_id="ctx-stable-b",
        stable_projection_overrides={
            "portfolio": {"beta_to_portfolio": "0.75"},
        },
    )

    with pytest.raises(ValueError, match="CANDIDATE_ID_COLLISION"):
        _board([baseline, collision])

    separated = _qualified(
        context_id="ctx-stable-c",
        stable_projection_overrides={
            "portfolio": {"beta_to_portfolio": "0.75"},
            "context_hashes": {"portfolio": "7" * 64},
        },
    )
    board = _board([baseline, separated])
    assert len(board["candidate_rows"]) == 2
    assert len({row["stable_cohort_hash"] for row in board["candidate_rows"]}) == 2
    assert len({row["candidate_id"] for row in board["candidate_rows"]}) == 2


@pytest.mark.parametrize(
    ("field", "poison"),
    (
        ("strategy_name", "other_strategy"),
        ("symbol", "ETHUSDT"),
        ("side", "Sell"),
        ("horizon_minutes", 60.0),
        ("event_ts_ms", 1.0),
        ("attempt_id", "grafted-attempt"),
        ("side_cell_key", "ma_crossover|BTCUSDT|Sell"),
    ),
)
def test_every_outer_identity_graft_is_exact_cohort_invalid(
    field: str, poison: object
) -> None:
    valid = _qualified(context_id="ctx-outer-valid")
    grafted = _qualified(
        context_id=f"ctx-outer-graft-{field}",
        captured_at_ms=int(
            dt.datetime(2026, 7, 8, 12, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
    )
    grafted[field] = poison

    board = _board([valid, grafted])

    assert board["qualified_lineage_outcome_row_count"] == 1
    assert board["invalid_lineage_outcome_row_count"] == 1
    assert board["invalid_exact_cohort_row_count"] == 1
    assert board["invalid_identity_family_row_count"] == 0
    candidate = board["candidate_rows"][0]
    assert candidate["qualified_raw_outcome_count"] == 1
    assert candidate["invalid_lineage_exact_cohort_row_count"] == 1
    assert "INVALID_LINEAGE_EXACT_COHORT_ROWS_PRESENT" in candidate["blockers"]
    assert candidate["arbiter_input_complete"] is False
    assert candidate["selection_eligible"] is False
    assert candidate["qualified_metrics_actionable"] is False
    assert candidate["metrics_scope"] == "QUALIFIED_SUBSET_DESCRIPTIVE_ONLY"


def test_exact_and_family_invalid_rows_block_only_addressable_cohorts() -> None:
    baseline = _qualified(
        context_id="ctx-attribution-base",
        captured_at_ms=int(
            dt.datetime(2026, 7, 7, 12, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
    )
    other_regime = _qualified(
        context_id="ctx-attribution-other-regime",
        captured_at_ms=int(
            dt.datetime(2026, 7, 8, 12, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
        stable_projection_overrides={
            "target_regime_context": {"label": "bull|high_vol|thin"},
        },
    )
    exact_invalid = _qualified(
        context_id="ctx-attribution-exact-invalid",
        captured_at_ms=int(
            dt.datetime(2026, 7, 9, 10, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
    )
    exact_summary = copy.deepcopy(exact_invalid["candidate_summary"])
    exact_summary["candidate_learning_context_projection"]["portfolio"][
        "beta_to_portfolio"
    ] = "0.9"
    exact_invalid["candidate_summary"] = exact_summary

    family_invalid = _qualified(
        context_id="ctx-attribution-family-invalid",
        captured_at_ms=int(
            dt.datetime(2026, 7, 9, 14, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
    )
    family_summary = copy.deepcopy(family_invalid["candidate_summary"])
    family_summary.pop("candidate_evaluation_context")
    family_invalid["candidate_summary"] = family_summary

    board = _board([other_regime, exact_invalid, family_invalid, baseline])

    assert board["qualified_lineage_outcome_row_count"] == 2
    assert board["invalid_lineage_outcome_row_count"] == 2
    assert board["invalid_exact_cohort_row_count"] == 1
    assert board["invalid_identity_family_row_count"] == 1
    assert board["unassigned_invalid_lineage_outcome_row_count"] == 0
    assert board["conflicting_duplicate_event_hash_row_count"] == 0
    assert len(board["candidate_rows"]) == 2
    exact_scoped = next(
        row
        for row in board["candidate_rows"]
        if row["invalid_lineage_exact_cohort_row_count"] == 1
    )
    family_only = next(
        row
        for row in board["candidate_rows"]
        if row["invalid_lineage_exact_cohort_row_count"] == 0
    )
    assert exact_scoped["invalid_lineage_identity_family_row_count"] == 1
    assert family_only["invalid_lineage_identity_family_row_count"] == 1
    assert "INVALID_LINEAGE_EXACT_COHORT_ROWS_PRESENT" in exact_scoped["blockers"]
    assert "INVALID_LINEAGE_EXACT_COHORT_ROWS_PRESENT" not in family_only["blockers"]
    assert all(
        "INVALID_LINEAGE_IDENTITY_FAMILY_ROWS_PRESENT" in row["blockers"]
        for row in board["candidate_rows"]
    )
    assert all(
        row["conflicting_event_hash_row_count"] == 0
        for row in board["candidate_rows"]
    )


def test_consistent_duplicate_event_hash_is_audit_only_and_permutation_stable() -> None:
    first = _qualified(context_id="ctx-duplicate-consistent")
    second = copy.deepcopy(first)
    first["generated_at_utc"] = "2026-07-10T12:00:00Z"
    second["generated_at_utc"] = "2026-07-10T12:01:00Z"

    forward = _board([first, second])
    reverse = _board([second, first])
    baseline = _board([first])

    assert forward == reverse
    assert forward["selection_hash"] == baseline["selection_hash"]
    assert forward["audit_hash"] != baseline["audit_hash"]
    assert forward["consistent_duplicate_event_hash_extra_row_count"] == 1
    assert forward["conflicting_duplicate_event_hash_row_count"] == 0
    candidate = forward["candidate_rows"][0]
    assert candidate["qualified_raw_outcome_count"] == 2
    assert candidate["qualified_evaluator_input_count"] == 1
    assert candidate["consistent_duplicate_event_hash_extra_row_count"] == 1
    assert candidate["conflicting_event_hash_row_count"] == 0
    assert candidate["n_eff"] == baseline["candidate_rows"][0]["n_eff"] == 1


def test_duplicate_event_hash_tolerance_chain_is_permutation_stable() -> None:
    """Pairwise tolerance must not let input order choose conflict vs denominator."""
    baseline = _qualified(context_id="ctx-duplicate-tolerance-chain")
    rows = []
    for delta in (0.0, 0.75e-9, 1.5e-9):
        row = copy.deepcopy(baseline)
        row["realized_net_bps"] = float(row["realized_net_bps"]) + delta
        rows.append(row)

    low_first = _board(rows)
    middle_first = _board([rows[1], rows[0], rows[2]])

    assert low_first == middle_first
    assert low_first["conflicting_duplicate_event_hash_row_count"] == 3
    assert low_first["consistent_duplicate_event_hash_extra_row_count"] == 0
    candidate = low_first["candidate_rows"][0]
    assert candidate["qualified_evaluator_input_count"] == 0
    assert candidate["duplicate_event_hash_outcome_conflict_row_count"] == 3


def test_duplicate_event_hash_group_comparison_is_linear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _qualified(context_id="ctx-duplicate-linear-group")
    rows = [copy.deepcopy(baseline) for _ in range(1_000)]
    original = candidate_board_module._duplicate_semantics_equal
    calls = 0

    def counted(left: object, right: object) -> bool:
        nonlocal calls
        calls += 1
        if calls > 2_000:
            raise AssertionError("duplicate group comparison exceeded linear budget")
        return original(left, right)

    monkeypatch.setattr(
        candidate_board_module,
        "_duplicate_semantics_equal",
        counted,
    )

    board = _board(rows)

    assert calls <= len(rows)
    assert board["consistent_duplicate_event_hash_extra_row_count"] == 999
    assert board["conflicting_duplicate_event_hash_row_count"] == 0


def test_multi_cohort_duplicate_attribution_is_linear_and_permutation_stable() -> None:
    class CountedCohort(str):
        comparisons = 0

        def __eq__(self, other: object) -> bool:
            type(self).comparisons += 1
            return super().__eq__(other)

        __hash__ = str.__hash__

    cohort_count = 512
    qualified = [
        {
            "event_hash": "e" * 64,
            "stable_cohort_hash": CountedCohort(f"{index:064x}"),
            "row": {},
        }
        for index in range(cohort_count)
    ]

    CountedCohort.comparisons = 0
    forward = candidate_board_module._gate_duplicate_event_hashes(qualified, [])
    forward_comparisons = CountedCohort.comparisons
    CountedCohort.comparisons = 0
    reverse = candidate_board_module._gate_duplicate_event_hashes(
        list(reversed(qualified)),
        [],
    )
    reverse_comparisons = CountedCohort.comparisons

    assert forward == reverse
    assert forward[3] == cohort_count
    assert forward_comparisons <= cohort_count * 8
    assert reverse_comparisons <= cohort_count * 8


def test_qualified_and_unqualified_duplicate_extremes_share_one_range() -> None:
    qualified = _qualified(context_id="ctx-duplicate-mixed-range")
    raw_only_low = copy.deepcopy(qualified)
    raw_only_high = copy.deepcopy(qualified)
    for row in (raw_only_low, raw_only_high):
        for field in (
            "candidate_evaluation_context",
            "candidate_evaluation_context_status",
            "candidate_learning_context_projection",
        ):
            row["candidate_summary"].pop(field)
    raw_only_low["realized_net_bps"] = float(qualified["realized_net_bps"]) - 0.75e-9
    raw_only_high["realized_net_bps"] = float(qualified["realized_net_bps"]) + 0.75e-9

    forward = _board([raw_only_low, qualified, raw_only_high])
    reverse = _board([raw_only_high, qualified, raw_only_low])

    assert forward == reverse
    assert forward["conflicting_duplicate_event_hash_row_count"] == 3
    candidate = forward["candidate_rows"][0]
    assert candidate["qualified_evaluator_input_count"] == 0
    assert candidate["duplicate_event_hash_outcome_conflict_row_count"] == 3


def test_censored_duplicate_event_hash_does_not_inflate_censoring_share() -> None:
    first = _qualified(context_id="ctx-duplicate-censored")
    first.update(
        {
            "censored": True,
            "censor_reason": "price_observation_missing",
            "gross_bps": None,
            "cost_bps": None,
            "realized_net_bps": None,
            "net_bps_optimistic": None,
        }
    )
    second = copy.deepcopy(first)

    single = _board([first])["candidate_rows"][0]
    duplicate = _board([second, first])["candidate_rows"][0]

    assert duplicate["qualified_raw_outcome_count"] == 2
    assert duplicate["qualified_evaluator_input_count"] == 1
    assert duplicate["qualified_censored_outcome_count"] == 1
    assert duplicate["qualified_uncensored_outcome_count"] == 0
    assert duplicate["censored_share"] == single["censored_share"] == 1.0
    assert duplicate["consistent_duplicate_event_hash_extra_row_count"] == 1


def test_duplicate_event_outcome_conflict_quarantines_every_copy() -> None:
    first = _qualified(context_id="ctx-duplicate-outcome-conflict")
    second = copy.deepcopy(first)
    second["realized_net_bps"] = first["realized_net_bps"] + 1.0

    forward = _board([first, second])
    reverse = _board([second, first])

    assert forward == reverse
    assert forward["conflicting_duplicate_event_hash_row_count"] == 2
    assert forward[
        "conflicting_duplicate_event_hash_attribution_row_count"
    ] == sum(
        row["conflicting_event_hash_row_count"]
        for row in forward["candidate_rows"]
    )
    candidate = forward["candidate_rows"][0]
    assert candidate["qualified_raw_outcome_count"] == 2
    assert candidate["qualified_evaluator_input_count"] == 0
    assert candidate["conflicting_event_hash_row_count"] == 2
    assert candidate["duplicate_event_hash_outcome_conflict_row_count"] == 2
    assert candidate["n_eff"] == 0
    assert "DUPLICATE_EVENT_HASH_OUTCOME_CONFLICT" in candidate["blockers"]
    assert candidate["arbiter_input_complete"] is False
    assert candidate["selection_eligible"] is False


def test_duplicate_event_hash_across_stable_cohorts_blocks_each_cohort() -> None:
    first = _qualified(context_id="ctx-duplicate-cross-cohort")
    second = _qualified(
        context_id="ctx-duplicate-cross-cohort",
        stable_projection_overrides={
            "portfolio": {"beta_to_portfolio": "0.75"},
            "context_hashes": {"portfolio": "7" * 64},
        },
    )

    board = _board([second, first])

    assert board["qualified_lineage_outcome_row_count"] == 2
    assert board["conflicting_duplicate_event_hash_row_count"] == 2
    assert len(board["candidate_rows"]) == 2
    for candidate in board["candidate_rows"]:
        assert candidate["qualified_evaluator_input_count"] == 0
        assert candidate["duplicate_event_hash_cohort_conflict_row_count"] == 1
        assert "DUPLICATE_EVENT_HASH_COHORT_CONFLICT" in candidate["blockers"]


def test_multi_cohort_unqualified_attribution_can_exceed_unique_conflict_count() -> None:
    first = _qualified(context_id="ctx-duplicate-cross-cohort-unqualified")
    second = _qualified(
        context_id="ctx-duplicate-cross-cohort-unqualified",
        stable_projection_overrides={
            "portfolio": {"beta_to_portfolio": "0.75"},
            "context_hashes": {"portfolio": "7" * 64},
        },
    )
    raw_only = copy.deepcopy(first)
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
    ):
        raw_only["candidate_summary"].pop(field)

    board = _board([raw_only, second, first])

    assert board["qualified_lineage_outcome_row_count"] == 2
    assert board["unqualified_raw_valid_evaluation_missing_row_count"] == 1
    assert board["conflicting_duplicate_event_hash_row_count"] == 3
    assert board["conflicting_duplicate_event_hash_attribution_row_count"] == 4
    assert len(board["candidate_rows"]) == 2
    for candidate in board["candidate_rows"]:
        assert candidate["qualified_raw_outcome_count"] == 1
        assert candidate["qualified_evaluator_input_count"] == 0
        assert candidate["conflicting_event_hash_row_count"] == 2
        assert candidate["duplicate_event_hash_cohort_conflict_row_count"] == 2


def test_disk_projection_matches_list_duplicate_addressability(
    tmp_path,
) -> None:
    first = _qualified(context_id="ctx-disk-projection-addressability")
    second = _qualified(
        context_id="ctx-disk-projection-addressability",
        stable_projection_overrides={
            "portfolio": {"beta_to_portfolio": "0.75"},
            "context_hashes": {"portfolio": "7" * 64},
        },
    )
    raw_only = copy.deepcopy(first)
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
    ):
        raw_only["candidate_summary"].pop(field)
    invalid_family = copy.deepcopy(first)
    invalid_family["candidate_summary"]["candidate_evaluation_context"][
        "identity"
    ]["symbol"] = "ETHUSDT"
    source_rows = [
        _ledger_source_row(row)
        for row in (raw_only, second, invalid_family, first)
    ]
    projected_rows = runtime_adapter_module.project_candidate_evidence_rows(
        source_rows
    )
    expected = build_blocked_signal_outcome_review(
        projected_rows,
        now_utc=NOW,
        source_ledger_row_count=len(source_rows),
    )
    ledger = tmp_path / "projection-parity.jsonl"
    ledger.write_text(
        "".join(json.dumps(row) + "\n" for row in source_rows),
        encoding="utf-8",
    )

    with read_candidate_board_ledger_projection(ledger) as projection:
        actual = build_blocked_signal_outcome_review(
            projection.rows,
            now_utc=NOW,
            source_ledger_row_count=projection.source_ledger_row_count,
        )

    assert actual == expected
    board = actual["learning_candidate_board"]
    assert board["raw_blocked_outcome_row_count"] == 4
    assert board["qualified_lineage_outcome_row_count"] == 2
    assert board["unqualified_lineage_outcome_row_count"] == 1
    assert board["invalid_lineage_outcome_row_count"] == 1
    assert board["conflicting_duplicate_event_hash_row_count"] == 4
    assert board["conflicting_duplicate_event_hash_attribution_row_count"] == 6


def test_disk_projection_preserves_current_exact_invalid_seed(
    tmp_path,
) -> None:
    invalid_exact = _qualified(
        context_id="ctx-disk-projection-current-exact"
    )
    invalid_exact["side_cell_key"] = "ma_crossover|BTCUSDT|Sell"
    source_rows = [_ledger_source_row(invalid_exact)]
    projected_rows = runtime_adapter_module.project_candidate_evidence_rows(
        source_rows
    )
    expected = build_blocked_signal_outcome_review(
        projected_rows,
        now_utc=NOW,
        source_ledger_row_count=1,
    )
    ledger = tmp_path / "current-exact-seed.jsonl"
    ledger.write_text(json.dumps(source_rows[0]) + "\n", encoding="utf-8")

    with read_candidate_board_ledger_projection(ledger) as projection:
        actual = build_blocked_signal_outcome_review(
            projection.rows,
            now_utc=NOW,
            source_ledger_row_count=projection.source_ledger_row_count,
        )

    assert actual == expected
    board = actual["learning_candidate_board"]
    assert board["qualified_lineage_outcome_row_count"] == 0
    assert board["invalid_exact_cohort_row_count"] == 1
    assert len(board["candidate_rows"]) == 1
    assert (
        board["candidate_rows"][0]["invalid_lineage_exact_cohort_row_count"]
        == 1
    )


def test_addressable_invalid_copy_participates_in_event_hash_conflict_gate() -> None:
    valid = _qualified(context_id="ctx-duplicate-invalid-copy")
    invalid = copy.deepcopy(valid)
    invalid["candidate_summary"]["candidate_learning_context_projection"]["proof"][
        "proof_stage"
    ] = 0

    board = _board([valid, invalid])

    assert board["qualified_lineage_outcome_row_count"] == 1
    assert board["invalid_exact_cohort_row_count"] == 1
    assert board["conflicting_duplicate_event_hash_row_count"] == 2
    candidate = board["candidate_rows"][0]
    assert candidate["qualified_evaluator_input_count"] == 0
    assert candidate["duplicate_event_hash_outcome_conflict_row_count"] == 2
    assert "DUPLICATE_EVENT_HASH_OUTCOME_CONFLICT" in candidate["blockers"]
    assert "INVALID_LINEAGE_EXACT_COHORT_ROWS_PRESENT" in candidate["blockers"]


def test_invalid_outcome_stays_qualified_and_censoring_uses_c_plus_u() -> None:
    rows = []
    base_ts = int(
        dt.datetime(2026, 7, 8, 0, tzinfo=dt.timezone.utc).timestamp() * 1_000
    )
    for index in range(10):
        row = _qualified(
            context_id=f"ctx-denominator-{index}",
            captured_at_ms=base_ts + index * 2 * 3_600_000,
        )
        if index < 3:
            row.update(
                {
                    "censored": True,
                    "censor_reason": "price_observation_missing",
                    "gross_bps": None,
                    "cost_bps": None,
                    "realized_net_bps": None,
                    "net_bps_optimistic": None,
                }
            )
        elif index == 3:
            row["realized_net_bps"] = None
        rows.append(row)

    board = _board(list(reversed(rows)))

    assert board["qualified_lineage_outcome_row_count"] == 10
    assert board["invalid_lineage_outcome_row_count"] == 0
    candidate = board["candidate_rows"][0]
    assert candidate["qualified_raw_outcome_count"] == 10
    assert candidate["qualified_evaluator_input_count"] == 10
    assert candidate["qualified_censored_outcome_count"] == 3
    assert candidate["qualified_uncensored_outcome_count"] == 7
    assert candidate["qualified_valid_uncensored_outcome_count"] == 6
    assert candidate["qualified_invalid_outcome_row_count"] == 1
    assert candidate["censored_share"] == pytest.approx(3.0 / 10.0)
    assert "INVALID_OUTCOME_ROWS_PRESENT" in candidate["blockers"]
    assert candidate["qualified_metrics_actionable"] is False
    assert candidate["selection_eligible"] is False


def test_default_review_quarantines_high_positive_unqualified_rows() -> None:
    legacy = _outcome(
        attempt_id="ctx-default-compat-legacy",
        realized_net_bps=100.0,
    )
    unqualified = _qualified(context_id="ctx-default-compat-unqualified")
    unqualified["realized_net_bps"] = 100.0
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
    ):
        unqualified["candidate_summary"].pop(field)

    review = build_blocked_signal_outcome_review(
        [legacy, unqualified],
        now_utc=NOW,
    )

    assert review["require_qualified_lineage"] is True
    assert (
        review["outcome_aggregation_policy"]
        == "CANDIDATE_BOARD_QUALIFIED_EVALUATOR_ROWS"
    )
    assert review["outcome_aggregation_input_row_count"] == 0
    assert review["status"] == "NO_QUALIFIED_LINEAGE_BLOCKED_SIGNAL_OUTCOMES"
    assert review["blocked_signal_outcome_count"] == 0
    assert review["side_cell_count"] == 0
    assert review["review_candidate_side_cell_count"] == 0
    assert review["top_side_cells"] == []


def test_strict_review_keeps_invalid_unqualified_audits_but_aggregates_none() -> None:
    invalid = _qualified(context_id="ctx-strict-empty-invalid")
    invalid["side_cell_key"] = "ma_crossover|BTCUSDT|Sell"
    invalid["realized_net_bps"] = 500.0
    unqualified = _qualified(context_id="ctx-strict-empty-unqualified")
    unqualified["realized_net_bps"] = 500.0
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
    ):
        unqualified["candidate_summary"].pop(field)

    review = build_blocked_signal_outcome_review(
        [invalid, unqualified],
        now_utc=NOW,
    )

    assert review["require_qualified_lineage"] is True
    assert (
        review["outcome_aggregation_policy"]
        == "CANDIDATE_BOARD_QUALIFIED_EVALUATOR_ROWS"
    )
    assert review["source_ledger_row_count"] == 2
    assert review["outcome_aggregation_input_row_count"] == 0
    assert review["status"] == "NO_QUALIFIED_LINEAGE_BLOCKED_SIGNAL_OUTCOMES"
    assert review["reason"] == "candidate_board_qualified_evaluator_rows_missing"
    assert (
        review["next_trigger"]
        == "continue_collecting_qualified_candidate_lineage_outcomes"
    )
    assert review["blocked_signal_outcome_count"] == 0
    assert review["side_cell_count"] == 0
    assert review["review_candidate_side_cell_count"] == 0
    assert review["top_side_cells"] == []
    board = review["learning_candidate_board"]
    assert board["invalid_lineage_outcome_row_count"] == 1
    assert board["unqualified_lineage_outcome_row_count"] == 1
    assert validate_learning_candidate_board_v2(board) == board


@pytest.mark.parametrize(
    ("expected_blocker", "stable_overrides", "with_cost_artifact"),
    (
        (
            "HIDDEN_OOS_CONSUMED",
            {"hidden_oos_state": {
                "state": "consumed",
                "open_count": 1,
                "opened_for_iteration": True,
                "consumed": True,
            }},
            True,
        ),
        (
            "PROOF_GAP_OPEN",
            {"proof": {"next_gap": {
                "kind": "LOCAL_ENGINEERING",
                "code": "PROOF_GAP_REMAINS",
            }}},
            True,
        ),
        ("EXPECTED_COST_NOT_FULLY_RECOMPUTABLE", None, False),
    ),
)
def test_final_candidate_blockers_exclude_cohort_from_strict_aggregation(
    expected_blocker: str,
    stable_overrides: dict[str, object] | None,
    with_cost_artifact: bool,
) -> None:
    review = build_blocked_signal_outcome_review(
        _eligible_cohort_rows(
            f"ctx-final-blocker-{expected_blocker.lower()}",
            stable_projection_overrides=stable_overrides,
        ),
        slippage_quantiles=(
            _expected_cost_artifact() if with_cost_artifact else None
        ),
        now_utc=NOW,
    )
    board = review["learning_candidate_board"]
    candidate = board["candidate_rows"][0]

    assert expected_blocker in candidate["blockers"]
    assert candidate["selection_eligible"] is False
    assert "eligible_evaluator_rows_by_cohort_sink" not in board
    assert "evaluator_rows_by_cohort" not in board
    assert review["outcome_aggregation_input_row_count"] == 0
    assert review["review_candidate_side_cell_count"] == 0
    assert review["top_side_cells"] == []


def test_same_side_cell_stable_cohort_ambiguity_blocks_strict_pooling() -> None:
    first = _eligible_cohort_rows(
        "ctx-ambiguous-cohort-a",
        stable_projection_overrides={"context_hashes": {"portfolio": "1" * 64}},
    )
    second = _eligible_cohort_rows(
        "ctx-ambiguous-cohort-b",
        stable_projection_overrides={"context_hashes": {"portfolio": "2" * 64}},
    )

    review = build_blocked_signal_outcome_review(
        [*second, *first],
        slippage_quantiles=_expected_cost_artifact(),
        now_utc=NOW,
    )
    board = review["learning_candidate_board"]

    assert len(board["candidate_rows"]) == 2
    assert len({row["stable_cohort_hash"] for row in board["candidate_rows"]}) == 2
    assert all(
        "SIDE_CELL_STABLE_COHORT_AMBIGUITY" in row["blockers"]
        and row["selection_eligible"] is False
        for row in board["candidate_rows"]
    )
    assert review["outcome_aggregation_input_row_count"] == 0
    assert review["blocked_signal_outcome_count"] == 0
    assert review["side_cell_count"] == 0
    assert review["review_candidate_side_cell_count"] == 0
    assert review["top_side_cells"] == []


def test_validator_reconstructs_required_side_cell_cohort_ambiguity() -> None:
    rows = [
        *_eligible_cohort_rows(
            "ctx-validator-ambiguity-a",
            stable_projection_overrides={"context_hashes": {"portfolio": "3" * 64}},
        ),
        *_eligible_cohort_rows(
            "ctx-validator-ambiguity-b",
            stable_projection_overrides={"context_hashes": {"portfolio": "4" * 64}},
        ),
    ]
    board = build_blocked_signal_outcome_review(
        rows, slippage_quantiles=_expected_cost_artifact(), now_utc=NOW
    )["learning_candidate_board"]

    assert validate_learning_candidate_board_v2(board) == board
    poisoned = copy.deepcopy(board)
    for row in poisoned["candidate_rows"]:
        row["blockers"].remove("SIDE_CELL_STABLE_COHORT_AMBIGUITY")
        row["selection_eligible"] = True
    _rehash_selection_and_board(poisoned)
    with pytest.raises(ValueError, match="candidate_ambiguity_blockers_invalid"):
        validate_learning_candidate_board_v2(poisoned)


def test_validator_rejects_extra_ambiguity_on_unique_or_base_blocked_row() -> None:
    eligible = build_blocked_signal_outcome_review(
        _eligible_cohort_rows("ctx-validator-unique"),
        slippage_quantiles=_expected_cost_artifact(),
        now_utc=NOW,
    )["learning_candidate_board"]
    base_blocked = _board([_qualified(context_id="ctx-validator-base-blocked")])

    for source in (eligible, base_blocked):
        poisoned = copy.deepcopy(source)
        row = poisoned["candidate_rows"][0]
        row["blockers"] = sorted({
            *row["blockers"], "SIDE_CELL_STABLE_COHORT_AMBIGUITY"
        })
        row["selection_eligible"] = False
        _rehash_selection_and_board(poisoned)
        with pytest.raises(ValueError, match="candidate_ambiguity_blockers_invalid"):
            validate_learning_candidate_board_v2(poisoned)


def test_retained_evaluation_semantics_are_stable_across_review_rollover() -> None:
    rows = _eligible_cohort_rows("ctx-retained-rollover")
    early = build_blocked_signal_outcome_review(
        rows,
        slippage_quantiles=_expected_cost_artifact(),
        now_utc=NOW,
    )
    late = build_blocked_signal_outcome_review(
        rows,
        slippage_quantiles=_expected_cost_artifact(),
        now_utc=NOW + dt.timedelta(days=1),
    )
    early_board = early["learning_candidate_board"]
    late_board = late["learning_candidate_board"]

    assert early_board["as_of_utc_date"] == "2026-07-10"
    assert late_board["as_of_utc_date"] == "2026-07-11"
    assert validate_learning_candidate_board_v2(early_board) == early_board
    assert validate_learning_candidate_board_v2(late_board) == late_board
    for field in (
        "qualified_lineage_outcome_row_count",
        "unqualified_lineage_outcome_row_count",
        "invalid_lineage_outcome_row_count",
        "lineage_exclusion_reason_counts",
        "candidate_rows",
        "selection_hash",
        "audit_hash",
    ):
        assert late_board[field] == early_board[field]
    assert late["outcome_aggregation_input_row_count"] == (
        early["outcome_aggregation_input_row_count"]
    ) == 30
    assert late["blocked_signal_outcome_count"] == (
        early["blocked_signal_outcome_count"]
    )
    assert late["review_candidate_side_cell_count"] == (
        early["review_candidate_side_cell_count"]
    )
    serialized_board = json.dumps(early_board, sort_keys=True)
    assert "eligible_evaluator_rows_by_cohort_sink" not in serialized_board
    assert rows[0]["attempt_id"] not in serialized_board

    future_evidence = copy.deepcopy(early_board)
    future_evidence["as_of_utc_date"] = "2026-07-09"
    _rehash_selection_and_board(future_evidence)
    with pytest.raises(ValueError, match="board_generation_precedes_evaluation"):
        validate_learning_candidate_board_v2(future_evidence)


def test_validator_binds_cost_window_to_recorded_evaluation_date() -> None:
    board = build_blocked_signal_outcome_review(
        _eligible_cohort_rows("ctx-validator-cost-date"),
        slippage_quantiles=_expected_cost_artifact(),
        now_utc=NOW + dt.timedelta(days=1),
    )["learning_candidate_board"]
    poisoned = copy.deepcopy(board)
    arbiter = poisoned["candidate_rows"][0]["arbiter_input"]
    arbiter["cost_evidence"]["source_asof_utc"] = "2026-07-11T18:00:00+00:00"
    arbiter["arbiter_input_hash"] = canonical_sha256({
        key: value for key, value in arbiter.items() if key != "arbiter_input_hash"
    })
    _rehash_selection_and_board(poisoned)

    with pytest.raises(ValueError, match="cost_evidence_semantics_invalid"):
        validate_learning_candidate_board_v2(poisoned)


def test_research_compatibility_preserves_lineage_partition_audit_counts() -> None:
    qualified = _qualified(context_id="ctx-research-audit-qualified")
    invalid = _qualified(context_id="ctx-research-audit-invalid")
    invalid["side_cell_key"] = "ma_crossover|BTCUSDT|Sell"
    unqualified = _qualified(context_id="ctx-research-audit-unqualified")
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
    ):
        unqualified["candidate_summary"].pop(field)

    review = build_research_compatibility_blocked_signal_outcome_review_no_authority(
        [qualified, invalid, unqualified],
        now_utc=NOW,
    )

    assert review["schema_version"] != (
        "cost_gate_demo_learning_lane_blocked_outcome_review_v6"
    )
    assert review["authority_eligible"] is False
    assert review["operator_review_eligible"] is False
    assert review["promotion_evidence"] is False
    audit = review["candidate_lineage_audit"]
    assert audit["source_schema_version"] == "cost_gate_learning_candidate_board_v2"
    assert audit["qualified_candidate_count"] == 1
    assert audit["invalid_lineage_count"] == 1
    assert audit["unqualified_lineage_count"] == 1


def test_research_compatibility_declares_outcome_row_units_and_aliases() -> None:
    qualified = [
        _qualified(context_id=f"ctx-research-row-unit-qualified-{index}")
        for index in range(2)
    ]
    invalid = [
        _qualified(context_id=f"ctx-research-row-unit-invalid-{index}")
        for index in range(3)
    ]
    for row in invalid:
        row["side_cell_key"] = "ma_crossover|BTCUSDT|Sell"
    unqualified = [
        _qualified(context_id=f"ctx-research-row-unit-unqualified-{index}")
        for index in range(4)
    ]
    for row in unqualified:
        for field in (
            "candidate_evaluation_context",
            "candidate_evaluation_context_status",
            "candidate_learning_context_projection",
        ):
            row["candidate_summary"].pop(field)

    review = build_research_compatibility_blocked_signal_outcome_review_no_authority(
        [*qualified, *invalid, *unqualified],
        now_utc=NOW,
    )
    audit = review["candidate_lineage_audit"]

    assert review["authority_eligible"] is False
    assert review["operator_review_eligible"] is False
    assert review["promotion_evidence"] is False
    assert audit["count_unit"] == "outcome_rows"
    assert audit["qualified_lineage_outcome_row_count"] == 2
    assert audit["invalid_lineage_outcome_row_count"] == 3
    assert audit["unqualified_lineage_outcome_row_count"] == 4
    assert audit["qualified_candidate_count"] == (
        audit["qualified_lineage_outcome_row_count"]
    )
    assert audit["invalid_lineage_count"] == (
        audit["invalid_lineage_outcome_row_count"]
    )
    assert audit["unqualified_lineage_count"] == (
        audit["unqualified_lineage_outcome_row_count"]
    )


def test_strict_review_top_level_is_invariant_to_positive_lineage_attacks() -> None:
    qualified = _qualified(context_id="ctx-strict-mixed-qualified")
    invalid = _qualified(context_id="ctx-strict-mixed-invalid")
    invalid["side_cell_key"] = "ma_crossover|BTCUSDT|Sell"
    invalid["realized_net_bps"] = 10_000.0
    unqualified = _qualified(context_id="ctx-strict-mixed-unqualified")
    unqualified["realized_net_bps"] = 10_000.0
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
    ):
        unqualified["candidate_summary"].pop(field)

    baseline = build_blocked_signal_outcome_review(
        [qualified],
        now_utc=NOW,
    )
    attacked = build_blocked_signal_outcome_review(
        [invalid, unqualified, qualified],
        now_utc=NOW,
    )

    for field in (
        "status",
        "reason",
        "next_trigger",
        "side_cell_count",
        "review_candidate_side_cell_count",
        "blocked_signal_outcome_count",
        "blocked_signal_effective_entry_count",
        "blocked_signal_positive_outcome_count",
        "avg_blocked_signal_outcome_net_bps",
        "top_side_cells",
    ):
        assert attacked[field] == baseline[field]
    assert attacked["outcome_aggregation_input_row_count"] == 0
    assert baseline["outcome_aggregation_input_row_count"] == 0
    baseline_board = baseline["learning_candidate_board"]
    attacked_board = attacked["learning_candidate_board"]
    assert attacked_board["invalid_lineage_outcome_row_count"] == 1
    assert attacked_board["unqualified_lineage_outcome_row_count"] == 1
    assert attacked_board["audit_hash"] != baseline_board["audit_hash"]
    assert attacked_board["board_hash"] != baseline_board["board_hash"]


def test_strict_review_reuses_board_duplicate_gate_for_same_event_conflict() -> None:
    qualified = _qualified(context_id="ctx-strict-same-event-conflict")
    conflicted = copy.deepcopy(qualified)
    conflicted["realized_net_bps"] = qualified["realized_net_bps"] + 500.0
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
    ):
        conflicted["candidate_summary"].pop(field)

    review = build_blocked_signal_outcome_review(
        [qualified, conflicted],
        now_utc=NOW,
    )

    assert review["outcome_aggregation_input_row_count"] == 0
    assert review["blocked_signal_outcome_count"] == 0
    assert review["top_side_cells"] == []
    board = review["learning_candidate_board"]
    assert board["qualified_lineage_outcome_row_count"] == 1
    assert board["unqualified_lineage_outcome_row_count"] == 1
    assert board["conflicting_duplicate_event_hash_row_count"] == 2
    assert board["candidate_rows"][0]["qualified_evaluator_input_count"] == 0
    assert validate_learning_candidate_board_v2(board) == board


def test_cli_main_enables_strict_lineage_policy_and_quarantines_positive_rows(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    ledger = tmp_path / "cli_strict_lineage.jsonl"
    ledger.write_text(
        json.dumps(
            _outcome(
                attempt_id="ctx-cli-strict-positive-unqualified",
                realized_net_bps=10_000.0,
            ),
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "outcome_review.py",
            "--ledger",
            str(ledger),
            "--print-json",
        ],
    )

    assert outcome_review_module.main() == 0
    review = json.loads(capsys.readouterr().out)

    assert review["require_qualified_lineage"] is True
    assert (
        review["outcome_aggregation_policy"]
        == "CANDIDATE_BOARD_QUALIFIED_EVALUATOR_ROWS"
    )
    assert review["outcome_aggregation_input_row_count"] == 0
    assert review["status"] == "NO_QUALIFIED_LINEAGE_BLOCKED_SIGNAL_OUTCOMES"
    assert review["review_candidate_side_cell_count"] == 0
    assert review["top_side_cells"] == []
