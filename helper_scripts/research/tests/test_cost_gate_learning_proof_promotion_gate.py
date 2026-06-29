from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from cost_gate_learning_lane.learning_adjudicator import (
    READY_STATUS as ADJUDICATOR_READY_STATUS,
    SCHEMA_VERSION as ADJUDICATOR_SCHEMA_VERSION,
)
from cost_gate_learning_lane.learning_proof_promotion_gate import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    BLOCKED_BY_ADJUDICATION_STATUS,
    BLOCKED_BY_PROOF_EXCLUSION_STATUS,
    BLOCKED_BY_PROOF_STATUS,
    BLOCKED_BY_SERVING_STATUS,
    PROOF_EVIDENCE_SCHEMA_VERSION,
    READY_STATUS,
    SCHEMA_VERSION,
    build_learning_proof_promotion_gate,
    main,
    render_markdown,
)
from cost_gate_learning_lane.learning_serving_snapshot import (
    BLOCKED_BY_RUNTIME_STATUS as SERVING_BLOCKED_BY_RUNTIME_STATUS,
    READY_STATUS as SERVING_READY_STATUS,
    SCHEMA_VERSION as SERVING_SCHEMA_VERSION,
)


NOW = dt.datetime(2026, 6, 29, 16, 0, tzinfo=dt.timezone.utc)
CANDIDATE_ID = "grid_trading|ETHUSDT|Buy"
SNAPSHOT_ID = "learning_serving_snapshot:abc123"
MODEL_VERSION = "qtrio-20260629T1400Z"


def _serving(**overrides) -> dict:
    payload = {
        "schema_version": SERVING_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": SERVING_READY_STATUS,
        "serving_snapshot_candidate": {
            "snapshot_id": SNAPSHOT_ID,
            "model_version": MODEL_VERSION,
            "runtime_agreement": "runtime_loaded_registry_intent",
            "feature_schema_hash": "feature-schema-v1",
            "allowed_actions": {
                "operator_review_allowed": True,
                "promotion_allowed_by_this_packet": False,
                "model_load_allowed_by_this_packet": False,
                "runtime_mutation_allowed_by_this_packet": False,
            },
        },
        "answers": {
            "serving_snapshot_authority_granted": False,
            "promotion_proof": False,
            "order_authority_granted": False,
        },
    }
    payload.update(overrides)
    return payload


def _blocked_serving() -> dict:
    return _serving(
        status=SERVING_BLOCKED_BY_RUNTIME_STATUS,
        serving_snapshot_candidate=None,
        blocked_snapshot={"runtime_blockers": ["runtime_state_missing"]},
    )


def _adjudicator(**overrides) -> dict:
    payload = {
        "schema_version": ADJUDICATOR_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": ADJUDICATOR_READY_STATUS,
        "summary": {
            "decision_count": 1,
            "review_count": 1,
            "upstream_quarantine_count": 0,
        },
        "decisions": [
            {
                "decision_id": "learning_adjudication:review123",
                "rank": 1,
                "decision_label": "REVIEW",
                "candidate_id": CANDIDATE_ID,
                "proof_eligibility_gates": {
                    "candidate_fill_backed_proof_event_count": 1,
                    "blocked_markout_proxy_counts_as_fill_backed_proof": False,
                    "promotion_proof_ready": False,
                },
                "allowed_actions": {
                    "review_packet_allowed": True,
                    "promotion_allowed": False,
                    "order_submission_allowed": False,
                    "cost_gate_change_allowed": False,
                },
            }
        ],
        "answers": {
            "promotion_evidence": False,
            "promotion_proof": False,
            "order_authority_granted": False,
            "pg_write_performed": False,
        },
    }
    payload.update(overrides)
    return payload


def _proof_evidence(**overrides) -> dict:
    payload = {
        "schema_version": PROOF_EVIDENCE_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": "CANDIDATE_PROOF_EVIDENCE_READY",
        "candidate_id": CANDIDATE_ID,
        "serving_snapshot_id": SNAPSHOT_ID,
        "model_version": MODEL_VERSION,
        "proof_thresholds": {
            "min_candidate_matched_demo_fills": 3,
        },
        "fill_evidence": {
            "candidate_matched_demo_fill_count": 3,
            "fee_evidence_present": True,
            "slippage_evidence_present": True,
            "spread_evidence_present": True,
            "capacity_evidence_present": True,
            "net_of_fees_positive": True,
            "avg_realized_net_bps": 4.2,
        },
        "execution_realism": {
            "execution_realism_passed": True,
        },
        "tail_risk": {
            "tail_risk_review_passed": True,
        },
        "validation": {
            "oos_validation_passed": True,
            "repeat_set_passed": True,
        },
        "matched_control_baseline": {
            "matched_control_baseline_present": True,
            "matched_control_count": 3,
            "matched_control_outperformance": True,
        },
        "proof_exclusion": {
            "proof_exclusion_passed": True,
            "proof_exclusion_present": False,
            "proof_excluded_row_count": 0,
        },
        "answers": {
            "order_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
            "cost_gate_lowering_allowed": False,
            "main_cost_gate_adjustment": "NONE",
        },
    }
    payload.update(overrides)
    return payload


