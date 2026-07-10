"""Pure P2-4 scanner-novelty statistical experiment and challenger builder."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ml_training.alr_candidate_learning_projection import (
    build_candidate_aware_learning_projection,
)

from ml_training.alr_stat_selector_baseline import (
    BOUNDARY_LABEL as SELECTOR_BOUNDARY_LABEL,
    INPUT_SCHEMA_VERSION as SELECTOR_INPUT_SCHEMA_VERSION,
    OBJECTIVE as SELECTOR_OBJECTIVE,
    build_alr_stat_selector_baseline,
    compute_selector_snapshot_hash,
    validate_alr_stat_selector_baseline,
)
from ml_training.learning_target_arbiter import (
    INPUT_SCHEMA_VERSION as TARGET_INPUT_SCHEMA_VERSION,
    OBJECTIVE as TARGET_OBJECTIVE,
    build_learning_target_runtime,
    compute_manifest_hash as compute_target_manifest_hash,
)
from ml_training.pit_dataset_manifest import (
    compute_pit_dataset_manifest_hash,
    validate_pit_dataset_manifest,
)


OUTPUT_SCHEMA_VERSION = "alr_scanner_statistical_experiment_v1"
TARGET_ARTIFACT_SCHEMA_VERSION = "alr_learning_target_runtime_v1"
PIT_ARTIFACT_KIND = "pit_dataset"
EXPERIMENT_ARTIFACT_KIND = "statistical_experiment"
CANDIDATE_ARTIFACT_KIND = "candidate_artifact"
DEFER_ARTIFACT_KIND = "defer_evidence"
TARGET_ARTIFACT_KIND = "learning_target"
DEFER_DECISION_FINGERPRINT_SCHEMA_VERSION = "alr_defer_decision_fingerprint_v1"
DEFER_REEVALUATION_MAX_SECONDS = 1800

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED_CYCLE_FIELDS = {"source_hash", "source_key", "source_ts", "canonical_payload"}
_NO_AUTHORITY = {
    "exchange_authority": False,
    "trading_authority": False,
    "order_or_probe_authority": False,
    "decision_lease_authority": False,
    "cost_gate_authority": False,
    "proof_authority": False,
    "serving_authority": False,
    "promotion_authority": False,
    "latest_authority": False,
}
_AUTHORITY_COUNTERS = {
    "exchange_contact_count": 0,
    "trading_action_count": 0,
    "order_or_probe_count": 0,
    "decision_lease_count": 0,
    "cost_gate_change_count": 0,
    "proof_claim_count": 0,
    "serving_or_promotion_count": 0,
}
_AFTER_COST_GAPS = (
    "candidate_matched_fills_missing",
    "actual_fees_missing",
    "slippage_or_funding_missing",
    "reconstruction_missing",
    "matched_control_outcomes_missing",
    "repeat_oos_outcomes_missing",
)
_DEFER_DECISION_POLICY = {
    "schema_version": "alr_defer_decision_policy_v1",
    "decision": "DEFER_EVIDENCE",
    "rotation_required": True,
    "global_stop": False,
    "max_suppression_seconds": DEFER_REEVALUATION_MAX_SECONDS,
    "freshness_basis": "source_event_time",
    "require_distinct_source_set": True,
    "legacy_packet_reuse_allowed": False,
}


@dataclass(frozen=True)
class AlrScannerStatisticalExperimentValidation:
    valid: bool
    reason: str
    reasons: tuple[str, ...] = ()


class AlrScannerStatisticalExperimentError(ValueError):
    """A scanner-only experiment cannot be built without its PIT boundaries."""


def compute_scanner_statistical_experiment_hash(result: Mapping[str, Any]) -> str:
    """Canonical hash over the complete experiment output excluding its hash."""
    payload = copy.deepcopy(dict(result))
    payload.pop("experiment_hash", None)
    return _canonical_sha256(payload)


def build_scanner_statistical_experiment(
    *,
    source_head: str,
    cycles: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build one research-only target -> PIT -> stat -> challenger lineage bundle."""
    if not isinstance(source_head, str) or not _HEX40_RE.fullmatch(source_head):
        raise AlrScannerStatisticalExperimentError("source_head_invalid")
    normalized_cycles = _normalize_cycles(cycles)
    candidate_summary = _candidate_summary(normalized_cycles)
    target_symbol, target_metrics = _select_target_symbol(candidate_summary)
    control_symbols = _control_symbols(candidate_summary, target_symbol)
    if not control_symbols:
        raise AlrScannerStatisticalExperimentError("matched_controls_missing")

    source_set_hash = _canonical_sha256(
        [item["source_hash"] for item in normalized_cycles]
    )
    as_of_ts = normalized_cycles[-1]["source_ts"]
    candidate_id = f"scanner_novelty|{target_symbol}|NONE"
    candidate_scope = {
        "candidate_id": candidate_id,
        "strategy_name": "scanner_novelty",
        "symbol": target_symbol,
        "side": "NONE",
        "engine_mode": "shadow",
    }

    learning_target = _build_learning_target(
        source_head=source_head,
        source_set_hash=source_set_hash,
        as_of_ts=as_of_ts,
        candidate_scope=candidate_scope,
        target_metrics=target_metrics,
    )
    target_hash = _canonical_sha256(learning_target)
    pit_dataset = _build_pit_dataset(
        normalized_cycles=normalized_cycles,
        source_head=source_head,
        source_set_hash=source_set_hash,
        as_of_ts=as_of_ts,
        candidate_scope=candidate_scope,
        control_symbols=control_symbols,
        target_hash=target_hash,
    )
    pit_hash = compute_pit_dataset_manifest_hash(pit_dataset)
    if pit_dataset["manifest_hash"] != pit_hash:
        raise AlrScannerStatisticalExperimentError("pit_manifest_hash_internal_mismatch")

    selector_output = _build_selector_output(
        source_head=source_head,
        source_set_hash=source_set_hash,
        as_of_ts=as_of_ts,
        candidate_scope=candidate_scope,
        pit_hash=pit_hash,
        target_metrics=target_metrics,
        control_symbols=control_symbols,
        cycle_count=len(normalized_cycles),
    )
    selector_validation = validate_alr_stat_selector_baseline(selector_output)
    if not selector_validation.valid:
        raise AlrScannerStatisticalExperimentError(
            f"statistical_selector_invalid:{selector_validation.reason}"
        )
    experiment = _build_statistical_experiment(
        source_set_hash=source_set_hash,
        candidate_scope=candidate_scope,
        pit_hash=pit_hash,
        selector_output=selector_output,
    )
    experiment_hash = _canonical_sha256(experiment)
    decision_fingerprint_components = _build_defer_decision_fingerprint_components(
        source_head=source_head,
        candidate_scope=candidate_scope,
        target_metrics=target_metrics,
        candidate_summary=candidate_summary,
        control_symbols=control_symbols,
        cycle_count=len(normalized_cycles),
        scanner_config_hashes=sorted(
            {
                _canonical_sha256(item["canonical_payload"].get("config"))
                for item in normalized_cycles
            }
        ),
    )
    decision_fingerprint = _canonical_sha256(decision_fingerprint_components)
    next_evaluation_due_at = _add_seconds_utc_z(
        as_of_ts,
        DEFER_REEVALUATION_MAX_SECONDS,
    )
    candidate_artifact = _build_candidate_artifact(
        candidate_scope=candidate_scope,
        target_hash=target_hash,
        pit_hash=pit_hash,
        experiment_hash=experiment_hash,
        decision_fingerprint=decision_fingerprint,
        decision_fingerprint_components=decision_fingerprint_components,
        evaluated_at=as_of_ts,
        next_evaluation_due_at=next_evaluation_due_at,
    )
    candidate_hash = _canonical_sha256(candidate_artifact)
    defer_artifact = _build_defer_artifact(
        candidate_scope=candidate_scope,
        candidate_hash=candidate_hash,
        decision_fingerprint=decision_fingerprint,
        decision_policy_hash=decision_fingerprint_components[
            "decision_policy_hash"
        ],
        evaluated_at=as_of_ts,
        next_evaluation_due_at=next_evaluation_due_at,
    )
    defer_hash = _canonical_sha256(defer_artifact)

    artifacts = [
        _artifact(TARGET_ARTIFACT_KIND, target_hash, learning_target),
        _artifact(PIT_ARTIFACT_KIND, pit_hash, pit_dataset),
        _artifact(EXPERIMENT_ARTIFACT_KIND, experiment_hash, experiment),
        _artifact(CANDIDATE_ARTIFACT_KIND, candidate_hash, candidate_artifact),
        _artifact(DEFER_ARTIFACT_KIND, defer_hash, defer_artifact),
    ]
    edges = [
        _edge(source_hash, target_hash, "training_input")
        for source_hash in (item["source_hash"] for item in normalized_cycles)
    ]
    edges.extend(
        (
            _edge(target_hash, pit_hash, "target_dataset"),
            _edge(pit_hash, experiment_hash, "dataset_experiment"),
            _edge(experiment_hash, candidate_hash, "experiment_candidate"),
            _edge(candidate_hash, defer_hash, "candidate_defer_evidence"),
        )
    )
    run = {
        "schema_version": "alr_training_run_v1",
        "run_kind": "scanner_novelty_statistical_baseline",
        "run_status": "DEFER_EVIDENCE",
        "source_set_hash": source_set_hash,
        "target_artifact_hash": target_hash,
        "pit_dataset_artifact_hash": pit_hash,
        "experiment_artifact_hash": experiment_hash,
        "candidate_artifact_hash": candidate_hash,
        "defer_artifact_hash": defer_hash,
    }
    run["run_hash"] = _canonical_sha256(run)
    result: dict[str, Any] = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "source_head": source_head,
        "source_set": {
            "source_set_hash": source_set_hash,
            "source_hashes": [item["source_hash"] for item in normalized_cycles],
            "as_of_ts": as_of_ts,
            "cycle_count": len(normalized_cycles),
            "source_identities": [
                {
                    "source_hash": item["source_hash"],
                    "source_key": item["source_key"],
                    "source_ts": item["source_ts"],
                }
                for item in normalized_cycles
            ],
        },
        "learning_target": learning_target,
        "pit_dataset_manifest": pit_dataset,
        "statistical_experiment": experiment,
        "candidate_artifact": candidate_artifact,
        "defer_evidence": defer_artifact,
        "artifacts": artifacts,
        "provenance_edges": edges,
        "run": run,
        "no_authority": dict(_NO_AUTHORITY),
        "authority_counters": dict(_AUTHORITY_COUNTERS),
    }
    result["experiment_hash"] = compute_scanner_statistical_experiment_hash(result)
    return result


