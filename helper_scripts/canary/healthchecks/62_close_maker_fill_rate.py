#!/usr/bin/env python3
"""[62] close_maker_fill_rate — Phase 1b 部署後 PASS gate。

MODULE_NOTE:
  AMD-2026-05-15-02 v0.6 §4.1 + spec §8.1 規範的 [62] healthcheck standalone
  入口。計算 7d demo+live_demo close-maker-first attempts 的 maker fill rate
  + Wilson 95% CI，per AMD §5.1 Consensus-MF-2 sample-size + Wilson-CI gating。

  與 ``passive_wait_healthcheck.checks_close_maker_audit.check_close_maker_fill_rate``
  ([70] slot) SQL 語意對齊；本檔是 PM/QA 手動觸發的 standalone 入口，輸出
  JSON artifact 給 24h post-deploy verify 流程引用。

Verdict ladder（spec §8.1 line 511-519，可透過 CLI 覆寫 threshold）：
  - n < 30 → INSUFFICIENT_SAMPLE（不入 PASS/FAIL 分母）
  - Wilson lower ≥ pass_lower → PASS
  - Wilson upper < warn_lower → FAIL
  - 其他 → WARN

Spec §8.1 預設 threshold 60/40（與 [70] slot 對齊）；PA prompt §1 提及的
conservative 25 / median 35 / target 50 是 AC-19 14d extended observation
gate，caller 透過 ``--pass-lower 0.50 --warn-lower 0.25`` 切換。

CLI:
  python3 62_close_maker_fill_rate.py [--window-secs 604800] \\
        [--engine-mode demo,live_demo] [--pass-lower 0.60] \\
        [--warn-lower 0.40] [--min-sample 30] [--write-file PATH] [--text]

Exit codes:
  0 = PASS / INSUFFICIENT_SAMPLE（後者不阻 deploy）
  1 = WARN or FAIL
  2 = PG connect error
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# 允許作為 standalone script + module 同時被呼叫
# stdlib import 之後加 sys.path 是為了讓 ``python3 62_close_maker_fill_rate.py``
# 直接執行也能 import 同目錄 _common；package import 走 ``__init__.py`` 不受影響
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _common import (  # noqa: E402
    EXIT_FAIL,
    EXIT_PASS,
    VERDICT_FAIL,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_WARN,
    build_argparser,
    configure_logging,
    connect_pg,
    emit_result,
    fill_rate_verdict,
    severity_max,
    split_engine_modes,
)


def _parse_args() -> argparse.Namespace:
    parser = build_argparser(
        name="62_close_maker_fill_rate",
        description=(
            "[62] close_maker_fill_rate Wilson-CI healthcheck — "
            "Phase 1b post-deploy verification gate"
        ),
    )
    parser.add_argument(
        "--pass-lower",
        type=float,
        default=0.60,
        help="Wilson CI lower bound for PASS (default 0.60 per spec §8.1)",
    )
    parser.add_argument(
        "--warn-lower",
        type=float,
        default=0.40,
        help="Wilson CI upper bound below which FAIL (default 0.40 per spec §8.1)",
    )
    parser.add_argument(
        "--min-sample",
        type=int,
        default=30,
        help="Minimum attempts before Wilson gate (default 30 per MIT-MF-2/SF-3)",
    )
    return parser.parse_args()


def run(
    cur,
    window_secs: int,
    engine_modes: list[str],
    pass_lower: float,
    warn_lower: float,
    min_sample: int,
) -> dict:
    """執行 SQL + Wilson 計算，回傳 result dict。"""
    cur.execute(
        """
        SELECT
            engine_mode,
            COUNT(*)::int AS attempts,
            COUNT(*) FILTER (WHERE close_maker_fallback_reason IS NULL)::int AS maker_fills,
            COUNT(*) FILTER (WHERE close_maker_fallback_reason IS NOT NULL)::int AS fallbacks
        FROM trading.fills
        WHERE close_maker_attempt = TRUE
          AND ts > NOW() - (%s::int * INTERVAL '1 second')
          AND engine_mode = ANY(%s::text[])
        GROUP BY engine_mode
        ORDER BY engine_mode
        """,
        (window_secs, engine_modes),
    )
    rows = list(cur.fetchall() or [])

    cells: list[dict] = []
    overall_verdict = "PASS"
    total_attempts = 0
    total_fills = 0

    if not rows:
        overall_verdict = VERDICT_INSUFFICIENT_SAMPLE
        cells.append({
            "engine_mode": ",".join(engine_modes),
            "n_attempts": 0,
            "n_fills": 0,
            "n_fallbacks": 0,
            "fill_rate": 0.0,
            "wilson_lower": 0.0,
            "wilson_upper": 0.0,
            "verdict": VERDICT_INSUFFICIENT_SAMPLE,
            "note": "no close_maker_attempt=TRUE rows in window",
        })
    else:
        for row in rows:
            engine_mode = row[0]
            attempts = int(row[1] or 0)
            fills = int(row[2] or 0)
            fallbacks = int(row[3] or 0)
            verdict, rate, lower, upper = fill_rate_verdict(
                fills, attempts, min_sample=min_sample,
                pass_lower=pass_lower, warn_lower=warn_lower,
            )
            cells.append({
                "engine_mode": engine_mode,
                "n_attempts": attempts,
                "n_fills": fills,
                "n_fallbacks": fallbacks,
                "fill_rate": round(rate, 4),
                "wilson_lower": round(lower, 4),
                "wilson_upper": round(upper, 4),
                "verdict": verdict,
            })
            overall_verdict = severity_max(overall_verdict, verdict)
            total_attempts += attempts
            total_fills += fills

    return {
        "metric": "close_maker_fill_rate",
        "check_id": "[62]",
        "spec": "AMD-2026-05-15-02 §4.1 / spec §8.1 Consensus-MF-2",
        "window_secs": window_secs,
        "engine_modes": engine_modes,
        "thresholds": {
            "min_sample": min_sample,
            "pass_lower": pass_lower,
            "warn_lower": warn_lower,
        },
        "total_attempts": total_attempts,
        "total_fills": total_fills,
        "cells": cells,
        "verdict": overall_verdict,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    configure_logging()
    args = _parse_args()
    engine_modes = split_engine_modes(args.engine_mode)

    conn = connect_pg()
    try:
        with conn.cursor() as cur:
            result = run(
                cur,
                window_secs=args.window_secs,
                engine_modes=engine_modes,
                pass_lower=args.pass_lower,
                warn_lower=args.warn_lower,
                min_sample=args.min_sample,
            )
    finally:
        conn.close()

    emit_result(result, write_file=args.write_file, text_mode=args.text)

    if result["verdict"] in (VERDICT_FAIL, VERDICT_WARN):
        return EXIT_FAIL
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
