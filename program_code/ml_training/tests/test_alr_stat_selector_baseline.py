from __future__ import annotations

import ast
import copy
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from ml_training.alr_stat_selector_baseline import (
    ALR_STAT_SELECTOR_BASELINE_FIELD,
    BOUNDARY_LABEL,
    DECISION_BLOCKED_BOUNDARY,
    DECISION_DEFER_EVIDENCE,
    DECISION_HYPOTHESIS_ONLY,
    DECISION_ROTATED,
    DECISION_SELECT_TARGET,
    DECISION_STOP_NO_EDGE,
    INPUT_SCHEMA_VERSION,
    OBJECTIVE,
    OUTPUT_SCHEMA_VERSION,
    AlrStatSelectorBaselineError,
    build_alr_stat_selector_baseline,
    compute_selector_output_hash,
    compute_selector_snapshot_hash,
    extract_alr_stat_selector_baseline,
    validate_alr_stat_selector_baseline,
)


def _candidate(candidate_id: str = "candidate-a", **overrides) -> dict:
    candidate = {
        "identity": {
            "candidate_id": candidate_id,
            "strategy_name": "ma_crossover",
            "symbol": "NEARUSDT",
            "side": "Buy",
        },
        "evidence": {
            "pit_dataset_manifest_hash": "b" * 64,
            "matched_control_ids": ["control-near-buy-001"],
            "negative_cell_ids": ["negative-cell-near-sell-001"],
            "regime_labels": {"trend": "range", "volatility": "normal"},
        },
        "stats": {
            "candidate_net_bps_mean": 12.0,
            "candidate_net_bps_std": 12.0,
            "candidate_oos_n": 80.0,
            "matched_control_net_bps_mean": 2.0,
            "matched_control_net_bps_std": 8.0,
            "matched_control_oos_n": 64.0,
        },
        "terms": {
            "voi_bps": 2.0,
            "offline_cost_bps": 0.25,
            "governance_risk_bps": 0.5,
            "staleness_penalty_bps": 0.75,
            "evidence_gap_penalty_bps": 0.0,
        },
        "flags": {
            "frozen_universe_member": True,
            "pre_registered_split": True,
            "walk_forward_oos": True,
            "retained_if_not_selected": True,
            "proof_ready_controlled_oos_evidence": False,
        },
    }
    for key, value in overrides.items():
        if key in candidate and isinstance(candidate[key], dict) and isinstance(value, dict):
            candidate[key].update(value)
        else:
            candidate[key] = value
    return candidate


def _snapshot(**overrides) -> dict:
    snapshot = {
        "schema_version": INPUT_SCHEMA_VERSION,
        "boundary_label": BOUNDARY_LABEL,
        "created_at": "2026-07-09T00:00:00Z",
        "source_head": "a" * 40,
        "snapshot_id": "alr-stat-selector-snapshot-20260709T000000Z",
        "objective": OBJECTIVE,
        "latest_alias_used": False,
        "frozen_universe": {
            "universe_id": "source-only-near-buy-v1",
            "frozen_at": "2026-07-09T00:00:00Z",
            "candidate_ids": ["candidate-a", "candidate-b", "candidate-z"],
            "universe_hash": "c" * 64,
        },
        "pre_registered_split": {
            "split_id": "controlled-oos-split-v1",
            "split_hash": "d" * 64,
            "train_window": {"start": "2026-01-01T00:00:00Z", "end": "2026-06-01T00:00:00Z"},
            "oos_window": {"start": "2026-06-01T00:00:00Z", "end": "2026-07-01T00:00:00Z"},
            "purge": 1.0,
            "embargo": 1.0,
            "walk_forward": True,
        },
        "selector_policy": {
            "lcb_z": 1.0,
            "prior_n": 16.0,
            "prior_delta_bps": 1.0,
            "min_candidate_oos_n": 40.0,
            "min_control_oos_n": 40.0,
        },
        "proof_exclusion": {
            "proof_not_claimed": False,
            "promotion_not_claimed": False,
            "runtime_not_claimed": False,
            "trading_not_claimed": False,
        },
        "no_authority": {
            "runtime": False,
            "pg": False,
            "ipc": False,
            "bybit_mcp": False,
            "decision_lease": False,
            "order_or_probe": False,
            "cost_gate": False,
            "latest": False,
            "serving": False,
            "proof": False,
            "promotion": False,
            "delete_apply": False,
            "scheduler": False,
        },
        "candidates": [_candidate()],
    }
    snapshot.update(overrides)
    snapshot["snapshot_hash"] = compute_selector_snapshot_hash(snapshot)
    return snapshot


