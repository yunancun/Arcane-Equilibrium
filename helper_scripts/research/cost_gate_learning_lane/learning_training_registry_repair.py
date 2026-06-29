#!/usr/bin/env python3
"""Classify ML training and model-registry repair work without mutating runtime.

This helper consumes ``learning_stack_health_snapshot_v1`` and emits a
deterministic repair packet for the degraded ML maintenance / registry /
artifact-parity layer. It is a source-only review artifact: it never runs
training, connects to PG, writes a registry row, edits cron, or grants serving,
order, Cost Gate, live, or promotion authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.learning_event_contract import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
)


SCHEMA_VERSION = "cost_gate_learning_training_registry_repair_v1"
HEALTH_SCHEMA_VERSION = "learning_stack_health_snapshot_v1"
HEALTH_READY_STATUS = "LEARNING_STACK_READY_FOR_SOURCE_ONLY_REVIEW"
HEALTH_DEGRADED_STATUS = "LEARNING_STACK_DEGRADED"
READY_STATUS = "LEARNING_TRAINING_REGISTRY_REPAIR_PACKET_READY_NO_AUTHORITY"
NO_REPAIR_REQUIRED_STATUS = "LEARNING_TRAINING_REGISTRY_REPAIR_NOT_REQUIRED_NO_AUTHORITY"
INPUT_NOT_READY_STATUS = "LEARNING_STACK_HEALTH_SNAPSHOT_INPUT_NOT_READY"

BOUNDARY = (
    "artifact-only ML training/model-registry repair packet; no PG query/write, "
    "DB migration, training run, ONNX export, artifact delete, Bybit call, order, "
    "config/risk/auth/runtime/env/service/cron mutation, Cost Gate lowering, "
    "serving authority, probe/order/live authority, or promotion proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "bybit_call_performed",
    "cost_gate_lowering_allowed",
    "demo_mutation_authority_granted",
    "env_mutation_performed",
    "global_cost_gate_lowering_recommended",
    "health_gate_valid_for_demo_mutation",
    "live_authority_granted",
    "mutation_enabled",
    "onnx_export_performed",
    "order_authority_granted",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "promotion_evidence",
    "promotion_proof",
    "registry_write_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "serving_snapshot_ready",
    "training_run_performed",
}
TRUTHY_AUTHORITY_STRINGS = {
    "1",
    "true",
    "yes",
    "y",
    "on",
    "enabled",
    "grant",
    "granted",
    "authorize",
    "authorized",
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _truthy_authority(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_AUTHORITY_STRINGS
    return False


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _authority_violations(payload: Any) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    stack: list[tuple[str, Any]] = [("$", payload)]
    while stack:
        path, item = stack.pop()
        if isinstance(item, list):
            for index, value in enumerate(item):
                stack.append((f"{path}[{index}]", value))
            continue
        data = _dict(item)
        if not data:
            continue
        for key, value in data.items():
            item_path = f"{path}.{key}"
            if key == "main_cost_gate_adjustment" and value not in (None, "", "NONE"):
                violations.append(
                    {
                        "path": item_path,
                        "key": key,
                        "reason": "main_cost_gate_adjustment_not_none",
                    }
                )
            elif key in AUTHORITY_TRUE_KEYS and _truthy_authority(value):
                violations.append(
                    {
                        "path": item_path,
                        "key": key,
                        "reason": "authority_truthy_value",
                    }
                )
            if isinstance(value, (dict, list)):
                stack.append((item_path, value))
    return violations


def _repair_id(kind: str, evidence: dict[str, Any]) -> str:
    seed = {"schema_version": SCHEMA_VERSION, "repair_kind": kind, "evidence": evidence}
    return "learning_repair:" + _sha256_text(_canonical_json(seed))[:24]


def _base_repair(
    *,
    kind: str,
    priority: str,
    reason: str,
    evidence: dict[str, Any],
    runbook: list[str],
    rollback: list[str],
) -> dict[str, Any]:
    return {
        "repair_id": _repair_id(kind, evidence),
        "repair_kind": kind,
        "priority": priority,
        "reason": reason,
        "evidence": evidence,
        "budget_backpressure_gates": {
            "separate_runtime_apply_gate_required": True,
            "dry_run_required_before_apply": True,
            "single_writer_lock_required": True,
            "max_training_jobs_per_apply": 1,
            "max_apply_duration_minutes": 30,
            "skip_if_cron_or_previous_training_active": True,
            "abort_on_registry_or_artifact_parity_regression": True,
        },
        "operator_runbook": runbook,
        "rollback_plan": rollback,
        "allowed_actions": {
            "review_packet_allowed": True,
            "training_run_allowed_by_this_packet": False,
            "registry_write_allowed_by_this_packet": False,
            "onnx_export_allowed_by_this_packet": False,
            "artifact_delete_allowed_by_this_packet": False,
            "runtime_mutation_allowed_by_this_packet": False,
            "pg_write_allowed_by_this_packet": False,
            "serving_snapshot_allowed_by_this_packet": False,
            "promotion_allowed_by_this_packet": False,
        },
    }


def _maintenance_repair(component: dict[str, Any]) -> dict[str, Any] | None:
    if (
        component.get("fresh")
        and component.get("latest_ok")
        and component.get("last_two_cycles_ok")
    ):
        return None
    evidence = {
        "status": component.get("status"),
        "fresh": component.get("fresh"),
        "latest_ok": component.get("latest_ok"),
        "last_two_cycles_ok": component.get("last_two_cycles_ok"),
        "job_statuses": component.get("job_statuses") or {},
        "history_error": component.get("history_error"),
        "path": component.get("path"),
    }
    return _base_repair(
        kind="ML_TRAINING_MAINTENANCE_REPAIR_REQUIRED",
        priority="P0",
        reason="ml_training_maintenance_status_is_stale_error_or_lacks_two_ok_cycles",
        evidence=evidence,
        runbook=[
            "inspect_ml_training_maintenance_status_and_recent_log_without_rerun",
            "identify_first_error_job_and_missing_dependency_or_sample_gate",
            "prepare_single-job dry-run under lock for operator review",
            "only after separate runtime gate, run one bounded maintenance job and require two ok cycles",
        ],
        rollback=[
            "preserve_previous_status_json_and_status_log_before_apply",
            "restore_prior_status_pointer_if_new_cycle_errors",
            "do_not_touch_crontab_or_service_from_this_packet",
        ],
    )


def _registry_repair(component: dict[str, Any]) -> dict[str, Any] | None:
    ready = (
        component.get("read_error") is None
        and component.get("registry_status_ok")
        and component.get("fresh")
        and _int(component.get("registry_row_count")) > 0
        and _int(component.get("shadow_or_canary_row_count")) > 0
        and component.get("q10_q50_q90_trio_complete") is True
        and component.get("artifact_hash_parity_ok") is True
        and component.get("feature_schema_hash_present") is True
        and component.get("artifact_newer_than_registry") is not True
    )
    if ready:
        return None
    evidence = {
        "read_error": component.get("read_error"),
        "status": component.get("status"),
        "fresh": component.get("fresh"),
        "registry_row_count": component.get("registry_row_count"),
        "shadow_or_canary_row_count": component.get("shadow_or_canary_row_count"),
        "q10_q50_q90_trio_complete": component.get("q10_q50_q90_trio_complete"),
        "artifact_hash_parity_ok": component.get("artifact_hash_parity_ok"),
        "feature_schema_hash_present": component.get("feature_schema_hash_present"),
        "artifact_newer_than_registry": component.get("artifact_newer_than_registry"),
        "newest_artifact_mtime_utc": _dict(component.get("artifact_inventory")).get(
            "newest_artifact_mtime_utc"
        ),
        "latest_registry_row_utc": component.get("latest_registry_row_utc"),
        "path": component.get("path"),
    }
    return _base_repair(
        kind="MODEL_REGISTRY_REPAIR_REQUIRED",
        priority="P0",
        reason="model_registry_is_missing_stale_incomplete_or_behind_onnx_artifacts",
        evidence=evidence,
        runbook=[
            "inventory_q10_q50_q90_onnx_artifacts_and_acceptance_reports",
            "verify_feature_schema_hash_and_training_config_hash_before_registry_write",
            "prepare registry upsert dry-run with artifact sha parity checks",
            "only after separate PG/runtime gate, register complete shadow trio and re-run health snapshot",
        ],
        rollback=[
            "snapshot existing registry rows and artifact hashes before write",
            "retire_or_reject_only_new_shadow_rows_if_parity_regresses",
            "never rewrite promoting_or_production_slots_from_training_repair",
        ],
    )


def _parity_repair(component: dict[str, Any]) -> dict[str, Any] | None:
    if component.get("fresh") and component.get("parity_ok"):
        return None
    evidence = {
        "status": component.get("status"),
        "fresh": component.get("fresh"),
        "parity_ok": component.get("parity_ok"),
        "mismatch_count": component.get("mismatch_count"),
        "read_error": component.get("read_error"),
        "path": component.get("path"),
    }
    return _base_repair(
        kind="ARTIFACT_PARITY_REPAIR_REQUIRED",
        priority="P0",
        reason="artifact_pg_parity_snapshot_is_missing_stale_or_reports_mismatches",
        evidence=evidence,
        runbook=[
            "generate read-only artifact registry parity preview",
            "map mismatches to missing artifact_hash_missing_registry_or_stale_registry",
            "repair registry references only after separate PG write gate",
            "rerun parity snapshot before serving snapshot work",
        ],
        rollback=[
            "keep pre-repair parity snapshot as rollback evidence",
            "remove only newly introduced registry rows on failed parity review",
            "do_not_delete_model_artifacts_from_this_packet",
        ],
    )


def _legacy_retirement_repair(registry: dict[str, Any]) -> dict[str, Any] | None:
    inventory = _dict(registry.get("artifact_inventory"))
    artifact_count = _int(inventory.get("artifact_count"))
    needs_review = (
        registry.get("artifact_newer_than_registry") is True
        or (
            artifact_count > 0
            and (
                _int(registry.get("registry_row_count")) == 0
                or registry.get("q10_q50_q90_trio_complete") is not True
            )
        )
    )
    if not needs_review:
        return None
    evidence = {
        "artifact_count": artifact_count,
        "newest_artifact_mtime_utc": inventory.get("newest_artifact_mtime_utc"),
        "registry_row_count": registry.get("registry_row_count"),
        "q10_q50_q90_trio_complete": registry.get("q10_q50_q90_trio_complete"),
        "artifact_newer_than_registry": registry.get("artifact_newer_than_registry"),
    }
    return _base_repair(
        kind="LEGACY_MODEL_ARTIFACT_RETIREMENT_REVIEW_REQUIRED",
        priority="P1",
        reason="legacy_or_unregistered_model_artifacts_need_review_before_serving_snapshot",
        evidence=evidence,
        runbook=[
            "classify unregistered artifacts as candidate current stale or orphan",
            "preserve artifacts until registry parity and serving snapshot are green",
            "prepare retirement manifest with sha256 path and replacement registry row",
            "delete or relink artifacts only after separate operator-approved filesystem gate",
        ],
        rollback=[
            "archive retirement manifest and pre-delete sha inventory",
            "restore artifact paths or symlinks from manifest if serving check fails",
            "never retire artifacts that are production_or_promoting registry slots",
        ],
    )


def _generic_blocker_repair(blockers: list[str]) -> dict[str, Any] | None:
    known = {
        "ml_training_maintenance_status_stale_or_missing",
        "ml_training_maintenance_latest_not_ok",
        "ml_training_maintenance_last_two_cycles_not_ok",
        "model_registry_not_fresh_or_artifact_parity_failed",
        "artifact_pg_parity_snapshot_stale_or_missing",
        "artifact_pg_parity_not_ok",
    }
    unknown = [blocker for blocker in blockers if blocker not in known]
    if not unknown:
        return None
    evidence = {"unclassified_blockers": unknown}
    return _base_repair(
        kind="UNCLASSIFIED_LEARNING_HEALTH_BLOCKER_REVIEW_REQUIRED",
        priority="P1",
        reason="learning_health_snapshot_has_blockers_outside_training_registry_repair_scope",
        evidence=evidence,
        runbook=[
            "leave blocker in health SSOT until owning source contract exists",
            "do not clear unrelated blockers from training_registry_repair_packet",
        ],
        rollback=["no_runtime_action_was_taken_by_this_packet"],
    )


def _answer_flags(status: str) -> dict[str, Any]:
    ready = status in {READY_STATUS, NO_REPAIR_REQUIRED_STATUS}
    return {
        "training_registry_repair_packet_ready": ready,
        "source_only_review_packet": True,
        "requires_separate_runtime_apply_gate": True,
        "requires_separate_pg_write_gate": True,
        "budget_backpressure_gates_declared": True,
        "legacy_retirement_requires_separate_filesystem_gate": True,
        "training_run_allowed": False,
        "training_run_performed": False,
        "onnx_export_allowed": False,
        "onnx_export_performed": False,
        "registry_write_allowed": False,
        "registry_write_performed": False,
        "artifact_delete_allowed": False,
        "runtime_mutation_allowed": False,
        "runtime_mutation_performed": False,
        "env_mutation_performed": False,
        "service_restart_performed": False,
        "cron_mutation_performed": False,
        "pg_query_performed": False,
        "pg_write_performed": False,
        "bybit_call_performed": False,
        "order_authority_granted": False,
        "order_submission_performed": False,
        "cost_gate_change_allowed": False,
        "cost_gate_lowering_allowed": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "serving_snapshot_ready": False,
        "promotion_evidence": False,
        "promotion_proof": False,
        "live_authority_granted": False,
    }


def build_learning_training_registry_repair(
    *,
    learning_stack_health_snapshot: dict[str, Any] | None,
    learning_stack_health_snapshot_path: Path | None = None,
    learning_stack_health_snapshot_error: str | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build a no-authority repair packet from a learning health snapshot."""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    snapshot = _dict(learning_stack_health_snapshot)
    components = _dict(snapshot.get("components"))
    blockers = [_str(item) for item in _list(snapshot.get("blockers")) if _str(item)]
    authority_violations = _authority_violations(snapshot)
    snapshot_ready = (
        learning_stack_health_snapshot_error is None
        and snapshot.get("schema_version") == HEALTH_SCHEMA_VERSION
        and snapshot.get("status") in {HEALTH_READY_STATUS, HEALTH_DEGRADED_STATUS}
    )

    repair_items = [
        item
        for item in (
            _maintenance_repair(_dict(components.get("ml_training_maintenance"))),
            _registry_repair(_dict(components.get("model_registry"))),
            _parity_repair(_dict(components.get("artifact_pg_parity"))),
            _legacy_retirement_repair(_dict(components.get("model_registry"))),
            _generic_blocker_repair(blockers),
        )
        if item is not None
    ]

    if snapshot.get("status") == AUTHORITY_BOUNDARY_VIOLATION_STATUS or authority_violations:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "learning_health_snapshot_authority_boundary_violation"
        repair_items = []
    elif not snapshot_ready:
        status = INPUT_NOT_READY_STATUS
        reason = "learning_stack_health_snapshot_missing_not_ready_or_schema_invalid"
        repair_items = []
    elif not repair_items:
        status = NO_REPAIR_REQUIRED_STATUS
        reason = "training_registry_repair_not_required_by_snapshot"
    else:
        status = READY_STATUS
        reason = "training_registry_repair_packet_ready_review_only"

    repair_packet_sha256 = _sha256_text(
        _canonical_json(
            {
                "schema_version": SCHEMA_VERSION,
                "status": status,
                "repair_ids": [item.get("repair_id") for item in repair_items],
                "snapshot_sha256": snapshot.get("snapshot_sha256"),
                "blockers": blockers,
            }
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "repair_packet_sha256": repair_packet_sha256,
        "source_snapshot": {
            "path": str(learning_stack_health_snapshot_path)
            if learning_stack_health_snapshot_path
            else None,
            "schema_version": snapshot.get("schema_version"),
            "status": snapshot.get("status"),
            "source_error": learning_stack_health_snapshot_error,
            "blockers": blockers,
        },
        "summary": {
            "repair_item_count": len(repair_items),
            "maintenance_repair_required": any(
                item.get("repair_kind") == "ML_TRAINING_MAINTENANCE_REPAIR_REQUIRED"
                for item in repair_items
            ),
            "registry_repair_required": any(
                item.get("repair_kind") == "MODEL_REGISTRY_REPAIR_REQUIRED"
                for item in repair_items
            ),
            "artifact_parity_repair_required": any(
                item.get("repair_kind") == "ARTIFACT_PARITY_REPAIR_REQUIRED"
                for item in repair_items
            ),
            "legacy_retirement_review_required": any(
                item.get("repair_kind")
                == "LEGACY_MODEL_ARTIFACT_RETIREMENT_REVIEW_REQUIRED"
                for item in repair_items
            ),
            "authority_violation_count": len(authority_violations),
            "snapshot_blocker_count": len(blockers),
        },
        "repair_items": repair_items,
        "authority_violations": authority_violations,
        "answers": _answer_flags(status),
        "next_actions": (
            [
                "remove_authority_bearing_learning_health_snapshot_input",
                "operator_review_authority_boundary_violation_before_training_registry_repair",
            ]
            if status == AUTHORITY_BOUNDARY_VIOLATION_STATUS
            else [
                "review_training_registry_repair_packet_without_runtime_mutation",
                "prepare_separate_runtime_pg_apply_gate_for_selected_repair_item",
                "rerun_learning_stack_health_snapshot_after_any_approved_repair",
            ]
        ),
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("summary"))
    answers = _dict(packet.get("answers"))
    lines = [
        "# Cost Gate Learning Training/Registry Repair",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Repair items: `{summary.get('repair_item_count')}`",
        f"- Registry repair required: `{summary.get('registry_repair_required')}`",
        f"- Training run performed: `{answers.get('training_run_performed')}`",
        f"- Registry write performed: `{answers.get('registry_write_performed')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Repair Items",
        "",
        "| kind | priority | reason |",
        "|---|---|---|",
    ]
    for item in _list(packet.get("repair_items")):
        lines.append(
            f"| `{item.get('repair_kind')}` | `{item.get('priority')}` | "
            f"`{item.get('reason')}` |"
        )
    lines.extend(["", "## No-Authority Answers", ""])
    for key, value in answers.items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, "missing_path"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, f"{type(exc).__name__}:{exc}"
    if not isinstance(payload, dict):
        return None, "not_object"
    return payload, None


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--learning-stack-health-snapshot-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    snapshot, err = _read_json(args.learning_stack_health_snapshot_json)
    packet = build_learning_training_registry_repair(
        learning_stack_health_snapshot=snapshot,
        learning_stack_health_snapshot_path=args.learning_stack_health_snapshot_json,
        learning_stack_health_snapshot_error=err,
    )
    markdown = render_markdown(packet)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    elif not args.output and not args.json_output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
