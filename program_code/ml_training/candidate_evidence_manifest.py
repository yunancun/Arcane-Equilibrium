"""
MODULE_NOTE
模塊用途：Demo alpha live-candidate 的 EvidenceManifest 共享契約驗證器。
主要類/函數：CandidateEvidenceManifestValidation、
validate_candidate_evidence_manifest、extract_candidate_evidence_manifest。
依賴：僅 Python 標準庫與 residual alpha report 契約；不讀 DB、不連交易所、
不生成 promotion evidence。
硬邊界：缺 manifest、非 canonical field、hash mismatch、hidden OOS / lineage
欄位不足、residual report 不合法時，promotion/live-candidate gate 必須
fail-closed。
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

try:
    from .candidate_signal_spec import validate_signal_spec
    from .residual_alpha_report_contract import validate_demo_residual_alpha_report
except ImportError:  # pragma: no cover - direct script execution fallback
    from candidate_signal_spec import validate_signal_spec  # type: ignore
    from residual_alpha_report_contract import (  # type: ignore
        validate_demo_residual_alpha_report,
    )


CANDIDATE_EVIDENCE_MANIFEST_FIELD = "candidate_evidence_manifest"
CANDIDATE_EVIDENCE_MANIFEST_SCHEMA_VERSION = "candidate_evidence_manifest_v1"

PROMOTION_READY = "promotion_ready"
RESEARCH_ONLY = "research_only"
PENDING_SCHEMA = "pending_schema"
INVALID = "invalid"

_ALLOWED_VERDICTS = {PROMOTION_READY, RESEARCH_ONLY, PENDING_SCHEMA, INVALID}
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CandidateEvidenceManifestValidation:
    """EvidenceManifest 驗證結果；caller 只能看 promotion_ready 放行。"""

    promotion_ready: bool
    verdict: str
    reason: str
    reasons: tuple[str, ...]
    lineage_downgraded: bool = False


def extract_candidate_evidence_manifest(mapping: Any) -> Any:
    """只讀 canonical ``candidate_evidence_manifest`` 欄位，不接受 alias。"""
    if not isinstance(mapping, Mapping):
        return None
    return mapping.get(CANDIDATE_EVIDENCE_MANIFEST_FIELD)


def compute_candidate_evidence_manifest_hash(manifest: Mapping[str, Any]) -> str:
    """對 manifest 做 canonical JSON sha256；頂層 ``manifest_hash`` 不入 hash。"""
    payload = copy.deepcopy(dict(manifest))
    payload.pop("manifest_hash", None)
    return _canonical_sha256(payload)


def validate_candidate_evidence_manifest(
    manifest: Any,
    *,
    residual_report: Any = None,
    signal_spec: Any = None,
) -> CandidateEvidenceManifestValidation:
    """驗證 manifest 是否可作 promotion/live-candidate gate。

    這裡只做 deterministic contract validation；不查 DB、不驗證 hidden OOS
    是否全局唯一或真的 sealed。缺少能機械驗證的欄位一律不 promotion-ready。
    """
    if manifest is None:
        return _result(PENDING_SCHEMA, "manifest_missing")
    if not isinstance(manifest, Mapping):
        return _result(INVALID, "manifest_not_mapping")

    reasons: list[str] = []
    lineage_downgraded = False

    schema_version = _text(manifest.get("schema_version"))
    if schema_version != CANDIDATE_EVIDENCE_MANIFEST_SCHEMA_VERSION:
        return _result(PENDING_SCHEMA, "schema_version_unknown")

    manifest_verdict = _text(manifest.get("verdict"))
    if manifest_verdict not in _ALLOWED_VERDICTS:
        return _result(INVALID, "verdict_unknown")
    if manifest_verdict != PROMOTION_READY:
        return _result(
            manifest_verdict,
            f"verdict_not_promotion_ready:{manifest_verdict}",
        )

    for field in ("family_id", "candidate_id"):
        if not _text(manifest.get(field)):
            reasons.append(f"{field}_missing")

    spec_hash = _text(manifest.get("spec_hash"))
    if not spec_hash:
        reasons.append("spec_hash_missing")
    elif not _is_stable_hash(spec_hash):
        reasons.append("spec_hash_malformed")

    signal_spec_validation = validate_signal_spec(
        signal_spec,
        expected_spec_hash=spec_hash,
        candidate_id=_text(manifest.get("candidate_id")),
        family_id=_text(manifest.get("family_id")),
    )
    if not signal_spec_validation.ok:
        reasons.append(f"signal_spec:{signal_spec_validation.reason}")

    replay_experiment_id = _text(manifest.get("replay_experiment_id"))
    if not replay_experiment_id:
        reasons.append("replay_experiment_id_missing")
        lineage_downgraded = True

    replay_manifest_hash = _text(manifest.get("replay_manifest_hash"))
    if not replay_manifest_hash:
        reasons.append("replay_manifest_hash_missing")
        lineage_downgraded = True
    elif not _is_stable_hash(replay_manifest_hash):
        reasons.append("replay_manifest_hash_malformed")

    hidden_ok, hidden_reason = _validate_hidden_oos(manifest.get("hidden_oos"))
    if not hidden_ok:
        reasons.append(hidden_reason)

    residual_ok, residual_reason = validate_demo_residual_alpha_report(residual_report)
    if not residual_ok:
        reasons.append(f"residual_alpha:{residual_reason}")
    else:
        residual_hash = _text(manifest.get("demo_residual_alpha_report_hash"))
        if not residual_hash:
            reasons.append("demo_residual_alpha_report_hash_missing")
        elif not _is_hex64(residual_hash):
            reasons.append("demo_residual_alpha_report_hash_malformed")
        elif isinstance(residual_report, Mapping):
            expected = _canonical_sha256(dict(residual_report))
            if residual_hash != expected:
                reasons.append("demo_residual_alpha_report_hash_mismatch")
        else:
            reasons.append("demo_residual_alpha_report_hash_unverifiable")

    manifest_hash = _text(manifest.get("manifest_hash"))
    if not manifest_hash:
        reasons.append("manifest_hash_missing")
        lineage_downgraded = True
    elif not _is_hex64(manifest_hash):
        reasons.append("manifest_hash_malformed")
    elif not reasons and manifest_hash != compute_candidate_evidence_manifest_hash(manifest):
        reasons.append("manifest_hash_mismatch")

    if reasons:
        verdict = _failure_verdict(reasons)
        return _result(verdict, reasons[0], reasons, lineage_downgraded=lineage_downgraded)

    return _result(PROMOTION_READY, "ok", ())


def _validate_hidden_oos(raw_hidden_oos: Any) -> tuple[bool, str]:
    if not isinstance(raw_hidden_oos, Mapping):
        return False, "hidden_oos_missing"

    if raw_hidden_oos.get("passes") is False:
        return False, "hidden_oos_not_passed"
    if raw_hidden_oos.get("opened_for_iteration") is True:
        return False, "hidden_oos_reused"

    split_ref = _text(raw_hidden_oos.get("split_hash")) or _text(
        raw_hidden_oos.get("split_id")
    )
    if not split_ref:
        return False, "hidden_oos_split_missing"
    if _text(raw_hidden_oos.get("split_hash")) and not _is_stable_hash(
        _text(raw_hidden_oos.get("split_hash"))
    ):
        return False, "hidden_oos_split_hash_malformed"

    for field in ("window_start", "window_end"):
        if not _text(raw_hidden_oos.get(field)):
            return False, f"hidden_oos_{field}_missing"

    if not any(
        _present(raw_hidden_oos.get(field))
        for field in ("embargo", "purge", "purge_days")
    ):
        return False, "hidden_oos_embargo_missing"

    if not any(
        _present(raw_hidden_oos.get(field))
        for field in ("K", "k", "trial_count", "total_candidates_K")
    ):
        return False, "hidden_oos_trial_count_missing"

    return True, "ok"


def _failure_verdict(reasons: list[str]) -> str:
    if any(reason.startswith("residual_alpha:") for reason in reasons):
        return INVALID
    pending_tokens = (
        "_missing",
        "schema",
        "replay_experiment_id_missing",
        "manifest_hash_missing",
    )
    research_tokens = (
        "hidden_oos_not_passed",
        "hidden_oos_reused",
    )
    if any(token in reason for reason in reasons for token in research_tokens):
        return RESEARCH_ONLY
    if any(token in reason for reason in reasons for token in pending_tokens):
        return PENDING_SCHEMA
    return INVALID


def _result(
    verdict: str,
    reason: str,
    reasons: tuple[str, ...] | list[str] = (),
    *,
    lineage_downgraded: bool = False,
) -> CandidateEvidenceManifestValidation:
    normalized = tuple(str(item) for item in reasons) or (reason,)
    return CandidateEvidenceManifestValidation(
        promotion_ready=verdict == PROMOTION_READY and reason == "ok",
        verdict=verdict,
        reason=reason,
        reasons=normalized,
        lineage_downgraded=lineage_downgraded,
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


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


__all__ = [
    "CANDIDATE_EVIDENCE_MANIFEST_FIELD",
    "CANDIDATE_EVIDENCE_MANIFEST_SCHEMA_VERSION",
    "PROMOTION_READY",
    "RESEARCH_ONLY",
    "PENDING_SCHEMA",
    "INVALID",
    "CandidateEvidenceManifestValidation",
    "compute_candidate_evidence_manifest_hash",
    "extract_candidate_evidence_manifest",
    "validate_candidate_evidence_manifest",
]
