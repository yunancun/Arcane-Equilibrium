"""WP2-B B2.2a prospective candidate lineage propagation contract tests。

MODULE_NOTE:
  模塊用途：驗證 raw candidate_event_context 從 runtime event 經 ledger/outcome
    lossless 傳遞，並釘死 outer binding、materializer no-backfill 與 provenance。
  主要接口：runtime_adapter、reject_materializer、outcome_writer 的公開純函數。
  依賴：單一 Rust/Python 共用 candidate_event_context fixture；不讀目前狀態。
  硬邊界：純 source test，不觸 PG、Bybit、runtime、order、training 或 board schema。
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from cost_gate_learning_lane.candidate_evaluation_context import canonical_sha256
from cost_gate_learning_lane.contract import ADMIT_DECISION
from cost_gate_learning_lane.outcome_refresh import (
    OutcomeRefreshSelection,
    refresh_cost_gate_outcomes_from_price_rows,
)
from cost_gate_learning_lane.outcome_writer import (
    ProbeOutcomeConfig,
    build_blocked_signal_outcome_records,
)
from cost_gate_learning_lane.policy import DEMO_LEARNING_LANE_SCHEMA_VERSION
from cost_gate_learning_lane.reject_materializer import (
    RejectMaterializerConfig,
    build_materialized_reject_ledger_batch,
    fetch_cost_gate_reject_feature_rows,
    main as reject_materializer_main,
    pipeline_snapshot_recent_intents_to_feature_rows,
    reject_feature_row_to_event,
)
from cost_gate_learning_lane.runtime_adapter import (
    append_jsonl_ledger,
    build_ledger_record,
    evaluate_probe_admission,
    read_learning_ledger_partitions,
    read_jsonl_ledger,
)


def _candidate_context_reject_event() -> dict:
    fixture_path = (
        Path(__file__).resolve().parents[3]
        / "rust/openclaw_engine/tests/fixtures/candidate_event_context_v1/canonical_fixture.json"
    )
    context = json.loads(fixture_path.read_text(encoding="utf-8"))[
        "valid_candidate_event_context"
    ]
    return {
        "strategy_name": context["strategy_name"],
        "symbol": context["symbol"],
        "side": context["side"],
        "reject_reason_code": "cost_gate_js_demo_negative_edge",
        "engine_mode": context["evidence_engine_mode"],
        "ts_ms": context["captured_at_ms"],
        "context_id": context["context_id"],
        "signal_id": context["signal_id"],
        "candidate_event_context": context,
    }


def _event_now(event: dict) -> dt.datetime:
    return dt.datetime.fromtimestamp(event["ts_ms"] / 1000, tz=dt.timezone.utc)


def _minimal_valid_plan(event: dict) -> dict:
    key = "|".join(
        [event["strategy_name"], event["symbol"], event["side"]]
    )
    return {
        "schema_version": DEMO_LEARNING_LANE_SCHEMA_VERSION,
        "generated_at_utc": _event_now(event).isoformat(),
        "status": "READY_FOR_DEMO_LEARNING_PROBE",
        "gate_status": "READY",
        "main_cost_gate_adjustment": "NONE",
        "learning_gate_adjustment": "NONE",
        "order_authority": "NOT_GRANTED",
        "probe_candidates": [
            {
                "side_cell_key": key,
                "source_kind": "candidate_lineage_test",
                "probe_proposal": {
                    "mode": "demo_only_learning_probe",
                    "max_probe_orders": 1,
                    "cooldown_minutes": 30,
                    "outcome_horizon_minutes": 60,
                    "learning_outcome_horizon_minutes": 60,
                    "requires_runtime_policy_adapter": True,
                    "requires_probe_attempt_logging": True,
                    "requires_probe_outcome_logging": True,
                    "requires_candidate_horizon_outcome_logging": True,
                },
                "guardrails": {
                    "main_cost_gate_adjustment": "NONE",
                    "may_bypass_main_live_gate": False,
                    "demo_only": True,
                    "notional_or_qty_not_granted_by_artifact": True,
                },
            }
        ],
    }


def _capture_blocked_ledger_row() -> dict:
    event = _candidate_context_reject_event()
    decision = evaluate_probe_admission(
        _minimal_valid_plan(event),
        event,
        now_utc=_event_now(event),
        adapter_enabled=False,
    )
    row = json.loads(json.dumps(build_ledger_record(decision)))
    row["attempt_id"] = "blocked-capture-attempt"
    row["decision"] = "ADAPTER_DISABLED"
    row["allowed_to_submit_order"] = False
    row.pop("candidate_summary", None)
    context = row["event"]["candidate_event_context"]
    context["capture_status"] = "CAPTURE_BLOCKED"
    context["capture_blockers"] = ["BBO_MISSING_OR_INVALID"]
    context["market_inputs"]["best_bid"] = None
    context["event_hash"] = canonical_sha256(
        {key: value for key, value in context.items() if key != "event_hash"}
    )
    return row


@pytest.mark.parametrize(
    ("outer_field", "outer_value"),
    [
        ("strategy_name", "grid_trading"),
        ("symbol", "ETHUSDT"),
        ("side", "Sell"),
        ("context_id", "ctx-other-candidate"),
        ("signal_id", "sig-other-candidate"),
        ("engine_mode", "demo"),
        ("ts_ms", 1_783_700_000_001),
        ("ts_ms", None),
    ],
)
def test_runtime_adapter_rejects_grafted_or_timestamp_missing_candidate_context(
    outer_field: str,
    outer_value: object,
) -> None:
    event = _candidate_context_reject_event()
    if outer_value is None:
        event.pop(outer_field)
    else:
        event[outer_field] = outer_value

    with pytest.raises(
        ValueError,
        match="CANDIDATE_EVENT_CONTEXT_OUTER_BINDING_MISMATCH",
    ):
        evaluate_probe_admission(
            _minimal_valid_plan(_candidate_context_reject_event()),
            event,
            now_utc=_event_now(_candidate_context_reject_event()),
            adapter_enabled=False,
        )


def test_candidate_context_round_trips_into_blocked_outcome_without_enrichment(
    tmp_path: Path,
) -> None:
    event = _candidate_context_reject_event()
    expected_context = event["candidate_event_context"]
    decision = evaluate_probe_admission(
        _minimal_valid_plan(event),
        event,
        now_utc=_event_now(event),
        adapter_enabled=False,
    )

    assert decision["candidate_summary"]["candidate_event_context_status"] == "VALID"
    assert decision["candidate_summary"]["candidate_event_context"] == expected_context

    ledger_path = tmp_path / "candidate_context_ledger.jsonl"
    append_jsonl_ledger(ledger_path, build_ledger_record(decision))
    ledger = read_jsonl_ledger(ledger_path)
    assert ledger[0]["candidate_summary"]["candidate_event_context"] == expected_context

    event_ts_ms = expected_context["captured_at_ms"]
    outcomes = build_blocked_signal_outcome_records(
        ledger,
        [
            {"symbol": "BTCUSDT", "ts_ms": event_ts_ms, "close": 2_500.0},
            {
                "symbol": "BTCUSDT",
                "ts_ms": event_ts_ms + 60 * 60_000,
                "close": 2_510.0,
            },
        ],
        now_utc=dt.datetime.fromtimestamp(
            (event_ts_ms + 61 * 60_000) / 1000,
            tz=dt.timezone.utc,
        ),
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )

    assert len(outcomes) == 1
    summary = outcomes[0]["candidate_summary"]
    assert summary["candidate_event_context_status"] == "VALID"
    assert summary["candidate_event_context"] == expected_context
    assert summary["candidate_event_context"]["event_hash"] == expected_context["event_hash"]
    assert "candidate_evaluation_context" not in summary
    assert "candidate_learning_context_projection" not in summary


def test_outcome_refresh_quarantines_expected_capture_blocked_context(
    tmp_path: Path,
) -> None:
    complete_event = _candidate_context_reject_event()
    decision = evaluate_probe_admission(
        _minimal_valid_plan(complete_event),
        complete_event,
        now_utc=_event_now(complete_event),
        adapter_enabled=False,
    )
    complete_row = build_ledger_record(decision)
    blocked_row = _capture_blocked_ledger_row()

    ledger_path = tmp_path / "mixed-capture-ledger.jsonl"
    append_jsonl_ledger(ledger_path, complete_row)
    append_jsonl_ledger(ledger_path, blocked_row)
    event_ts_ms = complete_event["ts_ms"]
    price_rows = [
        {"symbol": "BTCUSDT", "ts_ms": event_ts_ms, "close": 2_500.0},
        {
            "symbol": "BTCUSDT",
            "ts_ms": event_ts_ms + 60 * 60_000,
            "close": 2_510.0,
        },
    ]
    now = dt.datetime.fromtimestamp(
        (event_ts_ms + 61 * 60_000) / 1000,
        tz=dt.timezone.utc,
    )

    batch = refresh_cost_gate_outcomes_from_price_rows(
        ledger_path,
        price_rows,
        now_utc=now,
        selection=OutcomeRefreshSelection(record_blocked_outcomes=True),
        outcome_cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
        append_ledger=True,
    )

    assert batch["blocked_signal_outcome_count"] == 1
    assert batch["outcomes"][0]["attempt_id"] == complete_row["attempt_id"]
    assert batch["outcomes"][0]["event"] == complete_row["event"]
    rerun = refresh_cost_gate_outcomes_from_price_rows(
        ledger_path,
        price_rows,
        now_utc=now,
        selection=OutcomeRefreshSelection(record_blocked_outcomes=True),
        outcome_cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
        append_ledger=False,
    )
    assert rerun["outcome_count"] == 0


def test_partitioned_reader_keeps_capture_blocked_only_for_dedup(
    tmp_path: Path,
) -> None:
    path = tmp_path / "capture-blocked.jsonl"
    blocked_row = _capture_blocked_ledger_row()
    existing_outcome = {
        "record_type": "blocked_signal_outcome",
        "attempt_id": "existing-outcome",
    }
    existing_fill = {
        "record_type": "probe_fill",
        "attempt_id": "existing-fill",
        "fill_id": "fill-1",
    }
    append_jsonl_ledger(path, blocked_row)
    append_jsonl_ledger(path, existing_outcome)
    append_jsonl_ledger(path, existing_fill)

    with pytest.raises(ValueError, match="EVENT_CONTEXT_CAPTURE_INCOMPLETE"):
        read_jsonl_ledger(path)
    partitions = read_learning_ledger_partitions(path)

    assert partitions.outcome_rows == [existing_outcome, existing_fill]
    assert partitions.dedup_rows == [blocked_row, existing_outcome, existing_fill]
    assert partitions.quarantined_capture_blocked_rows == [blocked_row]
    batch = build_materialized_reject_ledger_batch(
        _minimal_valid_plan(_candidate_context_reject_event()),
        [
            {
                **_candidate_context_reject_event(),
                "_materializer_source": "explicit_source_rows",
            }
        ],
        existing_ledger_rows=partitions.outcome_rows,
        dedup_ledger_rows=partitions.dedup_rows,
        now_utc=_event_now(blocked_row["event"]),
    )
    assert batch["materialized_record_count"] == 0
    assert batch["skipped_existing_event_key_count"] == 1


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("unknown_blocker", "CAPTURE_BLOCKED_BLOCKERS_NOT_ALLOWED"),
        ("empty_blockers", "CAPTURE_BLOCKED_BLOCKERS_NOT_ALLOWED"),
        ("admit", "CAPTURE_BLOCKED_ADMIT_CONTRADICTION"),
        ("hash", "EVENT_CONTEXT_HASH_MISMATCH"),
        ("schema", "EVENT_CONTEXT_SCHEMA_INVALID"),
        ("outer_binding", "CANDIDATE_EVENT_CONTEXT_OUTER_BINDING_MISMATCH"),
        ("summary_conflict", "CANDIDATE_EVENT_CONTEXT_SUMMARY_CONFLICT"),
        ("invalid_complete", "EVENT_CONTEXT_CAPTURE_BLOCKED"),
    ],
)
def test_partitioned_reader_keeps_noneligible_context_fail_closed(
    tmp_path: Path,
    mutation: str,
    error: str,
) -> None:
    row = _capture_blocked_ledger_row()
    context = row["event"]["candidate_event_context"]
    if mutation == "unknown_blocker":
        context["capture_blockers"] = ["BBO_CROSSED"]
    elif mutation == "empty_blockers":
        context["capture_blockers"] = []
    elif mutation == "admit":
        row["decision"] = ADMIT_DECISION
    elif mutation == "hash":
        context["event_hash"] = "0" * 64
    elif mutation == "schema":
        context["schema_version"] = "candidate_event_context_v2"
    elif mutation == "outer_binding":
        row["event"]["symbol"] = "ETHUSDT"
    elif mutation == "summary_conflict":
        row["candidate_summary"] = {
            "candidate_event_context_status": "VALID",
        }
    else:
        context["capture_status"] = "CAPTURE_COMPLETE"
    if mutation in {"unknown_blocker", "empty_blockers", "schema", "invalid_complete"}:
        context["event_hash"] = canonical_sha256(
            {key: value for key, value in context.items() if key != "event_hash"}
        )
    path = tmp_path / f"{mutation}.jsonl"
    append_jsonl_ledger(path, row)

    with pytest.raises(ValueError, match=error):
        read_learning_ledger_partitions(path)


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("empty_strategy", "STRATEGY_NAME_INVALID"),
        ("invalid_strategy_sha", "STRATEGY_VERSION_INVALID"),
        ("zero_captured_at", "CAPTURED_AT_INVALID"),
        ("lowercase_symbol", "SYMBOL_INVALID"),
        ("invalid_side", "SIDE_INVALID"),
    ],
)
def test_partitioned_reader_rejects_invalid_non_bbo_capture_semantics(
    tmp_path: Path,
    mutation: str,
    error: str,
) -> None:
    row = _capture_blocked_ledger_row()
    event = row["event"]
    context = event["candidate_event_context"]
    if mutation == "empty_strategy":
        event["strategy_name"] = ""
        context["strategy_name"] = ""
    elif mutation == "invalid_strategy_sha":
        context["strategy_version"] = "invalid"
        context["build_git_sha"] = "invalid"
    elif mutation == "zero_captured_at":
        event["ts_ms"] = 0
        context["captured_at_ms"] = 0
    elif mutation == "lowercase_symbol":
        event["symbol"] = "btcusdt"
        context["symbol"] = "btcusdt"
    else:
        event["side"] = "Long"
        context["side"] = "Long"
    context["event_hash"] = canonical_sha256(
        {key: value for key, value in context.items() if key != "event_hash"}
    )
    path = tmp_path / f"invalid-{mutation}.jsonl"
    append_jsonl_ledger(path, row)

    with pytest.raises(ValueError, match=error):
        read_learning_ledger_partitions(path)


def test_partitioned_reader_rejects_malformed_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "malformed.jsonl"
    path.write_text('{"record_type":', encoding="utf-8")

    with pytest.raises(ValueError, match="malformed JSONL ledger"):
        read_learning_ledger_partitions(path)


def test_legacy_contextless_event_keeps_original_ledger_shape(tmp_path: Path) -> None:
    event = _candidate_context_reject_event()
    event.pop("candidate_event_context")
    decision = evaluate_probe_admission(
        _minimal_valid_plan(event),
        event,
        now_utc=_event_now(event),
        adapter_enabled=False,
    )
    path = tmp_path / "legacy_contextless.jsonl"
    append_jsonl_ledger(path, build_ledger_record(decision))

    row = read_jsonl_ledger(path)[0]

    assert "candidate_event_context" not in row["event"]
    assert "candidate_event_context" not in row["candidate_summary"]
    assert "candidate_event_context_status" not in row["candidate_summary"]


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("summary_conflict", "CANDIDATE_EVENT_CONTEXT_SUMMARY_CONFLICT"),
        ("invalid_event_hash", "EVENT_CONTEXT_HASH_MISMATCH"),
    ],
)
def test_build_ledger_record_defensively_rejects_invalid_or_conflicting_context(
    mutation: str,
    error: str,
) -> None:
    event = _candidate_context_reject_event()
    decision = evaluate_probe_admission(
        _minimal_valid_plan(event),
        event,
        now_utc=_event_now(event),
        adapter_enabled=False,
    )
    decision = json.loads(json.dumps(decision))
    if mutation == "summary_conflict":
        decision["candidate_summary"]["candidate_event_context"] = {
            "event_hash": "0" * 64,
        }
    else:
        decision["event"]["candidate_event_context"]["event_hash"] = "0" * 64

    with pytest.raises(ValueError, match=error):
        build_ledger_record(decision)


def test_reject_materializer_preserves_valid_explicit_source_context_and_provenance():
    event = _candidate_context_reject_event()
    context = event["candidate_event_context"]
    batch = build_materialized_reject_ledger_batch(
        _minimal_valid_plan(event),
        [{**event, "_materializer_source": "explicit_source_rows"}],
        now_utc=_event_now(event),
    )

    assert batch["materialized_record_count"] == 1
    record = batch["records"][0]
    assert record["source"] == "materialized_from_explicit_source_rows"
    assert record["source_schema"] == "explicit_source_rows"
    assert record["event"]["candidate_event_context"] == context
    assert record["candidate_summary"]["candidate_event_context_status"] == "VALID"
    assert record["candidate_summary"]["candidate_event_context"] == context
    assert "candidate_evaluation_context" not in record["candidate_summary"]
    assert "candidate_learning_context_projection" not in record["candidate_summary"]


@pytest.mark.parametrize(
    "source_marker",
    [
        "pg_decision_features",
        "pipeline_snapshot_recent_intents",
        None,
    ],
)
def test_reject_materializer_rejects_context_from_non_explicit_source(
    source_marker: str | None,
) -> None:
    row = _candidate_context_reject_event()
    if source_marker is not None:
        row["_materializer_source"] = source_marker

    with pytest.raises(
        ValueError,
        match="CANDIDATE_EVENT_CONTEXT_SOURCE_NOT_EXPLICIT",
    ):
        reject_feature_row_to_event(row)


def test_reject_materializer_pg_rows_remain_contextless_and_unqualified():
    event = _candidate_context_reject_event()
    feature_row = {
        key: value
        for key, value in event.items()
        if key not in {"candidate_event_context", "signal_id"}
    }
    feature_row["_materializer_source"] = "pg_decision_features"
    batch = build_materialized_reject_ledger_batch(
        _minimal_valid_plan(event),
        [feature_row],
        now_utc=_event_now(event),
    )

    record = batch["records"][0]
    summary = record["candidate_summary"]
    assert record["source"] == "materialized_from_pg_decision_features"
    assert record["source_schema"] == "learning.decision_features"
    assert summary["candidate_event_context_status"] == "UNQUALIFIED_CONTEXT_MISSING"
    assert "candidate_event_context" not in summary
    assert "candidate_evaluation_context" not in summary
    assert "candidate_learning_context_projection" not in summary

    event_ts_ms = event["ts_ms"]
    outcomes = build_blocked_signal_outcome_records(
        [record],
        [
            {"symbol": event["symbol"], "ts_ms": event_ts_ms, "close": 2_500.0},
            {
                "symbol": event["symbol"],
                "ts_ms": event_ts_ms + 60 * 60_000,
                "close": 2_510.0,
            },
        ],
        now_utc=dt.datetime.fromtimestamp(
            (event_ts_ms + 61 * 60_000) / 1000,
            tz=dt.timezone.utc,
        ),
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )
    assert (
        outcomes[0]["candidate_summary"]["candidate_event_context_status"]
        == "UNQUALIFIED_CONTEXT_MISSING"
    )


def test_reject_materializer_snapshot_rows_never_fabricate_context():
    event = _candidate_context_reject_event()
    rows = pipeline_snapshot_recent_intents_to_feature_rows(
        {
            "trading_mode": event["engine_mode"],
            "recent_intents": [
                {
                    "timestamp_ms": event["ts_ms"],
                    "result": "rejected:cost_gate(JS-demo): estimated=-2.0bps < 0",
                    "intent": {
                        "strategy": event["strategy_name"],
                        "symbol": event["symbol"],
                        "is_long": True,
                        "limit_price": 2_500.0,
                    },
                }
            ],
        },
        engine_modes=(event["engine_mode"],),
        snapshot_path=Path("/tmp/openclaw/pipeline_snapshot.json"),
    )
    batch = build_materialized_reject_ledger_batch(
        _minimal_valid_plan(event),
        rows,
        now_utc=_event_now(event),
    )

    record = batch["records"][0]
    summary = record["candidate_summary"]
    assert record["source"] == "materialized_from_pipeline_snapshot_recent_intents"
    assert record["source_schema"] == "pipeline_snapshot.recent_intents"
    assert summary["candidate_event_context_status"] == "UNQUALIFIED_CONTEXT_MISSING"
    assert "candidate_event_context" not in summary
    assert "candidate_evaluation_context" not in summary
    assert "candidate_learning_context_projection" not in summary


@pytest.mark.parametrize(
    "mutation",
    [
        "outer_symbol_graft",
        "missing_ts_ms",
        "lowercase_symbol",
        "float_ts_ms",
        "lowercase_side",
        "uppercase_engine_mode",
    ],
)
def test_reject_materializer_rejects_explicit_source_context_mismatch(
    mutation: str,
) -> None:
    event = _candidate_context_reject_event()
    event["_materializer_source"] = "explicit_source_rows"
    if mutation == "outer_symbol_graft":
        event["symbol"] = "ETHUSDT"
    elif mutation == "missing_ts_ms":
        event.pop("ts_ms")
    elif mutation == "lowercase_symbol":
        event["symbol"] = str(event["symbol"]).lower()
    elif mutation == "float_ts_ms":
        event["ts_ms"] = float(event["ts_ms"])
    elif mutation == "lowercase_side":
        event["side"] = str(event["side"]).lower()
    else:
        event["engine_mode"] = str(event["engine_mode"]).upper()

    with pytest.raises(
        ValueError,
        match="CANDIDATE_EVENT_CONTEXT_OUTER_BINDING_MISMATCH",
    ):
        reject_feature_row_to_event(event)


def test_reject_materializer_cli_source_rows_uses_explicit_provenance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    event = _candidate_context_reject_event()
    plan_path = tmp_path / "plan.json"
    source_path = tmp_path / "source_rows.json"
    ledger_path = tmp_path / "ledger.jsonl"
    output_path = tmp_path / "materialized.json"
    plan_path.write_text(json.dumps(_minimal_valid_plan(event)), encoding="utf-8")
    source_path.write_text(
        json.dumps(
            [
                {
                    "ts_ms": event["ts_ms"],
                    "context_id": "ctx-explicit-source-row",
                    "engine_mode": event["engine_mode"],
                    "strategy_name": event["strategy_name"],
                    "symbol": event["symbol"],
                    "side": event["side"],
                    "reject_reason_code": event["reject_reason_code"],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "reject_materializer.py",
            "--plan",
            str(plan_path),
            "--ledger",
            str(ledger_path),
            "--source-rows",
            str(source_path),
            "--output",
            str(output_path),
        ],
    )

    assert reject_materializer_main() == 0
    record = json.loads(output_path.read_text(encoding="utf-8"))["records"][0]
    assert record["source"] == "materialized_from_explicit_source_rows"
    assert record["source_schema"] == "explicit_source_rows"
    assert (
        record["candidate_summary"]["candidate_event_context_status"]
        == "UNQUALIFIED_CONTEXT_MISSING"
    )


def test_reject_materializer_pg_fetch_rows_carry_explicit_source_marker():
    class FakeCursor:
        description = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _sql, _params):
            return None

        def fetchall(self):
            return [
                {
                    "ts_ms": 1_782_037_200_000,
                    "context_id": "ctx-pg-marker",
                    "engine_mode": "live_demo",
                    "strategy_name": "ma_crossover",
                    "symbol": "ETHUSDT",
                    "side": "Sell",
                    "reject_reason_code": "cost_gate_js_demo_negative_edge",
                }
            ]

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    rows = fetch_cost_gate_reject_feature_rows(
        FakeConnection(),
        RejectMaterializerConfig(),
    )

    assert rows[0]["_materializer_source"] == "pg_decision_features"
