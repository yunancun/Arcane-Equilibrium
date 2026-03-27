#!/usr/bin/env python3
"""
MODULE_NOTE:
- role: H0 local deterministic judgment core - trade eligibility handoff builder.
- purpose:
  Convert H0-C local trade eligibility into a compact handoff object for H1
  thought gate and later governance layers.
- upstream:
  1) runtime/bybit/local_judgment/bybit_local_trade_eligibility_latest.json
  2) runtime/bybit/local_judgment/bybit_local_market_friction_latest.json
  3) runtime/bybit/local_judgment/bybit_local_risk_envelope_latest.json
  4) runtime/bybit/bybit_runtime_state_latest.json
- output:
  runtime/bybit/local_judgment/bybit_local_trade_eligibility_handoff_latest.json
- notes:
  1) v2 is conservative and descriptive.
  2) This module does NOT authorize trading.
  3) It exists to provide a stable downstream handoff contract.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


TRADE_ELIGIBILITY_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment/"
    "bybit_local_trade_eligibility_latest.json"
)
MARKET_FRICTION_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment/"
    "bybit_local_market_friction_latest.json"
)
RISK_ENVELOPE_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment/"
    "bybit_local_risk_envelope_latest.json"
)
RUNTIME_STATE_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/"
    "bybit_runtime_state_latest.json"
)

OUTPUT_DIR = TRADE_ELIGIBILITY_PATH.parent
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_local_trade_eligibility_handoff_latest.json"


def load_json(path: Path) -> tuple[dict[str, Any], bool, str | None]:
    """Load JSON from disk."""
    if not path.exists():
        return {}, False, f"missing_file:{path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), True, None
    except Exception as exc:  # pragma: no cover
        return {}, False, f"json_load_error:{path}:{exc}"


def save_report(report: dict[str, Any]) -> tuple[Path, Path]:
    """Write latest and dated JSON outputs."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = LATEST_OUTPUT_PATH
    dated_path = OUTPUT_DIR / f"bybit_local_trade_eligibility_handoff_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    os.chmod(str(latest_path), 0o600)
    dated_path.write_text(serialized, encoding="utf-8")
    os.chmod(str(dated_path), 0o600)
    return latest_path, dated_path


def build_report() -> dict[str, Any]:
    """Build a conservative H0-D handoff object."""
    ts_ms = int(time.time() * 1000)

    eligibility, eligibility_present, eligibility_error = load_json(TRADE_ELIGIBILITY_PATH)
    friction, friction_present, friction_error = load_json(MARKET_FRICTION_PATH)
    risk, risk_present, risk_error = load_json(RISK_ENVELOPE_PATH)
    runtime, runtime_present, runtime_error = load_json(RUNTIME_STATE_PATH)

    source_errors = [
        error
        for error in [eligibility_error, friction_error, risk_error, runtime_error]
        if error
    ]

    trade_eligibility_state = eligibility.get("trade_eligibility_state", "unknown")
    allow_progress_to_thought_gate = bool(
        eligibility.get("allow_progress_to_thought_gate")
    ) if eligibility_present else False

    market_friction_state = friction.get("market_friction_state", "unknown")
    risk_envelope_state = risk.get("risk_envelope_state", "unknown")

    runtime_state = runtime.get("overall_runtime_state", "unknown")
    system_mode = runtime.get("system_mode", "unknown")
    execution_state = runtime.get("execution_state", "unknown")

    if not eligibility_present or not friction_present or not risk_present or not runtime_present:
        handoff_state = "blocked_missing_h0_sources"
        allow_progress_to_h1 = False
        next_step_hint = "repair_h0_missing_sources"
    elif trade_eligibility_state == "eligible_for_governed_ai_review":
        handoff_state = "ready_for_h1_thought_gate"
        allow_progress_to_h1 = True
        next_step_hint = "progress_to_h1_thought_gate"
    elif trade_eligibility_state == "blocked_by_market_friction":
        handoff_state = "blocked_waiting_market_friction_upgrade"
        allow_progress_to_h1 = False
        if market_friction_state == "observe_only_missing_public_microstructure":
            next_step_hint = "add_public_microstructure_inputs"
        else:
            next_step_hint = "repair_market_friction"
    elif trade_eligibility_state == "blocked_by_risk_envelope":
        handoff_state = "blocked_waiting_risk_envelope_repair"
        allow_progress_to_h1 = False
        next_step_hint = "repair_local_risk_envelope"
    elif trade_eligibility_state in {
        "blocked_by_source_integrity",
        "blocked_by_runtime_guard",
    }:
        handoff_state = "blocked_waiting_runtime_repair"
        allow_progress_to_h1 = False
        next_step_hint = "repair_runtime_guard_and_source_integrity"
    else:
        handoff_state = "blocked_unknown_h0_state"
        allow_progress_to_h1 = False
        next_step_hint = "inspect_h0_state_resolution"

    return {
        "handoff_type": "bybit_local_trade_eligibility_handoff",
        "handoff_version": "v2",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "H0-D",
        "report_ok": True,
        "source_refs": {
            "trade_eligibility_path": str(TRADE_ELIGIBILITY_PATH),
            "market_friction_path": str(MARKET_FRICTION_PATH),
            "risk_envelope_path": str(RISK_ENVELOPE_PATH),
            "runtime_state_path": str(RUNTIME_STATE_PATH),
        },
        "source_integrity": {
            "trade_eligibility_present": eligibility_present,
            "market_friction_present": friction_present,
            "risk_envelope_present": risk_present,
            "runtime_state_present": runtime_present,
            "source_errors": source_errors,
        },
        "current_runtime": {
            "system_mode": system_mode,
            "overall_runtime_state": runtime_state,
            "execution_state": execution_state,
        },
        "upstream_states": {
            "trade_eligibility_state": trade_eligibility_state,
            "allow_progress_to_thought_gate": allow_progress_to_thought_gate,
            "market_friction_state": market_friction_state,
            "risk_envelope_state": risk_envelope_state,
        },
        "handoff_state": handoff_state,
        "allow_progress_to_h1": allow_progress_to_h1,
        "next_step_hint": next_step_hint,
        "operator_message": (
            "H0-D handoff built. This object summarizes whether H0 has prepared the "
            "system to enter H1 thought gate."
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
