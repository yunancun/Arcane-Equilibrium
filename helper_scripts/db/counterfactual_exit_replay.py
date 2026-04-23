#!/usr/bin/env python3
"""Counterfactual exit replay — "lock profit at peak - k × ATR" vs realised exit.
反事實退場回放 — 「peak - k × ATR 鎖利」對比實際退場 net PnL。

MODULE_NOTE (EN): EDGE-DIAG-1 #3 (TODO.md §P1, 2026-04-23). Read-only SELECT over
the last N days of `learning.exit_features` to answer: "if Track P phys_lock had
actually fired in the current edge environment, would it have improved realised
net PnL vs the realised exit?" One-row-per-exit table (writer: `exit_feature_writer.rs`,
PK `(context_id, ts)`), realised `realized_net_bps` on same row as close-time
snapshot of `peak_pnl_pct` / `giveback_atr_norm` / `atr_pct`. Outputs stdout table
grouped by (engine_mode, strategy_name, symbol) + JSON at
`$OPENCLAW_DATA_DIR/audit/` (latest + dated siblings per CLAUDE.md §七).

**v1 SCOPE CAVEAT (read before interpreting output)**:
v1 simulates only Gate 4 (giveback threshold) with a LINEAR approximation k=0.3.
The v2 production path uses `non_linear_giveback_fn` (see `rust/openclaw_engine/src/exit_features/v2.rs:258-265`)
and full Gate 1/2/3 sequencing. Treat v1 outputs as lower/upper bounds, NOT
production-behavior estimates. v2 parity replay is FUP.

**FA ALGEBRA NOTE (2026-04-23, critical)**:
The v1 `proxy` cost model is **algebraically degenerate**: `realized_net_bps` is
ALREADY net of round-trip fees (writer nets both entry+close fees, see
`rust/openclaw_engine/src/tick_pipeline/pipeline_helpers.rs:387-411`). The proxy
formula `cost = peak_gross - realized_net` collapses to `giveback_gross + fees`,
so `cf_net - realized_net ≡ -k × atr_bps` for every fired row — verdict is fixed
before data is read. Script now offers a **`fee_only` cost model** (round-trip
taker fee only, no giveback double-count) as the empirically meaningful
comparison. Default `--cost-model both` emits both side-by-side; the `fee_only`
VERDICT is the one operator should read. The `proxy` column is retained as a
transparency sanity check so operator can verify the degenerate identity.

MODULE_NOTE (中): EDGE-DIAG-1 #3（TODO.md §P1，2026-04-23）。對 `learning.exit_features`
最近 N 天 read-only SELECT，回答：「Track P phys_lock 若在當前 edge 環境實際觸發，
會比實際退場 net PnL 更好嗎？」one-row-per-exit（writer `exit_feature_writer.rs`，
PK `(context_id, ts)`），同列同時含 realised `realized_net_bps` 與退場時刻快照。
輸出 (engine_mode, strategy_name, symbol) 分組表 + `$OPENCLAW_DATA_DIR/audit/`
JSON（latest + dated siblings，CLAUDE.md §七 新腳本契約）。

**v1 範圍限制**：僅模擬 Gate 4（giveback 閾值）線性近似 k=0.3。v2 生產路徑為
non-linear + 全 Gate 1/2/3 排序；v1 結果視為上/下界，非 production 行為估計。

**FA 代數警示**（2026-04-23）：`proxy` 成本模型代數退化 — `realized_net_bps`
writer 已扣進出兩側手續費，`proxy = peak_gross - realized_net` 恆 = `giveback_gross + fees`，
故 `cf_net - realized_net ≡ -k × atr_bps`，判決先於資料。新增 `fee_only`
成本模型（round-trip taker fee only，避雙重扣 giveback），`--cost-model both`
預設同時輸出，operator 應讀 `fee_only` VERDICT；`proxy` 欄保留作透明度核驗。

Usage:
  POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=... \\
    python3 helper_scripts/db/counterfactual_exit_replay.py [flags]

Counterfactual model / 反事實模型:
  At close time, the row carries the snapshot of `peak_pnl_pct` + `atr_pct` +
  `giveback_atr_norm = (peak - current) / ATR`. Simulated "peak - k × ATR" exit
  triggers at the first tick where giveback_atr_norm ≥ k, locking profit at
  `(peak_pnl_pct - k * atr_pct) * 100` bps gross of entry notional.
  退場時刻快照已齊全；模擬「peak - k × ATR」退場於 giveback_atr_norm ≥ k 觸發。

  Formula (dual cost model, pure fn _cf_row_outcome):
    cf_gross_bps          = (peak_pnl_pct - k * atr_pct) * 100.0
    # proxy (DEGENERATE — kept for transparency per FA audit):
    cost_proxy_bps        = max(0.0, peak_gross_bps - realized_net_bps)
    cf_net_proxy_bps      = cf_gross_bps - cost_proxy_bps
    # fee_only (EMPIRICALLY MEANINGFUL — use this for decisions):
    cost_fee_only_bps     = 2 * fee_bps_per_side      # round-trip taker fee
    cf_net_fee_only_bps   = cf_gross_bps - cost_fee_only_bps
    improvement_{model}   = cf_net_{model}_bps - realized_net_bps

  About k=0.3: v1 linear approximation of v2 non-linear threshold
  `max(giveback_base - giveback_slope × peak_atr_norm, giveback_floor)
   = max(1.0 - 0.15 × peak_atr_norm, 0.3)` (see `rust/openclaw_engine/src/exit_features/v2.rs:165-173`).
  The `0.3` floor is the **asymptotic** floor reached only when peak_atr_norm
  is extremely large; for typical peak_atr_norm ≈ 0.5–2.0 the effective v2
  threshold is ~0.7–0.925. v1 k=0.3 therefore **overstates** fire frequency
  relative to v2 (upper bound on "cf would have fired").
  關於 k=0.3：v2 實為 non-linear `max(1.0 - 0.15 × peak_atr_norm, 0.3)`（v2.rs:165-173）；
  0.3 為 asymptotic floor（僅 peak_atr_norm 極大時到達），常態 peak_atr_norm ≈ 0.5–2.0
  時 v2 有效閾值約 0.7–0.925。v1 k=0.3 因此高估 fire 頻率（「cf 會觸發」的上界）。

  Strategy filter default: `funding_arb` EXCLUDED — funding_arb realized pnl
  includes funding payment, peak_pnl_pct is price-only → proxy cost breaks.
  Use `--include-funding-arb` to opt in (with warning banner).
  策略過濾預設：排除 `funding_arb`（realized pnl 含資金費，peak_pnl_pct 僅含價格
  → proxy cost 失真）；`--include-funding-arb` 可強行納入（附警告橫幅）。

Edge cases / 邊界條件:
  (a) peak_pnl_pct <= 0    — loser trade; cf would not fire. cf_fired=0.
  (b) atr_pct == 0 or NULL — ATR unavailable; cf undefined. cf_fired=0.
  (c) giveback_atr_norm < k — cf did NOT trigger. cf_fired=0.
  (d) realized_net_bps NULL — dropped from aggregates (SQL filter).

Exit codes:
  0 = report generated (table printed, JSON written)
  2 = DB connection error (mirrors passive_wait_healthcheck.py convention)

READ-ONLY: pure SELECT. Safe on production DB. Dispatch via `ssh trade-core`.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---- connection (mirrors passive_wait_healthcheck.py exactly) ----
# 連線（完全沿用 passive_wait_healthcheck.py 模式）

def _get_conn():
    import psycopg2  # type: ignore
    dsn = (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )
    return psycopg2.connect(dsn)


# ---- counterfactual arithmetic (pure fn, unit-testable) ----
# 反事實算術（純函數，可單測）

def _cf_row_outcome(
    peak_pnl_pct: float | None,
    atr_pct: float | None,
    giveback_atr_norm: float | None,
    realized_net_bps: float | None,
    k: float,
    cost_model: str,
    fee_bps_per_side: float,
) -> tuple[bool, float, float, float]:
    """Return (cf_fired, cf_net_bps, actual_net_bps, improvement_bps) for one row.

    cost_model:
      - "proxy"    : cost = max(0, peak_gross - realized_net). DEGENERATE (FA 2026-04-23):
                     since realized_net_bps is already net of round-trip fees, this
                     collapses to giveback_gross + fees and makes improvement
                     deterministically -k × atr_bps for every fired row.
      - "fee_only" : cost = 2 × fee_bps_per_side (round-trip taker fee only). The
                     empirically meaningful comparison.

    cf_fired=False → cf_net_bps := actual (0 improvement, row still counted).
    All edge cases (a)(b)(c) collapse to cf_fired=False. Case (d) is filtered
    in SQL (realized_net_bps IS NOT NULL) — if it slips through, we treat it
    as "cannot score" and force cf_fired=False + improvement=0.

    回傳 (cf_fired, cf_net_bps, actual_net_bps, improvement_bps)；a/b/c 邊界皆
    collapse 為 cf_fired=False（0 improvement，row 仍計）。d 由 SQL 過濾。
    """
    # Guard: missing realised → cannot score, treat as no-op.
    # 防護：缺 realised → 無法評分，視為 no-op。
    if realized_net_bps is None or not math.isfinite(realized_net_bps):
        return (False, 0.0, 0.0, 0.0)

    actual = float(realized_net_bps)

    # Case (a): peak_pnl_pct <= 0 — no favorable excursion ever recorded.
    # Case (b): atr_pct missing or 0 — ATR undefined, cf trigger undefined.
    # Case (c): giveback_atr_norm missing or < k — cf did not trigger.
    # (a) peak<=0 / (b) atr 無效 / (c) giveback<k — cf 皆未觸發。
    if peak_pnl_pct is None or not math.isfinite(peak_pnl_pct) or peak_pnl_pct <= 0:
        return (False, actual, actual, 0.0)
    if atr_pct is None or not math.isfinite(atr_pct) or atr_pct <= 0:
        return (False, actual, actual, 0.0)
    if (
        giveback_atr_norm is None
        or not math.isfinite(giveback_atr_norm)
        or giveback_atr_norm < k
    ):
        return (False, actual, actual, 0.0)

    # cf fired — compute locked-in gross + apply chosen cost model.
    # cf 觸發 — 計算鎖定 gross + 套用選定成本模型。
    cf_gross_bps = (peak_pnl_pct - k * atr_pct) * 100.0
    peak_gross_bps = peak_pnl_pct * 100.0

    if cost_model == "proxy":
        # DEGENERATE proxy (see docstring; retained for transparency).
        # 退化 proxy（見 docstring；保留作透明度核驗）。
        cost_bps = max(0.0, peak_gross_bps - actual)
    elif cost_model == "fee_only":
        # Round-trip exchange fee only; no giveback double-count.
        # 僅 round-trip 手續費；不雙重扣 giveback。
        cost_bps = 2.0 * fee_bps_per_side
    else:
        raise ValueError(
            f"unknown cost_model {cost_model!r}; expected 'proxy' or 'fee_only'"
        )

    cf_net = cf_gross_bps - cost_bps
    return (True, cf_net, actual, cf_net - actual)


# ---- aggregation ----

def _aggregate(
    rows: list[dict[str, Any]],
    k: float,
    cost_models: tuple[str, ...],
    fee_bps_per_side: float,
) -> list[dict[str, Any]]:
    """Group by (engine_mode, strategy_name, symbol), emit summary rows per cost model.

    Output schema (per group):
      {engine_mode, strategy_name, symbol, n_exits, actual_net_bps_avg,
       per_model: {model_name: {cf_fired_count, cf_net_bps_avg,
                                improvement_bps_avg, improvement_pos_pct}}}
    """
    def _zero_model_acc() -> dict[str, Any]:
        return {
            "cf_fired_count": 0,
            "sum_cf": 0.0,
            "sum_improvement": 0.0,
            "improvement_pos_count": 0,
        }

    groups: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "n_exits": 0,
            "sum_actual": 0.0,
            "per_model": {m: _zero_model_acc() for m in cost_models},
        }
    )

    for r in rows:
        # Double-guard (d): SQL already filters, but skip if slipped through.
        # (d) 防護：SQL 已過濾；萬一漏過也跳過。
        rn = r.get("realized_net_bps")
        if rn is None:
            continue

        key = (
            r.get("engine_mode") or "",
            r.get("strategy_name") or "",
            r.get("symbol") or "",
        )
        g = groups[key]
        g["n_exits"] += 1
        g["sum_actual"] += float(rn)

        for model in cost_models:
            cf_fired, cf_net, _actual, improvement = _cf_row_outcome(
                r.get("peak_pnl_pct"),
                r.get("atr_pct"),
                r.get("giveback_atr_norm"),
                rn,
                k,
                model,
                fee_bps_per_side,
            )
            m_acc = g["per_model"][model]
            if cf_fired:
                m_acc["cf_fired_count"] += 1
                m_acc["sum_cf"] += cf_net
                m_acc["sum_improvement"] += improvement
                if improvement > 0:
                    m_acc["improvement_pos_count"] += 1
            else:
                # cf collapsed to actual for the avg-over-n_exits calculation.
                # cf 未觸發時以 actual 頂替（避免扭曲平均）。
                m_acc["sum_cf"] += float(rn)

    out = []
    for (engine_mode, strategy, symbol), g in sorted(groups.items()):
        n = g["n_exits"]
        per_model_out: dict[str, Any] = {}
        for model in cost_models:
            m_acc = g["per_model"][model]
            cf_n = m_acc["cf_fired_count"]
            per_model_out[model] = {
                "cf_fired_count": cf_n,
                "cf_net_bps_avg": (m_acc["sum_cf"] / n) if n else 0.0,
                "improvement_bps_avg": (m_acc["sum_improvement"] / cf_n) if cf_n else 0.0,
                "improvement_pos_pct": (100.0 * m_acc["improvement_pos_count"] / cf_n) if cf_n else 0.0,
            }
        out.append({
            "engine_mode": engine_mode,
            "strategy_name": strategy,
            "symbol": symbol,
            "n_exits": n,
            "actual_net_bps_avg": (g["sum_actual"] / n) if n else 0.0,
            "per_model": per_model_out,
        })
    return out


# ---- output formatting ----

def _print_table(rows: list[dict[str, Any]], cost_models: tuple[str, ...]) -> None:
    """Stdout table grouped by (engine_mode, strategy_name, symbol) + summary.

    When multiple cost models are active, emits one table per model (clearer
    than interleaved columns, per PA feedback).

    Note: `cf_avg` equals `actual` for rows where cf did NOT fire (by design, so
    averages are comparable — not biased to the fired subset).
    注意：`cf_avg` 在 cf 未觸發時等於 `actual`（刻意設計；保持平均值可比性，
    不偏向觸發子集）。
    """
    if not rows:
        print("(no rows — check --days window and filter flags)")
        return

    # QC-round-2 NIT: surface the cf_avg==actual-when-unfired note on stdout so
    # readers of raw table output see it, not only those reading the docstring.
    # 將 cf_avg 未觸發 fallback 的提示印到 stdout，避免只看表者誤讀。
    print()
    print("Note: cf_avg == actual for non-fired rows (by design; keeps averages")
    print("      comparable across groups, not biased to the fired subset).")

    for model in cost_models:
        print()
        print(f"=== cost_model: {model} ===")
        header = (
            f"{'engine_mode':<11} | {'strategy_name':<18} | {'symbol':<12} | "
            f"{'n_exits':>7} | {'cf_fired':>8} | {'actual_avg':>10} | "
            f"{'cf_avg':>10} | {'improv_avg':>10} | {'improv_pos%':>11}"
        )
        print(header)
        print("-" * len(header))
        for r in rows:
            m = r["per_model"][model]
            print(
                f"{r['engine_mode']:<11} | {r['strategy_name']:<18.18} | "
                f"{r['symbol']:<12.12} | {r['n_exits']:>7d} | "
                f"{m['cf_fired_count']:>8d} | {r['actual_net_bps_avg']:>10.2f} | "
                f"{m['cf_net_bps_avg']:>10.2f} | {m['improvement_bps_avg']:>10.2f} | "
                f"{m['improvement_pos_pct']:>10.1f}%"
            )
        # Summary row per model.
        total_n = sum(r["n_exits"] for r in rows)
        total_cf = sum(r["per_model"][model]["cf_fired_count"] for r in rows)
        if total_n == 0:
            continue
        total_actual = sum(r["actual_net_bps_avg"] * r["n_exits"] for r in rows) / total_n
        total_cf_avg = sum(
            r["per_model"][model]["cf_net_bps_avg"] * r["n_exits"] for r in rows
        ) / total_n
        total_imp = (
            sum(
                r["per_model"][model]["improvement_bps_avg"]
                * r["per_model"][model]["cf_fired_count"]
                for r in rows
            ) / total_cf
        ) if total_cf else 0.0
        total_pos_pct = (
            sum(
                r["per_model"][model]["improvement_pos_pct"] / 100.0
                * r["per_model"][model]["cf_fired_count"]
                for r in rows
            ) * 100.0 / total_cf
        ) if total_cf else 0.0
        print("-" * len(header))
        print(
            f"{'ALL':<11} | {'(summary)':<18} | {'':<12} | "
            f"{total_n:>7d} | {total_cf:>8d} | {total_actual:>10.2f} | "
            f"{total_cf_avg:>10.2f} | {total_imp:>10.2f} | {total_pos_pct:>10.1f}%"
        )


def _summary_totals(
    rows: list[dict[str, Any]], model: str
) -> tuple[int, int, float]:
    """Return (total_n_exits, total_cf_fired, total_improvement_bps_avg) for a model."""
    total_n = sum(r["n_exits"] for r in rows)
    total_cf = sum(r["per_model"][model]["cf_fired_count"] for r in rows)
    total_imp = (
        sum(
            r["per_model"][model]["improvement_bps_avg"]
            * r["per_model"][model]["cf_fired_count"]
            for r in rows
        ) / total_cf
    ) if total_cf else 0.0
    return (total_n, total_cf, total_imp)


def _write_json_outputs(
    rows: list[dict[str, Any]],
    args: argparse.Namespace,
    started_at: datetime,
    cost_models: tuple[str, ...],
) -> tuple[Path, Path]:
    """Write `--output-json` latest + dated sibling (CLAUDE.md §七 script spec)."""
    totals_by_model = {
        model: {
            "total_n_exits": _summary_totals(rows, model)[0],
            "total_cf_fired": _summary_totals(rows, model)[1],
            "total_improvement_bps_avg": _summary_totals(rows, model)[2],
        }
        for model in cost_models
    }
    payload = {
        "generated_at": started_at.isoformat(timespec="seconds"),
        "days": args.days,
        "cf_multiplier": args.cf_multiplier,
        "cost_models": list(cost_models),
        "fee_bps_per_side": args.fee_bps_per_side,
        "engine_mode_filter": args.engine_mode,
        "strategy_filter_requested": args.strategy,
        "funding_arb_included": bool(args.include_funding_arb),
        "symbol_filter": args.symbol,
        # FA-round-2 MINOR: expose v1 scope + linearity caveat to JSON consumers
        # so downstream dashboards / ML pipelines cannot silently over-extrapolate.
        # FA 二輪建議：JSON 消費者（dashboard / ML）無法看 docstring，顯式宣告 v1 scope 與線性近似。
        "v1_scope": (
            "Gate-4-only, LINEAR k=cf_multiplier (v2 uses non_linear_giveback_fn "
            "max(giveback_base - giveback_slope * peak_atr_norm, giveback_floor); "
            "default 0.3 is the asymptotic FLOOR, effective threshold is 0.7-0.925 "
            "for typical peak_atr_norm 0.5-2.0). Gate 1/2/3 sequencing parity + "
            "non-linear threshold = FUP. Outputs are lower/upper bounds, NOT "
            "production phys_lock behavior estimates."
        ),
        "totals_by_model": totals_by_model,
        "rows": rows,
    }

    latest = Path(args.output_json)
    latest.parent.mkdir(parents=True, exist_ok=True)
    stamp = started_at.strftime("%Y%m%d_%H%M%S")
    if latest.name.endswith("_latest.json"):
        dated = latest.with_name(latest.name.replace("_latest.json", f"_{stamp}.json"))
    else:
        dated = latest.with_name(f"{latest.stem}_{stamp}{latest.suffix}")

    for p in (latest, dated):
        with p.open("w") as f:
            json.dump(payload, f, indent=2, default=str)
    return (latest, dated)


# ---- SQL ----

_SELECT_SQL = """
    SELECT
        engine_mode,
        strategy_name,
        symbol,
        peak_pnl_pct,
        atr_pct,
        giveback_atr_norm,
        realized_net_bps
    FROM learning.exit_features
    WHERE ts > now() - (%(days)s || ' days')::interval
      AND realized_net_bps IS NOT NULL
      AND (%(engine_mode_all)s OR engine_mode = ANY(%(engine_modes)s))
      AND (%(strategy)s IS NULL OR strategy_name = %(strategy)s)
      AND (%(include_funding_arb)s OR strategy_name != 'funding_arb')
      AND (%(symbol)s IS NULL OR symbol = %(symbol)s)
