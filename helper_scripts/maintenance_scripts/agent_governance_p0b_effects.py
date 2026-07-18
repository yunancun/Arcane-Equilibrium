"""Purpose-built admission and closure bindings for the two-stage P0-B ALR effect."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent_governance_context_validation import validate_context_artifact
from agent_governance_p0b_observer import validate_observer_result
from agent_governance_p0b_phase1_lineage import validate_cutover_phase1_lineage
from agent_governance_p0b_runtime_bindings import validate_phase_runtime_bindings
from agent_governance_p0b_sources import validate_component_claims
from agent_governance_routing import (
    P0B_ADAPTER_ID,
    P0B_CLAIM_KEYS_BY_PHASE,
    _p0b_effect_phase,
)
from agent_governance_schema import schema_subset_errors

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RAW_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
SCHEMA_DIR = Path(__file__).resolve().parents[2] / ".codex/schemas"
REPO_ROOT = Path(__file__).resolve().parents[2]
INTENT_SCHEMA_PATH = SCHEMA_DIR / "p0b_alr_rollforward_intent_v1.schema.json"
RESULT_SCHEMA_PATH = SCHEMA_DIR / "p0b_alr_rollforward_effect_result_v1.schema.json"
CLOSURE_SCHEMA_PATH = SCHEMA_DIR / "closure_packet_v1.schema.json"
PRIVATE_BUNDLE_DESTINATION = (
    "/home/ncyu/BybitOpenClaw/var/openclaw/p0b-observer-deps"
)
COMMON_HARD_STOPS = (
    "phase-scoped P0-B ALR effect only",
    "no live/mainnet authority expansion",
    "no order/broker/decision-lease effect",
    "no unrelated service or user-manager mutation",
    "no ambient environment or secret inheritance",
    "only fresh public Git origin read, normal-lane readonly PG, and existing fixed-path credential load are allowed",
    "no broker/private external contact, package installation, or adapter credential-content read",
    "fail closed; never restore the old generation after cutover begins",
)
P0B_HARD_STOPS_BY_PHASE = {
    "stage": [
        *COMMON_HARD_STOPS,
        "stage keeps openclaw-alr-shadow.service uninterrupted",
    ],
    "cutover": [
        *COMMON_HARD_STOPS,
        "cutover finalizes only after OBSERVER_V2_EXACT_POSTCHECK_PASS",
    ],
}
CONTEXT_ROLES = {
    "pm": "PM",
    "pa": "PA",
    "e3": "E3",
    "ops_preflight": "OPS",
}
GOVERNANCE_ARTIFACT_BINDINGS = {
    "pa_role_fragment_digest": ("pa_role_fragment", "PA", "role_fragment_v1"),
    "pa_command_capture_digest": ("pa_command_capture", "PA", "command_capture_v2"),
    "e3_role_fragment_digest": ("e3_role_fragment", "E3", "role_fragment_v1"),
    "e3_command_capture_digest": ("e3_command_capture", "E3", "command_capture_v2"),
    "ops_preflight_role_fragment_digest": (
        "ops_preflight_role_fragment", "OPS", "role_fragment_v1"
    ),
    "ops_preflight_command_capture_digest": (
        "ops_preflight_command_capture", "OPS", "command_capture_v2"
    ),
    "ops_preflight_attestation_digest": (
        "ops_preflight_attestation", "OPS", "p0b_alr_ops_preflight_attestation_v1"
    ),
    "pm_approval_artifact_digest": (
        "pm_approval_artifact", "PM", "p0b_alr_pm_approval_v1"
    ),
    "phase_runtime_bindings_artifact_digest": (
        "phase_runtime_bindings", "OPS", "phase_runtime_bindings_v1"
    ),
}
@lru_cache(maxsize=1)
def _intent_schema() -> dict[str, Any]:
    return json.loads(INTENT_SCHEMA_PATH.read_text(encoding="utf-8"))
@lru_cache(maxsize=1)
def _result_schema() -> dict[str, Any]:
    return json.loads(RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))
@lru_cache(maxsize=1)
def _closure_schema() -> dict[str, Any]:
    return json.loads(CLOSURE_SCHEMA_PATH.read_text(encoding="utf-8"))
def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
def _digest(value: Any) -> str:
    raw = value if isinstance(value, bytes) else _canonical(value)
    return "sha256:" + hashlib.sha256(raw).hexdigest()

def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


def p0b_intent_digest(intent: dict[str, Any]) -> str:
    return _digest({key: value for key, value in intent.items() if key != "intent_digest"})


def p0b_authorization_digest(authorization: dict[str, Any]) -> str:
    return _digest({
        key: value for key, value in authorization.items()
        if key != "authorization_digest"
    })


def p0b_effect_receipt_digest(receipt: dict[str, Any]) -> str:
    return _digest({key: value for key, value in receipt.items() if key != "receipt_digest"})


def p0b_provisional_digest(provisional: dict[str, Any]) -> str:
    return _digest({
        key: value for key, value in provisional.items()
        if key != "provisional_digest"
    })


def p0b_operation_digest(operation: dict[str, Any]) -> str:
    return _digest({
        key: value for key, value in operation.items()
        if key != "operation_digest"
    })


def _route_digest(route: dict[str, Any]) -> str:
    return _digest(route)


def _typed_confirm(intent: dict[str, Any]) -> str:
    return (
        f"p0b-alr-rollforward:{intent.get('phase')}:{intent.get('target_host')}:"
        f"{intent.get('expected_source_head')}:{intent.get('intent_id')}"
    )


def _semantic_intent_errors(intent: dict[str, Any], *, now: str) -> list[str]:
    errors: list[str] = []
    phase = intent.get("phase")
    if intent.get("intent_digest") != p0b_intent_digest(intent):
        errors.append("P0-B intent_digest does not match canonical intent")
    if intent.get("typed_confirm") != _typed_confirm(intent):
        errors.append("P0-B typed_confirm is not bound to phase/host/head/intent")
    if intent.get("hard_stops") != P0B_HARD_STOPS_BY_PHASE.get(str(phase)):
        errors.append("P0-B hard_stops are not the exact phase contract")
    if intent.get("expected_source_head") != intent.get("expected_origin_main_head"):
        errors.append("P0-B target source head differs from fresh origin/main")
    if intent.get("private_bundle_destination") != PRIVATE_BUNDLE_DESTINATION:
        errors.append("P0-B private bundle destination is not exact")
    claims = intent.get("claim_bindings")
    if not isinstance(claims, dict) or set(claims) != P0B_CLAIM_KEYS_BY_PHASE.get(
        str(phase), frozenset()
    ):
        errors.append("P0-B intent claim_bindings do not exactly match the phase")
    else:
        try:
            if _p0b_effect_phase(claims) != phase:
                errors.append("P0-B intent phase differs from effect selection")
        except ValueError as error:
            errors.append(str(error))
        if intent.get("governance_bindings", {}).get(
            "protected_baseline_digest"
        ) != claims.get("p0b_protected_runtime_baseline"):
            errors.append("P0-B protected runtime baseline is not claim-bound")
    governance = intent.get("governance_bindings", {})
    if governance.get("compiled_route_schema") != "hybrid_execution_dag_v1":
        errors.append("P0-B intent requires hybrid_execution_dag_v1")
    if governance.get("context_artifact_schema") != "context_artifact_v1":
        errors.append("P0-B intent requires materialized context_artifact_v1")
    try:
        approved = _parse_time(str(intent.get("approved_at", "")))
        expiry = _parse_time(str(intent.get("expires_at", "")))
        current = _parse_time(now)
        ops_observed = _parse_time(str(governance.get("ops_preflight_observed_at", "")))
        ops_expiry = _parse_time(str(governance.get("ops_preflight_expires_at", "")))
        if not approved <= current < expiry:
            errors.append("P0-B intent is outside its approval window")
        maximum_ttl = timedelta(minutes=15) if phase == "cutover" else timedelta(hours=4)
        if expiry - approved > maximum_ttl:
            errors.append(f"P0-B {phase} intent TTL exceeds its phase limit")
        if not ops_observed <= current < ops_expiry:
            errors.append("P0-B OPS preflight attestation is stale")
        if ops_expiry - ops_observed > timedelta(minutes=15):
            errors.append("P0-B OPS preflight attestation TTL exceeds fifteen minutes")
    except (TypeError, ValueError):
        errors.append("P0-B intent timestamps are invalid")
    return errors


def validate_p0b_intent(
    intent: Any,
    *,
    route: dict[str, Any],
    context_artifacts: dict[str, dict[str, Any]],
    governance_artifacts: dict[str, Any],
    authorized_argv: list[str],
    expected_local_head: str,
    fresh_origin_main_head: str,
    now: str,
) -> list[str]:
    """Validate every byte-bearing admission input before an effect is possible."""

    if not isinstance(intent, dict):
        return ["P0-B intent must be an object"]
    schema = _intent_schema()
    errors = [
        f"P0-B intent schema violation: {error}"
        for error in schema_subset_errors(intent, schema, schema)
    ]
    errors.extend(_semantic_intent_errors(intent, now=now))
    errors.extend(validate_component_claims(
        intent.get("claim_bindings", {}), root=REPO_ROOT,
        phase=str(intent.get("phase", "")),
    ))
    effect_nodes = [
        node for node in route.get("nodes", [])
        if node.get("kind") == "effect_adapter" and node.get("mandatory")
    ]
    if len(effect_nodes) != 1 or effect_nodes[0].get("id") != P0B_ADAPTER_ID:
        errors.append("P0-B intent route did not select the exact Adapter")
    elif effect_nodes[0].get("effect_phase") != intent.get("phase"):
        errors.append("P0-B intent phase differs from compiled route")
    bindings = intent.get("governance_bindings", {})
    phase_runtime_artifact = governance_artifacts.get("phase_runtime_bindings", {})
    if route.get("schema_version") != "hybrid_execution_dag_v1":
        errors.append("P0-B compiled route schema is invalid")
    if bindings.get("compiled_route_digest") != _route_digest(route):
        errors.append("P0-B compiled route digest mismatch")
    if bindings.get("route_dag_digest") != route.get("dag_digest"):
        errors.append("P0-B route DAG digest mismatch")
    if intent.get("claim_bindings") != route.get("task_facts", {}).get("claim_inputs"):
        errors.append("P0-B intent claims differ from compiled task contract")
    if intent.get("expected_source_head") not in {
        expected_local_head, fresh_origin_main_head
    } or expected_local_head != fresh_origin_main_head:
        errors.append("P0-B target is not dynamic exact local HEAD plus fresh origin/main")
    expected_context_keys = set(CONTEXT_ROLES)
    if set(context_artifacts) != expected_context_keys:
        errors.append("P0-B materialized per-role Context inventory is not exact")
    else:
        for key, role in CONTEXT_ROLES.items():
            artifact = context_artifacts[key]
            result = validate_context_artifact(
                artifact,
                now=now,
                expected_task_facts=route.get("task_facts"),
            )
            errors.extend(
                f"P0-B {key} context artifact invalid: {error}"
                for error in result.get("errors", [])
            )
            plan = result.get("plan") or {}
            if plan.get("role") != role:
                errors.append(f"P0-B {key} context artifact role mismatch")
            field = f"{key}_context_artifact_digest"
            if bindings.get(field) != artifact.get("artifact_digest"):
                errors.append(f"P0-B {key} context artifact digest mismatch")
            if artifact.get("task_contract_digest") != intent.get("task_contract_digest"):
                errors.append(f"P0-B {key} context task contract mismatch")
        pm_digest = context_artifacts["pm"].get("artifact_digest")
        if intent.get("context_artifact_digest") != pm_digest:
            errors.append("P0-B intent is not bound to PM materialized Context")
    if set(governance_artifacts) != {
        item[0] for item in GOVERNANCE_ARTIFACT_BINDINGS.values()
    }:
        errors.append("P0-B governance artifact inventory is not exact")
    else:
        for field, (key, role, schema_version) in GOVERNANCE_ARTIFACT_BINDINGS.items():
            artifact = governance_artifacts[key]
            if not isinstance(artifact, dict):
                errors.append(f"P0-B {key} must be a typed object")
                continue
            artifact_digest = (
                _digest({
                    item: value for item, value in artifact.items()
                    if item != "artifact_digest"
                })
                if schema_version == "phase_runtime_bindings_v1"
                else _digest(artifact)
            )
            if bindings.get(field) != artifact_digest:
                errors.append(f"P0-B {key} content digest mismatch")
            if artifact.get("schema_version") != schema_version:
                errors.append(f"P0-B {key} schema mismatch")
            observed_role = artifact.get("role", artifact.get("role_id"))
            if observed_role is not None and observed_role != role:
                errors.append(f"P0-B {key} role mismatch")
            if schema_version == "role_fragment_v1" and (
                artifact.get("gate_verdict") != "PASS"
                or artifact.get("work_status") not in {"DONE", "DONE_WITH_CONCERNS"}
            ):
                errors.append(f"P0-B {key} does not carry a PASS verdict")
            if schema_version == "command_capture_v2" and (
                artifact.get("result") != "PASS" or artifact.get("exit_code") != 0
            ):
                errors.append(f"P0-B {key} command capture did not PASS")
            if schema_version == "phase_runtime_bindings_v1":
                errors.extend(validate_phase_runtime_bindings(artifact, intent=intent))
        errors.extend(validate_cutover_phase1_lineage(
            intent, phase_runtime_artifact,
            authorization_validator=validate_p0b_runtime_authorization,
            runtime_bindings_validator=validate_phase_runtime_bindings,
        ))
    if (
        not isinstance(authorized_argv, list)
        or not authorized_argv
        or any(not isinstance(arg, str) or not arg for arg in authorized_argv)
        or bindings.get("authorized_argv_digest") != _digest(authorized_argv)
    ):
        errors.append("P0-B authorized argv bytes are not digest-bound")
    else:
        runtime_path = bindings.get("phase_runtime_bindings_path")
        raw_runtime_digest = str(
            bindings.get("phase_runtime_bindings_artifact_digest", "")
        ).removeprefix("sha256:")
        authorization_path = bindings.get("authorization_path")
        required_argv = [
            (
                "--phase1-apply" if intent.get("phase") == "stage"
                else "--phase2-apply"
            ),
            "--authorization-json", authorization_path,
            "--runtime-bindings-json", runtime_path,
            "--runtime-bindings-sha256", raw_runtime_digest,
        ]
        if intent.get("phase") == "cutover":
            phase1_receipt_path = phase_runtime_artifact.get(
                "phase_paths", {}
            ).get("phase1_receipt_path")
            required_argv.extend([
                "--phase1-receipt-json", phase1_receipt_path,
                "--phase1-receipt-sha256",
                str(intent.get("phase1_effect_receipt_digest", "")).removeprefix(
                    "sha256:"
                ),
            ])
        if (
            not isinstance(runtime_path, str)
            or not runtime_path.startswith("/")
            or not isinstance(authorization_path, str)
            or not authorization_path.startswith("/")
            or authorized_argv != required_argv
        ):
            errors.append("P0-B authorized argv is not the exact ordered phase contract")
    return errors


def build_p0b_runtime_authorization(intent: dict[str, Any]) -> dict[str, Any]:
    """Project one already validated intent into the only core-consumable authority."""

    authorization = {
        **{key: value for key, value in intent.items() if key != "schema_version"},
        "schema_version": "p0b_alr_runtime_authorization_v1",
    }
    authorization["authorization_digest"] = p0b_authorization_digest(authorization)
    return authorization


def validate_p0b_runtime_authorization(
    authorization: Any, *, now: str
) -> list[str]:
    if not isinstance(authorization, dict):
        return ["P0-B runtime authorization must be an object"]
    expected_fields = set(_intent_schema()["required"]) | {"authorization_digest"}
    expected_fields.remove("intent_digest")
    expected_fields.add("intent_digest")
    if set(authorization) != expected_fields:
        return ["P0-B runtime authorization fields are not exact"]
    errors: list[str] = []
    if authorization.get("schema_version") != "p0b_alr_runtime_authorization_v1":
        errors.append("P0-B runtime authorization schema is invalid")
    result_schema = _result_schema()
    errors.extend(
        f"P0-B runtime authorization schema violation: {error}"
        for error in schema_subset_errors(
            authorization, result_schema["$defs"]["runtimeAuthorization"],
            result_schema,
        )
    )
    intent = {
        **{key: value for key, value in authorization.items()
           if key != "authorization_digest"},
        "schema_version": "p0b_alr_rollforward_intent_v1",
    }
    schema = _intent_schema()
    errors.extend(
        f"P0-B runtime authorization intent projection invalid: {error}"
        for error in schema_subset_errors(intent, schema, schema)
    )
    errors.extend(_semantic_intent_errors(intent, now=now))
    if authorization.get("authorization_digest") != p0b_authorization_digest(
        authorization
    ):
        errors.append("P0-B runtime authorization digest mismatch")
    return errors


def _validate_provisional(provisional: dict[str, Any], *, now: str) -> list[str]:
    schema = _result_schema()["$defs"]["provisionalCutover"]
    errors = [
        f"P0-B provisional cutover schema violation: {error}"
        for error in schema_subset_errors(provisional, schema, _result_schema())
    ]
    authorization = provisional.get("cutover_authorization")
    if isinstance(authorization, dict):
        errors.extend(validate_p0b_runtime_authorization(authorization, now=now))
        if provisional.get("cutover_authorization_digest") != authorization.get(
            "authorization_digest"
        ):
            errors.append("P0-B provisional cutover authorization digest mismatch")
        if authorization.get("phase") != "cutover":
            errors.append("P0-B provisional contains non-cutover authorization")
    else:
        errors.append("P0-B provisional lacks exact cutover authorization")
    return errors


def validate_p0b_effect_receipt(
    receipt: Any, *, expected_source_head: str, require_success: bool = False
) -> list[str]:
    if not isinstance(receipt, dict):
        return ["P0-B effect receipt must be an object"]
    schema = _result_schema()
    errors = [
        f"P0-B effect result schema violation: {error}"
        for error in schema_subset_errors(receipt, schema, schema)
    ]
    phase = str(receipt.get("phase", ""))
    status = receipt.get("effect_status")
    expected_status = {
        "stage": "PHASE1_STAGED_UNINTERRUPTED_PASS",
        "cutover": "PHASE2_APPLIED_POSTCHECK_PASS",
    }.get(phase)
    if receipt.get("receipt_digest") != p0b_effect_receipt_digest(receipt):
        errors.append("P0-B effect receipt digest mismatch")
    if receipt.get("source_head") != expected_source_head:
        errors.append("P0-B effect source head differs from closure baseline")
    if receipt.get("origin_main_head") != receipt.get("source_head"):
        errors.append("P0-B effect source head differs from fresh origin/main")
    if receipt.get("typed_confirm") != (
        f"p0b-alr-rollforward:{phase}:{receipt.get('target_host')}:"
        f"{receipt.get('source_head')}:{receipt.get('intent_id')}"
    ):
        errors.append("P0-B effect typed_confirm mismatch")
    if receipt.get("hard_stops") != P0B_HARD_STOPS_BY_PHASE.get(phase):
        errors.append("P0-B effect hard stops mismatch")
    claims = receipt.get("claim_bindings")
    if not isinstance(claims, dict) or set(claims) != P0B_CLAIM_KEYS_BY_PHASE.get(
        phase, frozenset()
    ):
        errors.append("P0-B effect claims are not exact")
    success = status == expected_status
    phase_result = receipt.get("phase_result")
    failure_reason = receipt.get("failure_reason")
    if success:
        if failure_reason is not None or not isinstance(phase_result, dict):
            errors.append("P0-B successful effect requires phase result and no failure")
        elif phase == "stage":
            errors.extend(
                f"P0-B stage result invalid: {error}"
                for error in schema_subset_errors(
                    phase_result, schema["$defs"]["stageResult"], schema
                )
            )
            bundle = phase_result.get("private_bundle", {})
            bindings = {
                "source_digest": "p0b_private_bundle_stager_source",
                "test_digest": "p0b_private_bundle_stager_tests",
                "source_manifest_digest": "p0b_private_bundle_source_manifest",
                "destination_absent_attestation_digest": (
                    "p0b_private_bundle_destination_absent_attestation"
                ),
            }
            for field, claim in bindings.items():
                if bundle.get(field) != claims.get(claim):
                    errors.append(f"P0-B stage private bundle {field} is not claim-bound")
            inventory_bindings = {
                "completion_inventory_digest": "p0b_completion_inventory",
                "producer_inventory_digest": "p0b_producer_inventory",
                "live_inventory_digest": "p0b_live_inventory",
            }
            for field, claim in inventory_bindings.items():
                if phase_result.get(field) != claims.get(claim):
                    errors.append(f"P0-B stage {field} is not claim-bound")
            if receipt.get("pre_runtime_identity_digest") != receipt.get(
                "post_runtime_identity_digest"
            ):
                errors.append("P0-B stage changed the uninterrupted runtime identity")
        else:
            errors.extend(
                f"P0-B cutover result invalid: {error}"
                for error in schema_subset_errors(
                    phase_result, schema["$defs"]["cutoverResult"], schema
                )
            )
            provisional = phase_result.get("provisional_cutover", {})
            errors.extend(_validate_provisional(
                provisional, now=str(receipt.get("completed_at", ""))
            ))
            if phase_result.get("provisional_cutover_digest") != p0b_provisional_digest(
                provisional
            ):
                errors.append("P0-B provisional digest mismatch")
            observer = phase_result.get("observer", {})
            errors.extend(validate_observer_result(
                observer, receipt=receipt, provisional=provisional
            ))
            if provisional.get("target_head") != receipt.get("source_head"):
                errors.append("P0-B provisional target head mismatch")
            if phase_result.get("phase1_effect_receipt_digest") != claims.get(
                "p0b_phase1_receipt"
            ):
                errors.append("P0-B cutover phase1 receipt is not claim-bound")
            if phase_result.get("phase1_closure_digest") != claims.get(
                "p0b_phase1_closure"
            ):
                errors.append("P0-B cutover phase1 closure is not claim-bound")
            result_claims = {
                "sealed_lineage_bundle_digest": "p0b_sealed_lineage_bundle",
                "private_bundle_receipt_digest": "p0b_private_bundle_receipt",
                "private_bundle_destination_digest": "p0b_private_bundle_destination",
            }
            for field, claim in result_claims.items():
                if phase_result.get(field) != claims.get(claim):
                    errors.append(f"P0-B cutover {field} is not claim-bound")
            raw_bindings = {
                "phase1_receipt": "p0b_phase1_receipt",
                "private_deps_receipt": "p0b_private_bundle_receipt",
                "live_board": "p0b_staged_candidate_board",
            }
            for field, claim in raw_bindings.items():
                raw = provisional.get(field, {}).get("sha256")
                if "sha256:" + str(raw) != claims.get(claim):
                    errors.append(f"P0-B provisional {field} is not claim-bound")
            fence = provisional.get("generation_fence", {})
            fence_claims = {
                "completion_inventory_sha256": "p0b_completion_inventory",
                "producer_inventory_sha256": "p0b_producer_inventory",
            }
            for field, claim in fence_claims.items():
                if fence.get(field) != claims.get(claim):
                    errors.append(f"P0-B provisional {field} is not claim-bound")
            service = phase_result.get("service", {})
            if service.get("source_head") != receipt.get("source_head") or provisional.get(
                "active_identity", {}
            ).get("ALRSourceHead") != receipt.get("source_head"):
                errors.append("P0-B cutover service identity is not target-head exact")
    elif status == "FAILED":
        if phase_result is not None or not isinstance(failure_reason, str) or not failure_reason:
            errors.append("P0-B FAILED result requires null phase result and failure reason")
    else:
        errors.append("P0-B effect status does not match its phase")
    if require_success and not success:
        errors.append("P0-B effect receipt does not prove successful phase apply")
    try:
        approved = _parse_time(str(receipt.get("approved_at", "")))
        started = _parse_time(str(receipt.get("started_at", "")))
        completed = _parse_time(str(receipt.get("completed_at", "")))
        intent_expiry = _parse_time(str(receipt.get("intent_expires_at", "")))
        evidence_expiry = _parse_time(str(receipt.get("evidence_expires_at", "")))
        if not approved <= started <= completed < intent_expiry:
            errors.append("P0-B effect approval/start/completion order is invalid")
        if not completed < evidence_expiry <= completed + timedelta(minutes=15):
            errors.append("P0-B effect evidence TTL exceeds fifteen minutes")
        if phase == "cutover" and isinstance(phase_result, dict):
            provisional = phase_result.get("provisional_cutover", {})
            observer = phase_result.get("observer", {})
            if _parse_time(str(observer.get("observed_at_utc", ""))) < _parse_time(
                str(provisional.get("created_at", receipt.get("started_at", "")))
            ):
                errors.append("P0-B observer predates provisional cutover")
    except (TypeError, ValueError):
        errors.append("P0-B effect timestamps are invalid")
    return errors


def validate_p0b_effect_evidence(
    evidence: dict[str, Any], *, expected_source_head: str
) -> tuple[list[str], dict[str, Any] | None]:
    receipt = evidence.get("receipt")
    errors = validate_p0b_effect_receipt(
        receipt, expected_source_head=expected_source_head, require_success=True
    )
    if not isinstance(receipt, dict):
        return errors, None
    bindings = {
        "source": receipt.get("adapter_id"),
        "digest": receipt.get("receipt_digest"),
        "host": receipt.get("target_host"),
        "environment": receipt.get("target_environment"),
        "observed_at": receipt.get("completed_at"),
        "expiry": receipt.get("evidence_expires_at"),
    }
    for field, expected in bindings.items():
        if evidence.get(field) != expected:
            errors.append(f"P0-B effect evidence {field} is not receipt-bound")
    if evidence.get("kind") != "effect_adapter_result_v1" or evidence.get(
        "scope"
    ) != "runtime":
        errors.append("P0-B effect evidence wrapper is invalid")
    return errors, receipt if not errors else None


def _validate_p0b_ops_evidence(
    evidence: dict[str, Any],
    *,
    node_id: str,
    receipt: dict[str, Any],
    route: dict[str, Any],
) -> list[str]:
    phase = str(receipt.get("phase", ""))
    operation = evidence.get("operation_receipt")
    if not isinstance(operation, dict):
        return [f"P0-B {node_id} lacks typed operation_receipt"]
    preflight = node_id == "ops_preflight"
    schema_name = "opsP0bPreflight" if preflight else "opsP0bPostcheck"
    closure_schema = _closure_schema()
    errors = [
        f"P0-B {node_id} schema violation: {error}"
        for error in schema_subset_errors(
            operation, closure_schema["$defs"][schema_name], closure_schema
        )
    ]
    expected = {
        "schema_version": (
            "ops_p0b_alr_preflight_v1" if preflight
            else "ops_p0b_alr_postcheck_v1"
        ),
        "adapter_id": P0B_ADAPTER_ID,
        "phase": phase,
        "intent_id": receipt.get("intent_id"),
        "intent_digest": receipt.get("intent_digest"),
        "task_contract_digest": receipt.get("task_contract_digest"),
        "context_artifact_digest": receipt.get("context_artifact_digest"),
        "compiled_route_digest": _route_digest(route),
        "source_head": receipt.get("source_head"),
        "target_host": receipt.get("target_host"),
        "target_user_unit": receipt.get("target_user_unit"),
    }
    if preflight:
        expected.update({
            "runtime_bindings_digest": receipt.get("claim_bindings", {}).get(
                "p0b_phase_runtime_bindings"
            ),
            "protected_baseline_digest": receipt.get("claim_bindings", {}).get(
                "p0b_protected_runtime_baseline"
            ),
            "ready": True,
        })
    else:
        phase_result = receipt.get("phase_result")
        observer = phase_result.get("observer") if isinstance(phase_result, dict) else None
        expected.update({
            "effect_receipt_digest": receipt.get("receipt_digest"),
            "phase_result_digest": (
                _digest(phase_result) if isinstance(phase_result, dict) else None
            ),
            "observer_receipt_digest": (
                _digest(observer)
                if phase == "cutover" and isinstance(observer, dict)
                else None
            ),
            "verified": True,
        })
    for field, value in expected.items():
        if operation.get(field) != value:
            errors.append(f"P0-B {node_id} {field} is not exact-bound")
    if operation.get("operation_digest") != p0b_operation_digest(operation):
        errors.append(f"P0-B {node_id} operation_digest mismatch")
    wrapper = {
        "kind": f"ops_{'preflight' if preflight else 'postcheck'}_v1",
        "source": f"p0b_{node_id}",
        "scope": "runtime",
        "host": receipt.get("target_host"),
        "environment": receipt.get("target_environment"),
        "digest": operation.get("operation_digest"),
        "observed_at": operation.get("observed_at"),
        "expiry": operation.get("expires_at"),
    }
    for field, value in wrapper.items():
        if evidence.get(field) != value:
            errors.append(f"P0-B {node_id} evidence {field} is not payload-bound")
    try:
        observed = _parse_time(str(operation.get("observed_at", "")))
        expiry = _parse_time(str(operation.get("expires_at", "")))
        boundary = _parse_time(str(receipt.get(
            "started_at" if preflight else "completed_at", ""
        )))
        if not observed < expiry or expiry - observed > timedelta(minutes=15):
            errors.append(f"P0-B {node_id} TTL exceeds fifteen minutes")
        if preflight and not observed <= boundary < expiry:
            errors.append("P0-B OPS preflight does not cover effect start")
        if not preflight and observed < boundary:
            errors.append("P0-B OPS postcheck predates final effect receipt")
    except (TypeError, ValueError):
        errors.append(f"P0-B {node_id} timestamps are invalid")
    return errors


def validate_p0b_effect_binding(
    packet: dict[str, Any],
    route: dict[str, Any],
    fragments_by_node: dict[str, dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    valid_receipts: dict[str, dict[str, Any]],
) -> list[str]:
    """Closure admission for one phase; never borrow generic binary deploy proof."""

    errors: list[str] = []
    matching = [
        (evidence_id, receipt) for evidence_id, receipt in valid_receipts.items()
        if receipt.get("adapter_id") == P0B_ADAPTER_ID
    ]
    if len(matching) != 1:
        return ["P0-B closure PASS requires exactly one phase effect receipt"]
    receipt_id, receipt = matching[0]
    phase = receipt.get("phase")
    try:
        route_phase = _p0b_effect_phase(
            route.get("task_facts", {}).get("claim_inputs", {})
        )
        if route_phase != phase:
            errors.append("P0-B closure route phase differs from receipt")
    except ValueError as error:
        errors.append(f"P0-B closure route is invalid: {error}")
    context = packet.get("dispatch", {}).get("context_artifact", {})
    if receipt.get("task_contract_digest") != context.get("task_contract_digest"):
        errors.append("P0-B receipt task contract differs from closure Context")
    if receipt.get("context_artifact_digest") != context.get("artifact_digest"):
        errors.append("P0-B receipt Context artifact differs from closure admission")
    if receipt.get("claim_bindings") != route.get("task_facts", {}).get("claim_inputs"):
        errors.append("P0-B receipt claims differ from closure route")
    intent_source = f"p0b_alr_rollforward_intent_v1:{receipt.get('intent_id')}"
    intent_refs = [
        ref for ref in packet.get("authority_refs", [])
        if ref.get("class") == "claim_evidence" and ref.get("source") == intent_source
    ]
    if len(intent_refs) != 1 or intent_refs[0].get("digest") != receipt.get(
        "intent_digest"
    ):
        errors.append("P0-B effect receipt lacks exact intent authority")
    else:
        if intent_refs[0].get("expiry") != receipt.get("intent_expires_at"):
            errors.append("P0-B intent authority expiry mismatch")
    valid_ops: dict[str, list[dict[str, Any]]] = {}
    for node_id, expected_kind in (
        ("ops_preflight", "ops_preflight_v1"),
        ("ops_postcheck", "ops_postcheck_v1"),
    ):
        fragment = fragments_by_node.get(node_id, {})
        candidates = [
            evidence_by_id[ref] for ref in fragment.get("evidence_refs", [])
            if ref in evidence_by_id
            and evidence_by_id[ref].get("kind") == expected_kind
            and evidence_by_id[ref].get("source") == f"p0b_{node_id}"
            and evidence_by_id[ref].get("operation_receipt", {}).get("adapter_id")
            == P0B_ADAPTER_ID
            and evidence_by_id[ref].get("operation_receipt", {}).get("phase") == phase
            and evidence_by_id[ref].get("operation_receipt", {}).get("intent_digest")
            == receipt.get("intent_digest")
        ]
        valid_ops[node_id] = []
        for candidate in candidates:
            candidate_errors = _validate_p0b_ops_evidence(
                candidate, node_id=node_id, receipt=receipt, route=route
            )
            if candidate_errors:
                errors.extend(candidate_errors)
            else:
                valid_ops[node_id].append(candidate)
        if len(valid_ops[node_id]) != 1:
            errors.append(f"P0-B closure requires exactly one independent {node_id}")
    postchecks = valid_ops.get("ops_postcheck", [])
    accepted = bool(postchecks) and any(
        item.get("status") == "PASS"
        and {receipt_id, postchecks[0].get("id")}.issubset(
            set(item.get("evidence_refs", []))
        )
        for item in packet.get("acceptance", [])
    )
    if not accepted:
        errors.append(
            "P0-B passed acceptance does not bind final receipt plus OPS postcheck"
        )
    if packet.get("side_effects", {}).get("runtime_contact") is not True:
        errors.append("P0-B successful effect must record runtime_contact=true")
    if packet.get("disposition") != "CHANGED":
        errors.append("P0-B successful effect closure must be CHANGED")
    return errors
