#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：Phase 1b calibration sweep CLI entry point。
用法：
  python3 helper_scripts/calibration/phase_1b_sweep_cli.py --smoke-test
  python3 helper_scripts/calibration/phase_1b_sweep_cli.py --all-cells
  python3 helper_scripts/calibration/phase_1b_sweep_cli.py --cells G-AB-01-C30 PG-AB-02-C15
依 PA spec §5 Step 3 sweep execution + spec §4 acceptance gate。
依賴：calibration package（pure modules）+ psycopg2 (runtime PG).
硬邊界：read-only PG；output 寫至 helper_scripts/calibration/output/；
        不動 production code / TOML / live auth。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase_1b_sweep_cells import CalibrationCell, enumerate_cells  # noqa: E402
from phase_1b_tick_loader import (  # noqa: E402
    _get_conn,
    get_taker_baseline_fee_bps,
    load_replay_seed,
    load_tick_size_map,
    verify_freshness,
)
from phase_1b_sweep_replay import (  # noqa: E402
    load_all_tick_windows,
    simulate_all_cells,
)
from phase_1b_sweep_report import build_report_for_cell, write_outputs  # noqa: E402


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 1b calibration sweep CLI",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all-cells", action="store_true",
        help="跑全部 81 cells（spec §5 Step 3 batch）",
    )
    group.add_argument(
        "--smoke-test", action="store_true",
        help="跑 2 cell（block 1 + block 2 各取 1）驗 end-to-end",
    )
    group.add_argument(
        "--cells", nargs="+", metavar="CELL_ID",
        help="跑指定 cell_id（e.g. G-AB-01-C30 PG-AB-02-C15）",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=None,
        help="Output 目錄；預設 helper_scripts/calibration/output/<timestamp>",
    )
    parser.add_argument(
        "--skip-pre-restart", action="store_true",
        help="僅跑 post-restart 4 row seed（spec §3.3 strict freshness）",
    )
    args = parser.parse_args(argv)

    # 選 cells
    all_cells = enumerate_cells()
    if args.all_cells:
        cells_to_run = all_cells
    elif args.smoke_test:
        cells_to_run = [
            c for c in all_cells
            if c.cell_id in ("G-AB-02-C30", "PG-AB-02-C15")
        ]
    elif args.cells:
        wanted = set(args.cells)
        cells_to_run = [c for c in all_cells if c.cell_id in wanted]
        missing = wanted - {c.cell_id for c in cells_to_run}
        if missing:
            print(f"ERROR: unknown cell_id(s): {sorted(missing)}", file=sys.stderr)
            return 2

    if not cells_to_run:
        print("ERROR: no cells selected", file=sys.stderr)
        return 2

    # output dir
    output_dir = args.output_dir
    if output_dir is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_dir = (
            Path(__file__).resolve().parent / "output" / f"sweep_{ts}"
        )

    print(f"=== Phase 1b Calibration Sweep ===")
    print(f"Cells selected: {len(cells_to_run)} / {len(all_cells)}")
    print(f"Output dir: {output_dir}")

    # PG 連線 + verify freshness
    conn = _get_conn()
    try:
        freshness = verify_freshness(conn)
        print(f"PG freshness: {freshness}")

        # 載入 seed + tick_size + taker baseline
        seeds = load_replay_seed(
            conn,
            include_pre_restart_baseline=(not args.skip_pre_restart),
            pre_restart_limit=50,
        )
        print(f"Replay seeds: {len(seeds)} (post_restart={sum(1 for s in seeds if s.seed_source=='post_restart')}, "
              f"pre_restart_baseline={sum(1 for s in seeds if s.seed_source=='pre_restart_baseline')})")

        symbols = list({s.symbol for s in seeds})
        tick_size_map = load_tick_size_map(conn, symbols)
        print(f"Tick size map: {len(tick_size_map)} / {len(symbols)} symbols")
        if len(tick_size_map) < len(symbols):
            missing_syms = set(symbols) - set(tick_size_map.keys())
            print(f"  WARN: missing tick_size for {sorted(missing_syms)}")

        taker_baseline_bps = get_taker_baseline_fee_bps(conn)
        print(f"Pre-Phase-1b taker baseline: {taker_baseline_bps:.2f} bps")

        # 載入所有 tick window（per seed.order_id key）
        print(f"Loading tick windows for {len(seeds)} seeds...")
        tick_windows = load_all_tick_windows(conn, seeds)
        n_with_data = sum(
            1 for w in tick_windows.values()
            if w.pre_fill_samples or w.replay_samples
        )
        print(f"Tick windows: {n_with_data} / {len(tick_windows)} with data")

    finally:
        conn.close()

    # 跑 simulation
    print(f"Running simulation for {len(cells_to_run)} cells...")
    outcomes = simulate_all_cells(
        cells=cells_to_run,
        seeds=seeds,
        tick_windows=tick_windows,
        tick_size_map=tick_size_map,
    )

    # 建 reports
    cell_meta_lookup = {c.cell_id: c for c in cells_to_run}
    reports = []
    for outcome in outcomes:
        cell = cell_meta_lookup[outcome.cell_id]
        report = build_report_for_cell(
            outcome=outcome,
            cell_meta={
                "block": cell.block,
                "family": cell.family,
                "offset_bps": cell.offset_bps,
                "buffer_ticks": cell.buffer_ticks,
                "timeout_ms": cell.timeout_ms,
                "spread_guard_bps": cell.spread_guard_bps,
                "is_baseline": cell.is_baseline,
                "direction_note": cell.direction_note,
            },
            pre_phase_1b_taker_baseline_bps=taker_baseline_bps,
        )
        reports.append(report)

    # 寫輸出
    info = write_outputs(reports, output_dir)
    print(f"\n=== Done ===")
    print(f"n_cells_written: {info['n_cells_written']}")
    print(f"summary: {info['summary']}")

    # 簡要 console summary
    print("\nPer-cell verdict:")
    for r in reports:
        print(
            f"  {r.cell_id:<20} {r.pass_gate:<11} "
            f"fill={r.maker_fill_rate*100:.1f}% "
            f"(CI {r.fill_rate_wilson_ci_low*100:.1f}-{r.fill_rate_wilson_ci_high*100:.1f}) "
            f"fee_saving={r.expected_fee_saving_bps:+.2f}bps "
            f"adverse={r.adverse_selection_proxy_bps if r.adverse_selection_proxy_bps is None else f'{r.adverse_selection_proxy_bps:+.2f}bps'} "
            f"(n_att={r.n_attempts} n_fill={r.n_simulated_fills} n_skip={r.n_attempts - r.n_eligible})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
