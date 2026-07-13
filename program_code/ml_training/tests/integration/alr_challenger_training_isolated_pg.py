"""Explicit disposable-PostgreSQL probe for the V158 persistence boundary.

Importing this module is inert. Execution requires an exact disposable database
name, a fixed confirmation sentinel, two complete DSNs, and the repository's
canonical V158 bytes. Fixture values are deterministic source data; no fixture
can inject SQL, routing, or accepted error text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence


_ROOT = Path(__file__).resolve().parents[4]
_CANONICAL_MIGRATION = (
    _ROOT / "sql/migrations/V158__alr_qualified_challenger_training.sql"
).resolve()
_EXPECTED_MIGRATION_SHA256 = (
    "7ed70599c6bd5f3cdb3376bc135a952d8c18f4ad62a62432c2bfdd8ee84e446b"
)
# A single psycopg execute of the transaction-owned migration is the
# ON_ERROR_STOP equivalent: the first database error is surfaced and no later
# statement is submitted by this probe.
_ON_ERROR_STOP_EQUIVALENT = True
_ACK_ENV = "ALR_V158_DISPOSABLE_ACK"
_ADMIN_DSN_ENV = "ALR_V158_DISPOSABLE_ADMIN_DSN"
_CALLER_DSN_ENV = "ALR_V158_DISPOSABLE_CALLER_DSN"
_DISPOSABLE_SENTINEL = "V158_DISPOSABLE_DATABASE_MUTATION_CONFIRMED"
_CALLER = "alr_challenger_trainer_caller"
_WRITER = "alr_challenger_writer"
_GENERIC_ROLES = ("trading_ai", "alr_shadow")
_TABLES = (
    "alr_qualified_training_receipts",
    "alr_challenger_training_runs",
    "alr_challenger_model_artifacts",
    "alr_challenger_registry",
)
_FUNCTIONS = {
    "receipt": "persist_alr_qualified_training_receipt_v1",
    "result": "persist_alr_challenger_training_result_v1",
    "receipt_read": "read_alr_qualified_training_receipt_v1",
    "result_read": "read_alr_challenger_training_result_v1",
}
_FUNCTION_REGPROCEDURES = (
    "learning.persist_alr_qualified_training_receipt_v1(text,text,text,text,text,"
    "text,text,text,text,text,text,text,text,text,text,jsonb)",
    "learning.persist_alr_challenger_training_result_v1(text,text,text,text,text,"
    "text,text,text,text,text,text,text,integer,text,text,text,timestamptz,"
    "timestamptz,text,text,bigint,text,text,bigint,text,text,bigint,text)",
    "learning.read_alr_qualified_training_receipt_v1(text,text)",
    "learning.read_alr_challenger_training_result_v1(text,text)",
    "learning.alr_v158_assert_complete_result()",
    "learning.alr_v158_reject_mutation()",
)
_NAMED_COMPLETENESS_CONSTRAINTS = (
    "learning.alr_challenger_run_complete_ct_v1, "
    "learning.alr_challenger_artifact_complete_ct_v1, "
    "learning.alr_challenger_registry_complete_ct_v1"
)
_FUNCTION_ARGUMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    _FUNCTIONS["receipt"]: tuple(
        (name, "text")
        for name in (
            "p_durable_receipt_hash",
            "p_source_receipt_hash",
            "p_source_contract_hash",
            "p_projection_artifact_hash",
            "p_selection_binding_hash",
            "p_proof_input_hash",
            "p_proof_packet_hash",
            "p_reward_set_hash",
            "p_pit_dataset_manifest_hash",
            "p_after_cost_label_set_hash",
            "p_evidence_set_hash",
            "p_training_input_hash",
            "p_training_key_hash",
            "p_code_manifest_hash",
            "p_training_config_hash",
        )
    )
    + (("p_canonical_payload", "jsonb"),),
    _FUNCTIONS["result"]: (
        ("p_training_run_hash", "text"),
        ("p_durable_receipt_hash", "text"),
        ("p_training_key_hash", "text"),
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
        ("p_model_artifact_set_hash", "text"),
        ("p_metrics_hash", "text"),
        ("p_resource_usage_hash", "text"),
        ("p_fit_started_at", "timestamptz"),
        ("p_fit_completed_at", "timestamptz"),
        ("p_q10_artifact_hash", "text"),
        ("p_q10_artifact_path", "text"),
        ("p_q10_artifact_size_bytes", "bigint"),
        ("p_q50_artifact_hash", "text"),
        ("p_q50_artifact_path", "text"),
        ("p_q50_artifact_size_bytes", "bigint"),
        ("p_q90_artifact_hash", "text"),
        ("p_q90_artifact_path", "text"),
        ("p_q90_artifact_size_bytes", "bigint"),
        ("p_challenger_hash", "text"),
    ),
    _FUNCTIONS["receipt_read"]: (
        ("p_durable_receipt_hash", "text"),
        ("p_training_key_hash", "text"),
    ),
    _FUNCTIONS["result_read"]: (
        ("p_training_run_hash", "text"),
        ("p_training_key_hash", "text"),
    ),
}
_ARGUMENT = re.compile(r"^p_[a-z][a-z0-9_]*$")
_DISPOSABLE_DATABASE = re.compile(r"(?:^|[_-])(ci|test|tmp|scratch|disposable)(?:[_-]|$)")
_NO_AUTHORITY = {
    "ex" + "change_authority": False,
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
    "ex" + "change_contact_count": 0,
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


class ProbeFailure(Exception):
    """A fail-closed disposable-probe result."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the explicit V158 PG16 probe")
    parser.add_argument("--confirm-disposable-v158", action="store_true")
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--disposable-sentinel", required=True)
    parser.add_argument("--migration", type=Path, default=_CANONICAL_MIGRATION)
    return parser


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ProbeFailure(f"{name} must be supplied explicitly")
    return value


