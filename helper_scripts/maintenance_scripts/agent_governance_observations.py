"""Content-addressed source, runtime, and business observation receipts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from agent_governance_registry import load_registry


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
BASELINE_FIELDS = {
    "source_head", "dirty_diff_hash", "untracked_relevant_hash",
    "runtime_head", "runtime_observed_at",
}
SOURCE_FIELDS = {
    "schema_version", "producer_role", "producer_adapter_digest", "command",
    "baseline", "criteria", "observed_at", "exit_code", "status",
    "stdout_digest", "stderr_digest", "receipt_digest",
}
RUNTIME_FIELDS = {
    "schema_version", "producer_role", "producer_adapter_digest", "probe_kind",
    "command", "source_head", "dirty_diff_hash", "untracked_relevant_hash",
    "runtime_head", "host", "environment", "observed_at", "expiry",
    "exit_code", "status", "facts", "stdout_digest", "stderr_digest",
    "receipt_digest",
}
BUSINESS_FIELDS = {
    "schema_version", "producer_role", "producer_adapter_digest", "criterion",
    "command", "baseline", "started_at", "completed_at", "exit_code", "passed",
    "output_digest", "stdout_digest", "stderr_digest", "receipt_digest",
}
CHANGE_FIELDS = {
    "schema_version", "producer_role", "producer_adapter_digest",
    "before_baseline", "after_baseline", "changed_paths", "patch_digest",
    "observed_at", "receipt_digest",
}
ADAPTER_PATH = Path(__file__).resolve()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def observation_adapter_digest() -> str:
    return _sha256(ADAPTER_PATH.read_bytes())


def observation_receipt_digest(receipt: dict[str, Any]) -> str:
    return _sha256(_canonical_bytes({
        key: value for key, value in receipt.items() if key != "receipt_digest"
    }))


def _time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed


def _baseline_errors(value: Any, label: str) -> list[str]:
    if not isinstance(value, dict) or set(value) != BASELINE_FIELDS:
        return [f"{label} fields are invalid"]
    errors: list[str] = []
    if not HEAD_RE.fullmatch(str(value.get("source_head", ""))):
        errors.append(f"{label} source_head is invalid")
    for field in ("dirty_diff_hash", "untracked_relevant_hash"):
        if not DIGEST_RE.fullmatch(str(value.get(field, ""))):
            errors.append(f"{label} {field} is invalid")
    runtime_head = value.get("runtime_head")
    runtime_observed = value.get("runtime_observed_at")
    if runtime_head is not None and not HEAD_RE.fullmatch(str(runtime_head)):
        errors.append(f"{label} runtime_head is invalid")
    if (runtime_head is None) != (runtime_observed is None):
        errors.append(f"{label} runtime identity/time must be present together")
    if runtime_observed is not None:
        try:
            _time(runtime_observed)
        except (TypeError, ValueError):
            errors.append(f"{label} runtime_observed_at is invalid")
    return errors


def _role_permission(role: Any) -> str | None:
    if not isinstance(role, str):
        return None
    return load_registry()["roles"].get(role, {}).get("permission")


def _common_errors(receipt: dict[str, Any], fields: set[str]) -> list[str]:
    errors: list[str] = []
    if set(receipt) != fields:
        errors.append("observation receipt fields do not match schema")
    if receipt.get("producer_adapter_digest") != observation_adapter_digest():
        errors.append("observation receipt producer adapter digest is stale or forged")
    if "exit_code" in receipt and (
        not isinstance(receipt.get("exit_code"), int)
        or isinstance(receipt.get("exit_code"), bool)
    ):
        errors.append("observation receipt exit_code must be an integer")
    try:
        expected_receipt_digest = observation_receipt_digest(receipt)
    except (TypeError, ValueError):
        expected_receipt_digest = None
        errors.append("observation receipt is not canonical JSON")
    if receipt.get("receipt_digest") != expected_receipt_digest:
        errors.append("observation receipt self-digest is invalid")
    return errors


def build_source_review_receipt(
    *,
    producer_role: str,
    command: str,
    baseline: dict[str, Any],
    criteria: list[str],
    observed_at: str,
    exit_code: int,
    stdout: bytes,
    stderr: bytes,
) -> dict[str, Any]:
    receipt = {
        "schema_version": "source_review_receipt_v1",
        "producer_role": producer_role,
        "producer_adapter_digest": observation_adapter_digest(),
        "command": command,
        "baseline": baseline,
        "criteria": criteria,
        "observed_at": observed_at,
        "exit_code": exit_code,
        "status": "PASS" if exit_code == 0 else "FAIL",
        "stdout_digest": _sha256(stdout),
        "stderr_digest": _sha256(stderr),
    }
    receipt["receipt_digest"] = observation_receipt_digest(receipt)
    return receipt


def build_runtime_observation_receipt(
    *,
    producer_role: str,
    probe_kind: str,
    command: str,
    baseline: dict[str, Any],
    runtime_head: str,
    host: str,
    environment: str,
    observed_at: str,
    expiry: str,
    exit_code: int,
    facts: dict[str, Any],
    stdout: bytes,
    stderr: bytes,
) -> dict[str, Any]:
    receipt = {
        "schema_version": "runtime_observation_receipt_v1",
        "producer_role": producer_role,
        "producer_adapter_digest": observation_adapter_digest(),
        "probe_kind": probe_kind,
        "command": command,
        "source_head": baseline["source_head"],
        "dirty_diff_hash": baseline["dirty_diff_hash"],
        "untracked_relevant_hash": baseline["untracked_relevant_hash"],
        "runtime_head": runtime_head,
        "host": host,
        "environment": environment,
        "observed_at": observed_at,
        "expiry": expiry,
        "exit_code": exit_code,
        "status": "PASS" if exit_code == 0 else "FAIL",
        "facts": facts,
        "stdout_digest": _sha256(stdout),
        "stderr_digest": _sha256(stderr),
    }
    receipt["receipt_digest"] = observation_receipt_digest(receipt)
    return receipt


def build_business_outcome_receipt(
    *,
    producer_role: str,
    criterion: str,
    command: str,
    baseline: dict[str, Any],
    started_at: str,
    completed_at: str,
    exit_code: int,
    output_digest: str,
    stdout: bytes,
    stderr: bytes,
) -> dict[str, Any]:
    receipt = {
        "schema_version": "business_outcome_receipt_v1",
        "producer_role": producer_role,
        "producer_adapter_digest": observation_adapter_digest(),
        "criterion": criterion,
        "command": command,
        "baseline": baseline,
        "started_at": started_at,
        "completed_at": completed_at,
        "exit_code": exit_code,
        "passed": exit_code == 0,
        "output_digest": output_digest,
        "stdout_digest": _sha256(stdout),
        "stderr_digest": _sha256(stderr),
    }
    receipt["receipt_digest"] = observation_receipt_digest(receipt)
    return receipt


def build_source_change_receipt(
    *,
    producer_role: str,
    before_baseline: dict[str, Any],
    after_baseline: dict[str, Any],
    changed_paths: list[str],
    patch_digest: str,
    observed_at: str,
) -> dict[str, Any]:
    receipt = {
        "schema_version": "source_change_receipt_v1",
        "producer_role": producer_role,
        "producer_adapter_digest": observation_adapter_digest(),
        "before_baseline": before_baseline,
        "after_baseline": after_baseline,
        "changed_paths": changed_paths,
        "patch_digest": patch_digest,
        "observed_at": observed_at,
    }
    receipt["receipt_digest"] = observation_receipt_digest(receipt)
    return receipt


def validate_observation_evidence(
    evidence: Any,
    *,
    expected_baseline: Any,
    adjudicated_at: str,
    task_baseline: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, Any] | None]:
    """Validate a typed evidence artifact and its wrapper bindings."""

    if not isinstance(evidence, dict):
        return ["typed observation evidence must be an object"], None
    artifact = evidence.get("artifact")
    if not isinstance(artifact, dict):
        return ["typed observation artifact is missing"], None
    version = artifact.get("schema_version")
    if not isinstance(version, str):
        return ["typed observation artifact schema_version is unsupported"], None
    fields = {
        "source_review_receipt_v1": SOURCE_FIELDS,
        "runtime_observation_receipt_v1": RUNTIME_FIELDS,
        "business_outcome_receipt_v1": BUSINESS_FIELDS,
        "source_change_receipt_v1": CHANGE_FIELDS,
    }.get(version)
    if fields is None:
        return ["typed observation artifact schema_version is unsupported"], None
    errors = _common_errors(artifact, fields)
    if not isinstance(expected_baseline, dict):
        errors.append("expected observation baseline must be an object")
        expected_baseline = {}
    if task_baseline is not None and not isinstance(task_baseline, dict):
        errors.append("task observation baseline must be an object")
        task_baseline = {}
    if evidence.get("digest") != artifact.get("receipt_digest"):
        errors.append("evidence digest is not bound to typed observation receipt")
    try:
        adjudicated = _time(adjudicated_at)
    except (TypeError, ValueError):
        adjudicated = None
        errors.append("observation adjudicated_at is invalid")

    if version == "source_review_receipt_v1":
        if evidence.get("scope") != "source" or evidence.get("kind") != version:
            errors.append("source review evidence wrapper is invalid")
        errors.extend(_baseline_errors(artifact.get("baseline"), "source review baseline"))
        if artifact.get("baseline") != expected_baseline:
            errors.append("source review receipt baseline differs from closure")
        if _role_permission(artifact.get("producer_role")) != "read_only":
            errors.append("source review receipt producer must be read-only")
        if not isinstance(artifact.get("command"), str) or not artifact.get("command", "").strip():
            errors.append("source review receipt command is empty")
        criteria = artifact.get("criteria")
        if (
            not isinstance(criteria, list)
            or not criteria
            or any(not isinstance(item, str) or not item.strip() for item in criteria)
            or len(criteria) != len(set(criteria))
        ):
            errors.append("source review receipt criteria are invalid")
        if artifact.get("exit_code") != 0 or artifact.get("status") != "PASS":
            errors.append("source review receipt does not prove success")
        observed_field = "observed_at"
    elif version == "runtime_observation_receipt_v1":
        if evidence.get("scope") != "runtime" or evidence.get("kind") != version:
            errors.append("runtime observation evidence wrapper is invalid")
        if artifact.get("producer_role") != "OPS":
            errors.append("runtime observation receipt must be produced by OPS")
        if not isinstance(artifact.get("probe_kind"), str) or not artifact.get("probe_kind", "").strip():
            errors.append("runtime observation probe_kind is empty")
        if not isinstance(artifact.get("command"), str) or not artifact.get("command", "").strip():
            errors.append("runtime observation command is empty")
        if not isinstance(artifact.get("facts"), dict) or not artifact.get("facts"):
            errors.append("runtime observation facts are empty")
        runtime_baseline = {
            "source_head": artifact.get("source_head"),
            "dirty_diff_hash": artifact.get("dirty_diff_hash"),
            "untracked_relevant_hash": artifact.get("untracked_relevant_hash"),
            "runtime_head": artifact.get("runtime_head"),
            "runtime_observed_at": artifact.get("observed_at"),
        }
        errors.extend(_baseline_errors(runtime_baseline, "runtime observation baseline"))
        if artifact.get("source_head") != expected_baseline.get("source_head"):
            errors.append("runtime observation source head differs from closure")
        for field in ("dirty_diff_hash", "untracked_relevant_hash"):
            if artifact.get(field) != expected_baseline.get(field):
                errors.append(f"runtime observation {field} differs from closure")
        if artifact.get("runtime_head") != expected_baseline.get("runtime_head"):
            errors.append("runtime observation runtime head differs from closure")
        if artifact.get("exit_code") != 0 or artifact.get("status") != "PASS":
            errors.append("runtime observation receipt does not prove success")
        for field in ("host", "environment", "observed_at", "expiry"):
            if evidence.get(field) != artifact.get(field):
                errors.append(f"runtime observation wrapper {field} is not receipt-bound")
        try:
            observed = _time(artifact.get("observed_at"))
            expiry = _time(artifact.get("expiry"))
            if not observed < expiry:
                errors.append("runtime observation expiry is not after observation")
            elif expiry - observed > timedelta(minutes=15):
                errors.append("runtime observation freshness window exceeds fifteen minutes")
            if adjudicated is None or not observed <= adjudicated < expiry:
                errors.append("runtime observation is stale at adjudication")
        except (TypeError, ValueError):
            errors.append("runtime observation timestamps are invalid")
        observed_field = None
    elif version == "business_outcome_receipt_v1":
        if evidence.get("scope") not in {"test", "data", "external"} or evidence.get("kind") != version:
            errors.append("business outcome evidence wrapper is invalid")
        if artifact.get("producer_role") != "QA":
            errors.append("business outcome receipt must be produced by QA")
        if not isinstance(artifact.get("criterion"), str) or not artifact.get("criterion", "").strip():
            errors.append("business outcome criterion is empty")
        if not isinstance(artifact.get("command"), str) or not artifact.get("command", "").strip():
            errors.append("business outcome command is empty")
        errors.extend(_baseline_errors(artifact.get("baseline"), "business outcome baseline"))
        if artifact.get("baseline") != expected_baseline:
            errors.append("business outcome baseline differs from closure")
        if artifact.get("exit_code") != 0 or artifact.get("passed") is not True:
            errors.append("business outcome receipt does not prove success")
        if not DIGEST_RE.fullmatch(str(artifact.get("output_digest", ""))):
            errors.append("business outcome output digest is invalid")
        try:
            started = _time(artifact.get("started_at"))
            completed = _time(artifact.get("completed_at"))
            if started > completed or (adjudicated is not None and completed > adjudicated):
                errors.append("business outcome time lineage is invalid")
        except (TypeError, ValueError):
            errors.append("business outcome timestamps are invalid")
        observed_field = "completed_at"
    else:
        if evidence.get("scope") != "source" or evidence.get("kind") != version:
            errors.append("source change evidence wrapper is invalid")
        if _role_permission(artifact.get("producer_role")) not in {
            "source_writer", "test_writer", "docs_writer",
        }:
            errors.append("source change receipt producer cannot own writes")
        errors.extend(_baseline_errors(artifact.get("before_baseline"), "source change before baseline"))
        errors.extend(_baseline_errors(artifact.get("after_baseline"), "source change after baseline"))
        if artifact.get("before_baseline") == artifact.get("after_baseline"):
            errors.append("source change receipt baseline did not change")
        if task_baseline is not None and artifact.get("before_baseline") != task_baseline:
            errors.append("source change receipt does not start at task baseline")
        if artifact.get("after_baseline") != expected_baseline:
            errors.append("source change receipt does not end at closure baseline")
        changed_paths = artifact.get("changed_paths")
        if not isinstance(changed_paths, list) or not changed_paths:
            errors.append("source change receipt changed_paths is empty")
        elif (
            any(
                not isinstance(path, str)
                or not path
                or path.startswith(("/", "~"))
                or ".." in Path(path).parts
                for path in changed_paths
            )
            or len(changed_paths) != len(set(changed_paths))
        ):
            errors.append("source change receipt changed_paths are unsafe or duplicated")
        if not DIGEST_RE.fullmatch(str(artifact.get("patch_digest", ""))):
            errors.append("source change patch digest is invalid")
        observed_field = "observed_at"

    for field in ("stdout_digest", "stderr_digest"):
        if field in artifact and not DIGEST_RE.fullmatch(str(artifact.get(field, ""))):
            errors.append(f"typed observation {field} is invalid")
    if observed_field:
        if evidence.get("observed_at") != artifact.get(observed_field):
            errors.append("observation wrapper observed_at is not receipt-bound")
        try:
            observed = _time(artifact.get(observed_field))
            if adjudicated is not None and observed > adjudicated:
                errors.append("typed observation occurs after adjudication")
        except (TypeError, ValueError):
            errors.append("typed observation timestamp is invalid")
    return errors, artifact if not errors else None
