from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from ml_training.advisory_review_packet import (
    ADVISORY_REVIEW_PACKET_SCHEMA_VERSION,
    build_advisory_review_packet,
    compute_advisory_review_packet_hash,
    stable_sha256_json,
    validate_advisory_review_packet,
)


@dataclass(frozen=True)
class _DataclassGrant:
    database_write_allowed: bool


class _ToListGrant:
    def tolist(self):
        return {"database_write_allowed": True}


class _ItemGrant:
    def item(self):
        return {"database_write_allowed": True}


class _CountingToList:
    def __init__(self) -> None:
        self.calls = 0

    def tolist(self):
        self.calls += 1
        return {"observation": "bounded"}


class _UnknownContainer:
    pass


class _SelfToList:
    def tolist(self):
        return self


class _LookupFailure:
    @property
    def tolist(self):
        raise RuntimeError("lookup failed")


class _CallFailure:
    def tolist(self):
        raise RuntimeError("call failed")


def test_stable_sha256_json_is_key_order_invariant():
    left = {"b": [2, 1], "a": {"x": True}}
    right = {"a": {"x": True}, "b": [2, 1]}

    assert stable_sha256_json(left) == stable_sha256_json(right)


def test_build_packet_has_required_inactive_authority_flags_and_hashes():
    packet = build_advisory_review_packet(
        capability_id="ml_advisory.diagnose_leak",
        producer="unit",
        mode="diagnose_leak",
        input_payloads={"context": {"strategy": "grid_trading", "secret_like": "abc"}},
        ledger_ref="l2r:abc",
        cost_ref="l2r:abc",
        budget_ref="DOC-08",
        cost_usd=0.01,
    )

    assert packet["schema_version"] == ADVISORY_REVIEW_PACKET_SCHEMA_VERSION
    assert packet["not_authority"] is True
    assert packet["inactive_review_packet"] is True
    assert packet["active"] is False
    assert packet["requires_operator_review"] is True
    assert packet["requires_governance"] is True
    assert packet["execution_authority"] == "not_granted"
    assert packet["decision_lease_emitted"] is False
    assert packet["demo_envelope_required_for_mutation"] is True
    assert packet["current_packet_grants_demo_mutation"] is False
    assert packet["no_provider_call"] is True
    assert packet["no_exchange_contact"] is True
    assert packet["no_private_read"] is True
    assert packet["no_mcp_runtime"] is True
    assert packet["ledger_ref"] == "l2r:abc"
    assert packet["cost_ref"] == "l2r:abc"
    assert packet["budget_ref"] == "DOC-08"
    assert set(packet["input_hashes"]) == {"context"}
    assert packet["advisory_review_packet_hash"] == (
        compute_advisory_review_packet_hash(packet)
    )
    assert "secret_like" not in json.dumps(packet)
    assert validate_advisory_review_packet(packet) is True


@pytest.mark.parametrize(
    "mutation",
    [
        {"active": True},
        {"not_authority": False},
        {"inactive_review_packet": False},
        {"requires_operator_review": False},
        {"requires_governance": False},
        {"no_order_mutation": False},
        {"no_probe_mutation": False},
        {"no_live_mutation": False},
        {"no_mainnet_mutation": False},
        {"no_runtime_mutation": False},
        {"no_db_mutation": False},
        {"no_secret_mutation": False},
        {"no_promotion_mutation": False},
        {"no_cost_gate_mutation": False},
        {"no_strategy_config_mutation": False},
        {"no_provider_call": False},
        {"no_exchange_contact": False},
        {"no_private_read": False},
        {"no_mcp_runtime": False},
        {"execution_authority": "granted"},
        {"decision_lease_emitted": True},
        {"demo_envelope_required_for_mutation": False},
        {"current_packet_grants_demo_mutation": True},
        {"order_mutation_allowed": True},
        {"probe_performed": True},
        {"live_execution_allowed": True},
        {"mainnet_enabled": True},
        {"runtime_write_allowed": True},
        {"db_mutation_performed": True},
        {"secret_read_authorized": True},
        {"promotion_granted": True},
        {"cost_gate_lowered": True},
        {"strategy_config_write_allowed": True},
        {"nested": {"order_authority": "granted"}},
        {"nested": {"database_write_allowed": True}},
        {"nested": {"databaseWriteAllowed": True}},
        {"nested": {"dbWriteAllowed": True}},
        {"nested": {"costGateLowered": True}},
        {"nested": {"strategyConfigWriteAllowed": True}},
        {"nested": {"configWriteAllowed": True}},
        {"nested": {"strategyWriteAllowed": True}},
        {"nested": {"authorityGranted": True}},
        {"nested": {"authorized": True}},
        {"nested": {"permissionGranted": True}},
        {"nested": [{"canExecute": True}]},
        {"nested": [{"writeAllowed": True}]},
        {"provider_call_performed": True},
        {"exchange_private_read_performed": True},
        {"private_read_performed": True},
        {"mcp_server_started": True},
        {"nested": {"providerCallPerformed": True}},
        {"nested": {"exchangeContacted": True}},
        {"nested": {"credentialAccessPerformed": True}},
        {"nested": [{"mcpServerStarted": True}]},
    ],
)
def test_validate_rejects_active_or_truthy_authority_grants(mutation):
    packet = build_advisory_review_packet(
        capability_id="unit",
        input_payloads={"x": {"ok": True}},
    )
    packet.update(mutation)

    with pytest.raises(ValueError):
        validate_advisory_review_packet(packet)


