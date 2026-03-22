#!/usr/bin/env python3
"""
MODULE_NOTE:
- role: contract checker for H0-A local market friction output.
- purpose:
  Validate schema, required keys, enum values, and core field types for
  bybit_local_market_friction_latest.json.
- upstream:
  runtime/bybit/local_judgment/bybit_local_market_friction_latest.json
- output:
  runtime/bybit/local_judgment/bybit_local_market_friction_contract_latest.json
- notes:
  1) This checker validates structure, not trading desirability.
  2) A conservative blocked/observe-only result is acceptable if schema is valid.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


INPUT_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment/"
    "bybit_local_market_friction_latest.json"
)
OUTPUT_DIR = INPUT_PATH.parent
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_local_market_friction_contract_latest.json"

ALLOWED_FRICTION_VERSIONS = {"v1", "v2", "v3"}
ALLOWED_MARKET_FRICTION_STATES = {
    "blocked",
    "observe_only_missing_public_microstructure",
    "observe_only_limited_visibility",
    "eligible_for_next_gate",
}
ALLOWED_RECOMMENDED_ACTIONS = {
    "repair_blockers_before_trade_consideration",
    "keep_observe_only_and_add_public_market_inputs",
    "keep_observe_only_until_visibility_improves",
    "may_progress_to_local_risk_envelope_gate",
}
ALLOWED_COST_MODEL_STATES = {"configured", "unconfigured"}


def load_json(path: Path) -> tuple[dict[str, Any], bool, str | None]:
    """Load JSON from disk."""
    if not path.exists():
        return {}, False, f"missing_file:{path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), True, None
    except Exception as exc:  # pragma: no cover - defensive
        return {}, False, f"json_load_error:{path}:{exc}"


def save_report(report: dict[str, Any]) -> tuple[Path, Path]:
    """Write latest and dated contract reports."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = LATEST_OUTPUT_PATH
    dated_path = OUTPUT_DIR / f"bybit_local_market_friction_contract_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path


def add_check(checks: list[dict[str, Any]], name: str, ok: bool, detail: Any) -> None:
    """Append one contract check row."""
    checks.append({"name": name, "ok": ok, "detail": detail})


def build_contract_report() -> dict[str, Any]:
    """Validate the H0-A market friction output contract."""
    ts_ms = int(time.time() * 1000)
    payload, present, error = load_json(INPUT_PATH)

    checks: list[dict[str, Any]] = []
    failed_checks: list[dict[str, Any]] = []

    add_check(checks, "report_exists", present, str(INPUT_PATH))
    if not present:
        failed_checks = [item for item in checks if not item["ok"]]
        return {
            "report_type": "bybit_local_market_friction_contract_check",
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
        "friction_type_expected",
        payload.get("friction_type") == "bybit_local_market_friction",
        payload.get("friction_type"),
    )
    add_check(
        checks,
        "friction_version_allowed",
        payload.get("friction_version") in ALLOWED_FRICTION_VERSIONS,
        payload.get("friction_version"),
    )
    add_check(checks, "ts_ms_int", isinstance(payload.get("ts_ms"), int), payload.get("ts_ms"))
    add_check(checks, "exchange_bybit", payload.get("exchange") == "bybit", payload.get("exchange"))
    add_check(checks, "stage_h0a", payload.get("stage") == "H0-A", payload.get("stage"))
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
        "local_visibility_dict",
        isinstance(payload.get("local_visibility"), dict),
        type(payload.get("local_visibility")).__name__,
    )
    add_check(
        checks,
        "known_context_dict",
        isinstance(payload.get("known_context"), dict),
        type(payload.get("known_context")).__name__,
    )
    add_check(
        checks,
        "cost_model_dict",
        isinstance(payload.get("cost_model"), dict),
        type(payload.get("cost_model")).__name__,
    )
    add_check(
        checks,
        "microstructure_coverage_dict",
        isinstance(payload.get("microstructure_coverage"), dict),
        type(payload.get("microstructure_coverage")).__name__,
    )
    add_check(
        checks,
        "minimum_edge_gate_dict",
        isinstance(payload.get("minimum_edge_gate"), dict),
        type(payload.get("minimum_edge_gate")).__name__,
    )
    add_check(
        checks,
        "market_friction_state_allowed",
        payload.get("market_friction_state") in ALLOWED_MARKET_FRICTION_STATES,
        payload.get("market_friction_state"),
    )
    add_check(
        checks,
        "allow_progress_bool",
        isinstance(payload.get("allow_progress_to_trade_path"), bool),
        payload.get("allow_progress_to_trade_path"),
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
    add_check(
        checks,
        "required_next_integrations_list",
        isinstance(payload.get("required_next_integrations"), list),
        type(payload.get("required_next_integrations")).__name__,
    )

    cost_model = payload.get("cost_model", {})
    add_check(
        checks,
        "cost_model_state_allowed",
        cost_model.get("cost_model_state") in ALLOWED_COST_MODEL_STATES,
        cost_model.get("cost_model_state"),
    )

    microstructure = payload.get("microstructure_coverage", {})
    coverage_types_ok = all(isinstance(value, bool) for value in microstructure.values())
    add_check(checks, "microstructure_values_bool", coverage_types_ok, microstructure)

    failed_checks = [item for item in checks if not item["ok"]]

    return {
        "report_type": "bybit_local_market_friction_contract_check",
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
