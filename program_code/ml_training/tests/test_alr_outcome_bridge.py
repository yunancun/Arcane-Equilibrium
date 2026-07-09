from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from ml_training.alr_controller_contracts import (
    OUTCOME_ADVANCED,
    OUTCOME_BLOCKED_BOUNDARY,
    OUTCOME_DEFER_EVIDENCE,
)
from ml_training.alr_outcome_bridge import (
    ALR_OUTCOME_BRIDGE_FIELD,
    STATUS_BLOCKED_BOUNDARY,
    STATUS_DEFER_EVIDENCE,
    STATUS_EVIDENCE_READY,
    build_alr_outcome_bridge_packet,
    compute_alr_outcome_bridge_hash,
    extract_alr_outcome_bridge,
    main,
    validate_alr_outcome_bridge_packet,
)
from ml_training.proof_packet_contract import (
    NO_MATCHED_FILLS,
    compute_proof_packet_hash,
)
from ml_training.reward_ledger import REWARD_LEDGER_FIELD, compute_reward_record_hash

_REWARD_LEDGER_TEST_PATH = Path(__file__).with_name("test_reward_ledger.py")
_REWARD_LEDGER_SPEC = importlib.util.spec_from_file_location(
    "_alr_outcome_bridge_reward_ledger_fixtures",
    _REWARD_LEDGER_TEST_PATH,
)
assert _REWARD_LEDGER_SPEC is not None
_reward_ledger_fixtures = importlib.util.module_from_spec(_REWARD_LEDGER_SPEC)
assert _REWARD_LEDGER_SPEC.loader is not None
_REWARD_LEDGER_SPEC.loader.exec_module(_reward_ledger_fixtures)
_build_record = _reward_ledger_fixtures._build_record
_no_fill_packet = _reward_ledger_fixtures._no_fill_packet
_valid_envelope = _reward_ledger_fixtures._valid_envelope
_valid_proof_packet = _reward_ledger_fixtures._valid_proof_packet


def _effect_window(index: int) -> dict:
    return {
        "window_id": f"effect:grid_trading|ETHUSDT|Buy:2026-07-06T10:0{index}:00Z",
        "start_ts": f"2026-07-06T10:0{index}:00Z",
        "end_ts": f"2026-07-06T10:0{index + 1}:00Z",
        "observation_count": 2,
        "window_source": "offline_fixture",
        "point_in_time": True,
    }


def _record(index: int, *, proof: dict | None = None) -> dict:
    proof_packet = proof or _valid_proof_packet()
    envelope = _valid_envelope(
        proof_packet,
        source_proposal_or_recommendation_id=f"mlde-shadow-rec-{index}",
        source_payload={
            "recommendation_id": f"mlde-shadow-rec-{index}",
            "candidate_id": "grid_trading|ETHUSDT|Buy",
            "strategy_name": "grid_trading",
            "symbol": "ETHUSDT",
            "side": "Buy",
        },
    )
    record = _build_record(
        proof_packet=proof_packet,
        demo_mutation_envelope=envelope,
        effect_window=_effect_window(index),
    )
    record["record_id"] = f"{record['record_id']}:sample-{index}"
    record["execution_identity"]["order_link_id"] = (
        f"oc_dm_1782040200000_{index}_0deadbeef"
    )
    record["execution_identity"]["fill_ids"] = [
        f"fill-entry-{index}",
        f"fill-exit-{index}",
    ]
    record["effect_window"] = _effect_window(index)
    record["record_hash"] = compute_reward_record_hash(record)
    return record


def _ready_inputs() -> tuple[dict, list[dict]]:
    proof = _valid_proof_packet()
    return proof, [_record(1, proof=proof), _record(2, proof=proof)]


def _rehash_proof(proof: dict) -> dict:
    proof["proof_packet_hash"] = compute_proof_packet_hash(proof)
    return proof


def _rehash_record(record: dict) -> dict:
    record["record_hash"] = compute_reward_record_hash(record)
    return record


def _bridge(proof: dict, records: list[dict]) -> dict:
    return build_alr_outcome_bridge_packet(
        proof_packet=proof,
        reward_records=records,
    )


