#!/usr/bin/env python3
"""
MODULE_NOTE:
- role: contract checker for H0 final audit output.
- purpose:
  Validate schema, required keys, enum values, and core field types for
  bybit_local_judgment_final_audit_latest.json.
- upstream:
  runtime/bybit/local_judgment/bybit_local_judgment_final_audit_latest.json
- output:
  runtime/bybit/local_judgment/bybit_local_judgment_final_audit_contract_latest.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


INPUT_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment/"
    "bybit_local_judgment_final_audit_latest.json"
)
OUTPUT_DIR = INPUT_PATH.parent
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_local_judgment_final_audit_contract_latest.json"

ALLOWED_FINAL_H0_STATES = {
    "structurally_valid_and_ready_for_h1",
    "structurally_valid_but_waiting_market_friction_upgrade",
    "h0_chain_requires_repair",
}
ALLOWED_RECOMMENDED_ACTIONS = {
    "progress_to_h1_thought_gate",
    "add_public_microstructure_and_cost_model",
    "repair_h0_chain_before_progression",
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
    dated_path = OUTPUT_DIR / f"bybit_local_judgment_final_audit_contract_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path


def add_check(checks: list[dict[str, Any]], name: str, ok: bool, detail: Any) -> None:
    """Append one contract check row."""
    checks.append({"name": name, "ok": ok, "detail": detail})


def build_contract_report() -> dict[str, Any]:
    """Validate the H0 final audit output contract."""
    ts_ms = int(time.time() * 1000)
    payload, present, error = load_json(INPUT_PATH)

    checks: list[dict[str, Any]] = []
    failed_checks: list[dict[str, Any]] = []

    add_check(checks, "report_exists", present, str(INPUT_PATH))
    if not present:
        failed_checks = [item for item in checks if not item["ok"]]
        return {
            "report_type": "bybit_local_judgment_final_audit_contract_check",
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
        "audit_type_expected",
        payload.get("audit_type") == "bybit_local_judgment_final_audit",
        payload.get("audit_type"),
    )
    add_check(
        checks,
        "audit_version_v1",
        payload.get("audit_version") == "v1",
        payload.get("audit_version"),
    )
    add_check(checks, "ts_ms_int", isinstance(payload.get("ts_ms"), int), payload.get("ts_ms"))
    add_check(checks, "exchange_bybit", payload.get("exchange") == "bybit", payload.get("exchange"))
    add_check(checks, "stage_h0final", payload.get("stage") == "H0-final", payload.get("stage"))
    add_check(
        checks,
        "overall_ok_bool",
        isinstance(payload.get("overall_ok"), bool),
        payload.get("overall_ok"),
    )
    add_check(
        checks,
        "h0_chain_ok_bool",
        isinstance(payload.get("h0_chain_ok"), bool),
        payload.get("h0_chain_ok"),
    )
    add_check(
        checks,
        "progression_ready_bool",
        isinstance(payload.get("progression_ready"), bool),
        payload.get("progression_ready"),
    )
    add_check(
        checks,
        "final_h0_state_allowed",
        payload.get("final_h0_state") in ALLOWED_FINAL_H0_STATES,
        payload.get("final_h0_state"),
    )
    add_check(
        checks,
        "recommended_action_allowed",
        payload.get("recommended_action") in ALLOWED_RECOMMENDED_ACTIONS,
        payload.get("recommended_action"),
    )
    add_check(
        checks,
        "checks_list",
        isinstance(payload.get("checks"), list),
        type(payload.get("checks")).__name__,
    )
    add_check(
        checks,
        "failed_checks_list",
        isinstance(payload.get("failed_checks"), list),
        type(payload.get("failed_checks")).__name__,
    )
    add_check(
        checks,
        "failed_count_int",
        isinstance(payload.get("failed_count"), int),
        payload.get("failed_count"),
    )
    add_check(
        checks,
        "upstream_summary_dict",
        isinstance(payload.get("upstream_summary"), dict),
        type(payload.get("upstream_summary")).__name__,
    )
    add_check(
        checks,
        "source_errors_list",
        isinstance(payload.get("source_errors"), list),
        type(payload.get("source_errors")).__name__,
    )

    failed_checks = [item for item in checks if not item["ok"]]

    return {
        "report_type": "bybit_local_judgment_final_audit_contract_check",
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
