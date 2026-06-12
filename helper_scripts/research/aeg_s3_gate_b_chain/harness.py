#!/usr/bin/env python3
"""AEG-S3 Gate-B listing_fade evidence-chain CLI."""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from . import RUNNER_VERSION, SUMMARY_SCHEMA_VERSION
    from . import artifact as artifact_mod
except ImportError:  # pragma: no cover
    _research = Path(__file__).resolve().parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_s3_gate_b_chain import RUNNER_VERSION, SUMMARY_SCHEMA_VERSION  # type: ignore
    from aeg_s3_gate_b_chain import artifact as artifact_mod  # type: ignore

try:
    from aeg_candidate_metrics import harness as candidate_metrics_harness
    from aeg_robustness_matrix import harness as robustness_harness
    from aeg_s3_candidate_rows import harness as candidate_rows_harness
    from aeg_s3_event_breadth import harness as event_breadth_harness
    from aeg_s3_event_execution_realism import harness as event_execution_harness
    from aeg_s3_execution_observations import harness as execution_observations_harness
    from aeg_s3_listing_fade import harness as listing_fade_harness
except ImportError:  # pragma: no cover
    _research = Path(__file__).resolve().parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_candidate_metrics import harness as candidate_metrics_harness  # type: ignore
    from aeg_robustness_matrix import harness as robustness_harness  # type: ignore
    from aeg_s3_candidate_rows import harness as candidate_rows_harness  # type: ignore
    from aeg_s3_event_breadth import harness as event_breadth_harness  # type: ignore
    from aeg_s3_event_execution_realism import harness as event_execution_harness  # type: ignore
    from aeg_s3_execution_observations import harness as execution_observations_harness  # type: ignore
    from aeg_s3_listing_fade import harness as listing_fade_harness  # type: ignore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _artifact_root_arg(args: argparse.Namespace) -> Optional[str]:
    return str(Path(args.artifact_root)) if args.artifact_root else None


def _ns(**kwargs: Any) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _require_matrix_inputs(args: argparse.Namespace) -> bool:
    matrix_requested = bool(args.fnd2_run_dir or args.regime_run_dir)
    if matrix_requested and not (args.fnd2_run_dir and args.regime_run_dir):
        raise ValueError("formal_matrix_requires_both_fnd2_run_dir_and_regime_run_dir")
    return matrix_requested


def _step(name: str, *, run_id: str, artifact_dir: Optional[str], summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "run_id": run_id,
        "artifact_dir": artifact_dir,
        "summary": summary,
    }


def _chain_status(
    *,
    matrix_requested: bool,
    execution_payload: dict[str, Any],
    matrix_summary: Optional[dict[str, Any]],
) -> str:
    if matrix_summary is not None:
        if matrix_summary.get("non_bull_independent_pass") is True:
            return "COMPLETE_MATRIX_HAS_DURABLE_NON_BULL"
        return "COMPLETE_MATRIX_NON_PROMOTABLE"
    if str(execution_payload.get("status") or "").upper() == "PASS":
        return "COMPLETE_EXECUTION_REALISM_PASS"
    if matrix_requested:
        return "COMPLETE_MATRIX_SKIPPED_AFTER_EXECUTION_REALISM_FAIL"
    return "COMPLETE_EXECUTION_REALISM_FAIL"


