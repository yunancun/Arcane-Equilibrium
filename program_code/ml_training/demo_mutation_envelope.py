"""
MODULE_NOTE
模塊用途：AI/ML roadmap 的 demo_mutation_envelope_v1 source-only contract。
主要函數：stable_sha256_json、build_demo_mutation_envelope、
validate_demo_mutation_envelope、extract_demo_mutation_envelope。
依賴：僅 Python 標準庫；不讀 DB、不連 runtime、不呼叫交易所或 provider。
硬邊界：本模塊只描述 Demo 變更的 review/audit envelope；不可授予下單、
probe、runtime、DB、secret、Cost Gate、strategy-config、deploy、live/mainnet
authority，也不會套用任何 mutation。
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any


DEMO_MUTATION_ENVELOPE_FIELD = "demo_mutation_envelope"
DEMO_MUTATION_ENVELOPE_SCHEMA_VERSION = "demo_mutation_envelope_v1"

STATUS_COUNTABLE = "countable_after_review"
STATUS_AUDIT_ONLY = "review_audit_only"
STATUS_INVALID = "invalid"
STATUS_PENDING_SCHEMA = "pending_schema"

APPLICATION_STATUS_APPLIED = "applied"
APPLICATION_STATUS_DRY_RUN = "dry_run"
APPLICATION_STATUS_SKIPPED = "skipped"
APPLICATION_STATUS_FAILED = "failed"

ENGINE_MODE_DEMO = "demo"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
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
_NON_DEMO_SCOPE_VALUES = {"live", "live_demo", "mainnet", "prod", "production"}
_SCOPE_KEYS = {
    "engine_mode",
    "execution_mode",
    "mode",
    "scope",
    "target_scope",
    "environment",
    "env",
    "market_mode",
    "runtime_scope",
}
_AUTHORITY_DIMENSION_TOKENS = {
    "cost",
    "gate",
    "db",
    "database",
    "deploy",
    "exchange",
    "live",
    "mainnet",
    "mcp",
    "mutation",
    "order",
    "private",
    "probe",
    "provider",
    "runtime",
    "secret",
    "strategy",
    "config",
}
_AUTHORITY_ACTION_TOKENS = {
    "access",
    "accessed",
    "allow",
    "allowed",
    "author",
    "authorization",
    "authorized",
    "authority",
    "call",
    "called",
    "change",
    "deploy",
    "enable",
    "enabled",
    "grant",
    "granted",
    "lower",
    "lowered",
    "mutate",
    "mutation",
    "perform",
    "performed",
    "read",
    "start",
    "started",
    "write",
}
_DIRECT_AUTHORITY_KEYS = {
    "cost_gate_lowered",
    "cost_gate_lowering_allowed",
    "database_write_allowed",
    "db_write_allowed",
    "demo_mutation_allowed",
    "demo_mutation_authority_granted",
    "live_authority_granted",
    "mainnet_allowed",
    "mainnet_enabled",
    "order_authority_granted",
    "probe_authority_granted",
    "runtime_mutation_allowed",
    "runtime_mutation_performed",
    "strategy_config_write_allowed",
}
_COUNTABLE_APPLICATION_STATUSES = {APPLICATION_STATUS_APPLIED}
_POST_REVIEW_PASS_STATUSES = {"pass", "passed", "ok", "approved"}
_GOVERNANCE_ALLOW_STATUSES = {
    "allow_review",
    "allowed_for_review",
    "approved_for_review",
    "pass",
    "passed",
    "review_allowed",
}
_IPC_SUCCESS_STATUSES = {"ok", "success", "applied", "accepted"}


@dataclass(frozen=True)
class DemoMutationEnvelopeValidation:
    """DemoMutationEnvelope 驗證結果；countable 才能進有效學習統計。"""

    valid: bool
    status: str
    reason: str
    reasons: tuple[str, ...]
    effective_learning_countable: bool = False
    authority_boundary_violation: bool = False


def extract_demo_mutation_envelope(mapping: Any) -> Any:
    """只讀 canonical ``demo_mutation_envelope`` 欄位，不接受 alias。"""
    if not isinstance(mapping, Mapping):
        return None
    return mapping.get(DEMO_MUTATION_ENVELOPE_FIELD)


def stable_sha256_json(value: Any) -> str:
    """對 JSON-compatible value 產生 key-order-stable SHA-256 hex。"""
    return hashlib.sha256(_stable_json_bytes(value)).hexdigest()


def compute_demo_mutation_envelope_hash(envelope: Mapping[str, Any]) -> str:
    """對 envelope 做 canonical JSON sha256；頂層 ``envelope_sha256`` 不入 hash。"""
    payload = copy.deepcopy(dict(envelope))
    payload.pop("envelope_sha256", None)
    return stable_sha256_json(payload)


def build_bounded_delta(
    *,
    previous_snapshot: Mapping[str, Any],
    proposed_patch: Mapping[str, Any],
    max_delta_policy: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """從 patch leaf path 建立 bounded-delta rows，供 applier mapping 後續消費。"""
    policy = dict(max_delta_policy or {})
    rows: list[dict[str, Any]] = []
    for path, proposed_value in _flatten_patch(proposed_patch):
        previous_present, previous_value = _get_path(previous_snapshot, path)
        max_delta_pct = _policy_max_delta_bound(policy, path, "max_delta_pct")
        max_delta = _policy_max_delta_bound(policy, path, "max_delta")
        delta_value, delta_pct = _delta(previous_value, proposed_value)
        within_policy = _within_delta_policy(
            delta_value=delta_value,
            delta_pct=delta_pct,
            max_delta=max_delta,
            max_delta_pct=max_delta_pct,
        )
        rows.append(
            {
                "path": path,
                "previous_value_present": previous_present,
                "previous_value": previous_value,
                "proposed_value": proposed_value,
                "delta": delta_value,
                "delta_pct": delta_pct,
                "max_delta": max_delta,
                "max_delta_pct": max_delta_pct,
                "within_policy": within_policy,
            }
        )
    return rows


def build_demo_mutation_envelope(
    *,
    source_proposal_or_recommendation_id: str,
    source_payload: Mapping[str, Any] | None = None,
    source_payload_hash: str | None = None,
    application_type: str,
    target: str,
    previous_snapshot: Mapping[str, Any] | None,
    proposed_patch: Mapping[str, Any] | None,
    bounded_delta: Sequence[Mapping[str, Any]] | None = None,
    max_delta_policy: Mapping[str, Any] | None = None,
    governance_verdict: Mapping[str, Any] | None = None,
    rollback_handle: Mapping[str, Any] | None = None,
    ipc_response: Mapping[str, Any] | None = None,
    ipc_response_status: str | None = None,
    ipc_response_hash: str | None = None,
    post_change_review: Mapping[str, Any] | None = None,
    proof_linkage: Mapping[str, Any] | None = None,
    application_status: str = APPLICATION_STATUS_APPLIED,
    dedupe: bool = False,
    dry_run: bool = False,
    engine_mode: str = ENGINE_MODE_DEMO,
    no_authority_answers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """建立 canonical Demo mutation envelope；不執行任何外部副作用。"""
    previous = dict(previous_snapshot or {})
    patch = dict(proposed_patch or {})
    policy = dict(max_delta_policy or {})
    source_hash = (
        _strip_sha256_prefix(source_payload_hash)
        if source_payload_hash
        else stable_sha256_json(source_payload or {})
    )
    delta_rows = (
        [dict(row) for row in bounded_delta]
        if bounded_delta is not None
        else build_bounded_delta(
            previous_snapshot=previous,
            proposed_patch=patch,
            max_delta_policy=policy,
        )
    )
    response_hash = (
        _strip_sha256_prefix(ipc_response_hash)
        if ipc_response_hash
        else stable_sha256_json(ipc_response or {})
    )
    source_id = str(source_proposal_or_recommendation_id)
    envelope_id_seed = {
        "schema_version": DEMO_MUTATION_ENVELOPE_SCHEMA_VERSION,
        "engine_mode": engine_mode,
        "source_id": source_id,
        "source_payload_hash": source_hash,
        "application_type": application_type,
        "target": target,
        "proposed_patch": patch,
    }
    envelope: dict[str, Any] = {
        "schema_version": DEMO_MUTATION_ENVELOPE_SCHEMA_VERSION,
        "envelope_id": "demo_mutation_envelope:" + stable_sha256_json(envelope_id_seed)[:24],
        "engine_mode": engine_mode,
        "source_proposal_or_recommendation_id": source_id,
        "source_payload_hash": source_hash,
        "source": {
            "source_proposal_or_recommendation_id": source_id,
            "source_payload_hash": source_hash,
        },
        "application_type": str(application_type),
        "target": str(target),
        "application": {
            "application_type": str(application_type),
            "target": str(target),
            "status": str(application_status),
            "dedupe": bool(dedupe),
            "dry_run": bool(dry_run),
        },
        "previous_snapshot": previous,
        "proposed_patch": patch,
        "bounded_delta": delta_rows,
        "max_delta_policy": policy,
        "governance_verdict": dict(governance_verdict or {}),
        "rollback_handle": dict(rollback_handle or {}),
        "ipc_response_hash": response_hash,
        "ipc_response_status": str(ipc_response_status or _text((ipc_response or {}).get("status"))),
        "post_change_review": dict(post_change_review or {}),
        "proof_linkage": dict(proof_linkage or {}),
        "answers": _no_authority_answers(no_authority_answers),
    }
    countable, countability_reasons = _countability(envelope)
    envelope["effective_learning_countable"] = countable
    envelope["envelope_status"] = STATUS_COUNTABLE if countable else STATUS_AUDIT_ONLY
    envelope["countability"] = {
        "effective_learning_countable": countable,
        "reasons": countability_reasons,
    }
    envelope["envelope_sha256"] = compute_demo_mutation_envelope_hash(envelope)
    return envelope


def validate_demo_mutation_envelope(envelope: Any) -> DemoMutationEnvelopeValidation:
    """驗證 ``demo_mutation_envelope_v1``，並 fail-closed 重算 countability。"""
    if envelope is None:
        return _result(False, STATUS_PENDING_SCHEMA, "demo_mutation_envelope_missing")
    if not isinstance(envelope, Mapping):
        return _result(False, STATUS_INVALID, "demo_mutation_envelope_not_mapping")

    authority_violations = _authority_violations(envelope)
    if authority_violations:
        return _result(
            False,
            STATUS_INVALID,
            f"authority_boundary_violation:{authority_violations[0]}",
            tuple(f"authority_boundary_violation:{item}" for item in authority_violations),
            authority_boundary_violation=True,
        )

    scope_reasons = _engine_mode_reasons(envelope) + _non_demo_scope_reasons(envelope)
    if scope_reasons:
        return _result(False, STATUS_INVALID, scope_reasons[0], scope_reasons)

    schema_version = _text(envelope.get("schema_version"))
    if schema_version != DEMO_MUTATION_ENVELOPE_SCHEMA_VERSION:
        return _result(False, STATUS_PENDING_SCHEMA, "schema_version_unknown")

    structural_reasons = _structural_reasons(envelope)
    if structural_reasons:
        return _result(False, STATUS_INVALID, structural_reasons[0], structural_reasons)

    countable, countability_reasons = _countability(envelope)
    claimed_countable = envelope.get("effective_learning_countable")
    if claimed_countable is True and not countable:
        return _result(
            False,
            STATUS_INVALID,
            "effective_learning_countable_claim_not_supported",
            tuple(countability_reasons),
        )
    if claimed_countable not in (None, True, False):
        return _result(False, STATUS_INVALID, "effective_learning_countable_not_bool")

    envelope_hash = _text(envelope.get("envelope_sha256"))
    if not envelope_hash:
        return _result(False, STATUS_INVALID, "envelope_sha256_missing")
    if not _is_hex64(envelope_hash):
        return _result(False, STATUS_INVALID, "envelope_sha256_malformed")
    if envelope_hash != compute_demo_mutation_envelope_hash(envelope):
        return _result(False, STATUS_INVALID, "envelope_sha256_mismatch")

    if countable:
        return _result(True, STATUS_COUNTABLE, "ok", (), effective_learning_countable=True)
    return _result(
        True,
        STATUS_AUDIT_ONLY,
        countability_reasons[0] if countability_reasons else "audit_only",
        tuple(countability_reasons),
    )


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


def _no_authority_answers(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    answers = {
        "demo_mutation_authority_granted": False,
        "runtime_mutation_allowed": False,
        "database_write_allowed": False,
        "cost_gate_lowered": False,
        "strategy_config_write_allowed": False,
        "order_authority_granted": False,
        "probe_authority_granted": False,
        "live_authority_granted": False,
        "mainnet_allowed": False,
        "secret_access_performed": False,
        "provider_call_performed": False,
        "exchange_call_performed": False,
        "mcp_server_started": False,
        "deploy_performed": False,
    }
    if overrides:
        answers.update(dict(overrides))
    return answers


def _structural_reasons(envelope: Mapping[str, Any]) -> tuple[str, ...]:
    reasons: list[str] = []
    if not _text(envelope.get("envelope_id")):
        reasons.append("envelope_id_missing")
    if not _text(envelope.get("source_proposal_or_recommendation_id")):
        reasons.append("source_proposal_or_recommendation_id_missing")
    if not _is_hex64(_text(envelope.get("source_payload_hash"))):
        reasons.append("source_payload_hash_missing_or_malformed")
    if not _text(envelope.get("application_type")):
        reasons.append("application_type_missing")
    if not _text(envelope.get("target")):
        reasons.append("target_missing")
    if not isinstance(envelope.get("previous_snapshot"), Mapping):
        reasons.append("previous_snapshot_missing")
    if not isinstance(envelope.get("proposed_patch"), Mapping):
        reasons.append("proposed_patch_missing")
    if not isinstance(envelope.get("bounded_delta"), Sequence) or isinstance(
        envelope.get("bounded_delta"), (str, bytes, bytearray)
    ):
        reasons.append("bounded_delta_missing")
    if not isinstance(envelope.get("max_delta_policy"), Mapping):
        reasons.append("max_delta_policy_missing")
    if not isinstance(envelope.get("governance_verdict"), Mapping):
        reasons.append("governance_verdict_missing")
    if not isinstance(envelope.get("rollback_handle"), Mapping):
        reasons.append("rollback_handle_missing")
    if not _is_hex64(_text(envelope.get("ipc_response_hash"))):
        reasons.append("ipc_response_hash_missing_or_malformed")
    if "ipc_response_status" not in envelope:
        reasons.append("ipc_response_status_missing")
    if not isinstance(envelope.get("post_change_review"), Mapping):
        reasons.append("post_change_review_missing")
    if not isinstance(envelope.get("proof_linkage"), Mapping):
        reasons.append("proof_linkage_missing")
    if not isinstance(envelope.get("answers"), Mapping):
        reasons.append("answers_missing")
    return tuple(reasons)


def _countability(envelope: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if _text(envelope.get("engine_mode")) != ENGINE_MODE_DEMO:
        reasons.append("engine_mode_not_demo")
    application = _mapping(envelope.get("application"))
    status = _text(application.get("status") or envelope.get("application_status"))
    if status not in _COUNTABLE_APPLICATION_STATUSES:
        reasons.append(f"application_status_not_applied:{status or 'missing'}")
    if _truthy(application.get("dedupe") or envelope.get("dedupe")):
        reasons.append("dedupe_true")
    if _truthy(application.get("dry_run") or envelope.get("dry_run")):
        reasons.append("dry_run_true")

    patch = envelope.get("proposed_patch")
    if not isinstance(patch, Mapping) or not _flatten_patch(patch):
        reasons.append("proposed_patch_empty")

    previous = envelope.get("previous_snapshot")
    if not isinstance(previous, Mapping) or not previous:
        reasons.append("previous_snapshot_empty")

    delta_rows = _delta_rows(envelope.get("bounded_delta"))
    if not delta_rows:
        reasons.append("bounded_delta_empty")
    else:
        reasons.extend(_delta_countability_reasons(delta_rows))

    policy = envelope.get("max_delta_policy")
    if not isinstance(policy, Mapping) or not policy:
        reasons.append("max_delta_policy_missing")

    if not _governance_allows_review(envelope.get("governance_verdict")):
        reasons.append("governance_verdict_not_allowing_review")
    if not _rollback_present(envelope.get("rollback_handle")):
        reasons.append("rollback_handle_missing")
    if not _ipc_status_ok(envelope.get("ipc_response_status")):
        reasons.append("ipc_response_status_not_success")
    if not _post_review_passed(envelope.get("post_change_review")):
        reasons.append("post_change_review_not_passed")
    if not _proof_linkage_valid(envelope.get("proof_linkage")):
        reasons.append("proof_linkage_not_valid")
    return not reasons, reasons


def _delta_countability_reasons(delta_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for index, row in enumerate(delta_rows):
        prefix = f"bounded_delta[{index}]"
        if not _text(row.get("path")):
            reasons.append(f"{prefix}_path_missing")
        if row.get("previous_value_present") is False:
            reasons.append(f"{prefix}_previous_value_missing")
        if "previous_value" not in row:
            reasons.append(f"{prefix}_previous_value_missing")
        if "proposed_value" not in row:
            reasons.append(f"{prefix}_proposed_value_missing")
        if "delta" not in row:
            reasons.append(f"{prefix}_delta_missing")
        if "max_delta_pct" not in row and "max_delta" not in row:
            reasons.append(f"{prefix}_max_delta_policy_missing")
        elif not _has_concrete_max_delta_bound(row):
            reasons.append(f"{prefix}_max_delta_policy_not_concrete")
        if row.get("within_policy") is not True:
            reasons.append(f"{prefix}_outside_max_delta_policy")
    return reasons


def _governance_allows_review(value: Any) -> bool:
    data = _mapping(value)
    if not data:
        return False
    if data.get("allowing_review") is True or data.get("review_allowed") is True:
        return True
    verdict = _text(data.get("verdict") or data.get("status"))
    return verdict in _GOVERNANCE_ALLOW_STATUSES


def _rollback_present(value: Any) -> bool:
    data = _mapping(value)
    if not data:
        return False
    if data.get("available") is False or data.get("present") is False:
        return False
    return any(_text(data.get(key)) for key in ("rollback_id", "rollback_ref", "handle_id", "ref"))


def _ipc_status_ok(value: Any) -> bool:
    return _text(value) in _IPC_SUCCESS_STATUSES


def _post_review_passed(value: Any) -> bool:
    data = _mapping(value)
    if not data:
        return False
    if data.get("passed") is True:
        return True
    return _text(data.get("status") or data.get("verdict")) in _POST_REVIEW_PASS_STATUSES


def _proof_linkage_valid(value: Any) -> bool:
    data = _mapping(value)
    if not data or data.get("valid") is not True:
        return False
    return any(
        _text(data.get(key))
        for key in ("proof_packet_hash", "proof_ref", "proof_linkage_id", "artifact_hash")
    )


def _authority_violations(value: Any, path: str = "$") -> tuple[str, ...]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            norm = _normalized_key(key)
            child_path = f"{path}.{key}"
            if _is_forbidden_authority_key(norm) and _truthy(child):
                violations.append(child_path)
            violations.extend(_authority_violations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_authority_violations(child, f"{path}[{index}]"))
    return tuple(violations)


def _is_forbidden_authority_key(norm_key: str) -> bool:
    if norm_key.startswith(("no_", "not_")):
        return False
    if norm_key in _DIRECT_AUTHORITY_KEYS:
        return True
    tokens = set(_key_tokens(norm_key))
    if not tokens:
        return False
    has_dimension = bool(tokens & _AUTHORITY_DIMENSION_TOKENS)
    if "cost" in tokens and "gate" in tokens:
        has_dimension = True
    if "demo" in tokens and "mutation" in tokens:
        has_dimension = True
    if "strategy" in tokens and "config" in tokens:
        has_dimension = True
    if not has_dimension:
        return False
    return bool(tokens & _AUTHORITY_ACTION_TOKENS)


def _non_demo_scope_reasons(value: Any, path: str = "$") -> tuple[str, ...]:
    reasons: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            norm = _normalized_key(key)
            child_path = f"{path}.{key}"
            if _is_scope_key(norm) and _text(child) in _NON_DEMO_SCOPE_VALUES:
                reasons.append(f"non_demo_scope:{child_path}={_text(child)}")
            reasons.extend(_non_demo_scope_reasons(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reasons.extend(_non_demo_scope_reasons(child, f"{path}[{index}]"))
    return tuple(reasons)


def _engine_mode_reasons(envelope: Mapping[str, Any]) -> tuple[str, ...]:
    engine_mode = _text(envelope.get("engine_mode"))
    if engine_mode != ENGINE_MODE_DEMO:
        return (f"non_demo_scope:$.engine_mode={engine_mode or 'missing'}",)
    return ()


def _flatten_patch(value: Mapping[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(child, Mapping) and child:
            rows.extend(_flatten_patch(child, path))
        else:
            rows.append((path, child))
    return rows


def _get_path(value: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _policy_max_delta_bound(policy: Mapping[str, Any], path: str, key: str) -> float | None:
    per_path = _mapping(policy.get("per_path"))
    path_policy = per_path.get(path)
    if isinstance(path_policy, Mapping):
        raw = path_policy.get(key, policy.get(key))
    elif path_policy is not None and key == "max_delta_pct":
        raw = path_policy
    else:
        raw = policy.get(key)
    return _finite_number(raw, nonnegative=True)


def _within_delta_policy(
    *,
    delta_value: Any,
    delta_pct: float | None,
    max_delta: float | None,
    max_delta_pct: float | None,
) -> bool:
    if max_delta_pct is not None and delta_pct is not None:
        return delta_pct <= max_delta_pct + 1e-12
    delta_abs = _absolute_finite_number(delta_value)
    if max_delta is not None and delta_abs is not None:
        return delta_abs <= max_delta + 1e-12
    return False


def _has_concrete_max_delta_bound(row: Mapping[str, Any]) -> bool:
    return any(
        _finite_number(row.get(key), nonnegative=True) is not None
        for key in ("max_delta_pct", "max_delta")
    )


def _finite_number(value: Any, *, nonnegative: bool = False) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or (nonnegative and number < 0):
        return None
    return number


def _absolute_finite_number(value: Any) -> float | None:
    number = _finite_number(value)
    return abs(number) if number is not None else None


def _is_scope_key(norm_key: str) -> bool:
    return norm_key in _SCOPE_KEYS or bool(
        set(_key_tokens(norm_key)) & {"scope", "engine_mode", "mode", "environment", "env"}
    )


def _delta(previous_value: Any, proposed_value: Any) -> tuple[Any, float | None]:
    try:
        previous = float(previous_value)
        proposed = float(proposed_value)
    except (TypeError, ValueError):
        return ("unchanged" if previous_value == proposed_value else "changed"), None
    if not math.isfinite(previous) or not math.isfinite(proposed):
        return None, None
    delta_value = proposed - previous
    if previous == 0:
        delta_pct = 0.0 if proposed == 0 else None
    else:
        delta_pct = abs(delta_value) / abs(previous)
    return delta_value, delta_pct


def _delta_rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _strip_sha256_prefix(value: str | None) -> str:
    text = _text(value)
    return text.removeprefix("sha256:")


def _is_hex64(value: str) -> bool:
    return _HEX64_RE.fullmatch(_strip_sha256_prefix(value)) is not None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
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


def _result(
    valid: bool,
    status: str,
    reason: str,
    reasons: tuple[str, ...] | None = None,
    *,
    effective_learning_countable: bool = False,
    authority_boundary_violation: bool = False,
) -> DemoMutationEnvelopeValidation:
    return DemoMutationEnvelopeValidation(
        valid=valid,
        status=status,
        reason=reason,
        reasons=tuple(reasons or (() if reason == "ok" else (reason,))),
        effective_learning_countable=effective_learning_countable,
        authority_boundary_violation=authority_boundary_violation,
    )


__all__ = [
    "APPLICATION_STATUS_APPLIED",
    "APPLICATION_STATUS_DRY_RUN",
    "APPLICATION_STATUS_FAILED",
    "APPLICATION_STATUS_SKIPPED",
    "DEMO_MUTATION_ENVELOPE_FIELD",
    "DEMO_MUTATION_ENVELOPE_SCHEMA_VERSION",
    "DemoMutationEnvelopeValidation",
    "ENGINE_MODE_DEMO",
    "STATUS_AUDIT_ONLY",
    "STATUS_COUNTABLE",
    "STATUS_INVALID",
    "STATUS_PENDING_SCHEMA",
    "build_bounded_delta",
    "build_demo_mutation_envelope",
    "compute_demo_mutation_envelope_hash",
    "extract_demo_mutation_envelope",
    "stable_sha256_json",
    "validate_demo_mutation_envelope",
]
