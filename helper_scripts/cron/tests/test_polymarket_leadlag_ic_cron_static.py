"""Static contract tests for polymarket_leadlag_ic cron wrapper."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

CRON_DIR = Path(__file__).resolve().parents[1]
WRAPPER = CRON_DIR / "polymarket_leadlag_ic_cron.sh"
INSTALLER = CRON_DIR / "install_polymarket_leadlag_ic_cron.sh"


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("script", [WRAPPER, INSTALLER], ids=["wrapper", "installer"])
def test_bash_syntax_ok(script):
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("script", [WRAPPER, INSTALLER], ids=["wrapper", "installer"])
def test_scripts_executable_and_strict_mode(script):
    assert script.stat().st_mode & 0o111, f"{script.name} not executable"
    assert "set -euo pipefail" in _src(script)


def test_wrapper_readonly_pg_and_status_artifacts_only():
    src = _src(WRAPPER)
    assert "basic_system_services.env" in src
    assert "POSTGRES_PASSWORD" in src
    assert 'PGOPTIONS="-c default_transaction_read_only=on"' in src
    assert "polymarket_leadlag_ic_cron.lock.d" in src
    assert "polymarket_leadlag_ic.last_fire" in src
    assert "polymarket_leadlag_ic.log" in src
    assert "polymarket_leadlag_latest.json" in src
    assert "polymarket_leadlag.replay_history" in src
    assert "polymarket_leadlag_replay_history_" in src
    assert "candidate_replay_history_status" in src
    assert "candidate_replay_history_evidence" in src
    assert "label_status_counts" in src
    assert "oldest_unmatured_exit_target_utc" in src
    assert "max_overlap_adjusted_ic_points" in src
    assert "preliminary_raw_candidate_count" in src
    assert "preliminary_hac_candidate_count" in src
    assert "pre_gate_hac_watchlist_count" in src
    assert "best_pre_gate_hac_watch" in src
    assert "pre_gate_watchlist_persistence_status" in src
    assert "pre_gate_watchlist_recurring_cell_count" in src
    assert "pre_gate_watchlist_persistent_cell_count" in src
    assert "pre_gate_watchlist_floor_qualified_recurring_cell_count" in src
    assert "pre_gate_watchlist_floor_qualified_persistent_cell_count" in src
    assert "pre_gate_watchlist_persistence_scorecard" in src
    assert "price_feedback_warning_count" in src
    assert "price_feedback_partial_collapse_count" in src
    assert "price_feedback_summary" in src
    assert "min_samples_remaining_to_gate" in src
    assert "sample_gate_eta_utc" in src
    assert "sample_gate_clock" in src
    assert "significance_t_stat" in src
    assert "max_abs_t_stat_hac" in src
    assert "max_bh_q" in src
    assert "PYTHONDONTWRITEBYTECODE=1" in src
    assert src.rstrip().endswith("exit 0")


def test_wrapper_invokes_harness_with_fail_closed_defaults():
    src = _src(WRAPPER)
    assert "OPENCLAW_POLYMARKET_LEADLAG_QUERY_SET" in src
    assert ":-v2}" in src
    assert "OPENCLAW_POLYMARKET_LEADLAG_SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT" in src
    assert "OPENCLAW_POLYMARKET_LEADLAG_MIN_POINTS:-30" in src
    assert "-m polymarket_leadlag.harness" in src
    assert "--query-set" in src
    assert "--mode" in src
    assert "--write-latest" in src
    assert "--price-timeframe" in src


def test_installer_active_hourly_after_collector_and_apply_gated():
    src = _src(INSTALLER)
    assert 'OPENCLAW_POLYMARKET_LEADLAG_CRON_MINUTES="${OPENCLAW_POLYMARKET_LEADLAG_CRON_MINUTES:-17}"' in src
    assert "OPENCLAW_POLYMARKET_LEADLAG_SYMBOLS" in src
    assert "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT" in src
    assert 'ENTRY="${OPENCLAW_POLYMARKET_LEADLAG_CRON_MINUTES} * * * *' in src
    assert '_validate_cron_minute_list "OPENCLAW_POLYMARKET_LEADLAG_CRON_MINUTES"' in src
    assert "2,17,32,47" in src
    assert "after polymarket_axis collector cadence" in src
    assert "OPENCLAW_POLYMARKET_LEADLAG_CRON_APPLY" in src
    assert "--remove" in src
    assert 'MARKER="polymarket_leadlag_ic_cron.sh"' in src
    assert 'grep -q "$MARKER"' in src


@pytest.mark.parametrize("script", [WRAPPER, INSTALLER], ids=["wrapper", "installer"])
def test_no_hardcoded_user_paths_or_trading_tokens(script):
    src = _src(script)
    forbidden = (
        "/home/ncyu",
        "/Users/",
        "OPENCLAW_ALLOW_MAINNET",
        "authorization.json",
        "create_order",
        "place_order",
    )
    for token in forbidden:
        assert token not in src
