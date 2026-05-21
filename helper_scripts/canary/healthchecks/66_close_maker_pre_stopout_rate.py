#!/usr/bin/env python3
"""[66] close_maker_pre_stopout_rate — close-maker-first 「來得及」健康度量。

MODULE_NOTE:
  P1-OBS-PRE-STOPOUT-RATE（FA round 1 #5 follow-up，2026-05-21）的 healthcheck
  standalone 入口。[62] 量度的是 close-maker-first **被掛單**之後 maker fill
  的成功率；本 [66] 量度的是 close-maker-first **嘗試本身**是否在止損 /
  liquidation 發生**之前**完成 — 也就是 attempt → strategy-driven graceful
  exit 比例。

  Slot 命名歷史（R2 E2 review F1，2026-05-21）：原 R1 取 ``[71]`` 與
  ``helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py``
  的 passive_wait ``[71] close_maker_zero_spine_lineage`` 字面碰撞；R2 改用
  ``[66]``（standalone canary [62][63][64][65] 鄰近 slot；passive_wait 用
  [70-74] 段），namespace 永遠物理分離。

  為什麼這是獨立量度（與 [62] 不重疊）：
    - [62] 分母：close_maker_attempt=TRUE 的 attempts
              分子：close_maker_fallback_reason IS NULL（maker leg 成交）
              觀察：掛了 maker order 之後成交不成交
    - [66] 分母：close_maker_attempt=TRUE 的 attempts
              分子：stop-out / liquidation 路徑出場的比例
              觀察：close maker 是否「來得及」在 stop-out 觸發前完成
    - 兩者皆 PASS 才代表 close-maker-first 整體健康；[62] PASS + [66] FAIL =
      maker leg 成交率 OK 但策略 already over-shoot 進入強制停損，close maker
      策略無實效。

  Schema 真相（2026-05-21 R2 E1 完整 grep risk_checks.rs + helpers_close_tags
  chain，**取代** R1 lowercase 猜測；參 E2 review 2026-05-20 §CRITICAL chain
  detail）：
    - V033 加入 ``trading.fills.exit_reason`` 為 free-text 自由文字（非 enum）。
    - Risk-driven hard stops 經 ``rust/openclaw_engine/src/risk_checks.rs``
      format!() 大寫 + 空格 + colon 字串：
        * line 334  ``format!("HARD STOP: pnl {:.2}% <= -{:.2}%")``
        * line 355  ``format!("DYNAMIC STOP: pnl ... (regime=..., atr=...)")``
        * line 379  ``format!("TRAILING STOP: peak ...")``
        * line 390  ``format!("TIME STOP: held {:.1}h >= limit {:.1}h ...")``
      step_6_risk_checks.rs 用 ``build_risk_close_tag`` 包成
      ``"risk_close:HARD STOP: ..."``；close emitter 經
      ``helpers_close_tags::build_close_tags_from_legacy`` strip ``risk_close:``
      前綴後寫入 ``fills.exit_reason="HARD STOP: ..."``（大寫保留）。
    - Strategy-internal trailing：``strategies/bb_breakout/mod.rs:910/919``
      emit lowercase ``"trailing_stop"``（非 risk_checks 路徑）→ exit_reason
      = "trailing_stop"。
    - 風控 fast-track：``step_0_fast_track.rs:486/500/603/616`` emit
      ``"risk_close:fast_track_reduce_half"`` / ``"risk_close:fast_track"``
      → strip 後 exit_reason = "fast_track_reduce_half" / "fast_track"。
    - HaltSession：``helpers_close_tags.rs:122-127`` R-A5 強制 prefix
      ``"risk_close:halt_session"`` regardless of upstream reason →
      strip 後 exit_reason = "halt_session"（或 "halt_session_*"）。
      SESSION DRAWDOWN / DAILY LOSS（risk_checks.rs:434/448）也走此 path。
    - phys_lock：emit lowercase ``"phys_lock_gate4_giveback"`` /
      ``"phys_lock_gate4_stale_roc_neg"`` → exit_reason 同字串。
    - 非 stopout（不計入分子）：``ma_reverse_cross`` / ``bb_mean_revert`` /
      ``pctb_revert`` / ``bw_squeeze`` / ``grid_close_long`` /
      ``grid_close_short`` / ``funding_arb_exit*`` / ``take_profit:%``。
    - liquidation：``event_consumer/unattributed_emit.rs:215`` 寫
      ``exit_reason=None``，改用 ``strategy_name LIKE 'unattributed:%'``
      偵測（交易所自動平倉 audit 簽名）。

  Stop-out pattern（CLI 可 override，default = source-derived list）：
    大寫 + 空格家族（risk_checks.rs format!() 直 emit）：
      ``HARD STOP%``  ``DYNAMIC STOP%``  ``TIME STOP%``  ``TRAILING STOP%``
    小寫底線家族（bb_breakout strategy / fast_track / halt_session /
    phys_lock 路徑）：
      ``trailing_stop%``  ``fast_track%``  ``halt_session%``  ``phys_lock_%``
    或 ``strategy_name LIKE 'unattributed:%'``（交易所 auto-close）。

Verdict ladder（R2 MEDIUM-D1 follow-up，2026-05-21；可 CLI 覆寫 threshold）：

  預設啟用 Wilson 95% CI sub-clause（mirror [62] AC-18 風格；可 ``--no-wilson``
  opt-out 退回原 raw-rate ladder）：

  Wilson 模式（預設）：
    - n < min_sample → INSUFFICIENT_SAMPLE
    - raw rate ≤ pass_upper **且** Wilson upper ≤ wilson_upper_pass → PASS
    - raw rate > fail_upper **或** Wilson lower > wilson_lower_fail → FAIL
    - 其他 → WARN

  Raw-rate 模式（``--no-wilson``）：
    - n < min_sample → INSUFFICIENT_SAMPLE
    - stopout_rate ≤ pass_upper → PASS（close maker 來得及；strategy graceful
      exit 為主）
    - stopout_rate > fail_upper → FAIL（close maker 太晚；多數 attempts 已過
      stopout 邊界）
    - 其他 → WARN

預設門檻 0.10 / 0.30 / Wilson upper 0.15 / Wilson lower 0.15；前兩者代表
「強制 stop-out 不超過 10% PASS / 過 30% FAIL」，Wilson 子句為 conservative
sub-clause：raw 雖在 PASS 邊但 upper CI 超 0.15 拒 PASS（降至 WARN）；
raw 雖在 WARN 邊但 lower CI 超 0.15 升至 FAIL（E2 R2 push back 後從 0.20 調降，
避免 demo velocity n~70/week 下成 dead gate）。

為什麼用 Wilson 而非純 raw：[62] AC-18 同步要求 Wilson；本 [66] 為對稱
failure-direction metric（rate 越低越好），mirror 風格意味 upper bound 作為
PASS conservativeness、lower bound 作為 FAIL conservativeness。

CLI:
  python3 66_close_maker_pre_stopout_rate.py [--window-secs 604800] \\
        [--engine-mode demo,live_demo] [--pass-upper 0.10] \\
        [--fail-upper 0.30] [--min-sample 30] [--write-file PATH] [--text] \\
        [--stopout-patterns PATTERN1,PATTERN2,...] [--no-wilson] \\
        [--wilson-upper-pass 0.15] [--wilson-lower-fail 0.15]

Exit codes:
  0 = PASS / INSUFFICIENT_SAMPLE（後者不阻 deploy）
  1 = WARN or FAIL
  2 = PG connect error
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# 允許作為 standalone script + module 同時被呼叫
# stdlib import 之後加 sys.path 是為了讓 ``python3 66_close_maker_pre_stopout_rate.py``
# 直接執行也能 import 同目錄 _common；package import 走 ``__init__.py`` 不受影響
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _common import (  # noqa: E402
    EXIT_FAIL,
    EXIT_PASS,
    VERDICT_FAIL,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_PASS,
    VERDICT_WARN,
    build_argparser,
    configure_logging,
    connect_pg,
    emit_result,
    severity_max,
    split_engine_modes,
    wilson_ci_95,
)

# ───────────────────────────────────────────────────────────────────────────
# Stop-out pattern allowlist（R2 source-derived，2026-05-21 E1 grep 驗證 +
# E2 review §CRITICAL chain detail 對齊）
# ───────────────────────────────────────────────────────────────────────────
#
# 這份 pattern 列表是「**強制** stop / liquidation 路徑」的 LIKE pattern：
# graceful strategy exit (ma_reverse_cross / bb_mean_revert / grid_close_*
# / funding_arb_exit / pctb_revert / bw_squeeze) 與 take_profit 都不計入。
#
# 為什麼用 LIKE：exit_reason 為 free-text，多筆值帶冒號 + 動態尾巴
# （`HARD STOP: pnl -25.00% <= -20.00%` / `phys_lock_gate4_giveback` / ...），
# 用 prefix LIKE 比 IN-list 更耐 schema drift。
#
# R1 → R2 修正歷史（E2 HIGH-A1 + HIGH-A2，2026-05-21）：
#   R1 用 lowercase ``hard_stop:%`` / ``time_stop:%``，但 production
#   exit_reason 經 `risk_checks.rs` format!() emit 後是大寫 + 空格 + colon
#   （`HARD STOP: ...` / `DYNAMIC STOP: ...` / `TIME STOP: ...`），且 R1
#   完全漏 `DYNAMIC STOP` 一族。R2 改用大寫 prefix + 加 `DYNAMIC STOP%`，
#   並補測 `test_default_patterns_match_real_production_exit_reasons` 用
#   fnmatch 模擬 LIKE 對 7 個 production 真實字串固化。
#
# Pattern 對應 emission source 一覽：
#   - 大寫 + 空格家族（risk_checks.rs format!() 直接 emit，經
#     step_6_risk_checks.rs build_risk_close_tag wrap 為 `risk_close:` 後
#     被 helpers_close_tags::build_close_tags_from_legacy strip 出 exit_reason）：
#       `HARD STOP%`     ← risk_checks.rs:334
#       `DYNAMIC STOP%`  ← risk_checks.rs:355（R1 漏，R2 補）
#       `TIME STOP%`     ← risk_checks.rs:390
#       `TRAILING STOP%` ← risk_checks.rs:379
#   - 小寫底線家族（strategy / fast_track / halt / phys_lock 直接 emit
#     lowercase，無大寫變體）：
#       `trailing_stop%` ← strategies/bb_breakout/mod.rs:910/919
#       `fast_track%`    ← step_0_fast_track.rs:486/500/603/616
#       `halt_session%`  ← helpers_close_tags.rs:122-127 R-A5
#                          fallback prefix（涵蓋 SESSION DRAWDOWN /
#                          DAILY LOSS）
#       `phys_lock_%`    ← physical_micro_profit_lock_v2 emit
#                          phys_lock_gate4_giveback / _stale_roc_neg
DEFAULT_STOPOUT_EXIT_REASON_PATTERNS: tuple[str, ...] = (
    # 大寫 + 空格家族（risk_checks.rs:334/355/379/390 format!() emit）
    "HARD STOP%",        # risk_checks.rs:334
    "DYNAMIC STOP%",     # risk_checks.rs:355（R2 HIGH-A2 補）
    "TIME STOP%",        # risk_checks.rs:390
    "TRAILING STOP%",    # risk_checks.rs:379
    # 小寫底線家族（strategy / fast_track / halt_session / phys_lock 路徑）
    "trailing_stop%",    # strategies/bb_breakout/mod.rs:910/919（lowercase）
    "fast_track%",       # step_0_fast_track.rs:486/500/603/616
    "halt_session%",     # helpers_close_tags.rs:122-127 R-A5 fallback prefix
    "phys_lock_%",       # physical_micro_profit_lock_v2 emit
)

# liquidation 路徑：交易所自動平倉的 audit 簽名（strategy_name 而非 exit_reason）
# 見 event_consumer/unattributed_emit.rs:174/215（exit_reason=None）+
# database/trading_writer.rs:1437
LIQUIDATION_STRATEGY_NAME_PATTERN: str = "unattributed:%"


def _parse_args() -> argparse.Namespace:
    parser = build_argparser(
        name="66_close_maker_pre_stopout_rate",
        description=(
            "[66] close_maker_pre_stopout_rate healthcheck — "
            "P1-OBS-PRE-STOPOUT-RATE close maker 來得及量度 (FA round 1 #5)"
        ),
    )
    parser.add_argument(
        "--pass-upper",
        type=float,
        default=0.10,
        help="stopout_rate ≤ pass_upper → PASS (default 0.10 per prompt 草案)",
    )
    parser.add_argument(
        "--fail-upper",
        type=float,
        default=0.30,
        help="stopout_rate > fail_upper → FAIL (default 0.30 per prompt 草案)",
    )
    parser.add_argument(
        "--min-sample",
        type=int,
        default=30,
        help="Minimum attempts before gate (default 30 per MIT-MF-2/SF-3)",
    )
    parser.add_argument(
        "--stopout-patterns",
        type=str,
        default=None,
        help=(
            "覆寫 stop-out exit_reason LIKE patterns CSV "
            "(default 用 DEFAULT_STOPOUT_EXIT_REASON_PATTERNS source-derived list)"
        ),
    )
    # R2 MEDIUM-D1（2026-05-21）：Wilson 95%% CI sub-clause（mirror [62] AC-18）
    # 注：argparse %%-format help，所有 ``%`` 字面要寫成 ``%%`` 避 _expand_help 崩
    parser.add_argument(
        "--no-wilson",
        action="store_true",
        help=(
            "停用 Wilson 95%% CI sub-clause，退回 R1 raw-rate-only ladder "
            "(default: Wilson sub-clause enabled per R2 MEDIUM-D1)"
        ),
    )
    parser.add_argument(
        "--wilson-upper-pass",
        type=float,
        default=0.15,
        help=(
            "Wilson upper bound ≤ 此值才允 PASS（搭配 raw ≤ pass_upper）；"
            "預設 0.15 (R2 MEDIUM-D1)"
        ),
    )
    parser.add_argument(
        "--wilson-lower-fail",
        type=float,
        default=0.15,
        help=(
            "Wilson lower bound > 此值即 FAIL（即使 raw ≤ fail_upper）；"
            "預設 0.15（E2 R2 push back 後從 0.20 調降，避免 demo "
            "velocity n~70/week 下 0.20 成 dead gate；對稱配 raw upper 0.15）"
        ),
    )
    return parser.parse_args()


def _split_patterns(patterns_csv: str | None) -> list[str]:
    """CSV → list；None / empty → default 列表。"""
    if not patterns_csv:
        return list(DEFAULT_STOPOUT_EXIT_REASON_PATTERNS)
    return [p.strip() for p in patterns_csv.split(",") if p.strip()]


def _stopout_rate_verdict(
    stopouts: int,
    total: int,
    min_sample: int,
    pass_upper: float,
    fail_upper: float,
    *,
    use_wilson: bool = True,
    wilson_upper_pass: float = 0.15,
    wilson_lower_fail: float = 0.15,
) -> tuple[str, float, float, float]:
    """[66] stopout_rate ladder。

    R1 為 raw-rate-only 雙閾值；R2 MEDIUM-D1（2026-05-21）補 Wilson 95% CI
    sub-clause（mirror [62] AC-18 風格）增強小樣本 conservativeness。

    本 metric 為 failure-direction（rate 越低越好），所以 mirror [62] 的方式
    對稱反轉：
      - [62] success-direction：PASS 要 Wilson **lower** ≥ pass_lower（即使
        raw 高，也要下界穩）；FAIL 要 Wilson **upper** < warn_lower
      - [66] failure-direction：PASS 要 Wilson **upper** ≤ wilson_upper_pass
        （即使 raw 低，也要上界穩）；FAIL 要 Wilson **lower** > wilson_lower_fail
        （即使 raw 還沒過 fail_upper，下界已超即可判 over-shoot）

    為什麼仍保留 raw-rate gate：prompt 0.10 / 0.30 為「rate-level」直觀門檻，
    operator 報告易理解；Wilson 為 secondary conservativeness layer，雙條件
    AND/OR 組合提升信號可靠度。

    回傳 (verdict, stopout_rate, wilson_lower, wilson_upper)。
    use_wilson=False 時 wilson_lower / wilson_upper 仍計算回傳（給 cell payload
    觀察用），但不參與 verdict 判定 — 即退回 R1 ladder。
    """
    if total < min_sample:
        rate = stopouts / total if total else 0.0
        return (VERDICT_INSUFFICIENT_SAMPLE, rate, 0.0, 0.0)
    rate = stopouts / total
    lower, upper = wilson_ci_95(stopouts, total)
    if not use_wilson:
        # R1 raw-rate-only ladder（``--no-wilson`` opt-out 走這條）
        if rate <= pass_upper:
            return (VERDICT_PASS, rate, lower, upper)
        if rate > fail_upper:
            return (VERDICT_FAIL, rate, lower, upper)
        return (VERDICT_WARN, rate, lower, upper)
    # R2 Wilson sub-clause（default）
    #   FAIL 先判（任一觸發）：raw > fail_upper OR Wilson lower > wilson_lower_fail
    #   PASS 再判（要 AND）：raw ≤ pass_upper AND Wilson upper ≤ wilson_upper_pass
    #   其他 → WARN
    if rate > fail_upper or lower > wilson_lower_fail:
        return (VERDICT_FAIL, rate, lower, upper)
    if rate <= pass_upper and upper <= wilson_upper_pass:
        return (VERDICT_PASS, rate, lower, upper)
    return (VERDICT_WARN, rate, lower, upper)


def run(
    cur,
    window_secs: int,
    engine_modes: list[str],
    pass_upper: float,
    fail_upper: float,
    min_sample: int,
    stopout_patterns: list[str],
    *,
    use_wilson: bool = True,
    wilson_upper_pass: float = 0.15,
    wilson_lower_fail: float = 0.15,
) -> dict:
    """執行 SQL + verdict 計算，回傳 result dict。

    SQL 語意：在 close_maker_attempt=TRUE 的母體上，計 stopout / clean exits
    per engine_mode。stopout 定義為 (exit_reason 命中 stopout_patterns 任一
    LIKE pattern) OR (strategy_name LIKE 'unattributed:%')。

    Wilson sub-clause（R2 MEDIUM-D1，2026-05-21）：
      use_wilson=True（default）：每 cell 額外計 Wilson 95% CI；PASS 要
        raw ≤ pass_upper AND upper ≤ wilson_upper_pass；FAIL 要
        raw > fail_upper OR lower > wilson_lower_fail。
      use_wilson=False（``--no-wilson``）：退回 R1 raw-rate-only ladder。
    """
    # 為什麼用 array_concat + ANY-pattern：psycopg2 LIKE %s ANY(array) pattern
    # 不直接支援；改用 ``exit_reason LIKE ANY(%s::text[])`` PG 9.5+ 標準語法。
    cur.execute(
        """
        SELECT
            engine_mode,
            COUNT(*)::int AS attempts,
            COUNT(*) FILTER (
                WHERE exit_reason LIKE ANY(%s::text[])
                   OR strategy_name LIKE %s
            )::int AS stopouts,
            COUNT(*) FILTER (
                WHERE NOT (
                    exit_reason LIKE ANY(%s::text[])
                    OR strategy_name LIKE %s
                )
            )::int AS clean_exits
        FROM trading.fills
        WHERE close_maker_attempt = TRUE
          AND ts > NOW() - (%s::int * INTERVAL '1 second')
          AND engine_mode = ANY(%s::text[])
        GROUP BY engine_mode
        ORDER BY engine_mode
        """,
        (
            stopout_patterns,
            LIQUIDATION_STRATEGY_NAME_PATTERN,
            stopout_patterns,
            LIQUIDATION_STRATEGY_NAME_PATTERN,
            window_secs,
            engine_modes,
        ),
    )
    rows = list(cur.fetchall() or [])

    cells: list[dict] = []
    overall_verdict = "PASS"
    total_attempts = 0
    total_stopouts = 0

    if not rows:
        overall_verdict = VERDICT_INSUFFICIENT_SAMPLE
        cells.append({
            "engine_mode": ",".join(engine_modes),
            "n_attempts": 0,
            "n_stopouts": 0,
            "n_clean_exits": 0,
            "stopout_rate": 0.0,
            "verdict": VERDICT_INSUFFICIENT_SAMPLE,
            "note": "no close_maker_attempt=TRUE rows in window",
        })
    else:
        for row in rows:
            engine_mode = row[0]
            attempts = int(row[1] or 0)
            stopouts = int(row[2] or 0)
            clean_exits = int(row[3] or 0)
            verdict, rate, wilson_lower, wilson_upper = _stopout_rate_verdict(
                stopouts,
                attempts,
                min_sample=min_sample,
                pass_upper=pass_upper,
                fail_upper=fail_upper,
                use_wilson=use_wilson,
                wilson_upper_pass=wilson_upper_pass,
                wilson_lower_fail=wilson_lower_fail,
            )
            cells.append({
                "engine_mode": engine_mode,
                "n_attempts": attempts,
                "n_stopouts": stopouts,
                "n_clean_exits": clean_exits,
                "stopout_rate": round(rate, 4),
                "wilson_lower": round(wilson_lower, 4),
                "wilson_upper": round(wilson_upper, 4),
                "verdict": verdict,
            })
            overall_verdict = severity_max(overall_verdict, verdict)
            total_attempts += attempts
            total_stopouts += stopouts

    return {
        "metric": "close_maker_pre_stopout_rate",
        "check_id": "[66]",
        "spec": (
            "P1-OBS-PRE-STOPOUT-RATE / FA 2026-05-20 round 1 #5 follow-up; "
            "schema = V033 exit_reason + V094 close_maker_attempt"
        ),
        "window_secs": window_secs,
        "engine_modes": engine_modes,
        "thresholds": {
            "min_sample": min_sample,
            "pass_upper": pass_upper,
            "fail_upper": fail_upper,
            "wilson_upper_pass": wilson_upper_pass,
            "wilson_lower_fail": wilson_lower_fail,
        },
        "use_wilson_subclause": use_wilson,
        "stopout_patterns": stopout_patterns,
        "liquidation_strategy_pattern": LIQUIDATION_STRATEGY_NAME_PATTERN,
        "total_attempts": total_attempts,
        "total_stopouts": total_stopouts,
        "cells": cells,
        "verdict": overall_verdict,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    configure_logging()
    args = _parse_args()
    engine_modes = split_engine_modes(args.engine_mode)
    stopout_patterns = _split_patterns(args.stopout_patterns)

    conn = connect_pg()
    try:
        with conn.cursor() as cur:
            result = run(
                cur,
                window_secs=args.window_secs,
                engine_modes=engine_modes,
                pass_upper=args.pass_upper,
                fail_upper=args.fail_upper,
                min_sample=args.min_sample,
                stopout_patterns=stopout_patterns,
                use_wilson=not args.no_wilson,
                wilson_upper_pass=args.wilson_upper_pass,
                wilson_lower_fail=args.wilson_lower_fail,
            )
    finally:
        conn.close()

    emit_result(result, write_file=args.write_file, text_mode=args.text)

    if result["verdict"] in (VERDICT_FAIL, VERDICT_WARN):
        return EXIT_FAIL
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
