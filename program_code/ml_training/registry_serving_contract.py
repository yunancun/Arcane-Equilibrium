"""
MODULE_NOTE
模塊用途：AI/ML roadmap 的 registry_serving_contract_v1 source-only contract。
主要類/函數：RegistryServingContractValidation、
validate_registry_serving_contract、compute_registry_serving_contract_hash、
extract_registry_serving_contract、attach_registry_serving_contract。
依賴：僅 Python 標準庫；不讀 DB、不連 runtime、不呼叫交易所。
硬邊界：本模塊只驗證 registry JSONB 內的 serving parity metadata；
不可授予 symlink、promotion、order、probe、runtime、Cost Gate、deploy、
live/mainnet authority。
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


REGISTRY_SERVING_CONTRACT_FIELD = "registry_serving_contract"
REGISTRY_SERVING_CONTRACT_SCHEMA_VERSION = "registry_serving_contract_v1"
PIT_DATASET_MANIFEST_SCHEMA_VERSION = "pit_dataset_manifest_v1"

ADVISORY_READY = "advisory_ready"
PENDING_SCHEMA = "pending_schema"
INVALID = "invalid"
RESEARCH_ONLY = "research_only"

_REQUIRED_HASH_FIELDS = (
    "dataset_manifest_hash",
    "label_schema_hash",
    "feature_schema_hash",
    "feature_definition_hash",
    "split_hash",
    "leakage_report_hash",
    "serving_config_hash",
)
_REQUIRED_POLICY_FIELDS = ("missingness_policy", "units", "side_handling")
_REQUIRED_QUANTILES = ("q10", "q50", "q90")
_CANONICAL_TOP_LEVEL_FIELDS = frozenset(
    (
        "schema_version",
        "serving_mode",
        "not_authority",
        "symlink_authority",
        "promotion_serving_ready",
        "dataset_manifest_schema_version",
        "artifact_hashes",
        "quantile_trio",
        "contract_hash",
    )
    + _REQUIRED_HASH_FIELDS
    + _REQUIRED_POLICY_FIELDS
)
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_TRUTHY_STRINGS = {"1", "true", "yes", "y", "on", "enabled", "grant", "granted"}

_AUTHORITY_TRUE_KEYS = {
    "cost_gate_change_performed",
    "cost_gate_lowering_allowed",
    "cost_gate_lowering_performed",
    "cost_gate_lowering_recommended",
    "db_read_allowed",
    "db_read_performed",
    "db_write_allowed",
    "db_write_performed",
    "deploy_allowed",
    "deploy_performed",
    "exchange_private_read_allowed",
    "exchange_private_read_performed",
    "live_allowed",
    "live_authority_granted",
    "live_enabled",
    "live_or_mainnet_performed",
    "mainnet_allowed",
    "mainnet_enabled",
    "mainnet_performed",
    "mcp_server_allowed",
    "mcp_server_started",
    "order_allowed",
    "order_authority_granted",
    "order_performed",
    "private_read_allowed",
    "private_read_performed",
    "probe_allowed",
    "probe_authority_granted",
    "probe_performed",
    "promotion_allowed",
    "promotion_authority_granted",
    "promotion_enabled",
    "runtime_mutation_allowed",
    "runtime_mutation_performed",
    "runtime_write_allowed",
    "secret_access_allowed",
    "secret_access_performed",
    "serving_authority_granted",
    "symlink_allowed",
    "symlink_authority_granted",
}
_AUTHORITY_KEY_TERMS = (
    "cost",
    "cost_gate",
    "db",
    "deploy",
    "exchange_private",
    "live",
    "mainnet",
    "mcp",
    "order",
    "private",
    "probe",
    "promotion",
    "runtime",
    "secret",
    "serving_authority",
    "symlink",
)
_AUTHORITY_ACTION_TERMS = (
    "allow",
    "allowed",
    "author",
    "change",
    "deploy",
    "enable",
    "enabled",
    "grant",
    "granted",
    "lower",
    "lowering",
    "mutat",
    "perform",
    "performed",
    "start",
    "started",
    "write",
)
_AUTHORITY_ACTION_TOKENS = {"read"}
_CANONICAL_BOUNDARY_KEYS = {
    "not_authority",
    "promotion_serving_ready",
    "symlink_authority",
}


@dataclass(frozen=True)
class RegistryServingContractValidation:
    """Registry serving contract 驗證結果；advisory_ready 不等於 serving authority。"""

    advisory_ready: bool
    verdict: str
    reason: str
    reasons: tuple[str, ...]
    authority_boundary_violation: bool = False


class RegistryServingContractError(ValueError):
    """Provided serving contract failed source-only validation before DB access."""


def extract_registry_serving_contract(mapping: Any) -> Any:
    """只讀 canonical ``registry_serving_contract`` 欄位，不接受 alias。"""
    if not isinstance(mapping, Mapping):
        return None
    return mapping.get(REGISTRY_SERVING_CONTRACT_FIELD)


def compute_registry_serving_contract_hash(contract: Mapping[str, Any]) -> str:
    """對 contract 做 canonical JSON sha256；頂層 ``contract_hash`` 不入 hash。"""
    payload = copy.deepcopy(dict(contract))
    payload.pop("contract_hash", None)
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_registry_serving_contract(
    contract: Any,
) -> RegistryServingContractValidation:
    """驗證 ``registry_serving_contract_v1`` 是否可附在 registry JSONB。

    本函數只證明 caller 提供的 source contract 欄位完整且沒有權限擴張；
    advisory-ready 仍只是研究/建議層 metadata，不代表 Rust serving closure。
    """
    if contract is None:
        return _result(PENDING_SCHEMA, "registry_serving_contract_missing")
    if not isinstance(contract, Mapping):
        return _result(INVALID, "registry_serving_contract_not_mapping")

    authority_violations = _authority_violations(contract)
    if authority_violations:
        return _result(
            INVALID,
            f"authority_boundary_violation:{authority_violations[0]}",
            tuple(f"authority_boundary_violation:{item}" for item in authority_violations),
            authority_boundary_violation=True,
        )

    schema_version = _text(contract.get("schema_version"))
    if schema_version != REGISTRY_SERVING_CONTRACT_SCHEMA_VERSION:
        return _result(PENDING_SCHEMA, "schema_version_unknown")

    reasons: list[str] = []
    reasons.extend(_validate_top_level_fields(contract))

    serving_mode = _text(contract.get("serving_mode"))
    if not serving_mode:
        reasons.append("serving_mode_missing")
    elif serving_mode == RESEARCH_ONLY:
        reasons.append("serving_mode_research_only")
    elif serving_mode != "advisory_only":
        reasons.append("serving_mode_not_advisory_only")

    if "not_authority" not in contract:
        reasons.append("not_authority_missing")
    elif contract.get("not_authority") is not True:
        reasons.append("not_authority_not_true")

    if "symlink_authority" not in contract:
        reasons.append("symlink_authority_missing")
    elif contract.get("symlink_authority") is not False:
        reasons.append("symlink_authority_not_false")

    if "promotion_serving_ready" not in contract:
        reasons.append("promotion_serving_ready_missing")
    elif contract.get("promotion_serving_ready") is not False:
        reasons.append("promotion_serving_ready_not_false")

    dataset_manifest_schema_version = _text(
        contract.get("dataset_manifest_schema_version")
    )
    if not dataset_manifest_schema_version:
        reasons.append("dataset_manifest_schema_version_missing")
    elif dataset_manifest_schema_version != PIT_DATASET_MANIFEST_SCHEMA_VERSION:
        reasons.append("dataset_manifest_schema_version_unknown")

    reasons.extend(_validate_required_hash_fields(contract))
    reasons.extend(_validate_required_policy_fields(contract))
    reasons.extend(_validate_artifact_hashes(contract.get("artifact_hashes")))
    reasons.extend(_validate_quantile_trio(contract.get("quantile_trio")))

    contract_hash = _text(contract.get("contract_hash"))
    if not contract_hash:
        reasons.append("contract_hash_missing")
    elif not _is_hash(contract_hash):
        reasons.append("contract_hash_malformed")
    elif not reasons:
        try:
            computed_hash = compute_registry_serving_contract_hash(contract)
        except (TypeError, ValueError):
            reasons.append("contract_hash_uncomputable")
        else:
            expected_hash = _strip_sha256_prefix(contract_hash)
            if expected_hash != computed_hash:
                reasons.append("contract_hash_mismatch")

    if reasons:
        return _result(_failure_verdict(reasons), reasons[0], reasons)

    return _result(ADVISORY_READY, "ok", ())


def attach_registry_serving_contract(
    acceptance_report: Mapping[str, Any] | None,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    """複製 acceptance report，且只在 valid contract 時附 canonical 欄位。

    Invalid contract 直接拋 ``RegistryServingContractError``，讓 caller 在
    DB connect/write 之前 fail closed。
    """
    validation = validate_registry_serving_contract(contract)
    if not validation.advisory_ready:
        raise RegistryServingContractError(
            f"invalid registry serving contract: {validation.reason}"
        )
    report = copy.deepcopy(dict(acceptance_report or {}))
    report[REGISTRY_SERVING_CONTRACT_FIELD] = copy.deepcopy(dict(contract))
    return report


def _validate_required_hash_fields(contract: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in _REQUIRED_HASH_FIELDS:
        value = _text(contract.get(field))
        if not value:
            reasons.append(f"{field}_missing")
        elif not _is_hash(value):
            reasons.append(f"{field}_malformed")
    return reasons


def _validate_top_level_fields(contract: Mapping[str, Any]) -> list[str]:
    extra = sorted(
        str(key) for key in contract.keys() if key not in _CANONICAL_TOP_LEVEL_FIELDS
    )
    if extra:
        return [f"top_level_fields_unknown:{','.join(extra)}"]
    return []


def _validate_required_policy_fields(contract: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in _REQUIRED_POLICY_FIELDS:
        if field not in contract:
            reasons.append(f"{field}_missing")
            continue
        value = contract.get(field)
        if not isinstance(value, str):
            reasons.append(f"{field}_not_string")
        elif not value.strip():
            reasons.append(f"{field}_empty")
    return reasons


def _validate_artifact_hashes(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return ["artifact_hashes_missing"]
    keys = tuple(value.keys())
    if set(keys) != set(_REQUIRED_QUANTILES):
        reasons: list[str] = []
        missing = [q for q in _REQUIRED_QUANTILES if q not in value]
        extra = sorted(str(q) for q in value.keys() if q not in _REQUIRED_QUANTILES)
        if missing:
            reasons.append(f"artifact_hashes_missing_quantiles:{','.join(missing)}")
        if extra:
            reasons.append(f"artifact_hashes_extra_quantiles:{','.join(extra)}")
        return reasons or ["artifact_hashes_quantile_set_mismatch"]
    if tuple(keys) != _REQUIRED_QUANTILES:
        return ["artifact_hashes_quantile_order_mismatch"]
    reasons = []
    for quantile in _REQUIRED_QUANTILES:
        if not _is_hash(_text(value.get(quantile))):
            reasons.append(f"artifact_hashes_{quantile}_malformed")
    return reasons


def _validate_quantile_trio(value: Any) -> list[str]:
    if not isinstance(value, list):
        return ["quantile_trio_missing"]
    if value != list(_REQUIRED_QUANTILES):
        return ["quantile_trio_not_exact_q10_q50_q90"]
    return []


def _failure_verdict(reasons: list[str]) -> str:
    if any(reason.startswith("serving_mode_research_only") for reason in reasons):
        return RESEARCH_ONLY
    if any(
        reason.startswith("authority_boundary_violation:")
        or reason
        in {
            "not_authority_not_true",
            "symlink_authority_not_false",
            "promotion_serving_ready_not_false",
            "contract_hash_mismatch",
            "contract_hash_malformed",
            "artifact_hashes_quantile_order_mismatch",
            "quantile_trio_not_exact_q10_q50_q90",
            "serving_mode_not_advisory_only",
        }
        or reason.startswith("top_level_fields_unknown:")
        or "_extra_quantiles:" in reason
        or "_missing_quantiles:" in reason
        or reason.endswith("_empty")
        or reason.endswith("_malformed")
        or reason.endswith("_mismatch")
        or reason.endswith("_not_false")
        or reason.endswith("_not_string")
        or reason.endswith("_not_true")
        for reason in reasons
    ):
        return INVALID
    return PENDING_SCHEMA


def _result(
    verdict: str,
    reason: str,
    reasons: tuple[str, ...] | list[str] = (),
    *,
    authority_boundary_violation: bool = False,
) -> RegistryServingContractValidation:
    normalized = tuple(str(item) for item in reasons) or (reason,)
    return RegistryServingContractValidation(
        advisory_ready=verdict == ADVISORY_READY and reason == "ok",
        verdict=verdict,
        reason=reason,
        reasons=normalized,
        authority_boundary_violation=authority_boundary_violation,
    )


def _authority_violations(contract: Mapping[str, Any]) -> list[str]:
    violations: list[str] = []
    for path, key, value in _walk(contract):
        if _is_authority_expansion_key(key) and _truthy(value):
            violations.append(path)
    return sorted(set(violations))


def _is_authority_expansion_key(key: str) -> bool:
    key_text = key.lower()
    if key_text in _CANONICAL_BOUNDARY_KEYS:
        return False
    if key_text in _AUTHORITY_TRUE_KEYS:
        return True
    key_tokens = tuple(re.findall(r"[a-z0-9]+", key_text))
    has_authority_term = any(term in key_text for term in _AUTHORITY_KEY_TERMS)
    has_authority_action = any(
        action in key_text for action in _AUTHORITY_ACTION_TERMS
    ) or any(token in _AUTHORITY_ACTION_TOKENS for token in key_tokens)
    return has_authority_term and has_authority_action


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


def _is_hash(value: str) -> bool:
    return bool(_HEX64_RE.match(_strip_sha256_prefix(value)))


def _strip_sha256_prefix(value: str) -> str:
    if value.startswith("sha256:"):
        return value[len("sha256:") :]
    return value


__all__ = [
    "REGISTRY_SERVING_CONTRACT_FIELD",
    "REGISTRY_SERVING_CONTRACT_SCHEMA_VERSION",
    "PIT_DATASET_MANIFEST_SCHEMA_VERSION",
    "ADVISORY_READY",
    "PENDING_SCHEMA",
    "INVALID",
    "RESEARCH_ONLY",
    "RegistryServingContractValidation",
    "RegistryServingContractError",
    "attach_registry_serving_contract",
    "compute_registry_serving_contract_hash",
    "extract_registry_serving_contract",
    "validate_registry_serving_contract",
]
