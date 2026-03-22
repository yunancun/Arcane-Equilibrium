#!/usr/bin/env python3
"""
MODULE_NOTE / 模块说明:
- role / 角色:
  Contract checker for H1-C thought gate decision output.
  H1-C thought gate decision 输出对象的契约检查器。

- purpose / 目的:
  Validate schema, required keys, enum values, and core field types for
  bybit_thought_gate_decision_latest.json.
  校验 bybit_thought_gate_decision_latest.json 的结构、必需字段、枚举值和核心字段类型。

- upstream / 上游输入:
  runtime/bybit/thought_gate/bybit_thought_gate_decision_latest.json

- output / 输出:
  runtime/bybit/thought_gate/bybit_thought_gate_decision_contract_latest.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


INPUT_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate/"
    "bybit_thought_gate_decision_latest.json"
)
OUTPUT_DIR = INPUT_PATH.parent
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_thought_gate_decision_contract_latest.json"

ALLOWED_DECISION_VERSIONS = {"v1", "v2"}
ALLOWED_DECISION_STATES = {
    "decision_blocked",
    "decision_skip_no_local_trigger_model",
    "decision_skip_trigger_model_not_fired",
    "decision_ready_light_ai_call",
    "decision_ready_standard_ai_call",
}
ALLOWED_AI_TIERS = {
    "none",
    "light",
    "standard",
}


def load_json(path: Path) -> tuple[dict[str, Any], bool, str | None]:
    """
    Load JSON from disk.
    从磁盘读取 JSON。
    """
    if not path.exists():
        return {}, False, f"missing_file:{path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), True, None
    except Exception as exc:  # pragma: no cover
        return {}, False, f"json_load_error:{path}:{exc}"


def save_report(report: dict[str, Any]) -> tuple[Path, Path]:
    """
    Save latest and dated contract reports.
    保存 latest 与按时间戳归档的 contract report。
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = LATEST_OUTPUT_PATH
    dated_path = OUTPUT_DIR / f"bybit_thought_gate_decision_contract_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path


def add_check(checks: list[dict[str, Any]], name: str, ok: bool, detail: Any) -> None:
    """
    Append one check row.
    添加一条检查结果。
    """
    checks.append({"name": name, "ok": ok, "detail": detail})


def build_contract_report() -> dict[str, Any]:
    """
    Validate H1-C decision output structure.
    校验 H1-C decision 输出结构。
    """
    ts_ms = int(time.time() * 1000)
    payload, present, error = load_json(INPUT_PATH)

    checks: list[dict[str, Any]] = []
    failed_checks: list[dict[str, Any]] = []

    add_check(checks, "report_exists", present, str(INPUT_PATH))
    if not present:
        failed_checks = [item for item in checks if not item["ok"]]
        return {
            "report_type": "bybit_thought_gate_decision_contract_check",
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
        "decision_type_expected",
        payload.get("decision_type") == "bybit_thought_gate_decision",
        payload.get("decision_type"),
    )
    add_check(
        checks,
        "decision_version_allowed",
        payload.get("decision_version") in ALLOWED_DECISION_VERSIONS,
        payload.get("decision_version"),
    )
    add_check(checks, "ts_ms_int", isinstance(payload.get("ts_ms"), int), payload.get("ts_ms"))
    add_check(checks, "exchange_bybit", payload.get("exchange") == "bybit", payload.get("exchange"))
    add_check(checks, "stage_h1c", payload.get("stage") == "H1-C", payload.get("stage"))
    add_check(
        checks,
        "report_ok_bool",
        isinstance(payload.get("report_ok"), bool),
        payload.get("report_ok"),
    )
    add_check(
        checks,
        "source_refs_dict",
        isinstance(payload.get("source_refs"), dict),
        type(payload.get("source_refs")).__name__,
    )
    add_check(
        checks,
        "source_integrity_dict",
        isinstance(payload.get("source_integrity"), dict),
        type(payload.get("source_integrity")).__name__,
    )
    add_check(
        checks,
        "input_summary_dict",
        isinstance(payload.get("input_summary"), dict),
        type(payload.get("input_summary")).__name__,
    )
    add_check(
        checks,
        "decision_result_dict",
        isinstance(payload.get("decision_result"), dict),
        type(payload.get("decision_result")).__name__,
    )
    add_check(
        checks,
        "warning_flags_list",
        isinstance(payload.get("warning_flags"), list),
        type(payload.get("warning_flags")).__name__,
    )
    add_check(
        checks,
        "blocking_reasons_list",
        isinstance(payload.get("blocking_reasons"), list),
        type(payload.get("blocking_reasons")).__name__,
    )
    add_check(
        checks,
        "decision_state_allowed",
        payload.get("decision_state") in ALLOWED_DECISION_STATES,
        payload.get("decision_state"),
    )

    decision_result = payload.get("decision_result", {})
    add_check(
        checks,
        "selected_ai_tier_allowed",
        decision_result.get("selected_ai_tier") in ALLOWED_AI_TIERS,
        decision_result.get("selected_ai_tier"),
    )
    add_check(
        checks,
        "should_call_ai_bool",
        isinstance(decision_result.get("should_call_ai"), bool),
        decision_result.get("should_call_ai"),
    )
    add_check(
        checks,
        "allow_progress_bool",
        isinstance(decision_result.get("allow_progress_to_h1d_prompt"), bool),
        decision_result.get("allow_progress_to_h1d_prompt"),
    )

    failed_checks = [item for item in checks if not item["ok"]]

    return {
        "report_type": "bybit_thought_gate_decision_contract_check",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }


def main() -> None:
    """
    Entry point / 程序入口。
    """
    report = build_contract_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    latest_path, dated_path = save_report(report)
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
