#!/usr/bin/env python3
"""Build a source-only learning model serving snapshot review packet.

This helper consumes training/registry repair, learning health, model-registry,
and optional runtime-serving state artifacts. It never loads a model, connects
to runtime, writes a registry row, edits services, or grants serving, order,
Cost Gate, live, or promotion authority.
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
from cost_gate_learning_lane.learning_training_registry_repair import (
    NO_REPAIR_REQUIRED_STATUS as REPAIR_NOT_REQUIRED_STATUS,
    READY_STATUS as REPAIR_REQUIRED_STATUS,
    SCHEMA_VERSION as REPAIR_SCHEMA_VERSION,
)


SCHEMA_VERSION = "cost_gate_learning_serving_snapshot_v1"
HEALTH_SCHEMA_VERSION = "learning_stack_health_snapshot_v1"
REGISTRY_SCHEMA_VERSION = "learning_model_registry_summary_v1"
RUNTIME_STATE_SCHEMA_VERSION = "learning_runtime_serving_state_v1"

READY_STATUS = "LEARNING_SERVING_SNAPSHOT_READY_FOR_OPERATOR_REVIEW_NO_AUTHORITY"
BLOCKED_BY_REPAIR_STATUS = (
    "LEARNING_SERVING_SNAPSHOT_BLOCKED_BY_TRAINING_REGISTRY_REPAIR_NO_AUTHORITY"
)
BLOCKED_BY_REGISTRY_STATUS = "LEARNING_SERVING_SNAPSHOT_BLOCKED_BY_REGISTRY_NO_AUTHORITY"
BLOCKED_BY_RUNTIME_STATUS = "LEARNING_SERVING_SNAPSHOT_BLOCKED_BY_RUNTIME_STATE_NO_AUTHORITY"
INPUT_NOT_READY_STATUS = "LEARNING_SERVING_SNAPSHOT_INPUT_NOT_READY"

BOUNDARY = (
    "artifact-only learning serving snapshot packet; no model load, no runtime "
    "service/env/cron mutation, no registry/PG query/write, no Bybit call, no "
    "order, no Cost Gate lowering, no serving authority, no probe/order/live "
    "authority, and no promotion proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "artifact_delete_performed",
    "bybit_call_performed",
    "canary_slot_promoted",
    "cost_gate_lowering_allowed",
    "env_mutation_performed",
    "global_cost_gate_lowering_recommended",
    "live_authority_granted",
    "ml_inference_hidden",
    "model_load_allowed",
    "model_load_allowed_by_this_packet",
    "model_load_performed",
    "order_authority_granted",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "production_slot_write_performed",
    "promotion_evidence",
    "promotion_proof",
    "registry_write_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "serving_authority_granted",
    "serving_snapshot_authority_granted",
    "serving_snapshot_ready",
    "training_run_performed",
}
AUTHORITY_TRUE_KEY_SUFFIXES = (
    "_allowed_by_this_packet",
)
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


def _sha256_payload(payload: Any) -> str:
    return _sha256_text(_canonical_json(payload))


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
            elif _is_authority_true_key(key) and _truthy_authority(value):
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


def _is_authority_true_key(key: str) -> bool:
    normalized = str(key or "").strip()
    return normalized in AUTHORITY_TRUE_KEYS or any(
        normalized.endswith(suffix) for suffix in AUTHORITY_TRUE_KEY_SUFFIXES
    )


def _source_ref(
    *,
    payload: dict[str, Any],
    path: Path | None,
    source_error: str | None,
) -> dict[str, Any]:
    return {
        "path": str(path) if path else None,
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "source_error": source_error,
        "sha256": _sha256_payload(payload) if payload else None,
    }


def _artifact_hashes(registry: dict[str, Any]) -> dict[str, str]:
    raw = _dict(registry.get("artifact_hashes"))
    hashes: dict[str, str] = {}
    for key in ("q10", "q50", "q90"):
        value = _str(raw.get(key) or registry.get(f"{key}_artifact_sha256"))
        if value:
            hashes[key] = value
    return hashes


def _feature_schema_hash(registry: dict[str, Any]) -> str:
    return _str(
        registry.get("feature_schema_hash")
        or registry.get("runtime_feature_schema_hash")
        or registry.get("feature_schema_sha256")
    )


def _intended_model_version(registry: dict[str, Any]) -> str:
    return _str(
        registry.get("intended_model_version")
        or registry.get("latest_model_version")
        or registry.get("model_version")
        or registry.get("registry_model_version")
    )


def _legacy_artifact_exclusion(registry: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "excluded_from_serving",
        "retired",
        "registry_current",
        "shadow_candidate",
        "canary_candidate",
        "production_current",
    }
    excluded: list[dict[str, Any]] = []
    blockers: list[str] = []
    for artifact in _list(registry.get("legacy_artifacts")):
        data = _dict(artifact)
        status = _str(data.get("status"))
        if status in {"excluded_from_serving", "retired"}:
            excluded.append(
                {
                    "path": data.get("path"),
                    "sha256": data.get("sha256"),
                    "status": status,
                }
            )
        elif status not in allowed:
            blockers.append(
                "legacy_artifact_not_explicitly_excluded_or_current:"
                + _str(data.get("path") or data.get("sha256") or "unknown")
            )
    return {
        "excluded_legacy_artifacts": excluded,
        "blockers": blockers,
        "stale_or_legacy_artifacts_excluded_from_serving": not blockers,
        "retirement_requires_separate_filesystem_gate": True,
    }


def _registry_gate(
    *,
    health_snapshot: dict[str, Any],
    registry_summary: dict[str, Any],
    registry_summary_error: str | None,
) -> dict[str, Any]:
    health_registry = _dict(_dict(health_snapshot.get("components")).get("model_registry"))
    artifact_hashes = _artifact_hashes(registry_summary)
    feature_hash = _feature_schema_hash(registry_summary)
    model_version = _intended_model_version(registry_summary)
    legacy = _legacy_artifact_exclusion(registry_summary)
    blockers: list[str] = []

    if registry_summary_error:
        blockers.append(f"model_registry_summary:{registry_summary_error}")
    if registry_summary.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        blockers.append("model_registry_summary_schema_invalid")
    if registry_summary.get("status") not in {"ok", "OK", "ready", "READY"}:
        blockers.append("model_registry_summary_status_not_ok")
    if _int(registry_summary.get("registry_row_count")) <= 0:
        blockers.append("model_registry_row_missing")
    if _int(registry_summary.get("shadow_or_canary_row_count")) <= 0:
        blockers.append("shadow_or_canary_registry_row_missing")
    if registry_summary.get("q10_q50_q90_trio_complete") is not True:
        blockers.append("q10_q50_q90_trio_incomplete")
    if registry_summary.get("artifact_hash_parity_ok") is not True:
        blockers.append("artifact_hash_parity_not_ok")
    if not feature_hash:
        blockers.append("feature_schema_hash_missing")
    if set(artifact_hashes) != {"q10", "q50", "q90"}:
        blockers.append("q10_q50_q90_artifact_hashes_missing")
    if not model_version:
        blockers.append("intended_model_version_missing")
    if health_registry.get("artifact_newer_than_registry") is True:
        blockers.append("onnx_artifact_newer_than_registry")
    if health_registry.get("feature_schema_hash_present") is not True:
        blockers.append("health_snapshot_feature_schema_hash_missing")
    if health_registry.get("artifact_hash_parity_ok") is not True:
        blockers.append("health_snapshot_artifact_hash_parity_not_ok")
    if health_registry.get("q10_q50_q90_trio_complete") is not True:
        blockers.append("health_snapshot_q10_q50_q90_trio_incomplete")
    blockers.extend(legacy["blockers"])

    return {
        "ready": not blockers,
        "blockers": blockers,
        "model_version": model_version,
        "feature_schema_hash": feature_hash,
        "artifact_hashes": artifact_hashes,
        "legacy_artifact_exclusion": legacy,
        "health_registry_status": health_registry.get("status"),
        "registry_row_count": registry_summary.get("registry_row_count"),
        "shadow_or_canary_row_count": registry_summary.get("shadow_or_canary_row_count"),
    }


def _runtime_gate(
    *,
    runtime_state: dict[str, Any],
    runtime_state_error: str | None,
    registry_gate: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    fallback_active = runtime_state.get("fallback_mode_active") is True
    fallback_visible = (
        fallback_active
        and bool(_str(runtime_state.get("fallback_reason")))
        and runtime_state.get("fallback_rule_based_visible") is True
    )
    registry_version = _str(registry_gate.get("model_version"))
    registry_feature_hash = _str(registry_gate.get("feature_schema_hash"))
    loaded_version = _str(runtime_state.get("loaded_model_version"))
    runtime_feature_hash = _str(runtime_state.get("runtime_feature_schema_hash"))
    loaded_hashes = _dict(runtime_state.get("loaded_artifact_hashes"))
    registry_hashes = _dict(registry_gate.get("artifact_hashes"))

    if runtime_state_error:
        blockers.append(f"runtime_serving_state:{runtime_state_error}")
    if runtime_state.get("schema_version") != RUNTIME_STATE_SCHEMA_VERSION:
        blockers.append("runtime_serving_state_schema_invalid")
    if runtime_state.get("status") not in {
        "RUNTIME_SERVING_STATE_READY",
        "RUNTIME_SERVING_STATE_FALLBACK_VISIBLE",
    }:
        blockers.append("runtime_serving_state_status_not_ready")
    if not fallback_active and loaded_version != registry_version:
        blockers.append("runtime_loaded_version_does_not_match_registry_intent")
    if fallback_active and not fallback_visible:
        blockers.append("runtime_fallback_not_explicitly_visible")
    if fallback_active and runtime_state.get("ml_inference_active") is True:
        blockers.append("runtime_fallback_hides_active_ml_inference")
    if not fallback_active and runtime_feature_hash != registry_feature_hash:
        blockers.append("runtime_feature_schema_hash_mismatch")
    if not fallback_active:
        for key, value in registry_hashes.items():
            if _str(loaded_hashes.get(key)) != _str(value):
                blockers.append(f"runtime_loaded_artifact_hash_mismatch:{key}")

    agreement = "blocked"
    if not blockers and fallback_visible:
        agreement = "explicit_fallback_visible"
    elif not blockers:
        agreement = "runtime_loaded_registry_intent"

    return {
        "ready": not blockers,
        "blockers": blockers,
        "agreement": agreement,
        "loaded_model_version": loaded_version or None,
        "registry_intent_model_version": registry_version or None,
        "runtime_feature_schema_hash": runtime_feature_hash or None,
        "fallback_mode_active": fallback_active,
        "fallback_reason": runtime_state.get("fallback_reason"),
        "fallback_rule_based_visible": runtime_state.get("fallback_rule_based_visible"),
        "ml_inference_active": runtime_state.get("ml_inference_active"),
    }


def _serving_slot_constraints(registry_summary: dict[str, Any]) -> dict[str, Any]:
    intent = _dict(registry_summary.get("serving_intent"))
    return {
        "registry_intent": intent,
        "shadow_slot_required_before_canary": True,
        "canary_requires_shadow_parity": True,
        "production_requires_separate_promotion_gate": True,
        "production_slot_write_allowed_by_this_packet": False,
        "canary_slot_write_allowed_by_this_packet": False,
        "shadow_slot_write_allowed_by_this_packet": False,
        "stale_or_legacy_artifacts_must_be_excluded": True,
    }


def _answer_flags(status: str) -> dict[str, Any]:
    return {
        "serving_snapshot_candidate_emitted": status == READY_STATUS,
        "source_only_review_packet": True,
        "requires_separate_runtime_serving_gate": True,
        "requires_separate_model_load_gate": True,
        "requires_separate_registry_write_gate": True,
        "model_load_allowed_by_this_packet": False,
        "model_load_performed": False,
        "serving_authority_granted": False,
        "serving_snapshot_authority_granted": False,
        "runtime_mutation_allowed": False,
        "runtime_mutation_performed": False,
        "env_mutation_performed": False,
        "service_restart_performed": False,
        "cron_mutation_performed": False,
        "registry_write_allowed": False,
        "registry_write_performed": False,
        "pg_query_performed": False,
        "pg_write_performed": False,
        "bybit_call_performed": False,
        "order_authority_granted": False,
        "order_submission_performed": False,
        "cost_gate_change_allowed": False,
        "cost_gate_lowering_allowed": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "promotion_evidence": False,
        "promotion_proof": False,
        "live_authority_granted": False,
    }


def _snapshot_id(registry_gate: dict[str, Any], runtime_gate: dict[str, Any]) -> str:
    seed = {
        "schema_version": SCHEMA_VERSION,
        "model_version": registry_gate.get("model_version"),
        "feature_schema_hash": registry_gate.get("feature_schema_hash"),
        "artifact_hashes": registry_gate.get("artifact_hashes"),
        "runtime_agreement": runtime_gate.get("agreement"),
        "loaded_model_version": runtime_gate.get("loaded_model_version"),
    }
    return "learning_serving_snapshot:" + _sha256_payload(seed)[:24]


def build_learning_serving_snapshot(
    *,
    training_registry_repair_packet: dict[str, Any] | None,
    learning_stack_health_snapshot: dict[str, Any] | None,
    model_registry_summary: dict[str, Any] | None,
    runtime_serving_state: dict[str, Any] | None = None,
    training_registry_repair_packet_path: Path | None = None,
    learning_stack_health_snapshot_path: Path | None = None,
    model_registry_summary_path: Path | None = None,
    runtime_serving_state_path: Path | None = None,
    training_registry_repair_packet_error: str | None = None,
    learning_stack_health_snapshot_error: str | None = None,
    model_registry_summary_error: str | None = None,
    runtime_serving_state_error: str | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build an immutable no-authority serving snapshot review packet."""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    repair = _dict(training_registry_repair_packet)
    health = _dict(learning_stack_health_snapshot)
    registry = _dict(model_registry_summary)
    runtime = _dict(runtime_serving_state)
    authority_violations = []
    for payload in (repair, health, registry, runtime):
        authority_violations.extend(_authority_violations(payload))

    input_blockers: list[str] = []
    if training_registry_repair_packet_error:
        input_blockers.append(f"training_registry_repair_packet:{training_registry_repair_packet_error}")
    if learning_stack_health_snapshot_error:
        input_blockers.append(f"learning_stack_health_snapshot:{learning_stack_health_snapshot_error}")
    if repair.get("schema_version") != REPAIR_SCHEMA_VERSION:
        input_blockers.append("training_registry_repair_schema_invalid")
    if health.get("schema_version") != HEALTH_SCHEMA_VERSION:
        input_blockers.append("learning_stack_health_schema_invalid")

    registry_gate = _registry_gate(
        health_snapshot=health,
        registry_summary=registry,
        registry_summary_error=model_registry_summary_error,
    )
    runtime_gate = _runtime_gate(
        runtime_state=runtime,
        runtime_state_error=runtime_serving_state_error,
        registry_gate=registry_gate,
    )

    repair_items = _list(repair.get("repair_items"))
    if repair.get("status") == AUTHORITY_BOUNDARY_VIOLATION_STATUS or authority_violations:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "serving_snapshot_input_authority_boundary_violation"
    elif input_blockers:
        status = INPUT_NOT_READY_STATUS
        reason = "serving_snapshot_required_inputs_missing_or_schema_invalid"
    elif repair.get("status") == REPAIR_REQUIRED_STATUS or repair_items:
        status = BLOCKED_BY_REPAIR_STATUS
        reason = "training_registry_repairs_must_close_before_serving_snapshot"
    elif repair.get("status") != REPAIR_NOT_REQUIRED_STATUS:
        status = INPUT_NOT_READY_STATUS
        reason = "training_registry_repair_packet_not_in_no_repair_required_state"
    elif not registry_gate["ready"]:
        status = BLOCKED_BY_REGISTRY_STATUS
        reason = "model_registry_or_artifact_health_not_ready_for_serving_snapshot"
    elif not runtime_gate["ready"]:
        status = BLOCKED_BY_RUNTIME_STATUS
        reason = "runtime_serving_state_not_aligned_or_fallback_not_visible"
    else:
        status = READY_STATUS
        reason = "serving_snapshot_candidate_ready_for_operator_review"

    snapshot_candidate: dict[str, Any] | None = None
    if status == READY_STATUS:
        snapshot_candidate = {
            "snapshot_id": _snapshot_id(registry_gate, runtime_gate),
            "immutable": True,
            "model_version": registry_gate.get("model_version"),
            "runtime_agreement": runtime_gate.get("agreement"),
            "artifact_hashes": registry_gate.get("artifact_hashes"),
            "feature_schema_hash": registry_gate.get("feature_schema_hash"),
            "runtime_feature_schema_hash": runtime_gate.get("runtime_feature_schema_hash"),
            "loaded_model_version": runtime_gate.get("loaded_model_version"),
            "fallback_mode_active": runtime_gate.get("fallback_mode_active"),
            "fallback_reason": runtime_gate.get("fallback_reason"),
            "serving_slot_constraints": _serving_slot_constraints(registry),
            "legacy_artifact_exclusion": registry_gate.get("legacy_artifact_exclusion"),
            "allowed_actions": {
                "operator_review_allowed": True,
                "model_load_allowed_by_this_packet": False,
                "runtime_mutation_allowed_by_this_packet": False,
                "registry_write_allowed_by_this_packet": False,
                "pg_write_allowed_by_this_packet": False,
                "production_slot_write_allowed_by_this_packet": False,
                "promotion_allowed_by_this_packet": False,
            },
        }

    blocked_snapshot = {
        "candidate_emitted": snapshot_candidate is not None,
        "input_blockers": input_blockers,
        "repair_blockers": [
            item.get("repair_kind") for item in repair_items if isinstance(item, dict)
        ],
        "registry_blockers": registry_gate.get("blockers"),
        "runtime_blockers": runtime_gate.get("blockers"),
    }
    packet_sha = _sha256_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "snapshot_candidate": snapshot_candidate,
            "blocked_snapshot": blocked_snapshot,
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "serving_snapshot_packet_sha256": packet_sha,
        "source_refs": {
            "training_registry_repair_packet": _source_ref(
                payload=repair,
                path=training_registry_repair_packet_path,
                source_error=training_registry_repair_packet_error,
            ),
            "learning_stack_health_snapshot": _source_ref(
                payload=health,
                path=learning_stack_health_snapshot_path,
                source_error=learning_stack_health_snapshot_error,
            ),
            "model_registry_summary": _source_ref(
                payload=registry,
                path=model_registry_summary_path,
                source_error=model_registry_summary_error,
            ),
            "runtime_serving_state": _source_ref(
                payload=runtime,
                path=runtime_serving_state_path,
                source_error=runtime_serving_state_error,
            ),
        },
        "summary": {
            "candidate_emitted": snapshot_candidate is not None,
            "runtime_agreement": runtime_gate.get("agreement"),
            "registry_ready": registry_gate.get("ready"),
            "runtime_ready": runtime_gate.get("ready"),
            "repair_item_count": len(repair_items),
            "authority_violation_count": len(authority_violations),
        },
        "registry_gate": registry_gate,
        "runtime_gate": runtime_gate,
        "serving_snapshot_candidate": snapshot_candidate,
        "blocked_snapshot": blocked_snapshot,
        "authority_violations": authority_violations,
        "answers": _answer_flags(status),
        "next_actions": _next_actions(status),
        "boundary": BOUNDARY,
    }


