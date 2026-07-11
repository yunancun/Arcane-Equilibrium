"""Canonical workflow receipts bind calls/order, not provider identity or telemetry."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from agent_governance_registry import load_registry
from agent_governance_workflow_identity import (
    REQUESTED_FIELDS,
    requested_identity_errors,
    requested_logical_role,
    requested_native_agent,
)
from agent_governance_workflow_budget import workflow_budget_errors
from agent_governance_execution_dag import (
    execution_dag_digest,
    topological_waves,
    validate_call_dag_fields,
    validate_wave_dag_order,
)
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$")
CALL_FIELDS = {
    "schema_version", "workflow_contract_digest", "logical_call_id",
    "node_id", "payload_kind", "attempt", "retry_parent_call_id", "phase",
    "label", "requested", "prompt_digest", "context_artifact_digest",
    "dag_digest", "requires", "topological_wave", "producer_generation",
    "task_contract_digest", "dirty_scope_digest", "focus_digest",
    "compiler_input_tokens_lower_bound", "admitted_input_tokens_lower_bound",
    "response_schema_digest", "started_at", "ended_at", "returned_null",
    "parsed_result_digest", "record_digest",
}
MANIFEST_FIELDS = {
    "schema_version", "workflow_contract_digest", "records", "manifest_digest",
}
WAVE_FIELDS = {
    "schema_version", "workflow_contract_digest", "context_artifact_digests",
    "dag_digest", "execution_waves",
    "compiler_planned_input_tokens_lower_bound",
    "admitted_planned_input_tokens_lower_bound",
    "scheduled_call_compiler_input_tokens_lower_bound",
    "scheduled_call_admitted_input_tokens_lower_bound", "admitted_tasks",
    "call_manifest_digest", "call_record_digests", "first_attempt_call_count",
    "retry_call_count", "null_call_count", "final_null_node_count",
    "coverage_debt", "budget_authority", "result_fragment_digests",
    "accounting_boundary", "record_digest",
}
ADMITTED_TASK_FIELDS = {
    "node_id", "role", "native_agent", "requires", "node_class", "permission", "payload_kind", "task_contract_digest",
    "context_artifact_digest", "description_digest", "base_prompt_digest",
    "requested", "dirty_scope", "dirty_scope_digest", "focus", "focus_digest",
    "compiler_estimated_input_tokens", "admitted_input_tokens_lower_bound",
}
ACCOUNTING_BOUNDARY_FIELDS = {
    "usage_measurement_status", "controller_overhead_status",
    "excluded_from_token_lower_bounds",
}
COVERAGE_DEBT_FIELDS = {"node", "reason", "disposition"}
JUDGMENT_FIELDS = {
    "work_status", "gate_verdict", "classification", "confidence", "summary",
    "evidence_refs", "concerns", "next_action", "payload",
}
PRODUCER_FIELDS = {
    "context_artifact_digest", "producer_record_kind", "producer_call_ref",
    "producer_call_receipt_digest",
}
NULL_DIGEST = "sha256:" + hashlib.sha256(b"null").hexdigest()

def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _unsigned_digest(record: dict[str, Any], digest_field: str) -> str:
    return canonical_digest(
        {key: value for key, value in record.items() if key != digest_field}
    )


def _identifier_error(value: Any, label: str) -> str | None:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        return f"{label} is invalid"
    return None


def _timestamp(value: Any, label: str) -> tuple[datetime | None, str | None]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return parsed, None
    except (TypeError, ValueError):
        return None, f"{label} must be a timezone-aware timestamp"


def _nonnegative_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def build_controller_workflow_call_record(
    *,
    workflow_contract_digest: str,
    logical_call_id: str,
    node_id: str,
    payload_kind: str,
    attempt: int,
    retry_parent_call_id: str | None,
    phase: str,
    label: str,
    requested: dict[str, Any],
    prompt_digest: str,
    context_artifact_digest: str,
    task_contract_digest: str,
    dirty_scope_digest: str,
    focus_digest: str,
    compiler_input_tokens_lower_bound: int,
    admitted_input_tokens_lower_bound: int,
    response_schema_digest: str,
    started_at: str,
    ended_at: str,
    returned_null: bool,
    parsed_result_digest: str,
    dag_digest: str | None = None,
    requires: list[str] | None = None,
    topological_wave: int = 0,
    producer_generation: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the canonical structural call record used by every workflow.

    The self-digest binds fields but is not proof that a provider call occurred;
    closure authenticates the enclosing wave through a trusted-host capability.
    """

    requested = dict(requested)
    requires = [] if requires is None else requires
    producer_generation = {} if producer_generation is None else producer_generation
    dag_digest = dag_digest or execution_dag_digest([
        {
            "node_id": node_id,
            "role": requested_logical_role(requested),
            "native_agent": requested_native_agent(requested),
            "requires": requires,
            "node_class": requested["node_class"],
            "permission": requested["permission"],
        }
    ])
    record: dict[str, Any] = {
        "schema_version": "workflow_call_record_v1",
        "workflow_contract_digest": workflow_contract_digest,
        "logical_call_id": logical_call_id,
        "node_id": node_id,
        "payload_kind": payload_kind,
        "attempt": attempt,
        "retry_parent_call_id": retry_parent_call_id,
        "phase": phase,
        "label": label,
        "requested": requested,
        "dag_digest": dag_digest,
        "requires": requires,
        "topological_wave": topological_wave,
        "producer_generation": producer_generation,
        "prompt_digest": prompt_digest,
        "context_artifact_digest": context_artifact_digest,
        "task_contract_digest": task_contract_digest,
        "dirty_scope_digest": dirty_scope_digest,
        "focus_digest": focus_digest,
        "compiler_input_tokens_lower_bound": compiler_input_tokens_lower_bound,
        "admitted_input_tokens_lower_bound": admitted_input_tokens_lower_bound,
        "response_schema_digest": response_schema_digest,
        "started_at": started_at,
        "ended_at": ended_at,
        "returned_null": returned_null,
        "parsed_result_digest": parsed_result_digest,
    }
    record["record_digest"] = _unsigned_digest(record, "record_digest")
    errors = validate_workflow_call_record(record)
    if errors:
        raise ValueError("invalid workflow call record: " + "; ".join(errors))
    return record


