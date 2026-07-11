from __future__ import annotations

import copy

from ml_training.candidate_proof_adapter import (
    INVALID,
    NO_MATCHED_FILLS,
    PENDING_EVIDENCE,
    READY_FOR_REWARD_VALIDATION,
    SELECTION_PROOF_BINDING_SCHEMA_VERSION,
    adapt_candidate_proof,
    compute_candidate_proof_adapter_hash,
    compute_selection_proof_binding_hash,
    derive_selected_candidate_proof_identity,
)
from ml_training.demo_mutation_envelope import compute_demo_mutation_envelope_hash
from ml_training.pit_dataset_manifest import compute_pit_dataset_manifest_hash
from ml_training.proof_packet_contract import compute_proof_packet_hash
from ml_training.tests.test_alr_candidate_projection_repository import (
    _projection,
    _with_handoff,
)
from ml_training.tests.test_proof_packet_contract import _no_fill_packet, _valid_packet
from ml_training.tests.test_reward_ledger import (
    _build_record,
    _valid_effect_window,
    _valid_envelope,
)


def _selected_projection() -> dict:
    return _with_handoff(_projection(selected=True))


def _binding(projection: dict, **overrides: object) -> dict:
    payload = projection["artifact"]["canonical_payload"]
    selected_identity = derive_selected_candidate_proof_identity(
        projection["decision"]["selected_candidate"]
    )
    binding = {
        "schema_version": SELECTION_PROOF_BINDING_SCHEMA_VERSION,
        "projection_hash": projection["projection_hash"],
        "artifact_hash": projection["artifact"]["artifact_hash"],
        "decision_hash": projection["decision"]["decision_hash"],
        "source_set_hash": projection["source_set"]["source_set_hash"],
        "handoff_hash": payload["source_refs"]["handoff"]["handoff_hash"],
        "candidate_id": selected_identity["candidate_id"],
        "context_id": selected_identity["context_id"],
        "selected_candidate": copy.deepcopy(projection["decision"]["selected_candidate"]),
    }
    binding.update(overrides)
    binding["binding_hash"] = compute_selection_proof_binding_hash(binding)
    return binding


def _bound_ready_packet(projection: dict, binding: dict) -> dict:
    packet = _valid_packet()
    candidate = packet["candidate_identity"]
    candidate["candidate_id"] = binding["candidate_id"]
    candidate["context_id"] = binding["context_id"]
    candidate["symbol"] = "BTCUSDT"
    packet["execution_identity"]["entry_context_id"] = binding["context_id"]
    manifest = packet["provenance"]["pit_dataset_manifest"]
    manifest["candidate_scope"]["candidate_id"] = binding["candidate_id"]
    manifest["candidate_scope"]["symbol"] = "BTCUSDT"
    manifest["manifest_hash"] = compute_pit_dataset_manifest_hash(manifest)
    packet["provenance"]["input_artifact_hashes"].update(
        {
            "candidate_projection_artifact_hash": projection["artifact"]["artifact_hash"],
            "candidate_projection_decision_hash": projection["decision"]["decision_hash"],
            "candidate_projection_handoff_hash": binding["handoff_hash"],
        }
    )
    packet["proof_packet_hash"] = compute_proof_packet_hash(packet)
    return packet


def _bound_no_fill_packet(projection: dict, binding: dict) -> dict:
    packet = _no_fill_packet()
    packet["candidate_identity"].update(
        {
            "candidate_id": binding["candidate_id"],
            "context_id": binding["context_id"],
            "symbol": "BTCUSDT",
        }
    )
    packet["provenance"]["input_artifact_hashes"].update(
        {
            "candidate_projection_artifact_hash": projection["artifact"]["artifact_hash"],
            "candidate_projection_decision_hash": projection["decision"]["decision_hash"],
            "candidate_projection_handoff_hash": binding["handoff_hash"],
        }
    )
    packet["proof_packet_hash"] = compute_proof_packet_hash(packet)
    return packet


