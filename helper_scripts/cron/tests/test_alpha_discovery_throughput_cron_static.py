"""Static contract tests for alpha_discovery_throughput_cron.sh."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

CRON_DIR = Path(__file__).resolve().parents[1]
WRAPPER = CRON_DIR / "alpha_discovery_throughput_cron.sh"


def _src() -> str:
    return WRAPPER.read_text(encoding="utf-8")


def test_bash_syntax_ok() -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = subprocess.run(["bash", "-n", str(WRAPPER)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_wrapper_refreshes_activation_packet_before_alpha_runner() -> None:
    src = _src()
    assert "set -euo pipefail" in src
    assert "demo_learning_stack_activation_packet.py" in src
    assert "demo_learning_stack_activation_packet_latest.json" in src
    assert "demo_learning_stack_activation_packet_stdout.json" in src
    assert "--json-output" in src
    assert "activation_packet_refresh rc=" in src
    assert "alpha_discovery_throughput.runtime_runner" in src
    assert src.index("demo_learning_stack_activation_packet.py") < src.index(
        "alpha_discovery_throughput.runtime_runner"
    )


def test_wrapper_keeps_refresh_artifact_only() -> None:
    src = _src()
    assert "OPENCLAW_DATA_DIR" in src
    assert "OPENCLAW_BASE_DIR" in src
    assert "crontab -" not in src
    assert "git pull" not in src
    assert "git reset" not in src
    assert "restart_all.sh" not in src
    assert "systemctl" not in src
    assert "OPENCLAW_ALLOW_MAINNET" not in src
    assert "authorization.json" not in src
    assert "place_order" not in src
    assert "cancel_order" not in src
