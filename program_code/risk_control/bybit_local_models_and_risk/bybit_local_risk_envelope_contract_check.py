#!/usr/bin/env python3
"""
MODULE_NOTE:
- role: contract checker for H0-B local risk envelope output.
- purpose:
  Validate schema, required keys, enum values, and core field types for
  bybit_local_risk_envelope_latest.json.
- upstream:
  runtime/bybit/local_judgment/bybit_local_risk_envelope_latest.json
- output:
  runtime/bybit/local_judgment/bybit_local_risk_envelope_contract_latest.json
- notes:
  1) This checker validates structure, not trading desirability.
  2) A blocked or conservative result is acceptable if schema is valid.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import os
from typing import Any


INPUT_PATH = Path(
    os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/local_judgment/"
    "bybit_local_risk_envelope_latest.json"
)
OUTPUT_DIR = INPUT_PATH.parent
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_local_risk_envelope_contract_latest.json"

ALLOWED_POSITION_ORDER_CONFLICT_STATES = {
    "flat_no_position_no_order",
    "open_position_no_pending_orders",
    "pending_orders_no_open_position",
    "open_position_with_pending_orders",
}

ALLOWED_EXPOSURE_STATES = {
    "flat_zero_exposure",
    "within_configured_limits",
    "limit_exceeded",
}

ALLOWED_RISK_ENVELOPE_STATES = {
    "blocked",
    "flat_idle_low_risk",
    "recent_activity_but_currently_flat",
    "active_risk_present_but_within_limits",
}

ALLOWED_RECOMMENDED_ACTIONS = {
    "repair_risk_blockers_before_eligibility",
    "may_progress_to_trade_eligibility_builder",
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
    """Write latest and dated contract reports."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = LATEST_OUTPUT_PATH
    dated_path = OUTPUT_DIR / f"bybit_local_risk_envelope_contract_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path


def add_check(checks: list[dict[str, Any]], name: str, ok: bool, detail: Any) -> None:
    """Append one contract check row."""
    checks.append({"name": name, "ok": ok, "detail": detail})


def build_contract_report() -> dict[str, Any]:
    """Validate the H0-B local risk envelope output contract."""
    ts_ms = int(time.time() * 1000)
    payload, present, error = load_json(INPUT_PATH)

    checks: list[dict[str, Any]] = []
    failed_checks: list[dict[str, Any]] = []

    add_check(checks, "report_exists", present, str(INPUT_PATH))
    if not present:
        failed_checks = [item for item in checks if not item["ok"]]
        return {
            "report_type": "bybit_local_risk_envelope_contract_check",
            "report_version": "v1",
            "ts_ms": ts_ms,
            "overall_ok": False,
            "failed_count": len(failed_checks),
            "checks": checks,
            "failed_checks": failed_checks,
            "source_error": error,
        }

    add_check(
        checks,
        "risk_type_expected",
        payload.get("risk_type") == "bybit_local_risk_envelope",
        payload.get("risk_type"),
    )
    add_check(
        checks,
        "risk_version_v1",
        payload.get("risk_version") == "v1",
        payload.get("risk_version"),
    )
    add_check(checks, "ts_ms_int", isinstance(payload.get("ts_ms"), int), payload.get("ts_ms"))
    add_check(checks, "exchange_bybit", payload.get("exchange") == "bybit", payload.get("exchange"))
    add_check(checks, "stage_h0b", payload.get("stage") == "H0-B", payload.get("stage"))
    add_check(
        checks,
        "report_ok_bool",
        isinstance(payload.get("report_ok"), bool),
        payload.get("report_ok"),
    )
    add_check(
        checks,
        "source_integrity_dict",
        isinstance(payload.get("source_integrity"), dict),
        type(payload.get("source_integrity")).__name__,
    )
    add_check(
        checks,
        "risk_controls_dict",
        isinstance(payload.get("risk_controls"), dict),
        type(payload.get("risk_controls")).__name__,
    )
    add_check(
        checks,
        "account_context_dict",
        isinstance(payload.get("account_context"), dict),
        type(payload.get("account_context")).__name__,
    )
    add_check(
        checks,
        "position_order_conflict_state_allowed",
        payload.get("position_order_conflict_state") in ALLOWED_POSITION_ORDER_CONFLICT_STATES,
        payload.get("position_order_conflict_state"),
    )
    add_check(
        checks,
        "exposure_state_allowed",
        payload.get("exposure_state") in ALLOWED_EXPOSURE_STATES,
        payload.get("exposure_state"),
    )
    add_check(
        checks,
        "risk_envelope_state_allowed",
        payload.get("risk_envelope_state") in ALLOWED_RISK_ENVELOPE_STATES,
        payload.get("risk_envelope_state"),
    )
    add_check(
        checks,
        "allow_progress_bool",
        isinstance(payload.get("allow_progress_to_eligibility"), bool),
        payload.get("allow_progress_to_eligibility"),
    )
    add_check(
        checks,
        "recommended_action_allowed",
        payload.get("recommended_action") in ALLOWED_RECOMMENDED_ACTIONS,
        payload.get("recommended_action"),
    )
    add_check(
        checks,
        "blocking_reasons_list",
        isinstance(payload.get("blocking_reasons"), list),
        type(payload.get("blocking_reasons")).__name__,
    )

    risk_controls = payload.get("risk_controls", {})
    add_check(
        checks,
        "kill_switch_bool",
        isinstance(risk_controls.get("kill_switch_active"), bool),
        risk_controls.get("kill_switch_active"),
    )
    add_check(
        checks,
        "cooldown_bool",
        isinstance(risk_controls.get("cooldown_active"), bool),
        risk_controls.get("cooldown_active"),
    )
    add_check(
        checks,
        "max_position_count_int",
        isinstance(risk_controls.get("max_position_count"), int),
        risk_controls.get("max_position_count"),
    )
    add_check(
        checks,
        "max_order_count_int",
        isinstance(risk_controls.get("max_order_count"), int),
        risk_controls.get("max_order_count"),
    )

    failed_checks = [item for item in checks if not item["ok"]]

    return {
        "report_type": "bybit_local_risk_envelope_contract_check",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }


def main() -> None:
    """Entry point."""
    report = build_contract_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    latest_path, dated_path = save_report(report)
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