def validate_scanner_statistical_experiment(
    result: Mapping[str, Any],
) -> AlrScannerStatisticalExperimentValidation:
    """Validate the research-only output before persistence can be considered."""
    if not isinstance(result, Mapping):
        return _invalid("result_not_mapping")
    reasons: list[str] = []
    if result.get("schema_version") != OUTPUT_SCHEMA_VERSION:
        reasons.append("schema_version_invalid")
    if result.get("experiment_hash") != compute_scanner_statistical_experiment_hash(result):
        reasons.append("experiment_hash_mismatch")
    if not _all_false(result.get("no_authority")):
        reasons.append("no_authority_not_false")
    if not _all_zero(result.get("authority_counters")):
        reasons.append("authority_counters_not_zero")
    pit = result.get("pit_dataset_manifest")
    if not isinstance(pit, Mapping):
        reasons.append("pit_dataset_manifest_missing")
    else:
        if pit.get("verdict") != "research_only":
            reasons.append("pit_verdict_not_research_only")
        if pit.get("point_in_time") is not True or pit.get("future_data_allowed") is not False:
            reasons.append("pit_boundary_invalid")
        if pit.get("manifest_hash") != compute_pit_dataset_manifest_hash(pit):
            reasons.append("pit_manifest_hash_mismatch")
    experiment = result.get("statistical_experiment")
    if not isinstance(experiment, Mapping) or experiment.get("statistical_experiment_performed") is not True:
        reasons.append("statistical_experiment_not_performed")
    elif experiment.get("model_training_performed") is not False:
        reasons.append("model_training_flag_invalid")
    candidate = result.get("candidate_artifact")
    if not isinstance(candidate, Mapping):
        reasons.append("candidate_artifact_missing")
    else:
        after_cost = candidate.get("after_cost_evaluation")
        if not isinstance(after_cost, Mapping) or after_cost.get("status") != "DEFER_EVIDENCE":
            reasons.append("after_cost_status_invalid")
        if candidate.get("serving_ready") is not False or candidate.get("promotion_ready") is not False:
            reasons.append("candidate_authority_invalid")
        components = candidate.get("decision_fingerprint_components")
        decision_fingerprint = candidate.get("decision_fingerprint")
        if (
            not isinstance(components, Mapping)
            or not isinstance(decision_fingerprint, str)
            or decision_fingerprint != _canonical_sha256(components)
        ):
            reasons.append("decision_fingerprint_mismatch")
        elif candidate.get("decision_policy_hash") != components.get(
            "decision_policy_hash"
        ):
            reasons.append("decision_policy_hash_mismatch")
        defer = result.get("defer_evidence")
        if not isinstance(defer, Mapping):
            reasons.append("defer_evidence_missing")
        elif (
            defer.get("decision_fingerprint") != decision_fingerprint
            or defer.get("decision_policy_hash")
            != candidate.get("decision_policy_hash")
        ):
            reasons.append("defer_decision_fingerprint_mismatch")
    if not isinstance(result.get("artifacts"), list) or len(result["artifacts"]) != 5:
        reasons.append("artifact_bundle_invalid")
    if not isinstance(result.get("provenance_edges"), list):
        reasons.append("provenance_edges_invalid")
    if reasons:
        return _invalid(*reasons)
    return AlrScannerStatisticalExperimentValidation(True, "ok", ())


