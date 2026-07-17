from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

import cost_gate_learning_lane.bounded_probe_execution_realism_review as realism_review_module
import cost_gate_learning_lane.runtime_adapter as runtime_adapter_module
from cost_gate_learning_lane import ledger_rotation

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
from cost_gate_learning_lane.ledger_rotation import maybe_rotate_ledger
from cost_gate_learning_lane.runtime_adapter import (
    append_jsonl_ledger,
)
from tests.test_candidate_lineage_propagation import _capture_blocked_ledger_row


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
        row.update(
            {
                "order_link_id": f"oc_dm_{prefix}_{i}",
                "order_id": f"bybit-{prefix}-{i}",
                "exec_id": f"exec-{prefix}-{i}",
                "fill_id": f"fill-{prefix}-{i}",
                "intent_id": f"intent-{prefix}-{i}",
                "risk_verdict": "APPROVED_BY_BOUNDED_DEMO_PROBE",
                "fee_bps": 2.0,
                "slippage_bps": max(cost_bps - 2.0, 0.0),
                "close_state": "CLOSED_AT_HORIZON",
                "source_artifact_path": f"artifacts/probe/{prefix}-{i}.json",
            }
        )
    return row


def _result_review(ledger_rows: list[dict]) -> dict:
    return build_bounded_demo_probe_result_review(
        preflight=_preflight(),
        ledger_rows=ledger_rows,
        now_utc=NOW,
    )


def _complete_result_review(ledger_rows: list[dict]) -> dict:
    result = _result_review(ledger_rows)
    result["ledger_observation"] = {
        "schema_version": "bounded_demo_probe_result_review_ledger_observation_v1",
        "status": "COMPLETE",
        "reason": "retained_ledger_generation_scanned_to_eof",
        "scan_performed": True,
        "retained_ledger_scan_complete": True,
        "target_scope_counts_known": True,
        "stale_snapshot_reused": False,
        "truncated": False,
    }
    return result


def _execution_gap_rows() -> list[dict]:
    return [
        _outcome(
            PROBE_OUTCOME_RECORD_TYPE,
            i,
            net_bps=2.0,
            gross_bps=6.0,
            cost_bps=4.0,
        )
        for i in range(1, 4)
    ] + [
        _outcome(
            BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
            i,
            net_bps=4.0,
            gross_bps=8.0,
            cost_bps=4.0,
        )
        for i in range(1, 4)
    ]


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


def _run_realism_review_cli(
    *,
    monkeypatch,
    result_review_path: Path,
    ledger_path: Path,
    output_path: Path,
) -> dict:
    markdown_path = output_path.with_suffix(".md")
    monkeypatch.setattr(
        "sys.argv",
        [
            "bounded_probe_execution_realism_review.py",
            "--result-review-json",
            str(result_review_path),
            "--ledger",
            str(ledger_path),
            "--output",
            str(markdown_path),
            "--json-output",
            str(output_path),
        ],
    )
    monkeypatch.setattr(realism_review_module, "_utc_now", lambda: NOW)
    assert realism_review_module.main() == 0
    return json.loads(output_path.read_text(encoding="utf-8"))


def test_execution_realism_cli_skips_ledger_when_result_precondition_is_unusable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result_review = _result_review([])
    result_review["ledger_observation"] = {
        "schema_version": "bounded_demo_probe_result_review_ledger_observation_v1",
        "status": "SKIPPED_PRECONDITION",
        "scan_performed": False,
        "retained_ledger_scan_complete": False,
        "target_scope_counts_known": False,
        "stale_snapshot_reused": False,
        "truncated": False,
    }
    result_review_path = tmp_path / "result-review.json"
    result_review_path.write_text(json.dumps(result_review), encoding="utf-8")

    def _unexpected_ledger_scan(*_args, **_kwargs):
        raise AssertionError("unsupported result review must not scan the ledger")

    monkeypatch.setattr(
        runtime_adapter_module,
        "scan_retained_jsonl",
        _unexpected_ledger_scan,
    )
    monkeypatch.setattr(
        realism_review_module,
        "scan_retained_jsonl",
        _unexpected_ledger_scan,
        raising=False,
    )

    packet = _run_realism_review_cli(
        monkeypatch=monkeypatch,
        result_review_path=result_review_path,
        ledger_path=tmp_path / "does-not-exist.jsonl",
        output_path=tmp_path / "review.json",
    )

    assert packet["status"] == "SKIPPED_PRECONDITION"
    assert packet["ledger_observation"]["status"] == "SKIPPED_PRECONDITION"
    assert packet["ledger_observation"]["scan_performed"] is False
    assert packet["ledger_observation"]["target_scope_counts_known"] is False
    assert packet["ledger_observation"]["stale_snapshot_reused"] is False
    assert packet["ledger_observation"]["truncated"] is False
    assert packet["probe_execution_summary"]["count"] is None
    assert packet["matched_control_execution_summary"]["count"] is None
    assert packet["gap_decomposition"]["net_capture_gap_bps"] is None
    assert packet["execution_gap_hypotheses"] is None
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["promotion_evidence"] is False


