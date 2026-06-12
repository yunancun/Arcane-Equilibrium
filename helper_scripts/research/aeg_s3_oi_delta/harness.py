#!/usr/bin/env python3
"""AEG-S3 OI delta evidence producer CLI。"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Optional

try:
    from . import artifact as artifact_mod
    from . import builder as builder_mod
except ImportError:  # pragma: no cover
    _here = Path(__file__).resolve()
    _research = _here.parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_s3_oi_delta import artifact as artifact_mod  # type: ignore
    from aeg_s3_oi_delta import builder as builder_mod  # type: ignore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_pbo_grid(args: argparse.Namespace) -> list[dict] | None:
    cells: list[dict] = []
    if args.include_default_pbo_grid:
        cells.extend(builder_mod.default_pbo_grid(
            cost_bps=args.round_trip_cost_bps,
            min_symbols=args.min_symbols,
            side_mode=args.side_mode,
        ))
    if args.pbo_grid_json:
        payload = json.loads(Path(args.pbo_grid_json).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            raw_cells = payload.get("cells") or payload.get("pbo_grid")
        else:
            raw_cells = payload
        if not isinstance(raw_cells, list) or not all(isinstance(row, dict) for row in raw_cells):
            raise ValueError("pbo_grid_json_must_be_list_or_object_with_cells")
        cells.extend(raw_cells)
    return cells or None


def build_and_write(args: argparse.Namespace) -> dict:
    path = Path(args.panel_jsonl)
    payload = builder_mod.load_jsonl(path)
    regime_by_date = builder_mod.load_regime_by_date(Path(args.regime_by_date_json)) if args.regime_by_date_json else {}
    evidence, summary = builder_mod.build_oi_delta_evidence(
        payload,
        source_path=str(path),
        run_id=args.run_id,
        lookback_hours=args.lookback_hours,
        horizon_hours=args.horizon_hours,
        cost_bps=args.round_trip_cost_bps,
        k_trials=args.k_trials,
        candidate_id=args.candidate_id,
        tail_frac=args.tail_frac,
        min_symbols=args.min_symbols,
        min_spacing_hours=args.min_spacing_hours,
        max_timestamp_lag_minutes=args.max_timestamp_lag_minutes,
        side_mode=args.side_mode,
        regime_by_date=regime_by_date,
        default_regime=args.default_regime,
        oos_start_date=args.oos_start_date,
        pbo_grid=_load_pbo_grid(args),
    )
    written = artifact_mod.write_all(
        evidence=evidence,
        summary=summary,
        run_id=args.run_id,
        repo_root=_repo_root(),
        artifact_root=Path(args.artifact_root) if args.artifact_root else None,
        runtime_host=socket.gethostname(),
        session_id=args.session_id,
        created_by_role=args.created_by_role,
    )
    return {"summary": summary, "written": written}


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aeg_s3_oi_delta.harness",
        description="Offline OI/price panel JSONL to AEG-S3 OI delta candidate evidence JSON",
    )
    p.add_argument("--panel-jsonl", required=True, dest="panel_jsonl")
    p.add_argument("--run-id", required=True, dest="run_id")
    p.add_argument("--lookback-hours", required=True, type=float, dest="lookback_hours")
    p.add_argument("--horizon-hours", required=True, type=float, dest="horizon_hours")
    p.add_argument("--round-trip-cost-bps", required=True, type=float, dest="round_trip_cost_bps")
    p.add_argument("--k-trials", required=True, type=int, dest="k_trials")
    p.add_argument("--candidate-id", default="oi_delta", dest="candidate_id")
    p.add_argument("--tail-frac", default=0.2, type=float, dest="tail_frac")
    p.add_argument("--min-symbols", default=10, type=int, dest="min_symbols")
    p.add_argument("--min-spacing-hours", default=None, type=float, dest="min_spacing_hours")
    p.add_argument("--max-timestamp-lag-minutes", default=90.0, type=float, dest="max_timestamp_lag_minutes")
    p.add_argument("--side-mode", default="long_high_short_low", choices=("long_high_short_low", "short_high_long_low"), dest="side_mode")
    p.add_argument("--regime-by-date-json", default=None, dest="regime_by_date_json")
    p.add_argument("--default-regime", default=None, dest="default_regime")
    p.add_argument("--oos-start-date", default=None, dest="oos_start_date")
    p.add_argument("--include-default-pbo-grid", action="store_true", dest="include_default_pbo_grid")
    p.add_argument("--pbo-grid-json", default=None, dest="pbo_grid_json")
    p.add_argument("--artifact-root", default=None, dest="artifact_root")
    p.add_argument("--session-id", default=None, dest="session_id")
    p.add_argument("--created-by-role", default="PM", dest="created_by_role")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    result = build_and_write(args)
    summary = result["summary"]
    print(json.dumps({
        "run_id": summary["run_id"],
        "candidate_id": summary["candidate_id"],
        "sample_count": summary["sample_count"],
        "rejected_sample_count": summary["rejected_sample_count"],
        "reject_reasons": summary["reject_reasons"],
        "pbo_status": summary["pbo_status"],
        "pbo_grid_cell_count": summary["pbo_grid_cell_count"],
        "pbo_grid_included_candidate_count": summary["pbo_grid_included_candidate_count"],
        "artifact_dir": result["written"]["run_dir"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
