#!/usr/bin/env python3
"""[64] close_maker_rate_limit_pause_duration — per-symbol + global backoff 健康度。

MODULE_NOTE:
  AMD-2026-05-15-02 v0.6 §5.4 BB-MF-2 dynamic backoff + spec §8.1 規範的
  [64] healthcheck standalone 入口。

  AMD §5.4 設計：
    - per-symbol exponential backoff 1s → 60s（binary，每次同 symbol 連續
      TooManyPending → ``backoff *= 2``，上限 60s）
    - conditional global pause 5min（同 1min window 內 ≥10 distinct symbol 同
      時在 backoff 才升級全域 5min pause）
    - audit row: per-symbol → ``close_maker_fallback_reason = 'rate_limit_backoff_per_symbol'``
                  global → ``close_maker_fallback_reason = 'rate_limit_pause_global'``
                          + ``details->>'rate_limit_scope' = 'global'``

  本 check 統計 7d demo+live_demo 兩種 backoff 樣本量 + 每日平均：
    per-symbol thresholds（spec §8.1 line 573-577 + AMD §5.4 line 244-247）:
      PASS: ≤ 5 sample/day per symbol（或 ≤ 5 min/day per symbol — 由 sample
            數推算；單次 backoff 平均 < 60s，5 samples ≈ 5 min upper-bound）
      WARN: 5-30 sample/day per symbol
      FAIL: > 30 sample/day per symbol
    Global pause thresholds（同上 line 578-582）:
      PASS: ≤ 5 sample/day
      WARN: 5-30 sample/day
      FAIL: > 30 sample/day

  PG 沒有直接記錄 backoff duration（runtime in-memory state，per AMD §5.4
  line 237-240「engine restart 後重置」），所以本 check 用 audit row count
  作 proxy；若未來引入 backoff duration audit field，可升級為 actual seconds
  accumulation。

  與 ``passive_wait_healthcheck.checks_close_maker_audit.check_close_maker_rate_limit_backoff_coverage``
  ([73] slot) SQL 語意對齊。

CLI:
  python3 64_close_maker_rate_limit_pause_duration.py [--window-secs 604800] \\
        [--engine-mode demo,live_demo] [--write-file PATH] [--text]

Exit codes:
  0 = PASS / INSUFFICIENT_SAMPLE
  1 = WARN / FAIL
  2 = PG connect error
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

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
)


def _parse_args() -> argparse.Namespace:
    parser = build_argparser(
        name="64_close_maker_rate_limit_pause_duration",
        description=(
            "[64] close_maker_rate_limit_pause_duration — per-symbol & global "
            "backoff sample-rate healthcheck"
        ),
    )
    parser.add_argument(
        "--per-symbol-warn-per-day",
        type=int,
        default=5,
        help="per-symbol per-day count above PASS (default 5 per AMD §5.4)",
    )
    parser.add_argument(
        "--per-symbol-fail-per-day",
        type=int,
        default=30,
        help="per-symbol per-day count above WARN → FAIL (default 30)",
    )
    parser.add_argument(
        "--global-warn-per-day",
        type=int,
        default=5,
        help="global pause per-day count above PASS (default 5)",
    )
    parser.add_argument(
        "--global-fail-per-day",
        type=int,
        default=30,
        help="global pause per-day count above WARN → FAIL (default 30)",
    )
    return parser.parse_args()


def _verdict_for_rate(per_day: float, warn_thr: float, fail_thr: float) -> str:
    """單一指標 rate ladder。"""
    if per_day <= warn_thr:
        return VERDICT_PASS
    if per_day <= fail_thr:
        return VERDICT_WARN
    return VERDICT_FAIL


def run(
    cur,
    window_secs: int,
    engine_modes: list[str],
    per_symbol_warn: int,
    per_symbol_fail: int,
    global_warn: int,
    global_fail: int,
) -> dict:
    days = max(window_secs / 86400.0, 1e-6)

    # (1) per-symbol backoff sample count by symbol — 用 audit row 數做 proxy
    cur.execute(
        """
        SELECT
            symbol,
            engine_mode,
            COUNT(*)::int AS n_per_symbol_backoff
        FROM trading.fills
        WHERE close_maker_attempt = TRUE
          AND close_maker_fallback_reason = 'rate_limit_backoff_per_symbol'
          AND ts > NOW() - (%s::int * INTERVAL '1 second')
          AND engine_mode = ANY(%s::text[])
        GROUP BY 1, 2
        ORDER BY n_per_symbol_backoff DESC
        """,
        (window_secs, engine_modes),
    )
    per_symbol_rows = list(cur.fetchall() or [])

    per_symbol_cells: list[dict] = []
    overall_verdict = "PASS"
    n_per_symbol_total = 0
    for row in per_symbol_rows:
        symbol = row[0]
        engine_mode = row[1]
        n = int(row[2] or 0)
        n_per_symbol_total += n
        per_day = n / days
        v = _verdict_for_rate(per_day, per_symbol_warn, per_symbol_fail)
        overall_verdict = severity_max(overall_verdict, v)
        per_symbol_cells.append({
            "symbol": symbol,
            "engine_mode": engine_mode,
            "count": n,
            "per_day": round(per_day, 3),
            "verdict": v,
        })

    # (2) global pause sample count by engine_mode
    cur.execute(
        """
        SELECT
            engine_mode,
            COUNT(*)::int AS n_global_pause,
            COUNT(*) FILTER (
                WHERE COALESCE(details->>'rate_limit_scope', '') = 'global'
            )::int AS n_scope_tagged
        FROM trading.fills
        WHERE close_maker_attempt = TRUE
          AND close_maker_fallback_reason = 'rate_limit_pause_global'
          AND ts > NOW() - (%s::int * INTERVAL '1 second')
          AND engine_mode = ANY(%s::text[])
        GROUP BY engine_mode
        ORDER BY engine_mode
        """,
        (window_secs, engine_modes),
    )
    global_rows = list(cur.fetchall() or [])

    global_cells: list[dict] = []
    n_global_total = 0
    for row in global_rows:
        engine_mode = row[0]
        n = int(row[1] or 0)
        n_tagged = int(row[2] or 0)
        n_global_total += n
        per_day = n / days
        v = _verdict_for_rate(per_day, global_warn, global_fail)
        overall_verdict = severity_max(overall_verdict, v)
        # 額外 sanity: global event 沒 scope=global tag → JSONB writer gap = WARN
        if n > 0 and n_tagged < n:
            scope_v = VERDICT_WARN
            overall_verdict = severity_max(overall_verdict, scope_v)
            scope_note = (
                f"only {n_tagged}/{n} global pause rows tagged "
                "details.rate_limit_scope=global"
            )
        else:
            scope_note = "scope tags complete"
        global_cells.append({
            "engine_mode": engine_mode,
            "count": n,
            "per_day": round(per_day, 3),
            "scope_tagged_count": n_tagged,
            "scope_note": scope_note,
            "verdict": v,
        })

    if n_per_symbol_total == 0 and n_global_total == 0:
        overall_verdict = VERDICT_INSUFFICIENT_SAMPLE

    return {
        "metric": "close_maker_rate_limit_pause_duration",
        "check_id": "[64]",
        "spec": "AMD-2026-05-15-02 §5.4 BB-MF-2 / spec §8.1 BB-SF-1",
        "window_secs": window_secs,
        "window_days": round(days, 3),
        "engine_modes": engine_modes,
        "thresholds": {
            "per_symbol_warn_per_day": per_symbol_warn,
            "per_symbol_fail_per_day": per_symbol_fail,
            "global_warn_per_day": global_warn,
            "global_fail_per_day": global_fail,
        },
        "n_per_symbol_backoff_total": n_per_symbol_total,
        "n_global_pause_total": n_global_total,
        "per_symbol_cells": per_symbol_cells,
        "global_cells": global_cells,
        "verdict": overall_verdict,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    configure_logging()
    args = _parse_args()

    conn = connect_pg()
    try:
        with conn.cursor() as cur:
            result = run(
                cur,
                window_secs=args.window_secs,
                engine_modes=[m.strip() for m in args.engine_mode.split(",") if m.strip()],
                per_symbol_warn=args.per_symbol_warn_per_day,
                per_symbol_fail=args.per_symbol_fail_per_day,
                global_warn=args.global_warn_per_day,
                global_fail=args.global_fail_per_day,
            )
    finally:
        conn.close()

    emit_result(result, write_file=args.write_file, text_mode=args.text)

    if result["verdict"] in (VERDICT_FAIL, VERDICT_WARN):
        return EXIT_FAIL
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
