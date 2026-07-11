"""Independent workflow receipt budget/cap validation."""

from __future__ import annotations

import hashlib
import json
from typing import Any


BUDGET_AUTHORITY_FIELDS = {"authority_digest", "authority_canonical", "admitted_caps"}
ADMITTED_CAP_FIELDS = {
    "max_context_tokens_per_call", "max_prompt_utf8_bytes_per_call",
    "max_workflow_planned_input_tokens",
    "max_unique_nodes", "max_call_attempts", "retry_budget",
}
CONTEXT_AUTHORITY_FIELDS = {
    "schema_version", "envelope", "accounting_basis", *ADMITTED_CAP_FIELDS,
}


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def workflow_budget_errors(
    budget: Any, *, tasks: list[dict[str, Any]], first_records: list[dict[str, Any]],
    retry_records: list[dict[str, Any]], records: list[dict[str, Any]],
    scheduled_admitted: int,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(budget, dict) or set(budget) != BUDGET_AUTHORITY_FIELDS:
        return ["workflow wave budget_authority fields do not match contract"]
    canonical = budget.get("authority_canonical")
    authority = None
    if not isinstance(canonical, str) or not canonical:
        errors.append("workflow wave budget authority canonical value is invalid")
    else:
        try:
            authority = json.loads(canonical)
            rendered = json.dumps(authority, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            if rendered != canonical:
                errors.append("workflow wave budget authority is not canonical JSON")
            digest = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if budget.get("authority_digest") != digest:
                errors.append("workflow wave budget authority digest differs from canonical bytes")
        except (TypeError, ValueError, json.JSONDecodeError):
            errors.append("workflow wave budget authority canonical value is invalid JSON")
    caps = budget.get("admitted_caps")
    if not isinstance(caps, dict) or set(caps) != ADMITTED_CAP_FIELDS:
        errors.append("workflow wave admitted caps fields do not match contract")
        return errors
    if any(not _nonnegative_int(value) for value in caps.values()):
        errors.append("workflow wave admitted caps must be non-negative integers")
        return errors
    if not isinstance(authority, dict) or set(authority) != CONTEXT_AUTHORITY_FIELDS:
        errors.append("workflow wave Context authority fields do not match contract")
        return errors
    if authority.get("accounting_basis") != "utf8_bytes_div4_planned_lower_bound_v1":
        errors.append("workflow wave Context accounting basis is invalid")
    if caps != {field: authority[field] for field in ADMITTED_CAP_FIELDS}:
        errors.append("workflow wave admitted caps differ from Context authority")
    if caps["max_call_attempts"] != caps["max_unique_nodes"] + caps["retry_budget"]:
        errors.append("workflow wave attempt cap differs from unique nodes plus retry budget")
    if len(tasks) > caps["max_unique_nodes"] or len(first_records) > caps["max_unique_nodes"]:
        errors.append("workflow wave unique-node cap was exceeded")
    if len(retry_records) > caps["retry_budget"]:
        errors.append("workflow wave retry budget was exceeded")
    if len(records) > caps["max_call_attempts"]:
        errors.append("workflow wave call-attempt cap was exceeded")
    if scheduled_admitted > caps["max_workflow_planned_input_tokens"]:
        errors.append("workflow wave planned-input cap was exceeded")
    if any(record.get("admitted_input_tokens_lower_bound", 0) >= caps["max_context_tokens_per_call"] for record in records):
        errors.append("workflow wave per-call planned-input cap was exceeded")
    return errors


def workflow_budget_matches_context(budget: Any, context_artifact: Any) -> bool:
    """Exact cross-binding used by workflow-specific closure validators."""

    if not isinstance(budget, dict) or not isinstance(context_artifact, dict):
        return False
    try:
        authority = json.loads(context_artifact["budget_authority_canonical"])
        caps = {field: authority[field] for field in ADMITTED_CAP_FIELDS}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return (
        budget.get("authority_canonical") == context_artifact.get("budget_authority_canonical")
        and budget.get("authority_digest") == context_artifact.get("budget_authority_digest")
        and budget.get("admitted_caps") == caps
    )
