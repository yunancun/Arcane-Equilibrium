"""
MODULE_NOTE
模塊用途：AI/ML roadmap 的 proof_packet_v1 source-only contract。
主要類/函數：ProofPacketValidation、validate_proof_packet、
compute_proof_packet_hash、extract_proof_packet。
依賴：僅 Python 標準庫；不讀 DB、不連 runtime、不呼叫交易所。
硬邊界：ProofPacket 只驗證 candidate-matched after-cost outcome 或明確
no-fill blocker；不可授予 promotion、order、probe、Cost Gate、runtime、live
authority。
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


PROOF_PACKET_FIELD = "proof_packet"
PROOF_PACKET_SCHEMA_VERSION = "proof_packet_v1"

PROOF_READY = "proof_ready"
NO_MATCHED_FILLS = "no_matched_fills"
RESEARCH_ONLY = "research_only"
PENDING_SCHEMA = "pending_schema"
INVALID = "invalid"

_ALLOWED_VERDICTS = {
    PROOF_READY,
    NO_MATCHED_FILLS,
    RESEARCH_ONLY,
    PENDING_SCHEMA,
    INVALID,
}
_ALLOWED_SIDES = {"Buy", "Sell", "Long", "Short"}
_ALLOWED_LIQUIDITY_ROLES = {"maker", "taker", "mixed"}
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")
_SYMBOL_RE = re.compile(r"^[A-Z0-9:_-]+$")

_COST_FIELDS = (
    "maker_fee_bps",
    "taker_fee_bps",
    "slippage_bps",
    "spread_bps",
    "funding_bps",
    "markout_bps",
    "realized_net_pnl_bps",
    "realized_net_pnl_usdt",
)
_NONNEGATIVE_COST_FIELDS = {"maker_fee_bps", "taker_fee_bps", "spread_bps"}

_AUTHORITY_TRUE_KEYS = {
    "cost_gate_change_performed",
    "cost_gate_lowering_performed",
    "db_write_performed",
    "global_cost_gate_lowering_recommended",
    "live_authority_granted",
    "live_or_mainnet_performed",
    "mcp_server_started",
    "order_authority_granted",
    "private_read_performed",
    "probe_authority_granted",
    "promotion_authority_granted",
    "runtime_mutation_performed",
    "secret_access_performed",
}
_TRUTHY_STRINGS = {"1", "true", "yes", "y", "on", "enabled", "grant", "granted"}

_PROOF_EXCLUSION_KEYS = {
    "cleanup_fill",
    "cleanup_or_risk_reduction_fill",
    "proof_excluded",
    "unattributed_fill",
}
_PROOF_EXCLUSION_TEXT_KEYS = {
    "outcome_source",
    "proof_exclusion_reason",
}
_PROOF_EXCLUSION_TEXT_TOKENS = ("cleanup", "proof_excluded", "unattributed")

_NO_FILL_LABEL_KEYS = {
    "label",
    "learning_label",
    "reward",
    "realized_net_pnl_bps",
    "realized_net_pnl_usdt",
    "training_label",
}


@dataclass(frozen=True)
class ProofPacketValidation:
    """ProofPacket 驗證結果；caller 只能用 proof_ready 放行下游 proof gate。"""

    proof_ready: bool
    verdict: str
    reason: str
    reasons: tuple[str, ...]
    no_fill_blocker: bool = False
    authority_boundary_violation: bool = False


def extract_proof_packet(mapping: Any) -> Any:
    """只讀 canonical ``proof_packet`` 欄位，不接受 alias。"""
    if not isinstance(mapping, Mapping):
        return None
    return mapping.get(PROOF_PACKET_FIELD)


def compute_proof_packet_hash(packet: Mapping[str, Any]) -> str:
    """對 packet 做 canonical JSON sha256；頂層 ``proof_packet_hash`` 不入 hash。"""
    payload = copy.deepcopy(dict(packet))
    payload.pop("proof_packet_hash", None)
    return _canonical_sha256(payload)


def validate_proof_packet(packet: Any) -> ProofPacketValidation:
    """驗證 ``proof_packet_v1`` 是否可作 candidate-matched proof input。

    本函數不證明 DB / exchange / runtime 事實，只驗證 caller 已提供的
    artifact contract 是否完整、可重建、且沒有 authority expansion。
    """
    if packet is None:
        return _result(PENDING_SCHEMA, "proof_packet_missing")
    if not isinstance(packet, Mapping):
        return _result(INVALID, "proof_packet_not_mapping")

    authority_violations = _authority_violations(packet)
    if authority_violations:
        return _result(
            INVALID,
            f"authority_boundary_violation:{authority_violations[0]}",
            tuple(f"authority_boundary_violation:{item}" for item in authority_violations),
            authority_boundary_violation=True,
        )

    if _truthy(packet.get("promotion_ready")):
        return _result(INVALID, "promotion_ready_field_not_allowed")

    schema_version = _text(packet.get("schema_version"))
    if schema_version != PROOF_PACKET_SCHEMA_VERSION:
        return _result(PENDING_SCHEMA, "schema_version_unknown")

    verdict = _text(packet.get("verdict"))
    if verdict not in _ALLOWED_VERDICTS:
        return _result(INVALID, "verdict_unknown")

    reasons: list[str] = []
    reasons.extend(_validate_candidate_identity(packet.get("candidate_identity")))
    reasons.extend(_validate_provenance(packet.get("provenance")))

    if verdict == PROOF_READY:
        reasons.extend(_validate_ready_packet(packet))
    elif verdict == NO_MATCHED_FILLS:
        reasons.extend(_validate_no_fill_packet(packet))
    else:
        reasons.append(f"verdict_not_proof_ready:{verdict}")

    packet_hash = _text(packet.get("proof_packet_hash"))
    if not packet_hash:
        reasons.append("proof_packet_hash_missing")
    elif not _is_hex64(packet_hash):
        reasons.append("proof_packet_hash_malformed")
    elif not reasons and packet_hash != compute_proof_packet_hash(packet):
        reasons.append("proof_packet_hash_mismatch")

    if reasons:
        return _result(_failure_verdict(reasons, verdict), reasons[0], reasons)

    if verdict == NO_MATCHED_FILLS:
        return _result(
            NO_MATCHED_FILLS,
            "ok_no_matched_fills",
            (),
            no_fill_blocker=True,
        )
    return _result(PROOF_READY, "ok", ())


def _validate_ready_packet(packet: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    candidate = _mapping(packet.get("candidate_identity"))
    execution = _mapping(packet.get("execution_identity"))
    cost = _mapping(packet.get("cost_identity"))
    controls = _mapping(packet.get("controls"))

    if not execution:
        reasons.append("execution_identity_missing")
    else:
        reasons.extend(_validate_execution_identity(candidate, execution))

    if not cost:
        reasons.append("cost_identity_missing")
    else:
        reasons.extend(_validate_cost_identity(cost))

    if not controls:
        reasons.append("controls_missing")
    else:
        reasons.extend(_validate_controls(controls))

    exclusion_reasons = _proof_exclusion_reasons(packet)
    if exclusion_reasons:
        reasons.extend(exclusion_reasons)

    return reasons


def _validate_no_fill_packet(packet: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    diagnosis = _mapping(packet.get("no_fill_diagnosis"))
    execution = _mapping(packet.get("execution_identity"))

    if not diagnosis:
        reasons.append("no_fill_diagnosis_missing")
    else:
        for field in ("blocker_code", "observed_window_start", "observed_window_end"):
            if not _text(diagnosis.get(field)):
                reasons.append(f"no_fill_diagnosis_{field}_missing")
        if _present(diagnosis.get("attempted_order_count")):
            count = _int(diagnosis.get("attempted_order_count"))
            if count is None or count < 0:
                reasons.append("no_fill_diagnosis_attempted_order_count_invalid")

    if _fill_ids(execution):
        reasons.append("no_fill_packet_has_fill_ids")
    if packet.get("cost_identity") is not None:
        reasons.append("no_fill_packet_has_cost_identity")
    for key in _NO_FILL_LABEL_KEYS:
        if _present(packet.get(key)):
            reasons.append(f"no_fill_packet_has_label:{key}")
    return reasons


def _validate_candidate_identity(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return ["candidate_identity_missing"]
    reasons: list[str] = []
    candidate_id = _text(value.get("candidate_id"))
    strategy = _text(value.get("strategy_name"))
    symbol = _text(value.get("symbol"))
    side = _text(value.get("side"))
    context_id = _text(value.get("context_id"))
    for field, field_value in (
        ("candidate_id", candidate_id),
        ("strategy_name", strategy),
        ("symbol", symbol),
        ("side", side),
        ("context_id", context_id),
    ):
        if not field_value:
            reasons.append(f"candidate_identity_{field}_missing")
    if symbol and (symbol != symbol.upper() or not _SYMBOL_RE.match(symbol)):
        reasons.append("candidate_identity_symbol_malformed")
    if side and side not in _ALLOWED_SIDES:
        reasons.append("candidate_identity_side_unknown")
    if candidate_id.count("|") >= 2:
        parts = candidate_id.split("|")
        if strategy and parts[0] != strategy:
            reasons.append("candidate_identity_strategy_mismatch")
        if symbol and parts[1].upper() != symbol:
            reasons.append("candidate_identity_symbol_mismatch")
        if side and parts[2] != side:
            reasons.append("candidate_identity_side_mismatch")
    return reasons


def _validate_execution_identity(
    candidate: Mapping[str, Any],
    execution: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if execution.get("candidate_matched") is not True:
        reasons.append("execution_identity_candidate_matched_not_true")
    for field in ("order_link_id", "entry_context_id", "exit_context_id"):
        if not _text(execution.get(field)):
            reasons.append(f"execution_identity_{field}_missing")
    fill_ids = _fill_ids(execution)
    if not fill_ids:
        reasons.append("execution_identity_fill_ids_missing")
    elif len(set(fill_ids)) != len(fill_ids):
        reasons.append("execution_identity_fill_ids_duplicate")
    liquidity_role = _text(execution.get("liquidity_role")).lower()
    if liquidity_role not in _ALLOWED_LIQUIDITY_ROLES:
        reasons.append("execution_identity_liquidity_role_unknown")
    if _text(candidate.get("context_id")) and _text(execution.get("entry_context_id")):
        if _text(candidate.get("context_id")) != _text(execution.get("entry_context_id")):
            reasons.append("execution_identity_entry_context_id_mismatch")
    return reasons


def _validate_cost_identity(cost: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in _COST_FIELDS:
        value = _number(cost.get(field))
        if value is None:
            reasons.append(f"cost_identity_{field}_missing_or_nonfinite")
            continue
        if field in _NONNEGATIVE_COST_FIELDS and value < 0:
            reasons.append(f"cost_identity_{field}_negative")
    return reasons


def _validate_controls(controls: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    control_ids = _stable_text_list(controls.get("matched_control_ids"))
    if not control_ids:
        reasons.append("controls_matched_control_ids_missing")
    elif len(set(control_ids)) != len(control_ids):
        reasons.append("controls_matched_control_ids_duplicate")

    regime_labels = controls.get("regime_labels")
    if not isinstance(regime_labels, Mapping) or not regime_labels:
        reasons.append("controls_regime_labels_missing")

    oos_split = _mapping(controls.get("oos_split"))
    if not oos_split:
        reasons.append("controls_oos_split_missing")
    else:
        split_hash = _text(oos_split.get("split_hash"))
        split_id = _text(oos_split.get("split_id"))
        if not split_hash and not split_id:
            reasons.append("controls_oos_split_ref_missing")
        if split_hash and not _is_stable_hash(split_hash):
            reasons.append("controls_oos_split_hash_malformed")

    proof_exclusions = controls.get("proof_exclusions")
    if proof_exclusions not in (None, [], (), {}):
        reasons.append("controls_proof_exclusions_present")
    return reasons


def _validate_provenance(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return ["provenance_missing"]
    reasons: list[str] = []
    for field in ("code_commit", "rust_build_sha"):
        if not _is_stable_ref(_text(value.get(field))):
            reasons.append(f"provenance_{field}_missing_or_malformed")

    source_hashes = _mapping(value.get("source_hashes"))
    input_hashes = _mapping(value.get("input_artifact_hashes"))
    if not source_hashes:
        reasons.append("provenance_source_hashes_missing")
    else:
        reasons.extend(_validate_hash_mapping(source_hashes, "source_hashes"))
    if not input_hashes:
        reasons.append("provenance_input_artifact_hashes_missing")
    else:
        reasons.extend(_validate_hash_mapping(input_hashes, "input_artifact_hashes"))
    return reasons


def _validate_hash_mapping(mapping: Mapping[str, Any], prefix: str) -> list[str]:
    reasons: list[str] = []
    for key, value in mapping.items():
        if not _text(key):
            reasons.append(f"provenance_{prefix}_key_missing")
        if not _is_stable_hash(_text(value)):
            reasons.append(f"provenance_{prefix}_{key}_hash_malformed")
    return reasons


def _proof_exclusion_reasons(packet: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for path, key, value in _walk(packet):
        if key in _PROOF_EXCLUSION_KEYS and _truthy(value):
            reasons.append(f"proof_exclusion_present:{path}")
        if key in _PROOF_EXCLUSION_TEXT_KEYS:
            text = _text(value).lower()
            if any(token in text for token in _PROOF_EXCLUSION_TEXT_TOKENS):
                reasons.append(f"proof_exclusion_present:{path}")
    return sorted(set(reasons))


def _authority_violations(packet: Mapping[str, Any]) -> list[str]:
    violations: list[str] = []
    for path, key, value in _walk(packet):
        if key in _AUTHORITY_TRUE_KEYS and _truthy(value):
            violations.append(path)
    return sorted(set(violations))


def _walk(value: Any, prefix: str = "") -> list[tuple[str, str, Any]]:
    found: list[tuple[str, str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            found.append((path, key_text, child))
            found.extend(_walk(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk(child, f"{prefix}[{index}]"))
    return found


def _failure_verdict(reasons: list[str], requested_verdict: str) -> str:
    if any(
        reason.startswith("authority_boundary_violation:")
        or reason.startswith("proof_exclusion_present:")
        or reason.startswith("promotion_ready_field_not_allowed")
        for reason in reasons
    ):
        return INVALID
    if any("hash_mismatch" in reason or "duplicate" in reason for reason in reasons):
        return INVALID
    if requested_verdict == NO_MATCHED_FILLS:
        return INVALID if any("has_" in reason for reason in reasons) else PENDING_SCHEMA
    if any(reason.endswith("_missing") or "_missing_" in reason for reason in reasons):
        return PENDING_SCHEMA
    return INVALID


def _result(
    verdict: str,
    reason: str,
    reasons: tuple[str, ...] | list[str] = (),
    *,
    no_fill_blocker: bool = False,
    authority_boundary_violation: bool = False,
) -> ProofPacketValidation:
    normalized = tuple(str(item) for item in reasons) or (reason,)
    return ProofPacketValidation(
        proof_ready=verdict == PROOF_READY and reason == "ok",
        verdict=verdict,
        reason=reason,
        reasons=normalized,
        no_fill_blocker=no_fill_blocker,
        authority_boundary_violation=authority_boundary_violation,
    )


def _canonical_sha256(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _fill_ids(execution: Mapping[str, Any]) -> list[str]:
    return _stable_text_list(execution.get("fill_ids"))


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
        return int(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY_STRINGS
    return False


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _present(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _is_hex64(value: str) -> bool:
    return bool(_HEX64_RE.match(value))


def _is_stable_hash(value: str) -> bool:
    return _is_hex64(value) or (value.startswith("sha256:") and len(value) > 7)


def _is_stable_ref(value: str) -> bool:
    return bool(_GIT_SHA_RE.match(value)) or _is_stable_hash(value)


__all__ = [
    "PROOF_PACKET_FIELD",
    "PROOF_PACKET_SCHEMA_VERSION",
    "PROOF_READY",
    "NO_MATCHED_FILLS",
    "RESEARCH_ONLY",
    "PENDING_SCHEMA",
    "INVALID",
    "ProofPacketValidation",
    "compute_proof_packet_hash",
    "extract_proof_packet",
    "validate_proof_packet",
]
