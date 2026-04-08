"""
James-Stein Shrinkage Estimator for cross-symbol partial pooling.
James-Stein 收縮估計器，用於跨幣種部分池化。

MODULE_NOTE (EN): Phase 5 P0 (2026-04-08 Edge Crisis). Takes per-(strategy, symbol) realized
  edge estimates (from realized_edge_stats.py), applies James-Stein shrinkage toward the
  universe grand mean, writes shrunk estimates to learning.james_stein_estimates (PG), and
  emits a JSON snapshot for hot-reloading into the Rust cost_gate (PH5-WIRE-1).
MODULE_NOTE (中): Phase 5 P0（Edge 危機）。接受 realized_edge_stats.py 的每 (策略, 幣種) 實現邊際，
  應用 James-Stein 收縮朝全域均值，寫入 learning.james_stein_estimates，並輸出 JSON 快照
  供 Rust cost_gate 熱重載（PH5-WIRE-1）。

James-Stein formula (positive-part, per parameter j):
  shrunk_j = grand_mean_j + (1 - B_j) * (raw_j - grand_mean_j)
  B_j = min(1, (p - 2) / n * sigma²_j / ||raw - grand_mean||²_j)

where:
  p  = number of groups (symbols × strategies sharing same param)
  n  = total observations across all groups
  sigma²_j = pooled within-group variance for param j

Usage / 使用：
    python -m program_code.ml_training.james_stein_estimator [--days N] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB helpers / 數據庫工具
# ---------------------------------------------------------------------------

def _get_db_conn():
    """psycopg2 connection from environment. / 從環境變量建立 psycopg2 連接。"""
    import psycopg2  # type: ignore[import]

    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "localhost"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DB", "trading_ai"),
        user=os.environ.get("PG_USER", "trading_admin"),
        password=os.environ.get("PG_PASSWORD", ""),
    )


# ---------------------------------------------------------------------------
# James-Stein core math / James-Stein 核心數學
# ---------------------------------------------------------------------------

def _js_shrinkage(
    raw_values: list[float],
    within_group_vars: list[float],
    grand_mean: float,
) -> list[float]:
    """
    Apply James-Stein positive-part shrinkage to a list of per-group estimates.
    對一組每組估計應用 James-Stein 正部收縮。

    Args:
        raw_values: Per-group raw estimates (e.g. mean_net_bps per cell). / 每組原始估計。
        within_group_vars: Per-group variance estimate (sigma² / n_i). / 每組方差估計。
        grand_mean: Target shrinkage point (universe mean). / 收縮目標（全域均值）。

    Returns:
        Shrunk estimates (same length as raw_values). / 收縮後估計。
    """
    p = len(raw_values)
    if p < 3:
        # JS undefined for p < 3; return raw values unchanged
        # JS 在 p < 3 時未定義，返回原始值
        logger.warning("James-Stein requires p >= 3 groups; returning raw values (p=%d)", p)
        return raw_values[:]

    # ||raw - grand_mean||² (sum of squared deviations from grand mean)
    sq_sum = sum((x - grand_mean) ** 2 for x in raw_values)
    if sq_sum < 1e-12:
        # All values identical → no shrinkage needed
        return raw_values[:]

    # Pooled within-group variance (weighted average)
    pooled_var = sum(within_group_vars) / p

    # Shrinkage factor B (positive-part: clamp to [0, 1])
    # B = (p - 2) * pooled_var / ||raw - grand_mean||²
    B = (p - 2) * pooled_var / sq_sum
    B = max(0.0, min(1.0, B))  # positive-part shrinkage / 正部收縮

    shrunk = [grand_mean + (1.0 - B) * (x - grand_mean) for x in raw_values]

    logger.debug(
        "JS shrinkage: p=%d grand_mean=%.3f bps pooled_var=%.4f sq_sum=%.4f B=%.4f",
        p, grand_mean, pooled_var, sq_sum, B,
    )
    return shrunk


# ---------------------------------------------------------------------------
# Main estimation logic / 主估計邏輯
# ---------------------------------------------------------------------------

def _shrink_and_attach(
    results: dict,
    stats: dict,
    keys: list,
    param_name: str,
    value_fn,
    var_fn,
) -> None:
    """
    Run JS shrinkage on one parameter across all cells; attach shrunk values to results.
    對所有格子的單個參數執行 JS 收縮，並將收縮值附加到結果中。

    Skips gracefully when p < 3 (JS undefined). Attaches `{param_name}_shrunk` key.
    p < 3 時優雅跳過（JS 未定義）。附加 `{param_name}_shrunk` 鍵。
    """
    raw = [value_fn(stats[k]) for k in keys]
    within_vars = [var_fn(stats[k]) for k in keys]
    grand = sum(raw) / len(raw) if raw else 0.0
    shrunk = _js_shrinkage(raw, within_vars, grand)
    for i, k in enumerate(keys):
        results[k][f"{param_name}_shrunk"] = round(shrunk[i], 6)
    logger.debug("JS per-param shrinkage '%s': grand=%.4f", param_name, grand)


def run_james_stein(
    days_back: int = 30,
    min_samples: int = 3,
    snapshot_path: Optional[str] = None,
) -> dict[tuple[str, str], dict]:
    """
    Full pipeline: query fills → compute edge stats → JS shrinkage → write to PG + JSON.
    完整管線：查詢成交 → 計算邊際統計 → JS 收縮 → 寫入 PG + JSON。

    Returns:
        Dict mapping (strategy_name, symbol) → {raw_bps, shrunk_bps, B_factor, n}.
    """
    from .realized_edge_stats import compute_edge_stats

    stats = compute_edge_stats(days_back=days_back, min_samples=min_samples)

    if not stats:
        logger.warning("No edge stats available — aborting JS estimation.")
        return {}

    # ── Build per-cell arrays ──
    keys = list(stats.keys())
    raw_values = [stats[k].mean_net_bps for k in keys]
    # Variance estimate per cell: std² / n (standard error of mean)
    within_vars = []
    for k in keys:
        es = stats[k]
        if es.n >= 2:
            # sample variance of the mean = std² / n
            var = (es.std_net_bps ** 2) / es.n
        else:
            # single observation — use a broad prior variance (100 bps²)
            var = 100.0
        within_vars.append(var)

    # Grand mean (unweighted across cells — per-parameter independent shrinkage)
    # 全域均值（跨格子的未加權均值）
    grand_mean = sum(raw_values) / len(raw_values)

    # Apply JS shrinkage
    shrunk_values = _js_shrinkage(raw_values, within_vars, grand_mean)

    # Compute shrinkage factors B_j per cell for reporting
    sq_sum = sum((x - grand_mean) ** 2 for x in raw_values)
    pooled_var = sum(within_vars) / len(within_vars) if within_vars else 0.0
    p = len(raw_values)
    B_global = max(0.0, min(1.0, (p - 2) * pooled_var / sq_sum)) if sq_sum > 1e-12 and p >= 3 else 0.0

    results: dict[tuple[str, str], dict] = {}
    for i, k in enumerate(keys):
        (strategy, symbol) = k
        es = stats[k]
        results[k] = {
            "strategy_name": strategy,
            "symbol": symbol,
            "raw_bps": raw_values[i],
            "shrunk_bps": shrunk_values[i],
            "grand_mean_bps": grand_mean,
            "shrinkage_factor_B": B_global,
            "n_observations": es.n,
            # 5-01: raw per-parameter values for multi-dimensional shrinkage.
            # 5-01：用於多維收縮的逐參數原始值。
            "win_rate": es.win_rate,
            "avg_win_bps": es.avg_win_bps,
            "avg_loss_bps": es.avg_loss_bps,
        }

    logger.info(
        "JS shrinkage complete: %d cells, grand_mean=%.2f bps, B=%.3f",
        len(results), grand_mean, B_global,
    )
    for k, r in results.items():
        logger.info(
            "  (%s, %s): raw=%.2f bps → shrunk=%.2f bps (n=%d, win_rate=%.2f)",
            k[0], k[1], r["raw_bps"], r["shrunk_bps"], r["n_observations"], r["win_rate"],
        )

    # 5-01: Run JS shrinkage on win_rate, avg_win_bps, avg_loss_bps independently.
    # 5-01：對勝率、平均盈利、平均虧損分別進行 JS 收縮。
    _shrink_and_attach(results, stats, keys, "win_rate",
                       lambda es: es.win_rate, lambda es: es.win_rate * (1 - es.win_rate) / max(es.n, 1))
    _shrink_and_attach(results, stats, keys, "avg_win_bps",
                       lambda es: es.avg_win_bps, lambda es: (es.std_net_bps ** 2) / max(es.n, 1))
    _shrink_and_attach(results, stats, keys, "avg_loss_bps",
                       lambda es: es.avg_loss_bps, lambda es: (es.std_net_bps ** 2) / max(es.n, 1))

    # Compute combined EV from shrunk components (win_rate * avg_win + (1-win_rate) * avg_loss).
    # 從收縮分量計算合成 EV（勝率 * 均盈 + (1-勝率) * 均虧）。
    for k in results:
        wr = results[k].get("win_rate_shrunk", results[k]["win_rate"])
        aw = results[k].get("avg_win_bps_shrunk", results[k]["avg_win_bps"])
        al = results[k].get("avg_loss_bps_shrunk", results[k]["avg_loss_bps"])
        results[k]["combined_ev_bps"] = round(wr * aw + (1.0 - wr) * al, 4)
        logger.info(
            "  (%s, %s): combined_ev=%.2f bps (wr=%.2f avg_win=%.2f avg_loss=%.2f)",
            k[0], k[1], results[k]["combined_ev_bps"], wr, aw, al,
        )

    # ── Write to Postgres ──
    _write_to_postgres(results)

    # ── Write JSON snapshot ──
    if snapshot_path is None:
        snapshot_path = os.environ.get(
            "OPENCLAW_EDGE_SNAPSHOT",
            os.path.join(
                os.path.dirname(__file__),
                "..", "..", "settings", "edge_estimates.json",
            ),
        )
        # Resolves to srv/settings/edge_estimates.json
        # 解析為 srv/settings/edge_estimates.json

    _write_json_snapshot(results, snapshot_path)

    return results


# ---------------------------------------------------------------------------
# Postgres write / Postgres 寫入
# ---------------------------------------------------------------------------

_UPSERT_SQL = """
INSERT INTO learning.james_stein_estimates
    (strategy_name, symbol, param_name, raw_estimate, shrunk_estimate,
     shrinkage_factor, grand_mean, n_observations, last_updated_ts)