def test_blocks_when_candidate_matched_demo_fills_are_missing() -> None:
    proof = _proof_evidence(
        fill_evidence={
            "candidate_matched_demo_fill_count": 0,
            "fee_evidence_present": True,
            "slippage_evidence_present": True,
            "spread_evidence_present": True,
            "capacity_evidence_present": True,
            "net_of_fees_positive": True,
        }
    )

    packet = build_learning_proof_promotion_gate(
        serving_snapshot_packet=_serving(),
        learning_adjudicator_packet=_adjudicator(),
        proof_evidence_packet=proof,
        now_utc=NOW,
    )

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == BLOCKED_BY_PROOF_STATUS
    assert packet["promotion_verdict"] is None
    assert "candidate_matched_demo_fills_below_floor" in packet["proof_gate"][
        "blockers"
    ]
    assert packet["answers"]["promotion_authority_granted"] is False
    assert packet["answers"]["cost_gate_lowering_allowed"] is False


def test_ready_promotion_verdict_is_review_only_without_authority() -> None:
    packet = build_learning_proof_promotion_gate(
        serving_snapshot_packet=_serving(),
        learning_adjudicator_packet=_adjudicator(),
        proof_evidence_packet=_proof_evidence(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["status"] == READY_STATUS
    verdict = packet["promotion_verdict"]
    assert verdict["verdict_id"].startswith("learning_promotion_verdict:")
    assert verdict["proof_requirements_satisfied"] is True
    assert verdict["allowed_actions"]["promotion_allowed_by_this_packet"] is False
    assert packet["answers"]["promotion_verdict_ready_for_operator_review"] is True
    assert packet["answers"]["promotion_proof"] is False
    assert packet["answers"]["live_authority_granted"] is False
    assert "Proof Promotion" in markdown


def test_row_backed_fill_evidence_can_satisfy_proof_requirements() -> None:
    proof = _proof_evidence(
        proof_thresholds={"min_candidate_matched_demo_fills": 2},
        fill_evidence={},
        candidate_matched_demo_fills=[
            {
                "candidate_id": CANDIDATE_ID,
                "side_cell_key": CANDIDATE_ID,
                "outcome_source": "candidate_matched_demo_fill",
                "realized_net_bps": 2.0,
                "order_link_id": "oc_dm_attempt_1",
                "exchange_order_id": "bybit-order-1",
                "exec_id": "exec-1",
                "intent_id": "intent-1",
                "risk_verdict": "APPROVED_BY_BOUNDED_DEMO_PROBE",
                "fee_bps": 2.0,
                "slippage_bps": 0.2,
                "spread_bps": 0.4,
                "capacity_usdt": 25.0,
                "close_state": "CLOSED_AT_HORIZON",
                "source_artifact_path": "artifacts/probe/fill-1.json",
            },
            {
                "candidate_id": CANDIDATE_ID,
                "side_cell_key": CANDIDATE_ID,
                "outcome_source": "candidate_matched_demo_fill",
                "realized_net_bps": 3.0,
                "order_link_id": "oc_dm_attempt_2",
                "exchange_order_id": "bybit-order-2",
                "exec_id": "exec-2",
                "intent_id": "intent-2",
                "risk_verdict": "APPROVED_BY_BOUNDED_DEMO_PROBE",
                "fee_bps": 2.0,
                "slippage_bps": 0.3,
                "spread_bps": 0.5,
                "capacity_usdt": 25.0,
                "close_state": "CLOSED_AT_HORIZON",
                "source_artifact_path": "artifacts/probe/fill-2.json",
            },
        ],
        matched_control_baseline={
            "matched_control_outperformance": True,
        },
        matched_control_rows=[
            {"candidate_id": CANDIDATE_ID, "realized_net_bps": 0.5},
            {"candidate_id": CANDIDATE_ID, "realized_net_bps": 1.0},
        ],
    )

    packet = build_learning_proof_promotion_gate(
        serving_snapshot_packet=_serving(),
        learning_adjudicator_packet=_adjudicator(),
        proof_evidence_packet=proof,
        now_utc=NOW,
    )

    assert packet["status"] == READY_STATUS
    assert packet["proof_gate"]["row_backed"] is True
    assert packet["proof_gate"]["candidate_matched_demo_fill_count"] == 2
    assert packet["proof_gate"]["proof_exclusion_gate"]["proof_exclusion_present"] is False


def test_blocked_serving_snapshot_prevents_promotion_gate() -> None:
    packet = build_learning_proof_promotion_gate(
        serving_snapshot_packet=_blocked_serving(),
        learning_adjudicator_packet=_adjudicator(),
        proof_evidence_packet=_proof_evidence(),
        now_utc=NOW,
    )

    assert packet["status"] == BLOCKED_BY_SERVING_STATUS
    assert "serving_snapshot_not_ready" in packet["serving_gate"]["blockers"]
    assert packet["promotion_verdict"] is None
    assert packet["answers"]["promotion_allowed_by_this_packet"] is False


def test_matching_review_adjudication_is_required() -> None:
    adjudicator = _adjudicator()
    adjudicator["decisions"][0]["candidate_id"] = "other|ETHUSDT|Buy"

    packet = build_learning_proof_promotion_gate(
        serving_snapshot_packet=_serving(),
        learning_adjudicator_packet=adjudicator,
        proof_evidence_packet=_proof_evidence(),
        now_utc=NOW,
    )

    assert packet["status"] == BLOCKED_BY_ADJUDICATION_STATUS
    assert "learning_adjudicator_has_no_matching_review_decision" in packet[
        "adjudication_gate"
    ]["blockers"]
    assert packet["promotion_verdict"] is None


def test_proof_exclusion_blocks_even_when_other_evidence_is_ready() -> None:
    proof = _proof_evidence(
        proof_exclusion={
            "proof_exclusion_passed": False,
            "proof_exclusion_present": True,
            "proof_excluded_row_count": 1,
            "reason_counts": {"unattributed_strategy_name": 1},
        }
    )

    packet = build_learning_proof_promotion_gate(
        serving_snapshot_packet=_serving(),
        learning_adjudicator_packet=_adjudicator(),
        proof_evidence_packet=proof,
        now_utc=NOW,
    )

    assert packet["status"] == BLOCKED_BY_PROOF_EXCLUSION_STATUS
    assert packet["proof_gate"]["proof_exclusion_gate"]["proof_exclusion_present"] is True
    assert packet["promotion_verdict"] is None
    assert packet["answers"]["promotion_evidence"] is False


def test_authority_bearing_input_fails_closed() -> None:
    proof = _proof_evidence()
    proof["answers"]["promotion_proof"] = True

    packet = build_learning_proof_promotion_gate(
        serving_snapshot_packet=_serving(),
        learning_adjudicator_packet=_adjudicator(),
        proof_evidence_packet=proof,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["promotion_verdict"] is None
    assert packet["summary"]["authority_violation_count"] >= 1
    assert packet["answers"]["promotion_authority_granted"] is False
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"


def test_cli_writes_json_output(tmp_path: Path, monkeypatch) -> None:
    serving = tmp_path / "serving_snapshot.json"
    adjudicator = tmp_path / "learning_adjudicator.json"
    proof = tmp_path / "proof_evidence.json"
    out = tmp_path / "proof_promotion_gate.json"
    serving.write_text(json.dumps(_serving(), sort_keys=True), encoding="utf-8")
    adjudicator.write_text(json.dumps(_adjudicator(), sort_keys=True), encoding="utf-8")
    proof.write_text(json.dumps(_proof_evidence(), sort_keys=True), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "learning_proof_promotion_gate",
            "--serving-snapshot-json",
            str(serving),
            "--learning-adjudicator-json",
            str(adjudicator),
            "--proof-evidence-json",
            str(proof),
            "--json-output",
            str(out),
            "--print-json",
        ],
    )

    assert main() == 0
    packet = json.loads(out.read_text(encoding="utf-8"))
    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["summary"]["promotion_verdict_emitted"] is True


def test_static_no_network_db_runtime_model_load_order_or_cost_gate_side_effects() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/learning_proof_promotion_gate.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "requests.",
        "httpx.",
        "urllib.",
        "psycopg",
        "asyncpg",
        "INSERT INTO",
        "UPDATE learning",
        "DELETE FROM",
        "subprocess",
        "onnxruntime",
        "InferenceSession",
        "load_model(",
        "place_order",
        "cancel_order",
        "create_order",
        "crontab -",
        "os.system",
        "systemctl",
    ]
    for needle in forbidden:
        assert needle not in source
