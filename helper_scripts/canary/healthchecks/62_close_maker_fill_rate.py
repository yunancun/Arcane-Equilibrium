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
        [--warn-lower 0.40] [--min-sample 30] [--write-file PATH] [--text] \\
        [--stratify {none,hour,dow,both}]

``--stratify`` 行為（P1-OBS-FILL-RATE-STRATIFY，2026-05-21）：
  - none（預設）→ 與舊行為 100% 一致（per engine_mode 一行）
  - hour → GROUP BY engine_mode, EXTRACT(HOUR FROM ts) → 24 cells/engine_mode
  - dow  → GROUP BY engine_mode, EXTRACT(DOW FROM ts)  → 7 cells/engine_mode
  - both → GROUP BY engine_mode + HOUR + DOW            → 168 cells/engine_mode
  per-cell INSUFFICIENT_SAMPLE 在 stratify 模式下不影響 overall verdict
  （避免稀疏 hour/dow bucket 把整體拉成 INSUFFICIENT）。

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
    VERDICT_PASS,
    VERDICT_WARN,
    build_argparser,
    configure_logging,
    connect_pg,
    emit_result,
    fill_rate_verdict,
    severity_max,
    split_engine_modes,
)

# P1-OBS-FILL-RATE-STRATIFY（2026-05-21）：--stratify 模式允許的 cell 維度。
# none = 舊行為（per engine_mode 一行）；hour/dow/both = 階層化以協助找尋
# 時段或星期粒度的 fill_rate degeneration。
_STRATIFY_CHOICES = ("none", "hour", "dow", "both")


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
    parser.add_argument(
        "--stratify",
        type=str,
        choices=_STRATIFY_CHOICES,
        default="none",
        help=(
            "P1-OBS-FILL-RATE-STRATIFY 階層化維度 (default none)；"
            "hour / dow / both 增加 GROUP BY 維度，cells 內加 hour / dow 欄位"
        ),
    )
    return parser.parse_args()


# ───────────────────────────────────────────────────────────────────────────
# Stratify 輔助（P1-OBS-FILL-RATE-STRATIFY，2026-05-21）
# ───────────────────────────────────────────────────────────────────────────


def _stratify_sql_addons(stratify: str) -> tuple[str, str]:
    """根據 --stratify 回傳 (extra_select_cols, extra_group_by_cols)。

    為什麼拆函式：SQL 字串在 run() 內組裝；單獨函式讓 stratify 維度與 SELECT/
    GROUP BY clause 對應清晰，並讓 unit test 可單獨驗 mapping 正確。
    """
    if stratify == "none":
        return ("", "")
    if stratify == "hour":
        return (
            ", EXTRACT(HOUR FROM ts)::int AS hour",
            ", EXTRACT(HOUR FROM ts)",
        )
    if stratify == "dow":
        return (
            ", EXTRACT(DOW FROM ts)::int AS dow",
            ", EXTRACT(DOW FROM ts)",
        )
    if stratify == "both":
        return (
            ", EXTRACT(HOUR FROM ts)::int AS hour, EXTRACT(DOW FROM ts)::int AS dow",
            ", EXTRACT(HOUR FROM ts), EXTRACT(DOW FROM ts)",
        )
    raise ValueError(f"unknown stratify mode: {stratify}")


def _stratified_overall_verdict(cell_verdicts: list[str]) -> str:
    """Stratify 模式下的 overall verdict 收斂。

    為什麼與 ``severity_max`` 不同：階層化後 hour/dow bucket 必然稀疏（24 / 7 /
    168 cells），多數 cells 命中 ``INSUFFICIENT_SAMPLE``；用標準 severity_max
    會把 1 個 PASS 被 99 個 INSUFFICIENT 拉成 INSUFFICIENT，喪失 stratify 的
    觀察價值。Stratify 模式約定：**INSUFFICIENT 不參與整體裁決**，僅 PASS /
    WARN / FAIL cells 才被 severity_max 累積；全部 INSUFFICIENT 則整體為
    INSUFFICIENT（與 prompt 規範一致）。
    """
    actionable = [v for v in cell_verdicts if v != VERDICT_INSUFFICIENT_SAMPLE]
    if not actionable:
        return VERDICT_INSUFFICIENT_SAMPLE
    overall = VERDICT_PASS
    for verdict in actionable:
        overall = severity_max(overall, verdict)
    return overall


