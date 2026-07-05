#!/usr/bin/env python3
"""Score false-negative candidates by edge and bounded-probe friction.

This artifact is an aggressive-alpha research aid. It ranks false-negative
Cost Gate candidates by after-cost cushion, sample strength, and any available
bounded Demo touchability / placement / authorization friction evidence. It is
read-only and artifact-only: it never lowers the Cost Gate, grants authority,
mutates runtime state, writes PG, calls Bybit, or submits orders.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.bounded_probe_operator_authorization import (
    OPERATOR_AUTHORIZATION_PACKET_SCHEMA_VERSION,
)
from cost_gate_learning_lane.bounded_probe_placement_repair_plan import (
    PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION,
)
from cost_gate_learning_lane.bounded_probe_touchability_preflight import (
    TOUCHABILITY_PREFLIGHT_SCHEMA_VERSION,
)
from cost_gate_learning_lane.false_negative_candidate_packet import (
    SCHEMA_VERSION as FALSE_NEGATIVE_PACKET_SCHEMA_VERSION,
)

# 共用純函數葉節點：以 alias-import 保持函數體內 _dict/_list/_str/_utc_now 引用逐字節不變。
from cost_gate_learning_lane._lane_common import (
    as_dict as _dict,
    as_list as _list,
    as_str as _str,
    utc_now as _utc_now,
)


SCHEMA_VERSION = "cost_gate_false_negative_candidate_friction_scorecard_v1"
READY_STATUS = "FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY"
NO_CANDIDATES_STATUS = "NO_FALSE_NEGATIVE_CANDIDATES_FOR_FRICTION_SCORECARD"
INPUT_NOT_READY_STATUS = "FALSE_NEGATIVE_CANDIDATE_PACKET_NOT_READY"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"
BOUNDARY = (
    "artifact-only false-negative candidate friction scorecard; no PG "
    "query/write, Bybit call, order, config, risk, auth, runtime mutation, "
    "main Cost Gate lowering, probe authority, order authority, live authority, "
    "or promotion proof"
)
EXPECTED_ARTIFACT_SCHEMAS = {
    "false_negative_candidate_packet": FALSE_NEGATIVE_PACKET_SCHEMA_VERSION,
    "touchability_preflight": TOUCHABILITY_PREFLIGHT_SCHEMA_VERSION,
    "placement_repair_plan": PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION,
    "operator_authorization": OPERATOR_AUTHORIZATION_PACKET_SCHEMA_VERSION,
}
CANDIDATE_IDENTITY_KEYS = (
    "side_cell_key",
    "strategy_name",
    "symbol",
    "side",
    "outcome_horizon_minutes",
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "bounded_demo_probe_authorized",
    "auth_mutation_performed",
    "bybit_call_performed",
    "bybit_order_call_performed",
    "config_mutation_performed",
    "crontab_edit_performed",
    "db_query_performed",
    "db_schema_migration_performed",
    "db_write_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "global_cost_gate_lowering_recommended",
    "live_authority_granted",
    "live_promotion_performed",
    "live_promotion_recommended",
    "operator_authorization_object_emitted",
    "order_cancel_performed",
    "order_authority_granted",
    "order_authority_granted_in_authorization_object",
    "order_modify_performed",
    "order_submission_performed",
    "pg_query_performed",
    "pg_schema_migration_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "probe_authority_granted",
    "probe_authority_granted_in_authorization_object",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutation_performed",
    "rust_writer_enabled",
    "runtime_mutation_performed",
    "schema_migration_performed",
    "service_restart_performed",
    "strategy_mutation_performed",
    "writer_enabled",
}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _round(value: Any, ndigits: int = 4) -> float | None:
    parsed = _float(value)
    return round(parsed, ndigits) if parsed is not None else None


def _generated_at(payload: dict[str, Any]) -> Any:
    return payload.get("generated_at_utc") or payload.get("generated") or payload.get("ts_utc")


def _parse_dt(value: Any) -> dt.datetime | None:
    text = _str(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _age_seconds(value: Any, *, now_utc: dt.datetime) -> float | None:
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    age = (now_utc - parsed).total_seconds()
    return age if age >= 0.0 else None


def _artifact_summary(
    *,
    name: str,
    path: Path | None,
    payload: dict[str, Any] | None,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    present = bool(_dict(payload))
    generated_at = _generated_at(_dict(payload)) if present else None
    age = _age_seconds(generated_at, now_utc=now_utc) if generated_at else None
    if not present:
        status = "MISSING"
    elif age is None:
        status = "PRESENT_UNKNOWN_AGE"
    elif age > max_age_seconds:
        status = "STALE"
    else:
        status = "FRESH"
    return {
        "name": name,
        "path": str(path) if path else None,
        "present": present,
        "status": status,
        "generated_at_utc": generated_at,
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
        "schema_version": _dict(payload).get("schema_version") if present else None,
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
            "enabled",
            "grant",
            "granted",
            "authorize",
            "authorized",
        }
    return False


def _authority_preserved(*payloads: dict[str, Any] | None) -> bool:
    stack: list[Any] = list(payloads)
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
            continue
        data = _dict(item)
        if not data:
            continue
        if data.get("main_cost_gate_adjustment") not in (None, "", "NONE"):
            return False
        for key in AUTHORITY_TRUE_KEYS:
            if _truthy(data.get(key)):
                return False
        stack.extend(value for value in data.values() if isinstance(value, (dict, list)))
    return True


def _candidate_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "side_cell_key": row.get("side_cell_key"),
        "strategy_name": (_list(row.get("strategy_names")) or [None])[0],
        "symbol": (_list(row.get("symbols")) or [None])[0],
        "side": (_list(row.get("sides")) or [None])[0],
        "outcome_horizon_minutes": row.get("dominant_horizon_minutes")
        or (_list(row.get("horizon_minutes")) or [None])[0],
    }


def _candidate_from_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    return {key: mapping.get(key) for key in CANDIDATE_IDENTITY_KEYS}


def _candidate_from_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    candidates, _ = _candidate_identity_sources_from_payload(payload)
    return candidates[0] if candidates else {}


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    return (
        candidate.get("side_cell_key"),
        candidate.get("strategy_name"),
        candidate.get("symbol"),
        candidate.get("side"),
        candidate.get("outcome_horizon_minutes"),
    )


def _same_candidate(left: dict[str, Any], right: dict[str, Any]) -> bool:
    key = _candidate_key(left)
    return bool(key[0]) and key == _candidate_key(right)


def _candidate_like(source: dict[str, Any]) -> bool:
    return any(source.get(key) not in (None, "") for key in CANDIDATE_IDENTITY_KEYS)


def _candidate_identity_sources_from_payload(
    payload: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], bool]:
    data = _dict(payload)
    raw_sources = [
        _dict(data.get("candidate")),
        _dict(data.get("bounded_probe_design")),
        _dict(_dict(data.get("bounded_probe_design")).get("candidate")),
        _dict(_dict(data.get("placement_repair_plan")).get("candidate")),
        _dict(_dict(data.get("operator_authorization")).get("candidate")),
    ]
    candidates: list[dict[str, Any]] = []
    incomplete_candidate_like_source = False
    for raw in raw_sources:
        if not _candidate_like(raw):
            continue
        candidate = _candidate_from_mapping(raw)
        if not _candidate_is_complete(candidate):
            incomplete_candidate_like_source = True
            continue
        candidates.append(candidate)
    return candidates, incomplete_candidate_like_source


def _artifact_candidate_identity(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    candidates, incomplete = _candidate_identity_sources_from_payload(payload)
    if incomplete or not candidates:
        return None
    first = candidates[0]
    if not all(_same_candidate(first, candidate) for candidate in candidates[1:]):
        return None
    return first


def _packet_ready(packet: dict[str, Any], artifact: dict[str, Any]) -> bool:
    return (
        artifact.get("status") == "FRESH"
        and artifact.get("schema_version")
        == EXPECTED_ARTIFACT_SCHEMAS["false_negative_candidate_packet"]
        and packet.get("status") == "COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW"
    )


def _friction_artifacts_ready(artifacts: dict[str, dict[str, Any]]) -> bool:
    for name in ("touchability_preflight", "placement_repair_plan", "operator_authorization"):
        artifact = artifacts[name]
        if artifact.get("status") != "FRESH":
            return False
        if artifact.get("schema_version") != EXPECTED_ARTIFACT_SCHEMAS[name]:
            return False
    return True


def _candidate_is_complete(candidate: dict[str, Any]) -> bool:
    return all(
        candidate.get(key) not in (None, "")
        for key in (
            "side_cell_key",
            "strategy_name",
            "symbol",
            "side",
            "outcome_horizon_minutes",
        )
    )


def _artifact_candidates_aligned(
    *,
    packet_rows: list[dict[str, Any]],
    touchability_preflight: dict[str, Any] | None,
    placement_repair_plan: dict[str, Any] | None,
    operator_authorization: dict[str, Any] | None,
) -> bool:
    artifact_candidates = [
        _artifact_candidate_identity(touchability_preflight),
        _artifact_candidate_identity(placement_repair_plan),
        _artifact_candidate_identity(operator_authorization),
    ]
    if any(candidate is None for candidate in artifact_candidates):
        return False
    complete_candidates = [candidate for candidate in artifact_candidates if candidate is not None]
    first = complete_candidates[0]
    if not all(_same_candidate(first, candidate) for candidate in complete_candidates[1:]):
        return False
    packet_candidates = [_candidate_from_row(row) for row in packet_rows]
    return any(_same_candidate(first, candidate) for candidate in packet_candidates)


def _touchability_features(
    candidate: dict[str, Any],
    touchability_preflight: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = _dict(touchability_preflight)
    active_candidate = _candidate_from_payload(payload)
    matched = _same_candidate(candidate, active_candidate)
    answers = _dict(payload.get("answers"))
    touch = _dict(payload.get("order_touchability"))
    if not matched:
        return {
            "touchability_evidence_scope": "UNMEASURED_CANDIDATE",
            "touchability_status": None,
            "candidate_matched_fill_rows": None,
            "candidate_reviewed_orders": None,
            "non_candidate_fill_rows": None,
            "touchability_penalty": 25.0,
        }
    penalty = 0.0
    if answers.get("candidate_matched_fill_flow_present") is not True:
        penalty += 10.0
    if answers.get("touchability_repair_required") is True:
        penalty += 12.0
    if touch.get("bbo_touched_without_fill") is True:
        penalty += 4.0
    if _int(touch.get("candidate_reviewed_orders")) <= 0:
        penalty += 6.0
    return {
        "touchability_evidence_scope": "MEASURED_ACTIVE_CANDIDATE",
        "touchability_status": payload.get("status"),
        "candidate_matched_fill_rows": _int(touch.get("candidate_fill_rows")),
        "candidate_reviewed_orders": _int(touch.get("candidate_reviewed_orders")),
        "non_candidate_fill_rows": _int(touch.get("non_candidate_fill_rows")),
        "touchability_penalty": round(penalty, 4),
    }


def _placement_features(
    candidate: dict[str, Any],
    placement_repair_plan: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = _dict(placement_repair_plan)
    active_candidate = _candidate_from_payload(payload)
    matched = _same_candidate(candidate, active_candidate)
    plan = _dict(payload.get("placement_repair_plan"))
    if not matched:
        return {
            "placement_evidence_scope": "UNMEASURED_CANDIDATE",
            "placement_status": None,
            "order_mode": None,
            "placement_penalty": 10.0,
        }
    ready = payload.get("status") == "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW"
    near_touch = plan.get("order_mode") == "post_only_near_touch_or_skip"
    penalty = 2.0 if ready and near_touch else 12.0
    return {
        "placement_evidence_scope": "MEASURED_ACTIVE_CANDIDATE",
        "placement_status": payload.get("status"),
        "order_mode": plan.get("order_mode"),
        "placement_penalty": round(penalty, 4),
    }


def _authorization_features(
    candidate: dict[str, Any],
    operator_authorization: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = _dict(operator_authorization)
    active_candidate = _candidate_from_payload(payload)
    matched = _same_candidate(candidate, active_candidate)
    answers = _dict(payload.get("answers"))
    if not matched:
        return {
            "authorization_evidence_scope": "UNMEASURED_CANDIDATE",
            "authorization_status": None,
            "authorization_decision": None,
            "authorization_penalty": 10.0,
            "operator_authorization_object_emitted": None,
        }
    status = _str(payload.get("status"))
    if status == "READY_FOR_OPERATOR_AUTHORIZATION_REVIEW":
        penalty = 8.0
    elif status == "TYPED_CONFIRM_REQUIRED":
        penalty = 16.0
    else:
        penalty = 14.0
    return {
        "authorization_evidence_scope": "MEASURED_ACTIVE_CANDIDATE",
        "authorization_status": status,
        "authorization_decision": payload.get("decision"),
        "authorization_penalty": round(penalty, 4),
        "operator_authorization_object_emitted": (
            answers.get("operator_authorization_object_emitted") is True
        ),
    }


def _candidate_score(row: dict[str, Any], friction: dict[str, Any]) -> float:
    wrongful = _float(row.get("wrongful_block_score")) or 0.0
    cushion = _float(row.get("net_cost_cushion_bps")) or 0.0
    positive_pct = (_float(row.get("net_positive_pct")) or 0.0) / 100.0
    sample = math.log10(max(1, _int(row.get("outcome_count"))) + 1.0) * 8.0
    friction_penalty = (
        (_float(friction.get("touchability_penalty")) or 0.0)
        + (_float(friction.get("placement_penalty")) or 0.0)
        + (_float(friction.get("authorization_penalty")) or 0.0)
    )
    return round(wrongful + cushion * positive_pct + sample - friction_penalty, 4)


def _row_to_scorecard_candidate(
    row: dict[str, Any],
    *,
    touchability_preflight: dict[str, Any] | None,
    placement_repair_plan: dict[str, Any] | None,
    operator_authorization: dict[str, Any] | None,
) -> dict[str, Any]:
    candidate = _candidate_from_row(row)
    touchability = _touchability_features(candidate, touchability_preflight)
    placement = _placement_features(candidate, placement_repair_plan)
    authorization = _authorization_features(candidate, operator_authorization)
    friction = {**touchability, **placement, **authorization}
    score = _candidate_score(row, friction)
    measured = any(
        friction.get(key) == "MEASURED_ACTIVE_CANDIDATE"
        for key in (
            "touchability_evidence_scope",
            "placement_evidence_scope",
            "authorization_evidence_scope",
        )
    )
    if authorization.get("authorization_status") == "TYPED_CONFIRM_REQUIRED":
        next_action = "exact_bounded_demo_typed_confirm_required_or_select_next_candidate"
    elif measured:
        next_action = "operator_review_measured_candidate_friction_before_probe"
    else:
        next_action = "collect_touchability_and_authorization_friction_evidence_before_probe"
    return {
        "side_cell_key": row.get("side_cell_key"),
        "candidate": candidate,
        "false_negative_rank": row.get("false_negative_rank"),
        "source_status": row.get("status"),
        "outcome_count": _int(row.get("outcome_count")),
        "avg_net_bps": _round(row.get("avg_net_bps")),
        "net_cost_cushion_bps": _round(row.get("net_cost_cushion_bps")),
        "net_positive_pct": _round(row.get("net_positive_pct")),
        "wrongful_block_score": _round(row.get("wrongful_block_score")),
        "friction_adjusted_priority_score": score,
        "friction": friction,
        "next_action": next_action,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
    }


def _rank_candidates(candidates: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    ranked = sorted(
        candidates,
        key=lambda row: (
            -(_float(row.get("friction_adjusted_priority_score")) or 0.0),
            _int(row.get("false_negative_rank"), 999999),
            _str(row.get("side_cell_key")),
        ),
    )[:limit]
    out: list[dict[str, Any]] = []
    for index, row in enumerate(ranked, start=1):
        item = dict(row)
        item["friction_rank"] = index
        out.append(item)
    return out


def build_false_negative_candidate_friction_scorecard(
    *,
    false_negative_candidate_packet: dict[str, Any] | None,
    touchability_preflight: dict[str, Any] | None = None,
    placement_repair_plan: dict[str, Any] | None = None,
    operator_authorization: dict[str, Any] | None = None,
    paths: dict[str, Path | None] | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = 24,
    top_limit: int = 16,
) -> dict[str, Any]:
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")
    if top_limit < 1 or top_limit > 100:
        raise ValueError("top_limit must be in [1, 100]")
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    paths = paths or {}
    max_age_seconds = max_artifact_age_hours * 3600
    packet = _dict(false_negative_candidate_packet)
    artifacts = {
        "false_negative_candidate_packet": _artifact_summary(
            name="false_negative_candidate_packet",
            path=paths.get("false_negative_candidate_packet"),
            payload=packet,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "touchability_preflight": _artifact_summary(
            name="touchability_preflight",
            path=paths.get("touchability_preflight"),
            payload=touchability_preflight,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "placement_repair_plan": _artifact_summary(
            name="placement_repair_plan",
            path=paths.get("placement_repair_plan"),
            payload=placement_repair_plan,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "operator_authorization": _artifact_summary(
            name="operator_authorization",
            path=paths.get("operator_authorization"),
            payload=operator_authorization,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
    }
    authority_preserved = _authority_preserved(
        packet,
        touchability_preflight,
        placement_repair_plan,
        operator_authorization,
    )
    packet_ready = _packet_ready(packet, artifacts["false_negative_candidate_packet"])
    friction_artifacts_ready = _friction_artifacts_ready(artifacts)
    rows = [
        row for row in _list(packet.get("ranked_false_negative_candidates"))
        if isinstance(row, dict)
    ]
    artifact_candidates_aligned = _artifact_candidates_aligned(
        packet_rows=rows,
        touchability_preflight=touchability_preflight,
        placement_repair_plan=placement_repair_plan,
        operator_authorization=operator_authorization,
    )
    candidates = [
        _row_to_scorecard_candidate(
            row,
            touchability_preflight=touchability_preflight,
            placement_repair_plan=placement_repair_plan,
            operator_authorization=operator_authorization,
        )
        for row in rows
    ] if (
        packet_ready
        and friction_artifacts_ready
        and artifact_candidates_aligned
        and authority_preserved
    ) else []
    ranked = _rank_candidates(candidates, limit=top_limit)
    if not authority_preserved:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation_in_inputs"
    elif not packet_ready:
        status = INPUT_NOT_READY_STATUS
        reason = "false_negative_candidate_packet_not_fresh_ready_or_schema_valid"
    elif not friction_artifacts_ready:
        status = INPUT_NOT_READY_STATUS
        reason = "friction_artifacts_missing_stale_unknown_age_or_schema_mismatch"
    elif not artifact_candidates_aligned:
        status = INPUT_NOT_READY_STATUS
        reason = "friction_artifact_candidate_identity_mismatch_or_not_in_packet"
    elif not ranked:
        status = NO_CANDIDATES_STATUS
        reason = "no_ranked_false_negative_candidates"
    else:
        status = READY_STATUS
        reason = "ranked_false_negative_candidates_scored_by_friction"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "ranked_candidates": ranked,
        "summary": {
            "candidate_count": len(candidates),
            "ranked_count": len(ranked),
            "friction_artifacts_ready": friction_artifacts_ready,
            "artifact_candidates_aligned": artifact_candidates_aligned,
            "measured_active_candidate_count": sum(
                1 for row in ranked
                if any(
                    _dict(row.get("friction")).get(key) == "MEASURED_ACTIVE_CANDIDATE"
                    for key in (
                        "touchability_evidence_scope",
                        "placement_evidence_scope",
                        "authorization_evidence_scope",
                    )
                )
            ),
            "top_side_cell_key": ranked[0]["side_cell_key"] if ranked else None,
            "top_next_action": ranked[0]["next_action"] if ranked else None,
        },
        "answers": {
            "scorecard_ready": status == READY_STATUS,
            "source_only_research_artifact": True,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "artifacts": artifacts,
        "next_actions": [
            "review_top_friction_adjusted_candidate_before_any_bounded_authorization",
            "collect_candidate_matched_touchability_for_unmeasured_candidates",
            "keep_main_cost_gate_adjustment_none",
        ],
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# False-Negative Candidate Friction Scorecard",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Ranked Candidates",
        "",
        "| rank | side-cell | score | avg net bps | outcomes | next action |",
        "|---:|---|---:|---:|---:|---|",
    ]
    for row in _list(packet.get("ranked_candidates")):
        lines.append(
            f"| {row.get('friction_rank')} | `{row.get('side_cell_key')}` | "
            f"`{row.get('friction_adjusted_priority_score')}` | "
            f"`{row.get('avg_net_bps')}` | `{row.get('outcome_count')}` | "
            f"`{row.get('next_action')}` |"
        )
    lines.extend(["", "## No-Authority Answers", ""])
    for key, value in _dict(packet.get("answers")).items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--false-negative-candidate-packet-json", type=Path, required=True)
    parser.add_argument("--touchability-preflight-json", type=Path)
    parser.add_argument("--placement-repair-plan-json", type=Path)
    parser.add_argument("--operator-authorization-json", type=Path)
    parser.add_argument("--max-artifact-age-hours", type=int, default=24)
    parser.add_argument("--top-limit", type=int, default=16)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_false_negative_candidate_friction_scorecard(
        false_negative_candidate_packet=_read_json(args.false_negative_candidate_packet_json),
        touchability_preflight=_read_json(args.touchability_preflight_json),
        placement_repair_plan=_read_json(args.placement_repair_plan_json),
        operator_authorization=_read_json(args.operator_authorization_json),
        paths={
            "false_negative_candidate_packet": args.false_negative_candidate_packet_json,
            "touchability_preflight": args.touchability_preflight_json,
            "placement_repair_plan": args.placement_repair_plan_json,
            "operator_authorization": args.operator_authorization_json,
        },
        max_artifact_age_hours=args.max_artifact_age_hours,
        top_limit=args.top_limit,
    )
    markdown = render_markdown(packet)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True))
    elif not args.output and not args.json_output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
