#!/usr/bin/env python3
"""Read-only healthcheck for the demo-learning cron stack.

This checks whether the four operator-installed learning stack crons are
present and fresh enough to prove the runtime is accumulating demo-learning
evidence and bounded-review inputs.
It reads crontab, local artifacts, and local git metadata only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "demo_learning_stack_healthcheck_v1"


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _age_seconds(value: str | None, *, now_utc: dt.datetime) -> float | None:
    parsed = _parse_ts(value)
    if parsed is None:
        return None
    return max(0.0, (now_utc - parsed).total_seconds())


def _file_age(path: Path, *, now_utc: dt.datetime) -> dict[str, Any]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {
            "path": str(path),
            "present": False,
            "mtime_utc": None,
            "age_seconds": None,
        }
    mtime = dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.timezone.utc)
    return {
        "path": str(path),
        "present": True,
        "mtime_utc": mtime.isoformat().replace("+00:00", "Z"),
        "age_seconds": max(0.0, (now_utc - mtime).total_seconds()),
        "size_bytes": stat.st_size,
    }


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, "missing"
    except OSError as exc:
        return {}, f"{type(exc).__name__}:{exc}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"json_decode_error:{exc}"
    if not isinstance(payload, dict):
        return {}, "json_not_object"
    return payload, None


def _latest_json_line(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}, "missing"
    except OSError as exc:
        return {}, f"{type(exc).__name__}:{exc}"
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            return {}, f"json_line_decode_error:{exc}"
        if not isinstance(payload, dict):
            return {}, "json_line_not_object"
        return payload, None
    return {}, "no_json_status_line"


def _read_crontab(crontab_text_file: Path | None) -> tuple[str, str | None]:
    if crontab_text_file is not None:
        try:
            return crontab_text_file.read_text(encoding="utf-8"), None
        except OSError as exc:
            return "", f"{type(exc).__name__}:{exc}"
    try:
        proc = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            check=False,
            text=True,
        )
    except FileNotFoundError:
        return "", "crontab_command_missing"
    if proc.returncode not in (0, 1):
        return proc.stdout, f"crontab_rc_{proc.returncode}:{proc.stderr.strip()}"
    return proc.stdout, None


def _git_cmd(repo_root: Path, args: list[str]) -> tuple[str | None, str | None]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            check=False,
            text=True,
        )
    except FileNotFoundError:
        return None, "git_command_missing"
    if proc.returncode != 0:
        return None, f"git_rc_{proc.returncode}:{proc.stderr.strip()}"
    return proc.stdout.strip(), None


def _source_summary(repo_root: Path, expected_head: str | None) -> dict[str, Any]:
    head, head_error = _git_cmd(repo_root, ["rev-parse", "HEAD"])
    dirty_text, dirty_error = _git_cmd(repo_root, ["status", "--porcelain"])
    dirty_lines = [line for line in (dirty_text or "").splitlines() if line.strip()]
    expected_head_matches = None
    if expected_head:
        expected_head_matches = bool(head and head.startswith(expected_head))
    return {
        "repo_root": str(repo_root),
        "head": head,
        "head_error": head_error,
        "expected_head": expected_head or None,
        "expected_head_matches": expected_head_matches,
        "dirty_error": dirty_error,
        "dirty_path_count": len(dirty_lines),
        "dirty_path_sample": dirty_lines[:20],
        "source_clean": dirty_error is None and len(dirty_lines) == 0,
    }


def _cron_summary(text: str, error: str | None) -> dict[str, Any]:
    entries = [line.strip() for line in text.splitlines() if line.strip()]
    active_entries = [line for line in entries if not line.startswith("#")]

    def present(marker: str) -> bool:
        return any(marker in line for line in active_entries)

    return {
        "read_error": error,
        "active_entry_count": len(active_entries),
        "demo_learning_evidence_entry_present": present(
            "demo_learning_evidence_audit_cron.sh"
        ),
        "sealed_horizon_probe_preflight_entry_present": present(
            "sealed_horizon_probe_preflight_cron.sh"
        ),
        "cost_gate_learning_lane_entry_present": present(
            "cost_gate_learning_lane_cron.sh"
        ),
        "demo_learning_stack_healthcheck_entry_present": present(
            "demo_learning_stack_healthcheck_cron.sh"
        ),
        "matching_entries": [
            line
            for line in active_entries
            if "demo_learning_evidence_audit_cron.sh" in line
            or "sealed_horizon_probe_preflight_cron.sh" in line
            or "cost_gate_learning_lane_cron.sh" in line
            or "demo_learning_stack_healthcheck_cron.sh" in line
        ][:10],
    }


def _is_recent(age_seconds: float | None, max_seconds: int) -> bool:
    return age_seconds is not None and age_seconds <= max_seconds


def _component_summary(
    *,
    name: str,
    heartbeat: dict[str, Any],
    status_log: Path,
    latest_json: Path | None,
    now_utc: dt.datetime,
    max_heartbeat_age_seconds: int,
    max_status_age_seconds: int,
) -> dict[str, Any]:
    latest_status, status_error = _latest_json_line(status_log)
    latest_payload: dict[str, Any] = {}
    latest_payload_error: str | None = None
    if latest_json is not None:
        latest_payload, latest_payload_error = _read_json(latest_json)
    status_age = _age_seconds(str(latest_status.get("ts_utc") or ""), now_utc=now_utc)
    return {
        "name": name,
        "heartbeat": heartbeat,
        "heartbeat_recent": _is_recent(
            heartbeat.get("age_seconds"), max_heartbeat_age_seconds
        ),
        "status_log_path": str(status_log),
        "status_log_error": status_error,
        "latest_status": latest_status,
        "latest_status_age_seconds": status_age,
        "latest_status_recent": _is_recent(status_age, max_status_age_seconds),
        "latest_json_path": str(latest_json) if latest_json is not None else None,
        "latest_json_error": latest_payload_error,
        "latest_json": latest_payload,
    }


def _artifact_status(path: Path, *, now_utc: dt.datetime) -> dict[str, Any]:
    payload, error = _read_json(path)
    generated_at = payload.get("generated_at_utc") or payload.get("ts_utc")
    return {
        "path": str(path),
        "present": error is None,
        "error": error,
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "generated_at_utc": generated_at,
        "age_seconds": _age_seconds(str(generated_at or ""), now_utc=now_utc),
    }


# admission decision 記錄的 record_type(對齊 runtime_adapter.build_ledger_record 默認值)。
PROBE_ADMISSION_DECISION_RECORD_TYPE = "probe_admission_decision"
ADMIT_DECISION = "ADMIT_DEMO_LEARNING_PROBE"


def _soak_envelope_status(
    plan_path: Path, *, now_utc: dt.datetime
) -> dict[str, Any]:
    """讀 canonical soak plan 判斷內嵌 operator_authorization 是否 Active(未過期)。

    為什麼讀 plan 而非 engine env：healthcheck 是唯讀本地檔巡檢，無 engine env 訪問；
    envelope Active 由簽名塊 expires_at_utc 界定，read-only 可判。
    """
    payload, error = _read_json(plan_path)
    auth = payload.get("operator_authorization")
    auth = auth if isinstance(auth, dict) else {}
    expires_at = _parse_ts(auth.get("expires_at_utc"))
    active = (
        error is None
        and payload.get("status") == "READY_FOR_DEMO_LEARNING_PROBE"
        and expires_at is not None
        and expires_at > now_utc
    )
    return {
        "path": str(plan_path),
        "present": error is None,
        "error": error,
        "envelope_active": active,
        "expires_at_utc": auth.get("expires_at_utc"),
        "side_cell_key": auth.get("side_cell_key"),
    }


def _admission_decision_distribution(
    ledger_path: Path,
    *,
    now_utc: dt.datetime,
    window_seconds: int,
) -> dict[str, Any]:
    """統計滾動窗內 admission decision 的**分布**(非 ledger 行數)。

    為什麼用分布而非「有無新行」：§1.4 評審實證 capture-error 等雜 record 會餵飽 ledger
    行數使「有行=健康」的判據失明。故只計 record_type=probe_admission_decision 的記錄，
    輸出各 decision 值計數 + admitted / withheld 分類，讓哨兵判「窗內是否真有 admission
    活動且分布非全空/退化」。
    """
    try:
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {
            "path": str(ledger_path),
            "present": False,
            "error": "missing",
            "window_seconds": window_seconds,
            "admission_decision_count": 0,
            "decision_counts": {},
            "admitted_count": 0,
            "withheld_or_other_count": 0,
        }
    except OSError as exc:
        return {
            "path": str(ledger_path),
            "present": False,
            "error": f"{type(exc).__name__}:{exc}",
            "window_seconds": window_seconds,
            "admission_decision_count": 0,
            "decision_counts": {},
            "admitted_count": 0,
            "withheld_or_other_count": 0,
        }
    cutoff = now_utc - dt.timedelta(seconds=window_seconds)
    decision_counts: dict[str, int] = {}
    admission_count = 0
    admitted_count = 0
    parse_errors = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            parse_errors += 1
            continue
        if not isinstance(record, dict):
            continue
        if record.get("record_type") != PROBE_ADMISSION_DECISION_RECORD_TYPE:
            continue
        ts = _parse_ts(record.get("generated_at_utc") or record.get("ts_utc"))
        if ts is None or ts < cutoff:
            continue
        admission_count += 1
        decision = str(record.get("decision") or "UNKNOWN").strip() or "UNKNOWN"
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
        if decision == ADMIT_DECISION:
            admitted_count += 1
    return {
        "path": str(ledger_path),
        "present": True,
        "error": None,
        "window_seconds": window_seconds,
        "admission_decision_count": admission_count,
        "decision_counts": decision_counts,
        "admitted_count": admitted_count,
        "withheld_or_other_count": admission_count - admitted_count,
        "line_parse_errors": parse_errors,
    }


def _soak_sentinel(
    *,
    armed_adapter: bool,
    envelope: dict[str, Any],
    distribution: dict[str, Any],
    now_utc: dt.datetime,
) -> dict[str, Any]:
    """soak 哨兵：武裝中(flag=1∧envelope Active)而滾動 N 小時 admission 活動全空 → WARN。

    判據=admission decision 分布(禁 ledger 行數判據)。over-gate 誤殺誤禁的靜默是本哨兵
    要暴露的核心風險——soak 武裝卻長時間零 admission 決策=可能全被 over-gate 拒真而無人知。
    """
    armed = bool(armed_adapter) and bool(envelope.get("envelope_active"))
    admission_count = int(distribution.get("admission_decision_count") or 0)
    reasons: list[str] = []
    if armed and admission_count == 0:
        reasons.append("soak_armed_but_zero_admission_decisions_in_window")
    warn = bool(reasons)
    return {
        "armed": armed,
        "adapter_armed_input": bool(armed_adapter),
        "envelope_active": bool(envelope.get("envelope_active")),
        "envelope": envelope,
        "admission_distribution": distribution,
        "warn": warn,
        "reasons": reasons,
        "next_action": (
            "inspect_over_gate_admission_reasons_soak_window_zero_admission"
            if warn
            else "no_soak_sentinel_action"
        ),
    }


def build_healthcheck(
    *,
    data_dir: Path,
    repo_root: Path,
    expected_head: str | None,
    crontab_text_file: Path | None,
    max_heartbeat_age_minutes: int,
    max_status_age_minutes: int,
    soak_adapter_armed: bool = False,
    soak_plan_json: Path | None = None,
    probe_ledger_jsonl: Path | None = None,
    soak_sentinel_window_hours: int = 6,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = now_utc or _utc_now()
    max_heartbeat_age_seconds = max_heartbeat_age_minutes * 60
    max_status_age_seconds = max_status_age_minutes * 60

    crontab_text, crontab_error = _read_crontab(crontab_text_file)
    cron = _cron_summary(crontab_text, crontab_error)
    source = _source_summary(repo_root, expected_head)

    heartbeat_dir = data_dir / "cron_heartbeat"
    log_dir = data_dir / "logs"
    demo = _component_summary(
        name="demo_learning_evidence",
        heartbeat=_file_age(
            heartbeat_dir / "demo_learning_evidence_audit.last_fire",
            now_utc=now,
        ),
        status_log=log_dir / "demo_learning_evidence_audit.log",
        latest_json=data_dir
        / "demo_learning_evidence"
        / "demo_learning_evidence_audit_latest.json",
        now_utc=now,
        max_heartbeat_age_seconds=max_heartbeat_age_seconds,
        max_status_age_seconds=max_status_age_seconds,
    )
    cost = _component_summary(
        name="cost_gate_learning_lane",
        heartbeat=_file_age(
            heartbeat_dir / "cost_gate_learning_lane.last_fire",
            now_utc=now,
        ),
        status_log=log_dir / "cost_gate_learning_lane.log",
        latest_json=data_dir
        / "cost_gate_learning_lane"
        / "blocked_outcome_review_latest.json",
        now_utc=now,
        max_heartbeat_age_seconds=max_heartbeat_age_seconds,
        max_status_age_seconds=max_status_age_seconds,
    )

    cost_status = cost["latest_status"]
    demo_status = demo["latest_status"]
    review_json = cost.get("latest_json") or {}
    lane_dir = data_dir / "cost_gate_learning_lane"
    sealed_preflight_cron = _component_summary(
        name="sealed_horizon_probe_preflight",
        heartbeat=_file_age(
            heartbeat_dir / "sealed_horizon_probe_preflight.last_fire",
            now_utc=now,
        ),
        status_log=log_dir / "sealed_horizon_probe_preflight.log",
        latest_json=lane_dir / "sealed_horizon_probe_preflight_latest.json",
        now_utc=now,
        max_heartbeat_age_seconds=max_heartbeat_age_seconds,
        max_status_age_seconds=max_status_age_seconds,
    )
    sealed_preflight = _artifact_status(
        lane_dir / "sealed_horizon_probe_preflight_latest.json",
        now_utc=now,
    )
    bounded_result_review = _artifact_status(
        lane_dir / "bounded_probe_result_review_latest.json",
        now_utc=now,
    )
    bounded_execution_review = _artifact_status(
        lane_dir / "bounded_probe_execution_realism_review_latest.json",
        now_utc=now,
    )
    false_negative_candidate_packet = _artifact_status(
        lane_dir / "false_negative_candidate_packet_latest.json",
        now_utc=now,
    )
    false_negative_operator_review = _artifact_status(
        lane_dir / "false_negative_operator_review_latest.json",
        now_utc=now,
    )

    cost_rcs = [
        cost_status.get("scorecard_rc"),
        cost_status.get("plan_rc"),
        cost_status.get("materializer_rc"),
        cost_status.get("refresh_rc"),
        cost_status.get("review_rc"),
        cost_status.get("false_negative_candidate_packet_rc"),
        cost_status.get("false_negative_operator_review_rc"),
        cost_status.get("bounded_probe_result_review_rc"),
        cost_status.get("bounded_probe_execution_realism_review_rc"),
    ]
    cost_error = any(rc not in (None, 0) for rc in cost_rcs)
    stack_installed = (
        cron["demo_learning_evidence_entry_present"]
        and cron["sealed_horizon_probe_preflight_entry_present"]
        and cron["cost_gate_learning_lane_entry_present"]
        and cron["demo_learning_stack_healthcheck_entry_present"]
    )
    heartbeats_recent = (
        demo["heartbeat_recent"]
        and sealed_preflight_cron["heartbeat_recent"]
        and cost["heartbeat_recent"]
    )
    statuses_recent = (
        demo["latest_status_recent"]
        and sealed_preflight_cron["latest_status_recent"]
        and cost["latest_status_recent"]
    )
    latest_artifacts_present = (
        demo["latest_json_error"] is None and cost["latest_json_error"] is None
    )
    bounded_reviews_present = (
        bounded_result_review["present"] and bounded_execution_review["present"]
    )
    false_negative_review_chain_present = (
        false_negative_candidate_packet["present"]
        and false_negative_operator_review["present"]
    )
    false_negative_review_chain_recent = (
        _is_recent(
            false_negative_candidate_packet["age_seconds"],
            max_status_age_seconds,
        )
        and _is_recent(
            false_negative_operator_review["age_seconds"],
            max_status_age_seconds,
        )
    )
    ledger_rows = cost_status.get("ledger_row_count")
    blocked_outcomes = (
        cost_status.get("blocked_signal_outcome_count")
        if cost_status.get("blocked_signal_outcome_count") is not None
        else review_json.get("blocked_signal_outcome_count")
    )
    review_status = cost_status.get("review_status") or review_json.get("status")
    demo_classification_status = demo_status.get("classification_status")
    source_ready = (
        source["source_clean"]
        and (source["expected_head_matches"] is not False)
        and source["head_error"] is None
    )

    # soak 哨兵軸(RES-9)：僅武裝中(adapter armed∧envelope Active)才產 WARN；未武裝=非適用。
    soak_plan_path = (
        soak_plan_json
        if soak_plan_json is not None
        else lane_dir / "bounded_demo_probe_soak_plan.json"
    )
    probe_ledger_path = (
        probe_ledger_jsonl
        if probe_ledger_jsonl is not None
        else lane_dir / "probe_ledger.jsonl"
    )
    soak_window_seconds = max(1, int(soak_sentinel_window_hours)) * 3600
    soak_envelope = _soak_envelope_status(soak_plan_path, now_utc=now)
    admission_distribution = _admission_decision_distribution(
        probe_ledger_path, now_utc=now, window_seconds=soak_window_seconds
    )
    soak_sentinel = _soak_sentinel(
        armed_adapter=soak_adapter_armed,
        envelope=soak_envelope,
        distribution=admission_distribution,
        now_utc=now,
    )

    status = "EVIDENCE_STACK_ACTIVE"
    reason = "demo_learning_stack_recent_and_evidence_available"
    next_action = "observe_blocked_outcome_review_before_any_bounded_probe"
    if not source_ready:
        status = "SOURCE_NOT_READY"
        reason = "runtime_source_not_clean_or_expected_head_mismatch"
        next_action = "reconcile_runtime_source_before_stack_install_or_validation"
    elif not stack_installed:
        status = "NOT_INSTALLED"
        reason = "one_or_more_demo_learning_stack_crons_missing"
        next_action = "install_stack_after_operator_source_reconcile"
    elif not heartbeats_recent:
        status = "INSTALLED_NOT_FIRING"
        reason = "one_or_more_stack_heartbeats_missing_or_stale"
        next_action = "inspect_cron_logs_and_crontab_schedule"
    elif not statuses_recent:
        status = "FIRING_NO_RECENT_STATUS"
        reason = "heartbeats_recent_but_status_jsonl_missing_or_stale"
        next_action = "inspect_cron_logs_for_runtime_or_python_errors"
    elif cost_error:
        status = "ERROR"
        reason = "cost_gate_learning_lane_reported_nonzero_stage_rc"
        next_action = "inspect_cost_gate_learning_lane_status_log_and_stage_artifacts"
    elif not latest_artifacts_present:
        status = "FIRING_BUT_ARTIFACTS_INCOMPLETE"
        reason = "one_or_both_latest_evidence_artifacts_missing_or_unreadable"
        next_action = "wait_one_cycle_or_inspect_latest_artifact_paths"
    elif not ledger_rows:
        status = "RUNNING_NO_LEDGER_ROWS"
        reason = "stack_running_but_no_cost_gate_learning_ledger_rows_yet"
        next_action = "confirm_materializer_input_rows_and_writer_or_pg_reject_source"
    elif not blocked_outcomes:
        status = "LEDGER_ONLY_NEEDS_OUTCOME_REFRESH"
        reason = "ledger_rows_present_but_no_blocked_signal_outcomes_yet"
        next_action = "wait_for_outcome_refresh_or_inspect_price_observation_windows"
    elif not sealed_preflight["present"]:
        status = "BOUNDED_PROBE_PREFLIGHT_MISSING"
        reason = "sealed_horizon_probe_preflight_latest_missing_or_unreadable"
        next_action = "refresh_sealed_horizon_probe_preflight_before_bounded_probe_reviews"
    elif not false_negative_candidate_packet["present"]:
        status = "FALSE_NEGATIVE_CANDIDATE_PACKET_MISSING"
        reason = "blocked_outcomes_present_but_false_negative_candidate_packet_missing"
        next_action = "rerun_cost_gate_learning_lane_cron_to_refresh_false_negative_packet"
    elif not false_negative_operator_review["present"]:
        status = "FALSE_NEGATIVE_OPERATOR_REVIEW_MISSING"
        reason = "false_negative_candidate_packet_present_but_defer_review_missing"
        next_action = "rerun_cost_gate_learning_lane_cron_to_refresh_false_negative_operator_review"
    elif not false_negative_review_chain_recent:
        status = "FALSE_NEGATIVE_REVIEW_CHAIN_STALE"
        reason = "false_negative_candidate_or_operator_review_artifact_stale"
        next_action = "rerun_cost_gate_learning_lane_cron_to_refresh_false_negative_review_chain"
    elif not bounded_reviews_present:
        status = "BOUNDED_PROBE_REVIEW_ARTIFACTS_MISSING"
        reason = "bounded_probe_result_or_execution_realism_review_latest_missing_or_unreadable"
        next_action = "rerun_cost_gate_learning_lane_cron_after_sealed_preflight_refresh"
    elif soak_sentinel["warn"]:
        # soak 哨兵僅在 stack 本身已綠(EVIDENCE_STACK_ACTIVE)時才升 WARN，避免掩蓋更嚴重
        # blocker；語意=stack 健康但 soak 武裝窗零 admission 活動，需查 over-gate 誤殺。
        status = "SOAK_SENTINEL_WARN"
        reason = ";".join(soak_sentinel["reasons"])
        next_action = soak_sentinel["next_action"]

    return {
        "schema_version": SCHEMA_VERSION,
        "ts_utc": now.isoformat().replace("+00:00", "Z"),
        "status": status,
        "reason": reason,
        "next_action": next_action,
        "thresholds": {
            "max_heartbeat_age_minutes": max_heartbeat_age_minutes,
            "max_status_age_minutes": max_status_age_minutes,
            "soak_sentinel_window_hours": soak_sentinel_window_hours,
        },
        "answers": {
            "source_ready": source_ready,
            "stack_installed": stack_installed,
            "demo_learning_evidence_cron_entry_present": cron[
                "demo_learning_evidence_entry_present"
            ],
            "sealed_horizon_probe_preflight_cron_entry_present": cron[
                "sealed_horizon_probe_preflight_entry_present"
            ],
            "cost_gate_learning_lane_cron_entry_present": cron[
                "cost_gate_learning_lane_entry_present"
            ],
            "demo_learning_stack_healthcheck_cron_entry_present": cron[
                "demo_learning_stack_healthcheck_entry_present"
            ],
            "heartbeats_recent": heartbeats_recent,
            "demo_learning_evidence_heartbeat_recent": demo["heartbeat_recent"],
            "sealed_horizon_probe_preflight_heartbeat_recent": sealed_preflight_cron[
                "heartbeat_recent"
            ],
            "cost_gate_learning_lane_heartbeat_recent": cost["heartbeat_recent"],
            "statuses_recent": statuses_recent,
            "demo_learning_evidence_status_recent": demo["latest_status_recent"],
            "sealed_horizon_probe_preflight_status_recent": sealed_preflight_cron[
                "latest_status_recent"
            ],
            "cost_gate_learning_lane_status_recent": cost["latest_status_recent"],
            "latest_artifacts_present": latest_artifacts_present,
            "sealed_horizon_probe_preflight_present": sealed_preflight["present"],
            "false_negative_review_chain_present": false_negative_review_chain_present,
            "false_negative_review_chain_recent": false_negative_review_chain_recent,
            "false_negative_candidate_packet_present": (
                false_negative_candidate_packet["present"]
            ),
            "false_negative_operator_review_present": (
                false_negative_operator_review["present"]
            ),
            "false_negative_candidate_packet_status": (
                false_negative_candidate_packet["status"]
            ),
            "false_negative_operator_review_status": (
                false_negative_operator_review["status"]
            ),
            "bounded_probe_reviews_present": bounded_reviews_present,
            "bounded_probe_result_review_present": bounded_result_review["present"],
            "bounded_probe_execution_realism_review_present": (
                bounded_execution_review["present"]
            ),
            "bounded_probe_result_review_skip_reason": cost_status.get(
                "bounded_probe_result_review_skip_reason"
            ),
            "bounded_probe_execution_realism_review_skip_reason": cost_status.get(
                "bounded_probe_execution_realism_review_skip_reason"
            ),
            "cost_gate_learning_stage_error": cost_error,
            "cost_gate_learning_ledger_rows_present": bool(ledger_rows),
            "soak_sentinel_armed": soak_sentinel["armed"],
            "soak_sentinel_warn": soak_sentinel["warn"],
            "soak_window_admission_decision_count": (
                admission_distribution["admission_decision_count"]
            ),
            "blocked_signal_outcomes_present": bool(blocked_outcomes),
            "blocked_outcome_review_present": bool(review_status),
            "demo_learning_evidence_classification_status": demo_classification_status,
            "cost_gate_learning_review_status": review_status,
            "bounded_probe_result_review_status": bounded_result_review["status"],
            "bounded_probe_execution_realism_review_status": (
                bounded_execution_review["status"]
            ),
        },
        "source": source,
        "cron": cron,
        "soak_sentinel": soak_sentinel,
        "components": {
            "demo_learning_evidence": demo,
            "sealed_horizon_probe_preflight_cron": sealed_preflight_cron,
            "cost_gate_learning_lane": cost,
            "sealed_horizon_probe_preflight": sealed_preflight,
            "false_negative_candidate_packet": false_negative_candidate_packet,
            "false_negative_operator_review": false_negative_operator_review,
            "bounded_probe_result_review": bounded_result_review,
            "bounded_probe_execution_realism_review": bounded_execution_review,
        },
        "boundary": (
            "read-only crontab/artifact/status/source healthcheck with optional "
            "explicit local JSON artifact output only; no PG write, Bybit call, "
            "order authority, writer enablement, Cost Gate lowering, deploy, "
            "restart, or crontab mutation"
        ),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        default="/tmp/openclaw",
        help="OPENCLAW_DATA_DIR to inspect (default: /tmp/openclaw)",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="source checkout to inspect with local git commands",
    )
    parser.add_argument("--expected-head", default=None)
    parser.add_argument("--crontab-text-file", type=Path, default=None)
    parser.add_argument("--max-heartbeat-age-minutes", type=int, default=90)
    parser.add_argument("--max-status-age-minutes", type=int, default=180)
    parser.add_argument(
        "--soak-adapter-armed",
        action="store_true",
        help=(
            "declare the bounded-probe adapter is armed "
            "(OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=1); soak sentinel only warns "
            "when armed AND the soak envelope is active"
        ),
    )
    parser.add_argument(
        "--soak-plan-json",
        type=Path,
        default=None,
        help="canonical soak plan path (default: <data-dir>/cost_gate_learning_lane/bounded_demo_probe_soak_plan.json)",
    )
    parser.add_argument(
        "--probe-ledger-jsonl",
        type=Path,
        default=None,
        help="probe ledger path for admission decision distribution (default: <data-dir>/cost_gate_learning_lane/probe_ledger.jsonl)",
    )
    parser.add_argument("--soak-sentinel-window-hours", type=int, default=6)
    parser.add_argument(
        "--now-utc",
        default=None,
        help="test hook: ISO timestamp, defaults to current UTC",
    )
    parser.add_argument(
        "--fail-on-not-active",
        action="store_true",
        help="return nonzero unless status is EVIDENCE_STACK_ACTIVE",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help=(
            "optional explicit artifact path to write the healthcheck JSON; "
            "stdout is still emitted"
        ),
    )
    return parser.parse_args(argv)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    now = _parse_ts(args.now_utc) if args.now_utc else None
    if args.max_heartbeat_age_minutes <= 0 or args.max_status_age_minutes <= 0:
        raise SystemExit("age thresholds must be positive")
    if args.soak_sentinel_window_hours <= 0:
        raise SystemExit("soak sentinel window hours must be positive")
    payload = build_healthcheck(
        data_dir=Path(args.data_dir),
        repo_root=Path(args.repo_root),
        expected_head=args.expected_head,
        crontab_text_file=args.crontab_text_file,
        max_heartbeat_age_minutes=args.max_heartbeat_age_minutes,
        max_status_age_minutes=args.max_status_age_minutes,
        soak_adapter_armed=args.soak_adapter_armed,
        soak_plan_json=args.soak_plan_json,
        probe_ledger_jsonl=args.probe_ledger_jsonl,
        soak_sentinel_window_hours=args.soak_sentinel_window_hours,
        now_utc=now,
    )
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    print(text)
    if args.json_output is not None:
        _write_json_atomic(args.json_output, payload)
    if args.fail_on_not_active and payload.get("status") != "EVIDENCE_STACK_ACTIVE":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
