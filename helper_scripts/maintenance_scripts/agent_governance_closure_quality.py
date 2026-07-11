"""Immutable, externally attested durable-closure follow-up contract.

This module deliberately has no telemetry producer.  It can schedule a
follow-up, validate an externally supplied observation, and aggregate only
measurements whose reference is trusted by the caller-provided attestation
index.  Missing telemetry stays unavailable; it is never represented by zero.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent_governance_schema import schema_subset_errors
from agent_governance_workflow_receipts import canonical_digest


REPO_ROOT = Path(__file__).resolve().parents[2]
FOLLOWUP_SCHEMA_PATH = REPO_ROOT / ".codex/schemas/closure_quality_followup_v1.schema.json"
ATTESTATION_SCHEMA_PATH = REPO_ROOT / ".codex/schemas/closure_quality_attestation_v1.schema.json"
FOLLOWUP_FIELDS = {
    "schema_version",
    "closure_digest",
    "closure_task_id",
    "closure_adjudicated_at",
    "followup_window",
    "created_at",
    "measurement_status",
    "observed_at",
    "attestation_ref",
    "attestation_digest",
    "unavailable_reason",
    "metrics",
    "record_digest",
}
ATTESTATION_FIELDS = {
    "schema_version",
    "trust_tier",
    "closure_digest",
    "followup_window",
    "observed_at",
    "producer",
    "metrics",
    "record_digest",
}
WINDOW_FIELDS = {"opens_at", "closes_at"}
METRIC_FIELDS = {
    "reopened",
    "false_closure",
    "rework_count",
    "accepted_decision_changing_findings",
    "realized_value_status",
}
REALIZED_VALUE_STATUSES = {
    "positive",
    "neutral",
    "negative",
    "not_realized",
    "indeterminate",
}
MEASUREMENT_STATUSES = {"scheduled", "unavailable", "measured"}


@lru_cache(maxsize=2)
def _load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _timestamp(value: Any, label: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label} must be a non-empty RFC3339 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{label} must be a valid RFC3339 timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{label} must include a timezone")
        return None
    return parsed


def _unsigned(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "record_digest"}


def _digest_or_error(value: Any, label: str, errors: list[str]) -> str | None:
    try:
        return canonical_digest(value)
    except (TypeError, ValueError):
        errors.append(f"{label} is not canonical JSON")
        return None


def closure_quality_followup_digest(record: dict[str, Any]) -> str:
    """Return the self-integrity digest without trusting an existing digest."""

    return canonical_digest(_unsigned(record))


def _closure_identity(
    closure: Any, errors: list[str]
) -> tuple[str | None, str | None, str | None]:
    if not isinstance(closure, dict):
        errors.append("closure must be an object")
        return None, None, None
    if closure.get("schema_version") != "closure_packet_v1":
        errors.append("closure schema_version must be closure_packet_v1")
    task_id = closure.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        errors.append("closure task_id must be non-empty")
        task_id = None
    adjudicated_at = closure.get("adjudicated_at")
    _timestamp(adjudicated_at, "closure adjudicated_at", errors)
    if not isinstance(adjudicated_at, str):
        adjudicated_at = None
    return _digest_or_error(closure, "closure", errors), task_id, adjudicated_at


def build_scheduled_closure_quality_followup(
    closure: dict[str, Any],
    *,
    opens_at: str,
    closes_at: str,
    created_at: str,
) -> dict[str, Any]:
    """Schedule an honest no-measurement-yet record for one exact closure."""

    errors: list[str] = []
    digest, task_id, adjudicated_at = _closure_identity(closure, errors)
    opens = _timestamp(opens_at, "followup_window.opens_at", errors)
    closes = _timestamp(closes_at, "followup_window.closes_at", errors)
    created = _timestamp(created_at, "created_at", errors)
    adjudicated = _timestamp(adjudicated_at, "closure adjudicated_at", [])
    if opens and closes and opens >= closes:
        errors.append("followup window opens_at must precede closes_at")
    if created and closes and created > closes:
        errors.append("created_at cannot be after the follow-up window")
    if adjudicated and created and adjudicated > created:
        errors.append("created_at cannot precede closure adjudication")
    if errors:
        raise ValueError("; ".join(errors))
    record: dict[str, Any] = {
        "schema_version": "closure_quality_followup_v1",
        "closure_digest": digest,
        "closure_task_id": task_id,
        "closure_adjudicated_at": adjudicated_at,
        "followup_window": {"opens_at": opens_at, "closes_at": closes_at},
        "created_at": created_at,
        "measurement_status": "scheduled",
        "observed_at": None,
        "attestation_ref": None,
        "attestation_digest": None,
        "unavailable_reason": None,
        "metrics": None,
    }
    record["record_digest"] = closure_quality_followup_digest(record)
    return record


def _validate_window(value: Any, errors: list[str]) -> tuple[datetime | None, datetime | None]:
    if not isinstance(value, dict):
        errors.append("followup_window must be an object")
        return None, None
    if set(value) != WINDOW_FIELDS:
        errors.append("followup_window fields differ from closure_quality_followup_v1")
    opens = _timestamp(value.get("opens_at"), "followup_window.opens_at", errors)
    closes = _timestamp(value.get("closes_at"), "followup_window.closes_at", errors)
    if opens and closes and opens >= closes:
        errors.append("followup window opens_at must precede closes_at")
    return opens, closes


def _validate_metrics(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("measured follow-up metrics must be an object")
        return
    if set(value) != METRIC_FIELDS:
        errors.append("measured follow-up metric fields differ from contract")
    for field in ("reopened", "false_closure"):
        if type(value.get(field)) is not bool:
            errors.append(f"metrics.{field} must be boolean")
    for field in ("rework_count", "accepted_decision_changing_findings"):
        metric = value.get(field)
        if type(metric) is not int or metric < 0:
            errors.append(f"metrics.{field} must be a non-negative integer")
    if value.get("realized_value_status") not in REALIZED_VALUE_STATUSES:
        errors.append("metrics.realized_value_status is invalid")


def _attestation_errors(
    record: dict[str, Any],
    attestation_index: Any,
) -> list[str]:
    errors: list[str] = []
    index = attestation_index if isinstance(attestation_index, dict) else {}
    trusted = index.get("platform_attested", [])
    trusted_refs = set(trusted) if isinstance(trusted, (list, set, tuple)) else set()
    reference = record.get("attestation_ref")
    if not isinstance(reference, str) or not reference or reference not in trusted_refs:
        errors.append("measured follow-up requires a platform/external-attested ref")
        return errors
    records = index.get("records", {})
    attestation = records.get(reference) if isinstance(records, dict) else None
    if not isinstance(attestation, dict):
        errors.append("attestation_ref has no indexed attestation record")
        return errors
    errors.extend(
        f"attestation schema: {error}"
        for error in schema_subset_errors(
            attestation,
            _load_schema(ATTESTATION_SCHEMA_PATH),
        )
    )
    if set(attestation) != ATTESTATION_FIELDS:
        errors.append("attestation fields differ from closure_quality_attestation_v1")
    if attestation.get("schema_version") != "closure_quality_attestation_v1":
        errors.append("attestation schema_version is invalid")
    if attestation.get("trust_tier") != "PLATFORM_OR_EXTERNAL_ATTESTED":
        errors.append("attestation trust_tier is not platform/external-attested")
    digest = attestation.get("record_digest")
    expected_digest = _digest_or_error(
        _unsigned(attestation), "attestation", errors
    )
    if digest != expected_digest:
        errors.append("attestation record_digest differs from canonical content")
    if record.get("attestation_digest") != digest:
        errors.append("follow-up attestation_digest differs from attestation")
    if attestation.get("closure_digest") != record.get("closure_digest"):
        errors.append("attestation closure digest differs from follow-up")
    if attestation.get("followup_window") != record.get("followup_window"):
        errors.append("follow-up window differs from attestation")
    if attestation.get("observed_at") != record.get("observed_at"):
        errors.append("observed_at differs from attestation")
    if attestation.get("metrics") != record.get("metrics"):
        errors.append("metrics differ from attestation")
    producer = attestation.get("producer")
    if not isinstance(producer, dict) or set(producer) != {"id", "kind"}:
        errors.append("attestation producer is invalid")
    elif (
        not isinstance(producer.get("id"), str)
        or not producer["id"]
        or producer.get("kind") not in {"platform", "external"}
    ):
        errors.append("attestation producer is invalid")
    return errors


def validate_closure_quality_followup(
    record: Any,
    closure: Any,
    *,
    attestation_index: Any = None,
) -> list[str]:
    """Validate one record without treating self-labels as attestation trust."""

    errors: list[str] = []
    if not isinstance(record, dict):
        return ["closure quality follow-up must be an object"]
    errors.extend(
        f"follow-up schema: {error}"
        for error in schema_subset_errors(record, _load_schema(FOLLOWUP_SCHEMA_PATH))
    )
    if set(record) != FOLLOWUP_FIELDS:
        errors.append("follow-up fields differ from closure_quality_followup_v1")
    if record.get("schema_version") != "closure_quality_followup_v1":
        errors.append("follow-up schema_version is invalid")
    closure_digest, task_id, adjudicated_at = _closure_identity(closure, errors)
    if record.get("closure_digest") != closure_digest:
        errors.append("closure digest differs from the immutable closure")
    if record.get("closure_task_id") != task_id:
        errors.append("closure task_id differs from the immutable closure")
    if record.get("closure_adjudicated_at") != adjudicated_at:
        errors.append("closure adjudicated_at differs from the immutable closure")
    opens, closes = _validate_window(record.get("followup_window"), errors)
    created = _timestamp(record.get("created_at"), "created_at", errors)
    adjudicated = _timestamp(adjudicated_at, "closure adjudicated_at", [])
    if adjudicated and created and adjudicated > created:
        errors.append("created_at cannot precede closure adjudication")
    if created and closes and created > closes:
        errors.append("created_at cannot be after the follow-up window")
    status = record.get("measurement_status")
    if status not in MEASUREMENT_STATUSES:
        errors.append("measurement_status is invalid")
    if status in {"scheduled", "unavailable"}:
        if any(
            record.get(field) is not None
            for field in ("metrics", "observed_at", "attestation_ref", "attestation_digest")
        ):
            errors.append("scheduled/unavailable follow-up cannot carry measured values")
        reason = record.get("unavailable_reason")
        if status == "scheduled" and reason is not None:
            errors.append("scheduled follow-up cannot claim unavailable_reason")
        if status == "unavailable" and (not isinstance(reason, str) or not reason):
            errors.append("unavailable follow-up requires unavailable_reason")
    elif status == "measured":
        if record.get("unavailable_reason") is not None:
            errors.append("measured follow-up cannot carry unavailable_reason")
        _validate_metrics(record.get("metrics"), errors)
        observed = _timestamp(record.get("observed_at"), "observed_at", errors)
        if observed and opens and observed < opens:
            errors.append("observed_at precedes the follow-up window")
        if observed and closes and observed > closes:
            errors.append("observed_at follows the follow-up window")
        errors.extend(_attestation_errors(record, attestation_index))
    expected_record_digest = _digest_or_error(
        _unsigned(record), "follow-up", errors
    )
    if record.get("record_digest") != expected_record_digest:
        errors.append("follow-up record_digest differs from canonical content")
    return errors


def summarize_closure_quality_followups(
    records: list[dict[str, Any]],
    closures_by_digest: dict[str, dict[str, Any]],
    *,
    attestation_index: Any = None,
) -> dict[str, Any]:
    """Aggregate only externally attested measurements for AI economics."""

    errors: list[str] = []
    measured: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not isinstance(records, list) or not isinstance(closures_by_digest, dict):
        return {
            "schema_version": "closure_quality_summary_v1",
            "measurement_status": "invalid",
            "metrics": None,
            "errors": ["records and closures_by_digest must be containers"],
        }
    for index, record in enumerate(records):
        digest = record.get("closure_digest") if isinstance(record, dict) else None
        closure = closures_by_digest.get(digest) if isinstance(digest, str) else None
        record_errors = validate_closure_quality_followup(
            record, closure, attestation_index=attestation_index
        )
        errors.extend(f"records[{index}]: {error}" for error in record_errors)
        if isinstance(digest, str):
            if digest in seen:
                errors.append(f"records[{index}]: duplicate closure_digest would double count durability")
            seen.add(digest)
        if isinstance(record, dict) and record.get("measurement_status") == "measured":
            measured.append(record)
    if errors:
        return {
            "schema_version": "closure_quality_summary_v1",
            "measurement_status": "invalid",
            "metrics": None,
            "errors": errors,
        }
    if not measured:
        return {
            "schema_version": "closure_quality_summary_v1",
            "measurement_status": "unavailable",
            "metrics": None,
            "unavailable_reason": (
                "no platform/external-attested closure-quality measurement is available"
            ),
            "cost_per_durable_closure_status": (
                "unavailable_without_attested_durability_and_cost"
            ),
        }
    counts = {status: 0 for status in sorted(REALIZED_VALUE_STATUSES)}
    for record in measured:
        counts[record["metrics"]["realized_value_status"]] += 1
    durable = sum(
        not record["metrics"]["reopened"] and not record["metrics"]["false_closure"]
        for record in measured
    )
    metrics = {
        "observed_closures": len(measured),
        "durable_closures": durable,
        "reopened_closures": sum(record["metrics"]["reopened"] for record in measured),
        "false_closures": sum(record["metrics"]["false_closure"] for record in measured),
        "rework_count": sum(record["metrics"]["rework_count"] for record in measured),
        "accepted_decision_changing_findings": sum(
            record["metrics"]["accepted_decision_changing_findings"]
            for record in measured
        ),
        "realized_value_status_counts": counts,
    }
    return {
        "schema_version": "closure_quality_summary_v1",
        "measurement_status": (
            "measured" if len(measured) == len(records) else "partial"
        ),
        "metrics": metrics,
        "durability_attestation_digests": sorted(
            record["attestation_digest"] for record in measured
        ),
        "cost_per_durable_closure_status": (
            "requires_separate_platform_attested_cost"
        ),
    }
