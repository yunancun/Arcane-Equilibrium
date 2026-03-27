#!/usr/bin/env python3
"""
MODULE_NOTE:
- role: H0 local deterministic judgment core - local risk envelope gate.
- purpose:
  Build a conservative local risk envelope object from runtime health, current
  position/order/execution context, and simple local safety toggles.
- upstream:
  1) runtime/bybit/bybit_runtime_state_latest.json
  2) runtime/bybit/bybit_readonly_audit_latest.json
  3) runtime/bybit/bybit_latest_consistency_latest.json
  4) decision_packets/bybit/bybit_decision_packet_latest.json
- output:
  runtime/bybit/local_judgment/bybit_local_risk_envelope_latest.json
- notes:
  1) v1 is deterministic and conservative.
  2) This module does NOT authorize trading.
  3) This module only answers whether current local risk envelope is blocked or
     structurally acceptable for downstream eligibility review.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


RUNTIME_STATE_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/"
    "bybit_runtime_state_latest.json"
)
READONLY_AUDIT_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/"
    "bybit_readonly_audit_latest.json"
)
LATEST_CONSISTENCY_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/"
    "bybit_latest_consistency_latest.json"
)
DECISION_PACKET_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/decision_packets/bybit/"
    "bybit_decision_packet_latest.json"
)

OUTPUT_DIR = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment"
)
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_local_risk_envelope_latest.json"

KILL_SWITCH_ENV = "BYBIT_LOCAL_KILL_SWITCH_ACTIVE"
COOLDOWN_ENV = "BYBIT_LOCAL_RISK_COOLDOWN_ACTIVE"
MAX_POSITION_COUNT_ENV = "BYBIT_LOCAL_MAX_POSITION_COUNT"
MAX_ORDER_COUNT_ENV = "BYBIT_LOCAL_MAX_ORDER_COUNT"


def load_json(path: Path) -> tuple[dict[str, Any], bool, str | None]:
    """Load JSON from disk."""
    if not path.exists():
        return {}, False, f"missing_file:{path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), True, None
    except Exception as exc:  # pragma: no cover
        return {}, False, f"json_load_error:{path}:{exc}"


def parse_bool_env(name: str, default: bool = False) -> bool:
    """Parse a boolean-like environment variable."""
    raw = os.getenv(name)
    if raw is None:
        return default
    text = str(raw).strip().lower()
    return text in {"1", "true", "yes", "on"}


def parse_int_env(name: str, default: int) -> int:
    """Parse an integer environment variable."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def as_int(value: Any, default: int = 0) -> int:
    """Best-effort integer parsing."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def save_report(report: dict[str, Any]) -> tuple[Path, Path]:
    """Write latest and dated JSON outputs."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = LATEST_OUTPUT_PATH
    dated_path = OUTPUT_DIR / f"bybit_local_risk_envelope_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    os.chmod(str(latest_path), 0o600)
    dated_path.write_text(serialized, encoding="utf-8")
    os.chmod(str(dated_path), 0o600)
    return latest_path, dated_path


