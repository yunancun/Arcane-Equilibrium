"""
MODULE_NOTE
模塊用途：Demo alpha candidate 的 SignalSpec 共享契約驗證器。
主要類/函數：SignalSpecValidation、compute_signal_spec_hash、
extract_signal_spec、validate_signal_spec。
依賴：僅 Python 標準庫；不讀 DB、不連交易所、不生成 signal。
硬邊界：SignalSpec 是候選證據 manifest 的 metadata root；缺 canonical
spec、hash mismatch、PIT / residualization / hidden OOS policy 欄位不足時，
promotion/live-candidate gate 必須 fail-closed。
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


SIGNAL_SPEC_FIELD = "signal_spec"
SIGNAL_SPEC_SCHEMA_VERSION = "signal_spec_v1"

PROMOTION_READY = "promotion_ready"
PENDING_SCHEMA = "pending_schema"
INVALID = "invalid"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class SignalSpecValidation:
    """SignalSpec 驗證結果；ok=True 才能綁定 EvidenceManifest。"""

    ok: bool
    verdict: str
    reason: str
    reasons: tuple[str, ...]
    spec_hash: str


def extract_signal_spec(mapping: Any) -> Any:
    """只讀 canonical ``signal_spec`` 欄位，不接受 alias。"""
    if not isinstance(mapping, Mapping):
        return None
    return mapping.get(SIGNAL_SPEC_FIELD)


def compute_signal_spec_hash(signal_spec: Mapping[str, Any]) -> str:
    """對 SignalSpec 做 canonical JSON sha256；頂層 ``spec_hash`` 不入 hash。"""
    payload = copy.deepcopy(dict(signal_spec))
    payload.pop("spec_hash", None)
    return _canonical_sha256(payload)


def validate_signal_spec(
    signal_spec: Any,
    *,
    expected_spec_hash: str = "",
    candidate_id: str = "",
    family_id: str = "",
) -> SignalSpecValidation:
    """驗證 SignalSpec 是否足以支撐 candidate evidence manifest。

    此函數只驗 metadata contract：假設、輸入、PIT、universe/regime lineage、
    cost model、residualization、failure taxonomy、hidden OOS policy。真正
    residual alpha 數學由 ``demo_residual_alpha_report`` 另行驗證。
    """
    if signal_spec is None:
        return _result(PENDING_SCHEMA, "signal_spec_missing")
    if not isinstance(signal_spec, Mapping):
        return _result(INVALID, "signal_spec_not_mapping")

    reasons: list[str] = []
    schema_version = _text(signal_spec.get("schema_version"))
    if schema_version != SIGNAL_SPEC_SCHEMA_VERSION:
        return _result(PENDING_SCHEMA, "signal_spec_schema_version_unknown")

    spec_hash = compute_signal_spec_hash(signal_spec)
    embedded_hash = _text(signal_spec.get("spec_hash"))
    if embedded_hash and not _is_stable_hash(embedded_hash):
        reasons.append("signal_spec_hash_malformed")
    elif embedded_hash and embedded_hash != spec_hash:
        reasons.append("signal_spec_hash_mismatch")

    expected_hash = _text(expected_spec_hash)
    if expected_hash and not _is_stable_hash(expected_hash):
        reasons.append("expected_spec_hash_malformed")
    elif expected_hash and expected_hash != spec_hash:
        reasons.append("expected_spec_hash_mismatch")

    _require_matching_text(
        signal_spec,
        "candidate_id",
        expected=_text(candidate_id),
        reasons=reasons,
    )
    _require_matching_text(
        signal_spec,
        "family_id",
        expected=_text(family_id),
        reasons=reasons,
    )
    for field in ("hypothesis",):
        if not _text(signal_spec.get(field)):
            reasons.append(f"{field}_missing")

    for field in ("horizon", "universe_ref", "regime_ref", "cost_model_ref"):
        if not _structured_present(signal_spec.get(field)):
            reasons.append(f"{field}_missing")

    if not _sequence_present(signal_spec.get("inputs")):
        reasons.append("inputs_missing")

    if not isinstance(signal_spec.get("pit_contract"), Mapping):
        reasons.append("pit_contract_missing")
    else:
        pit_contract = signal_spec["pit_contract"]
        if pit_contract.get("point_in_time") is not True:
            reasons.append("pit_contract_not_point_in_time")
        if pit_contract.get("future_data_allowed") is True:
            reasons.append("pit_contract_future_data_allowed")

    if not isinstance(signal_spec.get("feature_schema"), Mapping):
        reasons.append("feature_schema_missing")

    residualization = signal_spec.get("residualization")
    if not isinstance(residualization, Mapping):
        reasons.append("residualization_missing")
    else:
        if not _text(residualization.get("method")):
            reasons.append("residualization_method_missing")
        if not (
            _sequence_present(residualization.get("factors"))
            or _text(residualization.get("factor_panel_hash"))
        ):
            reasons.append("residualization_factors_missing")

    if not _sequence_present(signal_spec.get("failure_taxonomy")):
        reasons.append("failure_taxonomy_missing")

    hidden_oos_policy = signal_spec.get("hidden_oos_policy")
    if not isinstance(hidden_oos_policy, Mapping):
        reasons.append("hidden_oos_policy_missing")
    else:
        if _text(hidden_oos_policy.get("state_required")) != "sealed":
            reasons.append("hidden_oos_policy_state_not_sealed")
        if hidden_oos_policy.get("open_once") is not True:
            reasons.append("hidden_oos_policy_open_once_missing")

    if reasons:
        return _result(_failure_verdict(reasons), reasons[0], reasons, spec_hash)
    return _result(PROMOTION_READY, "ok", (), spec_hash)


def _require_matching_text(
    signal_spec: Mapping[str, Any],
    field: str,
    *,
    expected: str,
    reasons: list[str],
) -> None:
    actual = _text(signal_spec.get(field))
    if not actual:
        reasons.append(f"{field}_missing")
        return
    if expected and actual != expected:
        reasons.append(f"{field}_mismatch")


def _failure_verdict(reasons: list[str]) -> str:
    if any(reason.endswith("_missing") for reason in reasons):
        return PENDING_SCHEMA
    return INVALID


def _result(
    verdict: str,
    reason: str,
    reasons: tuple[str, ...] | list[str] = (),
    spec_hash: str = "",
) -> SignalSpecValidation:
    normalized = tuple(str(item) for item in reasons) or (reason,)
    return SignalSpecValidation(
        ok=verdict == PROMOTION_READY and reason == "ok",
        verdict=verdict,
        reason=reason,
        reasons=normalized,
        spec_hash=spec_hash,
    )


def _canonical_sha256(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_hex64(value: str) -> bool:
    return bool(_HEX64_RE.match(value))


def _is_stable_hash(value: str) -> bool:
    if _is_hex64(value):
        return True
    if value.startswith("sha256:") and len(value) > len("sha256:"):
        return True
    return False


def _structured_present(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(value)
    return bool(_text(value))


def _sequence_present(value: Any) -> bool:
    if isinstance(value, (str, bytes)):
        return False
    if isinstance(value, Sequence):
        return len(value) > 0
    return False


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


__all__ = [
    "SIGNAL_SPEC_FIELD",
    "SIGNAL_SPEC_SCHEMA_VERSION",
    "SignalSpecValidation",
    "compute_signal_spec_hash",
    "extract_signal_spec",
    "validate_signal_spec",
]
