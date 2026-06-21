"""demo_learning_evidence_audit_cron.sh 靜態契約測試。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

CRON_DIR = Path(__file__).resolve().parents[1]
WRAPPER = CRON_DIR / "demo_learning_evidence_audit_cron.sh"
INSTALLER = CRON_DIR / "install_demo_learning_evidence_audit_cron.sh"


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("script", [WRAPPER, INSTALLER], ids=["wrapper", "installer"])
def test_bash_syntax_ok(script: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("script", [WRAPPER, INSTALLER], ids=["wrapper", "installer"])
def test_executable_strict_mode_and_portable_bash(script: Path) -> None:
    src = _src(script)
    assert script.stat().st_mode & 0o111, f"{script.name} not executable"
    assert "set -euo pipefail" in src
    assert "mapfile" not in src
    assert ":-{}}" not in src


def test_read_only_pg_and_runtime_boundaries() -> None:
    src = _src(WRAPPER)
    assert "basic_system_services.env" in src
    assert "POSTGRES_PASSWORD" in src
    assert 'PGOPTIONS="-c default_transaction_read_only=on' in src
    assert "demo_learning_evidence_audit.py" in src
    assert "--repo-root" in src
    assert "--data-dir" in src
    assert "--output" in src
    assert "--json-output" in src
    assert "PYTHONDONTWRITEBYTECODE=1" in src
    forbidden = (
        "OPENCLAW_ALLOW_MAINNET",
        "authorization.json",
        "restart_all.sh",
        "systemctl",
        "place_order",
        "cancel_order",
        "live_authorization",
        "--append-ledger",
        "cost_gate_learning_lane.outcome_refresh",
        "cost_gate_learning_lane.runtime_adapter",
    )
    for token in forbidden:
        assert token not in src


def test_artifact_log_lock_heartbeat_and_status_surfaces() -> None:
    src = _src(WRAPPER)
    assert "demo_learning_evidence_audit_cron.lock.d" in src
    assert "demo_learning_evidence_audit.last_fire" in src
    assert "demo_learning_evidence_audit_cron.log" in src
    assert "demo_learning_evidence_audit.log" in src
    assert "demo_learning_evidence_audit_latest.md" in src
    assert "demo_learning_evidence_audit_latest.json" in src
    assert "classification_status" in src
    assert "cost_gate_rejects_recorded_in_pg" in src
    assert "learning_lane_ledger_rows_present" in src
    assert "blocked_outcome_review_candidate_present" in src
    assert "demo_learning_evidence_readonly_pg_artifact_source_proc_no_order_no_cost_gate_relaxation" in src
    assert src.rstrip().endswith("exit 0")


def test_operator_knobs_cover_learning_evidence_questions() -> None:
    src = _src(WRAPPER)
    for key in (
        "OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_MODES:-demo,live_demo",
        "OPENCLAW_DEMO_LEARNING_EVIDENCE_LOOKBACK_HOURS:-24",
        "OPENCLAW_DEMO_LEARNING_EVIDENCE_TOP_LIMIT:-20",
        "OPENCLAW_DEMO_LEARNING_EVIDENCE_PG_STATEMENT_TIMEOUT_MS:-180000",
        "OPENCLAW_DEMO_LEARNING_EVIDENCE_EXPECTED_HEAD",
        "OPENCLAW_DEMO_LEARNING_EVIDENCE_RUNTIME_ENV_FILE",
        "OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_PID",
        "OPENCLAW_DEMO_LEARNING_EVIDENCE_RUNTIME_PROC_ENVIRON",
        "OPENCLAW_DEMO_LEARNING_EVIDENCE_AUTO_DETECT_ENGINE_PID:-0",
        "OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_WRITER_ENABLED:-0",
        "OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_PROCESS_WRITER_ENABLED:-0",
    ):
        assert key in src
    assert "--runtime-env-file" in src
    assert "--engine-pid" in src
    assert "--runtime-proc-environ" in src
    assert "--auto-detect-engine-pid" in src
    assert "--require-writer-enabled" in src
    assert "--require-process-writer-enabled" in src
    assert 'validate_bool01 "OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_WRITER_ENABLED"' in src
    assert 'validate_bool01 "OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_PROCESS_WRITER_ENABLED"' in src


def test_installer_dry_run_apply_gate_and_reversible_entry() -> None:
    src = _src(INSTALLER)
    assert (
        'OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_MINUTES="${OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_MINUTES:-7,37}"'
        in src
    )
    assert (
        'OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_MODES="${OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_MODES:-demo,live_demo}"'
        in src
    )
    assert (
        'OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_WRITER_ENABLED="${OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_WRITER_ENABLED:-0}"'
        in src
    )
    assert (
        'OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_PROCESS_WRITER_ENABLED="${OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_PROCESS_WRITER_ENABLED:-0}"'
        in src
    )
    assert 'ENTRY="${OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_MINUTES} * * * *' in src
    assert '_validate_cron_minute_list "OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_MINUTES"' in src
    assert '_validate_bool01 "OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_WRITER_ENABLED"' in src
    assert '_append_env_if_set "OPENCLAW_DEMO_LEARNING_EVIDENCE_RUNTIME_PROC_ENVIRON"' in src
    assert "OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY" in src
    assert "DRY-RUN: not modifying crontab." in src
    assert "--remove" in src
    assert 'MARKER="demo_learning_evidence_audit_cron.sh"' in src
    assert 'grep -q "$MARKER"' in src
    assert "filtered_crontab" in src
    assert 'grep -v "$MARKER" || true' in src
    assert "demo_learning_evidence_audit_cron.cron.log" in src
    assert (
        "Boundary: artifact-only Markdown/JSON heartbeat; readonly PG; no order authority or Cost Gate relaxation"
        in src
    )
    assert "install_demo_learning_evidence_audit_cron.sh requires Linux runtime" in src


@pytest.mark.parametrize("script", [WRAPPER, INSTALLER], ids=["wrapper", "installer"])
def test_no_hardcoded_user_paths_or_trading_tokens(script: Path) -> None:
    src = _src(script)
    assert "/home/ncyu" not in src
    assert "/Users/" not in src
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
