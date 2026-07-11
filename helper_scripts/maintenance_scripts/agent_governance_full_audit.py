"""Closure binding for the Full Audit controller and admitted axis fragments."""

from __future__ import annotations
import hashlib
import json
import re
from typing import Any

from agent_governance_workflow_identity import requested_logical_role
from agent_governance_workflow_budget import workflow_budget_matches_context
from agent_governance_workflow_capture import collect_bound_workflow_capture
from agent_governance_external_evidence import ExternalEvidenceVerifier
from agent_governance_full_audit_dag import (
    adaptive_axes as _adaptive_axes,
    nested_admission_inventory as _nested_admission_inventory,
    nonnegative_integer as _integer,
    parse_time as _parse_time,
)
from agent_governance_registry import load_registry, native_agent_binding

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
CONTROL_FIELDS = {
    "schema_version", "baseline", "scheduler", "selection_surfaces", "run_sequence",
    "adaptive_recall_approved", "adaptive_recall_authority_digest", "expected_axes",
    "admitted_axes", "deferred_axes", "axis_bindings", "axis_fragment_digests",
    "coverage_debt", "coverage_holes", "assumption_count", "disputed_count",
    "decision_changing_findings", "seam_present", "seam_result", "seam_result_digest",
    "seam_call_ref", "seam_call_receipt_digest", "workflow_contract_digest",
    "call_manifest_digest",
    "workflow_wave_record_digest", "pass_eligible", "unverified_projection",
}
AXIS_FIELDS = {
    "schema_version", "audit", "confirmed_decision_claim_ids", "disputed_claim_ids",
    "verification_outcomes", "assumptions_count", "coverage_debt_count",
}
OUTCOME_FIELDS = {
    "claim_id", "claim_key", "axis", "severity", "defect_type", "assertion",
    "evidence", "file", "symbol_anchor", "confirmed", "refuted", "disputed",
    "latent", "reachable", "verifier_dissent", "verifier_votes",
    "verification_calls",
}
VOTE_FIELDS = {
    "view", "refuted", "confidence", "reason", "evidence", "reachable",
    "producer_record_kind", "producer_call_ref", "producer_call_receipt_digest",
}
GOAL_TYPES = {"over-gate", "evolution-blocker", "lineage-gap"}
HIGH_RISK_TYPES = {"auth-bypass", "secret-leak", "missing-gate", "leakage", "replay-misuse"}
CAPABILITY_TYPES = {"over-gate", "evolution-blocker"}
STRUCTURAL_FINDING_FIELDS = ("title", "assertion", "evidence", "file", "symbol_anchor")

def _debt_projection(item: dict[str, Any]) -> str:
    canonical = {
        "id": item.get("id"),
        "kind": item.get("kind"),
        "owner": item.get("owner"),
        "reason": item.get("reason"),
    }
    if item.get("claim_key") is not None:
        canonical["claim_key"] = item.get("claim_key")
    return "full_audit_debt:" + _canonical_json(canonical)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _expected_projection(control: dict[str, Any]) -> list[str]:
    projection = [
        _debt_projection(item)
        for item in control.get("coverage_debt", [])
        if isinstance(item, dict)
    ]
    projection.extend(
        "full_audit_hole:" + _canonical_json({"axis": axis})
        for axis in control.get("coverage_holes", [])
    )
    if control.get("disputed_count", 0):
        projection.append(
            "full_audit_disputed:" + _canonical_json({"count": control["disputed_count"]})
        )
    if control.get("decision_changing_findings", 0):
        projection.append(
            "full_audit_decision_changing_findings:"
            + _canonical_json({"count": control["decision_changing_findings"]})
        )
    if control.get("seam_present") is False:
        projection.append("full_audit_seam_missing")
    return projection


