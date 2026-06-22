"""Static contract tests for the sealed-horizon preflight cron wrapper."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

CRON_DIR = Path(__file__).resolve().parents[1]
WRAPPER = CRON_DIR / "sealed_horizon_probe_preflight_cron.sh"
INSTALLER = CRON_DIR / "install_sealed_horizon_probe_preflight_cron.sh"


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_bash_syntax_ok() -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    for script in (WRAPPER, INSTALLER):
        proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert proc.returncode == 0, f"{script}: {proc.stderr}"


def test_scripts_executable_strict_mode_and_linux_only_installer() -> None:
    for script in (WRAPPER, INSTALLER):
        assert script.stat().st_mode & 0o111, f"{script.name} not executable"
        assert "set -euo pipefail" in _src(script)
    installer_src = _src(INSTALLER)
    assert "install_sealed_horizon_probe_preflight_cron.sh requires Linux runtime" in installer_src


def test_wrapper_refreshes_sealed_preflight_artifacts_and_status() -> None:
    src = _src(WRAPPER)
    assert "sealed_horizon_probe_preflight_cron.lock.d" in src
    assert "sealed_horizon_probe_preflight.last_fire" in src
    assert "sealed_horizon_probe_preflight_cron.log" in src
    assert "sealed_horizon_probe_preflight.log" in src
    assert "sealed_horizon_probe_preflight_${STAMP}.json" in src
    assert "sealed_horizon_probe_preflight_${STAMP}.md" in src
    assert "sealed_horizon_probe_preflight_latest.json" in src
    assert "sealed_horizon_probe_preflight_latest.md" in src
    assert "cost_gate_learning_lane.sealed_horizon_probe_preflight" in src
    assert "--sealed-horizon-learning-evidence-json" in src
    assert "--decision-packet-search-root" in src
    assert "--activation-preflight-json" in src
    assert "--stack-health-json" in src
    assert "--operator-review-json" in src
    assert "SEALED_HORIZON_EVIDENCE_MISSING" in src
    assert "sealed_horizon_probe_preflight_refresh_status_v1" in src
    assert "selected_decision_packet_path" in src
    assert "decision_packet_aligned" in src
    assert "operator_review_recorded" in src
    assert "production_learning_lane_accumulating" in src
    assert "blocking_gates" in src
    assert "artifact_only_no_pg_bybit_order_auth_risk_runtime_cost_gate_or_probe_authority" in src
    assert src.rstrip().endswith("exit 0")


def test_wrapper_knobs_are_namespaced_and_fail_soft() -> None:
    src = _src(WRAPPER)
    assert "OPENCLAW_SEALED_HORIZON_LEARNING_EVIDENCE_JSON" in src
    assert "OPENCLAW_SEALED_HORIZON_DECISION_PACKET_JSON" in src
    assert "OPENCLAW_SEALED_HORIZON_DECISION_PACKET_SEARCH_ROOT" in src
    assert "OPENCLAW_SEALED_HORIZON_ACTIVATION_PREFLIGHT_JSON" in src
    assert "OPENCLAW_SEALED_HORIZON_STACK_HEALTH_JSON" in src
    assert "OPENCLAW_SEALED_HORIZON_OPERATOR_REVIEW_JSON" in src
    assert "OPENCLAW_SEALED_HORIZON_PREFLIGHT_MAX_ARTIFACT_AGE_HOURS" in src
    assert "OPENCLAW_SEALED_HORIZON_PREFLIGHT_STALE_LOCK_MIN" in src
    assert 'validate_int "OPENCLAW_SEALED_HORIZON_PREFLIGHT_STALE_LOCK_MIN"' in src
    assert 'validate_int "OPENCLAW_SEALED_HORIZON_PREFLIGHT_MAX_ARTIFACT_AGE_HOURS"' in src
    assert "must be in [1, 336]" in src
    assert "write_status \"PREFLIGHT_PACKAGE_MISSING\"" in src
    assert "write_status \"SEALED_HORIZON_EVIDENCE_MISSING\"" in src
    assert "write_status \"\"" in src
    assert "fail-soft" in src


def test_installer_is_dry_run_gated_expected_head_aware_and_reversible() -> None:
    src = _src(INSTALLER)
    assert "OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_APPLY" in src
    assert "DRY-RUN: not modifying crontab." in src
    assert "sealed_horizon_probe_preflight_cron.sh" in src
    assert "OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD" in src
    assert "OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" in src
    assert "OPENCLAW_EXPECTED_SOURCE_HEAD" in src
    assert "OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_MINUTES:-22" in src
    assert "OPENCLAW_SEALED_HORIZON_PREFLIGHT_REQUIRE_EXPECTED_HEAD" in src
    assert "_validate_sha_prefix" in src
    assert "--remove" in src
    assert "grep -v \"$MARKER\"" in src
    assert "( crontab -l" in src
    assert "| crontab -" in src
    assert "no crontab write without apply" in src
    assert "probe authority" in src


def test_wrapper_does_not_touch_trading_or_runtime_authority_surfaces() -> None:
    src = _src(WRAPPER)
    forbidden = (
        "/home/ncyu",
        "/Users/",
        "OPENCLAW_ALLOW_MAINNET",
        "authorization.json",
        "create_order",
        "place_order",
        "cancel_order",
        "live_authorization",
        "restart_all.sh",
        "systemctl",
        "crontab -",
        "PGOPTIONS",
        "POSTGRES_",
        "psql",
        "bybit_connector",
    )
    for token in forbidden:
        assert token not in src


def test_installer_does_not_touch_trading_or_runtime_authority_surfaces() -> None:
    src = _src(INSTALLER)
    forbidden = (
        "/home/ncyu",
        "/Users/",
        "OPENCLAW_ALLOW_MAINNET",
        "authorization.json",
        "create_order",
        "place_order",
        "cancel_order",
        "live_authorization",
        "restart_all.sh",
        "systemctl",
        "PGOPTIONS",
        "POSTGRES_",
        "psql",
        "bybit_connector",
    )
    for token in forbidden:
        assert token not in src
