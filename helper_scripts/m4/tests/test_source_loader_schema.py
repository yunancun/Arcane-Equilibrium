"""
MODULE_NOTE
模塊用途：M4 Stage 1 source loader schema-grep regression test
   （per W2-E E2 review verdict 2026-05-25 MEDIUM-1 補強）。

為什麼這個 test：
   W1-C Round 1 IMPL 51 pytest 全 PASS — 但 0 個 test 真正 grep SQL string
   是否含真實 PG schema column。E2 cold review catch 5 個 schema-incorrect
   column（per docs/CCAgentWorkSpace/E2/workspace/reports/
   2026-05-25--w2e_m4_v109_dual_adversarial_review.md §2）。

這個 test cover 4 個 source loader（kline / fills / liquidations / funding）
   的 SQL string，用 white-list + black-list grep 防止未來 regression：
   - black-list：歷史已知非法 column（size / close_fill / realized_net_bps /
     aggregator_type / close_reason_code）
   - white-list：empirical PG verify 過的真實 column 必出現

對齊 memory feedback_v_migration_pg_dry_run（2026-05-05）：
   Mac mock pytest 不能 catch PG runtime semantic，但 SQL string grep 是
   schema-coupled regression 補位手段 — 任何 future schema 改動 + SQL 改動
   都會被這個 test catch。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# 把 srv 加進 path
SRV_ROOT = Path(__file__).resolve().parents[3]
if str(SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(SRV_ROOT))

from helper_scripts.m4.sources.fills_loader import (  # noqa: E402
    FILLS_QUERY_SQL,
    build_fills_query,
)
from helper_scripts.m4.sources.funding_loader import (  # noqa: E402
    FUNDING_QUERY_SQL,
    build_funding_query,
)
from helper_scripts.m4.sources.kline_loader import (  # noqa: E402
    KLINE_QUERY_SQL,
    build_kline_query,
)
from helper_scripts.m4.sources.liquidations_loader import (  # noqa: E402
    LIQUIDATIONS_QUERY_SQL,
    build_liquidations_query,
)


# ──────────────────────────────────────────────────────────────────────────────
# Schema black-list — 已知非法 column 不可出現於任何 source loader SQL
# ──────────────────────────────────────────────────────────────────────────────


def _grep_whole_word(sql: str, token: str) -> list[str]:
    """grep SQL string 中是否出現完整 token（不含 substring 誤判）。

    為什麼 \\b：避免 `size` 誤匹 `cascade_size` 之類字串；token 必須是
    SQL identifier 邊界。
    """
    pattern = re.compile(r"\b" + re.escape(token) + r"\b")
    return pattern.findall(sql)


# ──────────────────────────────────────────────────────────────────────────────
# §1 fills_loader.py: trading.fills 真實 schema 對齊
# ──────────────────────────────────────────────────────────────────────────────


def test_fills_loader_uses_qty_not_size():
    """trading.fills 真實 column 是 qty 非 size（per V003 + empirical \\d trading.fills）。"""
    # white-list：必含 qty
    assert _grep_whole_word(FILLS_QUERY_SQL, "qty"), (
        "FILLS_QUERY_SQL 必含 qty column（empirical PG verify 2026-05-25）"
    )
    # black-list：不可含 size（即使 substring 形式如 cascade_size 也不該出現）
    assert not _grep_whole_word(FILLS_QUERY_SQL, "size"), (
        "FILLS_QUERY_SQL 不可含 size column — trading.fills 無此 column"
    )


def test_fills_loader_uses_realized_pnl_not_realized_net_bps():
    """trading.fills 真實 column 是 realized_pnl 非 realized_net_bps。

    realized_net_bps 可作為 SELECT 別名（derived from realized_pnl / notional * 10000），
    但不可作為 source column 引用。
    """
    # white-list：必含 realized_pnl
    assert _grep_whole_word(FILLS_QUERY_SQL, "realized_pnl"), (
        "FILLS_QUERY_SQL 必含 realized_pnl source column"
    )
    # 允許 realized_net_bps 出現作為 AS 別名，但必須伴隨 realized_pnl 計算式
    # （即 `realized_pnl / ... AS realized_net_bps`）。檢查順序：
    if "realized_net_bps" in FILLS_QUERY_SQL:
        # 必須是 AS 別名（前面要有 realized_pnl 計算式）
        assert "AS realized_net_bps" in FILLS_QUERY_SQL, (
            "realized_net_bps 只能作為 AS 別名出現，不可作為 source column 直接引用"
        )


def test_fills_loader_uses_entry_context_id_pattern_not_close_fill():
    """close fill 判定走 entry_context_id IS NOT NULL，不走 close_fill = TRUE。

    canonical pattern per program_code/ml_training/edge_label_backfill.py：
       - entry 行：entry_context_id IS NULL
       - close 行：entry_context_id 指向 entry 的 context_id
    """
    # white-list：必含 entry_context_id IS NOT NULL pattern
    assert "entry_context_id IS NOT NULL" in FILLS_QUERY_SQL, (
        "FILLS_QUERY_SQL 必用 `entry_context_id IS NOT NULL` 判定 close fill"
    )
    # black-list：不可含 close_fill column
    assert not _grep_whole_word(FILLS_QUERY_SQL, "close_fill"), (
        "FILLS_QUERY_SQL 不可含 close_fill — trading.fills 無此 column"
    )


def test_fills_loader_uses_exit_reason_not_close_reason_code():
    """trading.fills 真實 column 是 exit_reason（per V### schema）非 close_reason_code。"""
    # white-list：exit_reason 出現
    assert _grep_whole_word(FILLS_QUERY_SQL, "exit_reason"), (
        "FILLS_QUERY_SQL 必含 exit_reason column"
    )
    # black-list：不可含 close_reason_code
    assert not _grep_whole_word(FILLS_QUERY_SQL, "close_reason_code"), (
        "FILLS_QUERY_SQL 不可含 close_reason_code — trading.fills 無此 column"
    )


