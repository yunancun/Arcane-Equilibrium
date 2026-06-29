#!/usr/bin/env python3
"""Read-only SSOT snapshot for the learning stack health gate.

This is the Phase-1 source-only health interface from the 2026-06-29 learning
engine completion plan. It aggregates existing local artifacts and crontab
shape into one fail-closed packet. It does not connect to PG, call Bybit, edit
crontab, restart services, lower Cost Gate, or grant mutation/order authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "learning_stack_health_snapshot_v1"
READY_STATUS = "LEARNING_STACK_READY_FOR_SOURCE_ONLY_REVIEW"
DEGRADED_STATUS = "LEARNING_STACK_DEGRADED"

EXPECTED_CRON_MARKERS = {
    "demo_learning_evidence": "demo_learning_evidence_audit_cron.sh",
    "sealed_horizon_probe_preflight": "sealed_horizon_probe_preflight_cron.sh",
    "cost_gate_learning_lane": "cost_gate_learning_lane_cron.sh",
    "demo_learning_stack_healthcheck": "demo_learning_stack_healthcheck_cron.sh",
    "ml_training_maintenance": "ml_training_maintenance_cron.sh",
}
EXPECTED_HEAD_ENV_RE = re.compile(
    r"\b(?P<name>OPENCLAW_(?:EXPECTED_SOURCE_HEAD|[A-Z0-9_]*EXPECTED_HEAD))="
    r"(?P<value>[0-9a-fA-F]{7,40})\b"
)
SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_ts(value: Any) -> dt.datetime | None:
    if value is None:
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


def _format_ts(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _age_seconds(value: Any, *, now_utc: dt.datetime) -> float | None:
    parsed = _parse_ts(value)
    if parsed is None:
        return None
    return max(0.0, (now_utc - parsed).total_seconds())


def _read_json(path: Path) -> tuple[dict[str, Any], str | None, str | None]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}, "missing", None
    except OSError as exc:
        return {}, f"{type(exc).__name__}:{exc}", None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, f"json_decode_error:{exc}", hashlib.sha256(raw).hexdigest()
    if not isinstance(payload, dict):
        return {}, "json_not_object", hashlib.sha256(raw).hexdigest()
    return payload, None, hashlib.sha256(raw).hexdigest()


def _read_jsonl_tail(path: Path, limit: int) -> tuple[list[dict[str, Any]], str | None]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return [], "missing"
    except OSError as exc:
        return [], f"{type(exc).__name__}:{exc}"
    rows: list[dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            return [], f"json_line_decode_error:{exc}"
        if not isinstance(payload, dict):
            return [], "json_line_not_object"
        rows.append(payload)
        if len(rows) >= limit:
            break
    rows.reverse()
    return rows, None


def _file_meta(path: Path, *, now_utc: dt.datetime) -> dict[str, Any]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {
            "path": str(path),
            "present": False,
            "mtime_utc": None,
            "age_seconds": None,
            "size_bytes": None,
            "sha256": None,
        }
    except OSError as exc:
        return {
            "path": str(path),
            "present": False,
            "error": f"{type(exc).__name__}:{exc}",
            "mtime_utc": None,
            "age_seconds": None,
            "size_bytes": None,
            "sha256": None,
        }
    mtime = dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.timezone.utc)
    digest: str | None = None
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        digest = None
    return {
        "path": str(path),
        "present": True,
        "mtime_utc": _format_ts(mtime),
        "age_seconds": max(0.0, (now_utc - mtime).total_seconds()),
        "size_bytes": stat.st_size,
        "sha256": digest,
    }


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


def _normalize_expected_head(value: str | None) -> tuple[str | None, str | None]:
    text = str(value or "").strip()
    if not text:
        return None, None
    if not SHA_RE.fullmatch(text):
        return text, "expected_head_must_be_7_to_40_hex_chars"
    return text.lower(), None


def _sha_prefix_matches(left: str | None, right: str | None) -> bool | None:
    left_norm, left_error = _normalize_expected_head(left)
    right_norm, right_error = _normalize_expected_head(right)
    if left_error or right_error or not left_norm or not right_norm:
        return None
    return left_norm.startswith(right_norm) or right_norm.startswith(left_norm)


def _cron_expected_head_pins(
    active_entries: list[str],
    expected_head: str | None,
) -> dict[str, Any]:
    normalized_expected, expected_error = _normalize_expected_head(expected_head)
    entries = []
    missing_components = []
    invalid_entries = []
    mismatched_entries = []
    for component, marker in EXPECTED_CRON_MARKERS.items():
        matching = [line for line in active_entries if marker in line]
        if not matching:
            missing_components.append(component)
            continue
        line = matching[0]
        pins = [
            {"name": match.group("name"), "value": match.group("value").lower()}
            for match in EXPECTED_HEAD_ENV_RE.finditer(line)
        ]
        if not pins:
            missing_components.append(component)
        for pin in pins:
            validation_error = _normalize_expected_head(pin["value"])[1]
            if validation_error:
                invalid_entries.append(
                    {
                        "component": component,
                        "name": pin["name"],
                        "value": pin["value"],
                        "validation_error": validation_error,
                    }
                )
                continue
            if (
                normalized_expected
                and _sha_prefix_matches(pin["value"], normalized_expected) is False
            ):
                mismatched_entries.append(
                    {
                        "component": component,
                        "name": pin["name"],
                        "value": pin["value"],
                        "target_expected_head": normalized_expected,
                    }
                )
        entries.append({"component": component, "pins": pins})
    if expected_error:
        status = "INVALID_TARGET_EXPECTED_HEAD"
    elif not normalized_expected:
        status = "TARGET_EXPECTED_HEAD_NOT_PROVIDED"
    elif missing_components:
        status = "EXPECTED_HEAD_PIN_MISSING"
    elif invalid_entries:
        status = "EXPECTED_HEAD_PIN_INVALID"
    elif mismatched_entries:
        status = "EXPECTED_HEAD_PIN_MISMATCH"
    else:
        status = "EXPECTED_HEAD_PINS_MATCH_TARGET"
    return {
        "status": status,
        "target_expected_head": normalized_expected,
        "target_expected_head_error": expected_error,
        "pins_match_target": status
        in {"EXPECTED_HEAD_PINS_MATCH_TARGET", "TARGET_EXPECTED_HEAD_NOT_PROVIDED"},
        "entries": entries,
        "missing_components": missing_components,
        "invalid_entries": invalid_entries,
        "mismatched_entries": mismatched_entries,
    }


def _cron_summary(
    text: str,
    error: str | None,
    expected_head: str | None,
) -> dict[str, Any]:
    entries = [line.strip() for line in text.splitlines() if line.strip()]
    active_entries = [line for line in entries if not line.startswith("#")]
    marker_counts = {
        name: sum(1 for line in active_entries if marker in line)
        for name, marker in EXPECTED_CRON_MARKERS.items()
    }
    expected_head_pins = _cron_expected_head_pins(active_entries, expected_head)
    return {
        "read_error": error,
        "active_entry_count": len(active_entries),
        "expected_marker_counts": marker_counts,
        "expected_markers_present": {
            name: count > 0 for name, count in marker_counts.items()
        },
        "expected_markers_unique": {
            name: count == 1 for name, count in marker_counts.items()
        },
        "unique_scheduler_authority": (
            error is None and all(count == 1 for count in marker_counts.values())
        ),
        "expected_head_pins": expected_head_pins,
        "expected_head_pins_match_target": expected_head_pins["pins_match_target"],
        "matching_entries": [
            line
            for line in active_entries
            if any(marker in line for marker in EXPECTED_CRON_MARKERS.values())
        ][:20],
    }


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
    normalized_expected, expected_error = _normalize_expected_head(expected_head)
    expected_head_matches = None
    if expected_error:
        expected_status = "INVALID"
        expected_head_matches = False
    elif not normalized_expected:
        expected_status = "NOT_PROVIDED"
    elif not head:
        expected_status = "HEAD_UNAVAILABLE"
        expected_head_matches = False
    elif _sha_prefix_matches(head, normalized_expected):
        expected_status = "MATCH"
        expected_head_matches = True
    else:
        expected_status = "MISMATCH"
        expected_head_matches = False
    return {
        "repo_root": str(repo_root),
        "head": head,
        "head_error": head_error,
        "expected_head": normalized_expected or expected_head or None,
        "expected_head_status": expected_status,
        "expected_head_matches": expected_head_matches,
        "expected_head_error": expected_error,
        "dirty_error": dirty_error,
        "dirty_path_count": len(dirty_lines),
        "dirty_path_sample": dirty_lines[:20],
        "source_clean": dirty_error is None and len(dirty_lines) == 0,
    }


def _status_age_ok(age_seconds: float | None, max_age_seconds: int) -> bool:
    return age_seconds is not None and age_seconds <= max_age_seconds


def _demo_stack_component(
    path: Path,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    payload, error, digest = _read_json(path)
    ts = payload.get("ts_utc") or payload.get("generated_at_utc")
    age = _age_seconds(ts, now_utc=now_utc)
    return {
        "path": str(path),
        "read_error": error,
        "sha256": digest,
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "next_action": payload.get("next_action"),
        "ts_utc": ts,
        "age_seconds": age,
        "fresh": error is None and _status_age_ok(age, max_age_seconds),
        "evidence_stack_active": payload.get("status") == "EVIDENCE_STACK_ACTIVE",
        "answers": payload.get("answers") if isinstance(payload.get("answers"), dict) else {},
    }


def _maintenance_component(
    status_path: Path,
    history_path: Path | None,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    payload, error, digest = _read_json(status_path)
    ts = payload.get("ts_utc") or payload.get("generated_at_utc") or payload.get("started_at_utc")
    age = _age_seconds(ts, now_utc=now_utc)
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    job_statuses = {
        str(row.get("job")): row.get("status")
        for row in results
        if isinstance(row, dict) and row.get("job")
    }
    latest_ok = (
        error is None
        and payload.get("status") == "ok"
        and all(status != "error" for status in job_statuses.values())
    )
    history_rows: list[dict[str, Any]] = []
    history_error: str | None = None
    if history_path is not None:
        history_rows, history_error = _read_jsonl_tail(history_path, 2)
    last_two_ok = (
        history_error is None
        and len(history_rows) >= 2
        and all(row.get("status") == "ok" for row in history_rows)
    )
    return {
        "path": str(status_path),
        "read_error": error,
        "sha256": digest,
        "status": payload.get("status"),
        "ts_utc": ts,
        "age_seconds": age,
        "fresh": error is None and _status_age_ok(age, max_age_seconds),
        "latest_ok": latest_ok,
        "job_statuses": job_statuses,
        "history_path": str(history_path) if history_path is not None else None,
        "history_error": history_error,
        "history_rows": history_rows,
        "last_two_cycles_ok": last_two_ok,
    }


def _scan_model_artifacts(paths: list[Path], *, now_utc: dt.datetime) -> dict[str, Any]:
    seen: dict[str, dict[str, Any]] = {}
    for path in paths:
        if path.is_dir():
            for child in path.rglob("*.onnx"):
                seen[str(child)] = _file_meta(child, now_utc=now_utc)
        elif path.suffix == ".onnx":
            seen[str(path)] = _file_meta(path, now_utc=now_utc)
    artifacts = sorted(seen.values(), key=lambda item: str(item.get("path")))
    newest = None
    for item in artifacts:
        parsed = _parse_ts(item.get("mtime_utc"))
        if parsed is None:
            continue
        if newest is None or parsed > newest:
            newest = parsed
    return {
        "artifact_count": len(artifacts),
        "artifacts": artifacts[:50],
        "newest_artifact_mtime_utc": _format_ts(newest) if newest else None,
    }


def _registry_component(
    summary_path: Path,
    artifact_paths: list[Path],
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    payload, error, digest = _read_json(summary_path)
    latest_ts = (
        payload.get("latest_registry_row_utc")
        or payload.get("latest_registered_at_utc")
        or payload.get("generated_at_utc")
    )
    latest_age = _age_seconds(latest_ts, now_utc=now_utc)
    inventory = _scan_model_artifacts(artifact_paths, now_utc=now_utc)
    newest_artifact_ts = _parse_ts(inventory.get("newest_artifact_mtime_utc"))
    latest_registry_ts = _parse_ts(latest_ts)
    artifact_newer_than_registry = False
    if newest_artifact_ts is not None and latest_registry_ts is not None:
        artifact_newer_than_registry = newest_artifact_ts > (
            latest_registry_ts + dt.timedelta(seconds=60)
        )
    status_ok = payload.get("status") in {"ok", "OK", "ready", "READY"}
    registry_rows = int(payload.get("registry_row_count") or 0)
    shadow_rows = int(payload.get("shadow_or_canary_row_count") or 0)
    trio_complete = payload.get("q10_q50_q90_trio_complete") is True
    return {
        "path": str(summary_path),
        "read_error": error,
        "sha256": digest,
        "status": payload.get("status"),
        "latest_registry_row_utc": latest_ts,
        "latest_registry_age_seconds": latest_age,
        "fresh": error is None and _status_age_ok(latest_age, max_age_seconds),
        "registry_row_count": registry_rows,
        "shadow_or_canary_row_count": shadow_rows,
        "q10_q50_q90_trio_complete": trio_complete,
        "artifact_hash_parity_ok": payload.get("artifact_hash_parity_ok") is True,
        "feature_schema_hash_present": bool(payload.get("feature_schema_hash")),
        "registry_status_ok": status_ok,
        "artifact_inventory": inventory,
        "artifact_newer_than_registry": artifact_newer_than_registry,
    }


def _ledger_component(
    ledger_path: Path,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    rows, error = _read_jsonl_tail(ledger_path, 200)
    meta = _file_meta(ledger_path, now_utc=now_utc)
    latest = rows[-1] if rows else {}
    promotion_count = sum(1 for row in rows if row.get("promotion_evidence") is True)
    allowed_submit_count = sum(
        1 for row in rows if row.get("allowed_to_submit_order") is True
    )
    fill_backed_count = sum(
        1
        for row in rows
        if row.get("proof_tier") == "fill_backed"
        or row.get("fill_backed_evidence") is True
        or int(row.get("candidate_matched_fill_count") or 0) > 0
    )
    return {
        "path": str(ledger_path),
        "read_error": error,
        "file": meta,
        "tail_row_count": len(rows),
        "latest_row": latest,
        "fresh": error is None and _status_age_ok(meta.get("age_seconds"), max_age_seconds),
        "allowed_to_submit_order_count": allowed_submit_count,
        "promotion_evidence_count": promotion_count,
        "fill_backed_tail_count": fill_backed_count,
    }


def _parity_component(path: Path, *, now_utc: dt.datetime, max_age_seconds: int) -> dict[str, Any]:
    payload, error, digest = _read_json(path)
    ts = payload.get("generated_at_utc") or payload.get("ts_utc")
    age = _age_seconds(ts, now_utc=now_utc)
    status = payload.get("status")
    parity_ok = payload.get("parity_ok") is True or status in {
        "ARTIFACT_PG_PARITY_OK",
        "ok",
        "OK",
    }
    return {
        "path": str(path),
        "read_error": error,
        "sha256": digest,
        "status": status,
        "ts_utc": ts,
        "age_seconds": age,
        "fresh": error is None and _status_age_ok(age, max_age_seconds),
        "parity_ok": error is None and parity_ok,
        "mismatch_count": payload.get("mismatch_count"),
    }


def _proof_component(path: Path, *, now_utc: dt.datetime, max_age_seconds: int) -> dict[str, Any]:
    payload, error, digest = _read_json(path)
    ts = payload.get("generated_at_utc") or payload.get("ts_utc")
    age = _age_seconds(ts, now_utc=now_utc)
    fill_count = int(payload.get("candidate_matched_fill_count") or 0)
    proof_exclusions_clear = payload.get("proof_exclusions_clear") is True
    return {
        "path": str(path),
        "read_error": error,
        "sha256": digest,
        "status": payload.get("status"),
        "ts_utc": ts,
        "age_seconds": age,
        "fresh": error is None and _status_age_ok(age, max_age_seconds),
        "candidate_matched_fill_count": fill_count,
        "proof_exclusions_clear": proof_exclusions_clear,
        "fill_backed_evidence_present": (
            error is None and fill_count > 0 and proof_exclusions_clear
        ),
    }


def _append_blocker(blockers: list[str], condition: bool, reason: str) -> None:
    if not condition:
        blockers.append(reason)


def build_snapshot(
    *,
    data_dir: Path,
    repo_root: Path,
    expected_head: str | None,
    crontab_text_file: Path | None,
    demo_stack_health_json: Path,
    ml_maintenance_status_json: Path,
    ml_maintenance_status_log_jsonl: Path | None,
    model_registry_summary_json: Path,
    model_artifact_paths: list[Path],
    artifact_pg_parity_json: Path,
    proof_summary_json: Path,
    probe_ledger_jsonl: Path,
    max_status_age_minutes: int,
    max_registry_age_hours: int,
    max_ledger_age_minutes: int,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = now_utc or _utc_now()
    max_status_age_seconds = max_status_age_minutes * 60
    max_registry_age_seconds = max_registry_age_hours * 3600
    max_ledger_age_seconds = max_ledger_age_minutes * 60

    crontab_text, crontab_error = _read_crontab(crontab_text_file)
    cron = _cron_summary(crontab_text, crontab_error, expected_head)
    source = _source_summary(repo_root, expected_head)
    demo_stack = _demo_stack_component(
        demo_stack_health_json,
        now_utc=now,
        max_age_seconds=max_status_age_seconds,
    )
    maintenance = _maintenance_component(
        ml_maintenance_status_json,
        ml_maintenance_status_log_jsonl,
        now_utc=now,
        max_age_seconds=max_status_age_seconds,
    )
    registry = _registry_component(
        model_registry_summary_json,
        model_artifact_paths,
        now_utc=now,
        max_age_seconds=max_registry_age_seconds,
    )
    ledger = _ledger_component(
        probe_ledger_jsonl,
        now_utc=now,
        max_age_seconds=max_ledger_age_seconds,
    )
    parity = _parity_component(
        artifact_pg_parity_json,
        now_utc=now,
        max_age_seconds=max_status_age_seconds,
    )
    proof = _proof_component(
        proof_summary_json,
        now_utc=now,
        max_age_seconds=max_status_age_seconds,
    )

    source_ready = (
        source["source_clean"]
        and source["head_error"] is None
        and source["expected_head_matches"] is not False
    )
    registry_ready = (
        registry["read_error"] is None
        and registry["registry_status_ok"]
        and registry["fresh"]
        and registry["registry_row_count"] > 0
        and registry["shadow_or_canary_row_count"] > 0
        and registry["q10_q50_q90_trio_complete"]
        and registry["artifact_hash_parity_ok"]
        and registry["feature_schema_hash_present"]
        and not registry["artifact_newer_than_registry"]
    )
    blockers: list[str] = []
    _append_blocker(blockers, source_ready, "source_not_clean_or_expected_head_mismatch")
    _append_blocker(blockers, cron["unique_scheduler_authority"], "scheduler_authority_not_unique_or_missing")
    _append_blocker(
        blockers,
        cron["expected_head_pins_match_target"] is not False,
        "scheduler_expected_head_pin_mismatch",
    )
    _append_blocker(blockers, demo_stack["fresh"], "demo_stack_health_snapshot_stale_or_missing")
    _append_blocker(blockers, demo_stack["evidence_stack_active"], "demo_stack_evidence_not_active")
    _append_blocker(blockers, maintenance["fresh"], "ml_training_maintenance_status_stale_or_missing")
    _append_blocker(blockers, maintenance["latest_ok"], "ml_training_maintenance_latest_not_ok")
    _append_blocker(blockers, maintenance["last_two_cycles_ok"], "ml_training_maintenance_last_two_cycles_not_ok")
    _append_blocker(blockers, registry_ready, "model_registry_not_fresh_or_artifact_parity_failed")
    _append_blocker(blockers, ledger["fresh"], "learning_probe_ledger_stale_or_missing")
    _append_blocker(blockers, ledger["tail_row_count"] > 0, "learning_probe_ledger_empty")
    _append_blocker(blockers, parity["fresh"], "artifact_pg_parity_snapshot_stale_or_missing")
    _append_blocker(blockers, parity["parity_ok"], "artifact_pg_parity_not_ok")
    _append_blocker(blockers, proof["fresh"], "fill_backed_proof_summary_stale_or_missing")
    _append_blocker(blockers, proof["fill_backed_evidence_present"], "fill_backed_candidate_evidence_missing")

    ready = len(blockers) == 0
    answers = {
        "source_ready": source_ready,
        "unique_scheduler_authority": cron["unique_scheduler_authority"],
        "demo_stack_health_fresh": demo_stack["fresh"],
        "demo_stack_evidence_active": demo_stack["evidence_stack_active"],
        "ml_training_maintenance_recent": maintenance["fresh"],
        "ml_training_maintenance_latest_ok": maintenance["latest_ok"],
        "ml_training_maintenance_last_two_ok": maintenance["last_two_cycles_ok"],
        "model_registry_fresh": registry["fresh"],
        "model_registry_ready": registry_ready,
        "onnx_newer_than_registry": registry["artifact_newer_than_registry"],
        "learning_ledger_fresh": ledger["fresh"],
        "learning_ledger_rows_present": ledger["tail_row_count"] > 0,
        "artifact_pg_parity_ok": parity["parity_ok"] and parity["fresh"],
        "fill_backed_evidence_present": proof["fill_backed_evidence_present"],
        "health_gate_valid_for_demo_mutation": ready,
        "mutation_enabled": False,
        "demo_mutation_authority_granted": False,
        "order_authority_granted": False,
        "live_authority_granted": False,
        "cost_gate_lowering_allowed": False,
        "bybit_call_performed": False,
        "pg_write_performed": False,
    }
    status = READY_STATUS if ready else DEGRADED_STATUS
    next_action = (
        "continue_to_learning_event_contract_source_work"
        if ready
        else "repair_learning_stack_health_inputs_before_demo_mutation"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _format_ts(now),
        "status": status,
        "reason": "all_learning_health_gates_ready" if ready else "learning_stack_health_gate_failed_closed",
        "next_action": next_action,
        "blockers": blockers,
        "thresholds": {
            "max_status_age_minutes": max_status_age_minutes,
            "max_registry_age_hours": max_registry_age_hours,
            "max_ledger_age_minutes": max_ledger_age_minutes,
        },
        "answers": answers,
        "source": source,
        "cron": cron,
        "components": {
            "demo_stack_health": demo_stack,
            "ml_training_maintenance": maintenance,
            "model_registry": registry,
            "learning_probe_ledger": ledger,
            "artifact_pg_parity": parity,
            "fill_backed_proof": proof,
        },
        "boundary": (
            "read-only source/crontab/local-artifact learning health snapshot; "
            "no PG write, DB migration, Bybit call, order/cancel/modify, "
            "Decision Lease activation, Cost Gate lowering, service restart, "
            "cron mutation, live authority, or demo mutation authority"
        ),
    }


def _default_paths(data_dir: Path) -> dict[str, Path]:
    return {
        "demo_stack_health_json": (
            data_dir
            / "demo_learning_stack_healthcheck"
            / "demo_learning_stack_healthcheck_latest.json"
        ),
        "ml_maintenance_status_json": (
            data_dir / "status" / "ml_training_maintenance_status.json"
        ),
        "ml_maintenance_status_log_jsonl": (
            data_dir / "logs" / "ml_training_maintenance_status.log"
        ),
        "model_registry_summary_json": (
            data_dir / "learning" / "model_registry_summary_latest.json"
        ),
        "artifact_pg_parity_json": (
            data_dir / "learning" / "artifact_pg_parity_latest.json"
        ),
        "proof_summary_json": data_dir / "learning" / "proof_summary_latest.json",
        "probe_ledger_jsonl": data_dir / "cost_gate_learning_lane" / "probe_ledger.jsonl",
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="/tmp/openclaw")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--expected-head", default=None)
    parser.add_argument("--crontab-text-file", type=Path, default=None)
    parser.add_argument("--demo-stack-health-json", type=Path, default=None)
    parser.add_argument("--ml-maintenance-status-json", type=Path, default=None)
    parser.add_argument("--ml-maintenance-status-log-jsonl", type=Path, default=None)
    parser.add_argument("--model-registry-summary-json", type=Path, default=None)
    parser.add_argument("--artifact-pg-parity-json", type=Path, default=None)
    parser.add_argument("--proof-summary-json", type=Path, default=None)
    parser.add_argument("--probe-ledger-jsonl", type=Path, default=None)
    parser.add_argument(
        "--model-artifact-dir",
        action="append",
        type=Path,
        default=None,
        help="directory or .onnx path to include in registry freshness parity",
    )
    parser.add_argument("--max-status-age-minutes", type=int, default=180)
    parser.add_argument("--max-registry-age-hours", type=int, default=72)
    parser.add_argument("--max-ledger-age-minutes", type=int, default=180)
    parser.add_argument("--now-utc", default=None)
    parser.add_argument("--json-output", type=Path, default=None)
    parser.add_argument("--fail-on-degraded", action="store_true")
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
    if args.max_status_age_minutes <= 0 or args.max_registry_age_hours <= 0:
        raise SystemExit("age thresholds must be positive")
    if args.max_ledger_age_minutes <= 0:
        raise SystemExit("ledger age threshold must be positive")
    data_dir = Path(args.data_dir)
    defaults = _default_paths(data_dir)
    now = _parse_ts(args.now_utc) if args.now_utc else None
    artifact_paths = args.model_artifact_dir or [data_dir / "models"]
    payload = build_snapshot(
        data_dir=data_dir,
        repo_root=Path(args.repo_root),
        expected_head=args.expected_head,
        crontab_text_file=args.crontab_text_file,
        demo_stack_health_json=args.demo_stack_health_json
        or defaults["demo_stack_health_json"],
        ml_maintenance_status_json=args.ml_maintenance_status_json
        or defaults["ml_maintenance_status_json"],
        ml_maintenance_status_log_jsonl=args.ml_maintenance_status_log_jsonl
        or defaults["ml_maintenance_status_log_jsonl"],
        model_registry_summary_json=args.model_registry_summary_json
        or defaults["model_registry_summary_json"],
        model_artifact_paths=artifact_paths,
        artifact_pg_parity_json=args.artifact_pg_parity_json
        or defaults["artifact_pg_parity_json"],
        proof_summary_json=args.proof_summary_json or defaults["proof_summary_json"],
        probe_ledger_jsonl=args.probe_ledger_jsonl or defaults["probe_ledger_jsonl"],
        max_status_age_minutes=args.max_status_age_minutes,
        max_registry_age_hours=args.max_registry_age_hours,
        max_ledger_age_minutes=args.max_ledger_age_minutes,
        now_utc=now,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    if args.json_output is not None:
        _write_json_atomic(args.json_output, payload)
    if args.fail_on_degraded and payload.get("status") != READY_STATUS:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
