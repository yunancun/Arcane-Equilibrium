"""Build local Gate-B full-chain readiness preflight summaries."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
import datetime as dt
import json
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from . import RUNNER_VERSION, SUMMARY_SCHEMA_VERSION
except ImportError:  # pragma: no cover
    import sys

    _research = Path(__file__).resolve().parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_s3_gate_b_preflight import RUNNER_VERSION, SUMMARY_SCHEMA_VERSION  # type: ignore

try:
    from aeg_s3_listing_fade import builder as listing_builder
except ImportError:  # pragma: no cover
    import sys

    _research = Path(__file__).resolve().parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_s3_listing_fade import builder as listing_builder  # type: ignore


GATE_B_REQUIRED_FILES = ("capture_lag.jsonl", "markout.jsonl", "ws_publictrade.jsonl")
FND2_REQUIRED_FILES = ("universe.csv", "universe_summary.json")
REGIME_REQUIRED_FILES = ("regime_labels.csv", "regime_summary.json")
GATE_WATCH_ACTIONABLE_START = "ACTIONABLE_START_NOW"
GATE_WATCH_ACTIONABLE_SCHEDULE = "ACTIONABLE_SCHEDULE"
GATE_WATCH_OPERATOR_REVIEW = "OPERATOR_REVIEW"
GATE_WATCH_WATCH_ONLY = "WATCH_ONLY"
GATE_WATCH_NO_CANDIDATE = "NO_ACTIONABLE_CANDIDATE"
GATE_WATCH_SOURCE_FAILURE = "SOURCE_FAILURE"
PROBE_DURATION_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class LocatedArtifact:
    path: Optional[Path]
    source: str
    required_files: tuple[str, ...]

    @property
    def missing_files(self) -> list[str]:
        if self.path is None:
            return list(self.required_files)
        return [name for name in self.required_files if not (self.path / name).exists()]

    @property
    def present(self) -> bool:
        return self.path is not None and not self.missing_files

    def to_summary(self) -> dict[str, Any]:
        return {
            "path": str(self.path) if self.path is not None else None,
            "source": self.source,
            "present": self.present,
            "required_files": list(self.required_files),
            "missing_files": self.missing_files,
        }


def default_openclaw_root() -> Path:
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base)


def default_gate_b_root() -> Path:
    return default_openclaw_root() / "aeg_gate_b_runs"


def default_alpha_history_root() -> Path:
    return default_openclaw_root() / "alpha_history_runs"


def default_gate_watch_latest_json() -> Path:
    return default_openclaw_root() / "gate_b_watch" / "gate_b_watch_latest.json"


def _dir_mtime(path: Path) -> float:
    mtimes = [path.stat().st_mtime]
    for child in path.iterdir():
        try:
            mtimes.append(child.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes)


def _json_or_none(path: Path) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _valid_gate_b_dir(path: Path) -> bool:
    return all((path / name).exists() for name in GATE_B_REQUIRED_FILES)


def _valid_fnd2_dir(path: Path) -> bool:
    summary = _json_or_none(path / "universe_summary.json")
    if summary is None:
        return False
    return bool(summary.get("run_id") and summary.get("universe_id"))


def _valid_regime_dir(path: Path) -> bool:
    summary = _json_or_none(path / "regime_summary.json")
    if summary is None:
        return False
    health = summary.get("healthcheck")
    health_status = str(health.get("status") if isinstance(health, dict) else "").upper()
    return (
        summary.get("classifier_version") == "aeg_regime_v0.1.0"
        and health_status == "PASS"
        and bool(summary.get("run_id"))
    )


def _latest_dir_with_files(
    root: Path,
    required_files: tuple[str, ...],
    validator: Optional[Callable[[Path], bool]] = None,
) -> Optional[Path]:
    if not root.exists() or not root.is_dir():
        return None
    candidates = [
        path for path in root.iterdir()
        if path.is_dir() and all((path / name).exists() for name in required_files)
    ]
    if validator is not None:
        candidates = [path for path in candidates if validator(path)]
    if not candidates:
        return None
    return max(candidates, key=_dir_mtime)


def locate_artifact(
    *,
    explicit_dir: Optional[str],
    root: Path,
    required_files: tuple[str, ...],
    validator: Optional[Callable[[Path], bool]] = None,
) -> LocatedArtifact:
    if explicit_dir:
        return LocatedArtifact(Path(explicit_dir), "explicit", required_files)
    latest = _latest_dir_with_files(root, required_files, validator)
    return LocatedArtifact(latest, f"latest_under:{root}", required_files)


def _check(name: str, status: str, message: str, **extra: Any) -> dict[str, Any]:
    out = {"name": name, "status": status, "message": message}
    out.update(extra)
    return out


def _quote_command(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def _parse_utc(value: Any) -> Optional[dt.datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _safe_candidate_count(value: Any, name: str) -> int:
    if isinstance(value, dict):
        raw = value.get(name)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0
    return 0


def _gate_watch_probe_command(candidate: dict[str, Any]) -> dict[str, Any]:
    symbol = str(candidate.get("symbol") or "unknown").lower()
    event_date = str(
        candidate.get("event_time_utc")
        or candidate.get("launch_time_utc")
        or ""
    )[:10].replace("-", "")
    suffix = event_date or "manual"
    run_id = f"gate_b_{symbol}_{suffix}"
    argv = [
        "python3",
        "helper_scripts/research/aeg_gate_b_probe.py",
        "--duration-seconds",
        str(PROBE_DURATION_SECONDS),
        "--run-id",
        run_id,
    ]
    return {
        "symbol": candidate.get("symbol"),
        "trigger_type": candidate.get("trigger_type"),
        "recommended_action": candidate.get("recommended_action"),
        "action_reason": candidate.get("action_reason"),
        "event_time_utc": candidate.get("event_time_utc"),
        "launch_time_utc": candidate.get("launch_time_utc"),
        "suggested_probe": candidate.get("suggested_probe"),
        "argv": argv,
        "shell": "PYTHONPATH=helper_scripts/research:helper_scripts " + _quote_command(argv),
    }


def _candidate_digest(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": candidate.get("symbol"),
        "source": candidate.get("source"),
        "trigger_type": candidate.get("trigger_type"),
        "priority": candidate.get("priority"),
        "recommended_action": candidate.get("recommended_action"),
        "action_reason": candidate.get("action_reason"),
        "should_alert": candidate.get("should_alert"),
        "status": candidate.get("status"),
        "cur_auction_phase": candidate.get("cur_auction_phase"),
        "event_time_utc": candidate.get("event_time_utc"),
        "launch_time_utc": candidate.get("launch_time_utc"),
        "publish_time_utc": candidate.get("publish_time_utc"),
        "suggested_probe": candidate.get("suggested_probe"),
        "title": candidate.get("title"),
        "url": candidate.get("url"),
    }


def _operator_action_for_watch_status(status: str) -> tuple[str, str]:
    if status == GATE_WATCH_ACTIONABLE_START:
        return (
            "START_ISOLATED_24H_PROBE",
            "watcher_found_start_now_window_run_probe_then_preflight_full_chain",
        )
    if status == GATE_WATCH_ACTIONABLE_SCHEDULE:
        return (
            "SCHEDULE_ISOLATED_24H_PROBE",
            "watcher_found_future_window_schedule_probe_then_preflight_full_chain",
        )
    if status == GATE_WATCH_OPERATOR_REVIEW:
        return (
            "OPERATOR_REVIEW_REQUIRED",
            "watcher_found_candidate_that_needs_manual_review_before_probe",
        )
    if status == GATE_WATCH_WATCH_ONLY:
        return (
            "WAIT_FOR_ACTIONABLE_WATCH",
            "watcher_has_only_non_alertable_conversion_watch_do_not_start_probe",
        )
    if status == GATE_WATCH_NO_CANDIDATE:
        return (
            "WAIT_FOR_FRESH_GATE_B_WINDOW",
            "watcher_has_no_actionable_candidate_do_not_start_probe",
        )
    if status == GATE_WATCH_SOURCE_FAILURE:
        return (
            "FIX_WATCHER_SOURCE_HEALTH",
            "watcher_sources_failed_do_not_start_probe_from_this_artifact",
        )
    return ("REVIEW_UNKNOWN_WATCH_STATUS", f"unknown_gate_watch_status:{status}")


def analyze_gate_watch_latest(
    *,
    latest_json: Optional[str],
    max_age_hours: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    explicit = bool(latest_json)
    path = Path(latest_json) if latest_json else default_gate_watch_latest_json()
    base = {
        "path": str(path),
        "explicit": explicit,
        "present": path.exists(),
        "max_age_hours": max_age_hours,
        "policy": "local_gate_b_watch_artifact_only_no_network_no_probe_autostart",
    }
    if not path.exists():
        status = "FAIL" if explicit else "WARN"
        return {
            **base,
            "artifact_status": "MISSING",
            "operator_action": "WATCH_ARTIFACT_MISSING",
            "operator_message": "gate_b_watch_latest_json_missing",
            "candidate_counts": {},
            "top_candidates": [],
            "probe_command_hints": [],
        }, _check(
            "gate_watch_latest",
            status,
            "gate_watch_latest_json_missing",
            path=str(path),
            explicit=explicit,
        )

    payload = _json_or_none(path)
    if payload is None:
        return {
            **base,
            "artifact_status": "MALFORMED",
            "operator_action": "REVIEW_WATCH_ARTIFACT",
            "operator_message": "gate_watch_latest_json_malformed",
            "candidate_counts": {},
            "top_candidates": [],
            "probe_command_hints": [],
        }, _check("gate_watch_latest", "FAIL", "gate_watch_latest_json_malformed", path=str(path))

    generated = _parse_utc(payload.get("generated_at_utc"))
    now = dt.datetime.now(dt.timezone.utc)
    age_hours: Optional[float] = None
    stale = False
    if generated is None:
        stale = True
    else:
        age_hours = max(0.0, (now - generated).total_seconds() / 3600.0)
        stale = age_hours > max_age_hours

    watch_status = str(payload.get("status") or "UNKNOWN")
    operator_action, operator_message = _operator_action_for_watch_status(watch_status)
    candidates = [
        item for item in payload.get("candidates", [])
        if isinstance(item, dict)
    ]
    actionable = [
        candidate for candidate in candidates
        if candidate.get("recommended_action") in {"START_GATE_B_NOW", "SCHEDULE_GATE_B_WINDOW", "OPERATOR_REVIEW"}
    ]
    probe_hints = [_gate_watch_probe_command(candidate) for candidate in actionable[:5]]
    candidate_counts = payload.get("candidate_counts") if isinstance(payload.get("candidate_counts"), dict) else {}
    summary = {
        **base,
        "artifact_status": watch_status,
        "generated_at_utc": payload.get("generated_at_utc"),
        "age_hours": age_hours,
        "stale": stale,
        "candidate_counts": {
            "total": _safe_candidate_count(candidate_counts, "total"),
            "alertable": _safe_candidate_count(candidate_counts, "alertable"),
            "start_now": _safe_candidate_count(candidate_counts, "start_now"),
            "schedule": _safe_candidate_count(candidate_counts, "schedule"),
            "watch_only": _safe_candidate_count(candidate_counts, "watch_only"),
        },
        "alerts_sent": payload.get("alerts_sent"),
        "source_health": payload.get("source_health"),
        "operator_action": operator_action,
        "operator_message": operator_message,
        "top_candidates": [_candidate_digest(candidate) for candidate in candidates[:10]],
        "probe_command_hints": probe_hints,
        "probe_preconditions": payload.get("probe_preconditions"),
        "boundary": payload.get("boundary"),
    }
    if stale:
        return summary, _check(
            "gate_watch_latest",
            "FAIL",
            "gate_watch_latest_json_stale_or_missing_generated_at",
            path=str(path),
            generated_at_utc=payload.get("generated_at_utc"),
            age_hours=age_hours,
            max_age_hours=max_age_hours,
        )
    if watch_status == GATE_WATCH_SOURCE_FAILURE:
        return summary, _check(
            "gate_watch_latest",
            "FAIL",
            "gate_watch_sources_failed",
            path=str(path),
            source_health=payload.get("source_health"),
        )
    return summary, _check(
        "gate_watch_latest",
        "PASS",
        f"gate_watch_latest_status:{watch_status}",
        path=str(path),
        generated_at_utc=payload.get("generated_at_utc"),
        operator_action=operator_action,
    )


def build_full_chain_command(
    *,
    chain_run_id: str,
    gate_b_run_dir: Path,
    fnd2_run_dir: Path,
    regime_run_dir: Path,
    artifact_root: Path,
    horizon_s: int,
    round_trip_cost_bps: float,
    k_trials: int,
    default_regime: Optional[str],
    allow_slow_capture: bool,
    order_notional_usdt: float,
    slippage_floor_bps: float,
    include_default_pbo_grid: bool,
) -> list[str]:
    parts = [
        "python3",
        "-m",
        "aeg_s3_gate_b_chain.harness",
        "--run-id",
        chain_run_id,
        "--gate-b-run-dir",
        str(gate_b_run_dir),
        "--horizon-s",
        str(horizon_s),
        "--round-trip-cost-bps",
        f"{round_trip_cost_bps:g}",
        "--k-trials",
        str(k_trials),
        "--order-notional-usdt",
        f"{order_notional_usdt:g}",
        "--slippage-floor-bps",
        f"{slippage_floor_bps:g}",
        "--fnd2-run-dir",
        str(fnd2_run_dir),
        "--regime-run-dir",
        str(regime_run_dir),
        "--artifact-root",
        str(artifact_root),
    ]
    if default_regime:
        parts.extend(["--default-regime", default_regime])
    if allow_slow_capture:
        parts.append("--allow-slow-capture")
    if include_default_pbo_grid:
        parts.append("--include-default-pbo-grid")
    return parts


def _command_operator_guard(
    *,
    command_shell: Optional[str],
    readiness_status: str,
    gate_watch: dict[str, Any],
    sample_count: Any,
    min_listing_samples: int,
) -> dict[str, Any]:
    if not command_shell:
        return {
            "operator_recommended": False,
            "operator_status": "UNAVAILABLE",
            "operator_message": "full_chain_command_unavailable_until_required_artifacts_exist",
        }
    if readiness_status == "BLOCKED_PRECHECK_FAILED":
        return {
            "operator_recommended": False,
            "operator_status": "BLOCKED_PRECHECK_FAILED",
            "operator_message": "fix_precheck_failures_before_running_full_chain",
        }

    gate_action = str(gate_watch.get("operator_action") or "")
    try:
        samples = int(sample_count) if sample_count is not None else None
    except (TypeError, ValueError):
        samples = None

    if gate_action in {"START_ISOLATED_24H_PROBE", "SCHEDULE_ISOLATED_24H_PROBE"}:
        return {
            "operator_recommended": False,
            "operator_status": "RUN_ISOLATED_PROBE_BEFORE_FULL_CHAIN",
            "operator_message": "watcher_is_actionable_start_or_schedule_probe_first_then_rerun_preflight",
        }
    if gate_action in {"OPERATOR_REVIEW_REQUIRED", "REVIEW_UNKNOWN_WATCH_STATUS"}:
        return {
            "operator_recommended": False,
            "operator_status": "OPERATOR_REVIEW_REQUIRED",
            "operator_message": "review_gate_watch_candidate_before_running_probe_or_full_chain",
        }
    if samples is not None and samples < min_listing_samples:
        if gate_action in {"WAIT_FOR_ACTIONABLE_WATCH", "WAIT_FOR_FRESH_GATE_B_WINDOW"}:
            return {
                "operator_recommended": False,
                "operator_status": "HOLD_WAIT_FOR_ACTIONABLE_WATCH",
                "operator_message": "do_not_run_full_chain_from_wait_only_watch_and_under_sample_artifact",
            }
        return {
            "operator_recommended": False,
            "operator_status": "DIAGNOSTIC_ONLY_SAMPLE_BELOW_GATE",
            "operator_message": "full_chain_shell_is_diagnostic_only_until_listing_sample_gate_is_met",
        }
    return {
        "operator_recommended": True,
        "operator_status": "RUNNABLE_FOR_RESEARCH_REVIEW",
        "operator_message": "full_chain_command_is_runnable_but_still_requires_e2_mit_qc_review_before_promotion",
    }


def _listing_preview(
    *,
    gate_b_run_dir: Path,
    run_id: str,
    horizon_s: int,
    round_trip_cost_bps: float,
    k_trials: int,
    default_regime: Optional[str],
    allow_slow_capture: bool,
    include_default_pbo_grid: bool,
) -> dict[str, Any]:
    payload = listing_builder.load_gate_b_run(gate_b_run_dir)
    pbo_grid = (
        listing_builder.default_pbo_grid(cost_bps=round_trip_cost_bps)
        if include_default_pbo_grid
        else None
    )
    _evidence, summary = listing_builder.build_listing_fade_evidence(
        payload,
        source_type="gate_b_run",
        source_path=str(gate_b_run_dir),
        run_id=f"{run_id}_listing_preview",
        horizon_s=horizon_s,
        cost_bps=round_trip_cost_bps,
        k_trials=k_trials,
        default_regime=default_regime,
        allow_slow_capture=allow_slow_capture,
        pbo_grid=pbo_grid,
    )
    return {
        "sample_count": summary["sample_count"],
        "rejected_sample_count": summary["rejected_sample_count"],
        "reject_reasons": summary["reject_reasons"],
        "daily_return_count": summary["daily_return_count"],
        "pbo_status": summary["pbo_status"],
        "pbo_grid_cell_count": summary["pbo_grid_cell_count"],
        "pbo_grid_included_candidate_count": summary["pbo_grid_included_candidate_count"],
    }


def build_preflight_summary(
    *,
    run_id: str,
    chain_run_id: Optional[str],
    gate_b_root: Optional[str],
    alpha_history_root: Optional[str],
    artifact_root: Optional[str],
    gate_b_run_dir: Optional[str],
    fnd2_run_dir: Optional[str],
    regime_run_dir: Optional[str],
    horizon_s: int,
    round_trip_cost_bps: float,
    k_trials: int,
    default_regime: Optional[str],
    allow_slow_capture: bool,
    order_notional_usdt: float,
    slippage_floor_bps: float,
    include_default_pbo_grid: bool,
    min_listing_samples: int,
    gate_watch_latest_json: Optional[str],
    gate_watch_max_age_hours: float,
) -> dict[str, Any]:
    alpha_root = Path(alpha_history_root) if alpha_history_root else default_alpha_history_root()
    out_root = Path(artifact_root) if artifact_root else alpha_root
    gate_root = Path(gate_b_root) if gate_b_root else default_gate_b_root()
    chain_id = chain_run_id or f"{run_id}_full_chain"

    gate_b = locate_artifact(
        explicit_dir=gate_b_run_dir,
        root=gate_root,
        required_files=GATE_B_REQUIRED_FILES,
        validator=_valid_gate_b_dir,
    )
    fnd2 = locate_artifact(
        explicit_dir=fnd2_run_dir,
        root=alpha_root,
        required_files=FND2_REQUIRED_FILES,
        validator=_valid_fnd2_dir,
    )
    regime = locate_artifact(
        explicit_dir=regime_run_dir,
        root=alpha_root,
        required_files=REGIME_REQUIRED_FILES,
        validator=_valid_regime_dir,
    )
    gate_watch, gate_watch_check = analyze_gate_watch_latest(
        latest_json=gate_watch_latest_json,
        max_age_hours=gate_watch_max_age_hours,
    )

    checks: list[dict[str, Any]] = []
    for name, located in (("gate_b", gate_b), ("fnd2", fnd2), ("regime", regime)):
        if located.present:
            checks.append(_check(name, "PASS", f"{name}_artifact_ready", path=str(located.path)))
        else:
            checks.append(_check(
                name,
                "FAIL",
                f"{name}_artifact_missing_or_incomplete",
                path=str(located.path) if located.path is not None else None,
                missing_files=located.missing_files,
            ))
    checks.append(gate_watch_check)

    listing_preview: Optional[dict[str, Any]] = None
    if gate_b.present and gate_b.path is not None:
        try:
            listing_preview = _listing_preview(
                gate_b_run_dir=gate_b.path,
                run_id=run_id,
                horizon_s=horizon_s,
                round_trip_cost_bps=round_trip_cost_bps,
                k_trials=k_trials,
                default_regime=default_regime,
                allow_slow_capture=allow_slow_capture,
                include_default_pbo_grid=include_default_pbo_grid,
            )
            checks.append(_check(
                "listing_sample_gate",
                "PASS" if listing_preview["sample_count"] >= min_listing_samples else "WARN",
                (
                    "listing_sample_count_meets_gate"
                    if listing_preview["sample_count"] >= min_listing_samples
                    else "listing_sample_count_below_gate"
                ),
                sample_count=listing_preview["sample_count"],
                min_listing_samples=min_listing_samples,
            ))
            if include_default_pbo_grid:
                checks.append(_check(
                    "listing_pbo_gate",
                    "PASS" if listing_preview["pbo_status"] == "produced_candidate_grid" else "FAIL",
                    listing_preview["pbo_status"],
                    pbo_grid_included_candidate_count=listing_preview["pbo_grid_included_candidate_count"],
                ))
        except Exception as exc:
            checks.append(_check("listing_preview", "FAIL", f"listing_preview_error:{exc}"))

    hard_fail = any(row["status"] == "FAIL" for row in checks)
    sample_count = (listing_preview or {}).get("sample_count")
    if hard_fail:
        readiness_status = "BLOCKED_PRECHECK_FAILED"
    elif sample_count is not None and sample_count < min_listing_samples:
        readiness_status = "READY_BUT_SAMPLE_BELOW_GATE"
    else:
        readiness_status = "PASS_READY_FOR_FULL_CHAIN"

    command_parts: Optional[list[str]] = None
    command_shell: Optional[str] = None
    if gate_b.present and fnd2.present and regime.present and gate_b.path and fnd2.path and regime.path:
        command_parts = build_full_chain_command(
            chain_run_id=chain_id,
            gate_b_run_dir=gate_b.path,
            fnd2_run_dir=fnd2.path,
            regime_run_dir=regime.path,
            artifact_root=out_root,
            horizon_s=horizon_s,
            round_trip_cost_bps=round_trip_cost_bps,
            k_trials=k_trials,
            default_regime=default_regime,
            allow_slow_capture=allow_slow_capture,
            order_notional_usdt=order_notional_usdt,
            slippage_floor_bps=slippage_floor_bps,
            include_default_pbo_grid=include_default_pbo_grid,
        )
        command_shell = (
            "PYTHONPATH=helper_scripts/research:helper_scripts "
            + _quote_command(command_parts)
        )
    command_guard = _command_operator_guard(
        command_shell=command_shell,
        readiness_status=readiness_status,
        gate_watch=gate_watch,
        sample_count=sample_count,
        min_listing_samples=min_listing_samples,
    )

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "run_id": run_id,
        "chain_run_id": chain_id,
        "readiness_status": readiness_status,
        "selected_artifacts": {
            "gate_b_run_dir": str(gate_b.path) if gate_b.path is not None else None,
            "fnd2_run_dir": str(fnd2.path) if fnd2.path is not None else None,
            "regime_run_dir": str(regime.path) if regime.path is not None else None,
        },
        "artifact_roots": {
            "gate_b_root": str(gate_root),
            "alpha_history_root": str(alpha_root),
            "output_artifact_root": str(out_root),
        },
        "artifact_checks": {
            "gate_b": gate_b.to_summary(),
            "fnd2": fnd2.to_summary(),
            "regime": regime.to_summary(),
        },
        "gate_watch": gate_watch,
        "listing_preview": listing_preview,
        "checks": checks,
        "recommended_command": {
            "argv": command_parts,
            "shell": command_shell,
            "policy": "artifact_only_full_chain_no_collection_no_runtime_mutation",
            **command_guard,
        },
        "gate_parameters": {
            "horizon_s": horizon_s,
            "round_trip_cost_bps": round_trip_cost_bps,
            "k_trials": k_trials,
            "default_regime": default_regime,
            "allow_slow_capture": allow_slow_capture,
            "order_notional_usdt": order_notional_usdt,
            "slippage_floor_bps": slippage_floor_bps,
            "include_default_pbo_grid": include_default_pbo_grid,
            "min_listing_samples": min_listing_samples,
            "gate_watch_max_age_hours": gate_watch_max_age_hours,
        },
        "notes": [
            "Preflight only inspects local artifacts and builds the recommended command.",
            "Gate-B watcher input is a local artifact only; preflight never starts the probe.",
            "READY_BUT_SAMPLE_BELOW_GATE means the full command is runnable but not promotion-eligible.",
            "Full-chain completion is not promotion proof; E2/MIT/QC review remains required.",
        ],
    }


__all__ = [
    "FND2_REQUIRED_FILES",
    "GATE_B_REQUIRED_FILES",
    "REGIME_REQUIRED_FILES",
    "build_preflight_summary",
    "default_alpha_history_root",
    "default_gate_b_root",
    "default_gate_watch_latest_json",
]
