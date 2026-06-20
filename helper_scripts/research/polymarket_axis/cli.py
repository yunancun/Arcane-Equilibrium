#!/usr/bin/env python3
"""Polymarket 數據軸採集 CLI（三模式：daily / hourly-topn / retrospective）。

MODULE_NOTE:
  模塊用途：採集編排入口——load state → collect → write artifact → save state。
    cron wrapper 與手動研究調用共用本入口。
  模式：
    - daily：crypto tag 全量枚舉 + keyword 補充 + track-to-resolution follow-up
      （baseline，QC memo §2 頻率規格）。
    - hourly-topn：volume24hr top-N（默認 50）單頁加密採樣（lead-lag 假說 H1
      的 horizon<1d 觀測需求；活化 = operator 決策）。
    - retrospective：CLOB /prices-history 歷史回補，獨立 lane 標
      retrospective=true，永不混 snapshot lane。
  依賴：本 package 各模塊 + 標準庫。零生產模組 import。
  硬邊界：state 持久化僅在 artifact 寫出成功後進行——artifact 寫失敗時若先推
    state，下輪 follow-up 會以為「已見過」而漏抓（state 與 artifact 的順序是
    load-bearing）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from . import QUERY_SET_V1_KEYWORDS, QUERY_SET_V1_TAG
    from . import QUERY_SET_V2_KEYWORDS, QUERY_SET_V2_TAG
    from . import LANE_RETROSPECTIVE, LANE_SNAPSHOT
    from . import artifact as artifact_mod
    from . import collector as collector_mod
    from . import state as state_mod
except ImportError:  # pragma: no cover —— 直跑 `python cli.py` 時的路徑兜底（照 aeg_s3 harness 形）。
    _here = Path(__file__).resolve()
    _research = _here.parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from polymarket_axis import QUERY_SET_V1_KEYWORDS, QUERY_SET_V1_TAG  # type: ignore
    from polymarket_axis import QUERY_SET_V2_KEYWORDS, QUERY_SET_V2_TAG  # type: ignore
    from polymarket_axis import LANE_RETROSPECTIVE, LANE_SNAPSHOT  # type: ignore
    from polymarket_axis import artifact as artifact_mod  # type: ignore
    from polymarket_axis import collector as collector_mod  # type: ignore
    from polymarket_axis import state as state_mod  # type: ignore


def _repo_root() -> Path:
    # cli.py → polymarket_axis → research → helper_scripts → srv（parents[3]，實測對齊 aeg_s3）。
    return Path(__file__).resolve().parents[3]


def _select_query_set(query_set: str) -> tuple[str, tuple[str, ...], str]:
    """回 (tag, keywords, version)。v1 是默認相容路徑；v2 是事件/監管 discovery。"""
    if query_set == "v1":
        return QUERY_SET_V1_TAG, tuple(QUERY_SET_V1_KEYWORDS), "v1"
    if query_set == "v2":
        return QUERY_SET_V2_TAG, tuple(QUERY_SET_V2_KEYWORDS), "v2"
    raise ValueError(f"unknown query set: {query_set!r}")


def run_snapshot_mode(args: argparse.Namespace) -> dict[str, Any]:
    """daily / hourly-topn 共用：collect → write artifact → save state。"""
    data_root = Path(args.data_root) if args.data_root else artifact_mod.resolve_data_root()
    state_path = state_mod.resolve_state_path(data_root)
    tracker = state_mod.load_state(state_path)
    client = collector_mod.ThrottledJsonClient(min_interval_s=args.min_interval_s)
    git_sha = artifact_mod._git_provenance(_repo_root())["git_sha"]
    default_tag, keywords, query_set_version = _select_query_set(args.query_set)
    tag_slug = args.tag or default_tag

    top_n: Optional[int] = args.top_n if args.mode == "hourly-topn" else None
    result = collector_mod.collect_snapshot_sweep(
        client,
        tracker,
        collector_git_sha=git_sha,
        tag_slug=tag_slug,
        keywords=keywords,
        keyword_pages=args.keyword_pages,
        max_event_pages=args.max_event_pages,
        top_n=top_n,
        query_set_version=query_set_version,
    )

    run_id = args.run_id or artifact_mod.default_run_id(args.mode)
    written = artifact_mod.write_run(
        lane=LANE_SNAPSHOT,
        mode=args.mode,
        run_id=run_id,
        repo_root=_repo_root(),
        stats=result["stats"],
        errors=result["errors"],
        snapshot_rows=result["rows"],
        raw_events=result["raw_events"],
        raw_markets=result["raw_markets"],
        artifact_root=Path(args.artifact_root) if args.artifact_root else artifact_mod.resolve_artifact_root(data_root),
        created_by_role=args.created_by_role,
        parquet_mirror=not args.no_parquet_mirror,
        query_set_version=query_set_version,
    )
    mirror_result: dict[str, Any] | None = None
    if args.mirror_artifact_root:
        try:
            mirror_result = artifact_mod.mirror_run_dir(
                Path(written["written"]["run_dir"]),
                Path(args.mirror_artifact_root),
            )
        except Exception as exc:  # noqa: BLE001 - mirror 失敗不可破壞 primary run。
            mirror_result = {
                "mirror_status": "failed",
                "reason": f"{type(exc).__name__}:{exc}",
                "mirror_root": str(args.mirror_artifact_root),
            }
    # state 在 artifact 成功後才落（順序 load-bearing，見 MODULE_NOTE）。
    state_mod.save_state(tracker, state_path)
    return {
        "mode": args.mode,
        "run_id": run_id,
        "run_dir": written["written"]["run_dir"],
        "mirror": mirror_result,
        "query_set_version": query_set_version,
        "snapshot_rows": result["stats"].get("snapshot_rows"),
        "unique_events": result["stats"].get("unique_events"),
        "tracker_counts": result["stats"].get("tracker_counts"),
        "http_requests": result["stats"].get("http_requests"),
        "errors": result["errors"],
    }


def run_retrospective_mode(args: argparse.Namespace) -> dict[str, Any]:
    """retrospective：tracked state（或顯式 --market-ids）取 clob token 拉歷史。"""
    data_root = Path(args.data_root) if args.data_root else artifact_mod.resolve_data_root()
    state_path = state_mod.resolve_state_path(data_root)
    tracker = state_mod.load_state(state_path)

    wanted: Optional[set[str]] = None
    if args.market_ids:
        wanted = {m.strip() for m in args.market_ids.split(",") if m.strip()}
    elif not args.all_tracked:
        # 防誤觸全量回補：retrospective 是手動 / 可選 lane，必須顯式選範圍。
        raise SystemExit("retrospective mode requires --market-ids or --all-tracked")

    token_jobs: list[dict[str, Any]] = []
    for mid, entry in sorted(tracker.entries.items()):
        if wanted is not None and mid not in wanted:
            continue
        for token in entry.get("clob_token_ids") or []:
            token_jobs.append({"market_id": mid, "clob_token_id": token})

    client = collector_mod.ThrottledJsonClient(min_interval_s=args.min_interval_s)
    git_sha = artifact_mod._git_provenance(_repo_root())["git_sha"]
    result = collector_mod.collect_prices_history(
        client,
        token_jobs=token_jobs,
        interval=args.interval,
        fidelity=args.fidelity,
        start_ts=args.start_ts,
        end_ts=args.end_ts,
        collector_git_sha=git_sha,
    )

    run_id = args.run_id or artifact_mod.default_run_id("retrospective")
    written = artifact_mod.write_run(
        lane=LANE_RETROSPECTIVE,
        mode="retrospective",
        run_id=run_id,
        repo_root=_repo_root(),
        stats=result["stats"],
        errors=result["errors"],
        prices_history_rows=result["rows"],
        artifact_root=Path(args.artifact_root) if args.artifact_root else artifact_mod.resolve_artifact_root(data_root),
        created_by_role=args.created_by_role,
        parquet_mirror=not args.no_parquet_mirror,
    )
    # retrospective 不更新 tracker（它不是觀測，是回補——state 只屬 snapshot lane）。
    return {
        "mode": "retrospective",
        "run_id": run_id,
        "run_dir": written["written"]["run_dir"],
        "tokens": result["stats"].get("tokens"),
        "rows": result["stats"].get("rows"),
        "http_requests": result["stats"].get("http_requests"),
        "errors": result["errors"],
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="polymarket_axis.cli",
        description="Polymarket 賠率 point-in-time 採集（artifact-only 離線研究軸）",
    )
    p.add_argument("--mode", required=True, choices=["daily", "hourly-topn", "retrospective"])
    p.add_argument("--run-id", default=None, dest="run_id")
    p.add_argument("--data-root", default=None, dest="data_root",
                   help="覆蓋 ${OPENCLAW_DATA_DIR:-/tmp/openclaw}（state + artifact 共用根）")
    p.add_argument("--artifact-root", default=None, dest="artifact_root")
    p.add_argument("--mirror-artifact-root", default=None, dest="mirror_artifact_root",
                   help="可選 durable mirror root；append-only 複製，不覆寫既有 run_id")
    p.add_argument("--created-by-role", default="E1", dest="created_by_role")
    p.add_argument("--min-interval-s", default=collector_mod.DEFAULT_MIN_INTERVAL_S,
                   type=float, dest="min_interval_s", help="client throttle（默認 0.5s = 2 req/s 上限）")
    p.add_argument("--no-parquet-mirror", action="store_true", dest="no_parquet_mirror")
    # snapshot lane 參數。
    p.add_argument("--query-set", default="v1", choices=["v1", "v2"], dest="query_set",
                   help="snapshot 查詢集版本（v1=既有 crypto 全域；v2=事件/監管 discovery）")
    p.add_argument("--tag", default=None, help="tag 枚舉主路（未指定時跟隨 --query-set 默認 tag）")
    p.add_argument("--keyword-pages", default=2, type=int, dest="keyword_pages",
                   help="keyword 補充每詞頁數（0 = 關閉補充；/public-search 每頁 5 events）")
    p.add_argument("--max-event-pages", default=collector_mod.MAX_EVENT_PAGES_DEFAULT,
                   type=int, dest="max_event_pages")
    p.add_argument("--top-n", default=50, type=int, dest="top_n",
                   help="hourly-topn 模式 volume24hr 降冪 top-N（QC memo N≈30-50）")
    # retrospective lane 參數。
    p.add_argument("--market-ids", default=None, dest="market_ids",
                   help="逗號分隔 market id（retrospective 範圍圈定）")
    p.add_argument("--all-tracked", action="store_true", dest="all_tracked",
                   help="retrospective 對全部 tracked market 回補（顯式才允許）")
    p.add_argument("--interval", default="max", dest="interval",
                   help="CLOB prices-history interval（resolved 市場僅 ≥12h 粒度，已知限制）")
    p.add_argument("--fidelity", default=720, type=int, dest="fidelity",
                   help="分鐘粒度（默認 720=12h：resolved 市場安全值）")
    p.add_argument("--start-ts", default=None, type=int, dest="start_ts")
    p.add_argument("--end-ts", default=None, type=int, dest="end_ts")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if args.mode in ("daily", "hourly-topn"):
        summary = run_snapshot_mode(args)
    else:
        summary = run_retrospective_mode(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
