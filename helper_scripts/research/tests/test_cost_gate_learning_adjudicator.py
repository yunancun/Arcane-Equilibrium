from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from cost_gate_learning_lane.learning_adjudicator import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    READY_STATUS,
    READY_WITH_QUARANTINE_STATUS,
    SCHEMA_VERSION,
    build_learning_adjudicator,
    main,
    render_markdown,
)
from cost_gate_learning_lane.learning_event_contract import build_learning_event_contract
from cost_gate_learning_lane.learning_proposal_compiler import (
    build_learning_proposal_compiler,
)


NOW = dt.datetime(2026, 6, 29, 11, 45, tzinfo=dt.timezone.utc)


def _admission_row(side_cell_key: str = "grid_trading|AVAXUSDT|Sell") -> dict:
    strategy, symbol, side = side_cell_key.split("|")
    return {
        "schema_version": "cost_gate_demo_learning_lane_adapter_v1",
        "record_type": "probe_admission_decision",
        "generated_at_utc": "2026-06-29T10:00:00+00:00",
        "attempt_id": f"attempt:{side_cell_key}",
        "decision": "REJECT_COST_GATE",
        "allowed_to_submit_order": False,
        "side_cell_key": side_cell_key,
        "event": {
            "strategy_name": strategy,
            "symbol": symbol,
            "side": side,
            "ts_ms": 1782727200000,
        },
        "candidate_summary": {"outcome_horizon_minutes": 60},
        "promotion_evidence": False,
    }


def _blocked_outcome_row(side_cell_key: str = "grid_trading|AVAXUSDT|Sell") -> dict:
    strategy, symbol, side = side_cell_key.split("|")
    return {
        "schema_version": "cost_gate_demo_learning_lane_adapter_v1",
        "record_type": "blocked_signal_outcome",
        "generated_at_utc": "2026-06-29T10:05:00+00:00",
        "attempt_id": f"attempt:{side_cell_key}",
        "side_cell_key": side_cell_key,
        "strategy_name": strategy,
        "symbol": symbol,
        "side": side,
        "outcome_horizon_minutes": 60,
        "realized_net_bps": 12.5,
        "outcome_source": "market_markout_proxy_for_blocked_signal",
        "promotion_evidence": False,
    }


def _write_jsonl(path: Path, rows: list[object]) -> None:
    path.write_text(
        "\n".join(
            row if isinstance(row, str) else json.dumps(row, sort_keys=True)
            for row in rows
        )
        + "\n",
        encoding="utf-8",
    )


def _compiler(tmp_path: Path, rows: list[object]) -> dict:
    ledger = tmp_path / "probe_ledger.jsonl"
    _write_jsonl(ledger, rows)
    contract = build_learning_event_contract(
        probe_ledger_jsonl=ledger,
        now_utc=NOW,
    )
    return build_learning_proposal_compiler(
        learning_event_contract=contract,
        now_utc=NOW,
    )


def test_adjudicator_defers_blocked_markout_context_only(tmp_path: Path) -> None:
    compiler = _compiler(tmp_path, [_admission_row(), _blocked_outcome_row()])

    packet = build_learning_adjudicator(
        learning_proposal_compiler=compiler,
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["summary"]["decision_count"] == 1
    assert packet["summary"]["defer_count"] == 1
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["cost_gate_change_allowed"] is False
    assert packet["answers"]["promotion_proof_ready"] is False

    decision = packet["decisions"][0]
    assert decision["decision_label"] == "DEFER"
    assert decision["adjudication"] == "DEFER_BLOCKED_MARKOUT_CONTEXT_ONLY_NOT_PROOF"
    gates = decision["proof_eligibility_gates"]
    assert gates["blocked_markout_proxy_count"] == 1
    assert gates["blocked_markout_proxy_counts_as_fill_backed_proof"] is False
    assert gates["candidate_fill_backed_proof_event_count"] == 0
    assert gates["promotion_proof_ready"] is False
    assert "Learning Adjudicator" in markdown


def test_adjudicator_ranks_defer_before_reject_deterministically(tmp_path: Path) -> None:
    compiler = _compiler(
        tmp_path,
        [
            _admission_row("grid_trading|AVAXUSDT|Sell"),
            _admission_row("grid_trading|SUIUSDT|Sell"),
            _blocked_outcome_row("grid_trading|SUIUSDT|Sell"),
        ],
    )

    packet = build_learning_adjudicator(
        learning_proposal_compiler=compiler,
        now_utc=NOW,
    )

    assert packet["status"] == READY_STATUS
    assert [decision["candidate_id"] for decision in packet["decisions"]] == [
        "grid_trading|SUIUSDT|Sell",
        "grid_trading|AVAXUSDT|Sell",
    ]
    assert [decision["decision_label"] for decision in packet["decisions"]] == [
        "DEFER",
        "REJECT",
    ]
    assert packet["summary"]["defer_count"] == 1
    assert packet["summary"]["reject_count"] == 1


def test_adjudicator_propagates_quarantine(tmp_path: Path) -> None:
    compiler = _compiler(tmp_path, [_admission_row(), "{not-json"])

    packet = build_learning_adjudicator(
        learning_proposal_compiler=compiler,
        now_utc=NOW,
    )

    assert packet["status"] == READY_WITH_QUARANTINE_STATUS
    assert packet["summary"]["upstream_quarantine_count"] == 1
    assert packet["quarantine"]["upstream_quarantine_review_required"] is True
    assert packet["decisions"][0]["proof_eligibility_gates"]["quarantine_clear"] is False
    assert packet["answers"]["review_defer_reject_decisions_emitted"] is True


def test_adjudicator_fails_closed_on_authority_violation() -> None:
    compiler = {
        "schema_version": "cost_gate_learning_proposal_compiler_v1",
        "status": "AUTHORITY_BOUNDARY_VIOLATION",
        "authority_violations": [
            {"path": "$.order_authority_granted", "key": "order_authority_granted"}
        ],
        "proposal_candidates": [],
        "answers": {"order_authority_granted": False},
    }

    packet = build_learning_adjudicator(
        learning_proposal_compiler=compiler,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["decisions"] == []
    assert packet["summary"]["authority_violation_count"] >= 1
    assert packet["answers"]["learning_adjudicator_ready"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_cli_writes_json_output(tmp_path: Path, monkeypatch) -> None:
    compiler = _compiler(tmp_path, [_admission_row(), _blocked_outcome_row()])
    compiler_path = tmp_path / "learning_proposal_compiler.json"
    out = tmp_path / "learning_adjudicator.json"
    compiler_path.write_text(json.dumps(compiler, sort_keys=True), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "learning_adjudicator",
            "--learning-proposal-compiler-json",
            str(compiler_path),
            "--json-output",
            str(out),
            "--print-json",
        ],
    )

    assert main() == 0
    packet = json.loads(out.read_text(encoding="utf-8"))
    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["decisions"][0]["decision_label"] == "DEFER"


def test_static_no_network_db_order_or_runtime_side_effects() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/learning_adjudicator.py"
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
