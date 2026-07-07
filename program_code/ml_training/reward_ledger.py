"""
MODULE_NOTE
模塊用途：AI/ML roadmap 的 reward_ledger_v1 source-only bridge contract。
主要類/函數：RewardLedgerValidation、compute_reward_record_hash、
validate_reward_record、build_reward_record_from_proof_and_mutation、
extract_reward_record。
依賴：僅 Python 標準庫與同目錄 source-only validators；不讀外部狀態、
不連 runtime、不呼叫交易所。
硬邊界：本模塊只把 caller 提供的 ProofPacket 與 Demo mutation envelope
橋接為 append-only reward record；不可授予 promotion、order、probe、
Cost Gate、runtime、live/mainnet authority。
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .demo_mutation_envelope import (
    ENGINE_MODE_DEMO,
    STATUS_COUNTABLE,
    compute_demo_mutation_envelope_hash,
    validate_demo_mutation_envelope,
)
from .proof_packet_contract import (
    PROOF_READY,
    compute_proof_packet_hash,
    validate_proof_packet,
)
from .pit_dataset_manifest import compute_pit_dataset_manifest_hash
from .registry_serving_contract import (
    compute_registry_serving_contract_hash,
    validate_registry_serving_contract,
)


REWARD_LEDGER_FIELD = "reward_ledger"
REWARD_LEDGER_SCHEMA_VERSION = "reward_ledger_v1"

REWARD_RECORD_READY = "reward_record_ready"
REWARD_RECORD_REJECTED = "reward_record_rejected"
PENDING_SCHEMA = "pending_schema"
INVALID = "invalid"

REWARD_KIND_AFTER_COST_REALIZED_DEMO = "after_cost_realized_demo"
REGISTRY_OPTIONAL_REASON_EXECUTION_REWARD = "execution_reward_not_training_contract_bound"

_HEX64_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_TRUTHY_STRINGS = {"1", "true", "yes", "y", "on", "enabled", "grant", "granted"}
_AUTHORITY_TRUE_KEYS = set(
    """
    cost_gate_change cost_gate_change_performed cost_gate_lowered
    cost_gate_lowering_allowed db_migration_allowed db_migration_performed
    db_read_allowed db_read_performed db_write_allowed db_write_performed
    deploy_allowed deploy_performed exchange_contact_performed
    exchange_private_read_performed live_allowed live_authority_granted live_enabled
    live_or_mainnet_performed mainnet_allowed mainnet_enabled mcp_server_started
    order_allowed order_authority_granted order_or_probe_allowed
    order_or_probe_performed private_read_allowed private_read_performed probe_allowed
    probe_authority_granted promotion_allowed promotion_authority_granted
    promotion_enabled runtime_mutation_allowed runtime_mutation_performed
    secret_access_allowed secret_access_performed serving_reload_allowed
    serving_reload_performed symlink_promotion_allowed symlink_promotion_performed
    """.split()
)
_AUTHORITY_KEY_TERMS = tuple(
    "cost cost_gate db deploy exchange live mainnet mcp order private probe "
    "promotion runtime secret serving symlink".split()
)
_AUTHORITY_ACTION_TERMS = tuple(
    "allow allowed author change deploy enable enabled grant granted lower "
    "lowering mutat perform performed reload start started write".split()
)
_AUTHORITY_ACTION_TOKENS = {"read"}
_CONTRACT_BOUND_MARKER_KEYS = {
    "contract_bound",
    "contract_bound_run",
    "registry_required",
}
_NO_AUTHORITY_KEYS = tuple(
    "runtime_mutation db_read db_write db_migration exchange_contact private_read "
    "secret_access order_or_probe cost_gate_change deploy live_or_mainnet promotion "
    "serving_reload symlink_promotion".split()
)
_CANDIDATE_FIELDS = ("candidate_id", "strategy_name", "symbol", "side")
_COST_FIELDS = tuple(
    "maker_fee_bps taker_fee_bps slippage_bps spread_bps funding_bps markout_bps "
    "realized_net_pnl_bps realized_net_pnl_usdt".split()
)


@dataclass(frozen=True)
class RewardLedgerValidation:
    """Reward record 驗證結果；reward_ready 才能進 append-only ledger。"""

    reward_ready: bool
    verdict: str
    reason: str
    reasons: tuple[str, ...]
    append_only: bool = True
    authority_boundary_violation: bool = False


class RewardLedgerError(ValueError):
    """Caller-provided source artifact cannot become reward ledger input."""


def extract_reward_record(mapping: Any) -> Any:
    """只讀 canonical ``reward_ledger`` 欄位，不接受 alias。"""
    if not isinstance(mapping, Mapping):
        return None
    return mapping.get(REWARD_LEDGER_FIELD)


def compute_reward_record_hash(record: Mapping[str, Any]) -> str:
    """對 reward record 做 canonical JSON sha256；頂層 ``record_hash`` 不入 hash。"""
    payload = copy.deepcopy(dict(record))
    payload.pop("record_hash", None)
    return _stable_sha256_json(payload)


def build_reward_record_from_proof_and_mutation(
    *,
    proof_packet: Mapping[str, Any],
    demo_mutation_envelope: Mapping[str, Any],
    effect_window: Mapping[str, Any],
    registry_serving_contract: Mapping[str, Any] | None = None,
    acceptance_report_ref: Mapping[str, Any] | None = None,
    registry_required: bool = True,
    registry_optional_reason: str = "",
) -> dict[str, Any]:
    """從 caller 提供的 source-only artifacts 建立 canonical reward record。"""
    reasons = _source_rejection_reasons(
        proof_packet=proof_packet,
        demo_mutation_envelope=demo_mutation_envelope,
        effect_window=effect_window,
        registry_serving_contract=registry_serving_contract,
        acceptance_report_ref=acceptance_report_ref,
        registry_required=registry_required,
        registry_optional_reason=registry_optional_reason,
    )
    if reasons:
        raise RewardLedgerError(reasons[0])

    proof_hash = _strip_hash(str(proof_packet["proof_packet_hash"]))
    envelope_hash = _strip_hash(str(demo_mutation_envelope["envelope_sha256"]))
    candidate = _mapping(proof_packet["candidate_identity"])
    execution = _mapping(proof_packet["execution_identity"])
    cost = _mapping(proof_packet["cost_identity"])
    controls = _mapping(proof_packet["controls"])
    provenance = _mapping(proof_packet["provenance"])
    pit_manifest = _mapping(provenance["pit_dataset_manifest"])
    registry_hash = (
        _strip_hash(str(registry_serving_contract["contract_hash"]))
        if registry_serving_contract is not None
        else ""
    )
    acceptance_hash = (
        _acceptance_report_hash(acceptance_report_ref)
        if acceptance_report_ref is not None
        else ""
    )

    record: dict[str, Any] = {
        "schema_version": REWARD_LEDGER_SCHEMA_VERSION,
        "record_id": (
            f"reward:{candidate['candidate_id']}:{proof_hash[:16]}:{envelope_hash[:16]}"
        ),
        "append_only": True,
        "verdict": REWARD_RECORD_READY,
        "candidate_identity": {
            "candidate_id": str(candidate["candidate_id"]),
            "strategy_name": str(candidate["strategy_name"]),
            "symbol": str(candidate["symbol"]),
            "side": str(candidate["side"]),
            "context_id": str(candidate["context_id"]),
        },
        "execution_identity": {
            "order_link_id": str(execution["order_link_id"]),
            "entry_context_id": str(execution["entry_context_id"]),
            "exit_context_id": str(execution["exit_context_id"]),
            "fill_ids": list(execution["fill_ids"]),
            "liquidity_role": str(execution["liquidity_role"]).lower(),
        },
        "cost_identity": {field: cost[field] for field in _COST_FIELDS},
        "reward": {
            "reward_kind": REWARD_KIND_AFTER_COST_REALIZED_DEMO,
            "net_pnl_bps": cost["realized_net_pnl_bps"],
            "net_pnl_usdt": cost["realized_net_pnl_usdt"],
            "sample_weight": 1.0,
            "no_fill_reward": False,
            "cleanup_reward": False,
            "dry_run_reward": False,
        },
        "controls": {
            "matched_control_ids": list(controls["matched_control_ids"]),
            "regime_labels": copy.deepcopy(dict(controls["regime_labels"])),
            "oos_split": copy.deepcopy(dict(controls["oos_split"])),
            "proof_exclusions": [],
        },
        "lineage": {
            "proof_packet_hash": proof_hash,
            "mutation_envelope_hash": envelope_hash,
            "pit_dataset_manifest_hash": _strip_hash(str(pit_manifest["manifest_hash"])),
            "registry_serving_contract_hash": registry_hash,
            "registry_required": registry_required,
            "registry_optional_reason": "" if registry_hash else registry_optional_reason,
            "acceptance_report_hash": acceptance_hash,
            "code_commit": str(provenance["code_commit"]),
            "rust_build_sha": str(provenance["rust_build_sha"]),
        },
        "mutation": {
            "envelope_id": str(demo_mutation_envelope["envelope_id"]),
            "source_proposal_or_recommendation_id": str(
                demo_mutation_envelope["source_proposal_or_recommendation_id"]
            ),
            "source_payload_hash": _strip_hash(
                str(demo_mutation_envelope["source_payload_hash"])
            ),
            "application_type": str(demo_mutation_envelope["application_type"]),
            "target": str(demo_mutation_envelope["target"]),
            "bounded_delta_hash": _stable_sha256_json(
                demo_mutation_envelope["bounded_delta"]
            ),
        },
        "effect_window": copy.deepcopy(dict(effect_window)),
        "source_artifacts": {
            "proof_packet": copy.deepcopy(dict(proof_packet)),
            "demo_mutation_envelope": copy.deepcopy(dict(demo_mutation_envelope)),
            "registry_serving_contract": (
                copy.deepcopy(dict(registry_serving_contract))
                if registry_serving_contract is not None
                else None
            ),
            "acceptance_report_ref": (
                copy.deepcopy(dict(acceptance_report_ref))
                if acceptance_report_ref is not None
                else None
            ),
        },
        "no_authority": {key: False for key in _NO_AUTHORITY_KEYS},
    }
    record["record_hash"] = compute_reward_record_hash(record)
    validation = validate_reward_record(record)
    if not validation.reward_ready:
        raise RewardLedgerError(validation.reason)
    return record


def validate_reward_record(record: Any) -> RewardLedgerValidation:
    """驗證 ``reward_ledger_v1`` 是否可作 append-only source ledger record。"""
    if record is None:
        return _result(PENDING_SCHEMA, "reward_record_missing")
    if not isinstance(record, Mapping):
        return _result(INVALID, "reward_record_not_mapping")

    authority_violations = _authority_violations(record)
    if authority_violations:
        return _result(
            INVALID,
            f"authority_boundary_violation:{authority_violations[0]}",
            tuple(f"authority_boundary_violation:{item}" for item in authority_violations),
            authority_boundary_violation=True,
        )

    reasons: list[str] = []
    if _text(record.get("schema_version")) != REWARD_LEDGER_SCHEMA_VERSION:
        reasons.append("schema_version_unknown")
    if record.get("append_only") is not True:
        reasons.append("append_only_not_true")
    if _text(record.get("verdict")) != REWARD_RECORD_READY:
        reasons.append("verdict_not_reward_record_ready")
    if not _text(record.get("record_id")):
        reasons.append("record_id_missing")

    candidate = _mapping(record.get("candidate_identity"))
    execution = _mapping(record.get("execution_identity"))
    cost = _mapping(record.get("cost_identity"))
    reward = _mapping(record.get("reward"))
    controls = _mapping(record.get("controls"))
    lineage = _mapping(record.get("lineage"))
    mutation = _mapping(record.get("mutation"))
    effect_window = _mapping(record.get("effect_window"))
    no_authority = _mapping(record.get("no_authority"))

    reasons.extend(_candidate_reasons(candidate))
    reasons.extend(_execution_reasons(candidate, execution))
    reasons.extend(_cost_reasons(cost))
    reasons.extend(_reward_reasons(cost, reward))
    reasons.extend(_controls_reasons(controls))
    reasons.extend(_lineage_reasons(lineage))
    reasons.extend(_mutation_reasons(mutation))
    reasons.extend(_effect_window_reasons(effect_window))
    reasons.extend(_source_artifact_reasons(record, lineage))
    reasons.extend(_no_authority_reasons(no_authority))

    record_hash = _text(record.get("record_hash"))
    if not record_hash:
        reasons.append("record_hash_missing")
    elif not _is_hash(record_hash):
        reasons.append("record_hash_malformed")
    elif not reasons:
        try:
            computed_hash = compute_reward_record_hash(record)
        except (TypeError, ValueError):
            reasons.append("record_hash_uncomputable")
        else:
            if _strip_hash(record_hash) != computed_hash:
                reasons.append("record_hash_mismatch")

    if reasons:
        return _result(_failure_verdict(reasons), reasons[0], reasons)
    return _result(REWARD_RECORD_READY, "ok", ())


def dedupe_reward_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """以 ``record_id`` 做 source-only batch 去重；不代表持久化唯一性。"""
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for record in records:
        record_id = _text(record.get("record_id")) if isinstance(record, Mapping) else ""
        if record_id and record_id not in seen:
            seen.add(record_id)
            deduped.append(copy.deepcopy(dict(record)))
    return deduped


def validate_reward_batch(records: Any) -> RewardLedgerValidation:
    """驗證 source-only batch 內每筆 ready 且 ``record_id`` 無重複。"""
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        return _result(INVALID, "reward_batch_not_sequence")
    seen: set[str] = set()
    reasons: list[str] = []
    for index, record in enumerate(records):
        validation = validate_reward_record(record)
        if not validation.reward_ready:
            reasons.append(f"record[{index}]:{validation.reason}")
            if validation.authority_boundary_violation:
                return _result(INVALID, reasons[0], reasons, authority_boundary_violation=True)
        record_id = _text(record.get("record_id")) if isinstance(record, Mapping) else ""
        if record_id in seen:
            reasons.append(f"record[{index}]:record_id_duplicate")
        seen.add(record_id)
    return _result(INVALID, reasons[0], reasons) if reasons else _result(
        REWARD_RECORD_READY, "ok", ()
    )


def _source_rejection_reasons(
    *,
    proof_packet: Mapping[str, Any],
    demo_mutation_envelope: Mapping[str, Any],
    effect_window: Mapping[str, Any],
    registry_serving_contract: Mapping[str, Any] | None,
    acceptance_report_ref: Mapping[str, Any] | None,
    registry_required: bool,
    registry_optional_reason: str,
) -> list[str]:
    reasons: list[str] = []
    if not isinstance(proof_packet, Mapping):
        return ["proof_packet_not_mapping"]
    if not isinstance(demo_mutation_envelope, Mapping):
        return ["demo_mutation_envelope_not_mapping"]
    if not isinstance(effect_window, Mapping):
        return ["effect_window_not_mapping"]
    if registry_serving_contract is not None and not isinstance(
        registry_serving_contract, Mapping
    ):
        return ["registry_serving_contract_not_mapping"]
    if acceptance_report_ref is not None and not isinstance(acceptance_report_ref, Mapping):
        return ["acceptance_report_ref_not_mapping"]
    if not isinstance(registry_required, bool):
        return ["registry_required_not_bool"]
    if not registry_required and registry_optional_reason != REGISTRY_OPTIONAL_REASON_EXECUTION_REWARD:
        return ["registry_optional_reason_missing_or_unknown"]

    for name, artifact in (
        ("proof_packet", proof_packet),
        ("demo_mutation_envelope", demo_mutation_envelope),
        ("effect_window", effect_window),
        ("registry_serving_contract", registry_serving_contract),
        ("acceptance_report_ref", acceptance_report_ref),
    ):
        if artifact is not None:
            violations = _authority_violations(artifact)
            reasons.extend(f"{name}:authority_boundary_violation:{item}" for item in violations)

    if not registry_required:
        contract_bound_markers = _contract_bound_markers(
            {
                "proof_packet": proof_packet,
                "demo_mutation_envelope": demo_mutation_envelope,
                "effect_window": effect_window,
                "registry_serving_contract": registry_serving_contract,
                "acceptance_report_ref": acceptance_report_ref,
            }
        )
        reasons.extend(
            f"registry_optional_source_contract_bound:{marker}"
            for marker in contract_bound_markers
        )

    proof_validation = validate_proof_packet(proof_packet)
    if not proof_validation.proof_ready or proof_validation.verdict != PROOF_READY:
        if getattr(proof_validation, "no_fill_blocker", False):
            reasons.append("proof_packet_no_matched_fills")
        else:
            reasons.append(f"proof_packet_not_proof_ready:{proof_validation.reason}")

    envelope_validation = validate_demo_mutation_envelope(demo_mutation_envelope)
    if (
        not envelope_validation.valid
        or envelope_validation.status != STATUS_COUNTABLE
        or envelope_validation.effective_learning_countable is not True
    ):
        reasons.append(f"demo_mutation_envelope_not_countable:{envelope_validation.reason}")

    proof_hash = _text(proof_packet.get("proof_packet_hash"))
    if not _is_hash(proof_hash):
        reasons.append("proof_packet_hash_missing_or_malformed")
    elif proof_hash != compute_proof_packet_hash(proof_packet):
        reasons.append("proof_packet_hash_mismatch")

    envelope_hash = _text(demo_mutation_envelope.get("envelope_sha256"))
    if not _is_hash(envelope_hash):
        reasons.append("mutation_envelope_hash_missing_or_malformed")
    elif envelope_hash != compute_demo_mutation_envelope_hash(demo_mutation_envelope):
        reasons.append("mutation_envelope_hash_mismatch")

    reasons.extend(_proof_linkage_reasons(proof_packet, demo_mutation_envelope))
    reasons.extend(_source_candidate_match_reasons(proof_packet, demo_mutation_envelope))
    reasons.extend(_effect_window_reasons(effect_window))
    reasons.extend(_pit_lineage_source_reasons(proof_packet))

    if registry_serving_contract is not None:
        registry_validation = validate_registry_serving_contract(registry_serving_contract)
        if not registry_validation.advisory_ready:
            reasons.append(f"registry_serving_contract_not_ready:{registry_validation.reason}")
        elif _strip_hash(str(registry_serving_contract.get("contract_hash", ""))) != (
            compute_registry_serving_contract_hash(registry_serving_contract)
        ):
            reasons.append("registry_serving_contract_hash_mismatch")

    if registry_required and registry_serving_contract is None:
        reasons.append("registry_lineage_missing")

    if acceptance_report_ref is not None:
        try:
            _acceptance_report_hash(acceptance_report_ref)
        except ValueError as exc:
            reasons.append(str(exc))

    return reasons


def _proof_linkage_reasons(
    proof_packet: Mapping[str, Any],
    envelope: Mapping[str, Any],
) -> list[str]:
    linkage = _mapping(envelope.get("proof_linkage"))
    proof_hash = _strip_hash(_text(proof_packet.get("proof_packet_hash")))
    linked_hash = _strip_hash(_text(linkage.get("proof_packet_hash")))
    if not linkage:
        return ["proof_linkage_missing"]
    if linkage.get("valid") is not True:
        return ["proof_linkage_not_valid"]
    if not linked_hash:
        return ["proof_linkage_proof_packet_hash_missing"]
    if linked_hash != proof_hash:
        return ["proof_linkage_proof_packet_hash_mismatch"]
    return []


def _source_candidate_match_reasons(
    proof_packet: Mapping[str, Any],
    envelope: Mapping[str, Any],
) -> list[str]:
    candidate = _mapping(proof_packet.get("candidate_identity"))
    reasons: list[str] = []
    if _text(envelope.get("engine_mode")) != ENGINE_MODE_DEMO:
        reasons.append("mutation_engine_mode_not_demo")
    for source_path, source in _candidate_sources(envelope):
        for field in _CANDIDATE_FIELDS:
            source_value = _text(source.get(field))
            candidate_value = _text(candidate.get(field))
            if source_value and candidate_value and source_value != candidate_value:
                reasons.append(f"{source_path}_{field}_mismatch")
    return reasons


def _candidate_sources(envelope: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    sources: list[tuple[str, Mapping[str, Any]]] = []
    for key in ("source", "source_payload", "metadata"):
        value = envelope.get(key)
        if isinstance(value, Mapping):
            sources.append((key, value))
    return sources


def _pit_lineage_source_reasons(proof_packet: Mapping[str, Any]) -> list[str]:
    provenance = _mapping(proof_packet.get("provenance"))
    pit_manifest = _mapping(provenance.get("pit_dataset_manifest"))
    if not pit_manifest:
        return ["pit_dataset_manifest_missing"]
    manifest_hash = _text(pit_manifest.get("manifest_hash"))
    if not _is_hash(manifest_hash):
        return ["pit_dataset_manifest_hash_missing_or_malformed"]
    return []


def _acceptance_report_hash(acceptance_report_ref: Mapping[str, Any]) -> str:
    claimed_hash = _text(
        acceptance_report_ref.get("acceptance_report_hash")
        or acceptance_report_ref.get("report_hash")
    )
    payload = copy.deepcopy(dict(acceptance_report_ref))
    payload.pop("acceptance_report_hash", None)
    payload.pop("report_hash", None)
    computed = _stable_sha256_json(payload)
    if claimed_hash and _strip_hash(claimed_hash) != computed:
        raise ValueError("acceptance_report_hash_mismatch")
    return computed


def _candidate_reasons(candidate: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in (*_CANDIDATE_FIELDS, "context_id"):
        if not _text(candidate.get(field)):
            reasons.append(f"candidate_identity_{field}_missing")
    candidate_id = _text(candidate.get("candidate_id"))
    if candidate_id.count("|") >= 2:
        parts = candidate_id.split("|")
        if _text(candidate.get("strategy_name")) and parts[0] != candidate["strategy_name"]:
            reasons.append("candidate_identity_strategy_mismatch")
        if _text(candidate.get("symbol")) and parts[1] != candidate["symbol"]:
            reasons.append("candidate_identity_symbol_mismatch")
        if _text(candidate.get("side")) and parts[2] != candidate["side"]:
            reasons.append("candidate_identity_side_mismatch")
    return reasons


def _execution_reasons(
    candidate: Mapping[str, Any],
    execution: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    for field in ("order_link_id", "entry_context_id", "exit_context_id", "liquidity_role"):
        if not _text(execution.get(field)):
            reasons.append(f"execution_identity_{field}_missing")
    fill_ids = execution.get("fill_ids")
    if not isinstance(fill_ids, list) or not fill_ids:
        reasons.append("execution_identity_fill_ids_missing")
    elif any(not _text(item) for item in fill_ids):
        reasons.append("execution_identity_fill_ids_invalid")
    elif len(set(str(item) for item in fill_ids)) != len(fill_ids):
        reasons.append("execution_identity_fill_ids_duplicate")
    if _text(candidate.get("context_id")) != _text(execution.get("entry_context_id")):
        reasons.append("execution_identity_entry_context_id_mismatch")
    return reasons


def _cost_reasons(cost: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in _COST_FIELDS:
        if _number(cost.get(field)) is None:
            reasons.append(f"cost_identity_{field}_missing_or_nonfinite")
    return reasons


def _reward_reasons(cost: Mapping[str, Any], reward: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if _text(reward.get("reward_kind")) != REWARD_KIND_AFTER_COST_REALIZED_DEMO:
        reasons.append("reward_kind_unknown")
    if reward.get("no_fill_reward") is not False:
        reasons.append("reward_no_fill_reward_not_false")
    if reward.get("cleanup_reward") is not False:
        reasons.append("reward_cleanup_reward_not_false")
    if reward.get("dry_run_reward") is not False:
        reasons.append("reward_dry_run_reward_not_false")
    if _number(reward.get("sample_weight")) is None or float(reward["sample_weight"]) <= 0:
        reasons.append("reward_sample_weight_invalid")
    for reward_field, cost_field in (
        ("net_pnl_bps", "realized_net_pnl_bps"),
        ("net_pnl_usdt", "realized_net_pnl_usdt"),
    ):
        if _number(reward.get(reward_field)) is None:
            reasons.append(f"reward_{reward_field}_missing_or_nonfinite")
        elif _number(cost.get(cost_field)) is not None and float(reward[reward_field]) != float(
            cost[cost_field]
        ):
            reasons.append(f"reward_{reward_field}_cost_identity_mismatch")
    return reasons


def _controls_reasons(controls: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    matched_control_ids = controls.get("matched_control_ids")
    if not isinstance(matched_control_ids, list) or not matched_control_ids:
        reasons.append("controls_matched_control_ids_missing")
    elif len(set(str(item) for item in matched_control_ids)) != len(matched_control_ids):
        reasons.append("controls_matched_control_ids_duplicate")
    if not isinstance(controls.get("regime_labels"), Mapping) or not controls["regime_labels"]:
        reasons.append("controls_regime_labels_missing")
    if not isinstance(controls.get("oos_split"), Mapping) or not controls["oos_split"]:
        reasons.append("controls_oos_split_missing")
    if controls.get("proof_exclusions") not in ([], (), None):
        reasons.append("controls_proof_exclusions_present")
    return reasons


def _lineage_reasons(lineage: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in (
        "proof_packet_hash",
        "mutation_envelope_hash",
        "pit_dataset_manifest_hash",
    ):
        if not _is_hash(_text(lineage.get(field))):
            reasons.append(f"lineage_{field}_missing_or_malformed")
    registry_hash = _text(lineage.get("registry_serving_contract_hash"))
    if not isinstance(lineage.get("registry_required"), bool):
        reasons.append("lineage_registry_required_missing_or_not_bool")
    if registry_hash and not _is_hash(registry_hash):
        reasons.append("lineage_registry_serving_contract_hash_malformed")
    if not registry_hash and (
        _text(lineage.get("registry_optional_reason"))
        != REGISTRY_OPTIONAL_REASON_EXECUTION_REWARD
    ):
        reasons.append("lineage_registry_optional_reason_missing")
    acceptance_hash = _text(lineage.get("acceptance_report_hash"))
    if acceptance_hash and not _is_hash(acceptance_hash):
        reasons.append("lineage_acceptance_report_hash_malformed")
    for field in ("code_commit", "rust_build_sha"):
        if not _text(lineage.get(field)):
            reasons.append(f"lineage_{field}_missing")
    return reasons


def _source_artifact_reasons(record: Mapping[str, Any], lineage: Mapping[str, Any]) -> list[str]:
    artifacts = _mapping(record.get("source_artifacts"))
    reasons: list[str] = []
    proof_packet = _mapping(artifacts.get("proof_packet"))
    envelope = _mapping(artifacts.get("demo_mutation_envelope"))
    registry = artifacts.get("registry_serving_contract")
    acceptance = artifacts.get("acceptance_report_ref")

    if not proof_packet:
        reasons.append("source_artifacts_proof_packet_missing")
    if not envelope:
        reasons.append("source_artifacts_demo_mutation_envelope_missing")
    if reasons:
        return reasons

    reasons.extend(
        _source_rejection_reasons(
            proof_packet=proof_packet,
            demo_mutation_envelope=envelope,
            effect_window=_mapping(record.get("effect_window")),
            registry_serving_contract=registry if isinstance(registry, Mapping) else None,
            acceptance_report_ref=acceptance if isinstance(acceptance, Mapping) else None,
            registry_required=lineage.get("registry_required") is True,
            registry_optional_reason=_text(lineage.get("registry_optional_reason")),
        )
    )

    proof_hash = compute_proof_packet_hash(proof_packet)
    if _strip_hash(_text(lineage.get("proof_packet_hash"))) != proof_hash:
        reasons.append("lineage_proof_packet_hash_source_mismatch")
    if _strip_hash(_text(proof_packet.get("proof_packet_hash"))) != proof_hash:
        reasons.append("source_artifacts_proof_packet_hash_mismatch")

    envelope_hash = compute_demo_mutation_envelope_hash(envelope)
    if _strip_hash(_text(lineage.get("mutation_envelope_hash"))) != envelope_hash:
        reasons.append("lineage_mutation_envelope_hash_source_mismatch")
    if _strip_hash(_text(envelope.get("envelope_sha256"))) != envelope_hash:
        reasons.append("source_artifacts_demo_mutation_envelope_hash_mismatch")

    pit_manifest = _mapping(_mapping(proof_packet.get("provenance")).get("pit_dataset_manifest"))
    if pit_manifest:
        pit_hash = compute_pit_dataset_manifest_hash(pit_manifest)
        if _strip_hash(_text(lineage.get("pit_dataset_manifest_hash"))) != pit_hash:
            reasons.append("lineage_pit_dataset_manifest_hash_source_mismatch")
        if _strip_hash(_text(pit_manifest.get("manifest_hash"))) != pit_hash:
            reasons.append("source_artifacts_pit_dataset_manifest_hash_mismatch")

    if _text(lineage.get("registry_serving_contract_hash")):
        if not isinstance(registry, Mapping):
            reasons.append("source_artifacts_registry_serving_contract_missing")
        else:
            registry_hash = compute_registry_serving_contract_hash(registry)
            if _strip_hash(_text(lineage.get("registry_serving_contract_hash"))) != registry_hash:
                reasons.append("lineage_registry_serving_contract_hash_source_mismatch")
            if _strip_hash(_text(registry.get("contract_hash"))) != registry_hash:
                reasons.append("source_artifacts_registry_serving_contract_hash_mismatch")

    if _text(lineage.get("acceptance_report_hash")):
        if not isinstance(acceptance, Mapping):
            reasons.append("source_artifacts_acceptance_report_ref_missing")
        else:
            try:
                acceptance_hash = _acceptance_report_hash(acceptance)
            except ValueError as exc:
                reasons.append(str(exc))
            else:
                if _strip_hash(_text(lineage.get("acceptance_report_hash"))) != acceptance_hash:
                    reasons.append("lineage_acceptance_report_hash_source_mismatch")
    return reasons


def _mutation_reasons(mutation: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in (
        "envelope_id",
        "source_proposal_or_recommendation_id",
        "source_payload_hash",
        "application_type",
        "target",
        "bounded_delta_hash",
    ):
        if not _text(mutation.get(field)):
            reasons.append(f"mutation_{field}_missing")
    for field in ("source_payload_hash", "bounded_delta_hash"):
        if _text(mutation.get(field)) and not _is_hash(_text(mutation.get(field))):
            reasons.append(f"mutation_{field}_malformed")
    return reasons


def _effect_window_reasons(effect_window: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in ("window_id", "start_ts", "end_ts", "window_source"):
        if not _text(effect_window.get(field)):
            reasons.append(f"effect_window_{field}_missing")
    if effect_window.get("point_in_time") is not True:
        reasons.append("effect_window_point_in_time_not_true")
    count = _int(effect_window.get("observation_count"))
    if count is None or count <= 0:
        reasons.append("effect_window_observation_count_invalid")
    start = _parse_timestamp(_text(effect_window.get("start_ts")))
    end = _parse_timestamp(_text(effect_window.get("end_ts")))
    if start is None:
        reasons.append("effect_window_start_ts_invalid")
    if end is None:
        reasons.append("effect_window_end_ts_invalid")
    if start is not None and end is not None and not start < end:
        reasons.append("effect_window_not_closed_forward")
    return reasons


def _no_authority_reasons(no_authority: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for key in _NO_AUTHORITY_KEYS:
        if key not in no_authority:
            reasons.append(f"no_authority_{key}_missing")
        elif no_authority.get(key) is not False:
            reasons.append(f"no_authority_{key}_not_false")
    return reasons


def _authority_violations(value: Any, path: str = "$") -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            norm = _normalized_key(key_text)
            child_path = f"{path}.{key_text}"
            if not norm.startswith(("no_", "not_")):
                if _is_authority_expansion_key(norm) and _truthy(child):
                    violations.append(child_path)
            violations.extend(_authority_violations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_authority_violations(child, f"{path}[{index}]"))
    return sorted(set(violations))


def _contract_bound_markers(value: Any, path: str = "$") -> list[str]:
    markers: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if _normalized_key(key_text) in _CONTRACT_BOUND_MARKER_KEYS and _truthy(child):
                markers.append(child_path)
            markers.extend(_contract_bound_markers(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            markers.extend(_contract_bound_markers(child, f"{path}[{index}]"))
    return sorted(set(markers))


def _is_authority_expansion_key(norm_key: str) -> bool:
    if norm_key in _AUTHORITY_TRUE_KEYS:
        return True
    if norm_key in _AUTHORITY_KEY_TERMS:
        return True
    tokens = set(_key_tokens(norm_key))
    has_authority_term = any(term in norm_key for term in _AUTHORITY_KEY_TERMS)
    has_authority_action = any(
        action in norm_key for action in _AUTHORITY_ACTION_TERMS
    ) or bool(tokens & _AUTHORITY_ACTION_TOKENS)
    return has_authority_term and has_authority_action


def _failure_verdict(reasons: list[str]) -> str:
    if any(reason.startswith("schema_version") or "_missing" in reason for reason in reasons):
        return PENDING_SCHEMA
    return INVALID


def _result(
    verdict: str,
    reason: str,
    reasons: tuple[str, ...] | list[str] = (),
    *,
    authority_boundary_violation: bool = False,
) -> RewardLedgerValidation:
    normalized = tuple(str(item) for item in reasons) or (reason,)
    return RewardLedgerValidation(
        reward_ready=verdict == REWARD_RECORD_READY and reason == "ok",
        verdict=verdict,
        reason=reason,
        reasons=normalized,
        append_only=True,
        authority_boundary_violation=authority_boundary_violation,
    )


def _stable_sha256_json(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY_STRINGS
    return False


def _is_hash(value: str) -> bool:
    return bool(_HEX64_RE.match(value))


def _strip_hash(value: str) -> str:
    text = _text(value)
    return text.removeprefix("sha256:")


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalized_key(key: str) -> str:
    return "_".join(_key_tokens(key))


def _key_tokens(key: str) -> list[str]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key))
    return [token for token in re.split(r"[^a-z0-9]+", expanded.lower()) if token]
