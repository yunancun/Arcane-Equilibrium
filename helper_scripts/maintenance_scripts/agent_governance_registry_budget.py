"""Registry budget-envelope schema and cross-field invariants."""

from __future__ import annotations

from typing import Any


FIELDS = {
    "target_context_tokens", "quality_reserve_context_tokens",
    "accounting_basis", "max_prompt_utf8_bytes_per_call",
    "max_context_tokens_per_call", "max_workflow_planned_input_tokens",
    "max_unique_nodes", "max_call_attempts", "retry_budget",
    "max_followup_attempts", "max_total_model_turns", "max_wait_cycles",
    "max_no_delta_wakeups", "max_wall_clock_ms", "max_call_duration_ms",
    "max_wave_duration_ms", "max_concurrent_calls",
    "max_spawn_depth_from_root",
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
        nonnegative_fields = {
            "retry_budget", "max_followup_attempts", "max_no_delta_wakeups",
        }
        positive = [
            value for field, value in envelope.items()
            if field not in {*nonnegative_fields, "accounting_basis"}
        ]
        if not all(type(value) is int and value > 0 for value in positive):
            errors.append(f"{name}: budget fields must be positive integers")
        elif any(
            type(envelope[field]) is not int or envelope[field] < 0
            for field in nonnegative_fields
        ):
            errors.append(f"{name}: retry/follow-up/no-delta caps must be non-negative")
        elif envelope["max_context_tokens_per_call"] <= envelope["target_context_tokens"] + envelope["quality_reserve_context_tokens"]:
            errors.append(f"{name}: per-call planned-input cap must leave a reviewed single-call band")
        elif envelope["max_prompt_utf8_bytes_per_call"] != 4 * (envelope["max_context_tokens_per_call"] - 1):
            errors.append(f"{name}: exact prompt byte cap must match the exclusive planned-input ceiling")
        elif envelope["max_call_attempts"] != envelope["max_unique_nodes"] + envelope["retry_budget"]:
            errors.append(f"{name}: max_call_attempts must equal unique nodes plus workflow retry budget")
        elif envelope["max_total_model_turns"] != (
            1 + envelope["max_call_attempts"] + envelope["max_followup_attempts"]
        ):
            errors.append(
                f"{name}: total model-turn cap must exact-cover root, calls, and follow-ups"
            )
        elif not (
            envelope["max_call_duration_ms"]
            <= envelope["max_wave_duration_ms"]
            <= envelope["max_wall_clock_ms"]
        ):
            errors.append(f"{name}: call/wave/wall deadlines must be monotonic")
        elif envelope["max_concurrent_calls"] > envelope["max_unique_nodes"]:
            errors.append(f"{name}: concurrency cap cannot exceed unique-node cap")
        elif envelope["max_spawn_depth_from_root"] != 1:
            errors.append(f"{name}: recursive child spawning must be denied by default")
        elif envelope["max_workflow_planned_input_tokens"] < envelope["max_call_attempts"] * envelope["max_context_tokens_per_call"]:
            errors.append(f"{name}: workflow cap must reserve the declared worst-case call attempts")
    return errors
