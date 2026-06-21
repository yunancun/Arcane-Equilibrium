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
import subprocess
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.historical_review import (
    build_historical_scorecard_review_from_file,
)
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
    "helper_scripts/research/cost_gate_learning_lane/reject_materializer.py",
    "helper_scripts/research/cost_gate_learning_lane/outcome_refresh.py",
    "helper_scripts/research/cost_gate_learning_lane/outcome_review.py",
    "helper_scripts/research/cost_gate_learning_lane/historical_review.py",
    "helper_scripts/research/cost_gate_learning_lane/status.py",
)

WRITER_ENABLE_ENV = "OPENCLAW_DEMO_LEARNING_LANE_WRITER"
WRITER_PLAN_ENV = "OPENCLAW_DEMO_LEARNING_LANE_PLAN"
WRITER_LEDGER_ENV = "OPENCLAW_DEMO_LEARNING_LANE_LEDGER"
REQUIRE_WRITER_ENABLED_ENV = "OPENCLAW_COST_GATE_REQUIRE_WRITER_ENABLED"
REQUIRE_PROCESS_WRITER_ENABLED_ENV = "OPENCLAW_COST_GATE_REQUIRE_PROCESS_WRITER_ENABLED"
AUTO_DETECT_ENGINE_PID_ENV = "OPENCLAW_COST_GATE_AUTO_DETECT_ENGINE_PID"
ENGINE_PROCESS_BASENAME = "openclaw-engine"
TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
FALSE_ENV_VALUES = {"0", "false", "no", "off", ""}


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