def test_execution_realism_cli_ignores_exact_capture_blocked_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    outcome_rows = [
        _outcome(
            PROBE_OUTCOME_RECORD_TYPE,
            i,
            net_bps=float(i),
            gross_bps=float(i + 4),
            cost_bps=4.0,
        )
        for i in range(1, 4)
    ] + [
        _outcome(
            BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
            i,
            net_bps=3.0,
            gross_bps=7.0,
            cost_bps=4.0,
        )
        for i in range(1, 4)
    ]
    result_review_path = tmp_path / "result-review.json"
    result_review_path.write_text(
        json.dumps(_complete_result_review(outcome_rows), ensure_ascii=False),
        encoding="utf-8",
    )
    outcome_only_ledger = tmp_path / "outcome-only.jsonl"
    mixed_ledger = tmp_path / "mixed.jsonl"
    for row in outcome_rows:
        append_jsonl_ledger(outcome_only_ledger, row)
        append_jsonl_ledger(mixed_ledger, row)
    append_jsonl_ledger(mixed_ledger, _capture_blocked_ledger_row())

    outcome_only = _run_realism_review_cli(
        monkeypatch=monkeypatch,
        result_review_path=result_review_path,
        ledger_path=outcome_only_ledger,
        output_path=tmp_path / "outcome-only.json",
    )
    mixed = _run_realism_review_cli(
        monkeypatch=monkeypatch,
        result_review_path=result_review_path,
        ledger_path=mixed_ledger,
        output_path=tmp_path / "mixed.json",
    )

    assert mixed == outcome_only