def test_valid_cli_writes_hash_bound_evidence_ready_packet(tmp_path: Path) -> None:
    proof, records = _ready_inputs()
    proof_path = tmp_path / "proof.json"
    first_reward_path = tmp_path / "reward_a.json"
    second_reward_path = tmp_path / "reward_b.json"
    out_path = tmp_path / "bridge.json"
    proof_path.write_text(json.dumps({"proof_packet": proof}), encoding="utf-8")
    first_reward_path.write_text(json.dumps(records[0]), encoding="utf-8")
    second_reward_path.write_text(
        json.dumps({REWARD_LEDGER_FIELD: records[1]}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--proof-packet",
            str(proof_path),
            "--reward-ledger",
            str(first_reward_path),
            "--reward-ledger",
            str(second_reward_path),
            "--out",
            str(out_path),
        ]
    )

    assert exit_code == 0
    packet = json.loads(out_path.read_text(encoding="utf-8"))
    assert packet["bridge_status"] == STATUS_EVIDENCE_READY
    assert packet["outcome"] == OUTCOME_ADVANCED
    assert packet["bridge_hash"] == compute_alr_outcome_bridge_hash(packet)
    validation = validate_alr_outcome_bridge_packet(packet)
    assert validation.valid is True
    assert validation.outcome == OUTCOME_ADVANCED
    assert packet["proof_packet_ready_count"] == 1
    assert packet["reward_ledger_ready_count"] == 2
    assert all(value == 0 for value in packet["authority_counters"].values())
    assert all(value is False for value in packet["no_authority"].values())
    for field in (
        "proof_authority_granted",
        "promotion_ready",
        "runtime_authority_granted",
        "order_allowed",
        "live_enabled",
    ):
        assert packet[field] is False


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (
            lambda proof, records: (_no_fill_packet(), records),
            "proof_packet_no_matched_fills",
        ),
        (
            lambda proof, records: (proof, []),
            "reward_records_missing",
        ),
        (
            lambda proof, records: (proof, records[:1]),
            "repeat_evidence_ready",
        ),
        (
            lambda proof, records: (
                proof,
                [
                    _rehash_record(
                        {
                            **copy.deepcopy(records[0]),
                            "cost_identity": {
                                k: v
                                for k, v in records[0]["cost_identity"].items()
                                if k not in {"funding_bps", "slippage_bps"}
                            },
                        }
                    ),
                    records[1],
                ],
            ),
            "actual_cost_fields_present",
        ),
        (
            lambda proof, records: (
                _rehash_proof({k: v for k, v in copy.deepcopy(proof).items() if k != "controls"}),
                records,
            ),
            "controls_present",
        ),
        (
            lambda proof, records: (
                _proof_without_oos(proof),
                [_record(1, proof=_proof_without_oos(proof)), _record(2, proof=_proof_without_oos(proof))],
            ),
            "oos_evidence_present",
        ),
        (
            lambda proof, records: (
                _proof_with_exclusion(proof),
                records,
            ),
            "proof_exclusions_empty",
        ),
    ],
)
def test_incomplete_evidence_defers(mutator, reason: str) -> None:
    proof, records = _ready_inputs()
    mutated_proof, mutated_records = mutator(copy.deepcopy(proof), copy.deepcopy(records))

    packet = _bridge(mutated_proof, mutated_records)
    validation = validate_alr_outcome_bridge_packet(packet)

    assert packet["bridge_status"] == STATUS_DEFER_EVIDENCE
    assert validation.valid is True
    assert validation.outcome == OUTCOME_DEFER_EVIDENCE
    assert reason in validation.reasons


def _proof_without_oos(proof: dict) -> dict:
    mutated = copy.deepcopy(proof)
    mutated["controls"]["oos_split"] = {"split_hash": "b" * 64}
    return _rehash_proof(mutated)


def _proof_with_exclusion(proof: dict) -> dict:
    mutated = copy.deepcopy(proof)
    mutated["controls"]["proof_exclusions"] = ["cleanup_fill"]
    return _rehash_proof(mutated)


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (
            lambda proof, records: (
                proof,
                [
                    _rehash_record(
                        {
                            **copy.deepcopy(records[0]),
                            "candidate_identity": {
                                **records[0]["candidate_identity"],
                                "symbol": "BTCUSDT",
                            },
                        }
                    ),
                    records[1],
                ],
            ),
            "candidate_identity_matches",
        ),
        (
            lambda proof, records: (
                proof,
                [
                    _rehash_record(
                        {
                            **copy.deepcopy(records[0]),
                            "lineage": {
                                **records[0]["lineage"],
                                "proof_packet_hash": "f" * 64,
                            },
                        }
                    ),
                    records[1],
                ],
            ),
            "proof_hash_matches_reward_lineage",
        ),
    ],
)
def test_candidate_or_hash_mismatch_defers(mutator, reason: str) -> None:
    proof, records = _ready_inputs()
    mutated_proof, mutated_records = mutator(proof, records)

    packet = _bridge(mutated_proof, mutated_records)
    validation = validate_alr_outcome_bridge_packet(packet)

    assert packet["bridge_status"] == STATUS_DEFER_EVIDENCE
    assert validation.valid is True
    assert validation.outcome == OUTCOME_DEFER_EVIDENCE
    assert reason in validation.reasons


