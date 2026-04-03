#!/usr/bin/env python3
"""
MODULE_NOTE:
- role: H0 local deterministic judgment core - final audit.
- purpose:
  Audit the full H0 chain (A/B/C/D) and confirm structural correctness,
  contract health, readonly protection, and current progression status.
- upstream:
  1) bybit_local_market_friction_latest.json
  2) bybit_local_market_friction_contract_latest.json
  3) bybit_local_risk_envelope_latest.json
  4) bybit_local_risk_envelope_contract_latest.json
  5) bybit_local_trade_eligibility_latest.json
  6) bybit_local_trade_eligibility_contract_latest.json
  7) bybit_local_trade_eligibility_handoff_latest.json
  8) bybit_local_trade_eligibility_handoff_contract_latest.json
  9) bybit_runtime_state_latest.json
  10) bybit_readonly_audit_latest.json
  11) bybit_latest_consistency_latest.json
- output:
  runtime/bybit/local_judgment/bybit_local_judgment_final_audit_latest.json
- notes:
  1) overall_ok means H0 chain is structurally valid and correctly audited.
  2) progression_ready may be false or true depending on whether H0 has fully
     opened the path into H1.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import os
from typing import Any


BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/local_judgment")
MARKET_FRICTION_PATH = BASE / "bybit_local_market_friction_latest.json"
MARKET_FRICTION_CONTRACT_PATH = BASE / "bybit_local_market_friction_contract_latest.json"
RISK_ENVELOPE_PATH = BASE / "bybit_local_risk_envelope_latest.json"
RISK_ENVELOPE_CONTRACT_PATH = BASE / "bybit_local_risk_envelope_contract_latest.json"
TRADE_ELIGIBILITY_PATH = BASE / "bybit_local_trade_eligibility_latest.json"
TRADE_ELIGIBILITY_CONTRACT_PATH = BASE / "bybit_local_trade_eligibility_contract_latest.json"
HANDOFF_PATH = BASE / "bybit_local_trade_eligibility_handoff_latest.json"
HANDOFF_CONTRACT_PATH = BASE / "bybit_local_trade_eligibility_handoff_contract_latest.json"

RUNTIME_STATE_PATH = Path(
    os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json"
)
READONLY_AUDIT_PATH = Path(
    os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_readonly_audit_latest.json"
)
LATEST_CONSISTENCY_PATH = Path(
    os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_latest_consistency_latest.json"
)

OUTPUT_DIR = BASE
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_local_judgment_final_audit_latest.json"

ALLOWED_MARKET_FRICTION_BLOCK_STATES = {
    "blocked",
    "observe_only_missing_public_microstructure",
    "observe_only_limited_visibility",
}


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
    dated_path = OUTPUT_DIR / f"bybit_local_judgment_final_audit_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path


def add_check(checks: list[dict[str, Any]], name: str, ok: bool, detail: Any) -> None:
    """Append one audit row."""
    checks.append({"name": name, "ok": ok, "detail": detail})


def build_report() -> dict[str, Any]:
    """Build the full H0 final audit report."""
    ts_ms = int(time.time() * 1000)

    friction, friction_present, friction_error = load_json(MARKET_FRICTION_PATH)
    friction_contract, friction_contract_present, friction_contract_error = load_json(MARKET_FRICTION_CONTRACT_PATH)
    risk, risk_present, risk_error = load_json(RISK_ENVELOPE_PATH)
    risk_contract, risk_contract_present, risk_contract_error = load_json(RISK_ENVELOPE_CONTRACT_PATH)
    eligibility, eligibility_present, eligibility_error = load_json(TRADE_ELIGIBILITY_PATH)
    eligibility_contract, eligibility_contract_present, eligibility_contract_error = load_json(TRADE_ELIGIBILITY_CONTRACT_PATH)
    handoff, handoff_present, handoff_error = load_json(HANDOFF_PATH)
    handoff_contract, handoff_contract_present, handoff_contract_error = load_json(HANDOFF_CONTRACT_PATH)
    runtime, runtime_present, runtime_error = load_json(RUNTIME_STATE_PATH)
    readonly_audit, readonly_audit_present, readonly_audit_error = load_json(READONLY_AUDIT_PATH)
    consistency, consistency_present, consistency_error = load_json(LATEST_CONSISTENCY_PATH)

    checks: list[dict[str, Any]] = []
    source_errors = [
        error
        for error in [
            friction_error,
            friction_contract_error,
            risk_error,
            risk_contract_error,
            eligibility_error,
            eligibility_contract_error,
            handoff_error,
            handoff_contract_error,
            runtime_error,
            readonly_audit_error,
            consistency_error,
        ]
        if error
    ]

    add_check(checks, "friction_exists", friction_present, str(MARKET_FRICTION_PATH))
    add_check(checks, "friction_contract_exists", friction_contract_present, str(MARKET_FRICTION_CONTRACT_PATH))
    add_check(checks, "risk_exists", risk_present, str(RISK_ENVELOPE_PATH))
    add_check(checks, "risk_contract_exists", risk_contract_present, str(RISK_ENVELOPE_CONTRACT_PATH))
    add_check(checks, "eligibility_exists", eligibility_present, str(TRADE_ELIGIBILITY_PATH))
    add_check(checks, "eligibility_contract_exists", eligibility_contract_present, str(TRADE_ELIGIBILITY_CONTRACT_PATH))
    add_check(checks, "handoff_exists", handoff_present, str(HANDOFF_PATH))
    add_check(checks, "handoff_contract_exists", handoff_contract_present, str(HANDOFF_CONTRACT_PATH))
    add_check(checks, "runtime_exists", runtime_present, str(RUNTIME_STATE_PATH))
    add_check(checks, "readonly_audit_exists", readonly_audit_present, str(READONLY_AUDIT_PATH))
    add_check(checks, "consistency_exists", consistency_present, str(LATEST_CONSISTENCY_PATH))

    add_check(
        checks,
        "friction_contract_ok",
        bool(friction_contract.get("overall_ok")) if friction_contract_present else False,
        friction_contract.get("failed_count") if friction_contract_present else "missing",
    )
    add_check(
        checks,
        "risk_contract_ok",
        bool(risk_contract.get("overall_ok")) if risk_contract_present else False,
        risk_contract.get("failed_count") if risk_contract_present else "missing",
    )
    add_check(
        checks,
        "eligibility_contract_ok",
        bool(eligibility_contract.get("overall_ok")) if eligibility_contract_present else False,
        eligibility_contract.get("failed_count") if eligibility_contract_present else "missing",
    )
    add_check(
        checks,
        "handoff_contract_ok",
        bool(handoff_contract.get("overall_ok")) if handoff_contract_present else False,
        handoff_contract.get("failed_count") if handoff_contract_present else "missing",
    )

    add_check(
        checks,
        "runtime_ready_readonly_observer",
        runtime.get("overall_runtime_state") == "ready_readonly_observer" if runtime_present else False,
        runtime.get("overall_runtime_state") if runtime_present else "missing",
    )
    add_check(
        checks,
        "runtime_system_mode_read_only",
        runtime.get("system_mode") == "read_only" if runtime_present else False,
        runtime.get("system_mode") if runtime_present else "missing",
    )
    add_check(
        checks,
        "runtime_execution_disabled",
        runtime.get("execution_state") == "disabled" if runtime_present else False,
        runtime.get("execution_state") if runtime_present else "missing",
    )
    add_check(
        checks,
        "readonly_audit_ok",
        bool(readonly_audit.get("overall_ok")) if readonly_audit_present else False,
        readonly_audit.get("failed_count") if readonly_audit_present else "missing",
    )
    add_check(
        checks,
        "latest_consistency_ok",
        bool(consistency.get("overall_ok")) if consistency_present else False,
        consistency.get("failed_count") if consistency_present else "missing",
    )

    friction_state = friction.get("market_friction_state", "unknown") if friction_present else "missing"
    risk_state = risk.get("risk_envelope_state", "unknown") if risk_present else "missing"
    eligibility_state = eligibility.get("trade_eligibility_state", "unknown") if eligibility_present else "missing"
    handoff_state = handoff.get("handoff_state", "unknown") if handoff_present else "missing"
    allow_progress_to_h1 = handoff.get("allow_progress_to_h1") if handoff_present else False

    blocked_path_ok = (
        friction_state in ALLOWED_MARKET_FRICTION_BLOCK_STATES
        and risk_state == "flat_idle_low_risk"
        and eligibility_state == "blocked_by_market_friction"
    )

    ready_path_ok = (
        friction_state == "eligible_for_next_gate"
        and risk_state == "flat_idle_low_risk"
        and eligibility_state == "eligible_for_governed_ai_review"
    )

    add_check(
        checks,
        "eligibility_matches_friction_risk",
        blocked_path_ok or ready_path_ok,
        {
            "market_friction_state": friction_state,
            "risk_envelope_state": risk_state,
            "trade_eligibility_state": eligibility_state,
        },
    )

    blocked_handoff_ok = (
        eligibility_state == "blocked_by_market_friction"
        and handoff_state == "blocked_waiting_market_friction_upgrade"
        and allow_progress_to_h1 is False
    )

    ready_handoff_ok = (
        eligibility_state == "eligible_for_governed_ai_review"
        and handoff_state == "ready_for_h1_thought_gate"
        and allow_progress_to_h1 is True
    )

    add_check(
        checks,
        "handoff_matches_eligibility",
        blocked_handoff_ok or ready_handoff_ok,
        {
            "trade_eligibility_state": eligibility_state,
            "handoff_state": handoff_state,
            "allow_progress_to_h1": allow_progress_to_h1,
        },
    )

    failed_checks = [item for item in checks if not item["ok"]]
    h0_chain_ok = len(failed_checks) == 0
    progression_ready = bool(allow_progress_to_h1)

    if h0_chain_ok and progression_ready:
        final_h0_state = "structurally_valid_and_ready_for_h1"
        recommended_action = "progress_to_h1_thought_gate"
    elif h0_chain_ok and not progression_ready:
        final_h0_state = "structurally_valid_but_waiting_market_friction_upgrade"
        recommended_action = "add_public_microstructure_and_cost_model"
    else:
        final_h0_state = "h0_chain_requires_repair"
        recommended_action = "repair_h0_chain_before_progression"

    return {
        "audit_type": "bybit_local_judgment_final_audit",
        "audit_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "H0-final",
        "overall_ok": h0_chain_ok,
        "h0_chain_ok": h0_chain_ok,
        "progression_ready": progression_ready,
        "final_h0_state": final_h0_state,
        "recommended_action": recommended_action,
        "checks": checks,
        "failed_checks": failed_checks,
        "failed_count": len(failed_checks),
        "upstream_summary": {
            "market_friction_state": friction_state,
            "risk_envelope_state": risk_state,
            "trade_eligibility_state": eligibility_state,
            "handoff_state": handoff_state,
        },
        "source_errors": source_errors,
        "operator_message": (
            "H0 final audit confirms whether the local deterministic judgment core "
            "is structurally valid and whether it is ready to hand off into H1."
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
