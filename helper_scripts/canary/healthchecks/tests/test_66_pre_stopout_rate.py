"""[66] close_maker_pre_stopout_rate run() 邏輯單元測試（fake cursor）。

對應 P1-OBS-PRE-STOPOUT-RATE follow-up（FA round 1 #5，2026-05-21）。

R2 修正歷史（E2 review 2026-05-20）：
  - HIGH-A1：production exit_reason 經 risk_checks.rs format!() emit 是
    大寫 + 空格 + colon（`HARD STOP: ...`），R1 lowercase patterns 全 miss
  - HIGH-A2：R1 漏 `DYNAMIC STOP%` pattern（risk_checks.rs:355 emit）
  - MEDIUM-E1：補 ``test_default_patterns_match_real_production_exit_reasons``
    用 fnmatch 模擬 PG LIKE，驗 default patterns 對 7 個 production 真實
    字串至少 match 一條，且非 stopout 字串保證 0 match — 設計上能 catch
    上述 A1/A2 失誤（patterns 全錯時必紅）
  - MEDIUM-F1：[71] → [66] 避與 passive_wait_healthcheck [71] slot 碰撞

驗證重點：
  - empty window → INSUFFICIENT_SAMPLE
  - 雙閾值 (pass_upper / fail_upper) ladder PASS / WARN / FAIL 三段
  - multi engine_mode severity_max 取最嚴重
  - min_sample 不足 → INSUFFICIENT_SAMPLE
  - SQL 同時 bind exit_reason patterns + strategy_name liquidation pattern
  - --stopout-patterns CLI 覆寫不影響預設 pattern list 結構
  - default patterns 命中 production 真實 exit_reason 字串（R2 新增 E1 修）
"""

from __future__ import annotations

import fnmatch


# ───────────────────────────────────────────────────────────────────────────
# Production exit_reason 真實字串 fixture（R2 E2 review HIGH-A1/A2 + MEDIUM-E1）
# ───────────────────────────────────────────────────────────────────────────
#
# 來源：grep `rust/openclaw_engine/src/risk_checks.rs` format!() literal +
# `helpers_close_tags.rs` strip chain + `step_0_fast_track.rs` emit。
# 每個字串都是 production 寫入 trading.fills.exit_reason 的真實格式。
#
# 這份 fixture 設計目的 = catch R1 lowercase pattern miss 的 regression：
# 若有人未來把 `HARD STOP%` 改成 `hard_stop%`（或漏 DYNAMIC STOP），
# `test_default_patterns_match_real_production_exit_reasons` 會立刻紅。

# 期望命中 default patterns 的 production exit_reason 字串
EXPECTED_STOPOUT_EXIT_REASONS = [
    # 大寫 + 空格家族（risk_checks.rs format!() 直接 emit）
    "HARD STOP: pnl -25.00% <= -20.00%",                                 # risk_checks.rs:334
    "DYNAMIC STOP: pnl -8.50% <= -7.20% (regime=trending, atr=Some(0.012))",  # :355
    "TIME STOP: held 24.0h >= limit 24.0h (regime=trending)",            # :390
    "TRAILING STOP: peak 8.46% - current 6.46% = 2.00% >= distance 2.00% (locked 6.46% >= floor 5.78%)",  # :379
    # 小寫底線家族（strategy / fast_track / halt_session / phys_lock 路徑）
    "trailing_stop",                                # bb_breakout/mod.rs:910/919
    "fast_track_reduce_half",                       # step_0_fast_track.rs:486
    "fast_track",                                   # step_0_fast_track.rs:603
    "halt_session",                                 # helpers_close_tags.rs:122-127 R-A5
    "halt_session_drawdown_3pct",                   # SESSION DRAWDOWN 走 halt path
    "halt_session_consecutive_loss",                # CONSECUTIVE LOSS 走 halt path
    "phys_lock_gate4_giveback",                     # physical_micro_profit_lock_v2 emit
    "phys_lock_gate4_stale_roc_neg",                # 同上
]

# 保證 0 命中 default patterns 的非 stopout 字串（graceful exit / TP）
EXPECTED_NON_STOPOUT_EXIT_REASONS = [
    "ma_reverse_cross",            # strategies/ma_crossover graceful exit
    "bb_mean_revert",              # strategies/bb_reversion graceful exit
    "pctb_revert",                 # bb_breakout graceful（非 trailing）
    "bw_squeeze",                  # bb_breakout graceful（非 trailing）
    "grid_close_long",             # grid_trading graceful
    "grid_close_short",            # grid_trading graceful
    "funding_arb_exit_settled",    # funding_arb graceful
    "take_profit: price 12345 hit target",  # TP（非 stopout）
]


