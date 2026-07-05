#!/usr/bin/env python3
"""Rank false-negative candidates against the cap-envelope evidence floor.

This is a source-only aggressive-alpha triage packet. It joins the current
false-negative friction scorecard, current-cap feasibility screen, and the
autonomous proposal evidence-floor contract. It never lowers Cost Gate, grants
authority, mutates runtime state, writes PG, calls Bybit, or submits orders.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

# 共用純函數葉節點：以 alias-import 保持函數體內 _utc_now/_dict/_list/_str 引用逐字節不變。
from cost_gate_learning_lane._lane_common import (
    as_dict as _dict,
    as_list as _list,
    as_str as _str,
    utc_now as _utc_now,
)


SCHEMA_VERSION = "cost_gate_false_negative_evidence_floor_ranking_v1"
READY_STATUS = "FALSE_NEGATIVE_EVIDENCE_FLOOR_RANKING_READY_NO_AUTHORITY"
INPUT_NOT_READY_STATUS = "FALSE_NEGATIVE_EVIDENCE_FLOOR_INPUT_NOT_READY"
NO_CANDIDATES_STATUS = "NO_FALSE_NEGATIVE_EVIDENCE_FLOOR_CANDIDATES"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"
EVIDENCE_FLOOR_CONTRACT_NOT_READY_STATUS = "EVIDENCE_FLOOR_CONTRACT_NOT_READY"
FRICTION_SCORECARD_SCHEMA_VERSION = "cost_gate_false_negative_candidate_friction_scorecard_v1"
FRICTION_SCORECARD_READY_STATUS = "FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY"
CAP_SCREEN_SCHEMA_VERSION = "bounded_probe_candidate_universe_instrument_screen_input_v1"
AUTONOMOUS_PROPOSAL_SCHEMA_VERSION = "cost_gate_autonomous_parameter_proposal_v1"
CAP_ENVELOPE_EVIDENCE_FLOOR_SCHEMA_VERSION = "cost_gate_cap_envelope_evidence_floor_v1"
MIN_SAMPLE_COUNT = 30
MIN_NET_CUSHION_BPS = 15.0
MIN_NET_POSITIVE_PCT = 75.0
MAX_CLEAN_SPREAD_BPS = 2.0
BOUNDARY = (
    "artifact-only false-negative evidence-floor ranking; no PG query/write, "
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


def _artifact_summary(
    *,
    name: str,
    path: Path | None,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    data = _dict(payload)
    return {
        "name": name,
        "path": str(path) if path else None,
        "present": bool(data),
        "schema_version": data.get("schema_version"),
        "status": data.get("status"),
        "generated_at_utc": data.get("generated_at_utc"),
    }


def _scorecard_ready(scorecard: dict[str, Any]) -> bool:
    return (
        scorecard.get("schema_version") == FRICTION_SCORECARD_SCHEMA_VERSION
        and scorecard.get("status") == FRICTION_SCORECARD_READY_STATUS
    )


def _cap_screen_ready(cap_screen: dict[str, Any]) -> bool:
    return cap_screen.get("schema_version") == CAP_SCREEN_SCHEMA_VERSION


def _proposal_floor(proposal: dict[str, Any]) -> dict[str, Any]:
    proposal_body = _dict(proposal.get("proposal"))
    floor = _dict(proposal_body.get("cap_envelope_evidence_floor"))
    if floor.get("schema_version") == CAP_ENVELOPE_EVIDENCE_FLOOR_SCHEMA_VERSION:
        return floor
    return {}


def _proposal_floor_ready(proposal: dict[str, Any]) -> bool:
    return (
        proposal.get("schema_version") == AUTONOMOUS_PROPOSAL_SCHEMA_VERSION
        and proposal.get("status") == "REVIEWABLE_PARAMETER_PROPOSAL_READY"
        and bool(_proposal_floor(proposal))
        and _dict(proposal.get("answers")).get("cap_envelope_mutation_allowed") is False
    )


def _scorecard_rows(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _list(scorecard.get("ranked_candidates")) if isinstance(row, dict)]


def _cap_rows_by_side_cell(cap_screen: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _list(cap_screen.get("rows")):
        data = _dict(row)
        side_cell = _str(data.get("side_cell_key"))
        if side_cell:
            out[side_cell] = data
    return out


def _candidate_identity(scorecard_row: dict[str, Any], cap_row: dict[str, Any]) -> dict[str, Any]:
    candidate = _dict(scorecard_row.get("candidate"))
    return {
        "side_cell_key": scorecard_row.get("side_cell_key") or cap_row.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name") or cap_row.get("strategy_name"),
        "symbol": candidate.get("symbol") or cap_row.get("symbol"),
        "side": candidate.get("side") or cap_row.get("side"),
        "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes")
        or cap_row.get("outcome_horizon_minutes"),
    }


def _complete_bbo(cap_row: dict[str, Any]) -> bool:
    return (_float(cap_row.get("best_bid")) or 0.0) > 0.0 and (
        _float(cap_row.get("best_ask")) or 0.0
    ) > 0.0


def _clean_spread(cap_row: dict[str, Any]) -> bool:
    spread = _float(cap_row.get("spread_bps"))
    return spread is not None and spread > 0.0 and spread <= MAX_CLEAN_SPREAD_BPS


def _classification(*, passes_pre_floor: bool, failures: list[str]) -> str:
    if passes_pre_floor:
        return "REVIEW_ONLY_LEADER_NOT_PROOF"
    if "current_cap_feasible" in failures:
        return "RESEARCH_ONLY_CAP_INFEASIBLE"
    if "complete_bbo" in failures or "clean_spread" in failures:
        return "REJECT_BBO_OR_SPREAD_NOT_CLEAN"
    if "sample_count_floor" in failures:
        return "RESEARCH_CONTROL_SAMPLE_BELOW_FLOOR"
    return "REJECT_EVIDENCE_FLOOR_PREFILTER"


def _evidence_floor_gaps(
    *,
    side_cell_key: str,
    proposal: dict[str, Any],
    pre_floor_pass: bool,
    complete_bbo: bool,
    current_cap_feasible: bool,
    sample_floor_pass: bool,
) -> dict[str, Any]:
    proposal_side_cell = _str(proposal.get("selected_side_cell_key"))
    return {
        "candidate_side_cell_matches_learning_packet": side_cell_key == proposal_side_cell,
        "candidate_matched_controls_present": False,
        "candidate_matched_fee_slippage_and_maker_taker_labels": False,
        "fresh_bbo_and_instrument_metadata_for_tick_qty_min_notional": False,
        "artifact_bbo_present": complete_bbo,
        "current_cap_construction_present": current_cap_feasible,
        "cap_staircase_with_discrete_exposure_tiers": False,
        "portfolio_exposure_and_survival_risk_budget_math": False,
        "empirical_execution_realism_or_explicit_research_only_status": False,
        "sample_count_floor_pass": sample_floor_pass,
        "proof_exclusion_scan_for_all_fill_backed_rows": False,
        "regime_breadth_freshness_survivorship_labels": False,
        "repeat_or_oos_path_before_any_promotion_claim": False,
        "floor_satisfied": False,
        "review_only_prefilter_pass": pre_floor_pass,
    }


def _next_action(classification: str) -> str:
    if classification == "REVIEW_ONLY_LEADER_NOT_PROOF":
        return "keep_as_review_only_leader_until_candidate_auth_and_floor_gaps_close"
    if classification == "RESEARCH_ONLY_CAP_INFEASIBLE":
        return "separate_cap_envelope_research_only_review"
    if classification == "RESEARCH_CONTROL_SAMPLE_BELOW_FLOOR":
        return "retain_as_research_control_until_sample_floor_and_controls_exist"
    return "exclude_from_bounded_probe_candidate_without_fresh_clean_evidence"


def _rank_score(
    *,
    pre_floor_pass: bool,
    current_cap_feasible: bool,
    clean_bbo: bool,
    sample_floor_pass: bool,
    net_cushion_bps: float,
    net_positive_pct: float,
    outcome_count: int,
    friction_rank: int,
) -> float:
    """僅供 sorted() 顯示排序 tie-break 的 heuristic score，非 gate 門檻（QC-9）。

    為什麼混量綱加總在此為 by-design：
      (1) 真 pass/fail 是 _rank_row 的獨立布林 checks（pre_floor_pass 等），本 score
          只決定 top-N 顯示先後，供 operator review，不作晉升或門檻依據。
      (2) tier bonus 1000/100/50/40 為刻意 lexicographic 分層：
          pre_floor_pass(1000) >> current_cap_feasible(100) >> clean_bbo(50) >>
          sample_floor(40)。巨大 gap 確保「同層」內才由連續量
          (net_cushion_bps + max(0,net_positive-50)/2 + log10(n)·5) 決序 —— 混量綱
          加總只在同層細排時起作用，跨層永遠由 tier 主導。
      (3) 常數敏感性：只要每級 tier gap 遠大於同層連續量的典型幅度（bps 級 cushion +
          最多 ~25 的 net_positive/2 + 個位數 log 項），排序即穩健，不需精調常數。
    此 docstring 為純說明；公式與常數 0 變更。
    """
    score = net_cushion_bps + max(0.0, net_positive_pct - 50.0) / 2.0
    score += math.log10(max(outcome_count, 1) + 1.0) * 5.0
    if pre_floor_pass:
        score += 1000.0
    if current_cap_feasible:
        score += 100.0
    if clean_bbo:
        score += 50.0
    if sample_floor_pass:
        score += 40.0
    score -= max(friction_rank - 1, 0) * 0.01
    return round(score, 4)


def _rank_row(
    scorecard_row: dict[str, Any],
    *,
    cap_row: dict[str, Any] | None,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    cap = _dict(cap_row)
    side_cell = _str(scorecard_row.get("side_cell_key"))
    current_cap_feasible = cap.get("fits_current_cap") is True
    complete_bbo = _complete_bbo(cap)
    clean_spread = complete_bbo and _clean_spread(cap)
    outcome_count = _int(scorecard_row.get("outcome_count") or cap.get("outcome_count"))
    sample_floor_pass = outcome_count >= MIN_SAMPLE_COUNT
    net_cushion = _float(
        scorecard_row.get("net_cost_cushion_bps") or cap.get("net_cost_cushion_bps")
    ) or 0.0
    net_positive = _float(scorecard_row.get("net_positive_pct") or cap.get("net_positive_pct")) or 0.0
    net_cushion_pass = net_cushion >= MIN_NET_CUSHION_BPS
    net_positive_pass = net_positive >= MIN_NET_POSITIVE_PCT
    checks = {
        "current_cap_feasible": current_cap_feasible,
        "complete_bbo": complete_bbo,
        "clean_spread": clean_spread,
        "sample_count_floor": sample_floor_pass,
        "net_cost_cushion_floor": net_cushion_pass,
        "net_positive_floor": net_positive_pass,
    }
    failures = [key for key, passed in checks.items() if not passed]
    pre_floor_pass = not failures
    classification = _classification(passes_pre_floor=pre_floor_pass, failures=failures)
    return {
        "side_cell_key": side_cell,
        "candidate": _candidate_identity(scorecard_row, cap),
        "source_friction_rank": scorecard_row.get("friction_rank"),
        "false_negative_rank": scorecard_row.get("false_negative_rank"),
        "classification": classification,
        "review_only_prefilter_pass": pre_floor_pass,
        "floor_satisfied": False,
        "checks": checks,
        "failed_checks": failures,
        "evidence_floor_gaps": _evidence_floor_gaps(
            side_cell_key=side_cell,
            proposal=proposal,
            pre_floor_pass=pre_floor_pass,
            complete_bbo=complete_bbo,
            current_cap_feasible=current_cap_feasible,
            sample_floor_pass=sample_floor_pass,
        ),
        "metrics": {
            "net_cost_cushion_bps": _round(net_cushion),
            "outcome_count": outcome_count,
            "net_positive_pct": _round(net_positive),
            "spread_bps": _round(cap.get("spread_bps")),
            "best_bid": _round(cap.get("best_bid")),
            "best_ask": _round(cap.get("best_ask")),
            "cap_usdt": _round(cap.get("cap_usdt")),
            "min_notional": _round(cap.get("min_notional")),
        },
        "ranking_score": _rank_score(
            pre_floor_pass=pre_floor_pass,
            current_cap_feasible=current_cap_feasible,
            clean_bbo=clean_spread,
            sample_floor_pass=sample_floor_pass,
            net_cushion_bps=net_cushion,
            net_positive_pct=net_positive,
            outcome_count=outcome_count,
            friction_rank=_int(scorecard_row.get("friction_rank"), 999999),
        ),
        "next_action": _next_action(classification),
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
    }


def build_false_negative_evidence_floor_ranking(
    *,
    false_negative_candidate_friction_scorecard: dict[str, Any] | None,
    cap_feasible_screen: dict[str, Any] | None,
    autonomous_parameter_proposal: dict[str, Any] | None,
    paths: dict[str, Path | None] | None = None,
    now_utc: dt.datetime | None = None,
    top_limit: int = 16,
) -> dict[str, Any]:
    if top_limit < 1 or top_limit > 100:
        raise ValueError("top_limit must be in [1, 100]")
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    paths = paths or {}
    scorecard = _dict(false_negative_candidate_friction_scorecard)
    cap_screen = _dict(cap_feasible_screen)
    proposal = _dict(autonomous_parameter_proposal)
    authority_preserved = _authority_preserved(scorecard, cap_screen, proposal)
    scorecard_ready = _scorecard_ready(scorecard)
    cap_screen_ready = _cap_screen_ready(cap_screen)
    proposal_floor_ready = _proposal_floor_ready(proposal)
    rows: list[dict[str, Any]] = []
    if authority_preserved and scorecard_ready and cap_screen_ready and proposal_floor_ready:
        cap_by_side_cell = _cap_rows_by_side_cell(cap_screen)
        rows = [
            _rank_row(row, cap_row=cap_by_side_cell.get(_str(row.get("side_cell_key"))), proposal=proposal)
            for row in _scorecard_rows(scorecard)
        ]
        rows = sorted(
            rows,
            key=lambda row: (
                -(_float(row.get("ranking_score")) or 0.0),
                _int(row.get("source_friction_rank"), 999999),
                _str(row.get("side_cell_key")),
            ),
        )[:top_limit]
        for index, row in enumerate(rows, start=1):
            row["evidence_floor_rank"] = index
    if not authority_preserved:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation_in_inputs"
    elif not scorecard_ready or not cap_screen_ready:
        status = INPUT_NOT_READY_STATUS
        reason = "scorecard_or_cap_screen_not_ready"
    elif not proposal_floor_ready:
        status = EVIDENCE_FLOOR_CONTRACT_NOT_READY_STATUS
        reason = "autonomous_parameter_proposal_missing_cap_envelope_evidence_floor"
    elif not rows:
        status = NO_CANDIDATES_STATUS
        reason = "no_rankable_false_negative_candidates"
    else:
        status = READY_STATUS
        reason = "ranked_false_negative_candidates_against_evidence_floor"
    leader = rows[0] if rows else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "ranked_candidates": rows,
        "summary": {
            "ranked_count": len(rows),
            "review_only_prefilter_pass_count": sum(
                1 for row in rows if row.get("review_only_prefilter_pass") is True
            ),
            "floor_satisfied_count": 0,
            "review_only_leader_side_cell_key": leader.get("side_cell_key"),
            "review_only_leader_classification": leader.get("classification"),
            "authorization_required_before_order": True,
            "top_next_action": leader.get("next_action"),
        },
        "answers": {
            "evidence_floor_ranking_ready": status == READY_STATUS,
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
        "artifacts": {
            "false_negative_candidate_friction_scorecard": _artifact_summary(
                name="false_negative_candidate_friction_scorecard",
                path=paths.get("false_negative_candidate_friction_scorecard"),
                payload=scorecard,
            ),
            "cap_feasible_screen": _artifact_summary(
                name="cap_feasible_screen",
                path=paths.get("cap_feasible_screen"),
                payload=cap_screen,
            ),
            "autonomous_parameter_proposal": _artifact_summary(
                name="autonomous_parameter_proposal",
                path=paths.get("autonomous_parameter_proposal"),
                payload=proposal,
            ),
        },
        "ranking_policy": {
            "min_sample_count": MIN_SAMPLE_COUNT,
            "min_net_cushion_bps": MIN_NET_CUSHION_BPS,
            "min_net_positive_pct": MIN_NET_POSITIVE_PCT,
            "max_clean_spread_bps": MAX_CLEAN_SPREAD_BPS,
            "floor_satisfied_requires_future_candidate_matched_controls_fills_realism_regime_oos": True,
        },
        "next_actions": [
            "keep_review_only_leader_blocked_until_candidate_scoped_authorization",
            "close_evidence_floor_gaps_before_any_cap_envelope_or_promotion_claim",
            "keep_main_cost_gate_adjustment_none",
        ],
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# False-Negative Evidence-Floor Ranking",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Ranked Candidates",
        "",
        "| rank | side-cell | classification | score | cushion bps | outcomes | failed checks | next action |",
        "|---:|---|---|---:|---:|---:|---|---|",
    ]
    for row in _list(packet.get("ranked_candidates")):
        metrics = _dict(row.get("metrics"))
        failed = ", ".join(_list(row.get("failed_checks"))) or "none"
        lines.append(
            f"| {row.get('evidence_floor_rank')} | `{row.get('side_cell_key')}` | "
            f"`{row.get('classification')}` | `{row.get('ranking_score')}` | "
            f"`{metrics.get('net_cost_cushion_bps')}` | `{metrics.get('outcome_count')}` | "
            f"`{failed}` | `{row.get('next_action')}` |"
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
    parser.add_argument("--false-negative-candidate-friction-scorecard-json", type=Path, required=True)
    parser.add_argument("--cap-feasible-screen-json", type=Path, required=True)
    parser.add_argument("--autonomous-parameter-proposal-json", type=Path, required=True)
    parser.add_argument("--top-limit", type=int, default=16)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_false_negative_evidence_floor_ranking(
        false_negative_candidate_friction_scorecard=_read_json(
            args.false_negative_candidate_friction_scorecard_json
        ),
        cap_feasible_screen=_read_json(args.cap_feasible_screen_json),
        autonomous_parameter_proposal=_read_json(args.autonomous_parameter_proposal_json),
        paths={
            "false_negative_candidate_friction_scorecard": (
                args.false_negative_candidate_friction_scorecard_json
            ),
            "cap_feasible_screen": args.cap_feasible_screen_json,
            "autonomous_parameter_proposal": args.autonomous_parameter_proposal_json,
        },
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