def run(
    cur,
    window_secs: int,
    engine_modes: list[str],
    pass_lower: float,
    warn_lower: float,
    min_sample: int,
    stratify: str = "none",
) -> dict:
    """執行 SQL + Wilson 計算，回傳 result dict。

    stratify 為 ``none`` 時 SQL 與行為與舊版 100% 一致（含逐字節 SQL string，
    保留現有 test_sql_uses_engine_mode_filter 通過）；hour / dow / both 為
    P1-OBS-FILL-RATE-STRATIFY 加入的階層化模式。
    """
    if stratify == "none":
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
    else:
        # Stratify 模式 — 在 SELECT / GROUP BY 加 hour / dow，cell 維度擴張。
        # ORDER BY 同時帶 hour/dow 讓輸出穩定（per engine_mode 內按時序排序）。
        extra_select, extra_group = _stratify_sql_addons(stratify)
        cur.execute(
            f"""
        SELECT
            engine_mode,
            COUNT(*)::int AS attempts,
            COUNT(*) FILTER (WHERE close_maker_fallback_reason IS NULL)::int AS maker_fills,
            COUNT(*) FILTER (WHERE close_maker_fallback_reason IS NOT NULL)::int AS fallbacks{extra_select}
        FROM trading.fills
        WHERE close_maker_attempt = TRUE
          AND ts > NOW() - (%s::int * INTERVAL '1 second')
          AND engine_mode = ANY(%s::text[])
        GROUP BY engine_mode{extra_group}
        ORDER BY engine_mode{extra_group}
        """,
            (window_secs, engine_modes),
        )

    rows = list(cur.fetchall() or [])

    cells: list[dict] = []
    # overall_verdict 由下方兩條路徑（not rows / else stratify branch）獨立
    # 賦值；舊版 line 225 ``"PASS"`` init 已被 stratify branch line 277 / 282
    # 覆蓋兩次，純 dead init（R2 E2 review LOW-F3 清理）。
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
            cell: dict = {
                "engine_mode": engine_mode,
                "n_attempts": attempts,
                "n_fills": fills,
                "n_fallbacks": fallbacks,
                "fill_rate": round(rate, 4),
                "wilson_lower": round(lower, 4),
                "wilson_upper": round(upper, 4),
                "verdict": verdict,
            }
            # Stratify 維度直接帶進 cell（none 時跳過，向後兼容）。
            # row schema：none → 4 cols；hour → 5；dow → 5；both → 6。
            if stratify == "hour":
                cell["hour"] = int(row[4]) if row[4] is not None else None
            elif stratify == "dow":
                cell["dow"] = int(row[4]) if row[4] is not None else None
            elif stratify == "both":
                cell["hour"] = int(row[4]) if row[4] is not None else None
                cell["dow"] = int(row[5]) if row[5] is not None else None
            cells.append(cell)
            total_attempts += attempts
            total_fills += fills

        # Stratify 模式下 INSUFFICIENT cells 不影響 overall；none 模式保留
        # 原 severity_max 行為，確保 default 路徑與舊版逐 verdict 等價。
        if stratify == "none":
            overall_verdict = "PASS"
            for cell in cells:
                overall_verdict = severity_max(overall_verdict, cell["verdict"])
        else:
            overall_verdict = _stratified_overall_verdict(
                [cell["verdict"] for cell in cells]
            )

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
        "stratify": stratify,
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
                stratify=args.stratify,
            )
    finally:
        conn.close()

    emit_result(result, write_file=args.write_file, text_mode=args.text)

    if result["verdict"] in (VERDICT_FAIL, VERDICT_WARN):
        return EXIT_FAIL
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
