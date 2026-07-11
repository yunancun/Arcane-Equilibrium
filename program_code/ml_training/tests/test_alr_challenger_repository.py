from __future__ import annotations

import copy
import hashlib
import inspect
import json
from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from ml_training.alr_challenger_repository import (
    AlrChallengerRepositoryError,
    persist_qualified_training_receipt,
    read_qualified_training_receipt,
)
from ml_training.alr_challenger_training_contract import (
    build_alr_challenger_training_contract,
    compute_alr_challenger_training_contract_hash,
)
from ml_training.tests.test_alr_challenger_training_contract import (
    _code_manifest,
    _ready_receipt,
    _training_config,
)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _training_contract() -> dict[str, Any]:
    return build_alr_challenger_training_contract(
        _ready_receipt(reward_count=2),
        code_manifest=_code_manifest(),
        training_config=_training_config(),
    )


def _rehash_contract(contract: dict[str, Any]) -> None:
    contract["training_input_hash"] = _canonical_hash(contract["input_lineage"])
    contract["training_key_hash"] = _canonical_hash(
        {
            "schema_version": contract["schema_version"],
            "repository_receipt_hash": contract["repository_receipt_hash"],
            "training_input_hash": contract["training_input_hash"],
            "code_manifest_hash": contract["code_manifest"]["code_manifest_hash"],
            "training_config_hash": contract["training_config"][
                "training_config_hash"
            ],
        }
    )
    contract["contract_hash"] = compute_alr_challenger_training_contract_hash(
        contract
    )


def _expected_payload(contract: dict[str, Any]) -> dict[str, Any]:
    lineage = contract["input_lineage"]
    reward_set_hash = _canonical_hash(
        {
            "schema_version": "alr_qualified_reward_set_v1",
            "reward_record_hashes": copy.deepcopy(
                lineage["reward_record_hashes"]
            ),
        }
    )
    payload_without_hash = {
        "schema_version": "alr_qualified_training_receipt_v1",
        "source_receipt_hash": contract["repository_receipt_hash"],
        "source_contract_hash": contract["contract_hash"],
        "projection_artifact_hash": lineage["projection_artifact_hash"],
        "projection_artifact_kind": "learning_target",
        "selection_binding_hash": lineage["selection_binding_hash"],
        "proof_input_hash": lineage["proof_input_hash"],
        "proof_packet_hash": lineage["proof_packet_hash"],
        "reward_set_hash": reward_set_hash,
        "pit_dataset_manifest_hash": lineage["pit_dataset_manifest_hash"],
        "after_cost_label_set_hash": lineage["after_cost_label_set_hash"],
        "evidence_set_hash": lineage["evidence_set_hash"],
        "training_input_hash": contract["training_input_hash"],
        "training_key_hash": contract["training_key_hash"],
        "code_manifest_hash": contract["code_manifest"]["code_manifest_hash"],
        "training_config_hash": contract["training_config"][
            "training_config_hash"
        ],
        "receipt_status": "QUALIFIED_INPUT_PERSISTED",
        "training_allowed": False,
        "model_training_performed": False,
        "registry_write_allowed": False,
        "runtime_or_exchange_attested": False,
        "no_authority": copy.deepcopy(contract["no_authority"]),
        "authority_counters": copy.deepcopy(contract["authority_counters"]),
        "dataset_hash": lineage["dataset_hash"],
        "row_ids_hash": lineage["row_ids_hash"],
        "split_hash": lineage["split_hash"],
        "feature_schema_hash": lineage["feature_schema_hash"],
        "label_schema_hash": lineage["label_schema_hash"],
        "training_rows": lineage["row_count"],
    }
    return {
        **payload_without_hash,
        "durable_receipt_hash": _canonical_hash(payload_without_hash),
    }


