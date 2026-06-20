"""Static contract tests for flash_dip_l1_short_exit_replay_cron.sh."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

CRON_DIR = Path(__file__).resolve().parents[1]
WRAPPER = CRON_DIR / "flash_dip_l1_short_exit_replay_cron.sh"


def _src() -> str:
    return WRAPPER.read_text(encoding="utf-8")


def test_bash_syntax_ok() -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = subprocess.run(["bash", "-n", str(WRAPPER)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_executable_strict_mode_and_portable_bash() -> None:
    src = _src()
    assert WRAPPER.stat().st_mode & 0o111
    assert "set -euo pipefail" in src
    assert "mapfile" not in src
    assert ":-{}}" not in src


def test_read_only_pg_and_runtime_boundaries() -> None:
    src = _src()
    assert 'PGOPTIONS="-c default_transaction_read_only=on"' in src
    assert "basic_system_services.env" in src
    assert "POSTGRES_PASSWORD" in src
    assert "shallow_retune_l1_short_exit_replay.py" in src
    assert "PYTHONPATH" in src
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


def test_local_artifact_log_lock_and_status_surfaces() -> None:
    src = _src()
    assert "flash_dip_l1_short_exit_replay_cron.lock.d" in src
    assert "flash_dip_l1_short_exit_replay.last_fire" in src
    assert "flash_dip_l1_short_exit_replay_cron.log" in src
    assert "flash_dip_l1_short_exit_replay.log" in src
    assert "shallow_retune_l1_short_exit_replay_latest.json" in src
    assert "counterfactual_only_not_promotion_evidence" in src
    assert "events_with_l1_in_event_window" in src
    assert "events_missing_l1_in_event_window" in src
    assert "event_window_l1_relation_counts" in src
    assert "dominant_missing_event_window_l1_relation" in src


def test_operator_knobs_match_replay_gate_defaults() -> None:
    src = _src()
    for key in (
        "OPENCLAW_FLASH_DIP_L1_REPLAY_K_PCT:-6",
        "OPENCLAW_FLASH_DIP_L1_REPLAY_HOLD:-2",
        "OPENCLAW_FLASH_DIP_L1_REPLAY_CAP:-3",
        "OPENCLAW_FLASH_DIP_L1_REPLAY_NOTIONAL_FRAC:-0.005",
        "OPENCLAW_FLASH_DIP_L1_REPLAY_HORIZON_MINUTES:-15,60,240",
        "OPENCLAW_FLASH_DIP_L1_REPLAY_QUEUE_AHEAD_FRACS:-0,0.5,1",
        "OPENCLAW_FLASH_DIP_L1_REPLAY_GATE_QUEUE_AHEAD_FRAC:-1",
        "OPENCLAW_FLASH_DIP_L1_REPLAY_GATE_HORIZON_MINUTES:-240",
        "OPENCLAW_FLASH_DIP_L1_REPLAY_MIN_FILLED:-30",
        "OPENCLAW_FLASH_DIP_L1_REPLAY_MIN_DAYS:-20",
    ):
        assert key in src


def test_no_hardcoded_user_paths() -> None:
    src = _src()
    assert "/home/ncyu" not in src
    assert "/Users/" not in src
