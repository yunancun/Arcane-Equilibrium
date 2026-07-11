"""Shared closure-side capture lookup for saved governance workflows."""

from __future__ import annotations

from typing import Any

from agent_governance_capture_binding import collect_capture_evidence


def collect_bound_workflow_capture(
    packet: dict[str, Any], control: dict[str, Any], *, label: str,
    external_evidence_verifier=None,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any], dict[str, Any], list[str]]:
    dispatch = packet.get("dispatch", {})
    context = dispatch.get("context_artifact", {})
    execution_tasks = {
        node.get("node_id"): node
        for node in [
            *dispatch.get("required_role_nodes", []),
            *dispatch.get("admitted_role_nodes", []),
        ]
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }
    captured = collect_capture_evidence(
        packet.get("evidence", []),
        expected_scope=dispatch.get("task_facts", {}).get("dirty_scope", []),
        expected_source_head=packet.get("baseline", {}).get("source_head", ""),
        expected_task_contract_digest=context.get("task_contract_digest", ""),
        expected_context_artifact_digest=context.get("artifact_digest", ""),
        expected_budget_authority_digest=context.get("budget_authority_digest"),
        expected_budget_authority_canonical=context.get("budget_authority_canonical"),
        require_current_repository=False,
        external_evidence_verifier=external_evidence_verifier,
        adjudicated_at=packet.get("adjudicated_at"),
        expected_execution_tasks=execution_tasks,
    )
    errors = [f"{label} workflow capture: {error}" for error in captured["errors"]]
    manifest = captured["manifests"].get(control.get("call_manifest_digest"))
    wave = captured["waves"].get(control.get("workflow_wave_record_digest"))
    if manifest is None:
        errors.append(f"{label} controller call manifest is missing")
    if wave is None:
        errors.append(f"{label} controller wave record is missing")
    if manifest and manifest.get("workflow_contract_digest") != control.get("workflow_contract_digest"):
        errors.append(f"{label} workflow contract digest differs from manifest")
    return captured["calls"], wave, context, captured, errors


def collect_closure_captures(
    packet: dict[str, Any], dispatch: dict[str, Any], task_contract: dict[str, Any],
    task_contract_digest: str | None, baseline: dict[str, Any], *,
    external_evidence_verifier=None,
) -> dict[str, Any]:
    context = dispatch.get("context_artifact", {})
    execution_tasks = {
        node.get("node_id"): node
        for node in [
            *dispatch.get("required_role_nodes", []),
            *dispatch.get("admitted_role_nodes", []),
        ]
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }
    return collect_capture_evidence(
        packet.get("evidence", []),
        expected_scope=task_contract.get("dirty_scope", []),
        expected_source_head=str(baseline.get("source_head", "")),
        expected_task_contract_digest=str(task_contract_digest or ""),
        expected_context_artifact_digest=str(context.get("artifact_digest", "")),
        expected_budget_authority_digest=context.get("budget_authority_digest"),
        expected_budget_authority_canonical=context.get("budget_authority_canonical"),
        require_current_repository=True,
        external_evidence_verifier=external_evidence_verifier,
        adjudicated_at=packet.get("adjudicated_at"),
        expected_execution_tasks=execution_tasks,
    )
