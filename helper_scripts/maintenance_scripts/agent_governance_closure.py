"""Closure, authority, and evidence Implementations for Development-Agent Governance."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_governance_registry import REPO_ROOT, load_registry
from agent_governance_authority import (
    resolve_authority_claims,
    validate_authority_claim,
)
from agent_governance_consumption import validate_consumption_binding
from agent_governance_workflow_capture import collect_closure_captures
from agent_governance_capture_binding import CAPTURE_KINDS
from agent_governance_context_validation import validate_context_artifact
from agent_governance_evidence import (
    validate_test_evidence_reuse_receipt,
    validate_test_execution_receipt,
)
from agent_governance_effects import (
    validate_deploy_effect_binding,
    validate_effect_evidence,
)
from agent_governance_execution_attestation import (
    ExecutionAttestationVerifier,
    validate_execution_attestations,
)
from agent_governance_external_evidence import ExternalEvidenceVerifier
from agent_governance_dispatch_validation import validate_dispatch_projection
from agent_governance_execution import (
    CLOSURE_REQUIRED_FIELDS,
    DIGEST_RE,
    DISPOSITIONS,
    GATE_VERDICTS,
    WORK_STATUSES,
    route_task,
)
from agent_governance_full_audit import validate_full_audit_binding
from agent_governance_observations import validate_observation_evidence
from agent_governance_profit import validate_profit_diagnosis_binding
from agent_governance_repository_changes import validate_repository_change_chain
from agent_governance_node_permissions import validate_node_scoped_permissions
from agent_governance_schema import schema_subset_errors as _schema_subset_errors
from agent_governance_trust import validate_closure_trust

CLOSURE_SCHEMA_REL = Path(".codex/schemas/closure_packet_v1.schema.json")


def _verification_fragment_truth_errors(
    fragment: dict[str, Any], label: str
) -> list[str]:
    errors: list[str] = []
    if fragment.get("classification") != "FACT":
        errors.append(f"{label} PASS must be FACT, not assumption/inference")
    if fragment.get("confidence") == "low":
        errors.append(f"{label} low-confidence fragment cannot support PASS")
    if fragment.get("concerns"):
        errors.append(f"{label} unresolved concerns cannot support PASS")
    return errors


def validate_closure(
    packet: dict[str, Any],
    *,
    execution_attestation_verifier: ExecutionAttestationVerifier | None = None,
    external_evidence_verifier: ExternalEvidenceVerifier | None = None,
) -> list[str]:
    """Validate closure_packet_v1 structure and cross-field truth semantics."""

    schema = json.loads((REPO_ROOT / CLOSURE_SCHEMA_REL).read_text(encoding="utf-8"))
    errors = _schema_subset_errors(packet, schema, schema)
    missing = CLOSURE_REQUIRED_FIELDS - set(packet)
    if missing:
        errors.append(f"closure missing fields: {sorted(missing)}")
        return errors
    unexpected = set(packet) - CLOSURE_REQUIRED_FIELDS
    if unexpected:
        errors.append(f"closure has unexpected fields: {sorted(unexpected)}")
    if packet.get("schema_version") != "closure_packet_v1":
        errors.append("schema_version must be closure_packet_v1")
    if packet.get("work_status") not in WORK_STATUSES:
        errors.append("invalid work_status")
    if packet.get("gate_verdict") not in GATE_VERDICTS:
        errors.append("invalid gate_verdict")
    if packet.get("disposition") not in DISPOSITIONS:
        errors.append("invalid disposition")
    if packet.get("confidence") not in {"high", "med", "low"}:
        errors.append("invalid confidence")
    try:
        adjudicated_at = _parse_timestamp(str(packet.get("adjudicated_at", "")))
        if adjudicated_at.tzinfo is None:
            raise ValueError("timezone missing")
    except (TypeError, ValueError):
        adjudicated_at = None
        errors.append("adjudicated_at must be a timezone-aware timestamp")
    if packet["work_status"] in {"BLOCKED", "NEEDS_CONTEXT"} and packet["gate_verdict"] == "PASS":
        errors.append("BLOCKED/NEEDS_CONTEXT cannot carry PASS")

    summary = packet.get("human_summary", {})
    if not summary.get("objective") or not summary.get("scope") or not summary.get("outcome"):
        errors.append("human_summary requires objective, scope, and outcome")
    baseline = packet.get("baseline", {})
    baseline_fields = {
        "source_head", "dirty_diff_hash", "untracked_relevant_hash",
        "runtime_head", "runtime_observed_at",
    }
    if set(baseline) != baseline_fields:
        errors.append("baseline fields do not match the canonical generation contract")
    if not isinstance(baseline.get("source_head"), str) or not re.fullmatch(
        r"[0-9a-f]{40}", baseline.get("source_head", "")
    ):
        errors.append("baseline source_head must be exact 40-hex")
    for field in ("dirty_diff_hash", "untracked_relevant_hash"):
        if not DIGEST_RE.fullmatch(str(baseline.get(field, ""))):
            errors.append(f"baseline {field} must be sha256")
    runtime_head = baseline.get("runtime_head")
    runtime_observed = baseline.get("runtime_observed_at")
    if (runtime_head is None) != (runtime_observed is None):
        errors.append("baseline runtime identity/time must be present together")
    if runtime_head is not None and not re.fullmatch(r"[0-9a-f]{40}", str(runtime_head)):
        errors.append("baseline runtime_head must be exact 40-hex")
    if runtime_observed is not None:
        try:
            if _parse_timestamp(str(runtime_observed)).tzinfo is None:
                raise ValueError("timezone missing")
        except (TypeError, ValueError):
            errors.append("baseline runtime_observed_at is invalid")

    dispatch = packet.get("dispatch", {})
    expected_route: dict[str, Any] | None = None
    expected_required_nodes: list[dict[str, str]] = []
    task_contract_digest: str | None = None
    task_contract: dict[str, Any] = {}
    try:
        expected_route = route_task(dispatch.get("task_facts"))
        expected_required_nodes = expected_route["required_role_nodes"]
        if dispatch.get("required_role_nodes") != expected_required_nodes:
            errors.append("dispatch required_role_nodes do not match recomputed route")
    except (AttributeError, TypeError, ValueError) as error:
        errors.append(f"dispatch task facts are invalid: {error}")

    context_result = validate_context_artifact(
        dispatch.get("context_artifact"),
        now=packet.get("adjudicated_at"),
        expected_task_facts=dispatch.get("task_facts"),
        require_local_provenance=(
            packet.get("gate_verdict") != "PASS"
            and execution_attestation_verifier is None
        ),
        provenance_verifier=execution_attestation_verifier,
        external_evidence_verifier=external_evidence_verifier,
    )
    if context_result.get("errors"):
        errors.extend(
            f"dispatch context artifact invalid: {error}"
            for error in context_result["errors"]
        )
    context_plan = context_result.get("plan")
    if isinstance(context_plan, dict):
        if context_plan.get("role") != "PM":
            errors.append("closure dispatch context artifact must be the PM admission bundle")
        if (
            packet.get("gate_verdict") == "PASS"
            and context_plan.get("budget", {}).get("claim_pass_eligible") is not True
        ):
            errors.append(
                "closure PASS is forbidden while admitted Context has unresolved verdict evidence debt"
            )
        task_contract = context_plan.get("task_contract", {})
        task_contract_digest = context_plan.get("task_contract_digest")
        if summary.get("objective") != task_contract.get("objective"):
            errors.append("closure objective differs from admitted task contract")
        if summary.get("scope") != task_contract.get("scope"):
            errors.append("closure scope differs from admitted task contract")
        if [item.get("criterion") for item in packet.get("acceptance", [])] != task_contract.get(
            "acceptance_criteria"
        ):
            errors.append("closure acceptance criteria differ from admitted task contract")
        task_baseline = task_contract.get("baseline", {})
        side_effect_class = task_contract.get("side_effect_class")
        if not (
            side_effect_class in {"repo_write", "docs_write", "local_test"}
            and packet.get("disposition") == "CHANGED"
        ):
            for field in ("source_head", "dirty_diff_hash", "untracked_relevant_hash"):
                if baseline.get(field) != task_baseline.get(field):
                    errors.append(
                        f"closure baseline {field} differs from no-change task contract"
                    )

    for index, ref in enumerate(packet.get("authority_refs", [])):
        errors.extend(
            f"authority_refs[{index}] {error}"
            for error in validate_authority_claim(
                ref, adjudicated_at=packet.get("adjudicated_at")
            )
        )
    if not packet.get("authority_refs"):
        errors.append("authority_refs must not be empty")

    evidence_by_id: dict[str, dict[str, Any]] = {}
    runtime_evidence: list[dict[str, Any]] = []
    valid_effect_receipts: dict[str, dict[str, Any]] = {}
    valid_observation_artifacts: dict[str, dict[str, Any]] = {}
    for index, evidence in enumerate(packet.get("evidence", [])):
        evidence_id = evidence.get("id")
        if not evidence_id or evidence_id in evidence_by_id:
            errors.append(f"evidence[{index}] id missing or duplicate")
            continue
        evidence_by_id[evidence_id] = evidence
        if evidence.get("scope") not in {"source", "runtime", "external", "test", "data"}:
            errors.append(f"evidence[{index}] has invalid scope")
        if not DIGEST_RE.fullmatch(str(evidence.get("digest", ""))):
            errors.append(f"evidence[{index}] has invalid digest")
        if evidence.get("scope") == "runtime":
            runtime_evidence.append(evidence)
            if not all(evidence.get(field) for field in ("host", "environment", "observed_at", "expiry")):
                errors.append("runtime evidence requires host, environment, observed_at, and expiry")
            else:
                try:
                    observed = _parse_timestamp(str(evidence["observed_at"]))
                    expiry = _parse_timestamp(str(evidence["expiry"]))
                    if observed.tzinfo is None or expiry.tzinfo is None or expiry <= observed:
                        raise ValueError("invalid runtime evidence interval")
                except (TypeError, ValueError):
                    errors.append("runtime evidence expiry must be after observed_at")
        if evidence.get("kind") == "effect_adapter_result_v1":
            receipt_errors, receipt = validate_effect_evidence(
                evidence,
                expected_adapter_id=str(evidence.get("source", "")),
                expected_source_head=str(packet.get("baseline", {}).get("source_head", "")),
            )
            if receipt_errors:
                errors.extend(
                    f"evidence[{index}] invalid effect Adapter receipt: {error}"
                    for error in receipt_errors
                )
            elif receipt is not None:
                valid_effect_receipts[evidence_id] = receipt
        elif evidence.get("receipt") is not None:
            errors.append(f"evidence[{index}] non-effect evidence cannot carry receipt")
        if (
            evidence.get("artifact") is not None
            and evidence.get("kind") not in CAPTURE_KINDS
        ):
            admitted_baseline = (dispatch.get("task_facts") or {}).get("baseline")
            if isinstance(admitted_baseline, dict) and set(admitted_baseline) == {
                "source_head", "dirty_diff_hash", "untracked_relevant_hash"
            }:
                admitted_baseline = {
                    **admitted_baseline,
                    "runtime_head": None,
                    "runtime_observed_at": None,
                }
            artifact_errors, artifact = validate_observation_evidence(
                evidence,
                expected_baseline=packet.get("baseline", {}),
                adjudicated_at=str(packet.get("adjudicated_at", "")),
                task_baseline=admitted_baseline,
            )
            if artifact_errors:
                errors.extend(
                    f"evidence[{index}] invalid typed observation: {error}"
                    for error in artifact_errors
                )
            elif artifact is not None:
                valid_observation_artifacts[evidence_id] = artifact
        if (
            evidence.get("operation_receipt") is not None
            and evidence.get("kind") not in {"ops_preflight_v1", "ops_postcheck_v1"}
        ):
            errors.append(
                f"evidence[{index}] non-OPS evidence cannot carry operation_receipt"
            )

    captures = collect_closure_captures(
        packet, dispatch, task_contract, task_contract_digest, baseline,
        external_evidence_verifier=external_evidence_verifier,
    )

    if not packet.get("acceptance"):
        errors.append("acceptance must not be empty")
    for index, acceptance in enumerate(packet.get("acceptance", [])):
        status = acceptance.get("status")
        if status not in {"PASS", "FAIL", "UNVERIFIED", "NOT_APPLICABLE"}:
            errors.append(f"acceptance[{index}] has invalid status")
        refs = acceptance.get("evidence_refs", [])
        if status != "NOT_APPLICABLE" and not refs:
            errors.append(f"acceptance[{index}] lacks direct evidence")
        for ref in refs:
            if ref not in evidence_by_id:
                errors.append(f"acceptance[{index}] references missing evidence {ref}")

    if not packet.get("role_fragments"):
        errors.append("role_fragments must not be empty")
    hard_gate_roles = {"CC", "E3", "QA", "BB", "IB", "OPS"}
    role_registry = load_registry()["roles"]
    valid_roles = set(role_registry)
    dispatch_validation = validate_dispatch_projection(
        dispatch, expected_route=expected_route,
        expected_required_nodes=expected_required_nodes,
        task_contract=task_contract, role_registry=role_registry,
    )
    errors.extend(dispatch_validation["errors"])
    admitted_role_nodes = dispatch_validation["admitted_nodes"]
    admitted_by_node = dispatch_validation["admitted_by_node"]
    writer_scopes = dispatch_validation["writer_scopes"]

    errors.extend(validate_node_scoped_permissions(captures, expected_route, admitted_by_node))

    if expected_route is not None:
        admitted_roles = {node.get("role") for node in admitted_by_node.values()}
        expected_skips = [
            item for item in expected_route.get("skipped", [])
            if item.get("role") not in admitted_roles
        ]
        if packet.get("skipped_roles") != expected_skips:
            errors.append("closure skipped_roles do not match deterministic route/admissions")

    bound_fragment_nodes = {requirement["node_id"] for requirement in expected_required_nodes} | set(admitted_by_node)
    fragment_ids: set[str] = set()
    fragments_by_node: dict[str, dict[str, Any]] = {}
    for index, fragment in enumerate(packet.get("role_fragments", [])):
        fragment_id = fragment.get("id")
        if not fragment_id or fragment_id in fragment_ids:
            errors.append(f"role_fragments[{index}] id missing or duplicate")
        else:
            fragment_ids.add(fragment_id)
        node_id = fragment.get("node_id")
        if not node_id or node_id in fragments_by_node:
            errors.append(f"role_fragments[{index}] node_id missing or duplicate")
        else:
            fragments_by_node[node_id] = fragment
            if node_id not in bound_fragment_nodes:
                errors.append(f"role fragment node {node_id} is not dispatch-bound")
        if fragment.get("role") not in valid_roles:
            errors.append(f"role_fragments[{index}] has invalid role")
        elif fragment.get("role") != "PM" and fragment.get("payload_kind") != role_registry[fragment["role"]].get("payload_kind"):
            errors.append(f"role_fragments[{index}] payload_kind does not match Registry")
        if fragment.get("work_status") not in WORK_STATUSES:
            errors.append(f"role_fragments[{index}] invalid work_status")
        if fragment.get("gate_verdict") not in GATE_VERDICTS:
            errors.append(f"role_fragments[{index}] invalid gate_verdict")
        if fragment.get("classification") not in {"FACT", "INFERENCE", "ASSUMPTION"}:
            errors.append(f"role_fragments[{index}] invalid classification")
        if fragment.get("confidence") not in {"high", "med", "low"}:
            errors.append(f"role_fragments[{index}] invalid confidence")
        if fragment.get("task_contract_digest") != task_contract_digest:
            errors.append(f"role_fragments[{index}] task contract digest is not dispatch-bound")
        for ref in fragment.get("evidence_refs", []):
            if ref not in evidence_by_id:
                errors.append(f"role_fragments[{index}] references missing evidence {ref}")
        if (
            packet["gate_verdict"] == "PASS"
            and fragment.get("role") in hard_gate_roles
            and fragment.get("gate_verdict") in {"FAIL", "UNVERIFIED"}
        ):
            errors.append("hard-gate fragment FAIL cannot be overridden by closure PASS")
        if (
            packet["gate_verdict"] == "PASS"
            and fragment.get("role") in hard_gate_roles
            and (
                fragment.get("gate_verdict") not in {"PASS", "NOT_APPLICABLE"}
                or fragment.get("work_status") in {"BLOCKED", "NEEDS_CONTEXT"}
            )
        ):
            errors.append("hard-gate fragment must be PASS or NOT_APPLICABLE for closure PASS")

    if "full_audit" in set((expected_route or {}).get("task_facts", {}).get("surfaces", [])):
        controller = fragments_by_node.get("ai_economics_review", {})
        errors.extend(
            _schema_subset_errors(
                controller.get("payload"), schema["$defs"]["fullAuditControl"], schema,
                "$.role_fragments[ai_economics_review].payload",
            )
        )
        for node_id, fragment in fragments_by_node.items():
            if node_id.startswith("audit:"):
                errors.extend(
                    _schema_subset_errors(
                        fragment.get("payload"), schema["$defs"]["fullAuditAxis"], schema,
                        f"$.role_fragments[{node_id}].payload",
                    )
                )
    errors.extend(
        validate_full_audit_binding(
            packet, expected_route, admitted_by_node, fragments_by_node,
            external_evidence_verifier=external_evidence_verifier,
        )
    )
    errors.extend(
        validate_profit_diagnosis_binding(
            packet, expected_route, admitted_by_node, fragments_by_node,
            external_evidence_verifier=external_evidence_verifier,
        )
    )

    check_ids: set[str] = set()
    valid_check_evidence_refs: set[str] = set()
    check_executor_by_evidence: dict[str, str] = {}
    for index, check in enumerate(packet.get("checks", [])):
        check_id = check.get("id")
        if not check_id or check_id in check_ids:
            errors.append(f"checks[{index}] id missing or duplicate")
        else:
            check_ids.add(check_id)
        status = check.get("status")
        if status not in {"EXECUTED", "REUSED", "SKIPPED", "FAILED"}:
            errors.append(f"checks[{index}] invalid status")
        if not DIGEST_RE.fullmatch(str(check.get("signature", ""))):
            errors.append(f"checks[{index}] has invalid signature")
        if status == "EXECUTED" and not check.get("executed_at"):
            errors.append(f"checks[{index}] EXECUTED requires executed_at")
        if status == "REUSED" and (not check.get("reused_from") or check.get("executed_at")):
            errors.append(f"checks[{index}] REUSED must identify source and cannot claim executed_at")
        if status == "SKIPPED" and not check.get("skip_reason"):
            errors.append(f"checks[{index}] SKIPPED requires skip_reason")
        evidence_ref = check.get("evidence_ref")
        if status != "SKIPPED" and evidence_ref not in evidence_by_id:
            errors.append(f"checks[{index}] references missing evidence {evidence_ref}")
        command_capture = captures.get("commands", {}).get(
            check.get("command_capture_ref")
        )
        if (
            status == "EXECUTED"
            and check.get("executed_at")
            and evidence_ref in evidence_by_id
            and isinstance(command_capture, dict)
        ):
            execution_receipt = check.get("execution_receipt")
            execution_errors: list[str] = []
            if isinstance(execution_receipt, dict):
                execution_errors.extend(
                    validate_test_execution_receipt(
                        execution_receipt,
                        expected_baseline=packet.get("baseline", {}),
                        expected_evidence_digest=evidence_by_id[evidence_ref].get("digest"),
                        require_success=True,
                    )
                )
                if execution_receipt.get("signature") != check.get("signature"):
                    execution_errors.append("typed execution signature differs from check")
                if execution_receipt.get("completed_at") != check.get("executed_at"):
                    execution_errors.append("typed execution completion differs from check")
                if execution_receipt.get("facts", {}).get("command") != check.get("command"):
                    execution_errors.append("typed execution command differs from check")
            if execution_errors:
                errors.append(
                    f"checks[{index}] EXECUTED requires valid typed receipt: "
                    + "; ".join(execution_errors)
                )
            else:
                valid_check_evidence_refs.add(evidence_ref)
                check_executor_by_evidence[evidence_ref] = command_capture["role_id"]
        if status == "REUSED":
            receipt_errors = validate_test_evidence_reuse_receipt(
                check.get("reuse_receipt"),
                check_signature=check.get("signature"),
                evidence_digest=evidence_by_id.get(evidence_ref, {}).get("digest"),
                reused_from=check.get("reused_from"),
                adjudicated_at=packet.get("adjudicated_at"),
            )
            if isinstance(check.get("reuse_receipt"), dict):
                receipt_errors.extend(
                    validate_test_execution_receipt(
                        check["reuse_receipt"].get("execution_receipt"),
                        expected_baseline=packet.get("baseline", {}),
                        expected_evidence_digest=evidence_by_id.get(evidence_ref, {}).get("digest"),
                        require_success=True,
                    )
                )
            if receipt_errors:
                errors.append(
                    "REUSED check requires a valid hash-pinned reuse receipt: "
                    + "; ".join(receipt_errors)
                )
            elif evidence_ref in evidence_by_id and isinstance(command_capture, dict):
                valid_check_evidence_refs.add(evidence_ref)
                check_executor_by_evidence[evidence_ref] = command_capture["role_id"]
        elif check.get("reuse_receipt") is not None:
            errors.append(f"checks[{index}] non-REUSED status cannot carry reuse_receipt")
        if status != "EXECUTED" and check.get("execution_receipt") is not None:
            errors.append(f"checks[{index}] non-EXECUTED status cannot carry execution_receipt")

    if packet["gate_verdict"] == "PASS":
        authority_decision = resolve_authority_claims(
            packet.get("authority_refs", []),
            adjudicated_at=str(packet.get("adjudicated_at", "")),
        )
        if authority_decision.get("gate_verdict") != "PASS":
            errors.append(
                "closure PASS has unresolved authority conflict or stale authority: "
                f"{authority_decision.get('status')}"
            )
        typed_direct_refs = (
            set(valid_observation_artifacts)
            | set(valid_effect_receipts)
            | valid_check_evidence_refs
            | set(captures.get("repositories", {}))
            | set(captures.get("commands", {}))
        )
        valid_runtime_refs = {
            evidence_id for evidence_id, artifact in valid_observation_artifacts.items()
            if artifact.get("schema_version") == "runtime_observation_receipt_v1"
        } | set(valid_effect_receipts)
        for index, item in enumerate(packet.get("acceptance", [])):
            if item.get("status") != "PASS":
                continue
            refs = set(item.get("evidence_refs", []))
            if not refs & typed_direct_refs:
                errors.append(
                    f"acceptance[{index}] PASS requires a typed content-addressed receipt"
                )
            for ref in refs & set(valid_observation_artifacts):
                artifact = valid_observation_artifacts[ref]
                criteria = artifact.get("criteria")
                criterion = artifact.get("criterion")
                if criteria is not None and item.get("criterion") not in criteria:
                    errors.append(
                        f"acceptance[{index}] criterion is not bound by source receipt {ref}"
                    )
                if criterion is not None and item.get("criterion") != criterion:
                    errors.append(
                        f"acceptance[{index}] criterion differs from outcome receipt {ref}"
                    )
        if any(item.get("status") in {"FAIL", "UNVERIFIED"} for item in packet.get("acceptance", [])):
            errors.append("closure PASS requires every applicable acceptance item to PASS")
        if packet.get("unverified"):
            errors.append("closure PASS cannot retain unverified scope")
        if not any(item.get("status") == "PASS" for item in packet.get("acceptance", [])):
            errors.append("closure PASS requires at least one passed acceptance item")
        if any(check.get("status") == "FAILED" for check in packet.get("checks", [])):
            errors.append("closure PASS cannot contain FAILED checks")
        work_only_nodes = {
            "implementation", "implementation_backend", "implementation_frontend",
            "test_implementation", "docs_update", "docs_projection",
        }
        for requirement in expected_required_nodes:
            fragment = fragments_by_node.get(requirement["node_id"])
            if fragment is None or fragment.get("role") != requirement["role"]:
                errors.append(
                    f"closure PASS missing mandatory node fragment {requirement['node_id']}:{requirement['role']}"
                )
                continue
            if fragment.get("work_status") not in {"DONE", "DONE_WITH_CONCERNS"}:
                errors.append(
                    f"mandatory node {requirement['node_id']} cannot support closure PASS"
                )
                continue
            if requirement["node_id"] in work_only_nodes:
                if fragment.get("gate_verdict") not in {"PASS", "NOT_APPLICABLE"}:
                    errors.append(
                        f"mandatory work node {requirement['node_id']} cannot support closure PASS"
                    )
            elif fragment.get("gate_verdict") != "PASS":
                errors.append(
                    f"mandatory verification node {requirement['node_id']} requires PASS"
                )
            else:
                errors.extend(
                    _verification_fragment_truth_errors(
                        fragment, f"mandatory verification node {requirement['node_id']}"
                    )
                )

        for node_id, admission in admitted_by_node.items():
            if admission.get("result_binding") == "nested_payload":
                continue
            fragment = fragments_by_node.get(node_id)
            if fragment is None or fragment.get("role") != admission.get("role"):
                errors.append(
                    f"closure PASS missing admitted node fragment {node_id}:{admission.get('role')}"
                )
                continue
            if fragment.get("work_status") not in {"DONE", "DONE_WITH_CONCERNS"}:
                errors.append(f"admitted node {node_id} cannot support closure PASS")
                continue
            if admission.get("node_class") == "work":
                if fragment.get("gate_verdict") not in {"PASS", "NOT_APPLICABLE"}:
                    errors.append(f"admitted work node {node_id} cannot support closure PASS")
            elif fragment.get("gate_verdict") != "PASS":
                errors.append(f"admitted verification node {node_id} requires PASS")
            else:
                errors.extend(
                    _verification_fragment_truth_errors(
                        fragment, f"admitted verification node {node_id}"
                    )
                )

        if expected_route is not None:
            if expected_route.get("task_facts", {}).get("runtime_claim") and (
                baseline.get("runtime_head") is None
                or baseline.get("runtime_observed_at") is None
            ):
                errors.append("runtime claim closure requires runtime baseline identity/time")
            for requirement in expected_required_nodes:
                if requirement["role"] != "E4":
                    continue
                fragment = fragments_by_node.get(requirement["node_id"], {})
                test_refs = {
                    ref
                    for ref in fragment.get("evidence_refs", [])
                    if evidence_by_id.get(ref, {}).get("scope") == "test"
                }
                if not test_refs:
                    errors.append(f"E4 node {requirement['node_id']} requires direct test evidence")
                if not test_refs.intersection(valid_check_evidence_refs):
                    errors.append(f"E4 node {requirement['node_id']} requires an EXECUTED/REUSED check")
                elif not any(
                    check_executor_by_evidence.get(ref) == "E4"
                    for ref in test_refs & valid_check_evidence_refs
                ):
                    errors.append(
                        f"E4 node {requirement['node_id']} test receipt must bind executor_role=E4"
                    )

            valid_runtime_refs = {
                evidence_id for evidence_id, artifact in valid_observation_artifacts.items()
                if artifact.get("schema_version") == "runtime_observation_receipt_v1"
            } | set(valid_effect_receipts)
            required_ops = [item for item in expected_required_nodes if item["role"] == "OPS"]
            if required_ops and not valid_runtime_refs:
                errors.append("runtime/operations closure PASS requires fresh runtime evidence")
            for requirement in required_ops:
                fragment = fragments_by_node.get(requirement["node_id"], {})
                if not any(
                    ref in valid_runtime_refs
                    for ref in fragment.get("evidence_refs", [])
                ):
                    errors.append(
                        f"OPS node {requirement['node_id']} requires direct runtime evidence"
                    )

            if expected_route["task_facts"].get("end_to_end_claim"):
                typed_outcome_refs = {
                    evidence_id for evidence_id, artifact in valid_observation_artifacts.items()
                    if artifact.get("schema_version") == "business_outcome_receipt_v1"
                }
                accepted_outcome_refs = {
                    ref
                    for item in packet.get("acceptance", [])
                    if item.get("status") == "PASS"
                    for ref in item.get("evidence_refs", [])
                    if ref in typed_outcome_refs
                }
                if not accepted_outcome_refs:
                    errors.append("end-to-end closure PASS requires direct outcome evidence")
                for requirement in expected_required_nodes:
                    if requirement["role"] != "QA":
                        continue
                    fragment = fragments_by_node.get(requirement["node_id"], {})
                    if not any(
                        ref in typed_outcome_refs
                        for ref in fragment.get("evidence_refs", [])
                    ):
                        errors.append("QA end-to-end PASS requires direct outcome evidence")

            errors.extend(
                validate_deploy_effect_binding(
                    packet,
                    expected_route,
                    fragments_by_node,
                    evidence_by_id,
                    valid_effect_receipts,
                )
            )
        if runtime_evidence and any(
            not all(evidence.get(field) for field in ("host", "environment", "observed_at", "expiry"))
            for evidence in runtime_evidence
        ):
            errors.append("runtime PASS evidence requires host, environment, observed_at, and expiry")
        if adjudicated_at is not None:
            for evidence in runtime_evidence:
                try:
                    observed = _parse_timestamp(str(evidence["observed_at"]))
                    expiry = _parse_timestamp(str(evidence["expiry"]))
                    if not observed <= adjudicated_at < expiry:
                        errors.append("runtime PASS evidence is stale at adjudicated_at")
                except (KeyError, TypeError, ValueError):
                    pass
        effects = packet.get("side_effects", {})
        side_effect_class = (expected_route or {}).get("task_facts", {}).get(
            "side_effect_class", "none"
        )
        if side_effect_class == "none" and any(effects.values()):
            errors.append("side_effect_class=none contradicts recorded effects")
        if effects.get("repo_mutation") and side_effect_class not in {
            "repo_write", "docs_write", "local_test"
        }:
            errors.append("repo mutation is outside the routed side_effect_class")
        if (
            side_effect_class in {"repo_write", "docs_write", "local_test"}
            and packet.get("disposition") == "CHANGED"
            and not effects.get("repo_mutation")
        ):
            errors.append("routed source-write change must record repo_mutation=true")
        if side_effect_class == "deploy" and not effects.get("runtime_contact"):
            errors.append("successful deploy closure must record runtime_contact=true")
        source_change_refs = {
            evidence_id for evidence_id, artifact in valid_observation_artifacts.items()
            if artifact.get("schema_version") == "source_change_receipt_v1"
        } | set(captures.get("changes", {}))
        captured_change_ids = captures.get("change_order", [])
        captured_change_records = [
            captures.get("changes", {}).get(evidence_id)
            for evidence_id in captured_change_ids
            if evidence_id in captures.get("changes", {})
        ]
        if effects.get("repo_mutation"):
            if packet.get("disposition") != "CHANGED":
                errors.append("repo mutation requires CHANGED disposition")
            if not source_change_refs:
                errors.append("repo mutation requires a typed source-change receipt")
            if packet.get("gate_verdict") == "PASS" and not captured_change_records:
                errors.append("repo mutation PASS requires an ordered repository change chain")
            elif captured_change_records:
                errors.extend(
                    validate_repository_change_chain(
                        captured_change_records,
                        expected_writer_scopes=writer_scopes,
                        require_final_current=True,
                    )
                )
        elif source_change_refs:
            errors.append("source-change receipt contradicts repo_mutation=false")
        if packet.get("disposition") == "NO_CHANGE_NEEDED" and any(effects.values()):
            errors.append("NO_CHANGE_NEEDED contradicts recorded side effects")
        if (
            expected_route is not None
            and expected_route.get("task_facts", {}).get("task_shape")
            in {"implementation", "feature", "change", "bug", "fix", "refactor", "migration"}
            and packet.get("disposition") == "CHANGED"
            and not effects.get("repo_mutation")
        ):
            errors.append("changed implementation closure must record repo_mutation=true")
        if effects.get("runtime_contact") and not valid_runtime_refs:
            errors.append("runtime contact requires a typed runtime/effect receipt")
        valid_external_refs = {
            evidence_id for evidence_id, artifact in valid_observation_artifacts.items()
            if artifact.get("schema_version") == "business_outcome_receipt_v1"
            and evidence_by_id.get(evidence_id, {}).get("scope") == "external"
        }
        if effects.get("private_external_contact") and not valid_external_refs:
            errors.append(
                "private external contact requires a typed external observation receipt"
            )
        if effects.get("broker_effect"):
            errors.append(
                "broker effect cannot PASS: broker_probe_adapter_v1 has no closure-grade receipt implementation"
            )

        unsupported_effects = [
            node.get("id") for node in (expected_route or {}).get("nodes", [])
            if node.get("kind") == "unsupported_effect"
        ]
        if unsupported_effects:
            errors.append(
                f"unsupported effect route cannot PASS: {sorted(unsupported_effects)}"
            )

    if isinstance(context_plan, dict) and isinstance(task_contract_digest, str):
        errors.extend(
            validate_closure_trust(
                packet,
                captures=captures,
                evidence_by_id=evidence_by_id,
                context_plan=context_plan,
                task_contract_digest=task_contract_digest,
                expected_route=expected_route,
                fragments_by_node=fragments_by_node,
            )
        )
    errors.extend(
        validate_consumption_binding(
            packet, packet.get("role_fragments", []), expected_route, captures
        )
    )
    errors.extend(validate_execution_attestations(
        gate_verdict=str(packet.get("gate_verdict", "")),
        captures=captures,
        observation_artifacts=valid_observation_artifacts,
        effect_receipts=valid_effect_receipts,
        verifier=execution_attestation_verifier,
    ))
    return errors


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
