"""Prospective cold-evaluation producer and pre-append fence tests."""

from __future__ import annotations

import copy
import datetime as dt

import pytest

import cost_gate_learning_lane.outcome_refresh as outcome_refresh_module
from helper_scripts.research.tests.candidate_lineage_v2_test_support import (
    build_candidate_event_context_v1,
)
from cost_gate_learning_lane.candidate_board_validation import (
    validate_learning_candidate_board_v2,
)
from cost_gate_learning_lane.candidate_evaluation_context import (
    REGIME_BUCKETS,
    attach_candidate_evaluation_context,
    build_candidate_evaluation_context,
    canonical_sha256,
)
from cost_gate_learning_lane.candidate_evaluation_producer import (
    ATTACHED,
    DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE,
    NOT_APPLICABLE,
    attach_candidate_evaluation_to_outcome,
    partition_candidate_evaluation_outcomes,
)
from cost_gate_learning_lane.outcome_refresh import (
    OutcomeRefreshSelection,
    append_refresh_outcomes_to_ledger,
    refresh_cost_gate_outcomes_from_price_rows,
)
from cost_gate_learning_lane.outcome_review import (
    build_blocked_signal_outcome_review,
)
from cost_gate_learning_lane.outcome_writer import (
    ProbeOutcomeConfig,
    build_blocked_signal_outcome_records,
)
from cost_gate_learning_lane.policy import DEMO_LEARNING_LANE_SCHEMA_VERSION
from cost_gate_learning_lane.runtime_adapter import (
    append_jsonl_ledger,
    build_ledger_record,
    evaluate_probe_admission,
    read_jsonl_ledger,
)


def _raw_valid_reject_event(
    context_id: str = "ctx-cold-evaluation-producer-001",
    captured_at_utc: dt.datetime | None = None,
) -> dict:
    captured_at_utc = captured_at_utc or dt.datetime(
        2026, 7, 9, 12, tzinfo=dt.timezone.utc
    )
    context = build_candidate_event_context_v1(
        context_id=context_id,
        captured_at_ms=int(captured_at_utc.timestamp() * 1_000),
        evidence_engine_mode="live_demo",
    )
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


