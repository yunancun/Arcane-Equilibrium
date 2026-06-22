#!/usr/bin/env python3
"""Seal a horizon-specific Cost Gate retiming replay candidate.

The horizon edge packet chooses a retiming candidate. This module does not
search for a better cell. It binds that preselected candidate to a replay
counterfactual artifact, hashes the inputs, and checks whether the selected
best horizon still clears the required gates.

It is artifact-only: no PG query/write, Bybit call, order placement, config /
risk / auth / runtime mutation, Cost Gate lowering, probe authority, or
promotion authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "horizon_specific_sealed_replay_packet_v1"
BOUNDARY = (
    "artifact-only sealed replay packet; no PG query/write, Bybit call, order, "
    "config, risk, auth, runtime mutation, Cost Gate lowering, probe authority, "
    "or promotion authority"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value: Any, ndigits: int = 4) -> float | None:
    out = _float(value)
    return round(out, ndigits) if out is not None else None


def _side_cell_parts(side_cell_key: str | None) -> tuple[str | None, str | None, str | None]:
    parts = _str(side_cell_key).split("|")
    if len(parts) != 3:
        return None, None, None
    return parts[0], parts[1], parts[2]


def _horizon_scorecard(counterfactual: dict[str, Any]) -> dict[str, Any]:
    return _dict(_dict(counterfactual.get("learning_lane_scorecard")).get("horizon_stability_scorecard"))


def _learning_thresholds(counterfactual: dict[str, Any]) -> dict[str, Any]:
    return _dict(_dict(counterfactual.get("learning_lane_scorecard")).get("thresholds"))


def _input_meta(path: Path | None, payload: dict[str, Any]) -> dict[str, Any]:
    sha256 = None
    if path is not None:
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "path": str(path) if path is not None else None,
        "sha256": sha256,
        "schema_version": payload.get("schema_version")
        or _dict(payload.get("learning_lane_scorecard")).get("schema_version"),
        "generated_at_utc": payload.get("generated_at_utc"),
    }


def _find_candidate(
    horizon_packet: dict[str, Any],
    *,
    candidate_rank: int,
    side_cell_key: str | None,
) -> dict[str, Any] | None:
    candidates = [row for row in _list(horizon_packet.get("candidates")) if isinstance(row, dict)]
    if side_cell_key:
        for row in candidates:
            if row.get("side_cell_key") == side_cell_key:
                return row
        return None
    for row in candidates:
        if _int(row.get("rank")) == candidate_rank:
            return row
    return None


def _side_cell_matches(row: dict[str, Any], side_cell_key: str) -> bool:
    strategy, symbol, side = _side_cell_parts(side_cell_key)
    if not strategy:
        return False
    return (
        row.get("strategy_name") == strategy
        and row.get("symbol") == symbol
        and row.get("side") == side
    )


def _find_horizon_side_cell(counterfactual: dict[str, Any], side_cell_key: str) -> dict[str, Any] | None:
    for row in _list(_horizon_scorecard(counterfactual).get("top_side_cells")):
        if isinstance(row, dict) and row.get("side_cell_key") == side_cell_key:
            return row
    return None


def _find_replay_row(counterfactual: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any] | None:
    side_cell_key = _str(candidate.get("side_cell_key"))
    best_horizon = _int(candidate.get("best_horizon_minutes"))
    side_cell = _find_horizon_side_cell(counterfactual, side_cell_key)
    if side_cell:
        for row in _list(side_cell.get("horizon_rows")):
            if isinstance(row, dict) and _int(row.get("horizon_minutes")) == best_horizon:
                out = dict(row)
                out.setdefault("side_cell_key", side_cell_key)
                out.setdefault("source", "horizon_stability_scorecard")
                return out

    top_horizon = _int(counterfactual.get("horizon_minutes"))
    if top_horizon != best_horizon:
        return None
    for row in _list(_dict(counterfactual.get("learning_lane_scorecard")).get("rows")):
        if isinstance(row, dict) and _side_cell_matches(row, side_cell_key):
            out = dict(row)
            out.setdefault("horizon_minutes", top_horizon)
            out.setdefault("sample_count_for_gate", row.get("sample_count_for_gate") or row.get("distinct_ts") or row.get("n"))
            out.setdefault("source", "learning_lane_scorecard.rows")
            return out
    return None


def _find_primary_row(candidate: dict[str, Any]) -> dict[str, Any] | None:
    primary_horizon = _int(candidate.get("primary_horizon_minutes"))
    for row in _list(candidate.get("raw_horizon_rows")):
        if isinstance(row, dict) and _int(row.get("horizon_minutes")) == primary_horizon:
            return row
    return None


def _metric_drift(candidate_value: Any, replay_value: Any) -> float | None:
    left = _float(candidate_value)
    right = _float(replay_value)
    if left is None or right is None:
        return None
    return abs(left - right)


def _gate(name: str, passed: bool, *, actual: Any = None, expected: Any = None) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "actual": actual,
        "expected": expected,
    }


def build_horizon_specific_sealed_replay_packet(
    *,
    horizon_packet: dict[str, Any] | None,
    replay_counterfactual: dict[str, Any] | None,
    candidate_rank: int = 1,
    side_cell_key: str | None = None,
    horizon_packet_path: Path | None = None,
    replay_counterfactual_path: Path | None = None,
    min_sample: int | None = None,
    min_avg_net_bps: float | None = None,
    min_net_positive_pct: float | None = None,
    min_edge_amplification_bps: float = 0.0,
    max_metric_drift_bps: float = 0.001,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    horizon_payload = _dict(horizon_packet)
    replay_payload = _dict(replay_counterfactual)
    candidate = _find_candidate(
        horizon_payload,
        candidate_rank=candidate_rank,
        side_cell_key=side_cell_key,
    )

    thresholds = _learning_thresholds(replay_payload)
    friction_bps = _float(replay_payload.get("friction_bps")) or _float(thresholds.get("friction_bps")) or 4.0
    sample_floor = min_sample if min_sample is not None else _int(thresholds.get("min_probe_sample"), 100)
    avg_net_floor = (
        min_avg_net_bps
        if min_avg_net_bps is not None
        else (_float(thresholds.get("min_probe_avg_net_bps")) or 0.0)
    )
    hit_rate_floor = (
        min_net_positive_pct
        if min_net_positive_pct is not None
        else (_float(thresholds.get("min_probe_net_positive_pct")) or 55.0)
    )

    replay_row = _find_replay_row(replay_payload, candidate) if candidate else None
    primary_row = _find_primary_row(candidate) if candidate else None

    selected = {
        "rank": candidate.get("rank") if candidate else None,
        "side_cell_key": candidate.get("side_cell_key") if candidate else side_cell_key,
        "candidate_status": candidate.get("status") if candidate else None,
        "best_horizon_minutes": candidate.get("best_horizon_minutes") if candidate else None,
        "primary_horizon_minutes": candidate.get("primary_horizon_minutes") if candidate else None,
        "primary_horizon_action": candidate.get("primary_horizon_action") if candidate else None,
        "required_next_gate": candidate.get("required_next_gate") if candidate else None,
    }

    replay_metrics = {
        "source": replay_row.get("source") if replay_row else None,
        "horizon_minutes": _int(replay_row.get("horizon_minutes")) if replay_row else None,
        "learning_lane_action": replay_row.get("learning_lane_action") if replay_row else None,
        "sample_count_for_gate": _int(replay_row.get("sample_count_for_gate")) if replay_row else 0,
        "avg_net_bps": _round(replay_row.get("avg_net_bps")) if replay_row else None,
        "p50_gross_bps": _round(replay_row.get("p50_gross_bps")) if replay_row else None,
        "net_positive_pct": _round(replay_row.get("net_positive_pct")) if replay_row else None,
        "candidate_best_net_bps": _round(candidate.get("best_net_bps")) if candidate else None,
        "candidate_best_p50_gross_bps": _round(candidate.get("best_p50_gross_bps")) if candidate else None,
        "candidate_edge_amplification_vs_primary_bps": (
            _round(candidate.get("edge_amplification_vs_primary_bps")) if candidate else None
        ),
        "best_net_metric_drift_bps": (
            _round(_metric_drift(candidate.get("best_net_bps"), replay_row.get("avg_net_bps")), 6)
            if candidate and replay_row
            else None
        ),
        "p50_gross_metric_drift_bps": (
            _round(_metric_drift(candidate.get("best_p50_gross_bps"), replay_row.get("p50_gross_bps")), 6)
            if candidate and replay_row
            else None
        ),
    }
    primary_metrics = {
        "horizon_minutes": _int(primary_row.get("horizon_minutes")) if primary_row else None,
        "learning_lane_action": primary_row.get("learning_lane_action") if primary_row else None,
        "avg_net_bps": _round(primary_row.get("avg_net_bps")) if primary_row else None,
        "sample_count_for_gate": _int(primary_row.get("sample_count_for_gate")) if primary_row else 0,
    }

    gates = [
        _gate("candidate_found", candidate is not None, actual=bool(candidate), expected=True),
        _gate(
            "candidate_is_retiming",
            bool(candidate and candidate.get("status") == "RETIMING_CANDIDATE"),
            actual=candidate.get("status") if candidate else None,
            expected="RETIMING_CANDIDATE",
        ),
        _gate("replay_row_found", replay_row is not None, actual=bool(replay_row), expected=True),
        _gate(
            "best_horizon_matches_selection",
            bool(replay_row and candidate and _int(replay_row.get("horizon_minutes")) == _int(candidate.get("best_horizon_minutes"))),
            actual=replay_metrics["horizon_minutes"],
            expected=candidate.get("best_horizon_minutes") if candidate else None,
        ),
        _gate(
            "replay_action_is_candidate",
            bool(replay_row and replay_row.get("learning_lane_action") == "LEARNING_PROBE_CANDIDATE"),
            actual=replay_metrics["learning_lane_action"],
            expected="LEARNING_PROBE_CANDIDATE",
        ),
        _gate(
            "sample_floor_met",
            replay_metrics["sample_count_for_gate"] >= sample_floor,
            actual=replay_metrics["sample_count_for_gate"],
            expected=f">={sample_floor}",
        ),
        _gate(
            "avg_net_floor_met",
            bool(_float(replay_metrics["avg_net_bps"]) is not None and _float(replay_metrics["avg_net_bps"]) > avg_net_floor),
            actual=replay_metrics["avg_net_bps"],
            expected=f">{avg_net_floor}",
        ),
        _gate(
            "median_gross_clears_friction",
            bool(_float(replay_metrics["p50_gross_bps"]) is not None and _float(replay_metrics["p50_gross_bps"]) > friction_bps),
            actual=replay_metrics["p50_gross_bps"],
            expected=f">{friction_bps}",
        ),
        _gate(
            "hit_rate_floor_met",
            bool(_float(replay_metrics["net_positive_pct"]) is not None and _float(replay_metrics["net_positive_pct"]) >= hit_rate_floor),
            actual=replay_metrics["net_positive_pct"],
            expected=f">={hit_rate_floor}",
        ),
        _gate(
            "primary_horizon_block_confirmed",
            bool(primary_row and primary_row.get("learning_lane_action") == "BLOCK_CONFIRMED"),
            actual=primary_metrics["learning_lane_action"],
            expected="BLOCK_CONFIRMED",
        ),
        _gate(
            "primary_horizon_net_negative",
            bool(_float(primary_metrics["avg_net_bps"]) is not None and _float(primary_metrics["avg_net_bps"]) < 0),
            actual=primary_metrics["avg_net_bps"],
            expected="<0",
        ),
        _gate(
            "edge_amplification_positive",
            bool(
                candidate
                and _float(candidate.get("edge_amplification_vs_primary_bps")) is not None
                and _float(candidate.get("edge_amplification_vs_primary_bps")) > min_edge_amplification_bps
            ),
            actual=candidate.get("edge_amplification_vs_primary_bps") if candidate else None,
            expected=f">{min_edge_amplification_bps}",
        ),
        _gate(
            "best_net_metric_drift_within_tolerance",
            bool(
                replay_metrics["best_net_metric_drift_bps"] is not None
                and replay_metrics["best_net_metric_drift_bps"] <= max_metric_drift_bps
            ),
            actual=replay_metrics["best_net_metric_drift_bps"],
            expected=f"<={max_metric_drift_bps}",
        ),
        _gate(
            "p50_gross_metric_drift_within_tolerance",
            bool(
                replay_metrics["p50_gross_metric_drift_bps"] is not None
                and replay_metrics["p50_gross_metric_drift_bps"] <= max_metric_drift_bps
            ),
            actual=replay_metrics["p50_gross_metric_drift_bps"],
            expected=f"<={max_metric_drift_bps}",
        ),
    ]
    passed = all(gate["passed"] for gate in gates)
    status = (
        "SEALED_HORIZON_REPLAY_READY_FOR_OPERATOR_REVIEW"
        if passed
        else "SEALED_HORIZON_REPLAY_BLOCKED"
    )
    failed_gate_names = [gate["name"] for gate in gates if not gate["passed"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": (
            "preselected_retiming_candidate_revalidated_against_sealed_replay_artifact"
            if passed
            else "sealed_replay_gates_failed"
        ),
        "next_action": (
            "operator_review_sealed_replay_then_wait_for_learning_stack_outcome_accumulation"
            if passed
            else "rerun_or_repair_horizon_replay_artifacts_before_any_probe_review"
        ),
        "selection": {
            "candidate_rank": candidate_rank,
            "requested_side_cell_key": side_cell_key,
            "selected": selected,
        },
        "source": {
            "horizon_packet": _input_meta(horizon_packet_path, horizon_payload),
            "replay_counterfactual": _input_meta(replay_counterfactual_path, replay_payload),
        },
        "thresholds": {
            "min_sample": sample_floor,
            "min_avg_net_bps": avg_net_floor,
            "min_net_positive_pct": hit_rate_floor,
            "min_edge_amplification_bps": min_edge_amplification_bps,
            "max_metric_drift_bps": max_metric_drift_bps,
            "friction_bps": friction_bps,
        },
        "replay_evaluation": {
            "side_cell_key": selected["side_cell_key"],
            "best_horizon": replay_metrics,
            "primary_horizon": primary_metrics,
            "failed_gate_names": failed_gate_names,
            "gates": gates,
        },
        "answers": {
            "sealed_replay_passed": passed,
            "retiming_candidate_revalidated": passed,
            "operator_review_ready": passed,
            "requires_learning_stack_accumulation": True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "global_boundaries": {
            "order_authority": "NOT_GRANTED",
            "probe_authority": "NOT_GRANTED",
            "main_cost_gate_adjustment": "NONE",
            "runtime_mutation": "NONE",
            "promotion_evidence": False,
            "boundary": BOUNDARY,
        },
    }


def render_markdown(packet: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|")

    selected = _dict(_dict(packet.get("selection")).get("selected"))
    replay = _dict(_dict(packet.get("replay_evaluation")).get("best_horizon"))
    primary = _dict(_dict(packet.get("replay_evaluation")).get("primary_horizon"))
    lines = [
        "# Horizon Specific Sealed Replay Packet",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Next action: `{packet.get('next_action')}`",
        "- Boundary: artifact-only; no order authority, no probe authority, no Cost Gate lowering.",
        "",
        "## Selected Candidate",
        "",
        "| field | value |",
        "|---|---|",
        f"| side_cell | {cell(selected.get('side_cell_key'))} |",
        f"| candidate_status | `{selected.get('candidate_status')}` |",
        f"| primary_horizon | `{selected.get('primary_horizon_minutes')}` |",
        f"| best_horizon | `{selected.get('best_horizon_minutes')}` |",
        f"| required_next_gate | `{selected.get('required_next_gate')}` |",
        "",
        "## Replay Metrics",
        "",
        "| horizon | action | sample_n | avg_net_bps | p50_gross_bps | net_positive_pct |",
        "|---:|---|---:|---:|---:|---:|",
        (
            f"| {replay.get('horizon_minutes')} | {replay.get('learning_lane_action')} | "
            f"{replay.get('sample_count_for_gate')} | {replay.get('avg_net_bps')} | "
            f"{replay.get('p50_gross_bps')} | {replay.get('net_positive_pct')} |"
        ),
        (
            f"| {primary.get('horizon_minutes')} | {primary.get('learning_lane_action')} | "
            f"{primary.get('sample_count_for_gate')} | {primary.get('avg_net_bps')} | n/a | n/a |"
        ),
        "",
        "## Gates",
        "",
        "| gate | passed | actual | expected |",
        "|---|---:|---|---|",
    ]
    for gate in _list(_dict(packet.get("replay_evaluation")).get("gates")):
        if not isinstance(gate, dict):
            continue
        lines.append(
            f"| {cell(gate.get('name'))} | `{gate.get('passed')}` | "
            f"`{cell(gate.get('actual'))}` | `{cell(gate.get('expected'))}` |"
        )
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizon-packet-json", type=Path, required=True)
    parser.add_argument("--replay-counterfactual-json", type=Path, required=True)
    parser.add_argument("--candidate-rank", type=int, default=1)
    parser.add_argument("--side-cell-key")
    parser.add_argument("--min-sample", type=int)
    parser.add_argument("--min-avg-net-bps", type=float)
    parser.add_argument("--min-net-positive-pct", type=float)
    parser.add_argument("--min-edge-amplification-bps", type=float, default=0.0)
    parser.add_argument("--max-metric-drift-bps", type=float, default=0.001)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_horizon_specific_sealed_replay_packet(
        horizon_packet=_read_json(args.horizon_packet_json),
        replay_counterfactual=_read_json(args.replay_counterfactual_json),
        candidate_rank=args.candidate_rank,
        side_cell_key=args.side_cell_key,
        horizon_packet_path=args.horizon_packet_json,
        replay_counterfactual_path=args.replay_counterfactual_json,
        min_sample=args.min_sample,
        min_avg_net_bps=args.min_avg_net_bps,
        min_net_positive_pct=args.min_net_positive_pct,
        min_edge_amplification_bps=args.min_edge_amplification_bps,
        max_metric_drift_bps=args.max_metric_drift_bps,
    )
    if args.output:
        _write_text(args.output, render_markdown(packet))
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    if not (args.output or args.json_output or args.print_json):
        print(render_markdown(packet), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