def validate_workflow_call_record(
    record: Any,
    *,
    expected_call_id: str | None = None,
    expected_task_contract_digest: str | None = None,
    expected_context_artifact_digest: str | None = None,
    expected_node_id: str | None = None,
    expected_role_id: str | None = None,
    expected_result_digest: str | None = None,
) -> list[str]:
    """Validate integrity and exact controller-known call bindings."""

    if not isinstance(record, dict):
        return ["workflow call record must be an object"]
    errors: list[str] = []
    if set(record) != CALL_FIELDS:
        errors.append("workflow call record fields do not match canonical contract")
    if record.get("schema_version") != "workflow_call_record_v1":
        errors.append("workflow call record schema_version is invalid")
    for field in (
        "workflow_contract_digest", "prompt_digest", "context_artifact_digest",
        "task_contract_digest", "dirty_scope_digest", "focus_digest",
        "response_schema_digest", "parsed_result_digest",
    ):
        if not DIGEST_RE.fullmatch(str(record.get(field, ""))):
            errors.append(f"workflow call {field} is invalid")
    for field in ("logical_call_id", "node_id", "payload_kind", "phase", "label"):
        error = _identifier_error(record.get(field), f"workflow call {field}")
        if error:
            errors.append(error)
    requested = record.get("requested")
    errors.extend(requested_identity_errors(requested, expected_role=expected_role_id))
    errors.extend(validate_call_dag_fields(record))
    if isinstance(requested, dict) and requested_logical_role(requested) in load_registry()["roles"]:
        expected_payload = load_registry()["roles"][requested_logical_role(requested)].get("payload_kind")
        if record.get("payload_kind") != expected_payload:
            errors.append("workflow call payload_kind differs from Registry role contract")
    attempt = record.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        errors.append("workflow call attempt must be a positive integer")
    parent = record.get("retry_parent_call_id")
    if attempt == 1 and parent is not None:
        errors.append("first workflow call attempt cannot have a retry parent")
    if isinstance(attempt, int) and attempt > 1:
        error = _identifier_error(parent, "workflow call retry_parent_call_id")
        if error:
            errors.append(error)
        if parent == record.get("logical_call_id"):
            errors.append("workflow call cannot be its own retry parent")
    for field in (
        "compiler_input_tokens_lower_bound", "admitted_input_tokens_lower_bound",
    ):
        if not _nonnegative_integer(record.get(field)):
            errors.append(f"workflow call {field} must be a non-negative integer")
    started, start_error = _timestamp(record.get("started_at"), "workflow call started_at")
    ended, end_error = _timestamp(record.get("ended_at"), "workflow call ended_at")
    errors.extend(error for error in (start_error, end_error) if error)
    if started is not None and ended is not None and ended < started:
        errors.append("workflow call ended_at precedes started_at")
    returned_null = record.get("returned_null")
    if not isinstance(returned_null, bool):
        errors.append("workflow call returned_null must be boolean")
    elif returned_null and record.get("parsed_result_digest") != NULL_DIGEST:
        errors.append("null workflow call result digest is not canonical null")
    elif not returned_null and record.get("parsed_result_digest") == NULL_DIGEST:
        errors.append("non-null workflow call cannot carry canonical null digest")
    bindings = {
        "logical_call_id": expected_call_id,
        "task_contract_digest": expected_task_contract_digest,
        "context_artifact_digest": expected_context_artifact_digest,
        "node_id": expected_node_id,
        "parsed_result_digest": expected_result_digest,
    }
    for field, expected in bindings.items():
        if expected is not None and record.get(field) != expected:
            errors.append(f"workflow call record does not match expected {field}")
    try:
        expected_digest = _unsigned_digest(record, "record_digest")
    except (TypeError, ValueError):
        expected_digest = None
        errors.append("workflow call record is not canonical JSON")
    if record.get("record_digest") != expected_digest:
        errors.append("workflow call record self-digest is invalid")
    return errors


