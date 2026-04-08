"""
Edge Cluster Analysis — k-means clustering on JS shrunk estimates (Phase 5 5-02~03).
邊際聚類分析 — 對 JS 收縮估計進行 k-means 聚類（Phase 5 5-02~03）。

MODULE_NOTE (EN): Phase 5 5-02~03 (2026-04-08). Loads the JS snapshot
  (edge_estimates.json) and/or learning.james_stein_estimates from PG,
  computes multi-dimensional features per (strategy, symbol) cell, performs
  k-means clustering (k=2 or 3) to partition cells into edge-quality tiers,
  ranks all pairs by estimated edge, and writes recommendations to
  settings/edge_clusters.json. Helps operator identify which (strategy, symbol)
  pairs are "least bad" (candidates for priority exploration) vs "most bad"
  (candidates for deprioritization or eventual filtering in live mode).

MODULE_NOTE (中): Phase 5 5-02~03（2026-04-08）。加載 JS 快照（edge_estimates.json）
  或 PG 的 learning.james_stein_estimates，計算每 (策略, 幣種) 格子的多維特徵，
  執行 k-means 聚類（k=2 或 3）將格子分成邊際質量層次，排名所有交易對，
  並將建議寫入 settings/edge_clusters.json。幫助 operator 識別「最不差」
  （優先探索候選）和「最差」（降優先或 live 模式過濾候選）的 (策略, 幣種) 對。

Usage / 使用：
    python -m program_code.ml_training.edge_cluster_analysis [--snapshot PATH]
    python -m program_code.ml_training.edge_cluster_analysis --from-pg [--days N]
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures / 數據結構
# ---------------------------------------------------------------------------

@dataclass
class CellFeatures:
    """
    Multi-dimensional feature vector for one (strategy, symbol) cell.
    單個 (策略, 幣種) 格子的多維特徵向量。
    """
    key: str                    # "strategy::symbol"
    shrunk_bps: float           # JS shrunk realized edge / JS 收縮實現邊際
    combined_ev_bps: float      # Kelly-style EV from win_rate × avg_win + ... / 合成 EV
    win_rate: float             # fraction of winning round-trips / 盈利往返佔比
    avg_win_bps: float          # mean win bps (shrunk) / 平均盈利 bps（收縮）
    avg_loss_bps: float         # mean loss bps (shrunk, typically negative) / 平均虧損 bps（收縮）
    n: int                      # number of round-trips observed / 觀測往返數


@dataclass
class ClusterResult:
    """
    Output for one (strategy, symbol) cell after clustering.
    聚類後單個 (策略, 幣種) 格子的輸出。
    """
    key: str
    strategy: str
    symbol: str
    shrunk_bps: float
    combined_ev_bps: float
    win_rate: float
    n: int
    cluster: int                    # k-means cluster id (0-based) / k-means 聚類 id
    cluster_label: str              # "candidate" | "underperformer" | "middle"
    rank_overall: int               # 1 = best edge (least negative) / 1 = 最優 edge


# ---------------------------------------------------------------------------
# Feature loading / 特徵加載
# ---------------------------------------------------------------------------

def load_from_snapshot(path: str) -> list[CellFeatures]:
    """
    Load features from the JSON snapshot (settings/edge_estimates.json).
    從 JSON 快照（settings/edge_estimates.json）加載特徵。
    """
    with open(path) as f:
        data = json.load(f)

    cells = []
    for key, val in data.items():
        if key.startswith("_"):
            continue
        cells.append(CellFeatures(
            key=key,
            shrunk_bps=val.get("shrunk_bps", 0.0),
            combined_ev_bps=val.get("combined_ev_bps", val.get("shrunk_bps", 0.0)),
            win_rate=val.get("win_rate_shrunk", val.get("win_rate", 0.0)),
            avg_win_bps=val.get("avg_win_bps_shrunk", 0.0),
            avg_loss_bps=val.get("avg_loss_bps_shrunk", 0.0),
            n=val.get("n", 0),
        ))
    logger.info("Loaded %d cells from snapshot %s", len(cells), path)
    return cells


def load_from_postgres(days_back: int = 30) -> list[CellFeatures]:
    """
    Load features from learning.james_stein_estimates in Postgres.
    從 Postgres learning.james_stein_estimates 加載特徵。
    """
    import psycopg2  # type: ignore[import]
    import os

    conn = psycopg2.connect(
        host=os.environ.get("PG_HOST", "localhost"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DB", "trading_ai"),
        user=os.environ.get("PG_USER", "trading_admin"),
        password=os.environ.get("PG_PASSWORD", ""),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT strategy_name, symbol, param_name, shrunk_estimate, n_observations
                FROM learning.james_stein_estimates
                WHERE last_updated_ts >= NOW() - INTERVAL '%s days'
                ORDER BY strategy_name, symbol, param_name
            """, (days_back,))
            rows = cur.fetchall()
    finally:
        conn.close()

    # Pivot: (strategy, symbol) → {param_name: shrunk_estimate}
    pivot: dict[str, dict] = {}
    for strategy, symbol, param, shrunk, n in rows:
        key = f"{strategy}::{symbol}"
        if key not in pivot:
            pivot[key] = {"n": n}
        pivot[key][param] = shrunk

    cells = []
    for key, vals in pivot.items():
        wr = vals.get("win_rate", 0.0)
        aw = vals.get("avg_win_bps", 0.0)
        al = vals.get("avg_loss_bps", 0.0)
        cells.append(CellFeatures(
            key=key,
            shrunk_bps=vals.get("realized_edge_bps", 0.0),
            combined_ev_bps=round(wr * aw + (1.0 - wr) * al, 4),
            win_rate=wr,
            avg_win_bps=aw,
            avg_loss_bps=al,
            n=vals.get("n", 0),
        ))
    logger.info("Loaded %d cells from Postgres (last %d days)", len(cells), days_back)
    return cells