def _strip_env_value(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def _read_env_file(path: Path) -> tuple[dict[str, str] | None, str | None]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        return None, f"read_error:{type(exc).__name__}"

    values: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _strip_env_value(value)
    return values, None


def _read_proc_environ_file(path: Path) -> tuple[dict[str, str] | None, str | None]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        return None, f"read_error:{type(exc).__name__}"

    values: dict[str, str] = {}
    for chunk in raw.split(b"\0"):
        if not chunk or b"=" not in chunk:
            continue
        text = chunk.decode("utf-8", errors="replace")
        key, value = text.split("=", 1)
        if key:
            values[key] = value
    return values, None


def _read_proc_cmdline(path: Path) -> tuple[list[str] | None, str | None]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        return None, f"read_error:{type(exc).__name__}"

    argv = [
        chunk.decode("utf-8", errors="replace")
        for chunk in raw.split(b"\0")
        if chunk
    ]
    return argv, None


def _is_openclaw_engine_cmdline(argv: list[str] | None) -> bool:
    if not argv:
        return False
    return Path(argv[0]).name == ENGINE_PROCESS_BASENAME


def _detect_openclaw_engine_process(proc_root: Path = Path("/proc")) -> dict[str, Any]:
    try:
        entries = list(proc_root.iterdir())
    except FileNotFoundError:
        return {
            "engine_pid_detection_status": "PROC_ROOT_MISSING",
            "engine_pid_detection_error": "proc_root_missing",
            "engine_pid_candidate_count": 0,
            "engine_pid_candidates": [],
            "engine_pid_detected": None,
        }
    except OSError as exc:
        return {
            "engine_pid_detection_status": "PROC_ROOT_UNREADABLE",
            "engine_pid_detection_error": f"read_error:{type(exc).__name__}",
            "engine_pid_candidate_count": 0,
            "engine_pid_candidates": [],
            "engine_pid_detected": None,
        }

    candidates: list[dict[str, Any]] = []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = _int(entry.name, default=-1)
        if pid < 0:
            continue
        argv, err = _read_proc_cmdline(entry / "cmdline")
        if err or not _is_openclaw_engine_cmdline(argv):
            continue
        candidates.append(
            {
                "pid": pid,
                "cmdline": " ".join(argv or []),
            }
        )

    candidates.sort(key=lambda row: int(row["pid"]))
    if not candidates:
        return {
            "engine_pid_detection_status": "NOT_FOUND",
            "engine_pid_detection_error": None,
            "engine_pid_candidate_count": 0,
            "engine_pid_candidates": [],
            "engine_pid_detected": None,
        }

    detected = int(candidates[-1]["pid"])
    return {
        "engine_pid_detection_status": (
            "FOUND" if len(candidates) == 1 else "MULTIPLE_FOUND"
        ),
        "engine_pid_detection_error": None,
        "engine_pid_candidate_count": len(candidates),
        "engine_pid_candidates": candidates[-5:],
        "engine_pid_detected": detected,
    }


def _parse_env_bool(value: Any) -> tuple[bool | None, str | None]:
    if value is None:
        return None, None
    text = str(value).strip().lower()
    if text in TRUE_ENV_VALUES:
        return True, None
    if text in FALSE_ENV_VALUES:
        return False, None
    return None, "invalid_bool"


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


def _run_git(repo_root: Path, args: list[str]) -> tuple[str | None, str | None]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            text=True,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"git_error:{type(exc).__name__}"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return None, err or f"git_rc:{proc.returncode}"
    return proc.stdout.strip(), None


def _normalize_expected_head(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _expected_head_status(
    *,
    head_full: str | None,
    expected_head: str | None,
) -> tuple[str, bool | None, str | None]:
    expected = _normalize_expected_head(expected_head)
    if expected is None:
        return "NOT_PROVIDED", None, None
    if not all(ch in "0123456789abcdefABCDEF" for ch in expected):
        return "INVALID", False, "expected_head_must_be_hex_sha_prefix"
    if len(expected) < 7 or len(expected) > 40:
        return "INVALID", False, "expected_head_length_must_be_7_to_40_hex_chars"
    if not head_full:
        return "UNKNOWN_HEAD", False, "current_git_head_unavailable"
    expected_lower = expected.lower()
    head_lower = head_full.lower()
    if head_lower.startswith(expected_lower):
        return "MATCH", True, None
    return "MISMATCH", False, "current_git_head_does_not_match_expected_head"


def _summarize_git_checkout(
    repo_root: Path,
    *,
    expected_head: str | None = None,
) -> dict[str, Any]:
    inside, inside_err = _run_git(repo_root, ["rev-parse", "--is-inside-work-tree"])
    if inside_err or inside != "true":
        return {
            "git_status": "NOT_GIT_REPO",
            "git_ready_for_activation": False,
            "git_error": inside_err,
            "git_branch": None,
            "git_head_short": None,
            "git_head": None,
            "git_upstream": None,
            "git_ahead_count": None,
            "git_behind_count": None,
            "git_dirty_path_count": None,
            "git_untracked_path_count": None,
            "git_dirty_path_sample": [],
            "expected_head": _normalize_expected_head(expected_head),
            "expected_head_status": (
                "NOT_PROVIDED"
                if _normalize_expected_head(expected_head) is None
                else "UNKNOWN_HEAD"
            ),
            "expected_head_matches": None,
            "expected_head_error": inside_err,
        }

    branch, branch_err = _run_git(repo_root, ["branch", "--show-current"])
    head, head_err = _run_git(repo_root, ["rev-parse", "HEAD"])
    head_short, head_short_err = _run_git(repo_root, ["rev-parse", "--short", "HEAD"])
    upstream, upstream_err = _run_git(
        repo_root,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
    )
    dirty_text, dirty_err = _run_git(repo_root, ["status", "--porcelain"])
    expected_status, expected_matches, expected_error = _expected_head_status(
        head_full=head,
        expected_head=expected_head,
    )

    dirty_lines = [
        line
        for line in (dirty_text or "").splitlines()
        if line.strip()
    ]
    untracked_count = sum(1 for line in dirty_lines if line.startswith("??"))
    dirty_count = len(dirty_lines)

    ahead_count: int | None = None
    behind_count: int | None = None
    counts_err: str | None = None
    if upstream and not upstream_err:
        counts, counts_err = _run_git(
            repo_root,
            ["rev-list", "--left-right", "--count", f"HEAD...{upstream}"],
        )
        if counts:
            parts = counts.split()
            if len(parts) >= 2:
                ahead_count = _int(parts[0])
                behind_count = _int(parts[1])

    if branch_err or head_err or head_short_err or dirty_err:
        status = "GIT_UNREADABLE"
        ready = False
        error = branch_err or head_err or head_short_err or dirty_err
    elif upstream_err:
        status = "NO_UPSTREAM"
        ready = False
        error = upstream_err
    elif dirty_count > 0:
        status = "DIRTY"
        ready = False
        error = None
    elif (ahead_count or 0) > 0 and (behind_count or 0) > 0:
        status = "DIVERGED"
        ready = False
        error = None
    elif (behind_count or 0) > 0:
        status = "BEHIND_UPSTREAM"
        ready = False
        error = None
    elif (ahead_count or 0) > 0:
        status = "AHEAD_OF_UPSTREAM"
        ready = False
        error = None
    elif counts_err:
        status = "GIT_UNREADABLE"
        ready = False
        error = counts_err
    elif expected_status == "INVALID":
        status = "EXPECTED_HEAD_INVALID"
        ready = False
        error = expected_error
    elif expected_status == "UNKNOWN_HEAD":
        status = "EXPECTED_HEAD_UNVERIFIED"
        ready = False
        error = expected_error
    elif expected_status == "MISMATCH":
        status = "EXPECTED_HEAD_MISMATCH"
        ready = False
        error = expected_error
    else:
        status = "SYNCED_CLEAN"
        ready = True
        error = None

    return {
        "git_status": status,
        "git_ready_for_activation": ready,
        "git_error": error,
        "git_branch": branch or None,
        "git_head_short": head_short or None,
        "git_head": head or None,
        "git_upstream": upstream or None,
        "git_ahead_count": ahead_count,
        "git_behind_count": behind_count,
        "git_dirty_path_count": dirty_count,
        "git_untracked_path_count": untracked_count,
        "git_dirty_path_sample": dirty_lines[:12],
        "expected_head": _normalize_expected_head(expected_head),
        "expected_head_status": expected_status,
        "expected_head_matches": expected_matches,
        "expected_head_error": expected_error,
    }


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
        "capture_error_count": 0,
        "captured_reject_count": 0,
        "admit_decision_count": 0,
        "order_authority_not_granted_count": 0,
        "allowed_to_submit_order_count": 0,
        "probe_outcome_count": 0,
        "blocked_signal_outcome_count": 0,
        "blocked_signal_positive_outcome_count": 0,
        "latest_record_type": None,
        "latest_generated_at_utc": None,
        "latest_admission_decision": None,
        "latest_capture_error": None,
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
            summary["captured_reject_count"] += 1
            summary["latest_admission_decision"] = decision or None
            if decision == "ADMIT_DEMO_LEARNING_PROBE":
                summary["admit_decision_count"] += 1
            if decision == "ORDER_AUTHORITY_NOT_GRANTED":
                summary["order_authority_not_granted_count"] += 1
            if row.get("allowed_to_submit_order") is True:
                summary["allowed_to_submit_order_count"] += 1
        elif record_type == "probe_capture_error":
            decision = str(row.get("decision") or "").strip()
            summary["capture_error_count"] += 1
            summary["captured_reject_count"] += 1
            summary["latest_admission_decision"] = decision or None
            summary["latest_capture_error"] = (
                row.get("capture_error")
                or row.get("reason")
                or "runtime_admission_evaluation_failed"
            )
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
    elif summary["capture_error_count"] > 0:
        summary["ledger_status"] = "CAPTURE_ERRORS_PRESENT"
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
    plan_latest_path = lane_dir / "demo_learning_lane_plan_latest.json"
    materializer_latest_path = lane_dir / "reject_materializer_latest.json"
    refresh_latest_path = lane_dir / "outcome_refresh_latest.json"
    review_latest_path = lane_dir / "blocked_outcome_review_latest.json"

    heartbeat_present, heartbeat_mtime, heartbeat_age = _file_mtime_age(
        heartbeat_path,
        now_utc=now_utc,
    )
    status_row, status_err = _latest_json_line(status_log_path)
    materializer_payload, materializer_err = _read_json(materializer_latest_path)
    refresh_payload, refresh_err = _read_json(refresh_latest_path)
    review_payload, review_err = _read_json(review_latest_path)

    status_ts = status_row.get("ts_utc") if status_row else None
    status_age = _age_seconds(status_ts, now_utc=now_utc)
    plan_rc = _int(status_row.get("plan_rc")) if status_row else None
    refresh_plan_enabled = (
        status_row.get("refresh_plan")
        if status_row and isinstance(status_row.get("refresh_plan"), bool)
        else None
    )
    materializer_rc = _int(status_row.get("materializer_rc")) if status_row else None
    materialize_rejects_enabled = (
        status_row.get("materialize_rejects")
        if status_row and isinstance(status_row.get("materialize_rejects"), bool)
        else None
    )
    append_materialized_rejects_enabled = (
        status_row.get("append_materialized_rejects")
        if status_row and isinstance(status_row.get("append_materialized_rejects"), bool)
        else None
    )
    refresh_rc = _int(status_row.get("refresh_rc")) if status_row else None
    review_rc = _int(status_row.get("review_rc")) if status_row else None
    ledger_row_count = (
        _int(status_row.get("ledger_row_count"))
        if status_row and status_row.get("ledger_row_count") is not None
        else None
    )
    materializer_status = (
        str(status_row.get("materializer_status") or "").strip()
        if status_row and status_row.get("materializer_status") is not None
        else str((materializer_payload or {}).get("status") or "").strip()
    )
    materializer_input_feature_row_count = (
        _int(status_row.get("materializer_input_feature_row_count"))
        if status_row and status_row.get("materializer_input_feature_row_count") is not None
        else (
            _int((materializer_payload or {}).get("input_feature_row_count"))
            if materializer_payload
            else None
        )
    )
    materializer_materialized_record_count = (
        _int(status_row.get("materializer_materialized_record_count"))
        if status_row and status_row.get("materializer_materialized_record_count") is not None
        else (
            _int((materializer_payload or {}).get("materialized_record_count"))
            if materializer_payload
            else None
        )
    )
    materializer_appended_record_count = (
        _int(status_row.get("materializer_appended_record_count"))
        if status_row and status_row.get("materializer_appended_record_count") is not None
        else (
            _int((materializer_payload or {}).get("appended_record_count"))
            if materializer_payload
            else None
        )
    )
    materializer_decision_counts = (
        status_row.get("materializer_decision_counts")
        if status_row and status_row.get("materializer_decision_counts") is not None
        else (materializer_payload or {}).get("decision_counts")
    )
    if not isinstance(materializer_decision_counts, dict):
        materializer_decision_counts = None
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
        for err in (status_err, materializer_err, refresh_err, review_err)
    ) or heartbeat_present
    status = "NOT_SEEN"
    reason = "no_cron_heartbeat_status_or_learning_artifacts"
    if status_row:
        if status_age is not None and status_age > max_age_seconds:
            status = "STALE_STATUS"
            reason = "cost_gate_learning_status_stale"
        elif (
            plan_rc not in (None, 0)
            or materializer_rc not in (None, 0)
            or refresh_rc not in (None, 0)
            or review_rc not in (None, 0)
        ):
            status = "ERROR"
            reason = "cost_gate_learning_plan_materializer_refresh_or_review_failed"
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
        "learning_loop_plan_latest_path": str(plan_latest_path),
        "learning_loop_refresh_plan_enabled": refresh_plan_enabled,
        "learning_loop_last_plan_rc": plan_rc,
        "learning_loop_last_plan_policy_status": (
            status_row.get("plan_policy_status") if status_row else None
        ),
        "learning_loop_last_plan_gate_status": (
            status_row.get("plan_gate_status") if status_row else None
        ),
        "learning_loop_last_plan_selected_probe_candidate_count": (
            status_row.get("plan_selected_probe_candidate_count")
            if status_row else None
        ),
        "learning_loop_materializer_latest_path": str(materializer_latest_path),
        "learning_loop_materializer_latest_error": materializer_err,
        "learning_loop_refresh_latest_path": str(refresh_latest_path),
        "learning_loop_refresh_latest_error": refresh_err,
        "learning_loop_review_latest_path": str(review_latest_path),
        "learning_loop_review_latest_error": review_err,
        "learning_loop_materialize_rejects_enabled": materialize_rejects_enabled,
        "learning_loop_append_materialized_rejects_enabled": (
            append_materialized_rejects_enabled
        ),
        "learning_loop_last_materializer_rc": materializer_rc,
        "learning_loop_last_materializer_status": materializer_status or None,
        "learning_loop_last_materializer_input_feature_row_count": (
            materializer_input_feature_row_count
        ),
        "learning_loop_last_materialized_record_count": (
            materializer_materialized_record_count
        ),
        "learning_loop_last_appended_materialized_record_count": (
            materializer_appended_record_count
        ),
        "learning_loop_last_materializer_decision_counts": materializer_decision_counts,
        "learning_loop_last_refresh_rc": refresh_rc,
        "learning_loop_last_review_rc": review_rc,
        "learning_loop_last_ledger_row_count": ledger_row_count,
        "learning_loop_last_review_status": review_status or None,
        "learning_loop_last_review_next_trigger": review_next_trigger,
    }


