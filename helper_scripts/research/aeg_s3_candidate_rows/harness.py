#!/usr/bin/env python3
"""AEG-S3 candidate direct rows CLI。"""

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
    from aeg_s3_candidate_rows import artifact as artifact_mod  # type: ignore
    from aeg_s3_candidate_rows import builder as builder_mod  # type: ignore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_and_write(args: argparse.Namespace) -> dict:
    evidence = builder_mod.load_evidence(Path(args.candidate_evidence_json))
    direct_report, summary, sample_rows, daily_rows = builder_mod.build_direct_report(
        evidence,
        run_id=args.run_id,
    )
    written = artifact_mod.write_all(
        direct_report=direct_report,
        summary=summary,
        sample_rows=sample_rows,
        daily_rows=daily_rows,
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
        prog="aeg_s3_candidate_rows.harness",
        description="AEG-S3 candidate sample returns to direct candidate_regime_metrics report",
    )
    p.add_argument("--run-id", required=True, dest="run_id")
    p.add_argument("--candidate-evidence-json", required=True, dest="candidate_evidence_json")
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
        "strategy_family": summary["strategy_family"],
        "sample_count": summary["sample_count"],
        "n_regime_rows": summary["n_regime_rows"],
        "pbo_status": summary["pbo_status"],
        "artifact_dir": result["written"]["run_dir"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