# ---------------------------------------------------------------------------
# K-means clustering (no sklearn dependency) / k-means 聚類（無 sklearn 依賴）
# ---------------------------------------------------------------------------

def _normalize_features(cells: list[CellFeatures]) -> list[list[float]]:
    """
    Build normalized feature matrix for k-means.
    Features: [shrunk_bps_norm, win_rate, combined_ev_bps_norm]
    構建 k-means 的歸一化特徵矩陣。
    特徵：[shrunk_bps_norm, win_rate, combined_ev_bps_norm]
    """
    shrunk_vals = [c.shrunk_bps for c in cells]
    ev_vals = [c.combined_ev_bps for c in cells]

    def _min_max(vals: list[float]) -> tuple[float, float]:
        lo, hi = min(vals), max(vals)
        return lo, hi if hi != lo else lo + 1.0

    s_lo, s_hi = _min_max(shrunk_vals)
    ev_lo, ev_hi = _min_max(ev_vals)

    features = []
    for c in cells:
        features.append([
            (c.shrunk_bps - s_lo) / (s_hi - s_lo),  # normalized shrunk_bps
            c.win_rate,                               # already in [0,1]
            (c.combined_ev_bps - ev_lo) / (ev_hi - ev_lo),  # normalized combined_ev
        ])
    return features


