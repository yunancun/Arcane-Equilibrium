#!/usr/bin/env python3
"""[67] liquidation_pulse_freshness — W-AUDIT-8a C1-LIQ-WRITER acceptance #3。

MODULE_NOTE:
  PA decomposition §6.3 acceptance #3 規範的 [67] healthcheck standalone 入口。
  覆蓋四個維度（per PA spec 與 acceptance criteria）：
    1. **Topic freshness** — `market.liquidations` 最新 row 的 age vs NOW()；
       Bybit `allLiquidation.{symbol}` WS 應持續推送（24h baseline ~6000+
       row / 32 sym distinct），latest_age 應 < 60s。閾值：WARN > 60s / FAIL > 300s。
    2. **Row volume** — observation window 內 row 數；BB rate budget 假設
       8h baseline ~1500-2500 row（per 24h 6124 row Linux empirical 2026-05-18）。
       per-hour PASS lower 預設 30（即 8h 240+；24h 720+），FAIL 0。
    3. **Symbol coverage** — distinct symbols / cohort size；cohort = 25 sym
       hardcoded（per main.rs DEFAULT_COHORT 25-sym snapshot）。WARN < 80% /
       FAIL < 50%。注意 `market.liquidations` 沒有 cohort 過濾（不在 cohort
       的 symbol 也會被寫），所以 coverage 用 cohort_symbols ∩ observed
       來計算（不用 raw distinct）。
    4. **Parse error guard** — V095 CHECK constraint `chk_..._side_v095`
       強制 side ∈ {'Buy', 'Sell'}；任何 parser bug 寫入怪 side 會被 V095 拒
       （write-error），即 DB 內 row = 全 PASS parse。本 check 透過 enum
       coverage（Buy + Sell 都出現）+ qty/price finite 雙重驗證，發現 parser
       silent degradation（如全 Buy 不見 Sell，或 qty/price NaN/負值）。
       閾值：side enum 兩值都出現 + qty/price > 0 finite ratio = 100% = PASS。

  與既有 [62-65] healthcheck 對齊 SQL semantic / Wilson 閾值 / JSON 輸出格式；
  本 check 不用 Wilson CI（freshness/coverage 是 ratio 而非 proportion test）。

Verdict ladder（per dimension 嚴重度 max-rolled up）：
  - topic_freshness > 300s → FAIL；> 60s → WARN；else PASS
  - row_volume < 1 row in window → FAIL；< pass_lower_per_hour × hours →
    WARN；else PASS
  - symbol_coverage < 50% → FAIL；< 80% → WARN；else PASS
  - parse_guard: side 兩 enum 缺一 → FAIL；qty/price non-finite ratio > 0 → FAIL

整體 verdict 取四維 severity_max；任一 FAIL → overall FAIL。

CLI:
  python3 67_liquidation_pulse_freshness.py [--window-secs 86400] \\
        [--pass-lower-per-hour 30] [--warn-freshness-secs 60] \\
        [--fail-freshness-secs 300] [--warn-coverage 0.80] \\
        [--fail-coverage 0.50] [--write-file PATH] [--text]

Exit codes:
  0 = PASS / INSUFFICIENT_SAMPLE
  1 = WARN or FAIL
  2 = PG connect error
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# 允許 standalone script + module 同時被呼叫
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
    configure_logging,
    connect_pg,
    emit_result,
    severity_max,
)


# ───────────────────────────────────────────────────────────────────────────
# Cohort（per main.rs DEFAULT_COHORT 25-sym snapshot）
# ───────────────────────────────────────────────────────────────────────────
#
# 為什麼 hardcoded：W1 IMPL 階段 cohort 是 fixed snapshot，dynamic cohort 在
# W-AUDIT-8c phase 才接（per panel_aggregator/funding_curve.rs note）。本
# healthcheck 用同一個常量保證跟 LiquidationPulseAggregator 一致。
#
# 為什麼這 25 sym：與 funding_curve / oi_delta / liquidation_pulse aggregator
# 共用；POLUSDT 取代 MATICUSDT（Bybit V5 status=Closed since 2024-09-06）。
COHORT_SYMBOLS: tuple[str, ...] = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
    "AVAXUSDT", "LINKUSDT", "DOTUSDT", "POLUSDT", "LTCUSDT", "BCHUSDT",
    "NEARUSDT", "UNIUSDT", "ATOMUSDT", "ETCUSDT", "FILUSDT", "ICPUSDT",
    "TRXUSDT", "ARBUSDT", "OPUSDT", "APTUSDT", "SUIUSDT", "TONUSDT",
    "INJUSDT",
)

DEFAULT_WINDOW_SECS_LIQ: int = 86400  # 24h；對齊 PA prompt §6.3 expected baseline


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="67_liquidation_pulse_freshness",
        description=(
            "[67] liquidation_pulse_freshness — topic freshness + row volume + "
            "symbol coverage + parse guard (PA §6.3 #3)"
        ),
    )
    parser.add_argument(
        "--window-secs",
        type=int,
        default=DEFAULT_WINDOW_SECS_LIQ,
        help=(
            f"Observation window in seconds (default {DEFAULT_WINDOW_SECS_LIQ}s = 24h)"
        ),
    )
    parser.add_argument(
        "--pass-lower-per-hour",
        type=float,
        default=30.0,
        help=(
            "Row volume PASS threshold per hour (default 30; 24h × 30 = 720). "
            "Linux empirical 2026-05-18 24h baseline ~6000 row / cohort sym."
        ),
    )
    parser.add_argument(
        "--warn-freshness-secs",
        type=float,
        default=60.0,
        help="Latest row age WARN threshold (default 60s).",
    )
    parser.add_argument(
        "--fail-freshness-secs",
        type=float,
        default=300.0,
        help="Latest row age FAIL threshold (default 300s = 5min).",
    )
    parser.add_argument(
        "--warn-coverage",
        type=float,
        default=0.80,
        help="Symbol coverage WARN threshold (default 0.80 = 20/25 sym).",
    )
    parser.add_argument(
        "--fail-coverage",
        type=float,
        default=0.50,
        help="Symbol coverage FAIL threshold (default 0.50 = 12/25 sym).",
    )
    parser.add_argument(
        "--write-file",
        type=str,
        default=None,
        help="Optional JSON artifact write path.",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Human-readable text output instead of JSON.",
    )
    return parser.parse_args()


def _freshness_verdict(
    latest_age_secs: float | None,
    warn_secs: float,
    fail_secs: float,
) -> tuple[str, str]:
    """Topic freshness 判定。

    為什麼 None → INSUFFICIENT_SAMPLE：0 row in window 意味著 WS 沒 push 或
    cohort 全部過濾，本身就是異常但無 row 無法計算 age；交由 row_volume
    判定 FAIL，這裡 fail-back 到 INSUFFICIENT_SAMPLE 避免雙計。
    """
    if latest_age_secs is None:
        return (VERDICT_INSUFFICIENT_SAMPLE, "no rows in window")
    if latest_age_secs > fail_secs:
        return (VERDICT_FAIL, f"latest_age={latest_age_secs:.0f}s > fail={fail_secs}s")
    if latest_age_secs > warn_secs:
        return (VERDICT_WARN, f"latest_age={latest_age_secs:.0f}s > warn={warn_secs}s")
    return (VERDICT_PASS, f"latest_age={latest_age_secs:.0f}s")


def _volume_verdict(
    n_rows: int,
    window_secs: int,
    pass_lower_per_hour: float,
) -> tuple[str, str]:
    """Row volume 判定（per-hour rate ladder）。

    為什麼 per-hour 而非 absolute：window 可變（CLI --window-secs），用
    per-hour rate normalize；24h vs 8h 共用同一 pass_lower。
    """
    if n_rows < 1:
        return (VERDICT_FAIL, f"n_rows={n_rows} (zero rows in window)")
    hours = window_secs / 3600.0
    pass_lower_total = pass_lower_per_hour * hours
    # WARN 折半 — 顯著低於 baseline 但非完全空
    warn_lower_total = pass_lower_total * 0.5
    if n_rows < warn_lower_total:
        return (
            VERDICT_FAIL,
            f"n_rows={n_rows} < warn_lower={warn_lower_total:.0f} "
            f"(per_hour={pass_lower_per_hour})",
        )
    if n_rows < pass_lower_total:
        return (
            VERDICT_WARN,
            f"n_rows={n_rows} < pass_lower={pass_lower_total:.0f} "
            f"(per_hour={pass_lower_per_hour})",
        )
    return (
        VERDICT_PASS,
        f"n_rows={n_rows} >= pass_lower={pass_lower_total:.0f}",
    )


def _coverage_verdict(
    cohort_observed: int,
    cohort_total: int,
    warn_ratio: float,
    fail_ratio: float,
) -> tuple[str, str, float]:
    """Symbol coverage 判定。

    為什麼 cohort_observed 而非 raw distinct：non-cohort symbol（BSBUSDT /
    HYPEUSDT 等）也會被 Bybit 推到 market.liquidations，但 aggregator 會
    silent ignore；coverage 應以 25-sym cohort 為分母。
    """
    if cohort_total <= 0:
        return (VERDICT_INSUFFICIENT_SAMPLE, "cohort empty", 0.0)
    ratio = cohort_observed / cohort_total
    if ratio < fail_ratio:
        return (
            VERDICT_FAIL,
            f"coverage={ratio:.2%} < fail={fail_ratio:.0%} "
            f"({cohort_observed}/{cohort_total})",
            ratio,
        )
    if ratio < warn_ratio:
        return (
            VERDICT_WARN,
            f"coverage={ratio:.2%} < warn={warn_ratio:.0%} "
            f"({cohort_observed}/{cohort_total})",
            ratio,
        )
    return (
        VERDICT_PASS,
        f"coverage={ratio:.2%} ({cohort_observed}/{cohort_total})",
        ratio,
    )


def _parse_guard_verdict(
    buy_count: int,
    sell_count: int,
    non_finite_count: int,
    n_rows: int,
) -> tuple[str, str]:
    """Parse guard 判定（V095 CHECK constraint 已強制 side ∈ {Buy, Sell}）。

    為什麼仍要 check：V095 是 NOT VALID（不掃描歷史 row），且 parser silent
    degradation 可能寫只 Buy 不見 Sell；qty/price 是 real 型，理論不該 NaN
    但 V005 baseline 沒 finite constraint，這裡多一道保護。

    本 check 不算 ratio 而是 enum coverage + finite count：
      - side enum 兩值都需 ≥ 1 出現（否則 parser 半邊瞎）
      - qty <= 0 或 price <= 0 視為 non-finite（real 型 NaN/inf 也 ≤ 0
        comparison 為 false，所以 SQL 用 qty > 0 AND price > 0 取補集）
    """
    if n_rows < 1:
        return (VERDICT_INSUFFICIENT_SAMPLE, "no rows to parse-guard")
    issues: list[str] = []
    if buy_count == 0:
        issues.append("Buy_side_absent")
    if sell_count == 0:
        issues.append("Sell_side_absent")
    if non_finite_count > 0:
        issues.append(f"non_finite_qty_or_price={non_finite_count}")
    if issues:
        return (VERDICT_FAIL, f"parse guard issues: {issues}")
    return (
        VERDICT_PASS,
        f"side enum complete (Buy={buy_count}, Sell={sell_count}); "
        f"all qty/price > 0",
    )


def run(
    cur,
    window_secs: int,
    cohort: tuple[str, ...],
    pass_lower_per_hour: float,
    warn_freshness_secs: float,
    fail_freshness_secs: float,
    warn_coverage: float,
    fail_coverage: float,
) -> dict:
    """執行 4 維 SQL probe + 合併 verdict。"""
    # ─────────────────────────────────────────────────────────────────────
    # Query 1: window 內整體 row volume + latest_age + buy/sell + non-finite
    # ─────────────────────────────────────────────────────────────────────
    cur.execute(
        """
        SELECT
            COUNT(*)::int AS n_rows,
            EXTRACT(EPOCH FROM (NOW() - MAX(ts)))::float AS latest_age_secs,
            COUNT(*) FILTER (WHERE side = 'Buy')::int AS buy_count,
            COUNT(*) FILTER (WHERE side = 'Sell')::int AS sell_count,
            COUNT(*) FILTER (WHERE NOT (qty > 0 AND price > 0))::int AS non_finite_count
        FROM market.liquidations
        WHERE ts > NOW() - (%s::int * INTERVAL '1 second')
        """,
        (window_secs,),
    )
    row = cur.fetchone() or (0, None, 0, 0, 0)
    n_rows = int(row[0] or 0)
    latest_age_secs = float(row[1]) if row[1] is not None else None
    buy_count = int(row[2] or 0)
    sell_count = int(row[3] or 0)
    non_finite_count = int(row[4] or 0)

    # ─────────────────────────────────────────────────────────────────────
    # Query 2: cohort 內 distinct symbol coverage
    # ─────────────────────────────────────────────────────────────────────
    cur.execute(
        """
        SELECT DISTINCT symbol
        FROM market.liquidations
        WHERE ts > NOW() - (%s::int * INTERVAL '1 second')
          AND symbol = ANY(%s::text[])
        """,
        (window_secs, list(cohort)),
    )
    observed_cohort_symbols = {r[0] for r in (cur.fetchall() or [])}
    cohort_observed = len(observed_cohort_symbols)
    cohort_total = len(cohort)
    missing_cohort = sorted(set(cohort) - observed_cohort_symbols)

    # ─────────────────────────────────────────────────────────────────────
    # Dimension verdicts
    # ─────────────────────────────────────────────────────────────────────
    fresh_verdict, fresh_note = _freshness_verdict(
        latest_age_secs, warn_freshness_secs, fail_freshness_secs
    )
    vol_verdict, vol_note = _volume_verdict(
        n_rows, window_secs, pass_lower_per_hour
    )
    cov_verdict, cov_note, cov_ratio = _coverage_verdict(
        cohort_observed, cohort_total, warn_coverage, fail_coverage
    )
    parse_verdict, parse_note = _parse_guard_verdict(
        buy_count, sell_count, non_finite_count, n_rows
    )

    overall_verdict = VERDICT_PASS
    for v in (fresh_verdict, vol_verdict, cov_verdict, parse_verdict):
        overall_verdict = severity_max(overall_verdict, v)

    return {
        "metric": "liquidation_pulse_freshness",
        "check_id": "[67]",
        "spec": (
            "PA decomposition 2026-05-18 §6.3 acceptance #3 / "
            "W-AUDIT-8a C1-LIQ-WRITER"
        ),
        "window_secs": window_secs,
        "thresholds": {
            "pass_lower_per_hour": pass_lower_per_hour,
            "warn_freshness_secs": warn_freshness_secs,
            "fail_freshness_secs": fail_freshness_secs,
            "warn_coverage": warn_coverage,
            "fail_coverage": fail_coverage,
        },
        "cohort_size": cohort_total,
        "n_rows": n_rows,
        "latest_age_secs": (
            round(latest_age_secs, 2) if latest_age_secs is not None else None
        ),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "non_finite_count": non_finite_count,
        "cohort_observed": cohort_observed,
        "cohort_coverage_pct": round(cov_ratio * 100, 2),
        "missing_cohort_symbols": missing_cohort,
        "dimensions": {
            "freshness": {"verdict": fresh_verdict, "note": fresh_note},
            "row_volume": {"verdict": vol_verdict, "note": vol_note},
            "symbol_coverage": {"verdict": cov_verdict, "note": cov_note},
            "parse_guard": {"verdict": parse_verdict, "note": parse_note},
        },
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
                cohort=COHORT_SYMBOLS,
                pass_lower_per_hour=args.pass_lower_per_hour,
                warn_freshness_secs=args.warn_freshness_secs,
                fail_freshness_secs=args.fail_freshness_secs,
                warn_coverage=args.warn_coverage,
                fail_coverage=args.fail_coverage,
            )
    finally:
        conn.close()

    emit_result(result, write_file=args.write_file, text_mode=args.text)

    if result["verdict"] in (VERDICT_FAIL, VERDICT_WARN):
        return EXIT_FAIL
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
