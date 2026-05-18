#!/usr/bin/env python3
"""[65] close_maker_reject_samples — Phase 2a Demo silent degradation 防護。

MODULE_NOTE:
  AMD-2026-05-15-02 v0.6 §4.1 + spec §8.3 BB-MF-5 規範的 [65] healthcheck
  standalone 入口。

  問題背景（spec §8.3 line 603-606）：Bybit demo doc 沒明文聲明 demo endpoint
  對 PostOnly close 的 reject 推送行為；7d 0 reject sample 可能是 demo silent
  degradation（reject 沒被推回 engine = audit 失效）。Phase 2b LiveDemo 啟用
  前必確認 demo endpoint 真的會推送 reject sample。

  PASS criteria（spec §8.3 line 608-611，per env 7d）：
    - ``EC_PostOnlyWillTakeLiquidity`` reject sample count ≥ 1
    - ``EC_ReachMaxPendingOrders`` reject sample count ≥ 1
  兩 category 各至少 1 樣本確認 Bybit demo endpoint 真會推送 reject。

  Reject sample SQL 來源（與 [74] slot 對齊）：
    - ``close_maker_fallback_reason = 'postonly_reject'`` 或
      ``details->>'reject_reason' = 'EC_PostOnlyWillTakeLiquidity'`` → PostOnly
    - ``close_maker_fallback_reason IN ('rate_limit_pause_global',
      'rate_limit_backoff_per_symbol')`` 或
      ``details->>'reject_reason' = 'EC_ReachMaxPendingOrders'`` → MaxPending

  Verdict ladder：
    - n_attempts < min_sample → INSUFFICIENT_SAMPLE
    - any engine_mode 缺 PostOnly 或 MaxPending sample → FAIL
      （per AC-15 強要求；缺一即無法 promote Phase 2b）
    - all engine_mode 兩 category 都 ≥ 1 sample → PASS

CLI:
  python3 65_reject_sample_healthcheck.py [--window-secs 604800] \\
        [--engine-mode demo,live_demo] [--min-attempts 5] \\
        [--write-file PATH] [--text]

Exit codes:
  0 = PASS / INSUFFICIENT_SAMPLE
  1 = FAIL（缺任一 category sample）
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
    build_argparser,
    configure_logging,
    connect_pg,
    emit_result,
)


def _parse_args() -> argparse.Namespace:
    parser = build_argparser(
        name="65_reject_sample_healthcheck",
        description=(
            "[65] close_maker_reject_samples — PostOnly + MaxPending coverage proof"
        ),
    )
    parser.add_argument(
        "--min-attempts",
        type=int,
        default=5,
        help=(
            "Minimum close_maker_attempt=TRUE rows before invoking reject coverage "
            "ladder; below this → INSUFFICIENT_SAMPLE (default 5)"
        ),
    )
    return parser.parse_args()


def run(
    cur,
    window_secs: int,
    engine_modes: list[str],
    min_attempts: int,
) -> dict:
    cur.execute(
        """
        SELECT
            engine_mode,
            COUNT(*)::int AS attempts,
            COUNT(*) FILTER (
                WHERE close_maker_fallback_reason = 'postonly_reject'
                   OR details->>'reject_reason' = 'EC_PostOnlyWillTakeLiquidity'
            )::int AS postonly_reject_samples,
            COUNT(*) FILTER (
                WHERE close_maker_fallback_reason IN (
                    'rate_limit_pause_global',
                    'rate_limit_backoff_per_symbol'
                )
                   OR details->>'reject_reason' = 'EC_ReachMaxPendingOrders'
            )::int AS max_pending_samples
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
    overall_verdict = VERDICT_PASS
    total_attempts = 0
    total_postonly = 0
    total_max_pending = 0
    missing_categories: list[str] = []

    if not rows:
        return {
            "metric": "close_maker_reject_samples",
            "check_id": "[65]",
            "spec": "AMD-2026-05-15-02 §4.1 / spec §8.3 BB-MF-5 / AC-15",
            "window_secs": window_secs,
            "engine_modes": engine_modes,
            "thresholds": {"min_attempts": min_attempts},
            "total_attempts": 0,
            "total_postonly_samples": 0,
            "total_max_pending_samples": 0,
            "cells": [],
            "missing_categories": [],
            "verdict": VERDICT_INSUFFICIENT_SAMPLE,
            "verdict_note": (
                "0 close_maker_attempt=TRUE rows in window — "
                "cannot prove reject sample coverage"
            ),
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    any_below_min = False
    for row in rows:
        engine_mode = row[0]
        attempts = int(row[1] or 0)
        postonly = int(row[2] or 0)
        max_pending = int(row[3] or 0)
        total_attempts += attempts
        total_postonly += postonly
        total_max_pending += max_pending

        cell_missing: list[str] = []
        if attempts < min_attempts:
            any_below_min = True
            cell_status = VERDICT_INSUFFICIENT_SAMPLE
            note = f"n_attempts={attempts} < min={min_attempts}"
        else:
            if postonly == 0:
                cell_missing.append("EC_PostOnlyWillTakeLiquidity")
            if max_pending == 0:
                cell_missing.append("EC_ReachMaxPendingOrders")
            if cell_missing:
                cell_status = VERDICT_FAIL
                note = f"missing reject samples: {cell_missing}"
                missing_categories.extend(
                    [f"{engine_mode}/{cat}" for cat in cell_missing]
                )
                overall_verdict = VERDICT_FAIL
            else:
                cell_status = VERDICT_PASS
                note = "PostOnly + MaxPending samples both present"

        cells.append({
            "engine_mode": engine_mode,
            "n_attempts": attempts,
            "postonly_reject_samples": postonly,
            "max_pending_samples": max_pending,
            "missing": cell_missing,
            "verdict": cell_status,
            "note": note,
        })

    # 全部 cell INSUFFICIENT_SAMPLE → overall = INSUFFICIENT_SAMPLE
    if any_below_min and overall_verdict == VERDICT_PASS:
        if all(c["verdict"] == VERDICT_INSUFFICIENT_SAMPLE for c in cells):
            overall_verdict = VERDICT_INSUFFICIENT_SAMPLE

    return {
        "metric": "close_maker_reject_samples",
        "check_id": "[65]",
        "spec": "AMD-2026-05-15-02 §4.1 / spec §8.3 BB-MF-5 / AC-15",
        "window_secs": window_secs,
        "engine_modes": engine_modes,
        "thresholds": {"min_attempts": min_attempts},
        "total_attempts": total_attempts,
        "total_postonly_samples": total_postonly,
        "total_max_pending_samples": total_max_pending,
        "cells": cells,
        "missing_categories": missing_categories,
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
                min_attempts=args.min_attempts,
            )
    finally:
        conn.close()

    emit_result(result, write_file=args.write_file, text_mode=args.text)

    if result["verdict"] == VERDICT_FAIL:
        return EXIT_FAIL
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
