"""Disposable PostgreSQL concurrency probe for the V159 durable-fit seam.

Import is inert; destructive execution requires an explicitly disposable DB.
Output excludes DSNs, fixtures, receipt bytes, identities, locks, and errors.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from queue import Queue
from threading import Barrier, Event
from typing import Any, Callable, Iterator, Mapping, Sequence

_ROOT = Path(__file__).resolve().parents[4]
_PROGRAM_CODE = _ROOT / "program_code"
if str(_PROGRAM_CODE) not in sys.path:
    sys.path.insert(0, str(_PROGRAM_CODE))
from ml_training.tests.integration.alr_durable_fit_attestation_isolated_pg import (
    ProbeFailure,
    _ADMIN_DSN_ENV,
    _ATTESTOR_CALLER,
    _DISPOSABLE_DATABASE,
    _FUNCTIONS,
    _NO_AUTHORITY,
    _ON_ERROR_STOP_EQUIVALENT,
    _TRAINER_CALLER,
    _V158,
    _V159,
    _ZERO_COUNTERS,
    _adapt,
    _artifact_set_hash,
    _assert_bundle_snapshot,
    _assert_exact_bound_bundle,
    _assert_same_target,
    _attestation_fixture,
    _attestation_row_identity,
    _call,
    _canonical_pg_jsonb_bytes,
    _connect,
    _connect_as_role,
    _expected_durable_attestation_hash,
    _expected_durable_training_run_hash,
    _migration_bytes,
    _normalized,
    _orchestrate_migrations,
    _parse_complete_dsn,
    _persist_qualified_receipt,
    _reject_ambient_libpq_routing,
    _required_env,
    _seed_v159_role_preconditions,
    _target_identity,
    _utc_six_digit_z,
)


_EXPECTED_SHA256 = {
    "V158": "7ed70599c6bd5f3cdb3376bc135a952d8c18f4ad62a62432c2bfdd8ee84e446b",
    "V159": "2e11d0ae0cbc2c1161a47d04bed4054c31b728e8cf945f931197f9b3455b7d74",
}
_ACK_ENV = "ALR_V159_CONCURRENCY_DISPOSABLE_ACK"
_SENTINEL = "V159_DURABLE_FIT_CONCURRENCY_DISPOSABLE_MUTATION_CONFIRMED"
_SAFE_FAILURE_MESSAGE = "V159 concurrency disposable probe failed safely"
_DEADLINE_SECONDS = 30.0
_POLL_SECONDS = 0.05
_STATEMENT_TIMEOUT_MS = 25000
_LOCK_TIMEOUT_MS = 24000
_SCENARIO_ORDER = (
    "_scenario_identical_attestation",
    "_scenario_structural_identity_collisions",
    "_scenario_artifact_collisions",
    "_scenario_wait_past_expiry_attestor_lock",
    "_scenario_wait_past_expiry_unique_index",
    "_scenario_uncommitted_visibility",
    "_scenario_partial_bundle_injection",
    "_scenario_identical_bind",
    "_scenario_divergent_bind",
    "_scenario_bind_rollback",
    "_scenario_wait_past_expiry_bind",
)
_STRUCTURAL_IDENTITY_FIELDS = (
    "p_structural_result_hash",
    "p_structural_fit_capture_hash",
    "p_structural_candidate_hash",
    "p_structural_training_run_hash",
    "p_structural_challenger_hash",
    "p_ordered_artifact_set_hash",
)
_ARTIFACT_COLLISION_MODES = (
    "same_quantile",
    "cross_quantile",
    "exact_set",
)
_REQUIRED_MARKERS = (
    "IDENTICAL_ATTESTATION_PERSISTED_DUPLICATE",
    "IDENTICAL_ATTESTATION_IMMUTABLE",
    "UNCOMMITTED_STRUCTURAL_IDENTITY_P0001",
    "ALL_SIX_STRUCTURAL_IDENTITIES_P0001",
    "SAME_QUANTILE_ARTIFACT_P0001",
    "CROSS_QUANTILE_ARTIFACT_P0001",
    "EXACT_SET_ARTIFACT_P0001",
    "LOCK_BLOCKED_ARTIFACT_P0001",
    "WAIT_PAST_EXPIRY_ATTESTOR_LOCK_REJECTED",
    "WAIT_PAST_EXPIRY_UNIQUE_INDEX_REJECTED",
    "UNCOMMITTED_ATTESTATION_INVISIBLE",
    "ATTESTED_UNBOUND_AFTER_COMMIT",
    "PARTIAL_DEFERRED_BUNDLE_INJECTION_REJECTED",
    "PARTIAL_DEFERRED_BUNDLE_ROLLBACK_CLEAN",
    "IDENTICAL_BIND_PERSISTED_DUPLICATE",
    "BIND_ADVISORY_LOCKS_OBSERVED",
    "EXACT_BOUND_BUNDLE",
    "DIVERGENT_BIND_P0001_NO_PARTIAL",
    "BIND_ROLLBACK_ATTESTED_UNBOUND",
    "WAIT_PAST_EXPIRY_BIND_REJECTED",
    "WORKER_CONNECTION_OWNERSHIP_UNIQUE",
    "NO_AUTHORITY_FALSE_ZERO",
    "GLOBAL_ORACLE_3_3_2_6_2",
    "SCENARIO_SUITE_COMPLETE",
)
_ROLE_AUTHORIZATION = {
    "alr_challenger_fit_attestor_caller": (
        "SET SESSION AUTHORIZATION alr_challenger_fit_attestor_caller"
    ),
    "alr_challenger_trainer_caller": (
        "SET SESSION AUTHORIZATION alr_challenger_trainer_caller"
    ),
}
_CONSTRAINTS = (
    "learning.alr_challenger_run_complete_ct_v1,"
    "learning.alr_challenger_artifact_complete_ct_v1,"
    "learning.alr_challenger_registry_complete_ct_v1,"
    "learning.alr_v159_run_complete_ct_v1,"
    "learning.alr_v159_artifact_complete_ct_v1,"
    "learning.alr_v159_registry_complete_ct_v1"
)


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ProbeFailure("invalid V159 concurrency probe arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(
        description="Run the explicit V159 disposable concurrency probe"
    )
    parser.add_argument("--confirm-disposable-v159-concurrency", action="store_true")
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--disposable-sentinel", required=True)
    parser.add_argument("--v158", type=Path, default=_V158)
    parser.add_argument("--v159", type=Path, default=_V159)
    return parser


def _deadline() -> float:
    return time.monotonic() + _DEADLINE_SECONDS

def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProbeFailure("bounded concurrency deadline expired")
    return min(remaining, _DEADLINE_SECONDS)

def _wait_event(event: Event, deadline: float, label: str) -> None:
    if not event.wait(timeout=_remaining(deadline)):
        raise ProbeFailure(f"bounded event was not reached: {label}")

def _worker_identity(
    connection: Any, label: str, expected_role: str
) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_backend_pid() AS backend_pid,session_user,current_user,"
            "current_setting('TimeZone') AS timezone,"
            "current_setting('default_transaction_isolation') AS isolation"
        )
        row = cursor.fetchone()
    if not row:
        raise ProbeFailure("worker session identity returned no row")
    expected = {
        "session_user": expected_role,
        "current_user": expected_role,
        "timezone": "UTC",
        "isolation": "read committed",
    }
    if {key: row[key] for key in expected} != expected:
        raise ProbeFailure("worker UTC/read-committed/session identity drifted")
    return {
        "worker": label,
        "backend_pid": int(row["backend_pid"]),
        "thread_id": threading.get_ident(),
    }

@contextmanager
def _worker_session(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    role: str,
    label: str,
    ownership: Queue[dict[str, Any]],
    deadline: float,
) -> Iterator[tuple[Any, dict[str, Any]]]:
    if role not in _ROLE_AUTHORIZATION:
        raise ProbeFailure("worker role is outside the fixed caller surface")
    connection = _connect_as_role(
        admin_parameters,
        expected_target,
        role,
        destructive_ack=True,
    )
    try:
        if _target_identity(connection) != dict(expected_target):
            raise ProbeFailure("worker connection target differs")
        connection.rollback()
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(_ROLE_AUTHORIZATION[role])
            cursor.execute("SET SESSION TimeZone='UTC'")
            cursor.execute(
                "SET SESSION default_transaction_isolation='read committed'"
            )
        connection.autocommit = False
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL statement_timeout='{_STATEMENT_TIMEOUT_MS}ms'")
            cursor.execute(f"SET LOCAL lock_timeout='{_LOCK_TIMEOUT_MS}ms'")
        identity = _worker_identity(connection, label, role)
        ownership.put(identity, timeout=_remaining(deadline))
        yield connection, identity
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()

@contextmanager
def _admin_worker_session(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    label: str,
    ownership: Queue[dict[str, Any]],
    deadline: float,
) -> Iterator[tuple[Any, dict[str, Any]]]:
    from psycopg2 import sql  # type: ignore

    connection = _connect(admin_parameters)
    try:
        if _target_identity(connection) != dict(expected_target):
            raise ProbeFailure("admin worker connection target differs")
        connection.rollback()
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SET SESSION AUTHORIZATION {}").format(
                    sql.Identifier(admin_parameters["user"])
                )
            )
            cursor.execute("SET SESSION TimeZone='UTC'")
            cursor.execute(
                "SET SESSION default_transaction_isolation='read committed'"
            )
        connection.autocommit = False
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL statement_timeout='{_STATEMENT_TIMEOUT_MS}ms'")
            cursor.execute(f"SET LOCAL lock_timeout='{_LOCK_TIMEOUT_MS}ms'")
        identity = _worker_identity(connection, label, admin_parameters["user"])
        ownership.put(identity, timeout=_remaining(deadline))
        yield connection, identity
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()

def _sync_worker(
    barrier: Barrier | None,
    gate: Event | None,
    deadline: float,
) -> None:
    if gate is not None:
        _wait_event(gate, deadline, "worker gate")
    if barrier is not None:
        barrier.wait(timeout=_remaining(deadline))

def _finish_transaction(
    connection: Any,
    resolution: str,
    ready: Event | None,
    release: Event | None,
    deadline: float,
) -> None:
    if ready is not None:
        ready.set()
    if release is not None:
        _wait_event(release, deadline, "transaction release")
    if resolution == "commit":
        connection.commit()
    elif resolution == "rollback":
        connection.rollback()
    else:
        raise ProbeFailure("unknown worker transaction resolution")

def _error_outcome(label: str, identity: Mapping[str, Any], exc: Any) -> dict[str, Any]:
    message = getattr(getattr(exc, "diag", None), "message_primary", None)
    return {
        "worker": label,
        "backend_pid": identity["backend_pid"],
        "thread_id": identity["thread_id"],
        "status": "ERROR",
        "sqlstate": getattr(exc, "pgcode", None),
        "message": message,
        "result": None,
    }

def _attest_worker(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    label: str,
    arguments: Mapping[str, Any],
    ownership: Queue[dict[str, Any]],
    deadline: float,
    barrier: Barrier | None = None,
    gate: Event | None = None,
    ready: Event | None = None,
    release: Event | None = None,
    resolution: str = "commit",
) -> dict[str, Any]:
    import psycopg2  # type: ignore

    with _worker_session(
        admin_parameters, expected_target, _ATTESTOR_CALLER, label, ownership, deadline
    ) as (connection, identity):
        _sync_worker(barrier, gate, deadline)
        try:
            result = _call(connection, _FUNCTIONS["attest"], arguments)
            _finish_transaction(connection, resolution, ready, release, deadline)
            return {
                "worker": label,
                "backend_pid": identity["backend_pid"],
                "thread_id": identity["thread_id"],
                "status": "OK",
                "sqlstate": None,
                "message": None,
                "result": result,
            }
        except psycopg2.Error as exc:
            connection.rollback()
            return _error_outcome(label, identity, exc)

def _bind_worker(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    label: str,
    arguments: Mapping[str, Any],
    ownership: Queue[dict[str, Any]],
    deadline: float,
    barrier: Barrier | None = None,
    gate: Event | None = None,
    ready: Event | None = None,
    release: Event | None = None,
    resolution: str = "commit",
    completed: Queue[str] | None = None,
) -> dict[str, Any]:
    import psycopg2  # type: ignore

    with _worker_session(
        admin_parameters, expected_target, _TRAINER_CALLER, label, ownership, deadline
    ) as (connection, identity):
        _sync_worker(barrier, gate, deadline)
        try:
            result = _call(connection, _FUNCTIONS["bind"], arguments)
            if completed is not None:
                completed.put(label, timeout=_remaining(deadline))
            _finish_transaction(connection, resolution, ready, release, deadline)
            return {
                "worker": label,
                "backend_pid": identity["backend_pid"],
                "thread_id": identity["thread_id"],
                "status": "OK",
                "sqlstate": None,
                "message": None,
                "result": result,
            }
        except psycopg2.Error as exc:
            connection.rollback()
            return _error_outcome(label, identity, exc)

def _read_worker(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    label: str,
    arguments: Mapping[str, Any],
    ownership: Queue[dict[str, Any]],
    deadline: float,
    barrier: Barrier | None = None,
    gate: Event | None = None,
) -> dict[str, Any]:
    with _worker_session(
        admin_parameters, expected_target, _TRAINER_CALLER, label, ownership, deadline
    ) as (connection, identity):
        _sync_worker(barrier, gate, deadline)
        result = _call(connection, _FUNCTIONS["read"], arguments)
        connection.commit()
        return {
            "worker": label,
            "backend_pid": identity["backend_pid"],
            "thread_id": identity["thread_id"],
            "status": "OK",
            "sqlstate": None,
            "message": None,
            "result": result,
        }

def _lock_holder_worker(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    label: str,
    materials: Sequence[str],
    ownership: Queue[dict[str, Any]],
    deadline: float,
    held: Event,
    release: Event,
) -> dict[str, Any]:
    with _worker_session(
        admin_parameters, expected_target, _ATTESTOR_CALLER, label, ownership, deadline
    ) as (connection, identity):
        with connection.cursor() as cursor:
            for material in sorted(set(materials)):
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                    (material,),
                )
        held.set()
        _wait_event(release, deadline, "advisory lock release")
        connection.rollback()
        return {
            "worker": label,
            "backend_pid": identity["backend_pid"],
            "thread_id": identity["thread_id"],
            "status": "LOCK_RELEASED",
            "sqlstate": None,
            "message": None,
            "result": None,
        }

def _collect_worker_ownership(
    ownership: Queue[dict[str, Any]],
    labels: Sequence[str],
    deadline: float,
) -> dict[str, dict[str, Any]]:
    records = [ownership.get(timeout=_remaining(deadline)) for _ in labels]
    by_label = {record["worker"]: record for record in records}
    if set(by_label) != set(labels) or len(by_label) != len(records):
        raise ProbeFailure("worker ownership labels are not exact")
    if len({record["backend_pid"] for record in records}) != len(records):
        raise ProbeFailure("workers shared a PostgreSQL backend")
    if len({record["thread_id"] for record in records}) != len(records):
        raise ProbeFailure("workers shared a Python thread")
    return by_label


def _run_concurrently(
    submissions: Sequence[tuple[Callable[..., dict[str, Any]], tuple[Any, ...]]],
    ownership: Queue[dict[str, Any]],
    labels: Sequence[str],
    observer: Callable[
        [Mapping[str, Mapping[str, Any]], Mapping[str, Future[Any]], float], None
    ]
    | None = None,
    releases: Sequence[Event] = (),
    barriers: Sequence[Barrier] = (),
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    deadline = _deadline()
    executor = ThreadPoolExecutor(
        max_workers=len(submissions), thread_name_prefix="v159-concurrency"
    )
    futures: list[Future[Any]] = []
    try:
        futures = [executor.submit(function, *arguments) for function, arguments in submissions]
        identities = _collect_worker_ownership(ownership, labels, deadline)
        by_label = dict(zip(labels, futures, strict=True))
        if observer is not None:
            observer(identities, by_label, deadline)
        results = [future.result(timeout=_remaining(deadline)) for future in futures]
        return results, identities
    finally:
        for release in releases:
            release.set()
        for barrier in barriers:
            try:
                barrier.abort()
            except threading.BrokenBarrierError:
                pass
        for future in futures:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

def _wait_for_blocked(
    admin: Any,
    backend_pid: int,
    expected_waits: Sequence[str],
    deadline: float,
) -> dict[str, Any]:
    poll = Event()
    observed: dict[str, Any] | None = None
    while observed is None:
        with admin.cursor() as cursor:
            cursor.execute("SELECT pg_stat_clear_snapshot()")
            cursor.execute(
                "SELECT wait_event_type,wait_event,state FROM pg_stat_activity "
                "WHERE pid=%s AND datname=current_database()",
                (backend_pid,),
            )
            row = cursor.fetchone()
        if (
            row
            and row["wait_event_type"] == "Lock"
            and row["wait_event"] in set(expected_waits)
            and row["state"] == "active"
        ):
            observed = dict(row)
        else:
            poll.wait(timeout=min(_POLL_SECONDS, _remaining(deadline)))
    return observed

def _observe_domain_locks(
    admin: Any,
    holder_pid: int,
    waiter_pid: int,
    materials: Sequence[str],
) -> None:
    with admin.cursor() as cursor:
        cursor.execute(
            "WITH expected AS ("
            "SELECT material,hashtextextended(material,0) AS lock_key FROM unnest(%s::text[]) material),"
            "holder_locks AS (SELECT e.material,holder.locktype,holder.database,"
            "holder.classid,holder.objid,holder.objsubid FROM pg_locks holder "
            "JOIN expected e ON holder.locktype='advisory' "
            "AND holder.pid=%s AND holder.granted IS TRUE "
            "AND holder.database=(SELECT oid FROM pg_database WHERE datname=current_database()) "
            "AND holder.objsubid=1 "
            "AND holder.classid=(((e.lock_key >> 32) & 4294967295)::oid) "
            "AND holder.objid=((e.lock_key & 4294967295)::oid)),waiter_locks AS ("
            "SELECT holder.material FROM holder_locks holder JOIN pg_locks waiter "
            "ON waiter.locktype=holder.locktype "
            "AND waiter.pid=%s AND waiter.granted IS FALSE "
            "AND waiter.database=holder.database "
            "AND waiter.classid=holder.classid AND waiter.objid=holder.objid "
            "AND waiter.objsubid=holder.objsubid) "
            "SELECT (SELECT array_agg(material ORDER BY material) FROM holder_locks) AS holder_labels,"
            "(SELECT array_agg(material ORDER BY material) FROM waiter_locks) AS waiter_labels",
            (list(materials), holder_pid, waiter_pid),
        )
        row = cursor.fetchone()
    expected = sorted(set(materials))
    if (
        not row
        or row["holder_labels"] != expected
        or not row["waiter_labels"]
        or len(row["waiter_labels"]) != 1
        or row["waiter_labels"][0] not in expected
    ):
        raise ProbeFailure("expected holder/waiter advisory locks were not observed")

def _wait_past_expiry(admin: Any, expires_at: Any, deadline: float) -> None:
    poll = Event()
    expired = False
    while not expired:
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT clock_timestamp()>=%s::timestamptz AS expired",
                (expires_at,),
            )
            row = cursor.fetchone()
        expired = bool(row and row["expired"] is True)
        if not expired:
            poll.wait(timeout=min(_POLL_SECONDS, _remaining(deadline)))
    return None


def _assert_pre_expiry(admin: Any, expires_at: Any) -> None:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT clock_timestamp()<%s::timestamptz AS pre_expiry",
            (expires_at,),
        )
        row = cursor.fetchone()
    if row != {"pre_expiry": True}:
        raise ProbeFailure("blocked waiter was not sampled before expiry")

def _assert_p0001(outcome: Mapping[str, Any], message: str) -> None:
    if outcome.get("sqlstate") == "23505":
        raise ProbeFailure("raw unique_violation escaped the V159 boundary")
    if outcome.get("sqlstate") != "P0001" or outcome.get("message") != message:
        raise ProbeFailure("fixed V159 collision/TTL failure differed")

def _assert_no_attestation(admin: Any, fixture: Mapping[str, Any]) -> None:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) AS rows FROM learning.alr_challenger_fit_attestations "
            "WHERE durable_attestation_hash=%s",
            (fixture["durable_attestation_hash"],),
        )
        row = cursor.fetchone()
    if row != {"rows": 0}:
        raise ProbeFailure("rejected attestation poisoned durable state")


def _refresh_fixture(admin: Any, fixture: Mapping[str, Any]) -> dict[str, Any]:
    refreshed = deepcopy(fixture)
    attest = refreshed["attest"]
    projection = attest["p_receipt_projection"]
    signed_bytes, digest = _canonical_pg_jsonb_bytes(admin, projection)
    attest["p_signed_receipt_bytes"] = signed_bytes
    attest["p_verified_at"] = projection["verified_at"]
    attest["p_expires_at"] = projection["expires_at"]
    durable_hash = _expected_durable_attestation_hash(attest, digest)
    refreshed["durable_attestation_hash"] = durable_hash
    refreshed["external_receipt_digest"] = digest
    refreshed["bind"]["p_durable_attestation_hash"] = durable_hash
    refreshed["read"]["p_durable_attestation_hash"] = durable_hash
    refreshed["read"]["p_structural_training_run_hash"] = attest[
        "p_structural_training_run_hash"
    ]
    return refreshed


def _structural_collision_fixture(
    admin: Any,
    receipt: Mapping[str, Any],
    winner: Mapping[str, Any],
    field: str,
    label: str,
    *,
    expiry_seconds: float = 3600.0,
) -> dict[str, Any]:
    fixture = _attestation_fixture(
        admin, receipt, label, expiry_seconds=expiry_seconds
    )
    attest = fixture["attest"]
    projection = attest["p_receipt_projection"]
    winner_attest = winner["attest"]
    subject_key = {
        "p_structural_result_hash": "result_hash",
        "p_structural_fit_capture_hash": "fit_capture_hash",
        "p_structural_candidate_hash": "candidate_attestation_hash",
        "p_structural_training_run_hash": "training_run_hash",
        "p_structural_challenger_hash": "challenger_hash",
        "p_ordered_artifact_set_hash": "ordered_artifact_set_hash",
    }[field]
    attest[field] = winner_attest[field]
    projection["subject"][subject_key] = winner_attest[field]
    if field == "p_ordered_artifact_set_hash":
        artifacts = deepcopy(
            winner_attest["p_receipt_projection"]["result_observation"]["artifacts"]
        )
        projection["result_observation"]["artifacts"] = artifacts
        for quantile in ("q10", "q50", "q90"):
            fixture["bind"][f"p_{quantile}_hash"] = artifacts[quantile][
                "artifact_hash"
            ]
            fixture["bind"][f"p_{quantile}_size"] = artifacts[quantile][
                "artifact_size_bytes"
            ]
    if field == "p_structural_training_run_hash":
        fixture["read"]["p_structural_training_run_hash"] = winner_attest[field]
    return _refresh_fixture(admin, fixture)


def _artifact_collision_fixture(
    admin: Any,
    receipt: Mapping[str, Any],
    winner: Mapping[str, Any],
    mode: str,
    label: str,
) -> dict[str, Any]:
    if mode not in _ARTIFACT_COLLISION_MODES:
        raise ProbeFailure("unknown artifact collision mode")
    fixture = _attestation_fixture(admin, receipt, label)
    artifacts = fixture["attest"]["p_receipt_projection"]["result_observation"][
        "artifacts"
    ]
    winner_artifacts = winner["attest"]["p_receipt_projection"][
        "result_observation"
    ]["artifacts"]
    if mode == "same_quantile":
        artifacts["q10"] = deepcopy(winner_artifacts["q10"])
    elif mode == "cross_quantile":
        artifacts["q50"] = deepcopy(winner_artifacts["q10"])
    else:
        fixture["attest"]["p_receipt_projection"]["result_observation"][
            "artifacts"
        ] = deepcopy(winner_artifacts)
        artifacts = fixture["attest"]["p_receipt_projection"][
            "result_observation"
        ]["artifacts"]
    hashes = tuple(artifacts[q]["artifact_hash"] for q in ("q10", "q50", "q90"))
    artifact_set = _artifact_set_hash(*hashes)
    fixture["attest"]["p_ordered_artifact_set_hash"] = artifact_set
    fixture["attest"]["p_receipt_projection"]["subject"][
        "ordered_artifact_set_hash"
    ] = artifact_set
    for quantile in ("q10", "q50", "q90"):
        fixture["bind"][f"p_{quantile}_hash"] = artifacts[quantile]["artifact_hash"]
        fixture["bind"][f"p_{quantile}_size"] = artifacts[quantile][
            "artifact_size_bytes"
        ]
    return _refresh_fixture(admin, fixture)


def _single_worker(
    function: Callable[..., dict[str, Any]],
    arguments: tuple[Any, ...],
    label: str,
) -> dict[str, Any]:
    ownership: Queue[dict[str, Any]] = Queue()
    deadline = _deadline()
    result = function(*arguments, ownership, deadline)
    record = ownership.get(timeout=_remaining(deadline))
    if record["worker"] != label:
        raise ProbeFailure("single worker ownership label differs")
    return result


def _outcomes_by_label(results: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    outcomes = {str(result["worker"]): result for result in results}
    if len(outcomes) != len(results):
        raise ProbeFailure("concurrent worker labels were not unique")
    return outcomes


def _artifact_material(fixture: Mapping[str, Any], quantile: str) -> str:
    artifact_hash = fixture["bind"][f"p_{quantile}_hash"]
    return f"v159:artifact:{artifact_hash}"


def _bind_materials(fixture: Mapping[str, Any]) -> tuple[str, ...]:
    attest = fixture["attest"]
    bind = fixture["bind"]
    return (
        f"v159:attestation:{fixture['durable_attestation_hash']}",
        f"v159:run:{attest['p_structural_training_run_hash']}",
        f"v159:challenger:{attest['p_structural_challenger_hash']}",
        f"v159:artifact:{bind['p_q10_hash']}",
        f"v159:artifact:{bind['p_q50_hash']}",
        f"v159:artifact:{bind['p_q90_hash']}",
    )


def _scenario_identical_attestation(
    admin: Any,
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    receipts: Mapping[str, Mapping[str, Any]],
    markers: set[str],
) -> dict[str, Any]:
    fixture = _attestation_fixture(admin, receipts["a"], "concurrency-a")
    barrier = Barrier(2)
    ownership: Queue[dict[str, Any]] = Queue()
    deadline = _deadline()
    submissions = (
        (
            _attest_worker,
            (
                admin_parameters, expected_target, "attest-a-1", fixture["attest"],
                ownership, deadline, barrier,
            ),
        ),
        (
            _attest_worker,
            (
                admin_parameters, expected_target, "attest-a-2", fixture["attest"],
                ownership, deadline, barrier,
            ),
        ),
    )
    results, _ = _run_concurrently(
        submissions,
        ownership,
        ("attest-a-1", "attest-a-2"),
        barriers=(barrier,),
    )
    statuses = sorted(
        result["result"]["status"]
        for result in results
        if result["status"] == "OK" and result["result"] is not None
    )
    if statuses != ["DUPLICATE", "PERSISTED"]:
        raise ProbeFailure("identical concurrent attestation result set differed")
    persisted = next(result["result"] for result in results if result["status"] == "OK" and result["result"]["status"] == "PERSISTED")
    duplicate = next(result["result"] for result in results if result["status"] == "OK" and result["result"]["status"] == "DUPLICATE")
    persisted_payload = {key: value for key, value in persisted.items() if key != "status"}
    duplicate_payload = {key: value for key, value in duplicate.items() if key != "status"}
    if persisted_payload != duplicate_payload:
        raise ProbeFailure("identical attestation payload parity differed")
    if (
        persisted_payload.get("durable_attestation_hash")
        != fixture["durable_attestation_hash"]
        or persisted_payload.get("external_receipt_digest")
        != fixture["external_receipt_digest"]
        or _utc_six_digit_z(persisted_payload.get("verified_at"))
        != _utc_six_digit_z(fixture["attest"]["p_verified_at"])
        or _utc_six_digit_z(persisted_payload.get("expires_at"))
        != _utc_six_digit_z(fixture["attest"]["p_expires_at"])
    ):
        raise ProbeFailure("identical attestation exact identity payload differed")
    markers.add("IDENTICAL_ATTESTATION_PERSISTED_DUPLICATE")
    before = _attestation_row_identity(admin, fixture["durable_attestation_hash"])
    replay = _single_worker(
        _attest_worker,
        (admin_parameters, expected_target, "attest-a-replay", fixture["attest"]),
        "attest-a-replay",
    )
    after = _attestation_row_identity(admin, fixture["durable_attestation_hash"])
    replay_payload = {key: value for key, value in replay["result"].items() if key != "status"}
    if (
        replay["result"].get("status") != "DUPLICATE"
        or replay_payload != persisted_payload
        or before != after
    ):
        raise ProbeFailure("identical attestation replay changed immutable identity")
    markers.add("IDENTICAL_ATTESTATION_IMMUTABLE")
    return fixture


def _scenario_structural_identity_collisions(
    admin: Any,
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    receipts: Mapping[str, Mapping[str, Any]],
    markers: set[str],
) -> dict[str, Any]:
    fixture = _attestation_fixture(admin, receipts["b"], "concurrency-b")
    first_field = _STRUCTURAL_IDENTITY_FIELDS[0]
    first_loser = _structural_collision_fixture(
        admin, receipts["c"], fixture, first_field, "collision-result"
    )
    ready = Event()
    release = Event()
    ownership: Queue[dict[str, Any]] = Queue()
    deadline = _deadline()
    submissions = (
        (
            _attest_worker,
            (
                admin_parameters, expected_target, "structural-winner", fixture["attest"],
                ownership, deadline, None, None, ready, release, "commit",
            ),
        ),
        (
            _attest_worker,
            (
                admin_parameters, expected_target, "structural-loser",
                first_loser["attest"], ownership, deadline, None, ready,
            ),
        ),
    )

    def observe(
        identities: Mapping[str, Mapping[str, Any]],
        _futures: Mapping[str, Future[Any]],
        observer_deadline: float,
    ) -> None:
        _wait_event(ready, observer_deadline, "structural winner insert")
        _wait_for_blocked(
            admin,
            int(identities["structural-loser"]["backend_pid"]),
            ("transactionid",),
            observer_deadline,
        )
        release.set()

    results, _ = _run_concurrently(
        submissions,
        ownership,
        ("structural-winner", "structural-loser"),
        observer=observe,
        releases=(release,),
    )
    outcomes = _outcomes_by_label(results)
    if outcomes["structural-winner"]["result"].get("status") != "PERSISTED":
        raise ProbeFailure("uncommitted structural winner was not persisted")
    _assert_p0001(
        outcomes["structural-loser"], "V159 attestation replay conflict"
    )
    _assert_no_attestation(admin, first_loser)
    markers.add("UNCOMMITTED_STRUCTURAL_IDENTITY_P0001")
    for ordinal, field in enumerate(_STRUCTURAL_IDENTITY_FIELDS[1:], start=1):
        loser = _structural_collision_fixture(
            admin, receipts["c"], fixture, field, f"collision-{ordinal}"
        )
        outcome = _single_worker(
            _attest_worker,
            (admin_parameters, expected_target, f"collision-{ordinal}", loser["attest"]),
            f"collision-{ordinal}",
        )
        _assert_p0001(outcome, "V159 attestation replay conflict")
        _assert_no_attestation(admin, loser)
    markers.add("ALL_SIX_STRUCTURAL_IDENTITIES_P0001")
    return fixture


def _scenario_artifact_collisions(
    admin: Any,
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    receipts: Mapping[str, Mapping[str, Any]],
    fixture_b: Mapping[str, Any],
    markers: set[str],
) -> None:
    same = _artifact_collision_fixture(
        admin, receipts["c"], fixture_b, "same_quantile", "artifact-same"
    )
    material = _artifact_material(fixture_b, "q10")
    held = Event()
    release = Event()
    ownership: Queue[dict[str, Any]] = Queue()
    deadline = _deadline()
    submissions = (
        (
            _lock_holder_worker,
            (
                admin_parameters, expected_target, "artifact-lock-holder", (material,),
                ownership, deadline, held, release,
            ),
        ),
        (
            _attest_worker,
            (
                admin_parameters, expected_target, "artifact-same-loser", same["attest"],
                ownership, deadline, None, held,
            ),
        ),
    )

    def observe(
        identities: Mapping[str, Mapping[str, Any]],
        _futures: Mapping[str, Future[Any]],
        observer_deadline: float,
    ) -> None:
        _wait_event(held, observer_deadline, "artifact lock held")
        loser_pid = int(identities["artifact-same-loser"]["backend_pid"])
        _wait_for_blocked(
            admin, loser_pid, ("advisory", "AdvisoryLock"), observer_deadline
        )
        holder_pid = int(identities["artifact-lock-holder"]["backend_pid"])
        _observe_domain_locks(admin, holder_pid, loser_pid, (material,))
        release.set()

    results, _ = _run_concurrently(
        submissions,
        ownership,
        ("artifact-lock-holder", "artifact-same-loser"),
        observer=observe,
        releases=(release,),
    )
    same_outcome = _outcomes_by_label(results)["artifact-same-loser"]
    _assert_p0001(same_outcome, "V159 attestation replay conflict")
    _assert_no_attestation(admin, same)
    markers.add("SAME_QUANTILE_ARTIFACT_P0001")
    markers.add("LOCK_BLOCKED_ARTIFACT_P0001")
    cross_quantile = _artifact_collision_fixture(
        admin, receipts["c"], fixture_b, "cross_quantile", "artifact-cross-quantile"
    )
    cross_outcome = _single_worker(
        _attest_worker,
        (
            admin_parameters, expected_target, "artifact-cross-quantile",
            cross_quantile["attest"],
        ),
        "artifact-cross-quantile",
    )
    _assert_p0001(cross_outcome, "V159 attestation replay conflict")
    _assert_no_attestation(admin, cross_quantile)
    markers.add("CROSS_QUANTILE_ARTIFACT_P0001")
    exact_set = _artifact_collision_fixture(
        admin, receipts["c"], fixture_b, "exact_set", "artifact-exact-set"
    )
    exact_outcome = _single_worker(
        _attest_worker,
        (
            admin_parameters, expected_target, "artifact-exact-set",
            exact_set["attest"],
        ),
        "artifact-exact-set",
    )
    _assert_p0001(exact_outcome, "V159 attestation replay conflict")
    _assert_no_attestation(admin, exact_set)
    markers.add("EXACT_SET_ARTIFACT_P0001")
    return None


def _scenario_wait_past_expiry_attestor_lock(
    admin: Any,
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    receipts: Mapping[str, Mapping[str, Any]],
    markers: set[str],
) -> None:
    fixture = _attestation_fixture(
        admin, receipts["c"], "ttl-artifact-lock", expiry_seconds=6.0
    )
    material = _artifact_material(fixture, "q10")
    held = Event()
    release = Event()
    ownership: Queue[dict[str, Any]] = Queue()
    deadline = _deadline()
    submissions = (
        (
            _lock_holder_worker,
            (
                admin_parameters, expected_target, "ttl-lock-holder", (material,),
                ownership, deadline, held, release,
            ),
        ),
        (
            _attest_worker,
            (
                admin_parameters, expected_target, "ttl-lock-loser", fixture["attest"],
                ownership, deadline, None, held,
            ),
        ),
    )

    def observe(
        identities: Mapping[str, Mapping[str, Any]],
        _futures: Mapping[str, Future[Any]],
        observer_deadline: float,
    ) -> None:
        _wait_event(held, observer_deadline, "TTL artifact lock held")
        _wait_for_blocked(
            admin,
            int(identities["ttl-lock-loser"]["backend_pid"]),
            ("advisory", "AdvisoryLock"),
            observer_deadline,
        )
        holder_pid = int(identities["ttl-lock-holder"]["backend_pid"])
        waiter_pid = int(identities["ttl-lock-loser"]["backend_pid"])
        _observe_domain_locks(admin, holder_pid, waiter_pid, (material,))
        _assert_pre_expiry(admin, fixture["attest"]["p_expires_at"])
        _wait_past_expiry(
            admin, fixture["attest"]["p_expires_at"], observer_deadline
        )
        release.set()

    results, _ = _run_concurrently(
        submissions,
        ownership,
        ("ttl-lock-holder", "ttl-lock-loser"),
        observer=observe,
        releases=(release,),
    )
    outcome = _outcomes_by_label(results)["ttl-lock-loser"]
    _assert_p0001(outcome, "V159 attestation future-dated or expired")
    _assert_no_attestation(admin, fixture)
    markers.add("WAIT_PAST_EXPIRY_ATTESTOR_LOCK_REJECTED")
    return None


def _scenario_wait_past_expiry_unique_index(
    admin: Any,
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    receipts: Mapping[str, Mapping[str, Any]],
    markers: set[str],
) -> None:
    winner = _attestation_fixture(admin, receipts["c"], "ttl-index-winner")
    loser = _structural_collision_fixture(
        admin,
        receipts["c"],
        winner,
        "p_structural_result_hash",
        "ttl-index-loser",
        expiry_seconds=6.0,
    )
    ready = Event()
    release = Event()
    ownership: Queue[dict[str, Any]] = Queue()
    deadline = _deadline()
    submissions = (
        (
            _attest_worker,
            (
                admin_parameters, expected_target, "index-winner", winner["attest"],
                ownership, deadline, None, None, ready, release, "rollback",
            ),
        ),
        (
            _attest_worker,
            (
                admin_parameters, expected_target, "index-loser", loser["attest"],
                ownership, deadline, None, ready,
            ),
        ),
    )

    def observe(
        identities: Mapping[str, Mapping[str, Any]],
        _futures: Mapping[str, Future[Any]],
        observer_deadline: float,
    ) -> None:
        _wait_event(ready, observer_deadline, "unique-index winner inserted")
        _wait_for_blocked(
            admin,
            int(identities["index-loser"]["backend_pid"]),
            ("transactionid",),
            observer_deadline,
        )
        _assert_pre_expiry(admin, loser["attest"]["p_expires_at"])
        _wait_past_expiry(
            admin, loser["attest"]["p_expires_at"], observer_deadline
        )
        release.set()

    results, _ = _run_concurrently(
        submissions,
        ownership,
        ("index-winner", "index-loser"),
        observer=observe,
        releases=(release,),
    )
    outcomes = _outcomes_by_label(results)
    if outcomes["index-winner"]["result"].get("status") != "PERSISTED":
        raise ProbeFailure("unique-index provisional winner did not insert")
    _assert_p0001(outcomes["index-loser"], "V159 attestation future-dated or expired")
    _assert_no_attestation(admin, winner)
    _assert_no_attestation(admin, loser)
    markers.add("WAIT_PAST_EXPIRY_UNIQUE_INDEX_REJECTED")
    return None


def _scenario_uncommitted_visibility(
    admin: Any,
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    receipts: Mapping[str, Mapping[str, Any]],
    markers: set[str],
) -> dict[str, Any]:
    fixture = _attestation_fixture(
        admin, receipts["c"], "concurrency-c", expiry_seconds=12.0
    )
    ready = Event()
    release = Event()
    observed: list[Mapping[str, Any]] = []
    ownership: Queue[dict[str, Any]] = Queue()
    deadline = _deadline()
    submissions = (
        (
            _attest_worker,
            (
                admin_parameters, expected_target, "visibility-writer", fixture["attest"],
                ownership, deadline, None, None, ready, release, "commit",
            ),
        ),
        (
            _read_worker,
            (
                admin_parameters, expected_target, "visibility-reader", fixture["read"],
                ownership, deadline, None, ready,
            ),
        ),
    )

    def observe(
        _identities: Mapping[str, Mapping[str, Any]],
        futures: Mapping[str, Future[Any]],
        observer_deadline: float,
    ) -> None:
        _wait_event(ready, observer_deadline, "uncommitted attestation insert")
        reader = futures["visibility-reader"].result(
            timeout=_remaining(observer_deadline)
        )
        observed.append(reader)
        release.set()

    results, _ = _run_concurrently(
        submissions,
        ownership,
        ("visibility-writer", "visibility-reader"),
        observer=observe,
        releases=(release,),
    )
    outcomes = _outcomes_by_label(results)
    if not observed or observed[0]["result"] != {
        "status": "NOT_FOUND",
        "state": "NOT_FOUND",
    }:
        raise ProbeFailure("uncommitted attestation was visible to reader")
    markers.add("UNCOMMITTED_ATTESTATION_INVISIBLE")
    if outcomes["visibility-writer"]["result"].get("status") != "PERSISTED":
        raise ProbeFailure("visibility attestation did not commit")
    found = _single_worker(
        _read_worker,
        (admin_parameters, expected_target, "visibility-after", fixture["read"]),
        "visibility-after",
    )
    if found["result"].get("state") != "ATTESTED_UNBOUND":
        raise ProbeFailure("committed attestation was not ATTESTED_UNBOUND")
    markers.add("ATTESTED_UNBOUND_AFTER_COMMIT")
    return fixture


def _partial_run_row(admin: Any, fixture: Mapping[str, Any]) -> dict[str, Any]:
    with admin.cursor() as cursor:
        cursor.execute("SELECT clock_timestamp() AS bound_at")
        row = cursor.fetchone()
    if not row:
        raise ProbeFailure("partial injection bound time is missing")
    bound_at = row["bound_at"]
    bind = fixture["bind"]
    attest = fixture["attest"]
    durable_run = _expected_durable_training_run_hash(fixture, bound_at)
    canonical_payload = {
        "schema_version": "alr_challenger_training_result_v2",
        "structural_training_run_hash": attest["p_structural_training_run_hash"],
        "durable_training_run_hash": durable_run,
        "durable_attestation_hash": fixture["durable_attestation_hash"],
        "structural_result_hash": attest["p_structural_result_hash"],
        "structural_fit_capture_hash": attest["p_structural_fit_capture_hash"],
        "structural_candidate_hash": attest["p_structural_candidate_hash"],
        "run_status": "TRAINING_PERFORMED",
        "model_training_performed": True,
        "attestation_bound_at": bound_at,
        "no_authority": deepcopy(_NO_AUTHORITY),
        "authority_counters": deepcopy(_ZERO_COUNTERS),
    }
    return {
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
        "canonical_payload": canonical_payload,
        "no_authority": deepcopy(_NO_AUTHORITY),
        "authority_counters": deepcopy(_ZERO_COUNTERS),
        "fit_started_at": bind["p_fit_started_at"],
        "fit_completed_at": bind["p_fit_completed_at"],
        "durable_attestation_hash": fixture["durable_attestation_hash"],
        "durable_training_run_hash": durable_run,
        "attestation_bound_at": bound_at,
        "attestation_verified_at": attest["p_verified_at"],
        "attestation_expires_at": attest["p_expires_at"],
    }


def _partial_bundle_worker(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    label: str,
    run_row: Mapping[str, Any],
    ownership: Queue[dict[str, Any]],
    deadline: float,
    ready: Event,
    release: Event,
) -> dict[str, Any]:
    import psycopg2  # type: ignore
    from psycopg2 import sql  # type: ignore

    with _admin_worker_session(
        admin_parameters, expected_target, label, ownership, deadline
    ) as (connection, identity):
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE FUNCTION pg_temp.v159_inject_partial_run(p_row jsonb) "
                    "RETURNS integer LANGUAGE plpgsql SECURITY DEFINER "
                    "SET search_path=pg_catalog,pg_temp AS $body$ "
                    "DECLARE r learning.alr_challenger_training_runs%ROWTYPE; BEGIN "
                    "IF session_user<>'alr_challenger_trainer_caller' OR "
                    "current_user<>'alr_challenger_writer' THEN "
                    "RAISE EXCEPTION 'partial injection identity rejected'; END IF; "
                    "IF current_setting('session_replication_role')<>'origin' THEN "
                    "RAISE EXCEPTION 'partial injection origin required'; END IF; "
                    "r:=jsonb_populate_record(NULL::learning.alr_challenger_training_runs,p_row); "
                    f"SET CONSTRAINTS {_CONSTRAINTS} DEFERRED; "
                    "INSERT INTO learning.alr_challenger_training_runs("
                    "training_run_hash,durable_receipt_hash,training_key_hash,source_head,"
                    "actual_dataset_hash,actual_row_ids_hash,actual_split_hash,"
                    "actual_code_manifest_hash,actual_training_config_hash,"
                    "actual_feature_schema_hash,actual_label_schema_hash,"
                    "model_schema_version,actual_training_rows,model_artifact_set_hash,"
                    "metrics_hash,resource_usage_hash,run_status,model_training_performed,"
                    "canonical_payload,no_authority,authority_counters,fit_started_at,"
                    "fit_completed_at,durable_attestation_hash,durable_training_run_hash,"
                    "attestation_bound_at,attestation_verified_at,attestation_expires_at) "
                    "VALUES(r.training_run_hash,r.durable_receipt_hash,r.training_key_hash,"
                    "r.source_head,r.actual_dataset_hash,r.actual_row_ids_hash,"
                    "r.actual_split_hash,r.actual_code_manifest_hash,"
                    "r.actual_training_config_hash,r.actual_feature_schema_hash,"
                    "r.actual_label_schema_hash,r.model_schema_version,"
                    "r.actual_training_rows,r.model_artifact_set_hash,r.metrics_hash,"
                    "r.resource_usage_hash,r.run_status,r.model_training_performed,"
                    "r.canonical_payload,r.no_authority,r.authority_counters,"
                    "r.fit_started_at,r.fit_completed_at,r.durable_attestation_hash,"
                    "r.durable_training_run_hash,r.attestation_bound_at,"
                    "r.attestation_verified_at,r.attestation_expires_at); RETURN 1; END "
                    "$body$"
                )
                cursor.execute(
                    "SELECT nspname FROM pg_namespace WHERE oid=pg_my_temp_schema()"
                )
                temp_row = cursor.fetchone()
                if not temp_row:
                    raise ProbeFailure("temporary injection schema is missing")
                temp_schema = temp_row["nspname"]
                signature = sql.SQL("{}.v159_inject_partial_run(jsonb)").format(
                    sql.Identifier(temp_schema)
                )
                cursor.execute(
                    sql.SQL("ALTER FUNCTION {} OWNER TO alr_challenger_writer").format(
                        signature
                    )
                )
                cursor.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA {} TO alr_challenger_writer,")
                    .format(sql.Identifier(temp_schema))
                    + sql.SQL("alr_challenger_trainer_caller")
                )
                cursor.execute(
                    sql.SQL("REVOKE ALL ON FUNCTION {} FROM PUBLIC").format(signature)
                )
                cursor.execute(
                    sql.SQL("GRANT EXECUTE ON FUNCTION {} TO ").format(signature)
                    + sql.SQL("alr_challenger_trainer_caller")
                )
                cursor.execute(
                    "SET SESSION AUTHORIZATION alr_challenger_trainer_caller"
                )
                cursor.execute(
                    sql.SQL("SELECT {}(%s::jsonb) AS rows").format(
                        sql.Identifier(temp_schema, "v159_inject_partial_run")
                    ),
                    (_adapt(_normalized(run_row)),),
                )
                inserted = cursor.fetchone()
            if inserted != {"rows": 1}:
                raise ProbeFailure("partial bundle helper did not insert one run")
            ready.set()
            _wait_event(release, deadline, "partial constraint release")
            with connection.cursor() as cursor:
                cursor.execute(
                    "SET CONSTRAINTS learning.alr_v159_run_complete_ct_v1 IMMEDIATE"
                )
            connection.commit()
            raise ProbeFailure("PARTIAL_OR_DIVERGENT bundle unexpectedly committed")
        except psycopg2.Error as exc:
            connection.rollback()
            return _error_outcome(label, identity, exc)


def _scenario_partial_bundle_injection(
    admin: Any,
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    fixture_c: Mapping[str, Any],
    markers: set[str],
) -> None:
    run_row = _partial_run_row(admin, fixture_c)
    ready = Event()
    release = Event()
    observed: list[Mapping[str, Any]] = []
    ownership: Queue[dict[str, Any]] = Queue()
    deadline = _deadline()
    submissions = (
        (
            _partial_bundle_worker,
            (
                admin_parameters, expected_target, "partial-writer", run_row,
                ownership, deadline, ready, release,
            ),
        ),
        (
            _read_worker,
            (
                admin_parameters, expected_target, "partial-reader", fixture_c["read"],
                ownership, deadline, None, ready,
            ),
        ),
    )

    def observe(
        _identities: Mapping[str, Mapping[str, Any]],
        futures: Mapping[str, Future[Any]],
        observer_deadline: float,
    ) -> None:
        _wait_event(ready, observer_deadline, "partial run inserted")
        reader = futures["partial-reader"].result(timeout=_remaining(observer_deadline))
        observed.append(reader)
        release.set()

    results, _ = _run_concurrently(
        submissions,
        ownership,
        ("partial-writer", "partial-reader"),
        observer=observe,
        releases=(release,),
    )
    outcomes = _outcomes_by_label(results)
    if not observed or observed[0]["result"].get("state") != "ATTESTED_UNBOUND":
        raise ProbeFailure("uncommitted partial bundle escaped reader isolation")
    _assert_p0001(
        outcomes["partial-writer"],
        "V159 complete bundle invariant: exact ordered q10/q50/q90 required",
    )
    markers.add("PARTIAL_DEFERRED_BUNDLE_INJECTION_REJECTED")
    snapshot = _assert_bundle_snapshot(
        admin,
        fixture_c["durable_attestation_hash"],
        fixture_c["read"]["p_structural_training_run_hash"],
    )
    if snapshot["attestations"] is None or any(
        snapshot[name] is not None for name in ("runs", "artifacts", "registry")
    ):
        raise ProbeFailure("PARTIAL_OR_DIVERGENT rollback left durable rows")
    markers.add("PARTIAL_DEFERRED_BUNDLE_ROLLBACK_CLEAN")
    return None


def _scenario_identical_bind(
    admin: Any,
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    fixture_b: Mapping[str, Any],
    markers: set[str],
) -> None:
    barrier = Barrier(2)
    release = Event()
    completed: Queue[str] = Queue()
    ownership: Queue[dict[str, Any]] = Queue()
    deadline = _deadline()
    submissions = (
        (
            _bind_worker,
            (
                admin_parameters, expected_target, "bind-b-1", fixture_b["bind"],
                ownership, deadline, barrier, None, None, release, "commit", completed,
            ),
        ),
        (
            _bind_worker,
            (
                admin_parameters, expected_target, "bind-b-2", fixture_b["bind"],
                ownership, deadline, barrier, None, None, release, "commit", completed,
            ),
        ),
    )

    def observe(
        identities: Mapping[str, Mapping[str, Any]],
        _futures: Mapping[str, Future[Any]],
        observer_deadline: float,
    ) -> None:
        winner = completed.get(timeout=_remaining(observer_deadline))
        loser = "bind-b-2" if winner == "bind-b-1" else "bind-b-1"
        winner_pid = int(identities[winner]["backend_pid"])
        loser_pid = int(identities[loser]["backend_pid"])
        _wait_for_blocked(
            admin,
            loser_pid,
            ("advisory", "AdvisoryLock"),
            observer_deadline,
        )
        _observe_domain_locks(
            admin, winner_pid, loser_pid, _bind_materials(fixture_b)
        )
        release.set()

    results, _ = _run_concurrently(
        submissions,
        ownership,
        ("bind-b-1", "bind-b-2"),
        observer=observe,
        releases=(release,),
        barriers=(barrier,),
    )
    successful = [result for result in results if result["status"] == "OK"]
    statuses = sorted(result["result"]["status"] for result in successful)
    if statuses != ["DUPLICATE", "PERSISTED"]:
        raise ProbeFailure("identical concurrent bind result set differed")
    persisted = next(result["result"] for result in successful if result["result"]["status"] == "PERSISTED")
    duplicate = next(result["result"] for result in successful if result["result"]["status"] == "DUPLICATE")
    persisted_payload = {key: value for key, value in persisted.items() if key != "status"}
    duplicate_payload = {key: value for key, value in duplicate.items() if key != "status"}
    if persisted_payload != duplicate_payload:
        raise ProbeFailure("identical bind payload parity differed")
    markers.add("IDENTICAL_BIND_PERSISTED_DUPLICATE")
    markers.add("BIND_ADVISORY_LOCKS_OBSERVED")
    readback = _single_worker(
        _read_worker,
        (admin_parameters, expected_target, "bind-b-read", fixture_b["read"]),
        "bind-b-read",
    )
    _assert_exact_bound_bundle(admin, fixture_b, persisted, readback["result"])
    markers.add("EXACT_BOUND_BUNDLE")
    return None


def _scenario_divergent_bind(
    admin: Any,
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    fixture_b: Mapping[str, Any],
    markers: set[str],
) -> None:
    before = _assert_bundle_snapshot(
        admin,
        fixture_b["durable_attestation_hash"],
        fixture_b["read"]["p_structural_training_run_hash"],
    )
    divergent = deepcopy(fixture_b["bind"])
    divergent["p_q10_size"] += 1
    ready = Event()
    release = Event()
    ownership: Queue[dict[str, Any]] = Queue()
    deadline = _deadline()
    submissions = (
        (
            _bind_worker,
            (
                admin_parameters, expected_target, "bind-b-exact-racer",
                fixture_b["bind"], ownership, deadline, None, None, ready,
                release,
            ),
        ),
        (
            _bind_worker,
            (
                admin_parameters, expected_target, "bind-b-divergent-racer",
                divergent, ownership, deadline, None, ready,
            ),
        ),
    )

    def observe(
        identities: Mapping[str, Mapping[str, Any]],
        _futures: Mapping[str, Future[Any]],
        observer_deadline: float,
    ) -> None:
        _wait_event(ready, observer_deadline, "exact bound duplicate holds locks")
        holder_pid = int(identities["bind-b-exact-racer"]["backend_pid"])
        waiter_pid = int(identities["bind-b-divergent-racer"]["backend_pid"])
        _wait_for_blocked(admin, waiter_pid, ("advisory", "AdvisoryLock"), observer_deadline)
        _observe_domain_locks(admin, holder_pid, waiter_pid, _bind_materials(fixture_b))
        release.set()

    results, _ = _run_concurrently(
        submissions,
        ownership,
        ("bind-b-exact-racer", "bind-b-divergent-racer"),
        observer=observe,
        releases=(release,),
    )
    outcomes = _outcomes_by_label(results)
    if outcomes["bind-b-exact-racer"]["result"].get("status") != "DUPLICATE":
        raise ProbeFailure("exact already-bound racer was not DUPLICATE")
    _assert_p0001(
        outcomes["bind-b-divergent-racer"],
        "V159 caller result differs from signed observation",
    )
    after = _assert_bundle_snapshot(
        admin,
        fixture_b["durable_attestation_hash"],
        fixture_b["read"]["p_structural_training_run_hash"],
    )
    if before != after:
        raise ProbeFailure("divergent bind race changed the exact bound bundle")
    markers.add("DIVERGENT_BIND_P0001_NO_PARTIAL")
    return None

def _scenario_bind_rollback(
    admin: Any,
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    fixture_a: Mapping[str, Any],
    markers: set[str],
) -> None:
    before = _assert_bundle_snapshot(
        admin,
        fixture_a["durable_attestation_hash"],
        fixture_a["read"]["p_structural_training_run_hash"],
    )
    ready = Event()
    release = Event()
    observed: list[Mapping[str, Any]] = []
    during_snapshots: list[Mapping[str, Any]] = []
    ownership: Queue[dict[str, Any]] = Queue()
    deadline = _deadline()
    submissions = (
        (
            _bind_worker,
            (
                admin_parameters, expected_target, "bind-a-rollback-writer",
                fixture_a["bind"], ownership, deadline, None, None, ready,
                release, "rollback",
            ),
        ),
        (
            _read_worker,
            (
                admin_parameters, expected_target, "bind-a-rollback-reader",
                fixture_a["read"], ownership, deadline, None, ready,
            ),
        ),
    )
    def observe(
        _identities: Mapping[str, Mapping[str, Any]],
        futures: Mapping[str, Future[Any]],
        observer_deadline: float,
    ) -> None:
        _wait_event(ready, observer_deadline, "provisional rollback bundle")
        reader = futures["bind-a-rollback-reader"].result(
            timeout=_remaining(observer_deadline)
        )
        observed.append(reader)
        during_snapshots.append(
            _assert_bundle_snapshot(
                admin,
                fixture_a["durable_attestation_hash"],
                fixture_a["read"]["p_structural_training_run_hash"],
            )
        )
        release.set()

    results, _ = _run_concurrently(
        submissions,
        ownership,
        ("bind-a-rollback-writer", "bind-a-rollback-reader"),
        observer=observe,
        releases=(release,),
    )
    provisional = _outcomes_by_label(results)["bind-a-rollback-writer"]
    if provisional["result"].get("status") != "PERSISTED":
        raise ProbeFailure("rollback bind was not provisionally persisted")
    if (
        not observed
        or observed[0]["result"].get("state") != "ATTESTED_UNBOUND"
        or not during_snapshots
        or during_snapshots[0] != before
    ):
        raise ProbeFailure("uncommitted rollback bundle was externally visible")
    unbound = _single_worker(
        _read_worker,
        (admin_parameters, expected_target, "bind-a-after-rollback", fixture_a["read"]),
        "bind-a-after-rollback",
    )
    after = _assert_bundle_snapshot(
        admin,
        fixture_a["durable_attestation_hash"],
        fixture_a["read"]["p_structural_training_run_hash"],
    )
    if unbound["result"].get("state") != "ATTESTED_UNBOUND" or after != before:
        raise ProbeFailure("rolled-back bind was externally visible")
    markers.add("BIND_ROLLBACK_ATTESTED_UNBOUND")
    committed = _single_worker(
        _bind_worker,
        (admin_parameters, expected_target, "bind-a-final", fixture_a["bind"]),
        "bind-a-final",
    )
    if committed["result"].get("status") != "PERSISTED":
        raise ProbeFailure("final A bind did not persist")
    readback = _single_worker(
        _read_worker,
        (admin_parameters, expected_target, "bind-a-final-read", fixture_a["read"]),
        "bind-a-final-read",
    )
    _assert_exact_bound_bundle(admin, fixture_a, committed["result"], readback["result"])
    return None


def _scenario_wait_past_expiry_bind(
    admin: Any,
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    fixture_c: Mapping[str, Any],
    markers: set[str],
) -> None:
    material = _bind_materials(fixture_c)[0]
    held = Event()
    release = Event()
    ownership: Queue[dict[str, Any]] = Queue()
    deadline = _deadline()
    submissions = (
        (
            _lock_holder_worker,
            (
                admin_parameters, expected_target, "bind-ttl-lock-holder", (material,),
                ownership, deadline, held, release,
            ),
        ),
        (
            _bind_worker,
            (
                admin_parameters, expected_target, "bind-ttl-loser", fixture_c["bind"],
                ownership, deadline, None, held,
            ),
        ),
    )

    def observe(
        identities: Mapping[str, Mapping[str, Any]],
        _futures: Mapping[str, Future[Any]],
        observer_deadline: float,
    ) -> None:
        _wait_event(held, observer_deadline, "bind TTL lock held")
        _wait_for_blocked(
            admin,
            int(identities["bind-ttl-loser"]["backend_pid"]),
            ("advisory", "AdvisoryLock"),
            observer_deadline,
        )
        holder_pid = int(identities["bind-ttl-lock-holder"]["backend_pid"])
        waiter_pid = int(identities["bind-ttl-loser"]["backend_pid"])
        _observe_domain_locks(admin, holder_pid, waiter_pid, (material,))
        _assert_pre_expiry(admin, fixture_c["attest"]["p_expires_at"])
        _wait_past_expiry(
            admin, fixture_c["attest"]["p_expires_at"], observer_deadline
        )
        release.set()

    results, _ = _run_concurrently(
        submissions,
        ownership,
        ("bind-ttl-lock-holder", "bind-ttl-loser"),
        observer=observe,
        releases=(release,),
    )
    outcome = _outcomes_by_label(results)["bind-ttl-loser"]
    _assert_p0001(outcome, "V159 expired or future attestation cannot bind")
    state = _single_worker(
        _read_worker,
        (admin_parameters, expected_target, "bind-ttl-read", fixture_c["read"]),
        "bind-ttl-read",
    )
    snapshot = _assert_bundle_snapshot(
        admin,
        fixture_c["durable_attestation_hash"],
        fixture_c["read"]["p_structural_training_run_hash"],
    )
    if state["result"].get("state") != "ATTESTED_UNBOUND" or any(
        snapshot[name] is not None for name in ("runs", "artifacts", "registry")
    ):
        raise ProbeFailure("wait-past-expiry bind left a bundle")
    markers.add("WAIT_PAST_EXPIRY_BIND_REJECTED")
    return None


def _assert_connection_limits(admin: Any) -> None:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT rolname,rolconnlimit FROM pg_roles WHERE rolname IN "
            "('alr_challenger_fit_attestor_caller','alr_challenger_trainer_caller') "
            "ORDER BY rolname"
        )
        rows = cursor.fetchall()
    if rows != [
        {"rolname": "alr_challenger_fit_attestor_caller", "rolconnlimit": 1},
        {"rolname": "alr_challenger_trainer_caller", "rolconnlimit": 1},
    ]:
        raise ProbeFailure("caller LOGIN role connection limits drifted")


def _global_oracle(admin: Any, markers: set[str]) -> dict[str, int]:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT "
            "(SELECT count(*) FROM learning.alr_qualified_training_receipts) AS receipts,"
            "(SELECT count(*) FROM learning.alr_challenger_fit_attestations) AS attestations,"
            "(SELECT count(*) FROM learning.alr_challenger_training_runs) AS runs,"
            "(SELECT count(*) FROM learning.alr_challenger_model_artifacts) AS artifacts,"
            "(SELECT count(*) FROM learning.alr_challenger_registry) AS registry,"
            "(SELECT count(*) FROM learning.alr_challenger_fit_attestations WHERE "
            "no_authority<>%s::jsonb OR authority_counters<>%s::jsonb) AS bad_attestation,"
            "(SELECT count(*) FROM learning.alr_challenger_training_runs WHERE "
            "no_authority<>%s::jsonb OR authority_counters<>%s::jsonb OR "
            "authority_counters->>'model_fit_count'<>'0') AS bad_run,"
            "(SELECT count(*) FROM learning.alr_challenger_model_artifacts WHERE "
            "serving_visible OR symlink_created) AS bad_artifact,"
            "(SELECT count(*) FROM learning.alr_challenger_registry WHERE "
            "serving_allowed OR promotion_allowed OR latest_pointer_allowed OR "
            "symlink_allowed) AS bad_registry",
            (
                _adapt(_NO_AUTHORITY), _adapt(_ZERO_COUNTERS),
                _adapt(_NO_AUTHORITY), _adapt(_ZERO_COUNTERS),
            ),
        )
        row = cursor.fetchone()
    if not row:
        raise ProbeFailure("global concurrency oracle returned no row")
    counts = {key: int(row[key]) for key in (
        "receipts", "attestations", "runs", "artifacts", "registry"
    )}
    if counts != {
        "receipts": 3,
        "attestations": 3,
        "runs": 2,
        "artifacts": 6,
        "registry": 2,
    }:
        raise ProbeFailure("global 3/3/2/6/2 oracle differed")
    if any(int(row[key]) != 0 for key in (
        "bad_attestation", "bad_run", "bad_artifact", "bad_registry"
    )):
        raise ProbeFailure("zero-authority or non-serving global oracle differed")
    markers.add("NO_AUTHORITY_FALSE_ZERO")
    markers.add("GLOBAL_ORACLE_3_3_2_6_2")
    return counts


def _run_scenarios(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
) -> dict[str, Any]:
    markers: set[str] = set()
    executed: list[str] = []
    admin = _connect(admin_parameters)
    receipt_connection = _connect_as_role(
        admin_parameters,
        expected_target,
        _TRAINER_CALLER,
        destructive_ack=True,
    )
    try:
        if _target_identity(admin) != dict(expected_target):
            raise ProbeFailure("scenario administrator target differs")
        _assert_connection_limits(admin)
        receipt_a = _persist_qualified_receipt(
            admin, receipt_connection, "concurrency-a"
        )
        receipt_b = _persist_qualified_receipt(
            admin, receipt_connection, "concurrency-b"
        )
        receipt_c = _persist_qualified_receipt(
            admin, receipt_connection, "concurrency-c"
        )
        receipts = {"a": receipt_a, "b": receipt_b, "c": receipt_c}

        fixture_a = _scenario_identical_attestation(
            admin, admin_parameters, expected_target, receipts, markers
        )
        executed.append("_scenario_identical_attestation")
        fixture_b = _scenario_structural_identity_collisions(
            admin, admin_parameters, expected_target, receipts, markers
        )
        executed.append("_scenario_structural_identity_collisions")
        _scenario_artifact_collisions(
            admin, admin_parameters, expected_target, receipts, fixture_b, markers
        )
        executed.append("_scenario_artifact_collisions")
        _scenario_wait_past_expiry_attestor_lock(
            admin, admin_parameters, expected_target, receipts, markers
        )
        executed.append("_scenario_wait_past_expiry_attestor_lock")
        _scenario_wait_past_expiry_unique_index(
            admin, admin_parameters, expected_target, receipts, markers
        )
        executed.append("_scenario_wait_past_expiry_unique_index")
        fixture_c = _scenario_uncommitted_visibility(
            admin, admin_parameters, expected_target, receipts, markers
        )
        executed.append("_scenario_uncommitted_visibility")
        _scenario_partial_bundle_injection(
            admin, admin_parameters, expected_target, fixture_c, markers
        )
        executed.append("_scenario_partial_bundle_injection")
        _scenario_identical_bind(
            admin, admin_parameters, expected_target, fixture_b, markers
        )
        executed.append("_scenario_identical_bind")
        _scenario_divergent_bind(
            admin, admin_parameters, expected_target, fixture_b, markers
        )
        executed.append("_scenario_divergent_bind")
        _scenario_bind_rollback(
            admin, admin_parameters, expected_target, fixture_a, markers
        )
        executed.append("_scenario_bind_rollback")
        _scenario_wait_past_expiry_bind(
            admin, admin_parameters, expected_target, fixture_c, markers
        )
        executed.append("_scenario_wait_past_expiry_bind")
        if tuple(executed) != _SCENARIO_ORDER:
            raise ProbeFailure("scenario execution order differed")
        markers.add("WORKER_CONNECTION_OWNERSHIP_UNIQUE")
        counts = _global_oracle(admin, markers)
        markers.add("SCENARIO_SUITE_COMPLETE")
        if markers != set(_REQUIRED_MARKERS):
            raise ProbeFailure("concurrency scenario marker coverage differed")
    finally:
        receipt_connection.close()
        admin.close()
    return {"markers": sorted(markers), "global_counts": counts}


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    destructive_ack = (
        args.confirm_disposable_v159_concurrency
        and os.environ.get(_ACK_ENV) == "1"
    )
    if not destructive_ack:
        raise ProbeFailure(
            "explicit concurrency disposable acknowledgement is required"
        )
    expected_sentinel = f"{_SENTINEL}:{args.expected_database}"
    if args.disposable_sentinel != expected_sentinel:
        raise ProbeFailure("exact V159 concurrency sentinel is required")
    if not _DISPOSABLE_DATABASE.search(args.expected_database.lower()):
        raise ProbeFailure("expected database is not explicitly disposable")
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
            raise ProbeFailure("administrator connection target differs")
        _seed_v159_role_preconditions(admin, destructive_ack=destructive_ack)
        expected_target = dict(identity)
        caller = _connect_as_role(
            admin_parameters,
            expected_target,
            _TRAINER_CALLER,
            destructive_ack=destructive_ack,
        )
        try:
            _assert_same_target(admin, caller, args.expected_database)
        finally:
            caller.close()
    finally:
        admin.close()
    _orchestrate_migrations(admin_parameters, expected_target, v158, v159)
    summary = _run_scenarios(admin_parameters, expected_target)
    output = {
        "schema_version": "alr_v159_concurrency_disposable_pg_probe_v1",
        "status": "PASS",
        "database": args.expected_database,
        "v158_sha256": _EXPECTED_SHA256["V158"],
        "v159_sha256": _EXPECTED_SHA256["V159"],
        "on_error_stop_equivalent": _ON_ERROR_STOP_EQUIVALENT,
        "double_apply": True,
        "scenario_markers": summary["markers"],
        "global_counts": summary["global_counts"],
        "signature_fixture_only": True,
        "external_authenticity_proven": False,
        "model_fit_performed_by_probe": False,
        "partial_deferred_bundle_injection_exercised": True,
        "partial_deferred_bundle_injection_claimed": True,
        "postgresql_executed": True,
        "session_authorization_test_only": True,
        "connection_limit_preserved": True,
        "admin_role_sessions_same_target": True,
        "utc_read_committed_sessions": True,
        "thread_local_connections": True,
        "bounded_synchronization": True,
        "advisory_lock_wait_observed": True,
    }
    print(json.dumps(output, sort_keys=True))
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