def build_report() -> dict[str, Any]:
    """Build a conservative H0-B local risk envelope report."""
    ts_ms = int(time.time() * 1000)

    runtime, runtime_present, runtime_error = load_json(RUNTIME_STATE_PATH)
    audit, audit_present, audit_error = load_json(READONLY_AUDIT_PATH)
    consistency, consistency_present, consistency_error = load_json(LATEST_CONSISTENCY_PATH)
    packet, packet_present, packet_error = load_json(DECISION_PACKET_PATH)

    source_errors = [
        error
        for error in [runtime_error, audit_error, consistency_error, packet_error]
        if error
    ]
    blocking_reasons: list[str] = []

    runtime_state = runtime.get("overall_runtime_state", "unknown")
    system_mode = runtime.get("system_mode", "unknown")
    observer_state = runtime.get("observer_state", "unknown")
    execution_state = runtime.get("execution_state", "unknown")

    readonly_audit_ok = bool(audit.get("overall_ok")) if audit_present else False
    latest_consistency_ok = bool(consistency.get("overall_ok")) if consistency_present else False

    position_summary = packet.get("position_summary", {}) if packet_present else {}
    order_summary = packet.get("order_summary", {}) if packet_present else {}
    execution_summary = packet.get("execution_summary", {}) if packet_present else {}
    risk_flags = packet.get("risk_flags", []) if packet_present else []

    position_count = as_int(position_summary.get("position_count"), 0)
    order_count = as_int(order_summary.get("order_count"), 0)
    execution_count = as_int(execution_summary.get("total_execution_count"), 0)

    kill_switch_active = parse_bool_env(KILL_SWITCH_ENV, default=False)
    cooldown_active = parse_bool_env(COOLDOWN_ENV, default=False)
    max_position_count = parse_int_env(MAX_POSITION_COUNT_ENV, default=1)
    max_order_count = parse_int_env(MAX_ORDER_COUNT_ENV, default=4)

    if position_count == 0 and order_count == 0:
        position_order_conflict_state = "flat_no_position_no_order"
    elif position_count > 0 and order_count == 0:
        position_order_conflict_state = "open_position_no_pending_orders"
    elif position_count == 0 and order_count > 0:
        position_order_conflict_state = "pending_orders_no_open_position"
    else:
        position_order_conflict_state = "open_position_with_pending_orders"

    if position_count == 0 and order_count == 0:
        exposure_state = "flat_zero_exposure"
    elif position_count <= max_position_count and order_count <= max_order_count:
        exposure_state = "within_configured_limits"
    else:
        exposure_state = "limit_exceeded"

    if not runtime_present:
        blocking_reasons.append("missing_runtime_state")
    if not audit_present:
        blocking_reasons.append("missing_readonly_audit")
    if not consistency_present:
        blocking_reasons.append("missing_latest_consistency")
    if not packet_present:
        blocking_reasons.append("missing_decision_packet")

    if runtime_present and system_mode != "read_only":
        blocking_reasons.append("system_mode_not_read_only")
    if runtime_present and execution_state != "disabled":
        blocking_reasons.append("execution_state_not_disabled")
    if runtime_present and runtime_state != "ready_readonly_observer":
        blocking_reasons.append("runtime_not_ready_readonly_observer")
    if audit_present and not readonly_audit_ok:
        blocking_reasons.append("readonly_audit_not_ok")
    if consistency_present and not latest_consistency_ok:
        blocking_reasons.append("latest_consistency_not_ok")
    if kill_switch_active:
        blocking_reasons.append("kill_switch_active")
    if cooldown_active:
        blocking_reasons.append("cooldown_active")
    if position_count > max_position_count:
        blocking_reasons.append("position_count_exceeds_limit")
    if order_count > max_order_count:
        blocking_reasons.append("order_count_exceeds_limit")

    if blocking_reasons:
        risk_envelope_state = "blocked"
        allow_progress_to_eligibility = False
        recommended_action = "repair_risk_blockers_before_eligibility"
    elif position_count == 0 and order_count == 0 and execution_count == 0:
        risk_envelope_state = "flat_idle_low_risk"
        allow_progress_to_eligibility = True
        recommended_action = "may_progress_to_trade_eligibility_builder"
    elif position_count == 0 and order_count == 0 and execution_count > 0:
        risk_envelope_state = "recent_activity_but_currently_flat"
        allow_progress_to_eligibility = True
        recommended_action = "may_progress_to_trade_eligibility_builder"
    else:
        risk_envelope_state = "active_risk_present_but_within_limits"
        allow_progress_to_eligibility = True
        recommended_action = "may_progress_to_trade_eligibility_builder"

    operator_message = (
        "H0-B local risk envelope built. This object is risk-perspective only "
        "and must not be treated as direct trade authorization."
    )

    return {
        "risk_type": "bybit_local_risk_envelope",
        "risk_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "H0-B",
        "report_ok": len(blocking_reasons) == 0,
        "system_mode": system_mode,
        "overall_runtime_state": runtime_state,
        "observer_state": observer_state,
        "execution_state": execution_state,
        "source_refs": {
            "runtime_state_path": str(RUNTIME_STATE_PATH),
            "readonly_audit_path": str(READONLY_AUDIT_PATH),
            "latest_consistency_path": str(LATEST_CONSISTENCY_PATH),
            "decision_packet_path": str(DECISION_PACKET_PATH),
        },
        "source_integrity": {
            "runtime_present": runtime_present,
            "readonly_audit_present": audit_present,
            "latest_consistency_present": consistency_present,
            "decision_packet_present": packet_present,
            "readonly_audit_ok": readonly_audit_ok,
            "latest_consistency_ok": latest_consistency_ok,
            "source_errors": source_errors,
        },
        "risk_controls": {
            "kill_switch_active": kill_switch_active,
            "cooldown_active": cooldown_active,
            "max_position_count": max_position_count,
            "max_order_count": max_order_count,
            "kill_switch_source": f"env:{KILL_SWITCH_ENV}",
            "cooldown_source": f"env:{COOLDOWN_ENV}",
        },
        "account_context": {
            "position_count": position_count,
            "order_count": order_count,
            "execution_count": execution_count,
            "risk_flags": risk_flags,
        },
        "position_order_conflict_state": position_order_conflict_state,
        "exposure_state": exposure_state,
        "risk_envelope_state": risk_envelope_state,
        "allow_progress_to_eligibility": allow_progress_to_eligibility,
        "recommended_action": recommended_action,
        "blocking_reasons": blocking_reasons,
        "operator_message": operator_message,
    }


def main() -> None:
    """Entry point."""
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    latest_path, dated_path = save_report(report)
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
