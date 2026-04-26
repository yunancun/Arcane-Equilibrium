#!/usr/bin/env python3
"""exit_threshold_calibrator — read-only `learning.exit_features` percentile bind tool.
exit_threshold_calibrator — 唯讀 `learning.exit_features` 百分位閾值 bind 工具。

MODULE_NOTE (EN): Wave 3 EDGE-P1b T1 helper. Reads `learning.exit_features`
rows, stratifies per-strategy, applies cohort filter (rolling 14d minus
7d embargo) + profit-cohort gate (`realized_net_bps > 0`), then computes
percentile thresholds across the 7-dim feature space defined by
V999__exit_features.sql:33-41:

    1. est_net_bps           (real)   — JS edge + cost_gate inferred net bps
    2. peak_pnl_pct          (real)   — max-favorable-pnl % since entry
    3. atr_pct               (real)   — ATR / price at exit time
    4. giveback_atr_norm     (real)   — (peak − current) / ATR (normalized)
    5. time_since_peak_ms    (bigint) — ms since peak achieved
    6. price_roc_short       (real)   — short-window price rate-of-change
    7. entry_age_secs        (real)   — seconds since entry

Per RFC §2.1 (PA report 2026-04-26--edge_p1b_7dim_bind_rfc.md), the bind
target is the existing `RiskConfig.exit.*` block (no schema extension).
The mapping from percentile to ExitConfig field is fixed:

    | ExitConfig field          | Percentile source                        |
    |---------------------------|------------------------------------------|
    | min_net_floor_bps         | profit cohort `est_net_bps` p10          |
    | min_peak_atr_norm         | profit cohort `peak_pnl_pct/atr_pct` p25 |
    | giveback_base             | profit cohort `giveback_atr_norm` p75    |
    | giveback_floor            | profit cohort `giveback_atr_norm` p25    |
    | stale_peak_ms             | profit cohort `time_since_peak_ms` p75   |
    | min_hold_secs             | profit cohort `entry_age_secs` p25       |

`giveback_slope` is derived as a linear interp between base and floor:
    slope = (giveback_base − giveback_floor) / max(peak_atr_norm, 1.0)

Dim 6 (`price_roc_short`) is NOT mapped this round (no corresponding
ExitConfig field) — preserved as future ML feature input only.

**Important caveats**:
  * `stale_peak_ms` calibration is computed but currently has NO IPC
    write path (see `ipc_server/handlers/risk.rs:84-99` — only 7 of 9
    ExitConfig fields are wired through `update_risk_config`). When
    `--apply` mode lands, `stale_peak_ms` patches require manual
    `risk_config_*.toml` edit + engine reload via
    `reload_risk_config?engine=demo` IPC. Listed in JSON patch output
    under `"toml_only_fields"` for operator transparency.
  * Pure dry-run by default. `--apply` only emits a JSON patch envelope
    that operator must manually approve. NO direct IPC write happens
    from this tool (RFC §2.2 manual-approve mode A). Future Phase B
    automation will add a separate operator-confirmation flow.

**Cohort sizing** (RFC §2.3):
  * rolling 14d minus 7d embargo (avoid regime-shift contamination)
  * profit cohort only (`realized_net_bps > 0`)
  * per-strategy ≥200 rows or strategy is skipped with INSUFFICIENT
  * total <1000 rows → exit code 1

**Pure read-only**: no PG writes, no business-logic mutation. Lazy-imports
psycopg2 inside main() (CLAUDE.md §七 hygiene rule — no PG connect at
import time so --smoke-test runs without a live DB).

MODULE_NOTE (中): Wave 3 EDGE-P1b T1 helper。讀 `learning.exit_features`，
依 strategy 分層，套 cohort filter（rolling 14d 減 7d embargo）+ profit
cohort gate（`realized_net_bps > 0`），計算 V999__exit_features.sql:33-41
定義的 7 維特徵百分位閾值（est_net_bps / peak_pnl_pct / atr_pct /
giveback_atr_norm / time_since_peak_ms / price_roc_short / entry_age_secs）。

依 RFC §2.1（PA 報告 2026-04-26--edge_p1b_7dim_bind_rfc.md），bind 目標是
既有 `RiskConfig.exit.*` 區段（不擴 schema）；ExitConfig 6 個 percentile 字段對應如上表。
`giveback_slope` 採 base/floor 線性外推；dim 6（price_roc_short）此輪不映射，
保留作未來 ML feature input。

重要注意事項：
  * `stale_peak_ms` 雖計算但目前 IPC 無寫入路徑
    （見 `ipc_server/handlers/risk.rs:84-99` — 9 個 ExitConfig 字段僅 7 個透過
    `update_risk_config` 接線）。未來 `--apply` 模式時 `stale_peak_ms` 補丁需
    手工編輯 `risk_config_*.toml` 並透過 `reload_risk_config?engine=demo` 重載；
    JSON patch 輸出將其放在 `"toml_only_fields"` 區塊以便 operator 識別。
  * 預設純 dry-run；`--apply` 只輸出 JSON patch 信封，operator 須人工審查。
    本工具不直接 IPC 寫（per RFC §2.2 manual-approve 模式 A）。後續 Phase B
    自動化將另行設計 operator-confirmation 流程。

Cohort 規模（RFC §2.3）：
  * rolling 14d 減 7d embargo（避 regime-shift 污染）
  * profit cohort（`realized_net_bps > 0`）
  * per-strategy ≥200 rows，否則該策略跳過並報 INSUFFICIENT
  * 總 <1000 rows → exit code 1

純唯讀：不寫資料；psycopg2 lazy-import 進 main()。

Usage:
  OPENCLAW_DATABASE_URL=postgresql://... \\
    python3 helper_scripts/research/exit_threshold_calibrator.py \\
      [--engine-mode demo] [--strategies grid_trading,ma_crossover] \\
      [--lookback-days 14] [--embargo-days 7] \\
      [--percentile-targets 90,95,99] [--min-samples-per-strategy 200] \\
      [--output-format markdown] [--apply] [--output-file path]
  python3 ... --smoke-test          # SQL syntax dry-run, no DB needed

Exit codes:
  0 = success + ≥1 strategy met sample threshold
  1 = no strategy met sample threshold (insufficient data; defer bind)
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

# ─────────────────────────────────────────────────────────────────────────
# Constants — mapping policy from RFC §2.1.
# 常量 — RFC §2.1 映射政策。
# ─────────────────────────────────────────────────────────────────────────

# 7 feature dim names exactly as in V999__exit_features.sql:33-41.
# 7 維特徵欄名（與 V999__exit_features.sql:33-41 完全對應）。
FEATURE_DIMS: tuple[str, ...] = (
    "est_net_bps",
    "peak_pnl_pct",
    "atr_pct",
    "giveback_atr_norm",
    "time_since_peak_ms",
    "price_roc_short",
    "entry_age_secs",
)

# ExitConfig fields wired through IPC `update_risk_config`
# (per ipc_server/handlers/risk.rs:84-99).
# `stale_peak_ms` and `shadow_enabled` are NOT in IPC and require TOML edit.
# ExitConfig 透過 IPC 接線的字段（`stale_peak_ms` / `shadow_enabled` 不在內，需 TOML 編輯）。
IPC_WIRED_EXIT_FIELDS: frozenset[str] = frozenset({
    "missing_edge_fallback_bps",
    "min_net_floor_bps",
    "min_hold_secs",
    "min_peak_atr_norm",
    "giveback_base",
    "giveback_slope",
    "giveback_floor",
})

TOML_ONLY_EXIT_FIELDS: frozenset[str] = frozenset({
    "stale_peak_ms",
    # shadow_enabled is binary toggle, not derived from percentile bind.
    # shadow_enabled 是二態開關，非百分位導出。
})


# ─────────────────────────────────────────────────────────────────────────
# SQL — read learning.exit_features for cohort + percentile compute.
# SQL — 讀 learning.exit_features 為 cohort + 百分位計算。
# ─────────────────────────────────────────────────────────────────────────
#
# Notes / 備註：
#   - %s placeholder style (psycopg2 default — not :name).
#   - cohort = rolling lookback minus embargo:
#       ts > now() - lookback days AND ts <= now() - embargo days
#     This excludes the most recent `embargo` days to avoid regime-shift
#     contamination (per RFC §2.3 + memory time-series-cv-protocol).
#   - profit cohort gate: `realized_net_bps > 0` (only successful exits
#     reflect intended threshold protection — losing exits indicate other
#     failure modes).
#   - per-strategy stratification via GROUP BY strategy_name.
#   - 7 features fetched as raw rows (NOT percentile_disc in SQL) so we
#     can apply our own NaN guard + sample-count check in Python.

PROFIT_COHORT_SQL = """
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
  AND ts <= now() - (%s || ' days')::interval
  AND realized_net_bps IS NOT NULL
  AND realized_net_bps > 0
  {strategy_filter}