def _receipt_row(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "durable_receipt_hash": payload["durable_receipt_hash"],
        "source_receipt_hash": payload["source_receipt_hash"],
        "source_contract_hash": payload["source_contract_hash"],
        "projection_artifact_hash": payload["projection_artifact_hash"],
        "selection_binding_hash": payload["selection_binding_hash"],
        "proof_input_hash": payload["proof_input_hash"],
        "proof_packet_hash": payload["proof_packet_hash"],
        "reward_set_hash": payload["reward_set_hash"],
        "pit_dataset_manifest_hash": payload["pit_dataset_manifest_hash"],
        "after_cost_label_set_hash": payload["after_cost_label_set_hash"],
        "evidence_set_hash": payload["evidence_set_hash"],
        "training_input_hash": payload["training_input_hash"],
        "training_key_hash": payload["training_key_hash"],
        "code_manifest_hash": payload["code_manifest_hash"],
        "training_config_hash": payload["training_config_hash"],
        "receipt_status": payload["receipt_status"],
        "canonical_payload": copy.deepcopy(payload),
        "no_authority": copy.deepcopy(payload["no_authority"]),
        "authority_counters": copy.deepcopy(payload["authority_counters"]),
        "created_at": "2026-07-11T22:15:00+00:00",
    }


class _Connection:
    def __init__(
        self,
        response: dict[str, Any],
        *,
        row_kind: str = "mapping",
        execute_error: Exception | None = None,
        fetch_error: Exception | None = None,
        commit_error: Exception | None = None,
        autocommit: Any = False,
        transaction_status: Any = 0,
    ) -> None:
        self.response = copy.deepcopy(response)
        self.row_kind = row_kind
        self.execute_error = execute_error
        self.fetch_error = fetch_error
        self.commit_error = commit_error
        self.autocommit = autocommit
        self.transaction_status = transaction_status
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.events: list[str] = []
        self.cursor_count = 0
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> "_Cursor":
        self.events.append("cursor")
        self.cursor_count += 1
        return _Cursor(self)

    def get_transaction_status(self) -> Any:
        self.events.append("transaction_status")
        return self.transaction_status

    def commit(self) -> None:
        self.events.append("commit")
        self.commits += 1
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self) -> None:
        self.events.append("rollback")
        self.rollbacks += 1


class _Cursor:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(
        self,
        sql: str,
        params: tuple[Any, ...] | None = None,
    ) -> None:
        self.connection.events.append("execute")
        self.connection.calls.append((sql, params))
        if self.connection.execute_error is not None:
            raise self.connection.execute_error

    def fetchone(self) -> Any:
        self.connection.events.append("fetchone")
        if self.connection.fetch_error is not None:
            raise self.connection.fetch_error
        response = copy.deepcopy(self.connection.response)
        if self.connection.row_kind == "mapping":
            return {"repository_result": response}
        if self.connection.row_kind == "tuple":
            return (response,)
        raise AssertionError(f"unexpected_row_kind:{self.connection.row_kind}")


class _MutatingContractMapping(Mapping[str, Any]):
    def __init__(
        self,
        contract: dict[str, Any],
        *,
        mutate_on_iteration: int = 5,
    ) -> None:
        self._contract = copy.deepcopy(contract)
        self.mutate_on_iteration = mutate_on_iteration
        self.iteration_count = 0

    def __getitem__(self, key: str) -> Any:
        return self._contract[key]

    def __iter__(self) -> Iterator[str]:
        self.iteration_count += 1
        if self.iteration_count == self.mutate_on_iteration:
            self._contract["training_key_hash"] = "f" * 64
        return iter(self._contract)

    def __len__(self) -> int:
        return len(self._contract)


