from __future__ import annotations

import copy

from ml_training.proof_packet_contract import (
    INVALID,
    NO_MATCHED_FILLS,
    PENDING_SCHEMA,
    PROOF_PACKET_FIELD,
    PROOF_PACKET_SCHEMA_VERSION,
    PROOF_READY,
    compute_proof_packet_hash,
    extract_proof_packet,
    validate_proof_packet,
)


def _valid_packet(**overrides) -> dict:
    packet = {
        "schema_version": PROOF_PACKET_SCHEMA_VERSION,
        "verdict": PROOF_READY,
        "candidate_identity": {
            "candidate_id": "grid_trading|ETHUSDT|Buy",
            "strategy_name": "grid_trading",
            "symbol": "ETHUSDT",
            "side": "Buy",
            "context_id": "ctx-entry-1",
        },
        "execution_identity": {
            "candidate_matched": True,
            "order_link_id": "oc_dm_1782040200000_1_0deadbeef",
            "fill_ids": ["fill-entry-1", "fill-exit-1"],
            "entry_context_id": "ctx-entry-1",
            "exit_context_id": "ctx-exit-1",
            "liquidity_role": "mixed",
            "fill_records": [
                {
                    "fill_id": "fill-entry-1",
                    "outcome_source": "candidate_matched_demo_fill",
                }
            ],
        },
        "cost_identity": {
            "maker_fee_bps": 2.0,
            "taker_fee_bps": 5.5,
            "slippage_bps": 0.4,
            "spread_bps": 1.1,
            "funding_bps": -0.2,
            "markout_bps": 3.8,
            "realized_net_pnl_bps": 4.2,
            "realized_net_pnl_usdt": 0.42,
        },
        "controls": {
            "matched_control_ids": ["control-1", "control-2"],
            "regime_labels": {"trend": "sideways", "volatility": "medium"},
            "oos_split": {"split_hash": "b" * 64, "hidden_oos": True},
            "proof_exclusions": [],
        },
        "provenance": {
            "code_commit": "a" * 40,
            "rust_build_sha": "c" * 40,
            "source_hashes": {
                "probe_ledger": "d" * 64,
                "candidate_manifest": "sha256:candidate-manifest",
            },
            "input_artifact_hashes": {
                "standing_envelope": "e" * 64,
                "bounded_auth": "sha256:bounded-auth",
            },
        },
    }
    _deep_update(packet, overrides)
    packet["proof_packet_hash"] = compute_proof_packet_hash(packet)
    return packet


def _no_fill_packet(**overrides) -> dict:
    packet = {
        "schema_version": PROOF_PACKET_SCHEMA_VERSION,
        "verdict": NO_MATCHED_FILLS,
        "candidate_identity": {
            "candidate_id": "grid_trading|ETHUSDT|Buy",
            "strategy_name": "grid_trading",
            "symbol": "ETHUSDT",
            "side": "Buy",
            "context_id": "ctx-entry-1",
        },
        "no_fill_diagnosis": {
            "blocker_code": "NO_MATCHED_FILLS_AFTER_AUTHORIZED_WINDOW",
            "observed_window_start": "2026-07-06T10:00:00Z",
            "observed_window_end": "2026-07-06T10:05:00Z",
            "attempted_order_count": 2,
        },
        "provenance": {
            "code_commit": "a" * 40,
            "rust_build_sha": "c" * 40,
            "source_hashes": {"probe_ledger": "d" * 64},
            "input_artifact_hashes": {"window_packet": "e" * 64},
        },
    }
    _deep_update(packet, overrides)
    packet["proof_packet_hash"] = compute_proof_packet_hash(packet)
    return packet


def _deep_update(target: dict, updates: dict) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def test_valid_proof_packet_is_proof_ready() -> None:
    validation = validate_proof_packet(_valid_packet())

    assert validation.proof_ready is True
    assert validation.verdict == PROOF_READY
    assert validation.reason == "ok"
    assert validation.no_fill_blocker is False


def test_extract_reads_only_canonical_field() -> None:
    packet = _valid_packet()

    assert extract_proof_packet({PROOF_PACKET_FIELD: packet}) == packet
    assert extract_proof_packet({"proof": packet}) is None