def build_workflow_call_manifest(
    records: list[dict[str, Any]], *, workflow_contract_digest: str
) -> dict[str, Any]:
    core = {
        "schema_version": "workflow_call_manifest_v1",
        "workflow_contract_digest": workflow_contract_digest,
        "records": records,
    }
    return {**core, "manifest_digest": canonical_digest(core)}


def validate_workflow_call_manifest(
    manifest: Any,
    *,
    expected_task_contract_digest: str | None = None,
    expected_context_artifact_digest: str | None = None,
) -> list[str]:
    if not isinstance(manifest, dict):
        return ["workflow call manifest must be an object"]
    errors: list[str] = []
    if set(manifest) != MANIFEST_FIELDS:
        errors.append("workflow call manifest fields do not match contract")
    if manifest.get("schema_version") != "workflow_call_manifest_v1":
        errors.append("workflow call manifest schema_version is invalid")
    contract_digest = manifest.get("workflow_contract_digest")
    if not DIGEST_RE.fullmatch(str(contract_digest or "")):
        errors.append("workflow call manifest contract digest is invalid")
    records = manifest.get("records")
    if not isinstance(records, list) or not records:
        errors.append("workflow call manifest records must be a non-empty array")
        records = []
    call_ids: list[Any] = []
    record_digests: list[Any] = []
    for index, record in enumerate(records):
        errors.extend(
            f"workflow call manifest records[{index}] {error}"
            for error in validate_workflow_call_record(
                record,
                expected_task_contract_digest=expected_task_contract_digest,
                expected_context_artifact_digest=expected_context_artifact_digest,
            )
        )
        if isinstance(record, dict):
            call_ids.append(record.get("logical_call_id"))
            record_digests.append(record.get("record_digest"))
            if record.get("workflow_contract_digest") != contract_digest:
                errors.append(f"workflow call manifest records[{index}] contract digest differs")
    if len(call_ids) != len(set(call_ids)):
        errors.append("workflow call manifest logical call ids must be unique")
    if len(record_digests) != len(set(record_digests)):
        errors.append("workflow call manifest record digests must be unique")
    try:
        expected_digest = _unsigned_digest(manifest, "manifest_digest")
    except (TypeError, ValueError):
        expected_digest = None
        errors.append("workflow call manifest is not canonical JSON")
    if manifest.get("manifest_digest") != expected_digest:
        errors.append("workflow call manifest digest is invalid")
    return errors


