#!/usr/bin/env python3
"""Phase 1a C readiness monitor.
Phase 1a C 資料就緒監控。

MODULE_NOTE (EN): Two views side-by-side:
  (1) Per-slice (engine_mode × strategy × symbol) labeled counts + 24h rate +
      ETA to min_samples. Answers "which exact slice is first to 200?".
  (2) Per-strategy pooled aggregate (engine_mode × strategy) — total labels
      across all symbols. Answers "is the strategy-wide pooled total already
      enough to train?". Critical for grid_trading which rotates across
      short-lived symbols (per-symbol never reaches 200; pooled does).
Phase 1a C (P1-7 C) originally required ≥1 per-slice ≥ min_samples before
run_training_pipeline.py could emit a non-trivial ONNX. As of 2026-04-23
pooled-training is the preferred path for grid_trading, so the pooled view
is the primary go/no-go signal.

MODULE_NOTE (中): 兩段視圖並列：
  (1) 逐切片（engine_mode × strategy × symbol）已標籤數 + 24h 速率 + 到 200 ETA。
      回答「哪個切片最先達 200？」。
  (2) 逐策略 pooled 聚合（engine_mode × strategy）— 跨所有 symbol 合計。
      回答「策略層面 pooled 總量夠不夠訓練？」。對 grid_trading（symbol 輪動，
      單一 symbol 永遠到不了 200；pooled 合計已可達）尤其關鍵。
2026-04-23 起 grid_trading 採 pooled-training 首選路徑，pooled 視圖即主要
go/no-go 信號。

Usage:
  POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=... \\
    python3 helper_scripts/db/phase1a_c_readiness.py [--min-samples 200] [--engine-mode demo]
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone


_PER_SLICE_SQL = """
WITH rates_24h AS (
    SELECT engine_mode, strategy_name, symbol,
           COUNT(*) FILTER (WHERE label_net_edge_bps IS NOT NULL
                            AND label_filled_at > now() - interval '24 hours') AS labels_24h
    FROM learning.decision_features
    GROUP BY 1, 2, 3
)
SELECT df.engine_mode, df.strategy_name, df.symbol,
       COUNT(*) FILTER (WHERE df.label_net_edge_bps IS NOT NULL) AS labeled,
       COUNT(*) AS total,
       COALESCE(r.labels_24h, 0) AS labels_24h
FROM learning.decision_features df
LEFT JOIN rates_24h r USING (engine_mode, strategy_name, symbol)
WHERE (%(engine_mode)s IS NULL OR df.engine_mode = %(engine_mode)s)
GROUP BY df.engine_mode, df.strategy_name, df.symbol, r.labels_24h
HAVING COUNT(*) FILTER (WHERE df.label_net_edge_bps IS NOT NULL) > 0
ORDER BY labeled DESC
"""


# Per-strategy pooled view: collapse symbols within (engine_mode, strategy) —
# useful when training config uses symbol=None (pool all symbols for the
# strategy, e.g. grid_trading rotating across short-lived symbols).
# 逐策略 pooled 視圖：聚合 (engine_mode, strategy) 下所有 symbol；供 pooled
# 訓練（symbol=None，跨所有 symbol 合計）決策使用。
_PER_STRATEGY_SQL = """
WITH rates_24h AS (
    SELECT engine_mode, strategy_name,
           COUNT(*) FILTER (WHERE label_net_edge_bps IS NOT NULL
                            AND label_filled_at > now() - interval '24 hours') AS labels_24h
    FROM learning.decision_features
    GROUP BY 1, 2
)
SELECT df.engine_mode, df.strategy_name,
       COUNT(*) FILTER (WHERE df.label_net_edge_bps IS NOT NULL) AS labeled,
       COUNT(*) AS total,
       COUNT(DISTINCT df.symbol) FILTER (WHERE df.label_net_edge_bps IS NOT NULL) AS n_symbols,
       COALESCE(r.labels_24h, 0) AS labels_24h
