#!/usr/bin/env python3
"""Deterministic shared-block renderer for standalone saved workflows."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from agent_governance_registry import REPO_ROOT, load_registry
from agent_governance_context_specs import trusted_derived_kinds
from agent_governance_execution_policy import (
    compile_execution_budget_policy,
    default_history_binding,
    surface_profile_binding,
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


def render_context_admission_block(
    registry: dict[str, Any] | None = None,
) -> str:
    registry = registry or load_registry()
    template = TEMPLATE.read_text(encoding="utf-8").rstrip()
    tokens = (
        TOKEN,
        TRUSTED_KINDS_TOKEN,
        SURFACE_BINDINGS_TOKEN,
        DEFAULT_HISTORY_TOKEN,
        SAVED_WORKFLOW_MODEL_POLICY_TOKEN,
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
    rendered = (
        template.replace(TOKEN, profiles)
        .replace(TRUSTED_KINDS_TOKEN, trusted_kinds)
        .replace(SURFACE_BINDINGS_TOKEN, surface_bindings)
        .replace(DEFAULT_HISTORY_TOKEN, history)
        .replace(
            SAVED_WORKFLOW_MODEL_POLICY_TOKEN,
            saved_workflow_model_policy,
        )
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
