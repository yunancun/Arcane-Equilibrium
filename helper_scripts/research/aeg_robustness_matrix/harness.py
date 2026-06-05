#!/usr/bin/env python3
"""AEG robustness matrix builder CLI."""

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
    from aeg_robustness_matrix import artifact as artifact_mod  # type: ignore
    from aeg_robustness_matrix import builder as builder_mod  # type: ignore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_and_write(args: argparse.Namespace) -> dict:
    regime = builder_mod.load_regime_artifact(Path(args.regime_run_dir))
    breadth = builder_mod.load_breadth_artifact(Path(args.breadth_run_dir))
    candidate_metrics = builder_mod.load_candidate_metrics_artifact(
        Path(args.candidate_metrics_run_dir) if args.candidate_metrics_run_dir else None
    )
    execution = builder_mod.load_execution_realism(
        Path(args.execution_realism_json) if args.execution_realism_json else None
    )
    rows, summary = builder_mod.build_matrix(
        run_id=args.run_id,
        regime_artifact=regime,
        breadth_artifact=breadth,
        execution_realism=execution,
        strategy_family=args.strategy_family,
        parameter_cell_id=args.parameter_cell_id,
        candidate_metrics=candidate_metrics,
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
        prog="aeg_robustness_matrix.harness",
        description="AEG-S2 robustness matrix builder (artifact-only verdict_matrix)",
    )
    p.add_argument("--run-id", required=True, dest="run_id")
    p.add_argument("--regime-run-dir", required=True, dest="regime_run_dir")
    p.add_argument("--breadth-run-dir", required=True, dest="breadth_run_dir")
    p.add_argument("--candidate-metrics-run-dir", default=None, dest="candidate_metrics_run_dir")
    p.add_argument("--execution-realism-json", default=None, dest="execution_realism_json")
    p.add_argument("--strategy-family", default="unknown", dest="strategy_family")
    p.add_argument("--parameter-cell-id", default="default", dest="parameter_cell_id")
    p.add_argument("--artifact-root", default=None, dest="artifact_root")
    p.add_argument("--session-id", default=None, dest="session_id")
    p.add_argument("--created-by-role", default="E1", dest="created_by_role")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    result = build_and_write(args)
    out = {
        "run_id": result["summary"]["run_id"],
        "candidate_id": result["summary"].get("candidate_id"),
        "row_count": result["summary"]["row_count"],
        "final_label_counts": result["summary"]["final_label_counts"],
        "coverage_gate_status": result["summary"]["coverage_gate_status"],
        "feature_lineage_status": result["summary"]["feature_lineage_status"],
        "survivorship_mode": result["summary"]["survivorship_mode"],
        "execution_realism_mode": result["summary"]["execution_realism_mode"],
        "artifact_dir": result["written"]["run_dir"],
        "parquet_result": result["written"]["parquet_result"],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
