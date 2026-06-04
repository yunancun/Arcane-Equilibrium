"""
MODULE_NOTE
模塊用途：MLDE producer 側 CandidateEvidenceManifest source contract。
主要類/函數：CandidateEvidenceSourceContractBuild、
build_live_candidate_evidence_from_source。
依賴：candidate manifest builder / validator 與 residual alpha report 契約；
不讀 DB、不查 replay registry、不連 runtime。
硬邊界：live candidate producer 只接受 row-level replay lineage 與 canonical
residual report；payload lineage / alias / synthetic / real_outcome 不可升級成
promotion-ready evidence。
"""

from __future__ import annotations

import copy
import datetime as _dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

try:
    from .candidate_evidence_manifest import (
        INVALID,
        PENDING_SCHEMA,
        RESEARCH_ONLY,
        CandidateEvidenceManifestValidation,
    )
    from .candidate_evidence_manifest_builder import (
        CandidateEvidenceManifestBuild,
        build_candidate_evidence_manifest_from_source,
    )
    from .residual_alpha_report_contract import (
        extract_demo_residual_alpha_report,
        validate_demo_residual_alpha_report,
    )
except ImportError:  # pragma: no cover - direct script execution fallback
    from candidate_evidence_manifest import (  # type: ignore
        INVALID,
        PENDING_SCHEMA,
        RESEARCH_ONLY,
        CandidateEvidenceManifestValidation,
    )
    from candidate_evidence_manifest_builder import (  # type: ignore
        CandidateEvidenceManifestBuild,
        build_candidate_evidence_manifest_from_source,
    )
    from residual_alpha_report_contract import (  # type: ignore
        extract_demo_residual_alpha_report,
        validate_demo_residual_alpha_report,
    )


PROMOTION_EVIDENCE_SOURCE_TIERS: tuple[str, ...] = (
    "calibrated_replay",
    "counterfactual_replay",
)
PROMOTION_REPLAY_REGISTRY_STATUSES: tuple[str, ...] = ("completed",)


@dataclass(frozen=True)
class CandidateEvidenceSourceContractBuild:
    """Producer source contract 結果；promotion_ready 才可寫 live candidate。"""

    manifest: dict[str, Any] | None
    residual_report: dict[str, Any] | None
    validation: CandidateEvidenceManifestValidation
    manifest_build: CandidateEvidenceManifestBuild | None
    source_tier: str
    replay_experiment_id: str
    replay_manifest_hash: str


