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
import math
import re
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Mapping

ADVISORY_REVIEW_PACKET_SCHEMA_VERSION = "advisory_review_packet_v1"
ADVISORY_REVIEW_PACKET_HASH_FIELD = "advisory_review_packet_hash"

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
_EXTERNAL_CONTACT_TOKENS = {
    "broker",
    "credential",
    "credentials",
    "exchange",
    "mcp",
    "private",
    "provider",
}
_EXTERNAL_CONTACT_ACTION_TOKENS = {
    "access",
    "accessed",
    "call",
    "called",
    "connect",
    "connected",
    "contact",
    "contacted",
    "fetch",
    "fetched",
    "perform",
    "performed",
    "query",
    "queried",
    "read",
    "request",
    "requested",
    "server",
    "session",
    "start",
    "started",
}
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
_MAX_MAPPING_KEY_LENGTH = 256
_MAX_NESTING_DEPTH = 32
_MAX_COLLECTION_LENGTH = 10_000
_MAX_NORMALIZED_NODES = 50_000
_MAX_STRING_LENGTH = 1024 * 1024


def _plain_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _normalize_plain_json(value: Any) -> Any:
    """Normalize explicitly supported values into one bounded plain-JSON tree."""
    active_ids: set[int] = set()
    node_count = 0

    def normalize(current: Any, *, depth: int) -> Any:
        nonlocal node_count
        if depth > _MAX_NESTING_DEPTH:
            raise ValueError("mapping nesting depth exceeds maximum")
        node_count += 1
        if node_count > _MAX_NORMALIZED_NODES:
            raise ValueError("normalized value exceeds node bound")

        if current is None or isinstance(current, bool):
            return current
        if isinstance(current, int):
            return current
        if isinstance(current, float):
            if not math.isfinite(current):
                raise ValueError("non-finite numbers are not supported")
            return current
        if isinstance(current, str):
            if len(current) > _MAX_STRING_LENGTH:
                raise ValueError("string exceeds maximum length")
            return current
        if isinstance(current, Path):
            rendered = str(current)
            if len(rendered) > _MAX_STRING_LENGTH:
                raise ValueError("string exceeds maximum length")
            return rendered

        current_id = id(current)
        if current_id in active_ids:
            raise ValueError("cyclic values are not supported")

        if is_dataclass(current) and not isinstance(current, type):
            dataclass_fields = fields(current)
            if len(dataclass_fields) > _MAX_COLLECTION_LENGTH:
                raise ValueError("collection exceeds maximum length")
            active_ids.add(current_id)
            try:
                return {
                    field.name: normalize(getattr(current, field.name), depth=depth + 1)
                    for field in dataclass_fields
                }
            finally:
                active_ids.remove(current_id)

        if isinstance(current, Mapping):
            if len(current) > _MAX_COLLECTION_LENGTH:
                raise ValueError("collection exceeds maximum length")
            active_ids.add(current_id)
            try:
                normalized: dict[str, Any] = {}
                for key, child in current.items():
                    if not isinstance(key, str):
                        raise ValueError("mapping keys must be strings")
                    if not key:
                        raise ValueError("mapping keys must not be empty")
                    if len(key) > _MAX_MAPPING_KEY_LENGTH:
                        raise ValueError("mapping key exceeds maximum length")
                    normalized[key] = normalize(child, depth=depth + 1)
                return normalized
            finally:
                active_ids.remove(current_id)

        if isinstance(current, (list, tuple)):
            if len(current) > _MAX_COLLECTION_LENGTH:
                raise ValueError("collection exceeds maximum length")
            active_ids.add(current_id)
            try:
                return [normalize(child, depth=depth + 1) for child in current]
            finally:
                active_ids.remove(current_id)

        if isinstance(current, (set, frozenset)):
            if len(current) > _MAX_COLLECTION_LENGTH:
                raise ValueError("collection exceeds maximum length")
            active_ids.add(current_id)
            try:
                normalized_items = [
                    normalize(child, depth=depth + 1) for child in current
                ]
                return sorted(normalized_items, key=_plain_json_bytes)
            finally:
                active_ids.remove(current_id)

        for method_name in ("tolist", "item"):
            try:
                converter = getattr(current, method_name, None)
            except Exception as exc:
                raise ValueError("supported conversion lookup failed") from exc
            if not callable(converter):
                continue
            active_ids.add(current_id)
            try:
                try:
                    converted = converter()
                except Exception as exc:
                    raise ValueError(f"{method_name} conversion failed") from exc
                return normalize(converted, depth=depth + 1)
            finally:
                active_ids.remove(current_id)

        raise ValueError("unsupported value type")

    return normalize(value, depth=0)


def _stable_json_bytes(value: Any) -> bytes:
    return _plain_json_bytes(_normalize_plain_json(value))


def stable_sha256_json(value: Any) -> str:
    """對 JSON-compatible value 產生穩定 SHA-256 hex。"""
    return hashlib.sha256(_stable_json_bytes(value)).hexdigest()


def _compute_normalized_packet_hash(packet: dict[str, Any]) -> str:
    payload = dict(packet)
    payload.pop(ADVISORY_REVIEW_PACKET_HASH_FIELD, None)
    return hashlib.sha256(_plain_json_bytes(payload)).hexdigest()


