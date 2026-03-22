#!/usr/bin/env python3
"""
MODULE_NOTE:
- role: H0 local deterministic judgment core - local trade eligibility builder.
- purpose:
  Merge runtime safety, H0-A market friction, and H0-B risk envelope into one
  conservative local trade eligibility result.
- upstream:
  1) runtime/bybit/bybit_runtime_state_latest.json
  2) runtime/bybit/bybit_readonly_audit_latest.json
  3) runtime/bybit/bybit_latest_consistency_latest.json
  4) runtime/bybit/local_judgment/bybit_local_market_friction_latest.json
  5) runtime/bybit/local_judgment/bybit_local_risk_envelope_latest.json
- output:
  runtime/bybit/local_judgment/bybit_local_trade_eligibility_latest.json
- notes:
  1) v1 is fail-closed.
  2) This module does NOT authorize trading.
  3) It only answers whether local conditions are good enough to progress into
     later governance layers.
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
MARKET_FRICTION_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment/"
    "bybit_local_market_friction_latest.json"
)
RISK_ENVELOPE_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment/"
    "bybit_local_risk_envelope_latest.json"
)

OUTPUT_DIR = MARKET_FRICTION_PATH.parent
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_local_trade_eligibility_latest.json"


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
    dated_path = OUTPUT_DIR / f"bybit_local_trade_eligibility_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path

def build_report() -> dict[str, Any]:
    """Build a conservative H0-C local trade eligibility report."""
    ts_ms = int(time.time() * 1000)

    runtime, runtime_present, runtime_error = load_json(RUNTIME_STATE_PATH)
    audit, audit_present, audit_error = load_json(READONLY_AUDIT_PATH)
    consistency, consistency_present, consistency_error = load_json(LATEST_CONSISTENCY_PATH)
    friction, friction_present, friction_error = load_json(MARKET_FRICTION_PATH)
    risk, risk_present, risk_error = load_json(RISK_ENVELOPE_PATH)

    source_errors = [
        error
        for error in [
            runtime_error,
            audit_error,
            consistency_error,
            friction_error,
            risk_error,
        ]
        if error
    ]
    blocking_reasons: list[str] = []

    runtime_state = runtime.get("overall_runtime_state", "unknown")
    system_mode = runtime.get("system_mode", "unknown")
    observer_state = runtime.get("observer_state", "unknown")
    execution_state = runtime.get("execution_state", "unknown")

    readonly_audit_ok = bool(audit.get("overall_ok")) if audit_present else False
    latest_consistency_ok = bool(consistency.get("overall_ok")) if consistency_present else False

    market_friction_state = friction.get("market_friction_state", "unknown")
    market_friction_allow = bool(friction.get("allow_progress_to_trade_path")) if friction_present else False

    risk_envelope_state = risk.get("risk_envelope_state", "unknown")
    risk_envelope_allow = bool(risk.get("allow_progress_to_eligibility")) if risk_present else False

    if not runtime_present:
        blocking_reasons.append("missing_runtime_state")
    if not audit_present:
        blocking_reasons.append("missing_readonly_audit")
    if not consistency_present:
        blocking_reasons.append("missing_latest_consistency")
    if not friction_present:
        blocking_reasons.append("missing_local_market_friction")
    if not risk_present:
        blocking_reasons.append("missing_local_risk_envelope")

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

    if friction_present and not market_friction_allow:
        blocking_reasons.append("market_friction_not_passed")
    if risk_present and not risk_envelope_allow:
        blocking_reasons.append("risk_envelope_not_passed")

    if not runtime_present or not audit_present or not consistency_present or not friction_present or not risk_present:
        trade_eligibility_state = "blocked_by_source_integrity"
        allow_progress_to_thought_gate = False
        recommended_action = "repair_missing_sources_before_thought_gate"
    elif runtime_state != "ready_readonly_observer" or system_mode != "read_only" or execution_state != "disabled":
        trade_eligibility_state = "blocked_by_runtime_guard"
        allow_progress_to_thought_gate = False
        recommended_action = "repair_runtime_guard_before_thought_gate"
    elif not readonly_audit_ok or not latest_consistency_ok:
        trade_eligibility_state = "blocked_by_runtime_guard"
        allow_progress_to_thought_gate = False
        recommended_action = "repair_runtime_guard_before_thought_gate"
    elif not market_friction_allow:
        trade_eligibility_state = "blocked_by_market_friction"
        allow_progress_to_thought_gate = False
        recommended_action = "repair_market_friction_before_thought_gate"
    elif not risk_envelope_allow:
        trade_eligibility_state = "blocked_by_risk_envelope"
        allow_progress_to_thought_gate = False
        recommended_action = "repair_risk_envelope_before_thought_gate"
    else:
        trade_eligibility_state = "eligible_for_governed_ai_review"
        allow_progress_to_thought_gate = True
        recommended_action = "may_progress_to_h1_thought_gate"

    operator_message = (
        "H0-C local trade eligibility built. This object is a local gate result "
        "and must not be treated as direct trade authorization."
    )

    return {
        "eligibility_type": "bybit_local_trade_eligibility",
        "eligibility_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "H0-C",
        "report_ok": True,
        "system_mode": system_mode,
        "overall_runtime_state": runtime_state,
        "observer_state": observer_state,
        "execution_state": execution_state,
        "source_refs": {
            "runtime_state_path": str(RUNTIME_STATE_PATH),
            "readonly_audit_path": str(READONLY_AUDIT_PATH),
            "latest_consistency_path": str(LATEST_CONSISTENCY_PATH),
            "market_friction_path": str(MARKET_FRICTION_PATH),
            "risk_envelope_path": str(RISK_ENVELOPE_PATH),
        },
        "source_integrity": {
            "runtime_present": runtime_present,
            "readonly_audit_present": audit_present,
            "latest_consistency_present": consistency_present,
            "market_friction_present": friction_present,
            "risk_envelope_present": risk_present,
            "readonly_audit_ok": readonly_audit_ok,
            "latest_consistency_ok": latest_consistency_ok,
            "source_errors": source_errors,
        },
        "upstream_states": {
            "market_friction_state": market_friction_state,
            "market_friction_allow": market_friction_allow,
            "risk_envelope_state": risk_envelope_state,
            "risk_envelope_allow": risk_envelope_allow,
        },
        "trade_eligibility_state": trade_eligibility_state,
        "allow_progress_to_thought_gate": allow_progress_to_thought_gate,
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