def _reject_ambient_libpq_routing() -> None:
    ambient = sorted(name for name in os.environ if name.startswith("PG"))
    if ambient:
        raise ProbeFailure(
            "ambient libpq PG* variables are forbidden: " + ", ".join(ambient)
        )


def _parse_complete_dsn(raw_dsn: str, expected_database: str, label: str) -> dict[str, str]:
    import psycopg2  # type: ignore

    try:
        from psycopg2.extensions import parse_dsn  # type: ignore

        parsed = {str(key): str(value) for key, value in parse_dsn(raw_dsn).items()}
    except psycopg2.ProgrammingError as exc:
        raise ProbeFailure(f"{label} DSN is not a valid explicit libpq DSN") from exc
    required = {"host", "port", "dbname", "user"}
    if not required.issubset(parsed) or any(not parsed[key] for key in required):
        raise ProbeFailure(f"{label} DSN must explicitly bind host, port, dbname, and user")
    if any(key in parsed for key in ("service", "servicefile")):
        raise ProbeFailure(f"{label} DSN must not use an ambient libpq service")
    if "," in parsed["host"] or "," in parsed["port"]:
        raise ProbeFailure(f"{label} DSN must bind exactly one server")
    try:
        port = int(parsed["port"])
    except ValueError as exc:
        raise ProbeFailure(f"{label} DSN port must be numeric") from exc
    if not 1 <= port <= 65535:
        raise ProbeFailure(f"{label} DSN port is outside the TCP range")
    if parsed["dbname"] != expected_database:
        raise ProbeFailure(f"{label} DSN database differs from --expected-database")
    password = parsed.get("password")
    passfile_value = parsed.get("passfile")
    if "password" in parsed and not password:
        raise ProbeFailure(f"{label} DSN contains an empty password")
    if "passfile" in parsed and not passfile_value:
        raise ProbeFailure(f"{label} DSN contains an empty passfile")
    if bool(password) == bool(passfile_value):
        raise ProbeFailure(
            f"{label} DSN must select exactly one explicit credential mode: "
            "nonempty password or absolute passfile"
        )
    if passfile_value:
        passfile = Path(passfile_value)
        if not passfile.is_absolute():
            raise ProbeFailure(f"{label} DSN passfile must be absolute")
        try:
            passfile_metadata = passfile.lstat()
        except OSError as exc:
            raise ProbeFailure(f"{label} DSN passfile is not readable metadata") from exc
        if stat.S_ISLNK(passfile_metadata.st_mode):
            raise ProbeFailure(f"{label} DSN passfile must not be a symlink")
        if not stat.S_ISREG(passfile_metadata.st_mode):
            raise ProbeFailure(f"{label} DSN passfile must be a regular file")
        resolved_passfile = passfile.resolve(strict=True)
        default_passfile = (Path.home() / ".pgpass").resolve(strict=False)
        if resolved_passfile == default_passfile:
            raise ProbeFailure(f"{label} DSN must not use the default passfile")
        if passfile_metadata.st_uid != os.geteuid():
            raise ProbeFailure(f"{label} DSN passfile owner must match the probe user")
        if stat.S_IMODE(passfile_metadata.st_mode) != 0o600:
            raise ProbeFailure(f"{label} DSN passfile mode must be exactly 0600")
        parsed["passfile"] = str(resolved_passfile)
    return parsed


def _migration_bytes(path: Path) -> bytes:
    resolved = path.resolve()
    if resolved != _CANONICAL_MIGRATION:
        raise ProbeFailure("migration must be the canonical repository V158 path")
    payload = resolved.read_bytes()
    observed = hashlib.sha256(payload).hexdigest()
    if observed != _EXPECTED_MIGRATION_SHA256:
        raise ProbeFailure(
            f"canonical V158 sha256 mismatch: expected {_EXPECTED_MIGRATION_SHA256}, "
            f"observed {observed}"
        )
    return payload


def _connect(parameters: Mapping[str, str]) -> Any:
    import psycopg2  # type: ignore
    from psycopg2.extras import RealDictCursor  # type: ignore

    explicit = dict(parameters)
    explicit["connect_timeout"] = "5"
    explicit["options"] = "-c statement_timeout=15000 -c lock_timeout=5000"
    return psycopg2.connect(cursor_factory=RealDictCursor, **explicit)


def _apply_migration(
    admin_parameters: Mapping[str, str],
    migration: bytes,
    expected_target: Mapping[str, Any],
    ordinal: int,
) -> None:
    import psycopg2  # type: ignore

    connection = _connect(admin_parameters)
    connection.autocommit = True
    try:
        if _target_identity(connection) != dict(expected_target):
            raise ProbeFailure(
                f"V158 apply {ordinal} target differs from the preflight target"
            )
        with connection.cursor() as cursor:
            cursor.execute(migration.decode("utf-8"))
    except psycopg2.Error as exc:
        primary = getattr(exc.diag, "message_primary", None) or str(exc).splitlines()[0]
        raise ProbeFailure(
            f"V158 apply {ordinal} failed with SQLSTATE {exc.pgcode}: {primary}"
        ) from exc
    finally:
        connection.close()


