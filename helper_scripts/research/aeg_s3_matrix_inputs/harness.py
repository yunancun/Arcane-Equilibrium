#!/usr/bin/env python3
"""AEG-S3 candidate-specific matrix input artifact CLI."""

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
    _here = Path(__file__).resolve()
    _research = _here.parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_s3_matrix_inputs import builder as builder_mod  # type: ignore

try:
    from aeg_breadth_ladder import artifact as breadth_artifact_mod
    from aeg_execution_realism import artifact as execution_artifact_mod
except ImportError:  # pragma: no cover
    _here = Path(__file__).resolve()
    _research = _here.parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_breadth_ladder import artifact as breadth_artifact_mod  # type: ignore
    from aeg_execution_realism import artifact as execution_artifact_mod  # type: ignore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_and_write(args: argparse.Namespace) -> dict:
    candidate_metrics = builder_mod.load_candidate_metrics(Path(args.candidate_metrics_run_dir))
    breadth_run_dir = getattr(args, "breadth_run_dir", None)
    execution_realism_json = getattr(args, "execution_realism_json", None)
    provided_breadth = (
        builder_mod.load_breadth_artifact(Path(breadth_run_dir))
        if breadth_run_dir
        else None
    )
    provided_execution = (
        builder_mod.load_execution_realism(Path(execution_realism_json))
        if execution_realism_json
        else None
    )
    rows, breadth_summary, execution_payload, summary = builder_mod.build_inputs(
        candidate_metrics,
        run_id=args.run_id,
        breadth_artifact=provided_breadth,
        execution_realism=provided_execution,
    )
    artifact_root = Path(args.artifact_root) if args.artifact_root else None
    host = socket.gethostname()
    if provided_breadth is None:
        breadth_written = breadth_artifact_mod.write_all(
            rows,
            breadth_summary,
            run_id=args.run_id,
            candidate_id=breadth_summary["candidate_id"],
            fnd2_universe_id=breadth_summary["fnd2_universe_id"],
            fnd2_run_id=breadth_summary["fnd2_run_id"],
            source_tables=[str(Path(args.candidate_metrics_run_dir))],
            repo_root=_repo_root(),
            runtime_host=host,
            artifact_root=artifact_root,
            session_id=args.session_id,
            created_by_role=args.created_by_role,
        )
        breadth_written["mode"] = "generated_placeholder"
    else:
        breadth_dir = Path(breadth_run_dir)
        breadth_written = {
            "mode": "provided",
            "run_dir": str(breadth_dir),
            "breadth_ladder_csv": str(breadth_dir / "breadth_ladder.csv"),
            "breadth_ladder_summary": str(breadth_dir / "breadth_ladder_summary.json"),
            "artifact_index": str(breadth_dir / "artifact_index.json"),
        }

    if provided_execution is None:
        execution_run_id = args.execution_run_id or f"{args.run_id}_execution_realism"
        execution_written = execution_artifact_mod.write_all(
            execution_payload,
            run_id=execution_run_id,
            repo_root=_repo_root(),
            runtime_host=host,
            artifact_root=artifact_root,
            session_id=args.session_id,
            created_by_role=args.created_by_role,
        )
        execution_written["mode"] = "generated_placeholder"
    else:
        execution_path = Path(execution_realism_json)
        execution_written = {
            "mode": "provided",
            "run_dir": str(execution_path.parent),
            "execution_realism_json": str(execution_path),
        }
    return {
        "summary": summary,
        "breadth_summary": breadth_summary,
        "execution_payload": execution_payload,
        "breadth_written": breadth_written,
        "execution_written": execution_written,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aeg_s3_matrix_inputs.harness",
        description=(
            "Build candidate-specific, fail-closed breadth and execution-realism "
            "inputs for aeg_robustness_matrix"
        ),
    )
    p.add_argument("--run-id", required=True, dest="run_id")
    p.add_argument("--candidate-metrics-run-dir", required=True, dest="candidate_metrics_run_dir")
    p.add_argument("--breadth-run-dir", default=None, dest="breadth_run_dir")
    p.add_argument("--execution-realism-json", default=None, dest="execution_realism_json")
    p.add_argument("--execution-run-id", default=None, dest="execution_run_id")
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
        "strategy_family": summary["strategy_family"],
        "parameter_cell_id": summary["parameter_cell_id"],
        "breadth_input_mode": summary["breadth_input_mode"],
        "breadth_policy": summary["breadth_policy"],
        "breadth_artifact_dir": result["breadth_written"]["run_dir"],
        "execution_input_mode": summary["execution_input_mode"],
        "execution_realism_json": result["execution_written"]["execution_realism_json"],
        "execution_realism_status": summary["execution_realism_status"],
        "execution_realism_mode": summary["execution_realism_mode"],
        "execution_realism_reject_reasons": summary["execution_realism_reject_reasons"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
