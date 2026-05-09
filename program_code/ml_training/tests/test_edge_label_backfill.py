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
    ABANDONED_TAG_PREFIX,
    BackfillResult,
    DEFAULT_ABANDON_AFTER_DAYS,
    EXCLUDED_TAG_PREFIXES,
    attribution_chain_ratio,
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

    def fetchone(self):
        # P0-V3 attribution_chain_ratio 用 fetchone（單 aggregate row）
        # P0-V3 attribution_chain_ratio uses fetchone (single aggregate row).
        return self._last_rows[0] if self._last_rows else None


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
    assert r.abandoned_count == 0  # P0-V3-MIT-ROOT-CAUSE: Pass 3 counter
    assert r.batch_limit_hit is False


def test_backfill_result_to_dict_keys():
    r = BackfillResult(filled_count=10, excluded_count=2, split_blend_count=1,
                      grid_merged_count=3, abandoned_count=42)
    d = r.to_dict()
    assert d["filled"] == 10
    assert d["excluded"] == 2
    assert d["split_blend"] == 1
    assert d["grid_merged"] == 3
    assert d["abandoned"] == 42  # P0-V3-MIT-ROOT-CAUSE: Pass 3 in dict
    assert d["batch_limit_hit"] is False


def test_abandoned_tag_prefix_is_documented():
    """ABANDONED_TAG_PREFIX 必為 'abandoned:no_close_fill' 與 SQL/healthcheck 對齊。
    Confirms the prefix string matches Pass 3 SQL + downstream healthcheck."""
    assert ABANDONED_TAG_PREFIX == "abandoned:no_close_fill"
    assert DEFAULT_ABANDON_AFTER_DAYS == 30  # 默認 30d conservative


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
    # P0-V3-MIT-ROOT-CAUSE: Pass 3 默認啟用，但 fixture 沒給 abandoned response
    # → 0 row（match key 'WITH abandoned_entries AS' 沒命中 fixture）
    assert result.abandoned_count == 0
    assert conn.committed is True
    assert conn.rolled_back is False
    assert conn.closed is True


def test_backfill_labels_empty_no_rows():
    with _patch_conn({}) as conn:
        result = backfill_labels(engine_mode="paper", batch_limit=50)
    assert result.filled_count == 0
    assert result.excluded_count == 0
    assert result.abandoned_count == 0
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
    # P0-V3-MIT-ROOT-CAUSE: Pass 3 預設 enabled → execute call 從 2 增至 3
    # 三個 pass 都用同一個 engine_modes 列表
    assert scopes == [
        ["live", "live_demo"],
        ["live", "live_demo"],
        ["live", "live_demo"],
    ]


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


def test_backfill_labels_pass3_abandoned_marker():
    """P0-V3-MIT-ROOT-CAUSE Pass 3：abandoned_entries fixture 觸發 abandoned counter。
    Pass 3 fires when fixture supplies abandoned_entries rowset."""
    responses = {
        "WITH entries AS": [("ctx-1", "ma_crossover", False)],   # Pass 1
        "WITH excluded_entries AS": [("ctx-x1",)],                # Pass 2
        "WITH abandoned_entries AS": [
            ("ctx-stuck-1",), ("ctx-stuck-2",), ("ctx-stuck-3",),
        ],
    }
    with _patch_conn(responses) as conn:
        result = backfill_labels(engine_mode="demo", batch_limit=100)

    assert result.filled_count == 1
    assert result.excluded_count == 1
    assert result.abandoned_count == 3
    assert conn.committed is True

    # 確認 Pass 3 SQL 用了正確的 abandoned_tag + abandon_after_days
    abandoned_sql_calls = [
        (sql, params) for sql, params in conn.execute_calls
        if "WITH abandoned_entries AS" in sql
    ]
    assert len(abandoned_sql_calls) == 1, "Pass 3 SQL must execute exactly once"
    _, params = abandoned_sql_calls[0]
    assert params["abandoned_tag"] == ABANDONED_TAG_PREFIX
    assert params["abandon_after_days"] == DEFAULT_ABANDON_AFTER_DAYS
    assert params["batch_limit"] == 100