def build_and_write(args: argparse.Namespace) -> dict[str, Any]:
    matrix_requested = _require_matrix_inputs(args)
    artifact_root = _artifact_root_arg(args)
    session_id = args.session_id
    role = args.created_by_role
    base = args.run_id

    listing_run_id = f"{base}_listing_fade_evidence"
    listing_result = listing_fade_harness.build_and_write(_ns(
        gate_b_run_dir=args.gate_b_run_dir,
        capture_events_jsonl=None,
        run_id=listing_run_id,
        horizon_s=args.horizon_s,
        round_trip_cost_bps=args.round_trip_cost_bps,
        k_trials=args.k_trials,
        candidate_id=args.candidate_id,
        regime_by_date_json=args.regime_by_date_json,
        default_regime=args.default_regime,
        oos_start_date=args.oos_start_date,
        allow_slow_capture=args.allow_slow_capture,
        include_default_pbo_grid=args.include_default_pbo_grid,
        pbo_grid_json=args.pbo_grid_json,
        artifact_root=artifact_root,
        session_id=session_id,
        created_by_role=role,
    ))
    listing_summary = listing_result["summary"]
    candidate_evidence_json = listing_result["written"]["candidate_evidence"]
    candidate_id = listing_summary["candidate_id"]
    strategy_family = listing_summary["strategy_family"]
    parameter_cell_id = listing_summary["parameter_cell_id"]

    candidate_rows_run_id = f"{base}_candidate_rows"
    candidate_rows_result = candidate_rows_harness.build_and_write(_ns(
        run_id=candidate_rows_run_id,
        candidate_evidence_json=candidate_evidence_json,
        artifact_root=artifact_root,
        session_id=session_id,
        created_by_role=role,
    ))
    direct_report_json = candidate_rows_result["written"]["candidate_direct_metrics_report"]

    candidate_metrics_run_id = f"{base}_candidate_metrics"
    candidate_metrics_result = candidate_metrics_harness.build_and_write(_ns(
        run_id=candidate_metrics_run_id,
        diagnostic_report_json=direct_report_json,
        candidate_id=candidate_id,
        strategy_family=strategy_family,
        parameter_cell_id=parameter_cell_id,
        artifact_root=artifact_root,
        session_id=session_id,
        created_by_role=role,
    ))

    execution_obs_run_id = f"{base}_execution_observations"
    execution_obs_result = execution_observations_harness.build_and_write(_ns(
        run_id=execution_obs_run_id,
        candidate_evidence_json=candidate_evidence_json,
        gate_b_run_dir=args.gate_b_run_dir,
        maker_fee_bps=args.maker_fee_bps,
        taker_fee_bps=args.taker_fee_bps,
        order_notional_usdt=args.order_notional_usdt,
        evidence_source_tier=args.evidence_source_tier,
        order_style=args.order_style,
        slippage_floor_bps=args.slippage_floor_bps,
        capacity_window_s=args.capacity_window_s,
        allow_slow_capture=args.allow_slow_capture,
        artifact_root=artifact_root,
        session_id=session_id,
        created_by_role=role,
    ))
    execution_observations_jsonl = execution_obs_result["written"]["execution_observations_jsonl"]

    event_execution_run_id = f"{base}_event_execution_realism"
    event_execution_result = event_execution_harness.build_and_write(_ns(
        run_id=event_execution_run_id,
        candidate_evidence_json=candidate_evidence_json,
        execution_observations_jsonl=execution_observations_jsonl,
        evidence_source_tier=None,
        order_style=None,
        capacity_notional_usdt=None,
        order_availability_status=None,
        artifact_root=artifact_root,
        session_id=session_id,
        created_by_role=role,
    ))
    execution_realism_json = event_execution_result["written"]["execution_realism_json"]

    event_breadth_result: Optional[dict[str, Any]] = None
    matrix_result: Optional[dict[str, Any]] = None
    if matrix_requested:
        event_breadth_run_id = f"{base}_event_breadth"
        event_breadth_result = event_breadth_harness.build_and_write(_ns(
            run_id=event_breadth_run_id,
            candidate_evidence_json=candidate_evidence_json,
            fnd2_run_dir=args.fnd2_run_dir,
            asof=args.asof,
            window_start=args.window_start,
            window_end=args.window_end,
            artifact_root=artifact_root,
            session_id=session_id,
            created_by_role=role,
        ))

        matrix_run_id = f"{base}_formal_matrix"
        matrix_result = robustness_harness.build_and_write(_ns(
            run_id=matrix_run_id,
            regime_run_dir=args.regime_run_dir,
            breadth_run_dir=event_breadth_result["written"]["run_dir"],
            candidate_metrics_run_dir=candidate_metrics_result["written"]["run_dir"],
            execution_realism_json=execution_realism_json,
            strategy_family=strategy_family,
            parameter_cell_id=parameter_cell_id,
            artifact_root=artifact_root,
            session_id=session_id,
            created_by_role=role,
        ))

    steps = [
        _step(
            "listing_fade_evidence",
            run_id=listing_run_id,
            artifact_dir=listing_result["written"]["run_dir"],
            summary={
                "sample_count": listing_summary["sample_count"],
                "rejected_sample_count": listing_summary["rejected_sample_count"],
                "reject_reasons": listing_summary["reject_reasons"],
            },
        ),
        _step(
            "candidate_rows",
            run_id=candidate_rows_run_id,
            artifact_dir=candidate_rows_result["written"]["run_dir"],
            summary={
                "sample_count": candidate_rows_result["summary"]["sample_count"],
                "n_regime_rows": candidate_rows_result["summary"]["n_regime_rows"],
                "pbo_status": candidate_rows_result["summary"]["pbo_status"],
            },
        ),
        _step(
            "candidate_metrics",
            run_id=candidate_metrics_run_id,
            artifact_dir=candidate_metrics_result["written"]["run_dir"],
            summary={
                "row_count": candidate_metrics_result["summary"]["row_count"],
                "metric_status_counts": candidate_metrics_result["summary"]["metric_status_counts"],
                "freshness_buckets": candidate_metrics_result["summary"]["freshness_buckets"],
            },
        ),
        _step(
            "execution_observations",
            run_id=execution_obs_run_id,
            artifact_dir=execution_obs_result["written"]["run_dir"],
            summary={
                "observation_count": execution_obs_result["summary"]["observation_count"],
                "rejected_observation_count": execution_obs_result["summary"]["rejected_observation_count"],
                "reject_reasons": execution_obs_result["summary"]["reject_reasons"],
            },
        ),
        _step(
            "event_execution_realism",
            run_id=event_execution_run_id,
            artifact_dir=event_execution_result["written"]["run_dir"],
            summary={
                "status": event_execution_result["payload"].get("status"),
                "execution_realism_mode": event_execution_result["payload"].get("execution_realism_mode"),
                "reject_reasons": event_execution_result["payload"].get("reject_reasons"),
                "matched_observation_count": (
                    event_execution_result["payload"].get("event_execution_summary", {})
                    .get("matched_observation_count")
                ),
            },
        ),
    ]
    if event_breadth_result is not None:
        steps.append(_step(
            "event_breadth",
            run_id=f"{base}_event_breadth",
            artifact_dir=event_breadth_result["written"]["run_dir"],
            summary={
                "row_count": event_breadth_result["row_count"],
                "survivorship_healthcheck": event_breadth_result["summary"].get("survivorship_healthcheck"),
                "verdict_hint": event_breadth_result["summary"].get("verdict_hint"),
            },
        ))
    if matrix_result is not None:
        steps.append(_step(
            "formal_matrix",
            run_id=f"{base}_formal_matrix",
            artifact_dir=matrix_result["written"]["run_dir"],
            summary={
                "row_count": matrix_result["summary"]["row_count"],
                "coverage_gate_status": matrix_result["summary"]["coverage_gate_status"],
                "survivorship_mode": matrix_result["summary"]["survivorship_mode"],
                "execution_realism_mode": matrix_result["summary"]["execution_realism_mode"],
                "final_label_counts": matrix_result["summary"]["final_label_counts"],
            },
        ))

    matrix_summary = matrix_result["summary"] if matrix_result is not None else None
    chain_status = _chain_status(
        matrix_requested=matrix_requested,
        execution_payload=event_execution_result["payload"],
        matrix_summary=matrix_summary,
    )
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "run_id": base,
        "chain_status": chain_status,
        "matrix_requested": matrix_requested,
        "gate_b_run_dir": str(Path(args.gate_b_run_dir)),
        "candidate_id": candidate_id,
        "strategy_family": strategy_family,
        "parameter_cell_id": parameter_cell_id,
        "steps": steps,
        "outputs": {
            "candidate_evidence_json": candidate_evidence_json,
            "candidate_rows_run_dir": candidate_rows_result["written"]["run_dir"],
            "candidate_metrics_run_dir": candidate_metrics_result["written"]["run_dir"],
            "execution_observations_jsonl": execution_observations_jsonl,
            "execution_realism_json": execution_realism_json,
            "event_breadth_run_dir": (
                event_breadth_result["written"]["run_dir"] if event_breadth_result is not None else None
            ),
            "formal_matrix_run_dir": (
                matrix_result["written"]["run_dir"] if matrix_result is not None else None
            ),
        },
        "gate_snapshot": {
            "listing_sample_count": listing_summary["sample_count"],
            "listing_pbo_status": listing_summary["pbo_status"],
            "execution_observation_count": execution_obs_result["summary"]["observation_count"],
            "execution_realism_status": event_execution_result["payload"].get("status"),
            "execution_realism_reject_reasons": event_execution_result["payload"].get("reject_reasons"),
            "matrix_final_label_counts": (
                matrix_summary.get("final_label_counts") if matrix_summary is not None else None
            ),
        },
        "notes": [
            "This wrapper orchestrates existing artifact-only harnesses; it is not a collector.",
            "Execution realism FAIL and matrix non-promotable labels are gate results, not orchestration errors.",
            "Gate-B v0.1 execution observations use publicTrade prints and do not claim orderbook-depth fill realism.",
        ],
    }
    written = artifact_mod.write_all(
        summary=summary,
        run_id=base,
        repo_root=_repo_root(),
        artifact_root=Path(args.artifact_root) if args.artifact_root else None,
        runtime_host=socket.gethostname(),
        session_id=session_id,
        created_by_role=role,
    )
    return {
        "summary": summary,
        "written": written,
        "listing": listing_result,
        "candidate_rows": candidate_rows_result,
        "candidate_metrics": candidate_metrics_result,
        "execution_observations": execution_obs_result,
        "event_execution_realism": event_execution_result,
        "event_breadth": event_breadth_result,
        "matrix": matrix_result,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aeg_s3_gate_b_chain.harness",
        description=(
            "Run the artifact-only Gate-B listing_fade evidence chain: listing evidence, "
            "candidate metrics, execution observations, execution realism, and optionally "
            "event breadth + formal robustness matrix."
        ),
    )
    p.add_argument("--run-id", required=True, dest="run_id")
    p.add_argument("--gate-b-run-dir", required=True, dest="gate_b_run_dir")
    p.add_argument("--horizon-s", required=True, type=int, dest="horizon_s")
    p.add_argument("--round-trip-cost-bps", required=True, type=float, dest="round_trip_cost_bps")
    p.add_argument("--k-trials", required=True, type=int, dest="k_trials")
    p.add_argument("--order-notional-usdt", required=True, type=float, dest="order_notional_usdt")
    p.add_argument("--candidate-id", default="listing_fade", dest="candidate_id")
    p.add_argument("--regime-by-date-json", default=None, dest="regime_by_date_json")
    p.add_argument("--default-regime", default=None, dest="default_regime")
    p.add_argument("--oos-start-date", default=None, dest="oos_start_date")
    p.add_argument("--allow-slow-capture", action="store_true", dest="allow_slow_capture")
    p.add_argument("--include-default-pbo-grid", action="store_true", dest="include_default_pbo_grid")
    p.add_argument("--pbo-grid-json", default=None, dest="pbo_grid_json")
    p.add_argument("--maker-fee-bps", type=float, default=2.0, dest="maker_fee_bps")
    p.add_argument("--taker-fee-bps", type=float, default=5.5, dest="taker_fee_bps")
    p.add_argument("--evidence-source-tier", default="calibrated_replay", dest="evidence_source_tier")
    p.add_argument("--order-style", default="taker", dest="order_style")
    p.add_argument("--slippage-floor-bps", type=float, default=0.0, dest="slippage_floor_bps")
    p.add_argument("--capacity-window-s", type=int, default=60, dest="capacity_window_s")
    p.add_argument("--fnd2-run-dir", default=None, dest="fnd2_run_dir")
    p.add_argument("--regime-run-dir", default=None, dest="regime_run_dir")
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
        "chain_status": summary["chain_status"],
        "candidate_id": summary["candidate_id"],
        "parameter_cell_id": summary["parameter_cell_id"],
        "listing_sample_count": summary["gate_snapshot"]["listing_sample_count"],
        "listing_pbo_status": summary["gate_snapshot"]["listing_pbo_status"],
        "execution_observation_count": summary["gate_snapshot"]["execution_observation_count"],
        "execution_realism_status": summary["gate_snapshot"]["execution_realism_status"],
        "execution_realism_reject_reasons": summary["gate_snapshot"]["execution_realism_reject_reasons"],
        "matrix_final_label_counts": summary["gate_snapshot"]["matrix_final_label_counts"],
        "artifact_dir": result["written"]["run_dir"],
        "summary_json": result["written"]["summary"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
