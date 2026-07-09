from __future__ import annotations

import ast
from pathlib import Path

from ml_training.alr_outcome_feedback import (
    build_outcome_feedback,
    compute_outcome_feedback_hash,
    validate_outcome_feedback,
)
from ml_training.alr_scanner_statistical_experiment import (
    build_scanner_statistical_experiment,
)


def _experiment() -> dict:
    cycles = []
    for ordinal in range(1, 5):
        cycles.append(
            {
                "source_hash": f"{ordinal:064x}",
                "source_key": f"scan-{ordinal}|2026-07-09T12:0{ordinal}:00Z",
                "source_ts": f"2026-07-09T12:0{ordinal}:00Z",
                "canonical_payload": {
                    "candidates": [
                        {"symbol": symbol, "final_score": ordinal}
                        for symbol in ("ALPHAUSDT", "BETAUSDT", "GAMMAUSDT")
                    ],
                    "added": ["ALPHAUSDT"] if ordinal == 1 else [],
                },
            }
        )
    return build_scanner_statistical_experiment(source_head="a" * 40, cycles=cycles)


def test_absent_proof_and_reward_become_deferred_feedback_and_rotation() -> None:
    experiment = _experiment()

    result = build_outcome_feedback(
        run=experiment["run"],
        candidate_artifact=experiment["candidate_artifact"],
    )

    validation = validate_outcome_feedback(result)
    assert validation.valid is True
    assert result["feedback"]["feedback_status"] == "DEFER_EVIDENCE"
    assert result["feedback"]["proof_packet_present"] is False
    assert result["feedback"]["reward_record_count"] == 0
    assert result["rotation"]["rotate_next_target"] is True
    assert result["rotation"]["global_stop"] is False
    assert result["feedback_hash"] == compute_outcome_feedback_hash(result)
    assert {item["artifact_kind"] for item in result["artifacts"]} == {
        "outcome_bridge",
        "outcome_feedback",
        "target_rotation",
    }
    assert all(value is False for value in result["no_authority"].values())
    assert all(value == 0 for value in result["authority_counters"].values())


def test_rejects_tampered_feedback_status_even_when_rehashed() -> None:
    experiment = _experiment()
    result = build_outcome_feedback(
        run=experiment["run"],
        candidate_artifact=experiment["candidate_artifact"],
    )
    result["feedback"]["feedback_status"] = "EVIDENCE_OBSERVED_NO_PROMOTION"
    result["feedback_hash"] = compute_outcome_feedback_hash(result)

    validation = validate_outcome_feedback(result)

    assert validation.valid is False
    assert validation.reason == "feedback_status_mismatch"


def test_source_is_pure_and_does_not_read_runtime_or_network() -> None:
    source_path = Path(__file__).resolve().parents[1] / "alr_outcome_feedback.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_imports = {
        "os",
        "subprocess",
        "socket",
        "psycopg2",
        "psycopg",
        "requests",
        "httpx",
    }
    forbidden_calls = {"connect", "request", "run", "Popen", "system", "remove", "unlink"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {alias.name for alias in node.names} & forbidden_imports
        if isinstance(node, ast.ImportFrom):
            assert node.module not in forbidden_imports
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls
