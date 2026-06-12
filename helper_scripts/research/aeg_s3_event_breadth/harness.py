#!/usr/bin/env python3
"""AEG-S3 event breadth CLI."""

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
    from aeg_s3_event_breadth import builder as builder_mod  # type: ignore

try:
    from aeg_breadth_ladder import artifact as artifact_mod
    from aeg_breadth_ladder import healthcheck as hc_mod
    from aeg_breadth_ladder import ladder as ladder_mod
    from aeg_breadth_ladder import tiers as tiers_mod
    from aeg_breadth_ladder import universe_artifact as ua_mod
    from aeg_breadth_ladder.harness import assemble_tier_results
except ImportError:  # pragma: no cover
    _research = Path(__file__).resolve().parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_breadth_ladder import artifact as artifact_mod  # type: ignore
    from aeg_breadth_ladder import healthcheck as hc_mod  # type: ignore
    from aeg_breadth_ladder import ladder as ladder_mod  # type: ignore
    from aeg_breadth_ladder import tiers as tiers_mod  # type: ignore
    from aeg_breadth_ladder import universe_artifact as ua_mod  # type: ignore
    from aeg_breadth_ladder.harness import assemble_tier_results  # type: ignore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _parse_utc(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    parsed = builder_mod._parse_ts(value)  # internal parser deliberately reused by CLI.
    return parsed.isoformat() if parsed is not None else None


def _summary_time(summary: Optional[dict], *keys: str) -> Optional[str]:
    if not isinstance(summary, dict):
        return None
    for key in keys:
        val = summary.get(key)
        parsed = _parse_utc(str(val)) if val else None
        if parsed:
            return parsed
    return None


def _resolve_time_bounds(
    *,
    args: argparse.Namespace,
    fnd2_summary: Optional[dict],
    evaluator: builder_mod.EventEvidenceEvaluator,
) -> tuple[str, str, str]:
    evidence_start, evidence_end = builder_mod.evidence_window(evaluator.samples)
    window_start = (
        _parse_utc(args.window_start)
        or _summary_time(fnd2_summary, "window_start_utc", "window_start")
        or evidence_start
    )
    window_end = (
        _parse_utc(args.window_end)
        or _summary_time(fnd2_summary, "window_end_utc", "window_end")
        or evidence_end
    )
    asof = (
        _parse_utc(args.asof)
        or _summary_time(fnd2_summary, "asof_utc", "asof", "created_at_utc")
        or window_end
    )
    if not (asof and window_start and window_end):
        raise ValueError("missing_time_bounds: provide --asof/--window-start/--window-end")
    return asof, window_start, window_end


def _read_fnd2_summary(fnd2_run_dir: Path) -> Optional[dict]:
    path = fnd2_run_dir / "universe_summary.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_and_write(args: argparse.Namespace) -> dict:
    evidence_path = Path(args.candidate_evidence_json)
    fnd2_run_dir = Path(args.fnd2_run_dir)
    evidence = builder_mod.load_evidence(evidence_path)
    evaluator = builder_mod.EventEvidenceEvaluator(evidence)

    universe_rows, meta = ua_mod.load_fnd2_universe(fnd2_run_dir)
    tiers_by_name = tiers_mod.assemble_tiers(universe_rows)
    tiers_mod.assert_nested_invariant(tiers_by_name)
    alive_mask = ua_mod.build_alive_mask(universe_rows)
    seen_delisted_map = ua_mod.build_seen_delisted_map(universe_rows)
    tier_results = assemble_tier_results(
        evaluator,
        tiers_by_name=tiers_by_name,
        alive_mask=alive_mask,
        seen_delisted_map=seen_delisted_map,
    )

    quality, pit_mode, exclusion = ua_mod.tier_quality_and_exclusion()
    fnd2_summary = _read_fnd2_summary(fnd2_run_dir)
    asof, window_start, window_end = _resolve_time_bounds(
        args=args,
        fnd2_summary=fnd2_summary,
        evaluator=evaluator,
    )
    rows, summary = ladder_mod.build_ladder(
        tier_results,
        run_id=args.run_id,
        candidate_id=evaluator.candidate_id,
        asof_utc=asof,
        window_start_utc=window_start,
        window_end_utc=window_end,
        fnd2_universe_id=meta["fnd2_universe_id"],
        fnd2_run_id=meta["fnd2_run_id"],
        tier_quality_by_name=quality,
        tier_rank_pit_mode_by_name=pit_mode,
        promotion_exclusion_by_name=exclusion,
    )

    if fnd2_summary is None:
        hc_status, hc_msg = (
            "WARN",
            f"FND-2 universe_summary.json missing: {fnd2_run_dir / 'universe_summary.json'}",
        )
    else:
        hc_status, hc_msg = hc_mod.check_aeg_breadth_universe_pit_payload(summary, fnd2_summary)
    summary["survivorship_healthcheck"] = {"status": hc_status, "message": hc_msg}
    summary["event_breadth_adapter"] = {
        "candidate_evidence_json": str(evidence_path),
        "raw_sample_count": len(evaluator.samples) + len(evaluator.rejected_samples),
        "valid_sample_count": len(evaluator.samples),
        "rejected_sample_count": len(evaluator.rejected_samples),
        "pbo_status": "measured" if evaluator.pbo is not None else "missing_or_insufficient",
        "policy": "single_symbol_event_samples_filtered_by_fnd2_alive_mask",
    }

    artifact_root = Path(args.artifact_root) if args.artifact_root else None
    written = artifact_mod.write_all(
        rows,
        summary,
        run_id=args.run_id,
        candidate_id=evaluator.candidate_id,
        fnd2_universe_id=meta["fnd2_universe_id"],
        fnd2_run_id=meta["fnd2_run_id"],
        source_tables=[str(evidence_path), str(fnd2_run_dir)],
        repo_root=_repo_root(),
        runtime_host=socket.gethostname(),
        artifact_root=artifact_root,
        session_id=args.session_id,
        created_by_role=args.created_by_role,
    )
    if hc_status == "FAIL":
        raise RuntimeError(f"event breadth survivorship healthcheck FAIL: {hc_msg}")

    return {
        "summary": summary,
        "written": written,
        "row_count": len(rows),
        "tiers": {key: len(value) for key, value in tiers_by_name.items()},
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aeg_s3_event_breadth.harness",
        description="Build true FND-2 PIT breadth_ladder artifacts for AEG-S3 event candidates",
    )
    p.add_argument("--run-id", required=True, dest="run_id")
    p.add_argument("--candidate-evidence-json", required=True, dest="candidate_evidence_json")
    p.add_argument("--fnd2-run-dir", required=True, dest="fnd2_run_dir")
    p.add_argument("--asof", default=None, dest="asof")
    p.add_argument("--window-start", default=None, dest="window_start")
    p.add_argument("--window-end", default=None, dest="window_end")
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
        "row_count": result["row_count"],
        "breadth_artifact_dir": result["written"]["run_dir"],
        "survivorship_healthcheck": summary.get("survivorship_healthcheck"),
        "verdict_hint": summary.get("verdict_hint"),
        "event_breadth_policy": summary["event_breadth_adapter"]["policy"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
