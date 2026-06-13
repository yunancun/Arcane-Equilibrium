#!/usr/bin/env python3
"""V5.8 pause readiness CLI."""

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
    from v58_pause_readiness import artifact as artifact_mod  # type: ignore
    from v58_pause_readiness import builder as builder_mod  # type: ignore


def _repo_root_from_file() -> Path:
    return Path(__file__).resolve().parents[3]


def build_and_write(args: argparse.Namespace) -> dict:
    repo_root = Path(args.repo_root).resolve() if args.repo_root else _repo_root_from_file()
    summary = builder_mod.build_summary(
        repo_root=repo_root,
        run_id=args.run_id,
        gate_watch_latest_json=args.gate_watch_latest_json,
    )
    written = artifact_mod.write_all(
        summary=summary,
        run_id=args.run_id,
        repo_root=repo_root,
        artifact_root=Path(args.artifact_root) if args.artifact_root else None,
        runtime_host=socket.gethostname(),
        session_id=args.session_id,
        created_by_role=args.created_by_role,
    )
    return {"summary": summary, "written": written}


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="v58_pause_readiness.harness",
        description="Build a repository-local V5.8 pause/readiness handoff artifact.",
    )
    p.add_argument("--run-id", required=True, dest="run_id")
    p.add_argument("--repo-root", default=None, dest="repo_root")
    p.add_argument("--artifact-root", default=None, dest="artifact_root")
    p.add_argument("--gate-watch-latest-json", default=None, dest="gate_watch_latest_json")
    p.add_argument("--session-id", default=None, dest="session_id")
    p.add_argument("--created-by-role", default="PM", dest="created_by_role")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    result = build_and_write(args)
    summary = result["summary"]
    print(json.dumps({
        "run_id": summary["run_id"],
        "pause_readiness_status": summary["pause_readiness_status"],
        "counts": summary["counts"],
        "gate_watch": summary["gate_watch"],
        "unfreeze_gate": summary["unfreeze_gate"],
        "artifact_dir": result["written"]["run_dir"],
        "summary_json": result["written"]["summary"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if summary["counts"]["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
