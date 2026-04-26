#!/usr/bin/env python3
"""exit_features_summary — read-only `learning.exit_features` distribution + sample-sufficiency report.
exit_features_summary — 唯讀 `learning.exit_features` 分布 + 樣本充足度報告。

MODULE_NOTE (EN): Wave 3 EDGE-P1b T2 helper. Pure-read companion to
`exit_threshold_calibrator.py` (T1) — answers operator questions:

  * How many rows of `learning.exit_features` exist per-strategy?
  * What is the cohort fraction (last 24h / 7d / 14d)?
  * Has each strategy reached the calibrator sample threshold?
  * What is the distribution shape (mean / std / quartiles / p90 / p99) of
    each of the 7 Track-P feature dimensions, per-strategy?

Use this BEFORE running `exit_threshold_calibrator --apply` so operator
sees whether the cohort is healthy enough for a percentile bind. Pure
read-only — no PG writes, no business-logic mutation, no IPC.

The 7 dims are exactly as in V999__exit_features.sql:33-41:
    est_net_bps / peak_pnl_pct / atr_pct / giveback_atr_norm /
    time_since_peak_ms / price_roc_short / entry_age_secs

Per RFC §3, this tool is the operator-review hook before approving any
ExitConfig bind. Three sample-sufficiency tiers reported:
    ≥200   = calibrator default min (per-strategy bind viable)
    ≥500   = comfortable bootstrap CI width
    ≥1000  = strong evidence

MODULE_NOTE (中): Wave 3 EDGE-P1b T2 helper。`exit_threshold_calibrator.py`
（T1）的純唯讀夥伴，回答 operator 問題：
  * `learning.exit_features` per-strategy 累積多少 rows？
  * cohort 占比（最近 24h / 7d / 14d）多少？
  * 各策略達到 calibrator 樣本門檻了嗎？
  * 7 維 Track-P 特徵的分布形態（mean / std / 四分位 / p90 / p99）per-strategy？

`--apply` 前先跑此工具，operator 看 cohort 是否健康才考慮 bind。純唯讀 — 不寫
PG / 不動業務邏輯 / 無 IPC。7 維與 V999__exit_features.sql:33-41 對應。

依 RFC §3，本工具為任何 ExitConfig bind 前的 operator review hook。三檔
樣本充足度：≥200（calibrator 預設）/ ≥500（bootstrap CI 寬度舒適）/ ≥1000（強證據）。

Usage:
  OPENCLAW_DATABASE_URL=postgresql://... \\
    python3 helper_scripts/research/exit_features_summary.py \\
      [--engine-mode demo] [--strategies grid_trading,ma_crossover] \\
      [--lookback-days 14] [--output-format markdown]
  python3 ... --smoke-test          # SQL syntax dry-run, no DB needed

Exit codes:
  0 = success
  1 = invalid args / output write error
  2 = DB connection error
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from typing import Any

# 7 feature dims as in V999__exit_features.sql:33-41.
# 7 維（與 V999__exit_features.sql:33-41 對應）。
FEATURE_DIMS: tuple[str, ...] = (
    "est_net_bps",
    "peak_pnl_pct",
    "atr_pct",
    "giveback_atr_norm",
    "time_since_peak_ms",
    "price_roc_short",
    "entry_age_secs",
)

# Sample-sufficiency tiers per RFC §3.
# RFC §3 樣本充足度三檔。
TIER_LABELS: tuple[tuple[int, str], ...] = (
    (200, "calibrator-min"),
    (500, "ci-comfortable"),
    (1000, "strong-evidence"),
)


# ─────────────────────────────────────────────────────────────────────────
# SQL — pure read-only.
# SQL — 純唯讀。
# ─────────────────────────────────────────────────────────────────────────
#
# Notes / 備註：
#   - %s placeholder style (psycopg2 default).
#   - Distribution rows fetched as raw values; mean/std/quartile computed in
#     Python (avoids relying on PG percentile_disc / percentile_cont which
#     differ in ties and require ORDER BY GROUPING; Python is simpler + tested).
#   - cohort_fraction queries use UTC arithmetic via now() — TimescaleDB chunk
#     pruning still applies because `ts` is the partition key.
#   - profit-cohort filter (realized_net_bps > 0) is OPTIONAL — this summary
#     gives BOTH the full cohort and the profit-only cohort so operator can
#     see what the calibrator's profit-gate would actually retain.

DIST_ROWS_SQL = """
SELECT
    strategy_name,
    est_net_bps,
    peak_pnl_pct,
    atr_pct,
    giveback_atr_norm,
    time_since_peak_ms,
    price_roc_short,
    entry_age_secs,
    realized_net_bps
