"""Fixture-only disposable-PG16 concurrency probe for V160 consumption.

Import is inert.  The bounded workers exercise only an explicitly disposable
database and never contact an issuer/runner or execute a model fit.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from queue import Queue
from threading import Barrier, Event
from typing import Any, Mapping, Sequence

_ROOT = Path(__file__).resolve().parents[4]
_PROGRAM_CODE = _ROOT / "program_code"
if str(_PROGRAM_CODE) not in sys.path:
    sys.path.insert(0, str(_PROGRAM_CODE))

from ml_training.tests.integration.alr_atomic_fit_consumption_isolated_pg import (  # noqa: E402
    ProbeFailure,
    _DISPOSABLE_DATABASE,
    _SENTINEL as _FUNCTIONAL_SENTINEL,
    _V158,
    _V159,
    _V160,
    _assert_eight_roles,
    _bundle_counts,
    _call,
    _claim_payload,
    _connect,
    _connect_as_consumption_caller,
    _migration_bytes,
    _orchestrate,
    _parse_complete_dsn,
    _register_payload,
    _reject_ambient_libpq_routing,
    _request_fixture,
    _required_env,
    _target_identity,
    _terminal_payload,
    _verifier_fixture,
    _status_payload,
)
from ml_training.tests.integration.alr_durable_fit_attestation_isolated_pg import (  # noqa: E402
    _canonical_pg_jsonb_bytes,
)

_ACK_ENV = "ALR_V160_CONCURRENCY_DISPOSABLE_ACK"
_ADMIN_DSN_ENV = "ALR_V160_DISPOSABLE_ADMIN_DSN"
_SENTINEL = "V160_ATOMIC_FIT_CONCURRENCY_DISPOSABLE_MUTATION_CONFIRMED"
_SAFE_FAILURE_MESSAGE = "V160 atomic-fit concurrency probe failed safely"
_STATEMENT_TIMEOUT_MS = 20_000
_LOCK_TIMEOUT_MS = 19_000
_REQUIRED_MARKERS = {
    "IDENTICAL_REGISTER_PERSISTED_DUPLICATE",
    "DIVERGENT_REGISTER_ONE_CONFLICT",
    "IDENTICAL_CLAIM_PERSISTED_DUPLICATE",
    "DIVERGENT_TERMINAL_ONE_CONFLICT",
    "CLAIM_VS_EXPIRE_RACE",
    "OUT_OF_ORDER_STATUS_SERIALIZED",
    "IDENTICAL_SUCCESS_TERMINAL_PERSISTED_DUPLICATE",
    "SUCCESS_VS_NONSUCCESS_ONE_CONFLICT",
    "DIVERGENT_ARTIFACT_ONE_CONFLICT",
    "EXACT_DOMAIN_LOCK_SET_OBSERVED",
    "ROLLBACK_NO_PARTIAL",
    "WORKER_CONNECTION_OWNERSHIP_UNIQUE",
    "GLOBAL_ORACLE",
    "SCENARIO_SUITE_COMPLETE",
}


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ProbeFailure("invalid V160 concurrency probe arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(description="Run the explicit V160 concurrency probe")
    parser.add_argument("--confirm-disposable-v160-concurrency", action="store_true")
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--disposable-sentinel", required=True)
    parser.add_argument("--v158", type=Path, default=_V158)
    parser.add_argument("--v159", type=Path, default=_V159)
    parser.add_argument("--v160", type=Path, default=_V160)
    return parser


def _worker(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    label: str,
    action: str,
    payload: Mapping[str, Any],
    barrier: Barrier,
    ownership: Queue[dict[str, Any]],
    *,
    resolution: str = "commit",
) -> dict[str, Any]:
    import psycopg2  # type: ignore

    connection = _connect_as_consumption_caller(admin_parameters, expected_target)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL statement_timeout='{_STATEMENT_TIMEOUT_MS}ms'")
            cursor.execute(f"SET LOCAL lock_timeout='{_LOCK_TIMEOUT_MS}ms'")
            cursor.execute("SELECT pg_backend_pid() AS backend_pid")
            identity = {
                "worker": label,
                "backend_pid": int(cursor.fetchone()["backend_pid"]),
                "thread_id": threading.get_ident(),
            }
        ownership.put(identity, timeout=5.0)
        barrier.wait(timeout=5.0)
        try:
            result = _call(connection, action, payload)
            if resolution == "commit":
                connection.commit()
            elif resolution == "rollback":
                connection.rollback()
            else:
                raise ProbeFailure("unknown V160 worker transaction resolution")
            return {
                **identity,
                "status": "OK",
                "sqlstate": None,
                "result": result,
                "resolution": resolution,
            }
        except psycopg2.Error as exc:
            connection.rollback()
            return {
                **identity,
                "status": "ERROR",
                "sqlstate": exc.pgcode,
                "result": None,
                "resolution": "rollback",
            }
    finally:
        connection.close()


def _run_pair(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    action: str,
    payloads: Sequence[Mapping[str, Any]],
    labels: Sequence[str],
    ownership: Queue[dict[str, Any]],
    resolutions: Sequence[str] = ("commit", "commit"),
) -> list[dict[str, Any]]:
    if len(payloads) != 2 or len(labels) != 2 or len(resolutions) != 2:
        raise ProbeFailure("V160 pair runner requires exactly two workers")
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="v160-probe") as executor:
        futures = [
            executor.submit(
                _worker,
                admin_parameters,
                expected_target,
                label,
                action,
                payload,
                barrier,
                ownership,
                resolution=resolution,
            )
            for label, payload, resolution in zip(labels, payloads, resolutions, strict=True)
        ]
        return [future.result(timeout=25.0) for future in futures]


def _run_mixed_pair(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    actions: Sequence[str],
    payloads: Sequence[Mapping[str, Any]],
    labels: Sequence[str],
    ownership: Queue[dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(actions) != 2 or len(payloads) != 2 or len(labels) != 2:
        raise ProbeFailure("V160 mixed pair runner requires exactly two workers")
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="v160-mixed") as executor:
        futures = [
            executor.submit(
                _worker,
                admin_parameters,
                expected_target,
                label,
                action,
                payload,
                barrier,
                ownership,
            )
            for label, action, payload in zip(labels, actions, payloads, strict=True)
        ]
        return [future.result(timeout=25.0) for future in futures]


def _status_variant(
    admin: Any,
    request: Mapping[str, Any],
    generation: int,
    issued_at: str,
) -> dict[str, Any]:
    payload = _status_payload(admin, request)
    projection = deepcopy(payload["response_projection"])
    projection["signed_payload"]["status_generation"] = generation
    projection["signed_payload"]["status_issued_at"] = issued_at
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


def _divergent_artifact_terminal(
    admin: Any,
    request: Mapping[str, Any],
    fixture: Mapping[str, Any],
) -> dict[str, Any]:
    payload = _terminal_payload(admin, request, fixture, "SUCCEEDED")
    inner = deepcopy(fixture["attest"]["p_receipt_projection"])
    q10 = hashlib.sha256(b"v160-divergent-q10").hexdigest()
    q50 = inner["result_observation"]["artifacts"]["q50"]["artifact_hash"]
    q90 = inner["result_observation"]["artifacts"]["q90"]["artifact_hash"]
    artifact_set = hashlib.sha256(
        f"q10={q10}\nq50={q50}\nq90={q90}\n".encode("utf-8")
    ).hexdigest()
    inner["result_observation"]["artifacts"]["q10"]["artifact_hash"] = q10
    inner["subject"]["ordered_artifact_set_hash"] = artifact_set
    inner_bytes, _ = _canonical_pg_jsonb_bytes(admin, inner)
    projection = deepcopy(payload["response_projection"])
    signed = projection["signed_payload"]
    signed["inner_receipt_bytes_base64url"] = (
        base64.urlsafe_b64encode(inner_bytes).decode("ascii").rstrip("=")
    )
    signed["inner_receipt_digest_sha256"] = hashlib.sha256(inner_bytes).hexdigest()
    signed["v159_subject"] = deepcopy(inner["subject"])
    signed["result_observation"] = deepcopy(inner["result_observation"])
    signed["ordered_artifact_set_hash"] = artifact_set
    event_bytes, _ = _canonical_pg_jsonb_bytes(admin, projection)
    verifier, verifier_bytes = _verifier_fixture(
        admin,
        request["bytes"],
        "TERMINAL_SUCCESS",
        terminal_bytes=event_bytes,
        inner_bytes=inner_bytes,
    )
    return {
        "request_hash": request["projection"]["request_hash"],
        "response_bytes_hex": event_bytes.hex(),
        "response_projection": projection,
        "inner_receipt_bytes_hex": inner_bytes.hex(),
        "verification_receipt_bytes_hex": verifier_bytes.hex(),
        "verification_receipt": verifier,
    }


def _lock_holder(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    payload: Mapping[str, Any],
    observation: Queue[dict[str, Any]],
    ready: Event,
    release: Event,
) -> dict[str, Any]:
    connection = _connect_as_consumption_caller(admin_parameters, expected_target)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL statement_timeout='{_STATEMENT_TIMEOUT_MS}ms'")
            cursor.execute("SELECT pg_backend_pid() AS backend_pid")
            backend_pid = int(cursor.fetchone()["backend_pid"])
        result = _call(connection, "REGISTER_REQUEST", payload)
        lock_result = {"backend_pid": backend_pid, "result": result}
        observation.put(lock_result, timeout=5.0)
        ready.set()
        if not release.wait(timeout=10.0):
            raise ProbeFailure("V160 advisory-lock observer did not release holder")
        connection.commit()
        return lock_result
    finally:
        connection.close()


def _status_set(outcomes: Sequence[Mapping[str, Any]]) -> set[tuple[str, str | None]]:
    return {
        (
            str(outcome["status"]),
            outcome.get("result", {}).get("status")
            if isinstance(outcome.get("result"), Mapping)
            else outcome.get("sqlstate"),
        )
        for outcome in outcomes
    }


def _outcomes_by_worker(
    outcomes: Sequence[Mapping[str, Any]], expected_workers: set[str]
) -> dict[str, Mapping[str, Any]]:
    mapped = {str(outcome["worker"]): outcome for outcome in outcomes}
    if set(mapped) != expected_workers or len(mapped) != len(outcomes):
        raise ProbeFailure("V160 concurrency worker outcome identity drifted")
    return mapped


def _claim_expire_eligibility(admin: Any, request_hash: str) -> dict[str, Any]:
    with admin.cursor() as cursor:
        cursor.execute(
            "WITH observed AS (SELECT clock_timestamp() AS observed_at) "
            "SELECT r.accept_by,observed.observed_at,"
            "observed.observed_at<r.accept_by AS claim_eligible,"
            "observed.observed_at>=r.accept_by AS expire_eligible,"
            "(SELECT count(*) FROM learning.alr_challenger_consumption_claims c "
            " WHERE c.request_hash=r.request_hash) AS claims,"
            "(SELECT count(*) FROM learning.alr_challenger_consumption_terminals t "
            " WHERE t.request_hash=r.request_hash) AS terminals "
            "FROM learning.alr_challenger_consumption_requests r CROSS JOIN observed "
            "WHERE r.request_hash=%s",
            (request_hash,),
        )
        row = cursor.fetchone()
    if not row:
        raise ProbeFailure("V160 claim/expire eligibility row was missing")
    return dict(row)


def _await_expire_eligibility(
    admin: Any, request_hash: str, *, timeout_seconds: float = 5.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        evidence = _claim_expire_eligibility(admin, request_hash)
        if evidence["claims"] != 0 or evidence["terminals"] != 0:
            raise ProbeFailure("V160 expiry eligibility acquired after durable winner")
        if evidence["expire_eligible"] is True:
            if evidence["claim_eligible"] is not False:
                raise ProbeFailure("V160 expiry eligibility boundary was ambiguous")
            return evidence
        time.sleep(0.05)
    raise ProbeFailure("V160 expiry eligibility boundary timed out")


def _prepare_registered_claim(
    admin: Any,
    caller: Any,
    request: Mapping[str, Any],
    label: str,
) -> None:
    if _call(caller, "REGISTER_REQUEST", _register_payload(admin, request)).get("status") != "PERSISTED":
        raise ProbeFailure("V160 concurrency setup register failed")
    caller.commit()
    if _call(caller, "CLAIM_REQUEST", _claim_payload(admin, request, label)).get("status") != "PERSISTED":
        raise ProbeFailure("V160 concurrency setup claim failed")
    caller.commit()


def _global_oracle(admin: Any) -> dict[str, int]:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT "
            "(SELECT count(*) FROM learning.alr_challenger_consumption_requests) AS requests,"
            "(SELECT count(*) FROM learning.alr_challenger_consumption_claims) AS claims,"
            "(SELECT count(*) FROM learning.alr_challenger_consumption_terminals) AS terminals,"
            "(SELECT count(*) FROM learning.alr_challenger_fit_attestations) AS attestations,"
            "(SELECT count(*) FROM learning.alr_challenger_training_runs) AS runs,"
            "(SELECT count(*) FROM learning.alr_challenger_model_artifacts) AS artifacts,"
            "(SELECT count(*) FROM learning.alr_challenger_registry) AS registry"
        )
        row = cursor.fetchone()
    if not row:
        raise ProbeFailure("V160 concurrency global oracle returned no row")
    return {key: int(value) for key, value in row.items()}


def _run_scenarios(
    admin_parameters: Mapping[str, str],
    expected_target: Mapping[str, Any],
    fixtures: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    markers: set[str] = set()
    ownership: Queue[dict[str, Any]] = Queue()
    admin = _connect(admin_parameters)
    caller = _connect_as_consumption_caller(admin_parameters, expected_target)
    try:
        requests = {
            label: _request_fixture(
                admin,
                fixture,
                f"concurrency-{label}",
                accept_seconds=180.0 if label == "success" else 30.0,
            )
            for label, fixture in fixtures.items()
        }

        identical = requests["success"]
        identical_payload = _register_payload(admin, identical)
        outcomes = _run_pair(
            admin_parameters,
            expected_target,
            "REGISTER_REQUEST",
            (identical_payload, identical_payload),
            ("identical-register-a", "identical-register-b"),
            ownership,
        )
        if _status_set(outcomes) != {("OK", "PERSISTED"), ("OK", "DUPLICATE")}:
            raise ProbeFailure("identical V160 register did not serialize persisted/duplicate")
        markers.add("IDENTICAL_REGISTER_PERSISTED_DUPLICATE")

        divergent = requests["rejected"]
        left = _register_payload(admin, divergent)
        right = deepcopy(left)
        right["request_projection"]["fixture_variant"] = "right"
        right_bytes, _ = _canonical_pg_jsonb_bytes(admin, right["request_projection"])
        right["request_bytes_hex"] = right_bytes.hex()
        verifier, verifier_bytes = _verifier_fixture(admin, right_bytes, "REQUEST_ONLY")
        right["verification_receipt"] = verifier
        right["verification_receipt_bytes_hex"] = verifier_bytes.hex()
        outcomes = _run_pair(
            admin_parameters,
            expected_target,
            "REGISTER_REQUEST",
            (left, right),
            ("divergent-register-a", "divergent-register-b"),
            ownership,
        )
        if _status_set(outcomes) != {("OK", "PERSISTED"), ("ERROR", "P0001")}:
            raise ProbeFailure("divergent V160 register did not produce one durable conflict")
        markers.add("DIVERGENT_REGISTER_ONE_CONFLICT")

        claim_request = requests["failed"]
        if _call(caller, "REGISTER_REQUEST", _register_payload(admin, claim_request)).get("status") != "PERSISTED":
            raise ProbeFailure("V160 identical-claim setup register failed")
        caller.commit()
        claim = _claim_payload(admin, claim_request, "identical-claim")
        outcomes = _run_pair(
            admin_parameters,
            expected_target,
            "CLAIM_REQUEST",
            (claim, claim),
            ("identical-claim-a", "identical-claim-b"),
            ownership,
        )
        if _status_set(outcomes) != {("OK", "PERSISTED"), ("OK", "DUPLICATE")}:
            raise ProbeFailure("identical V160 claim did not serialize persisted/duplicate")
        markers.add("IDENTICAL_CLAIM_PERSISTED_DUPLICATE")

        terminal_request = requests["expired"]
        _prepare_registered_claim(admin, caller, terminal_request, "terminal-conflict")
        rejected = _terminal_payload(admin, terminal_request, fixtures["expired"], "REJECTED_PRE_FIT")
        failed = _terminal_payload(admin, terminal_request, fixtures["expired"], "FAILED_AFTER_START")
        outcomes = _run_pair(
            admin_parameters,
            expected_target,
            "CONSUME_TERMINAL",
            (rejected, failed),
            ("terminal-rejected", "terminal-failed"),
            ownership,
        )
        if _status_set(outcomes) != {("OK", "PERSISTED"), ("ERROR", "P0001")}:
            raise ProbeFailure("divergent V160 terminal did not produce one durable conflict")
        markers.add("DIVERGENT_TERMINAL_ONE_CONFLICT")

        claim_winner = identical
        claim_winner_hash = claim_winner["projection"]["request_hash"]
        claim_eligibility = _claim_expire_eligibility(admin, claim_winner_hash)
        if claim_eligibility["claim_eligible"] is not True or claim_eligibility[
            "expire_eligible"
        ] is not False or claim_eligibility["claims"] != 0 or claim_eligibility[
            "terminals"
        ] != 0:
            raise ProbeFailure("V160 claim-winner eligibility evidence was not exact")
        claim_outcomes = _run_mixed_pair(
            admin_parameters,
            expected_target,
            ("CLAIM_REQUEST", "EXPIRE_UNCLAIMED"),
            (
                _claim_payload(admin, claim_winner, "claim-winner"),
                {
                    "request_hash": claim_winner_hash,
                    "reason": "ACCEPT_WINDOW_ELAPSED",
                },
            ),
            ("claim-winner-claim", "claim-winner-expire"),
            ownership,
        )
        claim_by_worker = _outcomes_by_worker(
            claim_outcomes, {"claim-winner-claim", "claim-winner-expire"}
        )
        if _status_set((claim_by_worker["claim-winner-claim"],)) != {
            ("OK", "PERSISTED")
        } or _status_set((claim_by_worker["claim-winner-expire"],)) != {
            ("ERROR", "P0001")
        }:
            raise ProbeFailure("V160 eligible claim did not deterministically win")
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT "
                "(SELECT count(*) FROM learning.alr_challenger_consumption_claims "
                " WHERE request_hash=%s) AS claims,"
                "(SELECT count(*) FROM learning.alr_challenger_consumption_terminals "
                " WHERE request_hash=%s) AS terminals,"
                "(SELECT max(outcome) FROM learning.alr_challenger_consumption_terminals "
                " WHERE request_hash=%s) AS terminal_outcome",
                (claim_winner_hash, claim_winner_hash, claim_winner_hash),
            )
            claim_winner_rows = cursor.fetchone()
        if claim_winner_rows != {
            "claims": 1,
            "terminals": 0,
            "terminal_outcome": None,
        }:
            raise ProbeFailure("V160 claim-winner durable readback was not exact")

        expire_winner = _request_fixture(
            admin,
            fixtures["claim_expire"],
            "concurrency-claim-expire",
            accept_seconds=2.0,
        )
        expire_winner_hash = expire_winner["projection"]["request_hash"]
        if _call(
            caller, "REGISTER_REQUEST", _register_payload(admin, expire_winner)
        ).get("status") != "PERSISTED":
            raise ProbeFailure("V160 expire-winner setup register failed")
        caller.commit()
        expire_eligibility = _await_expire_eligibility(admin, expire_winner_hash)
        expire_outcomes = _run_mixed_pair(
            admin_parameters,
            expected_target,
            ("CLAIM_REQUEST", "EXPIRE_UNCLAIMED"),
            (
                _claim_payload(admin, expire_winner, "expire-winner"),
                {
                    "request_hash": expire_winner_hash,
                    "reason": "ACCEPT_WINDOW_ELAPSED",
                },
            ),
            ("expire-winner-claim", "expire-winner-expire"),
            ownership,
        )
        expire_by_worker = _outcomes_by_worker(
            expire_outcomes, {"expire-winner-claim", "expire-winner-expire"}
        )
        if _status_set((expire_by_worker["expire-winner-claim"],)) != {
            ("ERROR", "P0001")
        } or _status_set((expire_by_worker["expire-winner-expire"],)) != {
            ("OK", "PERSISTED")
        }:
            raise ProbeFailure("V160 eligible expiry did not deterministically win")
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT "
                "(SELECT count(*) FROM learning.alr_challenger_consumption_claims "
                " WHERE request_hash=%s) AS claims,"
                "(SELECT count(*) FROM learning.alr_challenger_consumption_terminals "
                " WHERE request_hash=%s) AS terminals,"
                "(SELECT max(outcome) FROM learning.alr_challenger_consumption_terminals "
                " WHERE request_hash=%s) AS terminal_outcome",
                (expire_winner_hash, expire_winner_hash, expire_winner_hash),
            )
            expire_winner_rows = cursor.fetchone()
        if expire_winner_rows != {
            "claims": 0,
            "terminals": 1,
            "terminal_outcome": "EXPIRED_UNCLAIMED",
        }:
            raise ProbeFailure("V160 expire-winner durable readback was not exact")
        claim_expire_evidence = {
            "claim_wins": {
                "claim_eligible": True,
                "expire_eligible": False,
                "observed_at": str(claim_eligibility["observed_at"]),
                "accept_by": str(claim_eligibility["accept_by"]),
                "winner": "CLAIM_REQUEST",
                "readback": dict(claim_winner_rows),
            },
            "expire_wins": {
                "claim_eligible": False,
                "expire_eligible": True,
                "observed_at": str(expire_eligibility["observed_at"]),
                "accept_by": str(expire_eligibility["accept_by"]),
                "winner": "EXPIRE_UNCLAIMED",
                "readback": dict(expire_winner_rows),
            },
        }
        claim_expire_expected_claims = 7
        claim_expire_expected_terminals = 5
        markers.add("CLAIM_VS_EXPIRE_RACE")

        status_request = requests["status_race"]
        _prepare_registered_claim(admin, caller, status_request, "status-race")
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT to_char((clock_timestamp()-interval '2 seconds') AT TIME ZONE 'UTC',"
                "'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS lower,"
                "to_char((clock_timestamp()-interval '1 second') AT TIME ZONE 'UTC',"
                "'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS upper"
            )
            status_times = cursor.fetchone()
        if not status_times:
            raise ProbeFailure("V160 status race clock fixture returned no row")
        lower = _status_variant(admin, status_request, 1, status_times["lower"])
        upper = _status_variant(admin, status_request, 2, status_times["upper"])
        outcomes = _run_pair(
            admin_parameters,
            expected_target,
            "RECORD_STATUS",
            (lower, upper),
            ("status-generation-1", "status-generation-2"),
            ownership,
        )
        status_by_worker = _outcomes_by_worker(
            outcomes, {"status-generation-1", "status-generation-2"}
        )
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT status_generation,status_issued_at FROM learning.alr_challenger_consumption_statuses "
                "WHERE request_hash=%s ORDER BY status_generation",
                (status_request["projection"]["request_hash"],),
            )
            status_rows = cursor.fetchall()
        status_generations = [int(row["status_generation"]) for row in status_rows]
        if status_generations == [1]:
            raise ProbeFailure("V160 status race retained forbidden lower-only generation")
        if status_generations == [1, 2]:
            if _status_set((status_by_worker["status-generation-1"],)) != {
                ("OK", "PERSISTED")
            } or _status_set((status_by_worker["status-generation-2"],)) != {
                ("OK", "PERSISTED")
            }:
                raise ProbeFailure("V160 two-row status outcome/readback mapping drifted")
            if status_rows[1]["status_issued_at"] <= status_rows[0]["status_issued_at"]:
                raise ProbeFailure("V160 two-row status sequence was not monotonic")
        elif status_generations == [2]:
            if _status_set((status_by_worker["status-generation-1"],)) != {
                ("ERROR", "P0001")
            } or _status_set((status_by_worker["status-generation-2"],)) != {
                ("OK", "PERSISTED")
            }:
                raise ProbeFailure("V160 upper-only status outcome/readback mapping drifted")
        else:
            raise ProbeFailure("V160 status race persisted a forbidden generation set")
        status_ordering_evidence = {
            "generations": status_generations,
            "generation_1": sorted(_status_set((status_by_worker["status-generation-1"],))),
            "generation_2": sorted(_status_set((status_by_worker["status-generation-2"],))),
            "lower_only_rejected": True,
        }
        markers.add("OUT_OF_ORDER_STATUS_SERIALIZED")

        success_request = requests["terminal_success"]
        _prepare_registered_claim(admin, caller, success_request, "terminal-success")
        success_terminal = _terminal_payload(
            admin, success_request, fixtures["terminal_success"], "SUCCEEDED"
        )
        outcomes = _run_pair(
            admin_parameters,
            expected_target,
            "CONSUME_TERMINAL",
            (success_terminal, success_terminal),
            ("success-terminal-a", "success-terminal-b"),
            ownership,
        )
        if _status_set(outcomes) != {("OK", "PERSISTED"), ("OK", "DUPLICATE")}:
            raise ProbeFailure("identical V160 success terminals were not persisted/duplicate")
        success_counts = _bundle_counts(
            admin, success_request["projection"]["request_hash"]
        )
        if success_counts != {
            "terminals": 1,
            "attestations": 1,
            "runs": 1,
            "artifacts": 3,
            "registry": 1,
            "reconciliation": 0,
        }:
            raise ProbeFailure("identical success terminal race broke atomic bundle cardinality")
        markers.add("IDENTICAL_SUCCESS_TERMINAL_PERSISTED_DUPLICATE")

        mixed_terminal_request = requests["success_conflict"]
        _prepare_registered_claim(
            admin, caller, mixed_terminal_request, "success-nonsuccess"
        )
        success_candidate = _terminal_payload(
            admin,
            mixed_terminal_request,
            fixtures["success_conflict"],
            "SUCCEEDED",
        )
        failure_candidate = _terminal_payload(
            admin,
            mixed_terminal_request,
            fixtures["success_conflict"],
            "FAILED_AFTER_START",
        )
        outcomes = _run_pair(
            admin_parameters,
            expected_target,
            "CONSUME_TERMINAL",
            (success_candidate, failure_candidate),
            ("success-racer", "failure-racer"),
            ownership,
        )
        if _status_set(outcomes) != {("OK", "PERSISTED"), ("ERROR", "P0001")}:
            raise ProbeFailure("success/non-success terminal race lacked one conflict")
        mixed_counts = _bundle_counts(
            admin, mixed_terminal_request["projection"]["request_hash"]
        )
        allowed_mixed_counts = (
            {
                "terminals": 1,
                "attestations": 1,
                "runs": 1,
                "artifacts": 3,
                "registry": 1,
                "reconciliation": 0,
            },
            {
                "terminals": 1,
                "attestations": 0,
                "runs": 0,
                "artifacts": 0,
                "registry": 0,
                "reconciliation": 1,
            },
        )
        if mixed_counts not in allowed_mixed_counts:
            raise ProbeFailure("success/non-success race left a partial bundle")
        markers.add("SUCCESS_VS_NONSUCCESS_ONE_CONFLICT")

        artifact_request = requests["artifact_race"]
        _prepare_registered_claim(admin, caller, artifact_request, "artifact-race")
        canonical_artifact = _terminal_payload(
            admin, artifact_request, fixtures["artifact_race"], "SUCCEEDED"
        )
        divergent_artifact = _divergent_artifact_terminal(
            admin, artifact_request, fixtures["artifact_race"]
        )
        outcomes = _run_pair(
            admin_parameters,
            expected_target,
            "CONSUME_TERMINAL",
            (canonical_artifact, divergent_artifact),
            ("artifact-canonical", "artifact-divergent"),
            ownership,
        )
        if _status_set(outcomes) != {("OK", "PERSISTED"), ("ERROR", "P0001")}:
            raise ProbeFailure("divergent artifact terminal race lacked one conflict")
        artifact_counts = _bundle_counts(
            admin, artifact_request["projection"]["request_hash"]
        )
        if artifact_counts != {
            "terminals": 1,
            "attestations": 1,
            "runs": 1,
            "artifacts": 3,
            "registry": 1,
            "reconciliation": 0,
        }:
            raise ProbeFailure("divergent artifact race left a partial V159 bundle")
        markers.add("DIVERGENT_ARTIFACT_ONE_CONFLICT")

        lock_request = requests["locks"]
        lock_payload = _register_payload(admin, lock_request)
        lock_signed = lock_request["projection"]["signed_payload"]
        lock_admission = lock_signed["admission"]
        lock_materials = (
            "v160:admission:"
            f"{lock_admission['durable_receipt_hash']}:"
            f"{lock_admission['training_key_hash']}",
            "v160:generation:"
            f"{lock_admission['durable_receipt_hash']}:"
            f"{lock_admission['training_key_hash']}:"
            f"{lock_signed['request_generation']}",
            f"v160:issuer_nonce:{lock_signed['issuer_id']}:{lock_signed['nonce_digest']}",
            f"v160:request:{lock_request['projection']['request_hash']}",
        )
        lock_observation: Queue[dict[str, Any]] = Queue()
        ready = Event()
        release = Event()
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="v160-lock") as executor:
            future = executor.submit(
                _lock_holder,
                admin_parameters,
                expected_target,
                lock_payload,
                lock_observation,
                ready,
                release,
            )
            try:
                if not ready.wait(timeout=10.0):
                    raise ProbeFailure("V160 lock holder did not reach observation point")
                lock_result = lock_observation.get(timeout=5.0)
                with admin.cursor() as cursor:
                    cursor.execute(
                        "WITH expected AS ("
                        " SELECT DISTINCT hashtextextended(material,0) AS lock_key"
                        " FROM unnest(%s::text[]) material),"
                        "observed AS ("
                        " SELECT database,classid,objid,objsubid,granted,mode"
                        " FROM pg_catalog.pg_locks"
                        " WHERE locktype='advisory' AND pid=%s),"
                        "matched AS ("
                        " SELECT expected.lock_key FROM expected JOIN observed"
                        " ON observed.classid="
                        "(((expected.lock_key >> 32) & 4294967295)::oid)"
                        " AND observed.objid=((expected.lock_key & 4294967295)::oid))"
                        " SELECT"
                        " (SELECT array_agg(lock_key ORDER BY lock_key) FROM expected)"
                        " AS expected_keys,"
                        " (SELECT array_agg(lock_key ORDER BY lock_key) FROM matched)"
                        " AS matched_keys,"
                        " (SELECT count(*) FROM observed) AS observed_count,"
                        " (SELECT bool_and(granted IS TRUE AND mode='ExclusiveLock'"
                        " AND database=(SELECT oid FROM pg_catalog.pg_database"
                        " WHERE datname=current_database()) AND objsubid=1)"
                        " FROM observed) AS exact_properties",
                        (list(lock_materials), lock_result["backend_pid"]),
                    )
                    lock_row = cursor.fetchone()
                if (
                    not lock_row
                    or len(lock_row["expected_keys"] or []) != 4
                    or lock_row["matched_keys"] != lock_row["expected_keys"]
                    or lock_row["observed_count"] != 4
                    or lock_row["exact_properties"] is not True
                ):
                    raise ProbeFailure("V160 exact advisory lock domain set was not observable")
            finally:
                release.set()
            completed_lock_result = future.result(timeout=15.0)
        if completed_lock_result != lock_result:
            raise ProbeFailure("V160 lock-holder observation identity drifted")
        if lock_result.get("result", {}).get("status") != "PERSISTED":
            raise ProbeFailure("V160 lock-holder register did not persist")
        markers.add("EXACT_DOMAIN_LOCK_SET_OBSERVED")

        rollback_request = requests["reconcile"]
        rollback_payload = _register_payload(admin, rollback_request)
        barrier = Barrier(1)
        rolled_back = _worker(
            admin_parameters,
            expected_target,
            "rollback-register",
            "REGISTER_REQUEST",
            rollback_payload,
            barrier,
            ownership,
            resolution="rollback",
        )
        if rolled_back.get("status") != "OK":
            raise ProbeFailure("V160 rollback worker failed before rollback")
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) AS count FROM learning.alr_challenger_consumption_requests WHERE request_hash=%s",
                (rollback_request["projection"]["request_hash"],),
            )
            if cursor.fetchone() != {"count": 0}:
                raise ProbeFailure("V160 rolled-back register left partial state")
        if _call(caller, "REGISTER_REQUEST", rollback_payload).get("status") != "PERSISTED":
            raise ProbeFailure("V160 register after rollback did not persist")
        caller.commit()
        markers.add("ROLLBACK_NO_PARTIAL")

        ownership_rows: list[dict[str, Any]] = []
        while not ownership.empty():
            ownership_rows.append(ownership.get_nowait())
        backend_ids = [row["backend_pid"] for row in ownership_rows]
        worker_pairs = {(row["backend_pid"], row["thread_id"]) for row in ownership_rows}
        if len(backend_ids) != len(set(backend_ids)) or len(worker_pairs) != len(ownership_rows):
            raise ProbeFailure("V160 workers reused backend or thread ownership")
        markers.add("WORKER_CONNECTION_OWNERSHIP_UNIQUE")

        oracle = _global_oracle(admin)
        if (
            oracle["requests"] != 11
            or oracle["claims"] != claim_expire_expected_claims
            or oracle["terminals"] != claim_expire_expected_terminals
        ):
            raise ProbeFailure("V160 concurrency request/claim/terminal oracle drifted")
        if not (
            oracle["attestations"] == oracle["runs"] == oracle["registry"]
            and oracle["attestations"] in {2, 3}
            and oracle["artifacts"] == oracle["attestations"] * 3
        ):
            raise ProbeFailure("V160 concurrency success bundle global oracle drifted")
        markers.add("GLOBAL_ORACLE")
        markers.add("SCENARIO_SUITE_COMPLETE")
        if markers != _REQUIRED_MARKERS:
            raise ProbeFailure("V160 concurrency marker coverage is incomplete")
        return {
            "markers": sorted(markers),
            "global_oracle": oracle,
            "claim_expire_evidence": claim_expire_evidence,
            "status_ordering_evidence": status_ordering_evidence,
        }
    finally:
        caller.close()
        admin.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.confirm_disposable_v160_concurrency or os.environ.get(_ACK_ENV) != "1":
        raise ProbeFailure(
            f"explicit --confirm-disposable-v160-concurrency and {_ACK_ENV}=1 are required"
        )
    if _FUNCTIONAL_SENTINEL == _SENTINEL:
        raise ProbeFailure("functional and concurrency sentinels must remain distinct")
    if args.disposable_sentinel != f"{_SENTINEL}:{args.expected_database}":
        raise ProbeFailure("the exact V160 concurrency sentinel suffixed by database is required")
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
        _assert_eight_roles(admin)
        expected_target = dict(identity)
    finally:
        admin.close()
    fixtures, fingerprint = _orchestrate(admin_parameters, expected_target, payloads)
    summary = _run_scenarios(admin_parameters, expected_target, fixtures)
    print(
        json.dumps(
            {
                "schema_version": "alr_v160_concurrency_disposable_pg_probe_v1",
                "status": "PASS",
                "database": args.expected_database,
                "migration_sha256": digests,
                "schema_fingerprint": fingerprint,
                "scenario_markers": summary["markers"],
                "global_oracle": summary["global_oracle"],
                "claim_expire_evidence": summary["claim_expire_evidence"],
                "status_ordering_evidence": summary["status_ordering_evidence"],
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
