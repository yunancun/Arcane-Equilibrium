"""Independent admission checks for immutable Development-Agent Context bundles."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_governance_registry import REPO_ROOT, load_registry
from agent_governance_context_specs import trusted_derived_kinds
from agent_governance_context_projection import materialize_semantic_context


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
ARTIFACT_FIELDS = {
    "schema_version",
    "artifact_digest",
    "task_contract_digest",
    "budget_authority_digest",
    "budget_authority_canonical",
    "canonical_plan",
    "shared_task_context_digest",
    "shared_task_context_canonical",
    "role_context_delta_digest",
    "role_context_delta_canonical",
    "semantic_input_tokens",
}
PLAN_FIELDS = {
    "schema_version",
    "registry_schema_version",
    "role",
    "role_permission",
    "task_contract",
    "task_contract_digest",
    "mandatory_content",
    "omitted_mandatory",
    "baseline_errors",
    "selected_packs",
    "shared_packs",
    "role_packs",
    "sources",
    "unresolved_sources",
    "blocking_sources",
    "evidence_debt",
    "required_for_verdict",
    "acquisition_plan",
    "budget",
}
CONTRACT_FIELDS = {
    "task_shape",
    "surfaces",
    "risk",
    "uncertainty",
    "runtime_claim",
    "end_to_end_claim",
    "side_effect_class",
    "objective",
    "scope",
    "acceptance_criteria",
    "hard_stops",
    "baseline",
    "dirty_scope",
    "direct_interfaces",
    "previous_failure",
    "focus",
    "claim_inputs",
    "task_prompt",
    "task_prompt_digest",
}
MANDATORY_FIELDS = {
    "objective",
    "scope",
    "acceptance_criteria",
    "hard_stops",
    "baseline",
    "direct_interfaces",
    "previous_failure",
    "task_prompt",
    "task_prompt_digest",
}
BASELINE_FIELDS = {
    "source_head",
    "dirty_diff_hash",
    "untracked_relevant_hash",
}
BUDGET_FIELDS = {
    "envelope",
    "target_context_tokens",
    "quality_reserve_context_tokens",
    "accounting_basis",
    "max_context_tokens_per_call",
    "max_prompt_utf8_bytes_per_call",
    "estimated_tokens",
    "compiler_estimated_input_tokens",
    "action",
    "review_required",
    "review_rationale",
    "mandatory_truncated",
    "quality_reserve_reasons",
    "authority",
    "authority_canonical",
    "authority_digest",
    "call_allowed",
    "claim_pass_eligible",
    "pass_allowed",
}
CAPTURE_TTLS = {
    "runtime_observation": timedelta(minutes=15),
    "external_policy_snapshot": timedelta(days=30),
    "source_snapshot": timedelta(hours=4),
    "diff_snapshot": timedelta(hours=1),
    "interface_inventory": timedelta(hours=1),
    "caller_inventory": timedelta(hours=1),
    "test_inventory": timedelta(hours=1),
    "repository_inventory": timedelta(hours=1),
}
CompilerProvenanceVerifier = Callable[[str, str, dict[str, Any]], bool]


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _instant(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _envelope(contract: dict[str, Any]) -> str:
    risk = str(contract.get("risk", "unknown")).lower()
    uncertainty = str(contract["uncertainty"]).lower()
    surfaces = {str(value).lower() for value in contract.get("surfaces", [])}
    if "profit_diagnosis" in surfaces:
        return "profit_diagnosis"
    if (
        risk not in {"low", "medium", "high", "critical"}
        or uncertainty == "unknown"
        or "full_audit" in surfaces
    ):
        return "full_audit"
    if risk in {"high", "critical"} or uncertainty == "high" or surfaces & {
        "authority", "live", "risk", "cross_interface"
    }:
        return "complex"
    return "narrow" if risk == "low" and uncertainty == "low" else "standard"


def _source_bytes(source: dict[str, Any]) -> bytes:
    encoding = source.get("content_encoding")
    content = source.get("content")
    if encoding == "utf-8" and isinstance(content, str):
        return content.encode("utf-8")
    if encoding == "json":
        return _canonical(content).encode("utf-8")
    if encoding == "base64" and isinstance(content, str):
        return base64.b64decode(content, validate=True)
    raise ValueError("content/content_encoding is not canonical")


def _expected_facts_errors(
    contract: dict[str, Any], expected: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    required_projection = {
        "objective", "scope", "acceptance_criteria", "hard_stops", "baseline",
    }
    for field in required_projection:
        if field not in expected or contract.get(field) != expected.get(field):
            errors.append(f"task contract does not match expected task facts field {field}")
    optional_projection = {
        "direct_interfaces", "dirty_scope", "previous_failure", "focus",
        "claim_inputs", "runtime_claim", "end_to_end_claim"
    }
    for field in optional_projection & set(expected):
        if contract.get(field) != expected.get(field):
            errors.append(f"task contract does not match expected task facts field {field}")
    expected_prompt = expected.get("task_prompt", expected.get("objective"))
    expected_prompt_digest = (
        "sha256:" + hashlib.sha256(str(expected_prompt).encode("utf-8")).hexdigest()
    )
    if (
        contract.get("task_prompt") != expected_prompt
        or contract.get("task_prompt_digest") != expected_prompt_digest
    ):
        errors.append("task contract does not match expected task prompt bytes")
    if "uncertainty" not in expected:
        errors.append("expected task facts uncertainty is required")
    normalized = {
        "task_shape": str(expected.get("task_shape", "")).strip().lower(),
        "risk": str(expected.get("risk", "unknown")).strip().lower(),
        "uncertainty": str(expected.get("uncertainty", "<missing>")).strip().lower(),
        "surfaces": sorted(
            {str(value).strip().lower() for value in expected.get("surfaces", [])}
        ),
    }
    for field, value in normalized.items():
        if contract.get(field) != value:
            errors.append(f"task contract does not match expected task facts field {field}")
    if "side_effect_class" in expected:
        side_effect = str(expected["side_effect_class"]).strip().lower()
        if contract.get("side_effect_class") != side_effect:
            errors.append(
                "task contract does not match expected task facts field side_effect_class"
            )
    return errors


def _recaptured_source_projection(source: dict[str, Any]) -> dict[str, Any]:
    """Keep only locally reproducible provenance, excluding capture clock values."""

    fields = {
        "source", "selector", "status", "digest", "content_digest",
        "content_encoding", "content", "capture_kind", "producer", "baseline",
        "bytes", "source_bytes", "artifact_path", "artifact_bytes",
        "full_file_token_estimate", "planned_tokens",
        "inventory_manifest_token_estimate", "requirement_class",
        "context_scope",
    }
    projection = {key: source.get(key) for key in fields if key in source}
    if projection.get("status") in {"pinned", "pinned_verified"}:
        projection["status"] = "repository_bytes"
    return projection


def _local_provenance_errors(
    plan: dict[str, Any], *, registry: dict[str, Any], root: Path,
    external_evidence_verifier=None,
) -> list[str]:
    """Re-run the local compiler so caller-rehashed source bytes cannot self-attest."""

    from agent_governance_execution import compile_context

    contract = {
        key: value
        for key, value in plan["task_contract"].items()
        if value is not None
    }
    evidence_state = {
        source["source"]: {
            "artifact_path": source["artifact_path"],
            **(
                {"digest": source["digest"]}
                if isinstance(source.get("digest"), str)
                else {}
            ),
        }
        for source in plan.get("sources", [])
        if source.get("status") in {
            "resolved_artifact", "available_unattested_evidence",
            "stale_context_artifact",
        }
        and isinstance(source.get("artifact_path"), str)
    }
    if evidence_state:
        contract["evidence_state"] = evidence_state
    try:
        recaptured = compile_context(
            str(plan.get("role", "")), contract, registry=registry, root=root,
            external_evidence_verifier=external_evidence_verifier,
        )
    except (KeyError, OSError, TypeError, ValueError) as error:
        return [f"local Context provenance recapture failed: {error}"]
    errors: list[str] = []
    if recaptured.get("selected_packs") != plan.get("selected_packs"):
        errors.append("Registry-selected Context packs differ from caller artifact")
    actual_sources = recaptured.get("sources", [])
    claimed_sources = plan.get("sources", [])
    if [item.get("source") for item in actual_sources] != [
        item.get("source") for item in claimed_sources
    ]:
        errors.append("Registry-selected Context source inventory differs from caller artifact")
        return errors
    for index, (actual, claimed) in enumerate(zip(actual_sources, claimed_sources)):
        if _recaptured_source_projection(actual) != _recaptured_source_projection(claimed):
            errors.append(
                f"context source[{index}] differs from recaptured repository bytes or trusted producer output"
            )
    if recaptured.get("baseline_errors"):
        errors.append("recaptured repository generation differs from Context baseline")
    return errors


def validate_context_artifact(
    artifact: Any,
    now: datetime | str | None = None,
    expected_task_facts: dict[str, Any] | None = None,
    *,
    registry: dict[str, Any] | None = None,
    root: Path = REPO_ROOT,
    require_local_provenance: bool = True,
    provenance_verifier: CompilerProvenanceVerifier | None = None,
    external_evidence_verifier=None,
) -> dict[str, Any]:
    """Recompute an inline context bundle; never trust caller-provided digests."""

    errors: list[str] = []
    result: dict[str, Any] = {"errors": errors, "plan": None}
    if not isinstance(artifact, dict) or set(artifact) != ARTIFACT_FIELDS:
        errors.append("context artifact fields are not exact context_artifact_v1")
        return result
    if artifact.get("schema_version") != "context_artifact_v1":
        errors.append("context artifact schema_version is invalid")
    for field in (
        "artifact_digest", "task_contract_digest", "budget_authority_digest",
        "shared_task_context_digest", "role_context_delta_digest",
    ):
        if not isinstance(artifact.get(field), str) or not DIGEST_RE.fullmatch(
            artifact[field]
        ):
            errors.append(f"context artifact {field} is invalid")
    canonical_plan = artifact.get("canonical_plan")
    if not isinstance(canonical_plan, str):
        errors.append("context artifact canonical_plan must be exact string bytes")
        return result
    if _digest(canonical_plan.encode("utf-8")) != artifact.get("artifact_digest"):
        errors.append("canonical_plan digest does not match artifact_digest")
    try:
        plan = json.loads(
            canonical_plan,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, ValueError) as error:
        errors.append(f"canonical_plan is invalid JSON: {error}")
        return result
    result["plan"] = plan
    try:
        if _canonical(plan) != canonical_plan:
            errors.append("canonical_plan bytes are not canonical")
    except (TypeError, ValueError):
        errors.append("canonical_plan contains a non-canonical value")
    if not isinstance(plan, dict) or set(plan) != PLAN_FIELDS:
        errors.append("canonical plan fields are not exact context_plan_v1")
        return result
    if plan.get("schema_version") != "context_plan_v1":
        errors.append("canonical plan schema_version is invalid")
    if plan.get("registry_schema_version") != "agent_registry_v1":
        errors.append("canonical plan Registry generation is invalid")

    contract = plan.get("task_contract")
    if not isinstance(contract, dict) or set(contract) != CONTRACT_FIELDS:
        errors.append("task contract fields are not exact")
        return result
    contract_digest = _digest(_canonical(contract).encode("utf-8"))
    if contract_digest != plan.get("task_contract_digest"):
        errors.append("plan task_contract_digest does not match task contract")
    if contract_digest != artifact.get("task_contract_digest"):
        errors.append("artifact task_contract_digest does not match task contract")
    if contract.get("task_prompt_digest") != _digest(
        str(contract.get("task_prompt", "")).encode("utf-8")
    ):
        errors.append("task prompt digest does not match exact prompt bytes")
    baseline = contract.get("baseline")
    if (
        not isinstance(baseline, dict)
        or set(baseline) != BASELINE_FIELDS
        or not HEAD_RE.fullmatch(str(baseline.get("source_head", "")))
        or not DIGEST_RE.fullmatch(str(baseline.get("dirty_diff_hash", "")))
        or not DIGEST_RE.fullmatch(
            str(baseline.get("untracked_relevant_hash", ""))
        )
    ):
        errors.append("task contract baseline is invalid")
    mandatory = plan.get("mandatory_content")
    if not isinstance(mandatory, dict) or set(mandatory) != MANDATORY_FIELDS:
        errors.append("mandatory content fields are not exact")
    elif any(mandatory[field] != contract[field] for field in MANDATORY_FIELDS):
        errors.append("mandatory content is not bound to the task contract")
    for field in ("omitted_mandatory", "baseline_errors", "blocking_sources"):
        if not isinstance(plan.get(field), list) or plan[field]:
            errors.append(f"context plan {field} must be an empty list")
    evidence_debt = plan.get("evidence_debt")
    required_for_verdict = plan.get("required_for_verdict")
    acquisition_plan = plan.get("acquisition_plan")
    unresolved_sources = plan.get("unresolved_sources")
    for field, value in (
        ("evidence_debt", evidence_debt),
        ("required_for_verdict", required_for_verdict),
        ("unresolved_sources", unresolved_sources),
    ):
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            errors.append(f"context plan {field} must be a string list")
    if not isinstance(acquisition_plan, list):
        errors.append("context plan acquisition_plan must be a list")
        acquisition_plan = []
    if expected_task_facts is not None:
        if not isinstance(expected_task_facts, dict):
            errors.append("expected_task_facts must be an object")
        else:
            errors.extend(_expected_facts_errors(contract, expected_task_facts))

    observed_now = _instant(now) if now is not None else datetime.now(timezone.utc)
    if observed_now is None:
        errors.append("context validation now must be timezone-aware")
        observed_now = datetime.now(timezone.utc)
    registry = registry or load_registry()
    if plan.get("role_permission") != registry.get("roles", {}).get(plan.get("role"), {}).get("permission"):
        errors.append("context role_permission differs from Registry")
    try:
        expected_semantic = materialize_semantic_context(plan, registry)
    except (KeyError, TypeError, ValueError) as error:
        errors.append(f"semantic Context projection failed: {error}")
        expected_semantic = {}
    for field in (
        "shared_task_context_canonical", "shared_task_context_digest",
        "role_context_delta_canonical", "role_context_delta_digest",
        "semantic_input_tokens",
    ):
        if artifact.get(field) != expected_semantic.get(field):
            errors.append(f"artifact {field} is not canonical-plan-derived")
    trusted_kinds = trusted_derived_kinds(registry)
    sources = plan.get("sources")
    source_tokens = 0
    if not isinstance(sources, list) or not sources:
        errors.append("context plan sources must be a non-empty list")
        sources = []
    for index, source in enumerate(sources):
        prefix = f"context source[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{prefix} must be an object")
            continue
        status = source.get("status")
        requirement_class = source.get("requirement_class")
        if requirement_class not in {"call_context", "verdict_evidence"}:
            errors.append(f"{prefix} requirement_class is invalid")
        admitted_status = status in {
            "pinned", "pinned_verified", "resolved_artifact", "trusted_producer"
        }
        debt_status = (
            requirement_class == "verdict_evidence"
            and isinstance(evidence_debt, list)
            and source.get("source") in evidence_debt
            and status in {
                "resolve_on_demand", "stale_context_artifact",
                "trusted_producer_unavailable", "available_unattested_evidence",
            }
        )
        if not admitted_status and not debt_status:
            errors.append(f"{prefix} status is not admissible")
        if source.get("baseline") != baseline:
            errors.append(f"{prefix} baseline is not task-contract bound")
        if debt_status and status in {
            "resolve_on_demand", "trusted_producer_unavailable",
        }:
            if source.get("digest") is not None or source.get("planned_tokens") != 32:
                errors.append(f"{prefix} unresolved verdict evidence shape is invalid")
            source_tokens += 32
            continue
        try:
            content_bytes = _source_bytes(source)
        except (TypeError, ValueError) as error:
            errors.append(f"{prefix} {error}")
            continue
        if _digest(content_bytes) != source.get("content_digest"):
            errors.append(f"{prefix} content_digest does not match exact bytes")
        exact_tokens = max(1, (len(content_bytes) + 3) // 4)
        if source.get("bytes") != len(content_bytes):
            errors.append(f"{prefix} byte count was caller-modified")
        if source.get("planned_tokens") != exact_tokens:
            errors.append(f"{prefix} compiler token estimate was lowered")
        full_estimate = source.get("full_file_token_estimate")
        if not isinstance(full_estimate, int) or full_estimate < exact_tokens:
            errors.append(f"{prefix} full-file estimate is invalid")
        source_tokens += exact_tokens
        observed = _instant(source.get("observed_at"))
        expires = _instant(source.get("expires_at"))
        ttl = CAPTURE_TTLS.get(str(source.get("capture_kind", "")))
        if observed is None or expires is None or observed >= expires:
            errors.append(f"{prefix} freshness interval is invalid")
        elif ttl is None or expires - observed > ttl:
            errors.append(f"{prefix} exceeds capture-kind freshness authority")
        elif status == "stale_context_artifact" and observed <= observed_now:
            pass
        elif not (observed <= observed_now < expires):
            errors.append(f"{prefix} is expired or not yet valid")
        capture_kind = source.get("capture_kind")
        producer = source.get("producer")
        if status == "trusted_producer":
            if (
                producer != "agent_governance_context_producer_v1"
                or trusted_kinds.get(source.get("source")) != capture_kind
            ):
                errors.append(f"{prefix} trusted producer/capture kind is invalid")
        elif status == "resolved_artifact":
            expected_producer = {
                "runtime_observation": "runtime_observation_adapter_v1",
                "external_policy_snapshot": "external_policy_capture_adapter_v1",
                "source_snapshot": "repository_snapshot_adapter_v1",
            }.get(capture_kind)
            if (
                not isinstance(producer, dict)
                or producer.get("id") != expected_producer
                or not DIGEST_RE.fullmatch(str(producer.get("input_digest", "")))
            ):
                errors.append(f"{prefix} resolved producer is invalid")
        elif status in {"available_unattested_evidence", "stale_context_artifact"}:
            expected_producer = {
                "runtime_observation": "runtime_observation_adapter_v1",
                "external_policy_snapshot": "external_policy_capture_adapter_v1",
                "source_snapshot": "repository_snapshot_adapter_v1",
            }.get(capture_kind)
            if (
                not isinstance(producer, dict)
                or producer.get("id") != expected_producer
                or not DIGEST_RE.fullmatch(str(producer.get("input_digest", "")))
            ):
                errors.append(f"{prefix} unattested evidence integrity metadata is invalid")
        elif producer != "repository_bytes_v1" or capture_kind != "source_snapshot":
            errors.append(f"{prefix} repository producer/capture kind is invalid")

    expected_required = [
        source.get("source") for source in sources
        if source.get("requirement_class") == "verdict_evidence"
    ]
    if required_for_verdict != expected_required:
        errors.append("context required_for_verdict is not source-derived")
    expected_unresolved = [
        source.get("source") for source in sources
        if source.get("status") not in {
            "pinned", "pinned_verified", "resolved_artifact", "trusted_producer"
        }
    ]
    if plan.get("baseline_errors"):
        expected_unresolved.append("task contract baseline")
    if unresolved_sources != expected_unresolved:
        errors.append("context unresolved_sources is not source-derived")
    if isinstance(evidence_debt, list):
        expected_acquisition = [
            {
                "source": source.get("source"),
                "capture_kind": source.get("capture_kind"),
                "current_status": source.get("status"),
                "required_for": "claim_or_PASS_verdict",
                "action": "acquire through an implemented independent adapter, then recompile Context",
            }
            for source in sources if source.get("source") in evidence_debt
        ]
        if acquisition_plan != expected_acquisition:
            errors.append("context acquisition_plan is not evidence-debt-derived")

    if require_local_provenance:
        errors.extend(
            _local_provenance_errors(
                plan, registry=registry, root=root.resolve(),
                external_evidence_verifier=external_evidence_verifier,
            )
        )
    else:
        try:
            provenance_verified = (
                provenance_verifier is not None
                and provenance_verifier(
                    "context_artifact_v1",
                    str(artifact.get("artifact_digest", "")),
                    artifact,
                )
                is True
            )
        except Exception:
            provenance_verified = False
        if not provenance_verified:
            errors.append(
                "historical Context artifact lacks out-of-band compiler provenance attestation"
            )

    budget = plan.get("budget")
    if not isinstance(budget, dict) or set(budget) != BUDGET_FIELDS:
        errors.append("context budget fields are not exact")
        return result
    envelope_name = _envelope(contract)
    try:
        envelope = registry["budget_envelopes"][envelope_name]
    except (KeyError, TypeError):
        errors.append(f"Registry budget authority is missing envelope {envelope_name}")
        return result
    authority = {
        "schema_version": "context_budget_authority_v1",
        "envelope": envelope_name,
        "accounting_basis": envelope["accounting_basis"],
        "max_context_tokens_per_call": envelope["max_context_tokens_per_call"],
        "max_prompt_utf8_bytes_per_call": envelope["max_prompt_utf8_bytes_per_call"],
        "max_workflow_planned_input_tokens": envelope["max_workflow_planned_input_tokens"],
        "max_unique_nodes": envelope["max_unique_nodes"],
        "max_call_attempts": envelope["max_call_attempts"],
        "retry_budget": envelope["retry_budget"],
    }
    authority_canonical = _canonical(authority)
    authority_digest = _digest(authority_canonical.encode("utf-8"))
    if budget.get("authority") != authority:
        errors.append("context budget authority is not compiler-derived")
    if budget.get("authority_canonical") != authority_canonical:
        errors.append("context budget authority canonical bytes are invalid")
    if budget.get("authority_digest") != authority_digest:
        errors.append("context budget authority digest is invalid")
    if artifact.get("budget_authority_canonical") != authority_canonical:
        errors.append("artifact budget authority canonical bytes are not cross-bound")
    if artifact.get("budget_authority_digest") != authority_digest:
        errors.append("artifact budget authority digest is not cross-bound")
    estimated = max(
        1,
        (len(json.dumps(mandatory, ensure_ascii=False, sort_keys=True).encode("utf-8")) + 3)
        // 4,
    ) + source_tokens
    reserve_end = (
        envelope["target_context_tokens"]
        + envelope["quality_reserve_context_tokens"]
    )
    expected_action = (
        "within_target"
        if estimated <= envelope["target_context_tokens"]
        else "use_quality_reserve"
        if estimated <= reserve_end
        else "review_required"
        if estimated < envelope["max_context_tokens_per_call"]
        else "split_or_escalate"
    )
    review_required = expected_action == "review_required"
    expected_budget_values = {
        "envelope": envelope_name,
        "target_context_tokens": envelope["target_context_tokens"],
        "quality_reserve_context_tokens": envelope["quality_reserve_context_tokens"],
        "accounting_basis": envelope["accounting_basis"],
        "max_context_tokens_per_call": envelope["max_context_tokens_per_call"],
        "max_prompt_utf8_bytes_per_call": envelope["max_prompt_utf8_bytes_per_call"],
        "estimated_tokens": estimated,
        "compiler_estimated_input_tokens": estimated,
        "action": expected_action,
        "review_required": review_required,
        "review_rationale": (
            "single reviewed call is below the planned-input and exact prompt-byte caps and avoids duplicate core/source reload across a split"
            if review_required else None
        ),
        "mandatory_truncated": False,
    }
    for field, expected in expected_budget_values.items():
        if budget.get(field) != expected:
            errors.append(f"context budget {field} was not compiler-derived")
    expected_call_allowed = not plan.get("blocking_sources") and expected_action != "split_or_escalate"
    expected_claim_eligible = not plan.get("unresolved_sources") and expected_action != "split_or_escalate"
    if budget.get("call_allowed") is not expected_call_allowed:
        errors.append("context budget call_allowed is not independently derived")
    if budget.get("claim_pass_eligible") is not expected_claim_eligible:
        errors.append("context budget claim_pass_eligible is not independently derived")
    if budget.get("pass_allowed") is not expected_call_allowed:
        errors.append("context budget pass_allowed compatibility alias differs from call admission")
    if not expected_call_allowed:
        errors.append("context budget is not independently call_allowed")
    if not isinstance(budget.get("quality_reserve_reasons"), list):
        errors.append("context budget quality_reserve_reasons must be a list")
    return result
