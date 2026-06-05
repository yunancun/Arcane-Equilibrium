"""
MODULE_NOTE
模塊用途：MLDE producer 側 CandidateEvidenceManifest source contract。
主要類/函數：CandidateEvidenceSourceContractBuild、
build_live_candidate_evidence_from_source。
依賴：candidate manifest builder / validator 與 residual alpha report 契約；
不自行讀 DB、不連 runtime；只驗證 caller 已 JOIN 到 row 的 replay registry
snapshot 與 durable residual registry snapshot。
硬邊界：live candidate producer 只接受 row-level replay lineage 與 canonical
residual report；payload lineage / alias / synthetic / real_outcome 不可升級成
promotion-ready evidence。
"""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import re
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
HIDDEN_OOS_STATE_SCHEMA_VERSION = "hidden_oos_state_v1"
HIDDEN_OOS_PROMOTION_STATE = "sealed"
REGISTRY_RESIDUAL_ALPHA_HASH_FIELD = "demo_residual_alpha_report_hash"
DURABLE_RESIDUAL_ALPHA_HASH_FIELD = "durable_residual_alpha_report_hash"
DURABLE_RESIDUAL_ALPHA_REPORT_FIELD = "durable_residual_alpha_report_jsonb"
DURABLE_HIDDEN_OOS_STATE_FIELD = "durable_hidden_oos_state"
DURABLE_HIDDEN_OOS_STATE_JSONB_FIELD = "durable_hidden_oos_state_jsonb"
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CandidateEvidenceSourceContractBuild:
    """Producer source contract 結果；promotion_ready 才可寫 live candidate。"""

    manifest: dict[str, Any] | None
    residual_report: dict[str, Any] | None
    signal_spec: dict[str, Any] | None
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

    residual_registry_validation = _validate_registry_residual_report_hash(
        source_row=source_row,
        residual_report=residual_report,
    )
    if residual_registry_validation is not None:
        reason, verdict = residual_registry_validation
        return _contract_result(
            reason=reason,
            verdict=verdict,
            residual_report=residual_report,
            source_tier=source_tier,
            replay_experiment_id=replay_experiment_id,
            replay_manifest_hash=replay_manifest_hash,
            lineage_downgraded=verdict == PENDING_SCHEMA,
        )

    durable_residual_validation = _validate_durable_residual_report_snapshot(
        source_row=source_row,
        residual_report=residual_report,
    )
    if durable_residual_validation is not None:
        reason, verdict = durable_residual_validation
        return _contract_result(
            reason=reason,
            verdict=verdict,
            residual_report=residual_report,
            source_tier=source_tier,
            replay_experiment_id=replay_experiment_id,
            replay_manifest_hash=replay_manifest_hash,
            lineage_downgraded=verdict == PENDING_SCHEMA,
        )

    hidden_oos_state, hidden_oos_state_validation = _load_hidden_oos_state_snapshot(
        source_row
    )
    if hidden_oos_state_validation is not None:
        reason, verdict = hidden_oos_state_validation
        return _contract_result(
            reason=reason,
            verdict=verdict,
            residual_report=residual_report,
            source_tier=source_tier,
            replay_experiment_id=replay_experiment_id,
            replay_manifest_hash=replay_manifest_hash,
            lineage_downgraded=verdict == PENDING_SCHEMA,
        )
    assert hidden_oos_state is not None

    durable_hidden_oos_validation = _validate_durable_hidden_oos_state_snapshot(
        source_row=source_row,
        hidden_oos_state=hidden_oos_state,
    )
    if durable_hidden_oos_validation is not None:
        reason, verdict = durable_hidden_oos_validation
        return _contract_result(
            reason=reason,
            verdict=verdict,
            residual_report=residual_report,
            source_tier=source_tier,
            replay_experiment_id=replay_experiment_id,
            replay_manifest_hash=replay_manifest_hash,
            lineage_downgraded=verdict == PENDING_SCHEMA,
        )

    hydrated_source_row = _source_row_with_registry_hidden_oos(
        source_row,
        hidden_oos_state=hidden_oos_state,
    )
    manifest_build = build_candidate_evidence_manifest_from_source(
        source_row=hydrated_source_row,
        residual_report=residual_report,
    )
    if not manifest_build.validation.promotion_ready or manifest_build.manifest is None:
        return CandidateEvidenceSourceContractBuild(
            manifest=None,
            residual_report=residual_report,
            signal_spec=manifest_build.signal_spec,
            validation=manifest_build.validation,
            manifest_build=manifest_build,
            source_tier=source_tier,
            replay_experiment_id=replay_experiment_id,
            replay_manifest_hash=replay_manifest_hash,
        )

    manifest = manifest_build.manifest
    if not _manifest_hidden_oos_matches_registry(
        manifest,
        source_row,
        hidden_oos_state=hidden_oos_state,
    ):
        return _contract_result(
            reason="hidden_oos_registry_state_mismatch",
            verdict=INVALID,
            residual_report=residual_report,
            manifest_build=manifest_build,
            source_tier=source_tier,
            replay_experiment_id=replay_experiment_id,
            replay_manifest_hash=replay_manifest_hash,
        )
    if _text(manifest.get("family_id")) != _text(hidden_oos_state.get("family_id")):
        return _contract_result(
            reason="hidden_oos_state_family_id_mismatch",
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
        signal_spec=manifest_build.signal_spec,
        validation=manifest_build.validation,
        manifest_build=manifest_build,
        source_tier=source_tier,
        replay_experiment_id=replay_experiment_id,
        replay_manifest_hash=replay_manifest_hash,
    )