ORDER BY strategy_name ASC, ts ASC
"""

# strategies filter sub-clause; built only when --strategies is non-default.
# strategies 過濾子句；--strategies 非預設時才加。
STRATEGY_FILTER_TEMPLATE = "AND strategy_name = ANY(%s)"


# ─────────────────────────────────────────────────────────────────────────
# DB helpers — mirror passive_wait_healthcheck.py + ma_crossover_counterfactual_replay.py
# DB helpers — 沿用 passive_wait_healthcheck.py + ma_crossover_counterfactual_replay.py 風格。
# ─────────────────────────────────────────────────────────────────────────


def _build_dsn() -> str:
    """Build PG DSN from env, mirroring style in helper_scripts.
    從 env 構造 PG DSN，沿用 helper_scripts 風格。
    """
    return (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )


def _open_conn():
    """Lazy import + open PG connection. Failure raises (caller → exit 2).
    延遲載入並開 PG 連線；失敗向上拋（呼叫端轉 exit 2）。
    """
    import psycopg2  # type: ignore  # lazy: avoid import-time DB hard-dep

    dsn = _build_dsn()
    return psycopg2.connect(dsn)


# ─────────────────────────────────────────────────────────────────────────
# Percentile math — pure functions (testable without DB).
# 百分位計算 — 純函數（可不連 DB 測試）。
# ─────────────────────────────────────────────────────────────────────────


def percentile_linear(sorted_values: list[float], pct: float) -> float | None:
    """Linear-interpolation percentile (NumPy default `linear` method) on a
    pre-sorted ascending list. Returns None if list empty.

    pct in [0, 100]. Matches `numpy.percentile(values, pct)` for finite real
    inputs without pulling NumPy in.

    線性插值百分位（NumPy 預設 `linear` 方法），輸入須升序；空 list → None。
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


