from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from cost_gate_learning_lane.learning_adjudicator import (
    READY_STATUS as ADJUDICATOR_READY_STATUS,
    SCHEMA_VERSION as ADJUDICATOR_SCHEMA_VERSION,
)
from cost_gate_learning_lane.learning_candidate_proof_evidence import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    BLOCKED_STATUS,
    READY_STATUS,
    build_candidate_proof_evidence,
    main,
)
from cost_gate_learning_lane.learning_proof_promotion_gate import (
    READY_STATUS as PROMOTION_READY_STATUS,
    build_learning_proof_promotion_gate,
)
from cost_gate_learning_lane.learning_serving_snapshot import (
    READY_STATUS as SERVING_READY_STATUS,
    SCHEMA_VERSION as SERVING_SCHEMA_VERSION,
)


NOW = dt.datetime(2026, 6, 29, 18, 0, tzinfo=dt.timezone.utc)
CANDIDATE_ID = "grid_trading|ETHUSDT|Buy"
SNAPSHOT_ID = "learning_serving_snapshot:abc123"
MODEL_VERSION = "qtrio-20260629T1400Z"
HORIZON = "60"


def _fill_row(index: int = 0, **overrides) -> dict:
    row = {
        "candidate_id": CANDIDATE_ID,
        "side_cell_key": CANDIDATE_ID,
        "strategy_name": "grid_trading",
        "symbol": "ETHUSDT",
        "side": "Buy",
        "outcome_horizon_minutes": HORIZON,
        "engine_mode": "demo",
        "order_link_id": f"oc_demo_order_{index}",
        "exchange_order_id": f"bybit-order-{index}",
        "exec_id": f"exec-{index}",
        "intent_id": f"intent-{index}",
        "risk_verdict": "APPROVED_BY_GUARDIAN_AND_RUST_AUTHORITY",
        "fee_bps": 1.2,
        "slippage_bps": 0.4,
        "spread_bps": 1.1,
        "capacity_usdt": 950.0,
        "notional_usdt": 100.0,
        "close_state": "closed",
        "outcome_source": "candidate_matched_demo_fill",
        "realized_net_bps": 4.2 + index * 0.1,
    }
    row.update(overrides)
    return row


def _control_row(index: int = 0, **overrides) -> dict:
    row = {
        "candidate_id": CANDIDATE_ID,
        "side_cell_key": CANDIDATE_ID,
        "strategy_name": "grid_trading",
        "symbol": "ETHUSDT",
        "side": "Buy",
        "outcome_horizon_minutes": HORIZON,
        "control_id": f"control-{index}",
        "realized_net_bps": -0.5,
    }
    row.update(overrides)
    return row


def _serving() -> dict:
    return {
        "schema_version": SERVING_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": SERVING_READY_STATUS,
        "serving_snapshot_candidate": {
            "snapshot_id": SNAPSHOT_ID,
            "model_version": MODEL_VERSION,
            "runtime_agreement": "runtime_loaded_registry_intent",
            "feature_schema_hash": "feature-schema-v1",
            "allowed_actions": {"promotion_allowed_by_this_packet": False},
        },
        "answers": {"promotion_proof": False},
    }


def _adjudicator() -> dict:
    return {
        "schema_version": ADJUDICATOR_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": ADJUDICATOR_READY_STATUS,
        "summary": {"upstream_quarantine_count": 0},
        "decisions": [
            {
                "decision_id": "learning_adjudication:review123",
                "decision_label": "REVIEW",
                "candidate_id": CANDIDATE_ID,
            }
        ],
        "answers": {"promotion_proof": False},
    }


def _build(**overrides) -> dict:
    args = {
        "candidate_id": CANDIDATE_ID,
        "strategy_name": "grid_trading",
        "symbol": "ETHUSDT",
        "side": "Buy",
        "outcome_horizon_minutes": HORIZON,
        "serving_snapshot_id": SNAPSHOT_ID,
        "model_version": MODEL_VERSION,
        "candidate_fill_rows_packet": {
            "candidate_matched_demo_fills": [_fill_row(0), _fill_row(1), _fill_row(2)]
        },
        "matched_control_rows_packet": {
            "matched_control_outperformance": True,
            "rows": [_control_row(0), _control_row(1), _control_row(2)],
        },
        "execution_realism_packet": {"execution_realism_passed": True},
        "tail_risk_packet": {"tail_risk_review_passed": True},
        "validation_packet": {"oos_validation_passed": True, "repeat_set_passed": True},
        "proof_exclusion_packet": {"proof_exclusion_passed": True},
        "min_candidate_matched_demo_fills": 3,
        "now_utc": NOW,
    }
    args.update(overrides)
    return build_candidate_proof_evidence(**args)


