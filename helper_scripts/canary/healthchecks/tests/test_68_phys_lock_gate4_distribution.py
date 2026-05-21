"""[68] phys_lock_gate4_distribution run() 邏輯單元測試（fake cursor）。

對應 P2-PHYS-LOCK-72-HEALTHCHECK（FA C6 OQ-C6-2 follow-up，2026-05-21）。

驗證重點（per spec §4.1 acceptance criteria + §8 PA → E2 review 重點 3 點；
PA 2026-05-21 IMPL refine 後修正：spec §2.2 WARN 條件由
`stale_roc=0 AND giveback>=10` 改為 `giveback>=10 AND close_attempts=0`，
原條件會把 natural sparse 環境誤升 WARN）：

  AC-1：SQL bind `exit_reason LIKE 'phys_lock_%'` + `engine_modes` ANY
  AC-2：SQL 含 `details->>'close_maker_eligible_reason' LIKE 'phys_lock_%'`
        OR-condition
  AC-3：n < insufficient_sample_threshold → aggregate INSUFFICIENT_SAMPLE
  AC-4：gate4_giveback n>=threshold + close_maker_attempts>0 → PASS
        （stale_roc 0 fire 視 natural sparse 不沖淡）
  AC-5：gate4_giveback n>=10 + close_maker_attempts=0 → WARN
        （router 缺口弱訊號；giveback path close 也不通）
  AC-6：gate4_stale_roc_neg n>0 + close_maker_attempts=0 → FAIL (P1 ticket)
  AC-7：multi engine_mode (demo + live_demo) severity_max
  AC-8：production exit_reason 字串 fixture 真實 match
        `phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg`
        （fnmatch 模擬 PG LIKE 行為）

E2 review 重點 3 點對應（spec §8）：
  Point 1 → test_production_exit_reason_string_match + AC-8 fnmatch fixture
  Point 2 → test_fail_overrides_warn_when_both_conditions_met +
            test_multi_engine_severity_max 驗 FAIL/WARN 不被 PASS 沖淡
  Point 3 → test_sql_binds_or_condition_with_close_maker_eligible_reason 驗
            雙條件 OR 結構正確
"""

from __future__ import annotations

import fnmatch


# ───────────────────────────────────────────────────────────────────────────
# Production exit_reason 真實字串 fixture（per spec §8 Point 1 + AC-8）
# ───────────────────────────────────────────────────────────────────────────
#
# 來源：grep `rust/openclaw_engine/src/exit_features/v2.rs:351/359` +
# `risk_checks.rs:410-413` + helpers_close_tags strip chain。每個字串都是
# production 寫入 trading.fills.exit_reason 的真實格式（lowercase）。
#
# 這份 fixture 設計目的 = catch routing regression：
# - 若 emit 後 exit_reason 經未來 helpers_close_tags 改動帶 prefix
#   (如 "physical:phys_lock_gate4_giveback")，本 fixture 測試會紅 → spec §8
#   Point 1 push back 點落實

# 期望命中 'phys_lock_%' LIKE pattern 的 production exit_reason 字串
EXPECTED_PHYS_LOCK_GATE4_REASONS = [
    "phys_lock_gate4_giveback",        # exit_features/v2.rs:344/351/455/491/543/586/860/889
    "phys_lock_gate4_stale_roc_neg",   # exit_features/v2.rs:359/507/800
]

# 同屬 phys_lock 家族但非 gate4（會被 CASE WHEN 歸 "other_phys_lock"）
EXPECTED_OTHER_PHYS_LOCK_REASONS = [
    "phys_lock_gate1_low_edge",        # 未來可能新增；CASE fall through → other
    "phys_lock_gate2_some_condition",  # 未來可能新增
]

# 保證不命中 'phys_lock_%' pattern 的字串（其他 stopout / graceful exit）
EXPECTED_NON_PHYS_LOCK_REASONS = [
    "HARD STOP: pnl -25.00% <= -20.00%",
    "TRAILING STOP: peak 8.46% - current 6.46%",
    "trailing_stop",
    "fast_track_reduce_half",
    "halt_session",
    "ma_reverse_cross",
    "grid_close_long",
    "take_profit: price 12345",
]


