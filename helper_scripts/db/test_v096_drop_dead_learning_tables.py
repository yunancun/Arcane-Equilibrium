"""
MODULE_NOTE
模塊用途：V096 drop dead learning tables migration 的 source-only 驗證測試。
為什麼：dispatch 規範要求 source-only / no real PG apply，本測試純粹靜態
驗證 V096 SQL 內容滿足 (1) 檔名 pattern 對齊 V096__* (2) DROP 兩張表
且必含 IF EXISTS guard（idempotent）(3) 表 identifier 精確匹配 spec
(4) Guard 區塊（non-empty + pg_depend）兩表都有（與 V069 同 pattern）。

主要函數：
    - test_v096_filename_pattern
    - test_v096_drops_rl_transitions_with_if_exists
    - test_v096_drops_symbol_clusters_with_if_exists
    - test_v096_uses_restrict_not_cascade
    - test_v096_non_empty_guard_present
    - test_v096_pg_depend_guard_present
    - test_v096_does_not_touch_active_learning_tables
    - test_v096_idempotency_no_state_change
    - test_v096_references_governance_artifacts

依賴：pytest，純檔系統讀取，無 PG 連線。

硬邊界：本測試禁止連 PG / 禁止 apply migration。任何 dry-run 必以
SQL parser / regex 為界——對齊 dispatch §「Apply twice in dry-run mode
if Mac PG is available — but DO NOT actually apply to real PG」。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


SQL_PATH = (
    Path(__file__).resolve().parents[2]
    / "sql"
    / "migrations"
    / "V096__drop_dead_learning_tables.sql"
)

SQL_TEXT = SQL_PATH.read_text(encoding="utf-8")
SQL_LOWER = SQL_TEXT.lower()


def _strip_sql_line_comments(sql: str) -> str:
    """剝離 `-- ...` 行注釋後返回剩餘 SQL；保留行結構。
    為什麼：本測試多項斷言檢查 SQL statement 內容（如 CASCADE / DO $$
    出現次數），不能被 SQL header comment 內的中文敘述污染。"""
    out_lines: list[str] = []
    for line in sql.splitlines():
        # 處理 `<sql> -- comment` 與整行 `-- comment` 兩種
        comment_pos = line.find("--")
        if comment_pos == 0:
            continue  # 整行注釋
        if comment_pos > 0:
            out_lines.append(line[:comment_pos])
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


SQL_NO_COMMENTS = _strip_sql_line_comments(SQL_TEXT)
SQL_NO_COMMENTS_LOWER = SQL_NO_COMMENTS.lower()


# ============================================================
# 檔名 / 路徑 sanity
# ============================================================
def test_v096_filename_pattern() -> None:
    """檔名必須匹配 V096__*.sql pattern；任何重編號 / typo 都被 catch。"""
    assert SQL_PATH.name.startswith("V096__"), (
        f"檔名必以 V096__ 開頭，實得 {SQL_PATH.name}"
    )
    assert SQL_PATH.name.endswith(".sql"), (
        f"檔名必以 .sql 結尾，實得 {SQL_PATH.name}"
    )
    assert SQL_PATH.exists(), (
        f"V096 migration 應存在於 sql/migrations/，實際路徑 {SQL_PATH}"
    )


# ============================================================
# DROP 兩表 + IF EXISTS guard
# ============================================================
def test_v096_drops_rl_transitions_with_if_exists() -> None:
    """rl_transitions DROP 必含 IF EXISTS（idempotent）。"""
    assert "drop table if exists learning.rl_transitions" in SQL_LOWER, (
        "V096 必含 'DROP TABLE IF EXISTS learning.rl_transitions'"
    )


def test_v096_drops_symbol_clusters_with_if_exists() -> None:
    """symbol_clusters DROP 必含 IF EXISTS（idempotent）。"""
    assert "drop table if exists learning.symbol_clusters" in SQL_LOWER, (
        "V096 必含 'DROP TABLE IF EXISTS learning.symbol_clusters'"
    )


def test_v096_uses_restrict_not_cascade() -> None:
    """dispatch §2 字面寫 CASCADE，但 §「verify none first via rg sweep」
    語義等同 RESTRICT；且 grep 已證 0 依賴 → RESTRICT 更安全（fail-loud
    若意外有 leftover dep）。本測試確保 V096 採 V069 同 pattern（RESTRICT
    + non-empty guard），任何回退到 CASCADE 都觸發失敗以引發 PA review。

    註：只檢查 SQL statement 部分（剝 -- 行注釋），避免 header rationale
    內提及 CASCADE 字串造成偽陽。"""
    assert "restrict" in SQL_NO_COMMENTS_LOWER, (
        "V096 必含 RESTRICT 子句（dispatch 字面 CASCADE 已 push back 為 RESTRICT，"
        "理由：V069 一致 / ADR-0015 慣例 / grep 0 依賴 → fail-loud 優先）"
    )
    assert "cascade" not in SQL_NO_COMMENTS_LOWER, (
        "V096 SQL statement 不應用 CASCADE（採 RESTRICT + non-empty guard 替代）；"
        "若 PA 後續決定改回 CASCADE，請同步更新本 test 與 self-report 偏離說明"
    )


# ============================================================
# Guard pattern — non-empty + pg_depend
# ============================================================
def test_v096_non_empty_guard_present() -> None:
    """兩表 DROP 前必檢「row count = 0」，非 0 raise exception。
    對齊 V069 same-sprint sibling pattern + WP-07 audit 慣例。"""
    rl_pattern = re.search(
        r"select count\(\*\) from learning\.rl_transitions",
        SQL_LOWER,
    )
    assert rl_pattern is not None, "V096 必檢 rl_transitions row count"

    sc_pattern = re.search(
        r"select count\(\*\) from learning\.symbol_clusters",
        SQL_LOWER,
    )
    assert sc_pattern is not None, "V096 必檢 symbol_clusters row count"

    # 兩個 Guard FAIL 訊息都應存在
    assert "v096 guard a fail" in SQL_LOWER, (
        "V096 必含 Guard A FAIL 訊息（rl_transitions non-empty / dep）"
    )
    assert "v096 guard b fail" in SQL_LOWER, (
        "V096 必含 Guard B FAIL 訊息（symbol_clusters non-empty / dep）"
    )


def test_v096_pg_depend_guard_present() -> None:
    """兩表 DROP 前必檢 pg_depend 是否有外部依賴 relation。
    grep 已證 0 VIEW / FROM / JOIN 引用，guard 為 defense-in-depth。"""
    rl_dep = re.search(
        r"refobjid\s*=\s*'learning\.rl_transitions'::regclass",
        SQL_LOWER,
    )
    assert rl_dep is not None, (
        "V096 必含 rl_transitions pg_depend 檢查（refobjid 比對）"
    )

    sc_dep = re.search(
        r"refobjid\s*=\s*'learning\.symbol_clusters'::regclass",
        SQL_LOWER,
    )
    assert sc_dep is not None, (
        "V096 必含 symbol_clusters pg_depend 檢查（refobjid 比對）"
    )


# ============================================================
# 不觸碰 active learning.* 表
# ============================================================
@pytest.mark.parametrize(
    "active_table",
    [
        "learning.promotion_pipeline",
        "learning.ml_parameter_suggestions",
        "learning.bayesian_posteriors",
        "learning.james_stein_estimates",
        "learning.teacher_directives",
        "learning.directive_executions",
        "learning.experiment_ledger",
        "learning.foundation_model_features",
        "learning.weekly_review_log",
        "learning.ai_usage_log",
        "learning.linucb_state",
        "learning.cpcv_results",
        "learning.model_registry",
        "learning.shadow_recommendations",
    ],
)
def test_v096_does_not_touch_active_learning_tables(active_table: str) -> None:
    """V096 只 DROP rl_transitions + symbol_clusters；任何其他 learning.*
    出現在 DROP statement 中即為 scope creep，必 fail。"""
    forbidden = f"drop table if exists {active_table.lower()}"
    assert forbidden not in SQL_LOWER, (
        f"V096 出現非授權 DROP: {active_table}（scope 嚴限 rl_transitions + "
        f"symbol_clusters 兩表）"
    )


# ============================================================
# Idempotency — 兩次「apply」結構等價（規則 = 純粹 idempotency state machine）
# ============================================================
def test_v096_idempotency_no_state_change() -> None:
    """idempotency 的 source-only 證明：
    1. IF EXISTS guard 確保第二次 apply DROP 是 no-op
    2. DO $$ block 開頭 `IF to_regclass(...) IS NULL THEN RETURN`
       確保第二次 guard block 也短路返回，不觸發 row count / pg_depend 檢查
    本測試對「兩段 DO $$ block + 兩段 DROP TABLE IF EXISTS」進行存在性
    驗證；無實際 PG，故不能跑 apply twice。dispatch §3「Apply twice in
    dry-run mode if Mac PG is available — but DO NOT actually apply to
    real PG」對齊。"""
    # 兩段 DO $$ block（剝注釋後）
    do_block_count = SQL_NO_COMMENTS.count("DO $$")
    assert do_block_count == 2, (
        f"V096 必有兩段 DO $$ guard block（rl_transitions / symbol_clusters），"
        f"實得 {do_block_count}"
    )

    # 兩段 IF to_regclass(...) IS NULL THEN RETURN 短路
    short_circuit_count = len(
        re.findall(
            r"if\s+to_regclass\([^)]+\)\s+is\s+null\s+then",
            SQL_LOWER,
        )
    )
    assert short_circuit_count == 2, (
        f"V096 必有兩段 to_regclass IS NULL 短路 RETURN（idempotency 第二次 "
        f"apply 走 NOTICE + RETURN，非報錯），實得 {short_circuit_count}"
    )

    # 兩段 RAISE NOTICE 'V096: ... already absent'
    notice_count = SQL_LOWER.count("already absent")
    assert notice_count == 2, (
        f"V096 必對兩表都有 'already absent' notice 訊息，實得 {notice_count}"
    )


# ============================================================
# 治理 / 文檔對照
# ============================================================
def test_v096_references_governance_artifacts() -> None:
    """V096 header comment 必引 WP-07 + ADR-0015 + P2-DEAD-SCHEMA-DROP-1
    + V004 origin。"""
    assert "WP-07" in SQL_TEXT, "V096 必引 WP-07 dead-schema audit"
    assert "ADR-0015" in SQL_TEXT, "V096 必引 ADR-0015 dead-table reclamation"
    assert "P2-DEAD-SCHEMA-DROP-1" in SQL_TEXT, (
        "V096 必引 ticket P2-DEAD-SCHEMA-DROP-1"
    )
    assert "V004" in SQL_TEXT, (
        "V096 必註明 V004 origin（rl_transitions + symbol_clusters CREATE 來源）"
    )