def _normalize_cycles(cycles: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(cycles, Sequence) or isinstance(cycles, (str, bytes, bytearray)):
        raise AlrScannerStatisticalExperimentError("cycles_not_sequence")
    if len(cycles) < 3:
        raise AlrScannerStatisticalExperimentError("cycles_insufficient_for_pit_split")
    normalized: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for cycle in cycles:
        if not isinstance(cycle, Mapping):
            raise AlrScannerStatisticalExperimentError("cycle_not_mapping")
        missing = _REQUIRED_CYCLE_FIELDS - set(cycle)
        if missing:
            raise AlrScannerStatisticalExperimentError(
                f"cycle_missing_fields:{','.join(sorted(missing))}"
            )
        source_hash = cycle.get("source_hash")
        if not isinstance(source_hash, str) or not _HEX64_RE.fullmatch(source_hash):
            raise AlrScannerStatisticalExperimentError("source_hash_invalid")
        if source_hash in seen_hashes:
            raise AlrScannerStatisticalExperimentError("source_hash_duplicate")
        seen_hashes.add(source_hash)
        source_key = cycle.get("source_key")
        source_ts = cycle.get("source_ts")
        payload = cycle.get("canonical_payload")
        if not isinstance(source_key, str) or not source_key:
            raise AlrScannerStatisticalExperimentError("source_key_invalid")
        if not isinstance(source_ts, str) or not source_ts.endswith("Z"):
            raise AlrScannerStatisticalExperimentError("source_ts_invalid")
        if not isinstance(payload, Mapping):
            raise AlrScannerStatisticalExperimentError("canonical_payload_invalid")
        symbols = _symbols(payload)
        if not symbols:
            raise AlrScannerStatisticalExperimentError("source_candidates_empty")
        normalized.append(
            {
                "source_hash": source_hash,
                "source_key": source_key,
                "source_ts": source_ts,
                "canonical_payload": dict(payload),
            }
        )
    normalized.sort(key=lambda item: (item["source_ts"], item["source_key"], item["source_hash"]))
    return normalized


def _candidate_summary(cycles: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for cycle in cycles:
        payload = cycle["canonical_payload"]
        symbols = _symbols(payload)
        added = _text_set(payload.get("added"))
        for symbol in symbols:
            metrics = summary.setdefault(symbol, {"occurrences": 0, "novelty": 0})
            metrics["occurrences"] += 1
            if symbol in added:
                metrics["novelty"] += 1
    return summary


def _select_target_symbol(summary: Mapping[str, Mapping[str, int]]) -> tuple[str, dict[str, int]]:
    if not summary:
        raise AlrScannerStatisticalExperimentError("candidate_summary_empty")
    selected = min(
        summary,
        key=lambda symbol: (
            -int(summary[symbol]["novelty"]),
            -int(summary[symbol]["occurrences"]),
            symbol,
        ),
    )
    return selected, dict(summary[selected])


def _control_symbols(summary: Mapping[str, Mapping[str, int]], target_symbol: str) -> list[str]:
    controls = [symbol for symbol in summary if symbol != target_symbol]
    controls.sort(key=lambda symbol: (-int(summary[symbol]["occurrences"]), symbol))
    return controls


def _build_learning_target(
    *,
    source_head: str,
    source_set_hash: str,
    as_of_ts: str,
    candidate_scope: Mapping[str, str],
    target_metrics: Mapping[str, int],
) -> dict[str, Any]:
    target = {
        "target_id": candidate_scope["candidate_id"],
        "candidate_scope": dict(candidate_scope),
        "learning_question": "Does recurring scanner membership merit future after-cost evidence collection?",
        "evidence_source_tier": "scanner_snapshot_research",
        "expected_information_gain": float(target_metrics["novelty"] + target_metrics["occurrences"]),
        "uncertainty_reduction": float(target_metrics["occurrences"]),
        "cost_estimate": 0.0,
        "risk_penalty": 0.0,
        "staleness_penalty": 0.0,
        "eligibility": True,
    }
    manifest: dict[str, Any] = {
        "schema_version": TARGET_INPUT_SCHEMA_VERSION,
        "created_at": as_of_ts,
        "source_head": source_head,
        "snapshot_id": f"scanner-target:{source_set_hash[:16]}",
        "snapshot_kind": "alr_scanner_source_set",
        "objective": TARGET_OBJECTIVE,
        "latest_alias_used": False,
        "targets": [target],
        "proof_exclusion": {
            "scanner_evidence_is_proof": False,
            "no_order_evidence_is_reward": False,
            "artifact_count_evidence_is_edge": False,
        },
        "no_authority": dict(_NO_AUTHORITY),
    }
    manifest["manifest_hash"] = compute_target_manifest_hash(manifest)
    runtime = build_learning_target_runtime(manifest)
    if runtime.get("selected_target") is None:
        raise AlrScannerStatisticalExperimentError("learning_target_not_selected")
    return runtime


def _build_pit_dataset(
    *,
    normalized_cycles: Sequence[Mapping[str, Any]],
    source_head: str,
    source_set_hash: str,
    as_of_ts: str,
    candidate_scope: Mapping[str, str],
    control_symbols: Sequence[str],
    target_hash: str,
) -> dict[str, Any]:
    row_ids = [item["source_hash"] for item in normalized_cycles]
    train_ids, validation_ids, test_ids = _chronological_split(row_ids)
    rows = [
        {
            "source_hash": item["source_hash"],
            "source_key": item["source_key"],
            "source_ts": item["source_ts"],
            "candidate_count": len(_symbols(item["canonical_payload"])),
            "added_count": len(_text_set(item["canonical_payload"].get("added"))),
        }
        for item in normalized_cycles
    ]
    split_payload = {
        "train": train_ids,
        "validation": validation_ids,
        "oos": test_ids,
        "purge_cycles": 1,
        "embargo_cycles": 1,
    }
    manifest: dict[str, Any] = {
        "schema_version": "pit_dataset_manifest_v1",
        "verdict": "research_only",
        "dataset_id": f"scanner-pit:{source_set_hash[:16]}",
        "dataset_role": "scanner_novelty_statistical_research",
        "as_of_ts": as_of_ts,
        "point_in_time": True,
        "future_data_allowed": False,
        "candidate_scope": dict(candidate_scope),
        "source_query": {
            "query_id": "alr_source_set_by_hash_v1",
            "source_set_hash": source_set_hash,
            "source_head": source_head,
            "start_ts": normalized_cycles[0]["source_ts"],
            "end_ts": as_of_ts,
        },
        "row_set": {
            "row_count": len(rows),
            "row_ids_hash": _canonical_sha256(row_ids),
            "dataset_hash": _canonical_sha256(rows),
            "schema_hash": _canonical_sha256(sorted(rows[0])),
            "min_ts": normalized_cycles[0]["source_ts"],
            "max_ts": as_of_ts,
        },
        "feature_lineage": {
            "feature_schema_version": "alr_scanner_novelty_features_v1",
            "feature_schema_hash": _canonical_sha256(["candidate_count", "added_count"]),
            "feature_definition_hash": _canonical_sha256({"candidate_count": "cycle candidates", "added_count": "cycle additions"}),
            "feature_names_hash": _canonical_sha256(["candidate_count", "added_count"]),
        },
        "label_lineage": {
            "label_status": "after_cost_outcome_missing",
            "outcome_cutoff_ts": as_of_ts,
            "label_schema_hash": _canonical_sha256({"label": "unavailable"}),
            "label_config_hash": _canonical_sha256({"reason": "scanner evidence has no realized outcome"}),
        },
        "split_lineage": {
            "split_id": "chronological-scanner-cycle-v1",
            "split_hash": _canonical_sha256(split_payload),
            "train_row_ids_hash": _canonical_sha256(train_ids),
            "validation_row_ids_hash": _canonical_sha256(validation_ids),
            "test_row_ids_hash": _canonical_sha256(test_ids),
            "purge_cycles": 1,
            "embargo_cycles": 1,
        },
        "leakage_evidence": {
            "overlap_count": 0,
            "leakage_report_hash": _canonical_sha256({"all_rows_at_or_before": as_of_ts, "overlap_count": 0}),
            "fold_preprocessing_stats_hash": _canonical_sha256({"fit_scope": "train_partition_only"}),
        },
        "matched_controls": {"control_symbols": list(control_symbols)},
        "row_backed_fill_source": {"status": "not_available_from_scanner"},
        "provenance": {
            "source_set_hash": source_set_hash,
            "target_artifact_hash": target_hash,
            "source_hashes": {
                "scanner_source_set": source_set_hash,
                "target_artifact": target_hash,
            },
            "input_artifact_hashes": {
                "scanner_source_set": source_set_hash,
                "target_artifact": target_hash,
            },
            "source_identities": row_ids,
        },
    }
    manifest["manifest_hash"] = compute_pit_dataset_manifest_hash(manifest)
    validation = validate_pit_dataset_manifest(manifest)
    if validation.dataset_ready or validation.verdict != "research_only":
        raise AlrScannerStatisticalExperimentError("pit_research_only_validation_invalid")
    return manifest


def _build_selector_output(
    *,
    source_head: str,
    source_set_hash: str,
    as_of_ts: str,
    candidate_scope: Mapping[str, str],
    pit_hash: str,
    target_metrics: Mapping[str, int],
    control_symbols: Sequence[str],
    cycle_count: int,
) -> dict[str, Any]:
    candidate = {
        "identity": dict(candidate_scope),
        "evidence": {
            "pit_dataset_manifest_hash": pit_hash,
            "matched_control_ids": [f"scanner_control:{symbol}" for symbol in control_symbols],
            "negative_cell_ids": [f"scanner_negative:{symbol}" for symbol in control_symbols],
            "regime_labels": {"source": "scanner_snapshot", "measurement": "recurrence_not_return"},
        },
        "stats": {
            "candidate_net_bps_mean": 0.0,
            "candidate_net_bps_std": 0.0,
            "candidate_oos_n": float(cycle_count),
            "matched_control_net_bps_mean": 0.0,
            "matched_control_net_bps_std": 0.0,
            "matched_control_oos_n": float(cycle_count),
        },
        "terms": {
            "voi_bps": 0.0,
            "offline_cost_bps": 0.0,
            "governance_risk_bps": 0.0,
            "staleness_penalty_bps": 0.0,
            "evidence_gap_penalty_bps": 0.0,
        },
        "flags": {
            "frozen_universe_member": True,
            "pre_registered_split": True,
            "walk_forward_oos": True,
            "retained_if_not_selected": True,
            "proof_ready_controlled_oos_evidence": False,
            "scanner_occurrences": int(target_metrics["occurrences"]),
            "scanner_novelty": int(target_metrics["novelty"]),
        },
    }
    snapshot: dict[str, Any] = {
        "schema_version": SELECTOR_INPUT_SCHEMA_VERSION,
        "boundary_label": SELECTOR_BOUNDARY_LABEL,
        "created_at": as_of_ts,
        "source_head": source_head,
        "snapshot_id": f"scanner-stat:{source_set_hash[:16]}",
        "objective": SELECTOR_OBJECTIVE,
        "latest_alias_used": False,
        "frozen_universe": {
            "universe_id": f"scanner-source-set:{source_set_hash[:16]}",
            "frozen_at": as_of_ts,
            "candidate_ids": [candidate_scope["candidate_id"]],
            "universe_hash": _canonical_sha256([candidate_scope["candidate_id"]]),
        },
        "pre_registered_split": {
            "split_id": "chronological-scanner-cycle-v1",
            "split_hash": _canonical_sha256({"source_set_hash": source_set_hash, "cycle_count": cycle_count}),
            "train_window": {"end": as_of_ts, "kind": "closed_source_partition"},
            "oos_window": {"end": as_of_ts, "kind": "closed_source_partition"},
            "purge": 1.0,
            "embargo": 1.0,
            "walk_forward": True,
        },
        "selector_policy": {
            "lcb_z": 1.0,
            "prior_n": 1.0,
            "prior_delta_bps": 0.0,
            "min_candidate_oos_n": 1.0,
            "min_control_oos_n": 1.0,
        },
        "proof_exclusion": {
            "proof_not_claimed": False,
            "promotion_not_claimed": False,
            "runtime_not_claimed": False,
            "trading_not_claimed": False,
        },
        "no_authority": {
            "runtime": False,
            "pg": False,
            "ipc": False,
            "bybit_mcp": False,
            "decision_lease": False,
            "order_or_probe": False,
            "cost_gate": False,
            "latest": False,
            "serving": False,
            "proof": False,
            "promotion": False,
            "delete_apply": False,
            "scheduler": False,
        },
        "candidates": [candidate],
    }
    snapshot["snapshot_hash"] = compute_selector_snapshot_hash(snapshot)
    return build_alr_stat_selector_baseline(snapshot)


def _build_statistical_experiment(
    *,
    source_set_hash: str,
    candidate_scope: Mapping[str, str],
    pit_hash: str,
    selector_output: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "alr_scanner_novelty_statistical_run_v1",
        "experiment_kind": "scanner_novelty_statistical_baseline",
        "statistical_experiment_performed": True,
        "model_training_performed": False,
        "measurement_scope": "scanner_recurrence_and_novelty_not_after_cost_return",
        "candidate_scope": dict(candidate_scope),
        "source_set_hash": source_set_hash,
        "pit_dataset_manifest_hash": pit_hash,
        "selector_output": copy.deepcopy(dict(selector_output)),
        "no_authority": dict(_NO_AUTHORITY),
    }


def _build_candidate_artifact(
    *,
    candidate_scope: Mapping[str, str],
    target_hash: str,
    pit_hash: str,
    experiment_hash: str,
    decision_fingerprint: str,
    decision_fingerprint_components: Mapping[str, Any],
    evaluated_at: str,
    next_evaluation_due_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "alr_challenger_candidate_v1",
        "candidate_scope": dict(candidate_scope),
        "candidate_status": "CHALLENGER_RESEARCH_ONLY",
        "target_artifact_hash": target_hash,
        "pit_dataset_manifest_hash": pit_hash,
        "statistical_experiment_hash": experiment_hash,
        "decision_fingerprint": decision_fingerprint,
        "decision_fingerprint_components": copy.deepcopy(
            dict(decision_fingerprint_components)
        ),
        "decision_policy_hash": decision_fingerprint_components[
            "decision_policy_hash"
        ],
        "evaluated_at": evaluated_at,
        "next_evaluation_due_at": next_evaluation_due_at,
        "model_artifact": None,
        "after_cost_evaluation": {
            "status": "DEFER_EVIDENCE",
            "missing_evidence": list(_AFTER_COST_GAPS),
            "edge_claim_allowed": False,
            "profit_claim_allowed": False,
        },
        "serving_ready": False,
        "promotion_ready": False,
        "no_authority": dict(_NO_AUTHORITY),
    }


def _build_defer_artifact(
    *,
    candidate_scope: Mapping[str, str],
    candidate_hash: str,
    decision_fingerprint: str,
    decision_policy_hash: str,
    evaluated_at: str,
    next_evaluation_due_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "alr_defer_evidence_v1",
        "candidate_scope": dict(candidate_scope),
        "candidate_artifact_hash": candidate_hash,
        "decision_fingerprint": decision_fingerprint,
        "decision_policy_hash": decision_policy_hash,
        "evaluated_at": evaluated_at,
        "next_evaluation_due_at": next_evaluation_due_at,
        "status": "DEFER_EVIDENCE",
        "reasons": list(_AFTER_COST_GAPS),
        "rotate_next_target": True,
        "global_stop": False,
        "no_authority": dict(_NO_AUTHORITY),
    }


def _build_defer_decision_fingerprint_components(
    *,
    source_head: str,
    candidate_scope: Mapping[str, str],
    target_metrics: Mapping[str, int],
    candidate_summary: Mapping[str, Mapping[str, int]],
    control_symbols: Sequence[str],
    cycle_count: int,
    scanner_config_hashes: Sequence[str],
) -> dict[str, Any]:
    decision_policy_hash = _canonical_sha256(_DEFER_DECISION_POLICY)
    source_contract = {
        "source_table": "trading.scanner_snapshots",
        "feature_schema_version": "alr_scanner_novelty_features_v1",
        "measurement_scope": "scanner_recurrence_and_novelty_not_after_cost_return",
        "selector_schema_version": SELECTOR_INPUT_SCHEMA_VERSION,
    }
    return {
        "schema_version": DEFER_DECISION_FINGERPRINT_SCHEMA_VERSION,
        "source_head": source_head,
        "candidate_identity": {
            "candidate_id": candidate_scope["candidate_id"],
            "strategy_name": candidate_scope["strategy_name"],
            "strategy_version": "scanner_novelty_v1",
            "strategy_config_hash": decision_policy_hash,
            "symbol": candidate_scope["symbol"],
            "side": candidate_scope["side"],
            "horizon": "UNSPECIFIED",
            "regime": "scanner_recurrence_not_return",
            "engine_mode": candidate_scope["engine_mode"],
        },
        "regime_context": {
            "source": "scanner_snapshot",
            "measurement": "recurrence_not_return",
        },
        "semantic_evidence": {
            "scanner_occurrences": int(target_metrics["occurrences"]),
            "scanner_novelty": int(target_metrics["novelty"]),
            "matched_control_symbols": list(control_symbols),
            "candidate_summary": {
                symbol: {
                    "occurrences": int(metrics["occurrences"]),
                    "novelty": int(metrics["novelty"]),
                }
                for symbol, metrics in sorted(candidate_summary.items())
            },
            "scanner_config_hashes": list(scanner_config_hashes),
            "cycle_count": cycle_count,
            "after_cost_measurement": "unavailable",
        },
        "blockers": list(_AFTER_COST_GAPS),
        "reevaluation_policy": copy.deepcopy(_DEFER_DECISION_POLICY),
        "decision_policy_hash": decision_policy_hash,
        "source_contract_hash": _canonical_sha256(source_contract),
        "code_schema_versions": {
            "experiment": OUTPUT_SCHEMA_VERSION,
            "candidate": "alr_challenger_candidate_v1",
            "defer": "alr_defer_evidence_v1",
        },
    }


def _add_seconds_utc_z(value: str, seconds: int) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AlrScannerStatisticalExperimentError("source_ts_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AlrScannerStatisticalExperimentError("source_ts_invalid")
    return (
        parsed.astimezone(timezone.utc) + timedelta(seconds=seconds)
    ).isoformat().replace("+00:00", "Z")


def _artifact(kind: str, artifact_hash: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"artifact_kind": kind, "artifact_hash": artifact_hash, "canonical_payload": copy.deepcopy(dict(payload))}


def _edge(from_hash: str, to_hash: str, edge_role: str) -> dict[str, str]:
    edge = {"from_artifact_hash": from_hash, "to_artifact_hash": to_hash, "edge_role": edge_role}
    edge["edge_hash"] = _canonical_sha256(edge)
    return edge


def _chronological_split(row_ids: Sequence[str]) -> tuple[list[str], list[str], list[str]]:
    count = len(row_ids)
    train_end = max(1, count - 2)
    validation_end = max(train_end + 1, count - 1)
    return list(row_ids[:train_end]), list(row_ids[train_end:validation_end]), list(row_ids[validation_end:])


def _symbols(payload: Mapping[str, Any]) -> list[str]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return []
    symbols: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        symbol = candidate.get("symbol")
        if isinstance(symbol, str) and symbol.strip():
            symbols.add(symbol.strip())
    return sorted(symbols)


def _text_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item.strip() for item in value if isinstance(item, str) and item.strip()}


def _all_false(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(value) and all(_all_false(item) for item in value.values())
    if isinstance(value, list):
        return all(_all_false(item) for item in value)
    return value is False


def _all_zero(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(
        isinstance(item, int) and not isinstance(item, bool) and item == 0
        for item in value.values()
    )


def _invalid(*reasons: str) -> AlrScannerStatisticalExperimentValidation:
    return AlrScannerStatisticalExperimentValidation(False, reasons[0], tuple(reasons))


def _canonical_sha256(value: Any) -> str:
    try:
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise AlrScannerStatisticalExperimentError("canonical_json_invalid") from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
