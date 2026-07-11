"""Registry budget-envelope schema and cross-field invariants."""

from __future__ import annotations

from typing import Any


FIELDS = {
    "target_context_tokens", "quality_reserve_context_tokens",
    "accounting_basis", "max_prompt_utf8_bytes_per_call",
    "max_context_tokens_per_call", "max_workflow_planned_input_tokens",
    "max_unique_nodes", "max_call_attempts", "retry_budget",
}


def registry_budget_errors(envelopes: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for name, envelope in envelopes.items():
        if not isinstance(envelope, dict) or set(envelope) != FIELDS:
            errors.append(f"{name}: budget envelope fields must be exact Registry authority")
            continue
        if envelope.get("accounting_basis") != "utf8_bytes_div4_planned_lower_bound_v1":
            errors.append(f"{name}: accounting_basis must identify the deterministic planned lower bound")
            continue
        positive = [
            value for field, value in envelope.items()
            if field not in {"retry_budget", "accounting_basis"}
        ]
        if not all(type(value) is int and value > 0 for value in positive):
            errors.append(f"{name}: budget fields must be positive integers")
        elif type(envelope["retry_budget"]) is not int or envelope["retry_budget"] < 0:
            errors.append(f"{name}: retry_budget must be a non-negative integer")
        elif envelope["max_context_tokens_per_call"] <= envelope["target_context_tokens"] + envelope["quality_reserve_context_tokens"]:
            errors.append(f"{name}: per-call planned-input cap must leave a reviewed single-call band")
        elif envelope["max_prompt_utf8_bytes_per_call"] != 4 * (envelope["max_context_tokens_per_call"] - 1):
            errors.append(f"{name}: exact prompt byte cap must match the exclusive planned-input ceiling")
        elif envelope["max_call_attempts"] != envelope["max_unique_nodes"] + envelope["retry_budget"]:
            errors.append(f"{name}: max_call_attempts must equal unique nodes plus workflow retry budget")
        elif envelope["max_workflow_planned_input_tokens"] < envelope["max_call_attempts"] * envelope["max_context_tokens_per_call"]:
            errors.append(f"{name}: workflow cap must reserve the declared worst-case call attempts")
    return errors