def test_builds_ready_candidate_proof_evidence_and_feeds_promotion_gate() -> None:
    evidence = _build()

    assert evidence["status"] == READY_STATUS
    assert evidence["schema_version"] == "cost_gate_learning_candidate_proof_evidence_v1"
    assert evidence["fill_evidence"]["candidate_matched_demo_fill_count"] == 3
    assert evidence["proof_exclusion"]["proof_excluded_row_count"] == 0
    assert evidence["answers"]["promotion_authority_granted"] is False

    packet = build_learning_proof_promotion_gate(
        serving_snapshot_packet=_serving(),
        learning_adjudicator_packet=_adjudicator(),
        proof_evidence_packet=evidence,
        now_utc=NOW,
    )
    assert packet["status"] == PROMOTION_READY_STATUS


def test_blocks_without_candidate_fill_rows() -> None:
    evidence = _build(candidate_fill_rows_packet={"candidate_matched_demo_fills": []})

    assert evidence["status"] == BLOCKED_STATUS
    assert "candidate_matched_demo_fill_rows_missing" in evidence["summary"]["blockers"]
    assert evidence["fill_evidence"]["candidate_matched_demo_fill_count"] == 0


def test_identity_mismatch_rows_are_excluded() -> None:
    evidence = _build(
        candidate_fill_rows_packet={
            "candidate_matched_demo_fills": [
                _fill_row(0, symbol="BTCUSDT"),
                _fill_row(1, outcome_horizon_minutes="240"),
            ]
        },
        matched_control_rows_packet={
            "matched_control_outperformance": True,
            "rows": [_control_row(0, side="Sell")],
        },
    )

    assert evidence["status"] == BLOCKED_STATUS
    assert evidence["fill_evidence"]["candidate_matched_demo_fill_count"] == 0
    reasons = evidence["proof_exclusion"]["reason_counts"]
    assert reasons["candidate_fill_symbol_mismatch"] == 1
    assert reasons["candidate_fill_outcome_horizon_minutes_mismatch"] == 1
    assert reasons["matched_control_side_mismatch"] == 1


def test_authority_alias_fails_closed() -> None:
    evidence = _build(
        candidate_fill_rows_packet={
            "candidate_matched_demo_fills": [_fill_row(0), _fill_row(1), _fill_row(2)],
            "allowed_actions": {"order_allowed_by_this_packet": True},
        }
    )

    assert evidence["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert any(
        item["key"] == "order_allowed_by_this_packet"
        for item in evidence["authority_violations"]
    )


def test_cli_writes_json_output(tmp_path: Path, monkeypatch) -> None:
    fills = tmp_path / "fills.json"
    controls = tmp_path / "controls.json"
    execution = tmp_path / "execution.json"
    tail = tmp_path / "tail.json"
    validation = tmp_path / "validation.json"
    proof_exclusion = tmp_path / "proof_exclusion.json"
    out = tmp_path / "proof_evidence.json"
    fills.write_text(
        json.dumps({"candidate_matched_demo_fills": [_fill_row(0), _fill_row(1), _fill_row(2)]}),
        encoding="utf-8",
    )
    controls.write_text(
        json.dumps(
            {
                "matched_control_outperformance": True,
                "rows": [_control_row(0), _control_row(1), _control_row(2)],
            }
        ),
        encoding="utf-8",
    )
    execution.write_text(json.dumps({"execution_realism_passed": True}), encoding="utf-8")
    tail.write_text(json.dumps({"tail_risk_review_passed": True}), encoding="utf-8")
    validation.write_text(
        json.dumps({"oos_validation_passed": True, "repeat_set_passed": True}),
        encoding="utf-8",
    )
    proof_exclusion.write_text(json.dumps({"proof_exclusion_passed": True}), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "learning_candidate_proof_evidence",
            "--candidate-id",
            CANDIDATE_ID,
            "--strategy-name",
            "grid_trading",
            "--symbol",
            "ETHUSDT",
            "--side",
            "Buy",
            "--outcome-horizon-minutes",
            HORIZON,
            "--serving-snapshot-id",
            SNAPSHOT_ID,
            "--model-version",
            MODEL_VERSION,
            "--candidate-fill-rows-json",
            str(fills),
            "--matched-control-rows-json",
            str(controls),
            "--execution-realism-json",
            str(execution),
            "--tail-risk-json",
            str(tail),
            "--validation-json",
            str(validation),
            "--proof-exclusion-json",
            str(proof_exclusion),
            "--min-candidate-matched-demo-fills",
            "3",
            "--json-output",
            str(out),
            "--print-json",
        ],
    )

    assert main() == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == READY_STATUS
    assert payload["fill_evidence"]["candidate_matched_demo_fill_count"] == 3


def test_static_no_network_db_runtime_or_order_side_effects() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/learning_candidate_proof_evidence.py"
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
        "place_order",
        "cancel_order",
        "create_order",
        "crontab -",
        "os.system",
        "systemctl",
    ]
    for needle in forbidden:
        assert needle not in source
