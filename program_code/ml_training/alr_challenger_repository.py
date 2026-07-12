"""Fixed-function access for qualified challenger-training receipts.

This module is deliberately narrower than a trainer.  It validates an already
constructed ``alr_challenger_training_contract_v1``, derives the exact V158
receipt payload, and calls only the fixed receipt writer or reader.  It performs
no fit, filesystem publication, direct table DML, registry write, serving
action, or external request.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from ml_training.alr_challenger_training_contract import (
    validate_alr_challenger_training_contract,
)


QUALIFIED_RECEIPT_SCHEMA_VERSION = "alr_qualified_training_receipt_v1"
QUALIFIED_REWARD_SET_SCHEMA_VERSION = "alr_qualified_reward_set_v1"
QUALIFIED_RECEIPT_STATUS = "QUALIFIED_INPUT_PERSISTED"

_POSTGRES_INTEGER_MAX = 2_147_483_647
_PSYCOPG2_TRANSACTION_STATUS_IDLE = 0
_PERSISTED_STATUSES = {"PERSISTED", "DUPLICATE"}
_RECEIPT_ARGUMENT_FIELDS = (
    "durable_receipt_hash",
    "source_receipt_hash",
    "source_contract_hash",
    "projection_artifact_hash",
    "selection_binding_hash",
    "proof_input_hash",
    "proof_packet_hash",
    "reward_set_hash",
    "pit_dataset_manifest_hash",
    "after_cost_label_set_hash",
    "evidence_set_hash",
    "training_input_hash",
    "training_key_hash",
    "code_manifest_hash",
    "training_config_hash",
)
_RECEIPT_ROW_FIELDS = {
    *_RECEIPT_ARGUMENT_FIELDS,
    "receipt_status",
    "canonical_payload",
    "no_authority",
    "authority_counters",
    "created_at",
}
_PERSIST_RECEIPT_SQL = (
    "SELECT learning.persist_alr_qualified_training_receipt_v1("
    "%s::text, %s::text, %s::text, %s::text, %s::text, "
    "%s::text, %s::text, %s::text, %s::text, %s::text, "
    "%s::text, %s::text, %s::text, %s::text, %s::text, %s::jsonb"
    ") AS repository_result "
    "/* alr-challenger-repository:qualified-receipt */"
)
_READ_RECEIPT_SQL = (
    "SELECT learning.read_alr_qualified_training_receipt_v1("
    "%s::text, %s::text) AS repository_result "
    "/* alr-challenger-repository:qualified-receipt-reader */"
)


class AlrChallengerRepositoryError(ValueError):
    """A qualified contract or fixed-function response is not exact."""


def persist_qualified_training_receipt(
    connection: Any,
    *,
    training_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist one exact V158 qualified receipt through its fixed API only.

    ``connection`` must be a dedicated, clean psycopg2 connection with
    ``autocommit is False`` and transaction status ``IDLE``.  After that
    preflight this function owns the single receipt transaction and its
    commit-or-rollback outcome.
    """

    contract = _validated_contract(training_contract)
    payload = _receipt_payload(contract)
    _require_transactional_connection(connection)
    params = tuple(payload[field] for field in _RECEIPT_ARGUMENT_FIELDS) + (
        _canonical_json(payload),
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute(_PERSIST_RECEIPT_SQL, params)
            response = _fixed_function_response(cursor.fetchone())
        status, receipt = _validate_persist_response(response, payload=payload)
        result = {"status": status, "receipt": copy.deepcopy(dict(receipt))}
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return result


def read_qualified_training_receipt(
    connection: Any,
    *,
    training_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Read one exact V158 qualified receipt through its fixed API only."""

    contract = _validated_contract(training_contract)
    payload = _receipt_payload(contract)
    _require_transactional_connection(connection)
    params = (
        payload["durable_receipt_hash"],
        payload["training_key_hash"],
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute(_READ_RECEIPT_SQL, params)
            response = _fixed_function_response(cursor.fetchone())
        result = _validated_read_result(response, payload=payload)
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return result


def validate_qualified_training_receipt_read(
    qualified_receipt_read: Mapping[str, Any],
    *,
    training_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Purely validate one fixed-reader response against its bound contract."""

    contract = _validated_contract(training_contract)
    payload = _receipt_payload(contract)
    if not isinstance(qualified_receipt_read, Mapping):
        raise AlrChallengerRepositoryError("receipt_response_not_mapping")
    try:
        response = copy.deepcopy(dict(qualified_receipt_read))
    except Exception as exc:
        raise AlrChallengerRepositoryError(
            "receipt_response_snapshot_invalid"
        ) from exc
    return _validated_read_result(response, payload=payload)


def _validated_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AlrChallengerRepositoryError("training_contract_not_mapping")
    try:
        snapshot = copy.deepcopy(dict(value))
    except Exception as exc:
        raise AlrChallengerRepositoryError("training_contract_snapshot_invalid") from exc
    validation = validate_alr_challenger_training_contract(snapshot)
    if not validation.valid:
        raise AlrChallengerRepositoryError(
            "training_contract_invalid:" + validation.reason
        )
    return snapshot


def _require_transactional_connection(connection: Any) -> None:
    try:
        autocommit = connection.autocommit
    except (AttributeError, RuntimeError) as exc:
        raise AlrChallengerRepositoryError(
            "transactional_connection_required"
        ) from exc
    if autocommit is not False:
        raise AlrChallengerRepositoryError("transactional_connection_required")
    try:
        transaction_status = connection.get_transaction_status()
    except Exception as exc:
        raise AlrChallengerRepositoryError(
            "clean_idle_connection_required"
        ) from exc
    if (
        isinstance(transaction_status, bool)
        or not isinstance(transaction_status, int)
        or transaction_status != _PSYCOPG2_TRANSACTION_STATUS_IDLE
    ):
        raise AlrChallengerRepositoryError("clean_idle_connection_required")


def _receipt_payload(contract: Mapping[str, Any]) -> dict[str, Any]:
    lineage = _mapping(contract.get("input_lineage"), "input_lineage_invalid")
    code = _mapping(contract.get("code_manifest"), "code_manifest_invalid")
    config = _mapping(contract.get("training_config"), "training_config_invalid")
    training_rows = lineage.get("row_count")
    if (
        isinstance(training_rows, bool)
        or not isinstance(training_rows, int)
        or not 1 <= training_rows <= _POSTGRES_INTEGER_MAX
    ):
        raise AlrChallengerRepositoryError("training_rows_out_of_range")
    reward_hashes = copy.deepcopy(lineage.get("reward_record_hashes"))
    reward_set_hash = _canonical_hash(
        {
            "schema_version": QUALIFIED_REWARD_SET_SCHEMA_VERSION,
            "reward_record_hashes": reward_hashes,
        }
    )
    payload_without_hash = {
        "schema_version": QUALIFIED_RECEIPT_SCHEMA_VERSION,
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
        "code_manifest_hash": code["code_manifest_hash"],
        "training_config_hash": config["training_config_hash"],
        "receipt_status": QUALIFIED_RECEIPT_STATUS,
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
        "training_rows": training_rows,
    }
    return {
        **payload_without_hash,
        "durable_receipt_hash": _canonical_hash(payload_without_hash),
    }


def _fixed_function_response(row: Any) -> Mapping[str, Any]:
    if isinstance(row, Mapping):
        if set(row) != {"repository_result"}:
            raise AlrChallengerRepositoryError("receipt_response_row_fields_invalid")
        response = row["repository_result"]
    elif (
        isinstance(row, Sequence)
        and not isinstance(row, (str, bytes, bytearray))
        and len(row) == 1
    ):
        response = row[0]
    else:
        raise AlrChallengerRepositoryError("receipt_response_row_invalid")
    if not isinstance(response, Mapping):
        raise AlrChallengerRepositoryError("receipt_response_not_mapping")
    return response


def _validate_persist_response(
    response: Mapping[str, Any],
    *,
    payload: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any]]:
    if set(response) != {"status", "receipt"}:
        raise AlrChallengerRepositoryError("receipt_response_fields_invalid")
    status = response.get("status")
    if not isinstance(status, str) or status not in _PERSISTED_STATUSES:
        raise AlrChallengerRepositoryError("receipt_response_status_invalid")
    receipt = _validate_receipt_row(response.get("receipt"), payload=payload)
    return status, receipt


def _validate_read_response(
    response: Mapping[str, Any],
    *,
    payload: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any] | None]:
    if set(response) != {"status", "receipt"}:
        raise AlrChallengerRepositoryError("receipt_response_fields_invalid")
    status = response.get("status")
    if not isinstance(status, str):
        raise AlrChallengerRepositoryError("receipt_response_status_invalid")
    if status == "NOT_FOUND":
        if response.get("receipt") is not None:
            raise AlrChallengerRepositoryError(
                "receipt_not_found_payload_invalid"
            )
        return status, None
    if status != "FOUND":
        raise AlrChallengerRepositoryError("receipt_response_status_invalid")
    receipt = _validate_receipt_row(response.get("receipt"), payload=payload)
    return status, receipt


