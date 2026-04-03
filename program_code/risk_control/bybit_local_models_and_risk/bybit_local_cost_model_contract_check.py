#!/usr/bin/env python3
"""
MODULE_NOTE:
- role: contract checker for H0-E local cost model output.
- purpose:
  Validate schema, required keys, enum values, and core field types for
  bybit_local_cost_model_latest.json.
- upstream:
  runtime/bybit/local_judgment/bybit_local_cost_model_latest.json
- output:
  runtime/bybit/local_judgment/bybit_local_cost_model_contract_latest.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import os
from typing import Any


INPUT_PATH = Path(
    os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/local_judgment/"
    "bybit_local_cost_model_latest.json"
)
OUTPUT_DIR = INPUT_PATH.parent
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_local_cost_model_contract_latest.json"

ALLOWED_COST_MODEL_STATES = {
    "configured",
    "unconfigured",
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
    dated_path = OUTPUT_DIR / f"bybit_local_cost_model_contract_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path


def add_check(checks: list[dict[str, Any]], name: str, ok: bool, detail: Any) -> None:
    """Append one contract check row."""
    checks.append({"name": name, "ok": ok, "detail": detail})

def build_contract_report() -> dict[str, Any]:
    """Validate the H0-E local cost model output contract."""
    ts_ms = int(time.time() * 1000)
    payload, present, error = load_json(INPUT_PATH)

    checks: list[dict[str, Any]] = []
    failed_checks: list[dict[str, Any]] = []

    add_check(checks, "report_exists", present, str(INPUT_PATH))
    if not present:
        failed_checks = [item for item in checks if not item["ok"]]
        return {
            "report_type": "bybit_local_cost_model_contract_check",
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
        "cost_type_expected",
        payload.get("cost_type") == "bybit_local_cost_model",
        payload.get("cost_type"),
    )
    add_check(
        checks,
        "cost_version_v1",
        payload.get("cost_version") == "v1",
        payload.get("cost_version"),
    )
    add_check(checks, "ts_ms_int", isinstance(payload.get("ts_ms"), int), payload.get("ts_ms"))
    add_check(checks, "exchange_bybit", payload.get("exchange") == "bybit", payload.get("exchange"))
    add_check(checks, "stage_h0e", payload.get("stage") == "H0-E", payload.get("stage"))
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
        "config_dict",
        isinstance(payload.get("config"), dict),
        type(payload.get("config")).__name__,
    )
    add_check(
        checks,
        "derived_dict",
        isinstance(payload.get("derived"), dict),
        type(payload.get("derived")).__name__,
    )
    add_check(
        checks,
        "cost_model_state_allowed",
        payload.get("cost_model_state") in ALLOWED_COST_MODEL_STATES,
        payload.get("cost_model_state"),
    )
    add_check(
        checks,
        "allow_use_bool",
        isinstance(payload.get("allow_use_by_market_friction"), bool),
        payload.get("allow_use_by_market_friction"),
    )
    add_check(
        checks,
        "blocking_reasons_list",
        isinstance(payload.get("blocking_reasons"), list),
        type(payload.get("blocking_reasons")).__name__,
    )

    failed_checks = [item for item in checks if not item["ok"]]

    return {
        "report_type": "bybit_local_cost_model_contract_check",
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
