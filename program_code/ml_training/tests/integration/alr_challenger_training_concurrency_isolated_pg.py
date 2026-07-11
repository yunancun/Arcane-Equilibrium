"""Concurrent V158 checks for an explicitly confirmed disposable PG16 database.

The authorized caller keeps CONNECTION LIMIT 1. Administrator-authenticated
test backends use SET SESSION AUTHORIZATION solely to exercise database
serialization. Importing this module performs no I/O. Migration bytes, fixture
data, scenario keys, SQLSTATEs, and error messages are source-bound.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
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
    "b1ff8e2da1878fc498b1bf87e61a105a113bd21b3194a60df84238c8f890d8b9"
)
# A single psycopg execute of the transaction-owned migration is the
# ON_ERROR_STOP equivalent: the first database error is surfaced and no later
# statement is submitted by this probe.
_ON_ERROR_STOP_EQUIVALENT = True
_ACK_ENV = "ALR_V158_DISPOSABLE_ACK"
_ADMIN_DSN_ENV = "ALR_V158_DISPOSABLE_ADMIN_DSN"
_DISPOSABLE_SENTINEL = "V158_DISPOSABLE_DATABASE_MUTATION_CONFIRMED"
_CALLER = "alr_challenger_trainer_caller"
_WRITER = "alr_challenger_writer"
_ARGUMENT = re.compile(r"^p_[a-z][a-z0-9_]*$")
_COLUMN = re.compile(r"^[a-z][a-z0-9_]*$")
_DISPOSABLE_DATABASE = re.compile(r"(?:^|[_-])(ci|test|tmp|scratch|disposable)(?:[_-]|$)")
_RECEIPT_FUNCTION = "persist_alr_qualified_training_receipt_v1"
_RESULT_FUNCTION = "persist_alr_challenger_training_result_v1"
_RECEIPT_READER = "read_alr_qualified_training_receipt_v1"
_RESULT_READER = "read_alr_challenger_training_result_v1"
_FUNCTIONS = {
    _RECEIPT_FUNCTION,
    _RESULT_FUNCTION,
    _RECEIPT_READER,
    _RESULT_READER,
}
_FUNCTION_ARGUMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    _RECEIPT_FUNCTION: tuple(
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
    _RESULT_FUNCTION: (
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
    _RECEIPT_READER: (
        ("p_durable_receipt_hash", "text"),
        ("p_training_key_hash", "text"),
    ),
    _RESULT_READER: (
        ("p_training_run_hash", "text"),
        ("p_training_key_hash", "text"),
    ),
}
_TABLES = {
    "alr_qualified_training_receipts",
    "alr_challenger_training_runs",
    "alr_challenger_model_artifacts",
    "alr_challenger_registry",
}
_SCENARIO_CONTRACT = {
    "identical_receipt": {
        "function": _RECEIPT_FUNCTION,
        "expect": "both_success_same_body",
    },
    "divergent_receipt": {
        "function": _RECEIPT_FUNCTION,
        "expect": "one_success_one_error",
        "sqlstate": "P0001",
        "message": "V158 receipt replay conflict",
    },
    "alternate_unique_receipt": {
        "function": _RECEIPT_FUNCTION,
        "expect": "one_success_one_error",
        "sqlstate": "P0001",
        "message": "V158 receipt replay conflict",
    },
    "identical_result": {
        "function": _RESULT_FUNCTION,
        "expect": "both_success_same_body",
    },
    "divergent_result": {
        "function": _RESULT_FUNCTION,
        "expect": "one_success_one_error",
        "sqlstate": "P0001",
        "message": "V158 result replay conflict",
    },
}
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
    """A fail-closed concurrency-probe result."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run explicit V158 concurrency checks")
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