def build_live_candidate_evidence_from_source(
    source_row: Mapping[str, Any],
) -> CandidateEvidenceSourceContractBuild:
    """從 MLDE source row 產生 live-candidate evidence。

    與低階 builder 的差別：低階 builder 只整理欄位；本函數是 producer gate。
    它要求 row-level replay lineage 已由上游 SELECT / schema contract 提供，
    並禁止用 payload ``lineage`` 或 alias 欄位補洞。
    """
    residual_report = _extract_residual_report_from_source_row(source_row)
    residual_ok, residual_reason = validate_demo_residual_alpha_report(
        residual_report
    )
    if not residual_ok:
        return _contract_result(
            reason=f"residual_alpha:{residual_reason}",
            verdict=INVALID,
            residual_report=residual_report,
        )

    source_tier = _text(source_row.get("evidence_source_tier"))
    if source_tier not in PROMOTION_EVIDENCE_SOURCE_TIERS:
        verdict = RESEARCH_ONLY if source_tier == "synthetic_replay" else PENDING_SCHEMA
        return _contract_result(
            reason=f"evidence_source_tier_not_promotion_ready:{source_tier or 'missing'}",
            verdict=verdict,
            residual_report=residual_report,
            source_tier=source_tier,
        )

    replay_experiment_id = _text(source_row.get("replay_experiment_id"))
    if not replay_experiment_id:
        return _contract_result(
            reason="source_replay_experiment_id_missing",
            verdict=PENDING_SCHEMA,
            residual_report=residual_report,
            source_tier=source_tier,
            lineage_downgraded=True,
        )

    replay_manifest_hash = _text(source_row.get("manifest_hash"))
    if not replay_manifest_hash:
        return _contract_result(
            reason="source_replay_manifest_hash_missing",
            verdict=PENDING_SCHEMA,
            residual_report=residual_report,
            source_tier=source_tier,
            replay_experiment_id=replay_experiment_id,
            lineage_downgraded=True,
        )

    registry_validation = _validate_replay_registry_snapshot(
        source_row=source_row,
        replay_manifest_hash=replay_manifest_hash,
    )
    if registry_validation is not None:
        reason, verdict = registry_validation
        return _contract_result(
            reason=reason,
            verdict=verdict,
            residual_report=residual_report,
            source_tier=source_tier,
            replay_experiment_id=replay_experiment_id,
            replay_manifest_hash=replay_manifest_hash,
            lineage_downgraded=verdict == PENDING_SCHEMA,
        )

    hydrated_source_row = _source_row_with_registry_hidden_oos(source_row)
    manifest_build = build_candidate_evidence_manifest_from_source(
        source_row=hydrated_source_row,
        residual_report=residual_report,
    )
    if not manifest_build.validation.promotion_ready or manifest_build.manifest is None:
        return CandidateEvidenceSourceContractBuild(
            manifest=None,
            residual_report=residual_report,
            validation=manifest_build.validation,
            manifest_build=manifest_build,
            source_tier=source_tier,
            replay_experiment_id=replay_experiment_id,
            replay_manifest_hash=replay_manifest_hash,
        )

    manifest = manifest_build.manifest
    if not _manifest_hidden_oos_matches_registry(manifest, source_row):
        return _contract_result(
            reason="hidden_oos_registry_window_mismatch",
            verdict=INVALID,
            residual_report=residual_report,
            manifest_build=manifest_build,
            source_tier=source_tier,
            replay_experiment_id=replay_experiment_id,
            replay_manifest_hash=replay_manifest_hash,
        )
    if _text(manifest.get("replay_experiment_id")) != replay_experiment_id:
        return _contract_result(
            reason="replay_experiment_id_source_mismatch",
            verdict=INVALID,
            residual_report=residual_report,
            manifest_build=manifest_build,
            source_tier=source_tier,
            replay_experiment_id=replay_experiment_id,
            replay_manifest_hash=replay_manifest_hash,
        )
    if _text(manifest.get("replay_manifest_hash")) != replay_manifest_hash:
        return _contract_result(
            reason="replay_manifest_hash_source_mismatch",
            verdict=INVALID,
            residual_report=residual_report,
            manifest_build=manifest_build,
            source_tier=source_tier,
            replay_experiment_id=replay_experiment_id,
            replay_manifest_hash=replay_manifest_hash,
        )

    return CandidateEvidenceSourceContractBuild(
        manifest=manifest,
        residual_report=residual_report,
        validation=manifest_build.validation,
        manifest_build=manifest_build,
        source_tier=source_tier,
        replay_experiment_id=replay_experiment_id,
        replay_manifest_hash=replay_manifest_hash,
    )


def _manifest_hidden_oos_matches_registry(
    manifest: Mapping[str, Any],
    source_row: Mapping[str, Any],
) -> bool:
    hidden = manifest.get("hidden_oos")
    if not isinstance(hidden, Mapping):
        return False
    return _time_equivalent(
        hidden.get("window_start"),
        source_row.get("replay_registry_oos_label_window_start"),
    ) and _time_equivalent(
        hidden.get("window_end"),
        source_row.get("replay_registry_oos_label_window_end"),
    )


def _validate_replay_registry_snapshot(
    *,
    source_row: Mapping[str, Any],
    replay_manifest_hash: str,
) -> tuple[str, str] | None:
    registry_hash = _text(source_row.get("replay_registry_manifest_hash"))
    if not registry_hash:
        return "replay_registry_manifest_hash_missing", PENDING_SCHEMA
    if registry_hash != replay_manifest_hash:
        return "replay_registry_manifest_hash_mismatch", INVALID

    registry_status = _text(source_row.get("replay_registry_status"))
    if not registry_status:
        return "replay_registry_status_missing", PENDING_SCHEMA
    if registry_status not in PROMOTION_REPLAY_REGISTRY_STATUSES:
        return f"replay_registry_status_not_completed:{registry_status}", RESEARCH_ONLY

    registry_expires_at = source_row.get("replay_registry_expires_at")
    if not _text(registry_expires_at):
        return "replay_registry_expires_at_missing", PENDING_SCHEMA
    if _is_expired(registry_expires_at):
        return "replay_registry_expired", RESEARCH_ONLY

    if not isinstance(source_row.get("replay_registry_manifest_jsonb"), Mapping):
        return "replay_registry_manifest_jsonb_missing", PENDING_SCHEMA

    required_fields = (
        "replay_registry_oos_label_window_start",
        "replay_registry_oos_label_window_end",
        "replay_registry_oos_embargo_seconds",
        "replay_registry_total_candidates_k",
    )
    for field in required_fields:
        if not _text(source_row.get(field)):
            return f"{field}_missing", PENDING_SCHEMA

    return None