def _manifest_hidden_oos_matches_registry(
    manifest: Mapping[str, Any],
    source_row: Mapping[str, Any],
    *,
    hidden_oos_state: Mapping[str, Any],
) -> bool:
    hidden = manifest.get("hidden_oos")
    if not isinstance(hidden, Mapping):
        return False
    split_ref = _text(hidden.get("split_hash")) or _text(hidden.get("split_id"))
    return (
        split_ref == _text(hidden_oos_state.get("split_hash"))
        and _time_equivalent(
            hidden.get("window_start"),
            source_row.get("replay_registry_oos_label_window_start"),
        )
        and _time_equivalent(
            hidden.get("window_end"),
            source_row.get("replay_registry_oos_label_window_end"),
        )
        and _int_equivalent(
            _first_present(
                hidden.get("trial_count"),
                hidden.get("total_candidates_K"),
                hidden.get("total_candidates_k"),
                hidden.get("K"),
                hidden.get("k"),
            ),
            source_row.get("replay_registry_total_candidates_k"),
        )
        and _embargo_equivalent(
            _first_present(
                hidden.get("embargo"),
                hidden.get("purge"),
                hidden.get("purge_days"),
            ),
            source_row.get("replay_registry_oos_embargo_seconds"),
        )
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


def _validate_registry_residual_report_hash(
    *,
    source_row: Mapping[str, Any],
    residual_report: Mapping[str, Any] | None,
) -> tuple[str, str] | None:
    """驗 replay manifest 是否承諾同一份 residual alpha report。

    只比對 hash，不信任 registry manifest 內的 report body；report body 仍由
    canonical ``demo_residual_alpha_report`` 欄位提供並由 validator 檢查。
    """
    registry_manifest = source_row.get("replay_registry_manifest_jsonb")
    if not isinstance(registry_manifest, Mapping):
        return "replay_registry_manifest_jsonb_missing", PENDING_SCHEMA
    registry_hash = _text(registry_manifest.get(REGISTRY_RESIDUAL_ALPHA_HASH_FIELD))
    if not registry_hash:
        return f"replay_registry_{REGISTRY_RESIDUAL_ALPHA_HASH_FIELD}_missing", (
            PENDING_SCHEMA
        )
    if not _is_hex64(registry_hash):
        return f"replay_registry_{REGISTRY_RESIDUAL_ALPHA_HASH_FIELD}_malformed", (
            INVALID
        )
    if not isinstance(residual_report, Mapping):
        return "residual_alpha:not_dict", INVALID
    expected_hash = _canonical_sha256(dict(residual_report))
    if registry_hash != expected_hash:
        return f"replay_registry_{REGISTRY_RESIDUAL_ALPHA_HASH_FIELD}_mismatch", (
            INVALID
        )
    return None


def _validate_durable_residual_report_snapshot(
    *,
    source_row: Mapping[str, Any],
    residual_report: Mapping[str, Any] | None,
) -> tuple[str, str] | None:
    """驗 durable residual registry 是否能反查同一份 report body。"""
    registry_manifest = source_row.get("replay_registry_manifest_jsonb")
    if not isinstance(registry_manifest, Mapping):
        return "replay_registry_manifest_jsonb_missing", PENDING_SCHEMA

    registry_hash = _text(registry_manifest.get(REGISTRY_RESIDUAL_ALPHA_HASH_FIELD))
    if not registry_hash:
        return f"replay_registry_{REGISTRY_RESIDUAL_ALPHA_HASH_FIELD}_missing", (
            PENDING_SCHEMA
        )

    durable_hash = _text(source_row.get(DURABLE_RESIDUAL_ALPHA_HASH_FIELD))
    if not durable_hash:
        return f"{DURABLE_RESIDUAL_ALPHA_HASH_FIELD}_missing", PENDING_SCHEMA
    if not _is_hex64(durable_hash):
        return f"{DURABLE_RESIDUAL_ALPHA_HASH_FIELD}_malformed", INVALID
    if durable_hash != registry_hash:
        return f"{DURABLE_RESIDUAL_ALPHA_HASH_FIELD}_mismatch", INVALID

    durable_report = source_row.get(DURABLE_RESIDUAL_ALPHA_REPORT_FIELD)
    if not isinstance(durable_report, Mapping):
        return f"{DURABLE_RESIDUAL_ALPHA_REPORT_FIELD}_missing", PENDING_SCHEMA

    durable_ok, durable_reason = validate_demo_residual_alpha_report(durable_report)
    if not durable_ok:
        return (
            f"durable_residual_alpha_report_invalid:{durable_reason}",
            INVALID,
        )

    durable_body_hash = _canonical_sha256(dict(durable_report))
    if durable_body_hash != durable_hash:
        return "durable_residual_alpha_report_body_hash_mismatch", INVALID
    return None


def _load_hidden_oos_state_snapshot(
    source_row: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, tuple[str, str] | None]:
    """驗證 replay manifest 內 committed hidden OOS state。

    這不是 durable state table；它是 P1-B 的 migration-free producer gate：
    沒有在 registry manifest hash 內承諾 sealed state，就不能升級成
    live candidate evidence。
    """
    registry_manifest = source_row.get("replay_registry_manifest_jsonb")
    if not isinstance(registry_manifest, Mapping):
        return None, ("replay_registry_manifest_jsonb_missing", PENDING_SCHEMA)
    raw_state = registry_manifest.get("hidden_oos_state")
    if not isinstance(raw_state, Mapping):
        return None, ("hidden_oos_state_missing", PENDING_SCHEMA)

    state = dict(raw_state)
    schema_version = _text(state.get("schema_version"))
    if schema_version != HIDDEN_OOS_STATE_SCHEMA_VERSION:
        return None, ("hidden_oos_state_schema_version_unknown", PENDING_SCHEMA)

    state_label = _text(state.get("state"))
    if not state_label:
        return None, ("hidden_oos_state_state_missing", PENDING_SCHEMA)
    if state_label != HIDDEN_OOS_PROMOTION_STATE:
        return None, (f"hidden_oos_state_not_sealed:{state_label}", RESEARCH_ONLY)

    open_count = _int_value(state.get("open_count"))
    if open_count is None:
        return None, ("hidden_oos_state_open_count_missing", PENDING_SCHEMA)
    if open_count != 0:
        return None, ("hidden_oos_state_open_count_nonzero", RESEARCH_ONLY)
    if _truthy(state.get("opened_for_iteration")):
        return None, ("hidden_oos_state_opened_for_iteration", RESEARCH_ONLY)
    if _truthy(state.get("consumed")):
        return None, ("hidden_oos_state_consumed", RESEARCH_ONLY)
    if _truthy(state.get("invalidated")):
        return None, ("hidden_oos_state_invalidated", RESEARCH_ONLY)

    split_hash = _text(state.get("split_hash"))
    if not split_hash:
        return None, ("hidden_oos_state_split_hash_missing", PENDING_SCHEMA)
    if not _is_stable_hash(split_hash):
        return None, ("hidden_oos_state_split_hash_malformed", INVALID)

    if not _text(state.get("family_id")):
        return None, ("hidden_oos_state_family_id_missing", PENDING_SCHEMA)

    for field in ("window_start", "window_end"):
        if not _text(state.get(field)):
            return None, (f"hidden_oos_state_{field}_missing", PENDING_SCHEMA)
    if not _time_equivalent(
        state.get("window_start"),
        source_row.get("replay_registry_oos_label_window_start"),
    ) or not _time_equivalent(
        state.get("window_end"),
        source_row.get("replay_registry_oos_label_window_end"),
    ):
        return None, ("hidden_oos_state_window_mismatch", INVALID)

    state_embargo_seconds = _int_value(
        _first_present(
            state.get("embargo_seconds"),
            state.get("oos_embargo_seconds"),
            state.get("embargo"),
        )
    )
    registry_embargo_seconds = _int_value(
        source_row.get("replay_registry_oos_embargo_seconds")
    )
    if state_embargo_seconds is None:
        return None, ("hidden_oos_state_embargo_seconds_missing", PENDING_SCHEMA)
    if registry_embargo_seconds is None:
        return None, ("replay_registry_oos_embargo_seconds_malformed", INVALID)
    if state_embargo_seconds != registry_embargo_seconds:
        return None, ("hidden_oos_state_embargo_seconds_mismatch", INVALID)

    state_total_k = _int_value(
        _first_present(
            state.get("total_candidates_k"),
            state.get("total_candidates_K"),
            state.get("trial_count"),
            state.get("K"),
            state.get("k"),
        )
    )
    registry_total_k = _int_value(source_row.get("replay_registry_total_candidates_k"))
    if state_total_k is None:
        return None, ("hidden_oos_state_total_candidates_k_missing", PENDING_SCHEMA)
    if registry_total_k is None:
        return None, ("replay_registry_total_candidates_k_malformed", INVALID)
    if state_total_k != registry_total_k:
        return None, ("hidden_oos_state_total_candidates_k_mismatch", INVALID)
    if state_total_k <= 0:
        return None, ("hidden_oos_state_total_candidates_k_nonpositive", INVALID)

    return state, None


def _validate_durable_hidden_oos_state_snapshot(
    *,
    source_row: Mapping[str, Any],
    hidden_oos_state: Mapping[str, Any],
) -> tuple[str, str] | None:
    durable_state_label = _text(source_row.get(DURABLE_HIDDEN_OOS_STATE_FIELD))
    if not durable_state_label:
        return f"{DURABLE_HIDDEN_OOS_STATE_FIELD}_missing", PENDING_SCHEMA
    if durable_state_label != HIDDEN_OOS_PROMOTION_STATE:
        return f"{DURABLE_HIDDEN_OOS_STATE_FIELD}_not_sealed:{durable_state_label}", RESEARCH_ONLY

    durable_state = source_row.get(DURABLE_HIDDEN_OOS_STATE_JSONB_FIELD)
    if not isinstance(durable_state, Mapping):
        return f"{DURABLE_HIDDEN_OOS_STATE_JSONB_FIELD}_missing", PENDING_SCHEMA

    if _text(durable_state.get("schema_version")) != HIDDEN_OOS_STATE_SCHEMA_VERSION:
        return "durable_hidden_oos_state_schema_version_unknown", PENDING_SCHEMA
    if _text(durable_state.get("state")) != HIDDEN_OOS_PROMOTION_STATE:
        return "durable_hidden_oos_state_body_not_sealed", RESEARCH_ONLY
    if _int_value(durable_state.get("open_count")) != 0:
        return "durable_hidden_oos_state_open_count_nonzero", RESEARCH_ONLY
    for flag in ("opened_for_iteration", "consumed", "invalidated"):
        if _truthy(durable_state.get(flag)):
            return f"durable_hidden_oos_state_{flag}", RESEARCH_ONLY

    if _canonical_sha256(dict(durable_state)) != _canonical_sha256(
        dict(hidden_oos_state)
    ):
        return "durable_hidden_oos_state_body_mismatch", INVALID
    return None


def _source_row_with_registry_hidden_oos(
    source_row: Mapping[str, Any],
    *,
    hidden_oos_state: Mapping[str, Any],
) -> dict[str, Any]:
    """用 replay manifest 中的 sealed hidden_oos_state 覆寫 hidden_oos。"""
    row = dict(source_row)
    payload = source_row.get("payload")
    payload_dict = copy.deepcopy(dict(payload)) if isinstance(payload, Mapping) else {}
    total_k = _int_value(
        _first_present(
            hidden_oos_state.get("total_candidates_k"),
            hidden_oos_state.get("total_candidates_K"),
            hidden_oos_state.get("trial_count"),
        )
    )
    embargo_seconds = _int_value(
        _first_present(
            hidden_oos_state.get("embargo_seconds"),
            hidden_oos_state.get("oos_embargo_seconds"),
            hidden_oos_state.get("embargo"),
        )
    )
    payload_dict["hidden_oos"] = {
        "split_hash": _text(hidden_oos_state.get("split_hash")),
        "window_start": _text(hidden_oos_state.get("window_start")),
        "window_end": _text(hidden_oos_state.get("window_end")),
        "embargo": f"{embargo_seconds}s",
        "trial_count": total_k,
        "passes": True,
        "state": HIDDEN_OOS_PROMOTION_STATE,
        "open_count": 0,
        "opened_for_iteration": False,
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
        signal_spec=manifest_build.signal_spec if manifest_build else None,
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


def _canonical_sha256(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _first_present(*values: Any) -> Any:
    for value in values:
        if _text(value):
            return value
    return None


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = _text(value).lower()
    if not text:
        return None
    try:
        if text.endswith("s"):
            return int(float(text[:-1]))
        if text.endswith("d"):
            return int(float(text[:-1]) * 86400)
        return int(text)
    except ValueError:
        return None


def _int_equivalent(left: Any, right: Any) -> bool:
    left_int = _int_value(left)
    right_int = _int_value(right)
    return left_int is not None and right_int is not None and left_int == right_int


def _embargo_equivalent(left: Any, right_seconds: Any) -> bool:
    left_int = _int_value(left)
    right_int = _int_value(right_seconds)
    return left_int is not None and right_int is not None and left_int == right_int


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "on"}


def _is_hex64(value: str) -> bool:
    return bool(_HEX64_RE.match(value))


def _is_stable_hash(value: str) -> bool:
    return _is_hex64(value) or (
        value.startswith("sha256:") and len(value) > len("sha256:")
    )


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
    "HIDDEN_OOS_STATE_SCHEMA_VERSION",
    "HIDDEN_OOS_PROMOTION_STATE",
    "REGISTRY_RESIDUAL_ALPHA_HASH_FIELD",
    "PROMOTION_EVIDENCE_SOURCE_TIERS",
    "PROMOTION_REPLAY_REGISTRY_STATUSES",
    "CandidateEvidenceSourceContractBuild",
    "build_live_candidate_evidence_from_source",
]
