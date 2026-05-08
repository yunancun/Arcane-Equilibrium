from __future__ import annotations

from pathlib import Path


SQL = (
    Path(__file__).resolve().parents[2]
    / "sql"
    / "migrations"
    / "V074__decision_outcomes_live_backfill_schedule.sql"
).read_text(encoding="utf-8")


def test_v074_is_schema_guard_and_index_only() -> None:
    lowered = SQL.lower()

    assert "trading.decision_context_snapshots" in SQL
    assert "trading.decision_outcomes" in SQL
    assert "market.klines" in SQL
    assert "create index if not exists idx_dcs_outcome_backfill_engine_pending" in lowered
    assert "where outcome_backfilled = false" in lowered
    assert "on trading.decision_context_snapshots (engine_mode, ts asc)" in lowered

    forbidden = ("insert into", "update ", "delete from", "truncate ", "drop table")
    assert not any(token in lowered for token in forbidden)


def test_v074_guards_outcome_and_kline_contracts() -> None:
    for column in (
        "outcome_1m",
        "outcome_5m",
        "outcome_1h",
        "outcome_4h",
        "outcome_24h",
        "max_favorable",
        "max_adverse",
        "backfilled_ts",
        "engine_mode",
    ):
        assert column in SQL

    for column in ("symbol", "timeframe", "ts", "close", "high", "low"):
        assert column in SQL


def test_v074_does_not_install_cron_or_run_backfill() -> None:
    lowered = SQL.lower()

    assert "crontab" not in lowered
    assert "systemctl" not in lowered
    assert "pg_cron" not in lowered
    assert "no data backfill is performed here" in SQL.lower()
