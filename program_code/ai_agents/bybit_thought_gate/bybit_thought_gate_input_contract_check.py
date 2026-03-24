#!/usr/bin/env python3
"""
MODULE_NOTE / 模块说明:
- role / 角色:
  Contract checker for H1-A thought gate input output.
  H1-A thought gate 输入对象的契约检查器。

- purpose / 目的:
  Validate schema, required keys, enum values, and core field types for
  bybit_thought_gate_input_latest.json.
  校验 bybit_thought_gate_input_latest.json 的结构、必需字段、枚举值和核心字段类型。

- upstream / 上游输入:
  runtime/bybit/thought_gate/bybit_thought_gate_input_latest.json

- output / 输出:
  runtime/bybit/thought_gate/bybit_thought_gate_input_contract_latest.json

- notes / 备注:
  1) This checker validates structure, not final AI-call desirability.
     本检查器只校验结构，不判断“是否值得调用 AI”。
  2) A blocked or not-yet-ready input state is acceptable if schema is valid.
     即使 input_state 是 blocked，只要结构正确，也属于有效输出。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir
from typing import Any


INPUT_PATH = Path(
    str(get_thought_gate_runtime_dir()) + "/"
    "bybit_thought_gate_input_latest.json"
)
OUTPUT_DIR = INPUT_PATH.parent
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_thought_gate_input_contract_latest.json"

ALLOWED_INPUT_STATES = {
    "blocked_missing_sources",
    "blocked_h0_not_ready",
    "blocked_stale_public_microstructure",
    "blocked_stale_h0_final_audit",
    "ready_for_thought_gate_policy_evaluation",
}


def load_json(path: Path) -> tuple[dict[str, Any], bool, str | None]:
    """
    Load JSON payload from disk.
    从磁盘读取 JSON 数据。
    """
    if not path.exists():
        return {}, False, f"missing_file:{path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), True, None
    except Exception as exc:  # pragma: no cover
        return {}, False, f"json_load_error:{path}:{exc}"


def save_report(report: dict[str, Any]) -> tuple[Path, Path]:
    """
    Write latest and dated contract reports.
    写出 latest 与按时间戳归档的 contract report。
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = LATEST_OUTPUT_PATH
    dated_path = OUTPUT_DIR / f"bybit_thought_gate_input_contract_{report['ts_ms']}.json"
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
    Validate the H1-A thought gate input contract.
    校验 H1-A thought gate 输入对象的契约结构。
    """
    ts_ms = int(time.time() * 1000)
    payload, present, error = load_json(INPUT_PATH)

    checks: list[dict[str, Any]] = []
    failed_checks: list[dict[str, Any]] = []

    add_check(checks, "report_exists", present, str(INPUT_PATH))
    if not present:
        failed_checks = [item for item in checks if not item["ok"]]
        return {
            "report_type": "bybit_thought_gate_input_contract_check",
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
        "input_type_expected",
        payload.get("input_type") == "bybit_thought_gate_input",
        payload.get("input_type"),
    )
    add_check(
        checks,
        "input_version_v1",
        payload.get("input_version") == "v1",
        payload.get("input_version"),
    )
    add_check(checks, "ts_ms_int", isinstance(payload.get("ts_ms"), int), payload.get("ts_ms"))
    add_check(checks, "exchange_bybit", payload.get("exchange") == "bybit", payload.get("exchange"))
    add_check(checks, "stage_h1a", payload.get("stage") == "H1-A", payload.get("stage"))
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
        "h0_readiness_dict",
        isinstance(payload.get("h0_readiness"), dict),
        type(payload.get("h0_readiness")).__name__,
    )
    add_check(
        checks,
        "runtime_context_dict",
        isinstance(payload.get("runtime_context"), dict),
        type(payload.get("runtime_context")).__name__,
    )
    add_check(
        checks,
        "local_gate_context_dict",
        isinstance(payload.get("local_gate_context"), dict),
        type(payload.get("local_gate_context")).__name__,
    )
    add_check(
        checks,
        "market_context_dict",
        isinstance(payload.get("market_context"), dict),
        type(payload.get("market_context")).__name__,
    )
    add_check(
        checks,
        "cost_context_dict",
        isinstance(payload.get("cost_context"), dict),
        type(payload.get("cost_context")).__name__,
    )
    add_check(
        checks,
        "policy_inputs_dict",
        isinstance(payload.get("policy_inputs"), dict),
        type(payload.get("policy_inputs")).__name__,
    )
    add_check(
        checks,
        "freshness_dict",
        isinstance(payload.get("freshness"), dict),
        type(payload.get("freshness")).__name__,
    )
    add_check(
        checks,
        "input_state_allowed",
        payload.get("input_state") in ALLOWED_INPUT_STATES,
        payload.get("input_state"),
    )
    add_check(
        checks,
        "allow_progress_bool",
        isinstance(payload.get("allow_progress_to_h1b_policy"), bool),
        payload.get("allow_progress_to_h1b_policy"),
    )
    add_check(
        checks,
        "operator_flags_list",
        isinstance(payload.get("operator_flags"), list),
        type(payload.get("operator_flags")).__name__,
    )

    failed_checks = [item for item in checks if not item["ok"]]

    return {
        "report_type": "bybit_thought_gate_input_contract_check",
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