def summarize_cost_gate_learning_lane_historical_review(
    data_dir: Path,
    *,
    now_utc: dt.datetime,
) -> dict[str, Any]:
    lane_dir = data_dir / "cost_gate_learning_lane"
    review_path = lane_dir / "historical_scorecard_review_latest.json"
    scorecard_path = (
        data_dir
        / "cost_gate_counterfactual"
        / "cost_gate_reject_counterfactual_latest.json"
    )
    review_payload, review_err = _read_json(review_path)
    source_kind = "review_artifact"
    if review_err:
        source_kind = "scorecard_direct"
        review_payload = build_historical_scorecard_review_from_file(
            scorecard_path,
            now_utc=now_utc,
        )
    assert review_payload is not None
    generated_at = review_payload.get("generated_at_utc")
    age = _age_seconds(generated_at, now_utc=now_utc)
    status = str(review_payload.get("status") or "UNKNOWN")
    candidates = _int(review_payload.get("historical_candidate_side_cell_count"))
    keep_blocked = _int(review_payload.get("historical_keep_blocked_side_cell_count"))
    data_tasks = _int(review_payload.get("historical_data_coverage_task_count"))
    return {
        "historical_scorecard_review_path": str(review_path),
        "historical_scorecard_review_error": review_err,
        "historical_scorecard_review_source_kind": source_kind,
        "historical_scorecard_source_path": str(scorecard_path),
        "historical_scorecard_review_status": status,
        "historical_scorecard_review_reason": review_payload.get("reason"),
        "historical_scorecard_review_next_trigger": review_payload.get("next_trigger"),
        "historical_scorecard_review_generated_at_utc": generated_at,
        "historical_scorecard_review_age_seconds": age,
        "historical_candidate_side_cell_count": candidates,
        "historical_keep_blocked_side_cell_count": keep_blocked,
        "historical_data_coverage_task_count": data_tasks,
        "historical_counterfactual_candidates_present": candidates > 0,
        "historical_counterfactual_is_runtime_evidence": False,
        "historical_scorecard_review": review_payload,
    }