FROM learning.exit_features
WHERE engine_mode    = %s
  AND ts > now() - (%s || ' days')::interval
  {strategy_filter}
ORDER BY strategy_name ASC, ts ASC
"""

# strategies filter sub-clause; built only when --strategies given.
# strategies 過濾子句；--strategies 給定時才加。
STRATEGY_FILTER_TEMPLATE = "AND strategy_name = ANY(%s)"

# Cohort-fraction count queries (24h / 7d / 14d) — separate calls so
# operator can see how cohort size grows by window.
# cohort 占比計數查詢（24h / 7d / 14d 分開呼叫）。
COHORT_COUNT_SQL = """
SELECT strategy_name, COUNT(*) AS n
FROM learning.exit_features
WHERE engine_mode = %s
  AND ts > now() - (%s || ' hours')::interval
  {strategy_filter}
GROUP BY strategy_name
ORDER BY strategy_name ASC
"""


# ─────────────────────────────────────────────────────────────────────────
# DB helpers.
# DB helpers。
# ─────────────────────────────────────────────────────────────────────────


def _build_dsn() -> str:
    """Build PG DSN from env. 從 env 構造 PG DSN。"""
    return (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )


def _open_conn():
    """Lazy import + open PG connection. 延遲載入並開 PG 連線。"""
    import psycopg2  # type: ignore  # lazy: avoid import-time DB hard-dep

    dsn = _build_dsn()
    return psycopg2.connect(dsn)


# ─────────────────────────────────────────────────────────────────────────
# Pure-Python distribution stats (testable without DB or NumPy).
# 純 Python 分布統計（可不連 DB / 不裝 NumPy 測試）。
# ─────────────────────────────────────────────────────────────────────────


def filter_finite(values: list[float | None]) -> list[float]:
    """Drop None / NaN / Inf entries.
    丟棄 None / NaN / Inf。
    """
    out: list[float] = []
    for v in values:
        if v is None:
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(x):
            continue
        out.append(x)
    return out


def percentile_linear(sorted_values: list[float], pct: float) -> float | None:
    """Linear-interpolation percentile (NumPy default `linear`); list must
    be ascending-sorted. Empty → None.
    線性插值百分位（NumPy 預設 `linear`），輸入需升序；空 list → None。
    """
    if not sorted_values:
        return None
    if pct <= 0:
        return float(sorted_values[0])
    if pct >= 100:
        return float(sorted_values[-1])
    n = len(sorted_values)
    rank = (pct / 100.0) * (n - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return float(sorted_values[low])
    frac = rank - low
    return float(sorted_values[low] + (sorted_values[high] - sorted_values[low]) * frac)


def describe(values: list[float | None]) -> dict[str, float | int | None]:
    """Compute summary stats: count / mean / std (sample, ddof=1) / min /
    P25 / P50 / P75 / P90 / P99 / max.

    Returns dict with int `count` and floats for the rest; missing fields
    None when count too small (e.g. std needs n>=2; percentiles need n>=1).

    計算分布統計（count / mean / std (ddof=1) / min / P25 / P50 / P75 /
    P90 / P99 / max）；count 為 int，其餘 float；不足樣本時填 None。
    """
    finite = filter_finite(values)
    n = len(finite)
    out: dict[str, float | int | None] = {
        "count": n,
        "mean": None,
        "std": None,
        "min": None,
        "p25": None,
        "p50": None,
        "p75": None,
        "p90": None,
        "p99": None,
        "max": None,
    }
    if n == 0:
        return out
    finite.sort()
    out["min"] = finite[0]
    out["max"] = finite[-1]
    out["mean"] = sum(finite) / n
    if n >= 2:
        m = out["mean"]
        # Sample std (ddof=1) — matches numpy.std(values, ddof=1).
        # 樣本 std (ddof=1) — 與 numpy.std(ddof=1) 一致。
        var = sum((x - m) ** 2 for x in finite) / (n - 1)
        out["std"] = math.sqrt(var)
    out["p25"] = percentile_linear(finite, 25.0)
    out["p50"] = percentile_linear(finite, 50.0)
    out["p75"] = percentile_linear(finite, 75.0)
    out["p90"] = percentile_linear(finite, 90.0)
    out["p99"] = percentile_linear(finite, 99.0)
    return out


def stratify_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group rows by strategy_name (exact match — no prefix).
    依 strategy_name 精確分組（不 prefix）。
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        s = row.get("strategy_name")
        if not s:
            continue
        out.setdefault(str(s), []).append(row)
    return out


def compute_per_strategy_summary(
    rows_by_strategy: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """For each strategy, compute distribution stats over the 7 dims, plus a
    profit-cohort variant (realized_net_bps > 0) for comparison.

    Returns:
      {
        <strategy>: {
          "row_count_full": int,
          "row_count_profit": int,
          "profit_cohort_fraction": float | None,
          "tier_label": "strong-evidence" | "ci-comfortable" |
                        "calibrator-min" | "below-min",
          "dims_full":   {dim: stats_dict},
          "dims_profit": {dim: stats_dict},
        }, ...
      }

    計算 per-strategy 7 維分布（full + profit-only），profit cohort 比例 +
    sample sufficiency tier 標籤（strong-evidence / ci-comfortable /
    calibrator-min / below-min）。
    """
    out: dict[str, dict[str, Any]] = {}
    for strategy, rows in rows_by_strategy.items():
        n_full = len(rows)
        # profit cohort = realized_net_bps > 0
        # profit cohort = realized_net_bps > 0
        profit_rows = [
            r for r in rows
            if r.get("realized_net_bps") is not None
            and (r.get("realized_net_bps") or 0.0) > 0
        ]
        n_profit = len(profit_rows)
        cohort_fraction = (n_profit / n_full) if n_full > 0 else None

        # Tier (highest applicable) on profit cohort (calibrator inputs).
        # tier 用 profit cohort 行數判定（calibrator 實際輸入）。
        tier_label = "below-min"
        for threshold, label in TIER_LABELS:
            if n_profit >= threshold:
                tier_label = label

        dims_full: dict[str, Any] = {}
        dims_profit: dict[str, Any] = {}
        for dim in FEATURE_DIMS:
            dims_full[dim] = describe([r.get(dim) for r in rows])
            dims_profit[dim] = describe([r.get(dim) for r in profit_rows])
        out[strategy] = {
            "row_count_full": n_full,
            "row_count_profit": n_profit,
            "profit_cohort_fraction": cohort_fraction,
            "tier_label": tier_label,
            "dims_full": dims_full,
            "dims_profit": dims_profit,
        }
    return out


# ─────────────────────────────────────────────────────────────────────────
# Output rendering.
# 輸出渲染。
# ─────────────────────────────────────────────────────────────────────────


def _fmt_num(v: float | int | None) -> str:
    """Compact human-readable formatter for stats values.
    人類可讀的緊湊數字格式（自動科學記數）。
    """
    if v is None:
        return "—"
    if isinstance(v, int):
        return str(v)
    if v == 0:
        return "0"
    av = abs(v)
    if av >= 1e6 or av < 1e-3:
        return f"{v:.3e}"
    if av >= 100:
        return f"{v:.1f}"
    return f"{v:.4f}"


def render_markdown(
    summary: dict[str, dict[str, Any]],
    cohort_24h: dict[str, int],
    cohort_7d: dict[str, int],
    cohort_14d: dict[str, int],
    args: argparse.Namespace,
) -> str:
    """Render markdown report (operator-readable).
    渲染 markdown 報告（給 operator 看）。
    """
    lines: list[str] = []
    ts_now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines.append(f"# `learning.exit_features` Summary · {ts_now}")
    lines.append("")
    lines.append(f"- engine_mode: `{args.engine_mode}`")
    lines.append(f"- strategies filter: `{args.strategies or 'ALL'}`")
    lines.append(f"- lookback_days: {args.lookback_days}")
    lines.append("")

    # Cohort fraction summary.
    # cohort 占比摘要。
    lines.append("## Cohort fraction (per strategy)")
    lines.append("")
    lines.append("| strategy | last 24h | last 7d | last 14d |")
    lines.append("|---|---|---|---|")
    all_strats = sorted(
        set(cohort_24h.keys()) | set(cohort_7d.keys()) | set(cohort_14d.keys())
    )
    for s in all_strats:
        lines.append(
            f"| `{s}` | "
            f"{cohort_24h.get(s, 0)} | "
            f"{cohort_7d.get(s, 0)} | "
            f"{cohort_14d.get(s, 0)} |"
        )
    if not all_strats:
        lines.append("| _(no rows in any window)_ | 0 | 0 | 0 |")
    lines.append("")

    # Sample-sufficiency table (tier label per strategy).
    # 樣本充足度表（per-strategy tier 標籤）。
    lines.append("## Sample sufficiency (profit cohort, lookback window)")
    lines.append("")
    lines.append(
        "| strategy | full count | profit count | profit fraction | tier |"
    )
    lines.append("|---|---|---|---|---|")
    if summary:
        for strategy, det in sorted(summary.items()):
            cohort_frac = det.get("profit_cohort_fraction")
            cohort_pct = (
                f"{cohort_frac * 100:.1f}%" if cohort_frac is not None else "—"
            )
            lines.append(
                f"| `{strategy}` | "
                f"{det['row_count_full']} | "
                f"{det['row_count_profit']} | "
                f"{cohort_pct} | "
                f"`{det['tier_label']}` |"
            )
    else:
        lines.append("| _(no rows in lookback window)_ | 0 | 0 | — | `below-min` |")
    lines.append("")
    lines.append(
        "Tiers: `strong-evidence` (≥1000) / `ci-comfortable` (≥500) / "
        "`calibrator-min` (≥200) / `below-min` (<200)."
    )
    lines.append("")

    # Per-strategy distribution detail.
    # per-strategy 分布細節。
    lines.append("## Per-Strategy Distribution Detail")
    lines.append("")
    if not summary:
        lines.append("_(no rows in lookback window)_")
        lines.append("")
        return "\n".join(lines) + "\n"

    for strategy, det in sorted(summary.items()):
        lines.append(f"### `{strategy}`")
        lines.append("")
        lines.append(
            f"- full cohort rows: **{det['row_count_full']}** | "
            f"profit cohort rows: **{det['row_count_profit']}** | "
            f"tier: `{det['tier_label']}`"
        )
        lines.append("")

        # full cohort table
        # full cohort 表
        lines.append("**Full cohort (all `realized_net_bps`):**")
        lines.append("")
        lines.append(
            "| dim | count | mean | std | min | p25 | p50 | p75 | p90 | p99 | max |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for dim in FEATURE_DIMS:
            stats = det["dims_full"].get(dim, {})
            lines.append(
                f"| `{dim}` | "
                f"{stats.get('count', 0)} | "
                f"{_fmt_num(stats.get('mean'))} | "
                f"{_fmt_num(stats.get('std'))} | "
                f"{_fmt_num(stats.get('min'))} | "
                f"{_fmt_num(stats.get('p25'))} | "
                f"{_fmt_num(stats.get('p50'))} | "
                f"{_fmt_num(stats.get('p75'))} | "
                f"{_fmt_num(stats.get('p90'))} | "
                f"{_fmt_num(stats.get('p99'))} | "
                f"{_fmt_num(stats.get('max'))} |"
            )
        lines.append("")

        # profit cohort table (omit if empty).
        # profit cohort 表（空時略）。
        if det["row_count_profit"] > 0:
            lines.append("**Profit cohort (`realized_net_bps > 0`):**")
            lines.append("")
            lines.append(
                "| dim | count | mean | std | min | p25 | p50 | p75 | p90 | p99 | max |"
            )
            lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
            for dim in FEATURE_DIMS:
                stats = det["dims_profit"].get(dim, {})
                lines.append(
                    f"| `{dim}` | "
                    f"{stats.get('count', 0)} | "
                    f"{_fmt_num(stats.get('mean'))} | "
                    f"{_fmt_num(stats.get('std'))} | "
                    f"{_fmt_num(stats.get('min'))} | "
                    f"{_fmt_num(stats.get('p25'))} | "
                    f"{_fmt_num(stats.get('p50'))} | "
                    f"{_fmt_num(stats.get('p75'))} | "
                    f"{_fmt_num(stats.get('p90'))} | "
                    f"{_fmt_num(stats.get('p99'))} | "
                    f"{_fmt_num(stats.get('max'))} |"
                )
            lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- Run `exit_threshold_calibrator.py` (T1) AFTER reviewing this summary "
        "if `tier` ≥ `calibrator-min` and profit cohort fraction is reasonable "
        "(RFC §3 recommends ≥30%)."
    )
    lines.append(
        "- Low profit fraction (<30%) = strategy structurally bleeds; bind would "
        "lock in losing parameters."
    )
    return "\n".join(lines) + "\n"


def render_json(
    summary: dict[str, dict[str, Any]],
    cohort_24h: dict[str, int],
    cohort_7d: dict[str, int],
    cohort_14d: dict[str, int],
    args: argparse.Namespace,
) -> str:
    """Render JSON envelope (machine-readable).
    渲染 JSON 信封（機器可讀）。
    """
    envelope = {
        "schema_version": "edge_p1b.summary.v1",
        "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "params": {
            "engine_mode": args.engine_mode,
            "strategies_filter": args.strategies or None,
            "lookback_days": args.lookback_days,
        },
        "cohort_counts": {
            "last_24h": cohort_24h,
            "last_7d": cohort_7d,
            "last_14d": cohort_14d,
        },
        "per_strategy": summary,
        "tiers": {label: threshold for threshold, label in TIER_LABELS},
    }
    return json.dumps(envelope, indent=2, ensure_ascii=False, default=str) + "\n"


# ─────────────────────────────────────────────────────────────────────────
# CLI plumbing + main.
# CLI 接線 + main。
# ─────────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments per PM spec.
    依 PM 派發規格解析 CLI 參數。
    """
    parser = argparse.ArgumentParser(
        prog="exit_features_summary",
        description=(
            "EDGE-P1b T2: Summarize learning.exit_features distribution + "
            "sample sufficiency per-strategy. Read-only operator review hook."
        ),
    )
    parser.add_argument(
        "--engine-mode",
        default="demo",
        choices=["demo", "live_demo", "paper", "live"],
        help="engine_mode filter on learning.exit_features (default demo)",
    )
    parser.add_argument(
        "--strategies",
        default=None,
        help="comma-separated strategy_name list (default ALL); exact match only",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=14,
        help="lookback window in days for distribution + sample count (default 14)",
    )
    parser.add_argument(
        "--output-format",
        default="markdown",
        choices=["markdown", "json"],
        help="output format (default markdown)",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help="optional output file path (default stdout)",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="run SQL syntax / arg validation dry-run; no PG connection",
    )
    return parser.parse_args(argv)