def _sql_like_to_fnmatch(pattern: str) -> str:
    """把 SQL LIKE pattern 轉成 fnmatch glob pattern。

    PG LIKE 語法：``%`` = match 任意長度（含空）字串，``_`` = match 任意單字元。
    fnmatch 對應：``*`` / ``?``。
    本 healthcheck patterns 不含 ``_`` 通配（用作底線字面），只需轉 ``%`` → ``*``。

    為什麼用 fnmatch：psycopg2 LIKE 行為純 PG-side；test 不接 PG 真實 DB，
    用 fnmatch 模擬最簡潔且行為一致（前綴 + 任意 suffix）。
    """
    # 為什麼不轉 _：本檔 patterns 內 `phys_lock_%` / `halt_session%` /
    # `fast_track%` 的 `_` 都是字面底線（不是 LIKE 單字元通配）；fnmatch
    # 的 `?` 才是單字元通配。直接保留 `_` 為字面字元符合預期。
    return pattern.replace("%", "*")


def _sql_like_match(exit_reason: str, sql_pattern: str) -> bool:
    """模擬 PG ``exit_reason LIKE sql_pattern`` 行為。"""
    return fnmatch.fnmatchcase(exit_reason, _sql_like_to_fnmatch(sql_pattern))


# ───────────────────────────────────────────────────────────────────────────
# run() 邏輯單元測試
# ───────────────────────────────────────────────────────────────────────────


def test_empty_window_returns_insufficient_sample(hc66, fake_cursor_factory):
    cur = fake_cursor_factory([[]])  # 0 rows
    result = hc66.run(
        cur,
        window_secs=604800,
        engine_modes=["demo", "live_demo"],
        pass_upper=0.10,
        fail_upper=0.30,
        min_sample=30,
        stopout_patterns=list(hc66.DEFAULT_STOPOUT_EXIT_REASON_PATTERNS),
    )
    assert result["verdict"] == "INSUFFICIENT_SAMPLE"
    assert result["total_attempts"] == 0
    assert result["check_id"] == "[66]"


def test_pass_when_low_stopout_rate(hc66, fake_cursor_factory):
    # demo 100 attempts，stopouts=5，clean=95 → rate=0.05 ≤ 0.10 → PASS
    rows = [[("demo", 100, 5, 95)]]
    cur = fake_cursor_factory(rows)
    result = hc66.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_upper=0.10,
        fail_upper=0.30,
        min_sample=30,
        stopout_patterns=list(hc66.DEFAULT_STOPOUT_EXIT_REASON_PATTERNS),
    )
    assert result["verdict"] == "PASS"
    assert result["total_attempts"] == 100
    assert result["total_stopouts"] == 5
    assert result["cells"][0]["stopout_rate"] == 0.05


def test_warn_in_middle_zone(hc66, fake_cursor_factory):
    # demo 100 attempts，stopouts=20 → rate=0.20，pass_upper=0.10 < rate ≤ 0.30 → WARN
    rows = [[("demo", 100, 20, 80)]]
    cur = fake_cursor_factory(rows)
    result = hc66.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_upper=0.10,
        fail_upper=0.30,
        min_sample=30,
        stopout_patterns=list(hc66.DEFAULT_STOPOUT_EXIT_REASON_PATTERNS),
    )
    assert result["verdict"] == "WARN"
    assert result["cells"][0]["stopout_rate"] == 0.20


def test_fail_when_above_fail_upper(hc66, fake_cursor_factory):
    # demo 100 attempts，stopouts=50 → rate=0.50 > 0.30 → FAIL
    rows = [[("demo", 100, 50, 50)]]
    cur = fake_cursor_factory(rows)
    result = hc66.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_upper=0.10,
        fail_upper=0.30,
        min_sample=30,
        stopout_patterns=list(hc66.DEFAULT_STOPOUT_EXIT_REASON_PATTERNS),
    )
    assert result["verdict"] == "FAIL"
    assert result["cells"][0]["stopout_rate"] == 0.50


def test_multi_engine_takes_most_severe(hc66, fake_cursor_factory):
    rows = [
        [
            ("demo", 100, 5, 95),       # PASS
            ("live_demo", 100, 50, 50),  # FAIL
        ]
    ]
    cur = fake_cursor_factory(rows)
    result = hc66.run(
        cur,
        window_secs=604800,
        engine_modes=["demo", "live_demo"],
        pass_upper=0.10,
        fail_upper=0.30,
        min_sample=30,
        stopout_patterns=list(hc66.DEFAULT_STOPOUT_EXIT_REASON_PATTERNS),
    )
    assert result["verdict"] == "FAIL"  # FAIL wins
    assert len(result["cells"]) == 2


def test_below_min_sample_returns_insufficient(hc66, fake_cursor_factory):
    rows = [[("demo", 10, 7, 3)]]  # n<30
    cur = fake_cursor_factory(rows)
    result = hc66.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_upper=0.10,
        fail_upper=0.30,
        min_sample=30,
        stopout_patterns=list(hc66.DEFAULT_STOPOUT_EXIT_REASON_PATTERNS),
    )
    assert result["cells"][0]["verdict"] == "INSUFFICIENT_SAMPLE"
    assert result["verdict"] == "INSUFFICIENT_SAMPLE"


