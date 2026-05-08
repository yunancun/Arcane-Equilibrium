from __future__ import annotations

from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
SCRIPT = _SRV_ROOT / "helper_scripts" / "cron" / "edge_estimate_snapshots_cycle_cron.sh"


def _script() -> str:
    assert SCRIPT.exists(), f"script missing: {SCRIPT}"
    return SCRIPT.read_text(encoding="utf-8")


def test_cycle_cron_wraps_ref21_helper_for_v059_only() -> None:
    body = _script()

    assert "helper_scripts/db/ref21_backfill_v058_v059.py" in body
    assert "--skip-instruments" in body
    assert "--skip-freeze-log" in body
    assert "--actor edge_estimate_snapshots_cycle" in body
    assert "--apply" in body


def test_cycle_cron_sources_pg_credentials_and_sets_overlap_lock() -> None:
    body = _script()

    assert "basic_system_services.env" in body
    assert "POSTGRES_PASSWORD" in body
    assert "OPENCLAW_DATABASE_URL" in body
    assert "edge_estimate_snapshots_cycle_cron.lock.d" in body
    assert "mkdir \"$LOCK_DIR\"" in body


def test_cycle_cron_logs_to_openclaw_data_dir() -> None:
    body = _script()

    assert 'DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"' in body
    assert "edge_estimate_snapshots_cycle_cron.log" in body
    assert "cycle start" in body
    assert "cycle end OK" in body
