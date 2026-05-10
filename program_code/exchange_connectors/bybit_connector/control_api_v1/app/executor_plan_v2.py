"""Executor V2 deterministic ExecutionPlan builder.

MAG-061 keeps ExecutionPlan generation as a typed helper. It consumes an
approved or modified StrategistDecision + GuardianVerdict lineage and produces
an execution-quality plan only; it does not submit orders or bind Decision
Lease.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .agent_contracts import (
    ExecutionMakerPreference,
    ExecutionOrderStyle,
    ExecutionPlan,
    ExecutionUrgency,
    GuardianP2Modification,
    GuardianVerdict,
    StrategistDecision,
)


_EXECUTABLE_ACTIONS = {"open", "reduce", "close"}
_EXIT_ACTIONS = {"reduce", "close"}
_ENTRY_DIRECTIONS = {"long", "short"}
_EXIT_DIRECTIONS = {"close_long", "close_short"}
_URGENCY_ORDER = {"low": 0, "normal": 1, "high": 2, "urgent": 3}
_CANONICAL_STRATEGIES = {
    "ma_crossover",
    "grid_trading",
    "bb_reversion",
    "bb_breakout",
    "funding_arb",
}


@dataclass(frozen=True)
class ExecutorPlanConfig:
    default_max_slippage_bps: float = 10.0
    exit_max_slippage_bps: float = 25.0
    default_lease_ttl_ms: int = 30_000
    entry_lease_scope: str = "TRADE_ENTRY"
    exit_lease_scope: str = "TRADE_EXIT"
    default_urgency: ExecutionUrgency = "normal"
    exit_urgency: ExecutionUrgency = "high"
    price_maker_preference: ExecutionMakerPreference = "maker_only"
    market_entry_maker_preference: ExecutionMakerPreference = "allow_taker"
    exit_maker_preference: ExecutionMakerPreference = "none"


def build_execution_plan(
    decision: StrategistDecision,
    verdict: GuardianVerdict,
    *,
    ts_ms: int | None = None,
    order_plan_id: str | None = None,
    idempotency_key: str | None = None,
    config: ExecutorPlanConfig | None = None,
) -> ExecutionPlan:
    """Build a deterministic MAG-061 ExecutionPlan from approved lineage."""

    cfg = config or ExecutorPlanConfig()
    _validate_lineage(decision, verdict)

    qty = _positive_float(decision.proposed_qty, "strategist_proposed_qty_required")
    applied_modifications: list[dict[str, Any]] = []
    local_stop_policy: dict[str, Any] = {}
    order_style_params: dict[str, Any] = {}
    metadata_policies: dict[str, Any] = {}

    for modification in verdict.p2_modifications:
        applied = _apply_p2_modification(
            modification=modification,
            current_qty=qty,
            local_stop_policy=local_stop_policy,
            order_style_params=order_style_params,
            metadata_policies=metadata_policies,
        )
        qty = applied["qty"]
        applied_modifications.append(applied["record"])

    action = decision.decision_action
    reduce_only = action in _EXIT_ACTIONS
    order_shape = _order_shape(decision, reduce_only)
    urgency = _urgency(decision, reduce_only, cfg)
    max_slippage_bps = _max_slippage_bps(decision, reduce_only, cfg)
    lease_scope = cfg.exit_lease_scope if reduce_only else cfg.entry_lease_scope
    generated_ts_ms = ts_ms if ts_ms is not None else max(decision.ts_ms, verdict.ts_ms)

    generated_order_plan_id = order_plan_id or _order_plan_id(
        decision,
        verdict,
        qty,
        order_shape["order_style"],
        order_shape.get("limit_price"),
    )
    generated_idempotency_key = idempotency_key or (
        f"execution_plan:{decision.engine_mode}:{generated_order_plan_id}"
    )

    metadata = {
        "mag": "061",
        "builder": "executor_plan_v2",
        "execution_plan_model": "v1",
        "decision_action": action,
        "decision_ts_ms": decision.ts_ms,
        "verdict_ts_ms": verdict.ts_ms,
        "guardian_risk_level": verdict.risk_level,
        "guardian_reasons": list(verdict.reasons),
        "guardian_p2_modifications": [
            item.model_dump(mode="json") for item in verdict.p2_modifications
        ],
        "applied_p2_modifications": applied_modifications,
        "decision_metadata": dict(decision.metadata),
        "strategy_signal_id": decision.signal_id,
        "selected_candidate_id": decision.selected_candidate_id,
        "expected_net_edge_bps": decision.expected_net_edge_bps,
        **metadata_policies,
    }

    return ExecutionPlan(
        order_plan_id=generated_order_plan_id,
        decision_id=decision.decision_id,
        verdict_id=verdict.verdict_id,
        verdict_version=verdict.verdict_version,
        ts_ms=generated_ts_ms,
        engine_mode=decision.engine_mode,
        symbol=decision.symbol,
        strategy=decision.strategy,
        direction=decision.direction,
        symbol_source="strategist_decision",
        direction_source="strategist_decision",
        qty=qty,
        reduce_only=reduce_only,
        order_style=order_shape["order_style"],
        urgency=urgency,
        max_slippage_bps=max_slippage_bps,
        maker_preference=_maker_preference(order_shape["order_style"], reduce_only, cfg),
        order_type=order_shape["order_type"],
        limit_price=order_shape.get("limit_price"),
        time_in_force=order_shape.get("time_in_force"),
        order_style_params=order_style_params,
        local_stop_policy=local_stop_policy,
        anti_hunt_stop_policy={},
        lease_scope=lease_scope,
        lease_ttl_ms=cfg.default_lease_ttl_ms,
        lease_id=None,
        idempotency_key=generated_idempotency_key,
        metadata=metadata,
    )


def execution_plan_from_approved_intent_payload(
    payload: dict[str, Any],
    *,
    ts_ms: int | None = None,
    order_plan_id: str | None = None,
) -> ExecutionPlan:
    """Adapt legacy APPROVED_INTENT payloads into the typed ExecutionPlan seam."""

    if not isinstance(payload, dict) or not payload:
        raise ValueError("approved_intent_payload_required")
    explicit_plan = payload.get("execution_plan")
    if isinstance(explicit_plan, ExecutionPlan):
        return explicit_plan
    if isinstance(explicit_plan, dict):
        return ExecutionPlan(**explicit_plan)

    metadata = _dict_or_empty(payload.get("metadata"))
    params = _dict_or_empty(payload.get("params"))
    intent_id = str(payload.get("intent_id") or payload.get("decision_id") or "").strip()
    if not intent_id:
        raise ValueError("approved_intent_intent_id_required")

    generated_ts_ms = int(ts_ms or payload.get("timestamp_ms") or metadata.get("ts_ms") or 0)
    if generated_ts_ms <= 0:
        import time

        generated_ts_ms = int(time.time() * 1000)

    strategy = str(payload.get("strategy") or metadata.get("strategy") or "agent_executor")
    direction = str(payload.get("direction") or "").strip().lower()
    decision_action = str(payload.get("decision_action") or metadata.get("decision_action") or "open")
    if decision_action in _EXIT_ACTIONS and direction in {"long", "short"}:
        direction = "close_long" if direction == "long" else "close_short"

    proposed_price = (
        payload.get("price")
        if payload.get("price") is not None
        else payload.get("limit_price", params.get("limit_price"))
    )
    decision = StrategistDecision(
        decision_id=str(payload.get("decision_id") or f"decision:{intent_id}"),
        signal_id=str(payload.get("signal_id") or metadata.get("signal_id") or f"signal:{intent_id}"),
        ts_ms=generated_ts_ms,
        engine_mode=str(payload.get("engine_mode") or metadata.get("engine_mode") or "paper"),
        symbol=str(payload.get("symbol") or ""),
        strategy=strategy,
        direction=direction,
        confidence=float(payload.get("confidence", metadata.get("confidence", 0.0)) or 0.0),
        decision_action=decision_action,
        selected_strategy=strategy if strategy in _CANONICAL_STRATEGIES else None,
        expected_net_edge_bps=_optional_float(
            payload.get("expected_net_edge_bps", metadata.get("expected_net_edge_bps"))
        ),
        proposed_qty=_positive_float(payload.get("size"), "approved_intent_size_required"),
        proposed_price=_optional_float(proposed_price),
        rationale=str(payload.get("thesis") or metadata.get("rationale") or ""),
        evidence_refs=list(payload.get("evidence_refs") or metadata.get("evidence_refs") or []),
        metadata={
            "source_message_type": "approved_intent",
            "legacy_intent_id": intent_id,
            **metadata,
        },
    )
    verdict = GuardianVerdict(
        verdict_id=str(payload.get("verdict_id") or metadata.get("verdict_id") or f"verdict:{intent_id}:approved"),
        decision_id=decision.decision_id,
        verdict_version=int(payload.get("verdict_version", metadata.get("verdict_version", 1)) or 1),
        ts_ms=int(payload.get("verdict_ts_ms", metadata.get("verdict_ts_ms", generated_ts_ms)) or generated_ts_ms),
        engine_mode=decision.engine_mode,
        symbol=decision.symbol,
        strategy=decision.strategy,
        allow=True,
        risk_level=str(payload.get("risk_level") or metadata.get("risk_level") or "low"),
        reasons=list(payload.get("guardian_reasons") or metadata.get("guardian_reasons") or ["approved_intent_adapter"]),
        p2_modifications=[
            item if isinstance(item, GuardianP2Modification) else GuardianP2Modification(**item)
            for item in list(payload.get("p2_modifications") or metadata.get("p2_modifications") or [])
        ],
        metadata={"source_message_type": "approved_intent", **metadata},
    )
    return build_execution_plan(
        decision,
        verdict,
        ts_ms=generated_ts_ms,
        order_plan_id=order_plan_id,
    )


def acquire_execution_plan_lease(
    plan: ExecutionPlan,
    governance_hub: Any,
) -> ExecutionPlan:
    """Acquire and bind a Decision Lease for an ExecutionPlan."""

    if plan.lease_id:
        return plan
    if governance_hub is None or not hasattr(governance_hub, "acquire_lease"):
        raise ValueError("execution_plan_real_submit_requires_governance_hub")
    if not plan.lease_scope or plan.lease_ttl_ms is None:
        raise ValueError("execution_plan_lease_request_required")

    ttl_seconds = plan.lease_ttl_ms / 1000.0
    lease_id = governance_hub.acquire_lease(
        intent_id=plan.order_plan_id,
        scope=plan.lease_scope,
        ttl_seconds=ttl_seconds,
    )
    if not lease_id:
        raise ValueError("execution_plan_lease_acquisition_failed")

    return _copy_plan_with_lease(
        plan,
        lease_id=str(lease_id),
        lease_binding={
            "source": "governance_hub",
            "intent_id": plan.order_plan_id,
            "lease_scope": plan.lease_scope,
            "lease_ttl_ms": plan.lease_ttl_ms,
            "ttl_seconds": ttl_seconds,
        },
    )


def prepare_execution_plan_for_submit(
    plan: ExecutionPlan,
    *,
    real_submit: bool,
    governance_hub: Any | None = None,
) -> ExecutionPlan:
    """Return a submit-ready plan, fail-closed for real submit without lease."""

    if not real_submit:
        return plan
    bound_plan = plan if plan.lease_id else acquire_execution_plan_lease(plan, governance_hub)
    require_execution_plan_lease_for_submit(bound_plan, real_submit=real_submit)
    return bound_plan


def require_execution_plan_lease_for_submit(
    plan: ExecutionPlan,
    *,
    real_submit: bool,
) -> None:
    """Assert the MAG-062 lease invariant before any real submit."""

    if real_submit and not plan.lease_id:
        raise ValueError("execution_plan_real_submit_requires_lease_id")


def _validate_lineage(decision: StrategistDecision, verdict: GuardianVerdict) -> None:
    if not verdict.allow:
        raise ValueError("guardian_verdict_rejects_execution_plan")
    if verdict.decision_id != decision.decision_id:
        raise ValueError("guardian_verdict_decision_id_mismatch")
    for field in ("engine_mode", "symbol", "strategy"):
        if getattr(verdict, field) != getattr(decision, field):
            raise ValueError(f"guardian_verdict_{field}_mismatch")
    if decision.decision_action not in _EXECUTABLE_ACTIONS:
        raise ValueError("execution_plan_for_non_trading_decision")

    if decision.decision_action == "open" and decision.direction not in _ENTRY_DIRECTIONS:
        raise ValueError("open_decision_requires_entry_direction_from_strategist")
    if decision.decision_action in _EXIT_ACTIONS and decision.direction not in _EXIT_DIRECTIONS:
        raise ValueError("exit_decision_requires_close_direction_from_strategist")


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _apply_p2_modification(
    *,
    modification: GuardianP2Modification,
    current_qty: float,
    local_stop_policy: dict[str, Any],
    order_style_params: dict[str, Any],
    metadata_policies: dict[str, Any],
) -> dict[str, Any]:
    qty = current_qty
    record = {
        "field": modification.field,
        "action": modification.action,
        "reason_code": modification.reason_code,
        "reason": modification.reason,
        "original_value": modification.original_value,
        "modified_value": modification.modified_value,
        "unit": modification.unit,
        "evidence_refs": list(modification.evidence_refs),
    }

    if modification.field == "size":
        modified_qty = _positive_float(
            modification.modified_value,
            "guardian_p2_size_modification_invalid",
        )
        qty = min(current_qty, modified_qty)
        record["applied_qty"] = qty
    elif modification.field == "stop":
        local_stop_policy.update(
            {
                "source": "guardian_p2",
                "action": modification.action,
                "value": modification.modified_value,
                "unit": modification.unit,
                "reason_code": modification.reason_code,
                "reason": modification.reason,
                "evidence_refs": list(modification.evidence_refs),
            }
        )
    elif modification.field == "cooldown":
        order_style_params.setdefault("cooldown_policy", {})
        order_style_params["cooldown_policy"].update(
            {
                "source": "guardian_p2",
                "action": modification.action,
                "value": modification.modified_value,
                "unit": modification.unit,
                "reason_code": modification.reason_code,
                "cooldown_until_ms": modification.metadata.get("cooldown_until_ms"),
            }
        )
    elif modification.field == "leverage":
        metadata_policies["guardian_leverage_policy"] = {
            "source": "guardian_p2",
            "action": modification.action,
            "value": modification.modified_value,
            "unit": modification.unit,
            "reason_code": modification.reason_code,
        }

    return {"qty": qty, "record": record}


def _order_shape(decision: StrategistDecision, reduce_only: bool) -> dict[str, Any]:
    if reduce_only:
        return {
            "order_style": "market",
            "order_type": "market",
        }

    if decision.proposed_price is not None:
        limit_price = _positive_float(
            decision.proposed_price,
            "strategist_proposed_price_must_be_positive",
        )
        return {
            "order_style": "post_only",
            "order_type": "limit",
            "limit_price": limit_price,
            "time_in_force": "PostOnly",
        }

    return {
        "order_style": "market",
        "order_type": "market",
    }


def _maker_preference(
    order_style: ExecutionOrderStyle,
    reduce_only: bool,
    config: ExecutorPlanConfig,
) -> ExecutionMakerPreference:
    if reduce_only:
        return config.exit_maker_preference
    if order_style == "post_only":
        return config.price_maker_preference
    return config.market_entry_maker_preference


def _urgency(
    decision: StrategistDecision,
    reduce_only: bool,
    config: ExecutorPlanConfig,
) -> ExecutionUrgency:
    metadata_urgency = decision.metadata.get("urgency")
    if isinstance(metadata_urgency, str) and metadata_urgency in _URGENCY_ORDER:
        urgency = metadata_urgency
    else:
        urgency = config.default_urgency
    if reduce_only and _URGENCY_ORDER[urgency] < _URGENCY_ORDER[config.exit_urgency]:
        return config.exit_urgency
    return urgency  # type: ignore[return-value]


def _max_slippage_bps(
    decision: StrategistDecision,
    reduce_only: bool,
    config: ExecutorPlanConfig,
) -> float:
    metadata_slippage = decision.metadata.get("max_slippage_bps")
    if metadata_slippage is not None:
        value = _positive_or_zero_float(
            metadata_slippage,
            "metadata_max_slippage_bps_invalid",
        )
        if reduce_only:
            return max(value, config.exit_max_slippage_bps)
        return value
    return config.exit_max_slippage_bps if reduce_only else config.default_max_slippage_bps


def _order_plan_id(
    decision: StrategistDecision,
    verdict: GuardianVerdict,
    qty: float,
    order_style: str,
    limit_price: float | None,
) -> str:
    digest = _digest(
        [
            decision.engine_mode,
            decision.decision_id,
            verdict.verdict_id,
            str(verdict.verdict_version),
            decision.symbol,
            decision.direction,
            decision.strategy,
            decision.decision_action,
            f"{qty:.12g}",
            order_style,
            "" if limit_price is None else f"{limit_price:.12g}",
        ]
    )
    return f"exec-plan-{decision.engine_mode}-{decision.symbol}-{digest}"


def _digest(parts: list[str]) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8", errors="replace"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def _copy_plan_with_lease(
    plan: ExecutionPlan,
    *,
    lease_id: str,
    lease_binding: dict[str, Any],
) -> ExecutionPlan:
    payload = plan.model_dump(mode="json")
    metadata = dict(payload.get("metadata") or {})
    metadata["lease_binding"] = lease_binding
    payload["metadata"] = metadata
    payload["lease_id"] = lease_id
    return ExecutionPlan(**payload)


def _positive_float(value: Any, error_code: str) -> float:
    parsed = _as_float(value)
    if parsed is None or parsed <= 0.0:
        raise ValueError(error_code)
    return parsed


def _positive_or_zero_float(value: Any, error_code: str) -> float:
    parsed = _as_float(value)
    if parsed is None or parsed < 0.0:
        raise ValueError(error_code)
    return parsed


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