def _next_actions(status: str) -> list[str]:
    if status == AUTHORITY_BOUNDARY_VIOLATION_STATUS:
        return [
            "remove_authority_bearing_serving_snapshot_input",
            "rerun_source_only_serving_snapshot_after_clean_inputs",
        ]
    if status == BLOCKED_BY_REPAIR_STATUS:
        return [
            "complete_training_registry_repair_under_separate_runtime_or_pg_gate",
            "rerun_learning_stack_health_snapshot_and_training_registry_repair_packet",
        ]
    if status == BLOCKED_BY_REGISTRY_STATUS:
        return [
            "repair_model_registry_artifact_parity_feature_schema_or_legacy_exclusion",
            "rerun_serving_snapshot_with_fresh_model_registry_summary",
        ]
    if status == BLOCKED_BY_RUNTIME_STATUS:
        return [
            "produce_reviewed_runtime_serving_state_artifact_without_using_this_packet_as_model_load_authority",
            "ensure_loaded_version_matches_registry_or_explicit_fallback_is_visible",
        ]
    if status == READY_STATUS:
        return [
            "operator_review_serving_snapshot_packet_before_any_runtime_apply",
            "open_separate_runtime_model_load_or_fallback_review_if_serving_change_is_needed",
        ]
    return ["provide_valid_training_registry_repair_health_and_registry_artifacts"]


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("summary"))
    answers = _dict(packet.get("answers"))
    candidate = _dict(packet.get("serving_snapshot_candidate"))
    lines = [
        "# Cost Gate Learning Serving Snapshot",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate emitted: `{summary.get('candidate_emitted')}`",
        f"- Runtime agreement: `{summary.get('runtime_agreement')}`",
        f"- Snapshot id: `{candidate.get('snapshot_id')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Blockers",
        "",
    ]
    blocked = _dict(packet.get("blocked_snapshot"))
    for key in ("input_blockers", "repair_blockers", "registry_blockers", "runtime_blockers"):
        lines.append(f"- `{key}`: `{_list(blocked.get(key))}`")
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
    parser.add_argument("--training-registry-repair-json", type=Path, required=True)
    parser.add_argument("--learning-stack-health-snapshot-json", type=Path, required=True)
    parser.add_argument("--model-registry-summary-json", type=Path, required=True)
    parser.add_argument("--runtime-serving-state-json", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    repair, repair_error = _read_json(args.training_registry_repair_json)
    health, health_error = _read_json(args.learning_stack_health_snapshot_json)
    registry, registry_error = _read_json(args.model_registry_summary_json)
    runtime, runtime_error = _read_json(args.runtime_serving_state_json)
    packet = build_learning_serving_snapshot(
        training_registry_repair_packet=repair,
        learning_stack_health_snapshot=health,
        model_registry_summary=registry,
        runtime_serving_state=runtime,
        training_registry_repair_packet_path=args.training_registry_repair_json,
        learning_stack_health_snapshot_path=args.learning_stack_health_snapshot_json,
        model_registry_summary_path=args.model_registry_summary_json,
        runtime_serving_state_path=args.runtime_serving_state_json,
        training_registry_repair_packet_error=repair_error,
        learning_stack_health_snapshot_error=health_error,
        model_registry_summary_error=registry_error,
        runtime_serving_state_error=runtime_error,
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