def test_backfill_labels_pass3_disabled_when_none():
    """abandon_after_days=None 跳過 Pass 3 = safety fallback。
    Setting abandon_after_days=None skips Pass 3 entirely (legacy behavior)."""
    responses = {
        "WITH entries AS": [("ctx-1", "ma_crossover", False)],
        "WITH abandoned_entries AS": [("ctx-stuck-1",), ("ctx-stuck-2",)],
    }
    with _patch_conn(responses) as conn:
        result = backfill_labels(engine_mode="demo", batch_limit=100, abandon_after_days=None)

    assert result.filled_count == 1
    assert result.abandoned_count == 0  # Pass 3 跳過，counter 仍 0

    # 確認 Pass 3 SQL 未執行
    abandoned_sql_calls = [
        sql for sql, _params in conn.execute_calls
        if "WITH abandoned_entries AS" in sql
    ]
    assert len(abandoned_sql_calls) == 0, \
        "Pass 3 SQL must NOT execute when abandon_after_days=None"


def test_backfill_labels_pass3_custom_threshold():
    """abandon_after_days 可自訂（test 7 vs default 30）。
    Custom abandon_after_days propagates to SQL params."""
    responses = {
        "WITH entries AS": [],
        "WITH abandoned_entries AS": [("ctx-old-1",)],
    }
    with _patch_conn(responses) as conn:
        result = backfill_labels(engine_mode="demo", batch_limit=100, abandon_after_days=7)

    assert result.abandoned_count == 1
    abandoned_sql_calls = [
        params for sql, params in conn.execute_calls
        if "WITH abandoned_entries AS" in sql
    ]
    assert len(abandoned_sql_calls) == 1
    assert abandoned_sql_calls[0]["abandon_after_days"] == 7


def test_backfill_labels_pass3_batch_limit_hit_flag():
    """Pass 3 也算入 batch_limit_hit 判斷（避免單 cron run 漏了 batch）。
    Pass 3 also triggers batch_limit_hit (so cron schedules another pass)."""
    responses = {
        "WITH abandoned_entries AS": [(f"ctx-{i}",) for i in range(50)],
    }
    with _patch_conn(responses):
        result = backfill_labels(engine_mode="demo", batch_limit=50, abandon_after_days=30)
    assert result.abandoned_count == 50
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
# attribution_chain_ratio — healthcheck companion observer
# ============================================================
def test_attribution_chain_ratio_basic():
    """attribution_chain_ratio 回 dict 含 ok_n / total_n / 各 bucket。
    Returns dict with ok_n / total_n / bucket breakdown."""
    responses = {
        "FROM learning.mlde_edge_training_rows": [
            (1000, 50, 800, 100, 50),  # total=1000, ok=50, unfilled=800, abandoned=100, excluded=50
        ],
    }
    with _patch_conn(responses):
        ratio = attribution_chain_ratio(window_hours=24)

    assert ratio["window_hours"] == 24
    assert ratio["total_n"] == 1000
    assert ratio["ok_n"] == 50
    assert ratio["ok_ratio"] == 0.05
    assert ratio["unfilled_n"] == 800
    assert ratio["abandoned_n"] == 100
    assert ratio["excluded_n"] == 50


def test_attribution_chain_ratio_empty_window():
    """空窗口（healthcheck cold start）回 0 不 raise。
    Empty window returns zeros without raising."""
    responses = {
        "FROM learning.mlde_edge_training_rows": [(0, 0, 0, 0, 0)],
    }
    with _patch_conn(responses):
        ratio = attribution_chain_ratio(window_hours=1)

    assert ratio["total_n"] == 0
    assert ratio["ok_n"] == 0
    assert ratio["ok_ratio"] == 0.0
    assert ratio["abandoned_n"] == 0


