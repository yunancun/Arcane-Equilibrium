"""Explicit disposable-PG16 probe skeleton for the V159 durable-fit seam.

Importing this module is inert. Execution is destructive and requires an exact
CLI sentinel plus an environment acknowledgement. The probe never prints DSNs,
credentials, passfiles, signed receipt bytes, or receipt projections.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


_ROOT = Path(__file__).resolve().parents[4]
_PROGRAM_CODE = _ROOT / "program_code"
if str(_PROGRAM_CODE) not in sys.path:
    sys.path.insert(0, str(_PROGRAM_CODE))

from ml_training.tests.integration.alr_challenger_training_isolated_pg import (  # noqa: E402
    ProbeFailure,
    _adapt,
    _assert_pg16_and_roles,
    _assert_same_target,
    _call as _v158_call,
    _connect as _v158_connect,
    _normalized,
    _parse_complete_dsn,
    _receipt_arguments as _v158_receipt_arguments,
    _reject_ambient_libpq_routing,
    _seed_projection_artifact as _v158_seed_projection_artifact,
    _target_identity,
)


_V158 = (_ROOT / "sql/migrations/V158__alr_qualified_challenger_training.sql").resolve()
_V159 = (_ROOT / "sql/migrations/V159__alr_durable_fit_attestation.sql").resolve()
_EXPECTED_SHA256 = {
    "V158": "7ed70599c6bd5f3cdb3376bc135a952d8c18f4ad62a62432c2bfdd8ee84e446b",
    "V159": "5941b2b2b164e4b5408be32507d26e58faccc35f73cf83f6bc057498580fae5e",
}
_ON_ERROR_STOP_EQUIVALENT = True
_SAFE_FAILURE_MESSAGE = "V159 durable-fit disposable probe failed safely"
_ACK_ENV = "ALR_V159_DISPOSABLE_ACK"
_ADMIN_DSN_ENV = "ALR_V159_DISPOSABLE_ADMIN_DSN"
_SENTINEL = "V159_DURABLE_FIT_DISPOSABLE_MUTATION_CONFIRMED"
_DISPOSABLE_DATABASE = re.compile(
    r"(?:^|[_-])(ci|test|tmp|scratch|disposable)(?:[_-]|$)"
)
_ATTESTOR = "alr_challenger_fit_attestor"
_ATTESTOR_CALLER = "alr_challenger_fit_attestor_caller"
_WRITER = "alr_challenger_writer"
_TRAINER_CALLER = "alr_challenger_trainer_caller"
_GENERIC_ROLES = ("trading_ai", "alr_shadow")
_NO_AUTHORITY = {
    "exchange_authority": False,
    "trading_authority": False,
    "order_or_probe_authority": False,
    "decision_lease_authority": False,
    "cost_gate_authority": False,
    "proof_authority": False,
    "serving_authority": False,
    "promotion_authority": False,
    "latest_authority": False,
    "runtime_mutation_authority": False,
    "database_write_authority": False,
    "symlink_authority": False,
}
_ZERO_COUNTERS = {
    "exchange_contact_count": 0,
    "trading_action_count": 0,
    "order_or_probe_count": 0,
    "decision_lease_count": 0,
    "cost_gate_change_count": 0,
    "proof_claim_count": 0,
    "serving_or_promotion_count": 0,
    "runtime_mutation_count": 0,
    "database_write_count": 0,
    "symlink_update_count": 0,
    "model_fit_count": 0,
}
_BUNDLE_TABLES = (
    "alr_challenger_fit_attestations",
    "alr_challenger_training_runs",
    "alr_challenger_model_artifacts",
    "alr_challenger_registry",
)
_DIRECT_DENIAL_TABLES = ("alr_qualified_training_receipts", *_BUNDLE_TABLES)

_FUNCTIONS = {
    "attest": "persist_alr_challenger_fit_attestation_v1",
    "bind": "persist_alr_challenger_training_result_v2",
    "read": "read_alr_challenger_training_result_v2",
    "closed_write": "persist_alr_challenger_training_result_v1",
    "closed_read": "read_alr_challenger_training_result_v1",
}
_FUNCTION_ARGUMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    _FUNCTIONS["attest"]: (
        ("p_signed_receipt_bytes", "bytea"),
        ("p_receipt_projection", "jsonb"),
        ("p_durable_receipt_hash", "text"),
        ("p_training_key_hash", "text"),
        ("p_structural_result_hash", "text"),
        ("p_structural_fit_capture_hash", "text"),
        ("p_structural_candidate_hash", "text"),
        ("p_structural_training_run_hash", "text"),
        ("p_structural_challenger_hash", "text"),
        ("p_runner_identity_hash", "text"),
        ("p_actual_input_material_set_hash", "text"),
        ("p_ordered_artifact_set_hash", "text"),
        ("p_issuer_id", "text"),
        ("p_trust_policy_id", "text"),
        ("p_signature_key_id", "text"),
        ("p_signature_algorithm", "text"),
        ("p_verified_at", "timestamptz"),
        ("p_expires_at", "timestamptz"),
    ),
    _FUNCTIONS["bind"]: (
        ("p_durable_attestation_hash", "text"),
        ("p_source_head", "text"),
        ("p_actual_dataset_hash", "text"),
        ("p_actual_row_ids_hash", "text"),
        ("p_actual_split_hash", "text"),
        ("p_actual_code_manifest_hash", "text"),
        ("p_actual_training_config_hash", "text"),
        ("p_actual_feature_schema_hash", "text"),
        ("p_actual_label_schema_hash", "text"),
        ("p_model_schema_version", "text"),
        ("p_actual_training_rows", "integer"),
        ("p_metrics_hash", "text"),
        ("p_resource_usage_hash", "text"),
        ("p_fit_started_at", "timestamptz"),
        ("p_fit_completed_at", "timestamptz"),
        ("p_q10_hash", "text"),
        ("p_q10_size", "bigint"),
        ("p_q50_hash", "text"),
        ("p_q50_size", "bigint"),
        ("p_q90_hash", "text"),
        ("p_q90_size", "bigint"),
    ),
    _FUNCTIONS["read"]: (
        ("p_durable_attestation_hash", "text"),
        ("p_structural_training_run_hash", "text"),
    ),
}
_SIGNED_AND_PERSISTED_FIELDS = tuple(
    name for name, _ in _FUNCTION_ARGUMENTS[_FUNCTIONS["bind"]]
    if name != "p_durable_attestation_hash"
)
_SIGNED_ATTESTATION_FIELDS = tuple(
    name for name, _ in _FUNCTION_ARGUMENTS[_FUNCTIONS["attest"]]
    if name not in {"p_signed_receipt_bytes", "p_receipt_projection"}
)
_MALFORMED_RECEIPT_CASES = (
    "root_missing", "root_extra", "wrong_root_type", "subject_missing",
    "claims_false", "actual_inputs_extra", "model_scalar", "artifacts_missing",
    "bytes_mismatch", "signature_bad", "evidence_tier_bad", "claim_kind_bad",
    "authentication_status_bad", "issuer_id_bad", "policy_id_bad",
    "signature_key_id_bad", "algorithm_bad", "no_authority_true",
    "counter_nonzero", "hash_bad", "lineage_bad", "artifact_set_bad",
    "training_rows_string", "training_rows_zero", "training_rows_fraction",
    "training_rows_overflow", "artifact_size_zero", "artifact_size_string",
    "artifact_size_fraction", "artifact_size_overflow", "duplicate_q_hash",
    "q_object_extra", "q_object_scalar", "fit_completed_after_verified",
    "verified_not_before_expires", "time_reversed", "time_future",
    "time_expired", "time_nonfinite",
)
_NONFINITE_TIME_CONSTRAINT = "alr_fit_attestations_time_check"


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ProbeFailure("invalid V159 probe arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(
        description="Run the explicit V159 durable-fit disposable-PG16 probe"
    )
    parser.add_argument("--confirm-disposable-v159", action="store_true")
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--disposable-sentinel", required=True)
    parser.add_argument("--v158", type=Path, default=_V158)
    parser.add_argument("--v159", type=Path, default=_V159)
    return parser


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ProbeFailure(f"{name} must be supplied explicitly")
    return value


def _configure_v159_session(connection: Any) -> None:
    if not connection.autocommit:
        raise ProbeFailure("V159 session configuration requires autocommit")
    with connection.cursor() as cursor:
        cursor.execute("SET SESSION TimeZone='UTC'")
        cursor.execute(
            "SET SESSION default_transaction_isolation='read committed'"
        )
        cursor.execute(
            "SELECT current_setting('TimeZone') AS timezone,"
            "current_setting('default_transaction_isolation') AS isolation"
        )
        settings = cursor.fetchone()
    if settings != {"timezone": "UTC", "isolation": "read committed"}:
        raise ProbeFailure("V159 session UTC/read-committed contract drifted")


def _connect(parameters: Mapping[str, str]) -> Any:
    connection = _v158_connect(parameters)
    try:
        connection.rollback()
        connection.autocommit = True
        _configure_v159_session(connection)
        connection.autocommit = False
        return connection
    except Exception:
        connection.close()
        raise


def _migration_bytes(path: Path, version: str) -> bytes:
    expected_path = {"V158": _V158, "V159": _V159}[version]
    resolved = path.resolve()
    if resolved != expected_path:
        raise ProbeFailure(f"{version} must be the canonical repository migration path")
    payload = resolved.read_bytes()
    observed = hashlib.sha256(payload).hexdigest()
    if observed != _EXPECTED_SHA256[version]:
        raise ProbeFailure(
            f"canonical {version} sha256 mismatch: expected "
            f"{_EXPECTED_SHA256[version]}, observed {observed}"
        )
    return payload


def _apply_migration(
    admin_parameters: Mapping[str, str],
    migration: bytes,
    expected_target: Mapping[str, Any],
    version: str,
    ordinal: int,
) -> None:
    import psycopg2  # type: ignore

    connection = _connect(admin_parameters)
    connection.autocommit = True
    try:
        if _target_identity(connection) != dict(expected_target):
            raise ProbeFailure(
                f"{version} apply {ordinal} target differs from the preflight target"
            )
        with connection.cursor() as cursor:
            cursor.execute(migration.decode("utf-8"))
    except psycopg2.Error as exc:
        primary = getattr(exc.diag, "message_primary", None) or str(exc).splitlines()[0]
        raise ProbeFailure(
            f"{version} apply {ordinal} failed with SQLSTATE {exc.pgcode}: {primary}"
        ) from exc
    finally:
        connection.close()


def _seed_v159_role_preconditions(admin: Any, *, destructive_ack: bool) -> None:
    if not destructive_ack:
        raise ProbeFailure("V159 role seeding requires the explicit destructive ack")
    _assert_pg16_and_roles(admin)
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT session_user AS session_user, current_user AS current_user, "
            "r.rolsuper AS superuser, r.rolcanlogin AS can_login, "
            "pg_catalog.pg_get_userbyid(d.datdba) AS database_owner "
            "FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_database d "
            "WHERE r.rolname=current_user AND d.datname=current_database()"
        )
        identity = cursor.fetchone()
        if not identity or identity != {
            "session_user": identity["current_user"],
            "current_user": identity["current_user"],
            "superuser": True,
            "can_login": True,
            "database_owner": identity["current_user"],
        }:
            raise ProbeFailure(
                "V159 role fixture requires a direct login superuser owning the database"
            )
        cursor.execute(
            "DO $v159_probe_roles$ BEGIN "
            "IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='alr_challenger_fit_attestor') THEN "
            "CREATE ROLE alr_challenger_fit_attestor NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS; END IF; "
            "IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='alr_challenger_fit_attestor_caller') THEN "
            "CREATE ROLE alr_challenger_fit_attestor_caller LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 1; END IF; "
            "END $v159_probe_roles$"
        )
        cursor.execute(
            "SELECT count(*) AS count, bool_and(CASE WHEN rolname=%s THEN "
            "NOT rolcanlogin AND rolconnlimit=-1 ELSE rolcanlogin AND rolconnlimit=1 END "
            "AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND "
            "NOT rolinherit AND NOT rolreplication AND NOT rolbypassrls) AS exact "
            "FROM pg_catalog.pg_roles WHERE rolname IN(%s,%s)",
            (_ATTESTOR, _ATTESTOR, _ATTESTOR_CALLER),
        )
        posture = cursor.fetchone()
        if posture != {"count": 2, "exact": True}:
            raise ProbeFailure("V159 disposable role posture is not exact")
        cursor.execute(
            "SELECT count(*) AS count FROM pg_catalog.pg_auth_members "
            "WHERE roleid IN(SELECT oid FROM pg_catalog.pg_roles WHERE rolname IN(%s,%s)) "
            "OR member IN(SELECT oid FROM pg_catalog.pg_roles WHERE rolname IN(%s,%s))",
            (_ATTESTOR, _ATTESTOR_CALLER, _ATTESTOR, _ATTESTOR_CALLER),
        )
        if cursor.fetchone() != {"count": 0}:
            raise ProbeFailure("V159 roles must be membership-free")
        for role in (_ATTESTOR, _ATTESTOR_CALLER):
            cursor.execute(
                "SELECT pg_catalog.has_parameter_privilege("
                "%s,'session_replication_role','SET') AS allowed",
                (role,),
            )
            if cursor.fetchone() != {"allowed": False}:
                raise ProbeFailure(f"{role} may not SET session_replication_role")
    admin.commit()


def _schema_digest(admin: Any) -> str:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT jsonb_build_object("
            "'columns',(SELECT jsonb_agg(jsonb_build_array(c.relname,a.attnum,a.attname,a.atttypid::regtype::text,a.attnotnull,a.atthasdef) ORDER BY c.relname,a.attnum) FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='learning' AND c.relname IN('alr_challenger_fit_attestations','alr_challenger_training_runs','alr_challenger_model_artifacts','alr_challenger_registry') AND a.attnum>0 AND NOT a.attisdropped),"
            "'constraints',(SELECT jsonb_agg(jsonb_build_array(c.conname,c.conrelid::regclass::text,pg_catalog.pg_get_constraintdef(c.oid,false)) ORDER BY c.conname) FROM pg_catalog.pg_constraint c WHERE c.conrelid IN('learning.alr_challenger_fit_attestations'::regclass,'learning.alr_challenger_training_runs'::regclass,'learning.alr_challenger_model_artifacts'::regclass,'learning.alr_challenger_registry'::regclass)),"
            "'functions',(SELECT jsonb_agg(jsonb_build_array(p.oid::regprocedure::text,pg_catalog.pg_get_userbyid(p.proowner),md5(p.prosrc),p.proacl) ORDER BY p.oid::regprocedure::text) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='learning' AND p.proname LIKE '%alr_challenger%v2' OR n.nspname='learning' AND p.proname IN('persist_alr_challenger_fit_attestation_v1','alr_v159_assert_attested_bundle','alr_v159_reject_attestation_mutation')),"
            "'triggers',(SELECT jsonb_agg(jsonb_build_array(t.tgname,t.tgrelid::regclass::text,t.tgfoid::regprocedure::text,t.tgtype,t.tgdeferrable,t.tginitdeferred) ORDER BY t.tgname) FROM pg_catalog.pg_trigger t WHERE NOT t.tgisinternal AND t.tgname LIKE 'alr_v159_%')) AS fingerprint"
        )
        row = cursor.fetchone()
    if not row or "fingerprint" not in row:
        raise ProbeFailure("V159 schema fingerprint query returned no row")
    encoded = json.dumps(row["fingerprint"], sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _h(label: str) -> str:
    return hashlib.sha256(f"alr-v159-fixture:{label}".encode("utf-8")).hexdigest()


def _call(connection: Any, function_name: str, arguments: Mapping[str, Any]) -> Any:
    if function_name not in _FUNCTION_ARGUMENTS:
        raise ProbeFailure(f"function is outside the fixed V159 surface: {function_name}")
    signature = _FUNCTION_ARGUMENTS[function_name]
    names = [name for name, _ in signature]
    if list(arguments) != names:
        raise ProbeFailure(f"ordered argument set differs for {function_name}")
    placeholders = ", ".join(f"%s::{data_type}" for _, data_type in signature)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT learning.{function_name}({placeholders}) AS payload",  # noqa: S608
            tuple(_adapt(arguments[name]) for name in names),
        )
        row = cursor.fetchone()
    if not row or "payload" not in row:
        raise ProbeFailure(f"{function_name} returned no typed result")
    return _normalized(row["payload"])


def _expect_db_error(
    connection: Any,
    function_name: str,
    arguments: Mapping[str, Any],
    sqlstate: str,
    message: str,
) -> None:
    import psycopg2  # type: ignore

    try:
        _call(connection, function_name, arguments)
    except psycopg2.Error as exc:
        connection.rollback()
        primary = getattr(exc.diag, "message_primary", None)
        if exc.pgcode != sqlstate or primary != message:
            raise ProbeFailure(
                f"{function_name} returned ({exc.pgcode}, {primary!r}); "
                f"expected ({sqlstate}, {message!r})"
            ) from exc
    else:
        connection.rollback()
        raise ProbeFailure(f"{function_name} unexpectedly accepted invalid content")


def _expect_nonfinite_constraint_error(
    connection: Any, arguments: Mapping[str, Any]
) -> None:
    import psycopg2  # type: ignore

    try:
        _call(connection, _FUNCTIONS["attest"], arguments)
    except psycopg2.Error as exc:
        connection.rollback()
        constraint = getattr(exc.diag, "constraint_name", None)
        if exc.pgcode != "23514" or constraint != _NONFINITE_TIME_CONSTRAINT:
            raise ProbeFailure(
                f"nonfinite attestation returned ({exc.pgcode}, {constraint!r}); "
                f"expected (23514, {_NONFINITE_TIME_CONSTRAINT!r})"
            ) from exc
    else:
        connection.rollback()
        raise ProbeFailure("nonfinite attestation unexpectedly succeeded")


def _expect_db_sqlstate_only(
    connection: Any, arguments: Mapping[str, Any], sqlstate: str
) -> None:
    import psycopg2  # type: ignore

    try:
        _call(connection, _FUNCTIONS["attest"], arguments)
    except psycopg2.Error as exc:
        connection.rollback()
        if exc.pgcode != sqlstate:
            raise ProbeFailure(
                f"malformed cast returned {exc.pgcode}, expected {sqlstate}"
            ) from exc
    else:
        connection.rollback()
        raise ProbeFailure("malformed cast unexpectedly succeeded")


def _expect_statement_error(
    connection: Any,
    statement: str,
    sqlstate: str,
    message: str | None = None,
    parameters: Sequence[Any] = (),
) -> None:
    import psycopg2  # type: ignore

    try:
        with connection.cursor() as cursor:
            cursor.execute(statement, tuple(parameters))
    except psycopg2.Error as exc:
        connection.rollback()
        primary = getattr(exc.diag, "message_primary", None)
        if exc.pgcode != sqlstate or (message is not None and primary != message):
            raise ProbeFailure(
                f"statement returned ({exc.pgcode}, {primary!r}); "
                f"expected ({sqlstate}, {message!r})"
            ) from exc
    else:
        connection.rollback()
        raise ProbeFailure("statement unexpectedly succeeded")


def _database_times(admin: Any, expiry_seconds: float) -> dict[str, str]:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT "
            "to_char((statement_timestamp()-interval '3 seconds') AT TIME ZONE 'UTC',"
            "'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS fit_started_at,"
            "to_char((statement_timestamp()-interval '2 seconds') AT TIME ZONE 'UTC',"
            "'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS fit_completed_at,"
            "to_char((statement_timestamp()-interval '1 second') AT TIME ZONE 'UTC',"
            "'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS verified_at,"
            "to_char((statement_timestamp()+(%s*interval '1 second')) AT TIME ZONE 'UTC',"
            "'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS expires_at",
            (expiry_seconds,),
        )
        row = cursor.fetchone()
    if not row or set(row) != {
        "fit_started_at", "fit_completed_at", "verified_at", "expires_at"
    }:
        raise ProbeFailure("database-owned V159 time fixture is incomplete")
    return dict(row)


def _pg_jsonb_ordered(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _pg_jsonb_ordered(value[key])
            for key in sorted(
                value, key=lambda item: (len(item.encode("utf-8")), item.encode("utf-8"))
            )
        }
    if isinstance(value, list):
        return [_pg_jsonb_ordered(item) for item in value]
    return value


def _canonical_pg_jsonb_bytes(
    admin: Any, receipt_projection: Any
) -> tuple[bytes, str]:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT convert_to(%s::jsonb::text,'UTF8') AS canonical_bytes,"
            "encode(public.digest(convert_to(%s::jsonb::text,'UTF8'),"
            "'sha256'::text),'hex') AS db_sha256",
            (_adapt(receipt_projection), _adapt(receipt_projection)),
        )
        row = cursor.fetchone()
    if not row:
        raise ProbeFailure("PostgreSQL JSONB canonicalization returned no row")
    canonical = bytes(row["canonical_bytes"])
    python_canonical = json.dumps(
        _pg_jsonb_ordered(receipt_projection),
        ensure_ascii=False,
        separators=(", ", ": "),
        allow_nan=False,
    ).encode("utf-8")
    if python_canonical != canonical:
        raise ProbeFailure("PostgreSQL/Python JSONB canonical byte ordering differs")
    python_sha256 = hashlib.sha256(python_canonical).hexdigest()
    if python_sha256 != row["db_sha256"]:
        raise ProbeFailure("BYTE_SHA256_DB_PYTHON_PARITY failed")
    return canonical, python_sha256


def _artifact_set_hash(q10: str, q50: str, q90: str) -> str:
    return hashlib.sha256(
        f"q10={q10}\nq50={q50}\nq90={q90}\n".encode("utf-8")
    ).hexdigest()


def _persist_qualified_receipt(
    admin: Any, trainer_caller: Any, label: str
) -> dict[str, Any]:
    receipt = _v158_receipt_arguments(f"v159:{label}")
    _v158_seed_projection_artifact(
        admin,
        {
            "artifact_hash": receipt["p_projection_artifact_hash"],
            "artifact_kind": "learning_target",
            "canonical_payload": {
                "schema_version": "alr_v159_projection_fixture_v1",
                "fixture_id": label,
            },
        },
    )
    result = _v158_call(
        trainer_caller, "persist_alr_qualified_training_receipt_v1", receipt
    )
    trainer_caller.commit()
    if result.get("status") != "PERSISTED":
        raise ProbeFailure("V159 fixture qualified receipt was not newly persisted")
    return receipt


def _expected_durable_attestation_hash(
    arguments: Mapping[str, Any], external_receipt_digest: str
) -> str:
    projection = arguments["p_receipt_projection"]
    material = (
        "alr_durable_fit_attestation_v1\n"
        f"receipt={external_receipt_digest}\n"
        f"durable_receipt={arguments['p_durable_receipt_hash']}\n"
        f"training_key={arguments['p_training_key_hash']}\n"
        f"result={arguments['p_structural_result_hash']}\n"
        f"fit_capture={arguments['p_structural_fit_capture_hash']}\n"
        f"candidate={arguments['p_structural_candidate_hash']}\n"
        f"run={arguments['p_structural_training_run_hash']}\n"
        f"challenger={arguments['p_structural_challenger_hash']}\n"
        f"runner={arguments['p_runner_identity_hash']}\n"
        f"materials={arguments['p_actual_input_material_set_hash']}\n"
        f"artifacts={arguments['p_ordered_artifact_set_hash']}\n"
        f"issuer={arguments['p_issuer_id']}\n"
        f"policy={arguments['p_trust_policy_id']}\n"
        f"key={arguments['p_signature_key_id']}\n"
        f"verified={projection['verified_at']}\n"
        f"expires={projection['expires_at']}\n"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _utc_six_digit_z(value: Any) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    else:
        raise ProbeFailure("durable identity time has an unsupported type")
    if parsed.tzinfo is None:
        raise ProbeFailure("durable identity time must be timezone-aware")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _expected_durable_training_run_hash(
    fixture: Mapping[str, Any], bound_at: Any
) -> str:
    bind = fixture["bind"]
    material = (
        "alr_durable_training_run_v1\n"
        f"attestation={fixture['durable_attestation_hash']}\n"
        f"structural_run={fixture['read']['p_structural_training_run_hash']}\n"
        f"source={bind['p_source_head']}\n"
        f"dataset={bind['p_actual_dataset_hash']}\n"
        f"rows={bind['p_actual_row_ids_hash']}\n"
        f"split={bind['p_actual_split_hash']}\n"
        f"code={bind['p_actual_code_manifest_hash']}\n"
        f"config={bind['p_actual_training_config_hash']}\n"
        f"feature={bind['p_actual_feature_schema_hash']}\n"
        f"label={bind['p_actual_label_schema_hash']}\n"
        f"model={bind['p_model_schema_version']}\n"
        f"training_rows={bind['p_actual_training_rows']}\n"
        f"artifacts={fixture['attest']['p_ordered_artifact_set_hash']}\n"
        f"metrics={bind['p_metrics_hash']}\n"
        f"resources={bind['p_resource_usage_hash']}\n"
        f"fit_start={_utc_six_digit_z(bind['p_fit_started_at'])}\n"
        f"fit_end={_utc_six_digit_z(bind['p_fit_completed_at'])}\n"
        f"bound={_utc_six_digit_z(bound_at)}\n"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _expected_durable_challenger_hash(
    fixture: Mapping[str, Any], durable_training_run_hash: str
) -> str:
    material = (
        "alr_durable_challenger_v1\n"
        f"attestation={fixture['durable_attestation_hash']}\n"
        f"durable_run={durable_training_run_hash}\n"
        f"structural_challenger={fixture['attest']['p_structural_challenger_hash']}\n"
        f"artifacts={fixture['attest']['p_ordered_artifact_set_hash']}\n"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _attestation_fixture(
    admin: Any,
    receipt: Mapping[str, Any],
    label: str,
    *,
    expiry_seconds: float = 3600.0,
) -> dict[str, Any]:
    times = _database_times(admin, expiry_seconds)
    payload = receipt["p_canonical_payload"]
    q10, q50, q90 = (_h(f"{label}:{q}") for q in ("q10", "q50", "q90"))
    artifact_set = _artifact_set_hash(q10, q50, q90)
    subject = {
        "durable_receipt_hash": receipt["p_durable_receipt_hash"],
        "training_key_hash": receipt["p_training_key_hash"],
        "result_hash": _h(f"{label}:result"),
        "fit_capture_hash": _h(f"{label}:fit-capture"),
        "candidate_attestation_hash": _h(f"{label}:candidate"),
        "training_run_hash": _h(f"{label}:training-run"),
        "challenger_hash": _h(f"{label}:challenger"),
        "runner_identity_hash": _h(f"{label}:runner"),
        "actual_input_material_set_hash": _h(f"{label}:materials"),
        "ordered_artifact_set_hash": artifact_set,
    }
    issuer = "v159.probe.issuer"
    policy = "v159.probe.policy"
    key_id = "v159.probe.key"
    signature = base64.urlsafe_b64encode(
        hashlib.sha512(f"v159-signature:{label}".encode("utf-8")).digest()
    ).decode("ascii").rstrip("=")
    observation = {
        "source_head": _h(f"{label}:source-head")[:40],
        "actual_inputs": {
            "dataset_hash": payload["dataset_hash"],
            "row_ids_hash": payload["row_ids_hash"],
            "split_hash": payload["split_hash"],
            "code_manifest_hash": receipt["p_code_manifest_hash"],
            "training_config_hash": receipt["p_training_config_hash"],
            "feature_schema_hash": payload["feature_schema_hash"],
            "label_schema_hash": payload["label_schema_hash"],
            "training_rows": payload["training_rows"],
        },
        "model": {
            "model_schema_version": "v159_fixture_1",
            "metrics_hash": _h(f"{label}:metrics"),
            "resource_usage_hash": _h(f"{label}:resources"),
        },
        "fit_started_at": times["fit_started_at"],
        "fit_completed_at": times["fit_completed_at"],
        "artifacts": {
            "q10": {"artifact_hash": q10, "artifact_size_bytes": 101},
            "q50": {"artifact_hash": q50, "artifact_size_bytes": 102},
            "q90": {"artifact_hash": q90, "artifact_size_bytes": 103},
        },
    }
    projection = {
        "schema_version": "alr_fit_execution_signed_receipt_v1",
        "evidence_tier": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "claim_kind": "ALR_FIT_EXECUTION_ATTESTATION_V1",
        "authentication_status": "SIGNATURE_VERIFIED_BY_TRUST_POLICY",
        "subject": subject,
        "claims": {
            "actual_inputs_consumed": True,
            "actual_fit_executed": True,
            "model_training_performed": True,
            "artifact_readback_completed": True,
            "onnx_semantic_validation_passed": True,
        },
        "result_observation": observation,
        "authentication": {
            "issuer_id": issuer,
            "trust_policy_id": policy,
            "signature_key_id": key_id,
            "signature_algorithm": "ed25519",
            "signature": signature,
        },
        "verified_at": times["verified_at"],
        "expires_at": times["expires_at"],
        "no_authority": deepcopy(_NO_AUTHORITY),
        "authority_counters": deepcopy(_ZERO_COUNTERS),
    }
    signed_bytes, digest = _canonical_pg_jsonb_bytes(admin, projection)
    attest = {
        "p_signed_receipt_bytes": signed_bytes,
        "p_receipt_projection": projection,
        "p_durable_receipt_hash": subject["durable_receipt_hash"],
        "p_training_key_hash": subject["training_key_hash"],
        "p_structural_result_hash": subject["result_hash"],
        "p_structural_fit_capture_hash": subject["fit_capture_hash"],
        "p_structural_candidate_hash": subject["candidate_attestation_hash"],
        "p_structural_training_run_hash": subject["training_run_hash"],
        "p_structural_challenger_hash": subject["challenger_hash"],
        "p_runner_identity_hash": subject["runner_identity_hash"],
        "p_actual_input_material_set_hash": subject["actual_input_material_set_hash"],
        "p_ordered_artifact_set_hash": subject["ordered_artifact_set_hash"],
        "p_issuer_id": issuer,
        "p_trust_policy_id": policy,
        "p_signature_key_id": key_id,
        "p_signature_algorithm": "ed25519",
        "p_verified_at": times["verified_at"],
        "p_expires_at": times["expires_at"],
    }
    durable_hash = _expected_durable_attestation_hash(attest, digest)
    bind = {
        "p_durable_attestation_hash": durable_hash,
        "p_source_head": observation["source_head"],
        "p_actual_dataset_hash": observation["actual_inputs"]["dataset_hash"],
        "p_actual_row_ids_hash": observation["actual_inputs"]["row_ids_hash"],
        "p_actual_split_hash": observation["actual_inputs"]["split_hash"],
        "p_actual_code_manifest_hash": observation["actual_inputs"]["code_manifest_hash"],
        "p_actual_training_config_hash": observation["actual_inputs"]["training_config_hash"],
        "p_actual_feature_schema_hash": observation["actual_inputs"]["feature_schema_hash"],
        "p_actual_label_schema_hash": observation["actual_inputs"]["label_schema_hash"],
        "p_model_schema_version": observation["model"]["model_schema_version"],
        "p_actual_training_rows": observation["actual_inputs"]["training_rows"],
        "p_metrics_hash": observation["model"]["metrics_hash"],
        "p_resource_usage_hash": observation["model"]["resource_usage_hash"],
        "p_fit_started_at": observation["fit_started_at"],
        "p_fit_completed_at": observation["fit_completed_at"],
        "p_q10_hash": q10,
        "p_q10_size": 101,
        "p_q50_hash": q50,
        "p_q50_size": 102,
        "p_q90_hash": q90,
        "p_q90_size": 103,
    }
    return {
        "qualified_receipt": receipt,
        "attest": attest,
        "bind": bind,
        "read": {
            "p_durable_attestation_hash": durable_hash,
            "p_structural_training_run_hash": subject["training_run_hash"],
        },
        "durable_attestation_hash": durable_hash,
        "external_receipt_digest": digest,
    }


def _assert_bundle_snapshot(
    admin: Any, durable_attestation_hash: str, structural_training_run_hash: str
) -> dict[str, Any]:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT jsonb_build_object("
            "'attestations',(SELECT jsonb_agg(to_jsonb(a)-'signed_receipt_bytes'-'receipt_projection' ORDER BY a.durable_attestation_hash) FROM learning.alr_challenger_fit_attestations a WHERE a.durable_attestation_hash=%s OR a.structural_training_run_hash=%s),"
            "'runs',(SELECT jsonb_agg(to_jsonb(r) ORDER BY r.training_run_hash) FROM learning.alr_challenger_training_runs r WHERE r.durable_attestation_hash=%s OR r.training_run_hash=%s),"
            "'artifacts',(SELECT jsonb_agg(to_jsonb(m) ORDER BY m.quantile) FROM learning.alr_challenger_model_artifacts m WHERE m.durable_attestation_hash=%s OR m.training_run_hash=%s),"
            "'registry',(SELECT jsonb_agg(to_jsonb(g) ORDER BY g.training_run_hash) FROM learning.alr_challenger_registry g WHERE g.durable_attestation_hash=%s OR g.training_run_hash=%s)) AS snapshot",
            (
                durable_attestation_hash, structural_training_run_hash,
                durable_attestation_hash, structural_training_run_hash,
                durable_attestation_hash, structural_training_run_hash,
                durable_attestation_hash, structural_training_run_hash,
            ),
        )
        row = cursor.fetchone()
    if not row or "snapshot" not in row:
        raise ProbeFailure("V159 bundle snapshot returned no row")
    return _normalized(row["snapshot"])


def _require_fields(
    actual: Mapping[str, Any], expected: Mapping[str, Any], label: str
) -> None:
    observed = {name: actual.get(name) for name in expected}
    if observed != dict(expected):
        raise ProbeFailure(f"exact persisted {label} fields differ")


def _assert_exact_bound_bundle(
    admin: Any,
    fixture: Mapping[str, Any],
    bind_result: Mapping[str, Any],
    read_result: Mapping[str, Any],
) -> tuple[str, str]:
    bound_at = bind_result.get("attestation_bound_at")
    durable_run = _expected_durable_training_run_hash(fixture, bound_at)
    durable_challenger = _expected_durable_challenger_hash(fixture, durable_run)
    if any(
        payload.get("durable_training_run_hash") != durable_run
        or payload.get("durable_challenger_hash") != durable_challenger
        for payload in (bind_result, read_result)
    ):
        raise ProbeFailure(
            "DURABLE_TRAINING_RUN_HASH_PARITY or "
            "DURABLE_CHALLENGER_HASH_PARITY failed"
        )
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT to_jsonb(r) AS run,"
            "(SELECT jsonb_agg(to_jsonb(m) ORDER BY CASE m.quantile "
            "WHEN 'q10' THEN 1 WHEN 'q50' THEN 2 ELSE 3 END) "
            "FROM learning.alr_challenger_model_artifacts m "
            "WHERE m.training_run_hash=r.training_run_hash) AS artifacts,"
            "to_jsonb(g) AS registry "
            "FROM learning.alr_challenger_training_runs r "
            "JOIN learning.alr_challenger_registry g "
            "ON g.training_run_hash=r.training_run_hash "
            "WHERE r.durable_attestation_hash=%s",
            (fixture["durable_attestation_hash"],),
        )
        row = cursor.fetchone()
    if not row:
        raise ProbeFailure("exact bound bundle query returned no row")
    persisted = _normalized(row)
    run = persisted["run"]
    artifacts = persisted["artifacts"]
    registry = persisted["registry"]
    if (
        run != read_result.get("run")
        or artifacts != read_result.get("artifacts")
        or registry != read_result.get("registry")
        or artifacts != bind_result.get("artifacts")
    ):
        raise ProbeFailure("bind/read/persisted bundle projections differ")

    bind = fixture["bind"]
    attest = fixture["attest"]
    _require_fields(
        run,
        {
            "training_run_hash": attest["p_structural_training_run_hash"],
            "durable_receipt_hash": attest["p_durable_receipt_hash"],
            "training_key_hash": attest["p_training_key_hash"],
            "source_head": bind["p_source_head"],
            "actual_dataset_hash": bind["p_actual_dataset_hash"],
            "actual_row_ids_hash": bind["p_actual_row_ids_hash"],
            "actual_split_hash": bind["p_actual_split_hash"],
            "actual_code_manifest_hash": bind["p_actual_code_manifest_hash"],
            "actual_training_config_hash": bind["p_actual_training_config_hash"],
            "actual_feature_schema_hash": bind["p_actual_feature_schema_hash"],
            "actual_label_schema_hash": bind["p_actual_label_schema_hash"],
            "model_schema_version": bind["p_model_schema_version"],
            "actual_training_rows": bind["p_actual_training_rows"],
            "model_artifact_set_hash": attest["p_ordered_artifact_set_hash"],
            "metrics_hash": bind["p_metrics_hash"],
            "resource_usage_hash": bind["p_resource_usage_hash"],
            "run_status": "TRAINING_PERFORMED",
            "model_training_performed": True,
            "no_authority": _NO_AUTHORITY,
            "authority_counters": _ZERO_COUNTERS,
            "durable_attestation_hash": fixture["durable_attestation_hash"],
            "durable_training_run_hash": durable_run,
            "canonical_payload": {
                "schema_version": "alr_challenger_training_result_v2",
                "structural_training_run_hash": attest["p_structural_training_run_hash"],
                "durable_training_run_hash": durable_run,
                "durable_attestation_hash": fixture["durable_attestation_hash"],
                "structural_result_hash": attest["p_structural_result_hash"],
                "structural_fit_capture_hash": attest["p_structural_fit_capture_hash"],
                "structural_candidate_hash": attest["p_structural_candidate_hash"],
                "run_status": "TRAINING_PERFORMED",
                "model_training_performed": True,
                "attestation_bound_at": run["attestation_bound_at"],
                "no_authority": _NO_AUTHORITY,
                "authority_counters": _ZERO_COUNTERS,
            },
        },
        "run",
    )
    for actual_time, expected_time in (
        (run["fit_started_at"], bind["p_fit_started_at"]),
        (run["fit_completed_at"], bind["p_fit_completed_at"]),
        (run["attestation_verified_at"], attest["p_verified_at"]),
        (run["attestation_expires_at"], attest["p_expires_at"]),
        (run["attestation_bound_at"], bound_at),
    ):
        if _utc_six_digit_z(actual_time) != _utc_six_digit_z(expected_time):
            raise ProbeFailure("exact persisted run time differs")

    if [artifact.get("quantile") for artifact in artifacts] != ["q10", "q50", "q90"]:
        raise ProbeFailure("persisted artifact order differs")
    for quantile in ("q10", "q50", "q90"):
        artifact = artifacts[("q10", "q50", "q90").index(quantile)]
        _require_fields(
            artifact,
            {
                "artifact_hash": bind[f"p_{quantile}_hash"],
                "artifact_size_bytes": bind[f"p_{quantile}_size"],
                "artifact_path": f"runs/structural/{attest['p_structural_training_run_hash']}/{quantile}.onnx",
                "quantile": quantile,
                "artifact_format": "onnx",
                "training_run_hash": attest["p_structural_training_run_hash"],
                "training_key_hash": attest["p_training_key_hash"],
                "model_artifact_set_hash": attest["p_ordered_artifact_set_hash"],
                "feature_schema_hash": bind["p_actual_feature_schema_hash"],
                "model_schema_version": bind["p_model_schema_version"],
                "symlink_created": False,
                "serving_visible": False,
                "durable_attestation_hash": fixture["durable_attestation_hash"],
                "durable_training_run_hash": durable_run,
            },
            f"artifact {quantile}",
        )
    _require_fields(
        registry,
        {
            "challenger_hash": attest["p_structural_challenger_hash"],
            "training_run_hash": attest["p_structural_training_run_hash"],
            "training_key_hash": attest["p_training_key_hash"],
            "model_artifact_set_hash": attest["p_ordered_artifact_set_hash"],
            "registry_status": "NOT_SERVING",
            "serving_allowed": False,
            "promotion_allowed": False,
            "latest_pointer_allowed": False,
            "symlink_allowed": False,
            "durable_attestation_hash": fixture["durable_attestation_hash"],
            "durable_training_run_hash": durable_run,
            "durable_challenger_hash": durable_challenger,
            "canonical_payload": {
                "schema_version": "alr_challenger_registry_entry_v2",
                "structural_challenger_hash": attest["p_structural_challenger_hash"],
                "durable_challenger_hash": durable_challenger,
                "durable_training_run_hash": durable_run,
                "durable_attestation_hash": fixture["durable_attestation_hash"],
                "registry_status": "NOT_SERVING",
                "serving_allowed": False,
                "promotion_allowed": False,
                "latest_pointer_allowed": False,
                "symlink_allowed": False,
            },
        },
        "registry",
    )
    if _utc_six_digit_z(registry["attestation_bound_at"]) != _utc_six_digit_z(bound_at):
        raise ProbeFailure("exact registry bound time differs")
    return durable_run, durable_challenger


def _connect_as_role(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    role: str,
    *,
    destructive_ack: bool,
) -> Any:
    if not destructive_ack:
        raise ProbeFailure(
            "role-session creation requires the explicit destructive ack"
        )
    if role not in (
        _ATTESTOR_CALLER, _TRAINER_CALLER, _ATTESTOR, _WRITER, *_GENERIC_ROLES
    ):
        raise ProbeFailure(f"role is outside the fixed V159 probe surface: {role}")
    connection = _connect(admin_parameters)
    try:
        if _target_identity(connection) != dict(expected_target):
            raise ProbeFailure("role-session target differs from migration preflight")
        connection.rollback()
        connection.autocommit = True
        with connection.cursor() as cursor:
            if role == _ATTESTOR_CALLER:
                cursor.execute("SET SESSION AUTHORIZATION alr_challenger_fit_attestor_caller")
            elif role == _TRAINER_CALLER:
                cursor.execute("SET SESSION AUTHORIZATION alr_challenger_trainer_caller")
            elif role == _ATTESTOR:
                cursor.execute("SET SESSION AUTHORIZATION alr_challenger_fit_attestor")
            elif role == _WRITER:
                cursor.execute("SET SESSION AUTHORIZATION alr_challenger_writer")
            elif role == "trading_ai":
                cursor.execute("SET SESSION AUTHORIZATION trading_ai")
            else:
                cursor.execute("SET SESSION AUTHORIZATION alr_shadow")
        _configure_v159_session(connection)
        connection.autocommit = False
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT session_user AS session_user,current_user AS current_user,"
                "current_setting('TimeZone') AS timezone,"
                "current_setting('default_transaction_isolation') AS isolation"
            )
            identity = cursor.fetchone()
        if identity != {
            "session_user": role,
            "current_user": role,
            "timezone": "UTC",
            "isolation": "read committed",
        }:
            raise ProbeFailure(f"role-session identity mismatch for {role}")
        return connection
    except Exception:
        connection.close()
        raise


def _orchestrate_migrations(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    v158: bytes,
    v159: bytes,
) -> str:
    _apply_migration(admin_parameters, v158, expected_target, "V158", 1)
    _apply_migration(admin_parameters, v159, expected_target, "V159", 1)
    admin = _connect(admin_parameters)
    try:
        if _target_identity(admin) != dict(expected_target):
            raise ProbeFailure("target changed after first V159 apply")
        first = _schema_digest(admin)
    finally:
        admin.close()
    _apply_migration(admin_parameters, v159, expected_target, "V159", 2)
    admin = _connect(admin_parameters)
    try:
        if _target_identity(admin) != dict(expected_target):
            raise ProbeFailure("target changed after V159 replay")
        second = _schema_digest(admin)
    finally:
        admin.close()
    if second != first:
        raise ProbeFailure("exact second V159 apply changed the schema fingerprint")
    return second


def _attestation_row_identity(admin: Any, durable_hash: str) -> dict[str, Any]:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT xmin::text AS xmin,ctid::text AS ctid,created_at,"
            "to_jsonb(a)-'signed_receipt_bytes'-'receipt_projection' AS row "
            "FROM learning.alr_challenger_fit_attestations a "
            "WHERE durable_attestation_hash=%s",
            (durable_hash,),
        )
        row = cursor.fetchone()
    if not row:
        raise ProbeFailure("V159 attestation identity row is missing")
    return _normalized(row)


def _assert_happy_bundle(admin: Any, fixture: Mapping[str, Any]) -> None:
    durable_hash = fixture["durable_attestation_hash"]
    structural_run = fixture["read"]["p_structural_training_run_hash"]
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT "
            "(SELECT count(*) FROM learning.alr_challenger_fit_attestations WHERE durable_attestation_hash=%s) AS attestations,"
            "(SELECT count(*) FROM learning.alr_challenger_training_runs WHERE durable_attestation_hash=%s AND training_run_hash=%s) AS runs,"
            "(SELECT count(*) FROM learning.alr_challenger_model_artifacts WHERE durable_attestation_hash=%s AND training_run_hash=%s) AS artifacts,"
            "(SELECT count(*) FROM learning.alr_challenger_registry WHERE durable_attestation_hash=%s AND training_run_hash=%s) AS registry,"
            "(SELECT count(*) FROM learning.alr_challenger_fit_attestations WHERE durable_attestation_hash=%s AND no_authority=%s::jsonb AND authority_counters=%s::jsonb AND authority_counters->>'model_fit_count'='0') AS fixed_attestation,"
            "(SELECT count(*) FROM learning.alr_challenger_training_runs WHERE durable_attestation_hash=%s AND no_authority=%s::jsonb AND authority_counters=%s::jsonb AND authority_counters->>'model_fit_count'='0' AND model_training_performed IS TRUE) AS fixed_run,"
            "(SELECT count(*) FROM learning.alr_challenger_model_artifacts WHERE durable_attestation_hash=%s AND artifact_format='onnx' AND artifact_path='runs/structural/'||training_run_hash||'/'||quantile||'.onnx' AND symlink_created IS FALSE AND serving_visible IS FALSE) AS fixed_artifacts,"
            "(SELECT count(*) FROM learning.alr_challenger_registry WHERE durable_attestation_hash=%s AND registry_status='NOT_SERVING' AND serving_allowed IS FALSE AND promotion_allowed IS FALSE AND latest_pointer_allowed IS FALSE AND symlink_allowed IS FALSE) AS fixed_registry",
            (
                durable_hash, durable_hash, structural_run,
                durable_hash, structural_run, durable_hash, structural_run,
                durable_hash, _adapt(_NO_AUTHORITY), _adapt(_ZERO_COUNTERS),
                durable_hash, _adapt(_NO_AUTHORITY), _adapt(_ZERO_COUNTERS),
                durable_hash, durable_hash,
            ),
        )
        counts = cursor.fetchone()
    if counts != {
        "attestations": 1,
        "runs": 1,
        "artifacts": 3,
        "registry": 1,
        "fixed_attestation": 1,
        "fixed_run": 1,
        "fixed_artifacts": 3,
        "fixed_registry": 1,
    }:
        raise ProbeFailure("BUNDLE_1_3_1 or NO_AUTHORITY_FALSE_ZERO failed")


def _scenario_happy_path(
    admin: Any, trainer_caller: Any, attestor_caller: Any, markers: set[str]
) -> dict[str, Any]:
    receipt = _persist_qualified_receipt(admin, trainer_caller, "happy")
    fixture = _attestation_fixture(
        admin, receipt, "happy", expiry_seconds=12.0
    )
    missing = _call(trainer_caller, _FUNCTIONS["read"], fixture["read"])
    trainer_caller.commit()
    if missing != {"status": "NOT_FOUND", "state": "NOT_FOUND"}:
        raise ProbeFailure("V159 missing read was not exact")

    first_attestation = _call(
        attestor_caller, _FUNCTIONS["attest"], fixture["attest"]
    )
    attestor_caller.commit()
    replay_attestation = _call(
        attestor_caller, _FUNCTIONS["attest"], fixture["attest"]
    )
    attestor_caller.commit()
    if (
        first_attestation.get("status") != "PERSISTED"
        or replay_attestation.get("status") != "DUPLICATE"
        or first_attestation.get("durable_attestation_hash")
        != fixture["durable_attestation_hash"]
        or replay_attestation.get("durable_attestation_hash")
        != fixture["durable_attestation_hash"]
        or first_attestation.get("external_receipt_digest")
        != fixture["external_receipt_digest"]
        or replay_attestation.get("external_receipt_digest")
        != fixture["external_receipt_digest"]
    ):
        raise ProbeFailure("DURABLE_ATTESTATION_HASH_PARITY failed")
    markers.add("BYTE_SHA256_DB_PYTHON_PARITY")
    markers.add("DURABLE_ATTESTATION_HASH_PARITY")

    prebind = _call(trainer_caller, _FUNCTIONS["read"], fixture["read"])
    trainer_caller.commit()
    expected_base64 = base64.b64encode(
        fixture["attest"]["p_signed_receipt_bytes"]
    ).decode("ascii").replace("\n", "")
    if (
        prebind.get("status") != "FOUND"
        or prebind.get("state") != "ATTESTED_UNBOUND"
        or prebind.get("external_receipt_digest")
        != fixture["external_receipt_digest"]
        or prebind.get("signed_receipt_bytes_base64") != expected_base64
        or base64.b64decode(prebind["signed_receipt_bytes_base64"], validate=True)
        != fixture["attest"]["p_signed_receipt_bytes"]
        or _normalized(prebind.get("receipt_projection"))
        != _normalized(fixture["attest"]["p_receipt_projection"])
    ):
        raise ProbeFailure("BYTE_EXACT_READBACK failed before bind")
    markers.add("BYTE_EXACT_READBACK")

    attestation_before = _attestation_row_identity(
        admin, fixture["durable_attestation_hash"]
    )
    first_bind = _call(trainer_caller, _FUNCTIONS["bind"], fixture["bind"])
    trainer_caller.commit()
    replay_bind = _call(trainer_caller, _FUNCTIONS["bind"], fixture["bind"])
    trainer_caller.commit()
    if first_bind.get("status") != "PERSISTED" or replay_bind.get("status") != "DUPLICATE":
        raise ProbeFailure("V159 bind replay status mismatch")
    if {
        key: value for key, value in first_bind.items() if key != "status"
    } != {key: value for key, value in replay_bind.items() if key != "status"}:
        raise ProbeFailure("V159 bind replay changed server-owned state")
    postbind = _call(trainer_caller, _FUNCTIONS["read"], fixture["read"])
    trainer_caller.commit()
    if (
        postbind.get("status") != "FOUND"
        or postbind.get("state") != "BOUND_COMPLETE"
        or postbind.get("external_receipt_digest")
        != fixture["external_receipt_digest"]
        or postbind.get("structural_training_run_hash")
        != fixture["read"]["p_structural_training_run_hash"]
        or postbind.get("durable_training_run_hash")
        == postbind.get("structural_training_run_hash")
        or postbind.get("durable_challenger_hash")
        == postbind.get("structural_challenger_hash")
        or postbind.get("signed_receipt_bytes_base64") != expected_base64
        or postbind.get("attestation_bound_at")
        != postbind["run"].get("attestation_bound_at")
        or postbind.get("attestation_bound_at")
        != postbind["registry"].get("attestation_bound_at")
    ):
        raise ProbeFailure("V159 bound readback identity mismatch")
    durable_run, durable_challenger = _assert_exact_bound_bundle(
        admin, fixture, first_bind, postbind
    )
    if (
        durable_run != first_bind.get("durable_training_run_hash")
        or durable_challenger != first_bind.get("durable_challenger_hash")
    ):
        raise ProbeFailure("independent durable bundle identity mismatch")
    markers.add("DURABLE_TRAINING_RUN_HASH_PARITY")
    markers.add("DURABLE_CHALLENGER_HASH_PARITY")
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT verified_at<=attestation_bound_at AND attestation_bound_at<expires_at AS exact "
            "FROM learning.alr_challenger_training_runs WHERE durable_attestation_hash=%s",
            (fixture["durable_attestation_hash"],),
        )
        if cursor.fetchone() != {"exact": True}:
            raise ProbeFailure("V159 database-owned bind time is invalid")
    _assert_happy_bundle(admin, fixture)
    markers.add("BUNDLE_1_3_1")
    markers.add("NO_AUTHORITY_FALSE_ZERO")
    if _attestation_row_identity(admin, fixture["durable_attestation_hash"]) != attestation_before:
        raise ProbeFailure("ADVISORY_BIND_WITHOUT_UPDATE failed")
    markers.add("ADVISORY_BIND_WITHOUT_UPDATE")
    fixture["attestation_duplicate_response"] = replay_attestation
    fixture["bound_response"] = first_bind
    return fixture


def _mutated_bind_value(field_name: str, original: Mapping[str, Any]) -> Any:
    if field_name == "p_actual_training_rows":
        return int(original[field_name]) + 1
    if field_name.endswith("_size"):
        return int(original[field_name]) + 1
    if field_name == "p_fit_started_at":
        return "2000-01-01T00:00:00.000000Z"
    if field_name == "p_fit_completed_at":
        return original["p_fit_started_at"]
    if field_name == "p_source_head":
        return _h(f"mutation:{field_name}")[:40]
    if field_name == "p_model_schema_version":
        return "v159_fixture_mutated"
    return _h(f"mutation:{field_name}")


def _scenario_signed_field_mutations(
    admin: Any,
    trainer_caller: Any,
    attestor_caller: Any,
    fixture: Mapping[str, Any],
    markers: set[str],
) -> None:
    baseline = _assert_bundle_snapshot(
        admin,
        fixture["durable_attestation_hash"],
        fixture["read"]["p_structural_training_run_hash"],
    )
    divergent = _attestation_fixture(
        admin,
        fixture["qualified_receipt"],
        "divergent",
        expiry_seconds=12.0,
    )
    _expect_db_error(
        attestor_caller,
        _FUNCTIONS["attest"],
        divergent["attest"],
        "P0001",
        "V159 attestation replay conflict",
    )
    if _assert_bundle_snapshot(
        admin,
        fixture["durable_attestation_hash"],
        fixture["read"]["p_structural_training_run_hash"],
    ) != baseline:
        raise ProbeFailure("DIVERGENT_ATTESTATION_REPLAY_CONFLICT changed state")
    markers.add("DIVERGENT_ATTESTATION_REPLAY_CONFLICT")
    for field_name in _SIGNED_ATTESTATION_FIELDS:
        changed_attestation = deepcopy(fixture["attest"])
        if field_name == "p_signature_algorithm":
            changed_attestation[field_name] = "ecdsa-p256-sha256"
        elif field_name == "p_verified_at":
            changed_attestation[field_name] = "2000-01-01T00:00:00.000000Z"
        elif field_name == "p_expires_at":
            changed_attestation[field_name] = "3000-01-01T00:00:00.000000Z"
        elif field_name in {"p_issuer_id", "p_trust_policy_id", "p_signature_key_id"}:
            changed_attestation[field_name] = f"v159.mutated.{field_name[2:]}"
        else:
            changed_attestation[field_name] = _h(
                f"attestation-mutation:{field_name}"
            )
        _expect_db_error(
            attestor_caller,
            _FUNCTIONS["attest"],
            changed_attestation,
            "P0001",
            "V159 signed receipt bytes/projection/claim mismatch",
        )
        if _assert_bundle_snapshot(
            admin,
            fixture["durable_attestation_hash"],
            fixture["read"]["p_structural_training_run_hash"],
        ) != baseline:
            raise ProbeFailure(
                f"signed attestation mutation changed bundle: {field_name}"
            )
    markers.add("ATTESTATION_SIGNED_ARG_PARITY")

    lineage = {
        "p_actual_dataset_hash", "p_actual_row_ids_hash", "p_actual_split_hash",
        "p_actual_code_manifest_hash", "p_actual_training_config_hash",
        "p_actual_feature_schema_hash", "p_actual_label_schema_hash",
        "p_actual_training_rows",
    }
    artifact_hashes = {"p_q10_hash", "p_q50_hash", "p_q90_hash"}
    for field_name in _SIGNED_AND_PERSISTED_FIELDS:
        changed = dict(fixture["bind"])
        changed[field_name] = _mutated_bind_value(field_name, fixture["bind"])
        if field_name in lineage:
            message = "V159 exact qualified receipt lineage mismatch"
        elif field_name in artifact_hashes:
            message = "V159 result v2 artifact/fit mismatch"
        else:
            message = "V159 caller result differs from signed observation"
        _expect_db_error(
            trainer_caller, _FUNCTIONS["bind"], changed, "P0001", message
        )
        current = _assert_bundle_snapshot(
            admin,
            fixture["durable_attestation_hash"],
            fixture["read"]["p_structural_training_run_hash"],
        )
        if current != baseline:
            raise ProbeFailure(f"signed bind mutation changed bundle: {field_name}")
    markers.add("SIGNED_ALL_ARG_PARITY")


def _check_violation(constraint: str) -> str:
    return (
        'new row for relation "alr_challenger_fit_attestations" violates '
        f'check constraint "{constraint}"'
    )


def _malformed_attestation_arguments(
    admin: Any, fixture: Mapping[str, Any], malformed_case: str
) -> tuple[dict[str, Any], str, str]:
    arguments = deepcopy(fixture["attest"])
    projection: Any = deepcopy(arguments["p_receipt_projection"])
    observation = projection["result_observation"]
    inputs = observation["actual_inputs"]
    artifacts = observation["artifacts"]
    sqlstate, message = "P0001", "V159 signed receipt bytes/projection/claim mismatch"
    if malformed_case == "root_missing":
        del projection["schema_version"]
        sqlstate, message = "23514", _check_violation("alr_fit_attestations_evidence_check")
    elif malformed_case == "root_extra":
        projection["unexpected"] = False
        sqlstate, message = "23514", _check_violation("alr_fit_attestations_evidence_check")
    elif malformed_case == "wrong_root_type":
        projection = []
    elif malformed_case == "subject_missing":
        del projection["subject"]["result_hash"]
    elif malformed_case == "claims_false":
        projection["claims"]["actual_fit_executed"] = False
    elif malformed_case == "actual_inputs_extra":
        projection["result_observation"]["actual_inputs"]["unexpected"] = "x"
        message = "V159 actual_input fields/type mismatch"
    elif malformed_case == "model_scalar":
        projection["result_observation"]["model"] = "invalid"
        message = "V159 model observation fields/type mismatch"
    elif malformed_case == "artifacts_missing":
        del projection["result_observation"]["artifacts"]["q90"]
        message = "V159 artifact observation fields/type mismatch"
    elif malformed_case == "bytes_mismatch":
        arguments["p_signed_receipt_bytes"] += b"x"
        return arguments, sqlstate, message
    elif malformed_case == "signature_bad":
        projection["authentication"]["signature"] = "bad"
        sqlstate, message = "23514", _check_violation("alr_fit_attestations_evidence_check")
    elif malformed_case == "evidence_tier_bad":
        projection["evidence_tier"] = "SELF_REPORTED"
    elif malformed_case == "claim_kind_bad":
        projection["claim_kind"] = "OTHER"
    elif malformed_case == "authentication_status_bad":
        projection["authentication_status"] = "UNVERIFIED"
    elif malformed_case == "issuer_id_bad":
        projection["authentication"]["issuer_id"] = "other.issuer"
    elif malformed_case == "policy_id_bad":
        projection["authentication"]["trust_policy_id"] = "other.policy"
    elif malformed_case == "signature_key_id_bad":
        projection["authentication"]["signature_key_id"] = "other.key"
    elif malformed_case == "algorithm_bad":
        projection["authentication"]["signature_algorithm"] = "rsa"
    elif malformed_case == "no_authority_true":
        projection["no_authority"]["exchange_authority"] = True
    elif malformed_case == "counter_nonzero":
        projection["authority_counters"]["model_fit_count"] = 1
    elif malformed_case == "hash_bad":
        projection["subject"]["result_hash"] = "g" * 64
        arguments["p_structural_result_hash"] = "g" * 64
        sqlstate, message = "23514", _check_violation("alr_fit_attestations_hashes_check")
    elif malformed_case == "lineage_bad":
        projection["result_observation"]["actual_inputs"]["dataset_hash"] = _h("bad-lineage")
        message = "V159 signed observation differs from qualified receipt"
    elif malformed_case == "artifact_set_bad":
        bad_set = _h("bad-artifact-set")
        projection["subject"]["ordered_artifact_set_hash"] = bad_set
        arguments["p_ordered_artifact_set_hash"] = bad_set
        message = "V159 signed observation artifact set mismatch"
    elif malformed_case == "training_rows_string":
        inputs["training_rows"] = "not-an-integer"
        sqlstate, message = "22P02", "SQLSTATE_ONLY"
    elif malformed_case == "training_rows_zero":
        inputs["training_rows"] = 0
        message = "V159 signed observation differs from qualified receipt"
    elif malformed_case == "training_rows_fraction":
        inputs["training_rows"] = 12.5
        sqlstate, message = "22P02", "SQLSTATE_ONLY"
    elif malformed_case == "training_rows_overflow":
        inputs["training_rows"] = 2147483648
        sqlstate, message = "22003", "SQLSTATE_ONLY"
    elif malformed_case.startswith("artifact_size_"):
        artifacts["q10"]["artifact_size_bytes"] = {
            "artifact_size_zero": 0,
            "artifact_size_string": "101",
            "artifact_size_fraction": 101.5,
            "artifact_size_overflow": 9223372036854775808,
        }[malformed_case]
        sqlstate, message = "23514", _check_violation(
            "alr_fit_attestations_evidence_check"
        )
    elif malformed_case == "duplicate_q_hash":
        artifacts["q90"]["artifact_hash"] = artifacts["q10"]["artifact_hash"]
        message = "V159 artifact observation fields/type mismatch"
    elif malformed_case == "q_object_extra":
        artifacts["q10"]["unexpected"] = False
        sqlstate, message = "23514", _check_violation(
            "alr_fit_attestations_evidence_check"
        )
    elif malformed_case == "q_object_scalar":
        artifacts["q10"] = "invalid"
        message = "V159 signed observation artifact set mismatch"
    elif malformed_case == "fit_completed_after_verified":
        observation["fit_completed_at"] = "2998-01-01T00:00:00.000000Z"
        message = "V159 fit observation ordering mismatch"
    elif malformed_case == "verified_not_before_expires":
        projection["expires_at"] = projection["verified_at"]
        arguments["p_expires_at"] = arguments["p_verified_at"]
        message = "V159 attestation future-dated or expired"
    elif malformed_case == "time_reversed":
        projection["result_observation"]["fit_started_at"] = "2999-01-01T00:00:00.000000Z"
        message = "V159 fit observation ordering mismatch"
    elif malformed_case == "time_future":
        projection["verified_at"] = "2999-01-01T00:00:00.000000Z"
        projection["expires_at"] = "3000-01-01T00:00:00.000000Z"
        arguments["p_verified_at"] = projection["verified_at"]
        arguments["p_expires_at"] = projection["expires_at"]
        message = "V159 attestation future-dated or expired"
    elif malformed_case == "time_expired":
        projection["result_observation"]["fit_started_at"] = "1999-01-01T00:00:00.000000Z"
        projection["result_observation"]["fit_completed_at"] = "1999-01-01T00:00:01.000000Z"
        projection["verified_at"] = "2000-01-01T00:00:00.000000Z"
        projection["expires_at"] = "2001-01-01T00:00:00.000000Z"
        arguments["p_verified_at"] = projection["verified_at"]
        arguments["p_expires_at"] = projection["expires_at"]
        message = "V159 attestation future-dated or expired"
    elif malformed_case == "time_nonfinite":
        projection["expires_at"] = "infinity"
        arguments["p_expires_at"] = "infinity"
        sqlstate, message = "23514", "NONFINITE_TIME_CONSTRAINT"
    else:
        raise ProbeFailure(f"unknown malformed receipt case: {malformed_case}")
    arguments["p_receipt_projection"] = projection
    arguments["p_signed_receipt_bytes"] = _canonical_pg_jsonb_bytes(admin, projection)[0]
    return arguments, sqlstate, message


def _scenario_malformed_receipts(
    admin: Any, trainer_caller: Any, attestor_caller: Any, markers: set[str]
) -> None:
    receipt = _persist_qualified_receipt(admin, trainer_caller, "malformed")
    fixture = _attestation_fixture(admin, receipt, "malformed")
    baseline = _assert_bundle_snapshot(
        admin,
        fixture["durable_attestation_hash"],
        fixture["read"]["p_structural_training_run_hash"],
    )
    provisional = _call(attestor_caller, _FUNCTIONS["attest"], fixture["attest"])
    invisible = _call(trainer_caller, _FUNCTIONS["read"], fixture["read"])
    trainer_caller.commit()
    attestor_caller.rollback()
    absent = _call(trainer_caller, _FUNCTIONS["read"], fixture["read"])
    trainer_caller.commit()
    if (
        provisional.get("status") != "PERSISTED"
        or invisible != {"status": "NOT_FOUND", "state": "NOT_FOUND"}
        or absent != invisible
        or _assert_bundle_snapshot(
            admin,
            fixture["durable_attestation_hash"],
            fixture["read"]["p_structural_training_run_hash"],
        ) != baseline
    ):
        raise ProbeFailure("MALFORMED_VALID_ROLLBACK_NOT_FOUND failed")
    markers.add("MALFORMED_VALID_ROLLBACK_NOT_FOUND")
    executed_cases: set[str] = set()
    for malformed_case in _MALFORMED_RECEIPT_CASES:
        changed, sqlstate, message = _malformed_attestation_arguments(
            admin, fixture, malformed_case
        )
        if malformed_case == "time_nonfinite":
            if (sqlstate, message) != ("23514", "NONFINITE_TIME_CONSTRAINT"):
                raise ProbeFailure("nonfinite case expectation routing drifted")
            _expect_nonfinite_constraint_error(attestor_caller, changed)
        elif message == "SQLSTATE_ONLY":
            _expect_db_sqlstate_only(attestor_caller, changed, sqlstate)
        else:
            _expect_db_error(
                attestor_caller, _FUNCTIONS["attest"], changed, sqlstate, message
            )
        if _assert_bundle_snapshot(
            admin,
            fixture["durable_attestation_hash"],
            fixture["read"]["p_structural_training_run_hash"],
        ) != baseline:
            raise ProbeFailure(f"malformed receipt changed state: {malformed_case}")
        executed_cases.add(malformed_case)
    if executed_cases != set(_MALFORMED_RECEIPT_CASES):
        raise ProbeFailure("malformed case execution accounting differs")
    markers.add("MALFORMED_RECEIPTS_REJECTED")


def _scenario_expiry_replay(
    admin: Any,
    trainer_caller: Any,
    attestor_caller: Any,
    happy_fixture: Mapping[str, Any],
    markers: set[str],
) -> None:
    receipt = _persist_qualified_receipt(admin, trainer_caller, "expiry")
    fixture = _attestation_fixture(
        admin, receipt, "expiry", expiry_seconds=6.0
    )
    persisted = _call(attestor_caller, _FUNCTIONS["attest"], fixture["attest"])
    attestor_caller.commit()
    if persisted.get("status") != "PERSISTED":
        raise ProbeFailure("expiry fixture attestation was not persisted")
    bound_before = _assert_bundle_snapshot(
        admin,
        happy_fixture["durable_attestation_hash"],
        happy_fixture["read"]["p_structural_training_run_hash"],
    )
    bound_identity_before = _attestation_row_identity(
        admin, happy_fixture["durable_attestation_hash"]
    )
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT pg_sleep(GREATEST(0,extract(epoch FROM "
            "(GREATEST(%s::timestamptz,%s::timestamptz)-"
            "statement_timestamp())))+0.20)",
            (
                happy_fixture["attest"]["p_expires_at"],
                fixture["attest"]["p_expires_at"],
            ),
        )
    bound_attestation_replay = _call(
        attestor_caller, _FUNCTIONS["attest"], happy_fixture["attest"]
    )
    attestor_caller.commit()
    if bound_attestation_replay != happy_fixture["attestation_duplicate_response"]:
        raise ProbeFailure("bound expired attestation replay changed response")
    bound_result_replay = _call(
        trainer_caller, _FUNCTIONS["bind"], happy_fixture["bind"]
    )
    trainer_caller.commit()
    if (
        bound_result_replay.get("status") != "DUPLICATE"
        or {key: value for key, value in bound_result_replay.items() if key != "status"}
        != {
            key: value
            for key, value in happy_fixture["bound_response"].items()
            if key != "status"
        }
    ):
        raise ProbeFailure("BOUND_EXPIRED_RESULT_REPLAY_DUPLICATE failed")
    markers.add("BOUND_EXPIRED_RESULT_REPLAY_DUPLICATE")
    if (
        _assert_bundle_snapshot(
            admin,
            happy_fixture["durable_attestation_hash"],
            happy_fixture["read"]["p_structural_training_run_hash"],
        ) != bound_before
        or _attestation_row_identity(
            admin, happy_fixture["durable_attestation_hash"]
        ) != bound_identity_before
    ):
        raise ProbeFailure("BOUND_EXPIRED_SNAPSHOT_UNCHANGED failed")
    markers.add("BOUND_EXPIRED_SNAPSHOT_UNCHANGED")

    replay = _call(attestor_caller, _FUNCTIONS["attest"], fixture["attest"])
    attestor_caller.commit()
    if replay.get("status") != "DUPLICATE":
        raise ProbeFailure("EXPIRED_REPLAY_DUPLICATE failed")
    markers.add("EXPIRED_REPLAY_DUPLICATE")
    _expect_db_error(
        trainer_caller,
        _FUNCTIONS["bind"],
        fixture["bind"],
        "P0001",
        "V159 expired or future attestation cannot bind",
    )
    state = _call(trainer_caller, _FUNCTIONS["read"], fixture["read"])
    trainer_caller.commit()
    if state.get("state") != "ATTESTED_UNBOUND":
        raise ProbeFailure("EXPIRED_ORPHAN_BIND_DENIED failed")
    snapshot = _assert_bundle_snapshot(
        admin,
        fixture["durable_attestation_hash"],
        fixture["read"]["p_structural_training_run_hash"],
    )
    if any(snapshot[name] is not None for name in ("runs", "artifacts", "registry")):
        raise ProbeFailure("expired orphan unexpectedly acquired result rows")
    markers.add("EXPIRED_ORPHAN_BIND_DENIED")


def _scenario_rollback_invariants(
    admin: Any, trainer_caller: Any, attestor_caller: Any, markers: set[str]
) -> None:
    receipt = _persist_qualified_receipt(admin, trainer_caller, "rollback")
    fixture = _attestation_fixture(admin, receipt, "rollback")
    persisted = _call(attestor_caller, _FUNCTIONS["attest"], fixture["attest"])
    attestor_caller.commit()
    if persisted.get("status") != "PERSISTED":
        raise ProbeFailure("rollback fixture attestation was not persisted")
    before = _assert_bundle_snapshot(
        admin,
        fixture["durable_attestation_hash"],
        fixture["read"]["p_structural_training_run_hash"],
    )
    provisional = _call(trainer_caller, _FUNCTIONS["bind"], fixture["bind"])
    if provisional.get("status") != "PERSISTED":
        trainer_caller.rollback()
        raise ProbeFailure("rollback fixture did not reach provisional persistence")
    trainer_caller.rollback()
    state = _call(trainer_caller, _FUNCTIONS["read"], fixture["read"])
    trainer_caller.commit()
    after = _assert_bundle_snapshot(
        admin,
        fixture["durable_attestation_hash"],
        fixture["read"]["p_structural_training_run_hash"],
    )
    if state.get("state") != "ATTESTED_UNBOUND" or after != before:
        raise ProbeFailure("ROLLBACK_CANONICAL_UNCHANGED failed")
    markers.add("ROLLBACK_CANONICAL_UNCHANGED")


def _expect_function_sqlstate(
    connection: Any,
    function_name: str,
    arguments: Mapping[str, Any],
    expected_sqlstate: str,
) -> None:
    import psycopg2  # type: ignore

    try:
        _call(connection, function_name, arguments)
    except psycopg2.Error as exc:
        connection.rollback()
        if exc.pgcode != expected_sqlstate:
            raise ProbeFailure(
                f"function denial returned {exc.pgcode}, expected {expected_sqlstate}"
            ) from exc
    else:
        connection.rollback()
        raise ProbeFailure("function denial unexpectedly succeeded")


def _closed_v1_statement(kind: str) -> tuple[str, tuple[Any, ...]]:
    if kind == "write":
        types = (
            *("text",) * 12, "integer", "text", "text", "text",
            "timestamptz", "timestamptz", "text", "text", "bigint",
            "text", "text", "bigint", "text", "text", "bigint", "text",
        )
        placeholders = ",".join(f"%s::{value}" for value in types)
        return (
            "SELECT learning.persist_alr_challenger_training_result_v1("
            f"{placeholders})",
            (None,) * len(types),
        )
    if kind == "read":
        return (
            "SELECT learning.read_alr_challenger_training_result_v1("
            "%s::text,%s::text)",
            (None, None),
        )
    raise ProbeFailure(f"unknown closed V1 call kind: {kind}")


def _assert_direct_dml_denied(connections: Sequence[Any]) -> None:
    for connection in connections:
        for table in _DIRECT_DENIAL_TABLES:
            for statement in (
                f"SELECT 1 FROM learning.{table} LIMIT 0",
                f"INSERT INTO learning.{table} DEFAULT VALUES",
                f"UPDATE learning.{table} SET created_at=created_at WHERE false",
                f"DELETE FROM learning.{table} WHERE false",
            ):
                _expect_statement_error(connection, statement, "42501")


def _scenario_acl_boundaries(
    admin: Any,
    trainer_caller: Any,
    attestor_caller: Any,
    fixture: Mapping[str, Any],
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    destructive_ack: bool,
    markers: set[str],
) -> None:
    closed_write, closed_write_parameters = _closed_v1_statement("write")
    closed_read, closed_read_parameters = _closed_v1_statement("read")
    _expect_statement_error(
        trainer_caller, closed_write, "42501", parameters=closed_write_parameters
    )
    _expect_statement_error(
        trainer_caller, closed_read, "42501", parameters=closed_read_parameters
    )
    markers.add("V1_CALLER_DENIED")

    writer = _connect_as_role(
        admin_parameters, expected_target, _WRITER, destructive_ack=destructive_ack
    )
    attestor_owner = _connect_as_role(
        admin_parameters, expected_target, _ATTESTOR, destructive_ack=destructive_ack
    )
    generics = [
        _connect_as_role(
            admin_parameters, expected_target, role, destructive_ack=destructive_ack
        )
        for role in _GENERIC_ROLES
    ]
    try:
        _expect_statement_error(
            writer,
            closed_write,
            "P0001",
            "V159 closed V158 result writer: durable fit attestation v2 required",
            closed_write_parameters,
        )
        _expect_statement_error(
            writer,
            closed_read,
            "P0001",
            "V159 closed V158 result reader: durable fit attestation v2 required",
            closed_read_parameters,
        )
        markers.add("V1_OWNER_HARDFAIL")
        _expect_db_error(
            writer, _FUNCTIONS["bind"], fixture["bind"], "P0001",
            "V159 result v2 writer session identity rejected",
        )
        _expect_db_error(
            writer, _FUNCTIONS["read"], fixture["read"], "P0001",
            "V159 result v2 reader session identity rejected",
        )
        _expect_db_error(
            attestor_owner, _FUNCTIONS["attest"], fixture["attest"], "P0001",
            "V159 attestation writer session identity rejected",
        )
        markers.add("OWNER_V2_SESSION_IDENTITY_HARDFAIL")

        _expect_function_sqlstate(
            trainer_caller, _FUNCTIONS["attest"], fixture["attest"], "42501"
        )
        _expect_function_sqlstate(
            attestor_caller, _FUNCTIONS["bind"], fixture["bind"], "42501"
        )
        _expect_function_sqlstate(
            attestor_caller, _FUNCTIONS["read"], fixture["read"], "42501"
        )
        markers.add("CROSS_SEAM_DENIED")

        for generic in generics:
            _expect_function_sqlstate(
                generic, _FUNCTIONS["attest"], fixture["attest"], "42501"
            )
            _expect_function_sqlstate(
                generic, _FUNCTIONS["bind"], fixture["bind"], "42501"
            )
            _expect_function_sqlstate(
                generic, _FUNCTIONS["read"], fixture["read"], "42501"
            )
        _assert_direct_dml_denied(
            [trainer_caller, attestor_caller, *generics]
        )
        markers.add("DIRECT_DML_DENIED")

        _expect_statement_error(
            admin,
            "UPDATE learning.alr_challenger_fit_attestations "
            "SET created_at=created_at WHERE durable_attestation_hash=%s",
            "P0001",
            "V159 durable fit attestations are append-only: UPDATE rejected",
            (fixture["durable_attestation_hash"],),
        )
        markers.add("ATTESTATION_UPDATE_DENIED")

        for connection in (
            trainer_caller, attestor_caller, writer, attestor_owner, *generics
        ):
            _expect_statement_error(
                connection,
                "SET LOCAL session_replication_role='replica'",
                "42501",
            )
        markers.add("SESSION_REPLICATION_ROLE_DENIED")
    finally:
        for connection in (writer, attestor_owner, *generics):
            connection.close()


def _run_scenarios(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    *,
    destructive_ack: bool,
) -> dict[str, Any]:
    admin = _connect(admin_parameters)
    trainer_caller = _connect_as_role(
        admin_parameters,
        expected_target,
        _TRAINER_CALLER,
        destructive_ack=destructive_ack,
    )
    attestor_caller = _connect_as_role(
        admin_parameters,
        expected_target,
        _ATTESTOR_CALLER,
        destructive_ack=destructive_ack,
    )
    markers: set[str] = set()
    try:
        if _target_identity(admin) != dict(expected_target):
            raise ProbeFailure("scenario administrator target differs from preflight")
        happy = _scenario_happy_path(
            admin, trainer_caller, attestor_caller, markers
        )
        _scenario_signed_field_mutations(
            admin, trainer_caller, attestor_caller, happy, markers
        )
        _scenario_malformed_receipts(
            admin, trainer_caller, attestor_caller, markers
        )
        _scenario_expiry_replay(
            admin, trainer_caller, attestor_caller, happy, markers
        )
        _scenario_rollback_invariants(
            admin, trainer_caller, attestor_caller, markers
        )
        _scenario_acl_boundaries(
            admin,
            trainer_caller,
            attestor_caller,
            happy,
            admin_parameters,
            expected_target,
            destructive_ack,
            markers,
        )
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT "
                "(SELECT count(*) FROM learning.alr_qualified_training_receipts) AS receipts,"
                "(SELECT count(*) FROM learning.alr_challenger_fit_attestations) AS attestations,"
                "(SELECT count(*) FROM learning.alr_challenger_training_runs) AS runs,"
                "(SELECT count(*) FROM learning.alr_challenger_model_artifacts) AS artifacts,"
                "(SELECT count(*) FROM learning.alr_challenger_registry) AS registry"
            )
            global_counts = cursor.fetchone()
        if global_counts != {
            "receipts": 4,
            "attestations": 3,
            "runs": 1,
            "artifacts": 3,
            "registry": 1,
        }:
            raise ProbeFailure("V159 scenario suite global counts differ")
        required = {
            "BYTE_SHA256_DB_PYTHON_PARITY",
            "DURABLE_ATTESTATION_HASH_PARITY",
            "DURABLE_TRAINING_RUN_HASH_PARITY",
            "DURABLE_CHALLENGER_HASH_PARITY",
            "BYTE_EXACT_READBACK",
            "BUNDLE_1_3_1",
            "NO_AUTHORITY_FALSE_ZERO",
            "SIGNED_ALL_ARG_PARITY",
            "ATTESTATION_SIGNED_ARG_PARITY",
            "DIVERGENT_ATTESTATION_REPLAY_CONFLICT",
            "MALFORMED_VALID_ROLLBACK_NOT_FOUND",
            "MALFORMED_RECEIPTS_REJECTED",
            "EXPIRED_REPLAY_DUPLICATE",
            "BOUND_EXPIRED_RESULT_REPLAY_DUPLICATE",
            "BOUND_EXPIRED_SNAPSHOT_UNCHANGED",
            "EXPIRED_ORPHAN_BIND_DENIED",
            "V1_CALLER_DENIED",
            "V1_OWNER_HARDFAIL",
            "OWNER_V2_SESSION_IDENTITY_HARDFAIL",
            "CROSS_SEAM_DENIED",
            "DIRECT_DML_DENIED",
            "ATTESTATION_UPDATE_DENIED",
            "SESSION_REPLICATION_ROLE_DENIED",
            "ROLLBACK_CANONICAL_UNCHANGED",
            "ADVISORY_BIND_WITHOUT_UPDATE",
        }
        if not required.issubset(markers):
            raise ProbeFailure("V159 scenario marker coverage is incomplete")
        markers.add("SCENARIO_SUITE_COMPLETE")
        return {"markers": sorted(markers), "global_counts": dict(global_counts)}
    finally:
        attestor_caller.close()
        trainer_caller.close()
        admin.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    destructive_ack = (
        args.confirm_disposable_v159 and os.environ.get(_ACK_ENV) == "1"
    )
    if not destructive_ack:
        raise ProbeFailure(
            f"explicit --confirm-disposable-v159 and {_ACK_ENV}=1 are required"
        )
    expected_sentinel = f"{_SENTINEL}:{args.expected_database}"
    if args.disposable_sentinel != expected_sentinel:
        raise ProbeFailure("the exact V159 sentinel suffixed by the database is required")
    if not _DISPOSABLE_DATABASE.search(args.expected_database.lower()):
        raise ProbeFailure(
            "--expected-database must be named ci/test/tmp/scratch/disposable"
        )
    _reject_ambient_libpq_routing()
    v158 = _migration_bytes(args.v158, "V158")
    v159 = _migration_bytes(args.v159, "V159")
    admin_parameters = _parse_complete_dsn(
        _required_env(_ADMIN_DSN_ENV), args.expected_database, "administrator"
    )
    admin = _connect(admin_parameters)
    try:
        identity = _target_identity(admin)
        if identity["database_name"] != args.expected_database:
            raise ProbeFailure("connected database differs from explicit target")
        _seed_v159_role_preconditions(admin, destructive_ack=destructive_ack)
        expected_target = dict(identity)
    finally:
        admin.close()
    fingerprint = _orchestrate_migrations(
        admin_parameters, expected_target, v158, v159
    )
    scenario_summary = _run_scenarios(
        admin_parameters,
        expected_target,
        destructive_ack=destructive_ack,
    )
    output = {
        "schema_version": "alr_v159_disposable_pg_probe_v1",
        "status": "PASS",
        "database": args.expected_database,
        "v158_sha256": _EXPECTED_SHA256["V158"],
        "v159_sha256": _EXPECTED_SHA256["V159"],
        "on_error_stop_equivalent": _ON_ERROR_STOP_EQUIVALENT,
        "double_apply": True,
        "schema_fingerprint": fingerprint,
        "scenario_markers": scenario_summary["markers"],
        "global_counts": scenario_summary["global_counts"],
        "signature_fixture_only": True,
        "external_authenticity_proven": False,
        "model_fit_performed_by_probe": False,
        "partial_deferred_bundle_injection_claimed": False,
        "partial_deferred_bundle_injection_assigned_to": "V159_CONCURRENCY_PROBE",
    }
    print(
        json.dumps(output, sort_keys=True)
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
