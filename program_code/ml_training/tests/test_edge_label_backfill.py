"""
Tests for edge_label_backfill.
邊緣標籤回填模組測試。

Unit tests use a fake psycopg2 cursor to inject rowsets — the SQL itself
is validated at staging time (V017 deployment + demo 48h fill-rate check).
單元測試用 fake psycopg2 cursor 注入 rowset — SQL 本身在 staging 階段驗證
（V017 部署 + demo 48h 填充率檢查）。
"""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from unittest import mock

import pytest

from program_code.ml_training.edge_label_backfill import (
    BackfillResult,
    EXCLUDED_TAG_PREFIXES,
    backfill_labels,
    check_stale_labels,
    engine_mode_scope,
    fill_rate_summary,
)


# ============================================================
# Fake psycopg2 cursor/connection — allows injecting rowsets
# per SQL query (matched by substring of the statement text).
# ============================================================
class _FakeCursor:
    def __init__(self, responses: dict[str, list[tuple]], execute_calls: list[tuple[str, dict | None]]):
        self._responses = responses
        self._execute_calls = execute_calls
        self._last_rows: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql: str, params: dict | None = None):
        self._execute_calls.append((sql, params))
        for key, rows in self._responses.items():
            if key in sql:
                self._last_rows = list(rows)
                return
        self._last_rows = []

    def fetchall(self):
        return self._last_rows


class _FakeConn:
    def __init__(self, responses: dict[str, list[tuple]]):
        self._responses = responses
        self.execute_calls: list[tuple[str, dict | None]] = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return _FakeCursor(self._responses, self.execute_calls)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@contextmanager
def _patch_conn(responses: dict[str, list[tuple]]):
    """Patch _get_conn to return a FakeConn with the given rowsets.
    patch _get_conn 返回指定 rowset 的 FakeConn。"""
    fake = _FakeConn(responses)
    with mock.patch(
        "program_code.ml_training.edge_label_backfill._get_conn",
        return_value=fake,
    ):
        yield fake


# ============================================================
# Constants / contract invariants
# ============================================================
def test_excluded_tag_prefixes_contract():
    """Spec §4.2 — the three excluded close_tag prefixes must be present.
    §4.2 — 三個排除前綴必須存在。"""
    assert "orphan_close:" in EXCLUDED_TAG_PREFIXES
    assert "adopted_close:" in EXCLUDED_TAG_PREFIXES
    assert "shadow_fill:" in EXCLUDED_TAG_PREFIXES


def test_engine_mode_scope_live_includes_live_demo():
    assert engine_mode_scope("live") == ("live", "live_demo")
    assert engine_mode_scope("live_demo") == ("live_demo",)
    assert engine_mode_scope("demo") == ("demo",)


def test_backfill_result_default_empty():
    r = BackfillResult()
    assert r.filled_count == 0
    assert r.excluded_count == 0
    assert r.split_blend_count == 0
    assert r.grid_merged_count == 0
    assert r.skipped_no_entry_fill == 0
    assert r.batch_limit_hit is False


def test_backfill_result_to_dict_keys():
    r = BackfillResult(filled_count=10, excluded_count=2, split_blend_count=1, grid_merged_count=3)
    d = r.to_dict()
    assert d["filled"] == 10
    assert d["excluded"] == 2
    assert d["split_blend"] == 1
    assert d["grid_merged"] == 3
    assert d["batch_limit_hit"] is False


# ============================================================
# backfill_labels — counters classify rowsets correctly
# ============================================================
def test_backfill_labels_mixed_strategies_classified():
    """Pass 1 returns mix of grid / split / single → counters reflect §4.2/§4.3.
    Pass 1 返回 grid/split/single 混合 → 計數器反映 §4.2/§4.3。"""
    responses = {
        "WITH entries AS": [
            # (context_id, strategy_name, split_flag)
            ("ctx-1", "ma_crossover",    False),  # single close, non-split
            ("ctx-2", "bb_breakout",     True),   # split blend
            ("ctx-3", "grid_trading",    False),  # grid VWAP (split_flag always False for grid)
            ("ctx-4", "funding_arb",     False),
            ("ctx-5", "grid_trading",    False),
        ],
        "WITH excluded_entries AS": [
            ("ctx-x1",),
            ("ctx-x2",),
        ],
    }
    with _patch_conn(responses) as conn:
        result = backfill_labels(engine_mode="demo", batch_limit=100)

    assert result.filled_count == 5
    assert result.grid_merged_count == 2
    assert result.split_blend_count == 1
    assert result.excluded_count == 2
    assert conn.committed is True
    assert conn.rolled_back is False
    assert conn.closed is True


def test_backfill_labels_empty_no_rows():
    with _patch_conn({}) as conn:
        result = backfill_labels(engine_mode="paper", batch_limit=50)
    assert result.filled_count == 0
    assert result.excluded_count == 0
    assert conn.committed is True


def test_backfill_labels_dry_run_rolls_back():
    responses = {
        "WITH entries AS": [("ctx-1", "ma_crossover", False)],
    }
    with _patch_conn(responses) as conn:
        result = backfill_labels(engine_mode="demo", dry_run=True)
    assert result.filled_count == 1
    assert conn.rolled_back is True
    assert conn.committed is False


def test_backfill_labels_live_scope_params_include_live_demo():
    responses = {
        "WITH entries AS": [("ctx-1", "ma_crossover", False)],
    }
    with _patch_conn(responses) as conn:
        result = backfill_labels(engine_mode="live", dry_run=True)

    assert result.filled_count == 1
    scopes = [
        params["engine_modes"]
        for _sql, params in conn.execute_calls
        if params and "engine_modes" in params
    ]
    assert scopes == [["live", "live_demo"], ["live", "live_demo"]]


