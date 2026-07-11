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
SHADOW_RE = re.compile(
    r"\b(?:AUTHORITY_PROFILES|CONTEXT_(?:ARTIFACT|PLAN|BUDGET)_FIELDS|"
    r"TASK_CONTRACT_FIELDS|MANDATORY_CONTEXT_FIELDS)\b|"
    r"\bconst\s+(?:artifactFields|planFields|contextFields|contractFields|"
    r"mandatoryFields|budgetFields|authorityFields|trustedKinds|producerByKind|"
    r"ttlByKind|expectedTrustedKinds)\b"
)


def authority_profiles(registry: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Project the one Registry budget authority into saved-workflow JS."""

    return {
        name: {
            "accounting_basis": envelope["accounting_basis"],
            "max_context_tokens_per_call": envelope["max_context_tokens_per_call"],
            "max_prompt_utf8_bytes_per_call": envelope["max_prompt_utf8_bytes_per_call"],
            "max_workflow_planned_input_tokens": envelope["max_workflow_planned_input_tokens"],
            "max_unique_nodes": envelope["max_unique_nodes"],
            "max_call_attempts": envelope["max_call_attempts"],
            "retry_budget": envelope["retry_budget"],
            "target_context_tokens": envelope["target_context_tokens"],
            "quality_reserve_context_tokens": envelope["quality_reserve_context_tokens"],
        }
        for name, envelope in sorted(registry["budget_envelopes"].items())
    }


def render_context_admission_block(
    registry: dict[str, Any] | None = None,
) -> str:
    registry = registry or load_registry()
    template = TEMPLATE.read_text(encoding="utf-8").rstrip()
    if template.count(TOKEN) != 1 or template.count(TRUSTED_KINDS_TOKEN) != 1:
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
    rendered = template.replace(TOKEN, profiles).replace(
        TRUSTED_KINDS_TOKEN, trusted_kinds
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
