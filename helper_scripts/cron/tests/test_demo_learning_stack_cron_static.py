"""Static contract tests for install_demo_learning_stack_crons.sh."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

CRON_DIR = Path(__file__).resolve().parents[1]
STACK_INSTALLER = CRON_DIR / "install_demo_learning_stack_crons.sh"


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_bash_syntax_ok() -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = subprocess.run(
        ["bash", "-n", str(STACK_INSTALLER)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_executable_strict_mode_and_linux_only() -> None:
    src = _src(STACK_INSTALLER)
    assert STACK_INSTALLER.stat().st_mode & 0o111
    assert "set -euo pipefail" in src
    assert "install_demo_learning_stack_crons.sh requires Linux runtime" in src


def test_stack_wraps_both_installers_without_direct_crontab_write() -> None:
    src = _src(STACK_INSTALLER)
    assert "install_demo_learning_evidence_audit_cron.sh" in src
    assert "install_cost_gate_learning_lane_cron.sh" in src
    assert "cost_gate_learning_lane_cron.sh" in src
    assert "OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY=1" in src
    assert "OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1" in src
    assert "OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY=0" in src
    assert "OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=0" in src
    assert "( crontab -l" not in src
    assert "| crontab -" not in src


def test_apply_is_stack_gated_and_expected_head_required() -> None:
    src = _src(STACK_INSTALLER)
    assert "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY" in src
    assert "DRY-RUN: not modifying crontab." in src
    assert "OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" in src
    assert "OPENCLAW_EXPECTED_SOURCE_HEAD" in src
    assert "_validate_sha_prefix" in src
    assert "runtime source HEAD mismatch" in src
    assert "runtime source is dirty" in src
    assert "git -C \"$OPENCLAW_BASE_DIR\" status --porcelain" in src


def test_preflight_runs_before_any_child_apply_install() -> None:
    src = _src(STACK_INSTALLER)
    assert "build_cost_gate_learning_lane_activation_preflight" in src
    assert "read-only stack preflight; no crontab edit performed by this check" in src
    assert "OPENCLAW_COST_GATE_LEARNING_PREINSTALL_REFRESH_ONLY=1" in src
    assert "Running read-only/artifact-only Cost Gate preinstall refresh" in src
    apply_gate_index = src.index(
        'if [[ "${OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY:-0}" != "1" ]]'
    )
    preflight_index = src.index("    _source_head_preflight", apply_gate_index)
    refresh_index = src.index("    _run_preinstall_refresh", apply_gate_index)
    plan_preflight_index = src.index("    _cost_gate_plan_preflight", apply_gate_index)
    install_index = src.index("_install_children", plan_preflight_index)
    assert preflight_index < refresh_index < plan_preflight_index < install_index


def test_remove_is_reversible_through_child_installers() -> None:
    src = _src(STACK_INSTALLER)
    assert "--remove" in src
    assert "Removing Cost Gate learning cron first" in src
    assert '"$COST_INSTALLER" --remove' in src
    assert '"$DEMO_INSTALLER" --remove' in src
    assert 'OPENCLAW_COST_GATE_LEARNING_CRON_APPLY="${OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY:-0}"' in src
    assert 'OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY="${OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY:-0}"' in src


def test_no_trading_or_runtime_mutation_tokens() -> None:
    src = _src(STACK_INSTALLER)
    forbidden = (
        "/home/ncyu",
        "/Users/",
        "OPENCLAW_ALLOW_MAINNET",
        "authorization.json",
        "restart_all.sh",
        "systemctl",
        "place_order",
        "cancel_order",
        "live_authorization",
        "git pull",
        "git fetch",
        "git reset",
    )
    for token in forbidden:
        assert token not in src
