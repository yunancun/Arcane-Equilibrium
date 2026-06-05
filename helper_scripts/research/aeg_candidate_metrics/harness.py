#!/usr/bin/env python3
"""AEG candidate metrics adapter CLI。"""

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
    from aeg_candidate_metrics import artifact as artifact_mod  # type: ignore
    from aeg_candidate_metrics import builder as builder_mod  # type: ignore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_and_write(args: argparse.Namespace) -> dict:
    report = builder_mod.load_report(Path(args.diagnostic_report_json))
    rows, summary = builder_mod.build_candidate_metrics(
        report,
        run_id=args.run_id,
        candidate_id=args.candidate_id,
        strategy_family=args.strategy_family,
        parameter_cell_id=args.parameter_cell_id,
    )
    written = artifact_mod.write_all(
        rows,
        summary,
        run_id=args.run_id,
        repo_root=_repo_root(),
        runtime_host=socket.gethostname(),
        artifact_root=Path(args.artifact_root) if args.artifact_root else None,
        session_id=args.session_id,
        created_by_role=args.created_by_role,
    )
    return {"summary": summary, "written": written}


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aeg_candidate_metrics.harness",
        description="AEG candidate per-regime metrics adapter (artifact-only)",
    )
    p.add_argument("--run-id", required=True, dest="run_id")
    p.add_argument("--diagnostic-report-json", required=True, dest="diagnostic_report_json")
    p.add_argument("--candidate-id", required=True, dest="candidate_id")
    p.add_argument("--strategy-family", required=True, dest="strategy_family")
    p.add_argument("--parameter-cell-id", default="default", dest="parameter_cell_id")
    p.add_argument("--artifact-root", default=None, dest="artifact_root")
    p.add_argument("--session-id", default=None, dest="session_id")
    p.add_argument("--created-by-role", default="E1", dest="created_by_role")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    result = build_and_write(args)
    summary = result["summary"]
    print(json.dumps({
        "run_id": summary["run_id"],
        "candidate_id": summary["candidate_id"],
        "selected_variant": summary["selected_variant"],
        "row_count": summary["row_count"],
        "metric_status_counts": summary["metric_status_counts"],
        "freshness_buckets": summary["freshness_buckets"],
        "artifact_dir": result["written"]["run_dir"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