def _target_identity(connection: Any) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_database() AS database_name, "
            "(SELECT oid::text FROM pg_catalog.pg_database "
            " WHERE datname = current_database()) AS database_oid, "
            "current_setting('server_version_num') AS server_version_num, "
            "pg_catalog.pg_postmaster_start_time()::text AS postmaster_started_at, "
            "COALESCE(pg_catalog.inet_server_addr()::text, '<unix-socket>') AS server_addr, "
            "COALESCE(pg_catalog.inet_server_port()::text, '<unix-socket>') AS server_port"
        )
        row = cursor.fetchone()
    if not row:
        raise ProbeFailure("database target identity query returned no row")
    return dict(row)


def _assert_same_target(
    admin: Any, caller: Any, expected_database: str
) -> Mapping[str, Any]:
    admin_identity = _target_identity(admin)
    caller_identity = _target_identity(caller)
    if admin_identity != caller_identity:
        raise ProbeFailure(
            "administrator and caller DSNs do not resolve to the same server/database"
        )
    if admin_identity["database_name"] != expected_database:
        raise ProbeFailure("connected database differs from the explicit disposable target")
    return admin_identity


def _adapt(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        from psycopg2.extras import Json  # type: ignore

        return Json(value)
    return value


def _normalized(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalized(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalized(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def _call(connection: Any, function_name: str, arguments: Mapping[str, Any]) -> Any:
    if function_name not in _FUNCTIONS.values():
        raise ProbeFailure(f"function is outside the fixed V158 surface: {function_name}")
    signature = _FUNCTION_ARGUMENTS[function_name]
    names = [name for name, _ in signature]
    if set(arguments) != set(names) or any(
        _ARGUMENT.fullmatch(name) is None for name in arguments
    ):
        raise ProbeFailure(f"invalid named argument set for {function_name}")
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


def _h(label: str) -> str:
    return hashlib.sha256(f"alr-v158-fixture:{label}".encode("utf-8")).hexdigest()


def _receipt_arguments(label: str) -> dict[str, Any]:
    names = [name for name, _ in _FUNCTION_ARGUMENTS[_FUNCTIONS["receipt"]]][:-1]
    arguments = {name: _h(f"{label}:{name}") for name in names}
    payload = {name.removeprefix("p_"): value for name, value in arguments.items()}
    payload.update(
        {
            "schema_version": "alr_qualified_training_receipt_v1",
            "projection_artifact_kind": "learning_target",
            "receipt_status": "QUALIFIED_INPUT_PERSISTED",
            "training_allowed": False,
            "model_training_performed": False,
            "registry_write_allowed": False,
            "runtime_or_ex" + "change_attested": False,
            "no_authority": deepcopy(_NO_AUTHORITY),
            "authority_counters": deepcopy(_ZERO_COUNTERS),
            "dataset_hash": _h(f"{label}:dataset"),
            "row_ids_hash": _h(f"{label}:row-ids"),
            "split_hash": _h(f"{label}:split"),
            "feature_schema_hash": _h(f"{label}:feature-schema"),
            "label_schema_hash": _h(f"{label}:label-schema"),
            "training_rows": 12,
        }
    )
    arguments["p_canonical_payload"] = payload
    return arguments


def _result_arguments(label: str, receipt: Mapping[str, Any]) -> dict[str, Any]:
    payload = receipt["p_canonical_payload"]
    run_hash = _h(f"{label}:training-run")
    q10 = _h(f"{label}:q10")
    q50 = _h(f"{label}:q50")
    q90 = _h(f"{label}:q90")
    set_hash = hashlib.sha256(
        f"q10={q10}\nq50={q50}\nq90={q90}\n".encode("utf-8")
    ).hexdigest()
    return {
        "p_training_run_hash": run_hash,
        "p_durable_receipt_hash": receipt["p_durable_receipt_hash"],
        "p_training_key_hash": receipt["p_training_key_hash"],
        "p_source_head": _h(f"{label}:source-head")[:40],
        "p_actual_dataset_hash": payload["dataset_hash"],
        "p_actual_row_ids_hash": payload["row_ids_hash"],
        "p_actual_split_hash": payload["split_hash"],
        "p_actual_code_manifest_hash": receipt["p_code_manifest_hash"],
        "p_actual_training_config_hash": receipt["p_training_config_hash"],
        "p_actual_feature_schema_hash": payload["feature_schema_hash"],
        "p_actual_label_schema_hash": payload["label_schema_hash"],
        "p_model_schema_version": "v158_fixture_1",
        "p_actual_training_rows": payload["training_rows"],
        "p_model_artifact_set_hash": set_hash,
        "p_metrics_hash": _h(f"{label}:metrics"),
        "p_resource_usage_hash": _h(f"{label}:resource-usage"),
        "p_fit_started_at": "2026-07-11T10:00:00.000000Z",
        "p_fit_completed_at": "2026-07-11T10:00:01.000000Z",
        "p_q10_artifact_hash": q10,
        "p_q10_artifact_path": f"runs/{run_hash}/q10.onnx",
        "p_q10_artifact_size_bytes": 101,
        "p_q50_artifact_hash": q50,
        "p_q50_artifact_path": f"runs/{run_hash}/q50.onnx",
        "p_q50_artifact_size_bytes": 102,
        "p_q90_artifact_hash": q90,
        "p_q90_artifact_path": f"runs/{run_hash}/q90.onnx",
        "p_q90_artifact_size_bytes": 103,
        "p_challenger_hash": _h(f"{label}:challenger"),
    }


def _replace_receipt_field(
    arguments: Mapping[str, Any], field: str, value: str
) -> dict[str, Any]:
    changed = deepcopy(dict(arguments))
    changed[field] = value
    changed["p_canonical_payload"][field.removeprefix("p_")] = value
    return changed


def _fixture() -> Mapping[str, Any]:
    receipt = _receipt_arguments("functional")
    result = _result_arguments("functional", receipt)
    receipt_conflict = _replace_receipt_field(
        receipt, "p_source_contract_hash", _h("functional:conflict-contract")
    )
    result_conflict = dict(result)
    result_conflict["p_metrics_hash"] = _h("functional:conflict-metrics")
    set_hash_mismatch = dict(result)
    set_hash_mismatch["p_model_artifact_set_hash"] = _h("functional:wrong-set")
    schema_mismatch = dict(result)
    schema_mismatch["p_actual_feature_schema_hash"] = _h("functional:wrong-schema")
    return {
        "schema_version": "alr_v158_embedded_functional_fixture_v1",
        "projection_artifact": {
            "artifact_hash": receipt["p_projection_artifact_hash"],
            "artifact_kind": "learning_target",
            "canonical_payload": {
                "schema_version": "alr_v158_projection_fixture_v1",
                "fixture_id": "functional",
            },
        },
        "receipt": receipt,
        "result": result,
        "receipt_read": {
            "p_durable_receipt_hash": receipt["p_durable_receipt_hash"],
            "p_training_key_hash": receipt["p_training_key_hash"],
        },
        "result_read": {
            "p_training_run_hash": result["p_training_run_hash"],
            "p_training_key_hash": result["p_training_key_hash"],
        },
        "receipt_not_found": {
            "p_durable_receipt_hash": _h("functional:missing-receipt"),
            "p_training_key_hash": _h("functional:missing-receipt-key"),
        },
        "result_not_found": {
            "p_training_run_hash": _h("functional:missing-run"),
            "p_training_key_hash": _h("functional:missing-run-key"),
        },
        "invalid_calls": (
            (
                _FUNCTIONS["receipt"],
                receipt_conflict,
                "P0001",
                "V158 receipt replay conflict",
            ),
            (
                _FUNCTIONS["result"],
                result_conflict,
                "P0001",
                "V158 result replay conflict",
            ),
            (
                _FUNCTIONS["result"],
                set_hash_mismatch,
                "P0001",
                "V158 artifact set hash mismatch",
            ),
            (
                _FUNCTIONS["result"],
                schema_mismatch,
                "P0001",
                "V158 exact receipt lineage mismatch",
            ),
        ),
        "expected_counts": {
            "alr_qualified_training_receipts": 1,
            "alr_challenger_training_runs": 1,
            "alr_challenger_model_artifacts": 3,
            "alr_challenger_registry": 1,
        },
    }


def _assert_no_empty_fixture_value(value: Any, path: str = "fixture") -> None:
    if isinstance(value, str) and not value:
        raise ProbeFailure(f"{path} contains an empty string")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_no_empty_fixture_value(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_no_empty_fixture_value(item, f"{path}[{index}]")


def _validate_fixture(fixture: Mapping[str, Any]) -> None:
    _assert_no_empty_fixture_value(fixture)
    if fixture.get("schema_version") != "alr_v158_embedded_functional_fixture_v1":
        raise ProbeFailure("embedded fixture schema mismatch")
    calls = {
        "receipt": fixture["receipt"],
        "result": fixture["result"],
        "receipt_read": fixture["receipt_read"],
        "result_read": fixture["result_read"],
    }
    for key, arguments in calls.items():
        expected = {name for name, _ in _FUNCTION_ARGUMENTS[_FUNCTIONS[key]]}
        if not isinstance(arguments, Mapping) or set(arguments) != expected:
            raise ProbeFailure(f"embedded {key} arguments differ from the fixed V158 API")
    receipt = fixture["receipt"]
    result = fixture["result"]
    if result["p_durable_receipt_hash"] != receipt["p_durable_receipt_hash"]:
        raise ProbeFailure("result does not bind the embedded receipt hash")
    if result["p_training_key_hash"] != receipt["p_training_key_hash"]:
        raise ProbeFailure("result does not bind the embedded training key")
    if fixture["receipt_read"] != {
        "p_durable_receipt_hash": receipt["p_durable_receipt_hash"],
        "p_training_key_hash": receipt["p_training_key_hash"],
    }:
        raise ProbeFailure("receipt reader does not bind the writer key")
    if fixture["result_read"] != {
        "p_training_run_hash": result["p_training_run_hash"],
        "p_training_key_hash": result["p_training_key_hash"],
    }:
        raise ProbeFailure("result reader does not bind the writer key")


def _assert_pg16_and_roles(admin: Any, *, require_v158_acl: bool = False) -> None:
    with admin.cursor() as cursor:
        cursor.execute("SHOW server_version_num")
        version = int(cursor.fetchone()["server_version_num"])
        if not 160000 <= version < 170000:
            raise ProbeFailure(f"PostgreSQL 16 required, observed {version}")
        cursor.execute(
            "SELECT usesuper FROM pg_catalog.pg_user WHERE usename = current_user"
        )
        if cursor.fetchone() != {"usesuper": True}:
            raise ProbeFailure("V158 migration requires an explicit superuser DSN")
        cursor.execute(
            "SELECT "
            "bool_and(CASE WHEN rolname = %s THEN "
            "NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND "
            "NOT rolcreaterole AND NOT rolinherit AND NOT rolreplication AND "
            "NOT rolbypassrls ELSE "
            "rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND "
            "NOT rolcreaterole AND NOT rolinherit AND NOT rolreplication AND "
            "NOT rolbypassrls AND rolconnlimit = 1 END) AS exact, "
            "count(*) AS count FROM pg_catalog.pg_roles WHERE rolname IN (%s, %s)",
            (_WRITER, _WRITER, _CALLER),
        )
        role_row = cursor.fetchone()
        if role_row["count"] != 2 or role_row["exact"] is not True:
            raise ProbeFailure("V158 role posture is not exact")
        cursor.execute(
            "SELECT bool_and(NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb "
            "AND NOT rolcreaterole AND NOT rolinherit AND NOT rolreplication "
            "AND NOT rolbypassrls AND rolconnlimit = -1) AS exact, "
            "count(*) AS count FROM pg_catalog.pg_roles WHERE rolname IN (%s, %s)",
            _GENERIC_ROLES,
        )
        generic_row = cursor.fetchone()
        if generic_row["count"] != 2 or generic_row["exact"] is not True:
            raise ProbeFailure("V158 disposable generic role posture is not exact")
        bounded_roles = (_WRITER, _CALLER, *_GENERIC_ROLES)
        cursor.execute(
            "SELECT count(*) AS count FROM pg_catalog.pg_auth_members "
            "WHERE roleid IN (SELECT oid FROM pg_catalog.pg_roles "
            "WHERE rolname IN (%s, %s, %s, %s)) "
            "OR member IN (SELECT oid FROM pg_catalog.pg_roles "
            "WHERE rolname IN (%s, %s, %s, %s))",
            (*bounded_roles, *bounded_roles),
        )
        if cursor.fetchone()["count"] != 0:
            raise ProbeFailure("V158 caller, writer, and generic roles must be membership-free")
        for role in bounded_roles:
            cursor.execute(
                "SELECT pg_catalog.has_parameter_privilege("
                "%s, 'session_replication_role', 'SET') AS allowed",
                (role,),
            )
            if cursor.fetchone() != {"allowed": False}:
                raise ProbeFailure(
                    f"{role} unexpectedly has session_replication_role SET authority"
                )
        if require_v158_acl:
            for role in _GENERIC_ROLES:
                for function in _FUNCTION_REGPROCEDURES:
                    cursor.execute(
                        "SELECT pg_catalog.has_function_privilege("
                        "%s, %s, 'EXECUTE') AS allowed",
                        (role, function),
                    )
                    if cursor.fetchone() != {"allowed": False}:
                        raise ProbeFailure(f"{role} unexpectedly can execute {function}")
                for table in _TABLES:
                    for privilege in (
                        "SELECT",
                        "INSERT",
                        "UPDATE",
                        "DELETE",
                        "TRUNCATE",
                        "REFERENCES",
                        "TRIGGER",
                    ):
                        cursor.execute(
                            "SELECT pg_catalog.has_table_privilege("
                            "%s, %s, %s) AS allowed",
                            (role, f"learning.{table}", privilege),
                        )
                        if cursor.fetchone() != {"allowed": False}:
                            raise ProbeFailure(
                                f"{role} unexpectedly has {privilege} on {table}"
                            )
            for index, function in enumerate(_FUNCTION_REGPROCEDURES):
                cursor.execute(
                    "SELECT pg_catalog.has_function_privilege("
                    "%s, %s, 'EXECUTE') AS allowed",
                    (_CALLER, function),
                )
                if cursor.fetchone() != {"allowed": index < 4}:
                    raise ProbeFailure(
                        f"trainer caller EXECUTE posture differs for {function}"
                    )


def _assert_caller_identity(caller: Any) -> None:
    with caller.cursor() as cursor:
        cursor.execute("SELECT session_user AS session_user, current_user AS current_user")
        row = cursor.fetchone()
    if row != {"session_user": _CALLER, "current_user": _CALLER}:
        raise ProbeFailure(f"caller identity mismatch: {row}")


def _connect_as_generic(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    role: str,
) -> Any:
    connection = _connect(admin_parameters)
    try:
        if _target_identity(connection) != dict(expected_target):
            raise ProbeFailure("generic negative-check target differs from preflight")
        connection.rollback()
        connection.autocommit = True
        with connection.cursor() as cursor:
            if role == "trading_ai":
                cursor.execute("SET SESSION AUTHORIZATION trading_ai")
            elif role == "alr_shadow":
                cursor.execute("SET SESSION AUTHORIZATION alr_shadow")
            else:
                raise ProbeFailure(f"role is outside the fixed generic set: {role}")
        connection.autocommit = False
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT session_user AS session_user, current_user AS current_user"
            )
            identity = cursor.fetchone()
        if identity != {"session_user": role, "current_user": role}:
            raise ProbeFailure(f"generic session identity mismatch for {role}: {identity}")
        return connection
    except Exception:
        connection.close()
        raise


def _assert_generic_function_execute_denied(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    receipt_arguments: Mapping[str, Any],
) -> None:
    import psycopg2  # type: ignore

    for role in _GENERIC_ROLES:
        connection = _connect_as_generic(admin_parameters, expected_target, role)
        try:
            try:
                _call(connection, _FUNCTIONS["receipt"], receipt_arguments)
            except psycopg2.Error as exc:
                connection.rollback()
                if exc.pgcode != "42501":
                    raise ProbeFailure(
                        f"{role} function denial returned {exc.pgcode}, expected 42501"
                    ) from exc
            else:
                connection.rollback()
                raise ProbeFailure(f"{role} unexpectedly executed a V158 function")
        finally:
            connection.close()


def _assert_session_replication_role_denied(
    caller: Any,
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
) -> None:
    import psycopg2  # type: ignore

    connections = [caller]
    owned_connections: list[Any] = []
    try:
        for role in _GENERIC_ROLES:
            generic = _connect_as_generic(admin_parameters, expected_target, role)
            owned_connections.append(generic)
            connections.append(generic)
        for connection in connections:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL session_replication_role = 'replica'")
            except psycopg2.Error as exc:
                connection.rollback()
                if exc.pgcode != "42501":
                    raise ProbeFailure(
                        "session_replication_role denial returned "
                        f"{exc.pgcode}, expected 42501"
                    ) from exc
            else:
                connection.rollback()
                raise ProbeFailure(
                    "non-privileged V158 identity set session_replication_role"
                )
        _assert_caller_identity(caller)
    finally:
        for connection in owned_connections:
            connection.close()


def _seed_projection_artifact(admin: Any, artifact: Mapping[str, Any]) -> None:
    with admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO learning.alr_artifact_nodes "
            "(artifact_hash, artifact_kind, canonical_payload) VALUES (%s, %s, %s) "
            "ON CONFLICT (artifact_hash) DO NOTHING RETURNING artifact_hash",
            (
                artifact["artifact_hash"],
                artifact["artifact_kind"],
                _adapt(artifact["canonical_payload"]),
            ),
        )
        if cursor.fetchone() is None:
            cursor.execute(
                "SELECT artifact_kind, canonical_payload "
                "FROM learning.alr_artifact_nodes WHERE artifact_hash = %s",
                (artifact["artifact_hash"],),
            )
            existing = cursor.fetchone()
            expected = {
                "artifact_kind": artifact["artifact_kind"],
                "canonical_payload": artifact["canonical_payload"],
            }
            if _normalized(existing) != _normalized(expected):
                raise ProbeFailure("projection artifact replay conflict")
    admin.commit()


def _assert_direct_table_access_denied(caller: Any) -> None:
    import psycopg2  # type: ignore

    statements: list[str] = []
    for table in _TABLES:
        statements.extend(
            (
                f"SELECT 1 FROM learning.{table} LIMIT 0",
                f"INSERT INTO learning.{table} DEFAULT VALUES",
                f"UPDATE learning.{table} SET created_at = created_at WHERE false",
                f"DELETE FROM learning.{table} WHERE false",
            )
        )
    for statement in statements:
        try:
            with caller.cursor() as cursor:
                cursor.execute(statement)
        except psycopg2.Error as exc:
            caller.rollback()
            if exc.pgcode != "42501":
                raise ProbeFailure(
                    f"direct-access check returned SQLSTATE {exc.pgcode}, expected 42501"
                ) from exc
        else:
            caller.rollback()
            raise ProbeFailure("trainer caller unexpectedly received direct table access")


def _assert_counts_and_fixed_state(admin: Any, expected: Mapping[str, Any]) -> None:
    with admin.cursor() as cursor:
        for table in _TABLES:
            cursor.execute(f"SELECT count(*) AS count FROM learning.{table}")  # noqa: S608
            if cursor.fetchone()["count"] != int(expected[table]):
                raise ProbeFailure(f"unexpected row count for {table}")
        cursor.execute(
            "SELECT count(*) AS count FROM learning.alr_challenger_training_runs "
            "WHERE run_status = 'TRAINING_PERFORMED' AND model_training_performed IS TRUE"
        )
        if cursor.fetchone()["count"] != int(expected["alr_challenger_training_runs"]):
            raise ProbeFailure("completed-run fixed state mismatch")
        cursor.execute(
            "SELECT count(*) AS count FROM learning.alr_challenger_model_artifacts "
            "WHERE artifact_format = 'onnx' AND symlink_created IS FALSE "
            "AND serving_visible IS FALSE AND quantile IN ('q10', 'q50', 'q90')"
        )
        if cursor.fetchone()["count"] != int(expected["alr_challenger_model_artifacts"]):
            raise ProbeFailure("artifact fixed state mismatch")
        cursor.execute(
            "SELECT count(*) AS count FROM learning.alr_challenger_registry "
            "WHERE registry_status = 'NOT_SERVING' AND serving_allowed IS FALSE "
            "AND promotion_allowed IS FALSE AND latest_pointer_allowed IS FALSE "
            "AND symlink_allowed IS FALSE"
        )
        if cursor.fetchone()["count"] != int(expected["alr_challenger_registry"]):
            raise ProbeFailure("registry fixed state mismatch")


def _assert_admin_mutation_blocked(admin: Any) -> None:
    import psycopg2  # type: ignore

    for table in _TABLES:
        try:
            with admin.cursor() as cursor:
                cursor.execute(
                    f"UPDATE learning.{table} SET created_at = created_at",  # noqa: S608
                )
        except psycopg2.Error as exc:
            admin.rollback()
            primary = getattr(exc.diag, "message_primary", None)
            if exc.pgcode != "P0001" or primary != "V158 append-only table rejects UPDATE":
                raise ProbeFailure(
                    f"immutable check returned ({exc.pgcode}, {primary!r})"
                ) from exc
        else:
            admin.rollback()
            raise ProbeFailure(f"immutable trigger did not reject update: {table}")


def _assert_deferred_completeness_rejected(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    result: Mapping[str, Any],
) -> Mapping[str, str]:
    import psycopg2  # type: ignore

    expected_message = (
        "V158 complete result invariant: exact q10/q50/q90 bundle required"
    )
    cases = (
        ("partial_trio", "SET_CONSTRAINTS"),
        ("schema_mismatch", "COMMIT"),
    )
    expected_boundaries = dict(cases)
    observed_boundaries: dict[str, str] = {}
    for case, boundary in cases:
        connection = _connect(admin_parameters)
        try:
            if _target_identity(connection) != dict(expected_target):
                raise ProbeFailure(
                    "deferred completeness target differs from preflight target"
                )
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT challenger_hash, training_run_hash, training_key_hash, "
                        "model_artifact_set_hash, registry_status, serving_allowed, "
                        "promotion_allowed, latest_pointer_allowed, symlink_allowed, "
                        "canonical_payload FROM learning.alr_challenger_registry "
                        "WHERE training_run_hash = %s",
                        (result["p_training_run_hash"],),
                    )
                    registry = cursor.fetchone()
                    if not registry:
                        raise ProbeFailure(
                            "deferred completeness fixture registry row is missing"
                        )
                    cursor.execute(
                        f"SET CONSTRAINTS {_NAMED_COMPLETENESS_CONSTRAINTS} DEFERRED"
                    )
                    cursor.execute("SET LOCAL session_replication_role = 'replica'")
                    if case == "partial_trio":
                        cursor.execute(
                            "DELETE FROM learning.alr_challenger_model_artifacts "
                            "WHERE training_run_hash = %s AND quantile = 'q90'",
                            (result["p_training_run_hash"],),
                        )
                    else:
                        cursor.execute(
                            "UPDATE learning.alr_challenger_model_artifacts "
                            "SET feature_schema_hash = %s "
                            "WHERE training_run_hash = %s AND quantile = 'q10'",
                            (
                                _h("functional:deferred-wrong-schema"),
                                result["p_training_run_hash"],
                            ),
                        )
                    if cursor.rowcount != 1:
                        raise ProbeFailure(
                            f"{case} did not mutate exactly one disposable artifact"
                        )
                    cursor.execute(
                        "DELETE FROM learning.alr_challenger_registry "
                        "WHERE training_run_hash = %s",
                        (result["p_training_run_hash"],),
                    )
                    if cursor.rowcount != 1:
                        raise ProbeFailure(
                            f"{case} did not remove exactly one disposable registry row"
                        )
                    cursor.execute("SET LOCAL session_replication_role = 'origin'")
                    cursor.execute(
                        "GRANT INSERT ON TABLE learning.alr_challenger_registry "
                        "TO alr_challenger_trainer_caller"
                    )
                    cursor.execute(
                        "SET SESSION AUTHORIZATION alr_challenger_trainer_caller"
                    )
                    cursor.execute(
                        "INSERT INTO learning.alr_challenger_registry ("
                        "challenger_hash, training_run_hash, training_key_hash, "
                        "model_artifact_set_hash, registry_status, serving_allowed, "
                        "promotion_allowed, latest_pointer_allowed, symlink_allowed, "
                        "canonical_payload) VALUES ("
                        "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            registry["challenger_hash"],
                            registry["training_run_hash"],
                            registry["training_key_hash"],
                            registry["model_artifact_set_hash"],
                            registry["registry_status"],
                            registry["serving_allowed"],
                            registry["promotion_allowed"],
                            registry["latest_pointer_allowed"],
                            registry["symlink_allowed"],
                            _adapt(registry["canonical_payload"]),
                        ),
                    )
            except psycopg2.Error as exc:
                primary = getattr(exc.diag, "message_primary", None)
                connection.rollback()
                raise ProbeFailure(
                    f"{case} setup failed before {boundary}: "
                    f"({exc.pgcode}, {primary!r})"
                ) from exc

            actual_phase = boundary
            try:
                if actual_phase == "SET_CONSTRAINTS":
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f"SET CONSTRAINTS {_NAMED_COMPLETENESS_CONSTRAINTS} "
                            "IMMEDIATE"
                        )
                elif actual_phase == "COMMIT":
                    connection.commit()
                else:
                    raise ProbeFailure(f"unexpected deferred boundary: {actual_phase}")
            except psycopg2.Error as exc:
                primary = getattr(exc.diag, "message_primary", None)
                connection.rollback()
                if exc.pgcode != "P0001" or primary != expected_message:
                    raise ProbeFailure(
                        f"{case} failed with ({exc.pgcode}, {primary!r}); expected "
                        f"('P0001', {expected_message!r}) at {actual_phase}"
                    ) from exc
                observed_boundaries[case] = actual_phase
            else:
                connection.rollback()
                raise ProbeFailure(
                    f"{case} unexpectedly passed deferred completeness at {actual_phase}"
                )
        finally:
            connection.close()
    if observed_boundaries != expected_boundaries:
        raise ProbeFailure(
            f"deferred boundary coverage incomplete: {observed_boundaries}"
        )
    return observed_boundaries