def _source_row_with_registry_hidden_oos(
    source_row: Mapping[str, Any],
) -> dict[str, Any]:
    """用 replay.experiments snapshot 覆寫 hidden_oos 欄位。"""
    row = dict(source_row)
    payload = source_row.get("payload")
    payload_dict = copy.deepcopy(dict(payload)) if isinstance(payload, Mapping) else {}
    payload_dict["hidden_oos"] = {
        "split_hash": _text(source_row.get("replay_registry_manifest_hash")),
        "window_start": _text(source_row.get("replay_registry_oos_label_window_start")),
        "window_end": _text(source_row.get("replay_registry_oos_label_window_end")),
        "embargo": f"{_text(source_row.get('replay_registry_oos_embargo_seconds'))}s",
        "trial_count": _text(source_row.get("replay_registry_total_candidates_k")),
        "passes": True,
    }
    row["payload"] = payload_dict
    return row


def _extract_residual_report_from_source_row(
    source_row: Mapping[str, Any],
) -> dict[str, Any] | None:
    report = extract_demo_residual_alpha_report(source_row)
    if isinstance(report, dict):
        return report
    payload = source_row.get("payload")
    if isinstance(payload, Mapping):
        report = extract_demo_residual_alpha_report(payload)
        if isinstance(report, dict):
            return report
    return None


def _contract_result(
    *,
    reason: str,
    verdict: str,
    residual_report: dict[str, Any] | None,
    manifest_build: CandidateEvidenceManifestBuild | None = None,
    source_tier: str = "",
    replay_experiment_id: str = "",
    replay_manifest_hash: str = "",
    lineage_downgraded: bool = False,
) -> CandidateEvidenceSourceContractBuild:
    validation = CandidateEvidenceManifestValidation(
        promotion_ready=False,
        verdict=verdict,
        reason=reason,
        reasons=(reason,),
        lineage_downgraded=lineage_downgraded,
    )
    return CandidateEvidenceSourceContractBuild(
        manifest=None,
        residual_report=residual_report,
        validation=validation,
        manifest_build=manifest_build,
        source_tier=source_tier,
        replay_experiment_id=replay_experiment_id,
        replay_manifest_hash=replay_manifest_hash,
    )


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, _dt.datetime):
        return value.isoformat()
    return str(value).strip()


def _is_expired(value: Any) -> bool:
    if isinstance(value, _dt.datetime):
        ts = value
    else:
        text = _text(value)
        if not text:
            return False
        normalized = text.replace("Z", "+00:00")
        try:
            ts = _dt.datetime.fromisoformat(normalized)
        except ValueError:
            return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_dt.timezone.utc)
    return ts <= _dt.datetime.now(_dt.timezone.utc)


def _time_equivalent(left: Any, right: Any) -> bool:
    left_ts = _parse_datetime(left)
    right_ts = _parse_datetime(right)
    if left_ts is not None and right_ts is not None:
        return left_ts == right_ts
    return _text(left) == _text(right)


def _parse_datetime(value: Any) -> _dt.datetime | None:
    if isinstance(value, _dt.datetime):
        ts = value
    else:
        text = _text(value)
        if not text:
            return None
        try:
            ts = _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_dt.timezone.utc)
    return ts.astimezone(_dt.timezone.utc)


__all__ = [
    "PROMOTION_EVIDENCE_SOURCE_TIERS",
    "PROMOTION_REPLAY_REGISTRY_STATUSES",
    "CandidateEvidenceSourceContractBuild",
    "build_live_candidate_evidence_from_source",
]
