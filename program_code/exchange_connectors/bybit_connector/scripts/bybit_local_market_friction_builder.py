#!/usr/bin/env python3
"""
MODULE_NOTE:
- role: H0 local deterministic judgment core - local market friction builder.
- purpose:
  Build a conservative, coverage-aware local market friction object before any
  future AI governance or execution path is considered.
- upstream:
  1) runtime/bybit/bybit_runtime_state_latest.json
  2) runtime/bybit/bybit_readonly_audit_latest.json
  3) runtime/bybit/bybit_latest_consistency_latest.json
  4) decision_packets/bybit/bybit_decision_packet_latest.json
  5) runtime/bybit/local_judgment/bybit_local_cost_model_latest.json
  6) runtime/bybit/local_judgment/bybit_public_microstructure_latest.json
- output:
  runtime/bybit/local_judgment/bybit_local_market_friction_latest.json
- notes:
  1) v3 consumes auditable local cost model and public microstructure.
  2) This module does NOT authorize trading.
  3) H0-A focuses on market friction, not private business-event readiness.
"""

from __future__ import annotations

import json
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
COST_MODEL_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment/"
    "bybit_local_cost_model_latest.json"
)
PUBLIC_MICROSTRUCTURE_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment/"
    "bybit_public_microstructure_latest.json"
)

OUTPUT_DIR = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment"
)
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_local_market_friction_latest.json"


def load_json(path: Path) -> tuple[dict[str, Any], bool, str | None]:
    """Load a JSON file."""
    if not path.exists():
        return {}, False, f"missing_file:{path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), True, None
    except Exception as exc:  # pragma: no cover
        return {}, False, f"json_load_error:{path}:{exc}"


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
    dated_path = OUTPUT_DIR / f"bybit_local_market_friction_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path