def _euclidean(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _kmeans(features: list[list[float]], k: int, max_iter: int = 100) -> list[int]:
    """
    Simple Lloyd's k-means on a small feature matrix.
    Returns cluster assignments (0-based).
    對小型特徵矩陣的簡單 Lloyd k-means。返回聚類分配（0-based）。
    """
    n = len(features)
    if n <= k:
        return list(range(n))

    # Initialize centroids: spread across sorted dimension 0
    # 初始化質心：沿維度 0 排序分散
    sorted_idx = sorted(range(n), key=lambda i: features[i][0])
    step = n // k
    centroids = [features[sorted_idx[i * step]] for i in range(k)]

    labels = [0] * n
    for _ in range(max_iter):
        # Assignment step / 分配步驟
        new_labels = [
            min(range(k), key=lambda j: _euclidean(features[i], centroids[j]))
            for i in range(n)
        ]
        if new_labels == labels:
            break
        labels = new_labels

        # Update step / 更新步驟
        for j in range(k):
            members = [features[i] for i in range(n) if labels[i] == j]
            if members:
                centroids[j] = [sum(m[d] for m in members) / len(members)
                                 for d in range(len(features[0]))]
    return labels


def _label_clusters(cells: list[CellFeatures], labels: list[int], k: int) -> list[str]:
    """
    Name clusters by their mean shrunk_bps: best = "candidate", worst = "underperformer".
    按均值 shrunk_bps 命名聚類：最好 = "candidate"，最差 = "underperformer"。
    """
    cluster_means: dict[int, float] = {}
    cluster_counts: dict[int, int] = {}
    for i, c in enumerate(cells):
        j = labels[i]
        cluster_means[j] = cluster_means.get(j, 0.0) + c.shrunk_bps
        cluster_counts[j] = cluster_counts.get(j, 0) + 1
    for j in cluster_means:
        cluster_means[j] /= cluster_counts[j]

    # Rank clusters: 0 = highest mean = "candidate"
    ranked = sorted(cluster_means, key=lambda j: cluster_means[j], reverse=True)

    label_names: dict[int, str] = {}
    for rank, j in enumerate(ranked):
        if rank == 0:
            label_names[j] = "candidate"
        elif rank == len(ranked) - 1:
            label_names[j] = "underperformer"
        else:
            label_names[j] = "middle"

    return [label_names[labels[i]] for i in range(len(cells))]


# ---------------------------------------------------------------------------
# Main analysis / 主分析
# ---------------------------------------------------------------------------

def run_cluster_analysis(
    cells: list[CellFeatures],
    k: Optional[int] = None,
    output_path: Optional[str] = None,
) -> list[ClusterResult]:
    """
    Run k-means clustering + ranking on the given cells, write JSON output.
    對給定格子執行 k-means 聚類 + 排名，寫入 JSON 輸出。

    Args:
        cells: Feature vectors per cell. / 每格子的特徵向量。
        k: Number of clusters (default: 2 if n_cells < 6, else 3). / 聚類數（默認：n<6 用 2，否則 3）。
        output_path: Optional JSON output path. / 可選 JSON 輸出路徑。

    Returns:
        Sorted list of ClusterResult (rank 1 = best edge). / 按排名排序的 ClusterResult 列表。
    """
    if not cells:
        logger.warning("No cells to cluster — aborting. / 無格子可聚類。")
        return []

    n = len(cells)
    if k is None:
        k = 2 if n < 6 else 3
    k = min(k, n)  # cannot have more clusters than cells

    logger.info("Running k-means: %d cells, k=%d / 運行 k-means：%d 格子，k=%d", n, k, n, k)

    features = _normalize_features(cells)
    labels = _kmeans(features, k)
    cluster_labels = _label_clusters(cells, labels, k)

    # Rank all cells by shrunk_bps (descending: 1 = least negative = best)
    # 按 shrunk_bps 降序排名（1 = 最不負 = 最優）
    order = sorted(range(n), key=lambda i: cells[i].shrunk_bps, reverse=True)
    rank_map = {idx: rank + 1 for rank, idx in enumerate(order)}

    results: list[ClusterResult] = []
    for i, c in enumerate(cells):
        parts = c.key.split("::", 1)
        strategy = parts[0] if parts else c.key
        symbol = parts[1] if len(parts) > 1 else ""
        results.append(ClusterResult(
            key=c.key,
            strategy=strategy,
            symbol=symbol,
            shrunk_bps=c.shrunk_bps,
            combined_ev_bps=c.combined_ev_bps,
            win_rate=c.win_rate,
            n=c.n,
            cluster=labels[i],
            cluster_label=cluster_labels[i],
            rank_overall=rank_map[i],
        ))

    results.sort(key=lambda r: r.rank_overall)

    # Log summary / 記錄摘要
    logger.info("Cluster analysis results (ranked by edge):")
    for r in results:
        logger.info(
            "  [#%d %s] %s — shrunk=%.2f bps, combined_ev=%.2f bps, win_rate=%.2f, n=%d",
            r.rank_overall, r.cluster_label.upper(), r.key,
            r.shrunk_bps, r.combined_ev_bps, r.win_rate, r.n,
        )

    # Write JSON output / 寫入 JSON 輸出
    if output_path:
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        out = {
            "_meta": {
                "updated_at": now_iso,
                "n_cells": n,
                "k_clusters": k,
                "note": (
                    "Ranked by shrunk_bps (rank 1 = least negative = best candidate). "
                    "cluster_label: candidate | middle | underperformer. "
                    "All estimates currently negative — exploration mode active in paper/demo."
                ),
            },
            "ranked": [
                {
                    "rank": r.rank_overall,
                    "key": r.key,
                    "strategy": r.strategy,
                    "symbol": r.symbol,
                    "cluster_label": r.cluster_label,
                    "cluster_id": r.cluster,
                    "shrunk_bps": round(r.shrunk_bps, 4),
                    "combined_ev_bps": round(r.combined_ev_bps, 4),
                    "win_rate": round(r.win_rate, 4),
                    "n": r.n,
                }
                for r in results
            ],
        }
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        tmp = output_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(out, f, indent=2)
        os.replace(tmp, output_path)
        logger.info("Cluster analysis written to %s / 聚類分析已寫入 %s", output_path, output_path)

    return results


# ---------------------------------------------------------------------------
# CLI entry point / CLI 入口
# ---------------------------------------------------------------------------

def _default_output_path() -> str:
    return os.path.join(
        os.path.dirname(__file__), "..", "..", "settings", "edge_clusters.json"
    )


def _default_snapshot_path() -> str:
    return os.environ.get(
        "OPENCLAW_EDGE_SNAPSHOT",
        os.path.join(
            os.path.dirname(__file__), "..", "..", "settings", "edge_estimates.json"
        ),
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="K-means clustering on JS edge estimates.")
    p.add_argument("--snapshot", type=str, default=None,
                   help="Path to edge_estimates.json (default: settings/edge_estimates.json)")
    p.add_argument("--from-pg", action="store_true",
                   help="Load from Postgres instead of JSON snapshot")
    p.add_argument("--days", type=int, default=30, help="Days for PG query (default 30)")
    p.add_argument("--k", type=int, default=None, help="Number of clusters (default: auto)")
    p.add_argument("--out", type=str, default=None,
                   help="Output JSON path (default: settings/edge_clusters.json)")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    """CLI entry point. / CLI 入口。"""
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    if args.from_pg:
        cells = load_from_postgres(days_back=args.days)
    else:
        snapshot_path = args.snapshot or _default_snapshot_path()
        if not os.path.exists(snapshot_path):
            logger.error("Snapshot not found: %s — run james_stein_estimator.py first.",
                         snapshot_path)
            return
        cells = load_from_snapshot(snapshot_path)

    if not cells:
        logger.warning("No cells loaded — cannot cluster.")
        return

    output_path = args.out or _default_output_path()
    results = run_cluster_analysis(cells, k=args.k, output_path=output_path)

    # Print summary table / 打印摘要表
    print(f"\n{'Rank':<5} {'Cluster':<14} {'Key':<35} {'shrunk_bps':>10} {'combined_ev':>12} {'win_rate':>9} {'n':>5}")
    print("-" * 90)
    for r in results:
        print(f"{r.rank_overall:<5} {r.cluster_label:<14} {r.key:<35} "
              f"{r.shrunk_bps:>10.2f} {r.combined_ev_bps:>12.2f} {r.win_rate:>9.3f} {r.n:>5}")
    print()
    if results:
        best = results[0]
        worst = results[-1]
        print(f"Best candidate:    {best.key} ({best.shrunk_bps:.2f} bps)")
        print(f"Worst performer:   {worst.key} ({worst.shrunk_bps:.2f} bps)")
        print(f"Output:            {output_path}")


if __name__ == "__main__":
    main()