def test_sql_binds_patterns_and_liquidation(hc66, fake_cursor_factory):
    """SQL 必須 bind exit_reason patterns 兩次 + strategy_name unattributed pattern 兩次
    （SELECT FILTER 子句重用，psycopg2 不會自動 dedup）。
    """
    rows = [[]]
    cur = fake_cursor_factory(rows)
    patterns = list(hc66.DEFAULT_STOPOUT_EXIT_REASON_PATTERNS)
    hc66.run(
        cur,
        window_secs=3600,
        engine_modes=["demo"],
        pass_upper=0.10,
        fail_upper=0.30,
        min_sample=30,
        stopout_patterns=patterns,
    )
    sql, params = cur.executed_sqls[0]
    assert "close_maker_attempt = TRUE" in sql
    assert "exit_reason LIKE ANY" in sql
    assert "strategy_name LIKE" in sql
    # params tuple: (patterns, liq_pattern, patterns, liq_pattern, window_secs, engine_modes)
    assert params[0] == patterns
    assert params[1] == hc66.LIQUIDATION_STRATEGY_NAME_PATTERN
    assert params[2] == patterns
    assert params[3] == hc66.LIQUIDATION_STRATEGY_NAME_PATTERN
    assert params[4] == 3600
    assert params[5] == ["demo"]


def test_default_pattern_list_contains_known_stopout_reasons(hc66):
    """sanity check: default 預設 pattern list 含 source-derived stop-out 家族
    （HARD STOP / DYNAMIC STOP / TIME STOP / TRAILING STOP + 小寫家族
    trailing_stop / fast_track / phys_lock / halt_session）。
    若 default list 被誤刪某一族此 test 會 catch 到。

    注意：此 test 與 ``test_default_patterns_match_real_production_exit_reasons``
    互補 — 本 test 驗 prefix 字面存在；後者驗對 production 字串實 match。
    """
    patterns = set(hc66.DEFAULT_STOPOUT_EXIT_REASON_PATTERNS)
    # 大寫家族（risk_checks.rs format!() emit）
    assert any(p.startswith("HARD STOP") for p in patterns), "missing HARD STOP%"
    assert any(p.startswith("DYNAMIC STOP") for p in patterns), "missing DYNAMIC STOP% (R2 HIGH-A2)"
    assert any(p.startswith("TIME STOP") for p in patterns), "missing TIME STOP%"
    assert any(p.startswith("TRAILING STOP") for p in patterns), "missing TRAILING STOP%"
    # 小寫家族
    assert any(p.startswith("trailing_stop") for p in patterns), "missing trailing_stop% (bb_breakout)"
    assert any(p.startswith("fast_track") for p in patterns), "missing fast_track%"
    assert any(p.startswith("phys_lock_") for p in patterns), "missing phys_lock_%"
    assert any(p.startswith("halt_session") for p in patterns), "missing halt_session%"


def test_default_patterns_match_real_production_exit_reasons(hc66):
    """R2 E2 review MEDIUM-E1 修：用 fnmatch 模擬 PG LIKE 行為，驗 default
    patterns 對 production 真實 exit_reason 字串至少 match 一條。

    這個 test 設計上能 catch R1 HIGH-A1（lowercase patterns vs 大寫 emission）
    + HIGH-A2（漏 DYNAMIC STOP）— 若 patterns 全部 lowercase、或缺
    DYNAMIC STOP 字根，``HARD STOP: pnl ...`` / ``DYNAMIC STOP: pnl ...``
    將 0 match → test 紅。

    亦驗非 stopout（graceful exit / TP）保證 0 match — 否則代表 pattern 過
    寬會把 graceful exit 誤計入 stopouts，stopout_rate 失真。
    """
    default_patterns = list(hc66.DEFAULT_STOPOUT_EXIT_REASON_PATTERNS)

    # 正向：每個 production stopout exit_reason 至少命中一個 default pattern
    for reason in EXPECTED_STOPOUT_EXIT_REASONS:
        matched = [p for p in default_patterns if _sql_like_match(reason, p)]
        assert matched, (
            f"production stopout exit_reason {reason!r} 命中 0 default patterns；"
            f"檢查 DEFAULT_STOPOUT_EXIT_REASON_PATTERNS 是否漏字根或大小寫錯。"
            f"default={default_patterns}"
        )

    # 反向：非 stopout exit_reason 保證 0 match
    for reason in EXPECTED_NON_STOPOUT_EXIT_REASONS:
        matched = [p for p in default_patterns if _sql_like_match(reason, p)]
        assert not matched, (
            f"非 stopout exit_reason {reason!r} 誤命中 default patterns {matched}；"
            f"pattern 過寬會把 graceful exit 誤計入 stopouts。"
        )


def test_split_patterns_csv_override(hc66):
    """``--stopout-patterns HARD STOP%,fast_track%`` 應只用兩個 pattern。"""
    custom = hc66._split_patterns("HARD STOP%,fast_track%")
    assert custom == ["HARD STOP%", "fast_track%"]


def test_split_patterns_empty_falls_back_to_default(hc66):
    """空字串 / None → default list。"""
    assert hc66._split_patterns(None) == list(
        hc66.DEFAULT_STOPOUT_EXIT_REASON_PATTERNS
    )
    assert hc66._split_patterns("") == list(
        hc66.DEFAULT_STOPOUT_EXIT_REASON_PATTERNS
    )