def _validate_args(args: argparse.Namespace) -> list[str] | None:
    """Validate CLI inputs. Returns strategies_filter list or None.
    驗證 CLI 輸入；回傳 strategies_filter list 或 None。
    """
    if args.lookback_days <= 0:
        raise SystemExit("--lookback-days must be > 0")
    strats = None
    if args.strategies:
        strats = [s.strip() for s in args.strategies.split(",") if s.strip()]
        if not strats:
            raise SystemExit("--strategies parsed empty after split")
    return strats


def _build_dist_query(
    args: argparse.Namespace,
    strategies_filter: list[str] | None,
) -> tuple[str, list[Any]]:
    """Build (DIST_ROWS_SQL, args).
    建構 DIST_ROWS_SQL + args。
    """
    if strategies_filter:
        sql = DIST_ROWS_SQL.format(strategy_filter=STRATEGY_FILTER_TEMPLATE)
        sql_args: list[Any] = [
            args.engine_mode,
            args.lookback_days,
            strategies_filter,
        ]
    else:
        sql = DIST_ROWS_SQL.format(strategy_filter="")
        sql_args = [args.engine_mode, args.lookback_days]
    return sql, sql_args


def _build_cohort_query(
    args: argparse.Namespace,
    strategies_filter: list[str] | None,
    hours: int,
) -> tuple[str, list[Any]]:
    """Build cohort-count SQL for a specific hour-window.
    建構特定小時窗口的 cohort-count SQL。
    """
    if strategies_filter:
        sql = COHORT_COUNT_SQL.format(strategy_filter=STRATEGY_FILTER_TEMPLATE)
        sql_args: list[Any] = [args.engine_mode, hours, strategies_filter]
    else:
        sql = COHORT_COUNT_SQL.format(strategy_filter="")
        sql_args = [args.engine_mode, hours]
    return sql, sql_args


