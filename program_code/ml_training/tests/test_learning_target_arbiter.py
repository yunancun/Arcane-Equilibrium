from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ml_training.learning_target_arbiter import (
    INPUT_SCHEMA_VERSION,
    OBJECTIVE,
    OUTPUT_SCHEMA_VERSION,
    compute_manifest_hash,
    compute_runtime_hash,
)


def _target(**overrides) -> dict:
    target = {
        "target_id": "target-alpha",
        "candidate_scope": {
            "candidate_id": "grid_trading|ETHUSDT|Buy",
            "engine_mode": "demo",
        },
        "learning_question": "Which candidate should receive the next offline label budget?",
        "evidence_source_tier": "candidate_matched_fill",
        "expected_information_gain": 3.0,
        "uncertainty_reduction": 2.0,
        "cost_estimate": 1.0,
        "risk_penalty": 0.5,
        "staleness_penalty": 0.25,
        "eligibility": True,
    }
    target.update(overrides)
    return target


def _manifest(**overrides) -> dict:
    manifest = {
        "schema_version": INPUT_SCHEMA_VERSION,
        "created_at": "2026-07-09T00:00:00Z",
        "source_head": "a" * 40,
        "snapshot_id": "learning-target-snapshot-20260709T000000Z",
        "snapshot_kind": "source_only_offline_candidate_learning_targets",
        "objective": OBJECTIVE,
        "latest_alias_used": False,
        "targets": [_target()],
        "proof_exclusion": {
            "scanner_evidence_is_proof": False,
            "no_order_evidence_is_reward": False,
            "artifact_count_evidence_is_edge": False,
        },
        "no_authority": {
            "runtime": False,
            "pg": False,
            "ipc": False,
            "bybit_or_mcp": False,
            "scheduler": False,
            "service_env": False,
            "latest": False,
            "proof_or_promotion": False,
            "delete_or_apply": False,
            "cost_gate": False,
            "order_or_probe": False,
            "live_or_mainnet": False,
        },
    }
    manifest.update(overrides)
    manifest["manifest_hash"] = compute_manifest_hash(manifest)
    return manifest


def _write_manifest(path: Path, manifest: dict) -> Path:
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return path


def _clean_case_dir(tmp_path: Path, name: str) -> Path:
    case_dir = tmp_path.parent / name
    case_dir.mkdir(exist_ok=True)
    return case_dir