def _unique_axis_list(value: Any, allowed: set[str], field: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(item not in allowed for item in value):
        errors.append(f"full audit {field} must contain only contract axes")
        return []
    if len(value) != len(set(value)):
        errors.append(f"full audit {field} contains duplicate axes")
    return value


def _is_decision_outcome(outcome: dict[str, Any]) -> bool:
    return outcome.get("severity") in {"CRITICAL", "HIGH"} or (
        outcome.get("severity") == "MEDIUM"
        and bool(set(outcome.get("defect_type", [])) & GOAL_TYPES)
    )


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\\", "/").strip().lower().split())


def _normalize_file(value: Any) -> str:
    path = _normalize(value)
    marker = path.rfind("/srv/")
    if marker >= 0:
        return path[marker + 5 :]
    return path[4:] if path.startswith("srv/") else path


def _claim_key(value: dict[str, Any]) -> str:
    return "::".join(
        (
            _normalize_file(value.get("file")),
            _normalize(value.get("symbol_anchor")),
            _normalize(value.get("assertion")),
            _normalize(value.get("evidence")),
        )
    )


def _structural_finding_debt(axis: str, finding: dict[str, Any]) -> dict[str, str]:
    missing = [
        field
        for field in STRUCTURAL_FINDING_FIELDS
        if not str(finding.get(field) or "").strip()
    ]
    return {
        "kind": "claim",
        "id": "invalid:" + _digest({"axis": axis, "finding": finding}),
        "owner": axis,
        "reason": "missing deterministic evidence fields: " + ",".join(missing),
    }


def _workflow_capture(
    packet: dict[str, Any], control: dict[str, Any], errors: list[str],
    external_evidence_verifier: ExternalEvidenceVerifier | None,
):
    calls, wave, context, captured, capture_errors = collect_bound_workflow_capture(
        packet, control, label="full audit",
        external_evidence_verifier=external_evidence_verifier,
    )
    errors.extend(capture_errors)
    if wave is not None:
        budget = wave.get("budget_authority", {})
        if not workflow_budget_matches_context(budget, context):
            errors.append("full audit wave budget authority differs from admitted Context authority")
    return calls, wave, context


def _call_binding(call_map, fragment, *, node: str, role: str, result: Any) -> list[str]:
    call = call_map.get(str(fragment.get("producer_call_ref")))
    expected = {
        "node_id": node, "parsed_result_digest": _digest(result),
        "record_digest": fragment.get("producer_call_receipt_digest"),
    }
    errors = []
    if fragment.get("producer_record_kind") != "workflow_call_record_v1" or call is None:
        return [f"full audit {node} producer call is missing"]
    if any(call.get(field) != value for field, value in expected.items()):
        errors.append(f"full audit {node} producer call/result binding is invalid")
    if call.get("returned_null") is not False or requested_logical_role(call.get("requested", {})) != role:
        errors.append(f"full audit {node} producer role/null state is invalid")
    return errors


def validate_full_audit_binding(
    packet: dict[str, Any],
    expected_route: dict[str, Any] | None,
    admitted_by_node: dict[str, dict[str, Any]],
    fragments_by_node: dict[str, dict[str, Any]],
    *,
    external_evidence_verifier: ExternalEvidenceVerifier | None = None,
) -> list[str]:
    """Reject omission or contradiction between Full Audit result and closure."""

    surfaces = set((expected_route or {}).get("task_facts", {}).get("surfaces", []))
    if "full_audit" not in surfaces:
        return []
    errors: list[str] = []
    contract = load_registry()["workflow_contracts"]["full_audit_v3"]
    axes_contract = contract["axes"]
    allowed_axes = set(axes_contract)
    controller_node = contract["controller_node_id"]
    controller_role = contract["controller_role"]
    if not any(
        requirement.get("node_id") == controller_node
        and requirement.get("role") == controller_role
        for requirement in (expected_route or {}).get("required_role_nodes", [])
    ):
        errors.append("full audit route is missing its mandatory controller node")
    controller_fragment = fragments_by_node.get(controller_node)
    if not controller_fragment or controller_fragment.get("role") != controller_role:
        errors.append("full audit controller fragment is missing")
        return errors
    control = controller_fragment.get("payload")
    if not isinstance(control, dict) or control.get("schema_version") != "full_audit_control_v1":
        errors.append("full audit controller payload must be full_audit_control_v1")
        return errors
    if set(control) != CONTROL_FIELDS:
        errors.append("full audit controller fields do not match the canonical contract")
    call_map, wave, context_artifact = _workflow_capture(
        packet, control, errors, external_evidence_verifier,
    )
    if (
        controller_fragment.get("context_artifact_digest")
        != context_artifact.get("artifact_digest")
        or controller_fragment.get("producer_record_kind")
        != "workflow_wave_record_v1"
        or controller_fragment.get("producer_call_ref")
        != control.get("workflow_wave_record_digest")
        or controller_fragment.get("producer_call_receipt_digest")
        != control.get("workflow_wave_record_digest")
    ):
        errors.append("full audit controller producer wave binding is invalid")

    baseline = packet.get("baseline", {})
    required_baseline = {
        "source_head", "dirty_diff_hash", "untracked_relevant_hash",
        "runtime_head", "runtime_observed_at",
    }
    if set(baseline) != required_baseline:
        errors.append("full audit closure baseline must include exact source/untracked/runtime identity fields")
    if not HEAD_RE.fullmatch(str(baseline.get("source_head", ""))):
        errors.append("full audit closure source_head must be exact 40-hex")
    for field in ("dirty_diff_hash", "untracked_relevant_hash"):
        if not DIGEST_RE.fullmatch(str(baseline.get(field, ""))):
            errors.append(f"full audit closure {field} must be sha256")
    if control.get("baseline") != baseline:
        errors.append("full audit controller baseline does not match closure baseline")

    scheduler = control.get("scheduler")
    if scheduler not in {"full", "adaptive_shadow", "adaptive"}:
        errors.append("full audit controller scheduler is invalid")
    expected_axes = _unique_axis_list(
        control.get("expected_axes"), allowed_axes, "expected_axes", errors
    )
    admitted_axes = _unique_axis_list(
        control.get("admitted_axes"), allowed_axes, "admitted_axes", errors
    )
    deferred_axes = _unique_axis_list(
        control.get("deferred_axes"), allowed_axes, "deferred_axes", errors
    )
    selection_surfaces = control.get("selection_surfaces")
    if selection_surfaces != sorted(surfaces):
        errors.append("full audit selection_surfaces do not match routed task facts")
        selection_surfaces = sorted(surfaces)
    run_sequence = control.get("run_sequence")
    if not _integer(run_sequence):
        errors.append("full audit run_sequence must be a non-negative integer")
        run_sequence = 0
    if scheduler in {"full", "adaptive_shadow"} and expected_axes != axes_contract:
        errors.append("full/adaptive_shadow audit expected_axes must equal the Registry backstop")
    if scheduler == "adaptive":
        if control.get("adaptive_recall_approved") is not True:
            errors.append("adaptive full audit requires recall approval in the controller")
        recomputed_axes = _adaptive_axes(expected_route, run_sequence, axes_contract)
        if expected_axes != recomputed_axes:
            errors.append("adaptive full audit expected_axes do not match deterministic selection")
        approval_digest = control.get("adaptive_recall_authority_digest")
        if not DIGEST_RE.fullmatch(str(approval_digest or "")):
            errors.append("adaptive full audit lacks hash-pinned recall authority")
        approval_refs = [
            ref for ref in packet.get("authority_refs", [])
            if ref.get("subject") == "adaptive_full_audit_recall"
        ]
        if (
            len(approval_refs) != 1
            or approval_refs[0].get("class") not in {"normative_policy", "claim_evidence"}
            or approval_refs[0].get("digest") != approval_digest
        ):
            errors.append("adaptive full audit recall authority is not closure-bound")
        else:
            if approval_refs[0].get("scope") != "full_audit:adaptive_recall":
                errors.append("adaptive full audit recall authority scope is invalid")
            if (
                approval_refs[0].get("subject") != "adaptive_full_audit_recall"
                or approval_refs[0].get("value") != {"approved": True}
            ):
                errors.append(
                    "adaptive full audit recall authority does not approve recall"
                )
            expiry_value = approval_refs[0].get("expiry")
            if not expiry_value:
                errors.append("adaptive full audit recall authority requires expiry")
            try:
                observed = _parse_time(str(approval_refs[0].get("observed_at", "")))
                adjudicated = _parse_time(str(packet.get("adjudicated_at", "")))
                expiry = _parse_time(str(expiry_value))
                if observed > adjudicated or adjudicated >= expiry:
                    errors.append("adaptive full audit recall authority is stale at closure")
            except (TypeError, ValueError):
                errors.append("adaptive full audit recall authority timestamp is invalid")
    else:
        if control.get("adaptive_recall_approved") not in {False, True}:
            errors.append("full audit adaptive_recall_approved must be boolean")
        if control.get("adaptive_recall_authority_digest") is not None:
            errors.append("non-adaptive full audit cannot carry adaptive recall authority")
    if set(admitted_axes) & set(deferred_axes):
        errors.append("full audit admitted_axes and deferred_axes overlap")
    if set(admitted_axes) | set(deferred_axes) != set(expected_axes):
        errors.append("full audit admitted/deferred axes do not cover expected_axes exactly")

    expected_bindings = [
        {
            "node_id": f"audit:{axis}", "role": axis,
            **native_agent_binding(axis, "verification"),
            "node_class": "verification",
            "reason": "full audit admitted axis",
        }
        for axis in admitted_axes
    ]
    if control.get("axis_bindings") != expected_bindings:
        errors.append("full audit axis_bindings do not match admitted_axes")
    binding_fields = (
        "node_id", "role", "native_agent", "node_class", "permission", "reason",
    )
    actual_bindings = [
        {
            field: admitted_by_node[node_id].get(field)
            for field in binding_fields
        }
        for node_id in admitted_by_node
        if node_id.startswith("audit:")
    ]
    if actual_bindings != expected_bindings:
        errors.append("closure admitted_role_nodes do not match Full Audit axis bindings")
    expected_nested_admissions = _nested_admission_inventory(
        admitted_axes, fragments_by_node
    )
    actual_nested_admissions = [
        admission for admission in admitted_by_node.values()
        if admission.get("result_binding") == "nested_payload"
    ]
    if actual_nested_admissions != expected_nested_admissions:
        errors.append(
            "closure nested admissions do not match typed Full Audit call inventory"
        )
    axis_fragment_digests = control.get("axis_fragment_digests")
    expected_digest_nodes = {f"audit:{axis}" for axis in admitted_axes}
    if (
        not isinstance(axis_fragment_digests, dict)
        or set(axis_fragment_digests) != expected_digest_nodes
        or any(not DIGEST_RE.fullmatch(str(value)) for value in axis_fragment_digests.values())
    ):
        errors.append("full audit axis_fragment_digests do not match admitted axes")
        axis_fragment_digests = {}

    debt = control.get("coverage_debt")
    if not isinstance(debt, list) or any(not isinstance(item, dict) for item in debt):
        errors.append("full audit coverage_debt must be a list of objects")
        debt = []
    else:
        for item in debt:
            if set(item) - {"kind", "id", "reason", "owner", "claim_key"}:
                errors.append("full audit coverage_debt contains unknown fields")
            if not all(isinstance(item.get(field), str) and item.get(field) for field in ("kind", "id", "reason")):
                errors.append("full audit coverage_debt item lacks kind/id/reason")
        identities = [(item.get("kind"), item.get("id"), item.get("owner")) for item in debt]
        if len(identities) != len(set(identities)):
            errors.append("full audit coverage_debt contains duplicate identities")
    holes = control.get("coverage_holes")
    if not isinstance(holes, list) or any(axis not in allowed_axes for axis in holes):
        errors.append("full audit coverage_holes is invalid")
        holes = []
    for axis in deferred_axes:
        if not any(item.get("kind") == "axis" and item.get("id") == axis for item in debt):
            errors.append(f"full audit deferred axis {axis} lacks canonical coverage debt")
    for axis in holes:
        if not any(item.get("kind") == "axis" and item.get("id") == axis for item in debt):
            errors.append(f"full audit coverage hole {axis} lacks canonical coverage debt")

    totals = {
        "assumption_count": 0,
        "disputed_count": 0,
        "decision_changing_findings": 0,
    }
    for axis in admitted_axes:
        fragment = fragments_by_node.get(f"audit:{axis}")
        if fragment is None or fragment.get("role") != axis:
            errors.append(f"full audit admitted axis {axis} is missing its bound fragment")
            continue
        if axis_fragment_digests.get(f"audit:{axis}") != _digest(fragment):
            errors.append(f"full audit axis {axis} fragment digest does not match controller")
        if fragment.get("consumption", {}).get("measurement_status") != "unavailable":
            errors.append(f"full audit axis {axis} cannot self-attest actual consumption")
        payload = fragment.get("payload")
        if not isinstance(payload, dict) or payload.get("schema_version") != "full_audit_axis_v1":
            errors.append(f"full audit axis {axis} payload must be full_audit_axis_v1")
            continue
        if set(payload) != AXIS_FIELDS:
            errors.append(f"full audit axis {axis} fields do not match the canonical contract")
        audit = payload.get("audit")
        if not isinstance(audit, dict) or audit.get("schema_version") != "audit_fragment_v2":
            errors.append(f"full audit axis {axis} lacks its immutable audit_fragment_v2")
            audit = {}
        if audit.get("axis") != axis:
            errors.append(f"full audit axis {axis} nested audit identity is invalid")
        raw_audit = {key: value for key, value in audit.items() if key != "axis"}
        errors.extend(_call_binding(
            call_map, fragment, node=f"audit:{axis}", role=axis, result=raw_audit,
        ))
        if wave and wave.get("result_fragment_digests", {}).get(f"audit:{axis}") != _digest(fragment):
            errors.append(f"full audit axis {axis} differs from workflow wave result map")
        raw_findings = audit.get("findings", [])
        if not isinstance(raw_findings, list):
            errors.append(f"full audit axis {axis} raw findings must be a list")
            raw_findings = []
        expected_structural_debt: list[dict[str, str]] = []
        for finding in raw_findings:
            if not isinstance(finding, dict):
                errors.append(f"full audit axis {axis} raw finding must be an object")
                continue
            if any(
                not str(finding.get(field) or "").strip()
                for field in STRUCTURAL_FINDING_FIELDS
            ):
                expected_structural_debt.append(
                    _structural_finding_debt(axis, finding)
                )
        actual_structural_debt = [
            item
            for item in debt
            if item.get("owner") == axis
            and item.get("kind") == "claim"
            and str(item.get("id", "")).startswith("invalid:sha256:")
        ]
        if expected_structural_debt != actual_structural_debt:
            if expected_structural_debt and not actual_structural_debt:
                errors.append(
                    f"full audit axis {axis} structurally invalid finding lacks canonical coverage debt"
                )
            else:
                errors.append(
                    f"full audit axis {axis} structural finding debt is not one-to-one"
                )
        assumptions_count = payload.get("assumptions_count")
        coverage_debt_count = payload.get("coverage_debt_count")
        declared_confirmed_ids = payload.get("confirmed_decision_claim_ids")
        declared_disputed_ids = payload.get("disputed_claim_ids")
        outcome_records = payload.get("verification_outcomes")
        if not _integer(assumptions_count) or assumptions_count != len(audit.get("assumptions", [])):
            errors.append(f"full audit axis {axis} assumptions_count is inconsistent")
            assumptions_count = 0
        if not _integer(coverage_debt_count):
            errors.append(f"full audit axis {axis} coverage_debt_count is invalid")
            coverage_debt_count = 0
        axis_debt_count = sum(
            1 for item in debt
            if item.get("owner") == axis or (item.get("kind") == "axis" and item.get("id") == axis)
        )
        if coverage_debt_count != axis_debt_count:
            errors.append(f"full audit axis {axis} coverage_debt_count is inconsistent")
        confirmed_ids: list[str] = []
        disputed_ids: list[str] = []
        outcome_claim_keys: set[str] = set()
        raw_decision_by_claim_key: dict[str, dict[str, Any]] = {}
        for finding in audit.get("findings", []):
            if isinstance(finding, dict) and _is_decision_outcome(finding):
                raw_decision_by_claim_key.setdefault(_claim_key(finding), finding)
        if not isinstance(outcome_records, list):
            errors.append(f"full audit axis {axis} verification_outcomes is invalid")
            outcome_records = []
        seen_claim_ids: set[str] = set()
        for record in outcome_records:
            if not isinstance(record, dict) or set(record) != {"outcome", "outcome_digest"}:
                errors.append(f"full audit axis {axis} verification outcome shape is invalid")
                continue
            outcome = record.get("outcome")
            if not isinstance(outcome, dict) or set(outcome) != OUTCOME_FIELDS:
                errors.append(f"full audit axis {axis} verification outcome fields are invalid")
                continue
            claim_id = outcome.get("claim_id")
            if not isinstance(claim_id, str) or not claim_id or claim_id in seen_claim_ids:
                errors.append(f"full audit axis {axis} verification outcome claim_id is invalid")
                continue
            seen_claim_ids.add(claim_id)
            if outcome.get("axis") != axis:
                errors.append(f"full audit axis {axis} verification outcome identity is invalid")
            if outcome.get("claim_key") != _claim_key(outcome):
                errors.append(f"full audit axis {axis} verification outcome claim_key is invalid")
            else:
                outcome_claim_keys.add(outcome["claim_key"])
            raw_finding = raw_decision_by_claim_key.get(outcome.get("claim_key"))
            if raw_finding is None:
                errors.append(
                    f"full audit axis {axis} verification outcome lacks immutable raw finding"
                )
            elif (
                outcome.get("severity") != raw_finding.get("severity")
                or outcome.get("defect_type") != raw_finding.get("defect_type")
            ):
                errors.append(
                    f"full audit axis {axis} verification outcome changes raw severity or defect_type"
                )
            if record.get("outcome_digest") != _digest(outcome):
                errors.append(f"full audit axis {axis} verification outcome digest is invalid")
            if (
                outcome.get("severity") not in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
                or not isinstance(outcome.get("defect_type"), list)
                or any(not isinstance(item, str) for item in outcome.get("defect_type", []))
                or outcome.get("reachable") not in {"reachable", "latent", "unknown", "not_applicable"}
                or not isinstance(outcome.get("verifier_votes"), list)
                or not _integer(outcome.get("verification_calls"))
                or any(
                    not isinstance(outcome.get(field), bool)
                    for field in (
                        "confirmed", "refuted", "disputed", "latent", "verifier_dissent"
                    )
                )
            ):
                errors.append(f"full audit axis {axis} verification outcome types are invalid")
            state_count = sum(
                outcome.get(field) is True for field in ("confirmed", "refuted", "disputed")
            )
            if state_count != 1:
                errors.append(f"full audit axis {axis} verification outcome state is ambiguous")
            vote_records = (
                outcome.get("verifier_votes")
                if isinstance(outcome.get("verifier_votes"), list)
                else []
            )
            votes_by_view: dict[str, dict[str, Any]] = {}
            for vote in vote_records:
                if not isinstance(vote, dict) or set(vote) != VOTE_FIELDS:
                    errors.append(f"full audit axis {axis} verifier vote shape is invalid")
                    continue
                view = vote.get("view")
                if view not in {"source", "impact", "third"} or view in votes_by_view:
                    errors.append(f"full audit axis {axis} verifier vote view is invalid")
                    continue
                if (
                    not isinstance(vote.get("refuted"), bool)
                    or vote.get("confidence") not in {"high", "med", "low"}
                    or not isinstance(vote.get("reason"), str)
                    or not vote.get("reason", "").strip()
                    or not isinstance(vote.get("evidence"), str)
                    or not vote.get("evidence", "").strip()
                ):
                    errors.append(f"full audit axis {axis} verifier vote evidence is invalid")
                if view == "third":
                    if vote.get("reachable") not in {
                        "reachable", "latent", "unknown", "not_applicable"
                    }:
                        errors.append(
                            f"full audit axis {axis} third verifier reachability is invalid"
                        )
                elif vote.get("reachable") is not None:
                    errors.append(
                        f"full audit axis {axis} first-view verifier cannot claim reachability"
                    )
                projection = {
                    key: vote[key] for key in ("refuted", "confidence", "reason", "evidence")
                    if key in vote
                }
                if view == "third":
                    projection["reachable"] = vote.get("reachable")
                errors.extend(_call_binding(
                    call_map, vote, node=f"verify:{claim_id}:{view}",
                    role={"source": "E2", "impact": "PA", "third": "E3"}[view],
                    result=projection,
                ))
                if wave and wave.get("result_fragment_digests", {}).get(f"verify:{claim_id}:{view}") != _digest(projection):
                    errors.append(f"full audit {claim_id} {view} vote differs from wave result map")
                votes_by_view[view] = vote
            raw_defect_types = (
                raw_finding.get("defect_type", [])
                if isinstance(raw_finding, dict)
                and isinstance(raw_finding.get("defect_type", []), list)
                else []
            )
            outcome_defect_types = (
                outcome.get("defect_type", [])
                if isinstance(outcome.get("defect_type", []), list)
                else []
            )
            source_vote = votes_by_view.get("source")
            impact_vote = votes_by_view.get("impact")
            third_vote = votes_by_view.get("third")
            source_eligible = bool(
                source_vote is not None and source_vote.get("confidence") != "low"
            )
            impact_eligible = bool(
                impact_vote is not None and impact_vote.get("confidence") != "low"
            )
            third_eligible = bool(
                third_vote is not None and third_vote.get("confidence") != "low"
            )
            first_complete = source_eligible and impact_eligible
            first_refuted = sum(
                vote.get("refuted") is True
                for vote in (source_vote, impact_vote)
                if vote is not None and vote.get("confidence") != "low"
            )
            recomputed_dissent = first_complete and first_refuted == 1
            needs_third = (
                isinstance(raw_finding, dict)
                and (
                    raw_finding.get("severity") == "CRITICAL"
                    or bool(set(raw_defect_types) & HIGH_RISK_TYPES)
                )
            ) or recomputed_dissent
            if third_vote is not None and not needs_third:
                errors.append(f"full audit axis {axis} unexpected third verifier vote")
            quorum = first_complete and (not needs_third or third_eligible)
            ordered_votes = [
                vote
                for vote in (source_vote, impact_vote, third_vote)
                if vote is not None and vote.get("confidence") != "low"
            ]
            majority_refuted = (
                sum(vote.get("refuted") is True for vote in ordered_votes)
                > len(ordered_votes) / 2
            )
            recomputed_confirmed = quorum and not majority_refuted
            recomputed_refuted = quorum and majority_refuted
            recomputed_disputed = not quorum
            if (
                outcome.get("confirmed") is not recomputed_confirmed
                or outcome.get("refuted") is not recomputed_refuted
                or outcome.get("disputed") is not recomputed_disputed
            ):
                errors.append(
                    f"full audit axis {axis} aggregate state disagrees with typed verifier votes"
                )
            if outcome.get("verifier_dissent") is not recomputed_dissent:
                errors.append(
                    f"full audit axis {axis} dissent disagrees with typed verifier votes"
                )
            recomputed_reachable = (
                third_vote.get("reachable") if third_vote is not None else "not_applicable"
            )
            if outcome.get("reachable") != recomputed_reachable:
                errors.append(
                    f"full audit axis {axis} reachability disagrees with typed verifier votes"
                )
            required_calls = 2 + (1 if needs_third else 0)
            verification_calls = (
                outcome.get("verification_calls")
                if _integer(outcome.get("verification_calls"))
                else 0
            )
            if verification_calls < required_calls:
                errors.append(
                    f"full audit axis {axis} resolved outcome lacks required verification quorum"
                )
            expected_latent = (
                recomputed_reachable == "latent"
                and not bool(set(outcome_defect_types) & CAPABILITY_TYPES)
            )
            if outcome.get("latent") is not expected_latent:
                errors.append(f"full audit axis {axis} latent state is not derivable from reachability")
            if recomputed_confirmed and _is_decision_outcome(outcome) and not expected_latent:
                confirmed_ids.append(claim_id)
            if recomputed_disputed:
                disputed_ids.append(claim_id)
        if declared_confirmed_ids != confirmed_ids:
            errors.append(f"full audit axis {axis} confirmed decision IDs disagree with outcomes")
        if declared_disputed_ids != disputed_ids:
            errors.append(f"full audit axis {axis} disputed IDs disagree with outcomes")
        missing_outcome_keys = set(raw_decision_by_claim_key) - outcome_claim_keys
        for claim_key in sorted(missing_outcome_keys):
            if not any(
                item.get("kind") == "claim"
                and item.get("owner") == axis
                and item.get("claim_key") == claim_key
                for item in debt
            ):
                errors.append(
                    f"full audit axis {axis} decision finding lacks outcome or exact claim debt"
                )
        expected_gate = (
            "FAIL" if confirmed_ids
            else "CONDITIONAL" if disputed_ids
            else "UNVERIFIED" if audit.get("verdict") == "BLOCKED" or assumptions_count or coverage_debt_count
            else "PASS"
        )
        if fragment.get("gate_verdict") != expected_gate:
            errors.append(f"full audit axis {axis} gate verdict disagrees with its bound payload")
        totals["assumption_count"] += assumptions_count
        totals["disputed_count"] += len(disputed_ids)
        totals["decision_changing_findings"] += len(confirmed_ids)

    for field, total in totals.items():
        if not _integer(control.get(field)) or control.get(field) != total:
            errors.append(f"full audit controller {field} disagrees with axis fragments")
    assumption_debt_count = sum(1 for item in debt if item.get("kind") == "assumption")
    if _integer(control.get("assumption_count")) and control.get("assumption_count") != assumption_debt_count:
        errors.append("full audit assumption_count disagrees with coverage debt")
    seam_result = control.get("seam_result")
    seam_digest = control.get("seam_result_digest")
    seam_valid = (
        isinstance(seam_result, dict)
        and set(seam_result) == {"reprobes"}
        and isinstance(seam_result.get("reprobes"), list)
        and seam_digest == _digest(seam_result)
    )
    if seam_result is None and seam_digest is None:
        seam_valid = False
    elif not seam_valid:
        errors.append("full audit seam result/digest is invalid")
    errors.extend(_call_binding(
        call_map,
        {
            "producer_record_kind": "workflow_call_record_v1",
            "producer_call_ref": control.get("seam_call_ref"),
            "producer_call_receipt_digest": control.get("seam_call_receipt_digest"),
        },
        node="seam:critic", role="CC", result=seam_result,
    ))
    if wave and wave.get("result_fragment_digests", {}).get("seam:critic") != _digest(seam_result):
        errors.append("full audit seam result differs from workflow wave result map")
    if control.get("seam_present") is not seam_valid:
        errors.append("full audit seam_present disagrees with bound seam result")
    if seam_valid:
        for index, reprobe in enumerate(seam_result["reprobes"]):
            if not isinstance(reprobe, dict) or not all(
                isinstance(reprobe.get(field), str) and reprobe.get(field)
                for field in ("seam", "assign_axis", "why")
            ):
                errors.append("full audit seam reprobe shape is invalid")
                continue
            if not any(
                item.get("kind") == "seam_reprobe"
                and item.get("id") == f"seam-{index + 1}"
                and item.get("reason") == reprobe["seam"]
                and item.get("owner") == reprobe["assign_axis"]
                for item in debt
            ):
                errors.append("full audit seam reprobe lacks canonical coverage debt")
    if not seam_valid and not any(item.get("kind") == "seam" for item in debt):
        errors.append("full audit missing seam lacks canonical coverage debt")

    recomputed_eligible = seam_valid and not any(
        (
            deferred_axes,
            debt,
            holes,
            control.get("assumption_count"),
            control.get("disputed_count"),
            control.get("decision_changing_findings"),
        )
    )
    if control.get("pass_eligible") is not recomputed_eligible:
        errors.append("full audit pass_eligible disagrees with recomputed control state")
    expected_projection = _expected_projection(control)
    if control.get("unverified_projection") != expected_projection:
        errors.append("full audit unverified_projection is not canonical")
    if controller_fragment.get("concerns") != expected_projection:
        errors.append("full audit controller concerns do not exactly match unverified projection")
    expected_controller_gate = (
        "PASS" if recomputed_eligible
        else "FAIL" if control.get("decision_changing_findings", 0)
        else "CONDITIONAL" if control.get("disputed_count", 0)
        else "UNVERIFIED"
    )
    if controller_fragment.get("gate_verdict") != expected_controller_gate:
        errors.append("full audit controller gate verdict disagrees with recomputed state")
    if controller_fragment.get("consumption", {}).get("measurement_status") != "unavailable":
        errors.append("full audit controller cannot self-attest actual consumption")
    if packet.get("gate_verdict") == "PASS" and not recomputed_eligible:
        errors.append("full audit controller is not PASS-eligible")
    actual_projection = [
        item for item in packet.get("unverified", [])
        if isinstance(item, str) and item.startswith("full_audit_")
    ]
    if actual_projection != expected_projection:
        errors.append("closure unverified projection does not exactly match Full Audit debt")
    return errors
