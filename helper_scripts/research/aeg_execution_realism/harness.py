#!/usr/bin/env python3
"""AEG execution-realism builder CLI。"""

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
except ImportError:  # pragma: no cover - 直接執行檔案路徑時
    _here = Path(__file__).resolve()
    _research = _here.parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_execution_realism import artifact as artifact_mod  # type: ignore
    from aeg_execution_realism import builder as builder_mod  # type: ignore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_and_write(args: argparse.Namespace) -> dict:
    raw = builder_mod.load_input(Path(args.input_json))
    payload = builder_mod.evaluate(raw)
    written = artifact_mod.write_all(
        payload,
        run_id=args.run_id,
        repo_root=_repo_root(),
        runtime_host=socket.gethostname(),
        artifact_root=Path(args.artifact_root) if args.artifact_root else None,
        session_id=args.session_id,
        created_by_role=args.created_by_role,
    )
    return {"payload": payload, "written": written}


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aeg_execution_realism.harness",
        description="AEG execution-realism artifact builder (artifact-only)",
    )
    p.add_argument("--run-id", required=True, dest="run_id")
    p.add_argument("--input-json", required=True, dest="input_json")
    p.add_argument("--artifact-root", default=None, dest="artifact_root")
    p.add_argument("--session-id", default=None, dest="session_id")
    p.add_argument("--created-by-role", default="E1", dest="created_by_role")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    result = build_and_write(args)
    payload = result["payload"]
    out = {
        "run_id": args.run_id,
        "candidate_id": payload.get("candidate_id"),
        "status": payload["status"],
        "reject_reasons": payload["reject_reasons"],
        "execution_realism_mode": payload["execution_realism_mode"],
        "cost_bps_round_trip_p95": payload["cost_bps_round_trip_p95"],
        "artifact_dir": result["written"]["run_dir"],
        "execution_realism_json": result["written"]["execution_realism_json"],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
