"""
MODULE_NOTE
模塊用途：把既有 mlde_demo_applier `_record_application(...)` 寫入參數
映射成 `demo_mutation_envelope_v1` audit envelope。
依賴：僅 Python 標準庫與 sibling source-only envelope contract；不讀 DB、
不呼叫 IPC、不接觸 exchange/provider/secret，也不執行 rollback。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from ml_training.demo_mutation_envelope import (
    DEMO_MUTATION_ENVELOPE_FIELD,
    build_demo_mutation_envelope,
    stable_sha256_json,
    validate_demo_mutation_envelope,
)


_MAPPING_SCHEMA_VERSION = "demo_mutation_envelope_applier_mapping_v1"
_DEFAULT_MAX_DELTA_POLICY = {
    "policy_id": "mlde_demo_applier_existing_patch_bounds_source_mapping_v1",
    "source": "mlde_demo_applier_patch_calculation",
    "max_delta_pct": None,
    "source_only_mapping": True,
}


def map_record_application_to_demo_mutation_envelope(
    *,
    row: Mapping[str, Any],
    application_type: str,
    target_name: str,
    patch: Mapping[str, Any],
    prev_snapshot: Mapping[str, Any],
    ipc_response: Mapping[str, Any],
    status: str,
    reason: str,
    requires_governance: bool,
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Pure mapping from `_record_application` inputs to an audit envelope."""
    payload_map = _mapping(payload)
    source_payload = _source_payload(payload_map)
    source_payload_hash = _stable_hash(source_payload)
    ipc_response_hash = _stable_hash(ipc_response)
    engine_mode = str(row.get("engine_mode") or "")
    application_status = str(status or "")

    envelope = build_demo_mutation_envelope(
        source_proposal_or_recommendation_id=_source_id(
            row=row,
            application_type=application_type,
            target_name=target_name,
            status=application_status,
            reason=reason,
            source_payload_hash=source_payload_hash,
        ),
        source_payload_hash=source_payload_hash,
        application_type=str(application_type),
        target=str(target_name),
        previous_snapshot=dict(prev_snapshot or {}),
        proposed_patch=dict(patch or {}),
        max_delta_policy=_max_delta_policy(payload_map),
        governance_verdict=_governance_verdict(
            payload_map,
            requires_governance=requires_governance,
            status=application_status,
        ),
        rollback_handle=_rollback_handle(
            payload_map,
            row=row,
            application_type=application_type,
            target_name=target_name,
            status=application_status,
            reason=reason,
            prev_snapshot=prev_snapshot,
        ),
        ipc_response_status=_ipc_status(application_status, ipc_response),
        ipc_response_hash=ipc_response_hash,
        post_change_review=_optional_mapping(payload_map, "post_change_review"),
        proof_linkage=_optional_mapping(payload_map, "proof_linkage"),
        application_status=application_status,
        dedupe=_is_dedupe(application_status, reason, payload_map),
        dry_run=_is_dry_run(application_status, ipc_response),
        engine_mode=engine_mode,
    )
    # Keep validation local and side-effect-free; callers/tests can inspect the
    # canonical envelope while runtime INSERT behavior remains unchanged.
    validate_demo_mutation_envelope(envelope)
    return envelope


