"""Closure binding for the profit-diagnosis controller and admitted fragments."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from agent_governance_execution import DIGEST_RE
from agent_governance_profit_payloads import (
    valid_evidence_payload as _valid_evidence_payload,
    valid_fact as _valid_fact,
    validate_map_lineage,
    validate_probe_lineage,
)
from agent_governance_profit_external import (
    EXT_CAPTURE_DEBT,
    validate_ext_capture_lineage,
)
from agent_governance_registry import load_registry, native_agent_binding
from agent_governance_workflow_identity import requested_logical_role
from agent_governance_workflow_capture import collect_bound_workflow_capture
from agent_governance_external_evidence import ExternalEvidenceVerifier


CONTROL_FIELDS = {
    "schema_version", "baseline", "baseline_digest", "scope", "focus",
    "task_contract_digest", "context_artifact_digest", "budget_authority_digest",
    "hard_stops",
    "priors_digest", "claim_inputs_digest",
    "expected_evidence_axes", "admitted_evidence_axes", "expected_probe_axes",
    "admitted_probe_axes", "deferred_probe_axes", "fragment_bindings",
    "fragment_digests", "coverage_debt", "map_node_id", "decision_ready",
    "pass_eligible", "unverified_projection", "envelope", "workflow_contract_digest",
    "call_manifest_digest", "workflow_wave_record_digest",
}
DEBT_FIELDS = {"kind", "id", "reason", "owner"}
ENVELOPE_FIELDS = {
    "accounting_basis", "max_context_tokens_per_call",
    "max_prompt_utf8_bytes_per_call", "max_workflow_planned_input_tokens",
    "max_unique_nodes", "max_call_attempts", "retry_budget", "retry_capacity",
    "estimated_tokens_per_evidence", "estimated_tokens_per_probe",
    "estimated_tokens_for_map", "planned_input_tokens", "planned_unique_nodes",
    "planned_call_attempts",
}
def _time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _debt_projection(item: dict[str, Any]) -> str:
    return "profit_diagnosis_debt:" + _canonical_json(item)


def _workflow_capture(
    packet: dict[str, Any], control: dict[str, Any], errors: list[str],
    external_evidence_verifier: ExternalEvidenceVerifier | None,
):
    calls, wave, context, captured, capture_errors = collect_bound_workflow_capture(
        packet, control, label="profit diagnosis",
        external_evidence_verifier=external_evidence_verifier,
    )
    errors.extend(capture_errors)
    return calls, wave, context, captured


def _fact_debt(axis: str, item: dict[str, Any]) -> dict[str, str]:
    scope = item.get("scope")
    return {"kind": "evidence_fact", "id": f"{axis}:{item.get('id')}", "owner": axis,
            "reason": f"{scope} observation requires platform/external-attested capture"}


def _fact_binding_errors(facts, axis, captures, evidence_by_id, adjudicated_at, debt):
    errors, refs, valid_fresh = [], [], 0
    adjudicated = _time(adjudicated_at)
    for item in facts if isinstance(facts, list) else []:
        if not _valid_fact(item, _time):
            continue
        ref, scope = item.get("evidence_ref"), item.get("scope")
        if ref and ref not in refs:
            refs.append(ref)
        observed = _time(item.get("observed_at"))
        if adjudicated is None or observed is None or observed > adjudicated:
            errors.append(f"profit diagnosis {axis} fact {item.get('id')} is future-dated")
        if scope in {"runtime", "external"} and _fact_debt(axis, item) not in debt:
            errors.append(f"profit diagnosis {axis} fact {item.get('id')} lacks exact attestation debt")
        if item.get("classification") != "FACT":
            continue
        artifact = None
        if scope in {"source", "data"}:
            artifact = captures["repositories"].get(ref) or captures["commands"].get(ref)
        elif scope == "runtime" and ref in captures["runtime_attested"] | captures["outcome_attested"]:
            artifact = captures["telemetry"].get(ref)
        elif scope == "external" and ref in captures["external_policy_attested"] | captures["outcome_attested"]:
            artifact = captures["telemetry"].get(ref)
        if artifact is None:
            errors.append(f"profit diagnosis {axis} FACT {item.get('id')} lacks scope-appropriate captured evidence")
            continue
        captured_at = artifact.get("observed_at") or artifact.get("completed_at") or artifact.get("body", {}).get("observed_at")
        if item.get("observed_at") != captured_at:
            errors.append(f"profit diagnosis {axis} FACT {item.get('id')} observed_at differs from capture")
            continue
        expiry = _time(evidence_by_id.get(ref, {}).get("expiry"))
        age = (adjudicated - observed).total_seconds() if adjudicated and observed else -1
        expected = "expired" if expiry and adjudicated >= expiry else "fresh" if 0 <= age <= 900 else "recent" if age <= 14400 else "stale"
        if item.get("freshness") != expected:
            errors.append(f"profit diagnosis {axis} FACT {item.get('id')} freshness/TTL is invalid")
        elif expected in {"fresh", "recent"}:
            valid_fresh += 1
    if not valid_fresh:
        required = {"kind": "evidence_fact", "id": f"{axis}:fresh_fact", "owner": axis,
                    "reason": "no fresh source/data FACT with typed evidence_ref"}
        if required not in debt:
            errors.append(f"profit diagnosis {axis} has no fresh captured FACT or exact debt")
    return errors, refs


def _call_binding(call_map, fragment: dict[str, Any], result: Any) -> list[str]:
    call = call_map.get(str(fragment.get("producer_call_ref")))
    node = str(fragment.get("node_id"))
    if fragment.get("producer_record_kind") != "workflow_call_record_v1" or call is None:
        return [f"profit diagnosis {node} producer call is missing"]
    errors = []
    if (
        call.get("node_id") != node or call.get("parsed_result_digest") != _digest(result)
        or call.get("record_digest") != fragment.get("producer_call_receipt_digest")
    ):
        errors.append(f"profit diagnosis {node} producer call/result binding is invalid")
    if call.get("returned_null") is not False or requested_logical_role(call.get("requested", {})) != fragment.get("role"):
        errors.append(f"profit diagnosis {node} producer role/null state is invalid")
    return errors


def _axis_list(
    value: Any,
    *,
    allowed: set[str],
    field: str,
    errors: list[str],
) -> list[str]:
    if not isinstance(value, list) or any(item not in allowed for item in value):
        errors.append(f"profit diagnosis {field} is invalid")
        return []
    if len(value) != len(set(value)):
        errors.append(f"profit diagnosis {field} contains duplicates")
    return value


def validate_profit_diagnosis_binding(
    packet: dict[str, Any],
    expected_route: dict[str, Any] | None,
    admitted_by_node: dict[str, dict[str, Any]],
    fragments_by_node: dict[str, dict[str, Any]],
    *,
    external_evidence_verifier: ExternalEvidenceVerifier | None = None,
) -> list[str]:
    """Reject cherry-picking or debt omission from profit diagnosis results."""

    surfaces = set((expected_route or {}).get("task_facts", {}).get("surfaces", []))
    if "profit_diagnosis" not in surfaces:
        return []
    errors: list[str] = []
    contract = load_registry().get("workflow_contracts", {}).get("profit_diagnosis_v1", {})
    controller_node = contract.get("controller_node_id")
    controller_role = contract.get("controller_role")
    evidence_contract = contract.get("evidence_axes", [])
    probe_contract = contract.get("probe_axes", [])
    if not controller_node or not controller_role:
        return ["profit diagnosis Registry contract is missing"]
    fragment = fragments_by_node.get(controller_node)
    if not isinstance(fragment, dict) or fragment.get("role") != controller_role:
        return ["profit diagnosis controller fragment is missing"]
    control = fragment.get("payload")
    if not isinstance(control, dict) or control.get("schema_version") != "profit_diagnosis_control_v1":
        return ["profit diagnosis controller payload is invalid"]
    if set(control) != CONTROL_FIELDS:
        errors.append("profit diagnosis controller fields do not match contract")
    call_map, wave, context_artifact, captures = _workflow_capture(
        packet, control, errors, external_evidence_verifier,
    )
    evidence_by_id = {
        item.get("id"): item for item in packet.get("evidence", []) if isinstance(item, dict)
    }
    if (
        fragment.get("context_artifact_digest") != context_artifact.get("artifact_digest")
        or fragment.get("producer_record_kind") != "workflow_wave_record_v1"
        or fragment.get("producer_call_ref") != control.get("workflow_wave_record_digest")
        or fragment.get("producer_call_receipt_digest") != control.get("workflow_wave_record_digest")
    ):
        errors.append("profit diagnosis controller producer wave binding is invalid")
    context_plan = context_artifact.get("canonical_plan")
    try:
        context_value = json.loads(context_plan) if isinstance(context_plan, str) else {}
    except json.JSONDecodeError:
        context_value = {}
    context_contract = context_value.get("task_contract", {})
    if (
        control.get("task_contract_digest") != context_artifact.get("task_contract_digest")
        or control.get("context_artifact_digest") != context_artifact.get("artifact_digest")
        or control.get("budget_authority_digest") != context_artifact.get("budget_authority_digest")
        or control.get("hard_stops") != context_contract.get("hard_stops")
    ):
        errors.append("profit diagnosis controller is not bound to canonical Context authority/hard_stops")
    if control.get("baseline") != packet.get("baseline"):
        errors.append("profit diagnosis controller baseline does not match closure")
    if control.get("baseline_digest") != _digest(packet.get("baseline")):
        errors.append("profit diagnosis baseline digest is not canonical")
    if not isinstance(control.get("scope"), str) or not control.get("scope", "").strip():
        errors.append("profit diagnosis scope is empty")
    task_facts = (expected_route or {}).get("task_facts", {})
    if control.get("scope") != task_facts.get("scope"):
        errors.append("profit diagnosis scope differs from admitted task contract")
    if control.get("focus") != task_facts.get("focus", ""):
        errors.append("profit diagnosis focus differs from admitted task contract")
    priors_digest = control.get("priors_digest")
    if not DIGEST_RE.fullmatch(str(priors_digest or "")):
        errors.append("profit diagnosis priors digest is invalid")
    claim_inputs = task_facts.get("claim_inputs", {})
    if (
        not isinstance(claim_inputs, dict)
        or claim_inputs.get("profit_priors") != priors_digest
        or control.get("claim_inputs_digest") != _digest(claim_inputs)
    ):
        errors.append("profit diagnosis priors are not bound by task claim_inputs")
    priors_refs = [
        ref for ref in packet.get("authority_refs", [])
        if ref.get("source") == "profit_diagnosis_priors_v1"
    ]
    if (
        len(priors_refs) != 1
        or priors_refs[0].get("digest") != priors_digest
        or priors_refs[0].get("scope") != "profit_diagnosis:priors"
        or priors_refs[0].get("subject") != "profit_diagnosis_priors"
        or priors_refs[0].get("class") != "claim_evidence"
        or priors_refs[0].get("strength") != "derived"
        or priors_refs[0].get("source_ref")
        != "task_contract:claim_inputs:profit_priors"
        or not priors_refs[0].get("expiry")
    ):
        errors.append("profit diagnosis priors are not hash/scope-bound authority")
    elif _digest(priors_refs[0].get("value")) != priors_digest:
        errors.append(
            "profit diagnosis priors value does not match its canonical digest"
        )

    evidence_allowed = set(evidence_contract)
    probe_allowed = set(probe_contract)
    expected_evidence = _axis_list(
        control.get("expected_evidence_axes"), allowed=evidence_allowed,
        field="expected_evidence_axes", errors=errors,
    )
    admitted_evidence = _axis_list(
        control.get("admitted_evidence_axes"), allowed=evidence_allowed,
        field="admitted_evidence_axes", errors=errors,
    )
    expected_probes = _axis_list(
        control.get("expected_probe_axes"), allowed=probe_allowed,
        field="expected_probe_axes", errors=errors,
    )
    admitted_probes = _axis_list(
        control.get("admitted_probe_axes"), allowed=probe_allowed,
        field="admitted_probe_axes", errors=errors,
    )
    deferred_probes = _axis_list(
        control.get("deferred_probe_axes"), allowed=probe_allowed,
        field="deferred_probe_axes", errors=errors,
    )
    if expected_evidence != evidence_contract:
        errors.append("profit diagnosis expected evidence axes drift from Registry")
    if expected_probes != probe_contract:
        errors.append("profit diagnosis expected probe axes drift from Registry")
    if set(admitted_probes) & set(deferred_probes) or set(admitted_probes) | set(deferred_probes) != set(expected_probes):
        errors.append("profit diagnosis admitted/deferred probes do not partition contract")

    debt = control.get("coverage_debt")
    if not isinstance(debt, list):
        errors.append("profit diagnosis coverage debt must be a list")
        debt = []
    else:
        identities: set[tuple[Any, Any, Any]] = set()
        for item in debt:
            if not isinstance(item, dict) or set(item) != DEBT_FIELDS or not all(
                isinstance(item.get(field), str) and item.get(field)
                for field in DEBT_FIELDS
            ):
                errors.append("profit diagnosis coverage debt item is invalid")
                continue
            identity = (item["kind"], item["id"], item["owner"])
            if identity in identities:
                errors.append("profit diagnosis coverage debt identity is duplicated")
            identities.add(identity)
    for axis in set(expected_evidence) - set(admitted_evidence):
        if not any(
            item.get("kind") == "mandatory_evidence"
            and item.get("id") == axis
            and item.get("owner") == axis
            for item in debt
        ):
            errors.append(f"profit diagnosis missing evidence axis {axis} lacks debt")
    for axis in deferred_probes:
        expected_owner = "QC" if axis == "EXT" else axis
        if not any(
            item.get("kind") == "axis"
            and item.get("id") == axis
            and item.get("owner") == expected_owner
            for item in debt
        ):
            errors.append(f"profit diagnosis deferred probe {axis} lacks debt")

    bindings = control.get("fragment_bindings")
    digests = control.get("fragment_digests")
    if not isinstance(bindings, list) or not isinstance(digests, dict):
        errors.append("profit diagnosis fragment bindings/digests are invalid")
        bindings, digests = [], {}
    probe_roles = {axis: ("QC" if axis == "EXT" else axis) for axis in probe_contract}
    map_node = control.get("map_node_id")
    expected_bindings = [
        {
            "node_id": f"evidence:{axis}",
            "role": axis,
            **native_agent_binding(axis, "verification"),
            "node_class": "verification",
            "reason": "profit diagnosis admitted evidence/probe",
        }
        for axis in evidence_contract
        if axis in admitted_evidence
    ] + [
        {
            "node_id": f"probe:{axis}",
            "role": probe_roles[axis],
            **native_agent_binding(probe_roles[axis], "verification"),
            "node_class": "verification",
            "reason": "profit diagnosis admitted evidence/probe",
        }
        for axis in probe_contract
        if axis in admitted_probes and f"probe:{axis}" in fragments_by_node
    ]
    if map_node == "map:PA":
        expected_bindings.append(
            {
                "node_id": "map:PA",
                "role": "PA",
                **native_agent_binding("PA", "verification"),
                "node_class": "verification",
                "reason": "profit map synthesis",
            }
        )
    binding_fields = (
        "node_id", "role", "native_agent", "node_class", "permission", "reason",
    )
    profit_admissions = [
        {field: admission.get(field) for field in binding_fields}
        for node_id, admission in admitted_by_node.items()
        if node_id.startswith(("evidence:", "probe:")) or node_id == "map:PA"
    ]
    if bindings != expected_bindings or profit_admissions != expected_bindings:
        errors.append(
            "profit diagnosis fragment bindings are not the canonical admitted inventory"
        )
    bound_nodes: set[str] = set()
    seen_fact_ids: set[str] = set()
    seen_nested_ids: set[str] = set()
    opportunities_by_id: dict[str, dict[str, Any]] = {}
    ext_capture_ready = False
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) != {
            "node_id", "role", "native_agent", "node_class", "permission", "reason",
        }:
            errors.append("profit diagnosis fragment binding shape is invalid")
            continue
        node_id = binding.get("node_id")
        if not node_id or node_id in bound_nodes or binding.get("node_class") != "verification":
            errors.append("profit diagnosis fragment binding identity is invalid")
            continue
        bound_nodes.add(node_id)
        closure_admission = admitted_by_node.get(node_id)
        if not isinstance(closure_admission, dict) or {
            field: closure_admission.get(field) for field in binding_fields
        } != binding:
            errors.append(f"profit diagnosis fragment {node_id} is not closure-admitted")
        bound = fragments_by_node.get(node_id)
        if not isinstance(bound, dict) or bound.get("role") != binding.get("role"):
            errors.append(f"profit diagnosis fragment {node_id} is missing")
            continue
        if digests.get(node_id) != _digest(bound):
            errors.append(f"profit diagnosis fragment {node_id} digest is invalid")
        payload = bound.get("payload", {})
        errors.extend(_call_binding(call_map, bound, payload))
        if wave and wave.get("result_fragment_digests", {}).get(node_id) != _digest(bound):
            errors.append(f"profit diagnosis fragment {node_id} differs from workflow wave result map")
        if bound.get("consumption", {}).get("measurement_status") != "unavailable":
            errors.append(f"profit diagnosis fragment {node_id} cannot self-attest actual consumption")
        if node_id.startswith("evidence:") and not _valid_evidence_payload(
            payload, node_id.split(":", 1)[1], _time
        ):
            errors.append(
                f"profit diagnosis evidence fragment {node_id} payload is invalid"
            )
        elif node_id.startswith("evidence:"):
            axis = node_id.split(":", 1)[1]
            fact_ids = [item.get("id") for item in payload.get("facts", []) if isinstance(item, dict)]
            if seen_fact_ids.intersection(fact_ids):
                errors.append("profit diagnosis fact ids must be globally unique")
            seen_fact_ids.update(fact_ids)
            fact_errors, expected_refs = _fact_binding_errors(
                payload.get("facts"), axis, captures, evidence_by_id,
                packet.get("adjudicated_at"), debt,
            )
            errors.extend(fact_errors)
            if bound.get("evidence_refs") != expected_refs:
                errors.append(f"profit diagnosis evidence fragment {node_id} evidence_refs differ from facts")
        if node_id.startswith("probe:"):
            axis = node_id.split(":", 1)[1]
            probe_errors, expected_refs = validate_probe_lineage(
                payload,
                axis,
                evidence_ids=set(evidence_by_id),
                seen_content_ids=seen_nested_ids,
                opportunities_by_id=opportunities_by_id,
            )
            errors.extend(probe_errors)
            if axis == "EXT":
                ext_errors, ext_capture_ready = validate_ext_capture_lineage(
                    payload,
                    captures=captures,
                    evidence_by_id=evidence_by_id,
                    adjudicated_at=packet.get("adjudicated_at"),
                    coverage_debt=debt,
                    claim_inputs=task_facts.get("claim_inputs", {}),
                )
                errors.extend(ext_errors)
            if expected_refs and bound.get("evidence_refs") != expected_refs:
                errors.append(
                    f"profit diagnosis probe fragment {node_id} "
                    "evidence_refs differ from nested content"
                )
    if set(digests) != bound_nodes:
        errors.append("profit diagnosis fragment digest inventory differs from bindings")

    for axis in admitted_evidence:
        if f"evidence:{axis}" not in bound_nodes:
            errors.append(f"profit diagnosis admitted evidence {axis} has no bound fragment")
            continue
        evidence_payload = fragments_by_node[f"evidence:{axis}"].get("payload", {})
        evidence_fragment = fragments_by_node[f"evidence:{axis}"]
        evidence_gaps = evidence_payload.get("gaps", [])
        fact_concerns = [
            item["reason"] for item in debt
            if item.get("owner") == axis
            and item.get("kind") in {"evidence_fact", "mandatory_evidence"}
        ]
        evidence_concerns = evidence_gaps + fact_concerns
        expected_evidence_status = {
            "work_status": evidence_payload.get("work_status"),
            "gate_verdict": (
                "PASS"
                if evidence_payload.get("work_status") == "DONE" and not evidence_concerns
                else "CONDITIONAL"
            ),
            "classification": "INFERENCE" if evidence_concerns else "FACT",
            "confidence": "med" if evidence_concerns else "high",
            "concerns": evidence_concerns,
        }
        if any(
            evidence_fragment.get(field) != expected
            for field, expected in expected_evidence_status.items()
        ):
            errors.append(
                f"profit diagnosis evidence fragment evidence:{axis} "
                "status disagrees with payload"
            )
        if evidence_payload.get("work_status") != "DONE" and not any(
            item.get("kind") == "mandatory_evidence"
            and item.get("id") == axis
            and item.get("owner") == axis
            for item in debt
        ):
            errors.append(
                f"profit diagnosis mandatory evidence {axis} is incomplete without debt"
            )
        gaps = evidence_payload.get("gaps", [])
        if isinstance(gaps, list):
            for index, gap in enumerate(gaps):
                if not any(
                    item.get("kind") == "evidence_gap"
                    and item.get("id") == f"{axis}:{index + 1}"
                    and item.get("reason") == gap
                    and item.get("owner") == axis
                    for item in debt
                ):
                    errors.append(
                        f"profit diagnosis evidence gap {axis}:{index + 1} lacks debt"
                    )
    for axis in admitted_probes:
        expected_owner = "QC" if axis == "EXT" else axis
        probe_debt_present = any(
            item.get("kind") == "probe"
            and item.get("id") == axis
            and item.get("owner") == expected_owner
            for item in debt
        )
        if axis == "EXT" and EXT_CAPTURE_DEBT in debt:
            probe_debt_present = True
        if f"probe:{axis}" not in bound_nodes:
            if not probe_debt_present:
                errors.append(
                    f"profit diagnosis admitted probe {axis} vanished without debt"
                )
            continue
        probe_payload = fragments_by_node[f"probe:{axis}"].get("payload", {})
        probe_fragment = fragments_by_node[f"probe:{axis}"]
        probe_complete = (
            probe_payload.get("work_status") == "DONE"
            and probe_payload.get("verdict") != "BLOCKED"
            and (axis != "EXT" or ext_capture_ready)
        )
        if axis == "EXT" and not ext_capture_ready:
            probe_concerns = [EXT_CAPTURE_DEBT["reason"]]
        else:
            probe_concerns = [] if probe_complete else [
                f"status={probe_payload.get('work_status')}; "
                f"verdict={probe_payload.get('verdict')}: "
                f"{probe_payload.get('negative_search_summary')}"
            ]
        expected_probe_status = {
            "work_status": probe_payload.get("work_status"),
            "gate_verdict": (
                "PASS" if probe_complete
                else "CONDITIONAL" if axis == "EXT"
                else "UNVERIFIED"
            ),
            "classification": "INFERENCE" if probe_concerns else "FACT",
            "confidence": "med" if probe_concerns else "high",
            "concerns": probe_concerns,
        }
        if any(
            probe_fragment.get(field) != expected
            for field, expected in expected_probe_status.items()
        ):
            errors.append(
                f"profit diagnosis probe fragment probe:{axis} "
                "status disagrees with payload"
            )
        if (
            probe_payload.get("work_status") != "DONE"
            or probe_payload.get("verdict") == "BLOCKED"
        ) and not probe_debt_present:
            errors.append(
                f"profit diagnosis admitted probe {axis} is incomplete without debt"
            )
    if map_node not in {None, "map:PA"}:
        errors.append("profit diagnosis map node id is invalid")
    if map_node is None:
        if not any(item.get("kind") == "map" and item.get("id") == "PA" for item in debt):
            errors.append("profit diagnosis missing map lacks debt")
    elif map_node not in bound_nodes:
        errors.append("profit diagnosis declared map fragment is missing")

    envelope = control.get("envelope")
    integer_envelope_fields = ENVELOPE_FIELDS - {"accounting_basis"}
    if not isinstance(envelope, dict) or set(envelope) != ENVELOPE_FIELDS or any(
        not isinstance(envelope.get(field), int) or isinstance(envelope.get(field), bool)
        for field in integer_envelope_fields
    ) or envelope.get("accounting_basis") != "utf8_bytes_div4_planned_lower_bound_v1":
        errors.append("profit diagnosis envelope is invalid")
    else:
        estimates = (
            envelope["estimated_tokens_per_evidence"],
            envelope["estimated_tokens_per_probe"],
            envelope["estimated_tokens_for_map"],
        )
        try:
            context_authority = json.loads(context_artifact["budget_authority_canonical"])
        except (KeyError, TypeError, json.JSONDecodeError):
            context_authority = {}
        if any(
            envelope.get(field) != context_authority.get(field)
            for field in (
                "accounting_basis", "max_context_tokens_per_call",
                "max_prompt_utf8_bytes_per_call", "max_workflow_planned_input_tokens",
                "max_unique_nodes", "max_call_attempts", "retry_budget",
            )
        ):
            errors.append("profit diagnosis envelope differs from Context budget authority")
        if (
            envelope["max_unique_nodes"] < 4
            or envelope["max_call_attempts"] != envelope["max_unique_nodes"] + envelope["retry_budget"]
            or envelope["max_workflow_planned_input_tokens"] <= 0
            or envelope["retry_budget"] < 0
            or envelope["estimated_tokens_per_evidence"] < 20_000
            or envelope["estimated_tokens_per_probe"] < 24_000
            or envelope["estimated_tokens_for_map"] < 30_000
            or envelope["planned_input_tokens"] > envelope["max_workflow_planned_input_tokens"]
            or envelope["planned_unique_nodes"] > envelope["max_unique_nodes"]
            or envelope["planned_call_attempts"] > envelope["max_call_attempts"]
        ):
            errors.append("profit diagnosis envelope exceeds governed bounds")
        mandatory_calls = len(evidence_contract) + 1
        context_floor = max(
            (
                task.get("compiler_estimated_input_tokens", 0)
                for task in (wave or {}).get("admitted_tasks", [])
                if isinstance(task, dict)
            ),
            default=0,
        )
        effective_evidence = max(context_floor, envelope["estimated_tokens_per_evidence"])
        effective_probe = max(context_floor, envelope["estimated_tokens_per_probe"])
        effective_map = max(context_floor, envelope["estimated_tokens_for_map"])
        if max(effective_evidence, effective_probe, effective_map) >= envelope["max_context_tokens_per_call"]:
            errors.append("profit diagnosis per-call context cap is not respected")
        mandatory_tokens = len(evidence_contract) * effective_evidence + effective_map
        retry_estimate = max(effective_evidence, effective_probe, effective_map)
        retry_capacity_by_tokens = max(
            0,
            (envelope["max_workflow_planned_input_tokens"] - mandatory_tokens) // retry_estimate,
        )
        expected_retry_capacity = min(
            envelope["retry_budget"],
            max(0, envelope["max_call_attempts"] - mandatory_calls),
            retry_capacity_by_tokens,
        )
        if envelope["retry_capacity"] != expected_retry_capacity:
            errors.append("profit diagnosis retry capacity disagrees with its envelope")
        expected_tokens = (
            mandatory_tokens
            + expected_retry_capacity * retry_estimate
            + len(admitted_probes) * effective_probe
        )
        if envelope["planned_input_tokens"] != expected_tokens:
            errors.append("profit diagnosis planned token estimate is inconsistent")
        expected_unique = mandatory_calls + len(admitted_probes)
        expected_attempts = expected_unique + expected_retry_capacity
        if envelope["planned_unique_nodes"] != expected_unique:
            errors.append("profit diagnosis planned unique nodes are inconsistent")
        if envelope["planned_call_attempts"] != expected_attempts:
            errors.append("profit diagnosis planned call attempts are inconsistent")

    expected_projection = [_debt_projection(item) for item in debt]
    if control.get("unverified_projection") != expected_projection:
        errors.append("profit diagnosis unverified projection omits or changes debt")
    if fragment.get("concerns") != expected_projection:
        errors.append("profit diagnosis controller concerns omit or change debt")
    map_fragment = fragments_by_node.get("map:PA", {})
    map_payload = map_fragment.get("payload", {}) if isinstance(map_fragment, dict) else {}
    probe_payloads = {
        axis: fragments_by_node.get(f"probe:{axis}", {}).get("payload", {})
        for axis in admitted_probes
    }
    map_errors, expected_map_refs, map_payload_valid = validate_map_lineage(
        map_payload,
        probe_payloads=probe_payloads,
        opportunities_by_id=opportunities_by_id,
        evidence_ids=set(evidence_by_id),
    )
    if map_node == "map:PA":
        errors.extend(map_errors)
        if expected_map_refs and map_fragment.get("evidence_refs") != expected_map_refs:
            errors.append(
                "profit diagnosis map fragment evidence_refs differ from source lineage"
            )
    map_fragment_ready = bool(
        map_payload_valid
        and not map_errors
        and map_fragment.get("role") == "PA"
        and map_fragment.get("work_status") == "DONE"
        and map_fragment.get("gate_verdict") == "PASS"
        and map_fragment.get("classification") == "FACT"
        and not map_fragment.get("concerns")
        and map_payload.get("schema_version") == "profit_map_v2"
        and map_payload.get("work_status") == "DONE"
        and map_payload.get("decision_ready") is True
        and map_payload.get("coverage_debt") == []
        and bool(map_payload.get("top_moves") or map_payload.get("negative_results"))
    )
    actual_cost_unavailable = bool(
        map_payload_valid
        and map_payload.get("top_moves")
        and any(
            fragments_by_node.get(node_id, {}).get("consumption", {}).get(
                "measurement_status"
            )
            != "measured"
            for node_id in bound_nodes
        )
    )
    if actual_cost_unavailable:
        if not any(
            item.get("kind") == "actual_consumption"
            and item.get("id") == "profit-ranking"
            and item.get("owner") == "AI-E"
            for item in debt
        ):
            errors.append(
                "profit diagnosis ranked moves require actual-consumption debt when telemetry is unavailable"
            )
        map_fragment_ready = False
    map_coverage = map_payload.get("coverage_debt", [])
    if not isinstance(map_coverage, list) or any(
        not isinstance(item, str) or not item for item in map_coverage
    ):
        errors.append("profit diagnosis map coverage debt payload is invalid")
        map_coverage = []
    else:
        for index, item in enumerate(map_coverage):
            if not any(
                debt_item.get("kind") == "map_debt"
                and debt_item.get("id") == f"PA:{index + 1}"
                and debt_item.get("reason") == item
                and debt_item.get("owner") == "PA"
                for debt_item in debt
            ):
                errors.append(
                    "profit diagnosis map coverage debt "
                    f"PA:{index + 1} is not losslessly bound"
                )
    expected_map_debt_reason = None
    if map_node == "map:PA" and map_payload.get("work_status") != "DONE":
        expected_map_debt_reason = f"status={map_payload.get('work_status')}"
    elif (
        map_node == "map:PA"
        and map_payload.get("decision_ready") is not True
        and map_coverage == []
    ):
        expected_map_debt_reason = "decision_ready=false"
    if expected_map_debt_reason and not any(
            item.get("kind") == "map"
            and item.get("id") == "PA"
            and item.get("reason") == expected_map_debt_reason
            and item.get("owner") == "PA"
            for item in debt
    ):
        errors.append("profit diagnosis non-ready map lacks canonical debt")
    if control.get("decision_ready") is True and not map_fragment_ready:
        errors.append("profit diagnosis map readiness disagrees with its bound fragment")
    recomputed_ready = bool(
        not debt
        and set(admitted_evidence) == set(expected_evidence)
        and set(admitted_probes) == set(expected_probes)
        and map_node == "map:PA"
        and map_fragment_ready
    )
    if control.get("decision_ready") is not recomputed_ready:
        errors.append("profit diagnosis decision_ready disagrees with bound fragments/debt")
    if control.get("pass_eligible") is not recomputed_ready:
        errors.append("profit diagnosis pass_eligible disagrees with bound fragments/debt")
    expected_controller_status = {
        "work_status": "DONE" if recomputed_ready else "DONE_WITH_CONCERNS",
        "gate_verdict": "PASS" if recomputed_ready else "CONDITIONAL",
        "classification": "FACT" if recomputed_ready else "INFERENCE",
        "confidence": "high" if recomputed_ready else "med",
    }
    if any(
        fragment.get(field) != expected
        for field, expected in expected_controller_status.items()
    ):
        errors.append("profit diagnosis controller status disagrees with readiness")
    if fragment.get("consumption", {}).get("measurement_status") != "unavailable":
        errors.append("profit diagnosis controller cannot self-attest actual consumption")
    if packet.get("gate_verdict") == "PASS" and not recomputed_ready:
        errors.append("profit diagnosis controller is not PASS-eligible")
    actual_projection = [
        item
        for item in packet.get("unverified", [])
        if isinstance(item, str) and item.startswith("profit_diagnosis_")
    ]
    if actual_projection != expected_projection:
        errors.append("profit diagnosis closure unverified projection is not canonical")
    return errors
