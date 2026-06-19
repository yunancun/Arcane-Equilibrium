"""Read-only multi-arm discovery loop planner."""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import DISCOVERY_LOOP_SCHEMA_VERSION, RUNNER_VERSION

READY_FOR_AEG_CHAIN = "READY_FOR_AEG_CHAIN"
READY_FOR_PROBE = "READY_FOR_PROBE"
RUN_READ_ONLY_CAPTURE = "RUN_READ_ONLY_CAPTURE"
WAIT = "WAIT"
BLOCK = "BLOCK"

_PRIORITY = {
    READY_FOR_AEG_CHAIN: 0,
    READY_FOR_PROBE: 1,
    RUN_READ_ONLY_CAPTURE: 2,
    WAIT: 3,
    BLOCK: 4,
}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def decide_arm_action(arm: dict[str, Any], *, min_samples: int = 30) -> dict[str, Any]:
    """單 discovery arm 的 deterministic action。"""
    name = str(arm.get("arm_id") or arm.get("name") or "unknown")
    gate_status = str(arm.get("gate_status") or arm.get("status") or "").upper()
    sample_count = _int(arm.get("sample_count"))
    artifacts_ready = bool(arm.get("artifacts_ready"))
    source_ok = arm.get("source_ok", True) is not False
    reason = "default_wait"
    action = WAIT

    if not source_ok or gate_status in {"SOURCE_FAILURE", "ERROR", "FAILED"}:
        action, reason = BLOCK, "source_not_healthy"
    elif gate_status in {"WATCH_ONLY", "NO_CANDIDATE", "WAIT"}:
        action, reason = WAIT, f"gate_status:{gate_status.lower()}"
    elif artifacts_ready and sample_count >= min_samples:
        action, reason = READY_FOR_AEG_CHAIN, "artifacts_ready_and_sample_gate_met"
    elif gate_status in {"ACTIONABLE_START_NOW", "ACTIONABLE_SCHEDULE", "OPERATOR_REVIEW"}:
        action, reason = READY_FOR_PROBE, f"gate_status:{gate_status.lower()}"
    elif sample_count < min_samples:
        action, reason = RUN_READ_ONLY_CAPTURE, "sample_count_below_gate"

    return {
        "arm_id": name,
        "action": action,
        "reason": reason,
        "sample_count": sample_count,
        "min_samples": min_samples,
        "artifacts_ready": artifacts_ready,
        "gate_status": gate_status or "UNSPECIFIED",
        "rank": _PRIORITY[action],
    }


def build_discovery_plan(
    arms: list[dict[str, Any]],
    *,
    min_samples: int = 30,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """多臂 read-only discovery action plan。"""
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    decisions = [decide_arm_action(arm, min_samples=min_samples) for arm in arms]
    decisions.sort(key=lambda row: (row["rank"], row["arm_id"]))
    counts: dict[str, int] = {}
    for row in decisions:
        counts[row["action"]] = counts.get(row["action"], 0) + 1
    return {
        "schema_version": DISCOVERY_LOOP_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "created_at_utc": now.astimezone(dt.timezone.utc).isoformat(),
        "policy": "read_only_recommendations_no_probe_or_trade_side_effect",
        "action_counts": counts,
        "arms": decisions,
    }


__all__ = [
    "BLOCK",
    "READY_FOR_AEG_CHAIN",
    "READY_FOR_PROBE",
    "RUN_READ_ONLY_CAPTURE",
    "WAIT",
    "build_discovery_plan",
    "decide_arm_action",
]