def _parse_complete_dsn(raw_dsn: str, expected_database: str) -> dict[str, str]:
    import psycopg2  # type: ignore

    try:
        from psycopg2.extensions import parse_dsn  # type: ignore

        parsed = {str(key): str(value) for key, value in parse_dsn(raw_dsn).items()}
    except psycopg2.ProgrammingError as exc:
        raise ProbeFailure("administrator DSN is not a valid explicit libpq DSN") from exc
    required = {"host", "port", "dbname", "user"}
    if not required.issubset(parsed) or any(not parsed[key] for key in required):
        raise ProbeFailure(
            "administrator DSN must explicitly bind host, port, dbname, and user"
        )
    if any(key in parsed for key in ("service", "servicefile")):
        raise ProbeFailure("administrator DSN must not use an ambient libpq service")
    if "," in parsed["host"] or "," in parsed["port"]:
        raise ProbeFailure("administrator DSN must bind exactly one server")
    try:
        port = int(parsed["port"])
    except ValueError as exc:
        raise ProbeFailure("administrator DSN port must be numeric") from exc
    if not 1 <= port <= 65535:
        raise ProbeFailure("administrator DSN port is outside the TCP range")
    if parsed["dbname"] != expected_database:
        raise ProbeFailure("administrator DSN database differs from --expected-database")
    password = parsed.get("password")
    passfile_value = parsed.get("passfile")
    if "password" in parsed and not password:
        raise ProbeFailure("administrator DSN contains an empty password")
    if "passfile" in parsed and not passfile_value:
        raise ProbeFailure("administrator DSN contains an empty passfile")
    if bool(password) == bool(passfile_value):
        raise ProbeFailure(
            "administrator DSN must select exactly one explicit credential mode: "
            "nonempty password or absolute passfile"
        )
    if passfile_value:
        passfile = Path(passfile_value)
        if not passfile.is_absolute():
            raise ProbeFailure("administrator DSN passfile must be absolute")
        try:
            passfile_metadata = passfile.lstat()
        except OSError as exc:
            raise ProbeFailure(
                "administrator DSN passfile is not readable metadata"
            ) from exc
        if stat.S_ISLNK(passfile_metadata.st_mode):
            raise ProbeFailure("administrator DSN passfile must not be a symlink")
        if not stat.S_ISREG(passfile_metadata.st_mode):
            raise ProbeFailure("administrator DSN passfile must be a regular file")
        resolved_passfile = passfile.resolve(strict=True)
        default_passfile = (Path.home() / ".pgpass").resolve(strict=False)
        if resolved_passfile == default_passfile:
            raise ProbeFailure("administrator DSN must not use the default passfile")
        if passfile_metadata.st_uid != os.geteuid():
            raise ProbeFailure(
                "administrator DSN passfile owner must match the probe user"
            )
        if stat.S_IMODE(passfile_metadata.st_mode) != 0o600:
            raise ProbeFailure("administrator DSN passfile mode must be exactly 0600")
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
    explicit["options"] = "-c statement_timeout=20000 -c lock_timeout=10000"
    return psycopg2.connect(cursor_factory=RealDictCursor, **explicit)


def _apply_migration_twice(
    admin_parameters: Mapping[str, str],
    migration: bytes,
    expected_target: Mapping[str, Any],
) -> None:
    import psycopg2  # type: ignore

    for ordinal in (1, 2):
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


def _validate_call(call: Any, label: str, expected_function: str | None = None) -> None:
    if not isinstance(call, Mapping) or call.get("function") not in _FUNCTIONS:
        raise ProbeFailure(f"invalid fixed function in {label}")
    if expected_function is not None and call["function"] != expected_function:
        raise ProbeFailure(f"{label} must call exactly {expected_function}")
    arguments = call.get("args")
    expected = {name for name, _ in _FUNCTION_ARGUMENTS[str(call["function"])]}
    if not isinstance(arguments, Mapping) or set(arguments) != expected:
        raise ProbeFailure(f"named arguments do not match the fixed API in {label}")
    if any(_ARGUMENT.fullmatch(name) is None for name in arguments):
        raise ProbeFailure(f"invalid named argument in {label}")