def summarize_cost_gate_learning_lane_source(
    repo_root: Path | None = None,
    *,
    expected_head: str | None = None,
) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[3]
    git = _summarize_git_checkout(root, expected_head=expected_head)
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
    source_ready = status == "READY"
    source_activation_ready = (
        source_ready
        and git.get("git_ready_for_activation") is True
    )
    if not source_ready:
        source_activation_status = status
    else:
        source_activation_status = str(git.get("git_status") or "UNKNOWN")
    return {
        "source_status": status,
        "source_ready": source_ready,
        "source_activation_status": source_activation_status,
        "source_activation_ready": source_activation_ready,
        "repo_root": str(root),
        "required_source_relative_paths": list(REQUIRED_SOURCE_RELATIVE_PATHS),
        "missing_source_relative_paths": missing,
        "non_executable_source_relative_paths": non_executable,
        **git,
    }


def summarize_cost_gate_learning_lane_writer_config(
    data_dir: Path,
    *,
    env: dict[str, str] | None = None,
    env_file: Path | None = None,
    require_writer_enabled: bool = False,
) -> dict[str, Any]:
    """Summarize the disabled-by-default runtime writer config.

    This is intentionally read-only. When an env file is provided, it is treated
    as the inspected runtime config and process env does not leak into the check.
    """
    if env_file is not None:
        env_values, env_file_error = _read_env_file(env_file)
        env_values = env_values or {}
        env_source = "env_file"
    else:
        env_values = dict(os.environ if env is None else env)
        env_file_error = None
        env_source = "process_env" if env is None else "provided_env"

    raw_writer = env_values.get(WRITER_ENABLE_ENV)
    writer_enabled, writer_bool_error = _parse_env_bool(raw_writer)

    lane_dir = data_dir / "cost_gate_learning_lane"
    raw_plan_path = str(env_values.get(WRITER_PLAN_ENV) or "").strip()
    raw_ledger_path = str(env_values.get(WRITER_LEDGER_ENV) or "").strip()
    plan_path = (
        Path(raw_plan_path)
        if raw_plan_path
        else lane_dir / "demo_learning_lane_plan_latest.json"
    )
    ledger_path = (
        Path(raw_ledger_path)
        if raw_ledger_path
        else lane_dir / "probe_ledger.jsonl"
    )

    if env_file_error:
        status = "ENV_FILE_UNREADABLE"
        reason = f"runtime_env_file_{env_file_error}"
    elif raw_writer is None:
        status = "UNSET"
        reason = f"{WRITER_ENABLE_ENV}_unset"
    elif writer_bool_error:
        status = "INVALID"
        reason = f"{WRITER_ENABLE_ENV}_{writer_bool_error}"
    elif writer_enabled is True:
        status = "ENABLED"
        reason = "runtime_writer_explicitly_enabled"
    else:
        status = "DISABLED"
        reason = "runtime_writer_explicitly_disabled"

    return {
        "writer_config_status": status,
        "writer_config_reason": reason,
        "writer_enabled": writer_enabled,
        "writer_required_for_activation": require_writer_enabled,
        "writer_env_name": WRITER_ENABLE_ENV,
        "writer_env_value": raw_writer,
        "writer_env_source": env_source,
        "writer_env_file": str(env_file) if env_file else None,
        "writer_env_file_error": env_file_error,
        "writer_bool_error": writer_bool_error,
        "plan_env_name": WRITER_PLAN_ENV,
        "plan_path": str(plan_path),
        "plan_path_source": "env_override" if raw_plan_path else "default_data_dir",
        "ledger_env_name": WRITER_LEDGER_ENV,
        "ledger_path": str(ledger_path),
        "ledger_path_source": "env_override" if raw_ledger_path else "default_data_dir",
        "data_dir": str(data_dir),
    }