def build_report() -> dict[str, Any]:
    """Build a conservative market friction report for H0."""
    ts_ms = int(time.time() * 1000)

    runtime, runtime_present, runtime_error = load_json(RUNTIME_STATE_PATH)
    audit, audit_present, audit_error = load_json(READONLY_AUDIT_PATH)
    consistency, consistency_present, consistency_error = load_json(LATEST_CONSISTENCY_PATH)
    packet, packet_present, packet_error = load_json(DECISION_PACKET_PATH)
    cost_model, cost_model_present, cost_model_error = load_json(COST_MODEL_PATH)
    public_micro, public_micro_present, public_micro_error = load_json(PUBLIC_MICROSTRUCTURE_PATH)

    blocking_reasons: list[str] = []
    source_errors: list[str] = [
        error
        for error in [
            runtime_error,
            audit_error,
            consistency_error,
            packet_error,
            cost_model_error,
            public_micro_error,
        ]
        if error
    ]

    runtime_state = runtime.get("overall_runtime_state", "unknown")
    system_mode = runtime.get("system_mode", "unknown")
    observer_state = runtime.get("observer_state", "unknown")
    execution_state = runtime.get("execution_state", "unknown")
    ws_signal_strength = runtime.get("ws_signal_strength", "unknown")
    business_event_state = runtime.get("business_event_state", "unknown")

    readonly_audit_ok = bool(audit.get("overall_ok")) if audit_present else False
    latest_consistency_ok = bool(consistency.get("overall_ok")) if consistency_present else False

    account_summary = packet.get("account_summary", {}) if packet_present else {}
    position_summary = packet.get("position_summary", {}) if packet_present else {}
    order_summary = packet.get("order_summary", {}) if packet_present else {}
    execution_summary = packet.get("execution_summary", {}) if packet_present else {}
    risk_flags = packet.get("risk_flags", []) if packet_present else []

    position_count = as_int(position_summary.get("position_count"), 0)
    order_count = as_int(order_summary.get("order_count"), 0)
    execution_count = as_int(execution_summary.get("total_execution_count"), 0)

    cost_model_state = cost_model.get("cost_model_state", "unconfigured") if cost_model_present else "unconfigured"
    total_cost_floor_bps = cost_model.get("derived", {}).get("total_cost_floor_bps") if cost_model_present else None
    required_edge_bps = cost_model.get("derived", {}).get("required_edge_bps") if cost_model_present else None

    public_micro_state = public_micro.get("microstructure_state", "unknown") if public_micro_present else "unknown"
    public_micro_allow = bool(public_micro.get("allow_use_by_h0")) if public_micro_present else False
    public_coverage = public_micro.get("coverage", {}) if public_micro_present else {}
    public_derived = public_micro.get("derived", {}) if public_micro_present else {}

    microstructure_coverage = {
        "best_bid_ask_present": bool(public_coverage.get("best_bid_ask_present", False)),
        "orderbook_depth_present": bool(public_coverage.get("orderbook_depth_present", False)),
        "recent_trade_tape_present": bool(public_coverage.get("recent_trade_tape_present", False)),
        "volatility_band_present": bool(public_coverage.get("volatility_band_present", False)),
        "slippage_proxy_present": bool(public_coverage.get("slippage_proxy_present", False)),
    }

    if not runtime_present:
        blocking_reasons.append("missing_runtime_state")
    if not audit_present:
        blocking_reasons.append("missing_readonly_audit")
    if not consistency_present:
        blocking_reasons.append("missing_latest_consistency")
    if not packet_present:
        blocking_reasons.append("missing_decision_packet")
    if not cost_model_present:
        blocking_reasons.append("missing_local_cost_model")
    if not public_micro_present:
        blocking_reasons.append("missing_public_microstructure")

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
    if cost_model_present and cost_model_state != "configured":
        blocking_reasons.append("local_cost_model_not_configured")

    local_visibility = {
        "ws_signal_strength": ws_signal_strength,
        "business_event_state": business_event_state,
        "local_visibility_state": (
            "limited_control_only_visibility"
            if ws_signal_strength == "control_only" and business_event_state == "healthy_no_business_events_yet"
            else "runtime_visible"
        ),
        "h0a_visibility_policy": (
            "informational_only_for_market_friction_when_public_microstructure_is_healthy"
        ),
    }

    if blocking_reasons:
        market_friction_state = "blocked"
        allow_progress_to_trade_path = False
        recommended_action = "repair_blockers_before_trade_consideration"
    elif not public_micro_allow:
        if public_micro_state == "blocked_public_fetch_failed":
            market_friction_state = "blocked"
            allow_progress_to_trade_path = False
            recommended_action = "repair_blockers_before_trade_consideration"
        else:
            market_friction_state = "observe_only_missing_public_microstructure"
            allow_progress_to_trade_path = False
            recommended_action = "keep_observe_only_and_add_public_market_inputs"
    else:
        market_friction_state = "eligible_for_next_gate"
        allow_progress_to_trade_path = True
        recommended_action = "may_progress_to_local_risk_envelope_gate"

    return {
        "friction_type": "bybit_local_market_friction",
        "friction_version": "v3",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "H0-A",
        "report_ok": True,
        "system_mode": system_mode,
        "overall_runtime_state": runtime_state,
        "observer_state": observer_state,
        "execution_state": execution_state,
        "source_refs": {
            "runtime_state_path": str(RUNTIME_STATE_PATH),
            "readonly_audit_path": str(READONLY_AUDIT_PATH),
            "latest_consistency_path": str(LATEST_CONSISTENCY_PATH),
            "decision_packet_path": str(DECISION_PACKET_PATH),
            "cost_model_path": str(COST_MODEL_PATH),
            "public_microstructure_path": str(PUBLIC_MICROSTRUCTURE_PATH),
        },
        "source_integrity": {
            "runtime_present": runtime_present,
            "readonly_audit_present": audit_present,
            "latest_consistency_present": consistency_present,
            "decision_packet_present": packet_present,
            "cost_model_present": cost_model_present,
            "public_microstructure_present": public_micro_present,
            "readonly_audit_ok": readonly_audit_ok,
            "latest_consistency_ok": latest_consistency_ok,
            "source_errors": source_errors,
        },
        "local_visibility": local_visibility,
        "known_context": {
            "total_equity": account_summary.get("total_equity"),
            "position_count": position_count,
            "order_count": order_count,
            "execution_count": execution_count,
            "risk_flags": risk_flags,
        },
        "cost_model": {
            "cost_model_state": cost_model_state,
            "total_cost_floor_bps": total_cost_floor_bps,
            "required_edge_bps": required_edge_bps,
            "cost_model_source": str(COST_MODEL_PATH),
        },
        "public_microstructure": {
            "microstructure_state": public_micro_state,
            "allow_use_by_h0": public_micro_allow,
            "symbol": public_micro.get("config", {}).get("symbol"),
            "category": public_micro.get("config", {}).get("category"),
            "spread_bps": public_derived.get("spread_bps"),
            "volatility_bps": public_derived.get("volatility_bps"),
            "volatility_band": public_derived.get("volatility_band"),
            "slippage_buy_bps_for_test_notional": public_derived.get("slippage_buy_bps_for_test_notional"),
            "slippage_sell_bps_for_test_notional": public_derived.get("slippage_sell_bps_for_test_notional"),
            "source": str(PUBLIC_MICROSTRUCTURE_PATH),
        },
        "microstructure_coverage": microstructure_coverage,
        "minimum_edge_gate": {
            "state": (
                "active"
                if (required_edge_bps is not None and public_micro_allow)
                else "informational_only_pending_public_microstructure"
            ),
            "required_edge_bps": required_edge_bps,
            "formula": (
                "required_edge_bps supplied by local cost model latest"
                if required_edge_bps is not None
                else "unavailable_until_local_cost_model_is_configured"
            ),
        },
        "market_friction_state": market_friction_state,
        "allow_progress_to_trade_path": allow_progress_to_trade_path,
        "recommended_action": recommended_action,
        "blocking_reasons": blocking_reasons,
        "required_next_integrations": [],
        "operator_message": (
            "H0-A market friction v3 built. This object now consumes local cost model "
            "and public microstructure and only blocks on real friction-layer gaps."
        ),
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
