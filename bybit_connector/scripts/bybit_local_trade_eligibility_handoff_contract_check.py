#!/usr/bin/env python3
"""
MODULE_NOTE:
- role: contract checker for H0-D trade eligibility handoff output.
- purpose:
  Validate schema, required keys, enum values, and core field types for
  bybit_local_trade_eligibility_handoff_latest.json.
- upstream:
  runtime/bybit/local_judgment/bybit_local_trade_eligibility_handoff_latest.json
- output:
  runtime/bybit/local_judgment/bybit_local_trade_eligibility_handoff_contract_latest.json
- notes:
  1) This checker validates structure, not downstream policy desirability.
  2) A blocked handoff is acceptable if schema is valid.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


INPUT_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment/"
    "bybit_local_trade_eligibility_handoff_latest.json"
)
OUTPUT_DIR = INPUT_PATH.parent
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_local_trade_eligibility_handoff_contract_latest.json"

ALLOWED_HANDOFF_VERSIONS = {"v1", "v2"}
ALLOWED_HANDOFF_STATES = {
    "blocked_missing_h0_sources",
    "ready_for_h1_thought_gate",
    "blocked_waiting_market_friction_upgrade",
    "blocked_waiting_risk_envelope_repair",
    "blocked_waiting_runtime_repair",
    "blocked_unknown_h0_state",
}
ALLOWED_NEXT_STEP_HINTS = {
    "repair_h0_missing_sources",
    "progress_to_h1_thought_gate",
    "add_public_microstructure_and_cost_model",
    "add_public_microstructure_inputs",
    "repair_market_friction",
    "repair_local_risk_envelope",
    "repair_runtime_guard_and_source_integrity",
    "inspect_h0_state_resolution",
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
    dated_path = OUTPUT_DIR / f"bybit_local_trade_eligibility_handoff_contract_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path


def add_check(checks: list[dict[str, Any]], name: str, ok: bool, detail: Any) -> None:
    """Append one contract check row."""
    checks.append({"name": name, "ok": ok, "detail": detail})


def build_contract_report() -> dict[str, Any]:
    """Validate the H0-D handoff output contract."""
    ts_ms = int(time.time() * 1000)
    payload, present, error = load_json(INPUT_PATH)

    checks: list[dict[str, Any]] = []
    failed_checks: list[dict[str, Any]] = []

    add_check(checks, "report_exists", present, str(INPUT_PATH))
    if not present:
        failed_checks = [item for item in checks if not item["ok"]]
        return {
            "report_type": "bybit_local_trade_eligibility_handoff_contract_check",
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
        "handoff_type_expected",
        payload.get("handoff_type") == "bybit_local_trade_eligibility_handoff",
        payload.get("handoff_type"),
    )
    add_check(
        checks,
        "handoff_version_allowed",
        payload.get("handoff_version") in ALLOWED_HANDOFF_VERSIONS,
        payload.get("handoff_version"),
    )
    add_check(checks, "ts_ms_int", isinstance(payload.get("ts_ms"), int), payload.get("ts_ms"))
    add_check(checks, "exchange_bybit", payload.get("exchange") == "bybit", payload.get("exchange"))
    add_check(checks, "stage_h0d", payload.get("stage") == "H0-D", payload.get("stage"))
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
        "current_runtime_dict",
        isinstance(payload.get("current_runtime"), dict),
        type(payload.get("current_runtime")).__name__,
    )
    add_check(
        checks,
        "upstream_states_dict",
        isinstance(payload.get("upstream_states"), dict),
        type(payload.get("upstream_states")).__name__,
    )
    add_check(
        checks,
        "handoff_state_allowed",
        payload.get("handoff_state") in ALLOWED_HANDOFF_STATES,
        payload.get("handoff_state"),
    )
    add_check(
        checks,
        "allow_progress_bool",
        isinstance(payload.get("allow_progress_to_h1"), bool),
        payload.get("allow_progress_to_h1"),
    )
    add_check(
        checks,
        "next_step_hint_allowed",
        payload.get("next_step_hint") in ALLOWED_NEXT_STEP_HINTS,
        payload.get("next_step_hint"),
    )

    failed_checks = [item for item in checks if not item["ok"]]

    return {
        "report_type": "bybit_local_trade_eligibility_handoff_contract_check",
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