def _run_calls(caller: Any, fixture: Mapping[str, Any]) -> dict[str, Any]:
    receipt = fixture["receipt"]
    first_receipt = _call(caller, _FUNCTIONS["receipt"], receipt)
    caller.commit()
    replay_receipt = _call(caller, _FUNCTIONS["receipt"], receipt)
    caller.commit()
    if replay_receipt["receipt"] != first_receipt["receipt"]:
        raise ProbeFailure("receipt replay changed server-owned content")
    if first_receipt["status"] != "PERSISTED" or replay_receipt["status"] != "DUPLICATE":
        raise ProbeFailure("receipt replay did not report PERSISTED then DUPLICATE")

    result = fixture["result"]
    first_result = _call(caller, _FUNCTIONS["result"], result)
    caller.commit()
    replay_result = _call(caller, _FUNCTIONS["result"], result)
    caller.commit()
    first_body = {key: value for key, value in first_result.items() if key != "status"}
    replay_body = {key: value for key, value in replay_result.items() if key != "status"}
    if replay_body != first_body:
        raise ProbeFailure("result replay changed server-owned content")
    if first_result["status"] != "PERSISTED" or replay_result["status"] != "DUPLICATE":
        raise ProbeFailure("result replay did not report PERSISTED then DUPLICATE")

    for function_name, arguments, sqlstate, message in fixture["invalid_calls"]:
        _expect_db_error(caller, function_name, arguments, sqlstate, message)

    receipt_state = _call(caller, _FUNCTIONS["receipt_read"], fixture["receipt_read"])
    result_state = _call(caller, _FUNCTIONS["result_read"], fixture["result_read"])
    receipt_missing = _call(
        caller, _FUNCTIONS["receipt_read"], fixture["receipt_not_found"]
    )
    result_missing = _call(
        caller, _FUNCTIONS["result_read"], fixture["result_not_found"]
    )
    caller.commit()
    if receipt_state.get("status") != "FOUND" or result_state.get("status") != "FOUND":
        raise ProbeFailure("persisted writer keys did not produce exact FOUND reads")
    if receipt_missing != {"status": "NOT_FOUND", "receipt": None}:
        raise ProbeFailure("receipt NOT_FOUND response was not exact")
    if result_missing != {"status": "NOT_FOUND"}:
        raise ProbeFailure("result NOT_FOUND response was not exact")
    return {
        "receipt": receipt_state,
        "result": result_state,
        "receipt_not_found": receipt_missing,
        "result_not_found": result_missing,
    }


