#!/usr/bin/env python3
"""
MODULE_NOTE:
- role: H0 local deterministic judgment core - local cost model builder.
- purpose:
  Build an auditable local trading cost model object from operator-provided
  configuration for later H0 market friction use.
- upstream:
  1) runtime/bybit/bybit_runtime_state_latest.json
  2) decision_packets/bybit/bybit_decision_packet_latest.json
- output:
  runtime/bybit/local_judgment/bybit_local_cost_model_latest.json
- notes:
  1) v1 does not guess exchange fee tiers.
  2) Cost inputs must be operator-configured and auditable.
  3) This module does NOT authorize trading.
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
DECISION_PACKET_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/decision_packets/bybit/"
    "bybit_decision_packet_latest.json"
)

OUTPUT_DIR = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment"
)
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_local_cost_model_latest.json"

ROUND_TRIP_COST_BPS_ENV = "BYBIT_LOCAL_ROUND_TRIP_COST_BPS"
SLIPPAGE_BUFFER_BPS_ENV = "BYBIT_LOCAL_SLIPPAGE_BUFFER_BPS"
EDGE_MULTIPLIER_ENV = "BYBIT_LOCAL_EDGE_MULTIPLIER"


def load_json(path: Path) -> tuple[dict[str, Any], bool, str | None]:
    """Load JSON from disk."""
    if not path.exists():
        return {}, False, f"missing_file:{path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), True, None
    except Exception as exc:  # pragma: no cover
        return {}, False, f"json_load_error:{path}:{exc}"


def parse_optional_float(raw: str | None) -> float | None:
    """Parse optional float text into float."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def save_report(report: dict[str, Any]) -> tuple[Path, Path]:
    """Write latest and dated JSON outputs."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = LATEST_OUTPUT_PATH
    dated_path = OUTPUT_DIR / f"bybit_local_cost_model_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path

def build_report() -> dict[str, Any]:
    """Build a conservative H0-E local cost model report."""
    ts_ms = int(time.time() * 1000)

    runtime, runtime_present, runtime_error = load_json(RUNTIME_STATE_PATH)
    packet, packet_present, packet_error = load_json(DECISION_PACKET_PATH)

    source_errors = [
        error
        for error in [runtime_error, packet_error]
        if error
    ]
    blocking_reasons: list[str] = []

    runtime_state = runtime.get("overall_runtime_state", "unknown")
    system_mode = runtime.get("system_mode", "unknown")
    observer_state = runtime.get("observer_state", "unknown")
    execution_state = runtime.get("execution_state", "unknown")

    round_trip_cost_bps = parse_optional_float(os.getenv(ROUND_TRIP_COST_BPS_ENV))
    slippage_buffer_bps = parse_optional_float(os.getenv(SLIPPAGE_BUFFER_BPS_ENV))
    edge_multiplier = parse_optional_float(os.getenv(EDGE_MULTIPLIER_ENV))

    if slippage_buffer_bps is None:
        slippage_buffer_bps = 0.0
    if edge_multiplier is None:
        edge_multiplier = 1.5

    if round_trip_cost_bps is None:
        cost_model_state = "unconfigured"
        total_cost_floor_bps = None
        required_edge_bps = None
        blocking_reasons.append("round_trip_cost_bps_unconfigured")
    else:
        cost_model_state = "configured"
        total_cost_floor_bps = round(round_trip_cost_bps + slippage_buffer_bps, 6)
        required_edge_bps = round(total_cost_floor_bps * edge_multiplier, 6)

    if runtime_present and system_mode != "read_only":
        blocking_reasons.append("system_mode_not_read_only")
    if runtime_present and execution_state != "disabled":
        blocking_reasons.append("execution_state_not_disabled")
    if runtime_present and runtime_state != "ready_readonly_observer":
        blocking_reasons.append("runtime_not_ready_readonly_observer")

    allow_use_by_market_friction = len(blocking_reasons) == 0

    account_summary = packet.get("account_summary", {}) if packet_present else {}

    return {
        "cost_type": "bybit_local_cost_model",
        "cost_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "H0-E",
        "report_ok": True,
        "system_mode": system_mode,
        "overall_runtime_state": runtime_state,
        "observer_state": observer_state,
        "execution_state": execution_state,
        "source_refs": {
            "runtime_state_path": str(RUNTIME_STATE_PATH),
            "decision_packet_path": str(DECISION_PACKET_PATH),
        },
        "source_integrity": {
            "runtime_present": runtime_present,
            "decision_packet_present": packet_present,
            "source_errors": source_errors,
        },
        "config": {
            "round_trip_cost_bps": round_trip_cost_bps,
            "slippage_buffer_bps": slippage_buffer_bps,
            "edge_multiplier": edge_multiplier,
            "round_trip_cost_source": f"env:{ROUND_TRIP_COST_BPS_ENV}",
            "slippage_buffer_source": f"env:{SLIPPAGE_BUFFER_BPS_ENV}",
            "edge_multiplier_source": f"env:{EDGE_MULTIPLIER_ENV}",
        },
        "derived": {
            "total_cost_floor_bps": total_cost_floor_bps,
            "required_edge_bps": required_edge_bps,
            "formula": (
                "required_edge_bps = (round_trip_cost_bps + slippage_buffer_bps) * edge_multiplier"
                if required_edge_bps is not None
                else "unavailable_until_round_trip_cost_bps_is_configured"
            ),
        },
        "known_context": {
            "total_equity": account_summary.get("total_equity"),
            "usdt_wallet_balance": account_summary.get("usdt_wallet_balance"),
        },
        "cost_model_state": cost_model_state,
        "allow_use_by_market_friction": allow_use_by_market_friction,
        "blocking_reasons": blocking_reasons,
        "operator_message": (
            "H0-E local cost model built. This object converts operator-provided "
            "cost assumptions into an auditable local judgment input."
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