def _minimal_plan(event: dict) -> dict:
    side_cell_key = "|".join(
        (event["strategy_name"], event["symbol"], event["side"])
    )
    event_time = dt.datetime.fromtimestamp(
        event["ts_ms"] / 1_000,
        tz=dt.timezone.utc,
    )
    return {
        "schema_version": DEMO_LEARNING_LANE_SCHEMA_VERSION,
        "generated_at_utc": event_time.isoformat(),
        "status": "READY_FOR_DEMO_LEARNING_PROBE",
        "gate_status": "READY",
        "main_cost_gate_adjustment": "NONE",
        "learning_gate_adjustment": "NONE",
        "order_authority": "NOT_GRANTED",
        "probe_candidates": [
            {
                "side_cell_key": side_cell_key,
                "source_kind": "candidate_evaluation_producer_test",
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


def _complete_source_bundle(event_date: dt.date) -> dict:
    as_of = event_date + dt.timedelta(days=1)
    resource_body = {
        "daily_buckets": [
            {
                "utc_date": (as_of - dt.timedelta(days=offset)).isoformat(),
                "scan_complete": True,
                "distinct_entries": 5,
            }
            for offset in range(7, 0, -1)
        ],
        "estimated_rows_scanned": 700,
        "predicted_canonical_bytes": 7_000,
        "zero_resource_attested": False,
    }
    hidden_oos_body = {
        "schema_version": "hidden_oos_state_v1",
        "state": "sealed",
        "open_count": 0,
        "opened_for_iteration": False,
        "consumed": False,
        "invalidated": False,
        "family_id": "cold_evaluation_producer_test_family",
        "split_hash": canonical_sha256({"split": "cold-evaluation-producer-test"}),
    }
    counts = {label: 0 for label in (*REGIME_BUCKETS, "unknown")}
    evidence_regime = "neutral|low_vol|liquid"
    counts[evidence_regime] = 30
    return {
        "evidence_regime_label": evidence_regime,
        "regime_entry_counts": counts,
        "target_regime_context": {
            "label": evidence_regime,
            "utc_date": event_date.isoformat(),
            "point_in_time": "D-1",
            "source_complete": True,
            "source_hash": canonical_sha256({"source": "target-regime-test"}),
            "classifier_hash": canonical_sha256({"classifier": "test-v1"}),
        },
        "context_hashes": {
            "data": canonical_sha256({"context": "data"}),
            "evidence": canonical_sha256({"context": "evidence"}),
            "cost": canonical_sha256({"context": "cost"}),
            "portfolio": canonical_sha256({"context": "portfolio"}),
        },
        "resource": {
            **resource_body,
            "resource_estimator_hash": canonical_sha256(resource_body),
        },
        "portfolio": {
            "sector_exposure_share": "0.1",
            "strategy_active_target_share": "0.2",
            "beta_to_portfolio": "-1.5",
        },
        "proof": {
            "proof_stage": 1,
            "completed_proof_stages": [0, 1],
            "next_gap": {"kind": "NONE", "code": "DATA_GATES_READY"},
        },
        "hidden_oos_state": {
            **hidden_oos_body,
            "state_hash": canonical_sha256(hidden_oos_body),
        },
    }


def _price_rows(event: dict) -> list[dict]:
    return [
        {"symbol": event["symbol"], "ts_ms": event["ts_ms"], "close": 2_500.0},
        {
            "symbol": event["symbol"],
            "ts_ms": event["ts_ms"] + 60 * 60_000,
            "close": 2_510.0,
        },
    ]


def _blocked_subtype_fields() -> dict:
    return {
        "source_admission_decision": "ORDER_AUTHORITY_NOT_GRANTED",
        "allowed_to_submit_order": False,
        "outcome_source": "market_markout_proxy_for_blocked_signal",
    }


def _probe_subtype_fields() -> dict:
    return {
        "source_admission_decision": "ADMIT_DEMO_LEARNING_PROBE",
        "allowed_to_submit_order": True,
        "outcome_source": "market_markout_proxy",
    }


def _raw_valid_outcome(
    context_id: str = "ctx-cold-evaluation-raw-outcome",
    captured_at_utc: dt.datetime | None = None,
) -> tuple[dict, dt.datetime, dt.datetime, dict, dict]:
    event = _raw_valid_reject_event(context_id, captured_at_utc)
    event_time = dt.datetime.fromtimestamp(
        event["ts_ms"] / 1_000,
        tz=dt.timezone.utc,
    )
    admission = build_ledger_record(
        evaluate_probe_admission(
            _minimal_plan(event),
            event,
            now_utc=event_time,
            adapter_enabled=False,
        )
    )
    now = dt.datetime.combine(
        event_time.date() + dt.timedelta(days=1),
        dt.time(0, 1),
        tzinfo=dt.timezone.utc,
    )
    outcome = build_blocked_signal_outcome_records(
        [admission],
        _price_rows(event),
        now_utc=now,
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )[0]
    return event, event_time, now, admission, outcome


def _assert_telemetry_conservation(partition: dict) -> None:
    assert partition["generated_outcome_count"] == (
        partition["candidate_evaluation_eligible_count"]
        + partition["candidate_evaluation_not_applicable_count"]
    )
    assert partition["candidate_evaluation_eligible_count"] == (
        partition["candidate_evaluation_preflight_attached_count"]
        + partition["candidate_evaluation_deferred_count"]
    )
    assert sum(partition["candidate_evaluation_defer_reason_counts"].values()) == (
        partition["candidate_evaluation_deferred_count"]
    )
    assert partition["candidate_evaluation_batch_deferred"] is (
        partition["candidate_evaluation_deferred_count"] > 0
    )


def test_complete_explicit_source_attaches_and_reaches_strict_board(tmp_path) -> None:
    event = _raw_valid_reject_event()
    event_time = dt.datetime.fromtimestamp(
        event["ts_ms"] / 1_000,
        tz=dt.timezone.utc,
    )
    decision = evaluate_probe_admission(
        _minimal_plan(event),
        event,
        now_utc=event_time,
        adapter_enabled=False,
    )
    ledger_path = tmp_path / "learning-ledger.jsonl"
    append_jsonl_ledger(ledger_path, build_ledger_record(decision))

    provider_calls = []

    def provider(candidate_event_context: dict, as_of_utc_date: str) -> dict:
        provider_calls.append((candidate_event_context, as_of_utc_date))
        return _complete_source_bundle(event_time.date())

    now = dt.datetime(2026, 7, 10, 0, 1, tzinfo=dt.timezone.utc)
    batch = refresh_cost_gate_outcomes_from_price_rows(
        ledger_path,
        _price_rows(event),
        now_utc=now,
        selection=OutcomeRefreshSelection(record_blocked_outcomes=True),
        outcome_cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
        candidate_evaluation_source_provider=provider,
    )

    assert provider_calls == [
        (event["candidate_event_context"], "2026-07-10")
    ]
    assert batch["candidate_evaluation_preflight_attached_count"] == 1
    assert batch["candidate_evaluation_deferred_count"] == 0
    assert batch["candidate_evaluation_batch_deferred"] is False
    assert batch["outcome_count"] == 1
    attached = batch["outcomes"][0]
    assert attached["candidate_summary"]["candidate_evaluation_context_status"] == "VALID"
    assert attached["candidate_summary"]["candidate_evaluation_context"][
        "as_of_utc_date"
    ] == "2026-07-10"

    board = build_blocked_signal_outcome_review([attached], now_utc=now)[
        "learning_candidate_board"
    ]
    assert board["qualified_lineage_outcome_row_count"] == 1
    assert board["candidate_rows"][0]["qualified_evaluator_input_count"] == 1
    assert validate_learning_candidate_board_v2(board) == board


def test_missing_source_defers_without_summary_change_or_append(tmp_path) -> None:
    event = _raw_valid_reject_event()
    event_time = dt.datetime.fromtimestamp(
        event["ts_ms"] / 1_000,
        tz=dt.timezone.utc,
    )
    now = dt.datetime(2026, 7, 10, 0, 1, tzinfo=dt.timezone.utc)
    decision = evaluate_probe_admission(
        _minimal_plan(event),
        event,
        now_utc=event_time,
        adapter_enabled=False,
    )
    admission = build_ledger_record(decision)
    raw_outcome = build_blocked_signal_outcome_records(
        [admission],
        _price_rows(event),
        now_utc=now,
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )[0]
    summary_before = copy.deepcopy(raw_outcome["candidate_summary"])

    result = attach_candidate_evaluation_to_outcome(
        raw_outcome,
        now_utc=now,
    )

    assert result["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert result["defer_reason"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert result["outcome"]["candidate_summary"] == summary_before
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
        "candidate_learning_context",
    ):
        assert field not in result["outcome"]["candidate_summary"]

    ledger_path = tmp_path / "missing-source-ledger.jsonl"
    append_jsonl_ledger(ledger_path, admission)
    before_bytes = ledger_path.read_bytes()
    batch = refresh_cost_gate_outcomes_from_price_rows(
        ledger_path,
        _price_rows(event),
        now_utc=now,
        selection=OutcomeRefreshSelection(record_blocked_outcomes=True),
        outcome_cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
        append_ledger=True,
    )

    assert batch["candidate_evaluation_deferred_count"] == 1
    assert batch["candidate_evaluation_defer_reason_counts"] == {
        DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE: 1
    }
    assert batch["candidate_evaluation_batch_deferred"] is True
    assert batch["outcomes"] == []
    assert batch["outcome_count"] == 0
    assert batch["appended_outcome_count"] == 0
    assert ledger_path.read_bytes() == before_bytes
    assert len(read_jsonl_ledger(ledger_path)) == 1


def test_unclosed_event_day_or_later_dated_source_defers() -> None:
    event = _raw_valid_reject_event()
    event_time = dt.datetime.fromtimestamp(
        event["ts_ms"] / 1_000,
        tz=dt.timezone.utc,
    )
    admission = build_ledger_record(
        evaluate_probe_admission(
            _minimal_plan(event),
            event,
            now_utc=event_time,
            adapter_enabled=False,
        )
    )
    raw_outcome = build_blocked_signal_outcome_records(
        [admission],
        _price_rows(event),
        now_utc=dt.datetime(2026, 7, 10, 0, 1, tzinfo=dt.timezone.utc),
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )[0]
    provider_calls = []

    def provider(candidate_event_context: dict, as_of_utc_date: str) -> dict:
        provider_calls.append((candidate_event_context, as_of_utc_date))
        return _complete_source_bundle(event_time.date())

    no_clock = attach_candidate_evaluation_to_outcome(
        raw_outcome,
        source_provider=provider,
    )
    before_close = attach_candidate_evaluation_to_outcome(
        raw_outcome,
        source_provider=provider,
        now_utc=dt.datetime(2026, 7, 9, 23, 59, 59, tzinfo=dt.timezone.utc),
    )

    assert no_clock["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert before_close["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert provider_calls == []

    def later_provider(_candidate_event_context: dict, _as_of_utc_date: str) -> dict:
        bundle = _complete_source_bundle(event_time.date())
        bundle["target_regime_context"]["utc_date"] = "2026-07-10"
        return bundle

    later_source = attach_candidate_evaluation_to_outcome(
        raw_outcome,
        source_provider=later_provider,
        now_utc=dt.datetime(2026, 7, 10, 0, 1, tzinfo=dt.timezone.utc),
    )
    assert later_source["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE


def test_extra_hidden_oos_sensitive_metadata_defers_without_persistence() -> None:
    event = _raw_valid_reject_event()
    event_time = dt.datetime.fromtimestamp(
        event["ts_ms"] / 1_000,
        tz=dt.timezone.utc,
    )
    admission = build_ledger_record(
        evaluate_probe_admission(
            _minimal_plan(event),
            event,
            now_utc=event_time,
            adapter_enabled=False,
        )
    )
    now = dt.datetime(2026, 7, 10, 0, 1, tzinfo=dt.timezone.utc)
    raw_outcome = build_blocked_signal_outcome_records(
        [admission],
        _price_rows(event),
        now_utc=now,
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )[0]
    secret = "postgresql://redacted@runtime.invalid/private"

    def overbroad_provider(
        _candidate_event_context: dict,
        _as_of_utc_date: str,
    ) -> dict:
        bundle = _complete_source_bundle(event_time.date())
        hidden = bundle["hidden_oos_state"]
        hidden["state_jsonb"] = {
            "actor": "operator",
            "dsn": secret,
            "sql_error": "SELECT credential FROM private_state",
        }
        hidden["state_hash"] = canonical_sha256(
            {key: value for key, value in hidden.items() if key != "state_hash"}
        )
        return bundle

    result = attach_candidate_evaluation_to_outcome(
        raw_outcome,
        source_provider=overbroad_provider,
        now_utc=now,
    )
    partition = partition_candidate_evaluation_outcomes(
        [raw_outcome],
        source_provider=overbroad_provider,
        now_utc=now,
    )

    assert result["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert partition["candidate_evaluation_deferred_count"] == 1
    assert partition["outcomes"] == []
    assert secret not in repr(result)
    assert secret not in repr(partition)


def test_mixed_batch_with_one_defer_exposes_and_appends_nothing(tmp_path) -> None:
    first_event = _raw_valid_reject_event("ctx-cold-mixed-attached")
    second_event = _raw_valid_reject_event("ctx-cold-mixed-deferred")
    event_time = dt.datetime.fromtimestamp(
        first_event["ts_ms"] / 1_000,
        tz=dt.timezone.utc,
    )
    admissions = [
        build_ledger_record(
            evaluate_probe_admission(
                _minimal_plan(event),
                event,
                now_utc=event_time,
                adapter_enabled=False,
            )
        )
        for event in (first_event, second_event)
    ]
    now = dt.datetime(2026, 7, 10, 0, 1, tzinfo=dt.timezone.utc)
    raw_outcomes = build_blocked_signal_outcome_records(
        admissions,
        _price_rows(first_event),
        now_utc=now,
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )
    historical = copy.deepcopy(raw_outcomes[0])
    historical["attempt_id"] = "historical-contextless"
    historical["candidate_summary"] = {
        "candidate_event_context_status": "UNQUALIFIED_CONTEXT_MISSING"
    }
    historical["event"].pop("candidate_event_context")

    absent_provider_partition = partition_candidate_evaluation_outcomes(
        [raw_outcomes[0], historical],
        now_utc=now,
    )
    assert absent_provider_partition["candidate_evaluation_deferred_count"] == 1
    assert absent_provider_partition["candidate_evaluation_not_applicable_count"] == 1
    assert absent_provider_partition["outcomes"] == []

    def selective_provider(
        candidate_event_context: dict,
        _as_of_utc_date: str,
    ) -> dict | None:
        if candidate_event_context["context_id"] == "ctx-cold-mixed-attached":
            return _complete_source_bundle(event_time.date())
        return None

    ledger_path = tmp_path / "mixed-batch-ledger.jsonl"
    for admission in admissions:
        append_jsonl_ledger(ledger_path, admission)
    before_bytes = ledger_path.read_bytes()
    batch = refresh_cost_gate_outcomes_from_price_rows(
        ledger_path,
        _price_rows(first_event),
        now_utc=now,
        selection=OutcomeRefreshSelection(record_blocked_outcomes=True),
        outcome_cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
        append_ledger=True,
        candidate_evaluation_source_provider=selective_provider,
    )

    assert batch["generated_outcome_count"] == 2
    assert batch["candidate_evaluation_eligible_count"] == 2
    assert batch["candidate_evaluation_preflight_attached_count"] == 1
    assert batch["candidate_evaluation_deferred_count"] == 1
    assert batch["candidate_evaluation_not_applicable_count"] == 0
    assert sum(batch["candidate_evaluation_defer_reason_counts"].values()) == 1
    assert batch["candidate_evaluation_batch_deferred"] is True
    assert batch["outcomes"] == []
    assert batch["probe_outcomes"] == []
    assert batch["blocked_signal_outcomes"] == []
    assert batch["outcome_count"] == 0
    assert batch["probe_outcome_count"] == 0
    assert batch["blocked_signal_outcome_count"] == 0
    assert batch["appended_outcome_count"] == 0
    assert ledger_path.read_bytes() == before_bytes


def test_historical_only_batch_remains_not_applicable_and_appendable(tmp_path) -> None:
    captured_at_ms = int(
        dt.datetime(2026, 7, 9, 12, tzinfo=dt.timezone.utc).timestamp()
        * 1_000
    )
    event = {
        "strategy_name": "ma_crossover",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "reject_reason_code": "cost_gate_js_demo_negative_edge",
        "engine_mode": "live_demo",
        "ts_ms": captured_at_ms,
        "context_id": "ctx-historical-contextless",
        "signal_id": "signal-historical-contextless",
    }
    decision = evaluate_probe_admission(
        _minimal_plan(event),
        event,
        now_utc=dt.datetime(2026, 7, 9, 12, tzinfo=dt.timezone.utc),
        adapter_enabled=False,
    )
    admission = build_ledger_record(decision)
    now = dt.datetime(2026, 7, 10, 0, 1, tzinfo=dt.timezone.utc)
    raw_outcome = build_blocked_signal_outcome_records(
        [admission],
        _price_rows(event),
        now_utc=now,
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )[0]

    partition = partition_candidate_evaluation_outcomes(
        [raw_outcome],
        now_utc=now,
    )

    assert partition["generated_outcome_count"] == 1
    assert partition["candidate_evaluation_eligible_count"] == 0
    assert partition["candidate_evaluation_preflight_attached_count"] == 0
    assert partition["candidate_evaluation_deferred_count"] == 0
    assert partition["candidate_evaluation_not_applicable_count"] == 1
    assert partition["candidate_evaluation_batch_deferred"] is False
    assert partition["outcomes"] == [raw_outcome]

    ledger_path = tmp_path / "historical-only-ledger.jsonl"
    append_jsonl_ledger(ledger_path, admission)
    batch = refresh_cost_gate_outcomes_from_price_rows(
        ledger_path,
        _price_rows(event),
        now_utc=now,
        selection=OutcomeRefreshSelection(record_blocked_outcomes=True),
        outcome_cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
        append_ledger=True,
    )
    assert batch["candidate_evaluation_not_applicable_count"] == 1
    assert batch["candidate_evaluation_deferred_count"] == 0
    assert batch["outcome_count"] == 1
    assert batch["appended_outcome_count"] == 1
    assert len(read_jsonl_ledger(ledger_path)) == 2


def test_partial_preexisting_evaluation_fields_defer_instead_of_enrichment() -> None:
    _event, event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        "ctx-cold-partial-evaluation"
    )
    partial = copy.deepcopy(raw_outcome)
    partial["candidate_summary"]["candidate_evaluation_context_status"] = "VALID"
    summary_before = copy.deepcopy(partial["candidate_summary"])

    result = attach_candidate_evaluation_to_outcome(
        partial,
        source_provider=lambda _event, _as_of: _complete_source_bundle(
            event_time.date()
        ),
        now_utc=now,
    )
    partition = partition_candidate_evaluation_outcomes(
        [partial],
        source_provider=lambda _event, _as_of: _complete_source_bundle(
            event_time.date()
        ),
        now_utc=now,
    )

    assert result["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert result["outcome"]["candidate_summary"] == summary_before
    assert partition["candidate_evaluation_deferred_count"] == 1
    assert partition["outcomes"] == []


def test_append_refuses_missing_or_batch_deferred_preflight(tmp_path) -> None:
    _event, _event_time, _now, _admission, raw_outcome = _raw_valid_outcome(
        "ctx-cold-append-guard"
    )
    ledger_path = tmp_path / "append-guard-ledger.jsonl"
    missing_preflight = {"outcomes": [raw_outcome]}
    deferred_preflight = {
        "outcomes": [raw_outcome],
        "generated_outcome_count": 1,
        "candidate_evaluation_eligible_count": 1,
        "candidate_evaluation_preflight_attached_count": 0,
        "candidate_evaluation_deferred_count": 1,
        "candidate_evaluation_not_applicable_count": 0,
        "candidate_evaluation_defer_reason_counts": {
            DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE: 1
        },
        "candidate_evaluation_batch_deferred": True,
        "deferred_outcome_count": 1,
    }

    assert append_refresh_outcomes_to_ledger(ledger_path, missing_preflight) == 0
    assert append_refresh_outcomes_to_ledger(ledger_path, deferred_preflight) == 0
    assert not ledger_path.exists()
    for batch in (missing_preflight, deferred_preflight):
        assert batch["append_requested"] is True
        assert batch["appended_to_ledger"] is False
        assert batch["appended_outcome_count"] == 0


@pytest.mark.parametrize(
    "missing_field",
    [
        "evidence_regime_label",
        "regime_entry_counts",
        "target_regime_context",
        "context_hashes",
        "resource",
        "portfolio",
        "proof",
        "hidden_oos_state",
    ],
)
def test_each_missing_source_field_defers_with_zero_appendable(
    missing_field: str,
) -> None:
    _event, event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        f"ctx-cold-missing-{missing_field}"
    )

    def provider(_event: dict, _as_of: str) -> dict:
        bundle = _complete_source_bundle(event_time.date())
        bundle.pop(missing_field)
        return bundle

    partition = partition_candidate_evaluation_outcomes(
        [raw_outcome],
        source_provider=provider,
        now_utc=now,
    )
    _assert_telemetry_conservation(partition)
    assert partition["candidate_evaluation_deferred_count"] == 1
    assert partition["outcomes"] == []


@pytest.mark.parametrize(
    ("invalid_field", "invalid_value"),
    [
        ("evidence_regime_label", None),
        ("regime_entry_counts", None),
        ("target_regime_context", None),
        ("context_hashes", None),
        ("resource", None),
        ("portfolio", None),
        ("proof", None),
        ("hidden_oos_state", None),
    ],
)
def test_each_invalid_source_field_class_defers_with_zero_appendable(
    invalid_field: str,
    invalid_value: object,
) -> None:
    _event, event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        f"ctx-cold-invalid-{invalid_field}"
    )

    def provider(_event: dict, _as_of: str) -> dict:
        bundle = _complete_source_bundle(event_time.date())
        bundle[invalid_field] = invalid_value
        return bundle

    partition = partition_candidate_evaluation_outcomes(
        [raw_outcome],
        source_provider=provider,
        now_utc=now,
    )
    _assert_telemetry_conservation(partition)
    assert partition["candidate_evaluation_deferred_count"] == 1
    assert partition["outcomes"] == []


@pytest.mark.parametrize(
    "hash_case",
    ["target_source", "context_data", "resource_estimator", "hidden_state"],
)
def test_invalid_source_hashes_defer_with_zero_appendable(hash_case: str) -> None:
    _event, event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        f"ctx-cold-invalid-hash-{hash_case}"
    )

    def provider(_event: dict, _as_of: str) -> dict:
        bundle = _complete_source_bundle(event_time.date())
        if hash_case == "target_source":
            bundle["target_regime_context"]["source_hash"] = "invalid"
        elif hash_case == "context_data":
            bundle["context_hashes"]["data"] = "invalid"
        elif hash_case == "resource_estimator":
            bundle["resource"]["resource_estimator_hash"] = "0" * 64
        else:
            bundle["hidden_oos_state"]["state_hash"] = "0" * 64
        return bundle

    partition = partition_candidate_evaluation_outcomes(
        [raw_outcome],
        source_provider=provider,
        now_utc=now,
    )
    _assert_telemetry_conservation(partition)
    assert partition["candidate_evaluation_deferred_count"] == 1
    assert partition["outcomes"] == []


def test_provider_exception_defers_without_exposing_exception_or_source() -> None:
    _event, _event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        "ctx-cold-provider-error"
    )
    secret = "provider DSN postgresql://secret.invalid/private"

    def provider(_event: dict, _as_of: str) -> dict:
        raise RuntimeError(secret)

    partition = partition_candidate_evaluation_outcomes(
        [raw_outcome],
        source_provider=provider,
        now_utc=now,
    )
    _assert_telemetry_conservation(partition)
    assert partition["candidate_evaluation_deferred_count"] == 1
    assert partition["outcomes"] == []
    assert secret not in repr(partition)


@pytest.mark.parametrize(
    "nested_path",
    [
        "regime_entry_counts",
        "target_regime_context",
        "context_hashes",
        "resource",
        "resource.daily_buckets",
        "portfolio",
        "proof",
        "proof.next_gap",
    ],
)
def test_each_non_hidden_nested_source_object_rejects_extra_metadata(
    nested_path: str,
) -> None:
    _event, event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        "ctx-cold-extra-" + nested_path.replace(".", "-")
    )

    def provider(_event: dict, _as_of: str) -> dict:
        bundle = _complete_source_bundle(event_time.date())
        if nested_path == "resource.daily_buckets":
            bundle["resource"]["daily_buckets"][0]["actor"] = "operator"
            resource = bundle["resource"]
            resource["resource_estimator_hash"] = canonical_sha256(
                {
                    key: value
                    for key, value in resource.items()
                    if key != "resource_estimator_hash"
                }
            )
        elif nested_path == "proof.next_gap":
            bundle["proof"]["next_gap"]["actor"] = "operator"
        else:
            bundle[nested_path]["actor"] = "operator"
        return bundle

    partition = partition_candidate_evaluation_outcomes(
        [raw_outcome],
        source_provider=provider,
        now_utc=now,
    )
    _assert_telemetry_conservation(partition)
    assert partition["candidate_evaluation_deferred_count"] == 1
    assert partition["outcomes"] == []


def test_contextless_partial_claim_defers_but_legacy_projection_remains_applicable() -> None:
    partial_claim = {
        "record_type": "blocked_signal_outcome",
        **_blocked_subtype_fields(),
        "attempt_id": "contextless-partial-evaluation-claim",
        "candidate_summary": {
            "candidate_evaluation_context_status": "VALID",
        },
    }
    legacy_only = {
        "record_type": "blocked_signal_outcome",
        **_blocked_subtype_fields(),
        "attempt_id": "contextless-legacy-projection",
        "candidate_summary": {
            "candidate_learning_context": {"legacy": True},
        },
    }

    claim_result = attach_candidate_evaluation_to_outcome(partial_claim)
    legacy_result = attach_candidate_evaluation_to_outcome(legacy_only)
    mixed = partition_candidate_evaluation_outcomes(
        [partial_claim, legacy_only],
        now_utc=dt.datetime(2026, 7, 10, tzinfo=dt.timezone.utc),
    )
    historical_only = partition_candidate_evaluation_outcomes(
        [legacy_only],
        now_utc=dt.datetime(2026, 7, 10, tzinfo=dt.timezone.utc),
    )

    assert claim_result["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert legacy_result["status"] == NOT_APPLICABLE
    assert mixed["candidate_evaluation_deferred_count"] == 1
    assert mixed["candidate_evaluation_not_applicable_count"] == 1
    assert mixed["outcomes"] == []
    assert historical_only["outcomes"] == [legacy_only]


def test_contextless_complete_but_invalid_v2_claim_defers() -> None:
    claimed = {
        "record_type": "blocked_signal_outcome",
        **_blocked_subtype_fields(),
        "attempt_id": "contextless-complete-invalid-v2-claim",
        "candidate_summary": {
            "candidate_evaluation_context": {},
            "candidate_evaluation_context_status": "VALID",
            "candidate_learning_context_projection": {},
            "candidate_learning_context": {},
        },
    }

    result = attach_candidate_evaluation_to_outcome(claimed)
    partition = partition_candidate_evaluation_outcomes(
        [claimed],
        now_utc=dt.datetime(2026, 7, 10, tzinfo=dt.timezone.utc),
    )

    assert result["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert partition["candidate_evaluation_deferred_count"] == 1
    assert partition["outcomes"] == []


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        (
            "family_id",
            "postgresql://redacted@runtime.invalid/private",
        ),
        ("family_id", "/srv/private/hidden_oos_state.json"),
        ("family_id", "SELECT credential FROM hidden_oos_state"),
        ("family_id", "operator:secret"),
        ("family_id", "user:hunter2"),
        ("next_gap_code", "PGPASSWORD=operator-secret"),
        ("next_gap_code", "/srv/private/proof.json"),
        ("next_gap_code", "SELECT SECRET FROM RUNTIME"),
        ("next_gap_code", "SELECT_SECRET_FROM_RUNTIME"),
        ("next_gap_code", "CREDENTIAL_ERROR"),
        ("next_gap_code", "AUTH:ABC123"),
        ("next_gap_code", "AUTH_ABC123"),
    ],
)
def test_allowed_free_text_source_fields_reject_sensitive_payloads_without_echo(
    field: str,
    unsafe_value: str,
) -> None:
    _event, event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        f"ctx-cold-unsafe-token-{field}"
    )

    def provider(_event: dict, _as_of: str) -> dict:
        bundle = _complete_source_bundle(event_time.date())
        if field == "family_id":
            hidden = bundle["hidden_oos_state"]
            hidden["family_id"] = unsafe_value
            hidden["state_hash"] = canonical_sha256(
                {key: value for key, value in hidden.items() if key != "state_hash"}
            )
        else:
            bundle["proof"]["next_gap"]["code"] = unsafe_value
        return bundle

    result = attach_candidate_evaluation_to_outcome(
        raw_outcome,
        source_provider=provider,
        now_utc=now,
    )
    partition = partition_candidate_evaluation_outcomes(
        [raw_outcome],
        source_provider=provider,
        now_utc=now,
    )

    assert result["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert partition["candidate_evaluation_deferred_count"] == 1
    assert partition["outcomes"] == []
    assert unsafe_value not in repr(result)
    assert unsafe_value not in repr(partition)


def test_exact_attached_evaluation_is_idempotent_without_provider(tmp_path) -> None:
    _event, event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        "ctx-cold-idempotent-attached"
    )
    first = attach_candidate_evaluation_to_outcome(
        raw_outcome,
        source_provider=lambda _event, _as_of: _complete_source_bundle(
            event_time.date()
        ),
        now_utc=now,
    )
    assert first["status"] == ATTACHED
    attached = first["outcome"]

    second = attach_candidate_evaluation_to_outcome(
        attached,
        now_utc=now,
    )
    partition = partition_candidate_evaluation_outcomes(
        [attached],
        now_utc=now,
    )

    assert second["status"] == ATTACHED
    assert second["outcome"] == attached
    assert partition["candidate_evaluation_preflight_attached_count"] == 1
    assert partition["candidate_evaluation_deferred_count"] == 0
    assert partition["outcomes"] == [attached]

    ledger_path = tmp_path / "idempotent-attached-ledger.jsonl"
    batch = {
        "generated_at_utc": now.isoformat(),
        "outcome_count": 1,
        "probe_outcome_count": 0,
        "blocked_signal_outcome_count": 1,
        "outcomes": [attached],
        "probe_outcomes": [],
        "blocked_signal_outcomes": [attached],
        **{
            key: value
            for key, value in partition.items()
            if key
            not in {"outcomes", "probe_outcomes", "blocked_signal_outcomes"}
        },
    }
    assert append_refresh_outcomes_to_ledger(ledger_path, batch) == 1
    assert read_jsonl_ledger(ledger_path) == [attached]


