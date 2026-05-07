from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

SCRIPT = SCRIPT_DIR / "ref21_market_recorder_retention.py"
spec = importlib.util.spec_from_file_location("ref21_market_recorder_retention", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class FakeCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.rowcount = 0
        self._fetchone = (7,)

    def execute(self, sql, params=None) -> None:
        self.statements.append(str(sql))
        if "DELETE FROM" in str(sql):
            self.rowcount = 5

    def fetchone(self):
        return self._fetchone


def test_retention_days_clamps_to_minimum() -> None:
    assert mod.retention_days_from_env("1") == mod.MIN_RETENTION_DAYS
    assert mod.retention_days_from_env("90") == 90
    assert mod.retention_days_from_env("bad") == mod.DEFAULT_RETENTION_DAYS


def test_prune_table_dry_run_counts_without_delete(monkeypatch) -> None:
    monkeypatch.setattr(mod, "table_exists", lambda *_args, **_kwargs: True)
    cur = FakeCursor()
    result = mod.prune_table(
        cur,
        "market.market_tickers",
        datetime(2026, 5, 1, tzinfo=timezone.utc),
        max_rows=100,
        apply=False,
    )

    assert result["status"] == "dry_run"
    assert result["candidate_rows"] == 7
    assert result["deleted_rows"] == 0
    assert not any("DELETE FROM" in stmt for stmt in cur.statements)


def test_prune_table_apply_uses_allowlisted_market_table(monkeypatch) -> None:
    monkeypatch.setattr(mod, "table_exists", lambda *_args, **_kwargs: True)
    cur = FakeCursor()
    result = mod.prune_table(
        cur,
        "market.ob_snapshots",
        datetime(2026, 5, 1, tzinfo=timezone.utc),
        max_rows=100,
        apply=True,
    )

    assert result["status"] == "applied"
    assert result["candidate_rows"] == 7
    assert result["deleted_rows"] == 5
    assert any("DELETE FROM market.ob_snapshots" in stmt for stmt in cur.statements)


def test_prune_table_rejects_non_recorder_tables() -> None:
    cur = FakeCursor()
    try:
        mod.prune_table(
            cur,
            "trading.fills",
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            max_rows=100,
            apply=True,
        )
    except ValueError as exc:
        assert "table_not_allowed" in str(exc)
    else:
        raise AssertionError("expected non-recorder table rejection")
