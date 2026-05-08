#!/usr/bin/env python3
"""F-08 ML training maintenance runner.

This is the cron-facing orchestrator for the five ML paths called out by the
2026-05-08 full-chain audit:

* mlde_demo_applier
* linucb_trainer
* quantile_trainer
* scorer_trainer
* mlde_shadow_advisor

The runner is intentionally thin. It wires existing module entry points,
records a compact status JSON, and treats insufficient training samples as a
non-fatal skip so production cron does not page on normal low-volume periods.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable


VALID_JOBS = (
    "linucb_trainer",
    "mlde_shadow_advisor",
    "mlde_demo_applier",
    "scorer_trainer",
    "quantile_trainer",
)
DEFAULT_JOBS = ",".join(VALID_JOBS)
DEFAULT_STRATEGIES = "grid_trading,ma_crossover,bb_breakout,bb_reversion,funding_arb"
DEFAULT_TRAINING_ENGINE_MODES = "demo"
DEFAULT_SHADOW_ENGINE_MODES = "demo,live_demo"

logger = logging.getLogger("ml_training_maintenance")


@dataclass
class JobResult:
    job: str
    status: str
    elapsed_ms: int
    detail: dict[str, Any]
    error: str = ""


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv(value: str | None, default: str) -> list[str]:
    raw = value if value is not None else default
    return [part.strip() for part in raw.split(",") if part.strip()]


def _repo_root_from_file() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_repo_imports(base_dir: Path) -> None:
    """Make both ``program_code.*`` and top-level ``ml_training`` importable."""
    for path in (base_dir, base_dir / "program_code"):
        s = str(path)
        if s not in sys.path:
            sys.path.insert(0, s)


def _resolve_dsn(cli_dsn: str | None) -> str | None:
    return (
        cli_dsn
        or os.environ.get("OPENCLAW_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
    )


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _expected_training_skip(error: str) -> bool:
    lowered = (error or "").lower()
    return lowered.startswith("insufficient samples")


def _run_linucb(dsn: str | None, args: argparse.Namespace) -> JobResult:
    start = time.monotonic()
    if not dsn:
        return JobResult(
            "linucb_trainer",
            "skipped",
            _elapsed_ms(start),
            {},
            "no_database_url",
        )
    try:
        from ml_training.linucb_trainer import (  # type: ignore
            CANONICAL_FEATURE_NAMES_V1,
            LinUcbTrainConfig,
            train_all_arms,
        )

        cfg = LinUcbTrainConfig(
            feature_names=list(CANONICAL_FEATURE_NAMES_V1),
            engine_mode=args.linucb_engine_mode,
            reward_scale_bps=args.linucb_reward_scale_bps,
            observation_source="mlde_edge_training_rows",
            max_age_days=args.max_age_days,
        )
        rows = train_all_arms(dsn, cfg)
        detail = {
            "engine_mode": args.linucb_engine_mode,
            "arms": len(rows),
            "total_pulls": sum(row.n_pulls_after for row in rows),
            "converged_arms": sum(1 for row in rows if row.converged),
        }
        return JobResult("linucb_trainer", "ok", _elapsed_ms(start), detail)
    except Exception as exc:  # noqa: BLE001
        return JobResult(
            "linucb_trainer",
            "error",
            _elapsed_ms(start),
            {},
            f"{type(exc).__name__}: {exc}",
        )


def _run_shadow_advisor(dsn: str | None, args: argparse.Namespace) -> JobResult:
    start = time.monotonic()
    if not dsn:
        return JobResult(
            "mlde_shadow_advisor",
            "skipped",
            _elapsed_ms(start),
            {},
            "no_database_url",
        )
    try:
        from ml_training.mlde_shadow_advisor import (  # type: ignore
            config_from_env,
            generate_shadow_recommendations,
        )

        runs: list[dict[str, Any]] = []
        for mode in args.shadow_engine_modes:
            summary = generate_shadow_recommendations(
                dsn,
                config_from_env(engine_mode=mode),
                dry_run=args.dry_run,
            )
            runs.append(summary)
        detail = {
            "engine_modes": args.shadow_engine_modes,
            "runs": runs,
            "dry_run": args.dry_run,
        }
        return JobResult("mlde_shadow_advisor", "ok", _elapsed_ms(start), detail)
    except Exception as exc:  # noqa: BLE001
        return JobResult(
            "mlde_shadow_advisor",
            "error",
            _elapsed_ms(start),
            {},
            f"{type(exc).__name__}: {exc}",
        )


def _run_demo_applier(dsn: str | None, args: argparse.Namespace) -> JobResult:
    start = time.monotonic()
    if not dsn:
        return JobResult(
            "mlde_demo_applier",
            "skipped",
            _elapsed_ms(start),
            {},
            "no_database_url",
        )
    try:
        from ml_training.mlde_demo_applier import (  # type: ignore
            config_from_env,
            run_mlde_demo_applier,
        )

        cfg = config_from_env()
        if args.dry_run:
            cfg = replace(cfg, dry_run=True)
        summary = run_mlde_demo_applier(dsn, cfg)
        return JobResult(
            "mlde_demo_applier",
            "ok",
            _elapsed_ms(start),
            {"summary": summary, "dry_run": bool(getattr(cfg, "dry_run", False))},
        )
    except Exception as exc:  # noqa: BLE001
        return JobResult(
            "mlde_demo_applier",
            "error",
            _elapsed_ms(start),
            {},
            f"{type(exc).__name__}: {exc}",
        )


def _run_training_pipeline(
    job_name: str,
    *,
    use_quantile: bool,
    dsn: str | None,
    args: argparse.Namespace,
) -> JobResult:
    start = time.monotonic()
    if not dsn and not args.dry_run:
        return JobResult(job_name, "skipped", _elapsed_ms(start), {}, "no_database_url")
    try:
        from program_code.ml_training.run_training_pipeline import (  # type: ignore
            PipelineConfig,
            run_pipeline,
        )

        runs: list[dict[str, Any]] = []
        fatal_errors: list[str] = []
        output_dir = Path(args.output_dir) / job_name
        for engine_mode in args.training_engine_modes:
            for strategy in args.strategies:
                cfg = PipelineConfig(
                    strategy_type=strategy,
                    symbol=args.symbol,
                    output_dir=str(output_dir / engine_mode / strategy),
                    dsn=dsn,
                    min_samples=args.min_samples,
                    dry_run=args.dry_run,
                    skip_onnx=True,
                    use_quantile_predictor=use_quantile,
                    engine_mode=engine_mode,
                    onnx_validate_samples=args.onnx_validate_samples,
                )
                result = run_pipeline(cfg)
                status = "ok" if result.success else "skipped"
                if not result.success and not _expected_training_skip(result.error):
                    status = "error"
                    fatal_errors.append(f"{engine_mode}/{strategy}: {result.error}")
                runs.append(
                    {
                        "engine_mode": engine_mode,
                        "strategy": strategy,
                        "status": status,
                        "success": result.success,
                        "error": result.error,
                        "stages": result.stages_completed,
                        "verdict": result.verdict,
                        "acceptance_report_path": result.acceptance_report_path,
                    }
                )
        detail = {
            "use_quantile_predictor": use_quantile,
            "engine_modes": args.training_engine_modes,
            "strategies": args.strategies,
            "runs": runs,
            "dry_run": args.dry_run,
        }
        if fatal_errors:
            return JobResult(
                job_name,
                "error",
                _elapsed_ms(start),
                detail,
                "; ".join(fatal_errors),
            )
        return JobResult(job_name, "ok", _elapsed_ms(start), detail)
    except Exception as exc:  # noqa: BLE001
        return JobResult(
            job_name,
            "error",
            _elapsed_ms(start),
            {},
            f"{type(exc).__name__}: {exc}",
        )


def _run_job(job: str, dsn: str | None, args: argparse.Namespace) -> JobResult:
    if job == "linucb_trainer":
        return _run_linucb(dsn, args)
    if job == "mlde_shadow_advisor":
        return _run_shadow_advisor(dsn, args)
    if job == "mlde_demo_applier":
        return _run_demo_applier(dsn, args)
    if job == "scorer_trainer":
        return _run_training_pipeline(
            "scorer_trainer", use_quantile=False, dsn=dsn, args=args
        )
    if job == "quantile_trainer":
        return _run_training_pipeline(
            "quantile_trainer", use_quantile=True, dsn=dsn, args=args
        )
    return JobResult(job, "error", 0, {}, "unknown_job")


def _write_status(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(target)


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="F-08 ML training maintenance runner")
    parser.add_argument("--base-dir", default=str(_repo_root_from_file()))
    parser.add_argument("--dsn", default=None)
    parser.add_argument(
        "--jobs",
        default=os.environ.get("OPENCLAW_ML_CRON_JOBS", DEFAULT_JOBS),
        help=f"Comma-separated job list. Valid: {', '.join(VALID_JOBS)}",
    )
    parser.add_argument(
        "--strategies",
        default=os.environ.get("OPENCLAW_ML_CRON_STRATEGIES", DEFAULT_STRATEGIES),
    )
    parser.add_argument(
        "--training-engine-modes",
        default=os.environ.get(
            "OPENCLAW_ML_CRON_TRAINING_ENGINE_MODES",
            DEFAULT_TRAINING_ENGINE_MODES,
        ),
    )
    parser.add_argument(
        "--shadow-engine-modes",
        default=os.environ.get(
            "OPENCLAW_ML_CRON_SHADOW_ENGINE_MODES",
            DEFAULT_SHADOW_ENGINE_MODES,
        ),
    )
    parser.add_argument(
        "--linucb-engine-mode",
        default=os.environ.get("OPENCLAW_MLDE_LINUCB_ENGINE_MODE", "demo_live_demo"),
    )
    parser.add_argument(
        "--linucb-reward-scale-bps",
        type=float,
        default=float(os.environ.get("OPENCLAW_MLDE_LINUCB_REWARD_SCALE_BPS", "100.0")),
    )
    parser.add_argument(
        "--symbol",
        default=os.environ.get("OPENCLAW_ML_CRON_SYMBOL", None),
        help="Symbol filter. Omit or use ALL for pooled training.",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=int(os.environ.get("OPENCLAW_ML_CRON_MIN_SAMPLES", "200")),
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=int(os.environ.get("OPENCLAW_ML_CRON_MAX_AGE_DAYS", "90")),
    )
    parser.add_argument(
        "--onnx-validate-samples",
        type=int,
        default=int(os.environ.get("OPENCLAW_ML_CRON_ONNX_VALIDATE_SAMPLES", "1000")),
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get(
            "OPENCLAW_ML_CRON_OUTPUT_DIR",
            os.path.join(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"), "models", "ml_training_maintenance"),
        ),
    )
    parser.add_argument("--status-json", default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=_env_bool("OPENCLAW_ML_CRON_DRY_RUN", False),
    )
    parser.add_argument("--log-level", default=os.environ.get("OPENCLAW_ML_CRON_LOG_LEVEL", "INFO"))
    args = parser.parse_args(list(argv) if argv is not None else None)

    args.jobs = _csv(args.jobs, DEFAULT_JOBS)
    args.strategies = _csv(args.strategies, DEFAULT_STRATEGIES)
    args.training_engine_modes = _csv(
        args.training_engine_modes, DEFAULT_TRAINING_ENGINE_MODES
    )
    args.shadow_engine_modes = _csv(args.shadow_engine_modes, DEFAULT_SHADOW_ENGINE_MODES)
    args.symbol = None if args.symbol in {None, "", "ALL"} else args.symbol

    invalid = sorted(set(args.jobs) - set(VALID_JOBS))
    if invalid:
        parser.error(f"invalid jobs: {', '.join(invalid)}")
    return args


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    base_dir = Path(args.base_dir).resolve()
    _ensure_repo_imports(base_dir)

    dsn = _resolve_dsn(args.dsn)
    started = time.time()
    results = [_run_job(job, dsn, args) for job in args.jobs]
    payload = {
        "runner": "ml_training_maintenance",
        "started_epoch": started,
        "finished_epoch": time.time(),
        "dry_run": args.dry_run,
        "jobs": [asdict(result) for result in results],
    }
    payload["status"] = "error" if any(r.status == "error" for r in results) else "ok"
    _write_status(args.status_json, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if payload["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