def test_fills_loader_engine_mode_whitelist_in_form():
    """engine_mode filter 必 IN ('live', 'live_demo')，不可單獨 = 'live'。"""
    # 必含 IN form
    assert "IN ('live', 'live_demo')" in FILLS_QUERY_SQL, (
        "FILLS_QUERY_SQL 必含 engine_mode IN ('live','live_demo') (per project_engine_mode_tag_live_demo)"
    )
    # 不可單獨 =live
    assert "engine_mode = 'live'" not in FILLS_QUERY_SQL, (
        "FILLS_QUERY_SQL 不可單獨 engine_mode = 'live' — 必含 live_demo"
    )


def test_fills_loader_build_query_returns_sql_tuple():
    """build_fills_query 返 (sql, params) tuple 對齊既有 contract。"""
    sql, params = build_fills_query(lookback_days=90)
    assert isinstance(sql, str)
    assert isinstance(params, dict)
    assert "lookback" in params
    assert params["lookback"] == "90 days"


# ──────────────────────────────────────────────────────────────────────────────
# §2 liquidations_loader.py: market.liquidations 真實 schema 對齊
# ──────────────────────────────────────────────────────────────────────────────


def test_liquidations_loader_uses_qty_not_size():
    """market.liquidations 真實 column 是 qty 非 size。"""
    # white-list：必含 qty（liq.qty 形式）
    assert "liq.qty" in LIQUIDATIONS_QUERY_SQL, (
        "LIQUIDATIONS_QUERY_SQL 必含 liq.qty column（empirical \\d market.liquidations）"
    )
    # black-list：不可含 liq.size 或獨立 size column
    assert "liq.size" not in LIQUIDATIONS_QUERY_SQL, (
        "LIQUIDATIONS_QUERY_SQL 不可含 liq.size — market.liquidations 無此 column"
    )


def test_liquidations_loader_no_aggregator_type():
    """market.liquidations 無 aggregator_type column（0 V### migration ADD）。

    spec §1.3 列出的 aggregator_type 是 PA 草稿階段的 illustrative pseudo-schema；
    empirical PG 是 SSOT。cascade detection 必走 caller-side 5min rolling
    （algorithms/event_window.detect_liquidation_cascade_events）。
    """
    assert not _grep_whole_word(LIQUIDATIONS_QUERY_SQL, "aggregator_type"), (
        "LIQUIDATIONS_QUERY_SQL 不可含 aggregator_type — market.liquidations 無此 column"
    )


