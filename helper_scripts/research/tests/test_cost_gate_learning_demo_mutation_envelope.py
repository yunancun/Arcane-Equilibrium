from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from cost_gate_learning_lane.learning_adjudicator import build_learning_adjudicator
from cost_gate_learning_lane.learning_demo_mutation_envelope import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    BLOCKED_BY_RUNTIME_READINESS_STATUS,
    READY_STATUS,
    READY_WITH_QUARANTINE_STATUS,
    SCHEMA_VERSION,
    build_learning_demo_mutation_envelope,
    main,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 29, 12, 30, tzinfo=dt.timezone.utc)


def _decision(label: str = "REVIEW") -> dict:
    return {
        "decision_id": f"learning_adjudication:test:{label.lower()}",
        "rank": 1,
        "decision_label": label,
        "adjudication": (
            "REVIEW_REQUIRED_FILL_BACKED_EVIDENCE_GATED_NO_AUTHORITY"
            if label == "REVIEW"
            else "DEFER_BLOCKED_MARKOUT_CONTEXT_ONLY_NOT_PROOF"
        ),
        "candidate_id": "grid_trading|ETHUSDT|Buy",
        "candidate_identity": {
            "side_cell_key": "grid_trading|ETHUSDT|Buy",
            "strategy_name": "grid_trading",
            "symbol": "ETHUSDT",
            "side": "Buy",
            "outcome_horizon_minutes": 60,
        },
        "proof_eligibility_gates": {
            "blocked_markout_proxy_count": 0 if label == "REVIEW" else 1,
            "blocked_markout_proxy_counts_as_fill_backed_proof": False,
            "candidate_fill_backed_proof_event_count": 1 if label == "REVIEW" else 0,
            "fill_backed_proof_ready": False,
            "promotion_proof_ready": False,
            "quarantine_clear": True,
        },
        "source_event_ids": ["learning_event:test"],
        "source_event_packet_sha256s": ["a" * 64],
    }


def _adjudicator(*, label: str = "REVIEW", status: str | None = None, quarantine_count: int = 0) -> dict:
    status = status or (
        "LEARNING_ADJUDICATOR_READY_WITH_QUARANTINE_NO_AUTHORITY"
        if quarantine_count
        else "LEARNING_ADJUDICATOR_READY_NO_AUTHORITY"
    )
    return {
        "schema_version": "cost_gate_learning_adjudicator_v1",
        "generated_at_utc": NOW.isoformat(),
        "status": status,
        "reason": "test",
        "adjudicator_sha256": "b" * 64,
        "summary": {
            "decision_count": 1,
            "upstream_quarantine_count": quarantine_count,
            "authority_violation_count": 0,
        },
        "decisions": [_decision(label)],
        "quarantine": {
            "upstream_quarantine_count": quarantine_count,
            "upstream_quarantine_review_required": quarantine_count > 0,
        },
        "authority_violations": [],
        "answers": {
            "order_authority_granted": False,
            "demo_mutation_authority_granted": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "promotion_evidence": False,
        },
    }


def _runtime_readiness(*, ready: bool = True) -> dict:
    if ready:
        return {
            "schema_version": "bounded_demo_runtime_readiness_v1",
            "status": "BOUNDED_DEMO_RUNTIME_READY_FOR_FINAL_WINDOW_GATES",
            "candidate": {"side_cell_key": "grid_trading|ETHUSDT|Buy"},
            "checks": {
                "demo_api_slot": {"status": "READY", "ready": True},
                "connector_mode": {"status": "READY", "ready": True},
                "engine_env": {"status": "READY", "ready": True},
            },
            "blocking_reasons": [],
            "answers": {
                "order_capable_action_allowed_by_this_packet": False,
                "runtime_mutation_performed": False,
                "order_submission_performed": False,
                "promotion_evidence": False,
            },
        }
    return {
        "schema_version": "bounded_demo_runtime_readiness_v1",
        "status": "BOUNDED_DEMO_RUNTIME_BLOCKED_BY_CREDENTIALS",
        "candidate": {"side_cell_key": "grid_trading|ETHUSDT|Buy"},
        "checks": {
            "demo_api_slot": {
                "status": "BLOCKED",
                "ready": False,
                "blocking_reasons": ["demo_api_key_expected_value_mismatch"],
            },
            "connector_mode": {
                "status": "BLOCKED",
                "ready": False,
                "blocking_reasons": [
                    "bybit_mode_not_demo",
                    "bybit_connector_write_not_enabled",
                ],
            },
        },
        "blocking_reasons": [
            "demo_api_slot:demo_api_key_expected_value_mismatch",
            "connector_mode:bybit_mode_not_demo",
            "connector_mode:bybit_connector_write_not_enabled",
        ],
        "answers": {
            "order_capable_action_allowed_by_this_packet": False,
            "runtime_mutation_performed": False,
            "order_submission_performed": False,
            "promotion_evidence": False,
        },
    }