def _smoke_test(args: argparse.Namespace) -> int:
    """Validate SQL templates + args without DB. 0 = pass, 1 = fail.
    驗證 SQL 模板 + args（不需 DB）；通過回 0、失敗回 1。
    """
    log = logging.getLogger("summary.smoke")
    strats = _validate_args(args)

    # Validate dist SQL.
    # 驗 dist SQL。
    sql, sql_args = _build_dist_query(args, strats)
    pc = sql.count("%s")
    if pc != len(sql_args):
        log.error(
            "smoke-test FAIL: DIST_ROWS_SQL placeholder count %s != args count %s",
            pc,
            len(sql_args),
        )
        return 1

    # Validate cohort SQL.
    # 驗 cohort SQL。
    for hours in (24, 7 * 24, 14 * 24):
        csql, cargs = _build_cohort_query(args, strats, hours)
        cpc = csql.count("%s")
        if cpc != len(cargs):
            log.error(
                "smoke-test FAIL: COHORT_COUNT_SQL placeholder count %s != args %s "
                "(hours=%d)",
                cpc,
                len(cargs),
                hours,
            )
            return 1

    # Synthetic distribution smoke.
    # 合成分布煙霧測試。
    fake_rows = [
        {
            "strategy_name": "grid_trading",
            "est_net_bps": 1.0 * i,
            "peak_pnl_pct": 0.001 * i,
            "atr_pct": 0.05,
            "giveback_atr_norm": 0.5,
            "time_since_peak_ms": 100 * i,
            "price_roc_short": 0.0001 * i,
            "entry_age_secs": 30.0 * i,
            "realized_net_bps": (1.0 if i % 2 == 0 else -1.0),
        }
        for i in range(1, 11)
    ]
    rows_by_strategy = stratify_rows(fake_rows)
    summary = compute_per_strategy_summary(rows_by_strategy)
    grid = summary.get("grid_trading", {})
    if grid.get("row_count_full") != 10:
        log.error(
            "smoke-test FAIL: synthetic 10-row case not yielding 10 (got %s)",
            grid.get("row_count_full"),
        )
        return 1
    # 5 of 10 rows have realized_net_bps > 0.
    # 10 行中 5 行 realized_net_bps > 0。
    if grid.get("row_count_profit") != 5:
        log.error(
            "smoke-test FAIL: profit cohort count expected 5, got %s",
            grid.get("row_count_profit"),
        )
        return 1
    if grid.get("tier_label") != "below-min":
        log.error(
            "smoke-test FAIL: tier_label expected 'below-min' for n=5, got %s",
            grid.get("tier_label"),
        )
        return 1
    # Verify describe() returned mean/std/p50.
    # 驗 describe() 含 mean/std/p50。
    est_net_full = grid["dims_full"]["est_net_bps"]
    if est_net_full.get("count") != 10:
        log.error("smoke-test FAIL: dims_full count mismatch")
        return 1
    if est_net_full.get("mean") is None:
        log.error("smoke-test FAIL: dims_full mean is None")
        return 1

    log.info(
        "smoke-test PASS: dist placeholder count=%d args=%d, "
        "cohort 3 windows OK, synthetic 10-row → grid_trading "
        "below-min/profit=5/full=10",
        pc,
        len(sql_args),
    )
    return 0


