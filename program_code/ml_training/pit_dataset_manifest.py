"""
MODULE_NOTE
模塊用途：AI/ML roadmap 的 pit_dataset_manifest_v1 source-only contract。
主要類/函數：PitDatasetManifestValidation、
validate_pit_dataset_manifest、compute_pit_dataset_manifest_hash、
extract_pit_dataset_manifest。
依賴：僅 Python 標準庫；不讀 DB、不連 runtime、不呼叫交易所。
硬邊界：本模塊只驗證 caller 提供的 point-in-time dataset manifest
是否完整、可重建、無資料洩漏跡象；不可授予 order、probe、runtime、
DB、Cost Gate、deploy、live/mainnet authority。
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


PIT_DATASET_MANIFEST_FIELD = "pit_dataset_manifest"
PIT_DATASET_MANIFEST_SCHEMA_VERSION = "pit_dataset_manifest_v1"

DATASET_READY = "dataset_ready"
RESEARCH_ONLY = "research_only"
PENDING_SCHEMA = "pending_schema"
INVALID = "invalid"

_ALLOWED_VERDICTS = {DATASET_READY, RESEARCH_ONLY, PENDING_SCHEMA, INVALID}
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")
_TRUTHY_STRINGS = {"1", "true", "yes", "y", "on", "enabled", "grant", "granted"}

_AUTHORITY_TRUE_KEYS = {
    "cost_gate_change_performed",
    "cost_gate_lowering_performed",
    "cost_gate_lowering_recommended",
    "db_read_performed",
    "db_write_performed",
    "deploy_performed",
    "exchange_private_read_performed",
    "live_authority_granted",
    "live_or_mainnet_performed",
    "mainnet_performed",
    "mcp_server_started",
    "order_authority_granted",
    "order_performed",
    "private_read_performed",
    "probe_authority_granted",
    "probe_performed",
    "runtime_mutation_performed",
    "secret_access_performed",
}
_AUTHORITY_KEY_TERMS = (
    "cost",
    "db",
    "deploy",
    "live",
    "mainnet",
    "mcp",
    "order",
    "private",
    "probe",
    "runtime",
    "secret",
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
    "read",
    "start",
    "started",
    "write",
)
_UNPINNED_QUERY_TOKENS = (
    "now()",
    "current_timestamp",
    "current_date",
    "latest",
    "max_age_days",
)
_ROW_EXCLUSION_TOKENS = (
    "cleanup",
    "proof_excluded",
    "proof-excluded",
    "proof excluded",
    "unattributed",
)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\b[A-Z0-9_]*API[_-]?KEY\s*[:=]", re.IGNORECASE),
    re.compile(r"\bAPI[_-]?SECRET\s*[:=]", re.IGNORECASE),
    re.compile(r"\bSECRET[_-]?KEY\s*[:=]", re.IGNORECASE),
    re.compile(r"\bDATABASE_URL\s*[:=]", re.IGNORECASE),
    re.compile(r"\b(?:postgres|postgresql|mysql|redis|mongodb)://", re.IGNORECASE),
    re.compile(r"://[^/\s:@]+:[^/\s:@]+@"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
)
_SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|api[_-]?secret|secret[_-]?key|password|passwd|"
    r"database_url|dsn|authorization|bearer_token)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PitDatasetManifestValidation:
    """PIT manifest 驗證結果；caller 只能用 dataset_ready 放行訓練資料。"""

    dataset_ready: bool
    verdict: str
    reason: str
    reasons: tuple[str, ...]
    authority_boundary_violation: bool = False
    secret_leak_detected: bool = False


def extract_pit_dataset_manifest(mapping: Any) -> Any:
    """只讀 canonical ``pit_dataset_manifest`` 欄位，不接受 alias。"""
    if not isinstance(mapping, Mapping):
        return None
    return mapping.get(PIT_DATASET_MANIFEST_FIELD)


def compute_pit_dataset_manifest_hash(manifest: Mapping[str, Any]) -> str:
    """對 manifest 做 canonical JSON sha256；頂層 ``manifest_hash`` 不入 hash。"""
    payload = copy.deepcopy(dict(manifest))
    payload.pop("manifest_hash", None)
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_pit_dataset_manifest(manifest: Any) -> PitDatasetManifestValidation:
    """驗證 ``pit_dataset_manifest_v1`` 是否可作 point-in-time dataset input。

    本函數不證明 DB / runtime 事實，只驗證 caller 已提供 artifact 的
    schema、hash、PIT cutoff、rebuild 與 leakage evidence 是否足以被下游
    source-only gate 消費。
    """
    if manifest is None:
        return _result(PENDING_SCHEMA, "pit_dataset_manifest_missing")
    if not isinstance(manifest, Mapping):
        return _result(INVALID, "pit_dataset_manifest_not_mapping")

    authority_violations = _authority_violations(manifest)
    if authority_violations:
        return _result(
            INVALID,
            f"authority_boundary_violation:{authority_violations[0]}",
            tuple(f"authority_boundary_violation:{item}" for item in authority_violations),
            authority_boundary_violation=True,
        )

    secret_leaks = _secret_leak_reasons(manifest)
    if secret_leaks:
        return _result(
            INVALID,
            secret_leaks[0],
            secret_leaks,
            secret_leak_detected=True,
        )

    row_exclusions = _row_exclusion_reasons(manifest)
    if row_exclusions:
        return _result(INVALID, row_exclusions[0], row_exclusions)

    malformed_hashes = _malformed_hash_reasons(manifest)
    if malformed_hashes:
        return _result(INVALID, malformed_hashes[0], malformed_hashes)

    schema_version = _text(manifest.get("schema_version"))
    if schema_version != PIT_DATASET_MANIFEST_SCHEMA_VERSION:
        return _result(PENDING_SCHEMA, "schema_version_unknown")

    requested_verdict = _text(manifest.get("verdict"))
    if not requested_verdict:
        return _result(PENDING_SCHEMA, "verdict_missing")
    if requested_verdict not in _ALLOWED_VERDICTS:
        return _result(INVALID, "verdict_unknown")

    reasons: list[str] = []
    if requested_verdict != DATASET_READY:
        reasons.append(f"verdict_not_dataset_ready:{requested_verdict}")
    else:
        reasons.extend(_validate_dataset_ready_manifest(manifest))

    manifest_hash = _text(manifest.get("manifest_hash"))
    if not manifest_hash:
        reasons.append("manifest_hash_missing")
    elif not reasons:
        try:
            computed_hash = compute_pit_dataset_manifest_hash(manifest)
        except (TypeError, ValueError):
            reasons.append("manifest_hash_uncomputable")
        else:
            if manifest_hash != computed_hash:
                reasons.append("manifest_hash_mismatch")

    if reasons:
        return _result(_failure_verdict(reasons), reasons[0], reasons)

    return _result(DATASET_READY, "ok", ())


def _validate_dataset_ready_manifest(manifest: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []

    reasons.extend(_required_text_fields(manifest, "manifest", ("dataset_id", "dataset_role")))
    as_of_ts = _require_ts(manifest, "manifest", "as_of_ts", reasons)
    if "point_in_time" not in manifest:
        reasons.append("manifest_point_in_time_missing")
    elif manifest.get("point_in_time") is not True:
        reasons.append("manifest_point_in_time_not_true")
    if "future_data_allowed" not in manifest:
        reasons.append("manifest_future_data_allowed_missing")
    elif manifest.get("future_data_allowed") is not False:
        reasons.append("manifest_future_data_allowed_not_false")

    reasons.extend(_validate_candidate_scope(_mapping(manifest.get("candidate_scope"))))
    reasons.extend(_validate_source_query(_mapping(manifest.get("source_query"))))
    reasons.extend(_validate_row_set(_mapping(manifest.get("row_set")), as_of_ts))
    reasons.extend(_validate_feature_lineage(_mapping(manifest.get("feature_lineage"))))
    reasons.extend(_validate_label_lineage(_mapping(manifest.get("label_lineage")), as_of_ts))
    reasons.extend(_validate_split_lineage(_mapping(manifest.get("split_lineage"))))
    reasons.extend(_validate_leakage_evidence(_mapping(manifest.get("leakage_evidence"))))
    reasons.extend(_validate_matched_controls(_mapping(manifest.get("matched_controls"))))
    reasons.extend(
        _validate_row_backed_fill_source(_mapping(manifest.get("row_backed_fill_source")))
    )
    reasons.extend(_validate_rebuild_evidence(_mapping(manifest.get("rebuild_evidence"))))
    reasons.extend(_validate_provenance(_mapping(manifest.get("provenance"))))

    return reasons


def _validate_candidate_scope(value: Mapping[str, Any]) -> list[str]:
    if not value:
        return ["candidate_scope_missing"]
    return _required_text_fields(
        value,
        "candidate_scope",
        ("candidate_id", "strategy_name", "symbol", "side", "engine_mode"),
    )


def _validate_source_query(value: Mapping[str, Any]) -> list[str]:
    if not value:
        return ["source_query_missing"]
    reasons: list[str] = []
    reasons.extend(_required_text_fields(value, "source_query", ("query_id",)))
    reasons.extend(_required_hash_fields(value, "source_query", ("query_hash", "query_params_hash")))
    start_ts = _require_ts(value, "source_query", "start_ts", reasons)
    end_ts = _require_ts(value, "source_query", "end_ts", reasons)
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        reasons.append("source_query_start_ts_after_end_ts")
    reasons.extend(_source_query_unpinned_reasons(value))
    return reasons


def _validate_row_set(value: Mapping[str, Any], as_of_ts: datetime | None) -> list[str]:
    if not value:
        return ["row_set_missing"]
    reasons: list[str] = []
    _require_positive_int(value, "row_set", "row_count", reasons)
    reasons.extend(
        _required_hash_fields(
            value,
            "row_set",
            ("row_ids_hash", "dataset_hash", "schema_hash"),
        )
    )
    min_ts = _require_ts(value, "row_set", "min_ts", reasons)
    max_ts = _require_ts(value, "row_set", "max_ts", reasons)
    if min_ts is not None and max_ts is not None and min_ts > max_ts:
        reasons.append("row_set_min_ts_after_max_ts")
    if max_ts is not None and as_of_ts is not None and max_ts > as_of_ts:
        reasons.append("row_set_max_ts_after_as_of_ts")
    return reasons


def _validate_feature_lineage(value: Mapping[str, Any]) -> list[str]:
    if not value:
        return ["feature_lineage_missing"]
    reasons: list[str] = []
    reasons.extend(_required_text_fields(value, "feature_lineage", ("feature_schema_version",)))
    reasons.extend(
        _required_hash_fields(
            value,
            "feature_lineage",
            ("feature_schema_hash", "feature_definition_hash", "feature_names_hash"),
        )
    )
    return reasons


def _validate_label_lineage(
    value: Mapping[str, Any],
    as_of_ts: datetime | None,
) -> list[str]:
    if not value:
        return ["label_lineage_missing"]
    reasons: list[str] = []
    reasons.extend(
        _required_hash_fields(
            value,
            "label_lineage",
            ("label_schema_hash", "label_config_hash"),
        )
    )
    cutoff_ts = _require_ts(value, "label_lineage", "outcome_cutoff_ts", reasons)
    if cutoff_ts is not None and as_of_ts is not None and cutoff_ts > as_of_ts:
        reasons.append("label_lineage_outcome_cutoff_ts_after_as_of_ts")
    return reasons


def _validate_split_lineage(value: Mapping[str, Any]) -> list[str]:
    if not value:
        return ["split_lineage_missing"]
    reasons: list[str] = []
    reasons.extend(_required_text_fields(value, "split_lineage", ("split_id",)))
    reasons.extend(
        _required_hash_fields(
            value,
            "split_lineage",
            (
                "split_hash",
                "train_row_ids_hash",
                "validation_row_ids_hash",
                "test_row_ids_hash",
            ),
        )
    )
    if not any(
        ("embargo" in str(key).lower() or "purge" in str(key).lower()) and _present(child)
        for key, child in value.items()
    ):
        reasons.append("split_lineage_embargo_or_purge_missing")
    return reasons


def _validate_leakage_evidence(value: Mapping[str, Any]) -> list[str]:
    if not value:
        return ["leakage_evidence_missing"]
    reasons: list[str] = []
    reasons.extend(
        _required_hash_fields(
            value,
            "leakage_evidence",
            ("leakage_report_hash", "fold_preprocessing_stats_hash"),
        )
    )
    if "overlap_count" not in value:
        reasons.append("leakage_evidence_overlap_count_missing")
    elif _int(value.get("overlap_count")) != 0:
        reasons.append("leakage_evidence_overlap_count_not_zero")
    return reasons


def _validate_matched_controls(value: Mapping[str, Any]) -> list[str]:
    if not value:
        return ["matched_controls_missing"]
    reasons: list[str] = []
    reasons.extend(
        _required_hash_fields(
            value,
            "matched_controls",
            ("matched_control_artifact_hash", "matched_control_row_ids_hash"),
        )
    )
    _require_positive_int(value, "matched_controls", "matched_control_count", reasons)
    return reasons


def _validate_row_backed_fill_source(value: Mapping[str, Any]) -> list[str]:
    if not value:
        return ["row_backed_fill_source_missing"]
    reasons: list[str] = []
    reasons.extend(
        _required_hash_fields(
            value,
            "row_backed_fill_source",
            ("fill_source_artifact_hash", "fill_row_ids_hash"),
        )
    )
    reasons.extend(
        _required_text_fields(
            value,
            "row_backed_fill_source",
            ("fill_id_field", "order_link_id_field", "context_id_field"),
        )
    )
    return reasons


def _validate_rebuild_evidence(value: Mapping[str, Any]) -> list[str]:
    if not value:
        return ["rebuild_evidence_missing"]
    reasons: list[str] = []
    status = _text(value.get("status"))
    if not status:
        reasons.append("rebuild_evidence_status_missing")
    elif status != "rebuild_hash_match":
        reasons.append("rebuild_evidence_status_not_rebuild_hash_match")

    original_row_count = _int(value.get("original_row_count"))
    rebuilt_row_count = _int(value.get("rebuilt_row_count"))
    if original_row_count is None:
        reasons.append("rebuild_evidence_original_row_count_missing")
    if rebuilt_row_count is None:
        reasons.append("rebuild_evidence_rebuilt_row_count_missing")
    if (
        original_row_count is not None
        and rebuilt_row_count is not None
        and original_row_count != rebuilt_row_count
    ):
        reasons.append("rebuild_evidence_row_count_mismatch")

    for field in (
        "original_row_ids_hash",
        "rebuilt_row_ids_hash",
        "original_dataset_hash",
        "rebuilt_dataset_hash",
    ):
        if not _text(value.get(field)):
            reasons.append(f"rebuild_evidence_{field}_missing")
        elif not _is_hex64(_text(value.get(field))):
            reasons.append(f"rebuild_evidence_{field}_malformed")

    if _text(value.get("original_row_ids_hash")) and _text(value.get("rebuilt_row_ids_hash")):
        if value.get("original_row_ids_hash") != value.get("rebuilt_row_ids_hash"):
            reasons.append("rebuild_evidence_row_ids_hash_mismatch")
    if _text(value.get("original_dataset_hash")) and _text(value.get("rebuilt_dataset_hash")):
        if value.get("original_dataset_hash") != value.get("rebuilt_dataset_hash"):
            reasons.append("rebuild_evidence_dataset_hash_mismatch")
    return reasons


def _validate_provenance(value: Mapping[str, Any]) -> list[str]:
    if not value:
        return ["provenance_missing"]
    reasons: list[str] = []
    for field in ("code_commit", "rust_build_sha"):
        field_value = _text(value.get(field))
        if not field_value:
            reasons.append(f"provenance_{field}_missing")
        elif not _is_stable_ref(field_value):
            reasons.append(f"provenance_{field}_malformed")

    source_hashes = _mapping(value.get("source_hashes"))
    input_hashes = _mapping(value.get("input_artifact_hashes"))
    if not source_hashes:
        reasons.append("provenance_source_hashes_missing")
    else:
        reasons.extend(_validate_hash_mapping(source_hashes, "provenance_source_hashes"))
    if not input_hashes:
        reasons.append("provenance_input_artifact_hashes_missing")
    else:
        reasons.extend(
            _validate_hash_mapping(input_hashes, "provenance_input_artifact_hashes")
        )
    return reasons


def _required_text_fields(
    value: Mapping[str, Any],
    prefix: str,
    fields: tuple[str, ...],
) -> list[str]:
    return [f"{prefix}_{field}_missing" for field in fields if not _text(value.get(field))]


def _required_hash_fields(
    value: Mapping[str, Any],
    prefix: str,
    fields: tuple[str, ...],
) -> list[str]:
    reasons: list[str] = []
    for field in fields:
        field_value = _text(value.get(field))
        if not field_value:
            reasons.append(f"{prefix}_{field}_missing")
        elif not _is_hex64(field_value):
            reasons.append(f"{prefix}_{field}_malformed")
    return reasons


def _validate_hash_mapping(value: Mapping[str, Any], prefix: str) -> list[str]:
    reasons: list[str] = []
    for key, child in value.items():
        key_text = _text(key)
        if not key_text:
            reasons.append(f"{prefix}_key_missing")
        child_text = _text(child)
        if not child_text:
            reasons.append(f"{prefix}_{key_text}_missing")
        elif not _is_hex64(child_text):
            reasons.append(f"{prefix}_{key_text}_malformed")
    return reasons


def _require_ts(
    value: Mapping[str, Any],
    prefix: str,
    field: str,
    reasons: list[str],
) -> datetime | None:
    raw = _text(value.get(field))
    if not raw:
        reasons.append(f"{prefix}_{field}_missing")
        return None
    parsed = _parse_ts(raw)
    if parsed is None:
        reasons.append(f"{prefix}_{field}_invalid")
    return parsed


def _require_positive_int(
    value: Mapping[str, Any],
    prefix: str,
    field: str,
    reasons: list[str],
) -> None:
    if field not in value:
        reasons.append(f"{prefix}_{field}_missing")
        return
    parsed = _int(value.get(field))
    if parsed is None:
        reasons.append(f"{prefix}_{field}_invalid")
    elif parsed <= 0:
        reasons.append(f"{prefix}_{field}_not_positive")


def _malformed_hash_reasons(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    reasons: list[str] = []
    for path, key, value in _walk(manifest):
        if key.endswith("_hash") and _present(value) and not _is_hex64(_text(value)):
            reasons.append(f"hash_malformed:{path}")
        if key.endswith("_hashes") and _present(value):
            if not isinstance(value, Mapping):
                reasons.append(f"hash_mapping_malformed:{path}")
            else:
                for child_key, child_value in value.items():
                    child_path = f"{path}.{child_key}"
                    if not _text(child_key):
                        reasons.append(f"hash_mapping_malformed:{child_path}")
                    elif not _is_hex64(_text(child_value)):
                        reasons.append(f"hash_malformed:{child_path}")
    return tuple(sorted(set(reasons)))


def _authority_violations(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    violations: list[str] = []
    for path, key, value in _walk(manifest):
        if _is_authority_expansion_key(key) and _truthy(value):
            violations.append(path)
    return tuple(sorted(set(violations)))


def _is_authority_expansion_key(key: str) -> bool:
    key_text = key.lower()
    if key_text in _AUTHORITY_TRUE_KEYS:
        return True
    if key_text in _AUTHORITY_KEY_TERMS:
        return True
    return any(term in key_text for term in _AUTHORITY_KEY_TERMS) and any(
        action in key_text for action in _AUTHORITY_ACTION_TERMS
    )


def _secret_leak_reasons(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    reasons: list[str] = []
    for path, key, value in _walk(manifest):
        if _SENSITIVE_KEY_RE.search(key) and _present(value):
            reasons.append(f"secret_like_text_present:{path}")
            continue
        if isinstance(value, str):
            for pattern in _SECRET_VALUE_PATTERNS:
                if pattern.search(value):
                    reasons.append(f"secret_like_text_present:{path}")
                    break
    return tuple(sorted(set(reasons)))


def _row_exclusion_reasons(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    reasons: list[str] = []
    for path, key, value in _walk(manifest):
        key_text = key.lower()
        if any(token in key_text for token in _ROW_EXCLUSION_TOKENS):
            reasons.append(f"row_exclusion_indicator_present:{path}")
        if isinstance(value, str):
            value_text = value.lower()
            if any(token in value_text for token in _ROW_EXCLUSION_TOKENS):
                reasons.append(f"row_exclusion_indicator_present:{path}")
    return tuple(sorted(set(reasons)))


def _source_query_unpinned_reasons(value: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for path, key, child in _walk(value, "source_query"):
        key_text = key.lower()
        child_text = child.lower() if isinstance(child, str) else ""
        if any(token in key_text or token in child_text.lower() for token in _UNPINNED_QUERY_TOKENS):
            reasons.append(f"source_query_unpinned_relative_window:{path}")
    return sorted(set(reasons))


def _walk(value: Any, prefix: str = "") -> list[tuple[str, str, Any]]:
    found: list[tuple[str, str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            found.append((path, key_text, child))
            found.extend(_walk(child, path))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found.extend(_walk(child, f"{prefix}[{index}]"))
    return found


def _failure_verdict(reasons: list[str]) -> str:
    if any(
        reason.startswith("authority_boundary_violation:")
        or reason.startswith("secret_like_text_present:")
        or reason.startswith("row_exclusion_indicator_present:")
        or reason.startswith("hash_malformed:")
        or reason.startswith("hash_mapping_malformed:")
        or "hash_mismatch" in reason
        or "mismatch" in reason
        or reason.endswith("_malformed")
        or reason.endswith("_invalid")
        or reason.endswith("_not_true")
        or reason.endswith("_not_false")
        or reason.endswith("_not_zero")
        or reason.endswith("_not_positive")
        or reason.endswith("_after_as_of_ts")
        or reason.endswith("_after_end_ts")
        for reason in reasons
    ):
        return INVALID
    if any(reason.startswith("source_query_unpinned_relative_window:") for reason in reasons):
        return RESEARCH_ONLY
    if any(reason.startswith("verdict_not_dataset_ready:research_only") for reason in reasons):
        return RESEARCH_ONLY
    if any("_missing" in reason or reason.endswith("_not_mapping") for reason in reasons):
        return PENDING_SCHEMA
    return INVALID


def _result(
    verdict: str,
    reason: str,
    reasons: tuple[str, ...] | list[str] = (),
    *,
    authority_boundary_violation: bool = False,
    secret_leak_detected: bool = False,
) -> PitDatasetManifestValidation:
    normalized = tuple(str(item) for item in reasons) or (reason,)
    return PitDatasetManifestValidation(
        dataset_ready=verdict == DATASET_READY and reason == "ok",
        verdict=verdict,
        reason=reason,
        reasons=normalized,
        authority_boundary_violation=authority_boundary_violation,
        secret_leak_detected=secret_leak_detected,
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


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


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY_STRINGS
    return False


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _parse_ts(value: str) -> datetime | None:
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _is_hex64(value: str) -> bool:
    return bool(_HEX64_RE.match(value))


def _is_stable_ref(value: str) -> bool:
    return bool(_GIT_SHA_RE.match(value)) or _is_hex64(value)


__all__ = [
    "PIT_DATASET_MANIFEST_FIELD",
    "PIT_DATASET_MANIFEST_SCHEMA_VERSION",
    "DATASET_READY",
    "RESEARCH_ONLY",
    "PENDING_SCHEMA",
    "INVALID",
    "PitDatasetManifestValidation",
    "compute_pit_dataset_manifest_hash",
    "extract_pit_dataset_manifest",
    "validate_pit_dataset_manifest",
]
