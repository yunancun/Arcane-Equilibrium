"""Static contract tests for fill_sim_refresh_cron.sh.

The wrapper is allowed to refresh local fill_sim artifacts only. These tests do
not execute the job body; they pin the cron safety envelope and operator knobs.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

CRON_DIR = Path(__file__).resolve().parents[1]
WRAPPER = CRON_DIR / "fill_sim_refresh_cron.sh"


def _src() -> str:
    return WRAPPER.read_text(encoding="utf-8")


def test_bash_syntax_ok() -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = subprocess.run(["bash", "-n", str(WRAPPER)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_executable_and_strict_mode() -> None:
    assert WRAPPER.stat().st_mode & 0o111, "fill_sim_refresh_cron.sh must be executable"
    assert "set -euo pipefail" in _src()
    assert "mapfile" not in _src()  # macOS system bash is 3.2.
    assert ":-{}}" not in _src()  # bash parses this as a trailing literal brace.


def test_bounded_freshness_defaults_and_force_override() -> None:
    src = _src()
    assert 'OPENCLAW_FILL_SIM_HOURS:-2' in src
    assert 'OPENCLAW_FILL_SIM_MAX_AGE_H:-60' in src
    assert 'OPENCLAW_FILL_SIM_STALE_ALERT_H:-72' in src
    assert "OPENCLAW_FILL_SIM_FORCE" in src
    assert "skipped_fresh" in src


def test_runs_fill_sim_module_with_read_only_pg() -> None:
    src = _src()
    assert "program_code.research.microstructure.fill_sim" in src
    assert '--out "$REPORT"' in src
    assert 'PGOPTIONS="-c default_transaction_read_only=on"' in src
    assert "basic_system_services.env" in src
    assert "POSTGRES_PASSWORD" in src


def test_lock_heartbeat_status_and_alert_surfaces() -> None:
    src = _src()
    assert "fill_sim_refresh_cron.lock.d" in src
    assert "fill_sim_refresh.last_fire" in src
    assert "fill_sim_refresh.log" in src
    assert "fill_sim_refresh_cron.log" in src
    assert "alerts.jsonl" in src
    assert "refresh_failed" in src


def test_optional_cli_knobs_are_env_only() -> None:
    src = _src()
    for key in (
        "OPENCLAW_FILL_SIM_SINCE",
        "OPENCLAW_FILL_SIM_UNTIL",
        "OPENCLAW_FILL_SIM_CLEAN_SINCE",
        "OPENCLAW_FILL_SIM_CADENCE_S",
        "OPENCLAW_FILL_SIM_SKIP_QUANTILE",
        "OPENCLAW_FILL_SIM_HORIZONS",
        "OPENCLAW_FILL_SIM_MIN_L1_EVENTS",
    ):
        assert key in src


def test_no_trading_runtime_or_private_exchange_paths() -> None:
    src = _src()
    forbidden = (
        "OPENCLAW_ALLOW_MAINNET",
        "authorization.json",
        "restart_all.sh",
        "systemctl",
        "place_order",
        "cancel_order",
        "live_authorization",
    )
    for token in forbidden:
        assert token not in src


def test_no_hardcoded_user_paths() -> None:
    src = _src()
    assert "/home/ncyu" not in src
    assert "/Users/" not in src