def test_liquidations_loader_self_fill_filter_present():
    """self-fill 5s LEFT JOIN filter 必保留（防 self-fill cascade noise 污染）。"""
    assert "LEFT JOIN trading.fills" in LIQUIDATIONS_QUERY_SQL, (
        "LIQUIDATIONS_QUERY_SQL 必含 LEFT JOIN trading.fills self-fill filter"
    )
    assert "f.fill_id IS NULL" in LIQUIDATIONS_QUERY_SQL, (
        "LIQUIDATIONS_QUERY_SQL 必含 f.fill_id IS NULL 過濾 self-fill 命中行"
    )


def test_liquidations_loader_build_query_returns_sql_tuple():
    """build_liquidations_query 返 (sql, params) tuple 對齊既有 contract。"""
    sql, params = build_liquidations_query(lookback_days=90)
    assert isinstance(sql, str)
    assert isinstance(params, dict)
    assert "lookback" in params
    assert "self_fill_window" in params


# ──────────────────────────────────────────────────────────────────────────────
# §3 kline_loader.py: market.klines schema 對齊（regression baseline）
# ──────────────────────────────────────────────────────────────────────────────


def test_kline_loader_uses_canonical_columns():
    """market.klines 真實 column 對齊 baseline regression。"""
    for token in ("symbol", "timeframe", "ts", "open", "high", "low", "close", "volume"):
        assert _grep_whole_word(KLINE_QUERY_SQL, token), (
            f"KLINE_QUERY_SQL 必含 {token} column"
        )


def test_kline_loader_excludes_partial_bar():
    """kline source 必排 partial bar（last bar ts == now() 不可被讀入）。"""
    assert "MAX(ts) - INTERVAL '1 minute'" in KLINE_QUERY_SQL, (
        "KLINE_QUERY_SQL 必含 partial bar 排除 subquery（per W1-B spec §1.1）"
    )


def test_kline_loader_build_query_returns_sql_tuple():
    """build_kline_query 返 (sql, params) tuple 對齊既有 contract。"""
    sql, params = build_kline_query(symbols=["BTCUSDT"], timeframes=["1m"], lookback_days=30)
    assert isinstance(sql, str)
    assert isinstance(params, dict)
    assert params["symbols"] == ["BTCUSDT"]


# ──────────────────────────────────────────────────────────────────────────────
# §4 funding_loader.py: market.funding_rates schema 對齊
# ──────────────────────────────────────────────────────────────────────────────


def test_funding_loader_uses_canonical_columns():
    """market.funding_rates 真實 column 對齊。"""
    for token in ("symbol", "ts", "funding_rate"):
        assert _grep_whole_word(FUNDING_QUERY_SQL, token), (
            f"FUNDING_QUERY_SQL 必含 {token} column"
        )


def test_funding_loader_annualized_calculation():
    """funding_rate * 3 * 365 = annualized funding（per Bybit 8h × 3 settlement/day）。"""
    assert "funding_rate * 3 * 365" in FUNDING_QUERY_SQL, (
        "FUNDING_QUERY_SQL 必含 annualized funding 計算（per W1-B spec §1.4）"
    )


def test_funding_loader_build_query_returns_sql_tuple():
    """build_funding_query 返 (sql, params) tuple 對齊既有 contract。"""
    sql, params = build_funding_query(lookback_days=90)
    assert isinstance(sql, str)
    assert isinstance(params, dict)


# ──────────────────────────────────────────────────────────────────────────────
# §5 跨 loader black-list — 所有非法 column 在所有 loader 0 hit
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "illegal_token",
    [
        "close_fill",  # 不存在於 trading.fills
        "close_reason_code",  # 不存在於 trading.fills
        "aggregator_type",  # 不存在於 market.liquidations
    ],
)
def test_no_loader_uses_illegal_column(illegal_token: str):
    """非法 column 在 4 個 source loader 全 0 hit。"""
    all_sql = (
        KLINE_QUERY_SQL
        + "\n"
        + FILLS_QUERY_SQL
        + "\n"
        + LIQUIDATIONS_QUERY_SQL
        + "\n"
        + FUNDING_QUERY_SQL
    )
    assert not _grep_whole_word(all_sql, illegal_token), (
        f"非法 column '{illegal_token}' 不可出現在任何 source loader SQL"
    )
