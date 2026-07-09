"""
MODULE_NOTE
模塊用途：AI/ML roadmap 的 ALR outcome bridge source-only offline P0/P1 contract。
主要函數：build_alr_outcome_bridge_packet、validate_alr_outcome_bridge_packet、
compute_alr_outcome_bridge_hash、extract_alr_outcome_bridge。
依賴：僅 Python 標準庫與 proof/reward source-only validators；不讀 DB、
不連 runtime、不呼叫交易所、不讀 ``_latest``。
硬邊界：本模塊只把已驗證的 proof_packet_v1 與 reward_ledger_v1 聚合成
ALR outcome evidence packet；不可授予 proof、promotion、runtime、order、
probe、Cost Gate、serving、live/mainnet authority。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .alr_controller_contracts import (
    BOUNDARY_LABEL,
    OUTCOME_ADVANCED,
    OUTCOME_BLOCKED_BOUNDARY,
    OUTCOME_DEFER_EVIDENCE,
)
from .proof_packet_contract import (
    PROOF_PACKET_FIELD,
    PROOF_READY,
    compute_proof_packet_hash,
    extract_proof_packet,
    validate_proof_packet,
)
from .reward_ledger import (
    REWARD_LEDGER_FIELD,
    REWARD_RECORD_READY,
    compute_reward_record_hash,
    extract_reward_record,
    validate_reward_batch,
    validate_reward_record,
)


ALR_OUTCOME_BRIDGE_FIELD = "alr_outcome_bridge"
ALR_OUTCOME_BRIDGE_SCHEMA_VERSION = "alr_outcome_bridge_v1"

STATUS_EVIDENCE_READY = "EVIDENCE_READY"
STATUS_DEFER_EVIDENCE = "DEFER_EVIDENCE"
STATUS_BLOCKED_BOUNDARY = "BLOCKED_BOUNDARY"
_ALLOWED_STATUSES = {
    STATUS_EVIDENCE_READY,
    STATUS_DEFER_EVIDENCE,
    STATUS_BLOCKED_BOUNDARY,
}
_ALLOWED_OUTCOMES = {
    OUTCOME_ADVANCED,
    OUTCOME_DEFER_EVIDENCE,
    OUTCOME_BLOCKED_BOUNDARY,
}

_HEX64_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_TRUTHY_STRINGS = {
    "1",
    "true",
    "yes",
    "y",
    "on",
    "enabled",
    "enable",
    "grant",
    "granted",
    "allow",
    "allowed",
    "active",
    "approved",
    "present",
}
_FALSE_STRINGS = {
    "",
    "0",
    "false",
    "no",
    "n",
    "off",
    "disabled",
    "disable",
    "deny",
    "denied",
    "none",
    "null",
    "not_applicable",
    "n/a",
}
_AUTHORITY_TRUE_KEYS = set(
    """
    runtime runtime_allowed runtime_authority runtime_authority_granted
    runtime_mutation runtime_mutation_allowed runtime_mutation_performed
    db db_read db_read_allowed db_read_performed db_write db_write_allowed
    db_write_performed db_migration db_migration_allowed db_migration_performed
    pg pg_read pg_read_allowed pg_write pg_write_allowed ipc ipc_allowed
    ipc_authority_granted bybit bybit_allowed bybit_contact_performed mcp
    mcp_allowed mcp_server_started scheduler scheduler_allowed scheduler_enabled
    cron cron_allowed daemon daemon_allowed service service_allowed
    service_restart_allowed service_restart_performed env env_mutation_allowed
    env_mutation_performed latest latest_allowed latest_consumed
    latest_promotion_allowed proof proof_allowed proof_authority_granted
    proof_ready promotion promotion_allowed promotion_authority_granted
    promotion_enabled promotion_ready delete delete_allowed delete_performed
    apply apply_allowed apply_performed cost_gate cost_gate_allowed
    cost_gate_change cost_gate_change_performed cost_gate_lowered
    cost_gate_lowering_allowed order order_allowed order_authority_granted
    order_or_probe_allowed order_or_probe_performed probe probe_allowed
    probe_authority_granted serving serving_reload_allowed
    serving_reload_performed live live_allowed live_authority_granted
    live_enabled mainnet mainnet_allowed mainnet_enabled
    live_or_mainnet_performed exchange exchange_contact_performed
    private_read_allowed private_read_performed trade_allowed trading_allowed
    trading_enabled enable_trading execution_authority_granted
    execution_permission_granted execution_allowed
    """.split()
)
_AUTHORITY_KEY_TERMS = tuple(
    """
    runtime db pg ipc bybit mcp scheduler cron daemon service env latest proof
    promotion delete apply cost cost_gate order probe serving live mainnet
    exchange private trade trading execution
    """.split()
)
_AUTHORITY_ACTION_TERMS = tuple(
    """
    allow allowed author authority change consume consumed contact delete deploy
    enable enabled grant granted lower lowering mutate mutation perform performed
    promote promotion read reload restart start started touch use used write
    """.split()
)
_AUTHORITY_ACTION_TOKENS = {"read"}
_NO_AUTHORITY_KEYS = tuple(
    """
    runtime_mutation db_read db_write db_migration pg_read pg_write ipc bybit
    exchange_contact private_read secret_access mcp order_or_probe cost_gate_change
    deploy service_restart env_mutation serving_reload live_or_mainnet promotion
    proof_authority delete apply scheduler cron daemon
    """.split()
)
_AUTHORITY_COUNTER_KEYS = tuple(
    """
    runtime_mutation_count db_read_count db_write_count pg_read_count
    exchange_contact_count order_or_probe_count serving_reload_count
    promotion_count proof_authority_count live_or_mainnet_count
    """.split()
)
_FALSE_AUTHORITY_FIELDS = tuple(
    """
    proof_authority_granted promotion_ready promotion_authority_granted
    runtime_authority_granted runtime_mutation_allowed pg_read_allowed
    order_allowed order_authority_granted order_or_probe_allowed
    cost_gate_change_performed serving_reload_allowed live_enabled
    live_authority_granted mainnet_enabled
    """.split()
)
_CANDIDATE_FIELDS = ("candidate_id", "strategy_name", "symbol", "side")
_COST_FIELDS = tuple(
    "maker_fee_bps taker_fee_bps slippage_bps spread_bps funding_bps markout_bps "
    "realized_net_pnl_bps realized_net_pnl_usdt".split()
)
_PATH_FORBIDDEN_TERMS = {
    "runtime",
    "pg",
    "postgres",
    "postgresql",
    "database",
    "ipc",
    "bybit",
    "exchange",
    "mcp",
    "decision",
    "lease",
    "order",
    "probe",
    "cost_gate",
    "costgate",
    "serving",
    "promotion",
    "promote",
    "delete",
    "apply",
    "cron",
    "daemon",
    "scheduler",
    "service",
    "env",
    "live",
    "mainnet",
}


@dataclass(frozen=True)
class AlrOutcomeBridgeValidation:
    """ALR outcome bridge 驗證結果；boundary block 一律 fail closed。"""

    valid: bool
    outcome: str
    reason: str
    reasons: tuple[str, ...]
    authority_boundary_violation: bool = False


class AlrOutcomeBridgeError(ValueError):
    """Caller-provided source artifacts or paths violate bridge contract."""


def extract_alr_outcome_bridge(mapping: Any) -> Any:
    """只讀 canonical ``alr_outcome_bridge`` 欄位，不接受 alias。"""
    if not isinstance(mapping, Mapping):
        return None
    return mapping.get(ALR_OUTCOME_BRIDGE_FIELD)


def compute_alr_outcome_bridge_hash(packet: Mapping[str, Any]) -> str:
    """對 bridge packet 做 canonical JSON sha256；頂層 ``bridge_hash`` 不入 hash。"""
    payload = copy.deepcopy(dict(packet))
    payload.pop("bridge_hash", None)
    return _stable_sha256_json(payload)


def build_alr_outcome_bridge_packet(
    *,
    proof_packet: Mapping[str, Any],
    reward_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """從 caller 提供的 proof / reward artifacts 建立 hash-bound ALR evidence packet."""
    records = [copy.deepcopy(dict(record)) for record in reward_records]
    proof = copy.deepcopy(dict(proof_packet))
    decision = _decide(proof, records)
    candidate = _candidate_from_proof_or_records(proof, records)
    proof_hash = _hash_or_empty(proof.get("proof_packet_hash"))
    reward_refs = _reward_refs(records)
    proof_refs = sorted(
        {
            _strip_hash(_text(_mapping(record.get("lineage")).get("proof_packet_hash")))
            for record in records
            if _is_hash(_strip_hash(_text(_mapping(record.get("lineage")).get("proof_packet_hash"))))
        }
    )

    packet: dict[str, Any] = {
        "schema_version": ALR_OUTCOME_BRIDGE_SCHEMA_VERSION,
        "boundary_label": BOUNDARY_LABEL,
        "bridge_status": decision["status"],
        "outcome": decision["outcome"],
        "decision_reasons": decision["reasons"],
        "candidate_identity": candidate,
        "inputs": {
            "proof_packet_ref": {"proof_packet_hash": proof_hash},
            "reward_ledger_refs": reward_refs,
            "reward_lineage_proof_packet_refs": proof_refs,
        },
        "evidence_checks": decision["checks"],
        "candidate_matched_fills_count": _candidate_matched_fills_count(proof, records),
        "proof_packet_ready_count": 1 if decision["proof_ready"] else 0,
        "reward_ledger_ready_count": decision["ready_record_count"],
        "authority_counters": {key: 0 for key in _AUTHORITY_COUNTER_KEYS},
        "no_authority": _no_authority(),
        "source_artifacts": {
            "proof_packet": proof,
            "reward_records": records,
        },
    }
    for field in _FALSE_AUTHORITY_FIELDS:
        packet[field] = False
    packet["bridge_hash"] = compute_alr_outcome_bridge_hash(packet)
    return packet


def validate_alr_outcome_bridge_packet(packet: Any) -> AlrOutcomeBridgeValidation:
    """驗證 ``alr_outcome_bridge_v1`` packet 並重算 bridge outcome。"""
    if packet is None:
        return _result(False, OUTCOME_DEFER_EVIDENCE, "alr_outcome_bridge_missing")
    if not isinstance(packet, Mapping):
        return _result(False, OUTCOME_DEFER_EVIDENCE, "alr_outcome_bridge_not_mapping")

    authority_violations = _authority_violations(packet)
    if authority_violations:
        return _result(
            False,
            OUTCOME_BLOCKED_BOUNDARY,
            f"authority_boundary_violation:{authority_violations[0]}",
            tuple(f"authority_boundary_violation:{item}" for item in authority_violations),
            authority_boundary_violation=True,
        )

    proof = _mapping(_mapping(packet.get("source_artifacts")).get("proof_packet"))
    records = _reward_records(packet)
    decision = _decide(proof, records)

    structural_reasons: list[str] = []
    if _text(packet.get("schema_version")) != ALR_OUTCOME_BRIDGE_SCHEMA_VERSION:
        structural_reasons.append("schema_version_unknown")
    if _text(packet.get("boundary_label")) != BOUNDARY_LABEL:
        structural_reasons.append("boundary_label_mismatch")
    if _text(packet.get("bridge_status")) not in _ALLOWED_STATUSES:
        structural_reasons.append("bridge_status_unknown")
    if _text(packet.get("outcome")) not in _ALLOWED_OUTCOMES:
        structural_reasons.append("outcome_unknown")
    structural_reasons.extend(_no_authority_reasons(_mapping(packet.get("no_authority"))))
    structural_reasons.extend(
        _authority_counter_reasons(_mapping(packet.get("authority_counters")))
    )
    structural_reasons.extend(_false_authority_field_reasons(packet))

    bridge_hash = _text(packet.get("bridge_hash"))
    if not bridge_hash:
        structural_reasons.append("bridge_hash_missing")
    elif not _is_hash(bridge_hash):
        structural_reasons.append("bridge_hash_malformed")
    else:
        try:
            computed_hash = compute_alr_outcome_bridge_hash(packet)
        except (TypeError, ValueError):
            structural_reasons.append("bridge_hash_uncomputable")
        else:
            if _strip_hash(bridge_hash) != computed_hash:
                structural_reasons.append("bridge_hash_mismatch")

    if _text(packet.get("bridge_status")) != decision["status"]:
        structural_reasons.append("bridge_status_mismatch")
    if _text(packet.get("outcome")) != decision["outcome"]:
        structural_reasons.append("outcome_mismatch")
    declared_reasons = tuple(str(item) for item in packet.get("decision_reasons", ()))
    if declared_reasons != tuple(decision["reasons"]):
        structural_reasons.append("decision_reasons_mismatch")
    if _mapping(packet.get("evidence_checks")) != decision["checks"]:
        structural_reasons.append("evidence_checks_mismatch")
    if _mapping(packet.get("inputs")) != _expected_inputs(proof, records):
        structural_reasons.append("inputs_mismatch")

    if structural_reasons:
        return _result(False, decision["outcome"], structural_reasons[0], structural_reasons)
    return _result(
        decision["outcome"] != OUTCOME_BLOCKED_BOUNDARY,
        decision["outcome"],
        decision["reasons"][0],
        decision["reasons"],
        authority_boundary_violation=decision["outcome"] == OUTCOME_BLOCKED_BOUNDARY,
    )


def load_proof_packet(path: Path) -> Mapping[str, Any]:
    _reject_forbidden_path(path, "proof_packet")
    raw = _load_json(path, "proof_packet")
    proof = extract_proof_packet(raw) if isinstance(raw, Mapping) and PROOF_PACKET_FIELD in raw else raw
    if not isinstance(proof, Mapping):
        raise AlrOutcomeBridgeError("proof_packet_not_mapping")
    return proof


def load_reward_records(path: Path) -> list[Mapping[str, Any]]:
    _reject_forbidden_path(path, "reward_ledger")
    raw = _load_json(path, "reward_ledger")
    value = extract_reward_record(raw) if isinstance(raw, Mapping) and REWARD_LEDGER_FIELD in raw else raw
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, Mapping)):
        records = list(value)
    else:
        records = [value]
    if any(not isinstance(record, Mapping) for record in records):
        raise AlrOutcomeBridgeError("reward_ledger_not_mapping")
    return records


def write_bridge_output(packet: Mapping[str, Any], out_path: Path) -> None:
    _reject_forbidden_path(out_path, "out")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Source-only ALR outcome bridge")
    parser.add_argument("--proof-packet", required=True, help="Proof packet JSON path")
    parser.add_argument(
        "--reward-ledger",
        action="append",
        required=True,
        help="Reward ledger record JSON path; may be repeated",
    )
    parser.add_argument("--out", required=True, help="Explicit bridge output JSON path")
    args = parser.parse_args(argv)

    proof_path = Path(args.proof_packet)
    reward_paths = [Path(item) for item in args.reward_ledger]
    out_path = Path(args.out)

    try:
        for label, path in (
            ("proof_packet", proof_path),
            *[(f"reward_ledger[{index}]", path) for index, path in enumerate(reward_paths)],
            ("out", out_path),
        ):
            _reject_forbidden_path(path, label)

        proof_packet = load_proof_packet(proof_path)
        reward_records: list[Mapping[str, Any]] = []
        for reward_path in reward_paths:
            reward_records.extend(load_reward_records(reward_path))
        packet = build_alr_outcome_bridge_packet(
            proof_packet=proof_packet,
            reward_records=reward_records,
        )
        write_bridge_output(packet, out_path)
    except AlrOutcomeBridgeError as exc:
        print(f"alr_outcome_bridge_error:{exc}", file=sys.stderr)
        return 2
    return 0


def _decide(
    proof_packet: Mapping[str, Any],
    reward_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    boundary_reasons = _source_authority_reasons(proof_packet, reward_records)
    if boundary_reasons:
        return _decision(
            STATUS_BLOCKED_BOUNDARY,
            OUTCOME_BLOCKED_BOUNDARY,
            boundary_reasons,
            proof_ready=False,
            ready_record_count=0,
            checks={},
        )

    reasons: list[str] = []
    proof_validation = validate_proof_packet(proof_packet)
    if proof_validation.authority_boundary_violation:
        return _decision(
            STATUS_BLOCKED_BOUNDARY,
            OUTCOME_BLOCKED_BOUNDARY,
            list(proof_validation.reasons),
            proof_ready=False,
            ready_record_count=0,
            checks={},
        )
    if not proof_validation.proof_ready or proof_validation.verdict != PROOF_READY:
        if getattr(proof_validation, "no_fill_blocker", False):
            reasons.append("proof_packet_no_matched_fills")
        else:
            reasons.append(f"proof_packet_not_proof_ready:{proof_validation.reason}")

    if not reward_records:
        reasons.append("reward_records_missing")

    batch_validation = validate_reward_batch(reward_records)
    if batch_validation.authority_boundary_violation:
        return _decision(
            STATUS_BLOCKED_BOUNDARY,
            OUTCOME_BLOCKED_BOUNDARY,
            list(batch_validation.reasons),
            proof_ready=proof_validation.proof_ready,
            ready_record_count=0,
            checks={},
        )
    if not batch_validation.reward_ready:
        reasons.append(f"reward_batch_not_ready:{batch_validation.reason}")

    ready_records = [
        record
        for record in reward_records
        if validate_reward_record(record).reward_ready
        and _text(record.get("verdict")) == REWARD_RECORD_READY
    ]
    proof_hash = _strip_hash(_text(proof_packet.get("proof_packet_hash")))
    checks = _evidence_checks(proof_packet, reward_records, ready_records, proof_hash)
    for name, passed in checks.items():
        if not passed:
            reasons.append(name)

    if reasons:
        return _decision(
            STATUS_DEFER_EVIDENCE,
            OUTCOME_DEFER_EVIDENCE,
            reasons,
            proof_ready=proof_validation.proof_ready,
            ready_record_count=len(ready_records),
            checks=checks,
        )
    return _decision(
        STATUS_EVIDENCE_READY,
        OUTCOME_ADVANCED,
        ["ok"],
        proof_ready=True,
        ready_record_count=len(ready_records),
        checks=checks,
    )


def _decision(
    status: str,
    outcome: str,
    reasons: Sequence[str],
    *,
    proof_ready: bool,
    ready_record_count: int,
    checks: Mapping[str, bool],
) -> dict[str, Any]:
    normalized_reasons = tuple(str(reason) for reason in reasons) or ("ok",)
    return {
        "status": status,
        "outcome": outcome,
        "reasons": normalized_reasons,
        "proof_ready": proof_ready,
        "ready_record_count": ready_record_count,
        "checks": dict(checks),
    }


def _evidence_checks(
    proof_packet: Mapping[str, Any],
    reward_records: Sequence[Mapping[str, Any]],
    ready_records: Sequence[Mapping[str, Any]],
    proof_hash: str,
) -> dict[str, bool]:
    return {
        "proof_hash_matches_reward_lineage": _proof_hash_matches_reward_lineage(
            reward_records, proof_hash
        ),
        "candidate_identity_matches": _candidate_identity_matches(
            proof_packet, reward_records
        ),
        "candidate_matched_order_fill_evidence": _candidate_matched_order_fill_evidence(
            proof_packet, reward_records
        ),
        "actual_cost_fields_present": _actual_cost_fields_present(
            proof_packet, reward_records
        ),
        "pit_rebuild_and_lineage_consistent": _pit_rebuild_and_lineage_consistent(
            proof_packet, reward_records
        ),
        "controls_present": _controls_present(proof_packet, reward_records),
        "proof_exclusions_empty": _proof_exclusions_empty(proof_packet, reward_records),
        "repeat_evidence_ready": _repeat_evidence_ready(ready_records),
        "oos_evidence_present": _oos_evidence_present(proof_packet, reward_records),
    }


def _proof_hash_matches_reward_lineage(
    records: Sequence[Mapping[str, Any]],
    proof_hash: str,
) -> bool:
    if not proof_hash or not records:
        return False
    return all(
        _strip_hash(_text(_mapping(record.get("lineage")).get("proof_packet_hash")))
        == proof_hash
        for record in records
    )


def _candidate_identity_matches(
    proof_packet: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> bool:
    proof_candidate = _candidate_identity(_mapping(proof_packet.get("candidate_identity")))
    if not proof_candidate or not records:
        return False
    for record in records:
        if _candidate_identity(_mapping(record.get("candidate_identity"))) != proof_candidate:
            return False
    return True


def _candidate_matched_order_fill_evidence(
    proof_packet: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> bool:
    proof_execution = _mapping(proof_packet.get("execution_identity"))
    if proof_execution.get("candidate_matched") is not True:
        return False
    if not _text(proof_execution.get("order_link_id")) or not _stable_text_list(
        proof_execution.get("fill_ids")
    ):
        return False
    for record in records:
        execution = _mapping(record.get("execution_identity"))
        if not _text(execution.get("order_link_id")):
            return False
        if not _stable_text_list(execution.get("fill_ids")):
            return False
    return bool(records)


def _actual_cost_fields_present(
    proof_packet: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> bool:
    if not _all_cost_fields(_mapping(proof_packet.get("cost_identity"))):
        return False
    return bool(records) and all(
        _all_cost_fields(_mapping(record.get("cost_identity"))) for record in records
    )


def _pit_rebuild_and_lineage_consistent(
    proof_packet: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> bool:
    pit_manifest = _mapping(_mapping(proof_packet.get("provenance")).get("pit_dataset_manifest"))
    rebuild = _mapping(pit_manifest.get("rebuild_evidence"))
    manifest_hash = _strip_hash(_text(pit_manifest.get("manifest_hash")))
    if not manifest_hash or not rebuild:
        return False
    if _text(rebuild.get("status")) != "rebuild_hash_match":
        return False
    if _number(rebuild.get("original_row_count")) != _number(rebuild.get("rebuilt_row_count")):
        return False
    for field in ("row_ids_hash", "dataset_hash"):
        if _text(rebuild.get(f"original_{field}")) != _text(rebuild.get(f"rebuilt_{field}")):
            return False
    return bool(records) and all(
        _strip_hash(_text(_mapping(record.get("lineage")).get("pit_dataset_manifest_hash")))
        == manifest_hash
        for record in records
    )


def _controls_present(
    proof_packet: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> bool:
    if not _controls_ready(_mapping(proof_packet.get("controls"))):
        return False
    return bool(records) and all(
        _controls_ready(_mapping(record.get("controls"))) for record in records
    )


def _proof_exclusions_empty(
    proof_packet: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> bool:
    if _mapping(proof_packet.get("controls")).get("proof_exclusions") not in ([], (), None):
        return False
    return all(
        _mapping(record.get("controls")).get("proof_exclusions") in ([], (), None)
        for record in records
    )


def _repeat_evidence_ready(records: Sequence[Mapping[str, Any]]) -> bool:
    if len(records) < 2:
        return False
    record_ids = {_text(record.get("record_id")) for record in records}
    record_hashes = {_strip_hash(_text(record.get("record_hash"))) for record in records}
    order_ids = {
        _text(_mapping(record.get("execution_identity")).get("order_link_id"))
        for record in records
    }
    window_ids = {
        _text(_mapping(record.get("effect_window")).get("window_id"))
        for record in records
    }
    fill_sets = {
        tuple(_stable_text_list(_mapping(record.get("execution_identity")).get("fill_ids")))
        for record in records
    }
    mutation_hashes = {
        _strip_hash(_text(_mapping(record.get("lineage")).get("mutation_envelope_hash")))
        for record in records
    }
    source_envelope_hashes = {
        _strip_hash(
            _text(
                _mapping(
                    _mapping(record.get("source_artifacts")).get(
                        "demo_mutation_envelope"
                    )
                ).get("envelope_sha256")
            )
        )
        for record in records
    }
    return (
        len(record_ids) == len(records)
        and "" not in record_ids
        and len(record_hashes) == len(records)
        and "" not in record_hashes
        and len(order_ids) == len(records)
        and "" not in order_ids
        and len(window_ids) == len(records)
        and "" not in window_ids
        and len(fill_sets) == len(records)
        and () not in fill_sets
        and len(mutation_hashes) == len(records)
        and "" not in mutation_hashes
        and len(source_envelope_hashes) == len(records)
        and "" not in source_envelope_hashes
        and mutation_hashes == source_envelope_hashes
    )


def _oos_evidence_present(
    proof_packet: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> bool:
    proof_oos = _mapping(_mapping(proof_packet.get("controls")).get("oos_split"))
    if not _oos_split_ready(proof_oos):
        return False
    return bool(records) and all(
        _oos_split_ready(_mapping(_mapping(record.get("controls")).get("oos_split")))
        for record in records
    )


def _source_authority_reasons(
    proof_packet: Mapping[str, Any],
    reward_records: Sequence[Mapping[str, Any]],
) -> list[str]:
    reasons = [
        f"authority_boundary_violation:proof_packet:{path}"
        for path in _authority_violations(proof_packet)
    ]
    for index, record in enumerate(reward_records):
        reasons.extend(
            f"authority_boundary_violation:reward_records[{index}]:{path}"
            for path in _authority_violations(record)
        )
    return reasons


def _expected_inputs(
    proof_packet: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    proof_hash = _hash_or_empty(proof_packet.get("proof_packet_hash"))
    proof_refs = sorted(
        {
            _strip_hash(_text(_mapping(record.get("lineage")).get("proof_packet_hash")))
            for record in records
            if _is_hash(_strip_hash(_text(_mapping(record.get("lineage")).get("proof_packet_hash"))))
        }
    )
    return {
        "proof_packet_ref": {"proof_packet_hash": proof_hash},
        "reward_ledger_refs": _reward_refs(records),
        "reward_lineage_proof_packet_refs": proof_refs,
    }


def _reward_refs(records: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    refs = []
    for record in records:
        record_hash = ""
        try:
            record_hash = compute_reward_record_hash(record)
        except (TypeError, ValueError):
            record_hash = _hash_or_empty(record.get("record_hash"))
        refs.append({"record_id": _text(record.get("record_id")), "record_hash": record_hash})
    return refs


def _candidate_from_proof_or_records(
    proof_packet: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    proof_candidate = _candidate_identity(_mapping(proof_packet.get("candidate_identity")))
    if proof_candidate:
        return proof_candidate
    for record in records:
        candidate = _candidate_identity(_mapping(record.get("candidate_identity")))
        if candidate:
            return candidate
    return {field: "" for field in _CANDIDATE_FIELDS}


def _candidate_identity(candidate: Mapping[str, Any]) -> dict[str, str]:
    current = {field: _text(candidate.get(field)) for field in _CANDIDATE_FIELDS}
    return current if all(current.values()) else {}


def _candidate_matched_fills_count(
    proof_packet: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> int:
    count = 0
    proof_execution = _mapping(proof_packet.get("execution_identity"))
    if proof_execution.get("candidate_matched") is True:
        count += len(_stable_text_list(proof_execution.get("fill_ids")))
    for record in records:
        count += len(_stable_text_list(_mapping(record.get("execution_identity")).get("fill_ids")))
    return count


def _reward_records(packet: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records = _mapping(packet.get("source_artifacts")).get("reward_records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        return []
    return [record for record in records if isinstance(record, Mapping)]


def _all_cost_fields(cost: Mapping[str, Any]) -> bool:
    return all(_number(cost.get(field)) is not None for field in _COST_FIELDS)


def _controls_ready(controls: Mapping[str, Any]) -> bool:
    return (
        isinstance(controls.get("matched_control_ids"), list)
        and bool(controls.get("matched_control_ids"))
        and isinstance(controls.get("regime_labels"), Mapping)
        and bool(controls.get("regime_labels"))
        and isinstance(controls.get("oos_split"), Mapping)
        and bool(controls.get("oos_split"))
        and controls.get("proof_exclusions") in ([], (), None)
    )


def _oos_split_ready(oos_split: Mapping[str, Any]) -> bool:
    if not oos_split:
        return False
    if not (_text(oos_split.get("split_hash")) or _text(oos_split.get("split_id"))):
        return False
    return any(
        _truthy(oos_split.get(key))
        for key in ("hidden_oos", "oos", "out_of_sample", "out_of_sample_evidence")
    )


def _no_authority() -> dict[str, bool]:
    return {key: False for key in _NO_AUTHORITY_KEYS}


def _no_authority_reasons(no_authority: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for key in _NO_AUTHORITY_KEYS:
        if key not in no_authority:
            reasons.append(f"no_authority_{key}_missing")
        elif no_authority.get(key) is not False:
            reasons.append(f"no_authority_{key}_not_false")
    return reasons


def _authority_counter_reasons(counters: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for key in _AUTHORITY_COUNTER_KEYS:
        if key not in counters:
            reasons.append(f"authority_counters_{key}_missing")
        elif counters.get(key) != 0:
            reasons.append(f"authority_counters_{key}_not_zero")
    return reasons


def _false_authority_field_reasons(packet: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in _FALSE_AUTHORITY_FIELDS:
        if field not in packet:
            reasons.append(f"{field}_missing")
        elif packet.get(field) is not False:
            reasons.append(f"{field}_not_false")
    return reasons


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:  # pragma: no cover - platform-specific text
        raise AlrOutcomeBridgeError(f"{label}_read_failed:{exc}") from exc
    except json.JSONDecodeError as exc:
        raise AlrOutcomeBridgeError(f"{label}_json_invalid:{exc.msg}") from exc


def _reject_forbidden_path(path: Path, label: str) -> None:
    for part in path.parts:
        lowered = part.lower()
        if "_latest" in lowered:
            raise AlrOutcomeBridgeError(f"{label}_path_latest_rejected")
        tokens = set(_path_tokens(lowered))
        if "cost" in tokens and "gate" in tokens:
            raise AlrOutcomeBridgeError(f"{label}_path_forbidden_term:cost_gate")
        forbidden = sorted(tokens & _PATH_FORBIDDEN_TERMS)
        if forbidden:
            raise AlrOutcomeBridgeError(f"{label}_path_forbidden_term:{forbidden[0]}")


def _path_tokens(value: str) -> list[str]:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return [token for token in re.split(r"[^a-z0-9]+", normalized.lower()) if token]


def _authority_violations(value: Any, path: str = "$") -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            norm = _normalized_key(key_text)
            child_path = f"{path}.{key_text}"
            if not norm.startswith(("no_", "not_")):
                if _is_authority_expansion_key(norm) and _authority_value_grants(child):
                    violations.append(child_path)
            violations.extend(_authority_violations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_authority_violations(child, f"{path}[{index}]"))
    return sorted(set(violations))


def _is_authority_expansion_key(norm_key: str) -> bool:
    if norm_key in _AUTHORITY_TRUE_KEYS:
        return True
    tokens = set(_key_tokens(norm_key))
    authority_terms = set(_AUTHORITY_KEY_TERMS)
    action_terms = set(_AUTHORITY_ACTION_TERMS)
    if norm_key in authority_terms:
        return True
    has_authority_term = bool(tokens & authority_terms) or (
        "cost" in tokens and "gate" in tokens
    )
    has_authority_action = bool(tokens & action_terms) or bool(tokens & _AUTHORITY_ACTION_TOKENS)
    return has_authority_term and has_authority_action


def _authority_value_grants(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in _FALSE_STRINGS
    return _truthy(value)


def _stable_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _text(item)
        if not text or text != str(item):
            return []
        out.append(text)
    return out


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY_STRINGS
    return bool(value)


def _is_hash(value: str) -> bool:
    return bool(_HEX64_RE.match(value))


def _strip_hash(value: str) -> str:
    return _text(value).removeprefix("sha256:")


def _hash_or_empty(value: Any) -> str:
    text = _strip_hash(_text(value))
    return text if _is_hash(text) else ""


def _normalized_key(key: str) -> str:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key))
    return "_".join(token for token in re.split(r"[^a-z0-9]+", expanded.lower()) if token)


def _key_tokens(norm_key: str) -> list[str]:
    return [token for token in norm_key.split("_") if token]


def _stable_sha256_json(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _result(
    valid: bool,
    outcome: str,
    reason: str,
    reasons: tuple[str, ...] | list[str] = (),
    *,
    authority_boundary_violation: bool = False,
) -> AlrOutcomeBridgeValidation:
    normalized = tuple(str(item) for item in reasons) or (reason,)
    return AlrOutcomeBridgeValidation(
        valid=valid,
        outcome=outcome,
        reason=reason,
        reasons=normalized,
        authority_boundary_violation=authority_boundary_violation,
    )


if __name__ == "__main__":  # pragma: no cover - exercised by CLI tests
    raise SystemExit(main())
