"""
MODULE_NOTE
模塊用途：建立與驗證 advisory review packet，供 L2 / MLDE / DreamEngine 的非權威輸出共用。
主要函數：stable_sha256_json、build_advisory_review_packet、validate_advisory_review_packet。
依賴：僅 Python stdlib；不可 import control_api app package，避免 ML helper 綁定控制面。
硬邊界：packet 永遠是 inactive review packet；不得表示 order / probe / live / mainnet /
runtime / DB / secret / promotion / Cost Gate / strategy-config mutation authority。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping

ADVISORY_REVIEW_PACKET_SCHEMA_VERSION = "advisory_review_packet_v1"

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_MUTATION_DIMENSION_TOKENS = {
    "order",
    "probe",
    "live",
    "mainnet",
    "runtime",
    "db",
    "database",
    "secret",
    "promotion",
    "strategy",
    "config",
}
_GRANT_TOKENS = (
    "allow",
    "allowed",
    "authorize",
    "authorized",
    "authorization",
    "enable",
    "enabled",
    "grant",
    "granted",
    "permission",
    "permit",
    "permitted",
    "perform",
    "performed",
    "mutate",
    "mutation",
    "write",
    "lower",
    "lowered",
    "authority",
)
_FALSE_STRINGS = {
    "",
    "0",
    "false",
    "no",
    "none",
    "null",
    "disabled",
    "denied",
    "not_granted",
    "not granted",
}
_DIRECT_AUTHORITY_KEYS = {
    "allowed",
    "allow",
    "authorized",
    "authorize",
    "authorization",
    "can_execute",
    "can_mutate",
    "can_write",
    "enabled",
    "enable",
    "execute_allowed",
    "execution_allowed",
    "grant",
    "granted",
    "permission",
    "permission_granted",
    "permit",
    "permitted",
    "write_allowed",
}


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=repr)
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist") and callable(value.tolist):
        return value.tolist()
    if hasattr(value, "item") and callable(value.item):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _stable_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=_json_default,
    ).encode("utf-8")


def stable_sha256_json(value: Any) -> str:
    """對 JSON-compatible value 產生穩定 SHA-256 hex。"""
    return hashlib.sha256(_stable_json_bytes(value)).hexdigest()


def build_advisory_review_packet(
    *,
    capability_id: str,
    input_payloads: Mapping[str, Any] | None = None,
    input_hashes: Mapping[str, str] | None = None,
    producer: str | None = None,
    mode: str | None = None,
    ledger_ref: str | None = None,
    cost_ref: str | None = None,
    budget_ref: str | None = "DOC-08",
    cost_usd: float | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """建立 inactive advisory review packet 並立即驗證。

    input_payloads 只轉成 hash；packet 不保存原始輸入，以免把模型上下文或 runtime 細節
    複製進下游 durable payload。
    """
    hashes: dict[str, str] = {}
    for name, payload in (input_payloads or {}).items():
        hashes[str(name)] = stable_sha256_json(payload)
    for name, digest in (input_hashes or {}).items():
        hashes[str(name)] = str(digest).lower()

    packet: dict[str, Any] = {
        "schema_version": ADVISORY_REVIEW_PACKET_SCHEMA_VERSION,
        "capability_id": str(capability_id),
        "producer": producer,
        "mode": mode,
        "not_authority": True,
        "inactive_review_packet": True,
        "active": False,
        "requires_operator_review": True,
        "requires_governance": True,
        "no_order_mutation": True,
        "no_probe_mutation": True,
        "no_live_mutation": True,
        "no_mainnet_mutation": True,
        "no_runtime_mutation": True,
        "no_db_mutation": True,
        "no_secret_mutation": True,
        "no_promotion_mutation": True,
        "no_cost_gate_mutation": True,
        "no_strategy_config_mutation": True,
        "execution_authority": "not_granted",
        "decision_lease_emitted": False,
        "demo_envelope_required_for_mutation": True,
        "current_packet_grants_demo_mutation": False,
        "input_hashes": hashes,
        "ledger_ref": ledger_ref,
        "cost_ref": cost_ref,
        "budget_ref": budget_ref,
    }
    if cost_usd is not None:
        packet["cost_usd"] = float(cost_usd)
    if notes:
        packet["notes"] = list(notes)
    validate_advisory_review_packet(packet)
    return packet


def _require_exact(packet: Mapping[str, Any], key: str, expected: Any) -> None:
    if packet.get(key) != expected:
        raise ValueError(f"{key} must be {expected!r}")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in _FALSE_STRINGS
    return bool(value)


def _normalized_key(key: Any) -> str:
    raw = str(key).strip()
    raw = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw)
    raw = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", raw)
    raw = raw.lower().replace("-", "_").replace(" ", "_")
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]+", "_", raw)).strip("_")


def _key_tokens(norm_key: str) -> tuple[str, ...]:
    return tuple(part for part in norm_key.split("_") if part)


def _has_mutation_dimension(tokens: tuple[str, ...]) -> bool:
    token_set = set(tokens)
    if token_set & _MUTATION_DIMENSION_TOKENS:
        return True
    return "cost" in token_set and "gate" in token_set


def _is_forbidden_grant_key(norm_key: str) -> bool:
    if norm_key.startswith(("no_", "not_")):
        return False
    tokens = _key_tokens(norm_key)
    token_set = set(tokens)
    if "authority" in token_set or norm_key in _DIRECT_AUTHORITY_KEYS:
        return True
    return _has_mutation_dimension(tokens) and any(token in token_set for token in _GRANT_TOKENS)


def _scan_for_truthy_grants(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            norm = _normalized_key(key)
            child_path = f"{path}.{key}"
            if norm == "active" and _truthy(child):
                raise ValueError(f"{child_path} must not be active=true")
            if _is_forbidden_grant_key(norm) and _truthy(child):
                raise ValueError(f"{child_path} grants forbidden advisory authority")
            _scan_for_truthy_grants(child, child_path)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            _scan_for_truthy_grants(child, f"{path}[{idx}]")


def validate_advisory_review_packet(packet: Mapping[str, Any]) -> bool:
    """驗證 advisory review packet；不合規以 ValueError 拒絕。"""
    if not isinstance(packet, Mapping):
        raise ValueError("packet must be a mapping")

    _require_exact(packet, "schema_version", ADVISORY_REVIEW_PACKET_SCHEMA_VERSION)
    _require_exact(packet, "not_authority", True)
    _require_exact(packet, "inactive_review_packet", True)
    _require_exact(packet, "active", False)
    _require_exact(packet, "requires_operator_review", True)
    _require_exact(packet, "requires_governance", True)
    for key in (
        "no_order_mutation",
        "no_probe_mutation",
        "no_live_mutation",
        "no_mainnet_mutation",
        "no_runtime_mutation",
        "no_db_mutation",
        "no_secret_mutation",
        "no_promotion_mutation",
        "no_cost_gate_mutation",
        "no_strategy_config_mutation",
    ):
        _require_exact(packet, key, True)
    _require_exact(packet, "execution_authority", "not_granted")
    _require_exact(packet, "decision_lease_emitted", False)
    _require_exact(packet, "demo_envelope_required_for_mutation", True)
    _require_exact(packet, "current_packet_grants_demo_mutation", False)

    hashes = packet.get("input_hashes")
    if not isinstance(hashes, Mapping) or not hashes:
        raise ValueError("input_hashes must be a non-empty mapping")
    for key, digest in hashes.items():
        if not isinstance(key, str) or not key:
            raise ValueError("input_hashes keys must be non-empty strings")
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise ValueError(f"input_hashes[{key!r}] must be a sha256 hex digest")

    _scan_for_truthy_grants(packet)
    return True


__all__ = [
    "ADVISORY_REVIEW_PACKET_SCHEMA_VERSION",
    "stable_sha256_json",
    "build_advisory_review_packet",
    "validate_advisory_review_packet",
]
