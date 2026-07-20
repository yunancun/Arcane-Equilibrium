"""Typed task-fact normalization and deterministic Development-Agent routing."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any, Iterable

from agent_governance_execution_dag import (
    delegated_execution_projection,
    execution_dag_digest,
    non_call_controller_node_ids,
)
from agent_governance_registry import native_agent_binding
from agent_governance_task_control import (
    CONTINUATION_MODES,
    DEFAULT_CONTINUATION_MODE,
    compile_task_execution_policy,
    operator_loop_request_digest,
)
from agent_governance_vocabulary import KNOWN_SURFACES, UNCERTAINTY_LEVELS


TASK_FACT_FIELDS = {
    "task_shape", "surfaces", "risk", "runtime_claim", "end_to_end_claim",
    "objective", "scope", "acceptance_criteria", "hard_stops", "baseline",
    "direct_interfaces", "previous_failure", "evidence_state", "expected_output",
    "side_effect_class", "uncertainty", "dirty_scope", "operator_risk_acceptance",
    "verification_scope", "focus", "claim_inputs",
    "task_prompt", "task_prompt_digest", "continuation_mode",
    "operator_loop_request_digest",
}
SOURCE_REVIEW_SURFACES = {"python", "rust", "gui", "ml_data", "implementation", "runtime"}
OPERATION_SURFACES = {"deploy", "service", "cron", "pg", "operations", "runtime_effect", "incident_rca"}
DOC_SURFACES = {"docs", "governance", "index", "registry", "routing", "closure", "comments"}
SIDE_EFFECT_CLASSES = {
    "none", "repo_write", "local_test", "docs_write", "deploy", "broker_probe",
    "broker_private_effect", "public_web_read", "private_external_contact",
}
SOURCE_WRITE_SHAPES = {
    "implementation", "feature", "change", "bug", "fix", "refactor", "migration",
}
WRITE_EFFECT_BY_SHAPE = {
    **{shape: "repo_write" for shape in SOURCE_WRITE_SHAPES},
    "docs": "docs_write",
    "documentation": "docs_write",
    "test": "local_test",
    "deploy": "deploy",
}
BROKER_SURFACES = {"bybit", "ibkr", "tws", "stock_etf_cash", "broker_session"}
UNSUPPORTED_EFFECT_CLASSES = {
    "broker_probe", "broker_private_effect", "private_external_contact",
}
P0B_ADAPTER_ID = "p0b_alr_rollforward_adapter_v1"
P0B_CLAIM_KEYS_BY_PHASE = {
    "stage": frozenset({
        "p0b_effect_adapter_selection",
        "p0b_adapter_source",
        "p0b_adapter_tests",
        "p0b_base_adapter_source",
        "p0b_generation_apply_source",
        "p0b_phase_runtime_bindings",
        "p0b_runtime_source_binding",
        "p0b_runtime_protected_binding",
        "p0b_runtime_paths_binding",
        "p0b_runtime_inventories_binding",
        "p0b_runtime_lineage_binding",
        "p0b_private_bundle_stager_source",
        "p0b_private_bundle_stager_tests",
        "p0b_private_bundle_source_manifest",
        "p0b_private_bundle_destination_absent_attestation",
        "p0b_target_source_attestation",
        "p0b_completion_inventory",
        "p0b_producer_inventory",
        "p0b_live_inventory",
        "p0b_protected_runtime_baseline",
        "p0b_p0a_completed_board_input",
    }),
    "cutover": frozenset({
        "p0b_effect_adapter_selection",
        "p0b_adapter_source",
        "p0b_adapter_tests",
        "p0b_base_adapter_source",
        "p0b_generation_apply_source",
        "p0b_phase_runtime_bindings",
        "p0b_runtime_source_binding",
        "p0b_runtime_protected_binding",
        "p0b_runtime_paths_binding",
        "p0b_runtime_inventories_binding",
        "p0b_runtime_lineage_binding",
        "p0b_observer_source",
        "p0b_observer_tests",
        "p0b_observer_dependency_source",
        "p0b_phase1_task_contract",
        "p0b_phase1_route",
        "p0b_phase1_context_artifact",
        "p0b_phase1_intent",
        "p0b_phase1_receipt",
        "p0b_phase1_closure",
        "p0b_sealed_lineage_bundle",
        "p0b_private_bundle_receipt",
        "p0b_private_bundle_destination",
        "p0b_target_source_attestation",
        "p0b_completion_inventory",
        "p0b_producer_inventory",
        "p0b_live_inventory",
        "p0b_protected_runtime_baseline",
        "p0b_staged_candidate_board",
    }),
}
ROUTED_WORK_NODES = {
    "implementation", "implementation_backend", "implementation_frontend",
    "test_implementation", "docs_update", "docs_projection",
}
NARROW_QUERY_SURFACES = {
    "docs", "governance", "index", "registry", "routing", "closure", "comments",
}
TASK_CONTRACT_FIELDS = (
    "task_shape", "surfaces", "risk", "runtime_claim", "end_to_end_claim",
    "uncertainty", "side_effect_class", "objective", "scope", "acceptance_criteria", "hard_stops",
    "baseline", "dirty_scope", "verification_scope", "direct_interfaces", "previous_failure", "focus",
    "claim_inputs", "task_prompt", "task_prompt_digest", "continuation_mode",
    "operator_loop_request_digest",
)


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def task_contract_projection(normalized_facts: dict[str, Any]) -> dict[str, Any]:
    """Return the exact immutable contract projection shared with Context."""

    return {field: normalized_facts.get(field) for field in TASK_CONTRACT_FIELDS}


def p0b_effect_selection_digest(phase: str) -> str:
    """Return the only admitted selector digest for one P0-B effect phase."""

    if phase not in P0B_CLAIM_KEYS_BY_PHASE:
        raise ValueError(f"invalid P0-B effect phase: {phase}")
    selection = {
        "adapter_id": P0B_ADAPTER_ID,
        "phase": phase,
        "schema_version": "effect_adapter_selection_v1",
    }
    return _sha256_bytes(json.dumps(
        selection, sort_keys=True, separators=(",", ":")
    ).encode("utf-8"))


def _p0b_effect_phase(claim_inputs: dict[str, str]) -> str | None:
    selector = claim_inputs.get("p0b_effect_adapter_selection")
    p0b_keys = set().union(*P0B_CLAIM_KEYS_BY_PHASE.values())
    if selector is None:
        if set(claim_inputs).intersection(p0b_keys):
            raise ValueError("P0-B effect claim_inputs require an exact selection digest")
        return None
    matching = [
        phase for phase in P0B_CLAIM_KEYS_BY_PHASE
        if selector == p0b_effect_selection_digest(phase)
    ]
    if len(matching) != 1:
        raise ValueError("P0-B effect adapter selection digest is invalid")
    phase = matching[0]
    expected = P0B_CLAIM_KEYS_BY_PHASE[phase]
    if set(claim_inputs) != expected:
        raise ValueError(
            "P0-B effect selection digest requires exact claim_inputs: "
            f"missing={sorted(expected - set(claim_inputs))} "
            f"extra={sorted(set(claim_inputs) - expected)}"
        )
    return phase


def _documentation_path(path: str) -> bool:
    pure = PurePosixPath(path)
    lowered = path.casefold()
    return (
        pure.suffix.casefold() in {".md", ".mdx", ".rst", ".adoc"}
        or lowered.startswith(("docs/", "doc/", ".codex/docs/", ".claude/docs/"))
        or pure.name.casefold() in {
            "agents.md", "claude.md", "readme", "readme.md", "todo.md",
        }
    )


def _frontend_path(path: str) -> bool:
    pure = PurePosixPath(path)
    parts = tuple(part.casefold() for part in pure.parts)
    suffix = pure.suffix.casefold()
    frontend_parts = {"frontend", "gui", "ui", "components", "pages", "views"}
    if suffix in {
        ".css", ".scss", ".sass", ".less", ".html", ".jsx", ".tsx",
        ".vue", ".svelte",
    } or any(part in frontend_parts for part in parts):
        return True
    # Plain JavaScript is also used by backend Node services.  Treat it as
    # frontend only inside the repository's known browser-asset roots.
    return suffix in {".js", ".mjs"} and (
        "static" in parts or "assets" in parts
    ) and "control_api_v1" in parts


def _safe_verification_path(value: str) -> str | None:
    """Return one literal repo-relative verification path, never a git pathspec."""

    relative = value.strip()
    path = PurePosixPath(relative)
    if (
        not relative
        or relative in {"."}
        or relative.startswith(("/", "~", "-", "!", ":"))
        or ".." in path.parts
        or any(character in relative for character in ("\0", "\n", "\r", "\\", "*", "?", "["))
    ):
        return None
    normalized = path.as_posix()
    if normalized in {"", "."} or normalized.startswith("../"):
        return None
    return normalized


def _required_role_projection(
    nodes: list[dict[str, Any]], facts: dict[str, Any]
) -> list[dict[str, Any]]:
    """Project the hybrid route onto delegated role nodes and owned write paths."""

    delegated_ids = {
        node["id"] for node in nodes
        if node["kind"] == "role" and node["mandatory"] and node.get("role") != "PM"
    }
    by_id = {node["id"]: node for node in nodes}
    memo: dict[str, set[str]] = {}

    def delegated_predecessors(node_id: str) -> set[str]:
        if node_id in memo:
            return memo[node_id]
        predecessors: set[str] = set()
        for required in by_id[node_id].get("requires", []):
            if required in delegated_ids:
                predecessors.add(required)
            elif required in by_id:
                predecessors.update(delegated_predecessors(required))
        memo[node_id] = predecessors
        return predecessors

    dirty_scope = sorted(facts.get("dirty_scope", []))
    docs_scope = [path for path in dirty_scope if _documentation_path(path)]
    source_scope = [path for path in dirty_scope if path not in docs_scope]
    frontend_scope = [path for path in source_scope if _frontend_path(path)]
    backend_scope = [path for path in source_scope if path not in frontend_scope]
    mixed_docs = "docs_projection" in delegated_ids

    result: list[dict[str, Any]] = []
    for node in nodes:
        if node.get("id") not in delegated_ids:
            continue
        if node.get("node_class") != "work":
            path_scope: list[str] = []
        elif node["id"] == "docs_projection" and mixed_docs:
            path_scope = docs_scope
        elif node["id"] == "implementation" and mixed_docs:
            path_scope = source_scope
        elif node["id"] == "implementation_frontend":
            path_scope = frontend_scope
        elif node["id"] == "implementation_backend":
            path_scope = backend_scope
        else:
            path_scope = dirty_scope
        result.append({
            "node_id": node["id"],
            "role": node["role"],
            "native_agent": node["native_agent"],
            "node_class": node["node_class"],
            "permission": node["permission"],
            "requires": sorted(delegated_predecessors(node["id"])),
            "path_scope": path_scope,
        })
    return result


def _normalize_task_facts(task_facts: dict[str, Any]) -> dict[str, Any]:
    """Validate the typed task-facts seam shared by routing and Context."""

    if not isinstance(task_facts, dict):
        raise ValueError("task facts must be a JSON object")
    unknown_fields = sorted(set(task_facts) - TASK_FACT_FIELDS)
    if unknown_fields:
        raise ValueError(f"task facts contain unknown fields: {', '.join(unknown_fields)}")
    surfaces = task_facts.get("surfaces", [])
    if not isinstance(surfaces, list) or any(
        not isinstance(value, str) or not value.strip() for value in surfaces
    ):
        raise ValueError("task facts surfaces must be a list of non-empty strings")
    normalized_surfaces = {value.strip().lower() for value in surfaces}
    unknown_surfaces = sorted(normalized_surfaces - KNOWN_SURFACES)
    if unknown_surfaces:
        raise ValueError(
            f"task facts surfaces contain unknown values: {', '.join(unknown_surfaces)}"
        )
    for field in ("runtime_claim", "end_to_end_claim"):
        if field in task_facts and not isinstance(task_facts[field], bool):
            raise ValueError(f"task facts {field} must be boolean")
    shape = str(task_facts.get("task_shape", "")).strip().lower()
    valid_shapes = {
        "implementation", "feature", "change", "bug", "fix", "refactor", "migration",
        "deploy", "review", "audit", "analysis", "docs", "documentation", "test",
        "planning", "design", "research", "query",
    }
    if shape not in valid_shapes:
        raise ValueError(f"task facts task_shape is invalid: {shape or '<missing>'}")
    risk = str(task_facts.get("risk", "unknown")).strip().lower()
    if risk not in {"low", "medium", "high", "critical", "unknown"}:
        raise ValueError(f"task facts risk is invalid: {risk}")
    if "uncertainty" not in task_facts:
        raise ValueError("task facts uncertainty is required")
    uncertainty = str(task_facts["uncertainty"]).strip().lower()
    if uncertainty not in UNCERTAINTY_LEVELS:
        raise ValueError(f"task facts uncertainty is invalid: {uncertainty}")
    normalized = dict(task_facts)
    normalized.update(
        task_shape=shape, risk=risk, uncertainty=uncertainty,
        surfaces=sorted(normalized_surfaces),
        runtime_claim=task_facts.get("runtime_claim", False),
        end_to_end_claim=task_facts.get("end_to_end_claim", False),
    )
    continuation_mode = task_facts.get(
        "continuation_mode", DEFAULT_CONTINUATION_MODE
    )
    if continuation_mode not in CONTINUATION_MODES:
        raise ValueError(
            f"task facts continuation_mode is invalid: {continuation_mode}"
        )
    normalized["continuation_mode"] = continuation_mode
    supplied = "side_effect_class" in task_facts
    raw_effect = task_facts.get("side_effect_class")
    if raw_effect is None and not supplied:
        raw_effect = (
            "deploy"
            if shape == "deploy" or "deploy" in normalized_surfaces
            else WRITE_EFFECT_BY_SHAPE.get(
                shape,
                "public_web_read"
                if "public_web_read" in normalized_surfaces
                else "private_external_contact"
                if "private_external_contact" in normalized_surfaces
                else "none",
            )
        )
    if not isinstance(raw_effect, str):
        raise ValueError("task facts side_effect_class must be a string")
    effect = raw_effect.strip().lower()
    if effect not in SIDE_EFFECT_CLASSES:
        raise ValueError(f"task facts side_effect_class is invalid: {effect or '<missing>'}")
    if shape == "deploy" and effect != "deploy":
        raise ValueError("task_shape deploy requires side_effect_class=deploy")
    if "deploy" in normalized_surfaces and effect != "deploy":
        raise ValueError("deploy surface requires side_effect_class=deploy")
    if effect == "deploy" and shape != "deploy" and "deploy" not in normalized_surfaces:
        raise ValueError("side_effect_class=deploy requires task_shape or deploy surface")
    if (
        shape in SOURCE_WRITE_SHAPES
        and "deploy" not in normalized_surfaces
        and effect != "repo_write"
    ):
        raise ValueError(
            f"task_shape {shape} requires side_effect_class=repo_write"
        )
    if shape in {"docs", "documentation"} and effect != "docs_write":
        raise ValueError(
            f"task_shape {shape} requires side_effect_class=docs_write"
        )
    if shape == "test" and effect != "local_test":
        raise ValueError("task_shape test requires side_effect_class=local_test")
    if effect in {"broker_probe", "broker_private_effect"}:
        if not normalized_surfaces.intersection(BROKER_SURFACES):
            raise ValueError(f"side_effect_class={effect} requires a broker surface")
        if "private_external_contact" not in normalized_surfaces:
            raise ValueError(
                f"side_effect_class={effect} requires private_external_contact surface"
            )
    if (
        effect == "private_external_contact"
        and "private_external_contact" not in normalized_surfaces
    ):
        raise ValueError(
            "side_effect_class=private_external_contact requires "
            "private_external_contact surface"
        )
    if effect == "public_web_read":
        if "public_web_read" not in normalized_surfaces:
            raise ValueError(
                "side_effect_class=public_web_read requires public_web_read surface"
            )
        if shape in SOURCE_WRITE_SHAPES | {"docs", "documentation", "test", "deploy"}:
            raise ValueError("side_effect_class=public_web_read requires a read-only task shape")
    if (
        "public_web_read" in normalized_surfaces
        and shape not in SOURCE_WRITE_SHAPES | {"docs", "documentation", "test", "deploy"}
        and effect == "none"
    ):
        raise ValueError("public_web_read surface requires side_effect_class=public_web_read")
    if effect == "repo_write" and shape not in SOURCE_WRITE_SHAPES:
        raise ValueError("side_effect_class=repo_write requires a source-write task shape")
    if effect == "local_test" and shape != "test":
        raise ValueError("side_effect_class=local_test requires task_shape=test")
    if effect == "docs_write" and shape not in {"docs", "documentation"}:
        raise ValueError("side_effect_class=docs_write requires a documentation task shape")
    normalized["side_effect_class"] = effect
    if shape == "query":
        query_errors = []
        if effect != "none":
            query_errors.append("side_effect_class=none")
        if risk != "low" or uncertainty != "low":
            query_errors.append("low risk and low uncertainty")
        if normalized["runtime_claim"] or normalized["end_to_end_claim"]:
            query_errors.append("no runtime or end-to-end claim")
        if normalized_surfaces - NARROW_QUERY_SURFACES:
            query_errors.append("only narrow documentation/governance surfaces")
        if continuation_mode != DEFAULT_CONTINUATION_MODE:
            query_errors.append("continuation_mode=finite")
        direct_interfaces = normalized.get("direct_interfaces", [])
        if not isinstance(direct_interfaces, list) or direct_interfaces:
            query_errors.append("no direct interfaces")
        if query_errors:
            raise ValueError(
                "task_shape query requires " + ", ".join(query_errors)
            )
    for field in ("acceptance_criteria", "hard_stops", "direct_interfaces"):
        if field in normalized and (
            not isinstance(normalized[field], list)
            or any(
                not isinstance(item, str) or not item.strip()
                for item in normalized[field]
            )
        ):
            raise ValueError(f"task facts {field} must be a list of non-empty strings")
    if "objective" in normalized and (
        not isinstance(normalized["objective"], str)
        or not normalized["objective"].strip()
    ):
        raise ValueError("task facts objective must be a non-empty string")
    task_prompt = normalized.get("task_prompt", normalized.get("objective"))
    if not isinstance(task_prompt, str) or not task_prompt.strip():
        raise ValueError("task facts task_prompt must be a non-empty string")
    task_prompt_digest = _sha256_bytes(task_prompt.encode("utf-8"))
    if normalized.get("task_prompt_digest", task_prompt_digest) != task_prompt_digest:
        raise ValueError("task facts task_prompt_digest does not match exact prompt bytes")
    normalized["task_prompt"] = task_prompt
    normalized["task_prompt_digest"] = task_prompt_digest
    request_digest = operator_loop_request_digest(task_prompt)
    if continuation_mode == "operator_loop" and request_digest is None:
        raise ValueError(
            "operator_loop requires a leading /loop control line in the Operator task_prompt"
        )
    expected_loop_digest = request_digest if continuation_mode == "operator_loop" else None
    supplied_loop_digest = task_facts.get("operator_loop_request_digest")
    if (
        "operator_loop_request_digest" in task_facts
        and supplied_loop_digest
        != expected_loop_digest
    ):
        raise ValueError(
            "task facts operator_loop_request_digest does not match exact task_prompt"
        )
    normalized["operator_loop_request_digest"] = expected_loop_digest
    scope = normalized.get("scope")
    if scope is not None and not (
        isinstance(scope, str) and scope.strip()
        or isinstance(scope, list)
        and scope
        and all(isinstance(item, str) and item.strip() for item in scope)
    ):
        raise ValueError("task facts scope must be a non-empty string or string list")
    supplied_dirty_scope = normalized.get("dirty_scope")
    if supplied_dirty_scope is None:
        supplied_dirty_scope = scope if isinstance(scope, list) else []
    if not isinstance(supplied_dirty_scope, list) or any(
        not isinstance(item, str) or not item.strip()
        for item in supplied_dirty_scope
    ):
        raise ValueError("task facts dirty_scope must be a list of non-empty strings")
    safe_dirty_scope: list[str] = []
    for item in supplied_dirty_scope:
        relative = item.strip()
        path = PurePosixPath(relative)
        if relative.startswith(("/", "~")) or ".." in path.parts:
            raise ValueError("task facts dirty_scope must contain safe repo-relative paths")
        if relative not in safe_dirty_scope:
            safe_dirty_scope.append(relative)
    normalized["dirty_scope"] = safe_dirty_scope
    if effect in {"repo_write", "docs_write", "local_test"} and not safe_dirty_scope:
        raise ValueError(
            f"side_effect_class={effect} requires a non-empty dirty_scope"
        )
    supplied_verification_scope = normalized.get("verification_scope", [])
    if not isinstance(supplied_verification_scope, list) or any(
        not isinstance(item, str) or not item.strip()
        for item in supplied_verification_scope
    ):
        raise ValueError(
            "task facts verification_scope must be a list of non-empty strings"
        )
    safe_verification_scope: set[str] = set()
    for item in supplied_verification_scope:
        relative = _safe_verification_path(item)
        if relative is None:
            raise ValueError(
                "task facts verification_scope must contain literal safe repo-relative paths"
            )
        safe_verification_scope.add(relative)
    normalized["verification_scope"] = sorted(safe_verification_scope)
    focus = normalized.get("focus", "")
    if not isinstance(focus, str):
        raise ValueError("task facts focus must be a string")
    normalized["focus"] = focus.strip()
    claim_inputs = normalized.get("claim_inputs", {})
    if (
        not isinstance(claim_inputs, dict)
        or any(
            not isinstance(key, str) or not key.strip()
            or not isinstance(value, str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", value)
            for key, value in claim_inputs.items()
        )
    ):
        raise ValueError("task facts claim_inputs must map non-empty names to sha256 digests")
    normalized["claim_inputs"] = {
        key.strip(): claim_inputs[key] for key in sorted(claim_inputs)
    }
    if "previous_failure" in normalized and not isinstance(
        normalized["previous_failure"], str
    ):
        raise ValueError("task facts previous_failure must be a string")
    return normalized


def route_task(task_facts: dict[str, Any]) -> dict[str, Any]:
    """Compile task facts into the mandatory hybrid DAG."""

    facts = _normalize_task_facts(task_facts)
    surfaces, shape, risk = set(facts["surfaces"]), facts["task_shape"], facts["risk"]
    uncertainty = facts["uncertainty"]
    runtime_claim = facts.get("runtime_claim", False)
    end_to_end_claim = facts.get("end_to_end_claim", False)
    effect = facts["side_effect_class"]
    p0b_phase = _p0b_effect_phase(facts["claim_inputs"])
    if p0b_phase is not None:
        if not (
            effect == "deploy"
            and facts["runtime_claim"] is True
            and {"authority", "service", "runtime_effect"}.issubset(surfaces)
            and risk in {"high", "critical"}
        ):
            raise ValueError(
                "P0-B effect selection requires deploy, runtime_claim=true, "
                "authority/service/runtime_effect surfaces, and high or critical risk"
            )
    implementation = shape in SOURCE_WRITE_SHAPES
    full_stack_implementation = bool(
        implementation
        and "gui" in surfaces
        and surfaces.intersection({"python", "rust", "ml_data"})
    )
    if full_stack_implementation:
        implementation_scope = [
            path for path in facts["dirty_scope"] if not _documentation_path(path)
        ]
        frontend_scope = [path for path in implementation_scope if _frontend_path(path)]
        backend_scope = [path for path in implementation_scope if path not in frontend_scope]
        if not frontend_scope or not backend_scope:
            missing = "frontend" if not frontend_scope else "backend"
            raise ValueError(
                "mixed GUI/backend implementation requires non-empty disjoint "
                f"frontend and backend dirty_scope ownership; missing {missing} paths"
            )
    deploy = effect == "deploy"
    unsupported_effect = effect in UNSUPPORTED_EFFECT_CLASSES
    operations_needed = deploy or runtime_claim or bool(surfaces & OPERATION_SURFACES)
    unknown_risk = risk not in {"low", "medium", "high", "critical"}
    unknown_uncertainty = uncertainty == "unknown"
    narrow_query = shape == "query"
    nodes: list[dict[str, Any]] = []

    def add(
        node_id: str, *, role: str | None = None, kind: str = "role",
        requires: Iterable[str] = (), mandatory: bool = True, reason: str,
        **metadata: Any,
    ) -> None:
        node = {
            "id": node_id, "kind": kind, "requires": list(requires),
            "mandatory": mandatory, "reason": reason,
        }
        if role:
            node["role"] = role
            if role != "PM":
                node.update(native_agent_binding(
                    role, "work" if node_id in ROUTED_WORK_NODES else "verification"
                ))
        node.update(metadata)
        nodes.append(node)

    add("pm_triage", role="PM", reason="bind task facts, authority classes, acceptance, and scope")
    predecessor = "pm_triage"
    design_needed = not narrow_query and (
        shape in {"design", "planning", "analysis", "research", "audit"}
        or deploy or risk in {"high", "critical"}
        or uncertainty in {"high", "unknown"}
        or bool(surfaces & {"architecture", "authority", "schema", "cross_interface"})
    )
    if design_needed:
        add("pa_design", role="PA", requires=[predecessor], reason="cross-interface or high-risk design")
        predecessor = "pa_design"
    docs_change, test_change = shape in {"docs", "documentation"}, shape == "test"
    if narrow_query:
        pass
    elif docs_change:
        add("docs_update", role="TW", requires=[predecessor], reason="task-owned documentation projection")
        add("docs_review", role="R4", requires=["docs_update"], reason="documentation/index integrity hard edge")
        predecessor = "docs_review"
    elif test_change:
        add("test_implementation", role="E4", requires=[predecessor], reason="test-only implementation owner")
        add("test_adversarial_review", role="E2", requires=["test_implementation"], reason="tests must prove behavior rather than ceremony")
        predecessor = "test_adversarial_review"
    elif implementation:
        if full_stack_implementation:
            add(
                "implementation_backend", role="E1", requires=[predecessor],
                reason="mixed task backend source owner",
            )
            add(
                "implementation_frontend", role="E1a",
                requires=["implementation_backend"],
                reason="mixed task frontend/GUI source owner",
            )
            add(
                "implementation_join", kind="join",
                requires=["implementation_backend", "implementation_frontend"],
                reason="both full-stack builders complete before independent review",
            )
            review_requires = ["implementation_join"]
        else:
            builder = "E1a" if "gui" in surfaces else "E1"
            add("implementation", role=builder, requires=[predecessor], reason="task changes source")
            review_requires = ["implementation"]
        add("independent_review", role="E2", requires=review_requires, reason="implementation hard edge")
        add("regression", role="E4", requires=["independent_review"], reason="implementation hard edge")
        predecessor = "regression"
    elif shape == "review" and (not surfaces or surfaces & SOURCE_REVIEW_SURFACES):
        add("independent_review", role="E2", requires=[predecessor], reason="source correctness review owner")
        predecessor = "independent_review"

    gates: list[str] = []
    gate_specs = [
        ("functional_review", "FA", surfaces & {"functional", "acceptance", "spec"}, "functional outcome semantics changed"),
        ("constitutional_gate", "CC", surfaces & {"authority", "live", "risk", "auth", "hard_boundary", "policy", "compliance", "full_audit"} or unknown_risk or unknown_uncertainty, "normative authority or unknown risk/uncertainty"),
        ("security_gate", "E3", surfaces & {"authority", "live", "risk", "auth", "security", "secret", "ipc", "ffi", "private_external_contact"} or operations_needed or unsupported_effect, "security/effect boundary hard edge"),
        ("quant_review", "QC", surfaces & {"quant", "strategy", "portfolio", "alpha", "profitability", "risk_model"}, "quantitative semantics changed"),
        ("data_ml_review", "MIT", surfaces & {"ml", "ml_data", "data", "schema", "evidence_methodology"}, "data/ML/schema semantics changed"),
        ("ai_economics_review", "AI-E", surfaces & {"ai", "llm", "agent_workflow", "full_audit", "model_routing", "multi_agent", "consumption"}, "AI or orchestration economics matter"),
        ("profit_control", "AI-E", "profit_diagnosis" in surfaces, "profit diagnosis requires the Registry profit-control contract"),
        ("performance_review", "E5", surfaces & {"performance", "simplification", "large_file"}, "performance or maintainability claim"),
        ("ux_review", "A3", surfaces & {"gui", "ux", "accessibility", "visual"}, "operator-visible GUI/UX claim"),
    ]
    for node_id, role, triggered, reason in gate_specs:
        if narrow_query:
            continue
        if triggered:
            add(node_id, role=role, requires=[predecessor], reason=reason)
            gates.append(node_id)
    if not narrow_query and surfaces & DOC_SURFACES and not docs_change:
        docs_predecessor = predecessor
        if implementation:
            add("docs_projection", role="TW", requires=[predecessor], reason="mixed source/docs task keeps documentation ownership explicit")
            docs_predecessor = "docs_projection"
        add("docs_integrity_review", role="R4", requires=[docs_predecessor], reason="documentation/governance/index surface")
        gates.append("docs_integrity_review")
    if "bybit" in surfaces:
        add("broker_bybit_gate", role="BB", requires=[predecessor], reason="Bybit Adapter selected")
        gates.append("broker_bybit_gate")
    if surfaces & {"ibkr", "tws", "stock_etf_cash", "broker_session"}:
        add("broker_ibkr_gate", role="IB", requires=[predecessor], reason="IBKR Adapter selected")
        gates.append("broker_ibkr_gate")

    if operations_needed:
        add("ops_preflight", role="OPS", requires=[predecessor, *gates], reason="runtime/deploy preflight hard edge")
        postcheck_requires = ["ops_preflight"]
        if deploy:
            if p0b_phase is None:
                add("pm_deploy_approval", role="PM", requires=["ops_preflight"], reason="operator/PM authorizes exact intent; not verification")
                add("deploy_adapter_v1", kind="effect_adapter", requires=["pm_deploy_approval"], reason="generic deployment intent-validation seam")
                postcheck_requires = ["deploy_adapter_v1"]
            else:
                approval_id = f"pm_p0b_{p0b_phase}_approval"
                add(
                    approval_id, role="PM", requires=["ops_preflight"],
                    reason=f"operator/PM authorizes the exact P0-B {p0b_phase} intent; not verification",
                )
                add(
                    P0B_ADAPTER_ID, kind="effect_adapter",
                    requires=[approval_id],
                    reason=f"purpose-built P0-B {p0b_phase} effect seam",
                    effect_phase=p0b_phase,
                    intent_schema_version="p0b_alr_rollforward_intent_v1",
                    result_schema_version="p0b_alr_rollforward_effect_result_v1",
                )
                postcheck_requires = [P0B_ADAPTER_ID]
        add("ops_postcheck", role="OPS", requires=postcheck_requires, reason="independent operational evidence")
        predecessor = "ops_postcheck"
    elif unsupported_effect:
        if len(gates) == 1:
            predecessor = gates[0]
        elif gates:
            add("gate_join", kind="join", requires=gates, reason="all independently triggered gates must complete before an effect decision")
            predecessor = "gate_join"
        unsupported_id = "broker_effect_unsupported_v1" if effect in {"broker_probe", "broker_private_effect"} else "external_effect_unsupported_v1"
        add(unsupported_id, kind="unsupported_effect", requires=[predecessor], reason=f"{effect} has no closure-admissible deterministic Adapter; the workflow must remain blocked until that Interface exists")
        predecessor = unsupported_id
    elif len(gates) == 1:
        predecessor = gates[0]
    elif gates:
        add("gate_join", kind="join", requires=gates, reason="all independently triggered gates must complete before acceptance or closure")
        predecessor = "gate_join"
    if end_to_end_claim:
        add("business_acceptance", role="QA", requires=[predecessor], reason="end-to-end claim hard edge")
        predecessor = "business_acceptance"
    add("pm_closure", role="PM", requires=[predecessor], reason="integrate evidence and dissent without replacing gates")

    roles = [node["role"] for node in nodes if node["kind"] == "role"]
    possible = {"PA", "FA", "CC", "E1", "E1a", "E2", "E3", "E4", "E5", "QA", "QC", "MIT", "AI-E", "BB", "IB", "OPS", "A3", "R4", "TW"}
    skipped = [
        {
            "role": role,
            "reason": "task facts did not trigger this capability preset",
            "residual_risk": "coverage debt: risk, uncertainty, or surface facts are incomplete" if unknown_risk or unknown_uncertainty else "bounded by declared task facts; reopen on evidence or surface drift",
            "owner": "PM",
        }
        for role in sorted(possible - set(roles))
    ]
    required_role_nodes = _required_role_projection(nodes, facts)
    result = {
        "schema_version": "hybrid_execution_dag_v1",
        "task_facts": facts,
        "task_execution_control": compile_task_execution_policy(
            task_contract_projection(facts)
        ),
        "risk_state": "UNKNOWN" if unknown_risk else risk.upper(),
        "budget_envelope": (
            "profit_diagnosis"
            if "profit_diagnosis" in surfaces
            else "full_audit"
            if unknown_risk or unknown_uncertainty
            else "complex"
            if risk in {"high", "critical"} or uncertainty == "high"
            else "narrow"
            if risk == "low" and uncertainty == "low"
            else "standard"
        ),
        "roles": roles,
        "nodes": nodes,
        "required_role_nodes": required_role_nodes,
        "skipped": skipped,
    }
    delegated, dag_errors = delegated_execution_projection(
        required_role_nodes,
        [],
        excluded_nodes=non_call_controller_node_ids(facts),
    )
    if dag_errors:
        raise ValueError("invalid delegated execution projection: " + "; ".join(dag_errors))
    result["dag_digest"] = execution_dag_digest(delegated)
    return result