def summarize_cost_gate_learning_lane_writer_process(
    data_dir: Path,
    *,
    engine_pid: int | None = None,
    proc_environ_file: Path | None = None,
    auto_detect_engine_pid: bool = False,
    proc_root: Path = Path("/proc"),
    require_writer_enabled: bool = False,
) -> dict[str, Any]:
    detection = {
        "engine_pid_auto_detect": auto_detect_engine_pid,
        "engine_pid_detection_status": "NOT_REQUESTED",
        "engine_pid_detection_error": None,
        "engine_pid_candidate_count": None,
        "engine_pid_candidates": [],
        "engine_pid_detected": None,
    }
    if proc_environ_file is None and engine_pid is None and auto_detect_engine_pid:
        detection = {
            "engine_pid_auto_detect": True,
            **_detect_openclaw_engine_process(proc_root),
        }
        detected = detection.get("engine_pid_detected")
        if detected is not None:
            engine_pid = _int(detected, default=-1)
            if engine_pid < 0:
                engine_pid = None

    if proc_environ_file is None and engine_pid is not None:
        proc_environ_file = proc_root / str(engine_pid) / "environ"
    if proc_environ_file is None:
        status = "NOT_CHECKED"
        reason = "engine_pid_or_proc_environ_file_not_provided"
        if auto_detect_engine_pid:
            detection_status = str(detection.get("engine_pid_detection_status") or "")
            if detection_status == "NOT_FOUND":
                status = "ENGINE_PROCESS_NOT_FOUND"
                reason = "openclaw_engine_process_not_found"
            elif detection_status in {"PROC_ROOT_MISSING", "PROC_ROOT_UNREADABLE"}:
                status = "ENGINE_PROCESS_DETECTION_UNAVAILABLE"
                reason = str(
                    detection.get("engine_pid_detection_error")
                    or "engine_process_detection_unavailable"
                )
        return {
            "writer_process_checked": False,
            "writer_process_status": status,
            "writer_process_reason": reason,
            "writer_process_enabled": None,
            "writer_process_required_for_activation": require_writer_enabled,
            "engine_pid": engine_pid,
            "proc_environ_path": None,
            "proc_environ_error": None,
            "writer_env_value": None,
            "plan_path": None,
            "ledger_path": None,
            **detection,
        }

    env_values, err = _read_proc_environ_file(proc_environ_file)
    if err:
        return {
            "writer_process_checked": False,
            "writer_process_status": "PROC_ENVIRON_UNREADABLE",
            "writer_process_reason": f"proc_environ_{err}",
            "writer_process_enabled": None,
            "writer_process_required_for_activation": require_writer_enabled,
            "engine_pid": engine_pid,
            "proc_environ_path": str(proc_environ_file),
            "proc_environ_error": err,
            "writer_env_value": None,
            "plan_path": None,
            "ledger_path": None,
            **detection,
        }

    config = summarize_cost_gate_learning_lane_writer_config(
        data_dir,
        env=env_values or {},
        require_writer_enabled=require_writer_enabled,
    )
    return {
        "writer_process_checked": True,
        "writer_process_status": config["writer_config_status"],
        "writer_process_reason": config["writer_config_reason"],
        "writer_process_enabled": config["writer_enabled"],
        "writer_process_required_for_activation": require_writer_enabled,
        "engine_pid": engine_pid,
        "proc_environ_path": str(proc_environ_file),
        "proc_environ_error": None,
        "writer_env_value": config["writer_env_value"],
        "writer_bool_error": config["writer_bool_error"],
        "plan_path": config["plan_path"],
        "plan_path_source": config["plan_path_source"],
        "ledger_path": config["ledger_path"],
        "ledger_path_source": config["ledger_path_source"],
        **detection,
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
    policy_status = str(payload.get("status") or "") if payload else ""
    gate_status = str(payload.get("gate_status") or "") if payload else ""
    selected_count = (
        _int(payload.get("selected_probe_candidate_count"), default=0)
        if payload else 0
    )
    if err:
        status = "MISSING" if err == "missing" else "UNREADABLE"
        reason = f"plan_{err}"
    elif payload.get("schema_version") != "cost_gate_demo_learning_lane_plan_v1":
        status = "UNEXPECTED_SCHEMA"
        reason = "plan_schema_version_unexpected"
    elif age is None:
        status = "MISSING_GENERATED_AT"
        reason = "plan_generated_at_missing_or_unparseable"
    elif age > max_age_seconds:
        status = "STALE"
        reason = "plan_stale"
    elif policy_status != "READY_FOR_DEMO_LEARNING_PROBE":
        status = "POLICY_NOT_READY"
        reason = f"plan_policy_status_{policy_status or 'missing'}"
    elif gate_status != "OPERATOR_REVIEW":
        status = "POLICY_GATE_NOT_READY"
        reason = f"plan_gate_status_{gate_status or 'missing'}"
    elif selected_count < 1:
        status = "NO_SELECTED_CANDIDATES"
        reason = "plan_has_no_selected_probe_candidates"
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
    capture_error_count = _int(ledger.get("capture_error_count"))
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

    if capture_error_count > 0 and admission_count == 0 and blocked_count == 0:
        return {
            "status": "CAPTURE_ERRORS_NEED_OPERATOR_FIX",
            "reason": "rejects_captured_but_admission_evaluation_failed",
            "missing_links": ["demo_learning_lane_plan_or_writer_config"],
            "next_actions": [
                "inspect_probe_capture_error_rows",
                "refresh_demo_learning_lane_plan_and_verify_writer_paths",
            ],
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
    expected_head: str | None = None,
    runtime_env_file: Path | None = None,
    engine_pid: int | None = None,
    runtime_proc_environ: Path | None = None,
    auto_detect_engine_pid: bool = False,
    proc_root: Path = Path("/proc"),
    require_writer_enabled: bool = False,
    require_process_writer_enabled: bool = False,
    now_utc: dt.datetime | None = None,
    max_loop_age_seconds: int = DEFAULT_COST_GATE_LEARNING_LOOP_MAX_AGE_SECONDS,
    max_plan_age_seconds: int = DEFAULT_PLAN_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    lane_dir = data_dir / "cost_gate_learning_lane"
    plan_path = lane_dir / "demo_learning_lane_plan_latest.json"
    ledger_path = lane_dir / "probe_ledger.jsonl"

    source = summarize_cost_gate_learning_lane_source(
        repo_root,
        expected_head=expected_head,
    )
    plan = _plan_summary(plan_path, now_utc=now, max_age_seconds=max_plan_age_seconds)
    ledger = summarize_cost_gate_learning_lane_ledger(ledger_path)
    loop = summarize_cost_gate_learning_lane_loop(
        data_dir,
        now_utc=now,
        max_age_seconds=max_loop_age_seconds,
    )
    historical_review = summarize_cost_gate_learning_lane_historical_review(
        data_dir,
        now_utc=now,
    )
    writer_config = summarize_cost_gate_learning_lane_writer_config(
        data_dir,
        env_file=runtime_env_file,
        require_writer_enabled=require_writer_enabled,
    )
    writer_process = summarize_cost_gate_learning_lane_writer_process(
        data_dir,
        engine_pid=engine_pid,
        proc_environ_file=runtime_proc_environ,
        auto_detect_engine_pid=auto_detect_engine_pid,
        proc_root=proc_root,
        require_writer_enabled=require_process_writer_enabled,
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
    capture_error_count = _int(ledger.get("capture_error_count"))
    captured_reject_count = _int(ledger.get("captured_reject_count"))
    loop_recent = str(loop.get("learning_loop_status") or "").upper() in {
        "RUNNING",
        "RUNNING_NO_LEDGER_ROWS",
        "HEARTBEAT_ONLY_NO_STATUS",
    }
    activation_blockers = list(decision["missing_links"])
    if source.get("source_activation_ready") is not True:
        activation_blockers.insert(0, "source_checkout_not_synced_clean")
    expected_status = str(source.get("expected_head_status") or "NOT_PROVIDED")
    if expected_status == "MISMATCH":
        activation_blockers.insert(0, "expected_source_head_mismatch")
    elif expected_status == "INVALID":
        activation_blockers.insert(0, "expected_source_head_invalid")
    elif expected_status == "UNKNOWN_HEAD":
        activation_blockers.insert(0, "expected_source_head_unverified")
    writer_status = str(writer_config.get("writer_config_status") or "UNKNOWN")
    writer_enabled = writer_config.get("writer_enabled") is True
    if require_writer_enabled and not writer_enabled:
        activation_blockers.insert(0, "runtime_writer_not_enabled")
    writer_process_status = str(
        writer_process.get("writer_process_status") or "UNKNOWN"
    )
    writer_process_enabled = writer_process.get("writer_process_enabled") is True
    if require_process_writer_enabled and not writer_process_enabled:
        activation_blockers.insert(0, "running_engine_writer_not_enabled")
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
            "cost_gate_rejects_recorded": (
                admission_count > 0 or captured_reject_count > 0
            ),
            "admission_evaluation_errors_recorded": capture_error_count > 0,
            "silent_drop_risk": str(ledger.get("ledger_status")) in {"MISSING", "EMPTY"},
            "blocked_signal_outcomes_recorded": blocked_count > 0,
            "blocked_signal_profitability_review_available": (
                bool(ledger.get("blocked_signal_outcome_review_status"))
                or loop.get("learning_loop_review_latest_error") is None
            ),
            "reject_materializer_ran": (
                (
                    loop.get("learning_loop_materialize_rejects_enabled") is not False
                    and loop.get("learning_loop_last_materializer_rc") is not None
                )
                or loop.get("learning_loop_materializer_latest_error") is None
            ),
            "reject_materializer_enabled": (
                loop.get("learning_loop_materialize_rejects_enabled")
            ),
            "reject_materializer_append_enabled": (
                loop.get("learning_loop_append_materialized_rejects_enabled")
            ),
            "reject_materializer_latest_available": (
                loop.get("learning_loop_materializer_latest_error") is None
            ),
            "reject_materializer_status": (
                loop.get("learning_loop_last_materializer_status")
            ),
            "reject_materializer_materialized_records": _int(
                loop.get("learning_loop_last_materialized_record_count")
            ),
            "reject_materializer_appended_records": _int(
                loop.get("learning_loop_last_appended_materialized_record_count")
            ),
            "historical_counterfactual_review_available": (
                str(historical_review.get("historical_scorecard_review_status"))
                not in {"SOURCE_SCORECARD_UNAVAILABLE", "WAIT_FOR_HISTORICAL_SCORECARD_REFRESH"}
            ),
            "historical_counterfactual_candidates_present": (
                historical_review.get("historical_counterfactual_candidates_present") is True
            ),
            "historical_counterfactual_is_runtime_evidence": False,
            "runtime_source_ready_for_activation": (
                source.get("source_activation_ready") is True
            ),
            "runtime_writer_enabled": writer_enabled,
            "runtime_writer_config_status": writer_status,
            "runtime_writer_config_required": require_writer_enabled,
            "runtime_writer_config_checked_from_env_file": runtime_env_file is not None,
            "writer_disabled_or_unset_drop_risk": (
                require_writer_enabled and not writer_enabled
            ),
            "runtime_writer_process_checked": (
                writer_process.get("writer_process_checked") is True
            ),
            "runtime_writer_process_enabled": writer_process_enabled,
            "runtime_writer_process_status": writer_process_status,
            "runtime_writer_process_required": require_process_writer_enabled,
            "running_engine_writer_disabled_or_unset_drop_risk": (
                require_process_writer_enabled and not writer_process_enabled
            ),
            "activation_ready": not activation_blockers,
        },
        "activation_blockers": activation_blockers,
        "source": source,
        "writer_config": writer_config,
        "writer_process": writer_process,
        "plan": plan,
        "ledger": ledger,
        "learning_loop": loop,
        "historical_review": historical_review,
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
        "--expected-head",
        default=os.environ.get("OPENCLAW_EXPECTED_SOURCE_HEAD"),
        help="Expected git HEAD SHA/prefix for activation, e.g. PM-pushed origin/main.",
    )
    parser.add_argument(
        "--runtime-env-file",
        type=Path,
        default=None,
        help=(
            "Optional runtime env file to inspect for "
            "OPENCLAW_DEMO_LEARNING_LANE_WRITER and path overrides."
        ),
    )
    parser.add_argument(
        "--engine-pid",
        type=int,
        default=None,
        help="Optional running openclaw-engine PID; reads /proc/<pid>/environ.",
    )
    parser.add_argument(
        "--runtime-proc-environ",
        type=Path,
        default=None,
        help="Optional explicit proc environ file, e.g. /proc/<pid>/environ.",
    )
    parser.add_argument(
        "--auto-detect-engine-pid",
        action="store_true",
        default=_parse_env_bool(os.environ.get(AUTO_DETECT_ENGINE_PID_ENV))[0] is True,
        help=(
            "Auto-detect a running openclaw-engine process by scanning /proc/*/cmdline. "
            "Also enabled automatically when --require-process-writer-enabled is used "
            "without --engine-pid or --runtime-proc-environ."
        ),
    )
    parser.add_argument(
        "--proc-root",
        type=Path,
        default=Path("/proc"),
        help="Procfs root used for engine PID auto-detection.",
    )
    require_writer_default = (
        _parse_env_bool(os.environ.get(REQUIRE_WRITER_ENABLED_ENV))[0] is True
    )
    require_process_writer_default = (
        _parse_env_bool(os.environ.get(REQUIRE_PROCESS_WRITER_ENABLED_ENV))[0] is True
    )
    parser.add_argument(
        "--require-writer-enabled",
        action="store_true",
        default=require_writer_default,
        help=(
            "Fail activation preflight unless OPENCLAW_DEMO_LEARNING_LANE_WRITER "
            "is explicitly enabled in the inspected env."
        ),
    )
    parser.add_argument(
        "--require-process-writer-enabled",
        action="store_true",
        default=require_process_writer_default,
        help=(
            "Fail activation preflight unless the running engine process has "
            "OPENCLAW_DEMO_LEARNING_LANE_WRITER explicitly enabled."
        ),
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
        expected_head=args.expected_head,
        runtime_env_file=args.runtime_env_file,
        engine_pid=args.engine_pid,
        runtime_proc_environ=args.runtime_proc_environ,
        auto_detect_engine_pid=(
            args.auto_detect_engine_pid
            or (
                args.require_process_writer_enabled
                and args.engine_pid is None
                and args.runtime_proc_environ is None
            )
        ),
        proc_root=args.proc_root,
        require_writer_enabled=args.require_writer_enabled,
        require_process_writer_enabled=args.require_process_writer_enabled,
        max_loop_age_seconds=args.max_loop_age_seconds,
        max_plan_age_seconds=args.max_plan_age_seconds,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by CLI smoke.
    raise SystemExit(main())