def test_safe_preexisting_evaluation_with_wrong_as_of_defers_without_mutation() -> None:
    _event, event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        "ctx-cold-wrong-as-of-preserved"
    )
    wrong_as_of_date = event_time.date() + dt.timedelta(days=2)
    evaluation = build_candidate_evaluation_context(
        candidate_event_context=raw_outcome["candidate_summary"][
            "candidate_event_context"
        ],
        as_of_utc_date=wrong_as_of_date.isoformat(),
        **_complete_source_bundle(event_time.date() + dt.timedelta(days=1)),
    )
    forged = copy.deepcopy(raw_outcome)
    forged["candidate_summary"] = attach_candidate_evaluation_context(
        forged["candidate_summary"],
        candidate_evaluation_context=evaluation,
    )
    before_hash = canonical_sha256(forged)

    result = attach_candidate_evaluation_to_outcome(
        forged,
        now_utc=now,
    )

    assert result["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert result["outcome"] == forged
    assert result["outcome"]["candidate_summary"] == forged["candidate_summary"]
    assert canonical_sha256(result["outcome"]) == before_hash


def test_preexisting_unsafe_token_evaluation_defers_preserved_and_cannot_append(
    tmp_path,
) -> None:
    _event, event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        "ctx-cold-preexisting-unsafe-token-preserved"
    )
    unsafe_value = "user:hunter2"
    bundle = _complete_source_bundle(event_time.date())
    hidden = bundle["hidden_oos_state"]
    hidden["family_id"] = unsafe_value
    hidden["state_hash"] = canonical_sha256(
        {key: value for key, value in hidden.items() if key != "state_hash"}
    )
    evaluation = build_candidate_evaluation_context(
        candidate_event_context=raw_outcome["candidate_summary"][
            "candidate_event_context"
        ],
        as_of_utc_date=(event_time.date() + dt.timedelta(days=1)).isoformat(),
        **bundle,
    )
    forged = copy.deepcopy(raw_outcome)
    forged["candidate_summary"] = attach_candidate_evaluation_context(
        forged["candidate_summary"],
        candidate_evaluation_context=evaluation,
    )
    before_hash = canonical_sha256(forged)

    result = attach_candidate_evaluation_to_outcome(forged, now_utc=now)
    partition = partition_candidate_evaluation_outcomes(
        [forged],
        now_utc=now,
    )
    claimed_attached_batch = {
        "generated_at_utc": now.isoformat(),
        "outcome_count": 1,
        "probe_outcome_count": 0,
        "blocked_signal_outcome_count": 1,
        "outcomes": [forged],
        "probe_outcomes": [],
        "blocked_signal_outcomes": [forged],
        "generated_outcome_count": 1,
        "candidate_evaluation_eligible_count": 1,
        "candidate_evaluation_preflight_attached_count": 1,
        "candidate_evaluation_deferred_count": 0,
        "candidate_evaluation_not_applicable_count": 0,
        "candidate_evaluation_defer_reason_counts": {},
        "candidate_evaluation_batch_deferred": False,
        "deferred_outcome_count": 0,
    }
    ledger_path = tmp_path / "preexisting-unsafe-token-ledger.jsonl"

    assert result["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert result["outcome"] == forged
    assert canonical_sha256(result["outcome"]) == before_hash
    assert partition["candidate_evaluation_deferred_count"] == 1
    assert partition["outcomes"] == []
    assert append_refresh_outcomes_to_ledger(
        ledger_path,
        claimed_attached_batch,
    ) == 0
    assert not ledger_path.exists()
    assert claimed_attached_batch["outcomes"] == []


def test_append_guard_semantically_rejects_forged_not_applicable_raw_valid_row(
    tmp_path,
) -> None:
    _event, _event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        "ctx-cold-forged-not-applicable"
    )
    forged = {
        "generated_at_utc": now.isoformat(),
        "outcome_count": 1,
        "probe_outcome_count": 0,
        "blocked_signal_outcome_count": 1,
        "outcomes": [raw_outcome],
        "probe_outcomes": [],
        "blocked_signal_outcomes": [raw_outcome],
        "generated_outcome_count": 1,
        "candidate_evaluation_eligible_count": 0,
        "candidate_evaluation_preflight_attached_count": 0,
        "candidate_evaluation_deferred_count": 0,
        "candidate_evaluation_not_applicable_count": 1,
        "candidate_evaluation_defer_reason_counts": {},
        "candidate_evaluation_batch_deferred": False,
        "deferred_outcome_count": 0,
    }
    ledger_path = tmp_path / "forged-not-applicable-ledger.jsonl"

    assert append_refresh_outcomes_to_ledger(ledger_path, forged) == 0
    assert not ledger_path.exists()
    assert forged["appended_outcome_count"] == 0
    assert forged["outcomes"] == []