def test_proof_packet_hash_is_key_order_stable() -> None:
    packet_a = _valid_packet()
    packet_b = {
        "provenance": dict(reversed(list(packet_a["provenance"].items()))),
        "controls": dict(reversed(list(packet_a["controls"].items()))),
        "cost_identity": dict(reversed(list(packet_a["cost_identity"].items()))),
        "execution_identity": dict(reversed(list(packet_a["execution_identity"].items()))),
        "candidate_identity": dict(reversed(list(packet_a["candidate_identity"].items()))),
        "verdict": packet_a["verdict"],
        "schema_version": packet_a["schema_version"],
    }

    assert compute_proof_packet_hash(packet_a) == compute_proof_packet_hash(packet_b)


def test_hash_mismatch_is_invalid() -> None:
    packet = _valid_packet()
    packet["proof_packet_hash"] = "0" * 64

    validation = validate_proof_packet(packet)

    assert validation.proof_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "proof_packet_hash_mismatch"


def test_missing_candidate_identity_is_pending_schema() -> None:
    packet = _valid_packet()
    packet.pop("candidate_identity")

    validation = validate_proof_packet(packet)

    assert validation.proof_ready is False
    assert validation.verdict == PENDING_SCHEMA
    assert validation.reason == "candidate_identity_missing"


def test_proof_ready_requires_candidate_matched_fills() -> None:
    packet = _valid_packet(execution_identity={"candidate_matched": False, "fill_ids": []})

    validation = validate_proof_packet(packet)

    assert validation.proof_ready is False
    assert validation.verdict == PENDING_SCHEMA
    assert "execution_identity_candidate_matched_not_true" in validation.reasons
    assert "execution_identity_fill_ids_missing" in validation.reasons


def test_entry_context_must_match_candidate_context() -> None:
    packet = _valid_packet(execution_identity={"entry_context_id": "other-context"})

    validation = validate_proof_packet(packet)

    assert validation.proof_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "execution_identity_entry_context_id_mismatch"


def test_proof_excluded_or_unattributed_fills_cannot_pass() -> None:
    packet = _valid_packet(
        execution_identity={
            "fill_records": [
                {
                    "fill_id": "fill-entry-1",
                    "outcome_source": "unattributed_cleanup_fill",
                }
            ]
        }
    )

    validation = validate_proof_packet(packet)

    assert validation.proof_ready is False
    assert validation.verdict == INVALID
    assert validation.reason.startswith("proof_exclusion_present:")


def test_controls_proof_exclusions_cannot_pass() -> None:
    packet = _valid_packet(controls={"proof_exclusions": ["cleanup_fill"]})

    validation = validate_proof_packet(packet)

    assert validation.proof_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "controls_proof_exclusions_present"


def test_authority_expansion_fails_closed() -> None:
    packet = _valid_packet()
    packet["answers"] = {"order_authority_granted": True}
    packet["proof_packet_hash"] = compute_proof_packet_hash(packet)

    validation = validate_proof_packet(packet)

    assert validation.proof_ready is False
    assert validation.verdict == INVALID
    assert validation.authority_boundary_violation is True
    assert validation.reason == "authority_boundary_violation:answers.order_authority_granted"


def test_promotion_ready_field_is_not_allowed() -> None:
    packet = _valid_packet(promotion_ready=True)

    validation = validate_proof_packet(packet)

    assert validation.proof_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "promotion_ready_field_not_allowed"


def test_no_fill_packet_is_valid_blocker_not_learning_label() -> None:
    validation = validate_proof_packet(_no_fill_packet())

    assert validation.proof_ready is False
    assert validation.verdict == NO_MATCHED_FILLS
    assert validation.reason == "ok_no_matched_fills"
    assert validation.no_fill_blocker is True


def test_no_fill_packet_rejects_fill_ids_and_cost_labels() -> None:
    packet = _no_fill_packet(
        execution_identity={"fill_ids": ["fill-1"]},
        cost_identity={"realized_net_pnl_bps": 4.2},
        reward=1.0,
    )

    validation = validate_proof_packet(packet)

    assert validation.proof_ready is False
    assert validation.verdict == INVALID
    assert "no_fill_packet_has_fill_ids" in validation.reasons
    assert "no_fill_packet_has_cost_identity" in validation.reasons
    assert "no_fill_packet_has_label:reward" in validation.reasons


def test_non_proof_verdict_never_passes() -> None:
    packet = _valid_packet(verdict="research_only")

    validation = validate_proof_packet(packet)

    assert validation.proof_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "verdict_not_proof_ready:research_only"


def test_negative_fee_is_invalid() -> None:
    packet = _valid_packet(cost_identity={"maker_fee_bps": -0.1})

    validation = validate_proof_packet(packet)

    assert validation.proof_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "cost_identity_maker_fee_bps_negative"
