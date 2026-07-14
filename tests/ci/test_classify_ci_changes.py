from __future__ import annotations

import subprocess
import sys

from helper_scripts.ci.classify_ci_changes import GATES, classify_paths


def test_alr_strict_default_checkpoint_keeps_expensive_gates_off() -> None:
    result = classify_paths(
        [
            "helper_scripts/research/cost_gate_learning_lane/outcome_review.py",
            "helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py",
            "helper_scripts/research/tests/test_candidate_board_v2_lineage.py",
            "helper_scripts/research/tests/test_cost_gate_evidence_methodology.py",
            "helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py",
            "helper_scripts/research/tests/"
            "test_cost_gate_sealed_horizon_learning_evidence.py",
        ]
    )
    assert result == {gate: False for gate in GATES}


def test_ci_control_plane_change_forces_every_gate() -> None:
    for path in (
        ".github/workflows/ci.yml",
        "helper_scripts/ci/classify_ci_changes.py",
    ):
        assert all(classify_paths([path]).values())


def test_categories_are_narrow_but_cover_their_own_contracts() -> None:
    result = classify_paths(
        [
            ".codex/SUBAGENT_EXECUTION_RULES.md",
            "helper_scripts/maintenance_scripts/git_loop_guard.py",
            "rust/openclaw_alr_fit_verifier/src/main.rs",
            "sql/migrations/V160__alr_atomic_fit_consumption.sql",
            "program_code/exchange_connectors/bybit_connector/"
            "control_api_v1/tests/test_stock_etf_route_static_guard.py",
        ]
    )
    assert result == {
        "governance": True,
        "alr_fit_verifier": True,
        "rust": True,
        "schema": True,
        "stock_etf": True,
    }


def test_cli_writes_nul_safe_github_outputs(tmp_path) -> None:
    output = tmp_path / "github-output"
    completed = subprocess.run(
        [
            sys.executable,
            "helper_scripts/ci/classify_ci_changes.py",
            "--null",
            "--github-output",
            str(output),
        ],
        input=b"rust/openclaw_engine/src/main.rs\0",
        check=False,
    )
    assert completed.returncode == 0
    assert output.read_text(encoding="utf-8").splitlines() == [
        "governance=false",
        "alr_fit_verifier=false",
        "rust=true",
        "schema=true",
        "stock_etf=false",
    ]