def test_append_guard_rejects_non_mapping_row_even_with_consistent_counts(
    tmp_path,
) -> None:
    batch = {
        "generated_at_utc": "2026-07-10T00:01:00+00:00",
        "outcome_count": 1,
        "probe_outcome_count": 0,
        "blocked_signal_outcome_count": 0,
        "outcomes": ["not-a-row"],
        "probe_outcomes": [],
        "blocked_signal_outcomes": [],
        "generated_outcome_count": 1,
        "candidate_evaluation_eligible_count": 0,
        "candidate_evaluation_preflight_attached_count": 0,
        "candidate_evaluation_deferred_count": 0,
        "candidate_evaluation_not_applicable_count": 1,
        "candidate_evaluation_defer_reason_counts": {},
        "candidate_evaluation_batch_deferred": False,
        "deferred_outcome_count": 0,
    }
    ledger_path = tmp_path / "non-mapping-row-ledger.jsonl"

    assert append_refresh_outcomes_to_ledger(ledger_path, batch) == 0
    assert not ledger_path.exists()
    assert batch["appended_outcome_count"] == 0


def test_hostile_candidate_summary_mapping_fails_closed_without_secret_echo() -> None:
    secret = "postgresql://redacted@runtime.invalid/private"

    class HostileSummary(dict):
        def __deepcopy__(self, _memo):
            return self

        def __iter__(self):
            raise RuntimeError(secret)

    row = {
        "record_type": "blocked_signal_outcome",
        **_blocked_subtype_fields(),
        "candidate_summary": HostileSummary(),
    }

    result = attach_candidate_evaluation_to_outcome(row)

    assert result["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert secret not in repr(result)


def test_valid_outer_event_with_missing_summary_defers_whole_batch() -> None:
    _event, _event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        "ctx-cold-missing-summary-outer-valid"
    )
    malformed = copy.deepcopy(raw_outcome)
    malformed["candidate_summary"] = {}

    result = attach_candidate_evaluation_to_outcome(malformed, now_utc=now)
    partition = partition_candidate_evaluation_outcomes(
        [malformed],
        now_utc=now,
    )

    assert result["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert result["outcome"]["candidate_summary"] == malformed["candidate_summary"]
    assert partition["candidate_evaluation_deferred_count"] == 1
    assert partition["outcomes"] == []


def test_valid_summary_grafted_from_another_outer_event_defers_whole_batch() -> None:
    _first_event, first_time, now, _admission, first = _raw_valid_outcome(
        "ctx-cold-graft-target"
    )
    _second_event, _second_time, _now, _admission, second = _raw_valid_outcome(
        "ctx-cold-graft-source"
    )
    grafted = copy.deepcopy(first)
    grafted["candidate_summary"] = copy.deepcopy(second["candidate_summary"])

    result = attach_candidate_evaluation_to_outcome(
        grafted,
        source_provider=lambda _event, _as_of: _complete_source_bundle(
            first_time.date()
        ),
        now_utc=now,
    )
    partition = partition_candidate_evaluation_outcomes(
        [grafted],
        source_provider=lambda _event, _as_of: _complete_source_bundle(
            first_time.date()
        ),
        now_utc=now,
    )

    assert result["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert result["outcome"]["candidate_summary"] == grafted["candidate_summary"]
    assert partition["candidate_evaluation_deferred_count"] == 1
    assert partition["outcomes"] == []


def test_duplicate_event_with_conflicting_evaluation_hashes_defers_batch() -> None:
    _event, event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        "ctx-cold-duplicate-mixed-generation"
    )
    provider_call_count = 0

    def nondeterministic_provider(_event: dict, _as_of: str) -> dict:
        nonlocal provider_call_count
        provider_call_count += 1
        bundle = _complete_source_bundle(event_time.date())
        bundle["context_hashes"]["data"] = canonical_sha256(
            {"provider_call": provider_call_count}
        )
        return bundle

    partition = partition_candidate_evaluation_outcomes(
        [raw_outcome, copy.deepcopy(raw_outcome)],
        source_provider=nondeterministic_provider,
        now_utc=now,
    )

    _assert_telemetry_conservation(partition)
    assert provider_call_count == 2
    assert partition["candidate_evaluation_preflight_attached_count"] == 0
    assert partition["candidate_evaluation_deferred_count"] == 2
    assert partition["outcomes"] == []


def test_duplicate_event_with_identical_evaluation_is_appendable() -> None:
    _event, event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        "ctx-cold-duplicate-identical"
    )
    duplicate = copy.deepcopy(raw_outcome)
    partition = partition_candidate_evaluation_outcomes(
        [raw_outcome, duplicate],
        source_provider=lambda _event, _as_of: _complete_source_bundle(
            event_time.date()
        ),
        now_utc=now,
    )

    _assert_telemetry_conservation(partition)
    assert partition["candidate_evaluation_preflight_attached_count"] == 2
    assert partition["candidate_evaluation_deferred_count"] == 0
    assert len(partition["outcomes"]) == 2
    hashes = {
        row["candidate_summary"]["candidate_evaluation_context"][
            "candidate_evaluation_context_hash"
        ]
        for row in partition["outcomes"]
    }
    assert len(hashes) == 1


