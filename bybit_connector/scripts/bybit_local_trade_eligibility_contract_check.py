#!/usr/bin/env python3
"""
MODULE_NOTE:
- role: contract checker for H0-C local trade eligibility output.
- purpose:
  Validate schema, required keys, enum values, and core field types for
  bybit_local_trade_eligibility_latest.json.
- upstream:
  runtime/bybit/local_judgment/bybit_local_trade_eligibility_latest.json
- output:
  runtime/bybit/local_judgment/bybit_local_trade_eligibility_contract_latest.json
- notes:
  1) This checker validates structure, not trading desirability.
  2) A blocked result is acceptable if schema is valid.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


INPUT_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment/"
    "bybit_local_trade_eligibility_latest.json"
)
OUTPUT_DIR = INPUT_PATH.parent
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_local_trade_eligibility_contract_latest.json"

ALLOWED_TRADE_ELIGIBILITY_STATES = {
    "blocked_by_source_integrity",
    "blocked_by_runtime_guard",
    "blocked_by_market_friction",
    "blocked_by_risk_envelope",
    "eligible_for_governed_ai_review",
}

ALLOWED_RECOMMENDED_ACTIONS = {
    "repair_missing_sources_before_thought_gate",
    "repair_runtime_guard_before_thought_gate",
    "repair_market_friction_before_thought_gate",
    "repair_risk_envelope_before_thought_gate",
    "may_progress_to_h1_thought_gate",
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
    dated_path = OUTPUT_DIR / f"bybit_local_trade_eligibility_contract_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path


def add_check(checks: list[dict[str, Any]], name: str, ok: bool, detail: Any) -> None:
    """Append one contract check row."""
    checks.append({"name": name, "ok": ok, "detail": detail})

def build_contract_report() -> dict[str, Any]:
    """Validate the H0-C local trade eligibility output contract."""
    ts_ms = int(time.time() * 1000)
    payload, present, error = load_json(INPUT_PATH)

    checks: list[dict[str, Any]] = []
    failed_checks: list[dict[str, Any]] = []

    add_check(checks, "report_exists", present, str(INPUT_PATH))
    if not present:
        failed_checks = [item for item in checks if not item["ok"]]
        return {
            "report_type": "bybit_local_trade_eligibility_contract_check",
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
        "eligibility_type_expected",
        payload.get("eligibility_type") == "bybit_local_trade_eligibility",
        payload.get("eligibility_type"),
    )
    add_check(
        checks,
        "eligibility_version_v1",
        payload.get("eligibility_version") == "v1",
        payload.get("eligibility_version"),
    )
    add_check(checks, "ts_ms_int", isinstance(payload.get("ts_ms"), int), payload.get("ts_ms"))
    add_check(checks, "exchange_bybit", payload.get("exchange") == "bybit", payload.get("exchange"))
    add_check(checks, "stage_h0c", payload.get("stage") == "H0-C", payload.get("stage"))
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
        "upstream_states_dict",
        isinstance(payload.get("upstream_states"), dict),
        type(payload.get("upstream_states")).__name__,
    )
    add_check(
        checks,
        "trade_eligibility_state_allowed",
        payload.get("trade_eligibility_state") in ALLOWED_TRADE_ELIGIBILITY_STATES,
        payload.get("trade_eligibility_state"),
    )
    add_check(
        checks,
        "allow_progress_bool",
        isinstance(payload.get("allow_progress_to_thought_gate"), bool),
        payload.get("allow_progress_to_thought_gate"),
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

    failed_checks = [item for item in checks if not item["ok"]]

    return {
        "report_type": "bybit_local_trade_eligibility_contract_check",
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