def test_backfill_labels_invalid_engine_mode():
    with pytest.raises(ValueError, match="invalid engine_mode"):
        backfill_labels(engine_mode="mainnet")


def test_backfill_labels_batch_limit_hit_flag():
    """When filled_count hits batch_limit, batch_limit_hit=True.
    當 filled_count 達到 batch_limit，batch_limit_hit=True。"""
    responses = {
        "WITH entries AS": [(f"ctx-{i}", "ma_crossover", False) for i in range(10)],
    }
    with _patch_conn(responses):
        result = backfill_labels(engine_mode="demo", batch_limit=10)
    assert result.filled_count == 10
    assert result.batch_limit_hit is True


def test_backfill_labels_rollback_on_exception():
    """If cursor raises, connection must rollback and propagate.
    如 cursor 拋錯，連線必須 rollback 並向上拋。"""
    class ExplodingCursor(_FakeCursor):
        def execute(self, sql, params=None):
            raise RuntimeError("boom")

    class ExplodingConn(_FakeConn):
        def cursor(self):
            return ExplodingCursor({}, self.execute_calls)

    fake = ExplodingConn({})
    with mock.patch(
        "program_code.ml_training.edge_label_backfill._get_conn",
        return_value=fake,
    ):
        with pytest.raises(RuntimeError, match="boom"):
            backfill_labels(engine_mode="demo")

    assert fake.rolled_back is True
    assert fake.committed is False
    assert fake.closed is True


# ============================================================
# check_stale_labels — alerter
# ============================================================
def test_check_stale_labels_formats_rows():
    ts_old = datetime(2026, 4, 1, 12, 0, 0)
    ts_new = datetime(2026, 4, 10, 12, 0, 0)
    responses = {
        "stale_rows": [
            ("demo", "funding_arb",  42, ts_old, ts_new),
            ("demo", "ma_crossover", 10, ts_old, ts_new),
        ],
    }
    with _patch_conn(responses):
        rows = check_stale_labels(max_age_days=7)

    assert len(rows) == 2
    assert rows[0]["strategy_name"] == "funding_arb"
    assert rows[0]["stale_rows"] == 42
    assert rows[0]["oldest_ts"] == ts_old.isoformat()
    assert rows[0]["newest_ts"] == ts_new.isoformat()


def test_check_stale_labels_empty_returns_empty_list():
    with _patch_conn({}):
        rows = check_stale_labels(max_age_days=7)
    assert rows == []


# ============================================================
# fill_rate_summary — computes fill rate per (engine_mode, strategy)
# ============================================================
def test_fill_rate_summary_computes_rate_correctly():
    responses = {
        "FILTER (WHERE label_net_edge_bps IS NOT NULL)": [
            ("demo", "ma_crossover", 90, 5,  5,  100),  # 95/100 = 0.95
            ("demo", "funding_arb",  50, 10, 40, 100),  # 60/100 = 0.60
            ("paper", "bb_breakout", 0,  0,  0,  0),    # empty → 0.0
        ],
    }
    with _patch_conn(responses):
        summary = fill_rate_summary(window_hours=48)

    assert len(summary) == 3
    by_strategy = {(r["engine_mode"], r["strategy_name"]): r for r in summary}

    ma = by_strategy[("demo", "ma_crossover")]
    assert ma["labeled"] == 90
    assert ma["excluded"] == 5
    assert ma["pending"] == 5
    assert ma["fill_rate"] == 0.95

    fa = by_strategy[("demo", "funding_arb")]
    assert fa["fill_rate"] == 0.60

    bb = by_strategy[("paper", "bb_breakout")]
    assert bb["fill_rate"] == 0.0


# ============================================================
# SQL template sanity — ensure key clauses are present
# (cheap defense against accidental bad edit)
# ============================================================
def test_sql_templates_contain_expected_clauses():
    from program_code.ml_training import edge_label_backfill as m

    # Pass 1 must use composite columns from V017
    assert "label_net_edge_bps" in m._BACKFILL_INCLUDED_SQL
    assert "engine_mode = ANY(%(engine_modes)s)" in m._BACKFILL_INCLUDED_SQL
    assert "label_split_flag"   in m._BACKFILL_INCLUDED_SQL
    assert "label_filled_at"    in m._BACKFILL_INCLUDED_SQL
    assert "entry_context_id"   in m._BACKFILL_INCLUDED_SQL
    # Grid carve-out (§4.3)
    assert "grid_trading"       in m._BACKFILL_INCLUDED_SQL
    # Funding settlements must be joined into net edge, not left as a TODO.
    assert "trading.funding_settlements" in m._BACKFILL_INCLUDED_SQL
    assert "total_funding_pnl" in m._BACKFILL_INCLUDED_SQL
    assert "+ COALESCE(fb.total_funding_pnl, 0.0)" in m._BACKFILL_INCLUDED_SQL

    # Pass 2 must match the 3 excluded prefixes (§4.2)
    for prefix in ("orphan_close:", "adopted_close:", "shadow_fill:"):
        assert prefix in m._BACKFILL_EXCLUDED_SQL
    assert "engine_mode = ANY(%(engine_modes)s)" in m._BACKFILL_EXCLUDED_SQL

    # Stale-label SQL must filter on label_filled_at NULL
    assert "label_filled_at IS NULL" in m._STALE_LABELS_SQL
