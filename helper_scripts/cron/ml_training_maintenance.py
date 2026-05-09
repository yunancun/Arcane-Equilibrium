#!/usr/bin/env python3
"""F-08 ML training maintenance runner.

This is the cron-facing orchestrator for W-AUDIT-4 F-08 ML maintenance.
It runs both the operational MLDE maintenance jobs and the five legacy ML
scripts explicitly called out by the 2026-05-08 full-chain audit:

* mlde_demo_applier
* linucb_trainer
* quantile_trainer
* scorer_trainer
* mlde_shadow_advisor
* thompson_sampling
* optuna_optimizer
* cpcv_validator
* dl3_foundation
* weekly_report_generator

The runner is intentionally thin. It wires existing module entry points,
records a compact status JSON, and treats insufficient training samples as a
non-fatal skip so production cron does not page on normal low-volume periods.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CORE_JOBS = (
    "linucb_trainer",
    "mlde_shadow_advisor",
    "mlde_demo_applier",
    "scorer_trainer",
    "quantile_trainer",
)
AUDIT_JOBS = (
    "thompson_sampling",
    "optuna_optimizer",
    "cpcv_validator",
    "dl3_foundation",
    "weekly_report_generator",
)
VALID_JOBS = CORE_JOBS + AUDIT_JOBS
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


def _weekly_audit_due(args: argparse.Namespace) -> bool:
    """Return whether weekly legacy-audit jobs should run this cron cycle."""
    if args.force_audit_jobs:
        return True
    return datetime.now(timezone.utc).weekday() == args.audit_weekday


def _skip_not_due(job: str, start: float, args: argparse.Namespace) -> JobResult:
    return JobResult(
        job,
        "skipped",
        _elapsed_ms(start),
        {"audit_weekday": args.audit_weekday},
        "not_scheduled_for_this_weekday",
    )


def _pg_connect(dsn: str | None):
    if not dsn:
        return None
    try:
        import psycopg2  # type: ignore
    except ImportError:
        return None
    return psycopg2.connect(dsn)


def _fetch_recent_fill_returns(
    dsn: str,
    *,
    engine_modes: list[str],
    days: int,
    limit: int,
) -> dict[tuple[str, str, str], list[float]]:
    conn = _pg_connect(dsn)
    if conn is None:
        return {}
    try:
        grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(strategy_name, 'unknown') AS strategy_name,
                       symbol,
                       COALESCE(engine_mode, 'unknown') AS engine_mode,
                       (COALESCE(realized_pnl, 0) - ABS(COALESCE(fee, 0)))::float8
                FROM trading.fills
                WHERE ts >= NOW() - (%s || ' days')::interval
                  AND engine_mode = ANY(%s)
                  AND realized_pnl IS NOT NULL
                ORDER BY ts DESC
                LIMIT %s
                """,
                (days, engine_modes, limit),
            )
            for strategy, symbol, regime, net_pnl in cur.fetchall():
                grouped[(str(strategy), str(symbol), str(regime))].append(float(net_pnl or 0.0))
        return grouped
    finally:
        conn.close()