def _admitted_task_errors(task: Any, index: int) -> list[str]:
    label = f"workflow wave admitted_tasks[{index}]"
    if not isinstance(task, dict) or set(task) != ADMITTED_TASK_FIELDS:
        return [f"{label} fields do not match contract"]
    errors: list[str] = []
    for field in ("node_id", "role", "payload_kind"):
        error = _identifier_error(task.get(field), f"{label} {field}")
        if error:
            errors.append(error)
    errors.extend(requested_identity_errors(task.get("requested"), expected_role=task.get("role")))
    if isinstance(task.get("requested"), dict) and (
        task.get("native_agent") != requested_native_agent(task["requested"])
        or task.get("node_class") != task["requested"].get("node_class")
        or task.get("permission") != task["requested"].get("permission")
    ):
        errors.append(f"{label} native/class/permission differs from requested call")
    role = task.get("role")
    if isinstance(role, str) and role in load_registry()["roles"]:
        if task.get("payload_kind") != load_registry()["roles"][role].get("payload_kind"):
            errors.append(f"{label} payload_kind differs from Registry")
    for field in (
        "task_contract_digest", "context_artifact_digest", "description_digest",
        "base_prompt_digest", "dirty_scope_digest", "focus_digest",
    ):
        if not DIGEST_RE.fullmatch(str(task.get(field, ""))):
            errors.append(f"{label} {field} is invalid")
    dirty_scope = task.get("dirty_scope")
    if (
        not isinstance(dirty_scope, list) or not dirty_scope
        or any(not isinstance(item, str) or not item.strip() for item in dirty_scope)
        or len(dirty_scope) != len(set(dirty_scope))
        or dirty_scope != sorted(dirty_scope)
    ):
        errors.append(f"{label} dirty_scope must be sorted, unique, and non-empty")
    else:
        if task.get("dirty_scope_digest") != canonical_digest(dirty_scope):
            errors.append(f"{label} dirty_scope digest is invalid")
    focus = task.get("focus")
    if not isinstance(focus, str):
        errors.append(f"{label} focus must be a string")
    elif task.get("focus_digest") != canonical_digest(focus):
        errors.append(f"{label} focus digest is invalid")
    for field in (
        "compiler_estimated_input_tokens", "admitted_input_tokens_lower_bound",
    ):
        if not _nonnegative_integer(task.get(field)):
            errors.append(f"{label} {field} must be a non-negative integer")
    return errors


