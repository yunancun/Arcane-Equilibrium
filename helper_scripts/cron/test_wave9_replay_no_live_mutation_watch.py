"""wave9_replay_no_live_mutation_watch — pytest fixtures + scenarios.

wave9_replay_no_live_mutation_watch — pytest 場景測試。

MODULE_NOTE (EN): REF-20 Wave 9 R20-W9-T1. Pins four load-bearing
  behaviours of the validator + cron orchestration via a hand-rolled
  in-memory fake cursor that simulates trading.* + V035 schema:

    1. trading schema absent → ok=True graceful (no violation).
    2. trading schema present + 0 replay-source rows in 14d → ok=True.
    3. 5 replay-source rows in 14d window → ok=False + first_ts surfaced.
    4. window_days bound validation (1 ≤ window_days ≤ 365).

  Avoids spinning up real PostgreSQL; mirrors sibling cron test pattern
  (test_replay_artifact_prune.py).

MODULE_NOTE (中): REF-20 Wave 9 R20-W9-T1。用手寫 in-memory fake cursor
  釘死 validator + cron 4 條 load-bearing 行為，模擬 trading.* + V035
  schema：

    1. trading schema 缺 → ok=True graceful（無違反）。
    2. trading schema 在 + 0 replay-source row → ok=True。
    3. 14d 窗口 5 replay-source row → ok=False + first_ts 顯露。
    4. window_days 邊界（1 ≤ window_days ≤ 365）。

  不需真 PostgreSQL；對齊 sibling cron 測試模式（test_replay_artifact_prune.py）。

Tests / 測試覆蓋:
  1. test_trading_schema_absent_returns_ok_graceful
  2. test_zero_replay_source_rows_in_window_returns_ok
  3. test_five_replay_source_rows_returns_violation_with_first_ts
  4. test_window_days_validation_rejects_out_of_bounds
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


# Inject validator module path into sys.path.
# 將 validator module 路徑注入 sys.path。
_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
_VALIDATOR_DIR = (
    _SRV_ROOT
    / "program_code"
    / "exchange_connectors"
    / "bybit_connector"
    / "control_api_v1"
    / "replay"
)
if str(_VALIDATOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATOR_DIR))

# Import after sys.path injection (per test_replay_artifact_prune pattern).
# 在 sys.path 注入後 import（per test_replay_artifact_prune pattern）。
import wave9_continuous_validator as validator  # noqa: E402


# ─── Fake cursor / 假 cursor ─────────────────────────────────────────


class _FakeCursor:
    """Minimal psycopg2-compatible cursor for Wave 9 validator tests.

    Wave 9 validator 測試最小 psycopg2-相容 cursor。

    Tracks executed SQL + params for assertions; returns canned `fetchone()`
    based on configured presence flags + per-table replay-source row data.

    記錄 execute 之 SQL + params 供 assert；依配置的 presence flag + 每表
    replay-source row 資料回 fetchone 結果。
    """

    def __init__(
        self,
        trading_schema_present: bool = True,
        live_orders_present: bool = True,
        fills_present: bool = True,
        positions_present: bool = True,
        live_orders_source_col: bool = True,
        fills_source_col: bool = True,
        positions_source_col: bool = True,
        replay_source_counts: dict[str, tuple[int, datetime | None]] | None = None,
    ) -> None:
        self.trading_schema_present = trading_schema_present
        self.live_orders_present = live_orders_present
        self.fills_present = fills_present
        self.positions_present = positions_present
        self.live_orders_source_col = live_orders_source_col
        self.fills_source_col = fills_source_col
        self.positions_source_col = positions_source_col
        # replay_source_counts: per-table tuple (count, first_ts) for the
        # SELECT COUNT(*), MIN(ts) ... LIKE 'replay_%' query.
        # replay_source_counts: per-table tuple (count, first_ts) 給
        # SELECT COUNT(*), MIN(ts) ... LIKE 'replay_%' 查詢。
        self.replay_source_counts = replay_source_counts or {}
        self.executed: list[tuple[str, Any]] = []
        self._next_fetchone: Any = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))
        sql_lower = sql.lower()

        # Schema probe / Schema 偵測.
        if "information_schema.schemata" in sql_lower:
            self._next_fetchone = (
                (1,) if self.trading_schema_present else None
            )
            return

        # Table presence probe / Table 存在偵測.
        if (
            "information_schema.tables" in sql_lower
            and params
            and len(params) == 2
            and params[0] == "trading"
        ):
            table = params[1]
            if table == "live_orders":
                self._next_fetchone = (1,) if self.live_orders_present else None
            elif table == "fills":
                self._next_fetchone = (1,) if self.fills_present else None
            elif table == "positions":
                self._next_fetchone = (1,) if self.positions_present else None
            else:
                self._next_fetchone = None
            return

        # Source column probe / source 欄位偵測.
        if (
            "information_schema.columns" in sql_lower
            and params
            and len(params) == 3
            and params[0] == "trading"
            and params[2] == "source"
        ):
            table = params[1]
            if table == "live_orders":
                self._next_fetchone = (
                    (1,) if self.live_orders_source_col else None
                )
            elif table == "fills":
                self._next_fetchone = (1,) if self.fills_source_col else None
            elif table == "positions":
                self._next_fetchone = (
                    (1,) if self.positions_source_col else None
                )
            else:
                self._next_fetchone = None
            return

        # Per-table replay-source SELECT COUNT(*), MIN(ts) ...
        # LIKE 'replay_%' query.
        # 每表 replay-source SELECT COUNT(*), MIN(ts) ... LIKE 'replay_%' 查詢。
        if (
            "select count(*), min(ts)" in sql_lower
            and "from trading." in sql_lower
            and "where source like" in sql_lower
        ):
            # Extract table name from "FROM trading.<table>".
            # 從 "FROM trading.<table>" 抽 table 名稱。
            for table_name in ("live_orders", "fills", "positions"):
                if f"from trading.{table_name}" in sql_lower:
                    count, first_ts = self.replay_source_counts.get(
                        table_name, (0, None)
                    )
                    self._next_fetchone = (count, first_ts)
                    return
            self._next_fetchone = (0, None)
            return

        # Default: nothing to fetch.
        self._next_fetchone = None

    def fetchone(self) -> Any:
        return self._next_fetchone


# ─── Tests / 測試 ────────────────────────────────────────────────────


def test_trading_schema_absent_returns_ok_graceful() -> None:
    """trading schema 缺 → ok=True graceful + total=0 + first_ts=None."""
    cur = _FakeCursor(trading_schema_present=False)

    result = validator.validate_no_live_mutation(cursor=cur, window_days=14)

    assert result.ok is True, "expected ok=True for absent trading schema"
    assert result.total_replay_source_rows == 0
    assert result.first_violation_ts is None
    assert result.details.get("trading_schema_absent") is True
    # Only one SQL executed: the schema probe (early-return path).
    # 只執行一條 SQL：schema probe（早期 return path）。
    assert len(cur.executed) == 1
    sql, params = cur.executed[0]
    assert "information_schema.schemata" in sql.lower()
    assert params == ("trading",)


def test_zero_replay_source_rows_in_window_returns_ok() -> None:
    """All 3 tables present + 0 replay-source rows in 14d → ok=True."""
    cur = _FakeCursor(
        trading_schema_present=True,
        live_orders_present=True,
        fills_present=True,
        positions_present=True,
        live_orders_source_col=True,
        fills_source_col=True,
        positions_source_col=True,
        replay_source_counts={
            "live_orders": (0, None),
            "fills": (0, None),
            "positions": (0, None),
        },
    )

    result = validator.validate_no_live_mutation(cursor=cur, window_days=14)

    assert result.ok is True
    assert result.total_replay_source_rows == 0
    assert result.first_violation_ts is None
    assert result.window_days == 14
    # All 3 tables scanned (none skipped).
    # 3 表全掃描（無跳過）。
    assert sorted(result.details["scanned_tables"]) == sorted(
        ["live_orders", "fills", "positions"]
    )
    assert result.details["skipped_tables"] == []
    # per_table_counts present with all 0.
    # per_table_counts 存在且全 0。
    assert result.details["per_table_counts"] == {
        "live_orders": 0,
        "fills": 0,
        "positions": 0,
    }


def test_five_replay_source_rows_returns_violation_with_first_ts() -> None:
    """5 replay-source rows across tables → ok=False + first_ts is earliest."""
    # Seed 3 violations on live_orders + 2 on fills + 0 on positions.
    # Earliest ts is on live_orders (2026-04-20).
    # Seed live_orders 3 + fills 2 + positions 0；最早 ts 在 live_orders。
    earliest_ts = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)
    later_ts = datetime(2026, 4, 25, 8, 0, 0, tzinfo=timezone.utc)

    cur = _FakeCursor(
        trading_schema_present=True,
        live_orders_present=True,
        fills_present=True,
        positions_present=True,
        live_orders_source_col=True,
        fills_source_col=True,
        positions_source_col=True,
        replay_source_counts={
            "live_orders": (3, earliest_ts),
            "fills": (2, later_ts),
            "positions": (0, None),
        },
    )

    result = validator.validate_no_live_mutation(cursor=cur, window_days=14)

    assert result.ok is False, "expected ok=False for 5 replay-source rows"
    assert result.total_replay_source_rows == 5
    assert result.first_violation_ts == earliest_ts, (
        f"expected earliest violation ts on live_orders, got {result.first_violation_ts}"
    )
    assert result.details["per_table_counts"] == {
        "live_orders": 3,
        "fills": 2,
        "positions": 0,
    }


def test_window_days_validation_rejects_out_of_bounds() -> None:
    """window_days outside (0, 365] → ValueError."""
    cur = _FakeCursor(trading_schema_present=False)

    # Lower bound rejection / 下限拒絕.
    with pytest.raises(ValueError, match=r"window_days"):
        validator.validate_no_live_mutation(cursor=cur, window_days=0)

    # Upper bound rejection / 上限拒絕.
    with pytest.raises(ValueError, match=r"window_days"):
        validator.validate_no_live_mutation(cursor=cur, window_days=400)

    # Negative rejection / 負數拒絕.
    with pytest.raises(ValueError, match=r"window_days"):
        validator.validate_no_live_mutation(cursor=cur, window_days=-1)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
