"""Test-evidence signature and reuse Implementation for Agent Governance."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from agent_governance_execution import DIGEST_RE, TEST_EVIDENCE_FIELDS, _sha256_bytes


def test_evidence_signature(facts: dict[str, Any]) -> str:
    """Return the exact content/environment signature for reusable test proof."""

    missing = TEST_EVIDENCE_FIELDS - set(facts)
    if missing:
        raise ValueError(f"test evidence facts missing: {sorted(missing)}")
    unexpected = set(facts) - TEST_EVIDENCE_FIELDS
    if unexpected:
        raise ValueError(f"test evidence facts contain unsigned fields: {sorted(unexpected)}")
    canonical = {field: facts[field] for field in sorted(TEST_EVIDENCE_FIELDS)}
    return _sha256_bytes(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _receipt_digest(receipt: dict[str, Any]) -> str:
    payload = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    return _sha256_bytes(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def evidence_receipt_digest(receipt: dict[str, Any]) -> str:
    """Public canonical digest for typed execution/recheck/reuse receipts."""

    return _receipt_digest(receipt)


EXECUTION_RECEIPT_FIELDS = {
    "schema_version",
    "signature",
    "facts",
    "executor_role",
    "started_at",
    "completed_at",
    "exit_code",
    "result",
    "evidence_digest",
    "output_digest",
    "receipt_digest",
}
RECHECK_RECEIPT_FIELDS = {
    "schema_version",
    "execution_receipt_digest",
    "signature",
    "source_head",
    "dirty_diff_hash",
    "untracked_relevant_hash",
    "command",
    "selected_tests",
    "reviewer_role",
    "observed_at",
    "result",
    "evidence_digest",
    "receipt_digest",
}
REUSE_RECEIPT_FIELDS = {
    "schema_version",
    "eligible",
    "status",
    "reason",
    "current_signature",
    "reused_from",
    "created_at",
    "expires_at",
    "assessed_at",
    "execution_evidence_digest",
    "execution_receipt",
    "execution_receipt_digest",
    "executor_role",
    "critical",
    "independent_recheck_receipt",
    "independent_recheck_receipt_digest",
    "reviewer_role",
    "receipt_digest",
}


def build_test_execution_receipt(
    facts: dict[str, Any],
    *,
    executor_role: str,
    started_at: str,
    completed_at: str,
    exit_code: int,
    result: str,
    evidence_digest: str,
    output_digest: str,
) -> dict[str, Any]:
    """Build the self-hashed execution fact consumed by reuse admission."""

    receipt: dict[str, Any] = {
        "schema_version": "test_execution_receipt_v1",
        "signature": test_evidence_signature(facts),
        "facts": {field: facts[field] for field in sorted(TEST_EVIDENCE_FIELDS)},
        "executor_role": executor_role,
        "started_at": started_at,
        "completed_at": completed_at,
        "exit_code": exit_code,
        "result": result,
        "evidence_digest": evidence_digest,
        "output_digest": output_digest,
    }
    errors = _validate_test_execution_receipt(receipt, require_digest=False)
    if errors:
        raise ValueError("invalid test execution receipt: " + "; ".join(errors))
    receipt["receipt_digest"] = _receipt_digest(receipt)
    return receipt


def _validate_test_execution_receipt(
    receipt: Any, *, require_digest: bool = True
) -> list[str]:
    if not isinstance(receipt, dict):
        return ["typed execution receipt is missing"]
    expected_fields = EXECUTION_RECEIPT_FIELDS if require_digest else EXECUTION_RECEIPT_FIELDS - {"receipt_digest"}
    errors: list[str] = []
    if set(receipt) != expected_fields:
        errors.append("typed execution receipt fields do not match contract")
    if receipt.get("schema_version") != "test_execution_receipt_v1":
        errors.append("typed execution receipt schema is invalid")
    facts = receipt.get("facts")
    if not isinstance(facts, dict):
        errors.append("typed execution receipt lacks signed facts")
    else:
        try:
            signature = test_evidence_signature(facts)
            if receipt.get("signature") != signature:
                errors.append("typed execution receipt signature does not match facts")
        except (KeyError, TypeError, ValueError) as error:
            errors.append(f"typed execution receipt facts are invalid: {error}")
    if not isinstance(receipt.get("executor_role"), str) or not receipt.get("executor_role", "").strip():
        errors.append("typed execution receipt executor_role is missing")
    if receipt.get("result") not in {"PASS", "FAIL"}:
        errors.append("typed execution receipt result is invalid")
    if not isinstance(receipt.get("exit_code"), int) or isinstance(receipt.get("exit_code"), bool):
        errors.append("typed execution receipt exit_code is invalid")
    if receipt.get("result") == "PASS" and receipt.get("exit_code") != 0:
        errors.append("typed execution PASS requires exit_code=0")
    for field in ("evidence_digest", "output_digest"):
        if not DIGEST_RE.fullmatch(str(receipt.get(field, ""))):
            errors.append(f"typed execution receipt {field} is invalid")
    try:
        started = _parse_timestamp(str(receipt.get("started_at", "")))
        completed = _parse_timestamp(str(receipt.get("completed_at", "")))
        if started.tzinfo is None or completed.tzinfo is None or completed < started:
            raise ValueError("invalid execution interval")
    except (TypeError, ValueError):
        errors.append("typed execution receipt timestamps are invalid")
    if require_digest and receipt.get("receipt_digest") != _receipt_digest(receipt):
        errors.append("typed execution receipt digest mismatch")
    return errors


def validate_test_execution_receipt(
    receipt: Any,
    *,
    expected_facts: dict[str, Any] | None = None,
    expected_baseline: dict[str, Any] | None = None,
    expected_evidence_digest: str | None = None,
    expected_executor_role: str | None = None,
    require_success: bool = True,
) -> list[str]:
    """Validate one EXECUTED check fact against its external task identity."""

    errors = _validate_test_execution_receipt(receipt)
    if not isinstance(receipt, dict):
        return errors
    facts = receipt.get("facts")
    if expected_facts is not None and facts != expected_facts:
        errors.append("typed execution receipt does not match expected facts")
    if expected_baseline is not None:
        if not isinstance(facts, dict):
            errors.append("typed execution receipt cannot bind expected baseline")
        else:
            for field in (
                "source_head",
                "dirty_diff_hash",
                "untracked_relevant_hash",
                "runtime_head",
                "authorization_hash",
            ):
                if field in expected_baseline and facts.get(field) != expected_baseline.get(field):
                    errors.append(
                        f"typed execution receipt {field} does not match expected baseline"
                    )
    if (
        expected_evidence_digest is not None
        and receipt.get("evidence_digest") != expected_evidence_digest
    ):
        errors.append("typed execution receipt evidence does not match expected evidence")
    if (
        expected_executor_role is not None
        and receipt.get("executor_role") != expected_executor_role
    ):
        errors.append("typed execution receipt executor does not match expected role")
    if require_success and (
        receipt.get("result") != "PASS" or receipt.get("exit_code") != 0
    ):
        errors.append("typed execution receipt does not prove a successful execution")
    return errors


def build_test_recheck_receipt(
    execution_receipt: dict[str, Any],
    *,
    reviewer_role: str,
    observed_at: str,
    result: str,
    evidence_digest: str,
) -> dict[str, Any]:
    """Build an independent, execution-bound recheck fact for critical reuse."""

    execution_errors = _validate_test_execution_receipt(execution_receipt)
    if execution_errors:
        raise ValueError("invalid original execution receipt: " + "; ".join(execution_errors))
    if reviewer_role == execution_receipt["executor_role"]:
        raise ValueError("independent recheck must use a different role from the executor")
    facts = execution_receipt["facts"]
    receipt: dict[str, Any] = {
        "schema_version": "test_independent_recheck_receipt_v1",
        "execution_receipt_digest": execution_receipt["receipt_digest"],
        "signature": execution_receipt["signature"],
        "source_head": facts["source_head"],
        "dirty_diff_hash": facts["dirty_diff_hash"],
        "untracked_relevant_hash": facts["untracked_relevant_hash"],
        "command": facts["command"],
        "selected_tests": facts["selected_tests"],
        "reviewer_role": reviewer_role,
        "observed_at": observed_at,
        "result": result,
        "evidence_digest": evidence_digest,
    }
    errors = _validate_test_recheck_receipt(
        receipt, execution_receipt, require_digest=False
    )
    if errors:
        raise ValueError("invalid independent recheck receipt: " + "; ".join(errors))
    receipt["receipt_digest"] = _receipt_digest(receipt)
    return receipt


def _validate_test_recheck_receipt(
    receipt: Any,
    execution_receipt: Any,
    *,
    require_digest: bool = True,
) -> list[str]:
    if not isinstance(receipt, dict):
        return ["typed independent recheck receipt is missing"]
    expected_fields = RECHECK_RECEIPT_FIELDS if require_digest else RECHECK_RECEIPT_FIELDS - {"receipt_digest"}
    errors: list[str] = []
    if set(receipt) != expected_fields:
        errors.append("typed independent recheck receipt fields do not match contract")
    if receipt.get("schema_version") != "test_independent_recheck_receipt_v1":
        errors.append("typed independent recheck receipt schema is invalid")
    if not isinstance(execution_receipt, dict):
        errors.append("typed independent recheck lacks original execution")
        return errors
    facts = execution_receipt.get("facts", {})
    bindings = {
        "execution_receipt_digest": execution_receipt.get("receipt_digest"),
        "signature": execution_receipt.get("signature"),
        "source_head": facts.get("source_head"),
        "dirty_diff_hash": facts.get("dirty_diff_hash"),
        "untracked_relevant_hash": facts.get("untracked_relevant_hash"),
        "command": facts.get("command"),
        "selected_tests": facts.get("selected_tests"),
    }
    for field, expected in bindings.items():
        if receipt.get(field) != expected:
            errors.append(f"typed independent recheck {field} is not execution-bound")
    reviewer = receipt.get("reviewer_role")
    if not isinstance(reviewer, str) or not reviewer.strip():
        errors.append("typed independent recheck reviewer_role is missing")
    if reviewer == execution_receipt.get("executor_role"):
        errors.append("typed independent recheck must use a different role")
    if receipt.get("result") not in {"PASS", "FAIL"}:
        errors.append("typed independent recheck result is invalid")
    if not DIGEST_RE.fullmatch(str(receipt.get("evidence_digest", ""))):
        errors.append("typed independent recheck evidence_digest is invalid")
    if receipt.get("evidence_digest") == execution_receipt.get("evidence_digest"):
        errors.append("typed independent recheck evidence must differ from execution evidence")
    try:
        observed = _parse_timestamp(str(receipt.get("observed_at", "")))
        completed = _parse_timestamp(str(execution_receipt.get("completed_at", "")))
        if observed.tzinfo is None or completed.tzinfo is None or observed < completed:
            raise ValueError("recheck predates execution")
    except (TypeError, ValueError):
        errors.append("typed independent recheck timestamp is invalid")
    if require_digest and receipt.get("receipt_digest") != _receipt_digest(receipt):
        errors.append("typed independent recheck receipt digest mismatch")
    return errors


def validate_test_evidence_reuse_receipt(
    receipt: Any,
    *,
    check_signature: Any,
    evidence_digest: Any,
    reused_from: Any,
    adjudicated_at: Any,
) -> list[str]:
    """Validate a hash-pinned eligible reuse receipt at closure time."""

    if not isinstance(receipt, dict):
        return ["reuse receipt is missing"]
    errors: list[str] = []
    if set(receipt) != REUSE_RECEIPT_FIELDS:
        errors.append("reuse receipt fields do not match the exact typed contract")
    if receipt.get("schema_version") != "test_evidence_reuse_v2" or receipt.get("status") != "REUSED" or receipt.get("eligible") is not True:
        errors.append("reuse receipt is not an eligible test_evidence_reuse_v2")
    if receipt.get("current_signature") != check_signature:
        errors.append("reuse receipt signature does not match check signature")
    if receipt.get("execution_evidence_digest") != evidence_digest:
        errors.append("reuse receipt execution evidence does not match referenced evidence")
    if receipt.get("created_at") != reused_from:
        errors.append("reuse receipt lineage does not match reused_from")
    execution = receipt.get("execution_receipt")
    execution_errors = _validate_test_execution_receipt(execution)
    errors.extend(execution_errors)
    if isinstance(execution, dict):
        if receipt.get("execution_receipt_digest") != execution.get("receipt_digest"):
            errors.append("reuse receipt execution receipt digest mismatch")
        if receipt.get("execution_evidence_digest") != execution.get("evidence_digest"):
            errors.append("reuse receipt execution evidence is not typed-execution-bound")
        if receipt.get("executor_role") != execution.get("executor_role"):
            errors.append("reuse receipt executor role mismatch")
        if receipt.get("created_at") != execution.get("completed_at"):
            errors.append("reuse receipt creation time is not execution-bound")
    recheck = receipt.get("independent_recheck_receipt")
    if recheck is not None:
        errors.extend(_validate_test_recheck_receipt(recheck, execution))
        if isinstance(recheck, dict):
            if receipt.get("independent_recheck_receipt_digest") != recheck.get("receipt_digest"):
                errors.append("reuse receipt independent recheck digest mismatch")
            if receipt.get("reviewer_role") != recheck.get("reviewer_role"):
                errors.append("reuse receipt reviewer role mismatch")
            if recheck.get("result") != "PASS":
                errors.append("reuse receipt independent recheck did not PASS")
    if receipt.get("receipt_digest") != _receipt_digest(receipt):
        errors.append("reuse receipt digest mismatch")
    try:
        created = _parse_timestamp(str(receipt["created_at"]))
        assessed = _parse_timestamp(str(receipt["assessed_at"]))
        expiry = _parse_timestamp(str(receipt["expires_at"]))
        adjudicated = _parse_timestamp(str(adjudicated_at))
        if not created <= assessed <= adjudicated < expiry:
            errors.append("reuse receipt is stale or has invalid time lineage")
        if (expiry - created).total_seconds() > 24 * 60 * 60:
            errors.append("reuse receipt exceeds maximum TTL")
    except (KeyError, TypeError, ValueError):
        errors.append("reuse receipt timestamps are invalid")
    if receipt.get("critical") is True and receipt.get("independent_recheck_receipt") is None:
        errors.append("critical reuse receipt lacks a typed independent recheck")
    return errors


def assess_test_evidence_reuse(
    capsule: dict[str, Any],
    current_facts: dict[str, Any],
    *,
    now: str,
) -> dict[str, Any]:
    """Fail closed unless a successful evidence capsule is exactly reusable."""

    current_signature = test_evidence_signature(current_facts)
    execution = capsule.get("execution_receipt")
    execution_errors = _validate_test_execution_receipt(execution)
    recheck = capsule.get("independent_recheck_receipt")
    recheck_errors = (
        _validate_test_recheck_receipt(recheck, execution)
        if recheck is not None
        else ["typed independent recheck receipt is missing"]
    )
    checks = [
        (capsule.get("schema_version") == "test_evidence_capsule_v2", "capsule is not test_evidence_capsule_v2"),
        (capsule.get("status") == "PASS", "prior capsule is not PASS"),
        (capsule.get("signature") == current_signature, "content/environment signature changed"),
        (not execution_errors, "typed execution receipt is invalid: " + "; ".join(execution_errors)),
        (bool(capsule.get("created_at")), "capsule has no creation time"),
        (bool(capsule.get("expires_at")), "capsule has no expiry"),
        (not bool(capsule.get("flaky")), "flaky evidence must be executed again"),
        (
            recheck is None or not recheck_errors,
            "supplied typed independent recheck receipt is invalid: "
            + "; ".join(recheck_errors),
        ),
        (
            not bool(capsule.get("critical")) or not recheck_errors,
            "critical evidence requires a typed independent recheck receipt",
        ),
        (
            recheck is None
            or (isinstance(recheck, dict) and recheck.get("result") == "PASS"),
            "typed independent recheck must PASS before evidence can be reused",
        ),
    ]
    for passed, reason in checks:
        if not passed:
            return {
                "schema_version": "test_evidence_reuse_v2",
                "eligible": False,
                "status": "MISS",
                "reason": reason,
                "current_signature": current_signature,
            }
    if isinstance(execution, dict):
        execution_bindings = [
            (execution.get("signature") == current_signature, "typed execution signature changed"),
            (execution.get("result") == "PASS", "typed execution result is not PASS"),
            (execution.get("completed_at") == capsule.get("created_at"), "capsule creation is not execution-bound"),
        ]
        for passed, reason in execution_bindings:
            if not passed:
                return {
                    "schema_version": "test_evidence_reuse_v2",
                    "eligible": False,
                    "status": "MISS",
                    "reason": reason,
                    "current_signature": current_signature,
                }
    try:
        current = _parse_timestamp(now)
        created = _parse_timestamp(str(capsule["created_at"]))
        expiry = _parse_timestamp(str(capsule["expires_at"]))
        fresh = created <= current < expiry and (expiry - created).total_seconds() <= 24 * 60 * 60
        if isinstance(recheck, dict):
            rechecked_at = _parse_timestamp(str(recheck.get("observed_at", "")))
            fresh = fresh and created <= rechecked_at <= current
    except (TypeError, ValueError):
        fresh = False
    if not fresh:
        return {
            "schema_version": "test_evidence_reuse_v2",
            "eligible": False,
            "status": "MISS",
            "reason": "capsule expired, exceeds maximum TTL, or has invalid timestamp lineage",
            "current_signature": current_signature,
        }
    receipt = {
        "schema_version": "test_evidence_reuse_v2",
        "eligible": True,
        "status": "REUSED",
        "reason": "exact signature and freshness match",
        "current_signature": current_signature,
        "reused_from": capsule.get("created_at"),
        "created_at": capsule.get("created_at"),
        "expires_at": capsule.get("expires_at"),
        "assessed_at": now,
        "execution_evidence_digest": execution.get("evidence_digest"),
        "execution_receipt": execution,
        "execution_receipt_digest": execution.get("receipt_digest"),
        "executor_role": execution.get("executor_role"),
        "critical": bool(capsule.get("critical")),
        "independent_recheck_receipt": recheck,
        "independent_recheck_receipt_digest": (
            recheck.get("receipt_digest") if isinstance(recheck, dict) else None
        ),
        "reviewer_role": recheck.get("reviewer_role") if isinstance(recheck, dict) else None,
    }
    receipt["receipt_digest"] = _receipt_digest(receipt)
    return receipt
