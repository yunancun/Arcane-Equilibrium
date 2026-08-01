#!/usr/bin/env python3
"""Deterministic shared-block renderer for standalone saved workflows."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from agent_governance_registry import (
    REPO_ROOT,
    load_registry,
    native_agent_binding,
    registry_digest,
)
from agent_governance_context_specs import trusted_derived_kinds
from agent_governance_execution_policy import (
    compile_execution_budget_policy,
    default_history_binding,
    surface_profile_binding,
)
from agent_governance_vocabulary import KNOWN_SURFACES
from agent_governance_routing import (
    BROKER_SURFACES,
    DOC_SURFACES,
    NARROW_QUERY_SURFACES,
    OPERATION_SURFACES,
    P0B_CLAIM_KEYS_BY_PHASE,
    PROGRAM_REVIEW_NODES,
    S2_CLAIM_KEYS_BY_STEP,
    S2_EFFECT_STEPS,
    SIDE_EFFECT_CLASSES,
    SOURCE_REVIEW_SURFACES,
    SOURCE_WRITE_SHAPES,
    UNSUPPORTED_EFFECT_CLASSES,
    p0b_effect_selection_digest,
    s2_effect_selection_digest,
)
from agent_governance_aiml_adoption import (
    AIML_PROGRAM_ADOPTION_CLAIM_KEYS,
    AIML_PROGRAM_ADOPTION_PREDECESSOR_DIGESTS,
    AIML_PROGRAM_ADOPTION_SELECTOR_DIGEST,
    AIML_PROGRAM_ADOPTION_SURFACES,
)


TEMPLATE = REPO_ROOT / ".claude/workflows/context-admission-v1.fragment.js"
WORKFLOWS = (
    REPO_ROOT / ".claude/workflows/agent-wave.js",
    REPO_ROOT / ".claude/workflows/openclaw-full-audit.js",
    REPO_ROOT / ".claude/workflows/profit-diagnosis.js",
)
BEGIN = "// BEGIN GENERATED CONTEXT_ADMISSION_V1"
END = "// END GENERATED CONTEXT_ADMISSION_V1"
TOKEN = "__CONTEXT_AUTHORITY_PROFILES__"
TRUSTED_KINDS_TOKEN = "__CONTEXT_TRUSTED_KINDS__"
SURFACE_BINDINGS_TOKEN = "__EXECUTION_SURFACE_BINDINGS__"
DEFAULT_HISTORY_TOKEN = "__DEFAULT_REQUESTED_HISTORY__"
SAVED_WORKFLOW_MODEL_POLICY_TOKEN = "__SAVED_WORKFLOW_MODEL_POLICY__"
REGISTRY_DIGEST_TOKEN = "__REGISTRY_DIGEST__"
DAG_ROLE_BINDINGS_TOKEN = "__DAG_ROLE_BINDINGS__"
KNOWN_SURFACES_TOKEN = "__KNOWN_SURFACES__"
CONTROLLER_PERMISSION_TOKEN = "__CONTROLLER_PERMISSION__"
ROUTE_POLICY_TOKEN = "__GENERIC_ROUTE_POLICY__"
SHADOW_RE = re.compile(
    r"\b(?:AUTHORITY_PROFILES|CONTEXT_(?:ARTIFACT|PLAN|BUDGET)_FIELDS|"
    r"TASK_CONTRACT_FIELDS|MANDATORY_CONTEXT_FIELDS)\b|"
    r"\bconst\s+(?:artifactFields|planFields|contextFields|contractFields|"
    r"mandatoryFields|budgetFields|authorityFields|trustedKinds|producerByKind|"
    r"ttlByKind|expectedTrustedKinds)\b"
)


def authority_profiles(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Project the one Registry budget authority into saved-workflow JS."""

    return {
        name: compile_execution_budget_policy(name, registry)
        for name in sorted(registry["budget_envelopes"])
    }


def dag_role_bindings(
    registry: dict[str, Any],
) -> dict[str, dict[str, dict[str, str]]]:
    """Project exact Registry native bindings used by JS DAG validation."""

    projected: dict[str, dict[str, dict[str, str]]] = {}
    for role in sorted(registry["roles"]):
        classes: dict[str, dict[str, str]] = {}
        for node_class in ("verification", "work"):
            try:
                binding = native_agent_binding(role, node_class, registry)
            except ValueError:
                continue
            classes[node_class] = {
                "native_agent": binding["native_agent"],
                "permission": binding["permission"],
            }
        if classes:
            projected[role] = classes
    return projected