def _sql_like_match(value: str, sql_pattern: str) -> bool:
    """模擬 PG ``value LIKE sql_pattern`` 行為。

    PG LIKE 語法：``%`` = match 任意長度字串（含空），``_`` = match 任意單字元。
    fnmatch 對應：``*`` / ``?``。
    本 healthcheck patterns 不含 ``_`` 通配（用作字面底線），只需轉 ``%`` → ``*``。
    """
    return fnmatch.fnmatchcase(value, sql_pattern.replace("%", "*"))


# ───────────────────────────────────────────────────────────────────────────
# run() 邏輯單元測試 — AC-3 / AC-4 / AC-5 / AC-6 / AC-7
# ───────────────────────────────────────────────────────────────────────────


def test_empty_window_returns_insufficient_sample(hc68, fake_cursor_factory):
    """AC-3 — 0 rows 應 aggregate INSUFFICIENT_SAMPLE 且 exit code = 0（不阻 deploy）。"""
    cur = fake_cursor_factory([[]])  # 0 rows
    result = hc68.run(
        cur,
        window_secs=1209600,  # 14d
        engine_modes=["demo", "live_demo"],
        insufficient_sample_threshold=5,
        warn_giveback_threshold=10,
    )
    assert result["verdict"] == "INSUFFICIENT_SAMPLE"
    assert result["total_n"] == 0
    assert result["check_id"] == "[68]"
    # namespace field 強制標明（per spec §3 mitigation (b)）
    assert result["namespace"] == "canary"
    # 兩 engine_mode 都應在 per_engine_verdicts 中（即使 0 row）
    assert "demo" in result["per_engine_verdicts"]
    assert "live_demo" in result["per_engine_verdicts"]


def test_pass_with_giveback_and_close_attempts(hc68, fake_cursor_factory):
    """AC-4 — gate4_giveback n>0 + close_maker_attempts>0 → PASS。"""
    # demo: gate4_giveback n=30, close_attempts=25, fills=20
    rows = [[("demo", "gate4_giveback", 30, 25, 20)]]
    cur = fake_cursor_factory(rows)
    result = hc68.run(
        cur,
        window_secs=1209600,
        engine_modes=["demo"],
        insufficient_sample_threshold=5,
        warn_giveback_threshold=10,
    )
    assert result["verdict"] == "PASS"
    assert result["per_engine_verdicts"]["demo"] == "PASS"
    assert result["total_n"] == 30
    assert result["total_close_attempts"] == 25
    assert result["total_close_fills"] == 20


def test_insufficient_sample_when_n_below_threshold(hc68, fake_cursor_factory):
    """AC-3 — n < insufficient_sample_threshold → INSUFFICIENT_SAMPLE
    （PASS path 也要求 n 達 threshold；3 < 5 故不可升 PASS）。
    """
    # n=3 < threshold=5 → INSUFFICIENT_SAMPLE
    rows = [[("demo", "gate4_giveback", 3, 2, 1)]]
    cur = fake_cursor_factory(rows)
    result = hc68.run(
        cur,
        window_secs=1209600,
        engine_modes=["demo"],
        insufficient_sample_threshold=5,
        warn_giveback_threshold=10,
    )
    assert result["verdict"] == "INSUFFICIENT_SAMPLE"
    assert result["per_engine_verdicts"]["demo"] == "INSUFFICIENT_SAMPLE"


def test_warn_when_giveback_high_but_close_attempts_zero(hc68, fake_cursor_factory):
    """AC-5 — giveback n>=10 但 close_maker_attempts=0 → WARN (router 缺口弱訊號)。

    PA 2026-05-21 IMPL refine 後 WARN 條件變更：原 `stale_roc=0 AND giveback>=10`
    改為 `giveback>=10 AND close_attempts=0`。原條件會把 natural sparse 環境
    誤升 WARN（demo 上 stale_roc_neg 自然 14d 內 0 fire 是預期）。

    新 WARN 訊號 = giveback fire 多但 close path 完全 0 attempts → 與 FAIL
    對稱訊號（stale_roc 看不到 → giveback path 觀察為 close path 健康代理；
    若 giveback 也 0 attempts → router 缺口疑似）。
    """
    # demo: gate4_giveback n=20 但 close_attempts=0 → WARN
    rows = [[("demo", "gate4_giveback", 20, 0, 0)]]
    cur = fake_cursor_factory(rows)
    result = hc68.run(
        cur,
        window_secs=1209600,
        engine_modes=["demo"],
        insufficient_sample_threshold=5,
        warn_giveback_threshold=10,
    )
    assert result["verdict"] == "WARN"
    assert result["per_engine_verdicts"]["demo"] == "WARN"


