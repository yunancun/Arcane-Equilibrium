"""Effect receipt integrity and closure binding for Development-Agent Governance."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent_governance_schema import schema_subset_errors
from agent_governance_effect_evidence import deploy_evidence_identity_errors


ADAPTER_ID = "deploy_adapter_v1"
REQUIRED_HARD_STOPS = {
    "no live/mainnet authority expansion",
    "no risk/cost-gate/decision-lease bypass",
}
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
DEPLOY_MARKER_RE = re.compile(
    rb"(?m)^>>> DEPLOY-ATOMIC-VERIFIED: NEW_PID=([1-9][0-9]*) POST_SHA=([0-9a-f]{64})$"
)
RECEIPT_FIELDS = set("""
schema_version adapter_id effect_status intent_id intent_digest approved_by approved_at
intent_expires_at typed_confirm hard_stops source_head tree_clean target_host target_environment
runtime_environment_identity_digest pre_runtime_attestation post_runtime_attestation component_digest
started_at completed_at evidence_expires_at component_exit_code stdout_digest stderr_digest
deployed_binary_sha256 failure_reason receipt_digest
""".split())
SCHEMA_DIR = Path(__file__).resolve().parents[2] / ".codex/schemas"
RECEIPT_SCHEMA_PATH = SCHEMA_DIR / "effect_adapter_result_v1.schema.json"
RUNTIME_ATTESTATION_SCHEMA_PATH = SCHEMA_DIR / "runtime_environment_attestation_v1.schema.json"
RUNTIME_ATTESTATION_FIELDS = set("""
schema_version phase probe_kind host source_head config_identity_digest actual_endpoint_class
allow_mainnet runtime_mode authorization_scope process_identity_digest environment_identity_digest
observed_at expires_at attestation_digest
""".split())
RUNTIME_ENVIRONMENT_IDENTITY_FIELDS = (
    "host", "source_head", "config_identity_digest", "actual_endpoint_class",
    "allow_mainnet", "runtime_mode", "authorization_scope",
)
SAFE_RUNTIME_ENVIRONMENTS = {
    "demo": ("bybit_demo", False, "demo", "demo_only"),
    "live_demo": ("bybit_demo", False, "live_demo", "live_demo_only"),
    "research_runtime": ("research_local", False, "research_runtime", "research_read_only"),
}


@lru_cache(maxsize=1)
def _receipt_schema() -> dict[str, Any]:
    return json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _runtime_attestation_schema() -> dict[str, Any]:
    return json.loads(RUNTIME_ATTESTATION_SCHEMA_PATH.read_text(encoding="utf-8"))


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def effect_receipt_digest(receipt: dict[str, Any]) -> str:
    """Hash every receipt field except the self-digest."""
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    return _sha256_bytes(_canonical_bytes(unsigned))


def runtime_environment_identity_digest(attestation: dict[str, Any]) -> str:
    identity = {
        field: attestation.get(field) for field in RUNTIME_ENVIRONMENT_IDENTITY_FIELDS
    }
    return _sha256_bytes(_canonical_bytes(identity))


def runtime_attestation_digest(attestation: dict[str, Any]) -> str:
    unsigned = {
        key: value for key, value in attestation.items() if key != "attestation_digest"
    }
    return _sha256_bytes(_canonical_bytes(unsigned))


def build_runtime_environment_attestation(
    *,
    phase: str,
    host: str,
    source_head: str,
    config_identity_digest: str,
    actual_endpoint_class: str,
    allow_mainnet: bool,
    runtime_mode: str,
    authorization_scope: str,
    process_identity_digest: str,
    observed_at: str,
    expires_at: str,
) -> dict[str, Any]:
    """Build a canonical runtime-fact envelope; this is not authenticity proof."""
    attestation: dict[str, Any] = {
        "schema_version": "runtime_environment_attestation_v1",
        "phase": phase,
        "probe_kind": "local_runtime_process_v1",
        "host": host,
        "source_head": source_head,
        "config_identity_digest": config_identity_digest,
        "actual_endpoint_class": actual_endpoint_class,
        "allow_mainnet": allow_mainnet,
        "runtime_mode": runtime_mode,
        "authorization_scope": authorization_scope,
        "process_identity_digest": process_identity_digest,
        "observed_at": observed_at,
        "expires_at": expires_at,
    }
    attestation["environment_identity_digest"] = runtime_environment_identity_digest(
        attestation
    )
    attestation["attestation_digest"] = runtime_attestation_digest(attestation)
    return attestation


def validate_runtime_environment_attestation(
    attestation: Any,
    *,
    phase: str,
    now: str,
) -> list[str]:
    if not isinstance(attestation, dict):
        return ["runtime environment attestation must be an object"]
    schema = _runtime_attestation_schema()
    errors = [
        f"runtime environment attestation schema violation: {error}"
        for error in schema_subset_errors(attestation, schema, schema)
    ]
    if set(attestation) != RUNTIME_ATTESTATION_FIELDS:
        errors.append("runtime environment attestation fields do not match contract")
    if attestation.get("phase") != phase:
        errors.append("runtime environment attestation phase does not match")
    if attestation.get("environment_identity_digest") != runtime_environment_identity_digest(
        attestation
    ):
        errors.append("runtime environment identity digest mismatch")
    if attestation.get("attestation_digest") != runtime_attestation_digest(attestation):
        errors.append("runtime environment attestation digest mismatch")
    try:
        observed = _parse_time(str(attestation.get("observed_at", "")))
        expiry = _parse_time(str(attestation.get("expires_at", "")))
        current = _parse_time(now)
        if not observed <= current < expiry:
            errors.append("runtime environment attestation is not fresh")
        if not observed < expiry or expiry - observed > timedelta(minutes=15):
            errors.append("runtime environment attestation TTL exceeds fifteen minutes")
    except (TypeError, ValueError):
        errors.append("runtime environment attestation timestamps are invalid")
    return errors


def validate_runtime_attestation_for_intent(
    attestation: Any,
    intent: dict[str, Any],
    *,
    phase: str,
    now: str,
) -> list[str]:
    errors = validate_runtime_environment_attestation(
        attestation, phase=phase, now=now
    )
    if not isinstance(attestation, dict):
        return errors
    expected_environment = intent.get("target_environment")
    safe_identity = SAFE_RUNTIME_ENVIRONMENTS.get(str(expected_environment))
    actual_identity = (
        attestation.get("actual_endpoint_class"),
        attestation.get("allow_mainnet"),
        attestation.get("runtime_mode"),
        attestation.get("authorization_scope"),
    )
    if safe_identity is None or actual_identity != safe_identity:
        errors.append(
            "runtime attestation does not prove the requested safe runtime; "
            "mainnet or unknown identity is forbidden"
        )
    if attestation.get("host") != intent.get("target_host"):
        errors.append("runtime attestation host does not match deployment intent")
    if attestation.get("source_head") != intent.get("expected_source_head"):
        errors.append("runtime attestation source head does not match deployment intent")
    if attestation.get("environment_identity_digest") != intent.get(
        "expected_runtime_environment_identity_digest"
    ):
        errors.append("runtime attestation identity does not match deployment intent")
    return errors


def build_effect_receipt(
    intent: dict[str, Any],
    *,
    intent_digest: str,
    component_exit_code: int,
    component_stdout: bytes,
    component_stderr: bytes,
    started_at: str,
    completed_at: str,
    pre_runtime_attestation: dict[str, Any],
    post_runtime_attestation: dict[str, Any],
) -> dict[str, Any]:
    """Build the canonical structural receipt from supplied captured component bytes.

    Closure still requires an out-of-band trusted-host attestation.  This public
    builder and its self-digest cannot prove that the component or probes ran.
    """

    markers = DEPLOY_MARKER_RE.findall(component_stdout)
    reasons: list[str] = []
    if component_exit_code != 0:
        reasons.append(f"component_exit_code={component_exit_code}")
    if len(markers) != 1:
        reasons.append(f"verified_marker_count={len(markers)}")
    pre_errors = validate_runtime_attestation_for_intent(
        pre_runtime_attestation,
        intent,
        phase="preflight",
        now=started_at,
    )
    post_now = str(post_runtime_attestation.get("observed_at", ""))
    post_errors = validate_runtime_attestation_for_intent(
        post_runtime_attestation,
        intent,
        phase="postcheck",
        now=post_now,
    )
    reasons.extend(f"pre_attestation:{error}" for error in pre_errors)
    reasons.extend(f"post_attestation:{error}" for error in post_errors)
    expected_environment_identity = intent.get(
        "expected_runtime_environment_identity_digest"
    )
    if pre_runtime_attestation.get("environment_identity_digest") != expected_environment_identity:
        reasons.append("preflight runtime environment identity differs from intent")
    if post_runtime_attestation.get("environment_identity_digest") != expected_environment_identity:
        reasons.append("postcheck runtime environment identity differs from intent")
    try:
        completed = _parse_time(completed_at)
        intent_expiry = _parse_time(str(intent.get("expires_at", "")))
        if completed >= intent_expiry:
            reasons.append("intent expired before component completion")
    except (TypeError, ValueError):
        completed = _parse_time(completed_at)
        reasons.append("receipt or intent completion timestamp is invalid")

    success = not reasons
    deployed_digest = "sha256:" + markers[0][1].decode("ascii") if success else None
    if success and post_runtime_attestation.get("process_identity_digest") != deployed_digest:
        reasons.append("postcheck running process does not match deployed binary")
        success = False
        deployed_digest = None
    try:
        if _parse_time(str(pre_runtime_attestation.get("observed_at", ""))) > _parse_time(started_at):
            reasons.append("preflight runtime attestation was observed after effect start")
        if _parse_time(str(post_runtime_attestation.get("observed_at", ""))) < _parse_time(completed_at):
            reasons.append("postcheck runtime attestation was observed before effect completion")
    except (TypeError, ValueError):
        reasons.append("runtime attestation/effect time binding is invalid")
    if reasons:
        success = False
        deployed_digest = None
    maximum_evidence_expiry = completed + timedelta(minutes=15)
    try:
        post_attestation_expiry = _parse_time(
            str(post_runtime_attestation.get("expires_at", ""))
        )
    except (TypeError, ValueError):
        post_attestation_expiry = maximum_evidence_expiry
    evidence_expiry = min(maximum_evidence_expiry, post_attestation_expiry)
    receipt: dict[str, Any] = {
        "schema_version": "effect_adapter_result_v1",
        "adapter_id": ADAPTER_ID,
        "effect_status": "APPLIED_VERIFIED" if success else "FAILED",
        "intent_id": intent.get("intent_id"),
        "intent_digest": intent_digest,
        "approved_by": intent.get("approved_by"),
        "approved_at": intent.get("approved_at"),
        "intent_expires_at": intent.get("expires_at"),
        "typed_confirm": intent.get("typed_confirm"),
        "hard_stops": intent.get("hard_stops"),
        "source_head": intent.get("expected_source_head"),
        "tree_clean": intent.get("require_clean_tree"),
        "target_host": intent.get("target_host"),
        "target_environment": intent.get("target_environment"),
        "runtime_environment_identity_digest": expected_environment_identity,
        "pre_runtime_attestation": pre_runtime_attestation,
        "post_runtime_attestation": post_runtime_attestation,
        "component_digest": intent.get("expected_deploy_script_sha256"),
        "started_at": started_at,
        "completed_at": completed_at,
        "evidence_expires_at": evidence_expiry.isoformat(),
        "component_exit_code": component_exit_code,
        "stdout_digest": _sha256_bytes(component_stdout),
        "stderr_digest": _sha256_bytes(component_stderr),
        "deployed_binary_sha256": deployed_digest,
        "failure_reason": None if success else "; ".join(reasons),
    }
    receipt["receipt_digest"] = effect_receipt_digest(receipt)
    return receipt


def validate_effect_receipt(
    receipt: Any,
    *,
    require_success: bool = False,
) -> list[str]:
    """Validate receipt structure/integrity; not execution authenticity."""

    if not isinstance(receipt, dict):
        return ["effect receipt missing canonical receipt payload"]
    schema = _receipt_schema()
    errors = [
        f"effect receipt schema violation: {error}"
        for error in schema_subset_errors(receipt, schema, schema)
    ]
    if set(receipt) != RECEIPT_FIELDS:
        errors.append(
            "effect receipt fields mismatch: "
            f"missing={sorted(RECEIPT_FIELDS - set(receipt))} "
            f"extra={sorted(set(receipt) - RECEIPT_FIELDS)}"
        )
    if receipt.get("schema_version") != "effect_adapter_result_v1":
        errors.append("effect receipt schema_version is invalid")
    if receipt.get("adapter_id") != ADAPTER_ID:
        errors.append("effect receipt adapter_id is invalid")
    if receipt.get("effect_status") not in {"APPLIED_VERIFIED", "FAILED"}:
        errors.append("effect receipt effect_status is invalid")
    if not isinstance(receipt.get("intent_id"), str) or len(receipt.get("intent_id", "")) < 8:
        errors.append("effect receipt intent_id is invalid")
    for field in ("intent_digest", "component_digest", "stdout_digest", "stderr_digest"):
        if not DIGEST_RE.fullmatch(str(receipt.get(field, ""))):
            errors.append(f"effect receipt {field} is invalid")
    if not DIGEST_RE.fullmatch(
        str(receipt.get("runtime_environment_identity_digest", ""))
    ):
        errors.append("effect receipt runtime environment identity is invalid")
    if not HEAD_RE.fullmatch(str(receipt.get("source_head", ""))):
        errors.append("effect receipt source_head is invalid")
    if receipt.get("tree_clean") is not True:
        errors.append("effect receipt must bind tree_clean=true")
    if not isinstance(receipt.get("approved_by"), str) or not receipt.get("approved_by", "").strip():
        errors.append("effect receipt approved_by is invalid")
    if not isinstance(receipt.get("target_host"), str) or not receipt.get("target_host", "").strip():
        errors.append("effect receipt target_host is invalid")
    if receipt.get("target_environment") not in {"demo", "live_demo", "research_runtime"}:
        errors.append("effect receipt target_environment is invalid")
    expected_confirm = (
        f"deploy:{receipt.get('target_host', '')}:{receipt.get('source_head', '')}:"
        f"{receipt.get('intent_id', '')}"
    )
    if receipt.get("typed_confirm") != expected_confirm:
        errors.append("effect receipt typed_confirm is not bound to host/head/intent")
    pseudo_intent = {
        "target_host": receipt.get("target_host"),
        "target_environment": receipt.get("target_environment"),
        "expected_source_head": receipt.get("source_head"),
        "expected_runtime_environment_identity_digest": receipt.get(
            "runtime_environment_identity_digest"
        ),
    }
    pre_attestation = receipt.get("pre_runtime_attestation")
    post_attestation = receipt.get("post_runtime_attestation")
    pre_errors = validate_runtime_attestation_for_intent(
        pre_attestation,
        pseudo_intent,
        phase="preflight",
        now=str(receipt.get("started_at", "")),
    )
    post_now = (
        str(post_attestation.get("observed_at", ""))
        if isinstance(post_attestation, dict)
        else ""
    )
    post_errors = validate_runtime_attestation_for_intent(
        post_attestation,
        pseudo_intent,
        phase="postcheck",
        now=post_now,
    )
    errors.extend(f"preflight runtime attestation: {error}" for error in pre_errors)
    errors.extend(f"postcheck runtime attestation: {error}" for error in post_errors)
    hard_stops = receipt.get("hard_stops")
    if (
        not isinstance(hard_stops, list)
        or any(not isinstance(item, str) or not item for item in hard_stops)
        or not REQUIRED_HARD_STOPS.issubset(set(hard_stops))
    ):
        errors.append("effect receipt required hard stops are missing")
    exit_code = receipt.get("component_exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        errors.append("effect receipt component_exit_code is invalid")

    try:
        approved = _parse_time(str(receipt.get("approved_at", "")))
        started = _parse_time(str(receipt.get("started_at", "")))
        completed = _parse_time(str(receipt.get("completed_at", "")))
        intent_expiry = _parse_time(str(receipt.get("intent_expires_at", "")))
        evidence_expiry = _parse_time(str(receipt.get("evidence_expires_at", "")))
        if not approved <= started <= completed:
            errors.append("effect receipt approval/start/completion order is invalid")
        if intent_expiry - approved > timedelta(hours=4):
            errors.append("effect receipt intent TTL exceeds four hours")
        if not completed < evidence_expiry <= completed + timedelta(minutes=15):
            errors.append("effect receipt evidence freshness window exceeds fifteen minutes")
        if isinstance(post_attestation, dict) and evidence_expiry > _parse_time(
            str(post_attestation.get("expires_at", ""))
        ):
            errors.append("effect receipt outlives its postcheck runtime attestation")
    except (TypeError, ValueError):
        errors.append("effect receipt timestamps are invalid")
        completed = None
        intent_expiry = None

    success = receipt.get("effect_status") == "APPLIED_VERIFIED"
    deployed = receipt.get("deployed_binary_sha256")
    failure_reason = receipt.get("failure_reason")
    if success:
        if exit_code != 0:
            errors.append("APPLIED_VERIFIED receipt requires component_exit_code=0")
        if not DIGEST_RE.fullmatch(str(deployed or "")):
            errors.append("APPLIED_VERIFIED receipt requires deployed binary digest")
        if failure_reason is not None:
            errors.append("APPLIED_VERIFIED receipt cannot carry failure_reason")
        if (
            not isinstance(post_attestation, dict)
            or post_attestation.get("process_identity_digest") != deployed
        ):
            errors.append(
                "APPLIED_VERIFIED receipt postcheck process does not match deployed binary"
            )
        try:
            if not isinstance(pre_attestation, dict) or _parse_time(
                str(pre_attestation.get("observed_at", ""))
            ) > _parse_time(str(receipt.get("started_at", ""))):
                errors.append("effect receipt preflight attestation is too late")
            if not isinstance(post_attestation, dict) or _parse_time(
                str(post_attestation.get("observed_at", ""))
            ) < _parse_time(str(receipt.get("completed_at", ""))):
                errors.append("effect receipt postcheck attestation is too early")
        except (TypeError, ValueError):
            errors.append("effect receipt runtime attestation time binding is invalid")
        if completed is not None and intent_expiry is not None and completed >= intent_expiry:
            errors.append("APPLIED_VERIFIED receipt completed outside intent authority window")
    else:
        if not isinstance(failure_reason, str) or not failure_reason.strip():
            errors.append("FAILED receipt requires failure_reason")
        if deployed is not None:
            errors.append("FAILED receipt cannot claim deployed binary digest")
    if require_success and not success:
        errors.append("effect receipt does not prove successful apply")
    if receipt.get("receipt_digest") != effect_receipt_digest(receipt):
        errors.append("receipt_digest does not match canonical receipt")
    return errors


def build_effect_evidence(receipt: dict[str, Any]) -> dict[str, Any]:
    """Wrap a receipt in the closure evidence envelope without changing identity."""

    return {
        "id": f"effect:{receipt['adapter_id']}:{receipt['intent_id']}",
        "scope": "runtime",
        "kind": "effect_adapter_result_v1",
        "digest": receipt["receipt_digest"],
        "observed_at": receipt["completed_at"],
        "expiry": receipt["evidence_expires_at"],
        "host": receipt["target_host"],
        "environment": receipt["target_environment"],
        "source": receipt["adapter_id"],
        "receipt": receipt,
    }


OPS_COMMON_FIELDS = set("""
schema_version adapter_id intent_id intent_digest source_head target_host target_environment
component_digest runtime_environment_identity_digest runtime_attestation_digest
config_identity_digest actual_endpoint_class allow_mainnet runtime_mode authorization_scope
process_identity_digest observed_at
""".split())
OPS_ATTESTATION_BINDINGS = {
    field: field for field in (
        "config_identity_digest", "actual_endpoint_class", "allow_mainnet",
        "runtime_mode", "authorization_scope", "process_identity_digest",
    )
}
OPS_ATTESTATION_BINDINGS.update({
    "runtime_environment_identity_digest": "environment_identity_digest",
    "runtime_attestation_digest": "attestation_digest",
})


def build_ops_evidence(
    receipt: dict[str, Any],
    *,
    phase: str,
    observed_at: str,
    evidence_id: str,
    expiry: str,
    running_binary_sha256: str | None = None,
) -> dict[str, Any]:
    """Build typed, content-addressed OPS evidence for one deploy identity."""

    if phase not in {"preflight", "postcheck"}:
        raise ValueError("OPS deploy evidence phase must be preflight or postcheck")
    attestation_key = (
        "pre_runtime_attestation" if phase == "preflight" else "post_runtime_attestation"
    )
    attestation = receipt.get(attestation_key)
    if not isinstance(attestation, dict):
        raise ValueError(f"OPS {phase} requires a typed runtime attestation")
    if observed_at != attestation.get("observed_at") or expiry != attestation.get(
        "expires_at"
    ):
        raise ValueError(f"OPS {phase} observed_at/expiry must match runtime attestation")
    operation_receipt: dict[str, Any] = {
        "schema_version": f"ops_deploy_{phase}_v1",
        "adapter_id": receipt["adapter_id"],
        "intent_id": receipt["intent_id"],
        "intent_digest": receipt["intent_digest"],
        "source_head": receipt["source_head"],
        "target_host": receipt["target_host"],
        "target_environment": receipt["target_environment"],
        "component_digest": receipt["component_digest"],
        "observed_at": observed_at,
    }
    operation_receipt.update(
        {
            output: attestation[source]
            for output, source in OPS_ATTESTATION_BINDINGS.items()
        }
    )
    if phase == "preflight":
        operation_receipt.update({"tree_clean": True, "ready": True})
    else:
        operation_receipt.update(
            {
                "effect_receipt_digest": receipt["receipt_digest"],
                "deployed_binary_sha256": receipt["deployed_binary_sha256"],
                "running_binary_sha256": running_binary_sha256,
                "service_active": True,
            }
        )
    return {
        "id": evidence_id,
        "scope": "runtime",
        "kind": f"ops_{phase}_v1",
        "digest": _sha256_bytes(_canonical_bytes(operation_receipt)),
        "host": receipt["target_host"],
        "environment": receipt["target_environment"],
        "source": f"ops_{phase}",
        "observed_at": observed_at,
        "expiry": expiry,
        "operation_receipt": operation_receipt,
    }


def _validate_ops_evidence(
    evidence: dict[str, Any],
    *,
    phase: str,
    receipt: dict[str, Any],
) -> list[str]:
    payload = evidence.get("operation_receipt")
    if not isinstance(payload, dict):
        return [f"OPS {phase} lacks typed operation_receipt"]
    phase_fields = (
        OPS_COMMON_FIELDS | {"tree_clean", "ready"}
        if phase == "preflight"
        else OPS_COMMON_FIELDS
        | {
            "effect_receipt_digest",
            "deployed_binary_sha256",
            "running_binary_sha256",
            "service_active",
        }
    )
    errors: list[str] = []
    if set(payload) != phase_fields:
        errors.append(f"OPS {phase} operation_receipt fields do not match contract")
    expected_common = {
        "schema_version": f"ops_deploy_{phase}_v1",
        "adapter_id": receipt.get("adapter_id"),
        "intent_id": receipt.get("intent_id"),
        "intent_digest": receipt.get("intent_digest"),
        "source_head": receipt.get("source_head"),
        "target_host": receipt.get("target_host"),
        "target_environment": receipt.get("target_environment"),
        "component_digest": receipt.get("component_digest"),
        "observed_at": evidence.get("observed_at"),
    }
    attestation_key = (
        "pre_runtime_attestation" if phase == "preflight" else "post_runtime_attestation"
    )
    attestation = receipt.get(attestation_key)
    if not isinstance(attestation, dict):
        errors.append(f"OPS {phase} receipt lacks typed runtime attestation")
        attestation = {}
    expected_common.update(
        {
            output: attestation.get(source)
            for output, source in OPS_ATTESTATION_BINDINGS.items()
        }
    )
    for field, expected in expected_common.items():
        if payload.get(field) != expected:
            errors.append(f"OPS {phase} {field} does not match deploy identity")
    wrapper = {
        "kind": f"ops_{phase}_v1",
        "source": f"ops_{phase}",
        "scope": "runtime",
        "host": receipt.get("target_host"),
        "environment": receipt.get("target_environment"),
        "digest": _sha256_bytes(_canonical_bytes(payload)),
        "observed_at": attestation.get("observed_at"),
        "expiry": attestation.get("expires_at"),
    }
    for field, expected in wrapper.items():
        if evidence.get(field) != expected:
            errors.append(f"OPS {phase} evidence {field} is not payload-bound")
    if phase == "preflight":
        if payload.get("tree_clean") is not True or payload.get("ready") is not True:
            errors.append("OPS preflight must prove clean-tree readiness")
    else:
        if payload.get("effect_receipt_digest") != receipt.get("receipt_digest"):
            errors.append("OPS postcheck is not bound to the effect receipt digest")
        deployed = receipt.get("deployed_binary_sha256")
        if (
            payload.get("deployed_binary_sha256") != deployed
            or payload.get("running_binary_sha256") != deployed
            or payload.get("process_identity_digest") != deployed
            or payload.get("service_active") is not True
        ):
            errors.append("OPS postcheck does not prove the deployed binary is active")
    return errors


def validate_effect_evidence(
    evidence: dict[str, Any],
    *,
    expected_adapter_id: str,
    expected_source_head: str,
) -> tuple[list[str], dict[str, Any] | None]:
    """Validate a receipt and every wrapper-to-receipt binding."""

    receipt = evidence.get("receipt")
    errors = validate_effect_receipt(receipt, require_success=True)
    if not isinstance(receipt, dict):
        return errors, None
    bindings = {
        "source": (evidence.get("source"), receipt.get("adapter_id")),
        "digest": (evidence.get("digest"), receipt.get("receipt_digest")),
        "host": (evidence.get("host"), receipt.get("target_host")),
        "environment": (evidence.get("environment"), receipt.get("target_environment")),
        "observed_at": (evidence.get("observed_at"), receipt.get("completed_at")),
        "expiry": (evidence.get("expiry"), receipt.get("evidence_expires_at")),
    }
    for field, (outer, inner) in bindings.items():
        if outer != inner:
            errors.append(f"effect evidence {field} does not match canonical receipt")
    if evidence.get("scope") != "runtime":
        errors.append("deploy effect evidence scope must be runtime")
    if evidence.get("kind") != "effect_adapter_result_v1":
        errors.append("deploy effect evidence kind is invalid")
    if receipt.get("adapter_id") != expected_adapter_id:
        errors.append("effect receipt does not match routed Adapter")
    if receipt.get("source_head") != expected_source_head:
        errors.append("effect receipt source_head does not match closure baseline")
    return errors, receipt if not errors else None


def validate_deploy_effect_binding(
    packet: dict[str, Any],
    route: dict[str, Any],
    fragments_by_node: dict[str, dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    valid_receipts: dict[str, dict[str, Any]],
) -> list[str]:
    """Require intent, preflight, receipt, and independent postcheck for deploy PASS."""

    effect_nodes = [
        node for node in route.get("nodes", [])
        if node.get("kind") == "effect_adapter" and node.get("mandatory")
    ]
    errors: list[str] = []
    routed_adapters = {node["id"] for node in effect_nodes}
    receipt_adapters = {receipt.get("adapter_id") for receipt in valid_receipts.values()}
    if receipt_adapters - routed_adapters:
        errors.append(
            "closure contains unrouted effect Adapter receipts: "
            f"{sorted(str(item) for item in receipt_adapters - routed_adapters)}"
        )
    if not effect_nodes:
        return errors
    for node in effect_nodes:
        matching = [
            (evidence_id, receipt)
            for evidence_id, receipt in valid_receipts.items()
            if receipt.get("adapter_id") == node["id"]
        ]
        if not matching:
            errors.append(f"closure PASS missing effect Adapter receipt {node['id']}")
            continue
        if len(matching) != 1:
            errors.append(f"closure PASS requires exactly one effect Adapter receipt {node['id']}")
            continue
        receipt_id, receipt = matching[0]
        intent_source = f"deployment_intent_v1:{receipt['intent_id']}"
        intent_refs = [
            ref for ref in packet.get("authority_refs", [])
            if ref.get("class") == "claim_evidence" and ref.get("source") == intent_source
        ]
        if len(intent_refs) != 1 or intent_refs[0].get("digest") != receipt.get("intent_digest"):
            errors.append("effect receipt is not cross-bound to deployment_intent_v1 authority")
        else:
            intent_ref = intent_refs[0]
            if intent_ref.get("expiry") != receipt.get("intent_expires_at"):
                errors.append("deployment intent authority expiry does not match effect receipt")
            try:
                if _parse_time(str(intent_ref.get("observed_at", ""))) > _parse_time(receipt["started_at"]):
                    errors.append("deployment intent authority was observed after effect start")
            except (TypeError, ValueError):
                errors.append("deployment intent authority timestamp is invalid")

        def ops_evidence(node_id: str, kind: str, source: str) -> list[dict[str, Any]]:
            fragment = fragments_by_node.get(node_id, {})
            candidates = [
                evidence_by_id[ref]
                for ref in fragment.get("evidence_refs", [])
                if ref in evidence_by_id
                and evidence_by_id[ref].get("scope") == "runtime"
                and evidence_by_id[ref].get("kind") == kind
                and evidence_by_id[ref].get("source") == source
            ]
            phase = "preflight" if node_id == "ops_preflight" else "postcheck"
            valid: list[dict[str, Any]] = []
            for candidate in candidates:
                candidate_errors = _validate_ops_evidence(
                    candidate, phase=phase, receipt=receipt
                )
                if candidate_errors:
                    errors.extend(candidate_errors)
                else:
                    valid.append(candidate)
            return valid

        preflights = ops_evidence("ops_preflight", "ops_preflight_v1", "ops_preflight")
        postchecks = ops_evidence("ops_postcheck", "ops_postcheck_v1", "ops_postcheck")
        if len(preflights) != 1:
            errors.append("deploy PASS requires exactly one independent OPS preflight")
        if len(postchecks) != 1:
            errors.append("deploy PASS requires exactly one independent OPS postcheck")
        if len(preflights) == 1 and len(postchecks) == 1:
            preflight, postcheck = preflights[0], postchecks[0]
            errors.extend(deploy_evidence_identity_errors(
                receipt_id, evidence_by_id[receipt_id], receipt, preflight, postcheck,
            ))
            try:
                if _parse_time(str(preflight.get("observed_at", ""))) > _parse_time(receipt["started_at"]):
                    errors.append("OPS preflight must be observed no later than effect start")
                if _parse_time(str(postcheck.get("observed_at", ""))) < _parse_time(receipt["completed_at"]):
                    errors.append("OPS postcheck must be observed no earlier than effect completion")
            except (TypeError, ValueError):
                errors.append("OPS preflight/postcheck timestamps are invalid")
            accepted_together = any(
                item.get("status") == "PASS"
                and {receipt_id, postcheck.get("id")}.issubset(set(item.get("evidence_refs", [])))
                for item in packet.get("acceptance", [])
            )
            if not accepted_together:
                errors.append(
                    "passed acceptance must bind effect receipt and independent OPS postcheck"
                )
        if packet.get("side_effects", {}).get("runtime_contact") is not True:
            errors.append("deploy closure must truthfully record runtime_contact=true")
        if packet.get("disposition") != "CHANGED":
            errors.append("successful deploy closure disposition must be CHANGED")
    return errors