def _call(connection: Any, call: Mapping[str, Any]) -> Any:
    function_name = str(call["function"])
    arguments = call["args"]
    signature = _FUNCTION_ARGUMENTS[function_name]
    names = [name for name, _ in signature]
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


def _h(label: str) -> str:
    return hashlib.sha256(f"alr-v158-concurrency:{label}".encode("utf-8")).hexdigest()


def _receipt_arguments(label: str) -> dict[str, Any]:
    names = [name for name, _ in _FUNCTION_ARGUMENTS[_RECEIPT_FUNCTION]][:-1]
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


def _call_spec(function_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    return {"function": function_name, "args": deepcopy(dict(arguments))}


def _replace_receipt_field(
    arguments: Mapping[str, Any], field: str, value: str
) -> dict[str, Any]:
    changed = deepcopy(dict(arguments))
    changed[field] = value
    changed["p_canonical_payload"][field.removeprefix("p_")] = value
    return changed


def _projection_artifact(label: str, receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "artifact_hash": receipt["p_projection_artifact_hash"],
        "artifact_kind": "learning_target",
        "canonical_payload": {
            "schema_version": "alr_v158_projection_fixture_v1",
            "fixture_id": label,
        },
    }


def _expected_counts(function_name: str) -> Mapping[str, int]:
    return {
        "alr_qualified_training_receipts": 1,
        "alr_challenger_training_runs": int(function_name == _RESULT_FUNCTION),
        "alr_challenger_model_artifacts": 3 * int(function_name == _RESULT_FUNCTION),
        "alr_challenger_registry": int(function_name == _RESULT_FUNCTION),
    }


def _fixture() -> Mapping[str, Any]:
    receipts = {
        name: _receipt_arguments(name)
        for name in (
            "identical_receipt",
            "divergent_receipt",
            "alternate_unique_receipt",
            "identical_result",
            "divergent_result",
        )
    }
    identical_receipt = receipts["identical_receipt"]
    divergent_receipt = receipts["divergent_receipt"]
    divergent_receipt_right = _replace_receipt_field(
        divergent_receipt,
        "p_source_contract_hash",
        _h("divergent_receipt:alternate-contract"),
    )
    alternate_receipt = receipts["alternate_unique_receipt"]
    alternate_receipt_right = _replace_receipt_field(
        alternate_receipt,
        "p_durable_receipt_hash",
        _h("alternate_unique_receipt:alternate-durable"),
    )
    identical_result = _result_arguments(
        "identical_result", receipts["identical_result"]
    )
    divergent_result = _result_arguments(
        "divergent_result", receipts["divergent_result"]
    )
    divergent_result_right = dict(divergent_result)
    divergent_result_right["p_metrics_hash"] = _h(
        "divergent_result:alternate-metrics"
    )
    scenarios = {
        "identical_receipt": {
            "left": _call_spec(_RECEIPT_FUNCTION, identical_receipt),
            "right": _call_spec(_RECEIPT_FUNCTION, identical_receipt),
        },
        "divergent_receipt": {
            "left": _call_spec(_RECEIPT_FUNCTION, divergent_receipt),
            "right": _call_spec(_RECEIPT_FUNCTION, divergent_receipt_right),
        },
        "alternate_unique_receipt": {
            "left": _call_spec(_RECEIPT_FUNCTION, alternate_receipt),
            "right": _call_spec(_RECEIPT_FUNCTION, alternate_receipt_right),
        },
        "identical_result": {
            "left": _call_spec(_RESULT_FUNCTION, identical_result),
            "right": _call_spec(_RESULT_FUNCTION, identical_result),
        },
        "divergent_result": {
            "left": _call_spec(_RESULT_FUNCTION, divergent_result),
            "right": _call_spec(_RESULT_FUNCTION, divergent_result_right),
        },
    }
    for name, scenario in scenarios.items():
        scenario["expected_lineage_counts"] = _expected_counts(
            str(scenario["left"]["function"])
        )

    partial_run = _h("partial:run")
    partial_key = _h("partial:key")
    partial_set = _h("partial:set")
    partial_challenger = _h("partial:challenger")
    partial_row = {
        "challenger_hash": partial_challenger,
        "training_run_hash": partial_run,
        "training_key_hash": partial_key,
        "model_artifact_set_hash": partial_set,
        "registry_status": "NOT_SERVING",
        "serving_allowed": False,
        "promotion_allowed": False,
        "latest_pointer_allowed": False,
        "symlink_allowed": False,
        "canonical_payload": {
            "schema_version": "alr_challenger_registry_entry_v1",
            "challenger_hash": partial_challenger,
            "training_run_hash": partial_run,
            "training_key_hash": partial_key,
            "model_artifact_set_hash": partial_set,
            "registry_status": "NOT_SERVING",
            "serving_allowed": False,
            "promotion_allowed": False,
            "latest_pointer_allowed": False,
            "symlink_allowed": False,
        },
    }
    return {
        "schema_version": "alr_v158_embedded_concurrency_fixture_v1",
        "projection_artifacts": [
            _projection_artifact(name, receipt) for name, receipt in receipts.items()
        ],
        "prerequisites": [
            _call_spec(_RECEIPT_FUNCTION, receipts["identical_result"]),
            _call_spec(_RECEIPT_FUNCTION, receipts["divergent_result"]),
        ],
        "scenarios": scenarios,
        "partial_bundle": {
            "rows": [
                {
                    "table": "alr_challenger_registry",
                    "values": partial_row,
                }
            ],
            "read": _call_spec(
                _RESULT_READER,
                {
                    "p_training_run_hash": partial_run,
                    "p_training_key_hash": partial_key,
                },
            ),
            "expected_sqlstate": "P0001",
            "expected_message": "V158 result PARTIAL_OR_DIVERGENT",
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


def _validate_receipt_scenario(
    name: str, left: Mapping[str, Any], right: Mapping[str, Any]
) -> None:
    if left["p_training_key_hash"] != right["p_training_key_hash"]:
        raise ProbeFailure(f"{name} must bind one exact training key")
    if name == "identical_receipt":
        if left != right:
            raise ProbeFailure("identical_receipt calls must be byte-equivalent data")
    elif name == "divergent_receipt":
        fixed = {"p_durable_receipt_hash", "p_source_receipt_hash", "p_training_key_hash"}
        if any(left[field] != right[field] for field in fixed):
            raise ProbeFailure("divergent_receipt must collide on all receipt arbiters")
        deltas = {field for field in left if left[field] != right[field]}
        if deltas != {"p_source_contract_hash", "p_canonical_payload"}:
            raise ProbeFailure("divergent_receipt must vary only the bound contract field")
    elif name == "alternate_unique_receipt":
        if left["p_durable_receipt_hash"] == right["p_durable_receipt_hash"]:
            raise ProbeFailure("alternate_unique_receipt must vary durable receipt hash")
        if left["p_source_receipt_hash"] != right["p_source_receipt_hash"]:
            raise ProbeFailure("alternate_unique_receipt must collide on source receipt")
        deltas = {field for field in left if left[field] != right[field]}
        if deltas != {"p_durable_receipt_hash", "p_canonical_payload"}:
            raise ProbeFailure("alternate_unique_receipt has an unbound field delta")


def _validate_result_scenario(
    name: str, left: Mapping[str, Any], right: Mapping[str, Any]
) -> None:
    fixed = {"p_training_run_hash", "p_durable_receipt_hash", "p_training_key_hash"}
    if any(left[field] != right[field] for field in fixed):
        raise ProbeFailure(f"{name} must bind one exact run/receipt/training key")
    if name == "identical_result" and left != right:
        raise ProbeFailure("identical_result calls must be byte-equivalent data")
    if name == "divergent_result":
        deltas = {field for field in left if left[field] != right[field]}
        if deltas != {"p_metrics_hash"}:
            raise ProbeFailure("divergent_result must vary only metrics_hash")


def _validate_fixture(fixture: Mapping[str, Any]) -> None:
    _assert_no_empty_fixture_value(fixture)
    if fixture.get("schema_version") != "alr_v158_embedded_concurrency_fixture_v1":
        raise ProbeFailure("embedded concurrency fixture schema mismatch")
    scenarios = fixture.get("scenarios")
    if not isinstance(scenarios, Mapping) or set(scenarios) != set(_SCENARIO_CONTRACT):
        raise ProbeFailure("fixture must contain the exact V158 concurrency scenarios")
    prerequisites = fixture.get("prerequisites")
    if not isinstance(prerequisites, list) or len(prerequisites) != 2:
        raise ProbeFailure("exactly two result receipt prerequisites are required")
    prerequisite_by_key: dict[str, Mapping[str, Any]] = {}
    for index, call in enumerate(prerequisites):
        _validate_call(call, f"prerequisites[{index}]", _RECEIPT_FUNCTION)
        prerequisite_by_key[call["args"]["p_training_key_hash"]] = call["args"]
    if len(prerequisite_by_key) != 2:
        raise ProbeFailure("result prerequisites must bind distinct training keys")

    for name, contract in _SCENARIO_CONTRACT.items():
        scenario = scenarios[name]
        if not isinstance(scenario, Mapping):
            raise ProbeFailure(f"scenario must be an object: {name}")
        _validate_call(scenario.get("left"), f"{name}.left", str(contract["function"]))
        _validate_call(scenario.get("right"), f"{name}.right", str(contract["function"]))
        left = scenario["left"]["args"]
        right = scenario["right"]["args"]
        if contract["function"] == _RECEIPT_FUNCTION:
            _validate_receipt_scenario(name, left, right)
        else:
            _validate_result_scenario(name, left, right)
            receipt = prerequisite_by_key.get(left["p_training_key_hash"])
            if receipt is None:
                raise ProbeFailure(f"{name} has no exact receipt prerequisite")
            payload = receipt["p_canonical_payload"]
            exact_lineage = {
                "p_durable_receipt_hash": receipt["p_durable_receipt_hash"],
                "p_training_key_hash": receipt["p_training_key_hash"],
                "p_actual_dataset_hash": payload["dataset_hash"],
                "p_actual_row_ids_hash": payload["row_ids_hash"],
                "p_actual_split_hash": payload["split_hash"],
                "p_actual_code_manifest_hash": receipt["p_code_manifest_hash"],
                "p_actual_training_config_hash": receipt["p_training_config_hash"],
                "p_actual_feature_schema_hash": payload["feature_schema_hash"],
                "p_actual_label_schema_hash": payload["label_schema_hash"],
                "p_actual_training_rows": payload["training_rows"],
            }
            if any(left[field] != value for field, value in exact_lineage.items()):
                raise ProbeFailure(f"{name} result lineage differs from its receipt")
        expected_counts = scenario.get("expected_lineage_counts")
        if expected_counts != _expected_counts(str(contract["function"])):
            raise ProbeFailure(f"scenario lineage count contract mismatch: {name}")

    partial = fixture.get("partial_bundle")
    if not isinstance(partial, Mapping) or partial.get("expected_sqlstate") != "P0001":
        raise ProbeFailure("partial bundle must bind SQLSTATE P0001")
    if partial.get("expected_message") != "V158 result PARTIAL_OR_DIVERGENT":
        raise ProbeFailure("partial bundle must bind the exact V158 reader error")
    rows = partial.get("rows")
    if not isinstance(rows, list) or len(rows) != 1:
        raise ProbeFailure("partial bundle must contain one deterministic row")
    row = rows[0]
    if not isinstance(row, Mapping) or row.get("table") != "alr_challenger_registry":
        raise ProbeFailure("partial bundle must isolate one registry row")
    values = row.get("values")
    if not isinstance(values, Mapping) or any(
        _COLUMN.fullmatch(name) is None for name in values
    ):
        raise ProbeFailure("partial registry row has invalid columns")
    _validate_call(partial.get("read"), "partial_bundle.read", _RESULT_READER)
    read_args = partial["read"]["args"]
    if read_args != {
        "p_training_run_hash": values["training_run_hash"],
        "p_training_key_hash": values["training_key_hash"],
    }:
        raise ProbeFailure("partial read key does not exactly bind the injected row")


def _set_caller_identity(
    connection: Any, expected_target: Mapping[str, Any]
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f"SET SESSION AUTHORIZATION {_CALLER}")
        cursor.execute("SELECT session_user AS session_user, current_user AS current_user")
        row = cursor.fetchone()
    if row != {"session_user": _CALLER, "current_user": _CALLER}:
        raise ProbeFailure(f"test-only caller identity mismatch: {row}")
    if _target_identity(connection) != dict(expected_target):
        raise ProbeFailure("caller session is not on the validated administrator server/database")


def _assert_pg16_admin_and_limit(admin: Any, expected_database: str) -> Mapping[str, Any]:
    identity = _target_identity(admin)
    if identity["database_name"] != expected_database:
        raise ProbeFailure("connected database differs from the explicit disposable target")
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('server_version_num')::integer AS version, "
            "usesuper FROM pg_catalog.pg_user WHERE usename = current_user"
        )
        row = cursor.fetchone()
        if not 160000 <= row["version"] < 170000 or row["usesuper"] is not True:
            raise ProbeFailure("PostgreSQL 16 administrator identity is required")
        cursor.execute(
            "SELECT rolconnlimit, rolcanlogin FROM pg_catalog.pg_roles WHERE rolname = %s",
            (_CALLER,),
        )
        caller = cursor.fetchone()
        if caller != {"rolconnlimit": 1, "rolcanlogin": True}:
            raise ProbeFailure("caller must remain LOGIN CONNECTION LIMIT 1")
        cursor.execute(
            "SELECT rolcanlogin FROM pg_catalog.pg_roles WHERE rolname = %s",
            (_WRITER,),
        )
        if cursor.fetchone() != {"rolcanlogin": False}:
            raise ProbeFailure("writer must remain NOLOGIN")
    return identity


def _seed_projection_artifacts(admin: Any, artifacts: Sequence[Mapping[str, Any]]) -> None:
    with admin.cursor() as cursor:
        for artifact in artifacts:
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


def _serial_call(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    call: Mapping[str, Any],
) -> Any:
    connection = _connect(admin_parameters)
    try:
        _set_caller_identity(connection, expected_target)
        result = _call(connection, call)
        connection.commit()
        return result
    finally:
        connection.close()


def _concurrent_worker(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    call: Mapping[str, Any],
    barrier: threading.Barrier,
) -> Mapping[str, Any]:
    import psycopg2  # type: ignore

    connection = _connect(admin_parameters)
    try:
        _set_caller_identity(connection, expected_target)
        barrier.wait(timeout=10)
        try:
            result = _call(connection, call)
            connection.commit()
            return {"status": "success", "result": result}
        except psycopg2.Error as exc:
            connection.rollback()
            return {
                "status": "error",
                "sqlstate": exc.pgcode,
                "message": getattr(exc.diag, "message_primary", None),
            }
    finally:
        connection.close()


def _without_status(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "status"}


def _run_scenario(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    name: str,
    scenario: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    contract = _SCENARIO_CONTRACT[name]
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix=f"v158-{name}") as pool:
        futures = [
            pool.submit(
                _concurrent_worker,
                admin_parameters,
                expected_target,
                scenario[side],
                barrier,
            )
            for side in ("left", "right")
        ]
        outcomes = [future.result(timeout=30) for future in futures]
    statuses = sorted(str(outcome["status"]) for outcome in outcomes)
    if contract["expect"] == "both_success_same_body":
        if statuses != ["success", "success"]:
            raise ProbeFailure(f"{name} did not converge: {outcomes}")
        results = [outcome["result"] for outcome in outcomes]
        if {result.get("status") for result in results} != {"PERSISTED", "DUPLICATE"}:
            raise ProbeFailure(f"{name} did not serialize as PERSISTED plus DUPLICATE")
        if _without_status(results[0]) != _without_status(results[1]):
            raise ProbeFailure(f"{name} returned divergent replay content")
    elif statuses != ["error", "success"]:
        raise ProbeFailure(f"{name} did not fail closed: {outcomes}")
    else:
        error = next(outcome for outcome in outcomes if outcome["status"] == "error")
        if (
            error.get("sqlstate") != contract["sqlstate"]
            or error.get("message") != contract["message"]
        ):
            raise ProbeFailure(
                f"{name} returned ({error.get('sqlstate')}, {error.get('message')!r}); "
                f"expected ({contract['sqlstate']}, {contract['message']!r})"
            )
        success = next(outcome for outcome in outcomes if outcome["status"] == "success")
        if success["result"].get("status") != "PERSISTED":
            raise ProbeFailure(f"{name} successful writer was not the unique PERSISTED row")
    return outcomes


def _training_key(scenario: Mapping[str, Any]) -> str:
    keys = {
        call["args"].get("p_training_key_hash")
        for call in (scenario["left"], scenario["right"])
    }
    if len(keys) != 1 or None in keys:
        raise ProbeFailure("scenario must bind one p_training_key_hash")
    return str(next(iter(keys)))


def _assert_lineage_counts(
    admin: Any,
    training_key_hash: str,
    expected: Mapping[str, Any],
) -> None:
    with admin.cursor() as cursor:
        for table in sorted(_TABLES):
            cursor.execute(
                f"SELECT count(*) AS count FROM learning.{table} "  # noqa: S608
                "WHERE training_key_hash = %s",
                (training_key_hash,),
            )
            if cursor.fetchone()["count"] != int(expected[table]):
                raise ProbeFailure(f"lineage count mismatch for {table}")


def _assert_scenario_read_found(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    scenario: Mapping[str, Any],
    outcomes: Sequence[Mapping[str, Any]],
) -> None:
    left = scenario["left"]
    persisted = next(
        (
            outcome["result"]
            for outcome in outcomes
            if outcome["status"] == "success"
            and outcome["result"].get("status") == "PERSISTED"
        ),
        None,
    )
    if persisted is None:
        raise ProbeFailure("scenario produced no unique PERSISTED readback key")
    if left["function"] == _RECEIPT_FUNCTION:
        receipt = persisted.get("receipt")
        if not isinstance(receipt, Mapping):
            raise ProbeFailure("receipt scenario omitted its persisted receipt")
        call = _call_spec(
            _RECEIPT_READER,
            {
                "p_durable_receipt_hash": receipt["durable_receipt_hash"],
                "p_training_key_hash": receipt["training_key_hash"],
            },
        )
    else:
        run = persisted.get("run")
        if not isinstance(run, Mapping):
            raise ProbeFailure("result scenario omitted its persisted run")
        call = _call_spec(
            _RESULT_READER,
            {
                "p_training_run_hash": run["training_run_hash"],
                "p_training_key_hash": run["training_key_hash"],
            },
        )
    result = _serial_call(admin_parameters, expected_target, call)
    if result.get("status") != "FOUND":
        raise ProbeFailure("scenario readback was NOT_FOUND instead of exact FOUND")


def _inject_partial_bundle(admin: Any, rows: Sequence[Mapping[str, Any]]) -> None:
    import psycopg2  # type: ignore

    try:
        with admin.cursor() as cursor:
            cursor.execute("SET LOCAL session_replication_role = 'replica'")
            for row in rows:
                table = row["table"]
                values = row["values"]
                columns = list(values)
                placeholders = ", ".join("%s" for _ in columns)
                cursor.execute(
                    f"INSERT INTO learning.{table} ({', '.join(columns)}) "  # noqa: S608
                    f"VALUES ({placeholders})",
                    tuple(_adapt(values[column]) for column in columns),
                )
        admin.commit()
    except psycopg2.Error:
        admin.rollback()
        raise


def _assert_partial_read_rejected(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    partial: Mapping[str, Any],
) -> None:
    import psycopg2  # type: ignore

    connection = _connect(admin_parameters)
    try:
        _set_caller_identity(connection, expected_target)
        try:
            _call(connection, partial["read"])
        except psycopg2.Error as exc:
            connection.rollback()
            primary = getattr(exc.diag, "message_primary", None)
            if (
                exc.pgcode != partial["expected_sqlstate"]
                or primary != partial["expected_message"]
            ):
                raise ProbeFailure(
                    f"partial read returned ({exc.pgcode}, {primary!r}); expected "
                    f"({partial['expected_sqlstate']}, {partial['expected_message']!r})"
                ) from exc
        else:
            connection.rollback()
            raise ProbeFailure("partial bundle was exposed as FOUND or NOT_FOUND")
    finally:
        connection.close()


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
        _required_env(_ADMIN_DSN_ENV), args.expected_database
    )

    admin = _connect(admin_parameters)
    try:
        expected_target = _assert_pg16_admin_and_limit(admin, args.expected_database)
    finally:
        admin.close()
    _apply_migration_twice(admin_parameters, migration, expected_target)

    admin = _connect(admin_parameters)
    try:
        if _target_identity(admin) != dict(expected_target):
            raise ProbeFailure("administrator target changed during migration apply")
        _seed_projection_artifacts(admin, fixture["projection_artifacts"])
    finally:
        admin.close()

    for call in fixture["prerequisites"]:
        result = _serial_call(admin_parameters, expected_target, call)
        if result.get("status") != "PERSISTED":
            raise ProbeFailure("result prerequisite receipt was not newly PERSISTED")

    results: dict[str, Any] = {}
    admin = _connect(admin_parameters)
    try:
        for name in sorted(_SCENARIO_CONTRACT):
            scenario = fixture["scenarios"][name]
            results[name] = _run_scenario(
                admin_parameters,
                expected_target,
                name,
                scenario,
            )
            _assert_lineage_counts(
                admin,
                _training_key(scenario),
                scenario["expected_lineage_counts"],
            )
            _assert_scenario_read_found(
                admin_parameters,
                expected_target,
                scenario,
                results[name],
            )
        _inject_partial_bundle(admin, fixture["partial_bundle"]["rows"])
    finally:
        admin.close()
    _assert_partial_read_rejected(
        admin_parameters,
        expected_target,
        fixture["partial_bundle"],
    )
    admin = _connect(admin_parameters)
    try:
        if _assert_pg16_admin_and_limit(admin, args.expected_database) != dict(
            expected_target
        ):
            raise ProbeFailure("administrator target changed before final posture check")
    finally:
        admin.close()

    print(
        json.dumps(
            {
                "schema_version": "alr_v158_disposable_concurrency_result_v1",
                "status": "PASS",
                "migration_sha256": _EXPECTED_MIGRATION_SHA256,
                "database": args.expected_database,
                "admin_caller_same_target": True,
                "on_error_stop_equivalent": _ON_ERROR_STOP_EQUIVALENT,
                "connection_limit_preserved": True,
                "session_authorization_test_only": True,
                "scenarios": results,
                "partial_bundle_rejected": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