def test_envelope_preserves_credential_and_connector_mode_blockers() -> None:
    packet = build_learning_demo_mutation_envelope(
        learning_adjudicator=_adjudicator(label="REVIEW"),
        bounded_demo_runtime_readiness=_runtime_readiness(ready=False),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == BLOCKED_BY_RUNTIME_READINESS_STATUS
    assert packet["summary"]["credential_mode_blocker_count"] == 3
    assert packet["answers"]["credential_mode_blockers_preserved"] is True
    assert packet["answers"]["demo_mutation_allowed"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert "connector_mode:bybit_mode_not_demo" in packet["runtime_readiness_gate"][
        "credential_mode_blockers"
    ]
    assert "Demo Mutation Envelope" in markdown


def test_review_decision_is_operator_gated_and_inert_when_runtime_ready() -> None:
    packet = build_learning_demo_mutation_envelope(
        learning_adjudicator=_adjudicator(label="REVIEW"),
        bounded_demo_runtime_readiness=_runtime_readiness(ready=True),
        now_utc=NOW,
    )

    assert packet["status"] == READY_STATUS
    assert packet["summary"]["operator_review_required_count"] == 1
    envelope = packet["mutation_envelopes"][0]
    assert envelope["envelope_label"] == "OPERATOR_REVIEW_REQUIRED_NO_AUTHORITY"
    assert envelope["operator_gate"]["required"] is True
    assert envelope["operator_gate"]["satisfied_by_this_packet"] is False
    assert envelope["allowed_actions"]["demo_mutation_allowed_by_this_packet"] is False
    assert packet["answers"]["bounded_demo_final_window_prerequisites_ready"] is True
    assert packet["answers"]["runtime_mutation_allowed"] is False


def test_defer_blocked_markout_context_never_becomes_mutation_authority() -> None:
    adjudicator = build_learning_adjudicator(
        learning_proposal_compiler={
            "schema_version": "cost_gate_learning_proposal_compiler_v1",
            "status": "LEARNING_PROPOSAL_COMPILER_READY_NO_AUTHORITY",
            "summary": {"upstream_quarantine_count": 0},
            "proposal_candidates": [
                {
                    "proposal_id": "learning_proposal:test",
                    "candidate_id": "grid_trading|ETHUSDT|Buy",
                    "candidate_identity": _decision("DEFER")["candidate_identity"],
                    "proposal_status": "REVIEW_ONLY_BLOCKED_MARKOUT_CONTEXT_NOT_PROOF",
                    "proof_filters": {
                        "blocked_markout_proxy_count": 1,
                        "blocked_markout_proxy_counts_as_fill_backed_proof": False,
                        "candidate_fill_backed_proof_event_count": 0,
                    },
                    "source_event_ids": ["event:blocked"],
                    "source_event_packet_sha256s": ["c" * 64],
                }
            ],
            "answers": {
                "pg_write_performed": False,
                "bybit_call_performed": False,
                "order_authority_granted": False,
                "promotion_evidence": False,
            },
        },
        now_utc=NOW,
    )

    packet = build_learning_demo_mutation_envelope(
        learning_adjudicator=adjudicator,
        bounded_demo_runtime_readiness=_runtime_readiness(ready=True),
        now_utc=NOW,
    )

    assert packet["status"] == READY_STATUS
    envelope = packet["mutation_envelopes"][0]
    assert envelope["envelope_label"] == "DEFER_CONTEXT_ONLY_NO_DEMO_MUTATION"
    assert "blocked_markout_proxy_context_only_not_fill_backed_proof" in envelope[
        "blocking_reasons"
    ]
    assert envelope["proof_gates"]["blocked_markout_proxy_counts_as_fill_backed_proof"] is False
    assert packet["answers"]["demo_mutation_authority_granted"] is False


def test_envelope_propagates_quarantine() -> None:
    packet = build_learning_demo_mutation_envelope(
        learning_adjudicator=_adjudicator(label="REVIEW", quarantine_count=1),
        bounded_demo_runtime_readiness=_runtime_readiness(ready=True),
        now_utc=NOW,
    )

    assert packet["status"] == READY_WITH_QUARANTINE_STATUS
    assert packet["summary"]["upstream_quarantine_count"] == 1
    assert packet["quarantine"]["upstream_quarantine_review_required"] is True
    assert packet["mutation_envelopes"][0]["proof_gates"]["quarantine_clear"] is False


def test_fails_closed_on_authority_violation() -> None:
    adjudicator = _adjudicator(label="REVIEW")
    adjudicator["answers"]["order_authority_granted"] = True

    packet = build_learning_demo_mutation_envelope(
        learning_adjudicator=adjudicator,
        bounded_demo_runtime_readiness=_runtime_readiness(ready=True),
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["mutation_envelopes"] == []
    assert packet["summary"]["authority_violation_count"] >= 1
    assert packet["answers"]["learning_demo_mutation_envelope_ready"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_cli_writes_json_output(tmp_path: Path, monkeypatch) -> None:
    adjudicator_path = tmp_path / "learning_adjudicator.json"
    readiness_path = tmp_path / "runtime_readiness.json"
    out = tmp_path / "mutation_envelope.json"
    adjudicator_path.write_text(json.dumps(_adjudicator(label="REVIEW")), encoding="utf-8")
    readiness_path.write_text(json.dumps(_runtime_readiness(ready=True)), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "learning_demo_mutation_envelope",
            "--learning-adjudicator-json",
            str(adjudicator_path),
            "--bounded-demo-runtime-readiness-json",
            str(readiness_path),
            "--json-output",
            str(out),
            "--print-json",
        ],
    )

    assert main() == 0
    packet = json.loads(out.read_text(encoding="utf-8"))
    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["mutation_envelopes"][0]["candidate_id"] == "grid_trading|ETHUSDT|Buy"


def test_static_no_network_db_order_or_runtime_side_effects() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/learning_demo_mutation_envelope.py"
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
