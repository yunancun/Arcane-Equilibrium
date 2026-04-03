#!/usr/bin/env python3
"""
MODULE_NOTE / 模块说明:
- role / 角色:
  Contract checker for H2-A local trigger model output.
  H2-A 本地触发模型输出对象的契约检查器。

- purpose / 目的:
  Validate schema, required keys, enum values, and core field types for
  bybit_local_trigger_model_latest.json.
  校验 bybit_local_trigger_model_latest.json 的结构、必需字段、枚举值和核心字段类型。

- upstream / 上游输入:
  runtime/bybit/trigger_model/bybit_local_trigger_model_latest.json

- output / 输出:
  runtime/bybit/trigger_model/bybit_local_trigger_model_contract_latest.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import os
from typing import Any


INPUT_PATH = Path(
    os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/trigger_model/"
    "bybit_local_trigger_model_latest.json"
)
OUTPUT_DIR = INPUT_PATH.parent
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_local_trigger_model_contract_latest.json"

ALLOWED_TRIGGER_STATES = {
    "blocked_not_policy_ready",
    "not_triggered_insufficient_market_quality",
    "not_triggered_low_regime_interest",
    "triggered_light_ai_review",
    "triggered_standard_ai_review",
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
    dated_path = OUTPUT_DIR / f"bybit_local_trigger_model_contract_{report['ts_ms']}.json"
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
    Validate H2-A trigger model output.
    校验 H2-A trigger model 输出结构。
    """
    ts_ms = int(time.time() * 1000)
    payload, present, error = load_json(INPUT_PATH)

    checks: list[dict[str, Any]] = []
    failed_checks: list[dict[str, Any]] = []

    add_check(checks, "report_exists", present, str(INPUT_PATH))
    if not present:
        failed_checks = [item for item in checks if not item["ok"]]
        return {
            "report_type": "bybit_local_trigger_model_contract_check",
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
        "trigger_type_expected",
        payload.get("trigger_type") == "bybit_local_trigger_model",
        payload.get("trigger_type"),
    )
    add_check(
        checks,
        "trigger_version_v1",
        payload.get("trigger_version") == "v1",
        payload.get("trigger_version"),
    )
    add_check(checks, "ts_ms_int", isinstance(payload.get("ts_ms"), int), payload.get("ts_ms"))
    add_check(checks, "exchange_bybit", payload.get("exchange") == "bybit", payload.get("exchange"))
    add_check(checks, "stage_h2a", payload.get("stage") == "H2-A", payload.get("stage"))
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
        "trigger_thresholds_dict",
        isinstance(payload.get("trigger_thresholds"), dict),
        type(payload.get("trigger_thresholds")).__name__,
    )
    add_check(
        checks,
        "feature_snapshot_dict",
        isinstance(payload.get("feature_snapshot"), dict),
        type(payload.get("feature_snapshot")).__name__,
    )
    add_check(
        checks,
        "scores_dict",
        isinstance(payload.get("scores"), dict),
        type(payload.get("scores")).__name__,
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
        "trigger_state_allowed",
        payload.get("trigger_state") in ALLOWED_TRIGGER_STATES,
        payload.get("trigger_state"),
    )
    add_check(
        checks,
        "should_trigger_ai_review_bool",
        isinstance(payload.get("should_trigger_ai_review"), bool),
        payload.get("should_trigger_ai_review"),
    )
    add_check(
        checks,
        "suggested_ai_tier_allowed",
        payload.get("suggested_ai_tier") in ALLOWED_AI_TIERS,
        payload.get("suggested_ai_tier"),
    )

    failed_checks = [item for item in checks if not item["ok"]]

    return {
        "report_type": "bybit_local_trigger_model_contract_check",
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