def filter_finite(values: list[float | None]) -> list[float]:
    """Drop None / NaN / Inf — guard percentile inputs.
    丟棄 None / NaN / Inf — 百分位計算保護。
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


def compute_percentile_thresholds(
    rows: list[dict[str, Any]],
    pct_targets: list[float],
) -> dict[str, dict[str, float]]:
    """For each of the 7 feature dims, compute requested percentiles on the
    finite, non-null values across rows.

    Returns: {dim_name: {pct_str: value, ...}}
    Empty dim → {dim_name: {}} (caller decides INSUFFICIENT).

    對 7 維特徵的每個維度計算指定百分位（過濾 None/NaN/Inf 後）。
    回傳 {維度名: {百分位字串: 值}}；空維度 → {}（呼叫端判 INSUFFICIENT）。
    """
    out: dict[str, dict[str, float]] = {}
    for dim in FEATURE_DIMS:
        raw = [row.get(dim) for row in rows]
        finite = filter_finite(raw)
        finite.sort()
        per_pct: dict[str, float] = {}
        for pct in pct_targets:
            v = percentile_linear(finite, pct)
            if v is not None:
                per_pct[f"p{int(pct) if float(pct).is_integer() else pct}"] = v
        out[dim] = per_pct
    return out


# ─────────────────────────────────────────────────────────────────────────
# RFC §2.1 mapping — percentile → ExitConfig fields.
# RFC §2.1 映射 — 百分位 → ExitConfig 字段。
# ─────────────────────────────────────────────────────────────────────────


def derive_exit_config_patch(
    pct_results: dict[str, dict[str, float]],
) -> dict[str, Any]:
    """Apply RFC §2.1 mapping table; return ExitConfig patch dict.

    Mapping:
      min_net_floor_bps     ← est_net_bps p10                     (dim 1)
      min_peak_atr_norm     ← peak_pnl_pct/atr_pct ratio p25      (dim 2/3)
      giveback_base         ← giveback_atr_norm p75               (dim 4)
      giveback_floor        ← giveback_atr_norm p25               (dim 4)
      stale_peak_ms         ← time_since_peak_ms p75              (dim 5)
      min_hold_secs         ← entry_age_secs p25                  (dim 7)
      giveback_slope        ← linear interp from base/floor       (derived)

    Dim 6 (price_roc_short) NOT mapped this round.

    Returns dict with keys:
      "ipc_wired"     — 6 fields IPC can write
      "toml_only"     — `stale_peak_ms` (per IPC_WIRED_EXIT_FIELDS guard)
      "derivations"   — provenance for audit / E2 review
      "missing_pcts"  — list of (dim, pct) pairs absent from input

    依 RFC §2.1 映射；回傳 ExitConfig patch dict（含 ipc_wired / toml_only /
    derivations / missing_pcts 四 keys）。
    """
    ipc_wired: dict[str, float] = {}
    toml_only: dict[str, float | int] = {}
    derivations: list[dict[str, Any]] = []
    missing: list[tuple[str, str]] = []

    def _get(dim: str, pct_label: str) -> float | None:
        d = pct_results.get(dim, {})
        v = d.get(pct_label)
        if v is None:
            missing.append((dim, pct_label))
        return v

    # min_net_floor_bps ← est_net_bps p10
    p10_net = _get("est_net_bps", "p10")
    if p10_net is not None:
        # Floor at 0 — negative `min_net_floor_bps` violates ExitConfig validate().
        # 下限為 0 — 負值會違反 ExitConfig.validate()。
        v = max(p10_net, 0.0)
        ipc_wired["min_net_floor_bps"] = v
        derivations.append({
            "field": "min_net_floor_bps",
            "source": "est_net_bps p10",
            "raw_value": p10_net,
            "applied_value": v,
            "note": "clamped to >=0 per validate()" if v != p10_net else None,
        })

    # min_peak_atr_norm ← peak_pnl_pct/atr_pct ratio p25
    # We do NOT have a pre-computed ratio in the rows; compute it from raw rows
    # on the calling side. Here we expose the raw p25 of each — caller derives.
    # min_peak_atr_norm ← peak_pnl_pct/atr_pct 比例 p25（呼叫端用兩個 p25 合算）。
    p25_peak = _get("peak_pnl_pct", "p25")
    p25_atr = _get("atr_pct", "p25")
    if p25_peak is not None and p25_atr is not None and p25_atr > 0:
        ratio = p25_peak / p25_atr
        v = max(ratio, 0.0)
        ipc_wired["min_peak_atr_norm"] = v
        derivations.append({
            "field": "min_peak_atr_norm",
            "source": "peak_pnl_pct p25 / atr_pct p25",
            "raw_value": ratio,
            "applied_value": v,
            "note": "clamped to >=0 per validate()" if v != ratio else None,
        })

    # giveback_base ← giveback_atr_norm p75
    p75_gb = _get("giveback_atr_norm", "p75")
    if p75_gb is not None:
        # Floor at 0.001 — validate() requires giveback_base > 0.
        # 下限為 0.001 — validate() 要求 giveback_base > 0。
        v = max(p75_gb, 0.001)
        ipc_wired["giveback_base"] = v
        derivations.append({
            "field": "giveback_base",
            "source": "giveback_atr_norm p75",
            "raw_value": p75_gb,
            "applied_value": v,
            "note": "clamped to >0 per validate()" if v != p75_gb else None,
        })

    # giveback_floor ← giveback_atr_norm p25
    p25_gb = _get("giveback_atr_norm", "p25")
    if p25_gb is not None:
        # Floor at 0.001 — validate() requires giveback_floor > 0.
        # 下限為 0.001 — validate() 要求 giveback_floor > 0。
        v = max(p25_gb, 0.001)
        ipc_wired["giveback_floor"] = v
        derivations.append({
            "field": "giveback_floor",
            "source": "giveback_atr_norm p25",
            "raw_value": p25_gb,
            "applied_value": v,
            "note": "clamped to >0 per validate()" if v != p25_gb else None,
        })

    # giveback_slope ← linear interp (base − floor) / max(min_peak_atr_norm, 1.0)
    # validate() also requires giveback_floor <= giveback_base.
    # giveback_slope ← (base - floor) / max(min_peak_atr_norm, 1.0)
    if "giveback_base" in ipc_wired and "giveback_floor" in ipc_wired:
        base = ipc_wired["giveback_base"]
        floor = ipc_wired["giveback_floor"]
        if floor > base:
            # validate() invariant violation — log + clamp floor to base.
            # validate() 不變式違反 — 記錄並夾住 floor=base。
            ipc_wired["giveback_floor"] = base
            derivations.append({
                "field": "giveback_floor (rebound)",
                "source": "validate() invariant: floor must be <= base",
                "raw_value": floor,
                "applied_value": base,
                "note": "clamped to base because percentile inversion would fail validate()",
            })
            floor = base
        anchor = max(ipc_wired.get("min_peak_atr_norm", 1.0), 1.0)
        slope = (base - floor) / anchor
        v = max(slope, 0.0)  # validate() requires >= 0.
        ipc_wired["giveback_slope"] = v
        derivations.append({
            "field": "giveback_slope",
            "source": "derived: (giveback_base - giveback_floor) / max(min_peak_atr_norm, 1.0)",
            "raw_value": slope,
            "applied_value": v,
            "note": "clamped to >=0 per validate()" if v != slope else None,
        })

    # stale_peak_ms ← time_since_peak_ms p75 (TOML-only, no IPC path).
    # stale_peak_ms ← time_since_peak_ms p75（TOML-only，無 IPC 路徑）。
    p75_tsp = _get("time_since_peak_ms", "p75")
    if p75_tsp is not None:
        # Floor at 0; cast to int (column is bigint in SQL).
        # 下限 0；轉 int（SQL 欄位為 bigint）。
        v_int = max(int(p75_tsp), 0)
        toml_only["stale_peak_ms"] = v_int
        derivations.append({
            "field": "stale_peak_ms",
            "source": "time_since_peak_ms p75 (TOML-only — no IPC path)",
            "raw_value": p75_tsp,
            "applied_value": v_int,
            "note": "must be applied via TOML edit + reload_risk_config IPC",
        })

    # min_hold_secs ← entry_age_secs p25
    p25_age = _get("entry_age_secs", "p25")
    if p25_age is not None:
        # Floor at 0; validate() requires >= 0.
        # 下限 0；validate() 要求 >= 0。
        v = max(p25_age, 0.0)
        ipc_wired["min_hold_secs"] = v
        derivations.append({
            "field": "min_hold_secs",
            "source": "entry_age_secs p25",
            "raw_value": p25_age,
            "applied_value": v,
            "note": "clamped to >=0 per validate()" if v != p25_age else None,
        })

    return {
        "ipc_wired": ipc_wired,
        "toml_only": toml_only,
        "derivations": derivations,
        "missing_pcts": missing,
    }


# ─────────────────────────────────────────────────────────────────────────
# Per-strategy aggregation + sample sufficiency.
# Per-strategy 聚合 + 樣本充足性。
# ─────────────────────────────────────────────────────────────────────────


def stratify_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group rows by `strategy_name` (exact match — RFC §8 #2 stratification
    must NOT prefix-match).
    依 strategy_name 精確分組（RFC §8 #2 不可 prefix 匹配）。
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        s = row.get("strategy_name")
        if not s:
            continue
        out.setdefault(str(s), []).append(row)
    return out


def calibrate_per_strategy(
    rows_by_strategy: dict[str, list[dict[str, Any]]],
    pct_targets: list[float],
    min_samples: int,
) -> dict[str, Any]:
    """Run percentile + ExitConfig patch derivation per strategy.

    Returns:
      {
        "per_strategy": {
            <strategy>: {
              "row_count": N,
              "sufficient": bool,
              "percentiles": {dim: {pct: val}} | None,
              "patch": {ipc_wired, toml_only, derivations, missing_pcts} | None,
              "skip_reason": str | None,
            },
            ...
        },
        "summary": {
            "total_strategies": int,
            "sufficient_strategies": int,
            "total_rows": int,
            "sample_threshold": int,
        }
      }

    對每個策略執行百分位 + ExitConfig patch 計算；不足樣本量者跳過並記原因。
    """
    out: dict[str, Any] = {"per_strategy": {}, "summary": {}}
    sufficient_count = 0
    total_rows = 0
    for strategy, rows in rows_by_strategy.items():
        n = len(rows)
        total_rows += n
        if n < min_samples:
            out["per_strategy"][strategy] = {
                "row_count": n,
                "sufficient": False,
                "percentiles": None,
                "patch": None,
                "skip_reason": (
                    f"INSUFFICIENT (n={n} < min_samples={min_samples})"
                ),
            }
            continue
        sufficient_count += 1
        pct_results = compute_percentile_thresholds(rows, pct_targets)
        # ExitConfig patch needs p10/p25/p75 specifically. Ensure they exist
        # in pct_targets; otherwise add them silently for derivation use.
        # ExitConfig patch 需 p10/p25/p75；不在 pct_targets 時自動補算。
        required_pct = [10.0, 25.0, 75.0]
        if any(p not in pct_targets for p in required_pct):
            extended_pcts = sorted(set(list(pct_targets) + required_pct))
            pct_results = compute_percentile_thresholds(rows, extended_pcts)
        patch = derive_exit_config_patch(pct_results)
        out["per_strategy"][strategy] = {
            "row_count": n,
            "sufficient": True,
            "percentiles": pct_results,
            "patch": patch,
            "skip_reason": None,
        }
    out["summary"] = {
        "total_strategies": len(rows_by_strategy),
        "sufficient_strategies": sufficient_count,
        "total_rows": total_rows,
        "sample_threshold": min_samples,
    }
    return out


# ─────────────────────────────────────────────────────────────────────────
# Output renderers.
# 輸出渲染。
# ─────────────────────────────────────────────────────────────────────────


def render_markdown(
    result: dict[str, Any],
    args: argparse.Namespace,
    cohort_meta: dict[str, Any],
) -> str:
    """Render calibration result as a markdown report (operator-readable).

    渲染為 markdown 報告（給 operator 看）。
    """
    lines: list[str] = []
    ts_now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines.append(f"# EDGE-P1b 7-Dim Threshold Calibration · {ts_now}")
    lines.append("")
    lines.append(f"- engine_mode: `{args.engine_mode}`")
    lines.append(f"- strategies filter: `{args.strategies or 'ALL'}`")
    lines.append(
        f"- cohort: rolling {args.lookback_days}d minus {args.embargo_days}d embargo"
    )
    lines.append(
        f"- profit-cohort gate: `realized_net_bps > 0`"
    )
    lines.append(f"- min_samples_per_strategy: {args.min_samples_per_strategy}")
    lines.append(f"- percentile targets: {args.percentile_targets}")
    lines.append(f"- mode: {'APPLY (writes JSON patch envelope)' if args.apply else 'DRY-RUN'}")
    lines.append("")
    s = result["summary"]
    lines.append("## Summary")
    lines.append("")
    lines.append(
        f"- total strategies in cohort: **{s['total_strategies']}**"
    )
    lines.append(
        f"- strategies meeting sample threshold (≥{s['sample_threshold']}): "
        f"**{s['sufficient_strategies']}**"
    )
    lines.append(f"- total rows: **{s['total_rows']}**")
    lines.append("")
    if cohort_meta.get("orphan_count", 0) > 0:
        lines.append(
            f"- WARN: {cohort_meta['orphan_count']} rows had NULL/non-finite "
            "values across the 7 dims (excluded from percentile compute)."
        )
        lines.append("")

    lines.append("## Per-Strategy Detail")
    lines.append("")
    for strategy, det in sorted(result["per_strategy"].items()):
        lines.append(f"### `{strategy}`")
        lines.append("")
        lines.append(f"- row_count: **{det['row_count']}**")
        if not det["sufficient"]:
            lines.append(f"- status: **SKIP** — {det['skip_reason']}")
            lines.append("")
            continue
        lines.append("- status: **CALIBRATED**")
        lines.append("")

        # Percentile table
        # 百分位表
        pct_results = det["percentiles"]
        # Collect all percentile labels used.
        # 收集所有用到的百分位標籤。
        all_pcts: list[str] = []
        for dim_data in pct_results.values():
            for pct in dim_data.keys():
                if pct not in all_pcts:
                    all_pcts.append(pct)
        all_pcts.sort(key=lambda p: float(p.lstrip("p")))

        lines.append("**Percentiles per feature dim**:")
        lines.append("")
        header = "| dim | " + " | ".join(all_pcts) + " |"
        sep = "|---" * (len(all_pcts) + 1) + "|"
        lines.append(header)
        lines.append(sep)
        for dim in FEATURE_DIMS:
            row_vals = []
            for pct in all_pcts:
                v = pct_results.get(dim, {}).get(pct)
                if v is None:
                    row_vals.append("—")
                elif abs(v) >= 1e6 or (v != 0 and abs(v) < 1e-3):
                    row_vals.append(f"{v:.3e}")
                else:
                    row_vals.append(f"{v:.4f}")
            lines.append(f"| `{dim}` | " + " | ".join(row_vals) + " |")
        lines.append("")

        # ExitConfig patch
        # ExitConfig patch
        patch = det["patch"]
        lines.append("**ExitConfig patch (RFC §2.1 mapping)**:")
        lines.append("")
        lines.append("IPC-writable fields:")
        if patch["ipc_wired"]:
            for k, v in patch["ipc_wired"].items():
                lines.append(f"- `{k}`: {v}")
        else:
            lines.append("- (none derived)")
        lines.append("")
        if patch["toml_only"]:
            lines.append("TOML-only fields (no IPC path; manual edit needed):")
            for k, v in patch["toml_only"].items():
                lines.append(f"- `{k}`: {v}")
            lines.append("")
        if patch["missing_pcts"]:
            lines.append(
                f"- WARN: {len(patch['missing_pcts'])} percentile(s) missing for "
                "this strategy (insufficient samples in that dim — see derivations)"
            )
            lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- This output is informational. With `--apply`, a JSON patch envelope is "
        "emitted but NO direct IPC write happens — operator must manually approve."
    )
    lines.append(
        "- `stale_peak_ms` has no IPC write path; "
        "TOML edit + `reload_risk_config?engine=demo` is required."
    )
    lines.append(
        "- Per-strategy ExitConfig patches are SHOWN per strategy here, but the "
        "current ExitConfig schema is GLOBAL. Bind path = pick worst-case across "
        "strategies or wait for v3 per-strategy ExitConfig schema (RFC §10 #3)."
    )

    return "\n".join(lines) + "\n"


def render_json(
    result: dict[str, Any],
    args: argparse.Namespace,
    cohort_meta: dict[str, Any],
) -> str:
    """Render JSON envelope (machine-readable; basis for `--apply` patch file).
    渲染 JSON 信封（機器可讀；`--apply` patch 檔的基礎）。
    """
    envelope = {
        "schema_version": "edge_p1b.calibrator.v1",
        "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "params": {
            "engine_mode": args.engine_mode,
            "strategies_filter": args.strategies or None,
            "lookback_days": args.lookback_days,
            "embargo_days": args.embargo_days,
            "percentile_targets": args.percentile_targets,
            "min_samples_per_strategy": args.min_samples_per_strategy,
            "apply": bool(args.apply),
        },
        "cohort_meta": cohort_meta,
        "summary": result["summary"],
        "per_strategy": result["per_strategy"],
        "ipc_wired_exit_fields": sorted(IPC_WIRED_EXIT_FIELDS),
        "toml_only_exit_fields": sorted(TOML_ONLY_EXIT_FIELDS),
    }
    return json.dumps(envelope, indent=2, ensure_ascii=False, default=str) + "\n"


def render_yaml(
    result: dict[str, Any],
    args: argparse.Namespace,
    cohort_meta: dict[str, Any],
) -> str:
    """Render YAML (relies on PyYAML if available; else falls back to a
    pure-python emitter for the small dict shape we have).

    渲染 YAML（有 PyYAML 走 PyYAML，否則用內建純 python 簡易 emitter）。
    """
    envelope = json.loads(render_json(result, args, cohort_meta))
    try:
        import yaml  # type: ignore  # lazy: PyYAML is optional dep

        return yaml.safe_dump(  # type: ignore[no-any-return]
            envelope, sort_keys=False, allow_unicode=True
        )
    except ImportError:
        # Lightweight fallback: dump as JSON-style YAML (valid YAML 1.1).
        # PyYAML 缺席：用 JSON-style YAML（合法 YAML 1.1）。
        return (
            "# WARN: PyYAML not installed; emitting JSON-style YAML "
            "(install PyYAML for prettier output)\n"
            + json.dumps(envelope, indent=2, ensure_ascii=False, default=str)
            + "\n"
        )


# ─────────────────────────────────────────────────────────────────────────
# CLI plumbing + main.
# CLI 接線 + main。
# ─────────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments per PM spec.
    依 PM 派發規格解析 CLI 參數。
    """
    parser = argparse.ArgumentParser(
        prog="exit_threshold_calibrator",
        description=(
            "EDGE-P1b: Compute per-strategy 7-dim percentile thresholds "
            "from learning.exit_features and emit ExitConfig patch envelope."
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
        help="rolling lookback window in days (default 14)",
    )
    parser.add_argument(
        "--embargo-days",
        type=int,
        default=7,
        help="recent days to exclude (regime-shift embargo, default 7)",
    )
    parser.add_argument(
        "--percentile-targets",
        default="90,95,99",
        help="comma-separated percentile targets to report (default 90,95,99)",
    )
    parser.add_argument(
        "--min-samples-per-strategy",
        type=int,
        default=200,
        help="per-strategy minimum row count (default 200; <this → SKIP)",
    )
    parser.add_argument(
        "--output-format",
        default="markdown",
        choices=["markdown", "json", "yaml"],
        help="output format (default markdown)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "emit ExitConfig JSON patch envelope (NO direct IPC write — "
            "operator must manually approve via separate flow)"
        ),
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


def _validate_args(args: argparse.Namespace) -> tuple[list[float], list[str] | None]:
    """Validate / coerce CLI inputs. Returns (pct_targets, strategies_filter).
    驗證 / 強制 CLI 輸入；回傳 (pct_targets, strategies_filter)。
    """
    if args.lookback_days <= 0:
        raise SystemExit("--lookback-days must be > 0")
    if args.embargo_days < 0:
        raise SystemExit("--embargo-days must be >= 0")
    if args.embargo_days >= args.lookback_days:
        raise SystemExit(
            "--embargo-days must be < --lookback-days "
            f"(got embargo={args.embargo_days} >= lookback={args.lookback_days})"
        )
    if args.min_samples_per_strategy <= 0:
        raise SystemExit("--min-samples-per-strategy must be > 0")

    pct_raw = (args.percentile_targets or "").strip()
    if not pct_raw:
        raise SystemExit("--percentile-targets must be non-empty")
    try:
        pcts = [float(x.strip()) for x in pct_raw.split(",") if x.strip()]
    except ValueError as e:
        raise SystemExit(f"--percentile-targets parse error: {e}")
    for p in pcts:
        if not (0 < p < 100):
            raise SystemExit(f"--percentile-targets values must be in (0, 100); got {p}")

    strats = None
    if args.strategies:
        strats = [s.strip() for s in args.strategies.split(",") if s.strip()]
        if not strats:
            raise SystemExit("--strategies parsed empty after split")
    return pcts, strats


def _build_query_args(
    args: argparse.Namespace,
    strategies_filter: list[str] | None,
) -> tuple[str, list[Any]]:
    """Build (paramed SQL, args list) for PROFIT_COHORT_SQL.
    建構 PROFIT_COHORT_SQL 的 (參數化 SQL, args list)。
    """
    if strategies_filter:
        sql = PROFIT_COHORT_SQL.format(strategy_filter=STRATEGY_FILTER_TEMPLATE)
        sql_args: list[Any] = [
            args.engine_mode,
            args.lookback_days,
            args.embargo_days,
            strategies_filter,  # ANY(%s) accepts list → PG array
        ]
    else:
        sql = PROFIT_COHORT_SQL.format(strategy_filter="")
        sql_args = [args.engine_mode, args.lookback_days, args.embargo_days]
    return sql, sql_args


def _smoke_test(args: argparse.Namespace) -> int:
    """Validate SQL templates + args without DB. Exit 0 on pass, 1 on fail.
    驗證 SQL 模板 + args（不需 DB）；通過回 0、失敗回 1。
    """
    log = logging.getLogger("calibrator.smoke")
    pcts, strats = _validate_args(args)
    sql, sql_args = _build_query_args(args, strats)

    placeholder_count = sql.count("%s")
    if placeholder_count != len(sql_args):
        log.error(
            "smoke-test FAIL: SQL placeholder count %s != args count %s "
            "(SQL might inject)",
            placeholder_count,
            len(sql_args),
        )
        return 1

    # Validate percentile compute on a synthetic dataset.
    # 用合成資料集驗證百分位計算。
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
            "realized_net_bps": 1.0,
        }
        for i in range(1, 251)  # 250 rows ≥ 200 default min
    ]
    rows_by_strat = stratify_rows(fake_rows)
    result = calibrate_per_strategy(rows_by_strat, pcts, args.min_samples_per_strategy)
    if result["summary"]["sufficient_strategies"] != 1:
        log.error(
            "smoke-test FAIL: synthetic 250-row case did not yield 1 sufficient strategy "
            "(got summary=%s)",
            result["summary"],
        )
        return 1
    grid = result["per_strategy"].get("grid_trading")
    if grid is None or not grid.get("sufficient"):
        log.error("smoke-test FAIL: grid_trading not marked sufficient")
        return 1
    if not grid["patch"]["ipc_wired"]:
        log.error("smoke-test FAIL: ipc_wired patch is empty")
        return 1
    log.info(
        "smoke-test PASS: SQL placeholder count=%s args=%s; "
        "pcts=%s strategies=%s; synthetic 1-strategy 250-row → CALIBRATED",
        placeholder_count,
        len(sql_args),
        pcts,
        strats or "(ALL)",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entrypoint. Returns process exit code.
    主入口；回傳行程退出碼。
    """
    # stderr logging so stdout (markdown/json/yaml) stays clean for piping.
    # 訊息走 stderr，stdout 留乾淨給 markdown/json/yaml 管道。
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("calibrator")

    args = parse_args(argv)

    if args.smoke_test:
        return _smoke_test(args)

    pcts, strats = _validate_args(args)

    # Open PG (lazy); errors → exit 2.
    # 開 PG 連線（lazy）；錯誤 → exit 2。
    try:
        conn = _open_conn()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return 2

    try:
        cur = conn.cursor()
        sql, sql_args = _build_query_args(args, strats)
        try:
            cur.execute(sql, sql_args)
        except Exception as e:
            log.error("PROFIT_COHORT_SQL execute failed: %s", e)
            return 2
        col_names = [c.name for c in cur.description] if cur.description else []
        raw_rows = cur.fetchall()
        rows = [dict(zip(col_names, r, strict=False)) for r in raw_rows]
        log.info(
            "fetched %d rows from learning.exit_features "
            "(engine_mode=%s, lookback=%d, embargo=%d, strategies=%s)",
            len(rows),
            args.engine_mode,
            args.lookback_days,
            args.embargo_days,
            strats or "(ALL)",
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # Stratify + calibrate.
    # 分層 + 計算。
    rows_by_strategy = stratify_rows(rows)
    result = calibrate_per_strategy(rows_by_strategy, pcts, args.min_samples_per_strategy)

    cohort_meta: dict[str, Any] = {
        "rows_fetched": len(rows),
        "lookback_days": args.lookback_days,
        "embargo_days": args.embargo_days,
        "embargo_cutoff_iso": (
            f"now() - {args.embargo_days} days "
            "(SQL evaluated at fetch time; rolling boundary)"
        ),
        "engine_mode": args.engine_mode,
    }

    # Render output.
    # 渲染輸出。
    if args.output_format == "markdown":
        out_text = render_markdown(result, args, cohort_meta)
    elif args.output_format == "json":
        out_text = render_json(result, args, cohort_meta)
    elif args.output_format == "yaml":
        out_text = render_yaml(result, args, cohort_meta)
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

    # Exit-code policy per PM spec:
    # - 0 = ≥1 strategy met threshold (calibration usable)
    # - 1 = no strategy met threshold (insufficient — defer bind)
    # PM 規格的退出碼策略：≥1 策略達門檻 → 0；無 → 1。
    if result["summary"]["sufficient_strategies"] == 0:
        log.warning(
            "no strategy met sample threshold (>= %d) — defer bind, "
            "wait for more rows to accumulate",
            args.min_samples_per_strategy,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