def test_validate_rejects_advisory_packet_hash_mismatch():
    packet = build_advisory_review_packet(
        capability_id="unit",
        input_payloads={"x": {"ok": True}},
    )
    packet["advisory_review_packet_hash"] = "0" * 64

    with pytest.raises(ValueError, match="advisory_review_packet_hash mismatch"):
        validate_advisory_review_packet(packet)


def test_validate_requires_at_least_one_sha256_input_hash():
    packet = build_advisory_review_packet(
        capability_id="unit",
        input_payloads={"x": {"ok": True}},
    )
    packet["input_hashes"] = {}
    with pytest.raises(ValueError):
        validate_advisory_review_packet(packet)

    packet["input_hashes"] = {"x": "not-a-sha"}
    with pytest.raises(ValueError):
        validate_advisory_review_packet(packet)


def test_hash_rejects_oversized_mapping_key_before_authority_scan() -> None:
    packet = build_advisory_review_packet(
        capability_id="unit",
        input_payloads={"x": {"ok": True}},
    )
    packet["nested"] = {"databaseWriteAllowed" * 64: False}

    with pytest.raises(ValueError, match="mapping key exceeds maximum length"):
        compute_advisory_review_packet_hash(packet)


def test_hash_rejects_excessive_mapping_nesting_depth() -> None:
    packet = build_advisory_review_packet(
        capability_id="unit",
        input_payloads={"x": {"ok": True}},
    )
    nested: dict[str, object] = {"leaf": False}
    for _ in range(33):
        nested = {"nested": nested}
    packet["nested"] = nested

    with pytest.raises(ValueError, match="nesting depth exceeds maximum"):
        compute_advisory_review_packet_hash(packet)


def test_validate_depth_guard_runs_before_canonical_hash_serialization() -> None:
    packet = build_advisory_review_packet(
        capability_id="unit",
        input_payloads={"x": {"ok": True}},
    )
    nested: dict[str, object] = {"leaf": False}
    for _ in range(1000):
        nested = {"nested": nested}
    packet["nested"] = nested

    with pytest.raises(ValueError, match="nesting depth exceeds maximum"):
        validate_advisory_review_packet(packet)


@pytest.mark.parametrize(
    "camel_case_key",
    (
        "databaseWriteAllowed",
        "databaseHTTPWriteAllowed",
        "APIProviderCallPerformed",
    ),
)
def test_validate_rejects_bounded_camel_case_authority_keys(
    camel_case_key: str,
) -> None:
    packet = build_advisory_review_packet(
        capability_id="unit",
        input_payloads={"x": {"ok": True}},
    )
    packet["nested"] = {camel_case_key: True}
    packet["advisory_review_packet_hash"] = compute_advisory_review_packet_hash(packet)

    with pytest.raises(ValueError, match="forbidden"):
        validate_advisory_review_packet(packet)


def test_validate_rejects_truthy_authority_grant_hidden_in_tuple() -> None:
    packet = build_advisory_review_packet(
        capability_id="unit",
        input_payloads={"x": {"ok": True}},
    )
    packet["nested"] = ({"database_write_allowed": True},)
    packet["advisory_review_packet_hash"] = compute_advisory_review_packet_hash(packet)

    with pytest.raises(ValueError, match="forbidden"):
        validate_advisory_review_packet(packet)


