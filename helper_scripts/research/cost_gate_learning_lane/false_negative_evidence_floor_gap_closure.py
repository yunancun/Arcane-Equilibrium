#!/usr/bin/env python3
"""Build a no-order evidence-floor gap-closure design from ranking output.

The design turns a review-only false-negative leader into explicit evidence
lanes. It does not collect runtime data, write PG, call Bybit, submit orders,
mutate risk/cap state, lower Cost Gate, or grant authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "cost_gate_false_negative_evidence_floor_gap_closure_design_v1"
READY_STATUS = "EVIDENCE_FLOOR_GAP_CLOSURE_DESIGN_READY_NO_AUTHORITY"
INPUT_NOT_READY_STATUS = "EVIDENCE_FLOOR_RANKING_INPUT_NOT_READY"
NO_LEADER_STATUS = "NO_REVIEW_ONLY_EVIDENCE_FLOOR_LEADER"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"
RANKING_SCHEMA_VERSION = "cost_gate_false_negative_evidence_floor_ranking_v1"
RANKING_READY_STATUS = "FALSE_NEGATIVE_EVIDENCE_FLOOR_RANKING_READY_NO_AUTHORITY"
BOUNDARY = (
    "artifact-only evidence-floor gap-closure design; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, Cost Gate "
    "lowering, cap mutation, probe authority, order authority, live authority, "
    "or promotion proof"
)
AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "bybit_public_market_data_call_performed",
    "cap_envelope_mutation_allowed",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "global_cost_gate_lowering_recommended",
    "live_authority_granted",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "operator_authorization_object_emitted",
    "pg_write_performed",
    "plan_mutation_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutation_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "writer_enabled",
}


GAP_DESIGNS: dict[str, dict[str, Any]] = {
    "candidate_matched_controls_present": {
        "lane": "source_only_then_post_authorized_review",
        "required_data": [
            "same-side-cell blocked-signal controls",
            "candidate-matched probe outcome rows after authorization",
        ],
        "fastest_safe_test": "define source-only control identity and matching keys before any order",
        "authority_required": "none for design; bounded auth required before probe outcomes",
        "failure_condition": "controls cannot be matched to candidate side-cell or controls outperform probe after costs",
        "max_safe_next_action": "write source-only control contract; do not use cross-symbol controls as proof",
    },
    "candidate_matched_fee_slippage_and_maker_taker_labels": {
        "lane": "authorization_required_after_probe",
        "required_data": [
            "candidate-matched fills",
            "fees",
            "slippage",
            "maker/taker labels",
        ],
        "fastest_safe_test": "prepare no-order schema checks; wait for candidate-scoped bounded authorization before fills",
        "authority_required": "candidate-scoped bounded Demo authorization plus PM->E3->BB before order",
        "failure_condition": "missing fill lineage, missing fees, missing slippage, or unknown maker/taker state",
        "max_safe_next_action": "source-only schema contract only",
    },
    "fresh_bbo_and_instrument_metadata_for_tick_qty_min_notional": {
        "lane": "read_only_runtime_evidence",
        "required_data": [
            "fresh BBO",
            "tick size",
            "qty step",
            "min notional",
            "instrument status",
        ],
        "fastest_safe_test": "use existing no-order BBO/instrument snapshot path or separately reviewed read-only runtime capture",
        "authority_required": "PM->E3 if runtime read is needed; no order authority",
        "failure_condition": "stale BBO, incomplete instrument metadata, non-Trading instrument, or spread no longer clean",
        "max_safe_next_action": "read-only snapshot review only",
    },
    "cap_staircase_with_discrete_exposure_tiers": {
        "lane": "source_only_or_read_only_runtime_evidence",
        "required_data": [
            "cap value",
            "reference price",
            "qty step",
            "min notional",
            "tier notional ladder",
        ],
        "fastest_safe_test": "compute no-order cap staircase from fresh metadata",
        "authority_required": "none for current 10 USDT cap; operator/QC/E3/BB for any cap envelope change",
        "failure_condition": "first executable tier exceeds approved cap or requires cap mutation",
        "max_safe_next_action": "compute no-order current-cap staircase",
    },
    "portfolio_exposure_and_survival_risk_budget_math": {
        "lane": "source_only_risk_design",
        "required_data": [
            "per-order cap",
            "max orders",
            "portfolio exposure budget",
            "survival/risk envelope",
        ],
        "fastest_safe_test": "source-only risk budget worksheet using current caps and no mutation",
        "authority_required": "operator/QC/E3/BB only if risk/cap mutation is proposed",
        "failure_condition": "exposure cannot stay inside existing risk envelope",
        "max_safe_next_action": "source-only risk worksheet",
    },
    "empirical_execution_realism_or_explicit_research_only_status": {
        "lane": "authorization_required_after_probe",
        "required_data": [
            "sample_count >= 30 fill-backed attempts",
            "maker fill rate",
            "adverse selection bps",
            "latency p95",
            "participation rate",
            "capacity vs tier notional",
            "order availability",
        ],
        "fastest_safe_test": "keep current status research-only until authorized candidate-matched fills exist",
        "authority_required": "candidate-scoped bounded Demo authorization plus PM->E3->BB before order",
        "failure_condition": "execution realism thresholds fail or remain unmeasured",
        "max_safe_next_action": "record explicit research-only status",
    },
    "proof_exclusion_scan_for_all_fill_backed_rows": {
        "lane": "source_only_then_post_authorized_review",
        "required_data": [
            "orderLinkId lineage",
            "exchange order id",
            "fill id",
            "intent/risk/source artifact links",
            "fee/slippage fields",
        ],
        "fastest_safe_test": "source-only proof-exclusion contract now; run scan only on future fill-backed rows",
        "authority_required": "none for contract; bounded auth before fill-backed rows",
        "failure_condition": "any unattributed, cleanup, risk-close, stale local, source-smoke, replay-only, or lineage-incomplete row is used as proof",
        "max_safe_next_action": "write proof-exclusion checklist into gap design",
    },
    "regime_breadth_freshness_survivorship_labels": {
        "lane": "source_only_data_design",
        "required_data": [
            "point-in-time regime labels",
            "freshness timestamp",
            "symbol breadth labels",
            "survivorship/staleness labels",
        ],
        "fastest_safe_test": "define leak-free labels and join keys without querying PG",
        "authority_required": "none for design; reviewed read-only data path if runtime/PG labels are later queried",
        "failure_condition": "labels are stale, leaky, bull-only, or not tied to blocked-signal timestamps",
        "max_safe_next_action": "source-only label contract",
    },
    "repeat_or_oos_path_before_any_promotion_claim": {
        "lane": "source_only_validation_design",
        "required_data": [
            "repeat window definition",
            "OOS split",
            "distinct dates",
            "candidate-matched outcomes",
        ],
        "fastest_safe_test": "define repeat/OOS criteria; do not claim promotion from current ranking",
        "authority_required": "none for design; future outcomes require bounded auth",
        "failure_condition": "single-window, replay-only, or artifact-count evidence is used as promotion proof",
        "max_safe_next_action": "source-only repeat/OOS contract",
    },
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


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


def _authority_preserved(payload: dict[str, Any] | None) -> bool:
    stack: list[Any] = [payload]
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


def _ranking_ready(ranking: dict[str, Any]) -> bool:
    return (
        ranking.get("schema_version") == RANKING_SCHEMA_VERSION
        and ranking.get("status") == RANKING_READY_STATUS
    )


def _leader(ranking: dict[str, Any], selected_side_cell_key: str | None) -> dict[str, Any]:
    rows = [row for row in _list(ranking.get("ranked_candidates")) if isinstance(row, dict)]
    selected = _str(selected_side_cell_key)
    if selected:
        for row in rows:
            if _str(row.get("side_cell_key")) == selected:
                return row
        return {}
    for row in rows:
        if row.get("classification") == "REVIEW_ONLY_LEADER_NOT_PROOF":
            return row
    return rows[0] if rows else {}


def _missing_gap_keys(leader: dict[str, Any]) -> list[str]:
    gaps = _dict(leader.get("evidence_floor_gaps"))
    ordered = [key for key in GAP_DESIGNS if gaps.get(key) is False]
    return ordered


def _gap_items(gap_keys: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in gap_keys:
        design = GAP_DESIGNS[key]
        item = {"gap_key": key}
        item.update(design)
        items.append(item)
    return items


def _lane_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in items:
        lane = _str(item.get("lane"))
        summary[lane] = summary.get(lane, 0) + 1
    return summary


def build_false_negative_evidence_floor_gap_closure_design(
    *,
    evidence_floor_ranking: dict[str, Any] | None,
    selected_side_cell_key: str | None = None,
    ranking_path: Path | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    ranking = _dict(evidence_floor_ranking)
    authority_preserved = _authority_preserved(ranking)
    ranking_ready = _ranking_ready(ranking)
    leader = _leader(ranking, selected_side_cell_key)
    gap_keys = _missing_gap_keys(leader) if leader else []
    items = _gap_items(gap_keys)
    if not authority_preserved:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation_in_ranking_input"
    elif not ranking_ready:
        status = INPUT_NOT_READY_STATUS
        reason = "evidence_floor_ranking_not_ready"
    elif not leader or leader.get("classification") != "REVIEW_ONLY_LEADER_NOT_PROOF":
        status = NO_LEADER_STATUS
        reason = "no_review_only_evidence_floor_leader"
    else:
        status = READY_STATUS
        reason = "gap_closure_design_ready_for_review_only_leader"
    if status != READY_STATUS:
        items = []
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "candidate": _dict(leader.get("candidate")) if status == READY_STATUS else {},
        "leader_classification": leader.get("classification") if status == READY_STATUS else None,
        "source_ranking": {
            "path": str(ranking_path) if ranking_path else None,
            "schema_version": ranking.get("schema_version"),
            "status": ranking.get("status"),
            "leader_side_cell_key": leader.get("side_cell_key") if leader else None,
            "floor_satisfied_count": _dict(ranking.get("summary")).get("floor_satisfied_count"),
        },
        "gap_closure_items": items,
        "lane_summary": _lane_summary(items),
        "summary": {
            "gap_count": len(items),
            "source_only_or_design_gap_count": sum(
                1
                for item in items
                if _str(item.get("lane")).startswith("source_only")
                or "source_only" in _str(item.get("lane"))
            ),
            "read_only_runtime_gap_count": sum(
                1 for item in items if "read_only" in _str(item.get("lane"))
            ),
            "authorization_required_gap_count": sum(
                1 for item in items if "authorization_required" in _str(item.get("lane"))
            ),
            "floor_satisfied_after_this_design": False,
            "p0_authorization_required_before_probe": True,
            "max_safe_next_action": (
                "implement_source_only_gap_contracts_or_review_real_auth_delta"
                if status == READY_STATUS
                else "refresh_ready_no_authority_evidence_floor_ranking"
            ),
        },
        "answers": {
            "gap_closure_design_ready": status == READY_STATUS,
            "source_only_research_artifact": True,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "cap_envelope_mutation_allowed": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Evidence-Floor Gap-Closure Design",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Gap Items",
        "",
        "| gap | lane | fastest safe test | authority |",
        "|---|---|---|---|",
    ]
    for item in _list(packet.get("gap_closure_items")):
        lines.append(
            f"| `{item.get('gap_key')}` | `{item.get('lane')}` | "
            f"{item.get('fastest_safe_test')} | {item.get('authority_required')} |"
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
    parser.add_argument("--evidence-floor-ranking-json", type=Path, required=True)
    parser.add_argument("--selected-side-cell-key")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_false_negative_evidence_floor_gap_closure_design(
        evidence_floor_ranking=_read_json(args.evidence_floor_ranking_json),
        selected_side_cell_key=args.selected_side_cell_key,
        ranking_path=args.evidence_floor_ranking_json,
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
