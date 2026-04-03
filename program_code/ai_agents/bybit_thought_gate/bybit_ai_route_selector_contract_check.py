#!/usr/bin/env python3
"""
MODULE_NOTE / 模块说明:
- role / 角色:
  Contract checker for H1-R AI route selector output.
  H1-R AI 自动路由选择器输出对象的契约检查器。

- purpose / 目的:
  Validate schema, required keys, enum values, and core field types for
  bybit_ai_route_selector_latest.json.
  校验 bybit_ai_route_selector_latest.json 的结构、必需字段、枚举值和核心字段类型。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import os
from typing import Any

RUNTIME_ROOT = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit")
THOUGHT_GATE_DIR = RUNTIME_ROOT / "thought_gate"

REPORT_PATH = THOUGHT_GATE_DIR / "bybit_ai_route_selector_latest.json"
OUT_LATEST = THOUGHT_GATE_DIR / "bybit_ai_route_selector_contract_latest.json"

ALLOWED_ROUTE_PLANS = {
    "route_skip",
    "route_a_light",
    "route_b_standard",
    "route_c_escalated_standard",
}

ALLOWED_TIERS = {"none", "light", "standard"}

ALLOWED_ROUTE_STATES = {
    "route_ready_light",
    "route_ready_standard",
    "route_blocked_or_skipped",
}


def now_ms() -> int:  # TODO: consolidate with app.utils.time_utils.now_ms
    return int(time.time() * 1000)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail: Any) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def write_report(payload: dict[str, Any]) -> tuple[Path, Path]:
    OUT_LATEST.parent.mkdir(parents=True, exist_ok=True)
    ts_ms = payload["ts_ms"]
    dated = OUT_LATEST.with_name(f"bybit_ai_route_selector_contract_{ts_ms}.json")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    OUT_LATEST.write_text(text + "\n", encoding="utf-8")
    dated.write_text(text + "\n", encoding="utf-8")
    return OUT_LATEST, dated


def main() -> None:
    checks: list[dict[str, Any]] = []

    report_exists = REPORT_PATH.exists()
    payload = load_json(REPORT_PATH) if report_exists else {}

    checks.append(check("report_exists", report_exists, str(REPORT_PATH)))

    checks.append(check(
        "route_type_expected",
        payload.get("route_type") == "bybit_ai_route_selector",
        payload.get("route_type"),
    ))
    checks.append(check(
        "route_version_v1",
        payload.get("route_version") == "v1",
        payload.get("route_version"),
    ))
    checks.append(check(
        "ts_ms_int",
        isinstance(payload.get("ts_ms"), int),
        payload.get("ts_ms"),
    ))
    checks.append(check(
        "exchange_bybit",
        payload.get("exchange") == "bybit",
        payload.get("exchange"),
    ))
    checks.append(check(
        "stage_h1r",
        payload.get("stage") == "H1-R",
        payload.get("stage"),
    ))
    checks.append(check(
        "report_ok_bool",
        isinstance(payload.get("report_ok"), bool),
        payload.get("report_ok"),
    ))
    checks.append(check(
        "source_refs_dict",
        isinstance(payload.get("source_refs"), dict),
        type(payload.get("source_refs")).__name__,
    ))
    checks.append(check(
        "source_integrity_dict",
        isinstance(payload.get("source_integrity"), dict),
        type(payload.get("source_integrity")).__name__,
    ))
    checks.append(check(
        "input_summary_dict",
        isinstance(payload.get("input_summary"), dict),
        type(payload.get("input_summary")).__name__,
    ))
    checks.append(check(
        "route_controls_dict",
        isinstance(payload.get("route_controls"), dict),
        type(payload.get("route_controls")).__name__,
    ))
    checks.append(check(
        "route_scores_dict",
        isinstance(payload.get("route_scores"), dict),
        type(payload.get("route_scores")).__name__,
    ))
    checks.append(check(
        "route_decision_dict",
        isinstance(payload.get("route_decision"), dict),
        type(payload.get("route_decision")).__name__,
    ))
    checks.append(check(
        "warning_flags_list",
        isinstance(payload.get("warning_flags"), list),
        type(payload.get("warning_flags")).__name__,
    ))
    checks.append(check(
        "blocking_reasons_list",
        isinstance(payload.get("blocking_reasons"), list),
        type(payload.get("blocking_reasons")).__name__,
    ))
    checks.append(check(
        "route_state_allowed",
        payload.get("route_state") in ALLOWED_ROUTE_STATES,
        payload.get("route_state"),
    ))

    route_decision = payload.get("route_decision", {}) or {}
    checks.append(check(
        "route_plan_allowed",
        route_decision.get("route_plan") in ALLOWED_ROUTE_PLANS,
        route_decision.get("route_plan"),
    ))
    checks.append(check(
        "selected_ai_tier_allowed",
        route_decision.get("selected_ai_tier") in ALLOWED_TIERS,
        route_decision.get("selected_ai_tier"),
    ))
    checks.append(check(
        "should_call_ai_bool",
        isinstance(route_decision.get("should_call_ai"), bool),
        route_decision.get("should_call_ai"),
    ))
    checks.append(check(
        "allow_progress_bool",
        isinstance(payload.get("allow_progress_to_h1e_request"), bool),
        payload.get("allow_progress_to_h1e_request"),
    ))

    failed_checks = [item for item in checks if not item["ok"]]
    result = {
        "report_type": "bybit_ai_route_selector_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms(),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    latest_path, dated_path = write_report(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
