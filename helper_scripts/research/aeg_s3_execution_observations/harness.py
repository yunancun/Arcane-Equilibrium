#!/usr/bin/env python3
"""AEG-S3 execution observation producer CLI."""

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
    from aeg_s3_execution_observations import artifact as artifact_mod  # type: ignore
    from aeg_s3_execution_observations import builder as builder_mod  # type: ignore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_and_write(args: argparse.Namespace) -> dict:
    candidate_evidence = builder_mod.load_json(Path(args.candidate_evidence_json))
    gate_b_payload = builder_mod.load_gate_b_run(Path(args.gate_b_run_dir))
    observations, summary = builder_mod.build_gate_b_observations(
        candidate_evidence=candidate_evidence,
        gate_b_payload=gate_b_payload,
        source_path=str(Path(args.gate_b_run_dir)),
        maker_fee_bps=args.maker_fee_bps,
        taker_fee_bps=args.taker_fee_bps,
        order_notional_usdt=args.order_notional_usdt,
        evidence_source_tier=args.evidence_source_tier,
        order_style=args.order_style,
        slippage_floor_bps=args.slippage_floor_bps,
        capacity_window_s=args.capacity_window_s,
        allow_slow_capture=args.allow_slow_capture,
    )
    written = artifact_mod.write_all(
        observations=observations,
        summary=summary,
        run_id=args.run_id,
        repo_root=_repo_root(),
        artifact_root=Path(args.artifact_root) if args.artifact_root else None,
        runtime_host=socket.gethostname(),
        session_id=args.session_id,
        created_by_role=args.created_by_role,
    )
    return {"summary": summary, "observations": observations, "written": written}


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aeg_s3_execution_observations.harness",
        description="Convert Gate-B listing capture artifacts into AEG-S3 execution_observations.jsonl",
    )
    p.add_argument("--run-id", required=True, dest="run_id")
    p.add_argument("--candidate-evidence-json", required=True, dest="candidate_evidence_json")
    p.add_argument("--gate-b-run-dir", required=True, dest="gate_b_run_dir")
    p.add_argument("--maker-fee-bps", type=float, default=2.0, dest="maker_fee_bps")
    p.add_argument("--taker-fee-bps", type=float, default=5.5, dest="taker_fee_bps")
    p.add_argument("--order-notional-usdt", type=float, required=True, dest="order_notional_usdt")
    p.add_argument("--evidence-source-tier", default="calibrated_replay", dest="evidence_source_tier")
    p.add_argument("--order-style", default="taker", dest="order_style")
    p.add_argument("--slippage-floor-bps", type=float, default=0.0, dest="slippage_floor_bps")
    p.add_argument("--capacity-window-s", type=int, default=60, dest="capacity_window_s")
    p.add_argument("--allow-slow-capture", action="store_true", dest="allow_slow_capture")
    p.add_argument("--artifact-root", default=None, dest="artifact_root")
    p.add_argument("--session-id", default=None, dest="session_id")
    p.add_argument("--created-by-role", default="PM", dest="created_by_role")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    result = build_and_write(args)
    summary = result["summary"]
    print(json.dumps({
        "run_id": args.run_id,
        "candidate_id": summary["candidate_id"],
        "parameter_cell_id": summary["parameter_cell_id"],
        "observation_count": summary["observation_count"],
        "rejected_observation_count": summary["rejected_observation_count"],
        "reject_reasons": summary["reject_reasons"],
        "evidence_source_tier": summary["evidence_source_tier"],
        "order_style": summary["order_style"],
        "artifact_dir": result["written"]["run_dir"],
        "execution_observations_jsonl": result["written"]["execution_observations_jsonl"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