def test_execution_realism_cli_retains_only_exact_target_rows_from_large_stream(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_rows = [
        _outcome(
            PROBE_OUTCOME_RECORD_TYPE,
            i,
            net_bps=float(i),
            gross_bps=float(i + 4),
            cost_bps=4.0,
        )
        for i in range(1, 4)
    ] + [
        _outcome(
            BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
            i,
            net_bps=3.0,
            gross_bps=7.0,
            cost_bps=4.0,
        )
        for i in range(1, 4)
    ]
    result_review_path = tmp_path / "result-review.json"
    result_review_path.write_text(
        json.dumps(_complete_result_review(target_rows), ensure_ascii=False),
        encoding="utf-8",
    )
    ledger_path = tmp_path / "ledger.jsonl"
    for row in target_rows[:3]:
        append_jsonl_ledger(ledger_path, row)
    for index in range(1_000):
        irrelevant = _outcome(
            PROBE_OUTCOME_RECORD_TYPE,
            index + 10,
            net_bps=50.0,
            gross_bps=54.0,
            cost_bps=4.0,
        )
        irrelevant["side_cell_key"] = f"irrelevant|SYMBOL{index}|Buy"
        append_jsonl_ledger(ledger_path, irrelevant)
    wrong_horizon_probe = _outcome(
        PROBE_OUTCOME_RECORD_TYPE,
        99,
        net_bps=100.0,
        gross_bps=104.0,
        cost_bps=4.0,
    )
    wrong_horizon_probe["horizon_minutes"] = 60
    wrong_horizon_control = _outcome(
        BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
        99,
        net_bps=100.0,
        gross_bps=104.0,
        cost_bps=4.0,
    )
    wrong_horizon_control["horizon_minutes"] = 60
    append_jsonl_ledger(ledger_path, wrong_horizon_probe)
    append_jsonl_ledger(ledger_path, wrong_horizon_control)
    append_jsonl_ledger(
        ledger_path,
        {
            "record_type": "probe_fill",
            "attempt_id": "target-fill-not-an-execution-review-input",
            "side_cell_key": SIDE_CELL,
        },
    )
    for _ in range(100):
        for row in target_rows:
            append_jsonl_ledger(ledger_path, row)
    for row in target_rows[3:]:
        append_jsonl_ledger(ledger_path, row)

    observed: dict[str, object] = {}
    original_builder = realism_review_module.build_bounded_probe_execution_realism_review

    def _spy_builder(*, result_review, ledger_rows, now_utc=None):
        observed["ledger_rows"] = ledger_rows
        return original_builder(
            result_review=result_review,
            ledger_rows=ledger_rows,
            now_utc=now_utc,
        )

    monkeypatch.setattr(
        realism_review_module,
        "build_bounded_probe_execution_realism_review",
        _spy_builder,
    )

    packet = _run_realism_review_cli(
        monkeypatch=monkeypatch,
        result_review_path=result_review_path,
        ledger_path=ledger_path,
        output_path=tmp_path / "review.json",
    )

    assert observed["ledger_rows"] == target_rows
    assert packet["status"] == "EXECUTION_REALISM_GAP_DIAGNOSED_REPAIR_REQUIRED"
    assert packet["probe_execution_summary"]["count"] == 3
    assert packet["matched_control_execution_summary"]["count"] == 3


@pytest.mark.parametrize(
    "row_side_cell_key",
    [SIDE_CELL, "irrelevant|ETHUSDT|Buy"],
    ids=["target-row", "irrelevant-row"],
)
def test_execution_realism_cli_strictly_rejects_authority_sensitive_invalid_rows(
    tmp_path: Path,
    monkeypatch,
    row_side_cell_key: str,
) -> None:
    result_review_path = tmp_path / "result-review.json"
    result_review_path.write_text(
        json.dumps(_complete_result_review(_execution_gap_rows())),
        encoding="utf-8",
    )
    ledger_path = tmp_path / "ledger.jsonl"
    invalid = _capture_blocked_ledger_row()
    invalid["side_cell_key"] = row_side_cell_key
    invalid["event"]["candidate_event_context"]["event_hash"] = "0" * 64
    append_jsonl_ledger(ledger_path, invalid)

    with pytest.raises(ValueError, match="EVENT_CONTEXT_HASH_MISMATCH"):
        _run_realism_review_cli(
            monkeypatch=monkeypatch,
            result_review_path=result_review_path,
            ledger_path=ledger_path,
            output_path=tmp_path / "review.json",
        )


def test_execution_realism_cli_rejects_malformed_irrelevant_row_without_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result_review_path = tmp_path / "result-review.json"
    result_review_path.write_text(
        json.dumps(_complete_result_review(_execution_gap_rows())),
        encoding="utf-8",
    )
    ledger_path = tmp_path / "ledger.jsonl"
    append_jsonl_ledger(ledger_path, _execution_gap_rows()[0])
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write('{"side_cell_key":"irrelevant|ETHUSDT|Buy",\n')
    output_path = tmp_path / "review.json"

    with pytest.raises(ValueError, match="RETAINED_LEDGER_MALFORMED_JSON"):
        _run_realism_review_cli(
            monkeypatch=monkeypatch,
            result_review_path=result_review_path,
            ledger_path=ledger_path,
            output_path=output_path,
        )
    assert not output_path.exists()


def test_execution_realism_cli_spans_rotation_and_keeps_latest_duplicate_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(ledger_rotation, "_utc_now", lambda: NOW)
    final_rows = _execution_gap_rows()
    result_review_path = tmp_path / "result-review.json"
    result_review_path.write_text(
        json.dumps(_complete_result_review(final_rows)),
        encoding="utf-8",
    )
    ledger_path = tmp_path / "probe_ledger.jsonl"
    old_rows = [
        {**row, "realized_net_bps": 20.0, "gross_bps": 24.0}
        if row["record_type"] == PROBE_OUTCOME_RECORD_TYPE
        else {**row, "realized_net_bps": 1.0, "gross_bps": 5.0}
        for row in final_rows
    ]
    for row in old_rows:
        append_jsonl_ledger(ledger_path, row)
    rotation = maybe_rotate_ledger(
        ledger_path,
        threshold_bytes=1,
        now_utc=NOW - dt.timedelta(minutes=1),
    )
    assert rotation["rotated"] is True
    for row in final_rows:
        append_jsonl_ledger(ledger_path, row)

    observed: dict[str, object] = {}
    original_builder = realism_review_module.build_bounded_probe_execution_realism_review

    def _spy_builder(*, result_review, ledger_rows, now_utc=None):
        observed["ledger_rows"] = ledger_rows
        return original_builder(
            result_review=result_review,
            ledger_rows=ledger_rows,
            now_utc=now_utc,
        )

    monkeypatch.setattr(
        realism_review_module,
        "build_bounded_probe_execution_realism_review",
        _spy_builder,
    )
    packet = _run_realism_review_cli(
        monkeypatch=monkeypatch,
        result_review_path=result_review_path,
        ledger_path=ledger_path,
        output_path=tmp_path / "review.json",
    )

    assert len(observed["ledger_rows"]) == 6
    assert packet["ledger_observation"]["status"] == "COMPLETE"
    assert packet["probe_execution_summary"]["avg_net_bps"] == 2.0
    assert packet["matched_control_execution_summary"]["avg_net_bps"] == 4.0
    assert packet["gap_decomposition"]["net_capture_gap_bps"] == 2.0


@pytest.mark.parametrize(
    ("limit_kind", "expected_code"),
    [
        (
            "unique-entries",
            "EXECUTION_REALISM_PROJECTED_UNIQUE_ENTRIES_EXCEEDED",
        ),
        ("json-bytes", "EXECUTION_REALISM_PROJECTED_JSON_BYTES_EXCEEDED"),
    ],
)
def test_execution_realism_projection_limits_emit_rc0_noncomplete_unknown_artifact(
    tmp_path: Path,
    monkeypatch,
    limit_kind: str,
    expected_code: str,
) -> None:
    result_review_path = tmp_path / "result-review.json"
    result_review_path.write_text(
        json.dumps(_complete_result_review(_execution_gap_rows())),
        encoding="utf-8",
    )
    ledger_path = tmp_path / "ledger.jsonl"
    if limit_kind == "unique-entries":
        monkeypatch.setattr(
            realism_review_module,
            "MAX_EXECUTION_REALISM_PROJECTED_UNIQUE_ENTRIES",
            1,
            raising=False,
        )
        monkeypatch.setattr(
            realism_review_module,
            "MAX_EXECUTION_REALISM_PROJECTED_JSON_BYTES",
            1_000_000,
            raising=False,
        )
        append_jsonl_ledger(ledger_path, _execution_gap_rows()[0])
        append_jsonl_ledger(ledger_path, _execution_gap_rows()[1])
    else:
        monkeypatch.setattr(
            realism_review_module,
            "MAX_EXECUTION_REALISM_PROJECTED_UNIQUE_ENTRIES",
            100,
            raising=False,
        )
        monkeypatch.setattr(
            realism_review_module,
            "MAX_EXECUTION_REALISM_PROJECTED_JSON_BYTES",
            128,
            raising=False,
        )
        oversized = {
            **_execution_gap_rows()[0],
            "oversized_target_payload": "x" * 4_096,
        }
        append_jsonl_ledger(ledger_path, oversized)

    observed: dict[str, object] = {}
    original_builder = realism_review_module.build_bounded_probe_execution_realism_review

    def _spy_builder(*, result_review, ledger_rows, now_utc=None):
        observed["ledger_rows"] = ledger_rows
        return original_builder(
            result_review=result_review,
            ledger_rows=ledger_rows,
            now_utc=now_utc,
        )

    monkeypatch.setattr(
        realism_review_module,
        "build_bounded_probe_execution_realism_review",
        _spy_builder,
    )
    packet = _run_realism_review_cli(
        monkeypatch=monkeypatch,
        result_review_path=result_review_path,
        ledger_path=ledger_path,
        output_path=tmp_path / "review.json",
    )

    assert observed["ledger_rows"] == []
    assert packet["status"] == "PROJECTION_LIMIT_EXCEEDED"
    assert packet["ledger_observation"]["status"] == "PROJECTION_LIMIT_EXCEEDED"
    assert packet["ledger_observation"]["projection_limit_code"] == expected_code
    assert packet["ledger_observation"]["scan_performed"] is True
    assert packet["ledger_observation"]["retained_ledger_scan_complete"] is False
    assert packet["ledger_observation"]["target_scope_counts_known"] is False
    assert packet["ledger_observation"]["truncated"] is True
    assert packet["ledger_observation"]["stale_snapshot_reused"] is False
    assert packet["probe_execution_summary"]["count"] is None
    assert packet["matched_control_execution_summary"]["count"] is None
    assert packet["gap_decomposition"]["net_capture_gap_bps"] is None
    assert packet["execution_gap_hypotheses"] is None
    assert packet["answers"]["cost_gate_or_operator_review_allowed"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["promotion_evidence"] is False