def test_persist_qualified_training_receipt_uses_valid_contract_and_returns_exact_repository_row() -> None:
    contract = _training_contract()
    original_contract = copy.deepcopy(contract)
    payload = _expected_payload(contract)
    receipt = _receipt_row(payload)
    connection = _Connection({"status": "PERSISTED", "receipt": receipt})

    result = persist_qualified_training_receipt(
        connection,
        training_contract=contract,
    )

    assert result == {"status": "PERSISTED", "receipt": receipt}
    assert result["receipt"]["canonical_payload"] == payload
    assert len(payload) == 30
    assert payload["reward_set_hash"] == (
        "73580dd7c29558f97192815111add42323b5660ace93c78a2b7821c1a94ce90f"
    )
    assert payload["durable_receipt_hash"] == (
        "b5846686e523e3816094631fdc1881491caaae776aed2783218fd4b563a72739"
    )
    assert connection.cursor_count == 1
    assert connection.events == [
        "transaction_status",
        "cursor",
        "execute",
        "fetchone",
        "commit",
    ]
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert len(connection.calls) == 1
    sql, params = connection.calls[0]
    assert sql == (
        "SELECT learning.persist_alr_qualified_training_receipt_v1("
        "%s::text, %s::text, %s::text, %s::text, %s::text, "
        "%s::text, %s::text, %s::text, %s::text, %s::text, "
        "%s::text, %s::text, %s::text, %s::text, %s::text, %s::jsonb"
        ") AS repository_result "
        "/* alr-challenger-repository:qualified-receipt */"
    )
    assert sql.count("%s") == 16
    assert "learning.persist_alr_qualified_training_receipt_v1" in sql
    assert params is not None
    assert params[:15] == (
        payload["durable_receipt_hash"],
        payload["source_receipt_hash"],
        payload["source_contract_hash"],
        payload["projection_artifact_hash"],
        payload["selection_binding_hash"],
        payload["proof_input_hash"],
        payload["proof_packet_hash"],
        payload["reward_set_hash"],
        payload["pit_dataset_manifest_hash"],
        payload["after_cost_label_set_hash"],
        payload["evidence_set_hash"],
        payload["training_input_hash"],
        payload["training_key_hash"],
        payload["code_manifest_hash"],
        payload["training_config_hash"],
    )
    assert params[15] == _canonical_json(payload)
    upper_sql = sql.upper()
    assert "INSERT " not in upper_sql
    assert "UPDATE " not in upper_sql
    assert "DELETE " not in upper_sql
    assert "ALR_QUALIFIED_TRAINING_RECEIPTS" not in upper_sql
    assert "MODEL_REGISTRY" not in upper_sql
    assert "RUN_TRAINING_PIPELINE" not in upper_sql
    assert "PERSIST_ALR_CHALLENGER_TRAINING_RESULT_V1" not in upper_sql
    assert "READ_ALR_QUALIFIED_TRAINING_RECEIPT_V1" not in upper_sql
    assert contract == original_contract


def test_read_qualified_training_receipt_found_uses_contract_derived_identity_and_returns_exact_row() -> None:
    contract = _training_contract()
    original_contract = copy.deepcopy(contract)
    payload = _expected_payload(contract)
    receipt = _receipt_row(payload)
    connection = _Connection({"status": "FOUND", "receipt": receipt})

    result = read_qualified_training_receipt(
        connection,
        training_contract=contract,
    )

    assert result == {"status": "FOUND", "receipt": receipt}
    assert connection.events == [
        "transaction_status",
        "cursor",
        "execute",
        "fetchone",
        "commit",
    ]
    assert connection.cursor_count == 1
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert len(connection.calls) == 1
    sql, params = connection.calls[0]
    assert sql == (
        "SELECT learning.read_alr_qualified_training_receipt_v1("
        "%s::text, %s::text) AS repository_result "
        "/* alr-challenger-repository:qualified-receipt-reader */"
    )
    assert sql.count("%s") == 2
    assert params == (
        payload["durable_receipt_hash"],
        payload["training_key_hash"],
    )
    upper_sql = sql.upper()
    assert "INSERT " not in upper_sql
    assert "UPDATE " not in upper_sql
    assert "DELETE " not in upper_sql
    assert "ALR_QUALIFIED_TRAINING_RECEIPTS" not in upper_sql
    assert "PERSIST_ALR_QUALIFIED_TRAINING_RECEIPT_V1" not in upper_sql
    assert "PERSIST_ALR_CHALLENGER_TRAINING_RESULT_V1" not in upper_sql
    assert "READ_ALR_CHALLENGER_TRAINING_RESULT_V1" not in upper_sql
    assert contract == original_contract


