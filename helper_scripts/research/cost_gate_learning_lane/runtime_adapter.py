#!/usr/bin/env python3
"""Admission and ledger adapter for the cost-gate demo learning lane.

The policy artifact selects side-cells that may be worth a bounded demo probe.
This module turns that artifact into a deterministic admission decision and an
append-only JSONL ledger contract. It deliberately does not submit orders,
connect to PG, call Bybit, or mutate runtime config. Actual exchange routing
must be wired in the Rust hot path after explicit operator authority exists.
"""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.policy import DEMO_LEARNING_LANE_SCHEMA_VERSION

ADAPTER_SCHEMA_VERSION = "cost_gate_demo_learning_lane_adapter_v1"
ORDER_AUTHORITY_GRANTED = "DEMO_LEARNING_PROBE_GRANTED"
ELIGIBLE_REJECT_REASON_CODE = "cost_gate_js_demo_negative_edge"
ADMIT_DECISION = "ADMIT_DEMO_LEARNING_PROBE"


@dataclass(frozen=True)
class RuntimeAdmissionConfig:
    """Runtime-side guardrails for probe admission decisions."""

    max_plan_age_hours: int = 24
    min_failed_outcomes_to_disable: int = 2
    min_outcome_net_positive_pct: float = 50.0
    min_avg_net_bps: float = 0.0


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


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


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def side_cell_key(strategy_name: Any, symbol: Any, side: Any) -> str:
    return "|".join([_str(strategy_name), _str(symbol).upper(), _str(side)])


def normalize_reject_reason_code(value: Any) -> str:
    text = _str(value)
    lowered = text.lower()
    if lowered == ELIGIBLE_REJECT_REASON_CODE:
        return ELIGIBLE_REJECT_REASON_CODE
    if "cost_gate(js-demo)" in lowered and "negative" in lowered:
        return ELIGIBLE_REJECT_REASON_CODE
    if "cost_gate" in lowered and "js-demo" in lowered and "negative" in lowered:
        return ELIGIBLE_REJECT_REASON_CODE
    return lowered


def validate_runtime_config(cfg: RuntimeAdmissionConfig) -> None:
    if cfg.max_plan_age_hours < 1 or cfg.max_plan_age_hours > 24 * 14:
        raise ValueError("--max-plan-age-hours must be in [1, 336]")
    if cfg.min_failed_outcomes_to_disable < 1 or cfg.min_failed_outcomes_to_disable > 20:
        raise ValueError("--min-failed-outcomes-to-disable must be in [1, 20]")
    if cfg.min_outcome_net_positive_pct < 0.0 or cfg.min_outcome_net_positive_pct > 100.0:
        raise ValueError("--min-outcome-net-positive-pct must be in [0, 100]")
    if cfg.min_avg_net_bps < -10_000.0 or cfg.min_avg_net_bps > 10_000.0:
        raise ValueError("--min-avg-net-bps must be in [-10000, 10000]")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def read_jsonl_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed JSONL ledger at {path}:{line_no}") from exc
        if isinstance(row, dict):
            rows.append(row)
    return rows


