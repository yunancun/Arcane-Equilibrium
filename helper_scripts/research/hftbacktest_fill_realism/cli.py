#!/usr/bin/env python3
"""hftbacktest fill-realism harness CLI（fetch / convert / revalidate-d2）。

MODULE_NOTE:
  模塊用途：編排入口——
    - fetch：下載 Tardis 免費 first-day-of-month CSV.gz 到 append-only run dir/raw/。
    - convert：raw CSV.gz → hftbacktest 8-field npz（官方 tardis converter）。
    - revalidate-d2：cascade 事件（market.liquidations read-only，或 --liq-source
      tardis 用同窗 Tardis liquidations CSV）→ 反 cascade maker 掛單 → fill/逆選擇
      → net（禁 rebate）→ d2_revalidation.json 裁決。
    - run-all：fetch → convert → revalidate-d2 一條龍（單 symbol 單免費日）。
  依賴：本 package 各模塊 + 標準庫；revalidate-d2 PG 來源需 psycopg2。
  硬邊界：artifact root 禁硬編碼（${OPENCLAW_DATA_DIR:-/tmp/openclaw}）；不碰執行
    路徑、不碰 5-gate、不需 restart_all。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import socket
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from . import TARDIS_CHANNELS, TARDIS_EXCHANGE
    from . import artifact as artifact_mod
    from . import bridge_d2 as bridge_mod
    from . import converter as converter_mod
    from . import data_fetch as fetch_mod
except ImportError:  # pragma: no cover —— 直跑 `python cli.py` 的路徑兜底（mirror deribit_vol_axis）。
    _here = Path(__file__).resolve()
    _research = _here.parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from hftbacktest_fill_realism import TARDIS_CHANNELS, TARDIS_EXCHANGE  # type: ignore
    from hftbacktest_fill_realism import artifact as artifact_mod  # type: ignore
    from hftbacktest_fill_realism import bridge_d2 as bridge_mod  # type: ignore
    from hftbacktest_fill_realism import converter as converter_mod  # type: ignore
    from hftbacktest_fill_realism import data_fetch as fetch_mod  # type: ignore


def _repo_root() -> Path:
    # cli.py → hftbacktest_fill_realism → research → helper_scripts → srv（parents[3]）。
    return Path(__file__).resolve().parents[3]


def _parse_day(s: str) -> dt.date:
    d = dt.date.fromisoformat(s)
    if d.day != 1:
        raise argparse.ArgumentTypeError(f"Tardis 免費 tier 僅每月 1 號可下載：{s}（day != 1）")
    return d


def _resolve_run_dir(args: argparse.Namespace, mode: str) -> Path:
    artifact_root = Path(args.artifact_root) if args.artifact_root else artifact_mod.resolve_artifact_root()
    if args.run_id:
        run_id = args.run_id
    else:
        run_id = artifact_mod.default_run_id(mode)
    return artifact_mod.create_run_dir(run_id, artifact_root)


def cmd_fetch(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = _resolve_run_dir(args, "fetch")
    raw_dir = run_dir / "raw"
    day = _parse_day(args.day)
    fetched = fetch_mod.fetch_symbol_month(
        raw_dir,
        symbol=args.symbol,
        day=day,
        channels=TARDIS_CHANNELS,
        exchange=TARDIS_EXCHANGE,
    )
    extra = [
        artifact_mod.index_entry(Path(p).name, Path(p), "tardis.raw_csv_gz.v1")
        for p in fetched["files"].values()
    ]
    written = artifact_mod.write_manifest_and_index(
        run_dir,
        mode="fetch",
        run_id=run_dir.name,
        repo_root=_repo_root(),
        stats={"symbol": args.symbol, "day": day.isoformat(), "files": fetched["files"]},
        errors=fetched["errors"],
        extra_artifacts=extra,
        runtime_host=socket.gethostname(),
        created_by_role=args.created_by_role,
    )
    return {"mode": "fetch", "run_dir": str(run_dir), "fetched": fetched, "written": written["written"]}


def cmd_convert(args: argparse.Namespace) -> dict[str, Any]:
    raw_files = json.loads(args.raw_files_json)
    out_npz = Path(args.out_npz)
    res = converter_mod.convert_symbol(raw_files, out_npz=out_npz)
    return {"mode": "convert", "result": res}


def _load_liquidations(args: argparse.Namespace, day: dt.date) -> list[dict]:
    """依 --liq-source 取 cascade 事件源（pg read-only 或 tardis CSV）。"""
    if args.liq_source == "tardis":
        if not args.liq_csv:
            raise SystemExit("--liq-source tardis 需 --liq-csv <path>")
        return bridge_mod.load_liquidations_tardis_csv(Path(args.liq_csv))
    # pg read-only：當日 UTC 全天窗。
    window_start = dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc)
    window_end = window_start + dt.timedelta(days=1)
    conn = bridge_mod.connect_readonly(args.dsn)
    try:
        return bridge_mod.load_liquidations_pg(
            conn, symbol=args.symbol, window_start=window_start, window_end=window_end,
        )
    finally:
        conn.close()


def cmd_revalidate_d2(args: argparse.Namespace) -> dict[str, Any]:
    day = _parse_day(args.day)
    liquidations = _load_liquidations(args, day)
    result = bridge_mod.revalidate_d2(
        npz_path=Path(args.npz),
        liquidations=liquidations,
        symbol=args.symbol,
        tick_size=args.tick_size,
        lot_size=args.lot_size,
        cluster_window_s=args.cluster_window_s,
        min_events=args.min_events,
        exit_horizon_s=args.exit_horizon_s,
        overshoot_offset_bps=args.overshoot_offset_bps,
        order_qty=args.order_qty,
        queue_model=args.queue_model,
    )
    run_dir = _resolve_run_dir(args, "revalidate-d2")
    written = artifact_mod.write_manifest_and_index(
        run_dir,
        mode="revalidate-d2",
        run_id=run_dir.name,
        repo_root=_repo_root(),
        stats={
            "symbol": args.symbol,
            "day": day.isoformat(),
            "liq_source": args.liq_source,
            "n_liquidations": len(liquidations),
        },
        errors=list(result.get("sim_errors") or []),
        d2_revalidation_payload=result,
        runtime_host=socket.gethostname(),
        created_by_role=args.created_by_role,
    )
    return {"mode": "revalidate-d2", "run_dir": str(run_dir), "result": result, "written": written["written"]}


def cmd_run_all(args: argparse.Namespace) -> dict[str, Any]:
    """fetch → convert → revalidate-d2 一條龍（單 symbol 單免費日）。"""
    day = _parse_day(args.day)
    run_dir = _resolve_run_dir(args, "run-all")
    raw_dir = run_dir / "raw"
    fetched = fetch_mod.fetch_symbol_month(
        raw_dir, symbol=args.symbol, day=day, channels=TARDIS_CHANNELS, exchange=TARDIS_EXCHANGE,
    )
    hbt_dir = run_dir / "hbt"
    out_npz = hbt_dir / f"{args.symbol}_{day.isoformat()}.npz"
    conv = converter_mod.convert_symbol(fetched["files"], out_npz=out_npz)

    # cascade 事件源：默認用同 run 下載的 Tardis liquidations CSV（PG 不可達時的離線
    # 等價，且與 L2 tape 同窗 = 自然 intersection）；--liq-source pg 可改讀我們的 PG。
    if args.liq_source == "pg":
        liquidations = _load_liquidations(args, day)
    else:
        liq_csv = fetched["files"].get("liquidations")
        liquidations = bridge_mod.load_liquidations_tardis_csv(Path(liq_csv)) if liq_csv else []

    result = bridge_mod.revalidate_d2(
        npz_path=out_npz,
        liquidations=liquidations,
        symbol=args.symbol,
        tick_size=args.tick_size,
        lot_size=args.lot_size,
        cluster_window_s=args.cluster_window_s,
        min_events=args.min_events,
        exit_horizon_s=args.exit_horizon_s,
        overshoot_offset_bps=args.overshoot_offset_bps,
        order_qty=args.order_qty,
        queue_model=args.queue_model,
    )
    extra = [
        artifact_mod.index_entry(Path(p).name, Path(p), "tardis.raw_csv_gz.v1")
        for p in fetched["files"].values()
    ]
    if out_npz.exists():
        extra.append(artifact_mod.index_entry(out_npz.name, out_npz, "hftbacktest.event_npz.v1"))
    written = artifact_mod.write_manifest_and_index(
        run_dir,
        mode="run-all",
        run_id=run_dir.name,
        repo_root=_repo_root(),
        stats={
            "symbol": args.symbol,
            "day": day.isoformat(),
            "liq_source": args.liq_source,
            "n_liquidations": len(liquidations),
            "converter": conv,
            "fetch_errors": fetched["errors"],
        },
        errors=list(result.get("sim_errors") or []),
        d2_revalidation_payload=result,
        extra_artifacts=extra,
        runtime_host=socket.gethostname(),
        created_by_role=args.created_by_role,
    )
    return {"mode": "run-all", "run_dir": str(run_dir), "result": result, "written": written["written"]}


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--run-id", default=None, dest="run_id")
    p.add_argument("--artifact-root", default=None, dest="artifact_root",
                   help="覆蓋 ${OPENCLAW_DATA_DIR:-/tmp/openclaw}/hftbacktest_fill_realism_runs")
    p.add_argument("--created-by-role", default="E1", dest="created_by_role")


def _add_d2_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--symbol", required=True)
    p.add_argument("--day", required=True, help="Tardis 免費日 YYYY-MM-01（day 必為 1）")
    p.add_argument("--tick-size", type=float, required=True, dest="tick_size")
    p.add_argument("--lot-size", type=float, required=True, dest="lot_size")
    p.add_argument("--liq-source", default="tardis", choices=["tardis", "pg"], dest="liq_source")
    p.add_argument("--liq-csv", default=None, dest="liq_csv", help="--liq-source tardis 時的 liquidations CSV.gz")
    p.add_argument("--dsn", default=None, help="--liq-source pg 時的 read-only DSN（默認 resolve_report_dsn）")
    p.add_argument("--cluster-window-s", type=float, default=bridge_mod.CASCADE_CLUSTER_WINDOW_S_DEFAULT,
                   dest="cluster_window_s")
    p.add_argument("--min-events", type=int, default=bridge_mod.CASCADE_MIN_EVENTS_DEFAULT, dest="min_events")
    p.add_argument("--exit-horizon-s", type=float, default=bridge_mod.D2_EXIT_HORIZON_S_DEFAULT,
                   dest="exit_horizon_s")
    p.add_argument("--overshoot-offset-bps", type=float, default=0.0, dest="overshoot_offset_bps",
                   help="相對 live BBO 的掛單偏移 bps（0=貼 BBO 最積極被動 maker；>0=退深接超調）")
    p.add_argument("--order-qty", type=float, default=0.01, dest="order_qty")
    p.add_argument("--queue-model", default="log_prob",
                   choices=["log_prob", "power_prob", "risk_averse"], dest="queue_model")


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hftbacktest_fill_realism.cli",
        description="hftbacktest fill-realism harness（artifact-only 離線；D2 re-validation，禁 maker rebate）",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_fetch = sub.add_parser("fetch", help="下載 Tardis 免費 CSV.gz")
    _add_common(p_fetch)
    p_fetch.add_argument("--symbol", required=True)
    p_fetch.add_argument("--day", required=True, help="Tardis 免費日 YYYY-MM-01")
    p_fetch.set_defaults(func=cmd_fetch)

    p_conv = sub.add_parser("convert", help="raw CSV.gz → hftbacktest 8-field npz")
    _add_common(p_conv)
    p_conv.add_argument("--raw-files-json", required=True, dest="raw_files_json",
                        help='JSON dict 如 {"incremental_book_L2":"...","trades":"..."}')
    p_conv.add_argument("--out-npz", required=True, dest="out_npz")
    p_conv.set_defaults(func=cmd_convert)

    p_d2 = sub.add_parser("revalidate-d2", help="cascade → maker fill → net 裁決（用既有 npz）")
    _add_common(p_d2)
    _add_d2_args(p_d2)
    p_d2.add_argument("--npz", required=True, help="converter 產出的 8-field event npz")
    p_d2.set_defaults(func=cmd_revalidate_d2)

    p_all = sub.add_parser("run-all", help="fetch → convert → revalidate-d2 一條龍")
    _add_common(p_all)
    _add_d2_args(p_all)
    p_all.set_defaults(func=cmd_run_all)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    summary = args.func(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