def test_cloned_reward_record_cannot_satisfy_repeat_evidence() -> None:
    proof, records = _ready_inputs()
    cloned = copy.deepcopy(records[0])
    cloned["record_id"] = records[1]["record_id"]
    cloned["execution_identity"]["order_link_id"] = records[1]["execution_identity"][
        "order_link_id"
    ]
    cloned["execution_identity"]["fill_ids"] = records[1]["execution_identity"][
        "fill_ids"
    ]
    cloned["effect_window"] = records[1]["effect_window"]
    cloned["record_hash"] = compute_reward_record_hash(cloned)

    packet = _bridge(proof, [records[0], cloned])
    validation = validate_alr_outcome_bridge_packet(packet)

    assert packet["bridge_status"] == STATUS_DEFER_EVIDENCE
    assert validation.valid is True
    assert validation.outcome == OUTCOME_DEFER_EVIDENCE
    assert "repeat_evidence_ready" in validation.reasons


@pytest.mark.parametrize(
    "alias",
    [
        "order_allowed",
        "runtime_mutation_allowed",
        "pg_read_allowed",
        "promotion_ready",
        "live_enabled",
    ],
)
def test_authority_aliases_block_boundary(alias: str) -> None:
    proof, records = _ready_inputs()
    proof["metadata"] = {alias: True}
    proof["proof_packet_hash"] = compute_proof_packet_hash(proof)

    packet = _bridge(proof, records)
    validation = validate_alr_outcome_bridge_packet(packet)

    assert packet["bridge_status"] == STATUS_BLOCKED_BOUNDARY
    assert validation.valid is False
    assert validation.outcome == OUTCOME_BLOCKED_BOUNDARY
    assert validation.authority_boundary_violation is True


def test_extract_reads_canonical_field_only() -> None:
    proof, records = _ready_inputs()
    packet = _bridge(proof, records)

    assert extract_alr_outcome_bridge({ALR_OUTCOME_BRIDGE_FIELD: packet}) == packet
    assert extract_alr_outcome_bridge({"bridge": packet}) is None


@pytest.mark.parametrize(
    "bad_name",
    [
        "proof_latest.json",
        "bridge_latest.json",
    ],
)
def test_latest_input_or_output_path_rejected_and_no_file_written(
    tmp_path: Path,
    bad_name: str,
) -> None:
    proof, records = _ready_inputs()
    proof_path = tmp_path / "proof.json"
    reward_path = tmp_path / "reward.json"
    out_path = tmp_path / "bridge.json"
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    reward_path.write_text(json.dumps(records[0]), encoding="utf-8")

    if bad_name.startswith("proof"):
        proof_arg = tmp_path / bad_name
        out_arg = out_path
    else:
        proof_arg = proof_path
        out_arg = tmp_path / bad_name

    exit_code = main(
        [
            "--proof-packet",
            str(proof_arg),
            "--reward-ledger",
            str(reward_path),
            "--out",
            str(out_arg),
        ]
    )

    assert exit_code == 2
    assert not out_arg.exists()


@pytest.mark.parametrize(
    "forbidden_dir",
    ["runtime", "pg", "bybit_exchange"],
)
def test_forbidden_output_paths_rejected_and_no_file_written(
    tmp_path: Path,
    forbidden_dir: str,
) -> None:
    proof, records = _ready_inputs()
    proof_path = tmp_path / "proof.json"
    reward_path = tmp_path / "reward.json"
    out_path = tmp_path / forbidden_dir / "bridge.json"
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    reward_path.write_text(json.dumps(records[0]), encoding="utf-8")

    exit_code = main(
        [
            "--proof-packet",
            str(proof_path),
            "--reward-ledger",
            str(reward_path),
            "--out",
            str(out_path),
        ]
    )

    assert exit_code == 2
    assert not out_path.exists()
    assert not out_path.parent.exists()
