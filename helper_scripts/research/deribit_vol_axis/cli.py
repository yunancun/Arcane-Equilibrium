#!/usr/bin/env python3
"""Deribit 隱含波動率數據軸採集 CLI（daily / manual 模式）。

MODULE_NOTE:
  模塊用途：採集編排入口——collect → write artifact。cron wrapper 與手動研究
    調用共用本入口。本軸無持久 state（無 track-to-resolution——DVOL 序列 +
    surface 快照都是無狀態 PIT 採集），故較 polymarket_axis 少一個 state 環節。
  模式：
    - daily：BTC/ETH DVOL 最近一日 OHLC + 全 option surface 快照 + term-structure
      + skew（baseline cron）。
    - manual：手動研究調用（可覆寫 currencies / DVOL 窗口 / 粒度）。
  依賴：本 package 各模塊 + 標準庫。零生產模組 import、零 PG、零 auth。
  硬邊界：artifact root / data root 禁硬編碼（${OPENCLAW_DATA_DIR:-/tmp/openclaw}）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from . import COLLECTION_CURRENCIES
    from . import artifact as artifact_mod
    from . import collector as collector_mod
except ImportError:  # pragma: no cover —— 直跑 `python cli.py` 時的路徑兜底（mirror polymarket_axis）。
    _here = Path(__file__).resolve()
    _research = _here.parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from deribit_vol_axis import COLLECTION_CURRENCIES  # type: ignore
    from deribit_vol_axis import artifact as artifact_mod  # type: ignore
    from deribit_vol_axis import collector as collector_mod  # type: ignore


def _repo_root() -> Path:
    # cli.py → deribit_vol_axis → research → helper_scripts → srv（parents[3]，mirror polymarket_axis）。
    return Path(__file__).resolve().parents[3]


def run_collect(args: argparse.Namespace) -> dict[str, Any]:
    """daily / manual 共用：collect → write artifact。"""
    data_root = Path(args.data_root) if args.data_root else artifact_mod.resolve_data_root()
    currencies = tuple(
        c.strip().upper() for c in args.currencies.split(",") if c.strip()
    ) if args.currencies else COLLECTION_CURRENCIES
    client = collector_mod.ThrottledJsonClient(min_interval_s=args.min_interval_s)
    git_sha = artifact_mod._git_provenance(_repo_root())["git_sha"]

    result = collector_mod.collect_vol_snapshot(
        client,
        currencies=currencies,
        collector_git_sha=git_sha,
        dvol_window_s=args.dvol_window_s,
        dvol_resolution_s=args.dvol_resolution_s,
    )

    run_id = args.run_id or artifact_mod.default_run_id(args.mode)
    written = artifact_mod.write_run(
        mode=args.mode,
        run_id=run_id,
        repo_root=_repo_root(),
        stats=result["stats"],
        errors=result["errors"],
        dvol_rows=result["dvol_rows"],
        surface_rows=result["surface_rows"],
        term_structure_rows=result["term_structure_rows"],
        skew_rows=result["skew_rows"],
        raw_instruments=result["raw_instruments"],
        artifact_root=Path(args.artifact_root) if args.artifact_root else artifact_mod.resolve_artifact_root(data_root),
        created_by_role=args.created_by_role,
        parquet_mirror=not args.no_parquet_mirror,
    )
    return {
        "mode": args.mode,
        "run_id": run_id,
        "run_dir": written["written"]["run_dir"],
        "currencies": list(currencies),
        "dvol_rows": result["stats"].get("dvol_rows"),
        "surface_rows": result["stats"].get("surface_rows"),
        "term_structure_rows": result["stats"].get("term_structure_rows"),
        "skew_rows": result["stats"].get("skew_rows"),
        "http_requests": result["stats"].get("http_requests"),
        "errors": result["errors"],
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="deribit_vol_axis.cli",
        description="Deribit DVOL / IV-surface point-in-time 採集（artifact-only 離線研究軸）",
    )
    p.add_argument("--mode", default="daily", choices=["daily", "manual"])
    p.add_argument("--run-id", default=None, dest="run_id")
    p.add_argument("--data-root", default=None, dest="data_root",
                   help="覆蓋 ${OPENCLAW_DATA_DIR:-/tmp/openclaw}（artifact 根）")
    p.add_argument("--artifact-root", default=None, dest="artifact_root")
    p.add_argument("--created-by-role", default="E1", dest="created_by_role")
    p.add_argument("--min-interval-s", default=collector_mod.DEFAULT_MIN_INTERVAL_S,
                   type=float, dest="min_interval_s", help="client throttle（默認 0.5s = 2 req/s 上限）")
    p.add_argument("--no-parquet-mirror", action="store_true", dest="no_parquet_mirror")
    p.add_argument("--currencies", default=None,
                   help="逗號分隔幣種（默認 BTC,ETH；manual 研究可覆寫）")
    p.add_argument("--dvol-window-s", default=collector_mod.DVOL_WINDOW_S_DEFAULT,
                   type=int, dest="dvol_window_s",
                   help="DVOL OHLC 回補窗口秒數（默認 86400=24h；append-only 不回填更早歷史）")
    p.add_argument("--dvol-resolution-s", default=collector_mod.DVOL_RESOLUTION_S_DEFAULT,
                   type=int, dest="dvol_resolution_s",
                   help="DVOL bar 粒度秒數（默認 3600=1h）")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    summary = run_collect(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