def attach_demo_mutation_envelope_to_payload(
    *,
    row: Mapping[str, Any],
    application_type: str,
    target_name: str,
    patch: Mapping[str, Any],
    prev_snapshot: Mapping[str, Any],
    ipc_response: Mapping[str, Any],
    status: str,
    reason: str,
    requires_governance: bool,
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return a payload copy with canonical `demo_mutation_envelope` attached."""
    out = dict(payload or {})
    out[DEMO_MUTATION_ENVELOPE_FIELD] = map_record_application_to_demo_mutation_envelope(
        row=row,
        application_type=application_type,
        target_name=target_name,
        patch=patch,
        prev_snapshot=prev_snapshot,
        ipc_response=ipc_response,
        status=status,
        reason=reason,
        requires_governance=requires_governance,
        payload=payload,
    )
    return out


def _source_id(
    *,
    row: Mapping[str, Any],
    application_type: str,
    target_name: str,
    status: str,
    reason: str,
    source_payload_hash: str,
) -> str:
    row_id = row.get("id")
    if row_id not in (None, ""):
        return str(row_id)
    seed = {
        "mapping_schema_version": _MAPPING_SCHEMA_VERSION,
        "engine_mode": row.get("engine_mode"),
        "application_type": application_type,
        "target_name": target_name,
        "status": status,
        "reason": reason,
        "source_payload_hash": source_payload_hash,
    }
    return "audit:" + _stable_hash(seed)[:24]


def _source_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    source_payload = payload.get("source_payload")
    if isinstance(source_payload, Mapping):
        return source_payload
    return {
        key: value
        for key, value in payload.items()
        if key != DEMO_MUTATION_ENVELOPE_FIELD
    }


def _governance_verdict(
    payload: Mapping[str, Any],
    *,
    requires_governance: bool,
    status: str,
) -> dict[str, Any]:
    explicit = _optional_mapping(payload, "governance_verdict")
    if explicit:
        return dict(explicit)
    review_required = bool(requires_governance or status == "applied")
    return {
        "mapping_schema_version": _MAPPING_SCHEMA_VERSION,
        "requires_governance": bool(requires_governance),
        "review_required": review_required,
        "review_satisfied": False,
        "verdict": "review_required_not_satisfied",
        "reason": "downstream_post_change_review_and_proof_not_present",
    }


def _rollback_handle(
    payload: Mapping[str, Any],
    *,
    row: Mapping[str, Any],
    application_type: str,
    target_name: str,
    status: str,
    reason: str,
    prev_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    explicit = _optional_mapping(payload, "rollback_handle")
    if explicit:
        return dict(explicit)
    snapshot_hash = _stable_hash(prev_snapshot)
    seed = {
        "mapping_schema_version": _MAPPING_SCHEMA_VERSION,
        "engine_mode": row.get("engine_mode"),
        "recommendation_id": row.get("id"),
        "application_type": application_type,
        "target_name": target_name,
        "status": status,
        "reason": reason,
        "prev_snapshot_hash": snapshot_hash,
    }
    return {
        "mapping_schema_version": _MAPPING_SCHEMA_VERSION,
        "handle_id": "audit_rollback:" + _stable_hash(seed)[:24],
        "snapshot_hash": snapshot_hash,
        "target_name": str(target_name),
        "application_type": str(application_type),
        "status": str(status),
        "source_recommendation_id": row.get("id"),
        "source_only_mapping": True,
        "rollback_not_implemented": True,
        "available": False,
    }


def _max_delta_policy(payload: Mapping[str, Any]) -> dict[str, Any]:
    explicit = _optional_mapping(payload, "max_delta_policy")
    if explicit:
        return dict(explicit)
    explicit = _optional_mapping(payload, "demo_mutation_max_delta_policy")
    if explicit:
        return dict(explicit)
    return dict(_DEFAULT_MAX_DELTA_POLICY)


def _ipc_status(status: str, ipc_response: Mapping[str, Any]) -> str:
    raw_status = str(ipc_response.get("status") or "").strip().lower()
    if raw_status:
        return raw_status
    if ipc_response.get("ok") is True or ipc_response.get("accepted") is True:
        return "ok"
    if status == "applied":
        return "applied"
    if status == "dry_run":
        return "dry_run"
    return str(status or "").strip().lower()


def _is_dry_run(status: str, ipc_response: Mapping[str, Any]) -> bool:
    return status == "dry_run" or ipc_response.get("dry_run") is True


def _is_dedupe(status: str, reason: str, payload: Mapping[str, Any]) -> bool:
    if str(reason or "").strip().lower() == "dedupe":
        return True
    if payload.get("dedupe") is True:
        return True
    return status == "skipped" and "dedupe" in str(reason or "").strip().lower()


def _optional_mapping(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _stable_hash(value: Any) -> str:
    try:
        return stable_sha256_json(value)
    except (TypeError, ValueError):
        return hashlib.sha256(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                default=repr,
            ).encode("utf-8")
        ).hexdigest()


__all__ = [
    "attach_demo_mutation_envelope_to_payload",
    "map_record_application_to_demo_mutation_envelope",
]