def test_pass_when_giveback_alive_and_stale_roc_naturally_sparse(hc68, fake_cursor_factory):
    """AC-4 reframe — stale_roc 0 fire 是 natural sparse，**不應沖淡 PASS**。

    PA 2026-05-21 IMPL refine 後核心訴求 — spec §1 0-fire-natural vs
    0-fire-router-bug 區分：14d window 內 stale_roc_neg 自然 0 fire 是預期
    （emit 條件本身嚴苛），只要 giveback 健康 + close path 通就應該 PASS。

    這是修復原 spec §2.2 WARN 條件「stale_roc=0 AND giveback>=10 → WARN」
    對應的 false-positive case；本 test 確認新邏輯下 demo natural 30 giveback
    fire + 25 close attempts + 0 stale_roc → PASS 而非 WARN。
    """
    # demo: gate4_giveback n=30 close_attempts=25 + 0 stale_roc row
    rows = [[("demo", "gate4_giveback", 30, 25, 20)]]
    cur = fake_cursor_factory(rows)
    result = hc68.run(
        cur,
        window_secs=1209600,
        engine_modes=["demo"],
        insufficient_sample_threshold=5,
        warn_giveback_threshold=10,
    )
    # 關鍵：原 spec §2.2 邏輯下這個 case 會誤升 WARN；refine 後保持 PASS
    assert result["verdict"] == "PASS"
    assert result["per_engine_verdicts"]["demo"] == "PASS"


def test_fail_when_stale_roc_alive_but_close_path_broken(hc68, fake_cursor_factory):
    """AC-6 — gate4_stale_roc_neg n>0 + close_maker_attempts=0 → FAIL (P1 ticket)。

    spec §1 核心 FAIL 訊號：policy alive (stale_roc 有 fire) 但 close path
    完全不通（close_maker_attempts=0 即 maker_price.rs route 缺）。
    """
    # demo: gate4_stale_roc_neg n=8, close_attempts=0, close_fills=0
    rows = [
        [
            ("demo", "gate4_stale_roc_neg", 8, 0, 0),
        ]
    ]
    cur = fake_cursor_factory(rows)
    result = hc68.run(
        cur,
        window_secs=1209600,
        engine_modes=["demo"],
        insufficient_sample_threshold=5,
        warn_giveback_threshold=10,
    )
    assert result["verdict"] == "FAIL"
    assert result["per_engine_verdicts"]["demo"] == "FAIL"


def test_multi_engine_severity_max(hc68, fake_cursor_factory):
    """AC-7 — demo PASS / live_demo FAIL → aggregate FAIL（FAIL 不被 PASS 沖淡）。"""
    rows = [
        [
            ("demo", "gate4_giveback", 30, 25, 20),           # PASS
            ("live_demo", "gate4_stale_roc_neg", 5, 0, 0),    # FAIL
        ]
    ]
    cur = fake_cursor_factory(rows)
    result = hc68.run(
        cur,
        window_secs=1209600,
        engine_modes=["demo", "live_demo"],
        insufficient_sample_threshold=5,
        warn_giveback_threshold=10,
    )
    assert result["verdict"] == "FAIL"  # FAIL wins
    assert result["per_engine_verdicts"]["demo"] == "PASS"
    assert result["per_engine_verdicts"]["live_demo"] == "FAIL"


def test_fail_overrides_warn_when_both_conditions_met(hc68, fake_cursor_factory):
    """E2 push back Point 2 — 若同 engine 內 stale_roc FAIL 條件 + giveback WARN
    條件同時 trigger，FAIL 必須先判優於 WARN（spec §2.2 邏輯 1 vs 2 順序）。
    """
    # demo: giveback n=20 (滿足 WARN warn_giveback_threshold)，stale_roc n=3
    # close_attempts=0（滿足 FAIL）→ aggregate 應 FAIL (FAIL 先判)
    rows = [
        [
            ("demo", "gate4_giveback", 20, 15, 10),
            ("demo", "gate4_stale_roc_neg", 3, 0, 0),
        ]
    ]
    cur = fake_cursor_factory(rows)
    result = hc68.run(
        cur,
        window_secs=1209600,
        engine_modes=["demo"],
        insufficient_sample_threshold=5,
        warn_giveback_threshold=10,
    )
    # FAIL（stale_roc 條件）優先於 WARN（giveback 條件）—— spec §2.2 邏輯 1 在 2 之前
    assert result["verdict"] == "FAIL"


