"""Cross-bind capture artifacts to one admitted closure generation."""

from __future__ import annotations

from typing import Any

from agent_governance_capture import (
    PLATFORM_OR_EXTERNAL_ATTESTED,
    validate_command_capture,
    validate_repository_capture,
    validate_telemetry_record,
)
from agent_governance_workflow_receipts import (
    validate_workflow_call_manifest,
    validate_workflow_call_record,
    validate_workflow_wave_record,
)
from agent_governance_repository_changes import validate_repository_change_record
from agent_governance_external_evidence import (
    ExternalEvidenceVerifier,
    validate_external_evidence_capture,
)
from agent_governance_command_capture_v2 import validate_governed_command_capture


CAPTURE_KINDS = {
    "repository_capture_v1",
    "repository_change_record_v1",
    "command_capture_v1",
    "command_capture_v2",
    "workflow_call_record_v1",
    "workflow_call_manifest_v1",
    "workflow_wave_record_v1",
    "telemetry_record_v1",
    "external_evidence_capture_v1",
}


def _artifact_digest(kind: str, artifact: Any) -> Any:
    if not isinstance(artifact, dict):
        return None
    if kind == "workflow_call_manifest_v1":
        return artifact.get("manifest_digest")
    return artifact.get("record_digest")


def _append_unique(
    mapping: dict[str, dict[str, Any]],
    key: Any,
    value: dict[str, Any],
    *,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(key, str) or not key:
        errors.append(f"{label} has no canonical identifier")
    elif key in mapping and mapping[key] != value:
        errors.append(f"{label} collides with a different record")
    else:
        mapping[key] = value


def collect_capture_evidence(
    evidence_items: Any,
    *,
    expected_scope: list[str],
    expected_source_head: str,
    expected_task_contract_digest: str,
    expected_context_artifact_digest: str,
    expected_budget_authority_digest: str | None = None,
    expected_budget_authority_canonical: str | None = None,
    require_current_repository: bool,
    external_evidence_verifier: ExternalEvidenceVerifier | None = None,
    adjudicated_at: Any = None,
    expected_execution_tasks: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate wrappers, records, manifests, and complete wave accounting."""

    result: dict[str, Any] = {
        "errors": [],
        "repositories": {},
        "changes": {},
        "change_order": [],
        "commands": {},
        "calls": {},
        "manifests": {},
        "waves": {},
        "waves_by_id": {},
        "telemetry": {},
        "external_evidence": {},
        "platform_attested": set(),
        "runtime_attested": set(),
        "outcome_attested": set(),
        "external_policy_attested": set(),
        "capture_ids": set(),
    }
    errors: list[str] = result["errors"]
    artifact_digest_owner: dict[tuple[str, str], str] = {}
    if not isinstance(evidence_items, list):
        errors.append("closure evidence must be an array before capture binding")
        return result

    pending_waves: list[tuple[int, str, dict[str, Any]]] = []
    for index, wrapper in enumerate(evidence_items):
        if not isinstance(wrapper, dict):
            continue
        kind = wrapper.get("kind")
        if kind not in CAPTURE_KINDS:
            continue
        evidence_id = wrapper.get("id")
        artifact = wrapper.get("artifact")
        label = f"capture evidence[{index}] {evidence_id or '<missing>'}"
        if not isinstance(evidence_id, str) or not evidence_id:
            errors.append(f"{label} id is invalid")
            continue
        if evidence_id in result["capture_ids"]:
            errors.append(f"{label} id is duplicate")
            continue
        result["capture_ids"].add(evidence_id)
        if not isinstance(artifact, dict):
            errors.append(f"{label} artifact is required")
            continue
        if wrapper.get("digest") != _artifact_digest(str(kind), artifact):
            errors.append(f"{label} wrapper digest differs from captured artifact")
        internal_digest = _artifact_digest(str(kind), artifact)
        digest_key = (str(kind), str(internal_digest))
        prior_owner = artifact_digest_owner.get(digest_key)
        if prior_owner is not None:
            errors.append(
                f"{label} duplicates captured artifact digest already owned by {prior_owner}"
            )
            continue
        artifact_digest_owner[digest_key] = evidence_id

        if kind == "repository_capture_v1":
            record_errors = validate_repository_capture(
                artifact,
                expected_scope=expected_scope,
                require_current=require_current_repository,
            )
            if artifact.get("source_head") != expected_source_head:
                record_errors.append("repository capture source_head differs from closure baseline")
            errors.extend(f"{label}: {error}" for error in record_errors)
            if not record_errors:
                result["repositories"][evidence_id] = artifact
        elif kind == "repository_change_record_v1":
            record_errors = validate_repository_change_record(
                artifact,
                expected_task_contract_digest=expected_task_contract_digest,
                expected_source_head=expected_source_head,
                require_after_current=False,
            )
            if not set(artifact.get("scope", [])).issubset(set(expected_scope)):
                record_errors.append(
                    "repository change scope exceeds task dirty_scope"
                )
            errors.extend(f"{label}: {error}" for error in record_errors)
            if not record_errors:
                result["changes"][evidence_id] = artifact
                result["change_order"].append(evidence_id)
        elif kind == "command_capture_v1":
            record_errors = validate_command_capture(
                artifact,
                expected_task_contract_digest=expected_task_contract_digest,
                reexecute=True,
            )
            for boundary in ("repository_before", "repository_after"):
                captured = artifact.get(boundary)
                if isinstance(captured, dict):
                    if captured.get("scope") != sorted(expected_scope):
                        record_errors.append(
                            f"command capture {boundary} scope differs from task dirty_scope"
                        )
                    if captured.get("source_head") != expected_source_head:
                        record_errors.append(
                            f"command capture {boundary} source_head differs from closure baseline"
                        )
            errors.extend(f"{label}: {error}" for error in record_errors)
            if not record_errors:
                result["commands"][evidence_id] = artifact
        elif kind == "command_capture_v2":
            expected_task = (expected_execution_tasks or {}).get(
                str(artifact.get("node_id"))
            )
            if expected_task is None:
                record_errors = [
                    "governed command node is absent from closure dispatch"
                ]
                path_scope: list[str] = []
            else:
                path_scope = expected_task.get("path_scope") or expected_scope
                record_errors = validate_governed_command_capture(
                    artifact,
                    expected_context_artifact_digest=expected_context_artifact_digest,
                    expected_task_contract_digest=expected_task_contract_digest,
                    expected_execution_task={
                        field: expected_task.get(field)
                        for field in (
                            "node_id", "role", "native_agent", "node_class",
                            "permission", "requires", "path_scope",
                        )
                    },
                    expected_path_scope=path_scope,
                    expected_source_head=expected_source_head,
                    reexecute=True,
                )
            if wrapper.get("scope") != "test":
                record_errors.append("governed command wrapper scope must be test")
            errors.extend(f"{label}: {error}" for error in record_errors)
            if not record_errors:
                result["commands"][evidence_id] = artifact
        elif kind == "workflow_call_record_v1":
            record_errors = validate_workflow_call_record(
                artifact,
                expected_task_contract_digest=expected_task_contract_digest,
                expected_context_artifact_digest=expected_context_artifact_digest,
            )
            errors.extend(f"{label}: {error}" for error in record_errors)
            if not record_errors:
                result["calls"][artifact["logical_call_id"]] = artifact
        elif kind == "workflow_call_manifest_v1":
            record_errors = validate_workflow_call_manifest(
                artifact,
                expected_task_contract_digest=expected_task_contract_digest,
                expected_context_artifact_digest=expected_context_artifact_digest,
            )
            errors.extend(f"{label}: {error}" for error in record_errors)
            if not record_errors:
                result["manifests"][artifact["manifest_digest"]] = artifact
                for call in artifact["records"]:
                    _append_unique(
                        result["calls"],
                        call.get("logical_call_id"),
                        call,
                        label=f"{label} call",
                        errors=errors,
                    )
        elif kind == "workflow_wave_record_v1":
            pending_waves.append((index, evidence_id, artifact))
        elif kind == "telemetry_record_v1":
            record_errors = validate_telemetry_record(artifact)
            errors.extend(f"{label}: {error}" for error in record_errors)
            if not record_errors:
                result["telemetry"][evidence_id] = artifact
                if artifact.get("trust_tier") == PLATFORM_OR_EXTERNAL_ATTESTED:
                    result["platform_attested"].add(evidence_id)
        elif kind == "external_evidence_capture_v1":
            record_errors = validate_external_evidence_capture(
                artifact, verifier=external_evidence_verifier,
                adjudicated_at=adjudicated_at,
            )
            if wrapper.get("scope") != "external":
                record_errors.append("external evidence wrapper scope must be external")
            if wrapper.get("observed_at") != artifact.get("observed_at"):
                record_errors.append("external evidence wrapper observed_at differs from capture")
            if wrapper.get("expiry") != artifact.get("expires_at"):
                record_errors.append("external evidence wrapper expiry differs from capture")
            errors.extend(f"{label}: {error}" for error in record_errors)
            if not record_errors:
                result["external_evidence"][evidence_id] = artifact
                result["platform_attested"].add(evidence_id)
                target = (
                    "external_policy_attested"
                    if artifact.get("capture_kind") == "external_policy_snapshot"
                    else "outcome_attested"
                )
                result[target].add(evidence_id)

    used_manifest_digests: set[str] = set()
    for index, evidence_id, wave in pending_waves:
        label = f"capture evidence[{index}] {evidence_id}"
        manifest_digest = wave.get("call_manifest_digest")
        manifest = result["manifests"].get(manifest_digest)
        if manifest is None:
            errors.append(f"{label}: workflow wave references a missing call manifest")
            continue
        wave_errors = validate_workflow_wave_record(
            wave,
            manifest,
            expected_task_contract_digest=expected_task_contract_digest,
            expected_context_artifact_digest=expected_context_artifact_digest,
            expected_budget_authority_digest=expected_budget_authority_digest,
            expected_budget_authority_canonical=expected_budget_authority_canonical,
        )
        errors.extend(f"{label}: {error}" for error in wave_errors)
        if not wave_errors:
            _append_unique(
                result["waves"],
                wave.get("record_digest"),
                wave,
                label=label,
                errors=errors,
            )
            result["waves_by_id"][evidence_id] = wave
            used_manifest_digests.add(str(manifest_digest))
    orphan_manifests = set(result["manifests"]) - used_manifest_digests
    if orphan_manifests:
        errors.append(
            "workflow call manifests lack a complete wave record: "
            + ", ".join(sorted(orphan_manifests))
        )
    manifest_call_ids = {
        call["logical_call_id"]
        for manifest in result["manifests"].values()
        for call in manifest["records"]
    }
    orphan_calls = set(result["calls"]) - manifest_call_ids
    if orphan_calls:
        errors.append(
            "workflow call records lack a complete manifest/wave lineage: "
            + ", ".join(sorted(orphan_calls))
        )
    return result