VALUES
    (%(strategy_name)s, %(symbol)s, %(param_name)s, %(raw_estimate)s,
     %(shrunk_estimate)s, %(shrinkage_factor)s, %(grand_mean)s,
     %(n_observations)s, %(last_updated_ts)s)
ON CONFLICT (strategy_name, symbol, param_name)
DO UPDATE SET
    raw_estimate      = EXCLUDED.raw_estimate,
    shrunk_estimate   = EXCLUDED.shrunk_estimate,
    shrinkage_factor  = EXCLUDED.shrinkage_factor,
    grand_mean        = EXCLUDED.grand_mean,
    n_observations    = EXCLUDED.n_observations,
    last_updated_ts   = EXCLUDED.last_updated_ts
"""


def _write_to_postgres(results: dict[tuple[str, str], dict]) -> None:
    """
    UPSERT James-Stein estimates into learning.james_stein_estimates.
    UPSERT James-Stein 估計到 learning.james_stein_estimates。

    param_name = 'realized_edge_bps' (the specific parameter we're estimating).
    param_name = 'realized_edge_bps'（正在估計的參數）。
    """
    if not results:
        return

    now = datetime.now(tz=timezone.utc)
    rows = []
    for (strategy, symbol), r in results.items():
        # Primary: realized edge bps (shrunk) / 主要：實現邊際 bps（收縮）
        rows.append({
            "strategy_name": strategy,
            "symbol": symbol,
            "param_name": "realized_edge_bps",
            "raw_estimate": r["raw_bps"],
            "shrunk_estimate": r["shrunk_bps"],
            "shrinkage_factor": r["shrinkage_factor_B"],
            "grand_mean": r["grand_mean_bps"],
            "n_observations": r["n_observations"],
            "last_updated_ts": now,
        })
        # 5-01: Per-parameter rows / 5-01：逐參數行
        for param_key, raw_key, shrunk_key in [
            ("win_rate", "win_rate", "win_rate_shrunk"),
            ("avg_win_bps", "avg_win_bps", "avg_win_bps_shrunk"),
            ("avg_loss_bps", "avg_loss_bps", "avg_loss_bps_shrunk"),
        ]:
            rows.append({
                "strategy_name": strategy,
                "symbol": symbol,
                "param_name": param_key,
                "raw_estimate": r.get(raw_key, 0.0),
                "shrunk_estimate": r.get(shrunk_key, r.get(raw_key, 0.0)),
                "shrinkage_factor": r["shrinkage_factor_B"],
                "grand_mean": r.get(raw_key, 0.0),  # grand mean per param
                "n_observations": r["n_observations"],
                "last_updated_ts": now,
            })

    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.executemany(_UPSERT_SQL, rows)
        conn.commit()
        logger.info("Upserted %d JS estimate rows to learning.james_stein_estimates", len(rows))
    except Exception:
        conn.rollback()
        logger.exception("Failed to write JS estimates to Postgres")
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# JSON snapshot for Rust hot-reload / JSON 快照供 Rust 熱重載
# ---------------------------------------------------------------------------

def _write_json_snapshot(
    results: dict[tuple[str, str], dict],
    path: str,
) -> None:
    """
    Write a compact JSON snapshot for Rust cost_gate hot-reload (PH5-WIRE-1).
    Format: {"strategy::symbol": {"shrunk_bps": X, "n": N, "updated_at": ISO}, ...}
    寫入 JSON 快照供 Rust cost_gate 熱重載（PH5-WIRE-1）。
    """
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    snapshot: dict = {
        "_meta": {
            "updated_at": now_iso,
            "n_cells": len(results),
            "grand_mean_bps": results[next(iter(results))]["grand_mean_bps"] if results else 0.0,
        }
    }
    for (strategy, symbol), r in results.items():
        key = f"{strategy}::{symbol}"
        snapshot[key] = {
            # Primary signal for Rust cost_gate (WIRE-1): shrunk realized edge bps.
            # Rust cost_gate 主信號（WIRE-1）：收縮實現邊際 bps。
            "shrunk_bps": round(r["shrunk_bps"], 4),
            "raw_bps": round(r["raw_bps"], 4),
            "n": r["n_observations"],
            "B": round(r["shrinkage_factor_B"], 4),
            # 5-01: Per-parameter shrunk values for k-means clustering.
            # 5-01：用於 k-means 聚類的逐參數收縮值。
            "win_rate": round(r.get("win_rate", 0.0), 4),
            "win_rate_shrunk": round(r.get("win_rate_shrunk", r.get("win_rate", 0.0)), 4),
            "avg_win_bps_shrunk": round(r.get("avg_win_bps_shrunk", r.get("avg_win_bps", 0.0)), 4),
            "avg_loss_bps_shrunk": round(r.get("avg_loss_bps_shrunk", r.get("avg_loss_bps", 0.0)), 4),
            "combined_ev_bps": round(r.get("combined_ev_bps", r["shrunk_bps"]), 4),
        }

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(snapshot, f, indent=2)
    os.replace(tmp, path)  # atomic rename / 原子重命名
    logger.info("Edge snapshot written to %s (%d cells)", path, len(results))


# ---------------------------------------------------------------------------
# CLI entry point / CLI 入口
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compute James-Stein shrunk realized edge estimates."
    )
    p.add_argument("--days", type=int, default=30, help="Days of history to query (default 30)")
    p.add_argument("--min-samples", type=int, default=3, help="Min round-trips per cell (default 3)")
    p.add_argument("--out", type=str, default=None, help="JSON snapshot output path")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    """CLI entry point. / CLI 入口。"""
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    results = run_james_stein(
        days_back=args.days,
        min_samples=args.min_samples,
        snapshot_path=args.out,
    )

    if results:
        print(json.dumps(
            {f"{s}::{sym}": {"shrunk_bps": round(r["shrunk_bps"], 4), "n": r["n_observations"]}
             for (s, sym), r in results.items()},
            indent=2,
        ))
    else:
        print("{}")


if __name__ == "__main__":
    main()
