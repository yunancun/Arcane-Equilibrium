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
from helper_scripts.m4.draft_writer import (  # noqa: E402
    DRAFT_INSERT_SQL,
    build_writeback_payload,
    payload_to_params,
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

    realized_net_bps 可作為 SELECT 別名（derived from realized_pnl - fees），但不可作為
    source column 引用。
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


def test_fills_loader_realized_net_bps_subtracts_entry_and_exit_fee():
    """M4 net label 必扣 close fee + 單一代表 entry fee；close-row gross PnL 不可當 net label。

    entry fee 走 LATERAL single-representative（非 fan-out LEFT JOIN）：扣 close fee
    `COALESCE(f.fee, 0)` + 代表 entry fee `entry_rep.entry_fee`。
    """
    assert "LEFT JOIN LATERAL" in FILLS_QUERY_SQL
    assert "COALESCE(f.fee, 0)" in FILLS_QUERY_SQL
    assert "entry_rep.entry_fee" in FILLS_QUERY_SQL
    assert "AS realized_net_pnl" in FILLS_QUERY_SQL
    assert "AS realized_total_fee" in FILLS_QUERY_SQL


def test_fills_loader_entry_fee_uses_single_representative_lateral_not_fanout():
    """entry fee 必走 single-representative LATERAL，不可用會 fan-out 的裸 LEFT JOIN。

    為什麼：裸 `LEFT JOIN trading.fills entry_fill ON context_id = entry_context_id`
    有兩缺陷 —— (1) context_id 非唯一 → 行倍增 fan-out；(2) 缺 `entry_context_id
    IS NULL` 謂詞 → close 行被當 entry 命中、close fee 被雙重扣除。
    修法 = LATERAL ORDER BY ts ASC LIMIT 1 取最早一筆真 entry 行。
    """
    # white-list：必走 LATERAL + entry-row 謂詞 entry_context_id IS NULL + ORDER/LIMIT
    assert "LEFT JOIN LATERAL" in FILLS_QUERY_SQL, (
        "FILLS_QUERY_SQL 必用 LEFT JOIN LATERAL 取單一代表 entry fee"
    )
    assert "e.entry_context_id IS NULL" in FILLS_QUERY_SQL, (
        "LATERAL 必含 entry-row 謂詞 e.entry_context_id IS NULL（防 close 行被當 entry）"
    )
    assert "ORDER BY e.ts ASC" in FILLS_QUERY_SQL and "LIMIT 1" in FILLS_QUERY_SQL, (
        "LATERAL 必 ORDER BY e.ts ASC LIMIT 1 取最早一筆真 entry"
    )
    # black-list：不可殘留舊 fan-out 裸 LEFT JOIN（entry_fill alias 上的 ON 等值 join）
    assert "LEFT JOIN trading.fills entry_fill" not in FILLS_QUERY_SQL, (
        "FILLS_QUERY_SQL 不可含 fan-out 裸 `LEFT JOIN trading.fills entry_fill`"
    )
    assert "COALESCE(entry_fill.fee, 0)" not in FILLS_QUERY_SQL, (
        "不可殘留 fan-out 版 entry_fill.fee 引用"
    )


def test_fills_loader_excludes_close_shaped_rows_as_representative_entry():
    """代表 entry 行必排除 close-shaped strategy_name 前綴（writer 會誤標 partial-reduce）。

    Q-query 實證：`risk_close:fast_track_reduce_half` 行 entry_context_id IS NULL
    卻語義上是 close；不排除會被當代表 entry，污染 entry fee。
    """
    for prefix in (
        "risk_close:%%",
        "orphan_close:%%",
        "adopted_close:%%",
        "shadow_fill:%%",
        "unattributed:%%",
    ):
        assert f"NOT LIKE '{prefix}'" in FILLS_QUERY_SQL, (
            f"LATERAL 代表 entry 篩選必排除 '{prefix}' close-shaped 前綴"
        )


def test_fills_loader_entry_missing_yields_null_net_label_not_zero():
    """entry-missing（無代表 entry 行）時 net label 必 NULL，不可 COALESCE 成 0 捏造 gross。

    D-query 實證 26 rows 無代表 entry；COALESCE(...,0) 會捏造樂觀 gross label
    污染 M4 樣本。改 CASE WHEN entry_rep.entry_fill_found THEN ... ELSE NULL，
    並 emit entry_fill_found discriminator 供 caller dropna / flag。
    """
    # net label 必走 entry_fill_found CASE gate（非無條件計算）
    assert "CASE WHEN entry_rep.entry_fill_found" in FILLS_QUERY_SQL, (
        "realized_net_pnl/bps 必用 CASE WHEN entry_rep.entry_fill_found 守衛"
    )
    assert "ELSE NULL END AS realized_net_pnl" in FILLS_QUERY_SQL, (
        "entry-missing 時 realized_net_pnl 必 NULL"
    )
    assert "ELSE NULL END AS realized_net_bps" in FILLS_QUERY_SQL, (
        "entry-missing 時 realized_net_bps 必 NULL"
    )
    # discriminator 必輸出供 caller dropna
    assert "AS entry_fill_found" in FILLS_QUERY_SQL, (
        "FILLS_QUERY_SQL 必輸出 entry_fill_found discriminator column"
    )


def test_fills_loader_lateral_requires_entry_fee_not_null():
    """代表 entry 行必 `e.fee IS NOT NULL`（DIRTY-FIX LOW-1）。

    為什麼：trading.fills.fee 為 REAL DEFAULT 0 可空（V003）。若代表 entry fee 為
    NULL，entry_rep.entry_fee=NULL → net label 算術回 NULL 但 entry_fill_found 旗標
    仍 TRUE → discriminator 失真。加 `e.fee IS NOT NULL` 謂詞 = entry_fill_found=TRUE
    ⟹ entry_fee 必非 NULL，精確化 discriminator 契約。
    """
    assert "e.fee IS NOT NULL" in FILLS_QUERY_SQL, (
        "LATERAL 必含 `e.fee IS NOT NULL` 謂詞（保 entry_fill_found=TRUE ⟹ entry_fee 非 NULL）"
    )


def test_fills_loader_net_label_guards_close_realized_pnl_not_null():
    """close 行 realized_pnl 為 NULL 時 net label 必 NULL（DIRTY-FIX LOW-2）。

    為什麼：舊版 net label 用 `COALESCE(f.realized_pnl, 0)`，close 行 realized_pnl
    為 NULL 時會算成 `0 - fee - entry_fee` = 純費用小負值，被當真實 net label 餵入
    M4 → 靜默捏造小負 bps。改 CASE 加 `f.realized_pnl IS NOT NULL` 守衛 + 移除
    realized_pnl 的 COALESCE，realized_pnl NULL 時 emit NULL label。
    """
    # CASE 守衛必含 close 行 realized_pnl 非空條件
    assert "entry_rep.entry_fill_found AND f.realized_pnl IS NOT NULL" in FILLS_QUERY_SQL, (
        "net label CASE 必含 `entry_rep.entry_fill_found AND f.realized_pnl IS NOT NULL` 守衛"
    )
    # black-list：net label 算術不可再 COALESCE realized_pnl 成 0（會捏造純費用小負值）
    assert "COALESCE(f.realized_pnl, 0)" not in FILLS_QUERY_SQL, (
        "net label 不可用 COALESCE(f.realized_pnl, 0) — close 行 realized_pnl NULL 時"
        "會捏造純費用小負 bps；應 emit NULL label"
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


# ──────────────────────────────────────────────────────────────────────────────
# §6 draft_writer.py: learning.hypotheses V100 base + V103 EXTEND 真實 schema
# ──────────────────────────────────────────────────────────────────────────────
#
# 為什麼這個 §6：W1-C Round 1/2 IMPL 51 → 70 pytest 全 PASS 但 0 個 test 真正 grep
# DRAFT_INSERT_SQL column 名是否對齊 PG 真實 schema。W2-F QA + FA HIGH BLOCKER
# (commit fbfbd184) catch：6 個 m4_attribute_* column 不存在於 production
# learning.hypotheses。本 §6 補位 schema-grep regression。
#
# Empirical PG verify 2026-05-25 (`\\d learning.hypotheses`)：
#    19 column total = V100 base 13 + V103 EXTEND 6；**0 個 m4_attribute_***。


@pytest.mark.parametrize(
    "illegal_attribute_column",
    [
        "m4_attribute_n",
        "m4_attribute_p_bonferroni",
        "m4_attribute_effect_size",
        "m4_attribute_subperiod_pass",
        "m4_attribute_graveyard_flag",
        "m4_attribute_silhouette",
    ],
)
def test_draft_writer_no_m4_attribute_column(illegal_attribute_column: str):
    """DRAFT_INSERT_SQL 不可含 6 個 m4_attribute_* column（empirical 不存在）。

    W2-F QA + FA HIGH BLOCKER 教訓：first cron fire 會 PG ERROR
    `column "m4_attribute_n" of relation "hypotheses" does not exist`。
    """
    assert not _grep_whole_word(DRAFT_INSERT_SQL, illegal_attribute_column), (
        f"DRAFT_INSERT_SQL 不可含 '{illegal_attribute_column}' — "
        f"empirical PG learning.hypotheses 0 個 m4_attribute_* column"
    )


def test_draft_writer_writes_v100_base_required_columns():
    """V100 base 5 NOT NULL required column 必出現於 DRAFT_INSERT_SQL。"""
    required_v100_columns = (
        "strategy_name",
        "pre_reg_ts",
        "pre_reg_hash",
        "status",
        "engine_mode",
    )
    for col in required_v100_columns:
        assert _grep_whole_word(DRAFT_INSERT_SQL, col), (
            f"DRAFT_INSERT_SQL 必含 V100 base NOT NULL column '{col}'"
        )


def test_draft_writer_writes_v103_extend_real_columns():
    """V103 EXTEND 6 real column 必出現於 DRAFT_INSERT_SQL（per W1-A §7.3 mapping）。

    `decision_lease_draft_id` 必 audit chain backref；不可省略。
    """
    required_v103_columns = (
        "hypothesis_source_module",
        "leakage_scan_pass",
        "bonferroni_corrected_p",
        "replicability_score",
        "decision_lease_draft_id",
        "cowork_review_status",
    )
    for col in required_v103_columns:
        assert _grep_whole_word(DRAFT_INSERT_SQL, col), (
            f"DRAFT_INSERT_SQL 必含 V103 EXTEND column '{col}'"
        )


def test_draft_writer_w1a_spec_7_3_mapping_n_to_min_sample_size():
    """W1-A spec §7.3 mapping：attribute_n → min_sample_size（V100 base INTEGER）。

    per W1-A spec line 695 + W2-F QA report §5.3 mapping invariant。
    """
    assert _grep_whole_word(DRAFT_INSERT_SQL, "min_sample_size"), (
        "DRAFT_INSERT_SQL 必含 min_sample_size column（W1-A §7.3 attribute_n mapping）"
    )


def test_draft_writer_hypothesis_source_module_explicit_m4_auto():
    """INSERT SQL 必顯式設 hypothesis_source_module='M4_AUTO'（不依 DEFAULT 'OPERATOR'）。

    per V103 spec §2.2 backfill 'M4_AUTO' silent contamination 警示；M4 寫入路徑顯式設。
    """
    assert "'M4_AUTO'" in DRAFT_INSERT_SQL, (
        "DRAFT_INSERT_SQL 必含顯式 'M4_AUTO' literal（hypothesis_source_module）"
    )


def test_draft_writer_cowork_review_status_explicit_none():
    """INSERT SQL 必顯式設 cowork_review_status='NONE'（Y1 不啟 Cowork review）。"""
    assert "'NONE'" in DRAFT_INSERT_SQL, (
        "DRAFT_INSERT_SQL 必含顯式 'NONE' literal（cowork_review_status）"
    )


def test_draft_writer_no_evidence_json_column():
    """DRAFT_INSERT_SQL 不可含 evidence_json column（empirical learning.hypotheses 0 hit）。

    W1-C Round 3 dispatch packet 提及 `evidence_json` 但 empirical PG schema 不含；
    W1-A spec §7.3 mapping 也未要求；本 IMPL 採 caller-side audit log emit 取代。
    """
    assert not _grep_whole_word(DRAFT_INSERT_SQL, "evidence_json"), (
        "DRAFT_INSERT_SQL 不可含 evidence_json — empirical learning.hypotheses 0 hit"
    )


def test_draft_writer_no_status_promote_past_preregistered():
    """SQL 字串中不可出現 'live' / 'promoted' / 'rejected' 作為 INSERT status 常量。

    per W1-B spec §0 I-5 + AMD-2026-05-21-01 protected scope (a)：M4 不可 promote past
    'preregistered'。SQL 中 status 走 %(status)s placeholder，build_writeback_payload
    端 reject promote past。
    """
    # SQL 中 status 走 placeholder 不應 hard-code 'live' 之類常量
    for forbidden in ("'live'", "'promoted'", "'rejected'"):
        assert forbidden not in DRAFT_INSERT_SQL, (
            f"DRAFT_INSERT_SQL 不可出現 {forbidden} 常量（M4 status placeholder only）"
        )


def test_draft_writer_returns_hypothesis_id_for_audit_backref():
    """INSERT 必 RETURNING hypothesis_id — caller 需取得 ID 為下游 audit log emit / lease 更新。

    為什麼必含 RETURNING：BIGSERIAL DEFAULT nextval 後 caller 需要 ID 作 audit chain
    backref；INSERT without RETURNING 失去 audit chain key。
    """
    assert "RETURNING hypothesis_id" in DRAFT_INSERT_SQL, (
        "DRAFT_INSERT_SQL 必含 RETURNING hypothesis_id（audit chain backref）"
    )


def test_draft_writer_engine_mode_validation_blocks_paper():
    """engine_mode='paper' 必 reject（per CLAUDE.md §七 + memory project_engine_mode_tag_live_demo）。"""
    import uuid as uuid_mod

    with pytest.raises(ValueError, match="engine_mode"):
        build_writeback_payload(
            strategy_name="grid",
            n_observations=100,
            raw_p_value=1e-10,
            cohens_d=0.5,
            status_candidate="preregistered",
            decision_lease_draft_id=uuid_mod.uuid4(),
            engine_mode="paper",  # 必 fail
        )


def test_draft_writer_rejects_exploratory_pg_status():
    """analysis lane exploratory 不可直接寫 learning.hypotheses.status。"""
    import uuid as uuid_mod

    with pytest.raises(ValueError, match="draft.*preregistered"):
        build_writeback_payload(
            strategy_name="grid",
            n_observations=100,
            raw_p_value=0.5,
            cohens_d=0.0,
            status_candidate="exploratory",
            decision_lease_draft_id=uuid_mod.uuid4(),
        )


def test_draft_writer_replicability_score_composite_range():
    """replicability_score composite 必在 [0,1] (V103 EXTEND CHECK constraint)。"""
    import uuid as uuid_mod

    # 高分情境：強 cohens_d + subperiod pass + 高 silhouette
    payload_high = build_writeback_payload(
        strategy_name="grid",
        n_observations=100,
        raw_p_value=1e-10,
        cohens_d=2.5,  # |d|/3 = 0.83
        status_candidate="preregistered",
        decision_lease_draft_id=uuid_mod.uuid4(),
        subperiod_pass=True,
        silhouette=0.9,
    )
    assert payload_high.replicability_score is not None
    assert 0.0 <= payload_high.replicability_score <= 1.0, (
        f"replicability_score 超範圍 [0,1]: {payload_high.replicability_score}"
    )

    # 低分情境：弱 cohens_d + subperiod fail + 低 silhouette
    payload_low = build_writeback_payload(
        strategy_name="grid",
        n_observations=100,
        raw_p_value=0.5,
        cohens_d=0.0,
        status_candidate="draft",
        decision_lease_draft_id=uuid_mod.uuid4(),
        subperiod_pass=False,
        silhouette=0.0,
    )
    assert payload_low.replicability_score is not None
    assert 0.0 <= payload_low.replicability_score <= 1.0


def test_draft_writer_bonferroni_p_clamped_to_unit_interval():
    """bonferroni_corrected_p 必 clamp [0,1] 對齊 V103 EXTEND CHECK [0,1]。"""
    import uuid as uuid_mod

    # raw_p = 2.5 → clamp 到 1.0
    payload_over = build_writeback_payload(
        strategy_name="grid",
        n_observations=100,
        raw_p_value=2.5,
        cohens_d=0.5,
        status_candidate="draft",
        decision_lease_draft_id=uuid_mod.uuid4(),
    )
    assert payload_over.bonferroni_corrected_p == 1.0

    # raw_p = -0.1 → clamp 到 0.0
    payload_neg = build_writeback_payload(
        strategy_name="grid",
        n_observations=100,
        raw_p_value=-0.1,
        cohens_d=0.5,
        status_candidate="draft",
        decision_lease_draft_id=uuid_mod.uuid4(),
    )
    assert payload_neg.bonferroni_corrected_p == 0.0


def test_draft_writer_pre_reg_hash_deterministic():
    """同 input 必產生同 pre_reg_hash（canonical JSON SHA-256 不變式）。"""
    import uuid as uuid_mod

    lease_id = uuid_mod.uuid4()
    p1 = build_writeback_payload(
        strategy_name="grid",
        n_observations=100,
        raw_p_value=1e-10,
        cohens_d=0.5,
        status_candidate="preregistered",
        decision_lease_draft_id=lease_id,
        subperiod_pass=True,
        silhouette=0.6,
    )
    p2 = build_writeback_payload(
        strategy_name="grid",
        n_observations=100,
        raw_p_value=1e-10,
        cohens_d=0.5,
        status_candidate="preregistered",
        decision_lease_draft_id=lease_id,
        subperiod_pass=True,
        silhouette=0.6,
    )
    assert p1.pre_reg_hash == p2.pre_reg_hash, "同 input 必產生同 pre_reg_hash"
    # SHA-256 hex 長度 = 64
    assert len(p1.pre_reg_hash) == 64


def test_draft_writer_payload_to_params_excludes_caller_metadata():
    """payload_to_params 不可含 caller-side metadata（不入 PG）。"""
    import uuid as uuid_mod

    payload = build_writeback_payload(
        strategy_name="grid",
        n_observations=100,
        raw_p_value=1e-10,
        cohens_d=0.5,
        status_candidate="preregistered",
        decision_lease_draft_id=uuid_mod.uuid4(),
        graveyard_flag=True,
    )
    params = payload_to_params(payload)
    # caller-side metadata 不入 INSERT params
    forbidden_keys = {
        "raw_p_value",
        "cohens_d",
        "subperiod_pass",
        "graveyard_flag",
        "silhouette",
        "hypothesis_id",  # BIGSERIAL by PG
    }
    found_forbidden = forbidden_keys & params.keys()
    assert not found_forbidden, (
        f"payload_to_params 含禁止字段 {found_forbidden}（應為 caller-side metadata）"
    )