def _bound_reward_record(proof: dict, *, window_id: str) -> dict:
    envelope = _valid_envelope(proof)
    for field in ("candidate_id", "strategy_name", "symbol", "side"):
        envelope["source"][field] = proof["candidate_identity"][field]
    envelope["envelope_sha256"] = compute_demo_mutation_envelope_hash(envelope)
    return _build_record(
        proof_packet=proof,
        demo_mutation_envelope=envelope,
        effect_window=_valid_effect_window(window_id=window_id),
    )


def test_missing_proof_is_pending_and_never_grants_authority() -> None:
    projection = _selected_projection()

    result = adapt_candidate_proof(
        projection=projection,
        selection_proof_binding=_binding(projection),
    )

    assert result["status"] == PENDING_EVIDENCE
    assert result["proof"]["present"] is False
    assert result["projection_refs"]["durable_receipt_status"] == "unverified_source_only"
    assert set(result["no_authority"].values()) == {False}
    assert set(result["authority_counters"].values()) == {0}
    assert result["adapter_hash"] == compute_candidate_proof_adapter_hash(result)


def test_valid_no_fill_is_hash_bound_blocker_not_reward() -> None:
    projection = _selected_projection()
    binding = _binding(projection)

    result = adapt_candidate_proof(
        projection=projection,
        selection_proof_binding=binding,
        proof_packet=_bound_no_fill_packet(projection, binding),
    )

    assert result["status"] == NO_MATCHED_FILLS
    assert result["proof"]["verdict"] == NO_MATCHED_FILLS
    assert result["reward_records"] == []


def test_valid_complete_packet_is_only_ready_for_reward_validation() -> None:
    projection = _selected_projection()
    binding = _binding(projection)

    result = adapt_candidate_proof(
        projection=projection,
        selection_proof_binding=binding,
        proof_packet=_bound_ready_packet(projection, binding),
    )

    assert result["status"] == READY_FOR_REWARD_VALIDATION
    assert result["proof"]["verdict"] == "proof_ready"
    assert result["reasons"] == ["source_only_no_durable_receipt_attestation"]


def test_binding_cannot_invent_or_substitute_candidate_identity() -> None:
    projection = _selected_projection()
    binding = _binding(projection, candidate_id="other|BTCUSDT|Buy")

    result = adapt_candidate_proof(
        projection=projection,
        selection_proof_binding=binding,
    )

    assert result["status"] == INVALID
    assert result["reasons"] == ["selection_proof_binding_candidate_id_mismatch"]


def test_tampered_binding_or_provenance_fails_closed() -> None:
    projection = _selected_projection()
    binding = _binding(projection)
    tampered = copy.deepcopy(binding)
    tampered["candidate_id"] = "other|BTCUSDT|Buy"

    binding_result = adapt_candidate_proof(
        projection=projection,
        selection_proof_binding=tampered,
    )
    assert binding_result["status"] == INVALID
    assert binding_result["reasons"] == ["selection_proof_binding_hash_mismatch"]

    packet = _bound_ready_packet(projection, binding)
    packet["provenance"]["input_artifact_hashes"][
        "candidate_projection_handoff_hash"
    ] = "0" * 64
    packet["proof_packet_hash"] = compute_proof_packet_hash(packet)
    provenance_result = adapt_candidate_proof(
        projection=projection,
        selection_proof_binding=binding,
        proof_packet=packet,
    )
    assert provenance_result["status"] == INVALID
    assert "proof_packet_candidate_projection_handoff_hash_mismatch" in provenance_result[
        "reasons"
    ]