@pytest.mark.parametrize(
    "hidden_grant",
    (
        {_DataclassGrant(True)},
        frozenset({_DataclassGrant(True)}),
        _DataclassGrant(True),
        _ToListGrant(),
        _ItemGrant(),
    ),
    ids=("set", "frozenset", "dataclass", "tolist", "item"),
)
def test_validate_rejects_truthy_authority_grant_in_supported_wrappers(
    hidden_grant,
) -> None:
    packet = build_advisory_review_packet(
        capability_id="unit",
        input_payloads={"x": {"ok": True}},
    )
    packet["nested"] = hidden_grant
    packet["advisory_review_packet_hash"] = compute_advisory_review_packet_hash(packet)

    with pytest.raises(ValueError, match="forbidden"):
        validate_advisory_review_packet(packet)


def test_supported_values_normalize_to_deterministic_plain_json() -> None:
    wrapped = {
        "path": Path("/tmp/bounded"),
        "tuple": (3, 2, 1),
        "set": {3, 1, 2},
        "frozenset": frozenset({"b", "a"}),
        "dataclass": _DataclassGrant(False),
    }
    plain = {
        "path": "/tmp/bounded",
        "tuple": [3, 2, 1],
        "set": [1, 2, 3],
        "frozenset": ["a", "b"],
        "dataclass": {"database_write_allowed": False},
    }

    assert stable_sha256_json(wrapped) == stable_sha256_json(plain)


def test_set_and_frozenset_hashes_are_iteration_order_independent() -> None:
    expected = stable_sha256_json({"values": [1, 2, 3]})

    assert stable_sha256_json({"values": {3, 1, 2}}) == expected
    assert stable_sha256_json({"values": frozenset({2, 3, 1})}) == expected


def test_validate_normalizes_once_for_authority_scan_and_hash() -> None:
    expected = build_advisory_review_packet(
        capability_id="unit",
        input_payloads={"x": {"ok": True}},
    )
    expected["nested"] = {"observation": "bounded"}
    expected["advisory_review_packet_hash"] = compute_advisory_review_packet_hash(
        expected
    )
    wrapper = _CountingToList()
    packet = dict(expected)
    packet["nested"] = wrapper

    assert validate_advisory_review_packet(packet) is True
    assert wrapper.calls == 1


def test_build_hash_normalizes_each_untrusted_input_once() -> None:
    wrapper = _CountingToList()

    build_advisory_review_packet(
        capability_id="unit",
        input_payloads={"x": wrapper},
    )

    assert wrapper.calls == 1


def test_compute_hash_normalizes_each_untrusted_packet_value_once() -> None:
    packet = build_advisory_review_packet(
        capability_id="unit",
        input_payloads={"x": {"ok": True}},
    )
    wrapper = _CountingToList()
    packet["nested"] = wrapper

    compute_advisory_review_packet_hash(packet)

    assert wrapper.calls == 1


@pytest.mark.parametrize("value", (float("nan"), float("inf"), float("-inf")))
def test_stable_hash_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        stable_sha256_json({"value": value})


def test_stable_hash_rejects_cycles() -> None:
    cyclic: list[object] = []
    cyclic.append(cyclic)

    with pytest.raises(ValueError, match="cyclic"):
        stable_sha256_json(cyclic)


def test_stable_hash_rejects_converter_returning_self_as_cycle() -> None:
    with pytest.raises(ValueError, match="cyclic"):
        stable_sha256_json(_SelfToList())


@pytest.mark.parametrize(
    ("value", "message"),
    (
        (_LookupFailure(), "conversion lookup failed"),
        (_CallFailure(), "tolist conversion failed"),
    ),
)
def test_stable_hash_fails_closed_on_converter_errors(value, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        stable_sha256_json(value)


def test_stable_hash_rejects_non_string_mapping_keys() -> None:
    with pytest.raises(ValueError, match="mapping keys must be strings"):
        stable_sha256_json({1: "not-plain-json"})


def test_stable_hash_rejects_unknown_containers() -> None:
    with pytest.raises(ValueError, match="unsupported value type"):
        stable_sha256_json(_UnknownContainer())