def _fetch_kline_history(
    dsn: str,
    *,
    symbol: str,
    timeframe: str,
    limit: int,
) -> list[float]:
    conn = _pg_connect(dsn)
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT close::float8
                FROM market.klines
                WHERE symbol = %s AND timeframe = %s
                ORDER BY ts DESC
                LIMIT %s
                """,
                (symbol, timeframe, limit),
            )
            rows = [float(row[0]) for row in cur.fetchall()]
        rows.reverse()
        return rows
    finally:
        conn.close()


def _fetch_optuna_fills(
    dsn: str,
    *,
    strategy: str,
    symbol: str,
    engine_modes: list[str],
    days: int,
    limit: int,
) -> list[dict[str, float]]:
    conn = _pg_connect(dsn)
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    (COALESCE(realized_pnl, 0) - ABS(COALESCE(fee, 0)))::float8 AS pnl,
                    ABS(COALESCE(qty, 0) * COALESCE(price, 0))::float8 AS notional,
                    ABS(COALESCE(qty, 0))::float8 AS qty
                FROM trading.fills
                WHERE ts >= NOW() - (%s || ' days')::interval
                  AND engine_mode = ANY(%s)
                  AND strategy_name = %s
                  AND symbol = %s
                  AND realized_pnl IS NOT NULL
                ORDER BY ts DESC
                LIMIT %s
                """,
                (days, engine_modes, strategy, symbol, limit),
            )
            return [
                {"pnl": float(row[0] or 0.0), "notional": float(row[1] or 0.0), "qty": float(row[2] or 0.0)}
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


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


def _run_thompson_sampling(dsn: str | None, args: argparse.Namespace) -> JobResult:
    start = time.monotonic()
    if not _weekly_audit_due(args):
        return _skip_not_due("thompson_sampling", start, args)
    if not dsn:
        return JobResult("thompson_sampling", "skipped", _elapsed_ms(start), {}, "no_database_url")
    try:
        from program_code.ml_training.thompson_sampling import (  # type: ignore
            empirical_bayes_init,
            save_posteriors_to_pg,
        )

        returns_by_cell = _fetch_recent_fill_returns(
            dsn,
            engine_modes=args.audit_engine_modes,
            days=args.audit_lookback_days,
            limit=args.audit_fill_limit,
        )
        posteriors = {}
        for (strategy, symbol, regime), returns in returns_by_cell.items():
            if len(returns) < args.audit_min_fills_per_cell:
                continue
            posteriors[f"{strategy}|{symbol}|{regime}"] = empirical_bayes_init(returns)

        written = save_posteriors_to_pg(posteriors, dsn) if posteriors else 0
        return JobResult(
            "thompson_sampling",
            "ok",
            _elapsed_ms(start),
            {
                "cells_seen": len(returns_by_cell),
                "cells_written": len(posteriors),
                "rows_written": written,
                "lookback_days": args.audit_lookback_days,
                "engine_modes": args.audit_engine_modes,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return JobResult(
            "thompson_sampling",
            "error",
            _elapsed_ms(start),
            {},
            f"{type(exc).__name__}: {exc}",
        )


def _resolve_optuna_param_ranges(args: argparse.Namespace) -> tuple[str | None, str]:
    if args.optuna_param_ranges_json:
        return args.optuna_param_ranges_json, "env"
    try:
        from program_code.ml_training.optuna_optimizer import _send_ipc_command  # type: ignore

        result = _send_ipc_command(
            args.ipc_socket,
            "get_param_ranges",
            {"engine": args.optuna_engine, "strategy_name": args.optuna_strategy},
        )
        if isinstance(result, str):
            return result, "ipc"
        if isinstance(result, list):
            return json.dumps(result), "ipc"
        return json.dumps(result), "ipc"
    except Exception as exc:  # noqa: BLE001
        return None, f"unavailable:{type(exc).__name__}"


def _run_optuna_optimizer(dsn: str | None, args: argparse.Namespace) -> JobResult:
    start = time.monotonic()
    if not _weekly_audit_due(args):
        return _skip_not_due("optuna_optimizer", start, args)
    if not dsn:
        return JobResult("optuna_optimizer", "skipped", _elapsed_ms(start), {}, "no_database_url")
    try:
        from program_code.ml_training.optuna_optimizer import (  # type: ignore
            OptunaConfig,
            run_optimization,
        )

        param_ranges_json, source = _resolve_optuna_param_ranges(args)
        if not param_ranges_json:
            return JobResult(
                "optuna_optimizer",
                "skipped",
                _elapsed_ms(start),
                {"param_ranges_source": source},
                "param_ranges_unavailable",
            )
        fills = _fetch_optuna_fills(
            dsn,
            strategy=args.optuna_strategy,
            symbol=args.optuna_symbol,
            engine_modes=args.audit_engine_modes,
            days=args.audit_lookback_days,
            limit=args.audit_fill_limit,
        )
        cfg = OptunaConfig(
            sqlite_path=str(Path(args.output_dir) / "optuna" / "optuna_studies.log"),
            n_trials=args.optuna_trials,
            min_fills_required=args.optuna_min_fills,
        )
        result = run_optimization(
            args.optuna_strategy,
            args.optuna_symbol,
            args.optuna_regime,
            fills,
            param_ranges_json,
            config=cfg,
            ipc_socket_path=args.ipc_socket,
        )
        status = "ok" if result.get("status") in {"success", "insufficient_data", "no_adjustable_params"} else "error"
        return JobResult(
            "optuna_optimizer",
            status,
            _elapsed_ms(start),
            {
                "strategy": args.optuna_strategy,
                "symbol": args.optuna_symbol,
                "regime": args.optuna_regime,
                "fills": len(fills),
                "param_ranges_source": source,
                "result": result,
            },
            "" if status == "ok" else str(result.get("error", "")),
        )
    except Exception as exc:  # noqa: BLE001
        return JobResult(
            "optuna_optimizer",
            "error",
            _elapsed_ms(start),
            {},
            f"{type(exc).__name__}: {exc}",
        )


def _run_cpcv_validator(dsn: str | None, args: argparse.Namespace) -> JobResult:
    start = time.monotonic()
    if not _weekly_audit_due(args):
        return _skip_not_due("cpcv_validator", start, args)
    if not dsn:
        return JobResult("cpcv_validator", "skipped", _elapsed_ms(start), {}, "no_database_url")
    result = _run_training_pipeline(
        "cpcv_validator",
        use_quantile=False,
        dsn=dsn,
        args=args,
    )
    result.detail["entrypoint"] = "program_code.ml_training.cpcv_validator via run_training_pipeline"
    return result


def _run_dl3_foundation(dsn: str | None, args: argparse.Namespace) -> JobResult:
    start = time.monotonic()
    if not _weekly_audit_due(args):
        return _skip_not_due("dl3_foundation", start, args)
    if not dsn:
        return JobResult("dl3_foundation", "skipped", _elapsed_ms(start), {}, "no_database_url")
    try:
        from program_code.ml_training.dl3_foundation import (  # type: ignore
            Dl3Config,
            run_forecast,
        )

        runs: list[dict[str, Any]] = []
        for symbol in args.dl3_symbols:
            history = _fetch_kline_history(
                dsn,
                symbol=symbol,
                timeframe=args.dl3_timeframe,
                limit=args.dl3_history_limit,
            )
            if len(history) < args.dl3_min_history:
                runs.append({"symbol": symbol, "status": "skipped", "error": "insufficient_history", "history": len(history)})
                continue
            for model_name in args.dl3_models:
                cfg = Dl3Config(
                    model_name=model_name,
                    horizon_minutes=args.dl3_horizon_minutes,
                    timeout_seconds=args.dl3_timeout_seconds,
                )
                result = asyncio.run(
                    run_forecast(
                        cfg,
                        symbol=symbol,
                        history_close=history,
                        timestamp_ms=int(time.time() * 1000),
                        dsn=dsn,
                    )
                )
                runs.append(
                    {
                        "symbol": symbol,
                        "model": model_name,
                        "ok": result.ok,
                        "latency_ms": result.latency_ms,
                        "error": result.error_msg,
                    }
                )
        return JobResult(
            "dl3_foundation",
            "ok",
            _elapsed_ms(start),
            {"runs": runs, "timeframe": args.dl3_timeframe},
        )
    except Exception as exc:  # noqa: BLE001
        return JobResult(
            "dl3_foundation",
            "error",
            _elapsed_ms(start),
            {},
            f"{type(exc).__name__}: {exc}",
        )


def _run_weekly_report_generator(dsn: str | None, args: argparse.Namespace) -> JobResult:
    start = time.monotonic()
    if not _weekly_audit_due(args):
        return _skip_not_due("weekly_report_generator", start, args)
    if not dsn:
        return JobResult("weekly_report_generator", "skipped", _elapsed_ms(start), {}, "no_database_url")
    try:
        from program_code.ml_training.weekly_report_generator import (  # type: ignore
            current_week_iso,
            main as weekly_report_main,
        )

        week = current_week_iso()
        output = Path(args.output_dir) / "weekly_report" / f"phase4_{week}.md"
        rc = weekly_report_main(
            [
                "--week",
                week,
                "--output",
                str(output),
                "--dsn",
                dsn,
                "--persist",
            ]
        )
        return JobResult(
            "weekly_report_generator",
            "ok" if rc == 0 else "error",
            _elapsed_ms(start),
            {"week_iso": week, "output": str(output), "persist": True},
            "" if rc == 0 else f"weekly_report_generator exited {rc}",
        )
    except Exception as exc:  # noqa: BLE001
        return JobResult(
            "weekly_report_generator",
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
    if job == "thompson_sampling":
        return _run_thompson_sampling(dsn, args)
    if job == "optuna_optimizer":
        return _run_optuna_optimizer(dsn, args)
    if job == "cpcv_validator":
        return _run_cpcv_validator(dsn, args)
    if job == "dl3_foundation":
        return _run_dl3_foundation(dsn, args)
    if job == "weekly_report_generator":
        return _run_weekly_report_generator(dsn, args)
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
    parser.add_argument(
        "--audit-engine-modes",
        default=os.environ.get("OPENCLAW_ML_CRON_AUDIT_ENGINE_MODES", "demo,live_demo"),
    )
    parser.add_argument(
        "--audit-lookback-days",
        type=int,
        default=int(os.environ.get("OPENCLAW_ML_CRON_AUDIT_LOOKBACK_DAYS", "14")),
    )
    parser.add_argument(
        "--audit-fill-limit",
        type=int,
        default=int(os.environ.get("OPENCLAW_ML_CRON_AUDIT_FILL_LIMIT", "5000")),
    )
    parser.add_argument(
        "--audit-min-fills-per-cell",
        type=int,
        default=int(os.environ.get("OPENCLAW_ML_CRON_AUDIT_MIN_FILLS_PER_CELL", "5")),
    )
    parser.add_argument(
        "--audit-weekday",
        type=int,
        default=int(os.environ.get("OPENCLAW_ML_CRON_AUDIT_WEEKDAY", "6")),
        help="UTC weekday for legacy audit jobs; Monday=0, Sunday=6.",
    )
    parser.add_argument(
        "--force-audit-jobs",
        action="store_true",
        default=_env_bool("OPENCLAW_ML_CRON_FORCE_AUDIT_JOBS", False),
    )
    parser.add_argument(
        "--ipc-socket",
        default=os.environ.get(
            "OPENCLAW_IPC_SOCKET",
            os.path.join(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"), "engine.sock"),
        ),
    )
    parser.add_argument("--optuna-engine", default=os.environ.get("OPENCLAW_ML_CRON_OPTUNA_ENGINE", "demo"))
    parser.add_argument("--optuna-strategy", default=os.environ.get("OPENCLAW_ML_CRON_OPTUNA_STRATEGY", "ma_crossover"))
    parser.add_argument("--optuna-symbol", default=os.environ.get("OPENCLAW_ML_CRON_OPTUNA_SYMBOL", "BTCUSDT"))
    parser.add_argument("--optuna-regime", default=os.environ.get("OPENCLAW_ML_CRON_OPTUNA_REGIME", "live_observed"))
    parser.add_argument(
        "--optuna-param-ranges-json",
        default=os.environ.get("OPENCLAW_ML_CRON_OPTUNA_PARAM_RANGES_JSON", None),
    )
    parser.add_argument(
        "--optuna-trials",
        type=int,
        default=int(os.environ.get("OPENCLAW_ML_CRON_OPTUNA_TRIALS", "10")),
    )
    parser.add_argument(
        "--optuna-min-fills",
        type=int,
        default=int(os.environ.get("OPENCLAW_ML_CRON_OPTUNA_MIN_FILLS", "80")),
    )
    parser.add_argument(
        "--dl3-symbols",
        default=os.environ.get("OPENCLAW_ML_CRON_DL3_SYMBOLS", "BTCUSDT,ETHUSDT"),
    )
    parser.add_argument(
        "--dl3-models",
        default=os.environ.get("OPENCLAW_ML_CRON_DL3_MODELS", "chronos-t5-tiny,timesfm-1.0-200m"),
    )
    parser.add_argument(
        "--dl3-timeframe",
        default=os.environ.get("OPENCLAW_ML_CRON_DL3_TIMEFRAME", "1m"),
    )
    parser.add_argument(
        "--dl3-history-limit",
        type=int,
        default=int(os.environ.get("OPENCLAW_ML_CRON_DL3_HISTORY_LIMIT", "512")),
    )
    parser.add_argument(
        "--dl3-min-history",
        type=int,
        default=int(os.environ.get("OPENCLAW_ML_CRON_DL3_MIN_HISTORY", "64")),
    )
    parser.add_argument(
        "--dl3-horizon-minutes",
        type=int,
        default=int(os.environ.get("OPENCLAW_ML_CRON_DL3_HORIZON_MINUTES", "60")),
    )
    parser.add_argument(
        "--dl3-timeout-seconds",
        type=int,
        default=int(os.environ.get("OPENCLAW_ML_CRON_DL3_TIMEOUT_SECONDS", "60")),
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
    args.audit_engine_modes = _csv(args.audit_engine_modes, "demo,live_demo")
    args.dl3_symbols = _csv(args.dl3_symbols, "BTCUSDT,ETHUSDT")
    args.dl3_models = _csv(args.dl3_models, "chronos-t5-tiny,timesfm-1.0-200m")
    args.symbol = None if args.symbol in {None, "", "ALL"} else args.symbol

    invalid = sorted(set(args.jobs) - set(VALID_JOBS))
    if invalid:
        parser.error(f"invalid jobs: {', '.join(invalid)}")
    if args.audit_weekday < 0 or args.audit_weekday > 6:
        parser.error("--audit-weekday must be 0..6 (Monday=0, Sunday=6)")
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