def test_read_qualified_training_receipt_not_found_returns_exact_null_receipt() -> None:
    contract = _training_contract()
    payload = _expected_payload(contract)
    connection = _Connection({"status": "NOT_FOUND", "receipt": None})

    result = read_qualified_training_receipt(
        connection,
        training_contract=contract,
    )

    assert result == {"status": "NOT_FOUND", "receipt": None}
    assert connection.events == [
        "transaction_status",
        "cursor",
        "execute",
        "fetchone",
        "commit",
    ]
    assert connection.calls[0][0] == (
        "SELECT learning.read_alr_qualified_training_receipt_v1("
        "%s::text, %s::text) AS repository_result "
        "/* alr-challenger-repository:qualified-receipt-reader */"
    )
    assert connection.calls[0][1] == (
        payload["durable_receipt_hash"],
        payload["training_key_hash"],
    )
    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_read_qualified_training_receipt_public_api_has_no_raw_hash_lookup() -> None:
    parameters = inspect.signature(
        read_qualified_training_receipt
    ).parameters

    assert tuple(parameters) == ("connection", "training_contract")
    assert parameters["training_contract"].kind is inspect.Parameter.KEYWORD_ONLY


def test_read_found_tuple_jsonb_row_has_mapping_parity() -> None:
    contract = _training_contract()
    payload = _expected_payload(contract)
    response = {"status": "FOUND", "receipt": _receipt_row(payload)}
    mapping_connection = _Connection(response)
    tuple_connection = _Connection(response, row_kind="tuple")

    mapping_result = read_qualified_training_receipt(
        mapping_connection,
        training_contract=contract,
    )
    tuple_result = read_qualified_training_receipt(
        tuple_connection,
        training_contract=contract,
    )

    assert tuple_result == mapping_result
    assert mapping_connection.commits == tuple_connection.commits == 1
    assert mapping_connection.rollbacks == tuple_connection.rollbacks == 0


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (
            {"status": "FOUND"},
            "receipt_response_fields_invalid",
        ),
        (
            {"status": "NOT_FOUND", "receipt": {}},
            "receipt_not_found_payload_invalid",
        ),
        (
            {"status": "NOT_FOUND", "receipt": None, "unexpected": False},
            "receipt_response_fields_invalid",
        ),
        (
            {"status": "UNKNOWN", "receipt": None},
            "receipt_response_status_invalid",
        ),
        (
            {"status": "PERSISTED", "receipt": None},
            "receipt_response_status_invalid",
        ),
        (
            {"status": "DUPLICATE", "receipt": None},
            "receipt_response_status_invalid",
        ),
        (
            {"status": ["FOUND"], "receipt": None},
            "receipt_response_status_invalid",
        ),
        (
            {"status": "FOUND", "receipt": None},
            "receipt_row_fields_invalid",
        ),
    ],
)
def test_read_malformed_fixed_function_response_is_rolled_back(
    response: dict[str, Any],
    reason: str,
) -> None:
    connection = _Connection(response)

    with pytest.raises(AlrChallengerRepositoryError, match=reason):
        read_qualified_training_receipt(
            connection,
            training_contract=_training_contract(),
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_read_found_divergent_receipt_rolls_back_before_commit() -> None:
    contract = _training_contract()
    payload = _expected_payload(contract)
    receipt = _receipt_row(payload)
    receipt["canonical_payload"]["training_key_hash"] = "f" * 64
    connection = _Connection({"status": "FOUND", "receipt": receipt})

    with pytest.raises(
        AlrChallengerRepositoryError,
        match="receipt_row_content_mismatch",
    ):
        read_qualified_training_receipt(
            connection,
            training_contract=contract,
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("missing_field", "receipt_row_fields_invalid"),
        ("extra_field", "receipt_row_fields_invalid"),
        ("outer_key_mismatch", "receipt_row_content_mismatch"),
        ("naive_created_at", "receipt_created_at_invalid"),
        ("boolean_integer_alias", "receipt_row_content_mismatch"),
    ],
)
def test_read_found_enforces_complete_typed_twenty_field_row(
    mutation: str,
    reason: str,
) -> None:
    contract = _training_contract()
    payload = _expected_payload(contract)
    receipt = _receipt_row(payload)
    if mutation == "missing_field":
        del receipt["source_receipt_hash"]
    elif mutation == "extra_field":
        receipt["unexpected"] = "forbidden"
    elif mutation == "outer_key_mismatch":
        receipt["training_key_hash"] = "f" * 64
    elif mutation == "naive_created_at":
        receipt["created_at"] = "2026-07-11T22:15:00"
    elif mutation == "boolean_integer_alias":
        receipt["authority_counters"]["exchange_contact_count"] = False
    else:  # pragma: no cover - parameter table is exhaustive
        raise AssertionError(f"unknown_mutation:{mutation}")
    connection = _Connection({"status": "FOUND", "receipt": receipt})

    with pytest.raises(AlrChallengerRepositoryError, match=reason):
        read_qualified_training_receipt(
            connection,
            training_contract=contract,
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_read_tampered_contract_is_rejected_before_connection_use() -> None:
    contract = _training_contract()
    contract["training_key_hash"] = "f" * 64
    connection = _Connection({})

    with pytest.raises(
        AlrChallengerRepositoryError,
        match="training_contract_invalid:training_key_hash_mismatch",
    ):
        read_qualified_training_receipt(
            connection,
            training_contract=contract,
        )

    assert connection.events == []
    assert connection.calls == []
    assert connection.commits == 0
    assert connection.rollbacks == 0


def test_read_contract_is_snapshotted_once_before_connection_use() -> None:
    stable_contract = _training_contract()
    mutating_contract = _MutatingContractMapping(stable_contract)
    payload = _expected_payload(stable_contract)
    connection = _Connection(
        {"status": "FOUND", "receipt": _receipt_row(payload)}
    )

    result = read_qualified_training_receipt(
        connection,
        training_contract=mutating_contract,
    )

    assert result == {"status": "FOUND", "receipt": _receipt_row(payload)}
    assert mutating_contract.iteration_count == 1
    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_read_mutated_contract_snapshot_is_rejected_before_connection_use() -> None:
    mutating_contract = _MutatingContractMapping(
        _training_contract(),
        mutate_on_iteration=1,
    )
    connection = _Connection({})

    with pytest.raises(
        AlrChallengerRepositoryError,
        match="training_contract_invalid:training_key_hash_mismatch",
    ):
        read_qualified_training_receipt(
            connection,
            training_contract=mutating_contract,
        )

    assert mutating_contract.iteration_count == 1
    assert connection.events == []
    assert connection.calls == []
    assert connection.commits == 0
    assert connection.rollbacks == 0


def test_read_training_rows_above_postgres_integer_range_is_preflight_error() -> None:
    contract = _training_contract()
    contract["input_lineage"]["row_count"] = 2_147_483_648
    _rehash_contract(contract)
    connection = _Connection({})

    with pytest.raises(
        AlrChallengerRepositoryError,
        match="training_rows_out_of_range",
    ):
        read_qualified_training_receipt(
            connection,
            training_contract=contract,
        )

    assert connection.events == []
    assert connection.calls == []
    assert connection.commits == 0
    assert connection.rollbacks == 0


@pytest.mark.parametrize(
    ("autocommit", "transaction_status", "events", "reason"),
    [
        (True, 0, [], "transactional_connection_required"),
        (0, 0, [], "transactional_connection_required"),
        (None, 0, [], "transactional_connection_required"),
        (False, 1, ["transaction_status"], "clean_idle_connection_required"),
        (False, False, ["transaction_status"], "clean_idle_connection_required"),
    ],
)
def test_read_rejects_non_clean_connection_without_touching_pending_work(
    autocommit: Any,
    transaction_status: Any,
    events: list[str],
    reason: str,
) -> None:
    connection = _Connection(
        {},
        autocommit=autocommit,
        transaction_status=transaction_status,
    )

    with pytest.raises(AlrChallengerRepositoryError, match=reason):
        read_qualified_training_receipt(
            connection,
            training_contract=_training_contract(),
        )

    assert connection.events == events
    assert connection.cursor_count == 0
    assert connection.calls == []
    assert connection.commits == 0
    assert connection.rollbacks == 0


@pytest.mark.parametrize("failure_point", ["execute", "fetch"])
def test_read_database_failure_propagates_with_one_rollback(
    failure_point: str,
) -> None:
    error = RuntimeError(f"database_{failure_point}_failed")
    connection = _Connection(
        {},
        execute_error=error if failure_point == "execute" else None,
        fetch_error=error if failure_point == "fetch" else None,
    )

    with pytest.raises(RuntimeError, match=f"database_{failure_point}_failed"):
        read_qualified_training_receipt(
            connection,
            training_contract=_training_contract(),
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_read_commit_failure_is_rolled_back_and_propagated() -> None:
    contract = _training_contract()
    payload = _expected_payload(contract)
    connection = _Connection(
        {"status": "FOUND", "receipt": _receipt_row(payload)},
        commit_error=RuntimeError("database_commit_failed"),
    )

    with pytest.raises(RuntimeError, match="database_commit_failed"):
        read_qualified_training_receipt(
            connection,
            training_contract=contract,
        )

    assert connection.commits == 1
    assert connection.rollbacks == 1


def test_tampered_training_contract_is_rejected_before_opening_cursor() -> None:
    contract = _training_contract()
    contract["training_input_hash"] = "f" * 64
    connection = _Connection({})

    with pytest.raises(
        AlrChallengerRepositoryError,
        match="training_contract_invalid:training_input_hash_mismatch",
    ):
        persist_qualified_training_receipt(
            connection,
            training_contract=contract,
        )

    assert connection.cursor_count == 0
    assert connection.calls == []
    assert connection.commits == 0
    assert connection.rollbacks == 0
    assert connection.events == []


def test_exact_duplicate_is_accepted_with_original_created_at() -> None:
    contract = _training_contract()
    payload = _expected_payload(contract)
    receipt = _receipt_row(payload)
    receipt["created_at"] = "2026-07-11T21:59:59.123456+00:00"
    connection = _Connection({"status": "DUPLICATE", "receipt": receipt})

    result = persist_qualified_training_receipt(
        connection,
        training_contract=contract,
    )

    assert result["status"] == "DUPLICATE"
    assert result["receipt"] == receipt
    assert result["receipt"]["created_at"] == receipt["created_at"]
    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_divergent_replay_response_rolls_back_before_commit() -> None:
    contract = _training_contract()
    payload = _expected_payload(contract)
    receipt = _receipt_row(payload)
    receipt["canonical_payload"]["training_key_hash"] = "f" * 64
    connection = _Connection({"status": "DUPLICATE", "receipt": receipt})

    with pytest.raises(
        AlrChallengerRepositoryError,
        match="receipt_row_content_mismatch",
    ):
        persist_qualified_training_receipt(
            connection,
            training_contract=contract,
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_non_string_response_status_is_fail_closed_and_rolled_back() -> None:
    contract = _training_contract()
    payload = _expected_payload(contract)
    connection = _Connection(
        {"status": ["PERSISTED"], "receipt": _receipt_row(payload)}
    )

    with pytest.raises(
        AlrChallengerRepositoryError,
        match="receipt_response_status_invalid",
    ):
        persist_qualified_training_receipt(
            connection,
            training_contract=contract,
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        ({"status": "PERSISTED"}, "receipt_response_fields_invalid"),
        (
            {"status": "UNKNOWN", "receipt": {}},
            "receipt_response_status_invalid",
        ),
        (
            {"status": "PERSISTED", "receipt": None},
            "receipt_row_fields_invalid",
        ),
    ],
)
def test_malformed_fixed_function_response_is_rolled_back(
    response: dict[str, Any],
    reason: str,
) -> None:
    connection = _Connection(response)

    with pytest.raises(AlrChallengerRepositoryError, match=reason):
        persist_qualified_training_receipt(
            connection,
            training_contract=_training_contract(),
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


@pytest.mark.parametrize("failure_point", ["execute", "fetch"])
def test_database_failure_propagates_with_one_rollback(failure_point: str) -> None:
    error = RuntimeError(f"database_{failure_point}_failed")
    connection = _Connection(
        {},
        execute_error=error if failure_point == "execute" else None,
        fetch_error=error if failure_point == "fetch" else None,
    )

    with pytest.raises(RuntimeError, match=f"database_{failure_point}_failed"):
        persist_qualified_training_receipt(
            connection,
            training_contract=_training_contract(),
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_commit_failure_is_rolled_back_and_propagated() -> None:
    contract = _training_contract()
    payload = _expected_payload(contract)
    connection = _Connection(
        {"status": "PERSISTED", "receipt": _receipt_row(payload)},
        commit_error=RuntimeError("database_commit_failed"),
    )

    with pytest.raises(RuntimeError, match="database_commit_failed"):
        persist_qualified_training_receipt(
            connection,
            training_contract=contract,
        )

    assert connection.commits == 1
    assert connection.rollbacks == 1


def test_tuple_jsonb_row_has_mapping_row_parity() -> None:
    contract = _training_contract()
    payload = _expected_payload(contract)
    response = {"status": "PERSISTED", "receipt": _receipt_row(payload)}
    mapping_connection = _Connection(response)
    tuple_connection = _Connection(response, row_kind="tuple")

    mapping_result = persist_qualified_training_receipt(
        mapping_connection,
        training_contract=contract,
    )
    tuple_result = persist_qualified_training_receipt(
        tuple_connection,
        training_contract=contract,
    )

    assert tuple_result == mapping_result
    assert mapping_connection.commits == tuple_connection.commits == 1
    assert mapping_connection.rollbacks == tuple_connection.rollbacks == 0


def test_training_rows_above_postgres_integer_range_is_rejected_before_cursor() -> None:
    contract = _training_contract()
    contract["input_lineage"]["row_count"] = 2_147_483_648
    _rehash_contract(contract)
    connection = _Connection({})

    with pytest.raises(
        AlrChallengerRepositoryError,
        match="training_rows_out_of_range",
    ):
        persist_qualified_training_receipt(
            connection,
            training_contract=contract,
        )

    assert connection.cursor_count == 0
    assert connection.calls == []
    assert connection.commits == 0
    assert connection.rollbacks == 0
    assert connection.events == []


@pytest.mark.parametrize(
    "created_at",
    ["not-a-timestamp", "2026-07-11T22:15:00"],
)
def test_created_at_must_be_an_offset_aware_iso_timestamp(
    created_at: str,
) -> None:
    contract = _training_contract()
    payload = _expected_payload(contract)
    receipt = _receipt_row(payload)
    receipt["created_at"] = created_at
    connection = _Connection({"status": "PERSISTED", "receipt": receipt})

    with pytest.raises(
        AlrChallengerRepositoryError,
        match="receipt_created_at_invalid",
    ):
        persist_qualified_training_receipt(
            connection,
            training_contract=contract,
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


@pytest.mark.parametrize(
    ("container", "key", "alias"),
    [
        ("canonical_payload", "training_allowed", 0),
        ("no_authority", "exchange_authority", 0),
        ("authority_counters", "exchange_contact_count", False),
    ],
)
def test_boolean_integer_aliases_in_returned_row_are_rejected(
    container: str,
    key: str,
    alias: Any,
) -> None:
    contract = _training_contract()
    payload = _expected_payload(contract)
    receipt = _receipt_row(payload)
    receipt[container][key] = alias
    connection = _Connection({"status": "PERSISTED", "receipt": receipt})

    with pytest.raises(
        AlrChallengerRepositoryError,
        match="receipt_row_content_mismatch",
    ):
        persist_qualified_training_receipt(
            connection,
            training_contract=contract,
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_unknown_returned_row_field_is_rejected() -> None:
    contract = _training_contract()
    payload = _expected_payload(contract)
    receipt = _receipt_row(payload)
    receipt["unexpected"] = "forbidden"
    connection = _Connection({"status": "PERSISTED", "receipt": receipt})

    with pytest.raises(
        AlrChallengerRepositoryError,
        match="receipt_row_fields_invalid",
    ):
        persist_qualified_training_receipt(
            connection,
            training_contract=contract,
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_contract_is_snapshotted_before_delayed_mapping_mutation() -> None:
    stable_contract = _training_contract()
    mutating_contract = _MutatingContractMapping(stable_contract)
    payload = _expected_payload(stable_contract)
    connection = _Connection(
        {"status": "PERSISTED", "receipt": _receipt_row(payload)}
    )

    result = persist_qualified_training_receipt(
        connection,
        training_contract=mutating_contract,
    )

    assert result == {"status": "PERSISTED", "receipt": _receipt_row(payload)}
    assert mutating_contract.iteration_count == 1
    assert connection.cursor_count == 1
    assert len(connection.calls) == 1
    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_mutated_contract_snapshot_is_rejected_before_cursor() -> None:
    mutating_contract = _MutatingContractMapping(
        _training_contract(),
        mutate_on_iteration=1,
    )
    connection = _Connection({})

    with pytest.raises(
        AlrChallengerRepositoryError,
        match="training_contract_invalid:training_key_hash_mismatch",
    ):
        persist_qualified_training_receipt(
            connection,
            training_contract=mutating_contract,
        )

    assert mutating_contract.iteration_count == 1
    assert connection.cursor_count == 0
    assert connection.calls == []
    assert connection.commits == 0
    assert connection.rollbacks == 0
    assert connection.events == []


@pytest.mark.parametrize("autocommit", [True, 0, None])
def test_non_transactional_connection_is_rejected_before_cursor(
    autocommit: Any,
) -> None:
    connection = _Connection({}, autocommit=autocommit)

    with pytest.raises(
        AlrChallengerRepositoryError,
        match="transactional_connection_required",
    ):
        persist_qualified_training_receipt(
            connection,
            training_contract=_training_contract(),
        )

    assert connection.cursor_count == 0
    assert connection.calls == []
    assert connection.commits == 0
    assert connection.rollbacks == 0
    assert connection.events == []


def test_connection_without_autocommit_posture_is_rejected_before_cursor() -> None:
    connection = _Connection({})
    del connection.autocommit

    with pytest.raises(
        AlrChallengerRepositoryError,
        match="transactional_connection_required",
    ):
        persist_qualified_training_receipt(
            connection,
            training_contract=_training_contract(),
        )

    assert connection.cursor_count == 0
    assert connection.calls == []
    assert connection.commits == 0
    assert connection.rollbacks == 0
    assert connection.events == []


@pytest.mark.parametrize("transaction_status", [1, 2, 3, 4, False, None])
def test_non_idle_connection_is_rejected_without_touching_pending_transaction(
    transaction_status: Any,
) -> None:
    connection = _Connection({}, transaction_status=transaction_status)

    with pytest.raises(
        AlrChallengerRepositoryError,
        match="clean_idle_connection_required",
    ):
        persist_qualified_training_receipt(
            connection,
            training_contract=_training_contract(),
        )

    assert connection.cursor_count == 0
    assert connection.calls == []
    assert connection.commits == 0
    assert connection.rollbacks == 0
    assert connection.events == ["transaction_status"]
