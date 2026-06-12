#!/usr/bin/env python3
"""AEG-S3 Gate-B artifact preflight CLI."""

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
    _research = Path(__file__).resolve().parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_s3_gate_b_preflight import artifact as artifact_mod  # type: ignore
    from aeg_s3_gate_b_preflight import builder as builder_mod  # type: ignore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_and_write(args: argparse.Namespace) -> dict:
    summary = builder_mod.build_preflight_summary(
        run_id=args.run_id,
        chain_run_id=args.chain_run_id,
        gate_b_root=args.gate_b_root,
        alpha_history_root=args.alpha_history_root,
        artifact_root=args.artifact_root,
        gate_b_run_dir=args.gate_b_run_dir,
        fnd2_run_dir=args.fnd2_run_dir,
        regime_run_dir=args.regime_run_dir,
        horizon_s=args.horizon_s,
        round_trip_cost_bps=args.round_trip_cost_bps,
        k_trials=args.k_trials,
        default_regime=args.default_regime,
        allow_slow_capture=args.allow_slow_capture,
        order_notional_usdt=args.order_notional_usdt,
        slippage_floor_bps=args.slippage_floor_bps,
        include_default_pbo_grid=not args.no_default_pbo_grid,
        min_listing_samples=args.min_listing_samples,
        gate_watch_latest_json=args.gate_watch_latest_json,
        gate_watch_max_age_hours=args.gate_watch_max_age_hours,
    )
    written = artifact_mod.write_all(
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
        prog="aeg_s3_gate_b_preflight.harness",
        description=(
            "Inspect local Gate-B/FND2/regime artifacts and build the recommended "
            "artifact-only full-chain command."
        ),
    )
    p.add_argument("--run-id", required=True, dest="run_id")
    p.add_argument("--chain-run-id", default=None, dest="chain_run_id")
    p.add_argument("--gate-b-root", default=None, dest="gate_b_root")
    p.add_argument("--alpha-history-root", default=None, dest="alpha_history_root")
    p.add_argument("--artifact-root", default=None, dest="artifact_root")
    p.add_argument("--gate-b-run-dir", default=None, dest="gate_b_run_dir")
    p.add_argument("--fnd2-run-dir", default=None, dest="fnd2_run_dir")
    p.add_argument("--regime-run-dir", default=None, dest="regime_run_dir")
    p.add_argument("--horizon-s", type=int, default=60, dest="horizon_s")
    p.add_argument("--round-trip-cost-bps", type=float, default=5.0, dest="round_trip_cost_bps")
    p.add_argument("--k-trials", type=int, default=12, dest="k_trials")
    p.add_argument("--default-regime", default="chop", dest="default_regime")
    p.add_argument("--allow-slow-capture", action="store_true", dest="allow_slow_capture")
    p.add_argument("--order-notional-usdt", type=float, default=1.0, dest="order_notional_usdt")
    p.add_argument("--slippage-floor-bps", type=float, default=1.0, dest="slippage_floor_bps")
    p.add_argument("--no-default-pbo-grid", action="store_true", dest="no_default_pbo_grid")
    p.add_argument("--min-listing-samples", type=int, default=30, dest="min_listing_samples")
    p.add_argument("--gate-watch-latest-json", default=None, dest="gate_watch_latest_json")
    p.add_argument("--gate-watch-max-age-hours", type=float, default=4.0, dest="gate_watch_max_age_hours")
    p.add_argument("--session-id", default=None, dest="session_id")
    p.add_argument("--created-by-role", default="PM", dest="created_by_role")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    result = build_and_write(args)
    summary = result["summary"]
    print(json.dumps({
        "run_id": summary["run_id"],
        "readiness_status": summary["readiness_status"],
        "selected_artifacts": summary["selected_artifacts"],
        "gate_watch": summary["gate_watch"],
        "listing_preview": summary["listing_preview"],
        "recommended_command": summary["recommended_command"]["shell"],
        "recommended_command_operator_recommended": summary["recommended_command"]["operator_recommended"],
        "recommended_command_operator_status": summary["recommended_command"]["operator_status"],
        "recommended_command_operator_message": summary["recommended_command"]["operator_message"],
        "artifact_dir": result["written"]["run_dir"],
        "summary_json": result["written"]["summary"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