def compute_advisory_review_packet_hash(packet: Mapping[str, Any]) -> str:
    """對 advisory packet 做 canonical JSON sha256；頂層 self-hash 不入 hash。"""
    payload = _normalize_plain_json(packet)
    if not isinstance(payload, dict):
        raise ValueError("packet must normalize to an object")
    return _compute_normalized_packet_hash(payload)


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
        "no_provider_call": True,
        "no_exchange_contact": True,
        "no_private_read": True,
        "no_mcp_runtime": True,
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
    normalized_packet = _normalize_plain_json(packet)
    if not isinstance(normalized_packet, dict):
        raise ValueError("packet must normalize to an object")
    normalized_packet[ADVISORY_REVIEW_PACKET_HASH_FIELD] = (
        _compute_normalized_packet_hash(normalized_packet)
    )
    validate_advisory_review_packet(normalized_packet)
    return normalized_packet


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
    if len(raw) > _MAX_MAPPING_KEY_LENGTH:
        raise ValueError("mapping key exceeds maximum length")

    normalized: list[str] = []
    pending_separator = False
    for index, char in enumerate(raw):
        is_lower = "a" <= char <= "z"
        is_upper = "A" <= char <= "Z"
        is_digit = "0" <= char <= "9"
        if not (is_lower or is_upper or is_digit):
            pending_separator = bool(normalized)
            continue

        if pending_separator and normalized and normalized[-1] != "_":
            normalized.append("_")
        pending_separator = False

        if is_upper and normalized and normalized[-1] != "_":
            previous = raw[index - 1] if index else ""
            previous_is_lower_or_digit = (
                "a" <= previous <= "z" or "0" <= previous <= "9"
            )
            previous_is_upper = "A" <= previous <= "Z"
            next_char = raw[index + 1] if index + 1 < len(raw) else ""
            next_is_lower = "a" <= next_char <= "z"
            if previous_is_lower_or_digit or (previous_is_upper and next_is_lower):
                normalized.append("_")
        normalized.append(char.lower() if is_upper else char)

    return "".join(normalized).strip("_")


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


def _is_forbidden_external_contact_key(norm_key: str) -> bool:
    if norm_key.startswith(("no_", "not_")):
        return False
    tokens = _key_tokens(norm_key)
    token_set = set(tokens)
    if not (token_set & _EXTERNAL_CONTACT_TOKENS):
        return False
    return bool(token_set & _EXTERNAL_CONTACT_ACTION_TOKENS)


def _scan_for_truthy_grants(
    value: Any,
    path: str = "$",
    *,
    depth: int = 0,
) -> None:
    if depth > _MAX_NESTING_DEPTH:
        raise ValueError("mapping nesting depth exceeds maximum")
    if isinstance(value, Mapping):
        for key, child in value.items():
            norm = _normalized_key(key)
            child_path = f"{path}.{key}"
            if norm == "active" and _truthy(child):
                raise ValueError(f"{child_path} must not be active=true")
            if _is_forbidden_grant_key(norm) and _truthy(child):
                raise ValueError(f"{child_path} grants forbidden advisory authority")
            if _is_forbidden_external_contact_key(norm) and _truthy(child):
                raise ValueError(f"{child_path} records forbidden external contact")
            _scan_for_truthy_grants(child, child_path, depth=depth + 1)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            _scan_for_truthy_grants(child, f"{path}[{idx}]", depth=depth + 1)


def validate_advisory_review_packet(packet: Mapping[str, Any]) -> bool:
    """驗證 advisory review packet；不合規以 ValueError 拒絕。"""
    if not isinstance(packet, Mapping):
        raise ValueError("packet must be a mapping")
    normalized_packet = _normalize_plain_json(packet)
    if not isinstance(normalized_packet, dict):
        raise ValueError("packet must normalize to an object")

    _require_exact(normalized_packet, "schema_version", ADVISORY_REVIEW_PACKET_SCHEMA_VERSION)
    _require_exact(normalized_packet, "not_authority", True)
    _require_exact(normalized_packet, "inactive_review_packet", True)
    _require_exact(normalized_packet, "active", False)
    _require_exact(normalized_packet, "requires_operator_review", True)
    _require_exact(normalized_packet, "requires_governance", True)
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
        "no_provider_call",
        "no_exchange_contact",
        "no_private_read",
        "no_mcp_runtime",
    ):
        _require_exact(normalized_packet, key, True)
    _require_exact(normalized_packet, "execution_authority", "not_granted")
    _require_exact(normalized_packet, "decision_lease_emitted", False)
    _require_exact(normalized_packet, "demo_envelope_required_for_mutation", True)
    _require_exact(normalized_packet, "current_packet_grants_demo_mutation", False)

    hashes = normalized_packet.get("input_hashes")
    if not isinstance(hashes, Mapping) or not hashes:
        raise ValueError("input_hashes must be a non-empty mapping")
    for key, digest in hashes.items():
        if not isinstance(key, str) or not key:
            raise ValueError("input_hashes keys must be non-empty strings")
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise ValueError(f"input_hashes[{key!r}] must be a sha256 hex digest")

    # Bound and inspect the untrusted tree before canonical JSON hashing. Deep
    # hostile structures must fail with a controlled validation error rather
    # than reaching the JSON encoder's recursion limit.
    _scan_for_truthy_grants(normalized_packet)

    packet_hash = normalized_packet.get(ADVISORY_REVIEW_PACKET_HASH_FIELD)
    if not isinstance(packet_hash, str) or _SHA256_RE.fullmatch(packet_hash) is None:
        raise ValueError("advisory_review_packet_hash must be a sha256 hex digest")
    if packet_hash != _compute_normalized_packet_hash(normalized_packet):
        raise ValueError("advisory_review_packet_hash mismatch")

    return True


__all__ = [
    "ADVISORY_REVIEW_PACKET_SCHEMA_VERSION",
    "ADVISORY_REVIEW_PACKET_HASH_FIELD",
    "stable_sha256_json",
    "compute_advisory_review_packet_hash",
    "build_advisory_review_packet",
    "validate_advisory_review_packet",
]