def _read_calls(caller: Any, fixture: Mapping[str, Any]) -> dict[str, Any]:
    state = {
        "receipt": _call(caller, _FUNCTIONS["receipt_read"], fixture["receipt_read"]),
        "result": _call(caller, _FUNCTIONS["result_read"], fixture["result_read"]),
        "receipt_not_found": _call(
            caller, _FUNCTIONS["receipt_read"], fixture["receipt_not_found"]
        ),
        "result_not_found": _call(
            caller, _FUNCTIONS["result_read"], fixture["result_not_found"]
        ),
    }
    caller.commit()
    return state


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.confirm_disposable_v158 or os.environ.get(_ACK_ENV) != "1":
        raise ProbeFailure(
            f"explicit --confirm-disposable-v158 and {_ACK_ENV}=1 are required"
        )
    expected_sentinel = f"{_DISPOSABLE_SENTINEL}:{args.expected_database}"
    if args.disposable_sentinel != expected_sentinel:
        raise ProbeFailure(
            "the exact V158 disposable sentinel suffixed by the target database is required"
        )
    if not _DISPOSABLE_DATABASE.search(args.expected_database.lower()):
        raise ProbeFailure(
            "--expected-database must be explicitly named as ci/test/tmp/scratch/disposable"
        )
    _reject_ambient_libpq_routing()
    migration = _migration_bytes(args.migration)
    fixture = _fixture()
    _validate_fixture(fixture)
    admin_parameters = _parse_complete_dsn(
        _required_env(_ADMIN_DSN_ENV), args.expected_database, "administrator"
    )
    caller_parameters = _parse_complete_dsn(
        _required_env(_CALLER_DSN_ENV), args.expected_database, "caller"
    )
    if caller_parameters["user"] != _CALLER:
        raise ProbeFailure(f"caller DSN user must be exactly {_CALLER}")

    admin = _connect(admin_parameters)
    caller = _connect(caller_parameters)
    try:
        _assert_pg16_and_roles(admin)
        _assert_caller_identity(caller)
        expected_target = _assert_same_target(admin, caller, args.expected_database)
    finally:
        caller.close()
        admin.close()
    _apply_migration(admin_parameters, migration, expected_target, 1)

    admin = _connect(admin_parameters)
    caller = _connect(caller_parameters)
    try:
        if _assert_same_target(admin, caller, args.expected_database) != dict(
            expected_target
        ):
            raise ProbeFailure("connected target changed after first V158 apply")
        _seed_projection_artifact(admin, fixture["projection_artifact"])
        _assert_pg16_and_roles(admin, require_v158_acl=True)
        _assert_caller_identity(caller)
        _assert_generic_function_execute_denied(
            admin_parameters, expected_target, fixture["receipt"]
        )
        _assert_session_replication_role_denied(
            caller, admin_parameters, expected_target
        )
        _assert_direct_table_access_denied(caller)
        readback = _run_calls(caller, fixture)
        deferred_boundaries = _assert_deferred_completeness_rejected(
            admin_parameters, expected_target, fixture["result"]
        )
        if deferred_boundaries != {
            "partial_trio": "SET_CONSTRAINTS",
            "schema_mismatch": "COMMIT",
        }:
            raise ProbeFailure(
                f"deferred boundary result was not exact: {deferred_boundaries}"
            )
        _assert_direct_table_access_denied(caller)
        if _read_calls(caller, fixture) != readback:
            raise ProbeFailure("rollback-only negative checks changed persisted readback")
        _apply_migration(admin_parameters, migration, expected_target, 2)
        if _read_calls(caller, fixture) != readback:
            raise ProbeFailure("second V158 apply changed persisted readback")
        _assert_pg16_and_roles(admin, require_v158_acl=True)
        _assert_counts_and_fixed_state(admin, fixture["expected_counts"])
        _assert_admin_mutation_blocked(admin)
        print(
            json.dumps(
                {
                    "schema_version": "alr_v158_disposable_pg_result_v1",
                    "status": "PASS",
                    "migration_sha256": _EXPECTED_MIGRATION_SHA256,
                    "database": args.expected_database,
                    "admin_caller_same_target": True,
                    "on_error_stop_equivalent": _ON_ERROR_STOP_EQUIVALENT,
                    "double_apply": True,
                    "generic_function_execute_denied": True,
                    "session_replication_role_denied": True,
                    "partial_trio_boundary": "SET_CONSTRAINTS",
                    "schema_mismatch_boundary": "COMMIT",
                    "deferred_boundaries": deferred_boundaries,
                    "test_only_insert_grant_rolled_back": True,
                    "readback": readback,
                },
                sort_keys=True,
            )
        )
    finally:
        caller.close()
        admin.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