def test_no_fill_with_cost_or_duplicate_fill_packet_cannot_be_upgraded() -> None:
    projection = _selected_projection()
    binding = _binding(projection)
    no_fill = _bound_no_fill_packet(projection, binding)
    no_fill["cost_identity"] = {}
    no_fill["proof_packet_hash"] = compute_proof_packet_hash(no_fill)

    no_fill_result = adapt_candidate_proof(
        projection=projection,
        selection_proof_binding=binding,
        proof_packet=no_fill,
    )
    assert no_fill_result["status"] == INVALID

    duplicate = _bound_ready_packet(projection, binding)
    duplicate["execution_identity"]["fill_ids"] = ["fill-entry-1", "fill-entry-1"]
    duplicate["proof_packet_hash"] = compute_proof_packet_hash(duplicate)
    duplicate_result = adapt_candidate_proof(
        projection=projection,
        selection_proof_binding=binding,
        proof_packet=duplicate,
    )
    assert duplicate_result["status"] == INVALID


def test_pit_future_or_authority_injection_fails_closed() -> None:
    projection = _selected_projection()
    binding = _binding(projection)
    future_pit = _bound_ready_packet(projection, binding)
    manifest = future_pit["provenance"]["pit_dataset_manifest"]
    manifest["as_of_ts"] = "2026-07-10T13:00:00Z"
    manifest["manifest_hash"] = compute_pit_dataset_manifest_hash(manifest)
    future_pit["proof_packet_hash"] = compute_proof_packet_hash(future_pit)

    future_result = adapt_candidate_proof(
        projection=projection,
        selection_proof_binding=binding,
        proof_packet=future_pit,
    )
    assert future_result["status"] == INVALID
    assert "proof_packet_pit_after_projection_decision" in future_result["reasons"]

    authority = _bound_ready_packet(projection, binding)
    authority["source_only"] = {"order_authority_granted": True}
    authority["proof_packet_hash"] = compute_proof_packet_hash(authority)
    authority_result = adapt_candidate_proof(
        projection=projection,
        selection_proof_binding=binding,
        proof_packet=authority,
    )
    assert authority_result["status"] == INVALID
    assert any("authority_boundary_violation" in reason for reason in authority_result["reasons"])


def test_projection_must_be_selected_and_key_order_is_semantic() -> None:
    unselected = _projection(selected=False)
    invalid = adapt_candidate_proof(
        projection=unselected,
        selection_proof_binding=None,
    )
    assert invalid["status"] == INVALID
    assert invalid["reasons"] == ["projection_not_qualified_candidate"]

    projection = _selected_projection()
    binding = _binding(projection)
    packet = _bound_no_fill_packet(projection, binding)
    reordered = dict(reversed(list(binding.items())))
    assert compute_selection_proof_binding_hash(binding) == compute_selection_proof_binding_hash(
        reordered
    )
    assert adapt_candidate_proof(
        projection=projection,
        selection_proof_binding=binding,
        proof_packet=packet,
    )["adapter_hash"] == adapt_candidate_proof(
        projection=projection,
        selection_proof_binding=reordered,
        proof_packet=packet,
    )["adapter_hash"]


def test_legacy_projection_without_b2c_handoff_is_rejected() -> None:
    legacy = _projection(selected=True)
    result = adapt_candidate_proof(
        projection=legacy,
        selection_proof_binding=None,
    )

    assert result["status"] == INVALID
    assert result["reasons"] == ["projection_handoff_missing"]


def test_reward_record_permutation_has_one_proof_input_identity() -> None:
    projection = _selected_projection()
    binding = _binding(projection)
    proof = _bound_ready_packet(projection, binding)
    first = _bound_reward_record(proof, window_id="effect-window-1")
    second = _bound_reward_record(proof, window_id="effect-window-2")

    forward = adapt_candidate_proof(
        projection=projection,
        selection_proof_binding=binding,
        proof_packet=proof,
        reward_records=[first, second],
    )
    reverse = adapt_candidate_proof(
        projection=projection,
        selection_proof_binding=binding,
        proof_packet=proof,
        reward_records=[second, first],
    )

    assert forward["status"] == READY_FOR_REWARD_VALIDATION
    assert forward["proof_input_hash"] == reverse["proof_input_hash"]
    assert forward["adapter_hash"] == reverse["adapter_hash"]
    assert forward["reward_records"] == reverse["reward_records"]