def _run_cli(snapshot: Path, out: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        "-m",
        "ml_training.learning_target_arbiter",
        "--snapshot",
        str(snapshot),
    ]
    if out is not None:
        cmd.extend(["--out", str(out)])
    return subprocess.run(
        cmd,
        cwd=Path(__file__).resolve().parents[3],
        env={"PYTHONPATH": "program_code", "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=False,
    )


def _all_false(value) -> bool:
    if isinstance(value, dict):
        return all(_all_false(item) for item in value.values())
    if isinstance(value, list):
        return all(_all_false(item) for item in value)
    return value is False


def test_valid_manifest_cli_writes_explicit_runtime_output(tmp_path: Path) -> None:
    snapshot = _write_manifest(tmp_path / "snapshot.json", _manifest())
    out = tmp_path / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode == 0, result.stderr
    runtime = json.loads(out.read_text(encoding="utf-8"))
    assert runtime["schema_version"] == OUTPUT_SCHEMA_VERSION
    assert runtime["objective"] == OBJECTIVE
    assert runtime["decision"] == "SELECT_TARGET"
    assert runtime["selected_target"]["target_id"] == "target-alpha"


def test_output_binds_input_manifest_hash_and_runtime_hash_validates(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    snapshot = _write_manifest(tmp_path / "snapshot.json", manifest)
    out = tmp_path / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode == 0, result.stderr
    runtime = json.loads(out.read_text(encoding="utf-8"))
    assert runtime["input_snapshot_ref"]["manifest_hash"] == manifest["manifest_hash"]
    assert runtime["runtime_hash"] == compute_runtime_hash(runtime)


def test_missing_out_exits_nonzero(tmp_path: Path) -> None:
    snapshot = _write_manifest(tmp_path / "snapshot.json", _manifest())

    result = _run_cli(snapshot)

    assert result.returncode != 0


def test_latest_input_path_rejected(tmp_path: Path) -> None:
    case_dir = _clean_case_dir(tmp_path, "case_input_rejected")
    latest_dir = case_dir / "snap_latest"
    latest_dir.mkdir()
    snapshot = _write_manifest(latest_dir / "snapshot.json", _manifest())
    out = case_dir / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode != 0
    assert "snapshot_path_latest_rejected" in result.stderr


def test_latest_input_path_rejected_case_insensitive(tmp_path: Path) -> None:
    case_dir = _clean_case_dir(tmp_path, "case_input_rejected_uppercase")
    latest_dir = case_dir / "snap_LATEST"
    latest_dir.mkdir()
    snapshot = _write_manifest(latest_dir / "snapshot.json", _manifest())
    out = case_dir / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode != 0
    assert "snapshot_path_latest_rejected" in result.stderr


def test_latest_output_path_rejected(tmp_path: Path) -> None:
    case_dir = _clean_case_dir(tmp_path, "case_output_rejected")
    snapshot = _write_manifest(case_dir / "snapshot.json", _manifest())
    out_dir = case_dir / "runtime_latest"
    out_dir.mkdir()

    result = _run_cli(snapshot, out_dir / "runtime.json")

    assert result.returncode != 0
    assert "out_path_latest_rejected" in result.stderr


def test_latest_output_path_rejected_case_insensitive(tmp_path: Path) -> None:
    case_dir = _clean_case_dir(tmp_path, "case_output_rejected_uppercase")
    snapshot = _write_manifest(case_dir / "snapshot.json", _manifest())
    out_dir = case_dir / "runtime_LATEST"
    out_dir.mkdir()

    result = _run_cli(snapshot, out_dir / "runtime.json")

    assert result.returncode != 0
    assert "out_path_latest_rejected" in result.stderr


def test_latest_alias_true_rejected_from_non_latest_filename(tmp_path: Path) -> None:
    case_dir = _clean_case_dir(tmp_path, "case_alias_rejected")
    snapshot = _write_manifest(
        case_dir / "snapshot.json",
        _manifest(latest_alias_used=True),
    )
    out = case_dir / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode != 0
    assert "latest_alias_used_rejected" in result.stderr


@pytest.mark.parametrize("value", [1, "false", None])
def test_latest_alias_must_be_exact_false(tmp_path: Path, value) -> None:
    case_dir = _clean_case_dir(tmp_path, "case_alias_flag_rejected")
    snapshot = _write_manifest(
        case_dir / "snapshot.json",
        _manifest(latest_alias_used=value),
    )
    out = case_dir / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode != 0
    assert "latest_alias_used_rejected" in result.stderr


@pytest.mark.parametrize("value", [True, 1, "false"])
def test_source_path_latest_must_be_exact_false_when_present(
    tmp_path: Path,
    value,
) -> None:
    case_dir = _clean_case_dir(tmp_path, "case_source_flag_rejected")
    snapshot = _write_manifest(
        case_dir / "snapshot.json",
        _manifest(source_path_latest=value),
    )
    out = case_dir / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode != 0
    assert "source_path_latest_rejected" in result.stderr


def test_nested_source_ref_latest_rejected(tmp_path: Path) -> None:
    case_dir = _clean_case_dir(tmp_path, "case_nested_source_ref")
    snapshot = _write_manifest(
        case_dir / "snapshot.json",
        _manifest(source_refs={"artifact": "runtime_latest.json"}),
    )
    out = case_dir / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode != 0
    assert "source_ref_latest_rejected" in result.stderr


def test_nested_source_ref_latest_rejected_case_insensitive(tmp_path: Path) -> None:
    case_dir = _clean_case_dir(tmp_path, "case_nested_source_ref_uppercase")
    snapshot = _write_manifest(
        case_dir / "snapshot.json",
        _manifest(source_refs={"artifact": "runtime_LATEST.json"}),
    )
    out = case_dir / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode != 0
    assert "source_ref_latest_rejected" in result.stderr


def test_manifest_hash_mismatch_rejected(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["targets"][0]["cost_estimate"] = 99.0
    snapshot = _write_manifest(tmp_path / "snapshot.json", manifest)
    out = tmp_path / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode != 0
    assert "manifest_hash_mismatch" in result.stderr


def test_objective_must_be_expected_value_of_information(tmp_path: Path) -> None:
    snapshot = _write_manifest(
        tmp_path / "snapshot.json",
        _manifest(objective="expected_profit"),
    )
    out = tmp_path / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode != 0
    assert "objective_invalid" in result.stderr


def test_truthy_no_authority_rejected(tmp_path: Path) -> None:
    no_authority = _manifest()["no_authority"]
    no_authority["runtime"] = True
    snapshot = _write_manifest(
        tmp_path / "snapshot.json",
        _manifest(no_authority=no_authority),
    )
    out = tmp_path / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode != 0
    assert "no_authority_truthy:runtime" in result.stderr


@pytest.mark.parametrize(
    "proof_exclusion",
    [
        {
            "scanner_evidence_is_proof": True,
            "no_order_evidence_is_reward": False,
            "artifact_count_evidence_is_edge": False,
        },
        {
            "scanner_evidence_is_proof": False,
            "no_order_evidence_is_reward": True,
            "artifact_count_evidence_is_edge": False,
        },
        {
            "scanner_evidence_is_proof": False,
            "no_order_evidence_is_reward": False,
            "artifact_count_evidence_is_edge": True,
        },
        {
            "scanner_evidence_is_proof": False,
            "no_order_evidence_is_reward": False,
            "artifact_count_evidence_is_edge": False,
            "nested": {"promotion_granted": True},
        },
    ],
)
def test_truthy_proof_exclusion_grants_rejected(
    tmp_path: Path,
    proof_exclusion: dict,
) -> None:
    snapshot = _write_manifest(
        tmp_path / "snapshot.json",
        _manifest(proof_exclusion=proof_exclusion),
    )
    out = tmp_path / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode != 0
    assert "proof_exclusion_truthy:" in result.stderr


@pytest.mark.parametrize(
    "evidence_source_tier",
    [
        "scanner",
        "Scanner",
        "no_order",
        "NO-ORDER",
        "NO ORDER",
        "artifact_count",
        "Artifact-Count",
        "Artifact Count",
    ],
)
def test_blocked_sources_cannot_set_proof_reward_edge_promotion(
    tmp_path: Path,
    evidence_source_tier: str,
) -> None:
    target = _target(
        evidence_source_tier=evidence_source_tier,
        proof_packet_ready_count=1,
    )
    snapshot = _write_manifest(tmp_path / "snapshot.json", _manifest(targets=[target]))
    out = tmp_path / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode != 0
    assert "blocked_source_tier_authority_attempt" in result.stderr


def test_deterministic_scoring_tie_break_selects_highest_eligible(
    tmp_path: Path,
) -> None:
    ineligible_high = _target(
        target_id="target-ineligible-high",
        expected_information_gain=100.0,
        uncertainty_reduction=0.0,
        cost_estimate=0.0,
        risk_penalty=0.0,
        staleness_penalty=0.0,
        eligibility=False,
    )
    eligible_tie_b = _target(
        target_id="target-b",
        expected_information_gain=4.0,
        uncertainty_reduction=1.0,
        cost_estimate=1.0,
        risk_penalty=0.0,
        staleness_penalty=0.0,
    )
    eligible_tie_a = _target(
        target_id="target-a",
        expected_information_gain=3.0,
        uncertainty_reduction=2.0,
        cost_estimate=1.0,
        risk_penalty=0.0,
        staleness_penalty=0.0,
    )
    snapshot = _write_manifest(
        tmp_path / "snapshot.json",
        _manifest(targets=[eligible_tie_b, ineligible_high, eligible_tie_a]),
    )
    out = tmp_path / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode == 0, result.stderr
    runtime = json.loads(out.read_text(encoding="utf-8"))
    assert [target["target_id"] for target in runtime["ranked_targets"]] == [
        "target-ineligible-high",
        "target-a",
        "target-b",
    ]
    assert runtime["selected_target"]["target_id"] == "target-a"


def test_authority_counters_and_flags_remain_zero_false(tmp_path: Path) -> None:
    snapshot = _write_manifest(tmp_path / "snapshot.json", _manifest())
    out = tmp_path / "runtime.json"

    result = _run_cli(snapshot, out)

    assert result.returncode == 0, result.stderr
    runtime = json.loads(out.read_text(encoding="utf-8"))
    assert runtime["candidate_matched_fills_count"] == 0
    assert runtime["proof_packet_ready_count"] == 0
    assert runtime["reward_ledger_ready_count"] == 0
    assert runtime["promotion_ready"] is False
    assert runtime["edge_proof_ready"] is False
    assert _all_false(runtime["no_authority"])
