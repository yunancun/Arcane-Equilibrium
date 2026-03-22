#!/usr/bin/env python3
"""
MODULE_NOTE:
- role: contract checker for H0-F public microstructure output.
- purpose:
  Validate schema, required keys, enum values, and core field types for
  bybit_public_microstructure_latest.json.
- upstream:
  runtime/bybit/local_judgment/bybit_public_microstructure_latest.json
- output:
  runtime/bybit/local_judgment/bybit_public_microstructure_contract_latest.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


INPUT_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment/"
    "bybit_public_microstructure_latest.json"
)
OUTPUT_DIR = INPUT_PATH.parent
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_public_microstructure_contract_latest.json"

ALLOWED_MICROSTRUCTURE_STATES = {
    "blocked_public_fetch_failed",
    "partial_public_microstructure",
    "healthy_basic_public_microstructure",
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
    dated_path = OUTPUT_DIR / f"bybit_public_microstructure_contract_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path


def add_check(checks: list[dict[str, Any]], name: str, ok: bool, detail: Any) -> None:
    """Append one contract row."""
    checks.append({"name": name, "ok": ok, "detail": detail})

def build_contract_report() -> dict[str, Any]:
    """Validate the H0-F public microstructure output contract."""
    ts_ms = int(time.time() * 1000)
    payload, present, error = load_json(INPUT_PATH)

    checks: list[dict[str, Any]] = []
    failed_checks: list[dict[str, Any]] = []

    add_check(checks, "report_exists", present, str(INPUT_PATH))
    if not present:
        failed_checks = [item for item in checks if not item["ok"]]
        return {
            "report_type": "bybit_public_microstructure_contract_check",
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
        "public_type_expected",
        payload.get("public_type") == "bybit_public_microstructure",
        payload.get("public_type"),
    )
    add_check(
        checks,
        "public_version_v1",
        payload.get("public_version") == "v1",
        payload.get("public_version"),
    )
    add_check(checks, "ts_ms_int", isinstance(payload.get("ts_ms"), int), payload.get("ts_ms"))
    add_check(checks, "exchange_bybit", payload.get("exchange") == "bybit", payload.get("exchange"))
    add_check(checks, "stage_h0f", payload.get("stage") == "H0-F", payload.get("stage"))
    add_check(
        checks,
        "report_ok_bool",
        isinstance(payload.get("report_ok"), bool),
        payload.get("report_ok"),
    )
    add_check(
        checks,
        "runtime_context_dict",
        isinstance(payload.get("runtime_context"), dict),
        type(payload.get("runtime_context")).__name__,
    )
    add_check(
        checks,
        "config_dict",
        isinstance(payload.get("config"), dict),
        type(payload.get("config")).__name__,
    )
    add_check(
        checks,
        "fetch_status_dict",
        isinstance(payload.get("fetch_status"), dict),
        type(payload.get("fetch_status")).__name__,
    )
    add_check(
        checks,
        "derived_dict",
        isinstance(payload.get("derived"), dict),
        type(payload.get("derived")).__name__,
    )
    add_check(
        checks,
        "coverage_dict",
        isinstance(payload.get("coverage"), dict),
        type(payload.get("coverage")).__name__,
    )
    add_check(
        checks,
        "microstructure_state_allowed",
        payload.get("microstructure_state") in ALLOWED_MICROSTRUCTURE_STATES,
        payload.get("microstructure_state"),
    )
    add_check(
        checks,
        "allow_use_bool",
        isinstance(payload.get("allow_use_by_h0"), bool),
        payload.get("allow_use_by_h0"),
    )

    coverage = payload.get("coverage", {})
    coverage_bool_ok = all(isinstance(value, bool) for value in coverage.values())
    add_check(checks, "coverage_values_bool", coverage_bool_ok, coverage)

    failed_checks = [item for item in checks if not item["ok"]]

    return {
        "report_type": "bybit_public_microstructure_contract_check",
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
