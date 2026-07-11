"""Typed nested-payload lineage for the profit-diagnosis controller."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


EVIDENCE_PAYLOAD_FIELDS = {
    "schema_version", "axis", "work_status", "summary", "facts", "gaps",
    "consumption",
}
PROBE_PAYLOAD_FIELDS = {
    "schema_version", "axis", "work_status", "verdict", "diagnoses",
    "opportunities", "evidence_refs", "negative_search_summary",
    "next_experiments", "consumption",
}
MAP_PAYLOAD_FIELDS = {
    "schema_version", "work_status", "decision_ready", "top_moves",
    "negative_results", "coverage_debt", "consumption",
}
FACT_FIELDS = {
    "id", "classification", "scope", "evidence_ref", "observation",
    "observed_at", "freshness", "limitation",
}
DIAGNOSIS_FIELDS = {
    "id", "area", "title", "classification", "evidence_refs", "blocker",
    "net_profit_impact", "confidence",
}
OPPORTUNITY_FIELDS = {
    "id", "title", "mode", "hypothesis", "why_now", "evidence_refs",
    "estimated_net_edge", "estimated_cost", "wall_break_probability",
    "falsification", "classification", "confidence",
}
TOP_MOVE_FIELDS = {
    "rank", "title", "mode", "roi_rationale", "wall_break_probability",
    "evidence_level", "falsification", "next_step", "owner",
    "source_opportunity_ids", "evidence_refs",
}
NEGATIVE_RESULT_FIELDS = {
    "axis", "searched", "result", "next_review_condition", "evidence_refs",
}


def ordered_unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _text(value: Any, minimum: int = 1) -> bool:
    return isinstance(value, str) and len(value.strip()) >= minimum


def _string_list(value: Any, *, minimum: int = 1) -> bool:
    return bool(
        isinstance(value, list)
        and value
        and all(_text(item, minimum) for item in value)
        and len(value) == len(set(value))
    )


def _timezone_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not re.search(r"(?:Z|[+-]\d\d:\d\d)$", value):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def valid_fact(item: Any, time_parser) -> bool:
    return bool(
        isinstance(item, dict)
        and set(item) == FACT_FIELDS
        and _text(item.get("id"))
        and item.get("classification") in {"FACT", "INFERENCE", "ASSUMPTION"}
        and item.get("scope") in {"source", "runtime", "data", "external"}
        and (
            item.get("evidence_ref") is None
            or _text(item.get("evidence_ref"))
        )
        and (
            item.get("classification") != "FACT"
            or _text(item.get("evidence_ref"))
        )
        and _text(item.get("observation"))
        and time_parser(item.get("observed_at")) is not None
        and item.get("freshness")
        in {"fresh", "recent", "stale", "expired", "not_applicable"}
        and isinstance(item.get("limitation"), str)
    )


def valid_evidence_payload(payload: Any, axis: str, time_parser) -> bool:
    if not (
        isinstance(payload, dict)
        and set(payload) == EVIDENCE_PAYLOAD_FIELDS
        and payload.get("schema_version") == "profit_evidence_fragment_v2"
        and payload.get("axis") == axis
        and payload.get("work_status")
        in {"DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED"}
        and _text(payload.get("summary"))
        and isinstance(payload.get("facts"), list)
        and payload["facts"]
        and isinstance(payload.get("gaps"), list)
        and all(_text(item) for item in payload["gaps"])
        and isinstance(payload.get("consumption"), dict)
    ):
        return False
    facts = payload["facts"]
    return bool(
        all(valid_fact(item, time_parser) for item in facts)
        and len({item["id"] for item in facts}) == len(facts)
    )


def _valid_diagnosis(item: Any) -> bool:
    return bool(
        isinstance(item, dict)
        and DIAGNOSIS_FIELDS.issubset(item)
        and set(item).issubset(DIAGNOSIS_FIELDS | {"regime_caveat"})
        and all(
            _text(item.get(field))
            for field in ("id", "title", "blocker", "net_profit_impact")
        )
        and item.get("area") in {"leak", "frozen", "unrealized"}
        and item.get("classification") in {"FACT", "INFERENCE", "ASSUMPTION"}
        and item.get("confidence") in {"high", "med", "low"}
        and _string_list(item.get("evidence_refs"))
        and (
            "regime_caveat" not in item
            or isinstance(item.get("regime_caveat"), str)
        )
    )


def _valid_opportunity(item: Any, axis: str) -> bool:
    allowed = OPPORTUNITY_FIELDS | {"regime_caveat"}
    required = set(OPPORTUNITY_FIELDS)
    if axis == "EXT":
        required |= {"sources", "local_constraint_fit"}
        allowed |= {"sources", "local_constraint_fit"}
    if not (
        isinstance(item, dict)
        and required.issubset(item)
        and set(item).issubset(allowed)
        and all(_text(item.get(field)) for field in ("id", "title"))
        and item.get("mode") in {"defend", "attack", "unlock", "learn"}
        and _text(item.get("hypothesis"), 20)
        and _text(item.get("why_now"), 10)
        and _string_list(item.get("evidence_refs"))
        and _text(item.get("estimated_net_edge"), 8)
        and isinstance(item.get("estimated_cost"), str)
        and item.get("wall_break_probability") in {"high", "med", "low", "unknown"}
        and _text(item.get("falsification"), 20)
        and item.get("classification") in {"FACT", "INFERENCE", "ASSUMPTION"}
        and item.get("confidence") in {"high", "med", "low"}
        and (
            "regime_caveat" not in item
            or isinstance(item.get("regime_caveat"), str)
        )
    ):
        return False
    if axis != "EXT":
        return True
    sources = item.get("sources")
    return bool(
        isinstance(sources, list)
        and sources
        and all(
            isinstance(source, dict)
            and set(source) == {
                "url", "claim_excerpt", "opened_at", "content_digest",
                "citation_ref", "capture_ref",
            }
            and isinstance(source.get("url"), str)
            and source["url"].startswith("https://")
            and _text(source.get("claim_excerpt"), 8)
            and _timezone_timestamp(source.get("opened_at"))
            and isinstance(source.get("content_digest"), str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", source["content_digest"])
            and _text(source.get("citation_ref"))
            and _text(source.get("capture_ref"))
            for source in sources
        )
        and _text(item.get("local_constraint_fit"), 20)
    )


def valid_probe_payload(payload: Any, axis: str) -> bool:
    if not (
        isinstance(payload, dict)
        and set(payload) == PROBE_PAYLOAD_FIELDS
        and payload.get("schema_version") == "profit_probe_fragment_v2"
        and payload.get("axis") == axis
        and payload.get("work_status")
        in {"DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED"}
        and payload.get("verdict") in {"FINDINGS", "NO_EVIDENCE", "BLOCKED"}
        and isinstance(payload.get("diagnoses"), list)
        and isinstance(payload.get("opportunities"), list)
        and _string_list(payload.get("evidence_refs"))
        and _text(payload.get("negative_search_summary"), 20)
        and _string_list(payload.get("next_experiments"), minimum=15)
        and isinstance(payload.get("consumption"), dict)
        and all(_valid_diagnosis(item) for item in payload["diagnoses"])
        and all(_valid_opportunity(item, axis) for item in payload["opportunities"])
    ):
        return False
    has_findings = bool(payload["diagnoses"] or payload["opportunities"])
    return (payload["verdict"] == "FINDINGS") is has_findings


def validate_probe_lineage(
    payload: Any,
    axis: str,
    *,
    evidence_ids: set[str],
    seen_content_ids: set[str],
    opportunities_by_id: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    node = f"probe:{axis}"
    if not valid_probe_payload(payload, axis):
        return [f"profit diagnosis probe fragment {node} payload is invalid"], []
    errors: list[str] = []
    refs = payload["evidence_refs"]
    if any(ref not in evidence_ids for ref in refs):
        errors.append(f"profit diagnosis probe fragment {node} references missing evidence")
    nested = payload["diagnoses"] + payload["opportunities"]
    nested_refs = ordered_unique(
        [ref for item in nested for ref in item["evidence_refs"]]
    )
    if nested and refs != nested_refs:
        errors.append(
            f"profit diagnosis probe fragment {node} evidence_refs differ from nested content"
        )
    for item in nested:
        item_id = item["id"]
        if item_id in seen_content_ids:
            errors.append("profit diagnosis nested content ids must be globally unique")
        seen_content_ids.add(item_id)
    for item in payload["opportunities"]:
        opportunities_by_id[item["id"]] = item
    return errors, refs


def _valid_negative_result(item: Any) -> bool:
    return bool(
        isinstance(item, dict)
        and set(item) == NEGATIVE_RESULT_FIELDS
        and all(
            _text(item.get(field))
            for field in ("axis", "searched", "result", "next_review_condition")
        )
        and _string_list(item.get("evidence_refs"))
    )


def _valid_top_move(item: Any) -> bool:
    return bool(
        isinstance(item, dict)
        and TOP_MOVE_FIELDS.issubset(item)
        and set(item).issubset(TOP_MOVE_FIELDS | {"regime_caveat"})
        and isinstance(item.get("rank"), int)
        and not isinstance(item.get("rank"), bool)
        and item["rank"] >= 1
        and all(_text(item.get(field)) for field in ("title", "falsification", "owner"))
        and item.get("mode") in {"defend", "attack", "unlock", "learn"}
        and _text(item.get("roi_rationale"), 15)
        and item.get("wall_break_probability") in {"high", "med", "low", "unknown"}
        and item.get("evidence_level") in {"FACT", "INFERENCE", "ASSUMPTION"}
        and _text(item.get("next_step"), 10)
        and _string_list(item.get("source_opportunity_ids"))
        and _string_list(item.get("evidence_refs"))
        and (
            "regime_caveat" not in item
            or isinstance(item.get("regime_caveat"), str)
        )
    )


def validate_map_lineage(
    payload: Any,
    *,
    probe_payloads: dict[str, dict[str, Any]],
    opportunities_by_id: dict[str, dict[str, Any]],
    evidence_ids: set[str],
) -> tuple[list[str], list[str], bool]:
    outer_valid = bool(
        isinstance(payload, dict)
        and set(payload) == MAP_PAYLOAD_FIELDS
        and payload.get("schema_version") == "profit_map_v2"
        and payload.get("work_status")
        in {"DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED"}
        and isinstance(payload.get("decision_ready"), bool)
        and isinstance(payload.get("top_moves"), list)
        and isinstance(payload.get("negative_results"), list)
        and isinstance(payload.get("coverage_debt"), list)
        and all(_text(item) for item in payload.get("coverage_debt", []))
        and isinstance(payload.get("consumption"), dict)
    )
    if not outer_valid:
        return ["profit diagnosis map fragment payload is invalid"], [], False
    errors: list[str] = []
    moves = payload["top_moves"]
    if not all(_valid_top_move(item) for item in moves):
        errors.append("profit diagnosis map top move source lineage is invalid")
    elif [item["rank"] for item in moves] != list(range(1, len(moves) + 1)):
        errors.append("profit diagnosis map top move ranks are not contiguous")
    for move in moves:
        if not _valid_top_move(move):
            continue
        source_items = [
            opportunities_by_id.get(item_id)
            for item_id in move["source_opportunity_ids"]
        ]
        if any(item is None for item in source_items):
            errors.append("profit diagnosis map top move source lineage is invalid")
            continue
        expected_refs = ordered_unique(
            [ref for item in source_items if item for ref in item["evidence_refs"]]
        )
        if move["evidence_refs"] != expected_refs:
            errors.append("profit diagnosis map top move evidence lineage is invalid")
        if any(ref not in evidence_ids for ref in move["evidence_refs"]):
            errors.append("profit diagnosis map top move references missing evidence")
    negatives = payload["negative_results"]
    if not all(_valid_negative_result(item) for item in negatives):
        errors.append("profit diagnosis map negative result payload is invalid")
    expected_negatives = [
        {
            "axis": axis,
            "searched": probe.get("negative_search_summary"),
            "result": "NO_EVIDENCE under current baseline and priors",
            "next_review_condition": " | ".join(probe.get("next_experiments", [])),
            "evidence_refs": probe.get("evidence_refs"),
        }
        for axis, probe in probe_payloads.items()
        if probe.get("verdict") == "NO_EVIDENCE"
    ]
    if negatives != expected_negatives:
        errors.append("profit diagnosis map negative results differ from probe projections")
    map_refs = ordered_unique(
        [
            ref
            for item in moves + negatives
            if isinstance(item, dict)
            for ref in item.get("evidence_refs", [])
        ]
    )
    return errors, map_refs, True
