#!/usr/bin/env python3
"""Status and activation preflight for the cost-gate demo learning lane.

MODULE_NOTE:
  Purpose: summarize local learning-lane artifacts into one machine-readable
  activation state for operator/PM inspection.
  Boundary: read-only artifact/source inspection. No PG, Bybit, orders, auth,
  risk, config, or runtime mutation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.outcome_review import build_blocked_signal_outcome_review


DEFAULT_COST_GATE_LEARNING_LOOP_MAX_AGE_SECONDS = 3 * 60 * 60
DEFAULT_PLAN_MAX_AGE_SECONDS = 36 * 60 * 60
ACTIVATION_PREFLIGHT_SCHEMA_VERSION = (
    "cost_gate_demo_learning_lane_activation_preflight_v1"
)

REQUIRED_SOURCE_RELATIVE_PATHS = (
    "helper_scripts/cron/cost_gate_learning_lane_cron.sh",
    "helper_scripts/cron/install_cost_gate_learning_lane_cron.sh",
    "helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py",
    "helper_scripts/research/cost_gate_learning_lane/outcome_refresh.py",
    "helper_scripts/research/cost_gate_learning_lane/outcome_review.py",
    "helper_scripts/research/cost_gate_learning_lane/status.py",
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_dt(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _age_seconds(value: Any, *, now_utc: dt.datetime) -> float | None:
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    return max(0.0, (now_utc - parsed).total_seconds())


def _int(value: Any, default: int = 0) -> int:
    try:
        out = int(float(value))
    except (TypeError, ValueError):
        return default
    return out


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, f"malformed:{type(exc).__name__}"
    if not isinstance(data, dict):
        return None, "not_object"
    return data, None


def _latest_json_line(
    path: Path,
    *,
    prefix: str | None = None,
    max_scan_bytes: int = 4 * 1024 * 1024,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        return None, f"read_error:{type(exc).__name__}"

    scan = min(size, 262144)
    while scan <= min(size, max_scan_bytes):
        try:
            with open(path, "rb") as fh:
                start = max(0, size - scan)
                fh.seek(start, os.SEEK_SET)
                chunk = fh.read().decode("utf-8", errors="replace")
        except OSError as exc:
            return None, f"read_error:{type(exc).__name__}"

        lines = chunk.splitlines()
        if start > 0 and lines:
            lines = lines[1:]
        for raw_line in reversed(lines):
            line = raw_line.strip()
            if not line:
                continue
            if prefix:
                if not line.startswith(prefix):
                    continue
                line = line[len(prefix):]
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data, None
        if scan >= size or scan >= max_scan_bytes:
            break
        scan = min(size, scan * 2)
    return None, "no_json_status_line"


def _file_mtime_age(path: Path, *, now_utc: dt.datetime) -> tuple[bool, str | None, float | None]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return False, None, None
    except OSError:
        return False, None, None
    mtime = dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.timezone.utc)
    return True, mtime.isoformat(), max(0.0, (now_utc - mtime).total_seconds())


def summarize_cost_gate_learning_lane_ledger(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "ledger_path": str(path),
        "ledger_status": "MISSING",
        "ledger_source_error": None,
        "ledger_total_rows": 0,
        "ledger_malformed_line_count": 0,
        "admission_decision_count": 0,
        "admit_decision_count": 0,
        "order_authority_not_granted_count": 0,
        "allowed_to_submit_order_count": 0,
        "probe_outcome_count": 0,
        "blocked_signal_outcome_count": 0,
        "blocked_signal_positive_outcome_count": 0,
        "latest_record_type": None,
        "latest_generated_at_utc": None,
        "latest_admission_decision": None,
        "latest_side_cell_key": None,
        "avg_probe_outcome_net_bps": None,
        "avg_blocked_signal_outcome_net_bps": None,
        "blocked_signal_net_positive_pct": None,
        "blocked_signal_outcome_review": None,
        "blocked_signal_outcome_review_status": None,
        "blocked_signal_outcome_review_reason": None,
        "blocked_signal_outcome_review_next_trigger": None,
    }
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return summary
    except OSError as exc:
        summary["ledger_status"] = "READ_ERROR"
        summary["ledger_source_error"] = f"read_error:{type(exc).__name__}"
        return summary

    valid_rows: list[dict[str, Any]] = []
    probe_net_sum = 0.0
    blocked_net_sum = 0.0
    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            summary["ledger_malformed_line_count"] += 1
            summary["ledger_source_error"] = f"malformed_jsonl_line:{line_no}"
            continue
        if not isinstance(row, dict):
            summary["ledger_malformed_line_count"] += 1
            summary["ledger_source_error"] = f"non_object_jsonl_line:{line_no}"
            continue

        valid_rows.append(row)
        summary["ledger_total_rows"] += 1
        record_type = str(row.get("record_type") or "").strip()
        summary["latest_record_type"] = record_type or None
        generated_at = row.get("generated_at_utc")
        if generated_at:
            summary["latest_generated_at_utc"] = generated_at
        side_cell_key = row.get("side_cell_key")
        if side_cell_key:
            summary["latest_side_cell_key"] = side_cell_key

        if record_type == "probe_admission_decision":
            decision = str(row.get("decision") or "").strip()
            summary["admission_decision_count"] += 1
            summary["latest_admission_decision"] = decision or None
            if decision == "ADMIT_DEMO_LEARNING_PROBE":
                summary["admit_decision_count"] += 1
            if decision == "ORDER_AUTHORITY_NOT_GRANTED":
                summary["order_authority_not_granted_count"] += 1
            if row.get("allowed_to_submit_order") is True:
                summary["allowed_to_submit_order_count"] += 1
        elif record_type == "probe_outcome":
            net_bps = _float(row.get("realized_net_bps"))
            summary["probe_outcome_count"] += 1
            if net_bps is not None:
                probe_net_sum += net_bps
        elif record_type == "blocked_signal_outcome":
            net_bps = _float(row.get("realized_net_bps"))
            summary["blocked_signal_outcome_count"] += 1
            if net_bps is not None:
                blocked_net_sum += net_bps
                if net_bps > 0.0:
                    summary["blocked_signal_positive_outcome_count"] += 1

    if summary["ledger_total_rows"] == 0:
        summary["ledger_status"] = (
            "MALFORMED"
            if summary["ledger_malformed_line_count"] > 0
            else "EMPTY"
        )
    elif summary["blocked_signal_outcome_count"] > 0:
        summary["ledger_status"] = "BLOCKED_SIGNAL_OUTCOMES_PRESENT"
    elif summary["probe_outcome_count"] > 0:
        summary["ledger_status"] = "PROBE_OUTCOMES_PRESENT"
    elif summary["admission_decision_count"] > 0:
        summary["ledger_status"] = "ADMISSION_ROWS_PRESENT"
    else:
        summary["ledger_status"] = "OTHER_ROWS_PRESENT"

    if summary["probe_outcome_count"] > 0:
        summary["avg_probe_outcome_net_bps"] = probe_net_sum / summary["probe_outcome_count"]
    if summary["blocked_signal_outcome_count"] > 0:
        summary["avg_blocked_signal_outcome_net_bps"] = (
            blocked_net_sum / summary["blocked_signal_outcome_count"]
        )
        summary["blocked_signal_net_positive_pct"] = (
            summary["blocked_signal_positive_outcome_count"]
            / summary["blocked_signal_outcome_count"]
            * 100.0
        )
        review = build_blocked_signal_outcome_review(valid_rows)
        summary["blocked_signal_outcome_review"] = review
        summary["blocked_signal_outcome_review_status"] = review.get("status")
        summary["blocked_signal_outcome_review_reason"] = review.get("reason")
        summary["blocked_signal_outcome_review_next_trigger"] = review.get("next_trigger")
    return summary


def summarize_cost_gate_learning_lane_loop(
    data_dir: Path,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int = DEFAULT_COST_GATE_LEARNING_LOOP_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    lane_dir = data_dir / "cost_gate_learning_lane"
    heartbeat_path = data_dir / "cron_heartbeat" / "cost_gate_learning_lane.last_fire"
    status_log_path = data_dir / "logs" / "cost_gate_learning_lane.log"
    refresh_latest_path = lane_dir / "outcome_refresh_latest.json"
    review_latest_path = lane_dir / "blocked_outcome_review_latest.json"

    heartbeat_present, heartbeat_mtime, heartbeat_age = _file_mtime_age(
        heartbeat_path,
        now_utc=now_utc,
    )
    status_row, status_err = _latest_json_line(status_log_path)
    refresh_payload, refresh_err = _read_json(refresh_latest_path)
    review_payload, review_err = _read_json(review_latest_path)

    status_ts = status_row.get("ts_utc") if status_row else None
    status_age = _age_seconds(status_ts, now_utc=now_utc)
    refresh_rc = _int(status_row.get("refresh_rc")) if status_row else None
    review_rc = _int(status_row.get("review_rc")) if status_row else None
    ledger_row_count = (
        _int(status_row.get("ledger_row_count"))
        if status_row and status_row.get("ledger_row_count") is not None
        else None
    )
    review_status = (
        str(status_row.get("review_status") or "").strip()
        if status_row
        else str((review_payload or {}).get("status") or "").strip()
    )
    review_next_trigger = (
        status_row.get("review_next_trigger")
        if status_row
        else (review_payload or {}).get("next_trigger")
    )

    any_artifact_present = any(
        err is None
        for err in (status_err, refresh_err, review_err)
    ) or heartbeat_present
    status = "NOT_SEEN"
    reason = "no_cron_heartbeat_status_or_learning_artifacts"
    if status_row:
        if status_age is not None and status_age > max_age_seconds:
            status = "STALE_STATUS"
            reason = "cost_gate_learning_status_stale"
        elif refresh_rc not in (None, 0) or review_rc not in (None, 0):
            status = "ERROR"
            reason = "cost_gate_learning_refresh_or_review_failed"
        elif ledger_row_count == 0 and review_status == "NO_BLOCKED_SIGNAL_OUTCOMES":
            status = "RUNNING_NO_LEDGER_ROWS"
            reason = "cost_gate_learning_loop_ran_but_no_ledger_rows"
        else:
            status = "RUNNING"
            reason = "cost_gate_learning_status_recent"
    elif heartbeat_present:
        if heartbeat_age is not None and heartbeat_age > max_age_seconds:
            status = "STALE_HEARTBEAT"
            reason = "cost_gate_learning_heartbeat_stale"
        else:
            status = "HEARTBEAT_ONLY_NO_STATUS"
            reason = "cost_gate_learning_heartbeat_without_status_log"
    elif status_err and status_err not in {"missing", "no_json_status_line"}:
        status = "STATUS_UNREADABLE"
        reason = str(status_err)
    elif any_artifact_present:
        status = "ARTIFACTS_PRESENT_NO_STATUS"
        reason = "learning_artifacts_present_without_status_line"

    return {
        "learning_loop_status": status,
        "learning_loop_reason": reason,
        "learning_loop_max_age_seconds": max_age_seconds,
        "learning_loop_heartbeat_path": str(heartbeat_path),
        "learning_loop_heartbeat_present": heartbeat_present,
        "learning_loop_heartbeat_mtime_utc": heartbeat_mtime,
        "learning_loop_heartbeat_age_seconds": heartbeat_age,
        "learning_loop_status_log_path": str(status_log_path),
        "learning_loop_status_log_error": status_err,
        "learning_loop_status_ts_utc": status_ts,
        "learning_loop_status_age_seconds": status_age,
        "learning_loop_refresh_latest_path": str(refresh_latest_path),
        "learning_loop_refresh_latest_error": refresh_err,
        "learning_loop_review_latest_path": str(review_latest_path),
        "learning_loop_review_latest_error": review_err,
        "learning_loop_last_refresh_rc": refresh_rc,
        "learning_loop_last_review_rc": review_rc,
        "learning_loop_last_ledger_row_count": ledger_row_count,
        "learning_loop_last_review_status": review_status or None,
        "learning_loop_last_review_next_trigger": review_next_trigger,
    }


def summarize_cost_gate_learning_lane_source(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[3]
    missing: list[str] = []
    non_executable: list[str] = []
    for rel in REQUIRED_SOURCE_RELATIVE_PATHS:
        path = root / rel
        if not path.exists():
            missing.append(rel)
        elif path.suffix == ".sh" and not os.access(path, os.X_OK):
            non_executable.append(rel)

    if missing:
        status = "MISSING_FILES"
    elif non_executable:
        status = "NON_EXECUTABLE_CRON_WRAPPERS"
    else:
        status = "READY"
    return {
        "source_status": status,
        "source_ready": status == "READY",
        "repo_root": str(root),
        "required_source_relative_paths": list(REQUIRED_SOURCE_RELATIVE_PATHS),
        "missing_source_relative_paths": missing,
        "non_executable_source_relative_paths": non_executable,
    }


def _plan_summary(
    plan_path: Path,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    payload, err = _read_json(plan_path)
    generated_at = payload.get("generated_at_utc") if payload else None
    age = _age_seconds(generated_at, now_utc=now_utc)
    if err:
        status = "MISSING" if err == "missing" else "UNREADABLE"
        reason = f"plan_{err}"
    elif age is None:
        status = "MISSING_GENERATED_AT"
        reason = "plan_generated_at_missing_or_unparseable"
    elif age > max_age_seconds:
        status = "STALE"
        reason = "plan_stale"
    else:
        status = "READY"
        reason = "plan_recent"
    return {
        "plan_path": str(plan_path),
        "plan_status": status,
        "plan_reason": reason,
        "plan_source_error": err,
        "plan_generated_at_utc": generated_at,
        "plan_age_seconds": age,
        "plan_max_age_seconds": max_age_seconds,
        "plan_policy_status": payload.get("status") if payload else None,
        "plan_gate_status": payload.get("gate_status") if payload else None,
        "plan_selected_probe_candidate_count": (
            payload.get("selected_probe_candidate_count") if payload else None
        ),
        "main_cost_gate_adjustment": (
            payload.get("main_cost_gate_adjustment") if payload else "NONE"
        ),
        "order_authority": payload.get("order_authority") if payload else "NOT_GRANTED",
    }


def _activation_decision(
    *,
    source: dict[str, Any],
    plan: dict[str, Any],
    ledger: dict[str, Any],
    loop: dict[str, Any],
) -> dict[str, Any]:
    ledger_status = str(ledger.get("ledger_status") or "UNKNOWN").upper()
    loop_status = str(loop.get("learning_loop_status") or "UNKNOWN").upper()
    review_status = str(
        ledger.get("blocked_signal_outcome_review_status")
        or loop.get("learning_loop_last_review_status")
        or ""
    ).upper()
    admission_count = _int(ledger.get("admission_decision_count"))
    blocked_count = _int(ledger.get("blocked_signal_outcome_count"))
    probe_outcome_count = _int(ledger.get("probe_outcome_count"))

    status = "DATA_ACCUMULATING"
    reason = "cost_gate_learning_lane_has_runtime_evidence"
    missing_links: list[str] = []
    next_actions: list[str] = []

    if source.get("source_ready") is not True:
        return {
            "status": "SOURCE_NOT_READY",
            "reason": "required_learning_lane_source_files_missing_or_not_executable",
            "missing_links": ["source_sync"] + list(source.get("missing_source_relative_paths") or []),
            "next_actions": ["sync_runtime_source_to_current_main_before_activation"],
        }

    if plan.get("plan_status") != "READY":
        return {
            "status": "PLAN_NOT_READY",
            "reason": str(plan.get("plan_reason") or "plan_not_ready"),
            "missing_links": ["demo_learning_lane_plan_latest"],
            "next_actions": ["refresh_cost_gate_demo_learning_lane_plan"],
        }

    if loop_status in {"ERROR", "STATUS_UNREADABLE"}:
        return {
            "status": "LEARNING_LOOP_ERROR",
            "reason": str(loop.get("learning_loop_reason") or "learning_loop_error"),
            "missing_links": ["cost_gate_learning_lane_cron_health"],
            "next_actions": ["inspect_cost_gate_learning_lane_status_log_and_cron_log"],
        }

    if loop_status in {"STALE_STATUS", "STALE_HEARTBEAT"}:
        return {
            "status": "LEARNING_LOOP_STALE",
            "reason": str(loop.get("learning_loop_reason") or "learning_loop_stale"),
            "missing_links": ["fresh_cost_gate_learning_lane_cron_run"],
            "next_actions": ["verify_cost_gate_learning_lane_cron_is_installed_and_running"],
        }

    if ledger_status in {"MISSING", "EMPTY", "MALFORMED", "READ_ERROR"}:
        if loop_status == "RUNNING_NO_LEDGER_ROWS":
            status = "LOOP_RUNNING_NO_LEDGER_ROWS"
            reason = "learning_loop_recent_but_no_probe_ledger_rows"
            missing_links = ["runtime_ledger_writer_or_recent_cost_gate_reject_rows"]
            next_actions = [
                "verify_OPENCLAW_DEMO_LEARNING_LANE_WRITER_enabled_after_operator_review",
                "wait_for_new_eligible_cost_gate_rejects_or_investigate_writer",
            ]
        else:
            status = "NOT_ACCUMULATING"
            reason = "plan_present_but_writer_cron_or_ledger_not_observed"
            missing_links = [
                "probe_ledger_jsonl",
                "runtime_ledger_writer",
                "cost_gate_learning_lane_cron",
            ]
            next_actions = [
                "sync_runtime_source_then_enable_learning_lane_writer_after_operator_review",
                "install_or_run_cost_gate_learning_lane_cron",
                "rerun_activation_preflight_until_ledger_rows_appear",
            ]
        return {
            "status": status,
            "reason": reason,
            "missing_links": missing_links,
            "next_actions": next_actions,
        }

    if admission_count > 0 and blocked_count == 0 and probe_outcome_count == 0:
        if loop_status == "NOT_SEEN":
            status = "ADMISSION_ROWS_NEED_REFRESH_LOOP"
            reason = "rejects_recorded_but_outcome_refresh_loop_not_seen"
            missing_links = ["cost_gate_learning_lane_cron"]
            next_actions = ["install_or_run_cost_gate_learning_lane_cron"]
        else:
            status = "ADMISSION_ONLY_NEEDS_OUTCOME_REFRESH"
            reason = "rejects_recorded_but_blocked_signal_outcomes_missing"
            missing_links = ["blocked_signal_outcome_rows"]
            next_actions = ["run_cost_gate_outcome_refresh_for_blocked_signal_outcomes"]
        return {
            "status": status,
            "reason": reason,
            "missing_links": missing_links,
            "next_actions": next_actions,
        }

    if review_status == "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT":
        return {
            "status": "REVIEW_CANDIDATE_OPERATOR_REVIEW",
            "reason": "blocked_signal_markouts_clear_review_thresholds",
            "missing_links": [],
            "next_actions": ["operator_review_blocked_outcome_scorecard_before_demo_probe_authority"],
        }

    if review_status == "NO_DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE":
        return {
            "status": "KEEP_BLOCKED_REVIEWED",
            "reason": "blocked_signal_markouts_do_not_clear_review_thresholds",
            "missing_links": [],
            "next_actions": ["keep_cost_gate_blocked_for_reviewed_side_cells"],
        }

    if blocked_count > 0:
        return {
            "status": "BLOCKED_OUTCOMES_ACCUMULATING",
            "reason": "blocked_signal_outcomes_present_but_review_gate_not_cleared",
            "missing_links": ["more_blocked_signal_outcome_samples"],
            "next_actions": ["continue_recording_and_refreshing_blocked_signal_outcomes"],
        }

    if probe_outcome_count > 0:
        return {
            "status": "PROBE_OUTCOMES_ACCUMULATING",
            "reason": "demo_learning_probe_outcomes_present",
            "missing_links": [],
            "next_actions": ["continue_probe_outcome_review_without_promotion_authority"],
        }

    return {
        "status": status,
        "reason": reason,
        "missing_links": missing_links,
        "next_actions": next_actions,
    }


def build_cost_gate_learning_lane_activation_preflight(
    data_dir: Path,
    *,
    repo_root: Path | None = None,
    now_utc: dt.datetime | None = None,
    max_loop_age_seconds: int = DEFAULT_COST_GATE_LEARNING_LOOP_MAX_AGE_SECONDS,
    max_plan_age_seconds: int = DEFAULT_PLAN_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    lane_dir = data_dir / "cost_gate_learning_lane"
    plan_path = lane_dir / "demo_learning_lane_plan_latest.json"
    ledger_path = lane_dir / "probe_ledger.jsonl"

    source = summarize_cost_gate_learning_lane_source(repo_root)
    plan = _plan_summary(plan_path, now_utc=now, max_age_seconds=max_plan_age_seconds)
    ledger = summarize_cost_gate_learning_lane_ledger(ledger_path)
    loop = summarize_cost_gate_learning_lane_loop(
        data_dir,
        now_utc=now,
        max_age_seconds=max_loop_age_seconds,
    )
    decision = _activation_decision(
        source=source,
        plan=plan,
        ledger=ledger,
        loop=loop,
    )

    ledger_rows = _int(ledger.get("ledger_total_rows"))
    blocked_count = _int(ledger.get("blocked_signal_outcome_count"))
    admission_count = _int(ledger.get("admission_decision_count"))
    loop_recent = str(loop.get("learning_loop_status") or "").upper() in {
        "RUNNING",
        "RUNNING_NO_LEDGER_ROWS",
        "HEARTBEAT_ONLY_NO_STATUS",
    }
    return {
        "schema_version": ACTIVATION_PREFLIGHT_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "data_dir": str(data_dir),
        "status": decision["status"],
        "reason": decision["reason"],
        "missing_links": decision["missing_links"],
        "next_actions": decision["next_actions"],
        "answers": {
            "has_accumulated_ledger_rows": ledger_rows > 0,
            "currently_accumulating_evidence": ledger_rows > 0 and loop_recent,
            "cost_gate_rejects_recorded": admission_count > 0,
            "silent_drop_risk": str(ledger.get("ledger_status")) in {"MISSING", "EMPTY"},
            "blocked_signal_outcomes_recorded": blocked_count > 0,
            "blocked_signal_profitability_review_available": (
                bool(ledger.get("blocked_signal_outcome_review_status"))
                or loop.get("learning_loop_review_latest_error") is None
            ),
        },
        "source": source,
        "plan": plan,
        "ledger": ledger,
        "learning_loop": loop,
        "boundary": (
            "read-only activation preflight only; no PG write/schema migration, "
            "Bybit private/signed/trading call, order, auth/risk/runtime/config "
            "mutation, main Cost Gate lowering, or demo order authority"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only activation preflight for the cost-gate demo learning lane.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")),
        help="OpenClaw data dir containing cost_gate_learning_lane artifacts.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repo root used to verify required source files.",
    )
    parser.add_argument(
        "--max-loop-age-seconds",
        type=int,
        default=DEFAULT_COST_GATE_LEARNING_LOOP_MAX_AGE_SECONDS,
    )
    parser.add_argument(
        "--max-plan-age-seconds",
        type=int,
        default=DEFAULT_PLAN_MAX_AGE_SECONDS,
    )
    parser.add_argument("--print-json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)

    payload = build_cost_gate_learning_lane_activation_preflight(
        args.data_dir,
        repo_root=args.repo_root,
        max_loop_age_seconds=args.max_loop_age_seconds,
        max_plan_age_seconds=args.max_plan_age_seconds,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by CLI smoke.
    raise SystemExit(main())