def append_jsonl_ledger(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")


def _candidate_by_side_cell(plan: dict[str, Any], key: str) -> dict[str, Any] | None:
    for row in _list(plan.get("probe_candidates")):
        if isinstance(row, dict) and _str(row.get("side_cell_key")) == key:
            return row
    return None


def _event_to_side_cell(event: dict[str, Any]) -> str:
    return side_cell_key(
        event.get("strategy_name") or event.get("strategy"),
        event.get("symbol"),
        event.get("side"),
    )


def _ledger_side_cell(row: dict[str, Any]) -> str:
    if row.get("side_cell_key"):
        return _str(row.get("side_cell_key"))
    event = _dict(row.get("event"))
    if event:
        return _event_to_side_cell(event)
    return side_cell_key(row.get("strategy_name"), row.get("symbol"), row.get("side"))


def _row_decision(row: dict[str, Any]) -> str:
    if row.get("decision"):
        return _str(row.get("decision"))
    decision = _dict(row.get("admission_decision"))
    return _str(decision.get("decision"))


def _row_ts_ms(row: dict[str, Any]) -> int:
    for key in ("ts_ms", "attempt_ts_ms", "generated_at_ms"):
        value = _int(row.get(key), default=0)
        if value > 0:
            return value
    event = _dict(row.get("event"))
    return _int(event.get("ts_ms"), default=0)


def _candidate_max_orders(candidate: dict[str, Any]) -> int:
    return max(0, _int(_dict(candidate.get("probe_proposal")).get("max_probe_orders")))


def _candidate_cooldown_ms(candidate: dict[str, Any]) -> int:
    minutes = max(0, _int(_dict(candidate.get("probe_proposal")).get("cooldown_minutes")))
    return minutes * 60_000


def _valid_candidate_guardrails(candidate: dict[str, Any]) -> tuple[bool, str | None]:
    proposal = _dict(candidate.get("probe_proposal"))
    guardrails = _dict(candidate.get("guardrails"))
    if proposal.get("mode") != "demo_only_learning_probe":
        return False, "candidate_probe_mode_not_demo_only"
    if _candidate_max_orders(candidate) <= 0:
        return False, "candidate_probe_budget_not_positive"
    if proposal.get("requires_runtime_policy_adapter") is not True:
        return False, "candidate_missing_runtime_adapter_requirement"
    if proposal.get("requires_probe_attempt_logging") is not True:
        return False, "candidate_missing_attempt_logging_requirement"
    if proposal.get("requires_probe_outcome_logging") is not True:
        return False, "candidate_missing_outcome_logging_requirement"
    if guardrails.get("main_cost_gate_adjustment") != "NONE":
        return False, "candidate_main_cost_gate_adjustment_not_none"
    if guardrails.get("may_bypass_main_live_gate") is not False:
        return False, "candidate_live_bypass_guardrail_invalid"
    if guardrails.get("demo_only") is not True:
        return False, "candidate_demo_only_guardrail_missing"
    if guardrails.get("notional_or_qty_not_granted_by_artifact") is not True:
        return False, "candidate_qty_authority_guardrail_missing"
    return True, None


def summarize_side_cell_runtime_state(
    candidate: dict[str, Any],
    ledger_rows: list[dict[str, Any]],
    *,
    now_ms: int,
    cfg: RuntimeAdmissionConfig | None = None,
) -> dict[str, Any]:
    """Summarize attempts/outcomes and derive auto-disable state."""
    cfg = cfg or RuntimeAdmissionConfig()
    validate_runtime_config(cfg)
    key = _str(candidate.get("side_cell_key"))
    max_orders = _candidate_max_orders(candidate)
    cooldown_ms = _candidate_cooldown_ms(candidate)

    matching = [row for row in ledger_rows if _ledger_side_cell(row) == key]
    admitted = [row for row in matching if _row_decision(row) == ADMIT_DECISION]
    admitted_count = len(admitted)
    remaining = max(0, max_orders - admitted_count)
    attempt_ts = [_row_ts_ms(row) for row in admitted if _row_ts_ms(row) > 0]
    latest_attempt_ts_ms = max(attempt_ts) if attempt_ts else None
    cooldown_until = (
        latest_attempt_ts_ms + cooldown_ms
        if latest_attempt_ts_ms is not None and cooldown_ms > 0
        else None
    )
    cooldown_active = cooldown_until is not None and now_ms < cooldown_until

    completed_outcomes = [
        row for row in matching
        if _str(row.get("record_type")) == "probe_outcome"
        and _float(row.get("realized_net_bps")) is not None
    ]
    realized = [_float(row.get("realized_net_bps")) for row in completed_outcomes]
    realized_bps = [value for value in realized if value is not None]
    outcome_count = len(realized_bps)
    avg_net = sum(realized_bps) / outcome_count if outcome_count else None
    net_positive_pct = (
        100.0 * sum(1 for value in realized_bps if value > 0.0) / outcome_count
        if outcome_count
        else None
    )

    manual_disable = next(
        (
            row for row in matching
            if _str(row.get("record_type")) == "side_cell_disabled"
        ),
        None,
    )
    disable_reason = None
    if manual_disable is not None:
        disable_reason = _str(manual_disable.get("disable_reason")) or "manual_disable"
    elif remaining <= 0:
        disable_reason = "probe_budget_exhausted"
    elif (
        outcome_count >= cfg.min_failed_outcomes_to_disable
        and (
            (avg_net is not None and avg_net < cfg.min_avg_net_bps)
            or (
                net_positive_pct is not None
                and net_positive_pct < cfg.min_outcome_net_positive_pct
            )
        )
    ):
        disable_reason = "realized_probe_outcomes_fail_learning_threshold"

    return {
        "side_cell_key": key,
        "max_probe_orders": max_orders,
        "admitted_attempt_count": admitted_count,
        "remaining_probe_orders": remaining,
        "latest_probe_attempt_ts_ms": latest_attempt_ts_ms,
        "cooldown_ms": cooldown_ms,
        "cooldown_until_ts_ms": cooldown_until,
        "cooldown_active": cooldown_active,
        "completed_outcome_count": outcome_count,
        "avg_realized_net_bps": avg_net,
        "net_positive_pct": net_positive_pct,
        "disabled": disable_reason is not None,
        "disable_reason": disable_reason,
    }


def _decision(
    decision: str,
    *,
    reason: str,
    now_utc: dt.datetime,
    event: dict[str, Any],
    side_cell_key_value: str | None = None,
    runtime_state: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    allowed = decision == ADMIT_DECISION
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "generated_at_utc": now_utc.isoformat(),
        "decision": decision,
        "reason": reason,
        "allowed_to_submit_order": allowed,
        "no_order_authority": not allowed,
        "side_cell_key": side_cell_key_value,
        "event": event,
        "runtime_state": runtime_state or {},
        "plan_summary": {
            "schema_version": (plan or {}).get("schema_version"),
            "status": (plan or {}).get("status"),
            "gate_status": (plan or {}).get("gate_status"),
            "main_cost_gate_adjustment": (plan or {}).get("main_cost_gate_adjustment"),
            "learning_gate_adjustment": (plan or {}).get("learning_gate_adjustment"),
            "order_authority": (plan or {}).get("order_authority"),
            "selected_probe_candidate_count": (plan or {}).get("selected_probe_candidate_count"),
        },
        "boundary": (
            "admission-ledger artifact only; no PG, Bybit, order, config, risk, "
            "auth, or runtime mutation"
        ),
    }


def evaluate_probe_admission(
    plan: dict[str, Any],
    reject_event: dict[str, Any],
    *,
    ledger_rows: list[dict[str, Any]] | None = None,
    now_utc: dt.datetime | None = None,
    cfg: RuntimeAdmissionConfig | None = None,
    adapter_enabled: bool = False,
    risk_state: str = "NORMAL",
) -> dict[str, Any]:
    """Return a fail-closed admission decision for one rejected demo signal."""
    cfg = cfg or RuntimeAdmissionConfig()
    validate_runtime_config(cfg)
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    rows = ledger_rows or []

    normalized_event = dict(reject_event)
    normalized_event["side_cell_key"] = _event_to_side_cell(reject_event)
    normalized_event["reject_reason_code"] = normalize_reject_reason_code(
        reject_event.get("reject_reason_code") or reject_event.get("rejected_reason")
    )
    if _int(normalized_event.get("ts_ms")) <= 0:
        normalized_event["ts_ms"] = now_ms

    key = normalized_event["side_cell_key"]
    if plan.get("schema_version") != DEMO_LEARNING_LANE_SCHEMA_VERSION:
        return _decision(
            "PLAN_SCHEMA_MISMATCH",
            reason="plan_schema_version_is_not_cost_gate_demo_learning_lane_plan_v1",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            plan=plan,
        )
    if plan.get("status") != "READY_FOR_DEMO_LEARNING_PROBE":
        return _decision(
            "PLAN_NOT_READY",
            reason="plan_status_is_not_ready_for_demo_learning_probe",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            plan=plan,
        )
    plan_age = _age_seconds(plan.get("generated_at_utc"), now_utc=now)
    if plan_age is None or plan_age > cfg.max_plan_age_hours * 3600:
        return _decision(
            "PLAN_STALE_OR_MISSING_GENERATED_AT",
            reason="plan_generated_at_missing_or_too_old",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            plan=plan,
        )
    if plan.get("main_cost_gate_adjustment") != "NONE":
        return _decision(
            "MAIN_COST_GATE_ADJUSTMENT_NOT_ALLOWED",
            reason="demo_learning_lane_must_not_lower_main_cost_gate",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            plan=plan,
        )

    if _str(normalized_event.get("engine_mode")).lower() not in {"demo", "live_demo"}:
        return _decision(
            "NON_DEMO_ENGINE_MODE",
            reason="learning_probe_admission_is_demo_only",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            plan=plan,
        )
    if normalized_event["reject_reason_code"] != ELIGIBLE_REJECT_REASON_CODE:
        return _decision(
            "REJECT_REASON_NOT_ELIGIBLE",
            reason="only_cost_gate_js_demo_negative_edge_rejections_are_probe_eligible",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            plan=plan,
        )
    candidate = _candidate_by_side_cell(plan, key)
    if candidate is None:
        return _decision(
            "SIDE_CELL_NOT_SELECTED",
            reason="rejected_signal_side_cell_is_not_in_selected_probe_candidates",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            plan=plan,
        )

    valid_candidate, invalid_reason = _valid_candidate_guardrails(candidate)
    runtime_state = summarize_side_cell_runtime_state(
        candidate,
        rows,
        now_ms=now_ms,
        cfg=cfg,
    )
    if not valid_candidate:
        return _decision(
            "CANDIDATE_GUARDRAIL_INVALID",
            reason=invalid_reason or "candidate_guardrail_invalid",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            runtime_state=runtime_state,
            plan=plan,
        )
    if runtime_state["disabled"]:
        return _decision(
            runtime_state["disable_reason"].upper(),
            reason=runtime_state["disable_reason"],
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            runtime_state=runtime_state,
            plan=plan,
        )
    if runtime_state["cooldown_active"]:
        return _decision(
            "COOLDOWN_ACTIVE",
            reason="side_cell_probe_cooldown_active",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            runtime_state=runtime_state,
            plan=plan,
        )
    if _str(risk_state).upper() != "NORMAL":
        return _decision(
            "RISK_STATE_NOT_NORMAL",
            reason="session_halt_or_guardian_risk_state_not_normal",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            runtime_state=runtime_state,
            plan=plan,
        )
    if plan.get("order_authority") != ORDER_AUTHORITY_GRANTED:
        return _decision(
            "ORDER_AUTHORITY_NOT_GRANTED",
            reason="plan_matches_candidate_but_artifact_has_no_order_authority",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            runtime_state=runtime_state,
            plan=plan,
        )
    if not adapter_enabled:
        return _decision(
            "ADAPTER_DISABLED",
            reason="runtime_adapter_enable_flag_is_false",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            runtime_state=runtime_state,
            plan=plan,
        )

    return _decision(
        ADMIT_DECISION,
        reason="selected_side_cell_with_budget_cooldown_clear_and_explicit_demo_probe_authority",
        now_utc=now,
        event=normalized_event,
        side_cell_key_value=key,
        runtime_state=runtime_state,
        plan=plan,
    )


def build_ledger_record(decision: dict[str, Any], *, record_type: str = "probe_admission_decision") -> dict[str, Any]:
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "record_type": record_type,
        "generated_at_utc": decision["generated_at_utc"],
        "decision": decision["decision"],
        "allowed_to_submit_order": decision["allowed_to_submit_order"],
        "side_cell_key": decision.get("side_cell_key"),
        "event": decision.get("event") or {},
        "runtime_state": decision.get("runtime_state") or {},
        "reason": decision.get("reason"),
        "boundary": decision.get("boundary"),
    }


