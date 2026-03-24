#!/usr/bin/env python3
"""
MODULE_NOTE / 模块说明:
- role / 角色:
  Contract checker for H1-D AI prompt preparation output.
  H1-D AI prompt preparation 输出对象的契约检查器。

- purpose / 目的:
  Validate schema, required keys, enum values, and core field types for
  bybit_ai_prompt_prep_latest.json.
  校验 bybit_ai_prompt_prep_latest.json 的结构、必需字段、枚举值和核心字段类型。

- upstream / 上游输入:
  runtime/bybit/thought_gate/bybit_ai_prompt_prep_latest.json

- output / 输出:
  runtime/bybit/thought_gate/bybit_ai_prompt_prep_contract_latest.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir
from typing import Any


INPUT_PATH = Path(
    str(get_thought_gate_runtime_dir()) + "/"
    "bybit_ai_prompt_prep_latest.json"
)
OUTPUT_DIR = INPUT_PATH.parent
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_ai_prompt_prep_contract_latest.json"

ALLOWED_PREP_STATES = {
    "blocked_not_ready_for_prompt_prep",
    "ready_light_prompt_prep",
    "ready_standard_prompt_prep",
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
    dated_path = OUTPUT_DIR / f"bybit_ai_prompt_prep_contract_{report['ts_ms']}.json"
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
    Validate H1-D prompt prep output structure.
    校验 H1-D prompt prep 输出结构。
    """
    ts_ms = int(time.time() * 1000)
    payload, present, error = load_json(INPUT_PATH)

    checks: list[dict[str, Any]] = []
    failed_checks: list[dict[str, Any]] = []

    add_check(checks, "report_exists", present, str(INPUT_PATH))
    if not present:
        failed_checks = [item for item in checks if not item["ok"]]
        return {
            "report_type": "bybit_ai_prompt_prep_contract_check",
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
        "prep_type_expected",
        payload.get("prep_type") == "bybit_ai_prompt_prep",
        payload.get("prep_type"),
    )
    add_check(
        checks,
        "prep_version_v1",
        payload.get("prep_version") == "v1",
        payload.get("prep_version"),
    )
    add_check(checks, "ts_ms_int", isinstance(payload.get("ts_ms"), int), payload.get("ts_ms"))
    add_check(checks, "exchange_bybit", payload.get("exchange") == "bybit", payload.get("exchange"))
    add_check(checks, "stage_h1d", payload.get("stage") == "H1-D", payload.get("stage"))
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
        "readiness_summary_dict",
        isinstance(payload.get("readiness_summary"), dict),
        type(payload.get("readiness_summary")).__name__,
    )
    add_check(
        checks,
        "prompt_budget_dict",
        isinstance(payload.get("prompt_budget"), dict),
        type(payload.get("prompt_budget")).__name__,
    )
    add_check(
        checks,
        "fact_lines_list",
        isinstance(payload.get("fact_lines"), list),
        type(payload.get("fact_lines")).__name__,
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
        "prompt_payload_dict",
        isinstance(payload.get("prompt_payload"), dict),
        type(payload.get("prompt_payload")).__name__,
    )
    add_check(
        checks,
        "prep_state_allowed",
        payload.get("prep_state") in ALLOWED_PREP_STATES,
        payload.get("prep_state"),
    )
    add_check(
        checks,
        "allow_progress_bool",
        isinstance(payload.get("allow_progress_to_h1e_request"), bool),
        payload.get("allow_progress_to_h1e_request"),
    )

    readiness_summary = payload.get("readiness_summary", {})
    add_check(
        checks,
        "selected_ai_tier_allowed",
        readiness_summary.get("selected_ai_tier") in ALLOWED_AI_TIERS,
        readiness_summary.get("selected_ai_tier"),
    )

    failed_checks = [item for item in checks if not item["ok"]]

    return {
        "report_type": "bybit_ai_prompt_prep_contract_check",
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
