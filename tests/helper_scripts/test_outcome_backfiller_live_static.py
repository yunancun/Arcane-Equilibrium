from __future__ import annotations

import subprocess
from pathlib import Path


_SRV_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = _SRV_ROOT / "helper_scripts" / "db" / "outcome_backfiller_live.py"
WRAPPER = _SRV_ROOT / "helper_scripts" / "cron" / "outcome_backfiller_live_cron.sh"


def _script_body() -> str:
    assert SCRIPT.exists(), f"missing script: {SCRIPT}"
    return SCRIPT.read_text(encoding="utf-8")


def _wrapper_body() -> str:
    assert WRAPPER.exists(), f"missing wrapper: {WRAPPER}"
    return WRAPPER.read_text(encoding="utf-8")


def test_outcome_backfiller_live_syntax() -> None:
    py_rc = subprocess.run(
        ["python3", "-m", "py_compile", str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert py_rc.returncode == 0, py_rc.stderr

    bash_rc = subprocess.run(
        ["bash", "-n", str(WRAPPER)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert bash_rc.returncode == 0, bash_rc.stderr


def test_outcome_backfiller_live_uses_fixed_rust_sql_contract() -> None:
    body = _script_body()

    assert "s.engine_mode = ANY(%(engine_modes)s::text[])" in body
    assert "ON CONFLICT (context_id) DO UPDATE SET" in body
    assert "engine_mode = EXCLUDED.engine_mode" in body
    assert "outcome_backfilled = TRUE" in body

    for timeframe in ("'1m'", "'5m'", "'1h'", "'4h'"):
        assert f"k.timeframe = {timeframe}" in body
    for bad_timeframe in ("k.timeframe = '1'", "k.timeframe = '5'", "k.timeframe = '60'", "k.timeframe = '240'"):
        assert bad_timeframe not in body


def test_outcome_backfiller_live_repair_and_dry_run_contract() -> None:
    body = _script_body()

    assert "repair_existing" in body
    assert "o.outcome_1h IS NULL" in body
    assert "conn.rollback()" in body
    assert "conn.commit()" in body
    assert "DEFAULT_ENGINE_MODES = \"live,live_demo\"" in body


def test_outcome_backfiller_live_wrapper_env_lock_and_defaults() -> None:
    body = _wrapper_body()

    assert "basic_system_services.env" in body
    assert "OPENCLAW_DATABASE_URL" in body
    assert "PYTHONPATH" in body
    assert "outcome_backfiller_live_cron.lock.d" in body
    assert "outcome_backfiller_live_cron.log" in body
    assert "OPENCLAW_OUTCOME_BACKFILL_ENGINE_MODES:-live,live_demo" in body
    assert "OPENCLAW_OUTCOME_BACKFILL_BATCH_SIZE:-2000" in body
    assert "mkdir \"$LOCK_DIR\"" in body