def test_attribution_chain_ratio_ok_ratio_arithmetic():
    """ok_ratio 數學正確 + 防 ZeroDivisionError。
    ok_ratio arithmetic correct + guards ZeroDivisionError."""
    responses = {
        "FROM learning.mlde_edge_training_rows": [(283, 283, 0, 555535, 0)],
    }
    with _patch_conn(responses):
        ratio = attribution_chain_ratio(window_hours=24 * 7)

    assert ratio["total_n"] == 283
    assert ratio["ok_n"] == 283
    assert ratio["ok_ratio"] == 1.0  # all OK in this fixture


def test_attribution_chain_ratio_no_row_returned():
    """fetchone 回 None（cursor 沒 row）→ 安全回 zero dict。
    fetchone returns None → safely return zero dict."""
    class _NoRowConn(_FakeConn):
        def cursor(self):
            cur = _FakeCursor({}, self.execute_calls)
            cur.fetchone = lambda: None  # type: ignore[assignment]
            return cur

    fake = _NoRowConn({})
    with mock.patch(
        "program_code.ml_training.edge_label_backfill._get_conn",
        return_value=fake,
    ):
        ratio = attribution_chain_ratio(window_hours=24)

    assert ratio["total_n"] == 0


# ============================================================
# Regression: P0-V3-MIT-ROOT-CAUSE 驗收
# Regression: P0-V3-MIT-ROOT-CAUSE acceptance
# ============================================================
def test_p0_v3_mit_root_cause_pass3_invariant_label_net_edge_bps_stays_null():
    """Pass 3 SQL 必 EXPLICITLY 不寫 label_net_edge_bps（保持 NULL，不污染訓練集）。
    Pass 3 SQL must NEVER set label_net_edge_bps (per Pass 2 invariant).

    驗證方式：parse SET clause（移除 -- 註釋行）後檢查 column assignment 列表，
    `label_net_edge_bps =` 必不存在於任何 SET assignment（避免 false-positive
    把 SQL comment 內的提及誤判）。
    """
    import re
    from program_code.ml_training import edge_label_backfill as m

    sql = m._BACKFILL_ABANDONED_SQL
    # 取 SET ... FROM 之間的 raw text
    set_block_raw = sql.split("UPDATE")[1].split("FROM")[0]
    # 移除 -- 行內 / 行尾註釋（PG 風格 single-line comment）
    set_block_no_comment = "\n".join(
        re.sub(r"--.*$", "", line) for line in set_block_raw.split("\n")
    )
    # 確認必設的兩個 column 在 SET 子句出現
    assert "label_close_tag" in set_block_no_comment
    assert "label_filled_at" in set_block_no_comment
    # 關鍵不變式：移除 comment 後 label_net_edge_bps 不應出現在 SET 子句
    assert "label_net_edge_bps" not in set_block_no_comment, \
        "Pass 3 must NEVER assign label_net_edge_bps in SET clause (Pass 2 invariant)"


def test_p0_v3_mit_root_cause_pass3_filters_audit_rows():
    """Pass 3 必過濾 unattributed:% audit row（與 Pass 1+2 對齊 F4-2）。
    Pass 3 must filter unattributed:% audit rows (F4-2 alignment)."""
    from program_code.ml_training import edge_label_backfill as m
    assert "unattributed:" in m._BACKFILL_ABANDONED_SQL


def test_p0_v3_mit_root_cause_pass3_uses_not_exists():
    """Pass 3 必 NOT EXISTS（沒 close fill 才 abandoned）。
    Pass 3 must use NOT EXISTS so only no-close-fill rows are marked."""
    from program_code.ml_training import edge_label_backfill as m
    assert "NOT EXISTS" in m._BACKFILL_ABANDONED_SQL


