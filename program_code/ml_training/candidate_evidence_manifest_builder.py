"""
MODULE_NOTE
模塊用途：把 MLDE source row / payload 中的真實欄位整理成
CandidateEvidenceManifest builder 結果。
主要類/函數：CandidateEvidenceManifestBuild、
build_candidate_evidence_manifest_from_source。
依賴：candidate_evidence_manifest validator 與 residual alpha report 契約；
不讀 DB、不查 replay registry、不連 runtime。
硬邊界：只接受 canonical manifest 或明確 source fields；缺 hidden OOS /
lineage / residual 時只能 downgrade，不能生成 fake promotion evidence。
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

try:
    from .candidate_signal_spec import (
        compute_signal_spec_hash,
        extract_signal_spec,
    )
    from .candidate_evidence_manifest import (
        CANDIDATE_EVIDENCE_MANIFEST_SCHEMA_VERSION,
        PROMOTION_READY,
        CandidateEvidenceManifestValidation,
        compute_candidate_evidence_manifest_hash,
        extract_candidate_evidence_manifest,
        validate_candidate_evidence_manifest,
    )
except ImportError:  # pragma: no cover - direct script execution fallback
    from candidate_signal_spec import (  # type: ignore
        compute_signal_spec_hash,
        extract_signal_spec,
    )
    from candidate_evidence_manifest import (  # type: ignore
        CANDIDATE_EVIDENCE_MANIFEST_SCHEMA_VERSION,
        PROMOTION_READY,
        CandidateEvidenceManifestValidation,
        compute_candidate_evidence_manifest_hash,
        extract_candidate_evidence_manifest,
        validate_candidate_evidence_manifest,
    )


@dataclass(frozen=True)
class CandidateEvidenceManifestBuild:
    """Producer 側 manifest 解析結果；只有 validation 通過才可放入 payload。"""

    manifest: dict[str, Any] | None
    validation: CandidateEvidenceManifestValidation
    source: str
    signal_spec: dict[str, Any] | None = None
    downgrade_reason: str | None = None


def build_candidate_evidence_manifest_from_source(
    *,
    source_row: Mapping[str, Any],
    residual_report: Mapping[str, Any] | None,
) -> CandidateEvidenceManifestBuild:
    """從 source row / payload 建立或驗證 CandidateEvidenceManifest。

    規則：
    - row-level canonical manifest 優先於 payload manifest。
    - canonical manifest 只驗證，不修補。
    - 無 canonical manifest 時，只用明確欄位建 draft；缺欄位則 downgrade。
    - row-level replay manifest hash 只作 lineage 欄位，不可當 candidate
      manifest 的 ``manifest_hash``。
    """
    source_payload = _mapping(source_row.get("payload"))
    signal_spec = _extract_signal_spec_from_sources(source_row, source_payload)

    row_manifest = extract_candidate_evidence_manifest(source_row)
    if row_manifest is not None:
        return _build_from_existing_manifest(
            row_manifest,
            residual_report=residual_report,
            signal_spec=signal_spec,
            source="source_row_manifest",
        )

    payload_manifest = extract_candidate_evidence_manifest(source_payload)
    if payload_manifest is not None:
        return _build_from_existing_manifest(
            payload_manifest,
            residual_report=residual_report,
            signal_spec=signal_spec,
            source="payload_manifest",
        )

    draft = _draft_manifest_from_fields(
        source_row,
        source_payload,
        residual_report,
        signal_spec=signal_spec,
    )
    if "replay_manifest_hash" not in draft:
        validation = CandidateEvidenceManifestValidation(
            promotion_ready=False,
            verdict="pending_schema",
            reason="replay_manifest_hash_missing",
            reasons=("replay_manifest_hash_missing",),
            lineage_downgraded=True,
        )
        return CandidateEvidenceManifestBuild(
            manifest=None,
            validation=validation,
            source="source_fields_downgraded",
            signal_spec=signal_spec,
            downgrade_reason=validation.reason,
        )
    draft["manifest_hash"] = compute_candidate_evidence_manifest_hash(draft)
    validation = validate_candidate_evidence_manifest(
        draft,
        residual_report=residual_report,
        signal_spec=signal_spec,
    )
    if validation.promotion_ready:
        return CandidateEvidenceManifestBuild(
            manifest=draft,
            validation=validation,
            source="source_fields",
            signal_spec=signal_spec,
        )
    return CandidateEvidenceManifestBuild(
        manifest=None,
        validation=validation,
        source="source_fields_downgraded",
        signal_spec=signal_spec,
        downgrade_reason=validation.reason,
    )


def _build_from_existing_manifest(
    manifest: Any,
    *,
    residual_report: Mapping[str, Any] | None,
    signal_spec: dict[str, Any] | None,
    source: str,
) -> CandidateEvidenceManifestBuild:
    validation = validate_candidate_evidence_manifest(
        manifest,
        residual_report=residual_report,
        signal_spec=signal_spec,
    )
    manifest_dict = copy.deepcopy(dict(manifest)) if isinstance(manifest, Mapping) else None
    return CandidateEvidenceManifestBuild(
        manifest=manifest_dict if validation.promotion_ready else None,
        validation=validation,
        source=source,
        signal_spec=signal_spec,
        downgrade_reason=None if validation.promotion_ready else validation.reason,
    )


def _draft_manifest_from_fields(
    source_row: Mapping[str, Any],
    source_payload: Mapping[str, Any],
    residual_report: Mapping[str, Any] | None,
    *,
    signal_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    candidate_spec = _mapping(source_payload.get("candidate_spec"))
    signal_spec_mapping = _mapping(signal_spec)

    hidden_oos = _first_mapping(
        source_payload.get("hidden_oos"),
        source_payload.get("candidate_hidden_oos"),
        candidate_spec.get("hidden_oos"),
        signal_spec_mapping.get("hidden_oos"),
    )

    manifest: dict[str, Any] = {
        "schema_version": CANDIDATE_EVIDENCE_MANIFEST_SCHEMA_VERSION,
        "verdict": PROMOTION_READY,
    }
    _put_if_present(
        manifest,
        "candidate_id",
        _first_text(
            source_row.get("candidate_id"),
            source_payload.get("candidate_id"),
            candidate_spec.get("candidate_id"),
        ),
    )
    _put_if_present(
        manifest,
        "family_id",
        _first_text(
            source_row.get("family_id"),
            source_row.get("candidate_family_id"),
            source_payload.get("family_id"),
            source_payload.get("candidate_family_id"),
            candidate_spec.get("family_id"),
        ),
    )
    _put_if_present(
        manifest,
        "spec_hash",
        compute_signal_spec_hash(signal_spec_mapping)
        if signal_spec_mapping
        else _first_text(
            source_row.get("spec_hash"),
            source_row.get("signal_spec_hash"),
            source_payload.get("spec_hash"),
            source_payload.get("signal_spec_hash"),
            source_payload.get("factor_spec_hash"),
            candidate_spec.get("spec_hash"),
        ),
    )
    _put_if_present(
        manifest,
        "replay_experiment_id",
        _first_text(
            source_row.get("replay_experiment_id"),
            source_payload.get("replay_experiment_id"),
        ),
    )
    if hidden_oos is not None:
        manifest["hidden_oos"] = copy.deepcopy(dict(hidden_oos))

    replay_manifest_hash = _first_text(
        source_row.get("manifest_hash"),
        source_payload.get("replay_manifest_hash"),
        source_payload.get("source_replay_manifest_hash"),
    )
    _put_if_present(manifest, "replay_manifest_hash", replay_manifest_hash)

    residual_hash = _canonical_sha256(dict(residual_report)) if residual_report else ""
    _put_if_present(manifest, "demo_residual_alpha_report_hash", residual_hash)
    return manifest


def _extract_signal_spec_from_sources(
    source_row: Mapping[str, Any],
    source_payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    row_signal_spec = extract_signal_spec(source_row)
    if isinstance(row_signal_spec, Mapping):
        return copy.deepcopy(dict(row_signal_spec))
    payload_signal_spec = extract_signal_spec(source_payload)
    if isinstance(payload_signal_spec, Mapping):
        return copy.deepcopy(dict(payload_signal_spec))
    return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_mapping(*values: Any) -> Mapping[str, Any] | None:
    for value in values:
        if isinstance(value, Mapping):
            return value
    return None


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.hex()
    return str(value).strip()


def _put_if_present(target: dict[str, Any], key: str, value: str) -> None:
    if value:
        target[key] = value


def _canonical_sha256(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "CandidateEvidenceManifestBuild",
    "build_candidate_evidence_manifest_from_source",
]