"""


def _build_query_params(args: argparse.Namespace) -> dict[str, Any]:
    """Parse --engine-mode and return psycopg2 named-param dict."""
    em_raw = (args.engine_mode or "").strip().lower()
    if em_raw == "all":
        engine_mode_all = True
        engine_modes: list[str] = []
    else:
        engine_mode_all = False
        engine_modes = [s.strip() for s in em_raw.split(",") if s.strip()]
        if not engine_modes:
            # Default: demo + live_demo (per Edge 分析用 demo 不用 paper memory note)
            # 預設：demo + live_demo（依 feedback_demo_over_paper_for_edge memory）
            engine_modes = ["demo", "live_demo"]
    return {
        "days": str(args.days),
        "engine_mode_all": engine_mode_all,
        "engine_modes": engine_modes,
        "strategy": args.strategy,
        "include_funding_arb": bool(args.include_funding_arb),
        "symbol": args.symbol,
    }


# ---- main ----

def _default_output_path() -> str:
    """`$OPENCLAW_DATA_DIR/audit/counterfactual_exit_replay_latest.json`."""
    base = os.environ.get("OPENCLAW_DATA_DIR") or "/tmp/openclaw"
    return str(Path(base) / "audit" / "counterfactual_exit_replay_latest.json")


def _positive_int(raw: str) -> int:
    """argparse type fn: reject ``--days <= 0`` loudly (QC MINOR fix)."""
    try:
        v = int(raw)
    except (TypeError, ValueError) as e:
        raise argparse.ArgumentTypeError(f"expected int, got {raw!r}") from e
    if v <= 0:
        raise argparse.ArgumentTypeError(
            f"must be > 0 (got {v}); a non-positive window has no data to replay"
        )
    return v


def _positive_float(raw: str) -> float:
    """argparse type fn: reject ``--fee-bps-per-side < 0``."""
    try:
        v = float(raw)
    except (TypeError, ValueError) as e:
        raise argparse.ArgumentTypeError(f"expected float, got {raw!r}") from e
    if v < 0 or not math.isfinite(v):
        raise argparse.ArgumentTypeError(
            f"must be finite and >= 0 (got {v})"
        )
    return v


def _resolve_cost_models(raw: str) -> tuple[str, ...]:
    r = (raw or "").strip().lower()
    if r == "both":
        return ("proxy", "fee_only")
    if r in ("proxy", "fee_only"):
        return (r,)
    raise argparse.ArgumentTypeError(
        f"--cost-model must be one of proxy|fee_only|both (got {raw!r})"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--days", type=_positive_int, default=7,
                    help="Lookback window in days, must be > 0 (default 7)")
    ap.add_argument("--engine-mode", type=str, default="demo,live_demo",
                    help="Comma-separated list or 'all' (default: demo,live_demo)")
    ap.add_argument("--strategy", type=str, default=None,
                    help="Filter by strategy_name (optional)")
    ap.add_argument("--symbol", type=str, default=None,
                    help="Filter by symbol (optional)")
    ap.add_argument("--cf-multiplier", type=float, default=0.3,
                    help="k in 'peak - k × ATR' lock model (default 0.3; v2 "
                         "non-linear asymptotic floor — see module docstring)")
    ap.add_argument(
        "--cost-model",
        type=str,
        default="both",
        help="Cost model for cf_net: 'proxy' (degenerate per FA — retained for "
             "transparency), 'fee_only' (round-trip taker fee; empirically "
             "meaningful), or 'both' (default; prints two tables + two verdicts)",
    )
    ap.add_argument(
        "--fee-bps-per-side",
        type=_positive_float,
        default=5.5,
        help="Taker fee per side in bps for the fee_only cost model. Default "
             "5.5 = Bybit linear taker (0.00055; see "
             "rust/openclaw_engine/src/account_manager.rs:136 DEFAULT_TAKER_FEE)",
    )
    ap.add_argument(
        "--include-funding-arb",
        action="store_true",
        help="Opt-in to include strategy_name='funding_arb' rows. By default "
             "excluded because realized_pnl includes funding payment while "
             "peak_pnl_pct is price-only → proxy cost is distorted.",
    )
    ap.add_argument("--output-json", type=str, default=_default_output_path(),
                    help="Latest JSON output path (dated sibling auto-written)")
    args = ap.parse_args()

    cost_models = _resolve_cost_models(args.cost_model)

    started_at = datetime.now(timezone.utc)
    print(
        f"Counterfactual exit replay @ {started_at.isoformat(timespec='seconds')} UTC"
    )
    print(
        "  v1: Gate-4-only, LINEAR giveback k={k}. v2 non-linear + "
        "Gate 1/2/3 sequencing TBD. Lower/upper bounds, not production-behavior.".format(
            k=args.cf_multiplier
        )
    )
    print(
        f"  days={args.days}  cf_multiplier={args.cf_multiplier}  "
        f"cost_model={args.cost_model}  fee_bps_per_side={args.fee_bps_per_side}"
    )
    print(
        f"  engine_mode={args.engine_mode}  strategy={args.strategy or '(any)'}  "
        f"symbol={args.symbol or '(any)'}  "
        f"funding_arb={'INCLUDED' if args.include_funding_arb else 'excluded'}"
    )
    if args.include_funding_arb:
        print(
            "  [WARNING] funding_arb included: realized_pnl has funding payment "
            "component while peak_pnl_pct is price-only → proxy cost distorted; "
            "treat funding_arb rows with extra skepticism."
        )
    print("=" * 70)

    try:
        conn = _get_conn()
    except Exception as e:
        print(f"[FATAL] DB connect failed: {e}")
        return 2

    rows: list[dict[str, Any]] = []
    try:
        with conn.cursor() as cur:
            cur.execute(_SELECT_SQL, _build_query_params(args))
            colnames = [d.name for d in cur.description]  # type: ignore[union-attr]
            for row in cur.fetchall():
                rows.append(dict(zip(colnames, row)))
    except Exception as e:
        print(f"[FATAL] query failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return 2
    finally:
        try:
            conn.close()
        except Exception:
            pass

    agg = _aggregate(rows, args.cf_multiplier, cost_models, args.fee_bps_per_side)
    _print_table(agg, cost_models)
    print("=" * 70)

    latest, dated = _write_json_outputs(agg, args, started_at, cost_models)
    print(f"JSON written: {latest}")
    print(f"JSON dated:   {dated}")

    # Decision criterion per EDGE-DIAG-1 spec. When `both` models present, we
    # emit two captioned verdicts: operator should read the fee_only one.
    # EDGE-DIAG-1 判決條件；兩模型並存時，operator 應讀 fee_only 版。
    total_n = sum(r["n_exits"] for r in agg)
    if total_n == 0:
        print("VERDICT: no exits in window — nothing to judge")
        return 0

    def _emit_verdict(model: str, caption: str) -> None:
        _n, total_cf, total_imp = _summary_totals(agg, model)
        if total_cf == 0:
            print(
                f"VERDICT ({caption}): cf NEVER fired (all rows below giveback "
                f"threshold k={args.cf_multiplier}); cannot score — widen window or lower k"
            )
            return
        if total_imp > 0:
            print(
                f"VERDICT ({caption}): cf improvement avg = +{total_imp:.2f} bps "
                f"over {total_cf} fired exits — phys_lock WOULD have helped; "
                "widen Gate 1 fallback / re-tune floor to let it fire"
            )
        else:
            print(
                f"VERDICT ({caption}): cf improvement avg = {total_imp:.2f} bps "
                f"over {total_cf} fired exits — phys_lock WOULD NOT have helped; "
                "Track P physical layer mismatched to current edge env "
                "(EDGE-DIAG-1 reassessment trigger)"
            )

    if "fee_only" in cost_models:
        _emit_verdict("fee_only", "fee_only model, conservative — READ THIS")
    if "proxy" in cost_models:
        # FA-round-2 LOW: Add explicit degenerate-proxy banner BEFORE the verdict
        # body so a hurried reader scanning for "WOULD NOT" cannot mistake the
        # algebraically-pinned proxy signal for a real verdict.
        # FA 二輪建議：proxy verdict body 與 fee_only 同文字 "WOULD/WOULD NOT have helped"
        # 可誤讀；印顯式 degenerate banner 先於 verdict，提醒忽略其 sign。
        print()
        print(
            "[DEGENERATE PROXY WARNING] Per FA algebra proof, proxy improvement "
            "≡ −k × atr_pct × 100 bps identically for every fired row (fees "
            "cancel out + giveback is double-counted). IGNORE THE SIGN below; "
            "the proxy verdict is retained ONLY as an arithmetic sanity check "
            "that the formula collapses as derived."
        )
        _emit_verdict("proxy", "proxy model, degenerate — sanity check only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
