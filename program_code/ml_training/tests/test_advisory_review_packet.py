from __future__ import annotations

import json

import pytest

from ml_training.advisory_review_packet import (
    ADVISORY_REVIEW_PACKET_SCHEMA_VERSION,
    build_advisory_review_packet,
    compute_advisory_review_packet_hash,
    stable_sha256_json,
    validate_advisory_review_packet,
)


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