def _validated_read_result(
    response: Mapping[str, Any],
    *,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    status, receipt = _validate_read_response(response, payload=payload)
    return {
        "status": status,
        "receipt": None if receipt is None else copy.deepcopy(dict(receipt)),
    }


def _validate_receipt_row(
    receipt: Any,
    *,
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(receipt, Mapping) or set(receipt) != _RECEIPT_ROW_FIELDS:
        raise AlrChallengerRepositoryError("receipt_row_fields_invalid")
    created_at = receipt.get("created_at")
    if not _is_offset_aware_iso_timestamp(created_at):
        raise AlrChallengerRepositoryError("receipt_created_at_invalid")

    expected = {
        **{field: payload[field] for field in _RECEIPT_ARGUMENT_FIELDS},
        "receipt_status": QUALIFIED_RECEIPT_STATUS,
        "canonical_payload": copy.deepcopy(dict(payload)),
        "no_authority": copy.deepcopy(payload["no_authority"]),
        "authority_counters": copy.deepcopy(payload["authority_counters"]),
    }
    actual = {key: value for key, value in receipt.items() if key != "created_at"}
    if _canonical_json(actual) != _canonical_json(expected):
        raise AlrChallengerRepositoryError("receipt_row_content_mismatch")
    return receipt


def _mapping(value: Any, reason: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AlrChallengerRepositoryError(reason)
    return value


def _is_offset_aware_iso_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AlrChallengerRepositoryError("canonical_payload_invalid") from exc


__all__ = [
    "AlrChallengerRepositoryError",
    "QUALIFIED_RECEIPT_SCHEMA_VERSION",
    "QUALIFIED_REWARD_SET_SCHEMA_VERSION",
    "persist_qualified_training_receipt",
    "read_qualified_training_receipt",
    "validate_qualified_training_receipt_read",
]
