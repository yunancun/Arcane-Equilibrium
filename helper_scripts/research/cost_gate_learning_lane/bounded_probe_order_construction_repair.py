#!/usr/bin/env python3
"""Build a no-authority order-construction repair proposal for bounded probes.

This artifact consumes a no-order placement construction preview. It converts
instrument-filter and BBO failures into reviewable repair options, such as a
QC/operator-reviewed cap adjustment or rerouting to a candidate whose minimum
quantity fits the current cap.

It does not query PG, call Bybit, submit orders, lower the Cost Gate, grant
probe/order authority, append ledgers, or mutate runtime state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any

# 共用純函數葉節點：以 alias-import 保持函數體內 _dict/_list/_str/_utc_now 引用逐字節不變。
from cost_gate_learning_lane._lane_common import (
    as_dict as _dict,
    as_list as _list,
    as_str as _str,
    utc_now as _utc_now,
)


ORDER_CONSTRUCTION_REPAIR_SCHEMA_VERSION = (
    "bounded_demo_probe_order_construction_repair_v1"
)
PLACEMENT_CONSTRUCTION_PREVIEW_SCHEMA_VERSION = (
    "bounded_probe_no_order_placement_construction_preview_v1"
)
CANDIDATE_UNIVERSE_SCHEMA_VERSION = (
    "bounded_probe_candidate_universe_instrument_screen_input_v1"
)
BOUNDARY = (
    "artifact-only bounded Demo probe order-construction repair proposal; no PG "
    "query/write, Bybit call, order, config, risk, auth, runtime mutation, "
    "Cost Gate lowering, probe authority, order authority, ledger append, or "
    "promotion proof"
)

FORBIDDEN_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "bybit_call_performed",
    "canonical_plan_mutation_performed",
    "cost_gate_lowering_recommended",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "mainnet_authority_granted",
    "order_authority_granted",
    "order_submission_performed",
    "pg_write_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "runtime_mutation_performed",
    "writer_enabled",
}


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value: Any, ndigits: int = 6) -> float | None:
    parsed = _float(value)
    return round(parsed, ndigits) if parsed is not None else None


def _parse_dt(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
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


def _artifact_status(
    payload: dict[str, Any] | None,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    present = isinstance(payload, dict) and bool(payload)
    generated_at = (
        (payload or {}).get("generated_at_utc")
        or (payload or {}).get("generated")
        or (payload or {}).get("ts_utc")
    )
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
        "status": status,
        "present": present,
        "generated_at_utc": generated_at,
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
        "schema_version": (payload or {}).get("schema_version") if present else None,
    }


def _iter_nodes(value: Any) -> list[Any]:
    out: list[Any] = [value]
    if isinstance(value, dict):
        for item in value.values():
            out.extend(_iter_nodes(item))
    elif isinstance(value, list):
        for item in value:
            out.extend(_iter_nodes(item))
    return out


def _contaminating_value(value: Any) -> bool:
    if value is None or value is False:
        return False
    if value is True:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        return text not in {"", "0", "false", "no", "none", "null"}
    if isinstance(value, (dict, list, tuple, set)):
        return len(value) > 0
    return True


def _authority_preserved(payload: dict[str, Any] | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for node in _iter_nodes(_dict(payload)):
        if not isinstance(node, dict):
            continue
        for key, value in node.items():
            if key in FORBIDDEN_TRUE_KEYS and _contaminating_value(value):
                reasons.append(f"{key}_contaminating")
        adjustment = node.get("main_cost_gate_adjustment")
        if _str(adjustment).upper() not in ("", "NONE"):
            reasons.append("main_cost_gate_adjustment_not_none")
    return not reasons, sorted(set(reasons))


def _candidate_from_preview(preview: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(preview)
    side_cell_key = _str(payload.get("side_cell_key"))
    parts = side_cell_key.split("|") if side_cell_key else []
    return {
        "side_cell_key": side_cell_key or None,
        "strategy_name": parts[0] if len(parts) >= 1 else None,
        "symbol": _str(payload.get("symbol")) or (parts[1] if len(parts) >= 2 else None),
        "side": _str(payload.get("side")) or (parts[2] if len(parts) >= 3 else None),
    }


def _sizing_feasibility(
    *,
    symbol: str | None,
    side_cell_key: str | None,
    reference_price: float | None,
    limit_price: float | None,
    qty_step: float | None,
    min_notional: float | None,
    cap_usdt: float | None,
) -> dict[str, Any]:
    usable_price = limit_price if limit_price and limit_price > 0 else reference_price
    min_positive_notional = (
        usable_price * qty_step
        if usable_price and qty_step and usable_price > 0 and qty_step > 0
        else None
    )
    minimum_required = max(
        [value for value in (min_notional, min_positive_notional) if value is not None],
        default=None,
    )
    cap_shortfall = (
        minimum_required - cap_usdt
        if minimum_required is not None and cap_usdt is not None
        else None
    )
    feasible = (
        minimum_required is not None
        and cap_usdt is not None
        and cap_usdt >= minimum_required
    )
    return {
        "symbol": symbol,
        "side_cell_key": side_cell_key,
        "reference_price": _round(reference_price),
        "limit_price": _round(limit_price),
        "qty_step": _round(qty_step),
        "min_notional": _round(min_notional),
        "current_cap_usdt": _round(cap_usdt),
        "min_positive_qty_notional": _round(min_positive_notional, 4),
        "minimum_required_demo_notional_usdt_per_order": _round(minimum_required, 4),
        "cap_shortfall_usdt": _round(cap_shortfall, 4),
        "fits_current_cap": feasible,
    }


def _preview_sizing(preview: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(preview)
    construction = _dict(payload.get("sell_near_touch_construction")) or _dict(
        payload.get("buy_near_touch_construction")
    )
    qty = _dict(payload.get("qty_notional_construction"))
    instrument = _dict(payload.get("instrument_filters"))
    candidate = _candidate_from_preview(payload)
    return _sizing_feasibility(
        symbol=candidate.get("symbol"),
        side_cell_key=candidate.get("side_cell_key"),
        reference_price=_float(construction.get("reference_price")),
        limit_price=_float(construction.get("post_round_limit_price")),
        qty_step=_float(qty.get("qty_step") or instrument.get("qty_step")),
        min_notional=_float(qty.get("min_notional") or instrument.get("min_notional")),
        cap_usdt=_float(qty.get("max_demo_notional_usdt_per_order")),
    )


def _candidate_universe_screen(
    rows: list[Any],
    *,
    default_cap_usdt: float | None,
) -> list[dict[str, Any]]:
    screened: list[dict[str, Any]] = []
    for item in rows:
        row = _dict(item)
        price = _float(
            row.get("limit_price")
            or row.get("reference_price")
            or row.get("last_price")
            or row.get("best_ask")
            or row.get("best_bid")
        )
        sizing = _sizing_feasibility(
            symbol=_str(row.get("symbol")) or None,
            side_cell_key=_str(row.get("side_cell_key")) or None,
            reference_price=price,
            limit_price=_float(row.get("limit_price")) or price,
            qty_step=_float(row.get("qty_step")),
            min_notional=_float(row.get("min_notional")),
            cap_usdt=_float(row.get("cap_usdt")) or default_cap_usdt,
        )
        instrument_status = _str(row.get("instrument_status")) or None
        if instrument_status and instrument_status != "Trading":
            sizing["fits_current_cap"] = False
            sizing["instrument_reject_reason"] = "instrument_status_not_trading"
        sizing.update(
            {
                "strategy_name": _str(row.get("strategy_name")) or None,
                "side": _str(row.get("side")) or None,
                "outcome_horizon_minutes": _round(
                    row.get("outcome_horizon_minutes"), 0
                ),
                "false_negative_rank": _round(row.get("false_negative_rank"), 0),
                "friction_rank": _round(row.get("friction_rank"), 0),
                "friction_adjusted_priority_score": _round(
                    row.get("friction_adjusted_priority_score"), 4
                ),
                "avg_net_bps": _round(row.get("avg_net_bps"), 4),
                "net_positive_pct": _round(row.get("net_positive_pct"), 4),
                "outcome_count": _round(row.get("outcome_count"), 0),
                "spread_bps": _round(row.get("spread_bps"), 4),
                "instrument_status": instrument_status,
            }
        )
        screened.append(sizing)
    return sorted(
        screened,
        key=lambda row: (
            row.get("fits_current_cap") is not True,
            row.get("false_negative_rank") is None,
            row.get("false_negative_rank") or float("inf"),
            row.get("friction_rank") is None,
            row.get("friction_rank") or float("inf"),
            row.get("symbol") or "",
        ),
    )


def _repair_options(
    *,
    preview_sizing: dict[str, Any],
    stale_bbo: bool,
    candidate_screen: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    minimum_required = _float(
        preview_sizing.get("minimum_required_demo_notional_usdt_per_order")
    )
    current_cap = _float(preview_sizing.get("current_cap_usdt"))
    if stale_bbo:
        options.append(
            {
                "option_id": "repair_bbo_freshness_before_order_construction",
                "status": "REQUIRED_BEFORE_ANY_ORDER_ATTEMPT",
                "why": "placement preview BBO age exceeded the max_fresh_bbo_age_ms gate",
                "safe_next_action": "source_or_runtime_read_only_freshness_histogram_and_fail_closed_guard_review",
                "authority_required": "none_for_research; runtime mutation requires PM->E3 review",
            }
        )
    if minimum_required is not None and current_cap is not None and current_cap < minimum_required:
        options.append(
            {
                "option_id": "cap_repair_operator_qc_review_required",
                "status": "REVIEW_REQUIRED_NOT_AUTHORITY",
                "why": (
                    "current max_demo_notional_usdt_per_order is below the "
                    "minimum executable notional implied by qty_step/min_notional"
                ),
                "current_cap_usdt": _round(current_cap, 4),
                "minimum_required_demo_notional_usdt_per_order": _round(
                    minimum_required, 4
                ),
                "safe_next_action": (
                    "operator_qc_review_candidate_scoped_demo_cap_above_minimum_"
                    "executable_notional_without_changing_global_cost_gate"
                ),
                "authority_required": "operator/QC bounded demo risk-cap review",
            }
        )
    feasible = [row for row in candidate_screen if row.get("fits_current_cap") is True]
    options.append(
        {
            "option_id": "lower_price_candidate_reroute_screen",
            "status": "AVAILABLE" if feasible else "DATA_REQUIRED",
            "why": (
                "a lower-price symbol can preserve the existing cap while satisfying "
                "qty_step/min_notional constraints"
            ),
            "feasible_candidate_count": len(feasible),
            "top_feasible_candidates": feasible[:5],
            "safe_next_action": "screen_false_negative_candidates_against_instrument_filters_and_after_cost_edge",
            "authority_required": "none_for_screening; later candidate-specific demo authorization required",
        }
    )
    return options


def _status(
    *,
    artifact: dict[str, Any],
    authority_preserved: bool,
    preview: dict[str, Any] | None,
    preview_sizing: dict[str, Any],
    stale_bbo: bool,
) -> tuple[str, str, list[str]]:
    if authority_preserved is not True:
        return (
            "AUTHORITY_BOUNDARY_VIOLATION",
            "placement_preview_contains_authority_or_mutation_fields",
            ["remove_authority_or_mutation_fields_before_order_construction_review"],
        )
    if (
        artifact.get("status") != "FRESH"
        or artifact.get("schema_version") != PLACEMENT_CONSTRUCTION_PREVIEW_SCHEMA_VERSION
    ):
        return (
            "PLACEMENT_CONSTRUCTION_PREVIEW_REQUIRED",
            "fresh_bounded_probe_no_order_placement_construction_preview_v1_required",
            ["refresh_no_order_placement_construction_preview_before_repair"],
        )
    payload_status = _dict(preview).get("status")
    blocking_reasons = _list(_dict(preview).get("blocking_reasons"))
    cap_fits = preview_sizing.get("fits_current_cap") is True
    if (
        payload_status == "WOULD_SUBMIT_IF_AUTHORIZED_NO_ORDER"
        and cap_fits
        and not stale_bbo
        and not blocking_reasons
    ):
        return (
            "ORDER_CONSTRUCTION_FEASIBLE_NO_AUTHORITY",
            "no_order_construction_fits_current_cap_and_freshness_but_authority_still_required",
            ["continue_to_separate_candidate_scoped_authorization_review_without_order"],
        )
    return (
        "ORDER_CONSTRUCTION_REPAIR_REQUIRED",
        "no_order_construction_failed_or_does_not_fit_current_demo_cap",
        [
            "review_bbo_freshness_repair_before_any_order_attempt",
            "review_cap_repair_or_lower_price_candidate_reroute",
            "do_not_submit_order_until_order_construction_preview_is_feasible",
        ],
    )


def build_bounded_demo_probe_order_construction_repair(
    *,
    placement_preview: dict[str, Any] | None,
    candidate_universe: list[Any] | None = None,
    candidate_universe_artifact: dict[str, Any] | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = 24,
) -> dict[str, Any]:
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    artifact = _artifact_status(
        placement_preview,
        now_utc=now,
        max_age_seconds=max_artifact_age_hours * 3600,
    )
    candidate_artifact = _artifact_status(
        candidate_universe_artifact,
        now_utc=now,
        max_age_seconds=max_artifact_age_hours * 3600,
    )
    candidate_universe_valid = (
        candidate_universe_artifact is None
        or (
            candidate_artifact.get("status") == "FRESH"
            and candidate_artifact.get("schema_version")
            == CANDIDATE_UNIVERSE_SCHEMA_VERSION
        )
    )
    authority_preserved, contamination_reasons = _authority_preserved(placement_preview)
    preview_sizing = _preview_sizing(placement_preview)
    bbo = _dict(_dict(placement_preview).get("runtime_bbo_snapshot"))
    max_fresh_ms = _float(
        _dict(placement_preview).get("placement_repair_limits", {}).get(
            "max_fresh_bbo_age_ms"
        )
    )
    bbo_age_ms = _float(bbo.get("bbo_age_ms"))
    stale_bbo = (
        bbo_age_ms is not None
        and max_fresh_ms is not None
        and bbo_age_ms > max_fresh_ms
    )
    candidate_screen = _candidate_universe_screen(
        _list(candidate_universe) if candidate_universe_valid else [],
        default_cap_usdt=_float(preview_sizing.get("current_cap_usdt")),
    )
    status, reason, next_actions = _status(
        artifact=artifact,
        authority_preserved=authority_preserved,
        preview=placement_preview,
        preview_sizing=preview_sizing,
        stale_bbo=stale_bbo,
    )
    options = _repair_options(
        preview_sizing=preview_sizing,
        stale_bbo=stale_bbo,
        candidate_screen=candidate_screen,
    )
    return {
        "schema_version": ORDER_CONSTRUCTION_REPAIR_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "next_actions": next_actions,
        "candidate": _candidate_from_preview(placement_preview),
        "source_placement_preview": {
            "artifact": artifact,
            "status": _dict(placement_preview).get("status"),
            "blocking_reasons": _list(_dict(placement_preview).get("blocking_reasons")),
            "authority_preserved": authority_preserved,
            "authority_contamination_reasons": contamination_reasons,
        },
        "source_candidate_universe": {
            "artifact": candidate_artifact,
            "valid_for_reroute_screen": candidate_universe_valid,
            "ignored_reason": None
            if candidate_universe_valid
            else "candidate_universe_artifact_missing_stale_or_schema_mismatched",
        },
        "bbo_freshness": {
            "bbo_age_ms": _round(bbo_age_ms),
            "max_fresh_bbo_age_ms": _round(max_fresh_ms),
            "stale_bbo": stale_bbo,
        },
        "sizing_feasibility": preview_sizing,
        "candidate_universe_screen": {
            "input_count": len(_list(candidate_universe)),
            "screened_count": len(candidate_screen),
            "fits_current_cap_count": sum(
                1 for row in candidate_screen if row.get("fits_current_cap") is True
            ),
            "rows": candidate_screen,
        },
        "repair_options": options,
        "answers": {
            "order_construction_feasible_under_current_cap": (
                status == "ORDER_CONSTRUCTION_FEASIBLE_NO_AUTHORITY"
            ),
            "order_construction_repair_required": (
                status == "ORDER_CONSTRUCTION_REPAIR_REQUIRED"
            ),
            "runtime_mutation_performed": False,
            "canonical_plan_mutation_performed": False,
            "ledger_append_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "order_submission_performed": False,
            "writer_enabled": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    sizing = _dict(packet.get("sizing_feasibility"))
    freshness = _dict(packet.get("bbo_freshness"))
    lines = [
        "# Bounded Demo Probe Order Construction Repair",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: {packet.get('reason')}",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- BBO age ms: `{freshness.get('bbo_age_ms')}` / max `{freshness.get('max_fresh_bbo_age_ms')}`",
        f"- Current cap USDT: `{sizing.get('current_cap_usdt')}`",
        f"- Minimum required USDT/order: `{sizing.get('minimum_required_demo_notional_usdt_per_order')}`",
        f"- Fits current cap: `{sizing.get('fits_current_cap')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
    ]
    input_artifacts = _dict(packet.get("input_artifacts"))
    if input_artifacts:
        lines.extend(["## Input Artifacts", ""])
        for name, artifact in input_artifacts.items():
            artifact = _dict(artifact)
            lines.append(
                f"- `{name}`: `{artifact.get('path')}` sha256=`{artifact.get('sha256')}`"
            )
        lines.append("")
    lines.extend(["## Repair Options", ""])
    for option in packet.get("repair_options") or []:
        lines.append(
            f"- `{option.get('option_id')}` / `{option.get('status')}`: "
            f"{option.get('safe_next_action')}"
        )
    lines.extend(["", "## Next Actions", ""])
    for action in packet.get("next_actions") or []:
        lines.append(f"- `{action}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _read_json_any(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_json_list(payload: Any, *, path: Path | None = None) -> list[Any] | None:
    if payload is None:
        return None
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("rows", "candidates", "candidate_universe"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    label = str(path) if path else "payload"
    raise ValueError(f"{label} did not contain a JSON array or rows/candidates list")


def _read_json_list(path: Path | None) -> list[Any] | None:
    return _extract_json_list(_read_json_any(path), path=path)


def _artifact_file_metadata(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "present": False}
    if not path.exists():
        return {"path": str(path), "present": False}
    data = path.read_bytes()
    stat = path.stat()
    return {
        "path": str(path),
        "present": True,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": stat.st_size,
        "mtime_epoch_seconds": int(stat.st_mtime),
    }


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--placement-preview-json", type=Path)
    parser.add_argument("--candidate-universe-json", type=Path)
    parser.add_argument("--max-artifact-age-hours", type=int, default=24)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    placement_preview = _read_json(args.placement_preview_json)
    candidate_universe_payload = _read_json_any(args.candidate_universe_json)
    candidate_universe = _extract_json_list(
        candidate_universe_payload, path=args.candidate_universe_json
    )
    packet = build_bounded_demo_probe_order_construction_repair(
        placement_preview=placement_preview,
        candidate_universe=candidate_universe,
        candidate_universe_artifact=candidate_universe_payload
        if isinstance(candidate_universe_payload, dict)
        else {
            "schema_version": None,
            "generated_at_utc": None,
            "source_payload_type": "bare_array_without_schema_or_freshness",
        }
        if candidate_universe_payload is not None
        else None,
        max_artifact_age_hours=args.max_artifact_age_hours,
    )
    packet["input_artifacts"] = {
        "placement_preview_json": _artifact_file_metadata(args.placement_preview_json),
        "candidate_universe_json": _artifact_file_metadata(
            args.candidate_universe_json
        ),
    }
    markdown = render_markdown(packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    if not args.output and not args.json_output and not args.print_json:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