def _default_plan_path() -> Path:
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return data_dir / "cost_gate_learning_lane" / "demo_learning_lane_plan_latest.json"


def _default_ledger_path() -> Path:
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return data_dir / "cost_gate_learning_lane" / "probe_ledger.jsonl"


def _event_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.event_json:
        return _read_json(args.event_json)
    required = {
        "--strategy": args.strategy,
        "--symbol": args.symbol,
        "--side": args.side,
        "--reject-reason-code": args.reject_reason_code,
        "--engine-mode": args.engine_mode,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(f"missing required event args without --event-json: {', '.join(missing)}")
    return {
        "strategy_name": args.strategy,
        "symbol": args.symbol,
        "side": args.side,
        "reject_reason_code": args.reject_reason_code,
        "engine_mode": args.engine_mode,
        "ts_ms": args.ts_ms,
        "context_id": args.context_id,
        "signal_id": args.signal_id,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=_default_plan_path())
    parser.add_argument("--ledger", type=Path, default=_default_ledger_path())
    parser.add_argument("--event-json", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--record-decision", action="store_true")
    parser.add_argument("--adapter-enabled", action="store_true")
    parser.add_argument("--risk-state", default="NORMAL")
    parser.add_argument("--strategy")
    parser.add_argument("--symbol")
    parser.add_argument("--side")
    parser.add_argument("--reject-reason-code")
    parser.add_argument("--engine-mode")
    parser.add_argument("--ts-ms", type=int)
    parser.add_argument("--context-id")
    parser.add_argument("--signal-id")
    parser.add_argument("--max-plan-age-hours", type=int, default=24)
    parser.add_argument("--min-failed-outcomes-to-disable", type=int, default=2)
    parser.add_argument("--min-outcome-net-positive-pct", type=float, default=50.0)
    parser.add_argument("--min-avg-net-bps", type=float, default=0.0)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    cfg = RuntimeAdmissionConfig(
        max_plan_age_hours=args.max_plan_age_hours,
        min_failed_outcomes_to_disable=args.min_failed_outcomes_to_disable,
        min_outcome_net_positive_pct=args.min_outcome_net_positive_pct,
        min_avg_net_bps=args.min_avg_net_bps,
    )
    validate_runtime_config(cfg)
    plan = _read_json(args.plan)
    event = _event_from_args(args)
    ledger = read_jsonl_ledger(args.ledger)
    decision = evaluate_probe_admission(
        plan,
        event,
        ledger_rows=ledger,
        cfg=cfg,
        adapter_enabled=args.adapter_enabled,
        risk_state=args.risk_state,
    )
    if args.record_decision:
        append_jsonl_ledger(args.ledger, build_ledger_record(decision))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
    if args.print_json or not args.output:
        print(json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