def validate_workflow_wave_record(
    wave: Any,
    manifest: Any,
    *,
    expected_task_contract_digest: str | None = None,
    expected_context_artifact_digest: str | None = None,
    expected_budget_authority_digest: str | None = None,
    expected_budget_authority_canonical: str | None = None,
) -> list[str]:
    """Validate call accounting, retries, admitted nodes, and result coverage."""

    if not isinstance(wave, dict):
        return ["workflow wave record must be an object"]
    errors: list[str] = []
    if set(wave) != WAVE_FIELDS:
        errors.append("workflow wave record fields do not match contract")
    if wave.get("schema_version") != "workflow_wave_record_v1":
        errors.append("workflow wave record schema_version is invalid")
    manifest_errors = validate_workflow_call_manifest(
        manifest,
        expected_task_contract_digest=expected_task_contract_digest,
        expected_context_artifact_digest=expected_context_artifact_digest,
    )
    errors.extend(f"workflow wave manifest {error}" for error in manifest_errors)
    records = manifest.get("records", []) if isinstance(manifest, dict) else []
    if wave.get("workflow_contract_digest") != (
        manifest.get("workflow_contract_digest") if isinstance(manifest, dict) else None
    ):
        errors.append("workflow wave contract digest differs from manifest")
    if wave.get("call_manifest_digest") != (
        manifest.get("manifest_digest") if isinstance(manifest, dict) else None
    ):
        errors.append("workflow wave call_manifest_digest differs from manifest")
    actual_record_digests = [
        record.get("record_digest") for record in records if isinstance(record, dict)
    ]
    if wave.get("call_record_digests") != actual_record_digests:
        errors.append("workflow wave call_record_digests differ from manifest order")
    tasks = wave.get("admitted_tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("workflow wave admitted_tasks must be a non-empty array")
        tasks = []
    for index, task in enumerate(tasks):
        errors.extend(_admitted_task_errors(task, index))
    node_ids = [task.get("node_id") for task in tasks if isinstance(task, dict)]
    if len(node_ids) != len(set(node_ids)):
        errors.append("workflow wave admitted node ids must be unique")
    task_by_node = {
        task.get("node_id"): task for task in tasks
        if isinstance(task, dict) and isinstance(task.get("node_id"), str)
    }
    errors.extend(validate_wave_dag_order(wave, records, tasks))
    context_map = wave.get("context_artifact_digests")
    expected_context_map = {
        node: task.get("context_artifact_digest") for node, task in task_by_node.items()
    }
    if context_map != expected_context_map:
        errors.append("workflow wave context artifact map differs from admitted tasks")
    result_map = wave.get("result_fragment_digests")
    if not isinstance(result_map, dict) or set(result_map) != set(task_by_node):
        errors.append("workflow wave result fragment map differs from admitted nodes")
        result_map = {}
    elif any(value is not None and not DIGEST_RE.fullmatch(str(value)) for value in result_map.values()):
        errors.append("workflow wave result fragment digests are invalid")
    numeric_fields = (
        "compiler_planned_input_tokens_lower_bound",
        "admitted_planned_input_tokens_lower_bound",
        "scheduled_call_compiler_input_tokens_lower_bound",
        "scheduled_call_admitted_input_tokens_lower_bound",
        "first_attempt_call_count", "retry_call_count", "null_call_count",
        "final_null_node_count",
    )
    for field in numeric_fields:
        if not _nonnegative_integer(wave.get(field)):
            errors.append(f"workflow wave {field} must be a non-negative integer")
    expected_compiler_plan = sum(
        task.get("compiler_estimated_input_tokens", 0)
        for task in tasks if isinstance(task, dict)
    )
    expected_admitted_plan = sum(
        task.get("admitted_input_tokens_lower_bound", 0)
        for task in tasks if isinstance(task, dict)
    )
    if wave.get("compiler_planned_input_tokens_lower_bound") != expected_compiler_plan:
        errors.append("workflow wave compiler planned lower bound is inconsistent")
    if wave.get("admitted_planned_input_tokens_lower_bound") != expected_admitted_plan:
        errors.append("workflow wave admitted planned lower bound is inconsistent")
    scheduled_compiler = sum(
        record.get("compiler_input_tokens_lower_bound", 0)
        for record in records if isinstance(record, dict)
    )
    scheduled_admitted = sum(
        record.get("admitted_input_tokens_lower_bound", 0)
        for record in records if isinstance(record, dict)
    )
    if wave.get("scheduled_call_compiler_input_tokens_lower_bound") != scheduled_compiler:
        errors.append("workflow wave scheduled compiler lower bound is inconsistent")
    if wave.get("scheduled_call_admitted_input_tokens_lower_bound") != scheduled_admitted:
        errors.append("workflow wave scheduled admitted lower bound is inconsistent")
    first_records = [
        record for record in records
        if isinstance(record, dict) and record.get("attempt") == 1
    ]
    retry_records = [
        record for record in records
        if isinstance(record, dict) and isinstance(record.get("attempt"), int)
        and record.get("attempt") > 1
    ]
    null_records = [record for record in records if isinstance(record, dict) and record.get("returned_null") is True]
    if wave.get("first_attempt_call_count") != len(first_records):
        errors.append("workflow wave first-attempt count differs from manifest")
    if len(first_records) != len(tasks):
        errors.append("workflow wave requires exactly one first attempt per admitted task")
    if wave.get("retry_call_count") != len(retry_records):
        errors.append("workflow wave retry count differs from manifest")
    if wave.get("null_call_count") != len(null_records):
        errors.append("workflow wave null count differs from manifest")
    calls_by_id = {
        record.get("logical_call_id"): record for record in records if isinstance(record, dict)
    }
    for record in retry_records:
        parent = calls_by_id.get(record.get("retry_parent_call_id"))
        if parent is None:
            errors.append("workflow wave retry parent is missing from manifest")
        elif parent.get("node_id") != record.get("node_id"):
            errors.append("workflow wave retry parent belongs to another node")
        elif parent.get("returned_null") is not True:
            errors.append("workflow wave retry parent was not an infrastructure null")
    final_null = 0
    for node in task_by_node:
        node_records = [record for record in records if isinstance(record, dict) and record.get("node_id") == node]
        if not node_records:
            errors.append(f"workflow wave admitted node {node} has no call record")
            final_null += 1
            continue
        latest = max(node_records, key=lambda record: record.get("attempt", 0))
        ordered = sorted(node_records, key=lambda record: record.get("attempt", 0))
        attempts = [record.get("attempt") for record in ordered]
        if attempts != list(range(1, len(ordered) + 1)):
            errors.append(f"workflow wave node {node} attempts are not contiguous from one")
        for position, record in enumerate(ordered[1:], start=1):
            parent = ordered[position - 1]
            if record.get("retry_parent_call_id") != parent.get("logical_call_id"):
                errors.append(f"workflow wave node {node} retry does not bind the prior attempt")
            if parent.get("returned_null") is not True:
                errors.append(f"workflow wave node {node} retry parent was not null")
        if latest.get("returned_null") is True:
            final_null += 1
            if result_map.get(node) is not None:
                errors.append(f"workflow wave final-null node {node} cannot claim a result digest")
        elif result_map.get(node) is None:
            errors.append(f"workflow wave successful node {node} requires a result digest")
        task = task_by_node[node]
        for record in node_records:
            for field in ("task_contract_digest", "context_artifact_digest", "payload_kind"):
                if record.get(field) != task.get(field):
                    errors.append(f"workflow wave call {record.get('logical_call_id')} differs from admitted task {field}")
            if isinstance(record.get("requested"), dict) and requested_logical_role(record["requested"]) != task.get("role"):
                errors.append(f"workflow wave call {record.get('logical_call_id')} differs from admitted role")
    if wave.get("final_null_node_count") != final_null:
        errors.append("workflow wave final-null count differs from final call state")
    debt = wave.get("coverage_debt")
    if not isinstance(debt, list):
        errors.append("workflow wave coverage_debt must be an array")
        debt = []
    for index, item in enumerate(debt):
        if not isinstance(item, dict) or set(item) != COVERAGE_DEBT_FIELDS:
            errors.append(f"workflow wave coverage_debt[{index}] fields do not match contract")
        elif any(not isinstance(item.get(field), str) or not item.get(field, "").strip() for field in COVERAGE_DEBT_FIELDS):
            errors.append(f"workflow wave coverage_debt[{index}] values must be non-empty strings")
    if final_null and not debt:
        errors.append("workflow wave final null nodes require explicit coverage debt")
    errors.extend(workflow_budget_errors(
        wave.get("budget_authority"), tasks=tasks, first_records=first_records,
        retry_records=retry_records, records=records,
        scheduled_admitted=scheduled_admitted,
    ))
    budget = wave.get("budget_authority")
    if isinstance(budget, dict):
        if expected_budget_authority_digest is not None and budget.get("authority_digest") != expected_budget_authority_digest:
            errors.append("workflow wave budget authority digest differs from admitted Context")
        if expected_budget_authority_canonical is not None and budget.get("authority_canonical") != expected_budget_authority_canonical:
            errors.append("workflow wave budget authority canonical bytes differ from admitted Context")
    boundary = wave.get("accounting_boundary")
    if not isinstance(boundary, dict) or set(boundary) != ACCOUNTING_BOUNDARY_FIELDS:
        errors.append("workflow wave accounting boundary fields do not match contract")
    else:
        if boundary.get("usage_measurement_status") not in {"unavailable", "partial", "measured"}:
            errors.append("workflow wave usage measurement status is invalid")
        if boundary.get("controller_overhead_status") not in {"unavailable", "partial", "measured"}:
            errors.append("workflow wave controller overhead status is invalid")
        excluded = boundary.get("excluded_from_token_lower_bounds")
        if (
            not isinstance(excluded, list) or not excluded
            or any(not isinstance(item, str) or not item.strip() for item in excluded)
        ):
            errors.append("workflow wave excluded accounting boundary must be explicit")
    try:
        expected_digest = _unsigned_digest(wave, "record_digest")
    except (TypeError, ValueError):
        expected_digest = None
        errors.append("workflow wave record is not canonical JSON")
    if wave.get("record_digest") != expected_digest:
        errors.append("workflow wave record digest is invalid")
    return errors


def build_workflow_wave_record(
    *,
    manifest: dict[str, Any],
    admitted_tasks: list[dict[str, Any]],
    budget_authority: dict[str, Any],
    result_fragment_digests: dict[str, str | None],
    coverage_debt: list[dict[str, str]] | None = None,
    accounting_boundary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic wave ledger from canonical call records."""

    records = manifest.get("records", []) if isinstance(manifest, dict) else []
    admitted_tasks = [
        {
            **task, "requires": task.get("requires", []),
        }
        for task in admitted_tasks
    ]
    calls_by_node: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if isinstance(record, dict):
            calls_by_node.setdefault(str(record.get("node_id", "")), []).append(record)
    final_null = 0
    for task in admitted_tasks:
        node_records = calls_by_node.get(str(task.get("node_id", "")), [])
        if not node_records or max(
            node_records, key=lambda record: record.get("attempt", 0)
        ).get("returned_null") is True:
            final_null += 1
    core: dict[str, Any] = {
        "schema_version": "workflow_wave_record_v1",
        "workflow_contract_digest": manifest.get("workflow_contract_digest"),
        "dag_digest": execution_dag_digest(admitted_tasks),
        "execution_waves": topological_waves(admitted_tasks)[0],
        "context_artifact_digests": {
            str(task["node_id"]): task["context_artifact_digest"]
            for task in admitted_tasks
        },
        "compiler_planned_input_tokens_lower_bound": sum(
            int(task["compiler_estimated_input_tokens"])
            for task in admitted_tasks
        ),
        "admitted_planned_input_tokens_lower_bound": sum(
            int(task["admitted_input_tokens_lower_bound"])
            for task in admitted_tasks
        ),
        "scheduled_call_compiler_input_tokens_lower_bound": sum(
            int(record.get("compiler_input_tokens_lower_bound", 0))
            for record in records if isinstance(record, dict)
        ),
        "scheduled_call_admitted_input_tokens_lower_bound": sum(
            int(record.get("admitted_input_tokens_lower_bound", 0))
            for record in records if isinstance(record, dict)
        ),
        "admitted_tasks": admitted_tasks,
        "call_manifest_digest": manifest.get("manifest_digest"),
        "call_record_digests": [
            record.get("record_digest") for record in records if isinstance(record, dict)
        ],
        "first_attempt_call_count": sum(
            1 for record in records
            if isinstance(record, dict) and record.get("attempt") == 1
        ),
        "retry_call_count": sum(
            1 for record in records
            if isinstance(record, dict) and isinstance(record.get("attempt"), int)
            and record["attempt"] > 1
        ),
        "null_call_count": sum(
            1 for record in records
            if isinstance(record, dict) and record.get("returned_null") is True
        ),
        "final_null_node_count": final_null,
        "coverage_debt": coverage_debt or [],
        "budget_authority": budget_authority,
        "result_fragment_digests": result_fragment_digests,
        "accounting_boundary": accounting_boundary or {
            "usage_measurement_status": "unavailable",
            "controller_overhead_status": "unavailable",
            "excluded_from_token_lower_bounds": [
                "model output, cache, and tool usage",
                "PM/controller dispatch and synthesis",
                "workflow admission, hashing, and record construction",
            ],
        },
    }
    wave = {**core, "record_digest": canonical_digest(core)}
    errors = validate_workflow_wave_record(wave, manifest)
    if errors:
        raise ValueError("invalid workflow wave record: " + "; ".join(errors))
    return wave


def judgment_from_role_fragment(fragment: Any) -> dict[str, Any] | None:
    if not isinstance(fragment, dict) or not JUDGMENT_FIELDS.issubset(fragment):
        return None
    return {field: fragment[field] for field in JUDGMENT_FIELDS}


def validate_role_fragment_producer(
    fragment: Any,
    *,
    calls_by_id: dict[str, dict[str, Any]],
    wave_records_by_digest: dict[str, dict[str, Any]],
    expected_task_contract_digest: str,
    expected_context_artifact_digest: str,
    allow_payload_projection: bool = False,
    skip_result_projection: bool = False,
) -> list[str]:
    """Cross-bind a role fragment to the exact call or deterministic wave record."""

    if not isinstance(fragment, dict):
        return ["role fragment must be an object"]
    errors: list[str] = []
    if not PRODUCER_FIELDS.issubset(fragment):
        errors.append("role fragment is missing canonical producer fields")
        return errors
    if fragment.get("context_artifact_digest") != expected_context_artifact_digest:
        errors.append("role fragment context artifact digest is not dispatch-bound")
    kind = fragment.get("producer_record_kind")
    producer_ref = fragment.get("producer_call_ref")
    producer_digest = fragment.get("producer_call_receipt_digest")
    if kind == "workflow_call_record_v1":
        call = calls_by_id.get(str(producer_ref))
        if call is None:
            errors.append("role fragment producer call ref is missing")
            return errors
        judgment = judgment_from_role_fragment(fragment)
        if judgment is None:
            errors.append("role fragment judgment projection is incomplete")
            return errors
        expected_result_digest = call.get("parsed_result_digest")
        if not skip_result_projection:
            judgment_digest = canonical_digest(judgment)
            accepted_result_digests = {judgment_digest}
            if allow_payload_projection and isinstance(fragment.get("payload"), dict):
                accepted_result_digests.add(canonical_digest(fragment["payload"]))
            if expected_result_digest not in accepted_result_digests:
                errors.append("role fragment projection differs from producer call result")
        errors.extend(
            validate_workflow_call_record(
                call,
                expected_call_id=str(producer_ref),
                expected_task_contract_digest=expected_task_contract_digest,
                expected_context_artifact_digest=expected_context_artifact_digest,
                expected_node_id=str(fragment.get("node_id", "")),
                expected_role_id=str(fragment.get("role", "")),
                expected_result_digest=expected_result_digest,
            )
        )
        if call.get("record_digest") != producer_digest:
            errors.append("role fragment producer receipt digest differs from call record")
        if call.get("returned_null") is not False:
            errors.append("role fragment cannot be produced by a null call")
        if call.get("payload_kind") != fragment.get("payload_kind"):
            errors.append("role fragment payload kind differs from producer call")
    elif kind == "workflow_wave_record_v1":
        wave = wave_records_by_digest.get(str(producer_digest))
        if wave is None or wave.get("record_digest") != producer_digest:
            errors.append("controller fragment wave producer receipt is missing")
        if producer_ref != producer_digest:
            errors.append("controller fragment wave ref must equal canonical record digest")
    else:
        errors.append("role fragment producer_record_kind is invalid")
    return errors
