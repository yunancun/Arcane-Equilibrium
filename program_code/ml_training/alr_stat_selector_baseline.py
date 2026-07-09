"""
MODULE_NOTE
模塊用途：ALR 統計 selector 的 source-only offline deterministic baseline。
主要函數：compute_selector_snapshot_hash、compute_selector_output_hash、
load_selector_snapshot、build_alr_stat_selector_baseline、
validate_alr_stat_selector_baseline、extract_alr_stat_selector_baseline、main。
依賴：僅 Python 標準庫；不讀 DB、不連 runtime、不呼叫交易所、不使用
``_latest``；輸出只寫明確指定檔案。
硬邊界：本模塊只生成離線 selector artifact；不授予 proof/promotion/
runtime/trading/order/probe/Cost Gate/Decision Lease/serving 權限。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


INPUT_SCHEMA_VERSION = "alr_stat_selector_snapshot_v1"
OUTPUT_SCHEMA_VERSION = "alr_stat_selector_baseline_v1"
BOUNDARY_LABEL = "SOURCE_ONLY_OFFLINE_P0_P1"
OBJECTIVE = "active_learning_controlled_voi"
ALR_STAT_SELECTOR_BASELINE_FIELD = "alr_stat_selector_baseline"

DECISION_SELECT_TARGET = "SELECT_TARGET"
DECISION_DEFER_EVIDENCE = "DEFER_EVIDENCE"
DECISION_HYPOTHESIS_ONLY = "HYPOTHESIS_ONLY"
DECISION_STOP_NO_EDGE = "STOP_NO_EDGE"
DECISION_BLOCKED_BOUNDARY = "BLOCKED_BOUNDARY"
DECISION_ROTATED = "ROTATED"

_ALLOWED_DECISIONS = {
    DECISION_SELECT_TARGET,
    DECISION_DEFER_EVIDENCE,
    DECISION_HYPOTHESIS_ONLY,
    DECISION_STOP_NO_EDGE,
    DECISION_BLOCKED_BOUNDARY,
    DECISION_ROTATED,
}
_REQUIRED_SNAPSHOT_FIELDS = {
    "schema_version",
    "boundary_label",
    "created_at",
    "source_head",
    "snapshot_id",
    "objective",
    "latest_alias_used",
    "frozen_universe",
    "pre_registered_split",
    "selector_policy",
    "proof_exclusion",
    "no_authority",
    "candidates",
    "snapshot_hash",
}
_REQUIRED_CANDIDATE_FIELDS = {"identity", "evidence", "stats", "terms", "flags"}
_REQUIRED_FROZEN_UNIVERSE_FIELDS = {
    "universe_id",
    "frozen_at",
    "candidate_ids",
    "universe_hash",
}
_REQUIRED_PRE_REGISTERED_SPLIT_FIELDS = {
    "split_id",
    "split_hash",
    "train_window",
    "oos_window",
    "purge",
    "embargo",
    "walk_forward",
}
_REQUIRED_SELECTOR_POLICY_FIELDS = {
    "lcb_z",
    "prior_n",
    "prior_delta_bps",
    "min_candidate_oos_n",
    "min_control_oos_n",
}
_REQUIRED_IDENTITY_FIELDS = {"candidate_id", "strategy_name", "symbol", "side"}
_REQUIRED_STATS_FIELDS = {
    "candidate_net_bps_mean",
    "candidate_net_bps_std",
    "candidate_oos_n",
    "matched_control_net_bps_mean",
    "matched_control_net_bps_std",
    "matched_control_oos_n",
}
_REQUIRED_TERMS_FIELDS = {
    "voi_bps",
    "offline_cost_bps",
    "governance_risk_bps",
    "staleness_penalty_bps",
    "evidence_gap_penalty_bps",
}
_REQUIRED_TRUE_FLAGS = (
    "frozen_universe_member",
    "pre_registered_split",
    "walk_forward_oos",
    "retained_if_not_selected",
)
_NO_AUTHORITY_KEYS = tuple(
    """
    runtime pg ipc bybit mcp decision_lease order probe order_or_probe cost_gate
    latest serving proof promotion runtime_mutation trading live mainnet
    live_or_mainnet delete apply cron daemon scheduler service env
    """.split()
)
_AUTHORITY_COUNTER_KEYS = tuple(
    """
    runtime pg ipc bybit_mcp decision_lease order_probe cost_gate latest
    serving proof promotion runtime_mutation trading delete_apply
    cron_daemon_scheduler
    """.split()
)
_AUTHORITY_KEY_TERMS = tuple(
    """
    runtime pg ipc bybit mcp decision lease order probe cost cost_gate latest
    serving proof promotion trade trading live mainnet authority delete apply
    cron daemon scheduler service env
    """.split()
)
_AUTHORITY_ACTION_TERMS = tuple(
    """
    allow allowed approve approved author authority enable enabled grant granted
    ready perform performed use used touch touched start started mutate mutation
    write read lower lowered consume consumed promote promoted
    """.split()
)
_AUTHORITY_EXEMPT_KEYS = {"proof_ready_controlled_oos_evidence"}
_FALSE_STRINGS = {"", "0", "false", "no", "off", "disabled", "deny", "denied", "none", "null", "n/a"}


class AlrStatSelectorBaselineError(ValueError):
    """Raised for malformed source-only selector inputs."""


@dataclass(frozen=True)
class SelectorValidation:
    valid: bool
    decision: str | None
    reason: str
    reasons: tuple[str, ...] = ()


def compute_selector_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    """Canonical JSON sha256 over input snapshot, excluding ``snapshot_hash``."""
    payload = copy.deepcopy(dict(snapshot))
    payload.pop("snapshot_hash", None)
    return _canonical_sha256(payload)


def compute_selector_output_hash(output: Mapping[str, Any]) -> str:
    """Canonical JSON sha256 over selector output, excluding ``selector_hash``."""
    payload = copy.deepcopy(dict(output))
    payload.pop("selector_hash", None)
    return _canonical_sha256(payload)


def load_selector_snapshot(path: Path) -> dict[str, Any]:
    snapshot_path = Path(path)
    _reject_latest_path(snapshot_path, "snapshot")
    try:
        raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except OSError as exc:  # pragma: no cover - platform-specific text
        raise AlrStatSelectorBaselineError(f"snapshot_read_failed:{exc}") from exc
    except json.JSONDecodeError as exc:
        raise AlrStatSelectorBaselineError(f"snapshot_json_invalid:{exc.msg}") from exc
    if not isinstance(raw, dict):
        raise AlrStatSelectorBaselineError("snapshot_not_mapping")
    return raw


def build_alr_stat_selector_baseline(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    _validate_snapshot_shape(snapshot)
    if _contains_latest_ref(snapshot):
        raise AlrStatSelectorBaselineError("source_ref_latest_rejected")

    computed_snapshot_hash = compute_selector_snapshot_hash(snapshot)
    hash_matches = snapshot.get("snapshot_hash") == computed_snapshot_hash
    policy = dict(_mapping(snapshot["selector_policy"]))
    policy["_frozen_candidate_ids"] = set(snapshot["frozen_universe"]["candidate_ids"])
    scored_candidates = [
        _score_candidate(_mapping(candidate), policy)
        for candidate in snapshot["candidates"]
    ]
    scored_candidates.sort(key=lambda item: (-item["score"], item["candidate_id"]))

    boundary_reasons = _boundary_contamination_reasons(snapshot)
    decision, selected_target, decision_reasons = _select_decision(
        snapshot=snapshot,
        candidates=scored_candidates,
        hash_matches=hash_matches,
        boundary_reasons=boundary_reasons,
    )
    retained = [
        copy.deepcopy(candidate)
        for candidate in scored_candidates
        if selected_target is None or candidate["candidate_id"] != selected_target["candidate_id"]
    ]
    output: dict[str, Any] = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "boundary_label": BOUNDARY_LABEL,
        "objective": OBJECTIVE,
        "decision": decision,
        "decision_reasons": decision_reasons,
        "input_snapshot_ref": {
            "schema_version": snapshot["schema_version"],
            "boundary_label": snapshot["boundary_label"],
            "created_at": snapshot["created_at"],
            "source_head": snapshot["source_head"],
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_hash": snapshot["snapshot_hash"],
            "computed_snapshot_hash": computed_snapshot_hash,
            "snapshot_hash_matches": hash_matches,
        },
        "selected_target": copy.deepcopy(selected_target),
        "candidates": copy.deepcopy(scored_candidates),
        "retained_non_selected_candidates": retained,
        "authority_counters": _zero_authority_counters(),
        "no_authority": _false_no_authority(),
        "proof_ready": False,
        "promotion_ready": False,
        "runtime_ready": False,
        "trading_ready": False,
        "order_or_probe_ready": False,
        "serving_ready": False,
    }
    output["selector_hash"] = compute_selector_output_hash(output)
    return output


def validate_alr_stat_selector_baseline(output: Mapping[str, Any]) -> SelectorValidation:
    reasons: list[str] = []
    decision = output.get("decision") if isinstance(output, Mapping) else None
    if not isinstance(output, Mapping):
        return SelectorValidation(False, None, "output_not_mapping", ("output_not_mapping",))
    if output.get("schema_version") != OUTPUT_SCHEMA_VERSION:
        reasons.append("schema_version_invalid")
    if output.get("boundary_label") != BOUNDARY_LABEL:
        reasons.append("boundary_label_invalid")
    if decision not in _ALLOWED_DECISIONS:
        reasons.append("decision_invalid")
    if output.get("selector_hash") != compute_selector_output_hash(output):
        reasons.append("selector_hash_mismatch")
    if not _all_false(output.get("no_authority")):
        reasons.append("no_authority_not_false")
    if not _all_zero(output.get("authority_counters")):
        reasons.append("authority_counters_not_zero")
    for flag in ("proof_ready", "promotion_ready", "runtime_ready", "trading_ready", "order_or_probe_ready", "serving_ready"):
        if output.get(flag) is not False:
            reasons.append(f"{flag}_not_false")
    if decision == DECISION_SELECT_TARGET and not isinstance(output.get("selected_target"), Mapping):
        reasons.append("selected_target_missing")
    if decision != DECISION_SELECT_TARGET and output.get("selected_target") is not None:
        reasons.append("selected_target_unexpected")
    if not isinstance(output.get("candidates"), list):
        reasons.append("candidates_not_list")
    if not isinstance(output.get("retained_non_selected_candidates"), list):
        reasons.append("retained_non_selected_candidates_not_list")
    if reasons:
        return SelectorValidation(False, _optional_text(decision), reasons[0], tuple(reasons))
    return SelectorValidation(True, _optional_text(decision), "ok", ())


def extract_alr_stat_selector_baseline(value: Mapping[str, Any]) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    if value.get("schema_version") == OUTPUT_SCHEMA_VERSION:
        return dict(value)
    packet = value.get(ALR_STAT_SELECTOR_BASELINE_FIELD)
    if isinstance(packet, Mapping):
        return dict(packet)
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Source-only ALR statistical selector baseline")
    parser.add_argument("--snapshot", required=True, help="Explicit selector snapshot JSON path")
    parser.add_argument("--out", required=True, help="Explicit selector output JSON path")
    args = parser.parse_args(argv)

    try:
        snapshot = load_selector_snapshot(Path(args.snapshot))
        output = build_alr_stat_selector_baseline(snapshot)
        _write_selector_output(output, Path(args.out))
    except AlrStatSelectorBaselineError as exc:
        print(f"alr_stat_selector_baseline_error:{exc}", file=sys.stderr)
        return 2
    return 0


def _validate_snapshot_shape(snapshot: Mapping[str, Any]) -> None:
    missing = sorted(_REQUIRED_SNAPSHOT_FIELDS - set(snapshot))
    if missing:
        raise AlrStatSelectorBaselineError(f"snapshot_missing_fields:{','.join(missing)}")
    if snapshot.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise AlrStatSelectorBaselineError("schema_version_invalid")
    if snapshot.get("boundary_label") != BOUNDARY_LABEL:
        raise AlrStatSelectorBaselineError("boundary_label_invalid")
    if snapshot.get("objective") != OBJECTIVE:
        raise AlrStatSelectorBaselineError("objective_invalid")
    if snapshot.get("latest_alias_used") is not False:
        raise AlrStatSelectorBaselineError("latest_alias_used_rejected")
    for field in ("frozen_universe", "pre_registered_split", "selector_policy", "proof_exclusion", "no_authority"):
        if not isinstance(snapshot.get(field), Mapping):
            raise AlrStatSelectorBaselineError(f"{field}_not_mapping")
    _validate_frozen_universe(_mapping(snapshot["frozen_universe"]))
    _validate_pre_registered_split(_mapping(snapshot["pre_registered_split"]))
    _validate_selector_policy(_mapping(snapshot["selector_policy"]))
    candidates = snapshot.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise AlrStatSelectorBaselineError("candidates_invalid")
    for candidate in candidates:
        _validate_candidate_shape(candidate)


def _validate_frozen_universe(frozen_universe: Mapping[str, Any]) -> None:
    missing = sorted(_REQUIRED_FROZEN_UNIVERSE_FIELDS - set(frozen_universe))
    if missing:
        raise AlrStatSelectorBaselineError(f"frozen_universe_missing_fields:{','.join(missing)}")
    for field in ("universe_id", "frozen_at", "universe_hash"):
        if not _non_empty_text(frozen_universe.get(field)):
            raise AlrStatSelectorBaselineError(f"frozen_universe_{field}_invalid")
    candidate_ids = frozen_universe.get("candidate_ids")
    if not _non_empty_text_list(candidate_ids):
        raise AlrStatSelectorBaselineError("frozen_universe_candidate_ids_invalid")


def _validate_pre_registered_split(split: Mapping[str, Any]) -> None:
    missing = sorted(_REQUIRED_PRE_REGISTERED_SPLIT_FIELDS - set(split))
    if missing:
        raise AlrStatSelectorBaselineError(f"pre_registered_split_missing_fields:{','.join(missing)}")
    for field in ("split_id", "split_hash"):
        if not _non_empty_text(split.get(field)):
            raise AlrStatSelectorBaselineError(f"pre_registered_split_{field}_invalid")
    for field in ("train_window", "oos_window"):
        if not isinstance(split.get(field), Mapping) or not split[field]:
            raise AlrStatSelectorBaselineError(f"pre_registered_split_{field}_invalid")
    for field in ("purge", "embargo"):
        value = _finite_number(split.get(field), f"pre_registered_split_{field}")
        if value < 0:
            raise AlrStatSelectorBaselineError(f"pre_registered_split_{field}_negative")
    if split.get("walk_forward") is not True:
        raise AlrStatSelectorBaselineError("pre_registered_split_walk_forward_not_true")


def _validate_selector_policy(policy: Mapping[str, Any]) -> None:
    missing = sorted(_REQUIRED_SELECTOR_POLICY_FIELDS - set(policy))
    if missing:
        raise AlrStatSelectorBaselineError(f"selector_policy_missing_fields:{','.join(missing)}")
    for field in _REQUIRED_SELECTOR_POLICY_FIELDS:
        value = _finite_number(policy.get(field), f"selector_policy_{field}")
        if field != "prior_delta_bps" and value < 0:
            raise AlrStatSelectorBaselineError(f"selector_policy_{field}_negative")


def _validate_candidate_shape(candidate: Any) -> None:
    if not isinstance(candidate, Mapping):
        raise AlrStatSelectorBaselineError("candidate_not_mapping")
    missing = sorted(_REQUIRED_CANDIDATE_FIELDS - set(candidate))
    if missing:
        raise AlrStatSelectorBaselineError(f"candidate_missing_fields:{','.join(missing)}")
    for field in _REQUIRED_CANDIDATE_FIELDS:
        if not isinstance(candidate.get(field), Mapping):
            raise AlrStatSelectorBaselineError(f"candidate_{field}_not_mapping")
    identity = _mapping(candidate["identity"])
    identity_missing = sorted(_REQUIRED_IDENTITY_FIELDS - set(identity))
    if identity_missing:
        raise AlrStatSelectorBaselineError(f"candidate_identity_missing_fields:{','.join(identity_missing)}")
    for field in sorted(_REQUIRED_IDENTITY_FIELDS):
        if not _non_empty_text(identity.get(field)):
            raise AlrStatSelectorBaselineError(f"candidate_identity_{field}_invalid")
    stats = _mapping(candidate["stats"])
    terms = _mapping(candidate["terms"])
    stats_missing = sorted(_REQUIRED_STATS_FIELDS - set(stats))
    if stats_missing:
        raise AlrStatSelectorBaselineError(f"candidate_stats_missing_fields:{','.join(stats_missing)}")
    for field in sorted(_REQUIRED_STATS_FIELDS):
        value = _finite_number(stats.get(field), f"candidate_stats_{field}")
        if field.endswith("_std") and value < 0:
            raise AlrStatSelectorBaselineError(f"candidate_stats_{field}_negative")
        if field.endswith("_oos_n") and value <= 0:
            raise AlrStatSelectorBaselineError(f"candidate_stats_{field}_non_positive")
    terms_missing = sorted(_REQUIRED_TERMS_FIELDS - set(terms))
    if terms_missing:
        raise AlrStatSelectorBaselineError(f"candidate_terms_missing_fields:{','.join(terms_missing)}")
    for field in sorted(_REQUIRED_TERMS_FIELDS):
        _finite_number(terms.get(field), f"candidate_terms_{field}")


def _score_candidate(candidate: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    identity = copy.deepcopy(_mapping(candidate["identity"]))
    evidence = copy.deepcopy(_mapping(candidate["evidence"]))
    stats = copy.deepcopy(_mapping(candidate["stats"]))
    terms = copy.deepcopy(_mapping(candidate["terms"]))
    flags = copy.deepcopy(_mapping(candidate["flags"]))

    candidate_mean = _finite_number(stats["candidate_net_bps_mean"], "candidate_stats_candidate_net_bps_mean")
    control_mean = _finite_number(stats["matched_control_net_bps_mean"], "candidate_stats_matched_control_net_bps_mean")
    candidate_std = _finite_number(stats["candidate_net_bps_std"], "candidate_stats_candidate_net_bps_std")
    control_std = _finite_number(stats["matched_control_net_bps_std"], "candidate_stats_matched_control_net_bps_std")
    candidate_oos_n = _finite_number(stats["candidate_oos_n"], "candidate_stats_candidate_oos_n")
    control_oos_n = _finite_number(stats["matched_control_oos_n"], "candidate_stats_matched_control_oos_n")
    delta = candidate_mean - control_mean
    n_eff = min(candidate_oos_n, control_oos_n)
    prior_n = _finite_number(policy["prior_n"], "selector_policy_prior_n")
    prior_delta_bps = _finite_number(policy["prior_delta_bps"], "selector_policy_prior_delta_bps")
    lcb_z = _finite_number(policy["lcb_z"], "selector_policy_lcb_z")
    shrinkage_weight = n_eff / (n_eff + prior_n)
    shrunk_delta = prior_delta_bps + shrinkage_weight * (delta - prior_delta_bps)
    se = math.sqrt(
        (candidate_std * candidate_std / candidate_oos_n)
        + (control_std * control_std / control_oos_n)
    )
    conservative_lcb = shrunk_delta - lcb_z * se
    terms_values = {field: _finite_number(terms[field], f"candidate_terms_{field}") for field in _REQUIRED_TERMS_FIELDS}
    score = (
        conservative_lcb
        + terms_values["voi_bps"]
        - terms_values["offline_cost_bps"]
        - terms_values["governance_risk_bps"]
        - terms_values["staleness_penalty_bps"]
        - terms_values["evidence_gap_penalty_bps"]
    )
    evidence_gaps = _candidate_evidence_gaps(identity, evidence, stats, flags, policy)
    min_score = 0.0
    selectable = (
        not evidence_gaps
        and score > min_score
        and flags.get("hypothesis_only") is not True
        and flags.get("blocked") is not True
    )
    score_components = {
        "candidate_net_bps_mean": candidate_mean,
        "matched_control_net_bps_mean": control_mean,
        "candidate_net_bps_std": candidate_std,
        "matched_control_net_bps_std": control_std,
        "candidate_oos_n": candidate_oos_n,
        "matched_control_oos_n": control_oos_n,
        "delta": delta,
        "n_eff": n_eff,
        "shrinkage_weight": shrinkage_weight,
        "shrunk_delta": shrunk_delta,
        "se": se,
        "conservative_lcb": conservative_lcb,
        "voi_bps": terms_values["voi_bps"],
        "offline_cost_bps": terms_values["offline_cost_bps"],
        "governance_risk_bps": terms_values["governance_risk_bps"],
        "staleness_penalty_bps": terms_values["staleness_penalty_bps"],
        "evidence_gap_penalty_bps": terms_values["evidence_gap_penalty_bps"],
        "score": score,
    }
    return {
        "candidate_id": _candidate_id(identity),
        "identity": identity,
        "evidence": evidence,
        "stats": stats,
        "terms": terms,
        "flags": flags,
        "score_components": score_components,
        "score": score,
        "evidence_complete": not evidence_gaps,
        "evidence_gaps": evidence_gaps,
        "selection_eligible": selectable,
    }


def _select_decision(
    *,
    snapshot: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    hash_matches: bool,
    boundary_reasons: Sequence[str],
) -> tuple[str, dict[str, Any] | None, list[str]]:
    if boundary_reasons:
        return DECISION_BLOCKED_BOUNDARY, None, list(boundary_reasons)
    if not hash_matches:
        return DECISION_ROTATED, None, ["snapshot_hash_mismatch"]
    selected = next((candidate for candidate in candidates if candidate.get("selection_eligible") is True), None)
    if selected is not None:
        return DECISION_SELECT_TARGET, dict(selected), ["selected_highest_scored_complete_candidate"]
    all_gaps = sorted({gap for candidate in candidates for gap in candidate.get("evidence_gaps", [])})
    if all_gaps:
        return DECISION_DEFER_EVIDENCE, None, all_gaps
    max_score = max((float(candidate["score"]) for candidate in candidates), default=0.0)
    min_score = 0.0
    if _proof_ready_controlled_oos_evidence(snapshot) and max_score <= min_score:
        return DECISION_STOP_NO_EDGE, None, ["proof_ready_controlled_oos_no_positive_score"]
    return DECISION_HYPOTHESIS_ONLY, None, ["no_positive_selectable_candidate_without_proof_ready_stop_gate"]


def _candidate_evidence_gaps(
    identity: Mapping[str, Any],
    evidence: Mapping[str, Any],
    stats: Mapping[str, Any],
    flags: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> list[str]:
    gaps: list[str] = []
    if not _non_empty_text(evidence.get("pit_dataset_manifest_hash")):
        gaps.append("missing_pit_dataset_manifest_hash")
    if not _non_empty_text_list(evidence.get("matched_control_ids")):
        gaps.append("missing_matched_control_ids")
    if not _non_empty_text_list(evidence.get("negative_cell_ids")):
        gaps.append("missing_negative_cell_ids")
    if not isinstance(evidence.get("regime_labels"), Mapping) or not evidence["regime_labels"]:
        gaps.append("missing_regime_labels")
    for flag in _REQUIRED_TRUE_FLAGS:
        if flags.get(flag) is not True:
            gaps.append(f"{flag}_not_true")
    candidate_oos_n = _finite_number(stats["candidate_oos_n"], "candidate_stats_candidate_oos_n")
    control_oos_n = _finite_number(stats["matched_control_oos_n"], "candidate_stats_matched_control_oos_n")
    min_candidate_oos_n = _finite_number(policy["min_candidate_oos_n"], "selector_policy_min_candidate_oos_n")
    min_control_oos_n = _finite_number(policy["min_control_oos_n"], "selector_policy_min_control_oos_n")
    if candidate_oos_n < min_candidate_oos_n:
        gaps.append("candidate_oos_n_below_min")
    if control_oos_n < min_control_oos_n:
        gaps.append("matched_control_oos_n_below_min")
    candidate_ids = _mapping(policy).get("_frozen_candidate_ids")
    if isinstance(candidate_ids, set) and _candidate_id(identity) not in candidate_ids:
        gaps.append("candidate_not_in_frozen_universe")
    return gaps


def _boundary_contamination_reasons(snapshot: Mapping[str, Any]) -> list[str]:
    reasons = _truthy_no_authority_reasons(snapshot.get("no_authority"))
    reasons.extend(_truthy_authority_alias_reasons(snapshot))
    return sorted(set(reasons))


def _truthy_no_authority_reasons(value: Any, prefix: str = "no_authority") -> list[str]:
    reasons: list[str] = []
    if not isinstance(value, Mapping):
        return [f"{prefix}_not_mapping"]
    for key, item in value.items():
        path = f"{prefix}.{key}"
        if isinstance(item, Mapping):
            reasons.extend(_truthy_no_authority_reasons(item, path))
        elif isinstance(item, list):
            for index, child in enumerate(item):
                if _truthy(child):
                    reasons.append(f"no_authority_truthy:{path}[{index}]")
        elif item is not False:
            reasons.append(f"no_authority_not_false:{path}")
    return reasons


def _truthy_authority_alias_reasons(value: Any, path: str = "$") -> list[str]:
    reasons: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path != "$" else key_text
            normalized = key_text.lower()
            if normalized not in _AUTHORITY_EXEMPT_KEYS and _authority_key(normalized) and _truthy(item):
                reasons.append(f"authority_contamination:{child_path}")
            reasons.extend(_truthy_authority_alias_reasons(item, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reasons.extend(_truthy_authority_alias_reasons(item, f"{path}[{index}]"))
    return reasons


def _authority_key(normalized_key: str) -> bool:
    has_term = any(term in normalized_key for term in _AUTHORITY_KEY_TERMS)
    has_action = any(action in normalized_key for action in _AUTHORITY_ACTION_TERMS)
    return has_term and (has_action or normalized_key in _AUTHORITY_KEY_TERMS)


def _proof_ready_controlled_oos_evidence(snapshot: Mapping[str, Any]) -> bool:
    if snapshot.get("proof_ready_controlled_oos_evidence") is True:
        return True
    policy = _mapping(snapshot.get("selector_policy"))
    if policy.get("proof_ready_controlled_oos_evidence") is True:
        return True
    candidates = snapshot.get("candidates")
    if isinstance(candidates, list) and candidates:
        return all(_mapping(_mapping(candidate).get("flags")).get("proof_ready_controlled_oos_evidence") is True for candidate in candidates)
    return False


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AlrStatSelectorBaselineError(f"{label}_not_numeric")
    number = float(value)
    if not math.isfinite(number):
        raise AlrStatSelectorBaselineError(f"{label}_not_finite")
    return number


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _candidate_id(identity: Mapping[str, Any]) -> str:
    value = identity.get("candidate_id")
    return value if isinstance(value, str) and value else ""


def _non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _non_empty_text_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_non_empty_text(item) for item in value)
    )


def _zero_authority_counters() -> dict[str, int]:
    return {key: 0 for key in _AUTHORITY_COUNTER_KEYS}


def _false_no_authority() -> dict[str, bool]:
    return {key: False for key in _NO_AUTHORITY_KEYS}


def _all_false(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(_all_false(item) for item in value.values())
    if isinstance(value, list):
        return all(_all_false(item) for item in value)
    return value is False


def _all_zero(value: Any) -> bool:
    if not isinstance(value, Mapping) or not value:
        return False
    return all(item == 0 and not isinstance(item, bool) for item in value.values())


def _truthy(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_truthy(item) for item in value.values())
    if isinstance(value, list):
        return any(_truthy(item) for item in value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        return bool(normalized) and normalized not in _FALSE_STRINGS
    return bool(value)


def _contains_latest_ref(value: Any, key_path: str = "") -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            path = f"{key_path}.{key_text}" if key_path else key_text
            if _contains_latest_ref(item, path):
                return True
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if _contains_latest_ref(item, f"{key_path}[{index}]"):
                return True
    elif isinstance(value, str) and "_latest" in value.lower() and _is_ref_key(key_path):
        return True
    return False


def _is_ref_key(key_path: str) -> bool:
    normalized = key_path.lower()
    return any(
        "path" in part or "ref" in part or "source" in part or "alias" in part
        for part in normalized.split(".")
    )


def _reject_latest_path(path: Path, label: str) -> None:
    if any("_latest" in part.lower() for part in path.parts):
        raise AlrStatSelectorBaselineError(f"{label}_path_latest_rejected")


def _write_selector_output(output: Mapping[str, Any], path: Path) -> None:
    _reject_latest_path(path, "out")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(output, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _canonical_sha256(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


if __name__ == "__main__":  # pragma: no cover - exercised by CLI tests
    raise SystemExit(main())
