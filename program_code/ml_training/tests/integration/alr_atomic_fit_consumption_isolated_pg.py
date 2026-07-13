"""Explicit fixture-only disposable-PG16 probe for V160 atomic consumption.

Importing this module is inert.  Execution requires a disposable database name,
an exact CLI sentinel, and an environment acknowledgement.  The fixtures do
not attest a real host, contact an issuer/runner, or execute a model fit.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

_ROOT = Path(__file__).resolve().parents[4]
_PROGRAM_CODE = _ROOT / "program_code"
if str(_PROGRAM_CODE) not in sys.path:
    sys.path.insert(0, str(_PROGRAM_CODE))

from ml_training.tests.integration.alr_durable_fit_attestation_isolated_pg import (  # noqa: E402
    ProbeFailure,
    _NO_AUTHORITY,
    _TRAINER_CALLER,
    _ZERO_COUNTERS,
    _adapt,
    _apply_migration,
    _attestation_fixture,
    _canonical_pg_jsonb_bytes,
    _connect,
    _connect_as_role,
    _migration_bytes as _v159_migration_bytes,
    _parse_complete_dsn,
    _persist_qualified_receipt,
    _reject_ambient_libpq_routing,
    _required_env,
    _target_identity,
)

_V158 = (_ROOT / "sql/migrations/V158__alr_qualified_challenger_training.sql").resolve()
_V159 = (_ROOT / "sql/migrations/V159__alr_durable_fit_attestation.sql").resolve()
_V160 = (_ROOT / "sql/migrations/V160__alr_atomic_fit_consumption.sql").resolve()
_EXPECTED_SHA256 = {
    "V158": "7ed70599c6bd5f3cdb3376bc135a952d8c18f4ad62a62432c2bfdd8ee84e446b",
    "V159": "2e11d0ae0cbc2c1161a47d04bed4054c31b728e8cf945f931197f9b3455b7d74",
    "V160": "97024130f766443bd6396536ad135f33becb0b563c9e251c0b8c58799eb6e055",
}
_ACK_ENV = "ALR_V160_DISPOSABLE_ACK"
_ADMIN_DSN_ENV = "ALR_V160_DISPOSABLE_ADMIN_DSN"
_SENTINEL = "V160_ATOMIC_FIT_DISPOSABLE_MUTATION_CONFIRMED"
_SAFE_FAILURE_MESSAGE = "V160 atomic-fit disposable probe failed safely"
_DISPOSABLE_DATABASE = re.compile(r"(?:^|[_-])(ci|test|tmp|scratch|disposable)(?:[_-]|$)")
_CALLER = "alr_challenger_consumption_caller"
_COORDINATOR = "alr_challenger_consumption_coordinator"
_ACTIONS = (
    "REGISTER_REQUEST",
    "CLAIM_REQUEST",
    "RECORD_STATUS",
    "CONSUME_TERMINAL",
    "EXPIRE_UNCLAIMED",
    "MARK_RECONCILE_REQUIRED",
)
_RELATIONS = (
    "alr_challenger_consumption_requests",
    "alr_challenger_consumption_claims",
    "alr_challenger_consumption_statuses",
    "alr_challenger_consumption_verifier_evidence",
    "alr_challenger_consumption_terminals",
    "alr_challenger_consumption_reconciliation_audit",
)
_CLOSED_V159_FUNCTIONS = (
    "persist_alr_challenger_fit_attestation_v1",
    "persist_alr_challenger_training_result_v2",
    "read_alr_challenger_training_result_v2",
)
_CLOSED_ROLES = (
    "alr_challenger_writer",
    "alr_challenger_trainer_caller",
    "alr_challenger_fit_attestor",
    "alr_challenger_fit_attestor_caller",
    "trading_ai",
    "alr_shadow",
)
_NEGATIVE_MUTATIONS = ("missing", "extra", "wrong", "null", "foreign")
_REQUIRED_MARKERS = {
    "MIGRATION_REPLAY_STABLE",
    "REGISTER_EXACT_REPLAY",
    "CLAIM_BEFORE_FIT",
    "STATUS_MONOTONIC",
    "SUCCESS_BUNDLE_ATOMIC_1_1_3_1",
    "REJECTED_PRE_FIT_NO_V159",
    "FAILED_AFTER_START_RECONCILE_NO_V159",
    "EXPIRED_UNCLAIMED_NO_V159",
    "DIRECT_DML_AND_V159_WRAPPERS_CLOSED",
    "FIXED_READER_BYTE_READBACK",
    "NO_AUTHORITY_FALSE_ZERO",
    "DATABASE_RESIDENT_V157_SENTINEL",
    "CLOSED_ACTION_SCHEMA_MATRIX_6X5",
    "V159_WRAPPERS_ROLE_MATRIX_CLOSED",
    "COORDINATOR_EXECUTE_DELETION_FAIL_CLOSED",
    "INVALID_VERIFIER_FAIL_CLOSED",
    "FAILED_VERIFIER_FAIL_CLOSED",
    "TERMINAL_VERIFIER_PHASES_FAIL_CLOSED",
    "FIXED_READER_EXACT_LIFECYCLE_AND_V159",
    "NON_SUCCESS_TERMINAL_VERIFIER_EXACT",
    "FAILED_RECONCILIATION_EXACT",
    "NON_SUCCESS_FIXED_READER_NO_V159",
    "SCENARIO_SUITE_COMPLETE",
}


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ProbeFailure("invalid V160 probe arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(description="Run the explicit V160 disposable-PG16 probe")
    parser.add_argument("--confirm-disposable-v160", action="store_true")
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--disposable-sentinel", required=True)
    parser.add_argument("--v158", type=Path, default=_V158)
    parser.add_argument("--v159", type=Path, default=_V159)
    parser.add_argument("--v160", type=Path, default=_V160)
    return parser


def _h(label: str) -> str:
    return hashlib.sha256(f"alr-v160-fixture:{label}".encode("utf-8")).hexdigest()


def _migration_bytes(path: Path, version: str) -> tuple[bytes, str]:
    if version in {"V158", "V159"}:
        payload = _v159_migration_bytes(path, version)
    else:
        if version != "V160" or path.resolve() != _V160:
            raise ProbeFailure("V160 must be the canonical repository migration path")
        payload = path.resolve().read_bytes()
    observed = hashlib.sha256(payload).hexdigest()
    if observed != _EXPECTED_SHA256[version]:
        raise ProbeFailure(
            f"canonical {version} sha256 mismatch: expected "
            f"{_EXPECTED_SHA256[version]}, observed {observed}"
        )
    return payload, observed


def _assert_eight_roles(admin: Any) -> None:
    expected = {
        "alr_challenger_writer": (False, -1),
        "alr_challenger_trainer_caller": (True, 1),
        "alr_challenger_fit_attestor": (False, -1),
        "alr_challenger_fit_attestor_caller": (True, 1),
        _COORDINATOR: (False, -1),
        _CALLER: (True, 1),
        "trading_ai": (False, -1),
        "alr_shadow": (False, -1),
    }
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT rolname,rolcanlogin,rolconnlimit,rolsuper,rolcreatedb,"
            "rolcreaterole,rolinherit,rolreplication,rolbypassrls "
            "FROM pg_catalog.pg_roles WHERE rolname=ANY(%s) ORDER BY rolname",
            (list(expected),),
        )
        rows = cursor.fetchall()
        cursor.execute(
            "SELECT count(*) AS count FROM pg_catalog.pg_auth_members "
            "WHERE roleid IN(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=ANY(%s)) "
            "OR member IN(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=ANY(%s))",
            (list(expected), list(expected)),
        )
        memberships = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) AS count FROM unnest(%s::text[]) role_name "
            "WHERE pg_catalog.has_parameter_privilege(role_name,'session_replication_role','SET')",
            (list(expected),),
        )
        setters = cursor.fetchone()
    if len(rows) != 8 or memberships != {"count": 0} or setters != {"count": 0}:
        raise ProbeFailure("V160 exact eight-role fixture posture failed")
    for row in rows:
        can_login, connection_limit = expected[row["rolname"]]
        if row != {
            "rolname": row["rolname"],
            "rolcanlogin": can_login,
            "rolconnlimit": connection_limit,
            "rolsuper": False,
            "rolcreatedb": False,
            "rolcreaterole": False,
            "rolinherit": False,
            "rolreplication": False,
            "rolbypassrls": False,
        }:
            raise ProbeFailure("V160 role attributes drifted")


def _assert_v157_disposable_baseline(
    admin: Any,
    expected_target: Mapping[str, Any],
    expected_database: str,
) -> None:
    if _target_identity(admin) != dict(expected_target):
        raise ProbeFailure("V160 V157 baseline target identity drifted")
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT session_user,current_user,r.rolsuper,r.rolcanlogin,"
            "pg_catalog.pg_get_userbyid(d.datdba) AS database_owner "
            "FROM pg_catalog.pg_roles r JOIN pg_catalog.pg_database d "
            "ON d.datname=pg_catalog.current_database() "
            "WHERE r.rolname=current_user"
        )
        session = cursor.fetchone()
        cursor.execute(
            "SELECT max(version) AS highest_migration,count(*) AS migration_count,"
            "count(DISTINCT version) AS distinct_count,"
            "count(*) FILTER (WHERE version>157) AS post_v157_count,"
            "count(*) FILTER (WHERE success IS NOT TRUE) AS failed_count "
            "FROM public._sqlx_migrations"
        )
        ledger = cursor.fetchone()
        cursor.execute(
            "SELECT s.*,pg_catalog.pg_get_userbyid(c.relowner) AS relation_owner "
            "FROM public.alr_v160_disposable_probe_sentinel s "
            "JOIN pg_catalog.pg_class c ON c.oid="
            "'public.alr_v160_disposable_probe_sentinel'::regclass"
        )
        sentinels = cursor.fetchall()
    if session != {
        "session_user": session["current_user"] if session else None,
        "current_user": session["current_user"] if session else None,
        "rolsuper": True,
        "rolcanlogin": True,
        "database_owner": session["current_user"] if session else None,
    }:
        raise ProbeFailure("V160 baseline requires direct superuser database owner identity")
    if (
        not ledger
        or ledger["highest_migration"] != 157
        or not isinstance(ledger["migration_count"], int)
        or ledger["migration_count"] <= 0
        or ledger["distinct_count"] != ledger["migration_count"]
        or ledger["post_v157_count"] != 0
        or ledger["failed_count"] != 0
    ):
        raise ProbeFailure("V160 exact V157 migration ledger proof failed")
    if len(sentinels) != 1:
        raise ProbeFailure("V160 database-resident disposable sentinel cardinality failed")
    sentinel = dict(sentinels[0])
    expected_sentinel = {
        "sentinel_id": f"V160_V157_BASELINE_DISPOSABLE_CONFIRMED:{expected_database}",
        "database_name": expected_database,
        "database_oid": expected_target["database_oid"],
        "server_version_num": expected_target["server_version_num"],
        "postmaster_started_at": expected_target["postmaster_started_at"],
        "database_owner": session["current_user"],
        "baseline_session_user": session["current_user"],
        "baseline_current_user": session["current_user"],
        "highest_migration": 157,
        "migration_count": ledger["migration_count"],
        "expected_migration_count": ledger["migration_count"],
        "post_v157_count": 0,
        "relation_owner": session["current_user"],
    }
    observed = {key: sentinel.get(key) for key in expected_sentinel}
    if (
        sentinel.get("expected_migration_count") != ledger["migration_count"]
        or sentinel.get("migration_count") != ledger["distinct_count"]
        or observed != expected_sentinel
        or sentinel.get("created_at") is None
    ):
        raise ProbeFailure("V160 database-resident sentinel identity proof failed")


def _connect_as_consumption_caller(
    admin_parameters: Mapping[str, str], expected_target: Mapping[str, Any]
) -> Any:
    connection = _connect(admin_parameters)
    try:
        if _target_identity(connection) != dict(expected_target):
            raise ProbeFailure("V160 caller target differs from migration preflight")
        connection.rollback()
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION AUTHORIZATION alr_challenger_consumption_caller")
            cursor.execute("SET SESSION TimeZone='UTC'")
            cursor.execute("SET SESSION default_transaction_isolation='read committed'")
        connection.autocommit = False
        with connection.cursor() as cursor:
            cursor.execute("SELECT session_user,current_user,current_setting('TimeZone') AS timezone")
            identity = cursor.fetchone()
        if identity != {"session_user": _CALLER, "current_user": _CALLER, "timezone": "UTC"}:
            raise ProbeFailure("V160 caller session identity mismatch")
        return connection
    except Exception:
        connection.close()
        raise


def _call(connection: Any, action: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if action not in _ACTIONS:
        raise ProbeFailure("action is outside the fixed V160 coordinator surface")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT learning.coordinate_alr_challenger_consumption_v1(%s,%s::jsonb) AS result",
            (action, _adapt(payload)),
        )
        row = cursor.fetchone()
    if not row or not isinstance(row.get("result"), Mapping):
        raise ProbeFailure("V160 coordinator returned no JSON object")
    return dict(row["result"])


def _read(connection: Any, request_hash: str) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT learning.read_alr_challenger_consumption_v1(%s) AS result",
            (request_hash,),
        )
        row = cursor.fetchone()
    if not row or not isinstance(row.get("result"), Mapping):
        raise ProbeFailure("V160 reader returned no JSON object")
    return dict(row["result"])


def _jsonb_bytea(value: Any) -> bytes:
    if not isinstance(value, str) or not value.startswith("\\x"):
        raise ProbeFailure("V160 fixed reader returned a non-bytea JSON projection")
    try:
        return bytes.fromhex(value[2:])
    except ValueError as exc:
        raise ProbeFailure("V160 fixed reader returned malformed bytea hex") from exc


def _expect_p0001(connection: Any, action: str, payload: Mapping[str, Any]) -> None:
    import psycopg2  # type: ignore

    try:
        _call(connection, action, payload)
    except psycopg2.Error as exc:
        connection.rollback()
        if exc.pgcode != "P0001":
            raise ProbeFailure("V160 conflict did not fail with P0001") from exc
    else:
        connection.rollback()
        raise ProbeFailure("V160 divergent replay unexpectedly succeeded")


def _db_times(admin: Any, *, accept_seconds: float = 30.0) -> dict[str, str]:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT to_char((clock_timestamp()-interval '2 seconds') AT TIME ZONE 'UTC',"
            "'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS not_before,"
            "to_char((clock_timestamp()+(%s*interval '1 second')) AT TIME ZONE 'UTC',"
            "'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS accept_by,"
            "to_char((clock_timestamp()+interval '300 seconds') AT TIME ZONE 'UTC',"
            "'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS complete_by,"
            "to_char((clock_timestamp()-interval '1 second') AT TIME ZONE 'UTC',"
            "'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS verified_at",
            (accept_seconds,),
        )
        row = cursor.fetchone()
    if not row:
        raise ProbeFailure("V160 database clock fixture returned no row")
    return dict(row)


def _request_fixture(
    admin: Any, fixture: Mapping[str, Any], label: str, *, accept_seconds: float = 30.0
) -> dict[str, Any]:
    times = _db_times(admin, accept_seconds=accept_seconds)
    inner = fixture["attest"]["p_receipt_projection"]
    request_hash = _h(f"{label}:request")
    request = {
        "schema_version": "alr_trusted_fit_execution_request_v1",
        "request_hash": request_hash,
        "attempt_id": request_hash,
        "invocation_id": request_hash,
        "signed_payload": {
            "schema_version": "alr_trusted_fit_execution_request_v1",
            "signature_algorithm": "ed25519",
            "admission": {
                "durable_receipt_hash": fixture["qualified_receipt"]["p_durable_receipt_hash"],
                "training_key_hash": fixture["qualified_receipt"]["p_training_key_hash"],
            },
            "request_generation": 1,
            "issuer_id": inner["authentication"]["issuer_id"],
            "nonce_digest": _h(f"{label}:nonce"),
            "trust_policy_id": inner["authentication"]["trust_policy_id"],
            "trust_policy_snapshot_digest": _h(f"{label}:policy"),
            "runner_target_policy_hash": _h(f"{label}:runner-target"),
            "signing_key_id": inner["authentication"]["signature_key_id"],
            "not_before": times["not_before"],
            "accept_by": times["accept_by"],
            "complete_by": times["complete_by"],
        },
        "dispatch_allowed": False,
        "training_allowed": False,
        "persistence_allowed": False,
    }
    request_bytes, _digest = _canonical_pg_jsonb_bytes(admin, request)
    return {
        "projection": request,
        "bytes": request_bytes,
        "times": times,
        "terminal_verified_at": inner["verified_at"],
    }


def _verifier_fixture(
    admin: Any,
    request_bytes: bytes,
    phase: str,
    *,
    status_bytes: bytes | None = None,
    terminal_bytes: bytes | None = None,
    inner_bytes: bytes | None = None,
) -> tuple[dict[str, Any], bytes]:
    digest = lambda value: hashlib.sha256(value).hexdigest() if value is not None else None
    verifier = {
        "schema_version": "alr_fit_verifier_host_attestation_v1",
        "evidence_tier": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "declared_phase": phase,
        "capability_authenticity": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "coordinator_eligible": True,
        "semantic_phase_established": True,
        "canonical_input_bytes_established": True,
        "envelope_payload_binding_established": True,
        "policy_overlay_adjudication_established": True,
        "trusted_time_established": True,
        "signatures_valid": True,
        "request_envelope_sha256": digest(request_bytes),
        "signed_status_envelope_sha256": digest(status_bytes),
        "outer_terminal_envelope_sha256": digest(terminal_bytes),
        "v159_inner_envelope_sha256": digest(inner_bytes),
        "provider_evidence_digest_sha256": _h(f"{phase}:provider"),
        "host_attestation_digest_sha256": _h(f"{phase}:host"),
    }
    verifier_bytes, _ = _canonical_pg_jsonb_bytes(admin, verifier)
    return verifier, verifier_bytes


def _register_payload(admin: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    verifier, verifier_bytes = _verifier_fixture(admin, request["bytes"], "REQUEST_ONLY")
    return {
        "request_bytes_hex": request["bytes"].hex(),
        "request_projection": request["projection"],
        "verification_receipt_bytes_hex": verifier_bytes.hex(),
        "verification_receipt": verifier,
    }


def _claim_payload(admin: Any, request: Mapping[str, Any], label: str) -> dict[str, Any]:
    projection = {
        "schema_version": "alr_challenger_consumption_claim_v1",
        "request_hash": request["projection"]["request_hash"],
        "runner_identity_hash": _h(f"{label}:runner"),
        "claim_token_hash": _h(f"{label}:claim"),
    }
    event_bytes, _ = _canonical_pg_jsonb_bytes(admin, projection)
    verifier, verifier_bytes = _verifier_fixture(admin, request["bytes"], "REQUEST_ONLY")
    return {
        "request_hash": request["projection"]["request_hash"],
        "claim_bytes_hex": event_bytes.hex(),
        "claim_projection": projection,
        "verification_receipt_bytes_hex": verifier_bytes.hex(),
        "verification_receipt": verifier,
    }


def _status_payload(admin: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    projection = {
        "schema_version": "alr_isolated_fit_execution_receipt_v1",
        "response_kind": "STATUS",
        "outcome": "ACCEPTED_IN_PROGRESS",
        "signed_payload": {
            "request_hash": request["projection"]["request_hash"],
            "request_generation": 1,
            "status_generation": 1,
            "status_issued_at": request["terminal_verified_at"],
            "status_expires_at": request["times"]["complete_by"],
            "stage_observations": {
                "request_accepted": True,
                "actual_inputs_consumed": False,
                "fit_started": False,
            },
        },
    }
    event_bytes, _ = _canonical_pg_jsonb_bytes(admin, projection)
    verifier, verifier_bytes = _verifier_fixture(
        admin, request["bytes"], "SIGNED_STATUS", status_bytes=event_bytes
    )
    return {
        "request_hash": request["projection"]["request_hash"],
        "response_bytes_hex": event_bytes.hex(),
        "response_projection": projection,
        "verification_receipt_bytes_hex": verifier_bytes.hex(),
        "verification_receipt": verifier,
    }


def _terminal_payload(
    admin: Any,
    request: Mapping[str, Any],
    fixture: Mapping[str, Any],
    outcome: str,
) -> dict[str, Any]:
    inner = fixture["attest"]["p_receipt_projection"]
    signed = {
        "request_hash": request["projection"]["request_hash"],
        "request_generation": 1,
        "nonce_digest": request["projection"]["signed_payload"]["nonce_digest"],
        "issuer_id": request["projection"]["signed_payload"]["issuer_id"],
        "trust_policy_id": request["projection"]["signed_payload"]["trust_policy_id"],
        "trust_policy_snapshot_digest": request["projection"]["signed_payload"]["trust_policy_snapshot_digest"],
        "runner_target_policy_hash": request["projection"]["signed_payload"]["runner_target_policy_hash"],
        "signature_algorithm": "ed25519",
        "issuer_verified_at": inner["verified_at"],
        "no_authority": deepcopy(_NO_AUTHORITY),
        "authority_counters": deepcopy(_ZERO_COUNTERS),
        "stage_observations": {
            "request_accepted": True,
            "actual_inputs_consumed": outcome in {"SUCCEEDED", "FAILED_AFTER_START"},
            "fit_started": outcome in {"SUCCEEDED", "FAILED_AFTER_START"},
            "fit_completed": outcome == "SUCCEEDED",
            "artifacts_written": outcome == "SUCCEEDED",
            "artifact_readback_completed": outcome == "SUCCEEDED",
            "onnx_semantic_validation_completed": outcome == "SUCCEEDED",
        },
    }
    inner_bytes: bytes | None = None
    if outcome == "SUCCEEDED":
        inner_bytes = fixture["attest"]["p_signed_receipt_bytes"]
        signed.update(
            {
                "receipt_expires_at": inner["expires_at"],
                "signing_key_id": inner["authentication"]["signature_key_id"],
                "inner_receipt_bytes_base64url": base64.urlsafe_b64encode(inner_bytes).decode("ascii").rstrip("="),
                "inner_receipt_digest_sha256": hashlib.sha256(inner_bytes).hexdigest(),
                "v159_subject": deepcopy(inner["subject"]),
                "v159_claims": deepcopy(inner["claims"]),
                "result_observation": deepcopy(inner["result_observation"]),
                "actual_input_material_set_hash": inner["subject"]["actual_input_material_set_hash"],
                "ordered_artifact_set_hash": inner["subject"]["ordered_artifact_set_hash"],
                "fit_started_at": inner["result_observation"]["fit_started_at"],
                "fit_completed_at": inner["result_observation"]["fit_completed_at"],
            }
        )
    projection = {
        "schema_version": "alr_isolated_fit_execution_receipt_v1",
        "response_kind": "TERMINAL",
        "outcome": outcome,
        "signed_payload": signed,
    }
    event_bytes, _ = _canonical_pg_jsonb_bytes(admin, projection)
    phase = "TERMINAL_SUCCESS" if outcome == "SUCCEEDED" else "TERMINAL_NO_INNER"
    verifier, verifier_bytes = _verifier_fixture(
        admin,
        request["bytes"],
        phase,
        terminal_bytes=event_bytes,
        inner_bytes=inner_bytes,
    )
    return {
        "request_hash": request["projection"]["request_hash"],
        "response_bytes_hex": event_bytes.hex(),
        "response_projection": projection,
        "inner_receipt_bytes_hex": inner_bytes.hex() if inner_bytes is not None else None,
        "verification_receipt_bytes_hex": verifier_bytes.hex(),
        "verification_receipt": verifier,
    }


def _reconcile_payload(admin: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    signed_status = _status_payload(admin, request)
    return {
        "request_hash": request["projection"]["request_hash"],
        "event_bytes_hex": signed_status["response_bytes_hex"],
        "event_projection": signed_status["response_projection"],
        "verification_receipt_bytes_hex": signed_status[
            "verification_receipt_bytes_hex"
        ],
        "verification_receipt": signed_status["verification_receipt"],
    }


def _state_digest(admin: Any) -> str:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT md5(jsonb_build_object("
            "'requests',COALESCE((SELECT jsonb_agg(to_jsonb(r) ORDER BY r.request_hash) FROM learning.alr_challenger_consumption_requests r),'[]'::jsonb),"
            "'claims',COALESCE((SELECT jsonb_agg(to_jsonb(c) ORDER BY c.request_hash) FROM learning.alr_challenger_consumption_claims c),'[]'::jsonb),"
            "'statuses',COALESCE((SELECT jsonb_agg(to_jsonb(s) ORDER BY s.request_hash,s.status_generation) FROM learning.alr_challenger_consumption_statuses s),'[]'::jsonb),"
            "'verifier',COALESCE((SELECT jsonb_agg(to_jsonb(v) ORDER BY v.request_hash,v.action,v.verifier_receipt_hash) FROM learning.alr_challenger_consumption_verifier_evidence v),'[]'::jsonb),"
            "'terminals',COALESCE((SELECT jsonb_agg(to_jsonb(t) ORDER BY t.request_hash) FROM learning.alr_challenger_consumption_terminals t),'[]'::jsonb),"
            "'reconciliation',COALESCE((SELECT jsonb_agg(to_jsonb(a) ORDER BY a.reconciliation_hash) FROM learning.alr_challenger_consumption_reconciliation_audit a),'[]'::jsonb),"
            "'attestations',COALESCE((SELECT jsonb_agg(to_jsonb(a) ORDER BY a.durable_attestation_hash) FROM learning.alr_challenger_fit_attestations a),'[]'::jsonb),"
            "'runs',COALESCE((SELECT jsonb_agg(to_jsonb(r) ORDER BY r.training_run_hash) FROM learning.alr_challenger_training_runs r),'[]'::jsonb),"
            "'artifacts',COALESCE((SELECT jsonb_agg(to_jsonb(m) ORDER BY m.artifact_hash) FROM learning.alr_challenger_model_artifacts m),'[]'::jsonb),"
            "'registry',COALESCE((SELECT jsonb_agg(to_jsonb(g) ORDER BY g.challenger_hash) FROM learning.alr_challenger_registry g),'[]'::jsonb)"
            ")::text) AS digest"
        )
        row = cursor.fetchone()
    if not row or not isinstance(row.get("digest"), str):
        raise ProbeFailure("V160 durable state digest returned no value")
    return row["digest"]


def _expect_action_failure(
    caller: Any, action: str, payload: Mapping[str, Any]
) -> None:
    import psycopg2  # type: ignore

    try:
        _call(caller, action, payload)
    except psycopg2.Error:
        caller.rollback()
        return
    caller.rollback()
    raise ProbeFailure(f"V160 invalid {action} payload unexpectedly succeeded")


def _assert_closed_action_schemas(
    admin: Any,
    caller: Any,
    requests: Mapping[str, Mapping[str, Any]],
    fixtures: Mapping[str, Mapping[str, Any]],
    markers: set[str],
) -> None:
    register_request = requests["locks"]
    claim_request = requests["claim_expire"]
    status_request = requests["status_race"]
    terminal_request = requests["terminal_success"]
    expire_request = requests["success_conflict"]
    reconcile_request = requests["artifact_race"]
    for request in (
        claim_request,
        status_request,
        terminal_request,
        expire_request,
        reconcile_request,
    ):
        result = _call(caller, "REGISTER_REQUEST", _register_payload(admin, request))
        caller.commit()
        if result.get("status") != "PERSISTED":
            raise ProbeFailure("V160 closed-schema precondition register failed")
    for request, label in (
        (status_request, "schema-status"),
        (terminal_request, "schema-terminal"),
    ):
        result = _call(caller, "CLAIM_REQUEST", _claim_payload(admin, request, label))
        caller.commit()
        if result.get("status") != "PERSISTED":
            raise ProbeFailure("V160 closed-schema precondition claim failed")

    bases: dict[str, dict[str, Any]] = {
        "REGISTER_REQUEST": _register_payload(admin, register_request),
        "CLAIM_REQUEST": _claim_payload(admin, claim_request, "schema-claim"),
        "RECORD_STATUS": _status_payload(admin, status_request),
        "CONSUME_TERMINAL": _terminal_payload(
            admin, terminal_request, fixtures["terminal_success"], "REJECTED_PRE_FIT"
        ),
        "EXPIRE_UNCLAIMED": {
            "request_hash": expire_request["projection"]["request_hash"],
            "reason": "ACCEPT_WINDOW_ELAPSED",
        },
        "MARK_RECONCILE_REQUIRED": _reconcile_payload(admin, reconcile_request),
    }
    wrong_keys = {
        "REGISTER_REQUEST": "request_bytes_hex",
        "CLAIM_REQUEST": "claim_projection",
        "RECORD_STATUS": "response_projection",
        "CONSUME_TERMINAL": "response_projection",
        "EXPIRE_UNCLAIMED": "reason",
        "MARK_RECONCILE_REQUIRED": "event_projection",
    }
    actions = list(_ACTIONS)
    for index, action in enumerate(actions):
        base = bases[action]
        foreign = bases[actions[(index + 1) % len(actions)]]
        key = wrong_keys[action]
        mutations: dict[str, dict[str, Any]] = {}
        missing = deepcopy(base)
        missing.pop(key)
        mutations["missing"] = missing
        extra = deepcopy(base)
        extra["unexpected_field"] = "forbidden"
        mutations["extra"] = extra
        wrong = deepcopy(base)
        wrong[key] = [] if key != "reason" else 7
        mutations["wrong"] = wrong
        null = deepcopy(base)
        null[key] = None
        mutations["null"] = null
        mutations["foreign"] = deepcopy(foreign)
        if tuple(mutations) != _NEGATIVE_MUTATIONS:
            raise ProbeFailure("V160 closed-schema mutation inventory drifted")
        for mutation_name, mutated in mutations.items():
            before = _state_digest(admin)
            _expect_action_failure(caller, action, mutated)
            after = _state_digest(admin)
            if after != before:
                raise ProbeFailure(
                    f"V160 {action} {mutation_name} mutation changed durable state"
                )
    markers.add("CLOSED_ACTION_SCHEMA_MATRIX_6X5")


def _assert_verifier_fail_closed(
    admin: Any,
    caller: Any,
    request: Mapping[str, Any],
    markers: set[str],
) -> None:
    base = _register_payload(admin, request)
    cases = (
        ("INVALID_VERIFIER_FAIL_CLOSED", "invalid"),
        ("FAILED_VERIFIER_FAIL_CLOSED", "failed"),
    )
    for marker, case in cases:
        payload = deepcopy(base)
        verifier = deepcopy(payload["verification_receipt"])
        if case == "invalid":
            verifier.pop("schema_version")
        else:
            verifier["signatures_valid"] = False
            verifier["coordinator_eligible"] = False
        verifier_bytes, _ = _canonical_pg_jsonb_bytes(admin, verifier)
        payload["verification_receipt"] = verifier
        payload["verification_receipt_bytes_hex"] = verifier_bytes.hex()
        before = _state_digest(admin)
        _expect_action_failure(caller, "REGISTER_REQUEST", payload)
        if _state_digest(admin) != before:
            raise ProbeFailure("V160 invalid/failed verifier changed durable state")
        markers.add(marker)


def _assert_terminal_verifiers_fail_closed(
    admin: Any,
    caller: Any,
    request: Mapping[str, Any],
    fixture: Mapping[str, Any],
    markers: set[str],
) -> None:
    register = _call(caller, "REGISTER_REQUEST", _register_payload(admin, request))
    caller.commit()
    claim = _call(caller, "CLAIM_REQUEST", _claim_payload(admin, request, "verifier"))
    caller.commit()
    if register.get("status") != "PERSISTED" or claim.get("status") != "PERSISTED":
        raise ProbeFailure("V160 terminal-verifier precondition did not persist")
    baseline = _state_digest(admin)
    for outcome, expected_phase in (
        ("REJECTED_PRE_FIT", "TERMINAL_NO_INNER"),
        ("SUCCEEDED", "TERMINAL_SUCCESS"),
    ):
        base = _terminal_payload(admin, request, fixture, outcome)
        if base["verification_receipt"].get("declared_phase") != expected_phase:
            raise ProbeFailure("V160 terminal-verifier phase fixture drifted")
        for case in ("invalid", "failed"):
            payload = deepcopy(base)
            verifier = deepcopy(payload["verification_receipt"])
            if case == "invalid":
                verifier.pop("schema_version")
            else:
                verifier["signatures_valid"] = False
                verifier["coordinator_eligible"] = False
            verifier_bytes, _ = _canonical_pg_jsonb_bytes(admin, verifier)
            payload["verification_receipt"] = verifier
            payload["verification_receipt_bytes_hex"] = verifier_bytes.hex()
            _expect_action_failure(caller, "CONSUME_TERMINAL", payload)
            if _state_digest(admin) != baseline:
                raise ProbeFailure(
                    "V160 invalid/failed terminal verifier changed durable state"
                )
    markers.add("TERMINAL_VERIFIER_PHASES_FAIL_CLOSED")


def _closed_v159_statements() -> dict[str, str]:
    return {
        "persist_alr_challenger_fit_attestation_v1": (
            "SELECT learning.persist_alr_challenger_fit_attestation_v1("
            "NULL::bytea,NULL::jsonb,"
            + ",".join(["NULL::text"] * 14)
            + ",NULL::timestamptz,NULL::timestamptz)"
        ),
        "persist_alr_challenger_training_result_v2": (
            "SELECT learning.persist_alr_challenger_training_result_v2("
            + ",".join(["NULL::text"] * 10)
            + ",NULL::integer,NULL::text,NULL::text,"
            "NULL::timestamptz,NULL::timestamptz,"
            "NULL::text,NULL::bigint,NULL::text,NULL::bigint,"
            "NULL::text,NULL::bigint)"
        ),
        "read_alr_challenger_training_result_v2": (
            "SELECT learning.read_alr_challenger_training_result_v2("
            "NULL::text,NULL::text)"
        ),
    }


def _expect_statement_error(
    connection: Any,
    statement: str,
    sqlstate: str,
    message: str | None = None,
) -> None:
    import psycopg2  # type: ignore

    try:
        with connection.cursor() as cursor:
            cursor.execute(statement)
    except psycopg2.Error as exc:
        connection.rollback()
        primary = getattr(exc.diag, "message_primary", None)
        if exc.pgcode != sqlstate or (message is not None and primary != message):
            raise ProbeFailure(
                f"V160 closure returned ({exc.pgcode},{primary!r}); "
                f"expected ({sqlstate},{message!r})"
            ) from exc
        return
    connection.rollback()
    raise ProbeFailure("V160 closed statement unexpectedly executed")


def _assert_v159_application_closure(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    caller: Any,
    admin: Any,
    markers: set[str],
) -> None:
    statements = _closed_v159_statements()
    owner_failures = {
        (
            "alr_challenger_fit_attestor",
            "persist_alr_challenger_fit_attestation_v1",
        ): "V160 closed V159 attestation wrapper: atomic coordinator required",
        (
            "alr_challenger_writer",
            "persist_alr_challenger_training_result_v2",
        ): "V160 closed V159 result wrapper: atomic coordinator required",
        (
            "alr_challenger_writer",
            "read_alr_challenger_training_result_v2",
        ): "V160 closed V159 result reader: fixed consumption read required",
    }
    sessions: list[tuple[str, Any, bool]] = [(_CALLER, caller, False)]
    for role in _CLOSED_ROLES:
        sessions.append(
            (
                role,
                _connect_as_role(
                    admin_parameters,
                    expected_target,
                    role,
                    destructive_ack=True,
                ),
                True,
            )
        )
    try:
        for role, connection, _owned in sessions:
            _expect_statement_error(
                connection,
                "SELECT * FROM learning.alr_challenger_training_runs LIMIT 0",
                "42501",
            )
            for function_name, statement in statements.items():
                hard_failure = owner_failures.get((role, function_name))
                _expect_statement_error(
                    connection,
                    statement,
                    "P0001" if hard_failure else "42501",
                    hard_failure,
                )
    finally:
        for _role, connection, owned in sessions:
            if owned:
                connection.close()
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) AS count FROM pg_catalog.pg_proc p "
            "CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE("
            "p.proacl,pg_catalog.acldefault('f',p.proowner))) privilege "
            "WHERE p.oid=ANY(ARRAY["
            "'learning.persist_alr_challenger_fit_attestation_v1(bytea,jsonb,text,text,text,text,text,text,text,text,text,text,text,text,text,text,timestamp with time zone,timestamp with time zone)'::regprocedure,"
            "'learning.persist_alr_challenger_training_result_v2(text,text,text,text,text,text,text,text,text,text,integer,text,text,timestamp with time zone,timestamp with time zone,text,bigint,text,bigint,text,bigint)'::regprocedure,"
            "'learning.read_alr_challenger_training_result_v2(text,text)'::regprocedure]) "
            "AND privilege.grantee=0 AND privilege.privilege_type='EXECUTE'"
        )
        public_execute = cursor.fetchone()
    if public_execute != {"count": 0}:
        raise ProbeFailure("PUBLIC retains V159 application wrapper execution")
    markers.add("V159_WRAPPERS_ROLE_MATRIX_CLOSED")


def _assert_coordinator_execute_deletion(
    admin: Any,
    caller: Any,
    duplicate_register_payload: Mapping[str, Any],
    markers: set[str],
) -> None:
    before = _state_digest(admin)
    with admin.cursor() as cursor:
        cursor.execute(
            "REVOKE EXECUTE ON FUNCTION "
            "learning.coordinate_alr_challenger_consumption_v1(TEXT,JSONB) "
            "FROM alr_challenger_consumption_caller"
        )
    admin.commit()
    try:
        _expect_statement_error(
            caller,
            "SELECT learning.coordinate_alr_challenger_consumption_v1("
            "'REGISTER_REQUEST','{}'::jsonb)",
            "42501",
        )
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "GRANT EXECUTE ON FUNCTION "
                "learning.coordinate_alr_challenger_consumption_v1(TEXT,JSONB) "
                "TO alr_challenger_consumption_caller"
            )
        admin.commit()
    replay = _call(caller, "REGISTER_REQUEST", duplicate_register_payload)
    caller.commit()
    if replay.get("status") != "DUPLICATE" or _state_digest(admin) != before:
        raise ProbeFailure("V160 coordinator EXECUTE restore changed durable state")
    markers.add("COORDINATOR_EXECUTE_DELETION_FAIL_CLOSED")


def _assert_bytes_and_hash(
    row: Mapping[str, Any],
    bytes_field: str,
    hash_field: str,
    expected_bytes: bytes,
) -> None:
    if _jsonb_bytea(row.get(bytes_field)) != expected_bytes:
        raise ProbeFailure(f"V160 fixed reader byte mismatch: {bytes_field}")
    if row.get(hash_field) != hashlib.sha256(expected_bytes).hexdigest():
        raise ProbeFailure(f"V160 fixed reader hash mismatch: {hash_field}")


def _assert_request_readback(
    request_row: Mapping[str, Any],
    request: Mapping[str, Any],
    register: Mapping[str, Any],
) -> None:
    if (
        request_row.get("request_projection") != request["projection"]
        or _jsonb_bytea(request_row.get("request_bytes")) != request["bytes"]
        or request_row.get("request_hash") != request["projection"]["request_hash"]
        or request_row.get("verification_receipt")
        != register["verification_receipt"]
    ):
        raise ProbeFailure("V160 fixed reader request byte/projection identity drifted")
    _assert_bytes_and_hash(
        request_row,
        "verification_receipt_bytes",
        "verification_receipt_hash",
        bytes.fromhex(register["verification_receipt_bytes_hex"]),
    )


def _assert_claim_readback(
    claim_row: Mapping[str, Any], claim: Mapping[str, Any]
) -> None:
    if (
        claim_row.get("claim_projection") != claim["claim_projection"]
        or _jsonb_bytea(claim_row.get("claim_bytes"))
        != bytes.fromhex(claim["claim_bytes_hex"])
        or claim_row.get("verification_receipt")
        != claim["verification_receipt"]
    ):
        raise ProbeFailure("V160 fixed reader claim byte/projection drifted")
    _assert_bytes_and_hash(
        claim_row,
        "verification_receipt_bytes",
        "verification_receipt_hash",
        bytes.fromhex(claim["verification_receipt_bytes_hex"]),
    )


def _assert_verifier_evidence(
    readback: Mapping[str, Any],
    expected: Mapping[str, tuple[str, Mapping[str, Any]]],
) -> None:
    rows = readback.get("verifier_evidence")
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ProbeFailure("V160 fixed reader verifier evidence cardinality drifted")
    by_action = {row.get("action"): row for row in rows if isinstance(row, Mapping)}
    if set(by_action) != set(expected):
        raise ProbeFailure("V160 fixed reader verifier action inventory drifted")
    for action, (phase, payload) in expected.items():
        row = by_action[action]
        verifier_bytes = bytes.fromhex(payload["verification_receipt_bytes_hex"])
        if (
            row.get("declared_phase") != phase
            or row.get("verification_receipt") != payload["verification_receipt"]
        ):
            raise ProbeFailure("V160 fixed reader verifier projection drifted")
        _assert_bytes_and_hash(
            row,
            "verification_receipt_bytes",
            "verifier_receipt_hash",
            verifier_bytes,
        )


def _assert_exact_success_readback(
    readback: Mapping[str, Any],
    request: Mapping[str, Any],
    register: Mapping[str, Any],
    claim: Mapping[str, Any],
    status: Mapping[str, Any],
    terminal: Mapping[str, Any],
    fixture: Mapping[str, Any],
    terminal_result: Mapping[str, Any],
    markers: set[str],
) -> None:
    if readback.get("status") != "FOUND":
        raise ProbeFailure("V160 success fixed reader returned NOT_FOUND")
    request_row = readback.get("request")
    claim_row = readback.get("claim")
    statuses = readback.get("statuses")
    terminal_row = readback.get("terminal")
    if not all(isinstance(value, Mapping) for value in (request_row, claim_row, terminal_row)):
        raise ProbeFailure("V160 success fixed reader lifecycle row is missing")
    if not isinstance(statuses, list) or len(statuses) != 1:
        raise ProbeFailure("V160 success fixed reader status cardinality drifted")
    status_row = statuses[0]
    _assert_request_readback(request_row, request, register)
    _assert_claim_readback(claim_row, claim)

    status_bytes = bytes.fromhex(status["response_bytes_hex"])
    if status_row.get("response_projection") != status["response_projection"]:
        raise ProbeFailure("V160 fixed reader status projection drifted")
    _assert_bytes_and_hash(status_row, "response_bytes", "response_hash", status_bytes)
    status_verifier = bytes.fromhex(status["verification_receipt_bytes_hex"])
    _assert_bytes_and_hash(
        status_row,
        "verification_receipt_bytes",
        "verification_receipt_hash",
        status_verifier,
    )
    if status_row.get("verification_receipt") != status["verification_receipt"]:
        raise ProbeFailure("V160 status verifier projection drifted")

    terminal_bytes = bytes.fromhex(terminal["response_bytes_hex"])
    if (
        terminal_row.get("terminal_projection") != terminal["response_projection"]
        or terminal_row.get("outcome") != "SUCCEEDED"
    ):
        raise ProbeFailure("V160 fixed reader terminal projection drifted")
    _assert_bytes_and_hash(
        terminal_row, "terminal_bytes", "terminal_hash", terminal_bytes
    )
    if _jsonb_bytea(terminal_row.get("inner_receipt_bytes")) != fixture["attest"][
        "p_signed_receipt_bytes"
    ]:
        raise ProbeFailure("V160 fixed reader inner receipt bytes drifted")
    terminal_verifier = bytes.fromhex(terminal["verification_receipt_bytes_hex"])
    _assert_bytes_and_hash(
        terminal_row,
        "verification_receipt_bytes",
        "verification_receipt_hash",
        terminal_verifier,
    )
    if terminal_row.get("verification_receipt") != terminal["verification_receipt"]:
        raise ProbeFailure("V160 terminal verifier projection drifted")
    _assert_verifier_evidence(
        readback,
        {
            "REGISTER_REQUEST": ("REQUEST_ONLY", register),
            "CLAIM_REQUEST": ("REQUEST_ONLY", claim),
            "RECORD_STATUS": ("SIGNED_STATUS", status),
            "CONSUME_TERMINAL": ("TERMINAL_SUCCESS", terminal),
        },
    )

    bundle = readback.get("v159_bundle")
    if not isinstance(bundle, Mapping):
        raise ProbeFailure("V160 fixed reader V159 bundle is missing")
    attestation = bundle.get("attestation")
    run = bundle.get("training_run")
    artifacts = bundle.get("artifacts")
    registry = bundle.get("registry")
    if not all(isinstance(value, Mapping) for value in (attestation, run, registry)):
        raise ProbeFailure("V160 fixed reader V159 singleton bundle is incomplete")
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        raise ProbeFailure("V160 fixed reader V159 artifact trio is incomplete")
    inner = fixture["attest"]["p_receipt_projection"]
    subject = inner["subject"]
    observation = inner["result_observation"]
    inner_bytes = fixture["attest"]["p_signed_receipt_bytes"]
    if (
        _jsonb_bytea(attestation.get("signed_receipt_bytes")) != inner_bytes
        or attestation.get("receipt_projection") != inner
        or attestation.get("external_receipt_digest")
        != hashlib.sha256(inner_bytes).hexdigest()
        or attestation.get("durable_attestation_hash")
        != terminal_result.get("durable_attestation_hash")
        or attestation.get("durable_receipt_hash") != subject["durable_receipt_hash"]
        or attestation.get("training_key_hash") != subject["training_key_hash"]
        or attestation.get("structural_result_hash")
        != subject["result_hash"]
        or attestation.get("structural_fit_capture_hash")
        != subject["fit_capture_hash"]
        or attestation.get("structural_candidate_hash")
        != subject["candidate_attestation_hash"]
        or attestation.get("structural_training_run_hash")
        != subject["training_run_hash"]
        or attestation.get("structural_challenger_hash")
        != subject["challenger_hash"]
        or attestation.get("actual_input_material_set_hash")
        != subject["actual_input_material_set_hash"]
        or attestation.get("ordered_artifact_set_hash")
        != subject["ordered_artifact_set_hash"]
        or attestation.get("no_authority") != _NO_AUTHORITY
        or attestation.get("authority_counters") != _ZERO_COUNTERS
    ):
        raise ProbeFailure("V160 fixed reader V159 attestation/hash bundle drifted")
    if (
        run.get("training_run_hash") != subject["training_run_hash"]
        or run.get("durable_receipt_hash") != subject["durable_receipt_hash"]
        or run.get("training_key_hash") != subject["training_key_hash"]
        or run.get("durable_training_run_hash")
        != terminal_result.get("durable_training_run_hash")
        or run.get("durable_attestation_hash")
        != terminal_result.get("durable_attestation_hash")
        or run.get("run_status") != "TRAINING_PERFORMED"
        or run.get("model_training_performed") is not True
        or run.get("model_artifact_set_hash")
        != subject["ordered_artifact_set_hash"]
        or run.get("source_head") != observation["source_head"]
        or run.get("actual_dataset_hash")
        != observation["actual_inputs"]["dataset_hash"]
        or run.get("actual_row_ids_hash")
        != observation["actual_inputs"]["row_ids_hash"]
        or run.get("actual_split_hash")
        != observation["actual_inputs"]["split_hash"]
        or run.get("actual_code_manifest_hash")
        != observation["actual_inputs"]["code_manifest_hash"]
        or run.get("actual_training_config_hash")
        != observation["actual_inputs"]["training_config_hash"]
        or run.get("actual_feature_schema_hash")
        != observation["actual_inputs"]["feature_schema_hash"]
        or run.get("actual_label_schema_hash")
        != observation["actual_inputs"]["label_schema_hash"]
        or run.get("no_authority") != _NO_AUTHORITY
        or run.get("authority_counters") != _ZERO_COUNTERS
    ):
        raise ProbeFailure("V160 fixed reader V159 run/hash bundle drifted")
    artifact_by_quantile = {
        artifact.get("quantile"): artifact
        for artifact in artifacts
        if isinstance(artifact, Mapping)
    }
    if set(artifact_by_quantile) != {"q10", "q50", "q90"}:
        raise ProbeFailure("V160 fixed reader artifact quantiles drifted")
    for quantile in ("q10", "q50", "q90"):
        artifact = artifact_by_quantile[quantile]
        expected_artifact = observation["artifacts"][quantile]
        if (
            artifact.get("artifact_hash") != expected_artifact["artifact_hash"]
            or artifact.get("training_run_hash") != subject["training_run_hash"]
            or artifact.get("training_key_hash") != subject["training_key_hash"]
            or artifact.get("artifact_size_bytes")
            != expected_artifact["artifact_size_bytes"]
            or artifact.get("model_artifact_set_hash")
            != subject["ordered_artifact_set_hash"]
            or artifact.get("artifact_path")
            != f"runs/structural/{subject['training_run_hash']}/{quantile}.onnx"
            or artifact.get("artifact_format") != "onnx"
            or artifact.get("feature_schema_hash")
            != observation["actual_inputs"]["feature_schema_hash"]
            or artifact.get("model_schema_version")
            != observation["model"]["model_schema_version"]
            or artifact.get("durable_attestation_hash")
            != terminal_result.get("durable_attestation_hash")
            or artifact.get("durable_training_run_hash")
            != terminal_result.get("durable_training_run_hash")
            or artifact.get("symlink_created") is not False
            or artifact.get("serving_visible") is not False
        ):
            raise ProbeFailure("V160 fixed reader artifact/hash bundle drifted")
    if (
        registry.get("challenger_hash") != subject["challenger_hash"]
        or registry.get("training_run_hash") != subject["training_run_hash"]
        or registry.get("training_key_hash") != subject["training_key_hash"]
        or registry.get("model_artifact_set_hash")
        != subject["ordered_artifact_set_hash"]
        or registry.get("durable_challenger_hash")
        != terminal_result.get("durable_challenger_hash")
        or registry.get("durable_attestation_hash")
        != terminal_result.get("durable_attestation_hash")
        or registry.get("durable_training_run_hash")
        != terminal_result.get("durable_training_run_hash")
        or registry.get("registry_status") != "NOT_SERVING"
        or registry.get("serving_allowed") is not False
        or registry.get("promotion_allowed") is not False
        or registry.get("latest_pointer_allowed") is not False
        or registry.get("symlink_allowed") is not False
        or registry.get("attestation_bound_at") != run.get("attestation_bound_at")
    ):
        raise ProbeFailure("V160 fixed reader registry/hash bundle drifted")
    markers.add("FIXED_READER_EXACT_LIFECYCLE_AND_V159")


def _assert_exact_reconciliation_readback(
    readback: Mapping[str, Any],
    request: Mapping[str, Any],
    register: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
) -> None:
    request_row = readback.get("request")
    audits = readback.get("reconciliation_audit")
    if (
        readback.get("status") != "FOUND"
        or not isinstance(request_row, Mapping)
        or not isinstance(audits, list)
        or len(audits) != 1
        or readback.get("terminal") is not None
    ):
        raise ProbeFailure("V160 reconciliation fixed readback lifecycle drifted")
    _assert_request_readback(request_row, request, register)
    audit = audits[0]
    event_bytes = bytes.fromhex(reconciliation["event_bytes_hex"])
    if (
        audit.get("event_projection") != reconciliation["event_projection"]
        or audit.get("reason") != "AMBIGUOUS_RESPONSE"
    ):
        raise ProbeFailure("V160 reconciliation event byte/projection drifted")
    _assert_bytes_and_hash(
        audit, "event_bytes", "reconciliation_hash", event_bytes
    )
    verifier_bytes = bytes.fromhex(reconciliation["verification_receipt_bytes_hex"])
    _assert_bytes_and_hash(
        audit,
        "verification_receipt_bytes",
        "verification_receipt_hash",
        verifier_bytes,
    )
    if audit.get("verification_receipt") != reconciliation["verification_receipt"]:
        raise ProbeFailure("V160 reconciliation verifier projection drifted")
    _assert_verifier_evidence(
        readback,
        {
            "REGISTER_REQUEST": ("REQUEST_ONLY", register),
            "MARK_RECONCILE_REQUIRED": ("SIGNED_STATUS", reconciliation),
        },
    )
    bundle = readback.get("v159_bundle", {})
    if bundle != {
        "attestation": None,
        "training_run": None,
        "artifacts": [],
        "registry": None,
    }:
        raise ProbeFailure("V160 reconciliation readback exposed V159 state")


def _assert_non_success_readback(
    admin: Any,
    readback: Mapping[str, Any],
    request: Mapping[str, Any],
    register: Mapping[str, Any],
    outcome: str,
    claim: Mapping[str, Any] | None,
    terminal: Mapping[str, Any] | None,
    expiry_result: Mapping[str, Any] | None,
    expected_reconciliation: int,
    markers: set[str],
) -> None:
    request_row = readback.get("request")
    terminal_row = readback.get("terminal")
    if (
        readback.get("status") != "FOUND"
        or not isinstance(request_row, Mapping)
        or not isinstance(terminal_row, Mapping)
        or terminal_row.get("outcome") != outcome
        or readback.get("statuses") != []
    ):
        raise ProbeFailure("V160 non-success fixed reader lifecycle drifted")
    _assert_request_readback(request_row, request, register)
    if claim is None:
        if readback.get("claim") is not None:
            raise ProbeFailure("V160 expiry readback unexpectedly has a claim")
    else:
        claim_row = readback.get("claim")
        if not isinstance(claim_row, Mapping):
            raise ProbeFailure("V160 non-success claim readback is missing")
        _assert_claim_readback(claim_row, claim)
    if terminal is None:
        expiry_projection = terminal_row.get("terminal_projection")
        if (
            not isinstance(expiry_result, Mapping)
            or not isinstance(expiry_projection, Mapping)
            or expiry_projection
            != {
                "schema_version": "alr_challenger_consumption_expiry_v1",
                "request_hash": request["projection"]["request_hash"],
                "outcome": "EXPIRED_UNCLAIMED",
                "reason": "ACCEPT_WINDOW_ELAPSED",
                "expired_at": expiry_result.get("consumed_at"),
            }
            or json.loads(_jsonb_bytea(terminal_row.get("terminal_bytes")))
            != expiry_projection
            or terminal_row.get("verification_receipt") is not None
            or terminal_row.get("inner_receipt_bytes") is not None
        ):
            raise ProbeFailure("V160 expiry terminal carries verifier/inner bytes")
        _assert_bytes_and_hash(
            terminal_row,
            "terminal_bytes",
            "terminal_hash",
            _jsonb_bytea(terminal_row.get("terminal_bytes")),
        )
        expected_verifiers = {"REGISTER_REQUEST": ("REQUEST_ONLY", register)}
    else:
        terminal_bytes = bytes.fromhex(terminal["response_bytes_hex"])
        _assert_bytes_and_hash(
            terminal_row, "terminal_bytes", "terminal_hash", terminal_bytes
        )
        if terminal_row.get("terminal_projection") != terminal["response_projection"]:
            raise ProbeFailure("V160 non-success terminal projection drifted")
        if terminal_row.get("inner_receipt_bytes") is not None:
            raise ProbeFailure("V160 non-success terminal exposes inner receipt")
        _assert_non_success_terminal_verifier(
            terminal_row, terminal, markers
        )
        expected_verifiers = {
            "REGISTER_REQUEST": ("REQUEST_ONLY", register),
            "CLAIM_REQUEST": ("REQUEST_ONLY", claim),
            "CONSUME_TERMINAL": ("TERMINAL_NO_INNER", terminal),
        }
    _assert_verifier_evidence(readback, expected_verifiers)
    audits = readback.get("reconciliation_audit")
    if not isinstance(audits, list) or len(audits) != expected_reconciliation:
        raise ProbeFailure("V160 non-success reconciliation cardinality drifted")
    if expected_reconciliation:
        _assert_failed_reconciliation_readback(
            admin,
            audits[0],
            request["projection"]["request_hash"],
            terminal_row,
            terminal,
            markers,
        )
    bundle = readback.get("v159_bundle")
    if bundle != {
        "attestation": None,
        "training_run": None,
        "artifacts": [],
        "registry": None,
    }:
        raise ProbeFailure("V160 non-success fixed reader exposed V159 state")
    markers.add("NON_SUCCESS_FIXED_READER_NO_V159")


def _assert_non_success_terminal_verifier(
    terminal_row: Mapping[str, Any],
    terminal: Mapping[str, Any],
    markers: set[str],
) -> None:
    verifier_bytes = bytes.fromhex(terminal["verification_receipt_bytes_hex"])
    if terminal_row.get("verification_receipt") != terminal["verification_receipt"]:
        raise ProbeFailure("V160 non-success terminal verifier projection drifted")
    _assert_bytes_and_hash(
        terminal_row,
        "verification_receipt_bytes",
        "verification_receipt_hash",
        verifier_bytes,
    )
    markers.add("NON_SUCCESS_TERMINAL_VERIFIER_EXACT")


def _assert_failed_reconciliation_readback(
    admin: Any,
    audit: Mapping[str, Any],
    request_hash: str,
    terminal_row: Mapping[str, Any],
    terminal: Mapping[str, Any] | None,
    markers: set[str],
) -> None:
    if terminal is None:
        raise ProbeFailure("V160 failed reconciliation lacks terminal fixture")
    terminal_hash = terminal_row.get("terminal_hash")
    expected_projection = {
        "schema_version": "alr_challenger_reconciliation_event_v1",
        "request_hash": request_hash,
        "reason": "FAILED_AFTER_START",
        "terminal_hash": terminal_hash,
    }
    expected_bytes, _ = _canonical_pg_jsonb_bytes(admin, expected_projection)
    expected_hash = hashlib.sha256(
        (
            "v160_failed_after_start\n"
            f"request={request_hash}\n"
            f"terminal={terminal_hash}\n"
        ).encode("utf-8")
    ).hexdigest()
    if (
        audit.get("reason") != "FAILED_AFTER_START"
        or audit.get("event_projection") != expected_projection
        or _jsonb_bytea(audit.get("event_bytes")) != expected_bytes
        or audit.get("reconciliation_hash") != expected_hash
        or audit.get("verification_receipt")
        != terminal["verification_receipt"]
    ):
        raise ProbeFailure("V160 failed reconciliation exact readback drifted")
    _assert_bytes_and_hash(
        audit,
        "verification_receipt_bytes",
        "verification_receipt_hash",
        bytes.fromhex(terminal["verification_receipt_bytes_hex"]),
    )
    markers.add("FAILED_RECONCILIATION_EXACT")


def _schema_digest(admin: Any) -> str:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT jsonb_build_object("
            "'relations',(SELECT jsonb_agg(jsonb_build_array(c.relname,c.relowner,c.relacl) ORDER BY c.relname) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='learning' AND c.relname LIKE 'alr_challenger_consumption_%'),"
            "'functions',(SELECT jsonb_agg(jsonb_build_array(p.oid::regprocedure::text,p.proowner,p.proacl,md5(p.prosrc)) ORDER BY p.oid::regprocedure::text) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='learning' AND (p.proname LIKE '%alr_challenger_consumption%' OR p.proname IN('persist_alr_challenger_fit_attestation_v1','persist_alr_challenger_training_result_v2','read_alr_challenger_training_result_v2'))),"
            "'triggers',(SELECT jsonb_agg(jsonb_build_array(t.tgname,t.tgrelid::regclass::text,t.tgfoid::regprocedure::text) ORDER BY t.tgname) FROM pg_catalog.pg_trigger t WHERE NOT t.tgisinternal AND t.tgname LIKE 'alr_v160_%')) AS fingerprint"
        )
        row = cursor.fetchone()
    if not row:
        raise ProbeFailure("V160 schema fingerprint returned no row")
    return hashlib.sha256(json.dumps(row["fingerprint"], sort_keys=True, default=str).encode()).hexdigest()


def _orchestrate(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    migrations: Mapping[str, bytes],
) -> tuple[dict[str, dict[str, Any]], str]:
    _apply_migration(admin_parameters, migrations["V158"], expected_target, "V158", 1)
    _apply_migration(admin_parameters, migrations["V159"], expected_target, "V159", 1)
    admin = _connect(admin_parameters)
    trainer = _connect_as_role(
        admin_parameters, expected_target, _TRAINER_CALLER, destructive_ack=True
    )
    try:
        fixtures: dict[str, dict[str, Any]] = {}
        for label in (
            "success",
            "rejected",
            "failed",
            "expired",
            "reconcile",
            "claim_expire",
            "status_race",
            "terminal_success",
            "success_conflict",
            "artifact_race",
            "locks",
        ):
            receipt = _persist_qualified_receipt(admin, trainer, label)
            fixtures[label] = _attestation_fixture(admin, receipt, label, expiry_seconds=300.0)
    finally:
        trainer.close()
        admin.close()
    _apply_migration(admin_parameters, migrations["V160"], expected_target, "V160", 1)
    admin = _connect(admin_parameters)
    try:
        first = _schema_digest(admin)
    finally:
        admin.close()
    _apply_migration(admin_parameters, migrations["V160"], expected_target, "V160", 2)
    admin = _connect(admin_parameters)
    try:
        second = _schema_digest(admin)
    finally:
        admin.close()
    if first != second:
        raise ProbeFailure("exact second V160 apply changed the schema fingerprint")
    return fixtures, first


def _bundle_counts(admin: Any, request_hash: str) -> dict[str, int]:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT "
            "(SELECT count(*) FROM learning.alr_challenger_consumption_terminals WHERE request_hash=%s) AS terminals,"
            "(SELECT count(*) FROM learning.alr_challenger_fit_attestations a JOIN learning.alr_challenger_consumption_requests r ON r.durable_receipt_hash=a.durable_receipt_hash AND r.training_key_hash=a.training_key_hash WHERE r.request_hash=%s) AS attestations,"
            "(SELECT count(*) FROM learning.alr_challenger_training_runs x JOIN learning.alr_challenger_consumption_requests r ON r.durable_receipt_hash=x.durable_receipt_hash AND r.training_key_hash=x.training_key_hash WHERE r.request_hash=%s) AS runs,"
            "(SELECT count(*) FROM learning.alr_challenger_model_artifacts m JOIN learning.alr_challenger_training_runs x ON x.training_run_hash=m.training_run_hash JOIN learning.alr_challenger_consumption_requests r ON r.durable_receipt_hash=x.durable_receipt_hash AND r.training_key_hash=x.training_key_hash WHERE r.request_hash=%s) AS artifacts,"
            "(SELECT count(*) FROM learning.alr_challenger_registry g JOIN learning.alr_challenger_training_runs x ON x.training_run_hash=g.training_run_hash JOIN learning.alr_challenger_consumption_requests r ON r.durable_receipt_hash=x.durable_receipt_hash AND r.training_key_hash=x.training_key_hash WHERE r.request_hash=%s) AS registry,"
            "(SELECT count(*) FROM learning.alr_challenger_consumption_reconciliation_audit WHERE request_hash=%s) AS reconciliation",
            (request_hash,) * 6,
        )
        row = cursor.fetchone()
    if not row:
        raise ProbeFailure("V160 bundle count oracle returned no row")
    return {key: int(value) for key, value in row.items()}


def _wait_for_expiry(admin: Any, accept_by: str) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        with admin.cursor() as cursor:
            cursor.execute("SELECT clock_timestamp()>=%s::timestamptz AS expired", (accept_by,))
            if cursor.fetchone() == {"expired": True}:
                return
        time.sleep(0.05)
    raise ProbeFailure("bounded V160 expiry fixture did not reach database accept_by")


def _assert_closed_boundaries(caller: Any, request_hash: str) -> None:
    import psycopg2  # type: ignore

    statements = (
        ("SELECT * FROM learning.alr_challenger_consumption_requests", ()),
        ("INSERT INTO learning.alr_challenger_consumption_requests(request_hash) VALUES(%s)", (request_hash,)),
        ("SELECT learning.read_alr_challenger_training_result_v2(%s,%s)", (_h("none"), _h("none-run"))),
    )
    for statement, parameters in statements:
        try:
            with caller.cursor() as cursor:
                cursor.execute(statement, parameters)
        except psycopg2.Error as exc:
            caller.rollback()
            if exc.pgcode != "42501":
                raise ProbeFailure("V160 closed boundary returned unexpected SQLSTATE") from exc
        else:
            caller.rollback()
            raise ProbeFailure("V160 caller reached a closed table or V159 wrapper")


def _run_scenarios(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    fixtures: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    markers: set[str] = {
        "MIGRATION_REPLAY_STABLE",
        "DATABASE_RESIDENT_V157_SENTINEL",
    }
    admin = _connect(admin_parameters)
    caller = _connect_as_consumption_caller(admin_parameters, expected_target)
    try:
        requests = {
            label: _request_fixture(admin, fixture, label)
            for label, fixture in fixtures.items()
        }

        success = requests["success"]
        register = _register_payload(admin, success)
        first = _call(caller, "REGISTER_REQUEST", register)
        caller.commit()
        replay = _call(caller, "REGISTER_REQUEST", register)
        caller.commit()
        if first.get("status") != "PERSISTED" or replay.get("status") != "DUPLICATE":
            raise ProbeFailure("V160 request replay statuses are not exact")
        divergent = deepcopy(register)
        divergent["request_projection"]["dispatch_allowed"] = True
        divergent_bytes, _ = _canonical_pg_jsonb_bytes(admin, divergent["request_projection"])
        divergent["request_bytes_hex"] = divergent_bytes.hex()
        verifier, verifier_bytes = _verifier_fixture(admin, divergent_bytes, "REQUEST_ONLY")
        divergent["verification_receipt"] = verifier
        divergent["verification_receipt_bytes_hex"] = verifier_bytes.hex()
        _expect_p0001(caller, "REGISTER_REQUEST", divergent)
        markers.add("REGISTER_EXACT_REPLAY")

        claim = _claim_payload(admin, success, "success")
        if _call(caller, "CLAIM_REQUEST", claim).get("status") != "PERSISTED":
            raise ProbeFailure("V160 pre-fit claim was not persisted")
        caller.commit()
        markers.add("CLAIM_BEFORE_FIT")
        status = _status_payload(admin, success)
        if _call(caller, "RECORD_STATUS", status).get("status") != "PERSISTED":
            raise ProbeFailure("V160 monotonic status was not persisted")
        caller.commit()
        if _call(caller, "RECORD_STATUS", status).get("status") != "DUPLICATE":
            raise ProbeFailure("V160 status replay was not duplicate")
        caller.commit()
        markers.add("STATUS_MONOTONIC")
        terminal = _terminal_payload(admin, success, fixtures["success"], "SUCCEEDED")
        result = _call(caller, "CONSUME_TERMINAL", terminal)
        caller.commit()
        if result.get("status") != "PERSISTED" or result.get("outcome") != "SUCCEEDED":
            raise ProbeFailure("V160 success terminal did not atomically persist")
        replay_result = _call(caller, "CONSUME_TERMINAL", terminal)
        caller.commit()
        if replay_result.get("status") != "DUPLICATE":
            raise ProbeFailure("V160 success terminal replay was not duplicate")
        counts = _bundle_counts(admin, success["projection"]["request_hash"])
        if counts != {"terminals": 1, "attestations": 1, "runs": 1, "artifacts": 3, "registry": 1, "reconciliation": 0}:
            raise ProbeFailure("V160 success bundle was not atomic 1/1/3/1")
        markers.add("SUCCESS_BUNDLE_ATOMIC_1_1_3_1")

        readback = _read(caller, success["projection"]["request_hash"])
        caller.commit()
        _assert_exact_success_readback(
            readback,
            success,
            register,
            claim,
            status,
            terminal,
            fixtures["success"],
            result,
            markers,
        )
        markers.add("FIXED_READER_BYTE_READBACK")

        for label, outcome, expected_reconciliation, marker in (
            ("rejected", "REJECTED_PRE_FIT", 0, "REJECTED_PRE_FIT_NO_V159"),
            ("failed", "FAILED_AFTER_START", 1, "FAILED_AFTER_START_RECONCILE_NO_V159"),
        ):
            request = requests[label]
            branch_register = _register_payload(admin, request)
            _call(caller, "REGISTER_REQUEST", branch_register)
            caller.commit()
            branch_claim = _claim_payload(admin, request, label)
            _call(caller, "CLAIM_REQUEST", branch_claim)
            caller.commit()
            terminal_payload = _terminal_payload(admin, request, fixtures[label], outcome)
            terminal_result = _call(caller, "CONSUME_TERMINAL", terminal_payload)
            caller.commit()
            if terminal_result.get("outcome") != outcome:
                raise ProbeFailure("V160 non-success terminal outcome drifted")
            branch_counts = _bundle_counts(admin, request["projection"]["request_hash"])
            if branch_counts != {"terminals": 1, "attestations": 0, "runs": 0, "artifacts": 0, "registry": 0, "reconciliation": expected_reconciliation}:
                raise ProbeFailure("V160 non-success terminal wrote V159 state")
            branch_readback = _read(caller, request["projection"]["request_hash"])
            caller.commit()
            _assert_non_success_readback(
                admin,
                branch_readback,
                request,
                branch_register,
                outcome,
                branch_claim,
                terminal_payload,
                None,
                expected_reconciliation,
                markers,
            )
            markers.add(marker)

        reconcile = requests["reconcile"]
        reconcile_register = _register_payload(admin, reconcile)
        _call(caller, "REGISTER_REQUEST", reconcile_register)
        caller.commit()
        reconciliation = _reconcile_payload(admin, reconcile)
        if _call(caller, "MARK_RECONCILE_REQUIRED", reconciliation).get("status") != "PERSISTED":
            raise ProbeFailure("V160 reconciliation audit was not persisted")
        caller.commit()
        reconcile_readback = _read(caller, reconcile["projection"]["request_hash"])
        caller.commit()
        _assert_exact_reconciliation_readback(
            reconcile_readback,
            reconcile,
            reconcile_register,
            reconciliation,
        )

        expired = _request_fixture(
            admin, fixtures["expired"], "expired", accept_seconds=0.5
        )
        expired_register = _register_payload(admin, expired)
        _call(caller, "REGISTER_REQUEST", expired_register)
        caller.commit()
        _wait_for_expiry(admin, expired["times"]["accept_by"])
        expiry = _call(
            caller,
            "EXPIRE_UNCLAIMED",
            {"request_hash": expired["projection"]["request_hash"], "reason": "ACCEPT_WINDOW_ELAPSED"},
        )
        caller.commit()
        if expiry.get("outcome") != "EXPIRED_UNCLAIMED":
            raise ProbeFailure("V160 unclaimed request did not expire")
        expired_counts = _bundle_counts(admin, expired["projection"]["request_hash"])
        if expired_counts != {"terminals": 1, "attestations": 0, "runs": 0, "artifacts": 0, "registry": 0, "reconciliation": 0}:
            raise ProbeFailure("V160 expiry wrote forbidden V159 state")
        expired_readback = _read(caller, expired["projection"]["request_hash"])
        caller.commit()
        _assert_non_success_readback(
            admin,
            expired_readback,
            expired,
            expired_register,
            "EXPIRED_UNCLAIMED",
            None,
            None,
            expiry,
            0,
            markers,
        )
        markers.add("EXPIRED_UNCLAIMED_NO_V159")

        _assert_closed_action_schemas(admin, caller, requests, fixtures, markers)
        _assert_verifier_fail_closed(admin, caller, requests["locks"], markers)
        _assert_terminal_verifiers_fail_closed(
            admin, caller, requests["locks"], fixtures["locks"], markers
        )
        _assert_v159_application_closure(
            admin_parameters, expected_target, caller, admin, markers
        )
        _assert_coordinator_execute_deletion(admin, caller, register, markers)

        _assert_closed_boundaries(caller, success["projection"]["request_hash"])
        markers.add("DIRECT_DML_AND_V159_WRAPPERS_CLOSED")
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) AS count FROM learning.alr_challenger_training_runs "
                "WHERE model_training_performed IS TRUE AND no_authority=%s::jsonb "
                "AND authority_counters=%s::jsonb AND authority_counters->>'model_fit_count'='0'",
                (_adapt(_NO_AUTHORITY), _adapt(_ZERO_COUNTERS)),
            )
            if cursor.fetchone() != {"count": 1}:
                raise ProbeFailure("V160 fixture no-authority/zero-counter run drifted")
        markers.add("NO_AUTHORITY_FALSE_ZERO")
        markers.add("SCENARIO_SUITE_COMPLETE")
        if markers != _REQUIRED_MARKERS:
            raise ProbeFailure("V160 functional marker coverage is incomplete")
        return {"markers": sorted(markers), "success_bundle_counts": counts}
    finally:
        caller.close()
        admin.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.confirm_disposable_v160 or os.environ.get(_ACK_ENV) != "1":
        raise ProbeFailure(f"explicit --confirm-disposable-v160 and {_ACK_ENV}=1 are required")
    if args.disposable_sentinel != f"{_SENTINEL}:{args.expected_database}":
        raise ProbeFailure("the exact V160 sentinel suffixed by the database is required")
    if not _DISPOSABLE_DATABASE.search(args.expected_database.lower()):
        raise ProbeFailure("--expected-database must be named ci/test/tmp/scratch/disposable")
    _reject_ambient_libpq_routing()
    payloads: dict[str, bytes] = {}
    digests: dict[str, str] = {}
    for version, path in (("V158", args.v158), ("V159", args.v159), ("V160", args.v160)):
        payloads[version], digests[version] = _migration_bytes(path, version)
    admin_parameters = _parse_complete_dsn(
        _required_env(_ADMIN_DSN_ENV), args.expected_database, "administrator"
    )
    admin = _connect(admin_parameters)
    try:
        identity = _target_identity(admin)
        if identity["database_name"] != args.expected_database:
            raise ProbeFailure("connected database differs from explicit target")
        expected_target = dict(identity)
        _assert_v157_disposable_baseline(
            admin, expected_target, args.expected_database
        )
        _assert_eight_roles(admin)
    finally:
        admin.close()
    fixtures, fingerprint = _orchestrate(admin_parameters, expected_target, payloads)
    summary = _run_scenarios(admin_parameters, expected_target, fixtures)
    print(
        json.dumps(
            {
                "schema_version": "alr_v160_disposable_pg_probe_v1",
                "status": "PASS",
                "database": args.expected_database,
                "migration_sha256": digests,
                "schema_fingerprint": fingerprint,
                "double_apply": True,
                "scenario_markers": summary["markers"],
                "fixture_only": True,
                "external_authenticity_proven": False,
                "model_fit_performed_by_probe": False,
                "production_rows_created": False,
            },
            sort_keys=True,
        )
    )
    return 0


def _safe_entrypoint(argv: Sequence[str] | None = None) -> int:
    try:
        return main(argv)
    except ProbeFailure:
        sys.stderr.write(_SAFE_FAILURE_MESSAGE + "\n")
        return 1
    except Exception:
        sys.stderr.write(_SAFE_FAILURE_MESSAGE + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(_safe_entrypoint())
