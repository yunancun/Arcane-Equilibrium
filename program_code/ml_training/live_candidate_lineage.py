"""Live candidate lineage adapter.

This module keeps the producer/consumer contract for demo-to-live promotion
lineage in one small place. It deliberately stores lineage in the existing
candidate payload rather than introducing the ADR-0021 first-class Hypothesis
Pipeline tables ahead of that wave.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional


LINEAGE_PAYLOAD_KEY = "lineage"
LIVE_CANDIDATE_LINEAGE_SCHEMA_VERSION = "live_candidate_lineage_v1"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_text(*values: Any) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _nested(mapping: Mapping[str, Any], *keys: str) -> Optional[Any]:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _patch_keys(patch: Any) -> list[str]:
    if not isinstance(patch, Mapping):
        return []
    return sorted(str(key) for key in patch.keys())


def build_live_candidate_lineage_payload(
    *,
    source_row: Mapping[str, Any],
    application_id: int,
    application_type: str,
    patch: Mapping[str, Any],
    strategy_name: Optional[str],
    source_payload: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Build the stable lineage shape embedded in a live candidate payload."""
    source_payload = _mapping(source_payload)
    existing_lineage = _mapping(source_payload.get(LINEAGE_PAYLOAD_KEY))

    hypothesis_id = _first_text(
        source_payload.get("originating_hypothesis_id"),
        source_payload.get("hypothesis_id"),
        source_payload.get("related_hypothesis_id"),
        _nested(source_payload, "hypothesis", "hypothesis_id"),
        existing_lineage.get("originating_hypothesis_id"),
        existing_lineage.get("hypothesis_id"),
    )
    experiment_id = _first_text(
        source_payload.get("originating_experiment_id"),
        source_payload.get("experiment_id"),
        source_payload.get("related_experiment_id"),
        _nested(source_payload, "experiment", "experiment_id"),
        existing_lineage.get("originating_experiment_id"),
        existing_lineage.get("experiment_id"),
    )
    replay_experiment_id = _first_text(
        source_row.get("replay_experiment_id"),
        source_payload.get("replay_experiment_id"),
        existing_lineage.get("replay_experiment_id"),
    )
    manifest_hash = _first_text(
        source_row.get("manifest_hash"),
        source_payload.get("manifest_hash"),
        existing_lineage.get("manifest_hash"),
    )
    alpha_source_id = _first_text(
        source_payload.get("alpha_source_id"),
        source_payload.get("alpha_source"),
        existing_lineage.get("alpha_source_id"),
        source_row.get("source"),
    )

    return {
        "schema_version": LIVE_CANDIDATE_LINEAGE_SCHEMA_VERSION,
        "lineage_source": "producer_payload",
        "originating_hypothesis_id": hypothesis_id,
        "originating_experiment_id": experiment_id,
        "replay_experiment_id": replay_experiment_id,
        "manifest_hash": manifest_hash,
        "alpha_source_id": alpha_source_id,
        "source_demo_recommendation_id": source_row.get("id"),
        "source_demo_application_id": application_id,
        "source_recommendation_type": source_row.get("recommendation_type"),
        "source_system": source_row.get("source"),
        "strategy_name": _first_text(strategy_name, source_row.get("strategy_name")),
        "symbol": _first_text(source_row.get("symbol")),
        "context_id": _first_text(source_row.get("context_id"), source_payload.get("context_id")),
        "intent_id": _first_text(source_row.get("intent_id"), source_payload.get("intent_id")),
        "application_type": application_type,
        "promotion_stage": "demo_to_live_candidate",
        "patch_keys": _patch_keys(patch),
    }


def extract_live_candidate_lineage_payload(
    payload: Mapping[str, Any],
    *,
    candidate_row: Optional[Mapping[str, Any]] = None,
    source_recommendation: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Return a normalized lineage snapshot for audit payloads."""
    candidate_row = _mapping(candidate_row)
    source_recommendation = _mapping(source_recommendation)
    lineage_raw = payload.get(LINEAGE_PAYLOAD_KEY)
    has_payload_lineage = isinstance(lineage_raw, Mapping)
    lineage = _mapping(lineage_raw)

    return {
        "schema_version": _first_text(
            lineage.get("schema_version"),
            LIVE_CANDIDATE_LINEAGE_SCHEMA_VERSION,
        ),
        "lineage_source": "payload" if has_payload_lineage else "derived_from_candidate",
        "originating_hypothesis_id": _first_text(
            lineage.get("originating_hypothesis_id"),
            lineage.get("hypothesis_id"),
        ),
        "originating_experiment_id": _first_text(
            lineage.get("originating_experiment_id"),
            lineage.get("experiment_id"),
        ),
        "replay_experiment_id": _first_text(lineage.get("replay_experiment_id")),
        "manifest_hash": _first_text(lineage.get("manifest_hash")),
        "alpha_source_id": _first_text(lineage.get("alpha_source_id")),
        "source_demo_recommendation_id": lineage.get(
            "source_demo_recommendation_id",
            candidate_row.get("recommendation_id"),
        ),
        "source_demo_application_id": lineage.get("source_demo_application_id"),
        "source_recommendation_type": _first_text(
            lineage.get("source_recommendation_type"),
            source_recommendation.get("recommendation_type"),
        ),
        "source_system": _first_text(
            lineage.get("source_system"),
            source_recommendation.get("source"),
        ),
        "strategy_name": _first_text(
            lineage.get("strategy_name"),
            candidate_row.get("target_name"),
            source_recommendation.get("strategy_name"),
        ),
        "symbol": _first_text(lineage.get("symbol"), source_recommendation.get("symbol")),
        "context_id": _first_text(
            lineage.get("context_id"),
            source_recommendation.get("context_id"),
        ),
        "intent_id": _first_text(
            lineage.get("intent_id"),
            source_recommendation.get("intent_id"),
        ),
        "application_type": _first_text(
            lineage.get("application_type"),
            candidate_row.get("application_type"),
        ),
        "promotion_stage": _first_text(
            lineage.get("promotion_stage"),
            "demo_to_live_candidate",
        ),
        "patch_keys": list(lineage.get("patch_keys") or []),
    }
