"""Stable Dispatch/Context facade for Development-Agent governance."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent_governance_context import (
    _baseline_errors,
    _estimate_tokens,
    _select_envelope,
    _source_provenance,
    _task_contract,
    capture_repository_baseline,
)
from agent_governance_context_validation import validate_context_artifact
from agent_governance_context_specs import activated_source_specs, source_name
from agent_governance_context_projection import materialize_semantic_context
from agent_governance_registry import REPO_ROOT, load_registry
from agent_governance_external_evidence import ExternalEvidenceVerifier
from agent_governance_routing import (
    TASK_CONTRACT_FIELDS,
    _normalize_task_facts,
    _sha256_bytes,
    route_task,
)


MANDATORY_CONTEXT_FIELDS = (
    "objective",
    "scope",
    "acceptance_criteria",
    "hard_stops",
    "baseline",
    "direct_interfaces",
    "previous_failure",
    "task_prompt",
    "task_prompt_digest",
)
CLOSURE_REQUIRED_FIELDS = {
    "schema_version",
    "task_id",
    "human_summary",
    "work_status",
    "gate_verdict",
    "disposition",
    "confidence",
    "adjudicated_at",
    "baseline",
    "dispatch",
    "authority_refs",
    "acceptance",
    "evidence",
    "role_fragments",
    "checks",
    "side_effects",
    "unverified",
    "skipped_roles",
    "consumption",
    "next_action",
}
ROLE_WORK_STATUSES = {"DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED"}
WORK_STATUSES = {*ROLE_WORK_STATUSES, "BLOCKED_NO_DELTA"}
GATE_VERDICTS = {"PASS", "FAIL", "CONDITIONAL", "NOT_APPLICABLE", "UNVERIFIED"}
DISPOSITIONS = {"CHANGED", "NO_CHANGE_NEEDED", "DEFERRED"}
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
TEST_EVIDENCE_FIELDS = {
    "source_head",
    "dirty_diff_hash",
    "untracked_relevant_hash",
    "command",
    "selected_tests",
    "toolchain",
    "dependency_lock_hash",
    "os",
    "arch",
    "env_mode",
    "config_hash",
    "runtime_head",
    "authorization_hash",
}


def task_contract_digest(task_facts: dict[str, Any]) -> str:
    """Hash the normalized objective/scope/acceptance/hard-stop contract."""

    contract = _task_contract(_normalize_task_facts(task_facts))
    return _sha256_bytes(
        json.dumps(
            contract,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def compile_context(
    role_id: str,
    task_facts: dict[str, Any],
    registry: dict[str, Any] | None = None,
    root: Path = REPO_ROOT,
    external_evidence_verifier: ExternalEvidenceVerifier | None = None,
) -> dict[str, Any]:
    """Compile a lossless content-addressed context plan."""

    registry = registry or load_registry()
    facts = _normalize_task_facts(task_facts)
    if role_id not in registry["roles"]:
        raise ValueError(f"unknown role: {role_id}")
    role = registry["roles"][role_id]
    mandatory = {
        field: facts[field]
        for field in MANDATORY_CONTEXT_FIELDS
        if field in facts and facts[field] not in (None, "", [], {})
    }
    omitted = [field for field in MANDATORY_CONTEXT_FIELDS if field not in mandatory]
    surfaces = set(facts["surfaces"])
    conditional_packs = (
        (
            surfaces & {
                "operations", "runtime", "deploy", "service", "cron", "pg",
                "full_audit", "profit_diagnosis", "incident_rca",
            }
            or facts.get("runtime_claim", False)
            or facts.get("end_to_end_claim", False)
            or facts.get("uncertainty") in {"high", "unknown"},
            "active_state",
        ),
        (surfaces & {"python", "rust", "gui", "ml_data", "implementation"}, "source_change"),
        (
            surfaces & {"runtime", "deploy", "service", "cron", "pg", "operations"}
            or facts.get("runtime_claim", False)
            or facts.get("end_to_end_claim", False),
            "runtime",
        ),
        (surfaces & {"public_web_read", "private_external_contact"}, "external_policy"),
        ({"bybit"} & surfaces, "broker_bybit"),
        (surfaces & {"ibkr", "tws", "stock_etf_cash", "broker_session"}, "broker_ibkr"),
        (surfaces & {"ml", "ml_data", "data", "schema"}, "ml_data"),
        ({"gui"} & surfaces, "gui_visual"),
        (surfaces & {"docs", "governance"}, "docs"),
        (surfaces & {"architecture", "authority", "cross_interface"}, "architecture"),
    )
    shared_packs = [
        pack for pack in role["context_packs"]
        if pack in {"core", "active_state"}
    ]
    for condition, pack in conditional_packs:
        if condition and pack not in shared_packs:
            shared_packs.append(pack)
    role_packs = [
        pack for pack in role["context_packs"] if pack not in shared_packs
    ]
    selected_packs = [*shared_packs, *role_packs]
    shared_specs = activated_source_specs(registry, shared_packs, facts)
    shared_names = {source_name(spec) for spec in shared_specs}
    role_specs = [
        spec for spec in activated_source_specs(registry, role_packs, facts)
        if source_name(spec) not in shared_names
    ]
    source_specs = [*shared_specs, *role_specs]
    sources = [source_name(spec) for spec in source_specs]
    evidence_state = facts.get("evidence_state", {})
    if not isinstance(evidence_state, dict):
        raise ValueError("task facts evidence_state must be an object when supplied")
    unknown_evidence_sources = sorted(set(evidence_state) - set(sources))
    if unknown_evidence_sources:
        raise ValueError(
            f"task facts evidence_state contains unselected sources: {unknown_evidence_sources}"
        )
    try:
        actual_baseline = capture_repository_baseline(root)
    except ValueError:
        actual_baseline = None
    baseline_errors = _baseline_errors(facts.get("baseline"), actual_baseline)
    provenance = []
    for context_scope, specs in (("shared", shared_specs), ("role", role_specs)):
        for spec in specs:
            record = _source_provenance(
                spec, root, evidence_state, facts, actual_baseline,
                external_evidence_verifier,
            )
            record["context_scope"] = context_scope
            provenance.append(record)
    admissible = {"pinned", "pinned_verified", "resolved_artifact", "trusted_producer"}
    unresolved = [
        record["source"] for record in provenance if record["status"] not in admissible
    ]
    if baseline_errors:
        unresolved.append("task contract baseline")
    substitution_statuses = {
        "artifact_digest_mismatch", "invalid_context_artifact",
        "invalid_local_assertion", "local_digest_mismatch",
        "trusted_producer_override_rejected", "unbacked_evidence_state",
    }
    evidence_debt = [
        record["source"] for record in provenance
        if record.get("requirement_class") == "verdict_evidence"
        and record["status"] not in admissible
        and record["status"] not in substitution_statuses
    ]
    blocking_sources = [
        record["source"] for record in provenance
        if record["status"] not in admissible
        and record["source"] not in evidence_debt
    ]
    if baseline_errors:
        blocking_sources.append("task contract baseline")
    required_for_verdict = [
        record["source"] for record in provenance
        if record.get("requirement_class") == "verdict_evidence"
    ]
    acquisition_plan = [
        {
            "source": record["source"],
            "capture_kind": record.get("capture_kind"),
            "current_status": record["status"],
            "required_for": "claim_or_PASS_verdict",
            "action": "acquire through an implemented independent adapter, then recompile Context",
        }
        for record in provenance if record["source"] in evidence_debt
    ]

    envelope_name = _select_envelope(facts)
    registry_envelope = dict(registry["budget_envelopes"][envelope_name])
    envelope = {
        field: registry_envelope[field]
        for field in (
            "target_context_tokens", "quality_reserve_context_tokens",
            "accounting_basis", "max_context_tokens_per_call",
            "max_prompt_utf8_bytes_per_call",
        )
    }
    estimated_tokens = _estimate_tokens(mandatory) + sum(
        int(record.get("planned_tokens", 32)) for record in provenance
    )
    reserve_end = (
        envelope["target_context_tokens"]
        + envelope["quality_reserve_context_tokens"]
    )
    if estimated_tokens <= envelope["target_context_tokens"]:
        action = "within_target"
    elif estimated_tokens <= reserve_end:
        action = "use_quality_reserve"
    elif estimated_tokens < envelope["max_context_tokens_per_call"]:
        action = "review_required"
    else:
        action = "split_or_escalate"
    review_required = action == "review_required"
    review_rationale = (
        "single reviewed call is below the planned-input and exact prompt-byte caps and avoids duplicate core/source reload across a split"
        if review_required else None
    )
    reserve_reasons: list[str] = []
    if envelope_name in {"complex", "full_audit"}:
        reserve_reasons.append(
            "risk/complexity preserves room for independent challenge and evidence"
        )
    if facts.get("previous_failure"):
        reserve_reasons.append("previous failure or concern must remain available")
    if omitted:
        reserve_reasons.append("missing mandatory facts require context acquisition before PASS")

    contract = _task_contract(facts)
    contract_digest = _sha256_bytes(
        json.dumps(
            contract,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    authority = {
        "schema_version": "context_budget_authority_v1",
        "envelope": envelope_name,
        "accounting_basis": registry_envelope["accounting_basis"],
        "max_context_tokens_per_call": registry_envelope["max_context_tokens_per_call"],
        "max_prompt_utf8_bytes_per_call": registry_envelope["max_prompt_utf8_bytes_per_call"],
        "max_workflow_planned_input_tokens": registry_envelope["max_workflow_planned_input_tokens"],
        "max_unique_nodes": registry_envelope["max_unique_nodes"],
        "max_call_attempts": registry_envelope["max_call_attempts"],
        "retry_budget": registry_envelope["retry_budget"],
    }
    authority_canonical = json.dumps(
        authority,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    authority_digest = _sha256_bytes(authority_canonical.encode("utf-8"))
    plan = {
        "schema_version": "context_plan_v1",
        "registry_schema_version": registry["schema_version"],
        "role": role_id,
        "role_permission": role["permission"],
        "task_contract": contract,
        "task_contract_digest": contract_digest,
        "mandatory_content": mandatory,
        "omitted_mandatory": omitted,
        "baseline_errors": baseline_errors,
        "selected_packs": selected_packs,
        "shared_packs": shared_packs,
        "role_packs": role_packs,
        "sources": provenance,
        "unresolved_sources": unresolved,
        "blocking_sources": blocking_sources,
        "evidence_debt": evidence_debt,
        "required_for_verdict": required_for_verdict,
        "acquisition_plan": acquisition_plan,
        "budget": {
            "envelope": envelope_name,
            **envelope,
            "estimated_tokens": estimated_tokens,
            "compiler_estimated_input_tokens": estimated_tokens,
            "action": action,
            "review_required": review_required,
            "review_rationale": review_rationale,
            "mandatory_truncated": False,
            "quality_reserve_reasons": reserve_reasons,
            "authority": authority,
            "authority_canonical": authority_canonical,
            "authority_digest": authority_digest,
            "call_allowed": not omitted and not blocking_sources and action != "split_or_escalate",
            "claim_pass_eligible": (
                not omitted and not unresolved and action != "split_or_escalate"
            ),
            # Compatibility alias for existing saved-workflow admission.  It is
            # call admission, never evidence sufficiency for a PASS verdict.
            "pass_allowed": not omitted and not blocking_sources and action != "split_or_escalate",
        },
    }
    plan["context_digest"] = context_plan_digest(plan)
    return plan


def context_plan_digest(plan: dict[str, Any]) -> str:
    """Hash the complete canonical plan except its self-digest."""

    unsigned = {key: value for key, value in plan.items() if key != "context_digest"}
    return _sha256_bytes(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def materialize_context_artifact(plan: dict[str, Any]) -> dict[str, Any]:
    """Freeze Python-canonical plan bytes for cross-runtime admission/retry."""

    expected_digest = context_plan_digest(plan)
    if plan.get("context_digest") != expected_digest:
        raise ValueError("context plan self-digest is stale or forged")
    if not isinstance(plan.get("budget"), dict) or plan["budget"].get("call_allowed") is not True:
        raise ValueError("context plan is not call_allowed and cannot be materialized")
    unsigned = {key: value for key, value in plan.items() if key != "context_digest"}
    canonical_plan = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if _sha256_bytes(canonical_plan.encode("utf-8")) != expected_digest:
        raise ValueError("context plan canonical bytes do not match plan digest")
    semantic = materialize_semantic_context(plan, load_registry())
    return {
        "schema_version": "context_artifact_v1",
        "artifact_digest": expected_digest,
        "task_contract_digest": str(plan.get("task_contract_digest", "")),
        "budget_authority_digest": str(plan["budget"].get("authority_digest", "")),
        "budget_authority_canonical": str(plan["budget"].get("authority_canonical", "")),
        "canonical_plan": canonical_plan,
        **semantic,
    }
