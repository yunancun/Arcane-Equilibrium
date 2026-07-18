"""Fail-closed Phase 1 governance lineage admission for P0-B cutover."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from copy import deepcopy
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from agent_governance_schema import schema_subset_errors


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / ".codex/schemas"
CLOSURE_SCHEMA_PATH = (
    SCHEMA_DIR / "p0b_alr_phase1_governance_closure_v1.schema.json"
)
BUNDLE_SCHEMA_PATH = (
    SCHEMA_DIR / "p0b_alr_phase1_sealed_lineage_bundle_v1.schema.json"
)
PACKET_SCHEMA_PATH = SCHEMA_DIR / "closure_packet_v1.schema.json"
PRIVATE_DESTINATION = "/home/ncyu/BybitOpenClaw/var/openclaw/p0b-observer-deps"
CORE_SCHEMA = "p0b_alr_current_head_rollforward_v1"
ADAPTER_ID = "p0b_alr_rollforward_adapter_v1"
UNIT = "openclaw-alr-shadow.service"

CORE_RECEIPT_FIELDS = {
    "schema_version", "phase", "status", "approval_id",
    "authorization_digest", "stage_authorization", "stage_authorization_digest",
    "stage_runtime_bindings", "stage_runtime_bindings_artifact_digest",
    "stage_authorized_runtime", "target_head", "old_head", "protected_sha256",
    "old_alr_retained_running", "global_pin_retained_old",
    "live_publication_performed", "sealed_lineage", "completed_at_utc", "intent",
    "locks_held_through_effect_receipt", "boundaries",
}
AUTHORIZED_RUNTIME_FIELDS = {
    "expected_old_runtime_source_head", "expected_old_pin_digest",
    "expected_source_tree_digest", "expected_pin_consumer_inventory_digest",
    "expected_runtime_identity_digest",
}
SEALED_LINEAGE_FIELDS = {
    "started_at_utc", "completed_at_utc", "token", "completion",
    "producer_board", "cron_staged_board", "staged_board",
    "staging_publisher_receipt", "private_deps_receipt",
    "private_deps_destination", "private_deps_manifest_sha256",
    "publisher_result", "execution_tree", "live_inventory_sha256",
    "completion_inventory_sha256", "producer_inventory_sha256",
    "ledger_pre_inventory_sha256", "ledger_post_inventory_sha256",
    "lane_effective_config_sha256", "alr_availability_monitor",
    "normal_lane_returncode",
}
LANE_BOUNDARIES = {
    "broker_contact": False,
    "pg_access": "normal_lane_readonly",
    "credential_content_read": "normal_lane_existing_environment_load",
    "source_mutation": False,
    "order_effect": False,
    "risk_or_cost_gate_mutation": False,
    "policy_or_dsn_mutation": False,
    "engine_api_watchdog_mutation": False,
    "adapter_pg_access": False,
    "adapter_credential_content_read": False,
    "normal_lane_pg_readonly": True,
    "normal_lane_existing_environment_load": True,
    "live_alr_publication": False,
    "alr_service_mutation": False,
    "generation_pin_mutation": False,
}
PRIVATE_BOUNDARIES = {
    "service_mutation": False,
    "database_access": False,
    "broker_contact": False,
    "credential_access": False,
    "subprocess_spawned": False,
    "source_repository_mutation": False,
}


@lru_cache(maxsize=1)
def _closure_schema() -> dict[str, Any]:
    return json.loads(CLOSURE_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _bundle_schema() -> dict[str, Any]:
    return json.loads(BUNDLE_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _packet_schema() -> dict[str, Any]:
    return json.loads(PACKET_SCHEMA_PATH.read_text(encoding="utf-8"))


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _without(value: dict[str, Any], field: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != field}


def _strict_json(raw: bytes, *, label: str) -> dict[str, Any]:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ValueError(f"duplicate key {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"invalid constant {item}")
            ),
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not strict JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _identity(observed: os.stat_result) -> tuple[int, ...]:
    return (
        observed.st_dev, observed.st_ino, observed.st_mode, observed.st_nlink,
        observed.st_uid, observed.st_gid, observed.st_size, observed.st_mtime_ns,
        observed.st_ctime_ns,
    )


def _read_binding(binding: Any, *, label: str) -> tuple[dict[str, Any], bytes]:
    if (
        not isinstance(binding, dict)
        or set(binding) != {"path", "sha256"}
        or not isinstance(binding.get("path"), str)
        or not Path(binding["path"]).is_absolute()
        or not isinstance(binding.get("sha256"), str)
        or len(binding["sha256"]) != 64
    ):
        raise ValueError(f"{label} binding is invalid")
    path = Path(binding["path"])
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError(f"{label} is not a single-link regular file")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        final = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = os.lstat(path)
    raw = b"".join(chunks)
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_nlink != 1
        or _identity(before) != _identity(opened)
        or _identity(opened) != _identity(final)
        or _identity(final) != _identity(after)
        or len(raw) != opened.st_size
        or hashlib.sha256(raw).hexdigest() != binding["sha256"]
    ):
        raise ValueError(f"{label} identity or digest changed while reading")
    return _strict_json(raw, label=label), raw


def _time(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} timestamp is invalid")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{label} timestamp lacks timezone")
    return parsed


def _schema_errors(
    value: dict[str, Any], schema: dict[str, Any], *, label: str
) -> list[str]:
    return [
        f"P0-B {label} schema violation: {error}"
        for error in schema_subset_errors(value, schema, schema)
    ]


def _no_authority_errors(board: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    safe_strings = {"", "DENIED", "DISABLED", "FALSE", "NONE", "NOT_GRANTED", "NO_AUTHORITY"}

    def safe(value: Any) -> bool:
        return value is False or value is None or (
            isinstance(value, str) and value.upper() in safe_strings
        )

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = str(key).lower()
                sensitive = (
                    any(
                        domain in lowered and "authority" in lowered
                        for domain in ("order", "probe", "promotion", "runtime")
                    )
                    or lowered == "promotion_evidence"
                )
                if sensitive and not safe(child):
                    errors.append(f"P0-B staged board authority grant at {path}.{key}")
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    if board.get("order_authority") != "NOT_GRANTED":
        errors.append("P0-B staged board order authority is not denied")
    if board.get("promotion_evidence") is not False:
        errors.append("P0-B staged board promotion evidence is not false")
    visit(board, "board")
    return errors


def _validate_board(board: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    candidate = board.get("learning_candidate_board")
    if (
        board.get("schema_version")
        != "cost_gate_demo_learning_lane_blocked_outcome_review_v6"
        or board.get("candidate_board_generation_state") != "COMPLETE"
        or board.get("ledger_scan_status") != "COMPLETE"
        or board.get("latest_alias_used", False) is not False
        or not isinstance(candidate, dict)
        or candidate.get("schema_version") != "cost_gate_learning_candidate_board_v2"
        or candidate.get("candidate_universe_complete") is not True
        or not isinstance(candidate.get("candidate_rows"), list)
        or any(not isinstance(row, dict) for row in candidate.get("candidate_rows", []))
    ):
        errors.append("P0-B staged candidate board is not an exact COMPLETE v2 board")
    errors.extend(_no_authority_errors(board))
    return errors


def _validate_private(
    receipt: dict[str, Any], *, destination: str, manifest: str
) -> list[str]:
    expected_fields = {
        "schema_version", "status", "reason_codes", "source_root", "destination",
        "source_manifest_sha256", "destination_manifest_sha256",
        "mutation_performed", "boundaries", "source_total_bytes",
    }
    if set(receipt) != expected_fields:
        return ["P0-B private dependency receipt fields are not exact"]
    if (
        receipt.get("schema_version") != "p0b_psycopg_private_bundle_stage_v1"
        or receipt.get("status") != "APPLIED_POSTCHECK_PASS"
        or receipt.get("reason_codes") != []
        or not isinstance(receipt.get("source_root"), str)
        or receipt.get("destination") != destination
        or receipt.get("source_manifest_sha256") != manifest
        or receipt.get("destination_manifest_sha256") != manifest
        or receipt.get("mutation_performed") is not True
        or receipt.get("boundaries") != PRIVATE_BOUNDARIES
        or not isinstance(receipt.get("source_total_bytes"), int)
        or receipt["source_total_bytes"] < 1
    ):
        return ["P0-B private dependency receipt is not exact applied PASS"]
    return []


def _validate_core_receipt(
    receipt: dict[str, Any], bundle: dict[str, Any], stage_authorization: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    sealed = receipt.get("sealed_lineage")
    authorized = receipt.get("stage_authorized_runtime")
    locks = receipt.get("locks_held_through_effect_receipt")
    if set(receipt) != CORE_RECEIPT_FIELDS:
        errors.append("P0-B Phase 1 core receipt fields are not exact")
    if (
        receipt.get("schema_version") != CORE_SCHEMA
        or receipt.get("phase") != 1
        or receipt.get("status") != "PHASE1_STAGING_APPLIED_PASS"
        or receipt.get("approval_id") != bundle.get("intent_id")
        or receipt.get("authorization_digest") != bundle.get("stage_authorization_digest")
        or receipt.get("stage_authorization") != bundle.get("stage_authorization")
        or receipt.get("stage_authorization_digest") != bundle.get("stage_authorization_digest")
        or receipt.get("stage_runtime_bindings") != bundle.get("stage_runtime_bindings")
        or receipt.get("stage_runtime_bindings_artifact_digest")
        != bundle.get("stage_runtime_bindings_artifact_digest")
        or receipt.get("target_head") != bundle.get("target_head")
        or receipt.get("old_alr_retained_running") is not True
        or receipt.get("global_pin_retained_old") is not True
        or receipt.get("live_publication_performed") is not False
        or receipt.get("boundaries") != LANE_BOUNDARIES
    ):
        errors.append("P0-B Phase 1 core receipt is not exact staging PASS")
    if not isinstance(authorized, dict) or set(authorized) != AUTHORIZED_RUNTIME_FIELDS:
        errors.append("P0-B Phase 1 authorized runtime projection is not exact")
    elif any(authorized.get(field) != stage_authorization.get(field) for field in authorized):
        errors.append("P0-B Phase 1 authorized runtime differs from stage authority")
    if not isinstance(sealed, dict) or set(sealed) != SEALED_LINEAGE_FIELDS:
        errors.append("P0-B Phase 1 sealed lineage fields are not exact")
    else:
        for field, bundle_field in (
            ("staged_board", "staged_board"),
            ("private_deps_receipt", "private_deps_receipt"),
        ):
            if sealed.get(field) != bundle.get(bundle_field):
                errors.append(f"P0-B Phase 1 sealed lineage {field} mismatch")
        if (
            sealed.get("private_deps_destination") != bundle.get("private_deps_destination")
            or sealed.get("private_deps_manifest_sha256")
            != bundle.get("private_deps_manifest_sha256")
            or sealed.get("normal_lane_returncode") != 0
        ):
            errors.append("P0-B Phase 1 sealed lineage private/lane result mismatch")
    if not isinstance(locks, dict) or set(locks) != {"cost", "alpha", "unit", "publisher"}:
        errors.append("P0-B Phase 1 final lock receipt is not exact")
    elif locks.get("publisher") is not True or any(
        not isinstance(locks.get(name), dict)
        or set(locks[name]) != {"dev", "ino", "uid", "gid", "mode", "nlink"}
        or locks[name].get("nlink") != 1
        for name in ("cost", "alpha", "unit")
    ):
        errors.append("P0-B Phase 1 final lock identities are invalid")
    intent_binding = receipt.get("intent")
    if (
        not isinstance(intent_binding, dict)
        or set(intent_binding) != {"path", "sha256", "size"}
        or not Path(str(intent_binding.get("path", ""))).is_absolute()
        or not isinstance(intent_binding.get("size"), int)
        or intent_binding["size"] < 1
    ):
        errors.append("P0-B Phase 1 transaction intent binding is invalid")
    return errors


def validate_cutover_phase1_lineage(
    intent: dict[str, Any], runtime_bindings: dict[str, Any], *,
    authorization_validator: Callable[..., list[str]],
    runtime_bindings_validator: Callable[..., list[str]],
) -> list[str]:
    """Reopen and validate the exact Phase 1 PASS graph before cutover admission."""

    if intent.get("phase") != "cutover":
        return []
    errors: list[str] = []
    lineage = runtime_bindings.get("lineage")
    if not isinstance(lineage, dict):
        return ["P0-B cutover runtime bindings lack Phase 1 lineage"]
    try:
        bundle, _ = _read_binding(
            lineage.get("sealed_lineage_bundle"), label="sealed lineage bundle"
        )
        closure, _ = _read_binding(
            lineage.get("phase1_closure"), label="Phase 1 governance closure"
        )
        receipt, _ = _read_binding(
            lineage.get("phase1_receipt"), label="Phase 1 core receipt"
        )
    except (OSError, ValueError) as error:
        return [f"P0-B Phase 1 lineage unavailable: {error}"]

    errors.extend(_schema_errors(bundle, _bundle_schema(), label="sealed lineage bundle"))
    closure_schema = deepcopy(_closure_schema())
    closure_schema["properties"]["ops_postcheck"] = {"type": "object"}
    errors.extend(_schema_errors(closure, closure_schema, label="Phase 1 closure"))
    operation = closure.get("ops_postcheck")
    if isinstance(operation, dict):
        packet_schema = _packet_schema()
        errors.extend([
            f"P0-B Phase 1 OPS postcheck schema violation: {error}"
            for error in schema_subset_errors(
                operation, packet_schema["$defs"]["opsP0bPostcheck"], packet_schema
            )
        ])
    else:
        errors.append("P0-B Phase 1 closure lacks exact OPS postcheck")

    expected_lineage = {
        "phase1_effect_receipt": "phase1_receipt",
        "phase1_closure": "phase1_closure",
        "private_deps_receipt": "private_deps_receipt",
        "staged_board": "staged_board",
    }
    for bundle_field, lineage_field in expected_lineage.items():
        if bundle.get(bundle_field) != lineage.get(lineage_field):
            errors.append(f"P0-B sealed lineage {bundle_field} is not runtime-bound")
    expected_identity = {
        "intent_digest": intent.get("claim_bindings", {}).get("p0b_phase1_intent"),
        "task_contract_digest": intent.get("claim_bindings", {}).get("p0b_phase1_task_contract"),
        "compiled_route_digest": intent.get("claim_bindings", {}).get("p0b_phase1_route"),
        "context_artifact_digest": intent.get("claim_bindings", {}).get("p0b_phase1_context_artifact"),
    }
    for field, expected in expected_identity.items():
        if bundle.get(field) != expected or closure.get(field) != expected:
            errors.append(f"P0-B Phase 1 {field} is not exact cross-bound")
    if bundle.get("target_head") != intent.get("expected_source_head"):
        errors.append("P0-B Phase 1 target_head is not exact cross-bound")
    raw_claims = {
        "phase1_effect_receipt": (
            "p0b_phase1_receipt", "phase1_effect_receipt_digest"
        ),
        "phase1_closure": ("p0b_phase1_closure", "phase1_closure_digest"),
        "private_deps_receipt": ("p0b_private_bundle_receipt", None),
        "staged_board": ("p0b_staged_candidate_board", None),
    }
    claims = intent.get("claim_bindings", {})
    for bundle_field, (claim, direct) in raw_claims.items():
        expected = "sha256:" + str(bundle.get(bundle_field, {}).get("sha256", ""))
        if claims.get(claim) != expected:
            errors.append(f"P0-B Phase 1 {bundle_field} is not claim-bound")
        if direct is not None and intent.get(direct) != expected:
            errors.append(f"P0-B Phase 1 {bundle_field} is not authority-bound")
    bundle_raw_digest = "sha256:" + str(
        lineage.get("sealed_lineage_bundle", {}).get("sha256", "")
    )
    if (
        claims.get("p0b_sealed_lineage_bundle") != bundle_raw_digest
        or intent.get("sealed_lineage_bundle_digest") != bundle_raw_digest
        or bundle.get("bundle_digest") != _digest(_without(bundle, "bundle_digest"))
    ):
        errors.append("P0-B sealed lineage bundle digest is invalid")
    receipt_raw_digest = "sha256:" + str(
        lineage.get("phase1_receipt", {}).get("sha256", "")
    )
    closure_raw_digest = "sha256:" + str(
        lineage.get("phase1_closure", {}).get("sha256", "")
    )
    if (
        bundle.get("phase1_effect_receipt_digest") != receipt_raw_digest
        or closure.get("phase1_effect_receipt_digest") != receipt_raw_digest
        or bundle.get("phase1_closure_digest") != closure_raw_digest
        or closure.get("phase_result_digest") != _digest(receipt)
        or closure.get("closure_digest") != _digest(_without(closure, "closure_digest"))
    ):
        errors.append("P0-B Phase 1 receipt/closure digest graph is invalid")

    try:
        stage_authorization, _ = _read_binding(
            bundle.get("stage_authorization"), label="Phase 1 stage authorization"
        )
        stage_bindings, _ = _read_binding(
            bundle.get("stage_runtime_bindings"), label="Phase 1 runtime bindings"
        )
        private_receipt, _ = _read_binding(
            bundle.get("private_deps_receipt"), label="Phase 1 private receipt"
        )
        board, _ = _read_binding(bundle.get("staged_board"), label="Phase 1 staged board")
    except (OSError, ValueError) as error:
        return errors + [f"P0-B Phase 1 sealed artifact unavailable: {error}"]

    stage_intent = {
        **_without(stage_authorization, "authorization_digest"),
        "schema_version": "p0b_alr_rollforward_intent_v1",
    }
    errors.extend(
        f"P0-B historical stage authorization invalid: {error}"
        for error in authorization_validator(
            stage_authorization, now=str(stage_authorization.get("approved_at", ""))
        )
    )
    errors.extend(
        f"P0-B historical stage runtime bindings invalid: {error}"
        for error in runtime_bindings_validator(stage_bindings, intent=stage_intent)
    )
    if (
        stage_authorization.get("phase") != "stage"
        or stage_authorization.get("intent_id") != bundle.get("intent_id")
        or stage_authorization.get("intent_digest") != bundle.get("intent_digest")
        or stage_authorization.get("task_contract_digest")
        != bundle.get("task_contract_digest")
        or stage_authorization.get("context_artifact_digest")
        != bundle.get("context_artifact_digest")
        or stage_authorization.get("expected_source_head") != bundle.get("target_head")
        or stage_authorization.get("governance_bindings", {}).get(
            "compiled_route_digest"
        ) != bundle.get("compiled_route_digest")
        or stage_authorization.get("authorization_digest")
        != bundle.get("stage_authorization_digest")
        or closure.get("stage_authorization_digest")
        != bundle.get("stage_authorization_digest")
        or stage_bindings.get("artifact_digest")
        != bundle.get("stage_runtime_bindings_artifact_digest")
        or closure.get("stage_runtime_bindings_artifact_digest")
        != bundle.get("stage_runtime_bindings_artifact_digest")
    ):
        errors.append("P0-B Phase 1 authority/runtime lineage is not exact cross-bound")
    errors.extend(_validate_core_receipt(receipt, bundle, stage_authorization))
    errors.extend(_validate_private(
        private_receipt,
        destination=str(bundle.get("private_deps_destination", "")),
        manifest=str(bundle.get("private_deps_manifest_sha256", "")),
    ))
    errors.extend(_validate_board(board))

    if isinstance(operation, dict):
        expected_operation = {
            "schema_version": "ops_p0b_alr_postcheck_v1",
            "adapter_id": ADAPTER_ID,
            "phase": "stage",
            "intent_id": closure.get("intent_id"),
            "intent_digest": closure.get("intent_digest"),
            "task_contract_digest": closure.get("task_contract_digest"),
            "context_artifact_digest": closure.get("context_artifact_digest"),
            "compiled_route_digest": closure.get("compiled_route_digest"),
            "source_head": bundle.get("target_head"),
            "target_host": "trade-core",
            "target_user_unit": UNIT,
            "effect_receipt_digest": receipt_raw_digest,
            "phase_result_digest": _digest(receipt),
            "observer_receipt_digest": None,
            "verified": True,
        }
        for field, expected in expected_operation.items():
            if operation.get(field) != expected:
                errors.append(f"P0-B Phase 1 OPS postcheck {field} mismatch")
        if (
            operation.get("operation_digest") != _digest(
                _without(operation, "operation_digest")
            )
            or closure.get("ops_postcheck_digest") != operation.get("operation_digest")
        ):
            errors.append("P0-B Phase 1 OPS postcheck digest is invalid")
        try:
            completed = _time(receipt.get("completed_at_utc"), label="Phase 1 completion")
            observed = _time(operation.get("observed_at"), label="OPS postcheck observation")
            expires = _time(operation.get("expires_at"), label="OPS postcheck expiry")
            closed = _time(closure.get("closed_at_utc"), label="Phase 1 closure")
            if (
                not completed <= observed <= closed < expires
                or expires - observed > timedelta(minutes=15)
            ):
                errors.append("P0-B Phase 1 postcheck/closure time order is invalid")
        except (TypeError, ValueError):
            errors.append("P0-B Phase 1 postcheck/closure timestamps are invalid")
    return errors
