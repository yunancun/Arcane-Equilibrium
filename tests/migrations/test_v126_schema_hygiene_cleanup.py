"""Static migration tests for V126 schema hygiene cleanup.

這是 Mac-runnable 靜態守衛（讀檔 + 去註釋 + 正規化後字串斷言），不需 live DB。
作用：釘死 V126 的 load-bearing 不變量，防止未來 regression：

  - recent_sequences【絕對不可】出現在 DROP COLUMN（CC BLOCKER：view-fronted）。
  - 全 destructive drop 必 RESTRICT，不可 CASCADE。
  - 全 DROP 必 IF EXISTS（冪等）。
  - Packet 1（damaged）只用 pg_depend guard，不用 count(*)=0（故意非空）。
  - Packet 2（legacy）用 count(*)=0 + pg_depend 完整 guard。
  - Packet 3 恰好 7 個指定欄、且皆在 decision_context_snapshots 上。

注意：runtime semantic（runner-tx 包裹 / hypertable DROP COLUMN /
pg_depend 實際命中數）必須 Linux double-apply dry-run 實證，本靜態測試不替代。
"""

from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
V126_PATH = _SRV_ROOT / "sql" / "migrations" / "V126__schema_hygiene_cleanup.sql"

# Packet 1：4 個事故備份表（故意非空）
_DAMAGED_TABLES = (
    "trading.risk_verdicts_damaged_20260414_130607",
    "trading.fills_damaged_20260414_130607",
    "trading.intents_damaged_20260414_130607",
    "trading.orders_damaged_20260414_130607",
)

# Packet 2：6 個空 legacy 表
_LEGACY_TABLES = (
    "public.ai_cost_events_legacy",
    "public.market_tickers_legacy",
    "public.observer_verdicts_legacy",
    "public.order_events_legacy",
    "public.position_snapshots_legacy",
    "public.trade_executions_legacy",
)

# Packet 3：恰好 7 個乾淨死欄位（recent_sequences / regime_1h 不在內）
_DEAD_COLUMNS = (
    "predictor_decision",
    "shrinkage_decision",
    "predict_latency_us",
    "disagreed",
    "predicted_q10",
    "predicted_q50",
    "predicted_q90",
)


def _read_sql() -> str:
    assert V126_PATH.exists(), f"Migration file missing: {V126_PATH}"
    return V126_PATH.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def _normalized_sql() -> str:
    """去註釋 + lowercase + 摺疊空白。"""
    return re.sub(r"\s+", " ", _strip_sql_comments(_read_sql()).lower())


# ============================================================
# CC BLOCKER：recent_sequences 必須被排除
# ============================================================
def test_v126_excludes_recent_sequences_from_any_drop() -> None:
    """recent_sequences 被 learning.scorer_training_features view SELECT
    （V005:267），是 view-fronted；放進 V126 的 DROP COLUMN 會破壞 view。
    本斷言釘死它【絕不】出現在任何 executable DROP 語句。"""
    sql = _normalized_sql()
    assert "recent_sequences" not in sql, (
        "CC BLOCKER 違反：recent_sequences 是 view-fronted，不可出現在 V126 "
        "（即使註釋也應避免，以防去註釋後仍命中；它屬延後的 Packet 4）"
    )
    # regime_1h 同屬 view-fronted 延後組，也不應在本 migration drop。
    assert "regime_1h" not in sql, (
        "regime_1h 是 view-fronted（V005:237），屬延後 Packet 4，不可出現在 V126"
    )


# ============================================================
# 全域硬約束：RESTRICT / IF EXISTS / 無 CASCADE
# ============================================================
def test_v126_all_drops_use_restrict_not_cascade() -> None:
    sql = _normalized_sql()
    assert "cascade" not in sql, "destructive drop 不可用 CASCADE（必 RESTRICT fail-loud）"
    # 每張表的 DROP TABLE 必 RESTRICT
    for table in _DAMAGED_TABLES + _LEGACY_TABLES:
        assert f"drop table if exists {table} restrict" in sql, (
            f"{table} 的 DROP TABLE 必須是 'IF EXISTS ... RESTRICT'"
        )


def test_v126_table_drops_are_idempotent_if_exists() -> None:
    sql = _normalized_sql()
    # IF EXISTS 數量 = 10 個 DROP TABLE + 7 個 DROP COLUMN
    drop_table_if_exists = sql.count("drop table if exists ")
    drop_column_if_exists = sql.count("drop column if exists ")
    assert drop_table_if_exists == 10, (
        f"預期 10 個 'DROP TABLE IF EXISTS'，實得 {drop_table_if_exists}"
    )
    assert drop_column_if_exists == len(_DEAD_COLUMNS), (
        f"預期 {len(_DEAD_COLUMNS)} 個 'DROP COLUMN IF EXISTS'，實得 {drop_column_if_exists}"
    )


