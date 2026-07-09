from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ml_training.alr_scanner_statistical_experiment import (
    AlrScannerStatisticalExperimentError,
    build_scanner_statistical_experiment,
    compute_scanner_statistical_experiment_hash,
    validate_scanner_statistical_experiment,
)


def _cycle(
    ordinal: int,
    *,
    symbols: list[str],
    added: list[str],
) -> dict[str, object]:
    return {
        "source_hash": f"{ordinal:064x}",
        "source_key": f"scan-{ordinal}|2026-07-09T12:0{ordinal}:00Z",
        "source_ts": f"2026-07-09T12:0{ordinal}:00Z",
        "canonical_payload": {
            "ts": f"2026-07-09T12:0{ordinal}:00Z",
            "scan_id": f"scan-{ordinal}",
            "active_symbols": symbols,
            "added": added,
            "removed": [],
            "rejected_count": 0,
            "scan_duration_ms": 5,
            "candidates": [{"symbol": symbol, "final_score": ordinal} for symbol in symbols],
            "config": {"scanner_revision": "v1"},
        },
    }


def _cycles() -> list[dict[str, object]]:
    return [
        _cycle(1, symbols=["ALPHAUSDT", "BETAUSDT", "GAMMAUSDT"], added=["ALPHAUSDT"]),
        _cycle(2, symbols=["ALPHAUSDT", "BETAUSDT", "GAMMAUSDT"], added=[]),
        _cycle(3, symbols=["ALPHAUSDT", "BETAUSDT", "GAMMAUSDT"], added=[]),
        _cycle(4, symbols=["ALPHAUSDT", "BETAUSDT", "GAMMAUSDT"], added=[]),
    ]


def test_builds_pit_research_experiment_and_deferred_challenger() -> None:
    result = build_scanner_statistical_experiment(
        source_head="a" * 40,
        cycles=_cycles(),
    )

    validation = validate_scanner_statistical_experiment(result)
    assert validation.valid is True
    assert result["learning_target"]["selected_target"]["candidate_scope"]["symbol"] == "ALPHAUSDT"
    assert result["pit_dataset_manifest"]["verdict"] == "research_only"
    assert result["pit_dataset_manifest"]["point_in_time"] is True
    assert result["pit_dataset_manifest"]["future_data_allowed"] is False
    assert result["statistical_experiment"]["statistical_experiment_performed"] is True
    assert result["statistical_experiment"]["model_training_performed"] is False
    assert result["candidate_artifact"]["after_cost_evaluation"]["status"] == "DEFER_EVIDENCE"
    assert result["candidate_artifact"]["serving_ready"] is False
    assert result["candidate_artifact"]["promotion_ready"] is False
    assert result["experiment_hash"] == compute_scanner_statistical_experiment_hash(result)
    assert {item["artifact_kind"] for item in result["artifacts"]} == {
        "learning_target",
        "pit_dataset",
        "statistical_experiment",
        "candidate_artifact",
        "defer_evidence",
    }
    assert all(value is False for value in result["no_authority"].values())
    assert all(value == 0 for value in result["authority_counters"].values())


def test_is_deterministic_across_input_order() -> None:
    forward = build_scanner_statistical_experiment(source_head="b" * 40, cycles=_cycles())
    reverse = build_scanner_statistical_experiment(
        source_head="b" * 40,
        cycles=list(reversed(_cycles())),
    )

    assert forward["experiment_hash"] == reverse["experiment_hash"]
    assert forward["run"]["source_set_hash"] == reverse["run"]["source_set_hash"]


def test_rejects_duplicate_sources_and_missing_candidates() -> None:
    duplicate = _cycles()
    duplicate.append(dict(duplicate[0]))
    with pytest.raises(AlrScannerStatisticalExperimentError, match="source_hash_duplicate"):
        build_scanner_statistical_experiment(source_head="c" * 40, cycles=duplicate)

    no_candidates = _cycles()
    no_candidates[0] = _cycle(1, symbols=[], added=[])
    with pytest.raises(AlrScannerStatisticalExperimentError, match="source_candidates_empty"):
        build_scanner_statistical_experiment(source_head="c" * 40, cycles=no_candidates)


def test_rejects_tampered_after_cost_or_authority_claim() -> None:
    result = build_scanner_statistical_experiment(source_head="d" * 40, cycles=_cycles())
    result["candidate_artifact"]["after_cost_evaluation"]["status"] = "EVIDENCE_READY"
    result["experiment_hash"] = compute_scanner_statistical_experiment_hash(result)

    validation = validate_scanner_statistical_experiment(result)
    assert validation.valid is False
    assert validation.reason == "after_cost_status_invalid"


def test_source_is_pure_and_has_no_runtime_or_training_imports() -> None:
    source_path = Path(__file__).resolve().parents[1] / "alr_scanner_statistical_experiment.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_imports = {
        "os",
        "subprocess",
        "socket",
        "psycopg2",
        "psycopg",
        "requests",
        "httpx",
        "numpy",
        "sklearn",
        "torch",
    }
    forbidden_calls = {"connect", "request", "run", "Popen", "system", "remove", "unlink"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {alias.name for alias in node.names} & forbidden_imports
        if isinstance(node, ast.ImportFrom):
            assert node.module not in forbidden_imports
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls
