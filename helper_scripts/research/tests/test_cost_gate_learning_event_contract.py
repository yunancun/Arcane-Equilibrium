from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from cost_gate_learning_lane.learning_event_contract import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    EVENT_SCHEMA_VERSION,
    READY_STATUS,
    READY_WITH_QUARANTINE_STATUS,
    SCHEMA_VERSION,
    build_learning_event_contract,
    main,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 29, 10, 15, tzinfo=dt.timezone.utc)


def _admission_row(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_demo_learning_lane_adapter_v1",
        "record_type": "probe_admission_decision",
        "generated_at_utc": "2026-06-29T10:00:00+00:00",
        "attempt_id": "attempt-1",
        "decision": "REJECT_COST_GATE",
        "allowed_to_submit_order": False,
        "side_cell_key": "grid_trading|AVAXUSDT|Sell",
        "event": {
            "strategy_name": "grid_trading",
            "symbol": "AVAXUSDT",
            "side": "Sell",
            "ts_ms": 1782727200000,
        },
        "candidate_summary": {"outcome_horizon_minutes": 60},
        "promotion_evidence": False,
    }
    payload.update(overrides)
    return payload


def _blocked_outcome_row(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_demo_learning_lane_adapter_v1",
        "record_type": "blocked_signal_outcome",
        "generated_at_utc": "2026-06-29T10:05:00+00:00",
        "attempt_id": "attempt-1",
        "side_cell_key": "grid_trading|AVAXUSDT|Sell",
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
        "realized_net_bps": 12.5,
        "outcome_source": "market_markout_proxy_for_blocked_signal",
        "promotion_evidence": False,
    }
    payload.update(overrides)
    return payload


def _write_jsonl(path: Path, rows: list[object]) -> None:
    path.write_text(
        "\n".join(
            row if isinstance(row, str) else json.dumps(row, sort_keys=True)
            for row in rows
        )
        + "\n",
        encoding="utf-8",
    )


def test_learning_event_contract_wraps_probe_ledger_with_hashes(tmp_path: Path) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    _write_jsonl(ledger, [_admission_row(), _blocked_outcome_row()])

    packet = build_learning_event_contract(
        probe_ledger_jsonl=ledger,
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["current_learning_ssot"] == "artifact_probe_ledger_jsonl"
    assert packet["summary"]["event_count"] == 2
    assert packet["summary"]["blocked_markout_proxy_event_count"] == 1
    assert packet["answers"]["pg_write_performed"] is False
    assert packet["answers"]["bybit_call_performed"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["cost_gate_lowering_allowed"] is False

    admission, blocked = packet["events"]
    assert admission["schema_version"] == EVENT_SCHEMA_VERSION
    assert admission["candidate_id"] == "grid_trading|AVAXUSDT|Sell"
    assert admission["proof_tier"] == "admission_decision_not_outcome"
    assert admission["source_refs"][0]["path"] == str(ledger)
    assert admission["source_refs"][0]["source_sha256"]
    assert admission["source_refs"][0]["row_sha256"]
    assert admission["event_packet_sha256"]

    assert blocked["event_type"] == "blocked_signal_outcome"
    assert blocked["proof_tier"] == "blocked_markout_proxy"
    assert blocked["candidate_identity"]["outcome_horizon_minutes"] == 60
    assert "Cost Gate LearningEvent Contract" in markdown
    assert "blocked_markout_proxy" in markdown


def test_malformed_jsonl_row_is_quarantined_without_discarding_valid_events(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    _write_jsonl(ledger, [_admission_row(), "{not-json"])

    packet = build_learning_event_contract(
        probe_ledger_jsonl=ledger,
        now_utc=NOW,
    )

    assert packet["status"] == READY_WITH_QUARANTINE_STATUS
    assert packet["summary"]["event_count"] == 1
    assert packet["summary"]["quarantine_count"] == 1
    quarantine = packet["quarantine"]["events"][0]
    assert quarantine["reason"] == "malformed_jsonl"
    assert quarantine["line_no"] == 2
    assert quarantine["row_sha256"]


def test_authority_bearing_input_fails_closed(tmp_path: Path) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    row = _admission_row(probe_authority_granted=True)
    _write_jsonl(ledger, [row])

    packet = build_learning_event_contract(
        probe_ledger_jsonl=ledger,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["events"] == []
    assert packet["summary"]["authority_violation_count"] == 1
    assert packet["authority_violations"][0]["key"] == "probe_authority_granted"
    assert packet["answers"]["learning_event_contract_ready"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_artifact_json_input_wraps_into_learning_event(tmp_path: Path) -> None:
    artifact = tmp_path / "false_negative_candidate_packet.json"
    artifact.write_text(
        json.dumps(
            {
                "schema_version": "cost_gate_false_negative_candidate_packet_v1",
                "generated_at_utc": "2026-06-29T10:10:00+00:00",
                "status": "COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW",
                "candidate": {
                    "side_cell_key": "grid_trading|AVAXUSDT|Sell",
                    "strategy_name": "grid_trading",
                    "symbol": "AVAXUSDT",
                    "side": "Sell",
                    "outcome_horizon_minutes": 60,
                },
                "answers": {
                    "global_cost_gate_lowering_recommended": False,
                    "main_cost_gate_adjustment": "NONE",
                    "probe_authority_granted": False,
                    "order_authority_granted": False,
                    "promotion_evidence": False,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    packet = build_learning_event_contract(
        artifact_json_paths=[artifact],
        now_utc=NOW,
    )

    assert packet["status"] == READY_STATUS
    assert packet["summary"]["event_count"] == 1
    event = packet["events"][0]
    assert event["event_type"] == "cost_gate_false_negative_candidate_packet_v1"
    assert event["candidate_id"] == "grid_trading|AVAXUSDT|Sell"
    assert event["proof_tier"] == "artifact_review_only"
    assert event["source_refs"][0]["source_kind"] == "artifact_json"
    assert event["source_refs"][0]["path"] == str(artifact)
    assert event["source_refs"][0]["row_sha256"]


def test_cli_writes_json_output(tmp_path: Path, monkeypatch) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    out = tmp_path / "learning_event_contract.json"
    _write_jsonl(ledger, [_admission_row()])
    monkeypatch.setattr(
        "sys.argv",
        [
            "learning_event_contract",
            "--probe-ledger-jsonl",
            str(ledger),
            "--json-output",
            str(out),
            "--print-json",
        ],
    )

    assert main() == 0
    packet = json.loads(out.read_text(encoding="utf-8"))
    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["events"][0]["schema_version"] == EVENT_SCHEMA_VERSION


def test_missing_candidate_or_timestamp_quarantines_event(tmp_path: Path) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    _write_jsonl(ledger, [_admission_row(side_cell_key="", event={})])

    packet = build_learning_event_contract(
        probe_ledger_jsonl=ledger,
        now_utc=NOW,
    )

    assert packet["status"] == "LEARNING_EVENT_CONTRACT_BLOCKED"
    assert packet["summary"]["event_count"] == 0
    assert packet["quarantine"]["events"][0]["reason"] == "missing_candidate_identity"


def test_static_no_network_db_order_or_runtime_side_effects() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/learning_event_contract.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "requests.",
        "httpx.",
        "urllib.",
        "psycopg2",
        "asyncpg",
        "INSERT INTO",
        "UPDATE learning",
        "DELETE FROM",
        "subprocess",
        "place_order",
        "cancel_order",
        "create_order",
        "OPENCLAW_ALLOW_MAINNET=1",
    ]
    for needle in forbidden:
        assert needle not in source