def _fetch_cohort_counts(
    cur,
    args: argparse.Namespace,
    strategies_filter: list[str] | None,
    hours: int,
) -> dict[str, int]:
    """Fetch cohort row counts grouped by strategy_name for a given hour window.
    取得指定小時窗口的 per-strategy cohort 計數。
    """
    sql, sql_args = _build_cohort_query(args, strategies_filter, hours)
    cur.execute(sql, sql_args)
    return {row[0]: int(row[1] or 0) for row in cur.fetchall()}


def main(argv: list[str] | None = None) -> int:
    """Main entrypoint.
    主入口。
    """
    # stderr logging keeps stdout (markdown/json) clean for pipes.
    # stderr 走 log；stdout 留乾淨給 markdown/json 管道。
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("summary")
    args = parse_args(argv)

    if args.smoke_test:
        return _smoke_test(args)

    strats = _validate_args(args)

    try:
        conn = _open_conn()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return 2

    try:
        cur = conn.cursor()
        # Distribution rows.
        # 分布行。
        sql, sql_args = _build_dist_query(args, strats)
        try:
            cur.execute(sql, sql_args)
        except Exception as e:
            log.error("DIST_ROWS_SQL execute failed: %s", e)
            return 2
        col_names = [c.name for c in cur.description] if cur.description else []
        raw_rows = cur.fetchall()
        rows = [dict(zip(col_names, r, strict=False)) for r in raw_rows]

        # Cohort counts (24h / 7d / 14d).
        # cohort 計數（24h / 7d / 14d）。
        cohort_24h = _fetch_cohort_counts(cur, args, strats, 24)
        cohort_7d = _fetch_cohort_counts(cur, args, strats, 7 * 24)
        cohort_14d = _fetch_cohort_counts(cur, args, strats, 14 * 24)

        log.info(
            "fetched %d distribution rows + cohort counts "
            "(24h=%d total / 7d=%d / 14d=%d)",
            len(rows),
            sum(cohort_24h.values()),
            sum(cohort_7d.values()),
            sum(cohort_14d.values()),
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass

    rows_by_strategy = stratify_rows(rows)
    summary = compute_per_strategy_summary(rows_by_strategy)

    if args.output_format == "markdown":
        out_text = render_markdown(summary, cohort_24h, cohort_7d, cohort_14d, args)
    elif args.output_format == "json":
        out_text = render_json(summary, cohort_24h, cohort_7d, cohort_14d, args)
    else:
        log.error("unknown output-format: %s", args.output_format)
        return 1

    if args.output_file:
        try:
            with open(args.output_file, "w", encoding="utf-8") as f:
                f.write(out_text)
            log.info("wrote output to %s", args.output_file)
        except OSError as e:
            log.error("output file write failed: %s", e)
            return 1
    else:
        sys.stdout.write(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