def test_same_attempt_context_identity_with_different_event_hashes_defers() -> None:
    _event, event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        "ctx-cold-duplicate-event-hash-conflict"
    )
    conflicting = copy.deepcopy(raw_outcome)
    context = conflicting["candidate_summary"]["candidate_event_context"]
    context["market_inputs"]["last_price"] = 2500.05
    context["event_hash"] = canonical_sha256(
        {key: value for key, value in context.items() if key != "event_hash"}
    )
    conflicting["event"]["candidate_event_context"] = copy.deepcopy(context)

    partition = partition_candidate_evaluation_outcomes(
        [raw_outcome, conflicting],
        source_provider=lambda _event, _as_of: _complete_source_bundle(
            event_time.date()
        ),
        now_utc=now,
    )

    _assert_telemetry_conservation(partition)
    assert partition["candidate_evaluation_preflight_attached_count"] == 0
    assert partition["candidate_evaluation_deferred_count"] == 2
    assert partition["outcomes"] == []


@pytest.mark.parametrize("record_type", ["probe_outcome", "blocked_signal_outcome"])
def test_known_outcome_missing_all_subtype_fields_defers(record_type: str) -> None:
    _event, _event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        f"ctx-cold-missing-subtype-{record_type}"
    )
    missing = copy.deepcopy(raw_outcome)
    missing["record_type"] = record_type
    for field in (
        "source_admission_decision",
        "allowed_to_submit_order",
        "outcome_source",
    ):
        missing.pop(field)

    result = attach_candidate_evaluation_to_outcome(missing, now_utc=now)
    partition = partition_candidate_evaluation_outcomes(
        [missing],
        now_utc=now,
    )

    assert result["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert result["outcome"] == missing
    assert partition["candidate_evaluation_deferred_count"] == 1
    assert partition["candidate_evaluation_not_applicable_count"] == 0
    assert partition["outcomes"] == []


@pytest.mark.parametrize("record_type", [[], {}])
def test_unhashable_record_type_fails_closed_without_exception(record_type) -> None:
    row = {"record_type": record_type, "attempt_id": "malformed-record-type"}

    result = attach_candidate_evaluation_to_outcome(row)

    assert result["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
    assert result["outcome"] == row


def test_partition_rejects_unknown_string_record_type() -> None:
    row = {
        "record_type": "unexpected_outcome",
        "attempt_id": "unknown-record-type",
    }

    partition = partition_candidate_evaluation_outcomes(
        [row],
        now_utc=dt.datetime(2026, 7, 10, tzinfo=dt.timezone.utc),
    )

    assert partition["candidate_evaluation_deferred_count"] == 1
    assert partition["candidate_evaluation_not_applicable_count"] == 0
    assert partition["outcomes"] == []


def test_append_guard_rejects_blocked_row_relabelled_as_probe(tmp_path) -> None:
    _event, _event_time, now, _admission, raw_outcome = _raw_valid_outcome(
        "ctx-cold-blocked-relabelled-probe"
    )
    relabelled = copy.deepcopy(raw_outcome)
    relabelled["record_type"] = "probe_outcome"
    partition = partition_candidate_evaluation_outcomes(
        [relabelled],
        now_utc=now,
    )
    forged = {
        "generated_at_utc": now.isoformat(),
        "outcome_count": 1,
        "probe_outcome_count": 1,
        "blocked_signal_outcome_count": 0,
        "outcomes": [relabelled],
        "probe_outcomes": [relabelled],
        "blocked_signal_outcomes": [],
        "generated_outcome_count": 1,
        "candidate_evaluation_eligible_count": 0,
        "candidate_evaluation_preflight_attached_count": 0,
        "candidate_evaluation_deferred_count": 0,
        "candidate_evaluation_not_applicable_count": 1,
        "candidate_evaluation_defer_reason_counts": {},
        "candidate_evaluation_batch_deferred": False,
        "deferred_outcome_count": 0,
    }
    ledger_path = tmp_path / "blocked-relabelled-probe-ledger.jsonl"

    assert partition["candidate_evaluation_deferred_count"] == 1
    assert partition["candidate_evaluation_not_applicable_count"] == 0
    assert partition["outcomes"] == []
    assert append_refresh_outcomes_to_ledger(ledger_path, forged) == 0
    assert not ledger_path.exists()
    assert forged["appended_outcome_count"] == 0


def test_refresh_rerun_is_idempotent_after_attached_append(tmp_path) -> None:
    event = _raw_valid_reject_event("ctx-cold-refresh-rerun")
    event_time = dt.datetime.fromtimestamp(
        event["ts_ms"] / 1_000,
        tz=dt.timezone.utc,
    )
    admission = build_ledger_record(
        evaluate_probe_admission(
            _minimal_plan(event),
            event,
            now_utc=event_time,
            adapter_enabled=False,
        )
    )
    ledger_path = tmp_path / "refresh-rerun-ledger.jsonl"
    append_jsonl_ledger(ledger_path, admission)
    now = dt.datetime(2026, 7, 10, 0, 1, tzinfo=dt.timezone.utc)
    provider = lambda _event, _as_of: _complete_source_bundle(event_time.date())

    first = refresh_cost_gate_outcomes_from_price_rows(
        ledger_path,
        _price_rows(event),
        now_utc=now,
        selection=OutcomeRefreshSelection(record_blocked_outcomes=True),
        outcome_cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
        append_ledger=True,
        candidate_evaluation_source_provider=provider,
    )
    after_first = ledger_path.read_bytes()
    second = refresh_cost_gate_outcomes_from_price_rows(
        ledger_path,
        _price_rows(event),
        now_utc=now,
        selection=OutcomeRefreshSelection(record_blocked_outcomes=True),
        outcome_cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
        append_ledger=True,
        candidate_evaluation_source_provider=provider,
    )

    assert first["generated_outcome_count"] == 1
    assert first["appended_outcome_count"] == 1
    assert second["generated_outcome_count"] == 0
    assert second["outcome_count"] == 0
    assert second["appended_outcome_count"] == 0
    assert ledger_path.read_bytes() == after_first
    assert len(read_jsonl_ledger(ledger_path)) == 2


def test_append_semantic_clock_rejects_forged_future_batch_time(
    tmp_path,
    monkeypatch,
) -> None:
    future_event_time = dt.datetime(2099, 1, 9, 12, tzinfo=dt.timezone.utc)
    _event, event_time, future_now, _admission, raw_outcome = _raw_valid_outcome(
        "ctx-cold-forged-future-clock",
        captured_at_utc=future_event_time,
    )
    attached = attach_candidate_evaluation_to_outcome(
        raw_outcome,
        source_provider=lambda _event, _as_of: _complete_source_bundle(
            event_time.date()
        ),
        now_utc=future_now,
    )["outcome"]
    future_partition = partition_candidate_evaluation_outcomes(
        [attached],
        now_utc=future_now,
    )
    batch = {
        "generated_at_utc": future_now.isoformat(),
        "outcome_count": 1,
        "probe_outcome_count": 0,
        "blocked_signal_outcome_count": 1,
        "outcomes": [attached],
        "probe_outcomes": [],
        "blocked_signal_outcomes": [attached],
        **{
            key: value
            for key, value in future_partition.items()
            if key
            not in {"outcomes", "probe_outcomes", "blocked_signal_outcomes"}
        },
    }
    monkeypatch.setattr(
        outcome_refresh_module,
        "_utc_now",
        lambda: dt.datetime(2026, 7, 15, tzinfo=dt.timezone.utc),
    )
    ledger_path = tmp_path / "forged-future-clock-ledger.jsonl"

    assert append_refresh_outcomes_to_ledger(ledger_path, batch) == 0
    assert not ledger_path.exists()
    assert batch["appended_outcome_count"] == 0


@pytest.mark.parametrize(
    ("rows", "expected_probe", "expected_blocked"),
    [
        (
            [
                {
                    "record_type": "probe_outcome",
                    "attempt_id": "probe-only",
                    **_probe_subtype_fields(),
                }
            ],
            1,
            0,
        ),
        (
            [
                {
                    "record_type": "blocked_signal_outcome",
                    **_blocked_subtype_fields(),
                    "attempt_id": "historical-only",
                    "candidate_summary": {
                        "candidate_event_context_status": (
                            "UNQUALIFIED_CONTEXT_MISSING"
                        )
                    },
                }
            ],
            0,
            1,
        ),
        (
            [
                {
                    "record_type": "probe_outcome",
                    "attempt_id": "combined-probe",
                    **_probe_subtype_fields(),
                },
                {
                    "record_type": "blocked_signal_outcome",
                    **_blocked_subtype_fields(),
                    "attempt_id": "combined-historical",
                    "candidate_summary": {
                        "candidate_event_context_status": (
                            "UNQUALIFIED_CONTEXT_MISSING"
                        )
                    },
                },
            ],
            1,
            1,
        ),
    ],
)
def test_probe_blocked_and_combined_selection_partitions(
    rows: list[dict],
    expected_probe: int,
    expected_blocked: int,
) -> None:
    partition = partition_candidate_evaluation_outcomes(
        rows,
        now_utc=dt.datetime(2026, 7, 10, tzinfo=dt.timezone.utc),
    )

    _assert_telemetry_conservation(partition)
    assert partition["candidate_evaluation_not_applicable_count"] == len(rows)
    assert partition["candidate_evaluation_deferred_count"] == 0
    assert len(partition["probe_outcomes"]) == expected_probe
    assert len(partition["blocked_signal_outcomes"]) == expected_blocked
    assert partition["outcomes"] == rows