FROM learning.decision_features df
LEFT JOIN rates_24h r USING (engine_mode, strategy_name)
WHERE (%(engine_mode)s IS NULL OR df.engine_mode = %(engine_mode)s)
GROUP BY df.engine_mode, df.strategy_name, r.labels_24h
HAVING COUNT(*) FILTER (WHERE df.label_net_edge_bps IS NOT NULL) > 0
ORDER BY labeled DESC
"""


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


def _print_per_slice(rows, min_samples: int) -> int:
    """Print per-slice view. Returns count of slices already ≥ min_samples.
    輸出逐切片視圖；回傳已達 min_samples 的切片數。"""
    print("── Per-slice (engine_mode × strategy × symbol) ──")
    if not rows:
        print("(no labeled rows yet — run edge_label_backfill first)")
        return 0

    print(f"{'engine_mode':<12} {'strategy':<18} {'symbol':<14} {'labeled':>8} "
          f"{'total':>8} {'24h':>6} {'to_target':>10} {'ETA_hrs':>10}")
    print("-" * 98)
    ready = 0
    for em, strat, sym, labeled, total, r24 in rows:
        to_target = max(0, min_samples - labeled)
        if to_target == 0:
            eta = "READY"
            ready += 1
        elif r24 <= 0:
            eta = "∞ (0/24h)"
        else:
            eta_hrs = to_target / (r24 / 24.0)
            eta = f"{eta_hrs:>8.1f}h"
        print(f"{em:<12} {strat:<18} {sym:<14} {labeled:>8} {total:>8} "
              f"{r24:>6} {to_target:>10} {eta:>10}")
    print("-" * 98)
    print(f"Slices already ≥{min_samples}: {ready}")
    return ready


def _print_per_strategy(rows, min_samples: int) -> int:
    """Print per-strategy pooled view. Returns count of strategies pooled ≥ min_samples.
    輸出逐策略 pooled 視圖；回傳已達 min_samples 的策略數。"""
    print()
    print("── Per-strategy (pooled across all symbols) ──")
    if not rows:
        print("(no labeled rows yet)")
        return 0

    print(f"{'engine_mode':<12} {'strategy':<18} {'labeled':>8} {'total':>8} "
          f"{'#sym':>6} {'24h':>6} {'to_target':>10} {'ETA_hrs':>10}")
    print("-" * 90)
    ready = 0
    for em, strat, labeled, total, n_sym, r24 in rows:
        to_target = max(0, min_samples - labeled)
        if to_target == 0:
            eta = "READY"
            ready += 1
        elif r24 <= 0:
            eta = "∞ (0/24h)"
        else:
            eta_hrs = to_target / (r24 / 24.0)
            eta = f"{eta_hrs:>8.1f}h"
        print(f"{em:<12} {strat:<18} {labeled:>8} {total:>8} {n_sym:>6} "
              f"{r24:>6} {to_target:>10} {eta:>10}")
    print("-" * 90)
    print(f"Strategies pooled ≥{min_samples}: {ready}")
    return ready


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-samples", type=int, default=200,
                    help="Target threshold (default 200; matches PipelineConfig.min_samples)")
    ap.add_argument("--engine-mode", default=None,
                    help="Filter to one engine_mode (demo/live_demo/paper/live); default = all")
    args = ap.parse_args()

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(_PER_SLICE_SQL, {"engine_mode": args.engine_mode})
            slice_rows = cur.fetchall()
            cur.execute(_PER_STRATEGY_SQL, {"engine_mode": args.engine_mode})
            strategy_rows = cur.fetchall()
    finally:
        conn.close()

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    header = f"Phase 1a C readiness @ {now} UTC (min_samples={args.min_samples})"
    print(header)
    print("=" * len(header))

    per_slice_ready = _print_per_slice(slice_rows, args.min_samples)
    per_strategy_ready = _print_per_strategy(strategy_rows, args.min_samples)

    # Exit code: 0 iff ≥1 training path is go (either per-slice or pooled).
    # Pooled-mode is now the preferred training path for multi-symbol
    # strategies (grid_trading rotation), so per_strategy_ready satisfies the
    # gate on its own.
    # Exit code：per-slice 或 pooled 任一就緒即 0；pooled 為 grid_trading 類
    # 多 symbol 策略的首選訓練路徑，pooled_ready 即可通過 gate。
    any_ready = per_slice_ready + per_strategy_ready
    return 0 if any_ready > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
