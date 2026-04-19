#!/usr/bin/env python3
"""Phase 1a C readiness monitor.
Phase 1a C 資料就緒監控。

MODULE_NOTE (EN): Query per-slice (engine_mode × strategy × symbol) labeled
counts in learning.decision_features, then project ETA to min_samples=200
based on last-24h fill rate. Phase 1a C (P1-7 C) requires ≥1 slice crossing
200 before run_training_pipeline.py can emit a non-trivial ONNX artifact.
MODULE_NOTE (中): 查詢逐切片已標籤 rows + 依最近 24h 速率預估達 200 的 ETA；
Phase 1a C 需要 ≥1 切片過 200 才能訓首個有意義的 ONNX。

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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-samples", type=int, default=200,
                    help="Target threshold per slice (default 200; matches PipelineConfig.min_samples)")
    ap.add_argument("--engine-mode", default=None,
                    help="Filter to one engine_mode (demo/live_demo/paper/live); default = all")
    args = ap.parse_args()

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(_PER_SLICE_SQL, {"engine_mode": args.engine_mode})
            rows = cur.fetchall()
    finally:
        conn.close()

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    header = f"Phase 1a C readiness @ {now} UTC (min_samples={args.min_samples})"
    print(header)
    print("=" * len(header))
    if not rows:
        print("(no labeled rows yet — run edge_label_backfill first)")
        return 0

    print(f"{'engine_mode':<12} {'strategy':<18} {'symbol':<14} {'labeled':>8} "
          f"{'total':>8} {'24h':>6} {'to_200':>8} {'ETA_hrs':>10}")
    print("-" * 98)
    ready_slices = 0
    for em, strat, sym, labeled, total, r24 in rows:
        to_target = max(0, args.min_samples - labeled)
        if to_target == 0:
            eta = "READY"
            ready_slices += 1
        elif r24 <= 0:
            eta = "∞ (0/24h)"
        else:
            eta_hrs = to_target / (r24 / 24.0)
            eta = f"{eta_hrs:>8.1f}h"
        print(f"{em:<12} {strat:<18} {sym:<14} {labeled:>8} {total:>8} "
              f"{r24:>6} {to_target:>8} {eta:>10}")
    print("-" * 98)
    print(f"Slices already ≥{args.min_samples}: {ready_slices}")
    return 0 if ready_slices > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