def render_context_admission_block(
    registry: dict[str, Any] | None = None,
) -> str:
    registry = load_registry() if registry is None else registry
    if not isinstance(registry, dict) or not registry:
        raise ValueError("Registry must be a non-empty object")
    template = TEMPLATE.read_text(encoding="utf-8").rstrip()
    tokens = (
        TOKEN,
        TRUSTED_KINDS_TOKEN,
        SURFACE_BINDINGS_TOKEN,
        DEFAULT_HISTORY_TOKEN,
        SAVED_WORKFLOW_MODEL_POLICY_TOKEN,
        REGISTRY_DIGEST_TOKEN,
        DAG_ROLE_BINDINGS_TOKEN,
        KNOWN_SURFACES_TOKEN,
        CONTROLLER_PERMISSION_TOKEN,
        ROUTE_POLICY_TOKEN,
    )
    if any(template.count(token) != 1 for token in tokens):
        raise ValueError("Context admission template tokens must each occur once")
    profiles = json.dumps(
        authority_profiles(registry),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    trusted_kinds = json.dumps(
        trusted_derived_kinds(registry),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    surface_bindings = json.dumps(
        {
            profile_id: surface_profile_binding(profile_id, registry)
            for profile_id in sorted(
                registry["execution_policy"]["surface_profiles"]
            )
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    history = json.dumps(
        default_history_binding(registry),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    saved_workflow_model_policy = json.dumps(
        registry["saved_workflow_model_policy"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    admitted_registry_digest = json.dumps(registry_digest(registry))
    admitted_dag_role_bindings = json.dumps(
        dag_role_bindings(registry),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    admitted_known_surfaces = json.dumps(
        sorted(KNOWN_SURFACES),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    admitted_controller_permission = json.dumps(
        registry["roles"]["PM"]["permission"]
    )
    admitted_route_policy = json.dumps(
        {
            "source_write_shapes": sorted(SOURCE_WRITE_SHAPES),
            "source_review_surfaces": sorted(SOURCE_REVIEW_SURFACES),
            "operation_surfaces": sorted(OPERATION_SURFACES),
            "doc_surfaces": sorted(DOC_SURFACES),
            "broker_surfaces": sorted(BROKER_SURFACES),
            "narrow_query_surfaces": sorted(NARROW_QUERY_SURFACES),
            "side_effect_classes": sorted(SIDE_EFFECT_CLASSES),
            "unsupported_effect_classes": sorted(UNSUPPORTED_EFFECT_CLASSES),
            "program_review_nodes": PROGRAM_REVIEW_NODES,
            "aiml_adoption": {
                "selector_digest": AIML_PROGRAM_ADOPTION_SELECTOR_DIGEST,
                "claim_keys": sorted(AIML_PROGRAM_ADOPTION_CLAIM_KEYS),
                "predecessor_digests": AIML_PROGRAM_ADOPTION_PREDECESSOR_DIGESTS,
                "surfaces": sorted(AIML_PROGRAM_ADOPTION_SURFACES),
            },
            "p0b_phases": {
                phase: {
                    "selector_digest": p0b_effect_selection_digest(phase),
                    "claim_keys": sorted(P0B_CLAIM_KEYS_BY_PHASE[phase]),
                }
                for phase in sorted(P0B_CLAIM_KEYS_BY_PHASE)
            },
            "s2_steps": {
                step: {
                    "selector_digest": s2_effect_selection_digest(step),
                    "claim_keys": sorted(S2_CLAIM_KEYS_BY_STEP[step]),
                    "side_effect_class": S2_EFFECT_STEPS[step][
                        "side_effect_class"
                    ],
                }
                for step in sorted(S2_EFFECT_STEPS)
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    rendered = (
        template.replace(TOKEN, profiles)
        .replace(TRUSTED_KINDS_TOKEN, trusted_kinds)
        .replace(SURFACE_BINDINGS_TOKEN, surface_bindings)
        .replace(DEFAULT_HISTORY_TOKEN, history)
        .replace(
            SAVED_WORKFLOW_MODEL_POLICY_TOKEN,
            saved_workflow_model_policy,
        )
        .replace(REGISTRY_DIGEST_TOKEN, admitted_registry_digest)
        .replace(DAG_ROLE_BINDINGS_TOKEN, admitted_dag_role_bindings)
        .replace(KNOWN_SURFACES_TOKEN, admitted_known_surfaces)
        .replace(CONTROLLER_PERMISSION_TOKEN, admitted_controller_permission)
        .replace(ROUTE_POLICY_TOKEN, admitted_route_policy)
    )
    return f"{BEGIN}\n{rendered}\n{END}"


def _embedded(source: str) -> str | None:
    if source.count(BEGIN) != 1 or source.count(END) != 1:
        return None
    start = source.index(BEGIN)
    finish = source.index(END, start) + len(END)
    return source[start:finish]


def workflow_context_codegen_errors(
    registry: dict[str, Any] | None = None,
) -> list[str]:
    expected = render_context_admission_block(registry)
    errors: list[str] = []
    for path in WORKFLOWS:
        source = path.read_text(encoding="utf-8")
        embedded = _embedded(source)
        if embedded != expected:
            errors.append(f"{path.relative_to(REPO_ROOT)} shared Context block drift")
        remainder = source.replace(embedded or "", "", 1)
        if re.search(r"(?m)^\s*import(?:\s|\()", remainder) or re.search(
            r"\brequire\s*\(", remainder
        ):
            errors.append(
                f"{path.relative_to(REPO_ROOT)} violates standalone AsyncFunction loader"
            )
        if SHADOW_RE.search(remainder):
            errors.append(
                f"{path.relative_to(REPO_ROOT)} shadows generated Context contract"
            )
        if "contextPrefixV1(" not in remainder:
            errors.append(
                f"{path.relative_to(REPO_ROOT)} does not consume generated Context prefix"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.check == args.write:
        parser.error("select exactly one of --check or --write")
    if args.write:
        expected = render_context_admission_block()
        for path in WORKFLOWS:
            source = path.read_text(encoding="utf-8")
            embedded = _embedded(source)
            if embedded is None:
                raise ValueError(f"{path.relative_to(REPO_ROOT)} lacks one generated block")
            path.write_text(source.replace(embedded, expected, 1), encoding="utf-8")
        return 0
    errors = workflow_context_codegen_errors()
    print(json.dumps({"status": "PASS" if not errors else "FAIL", "errors": errors}))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