def _rehash(snapshot: dict) -> dict:
    snapshot["snapshot_hash"] = compute_selector_snapshot_hash(snapshot)
    return snapshot


def _write_snapshot(path: Path, snapshot: dict) -> Path:
    path.write_text(json.dumps(snapshot, sort_keys=True), encoding="utf-8")
    return path


def _run_cli(snapshot: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ml_training.alr_stat_selector_baseline",
            "--snapshot",
            str(snapshot),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[3],
        env={"PYTHONPATH": "program_code", "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=False,
    )


def test_formula_and_output_hash_validate() -> None:
    output = build_alr_stat_selector_baseline(_snapshot())

    selected = output["selected_target"]
    components = selected["score_components"]
    assert output["schema_version"] == OUTPUT_SCHEMA_VERSION
    assert output["decision"] == DECISION_SELECT_TARGET
    assert components["delta"] == pytest.approx(10.0)
    assert components["shrinkage_weight"] == pytest.approx(0.8)
    assert components["shrunk_delta"] == pytest.approx(8.2)
    assert components["se"] == pytest.approx(math.sqrt(2.8))
    assert components["conservative_lcb"] == pytest.approx(8.2 - math.sqrt(2.8))
    assert selected["score"] == pytest.approx(8.2 - math.sqrt(2.8) + 0.5)
    assert output["selector_hash"] == compute_selector_output_hash(output)
    assert validate_alr_stat_selector_baseline(output).valid is True
    assert extract_alr_stat_selector_baseline(output)["selector_hash"] == output["selector_hash"]
    assert extract_alr_stat_selector_baseline({ALR_STAT_SELECTOR_BASELINE_FIELD: output})["decision"] == DECISION_SELECT_TARGET


def test_deterministic_tie_break_selects_lexicographic_candidate_id() -> None:
    snapshot = _snapshot(
        candidates=[
            _candidate("candidate-b"),
            _candidate("candidate-a"),
        ]
    )

    output = build_alr_stat_selector_baseline(snapshot)

    assert [candidate["candidate_id"] for candidate in output["candidates"]] == [
        "candidate-a",
        "candidate-b",
    ]
    assert output["selected_target"]["candidate_id"] == "candidate-a"


def test_retains_non_selected_candidates() -> None:
    lower = _candidate(
        "candidate-z",
        stats={
            "candidate_net_bps_mean": 3.0,
            "matched_control_net_bps_mean": 2.0,
        },
    )
    output = build_alr_stat_selector_baseline(
        _snapshot(candidates=[_candidate("candidate-a"), lower])
    )

    assert output["selected_target"]["candidate_id"] == "candidate-a"
    assert [candidate["candidate_id"] for candidate in output["retained_non_selected_candidates"]] == [
        "candidate-z"
    ]
    assert {candidate["candidate_id"] for candidate in output["candidates"]} == {
        "candidate-a",
        "candidate-z",
    }


@pytest.mark.parametrize(
    ("field", "gap"),
    [
        ("pit_dataset_manifest_hash", "missing_pit_dataset_manifest_hash"),
        ("matched_control_ids", "missing_matched_control_ids"),
        ("negative_cell_ids", "missing_negative_cell_ids"),
        ("regime_labels", "missing_regime_labels"),
    ],
)
def test_missing_required_evidence_gates_defer_evidence(field: str, gap: str) -> None:
    candidate = _candidate()
    evidence = copy.deepcopy(candidate["evidence"])
    evidence.pop(field)
    candidate["evidence"] = evidence
    output = build_alr_stat_selector_baseline(
        _snapshot(candidates=[candidate])
    )

    assert output["decision"] == DECISION_DEFER_EVIDENCE
    assert output["selected_target"] is None
    assert gap in output["decision_reasons"]
    assert gap in output["candidates"][0]["evidence_gaps"]


@pytest.mark.parametrize("field", ["frozen_at", "candidate_ids", "universe_hash"])
def test_missing_frozen_universe_fields_rejected(field: str) -> None:
    snapshot = _snapshot()
    snapshot["frozen_universe"].pop(field)
    _rehash(snapshot)

    with pytest.raises(AlrStatSelectorBaselineError, match="frozen_universe_missing_fields"):
        build_alr_stat_selector_baseline(snapshot)


def test_missing_split_hash_and_walk_forward_false_rejected() -> None:
    missing_hash = _snapshot()
    missing_hash["pre_registered_split"].pop("split_hash")
    _rehash(missing_hash)
    with pytest.raises(AlrStatSelectorBaselineError, match="pre_registered_split_missing_fields:split_hash"):
        build_alr_stat_selector_baseline(missing_hash)

    walk_forward_false = _snapshot()
    walk_forward_false["pre_registered_split"]["walk_forward"] = False
    _rehash(walk_forward_false)
    with pytest.raises(AlrStatSelectorBaselineError, match="pre_registered_split_walk_forward_not_true"):
        build_alr_stat_selector_baseline(walk_forward_false)


def test_missing_stats_raw_fields_rejected() -> None:
    candidate = _candidate()
    candidate["stats"].pop("matched_control_net_bps_std")
    snapshot = _snapshot(candidates=[candidate])

    with pytest.raises(AlrStatSelectorBaselineError, match="candidate_stats_missing_fields:matched_control_net_bps_std"):
        build_alr_stat_selector_baseline(snapshot)


def test_min_oos_threshold_defer_evidence() -> None:
    candidate = _candidate(
        stats={
            "candidate_oos_n": 39.0,
            "matched_control_oos_n": 38.0,
        }
    )

    output = build_alr_stat_selector_baseline(_snapshot(candidates=[candidate]))

    assert output["decision"] == DECISION_DEFER_EVIDENCE
    assert output["selected_target"] is None
    assert output["decision_reasons"] == [
        "candidate_oos_n_below_min",
        "matched_control_oos_n_below_min",
    ]


def test_walk_forward_candidate_flag_false_defer_evidence() -> None:
    output = build_alr_stat_selector_baseline(
        _snapshot(candidates=[_candidate(flags={"walk_forward_oos": False})])
    )

    assert output["decision"] == DECISION_DEFER_EVIDENCE
    assert output["selected_target"] is None
    assert output["decision_reasons"] == ["walk_forward_oos_not_true"]


def test_latest_input_output_and_nested_ref_rejected(tmp_path: Path) -> None:
    case_dir = tmp_path.parent / "selector_case_latest_checks"
    case_dir.mkdir(exist_ok=True)
    latest_dir = case_dir / "snap_latest"
    latest_dir.mkdir()
    snapshot_path = _write_snapshot(latest_dir / "snapshot.json", _snapshot())
    result = _run_cli(snapshot_path, case_dir / "out.json")
    assert result.returncode != 0
    assert "snapshot_path_latest_rejected" in result.stderr

    clean_case_dir = tmp_path.parent / "selector_case_clean"
    clean_case_dir.mkdir(exist_ok=True)
    snapshot_path = _write_snapshot(clean_case_dir / "snapshot.json", _snapshot())
    out_dir = clean_case_dir / "out_latest"
    result = _run_cli(snapshot_path, out_dir / "selector.json")
    assert result.returncode != 0
    assert "out_path_latest_rejected" in result.stderr
    assert not (out_dir / "selector.json").exists()

    nested = _snapshot(source_refs={"packet": "selector_latest.json"})
    nested["snapshot_hash"] = compute_selector_snapshot_hash(nested)
    result = _run_cli(
        _write_snapshot(clean_case_dir / "nested.json", nested),
        clean_case_dir / "nested_out.json",
    )
    assert result.returncode != 0
    assert "source_ref_latest_rejected" in result.stderr


def test_hash_mismatch_rotates_instead_of_selecting(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot["candidates"][0]["stats"]["delta"] = 99.0
    snapshot_path = _write_snapshot(tmp_path / "snapshot.json", snapshot)
    out = tmp_path / "selector.json"

    result = _run_cli(snapshot_path, out)

    assert result.returncode == 0, result.stderr
    output = json.loads(out.read_text(encoding="utf-8"))
    assert output["decision"] == DECISION_ROTATED
    assert output["selected_target"] is None
    assert output["input_snapshot_ref"]["snapshot_hash_matches"] is False
    assert output["decision_reasons"] == ["snapshot_hash_mismatch"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda snap: snap["no_authority"].__setitem__("runtime", True),
        lambda snap: snap["candidates"][0]["flags"].__setitem__("order_authority_granted", True),
    ],
)
def test_authority_alias_contamination_blocks_boundary(mutation) -> None:
    snapshot = _snapshot()
    mutation(snapshot)
    snapshot["snapshot_hash"] = compute_selector_snapshot_hash(snapshot)

    output = build_alr_stat_selector_baseline(snapshot)

    assert output["decision"] == DECISION_BLOCKED_BOUNDARY
    assert output["selected_target"] is None
    assert all(value == 0 for value in output["authority_counters"].values())
    assert all(value is False for value in output["no_authority"].values())
    assert output["proof_ready"] is False
    assert output["promotion_ready"] is False
    assert output["runtime_ready"] is False
    assert output["trading_ready"] is False


def test_stop_no_edge_requires_explicit_proof_ready_controlled_oos_gate() -> None:
    no_edge_candidate = _candidate(
        stats={
            "candidate_net_bps_mean": 1.0,
            "candidate_net_bps_std": 2.0,
            "candidate_oos_n": 80.0,
            "matched_control_net_bps_mean": 2.0,
            "matched_control_net_bps_std": 2.0,
            "matched_control_oos_n": 64.0,
        },
        terms={
            "voi_bps": 0.0,
            "offline_cost_bps": 0.0,
            "governance_risk_bps": 0.0,
            "staleness_penalty_bps": 0.0,
            "evidence_gap_penalty_bps": 0.0,
        },
    )

    hypothesis = build_alr_stat_selector_baseline(_snapshot(candidates=[no_edge_candidate]))
    stopped = build_alr_stat_selector_baseline(
        _snapshot(candidates=[no_edge_candidate], proof_ready_controlled_oos_evidence=True)
    )

    assert hypothesis["decision"] == DECISION_HYPOTHESIS_ONLY
    assert stopped["decision"] == DECISION_STOP_NO_EDGE
    assert stopped["decision_reasons"] == ["proof_ready_controlled_oos_no_positive_score"]


def test_static_guard_no_forbidden_imports_or_calls() -> None:
    source_path = (
        Path(__file__).resolve().parents[1] / "alr_stat_selector_baseline.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_imports = {
        "os",
        "subprocess",
        "socket",
        "requests",
        "httpx",
        "urllib",
        "sqlite3",
        "psycopg2",
        "asyncpg",
        "ml_training.alr_local_runner",
    }
    forbidden_calls = {
        "connect",
        "request",
        "urlopen",
        "run",
        "Popen",
        "system",
        "remove",
        "unlink",
        "replace",
        "rename",
        "rmtree",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported = {alias.name for alias in node.names}
            assert not imported & forbidden_imports
        if isinstance(node, ast.ImportFrom):
            assert node.module not in forbidden_imports
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_calls