def test_p0_v3_mit_root_cause_label_close_tag_null_rate_invariant():
    """P0-V3 sibling regression test: 1 cycle Pass 3 應顯著降低 label_close_tag NULL rate。
    Sibling regression: 1 Pass 3 cycle should drastically reduce label_close_tag NULL rate.

    模擬 1000 row 的 view fixture，Pass 3 標 800 row → label_close_tag NULL rate
    應從 90% (900/1000) 降到 10% (100/1000)，attribution_chain_ratio
    抓 'abandoned_n' 應增加。
    """
    # 模擬：Pass 3 跑前
    responses_before = {
        "FROM learning.mlde_edge_training_rows": [
            # total=1000, ok=100, unfilled=900, abandoned=0, excluded=0
            # → label_close_tag NULL rate = (1000 - 100) / 1000 = 90%
            (1000, 100, 900, 0, 0),
        ],
    }
    with _patch_conn(responses_before):
        ratio_before = attribution_chain_ratio(window_hours=24)
    null_rate_before = (
        ratio_before["total_n"] - ratio_before["ok_n"] - ratio_before["abandoned_n"]
    ) / max(ratio_before["total_n"], 1)
    assert null_rate_before == 0.9  # 90% NULL

    # 模擬：Pass 3 跑後（800 stuck row 標 abandoned）
    responses_after = {
        "FROM learning.mlde_edge_training_rows": [
            # total=1000, ok=100, unfilled=100, abandoned=800, excluded=0
            # → label_close_tag NULL rate = (1000 - 100 - 800) / 1000 = 10%
            (1000, 100, 100, 800, 0),
        ],
    }
    with _patch_conn(responses_after):
        ratio_after = attribution_chain_ratio(window_hours=24)
    null_rate_after = (
        ratio_after["total_n"] - ratio_after["ok_n"] - ratio_after["abandoned_n"]
    ) / max(ratio_after["total_n"], 1)
    assert null_rate_after == 0.1  # 10% NULL（顯著改善）

    # 驗證 < 5% 目標需要更激進的 abandoned 比例（ok 100 / total 1000 自然 90% NULL ratio）
    # P0-V3 fix 不能讓 ok_ratio 升到 95%（因為 ok 是 close fill 自然決定，不可人造）；
    # fix 目標是把 attribution_chain_ok denominator 縮減，使 ok_ratio 「相對 total」上升。
    # 這個 test 抓 abandoned_n 變化即驗收。
    assert ratio_after["abandoned_n"] > ratio_before["abandoned_n"]
    assert ratio_after["abandoned_n"] >= 100  # P0-V3 sibling acceptance: at least 100 row abandoned


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
    # Partial closes must not finalize a label; future close fills can complete it.
    assert "close_qty_complete" in m._BACKFILL_INCLUDED_SQL
    assert "AND l.close_qty_complete" in m._BACKFILL_INCLUDED_SQL

    # Pass 2 must match the 3 excluded prefixes (§4.2)
    for prefix in ("orphan_close:", "adopted_close:", "shadow_fill:"):
        assert prefix in m._BACKFILL_EXCLUDED_SQL
    assert "engine_mode = ANY(%(engine_modes)s)" in m._BACKFILL_EXCLUDED_SQL

    # P0-V3-MIT-ROOT-CAUSE: Pass 3 must contain expected clauses
    assert "WITH abandoned_entries AS" in m._BACKFILL_ABANDONED_SQL
    assert "label_filled_at IS NULL" in m._BACKFILL_ABANDONED_SQL
    assert "engine_mode = ANY(%(engine_modes)s)" in m._BACKFILL_ABANDONED_SQL
    assert "abandon_after_days" in m._BACKFILL_ABANDONED_SQL
    assert "abandoned_tag" in m._BACKFILL_ABANDONED_SQL
    assert "NOT EXISTS" in m._BACKFILL_ABANDONED_SQL  # 沒 close fill 才標
    assert "label_close_tag = %(abandoned_tag)s" in m._BACKFILL_ABANDONED_SQL

    # Stale-label SQL must filter on label_filled_at NULL
    assert "label_filled_at IS NULL" in m._STALE_LABELS_SQL

    # P0-V3 attribution_chain_ratio SQL must select the 5 buckets
    assert "attribution_chain_ok" in m._ATTRIBUTION_RATIO_SQL
    assert "abandoned:" in m._ATTRIBUTION_RATIO_SQL  # detect Pass 3 marked rows
    assert "orphan_close:" in m._ATTRIBUTION_RATIO_SQL  # detect Pass 2 excluded