def test_v126_is_single_transaction() -> None:
    """與最新同類 migration（V115）對齊：body 內顯式 BEGIN;...COMMIT;
    使整批清理為單一原子單位（任一 guard RAISE → 全回滾）。"""
    sql = _normalized_sql()
    assert "begin;" in sql, "缺顯式 BEGIN;（與 V115 慣例對齊）"
    assert "commit;" in sql, "缺顯式 COMMIT;（與 V115 慣例對齊）"
    # 不走 no-transaction opt-out（檔首不可是 -- no-transaction）
    assert not _read_sql().lstrip().lower().startswith("-- no-transaction"), (
        "本檔不應 opt-out runner 事務（不可檔首 -- no-transaction）"
    )


# ============================================================
# Packet 1：damaged 表只用 pg_depend guard（故意非空 → 不用 count=0）
# ============================================================
def test_v126_packet1_damaged_uses_pg_depend_guard_only() -> None:
    sql = _normalized_sql()
    for table in _DAMAGED_TABLES:
        # 必有 to_regclass 早退 + pg_depend dependents guard
        assert f"to_regclass('{table}')" in sql, f"{table} 缺 to_regclass 早退守衛"
        assert f"d.refobjid = '{table}'::regclass" in sql, (
            f"{table} 缺 pg_depend dependents 守衛"
        )

    # damaged 表故意非空：不可對 4 張 damaged 表做 count(*) 非空檢查。
    # 用「damaged 表名 + count(*)」的同行出現作粗篩。
    for table in _DAMAGED_TABLES:
        bare = table.split(".", 1)[1]  # e.g. risk_verdicts_damaged_20260414_130607
        # 在去註釋 SQL 中，damaged 表不應出現在 'select count(*) from <table>' 句式
        assert f"select count(*) from {table}" not in sql, (
            f"Packet 1 不應對故意非空的 {table} 做 count(*)=0 檢查"
        )
        # 額外保險：damaged bare 名也不應緊跟 count(*) from
        assert f"count(*) from trading.{bare}" not in sql, (
            f"Packet 1 不應對 {table} 做 count(*) 檢查"
        )


# ============================================================
# Packet 2：legacy 表用 count(*)=0 + pg_depend 完整 guard
# ============================================================
def test_v126_packet2_legacy_uses_full_guard() -> None:
    sql = _normalized_sql()
    for table in _LEGACY_TABLES:
        assert f"to_regclass('{table}')" in sql, f"{table} 缺 to_regclass 早退守衛"
        assert f"select count(*) from {table}" in sql, (
            f"{table} 缺 count(*)=0 守衛（legacy 表應為空）"
        )
        assert f"d.refobjid = '{table}'::regclass" in sql, (
            f"{table} 缺 pg_depend dependents 守衛"
        )
        # 非空 → fail-loud
        assert f"v126 packet 2" in sql  # packet 2 fail 訊息存在
        assert "is not empty" in sql


# ============================================================
# Packet 3：恰好 7 欄，全在 decision_context_snapshots
# ============================================================
def test_v126_packet3_drops_exactly_seven_named_columns() -> None:
    sql = _normalized_sql()
    # DROP COLUMN 必掛在正確的 hypertable 上
    assert "alter table trading.decision_context_snapshots" in sql, (
        "Packet 3 必須 ALTER trading.decision_context_snapshots"
    )
    for col in _DEAD_COLUMNS:
        assert f"drop column if exists {col}" in sql, (
            f"Packet 3 缺 DROP COLUMN IF EXISTS {col}"
        )
    # 防止多 drop：DROP COLUMN 次數恰好等於 7
    assert sql.count("drop column if exists ") == len(_DEAD_COLUMNS)


# ============================================================
# 硬邊界：不觸碰 hard boundary / 不創建新物件
# ============================================================
def test_v126_does_not_touch_hard_boundaries_or_create_objects() -> None:
    sql = _normalized_sql()
    for forbidden in (
        "create table",
        "create index",
        "create view",
        "create materialized",
        "insert into",
        "update ",
        "delete from",
        "max_retries",
        "live_execution_allowed",
        "execution_authority",
        "system_mode",
    ):
        assert forbidden not in sql, (
            f"V126 是純回收 migration，不應出現 '{forbidden}'"
        )