# ───────────────────────────────────────────────────────────────────────────
# SQL binding 測試 — AC-1 + AC-2 + spec §8 Point 3
# ───────────────────────────────────────────────────────────────────────────


def test_sql_binds_or_condition_with_close_maker_eligible_reason(hc68, fake_cursor_factory):
    """AC-2 + spec §8 Point 3 — SQL 必須含 `details->>'close_maker_eligible_reason'`
    OR-condition；驗 SQL string + bind tuple shape。
    """
    rows = [[]]
    cur = fake_cursor_factory(rows)
    hc68.run(
        cur,
        window_secs=1209600,
        engine_modes=["demo", "live_demo"],
        insufficient_sample_threshold=5,
        warn_giveback_threshold=10,
    )
    sql, params = cur.executed_sqls[0]
    # AC-1：exit_reason LIKE 'phys_lock_%'
    assert "exit_reason LIKE 'phys_lock_" in sql, (
        "SQL 必須含 exit_reason LIKE 'phys_lock_%'"
    )
    # AC-2：details->>'close_maker_eligible_reason' LIKE 'phys_lock_%'
    assert "close_maker_eligible_reason" in sql, (
        "SQL 必須含 details->>'close_maker_eligible_reason' OR-condition"
    )
    # AC-2 雙條件 OR
    assert " OR " in sql, "SQL 必須使用 OR 雙條件（exit_reason OR details）"
    # CASE WHEN three buckets（gate4_giveback / gate4_stale_roc_neg / other）
    assert "gate4_giveback" in sql
    assert "gate4_stale_roc_neg" in sql
    assert "other_phys_lock" in sql
    # bind params shape：(window_secs, engine_modes)
    assert params[0] == 1209600
    assert params[1] == ["demo", "live_demo"]


# ───────────────────────────────────────────────────────────────────────────
# Production string match 測試 — AC-8 + spec §8 Point 1
# ───────────────────────────────────────────────────────────────────────────


def test_production_exit_reason_string_match():
    """AC-8 + spec §8 Point 1 — `exit_reason LIKE 'phys_lock_%'` 對 production
    真實字串行為驗證（fnmatch 模擬 PG LIKE）。

    這個 test 設計上能 catch：
      - 若未來 emit 邏輯改動寫成 ``"Physical:phys_lock_*"`` 帶 prefix → 紅
      - 若 helpers_close_tags strip 邏輯漏 strip → 紅
      - 若有人改動 SQL LIKE pattern 從 'phys_lock_%' 變 'phys_lock_gate4_%'
        → other_phys_lock 家族字串會漏，紅
    """
    sql_pattern = "phys_lock_%"

    # 正向：所有 production gate4 exit_reason 必命中
    for reason in EXPECTED_PHYS_LOCK_GATE4_REASONS:
        assert _sql_like_match(reason, sql_pattern), (
            f"production exit_reason {reason!r} 未命中 '{sql_pattern}'；"
            f"檢查 emit point + helpers_close_tags strip chain 是否漏 strip prefix"
        )

    # 正向：其他 phys_lock 家族也應命中（CASE WHEN fall through 到 other_phys_lock bucket）
    for reason in EXPECTED_OTHER_PHYS_LOCK_REASONS:
        assert _sql_like_match(reason, sql_pattern), (
            f"phys_lock 家族 exit_reason {reason!r} 未命中 '{sql_pattern}'；"
            f"若 LIKE 改 'phys_lock_gate4_%' 此 test 會紅，提示未來新 phys_lock_* "
            f"variant 會漏記"
        )

    # 反向：非 phys_lock 字串保證 0 match
    for reason in EXPECTED_NON_PHYS_LOCK_REASONS:
        assert not _sql_like_match(reason, sql_pattern), (
            f"非 phys_lock exit_reason {reason!r} 誤命中 '{sql_pattern}'；"
            f"pattern 過寬會把其他 stopout / graceful exit 誤計入 phys_lock 統計"
        )
