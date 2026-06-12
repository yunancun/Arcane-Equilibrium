#!/usr/bin/env python3
"""AEG-S3 event execution-realism empirical adapter CLI."""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Optional

try:
    from . import builder as builder_mod
except ImportError:  # pragma: no cover
    _research = Path(__file__).resolve().parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_s3_event_execution_realism import builder as builder_mod  # type: ignore

try:
    from aeg_execution_realism import artifact as artifact_mod
    from aeg_execution_realism import builder as exec_builder
except ImportError:  # pragma: no cover
    _research = Path(__file__).resolve().parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_execution_realism import artifact as artifact_mod  # type: ignore
    from aeg_execution_realism import builder as exec_builder  # type: ignore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_and_write(args: argparse.Namespace) -> dict:
    evidence = builder_mod.load_json(Path(args.candidate_evidence_json))
    observations = builder_mod.load_jsonl(Path(args.execution_observations_jsonl))
    raw_input, summary = builder_mod.build_execution_input(
        candidate_evidence=evidence,
        observation_rows=observations,
        evidence_source_tier=args.evidence_source_tier,
        order_style=args.order_style,
        capacity_notional_usdt=args.capacity_notional_usdt,
        order_availability_status=args.order_availability_status,
    )
    payload = exec_builder.evaluate(raw_input)
    payload["event_execution_summary"] = {
        key: summary[key]
        for key in (
            "candidate_sample_count",
            "observation_row_count",
            "matched_observation_count",
            "rejected_observation_reasons",
        )
    }
    written = artifact_mod.write_all(
        payload,
        run_id=args.run_id,
        repo_root=_repo_root(),
        runtime_host=socket.gethostname(),
        artifact_root=Path(args.artifact_root) if args.artifact_root else None,
        session_id=args.session_id,
        created_by_role=args.created_by_role,
    )
    return {"payload": payload, "summary": summary, "written": written}


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aeg_s3_event_execution_realism.harness",
        description=(
            "Aggregate empirical execution observations for single-symbol AEG-S3 "
            "event candidates and write execution_realism.json"
        ),
    )
    p.add_argument("--run-id", required=True, dest="run_id")
    p.add_argument("--candidate-evidence-json", required=True, dest="candidate_evidence_json")
    p.add_argument("--execution-observations-jsonl", required=True, dest="execution_observations_jsonl")
    p.add_argument("--evidence-source-tier", default=None, dest="evidence_source_tier")
    p.add_argument("--order-style", default=None, dest="order_style")
    p.add_argument("--capacity-notional-usdt", type=float, default=None, dest="capacity_notional_usdt")
    p.add_argument("--order-availability-status", default=None, dest="order_availability_status")
    p.add_argument("--artifact-root", default=None, dest="artifact_root")
    p.add_argument("--session-id", default=None, dest="session_id")
    p.add_argument("--created-by-role", default="PM", dest="created_by_role")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    result = build_and_write(args)
    payload = result["payload"]
    print(json.dumps({
        "run_id": args.run_id,
        "candidate_id": payload.get("candidate_id"),
        "status": payload.get("status"),
        "reject_reasons": payload.get("reject_reasons"),
        "execution_realism_mode": payload.get("execution_realism_mode"),
        "matched_observation_count": payload.get("event_execution_summary", {}).get("matched_observation_count"),
        "cost_bps_round_trip_p95": payload.get("cost_bps_round_trip_p95"),
        "artifact_dir": result["written"]["run_dir"],
        "execution_realism_json": result["written"]["execution_realism_json"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
