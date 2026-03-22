#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MODULE_NOTE / 模块说明:
- role / 角色:
  Contract check for provider-native H1-F invocation attempt.
  面向 provider-native H1-F 调用尝试对象的契约检查器。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


INVOCATION_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate/bybit_ai_invocation_attempt_latest.json"
)
OUTPUT_LATEST_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate/bybit_ai_invocation_attempt_contract_latest.json"
)


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    now_ms = int(time.time() * 1000)

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    def add_check(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failed_checks.append(name)

    add_check("report_exists", INVOCATION_PATH.exists(), str(INVOCATION_PATH))

    payload: Dict[str, Any] = {}
    if INVOCATION_PATH.exists():
        payload = read_json(INVOCATION_PATH)

    add_check("invocation_type_expected", payload.get("invocation_type") == "bybit_ai_invocation_attempt", payload.get("invocation_type"))
    add_check("invocation_version_allowed", payload.get("invocation_version") in {"v2"}, payload.get("invocation_version"))
    add_check("ts_ms_int", isinstance(payload.get("ts_ms"), int), payload.get("ts_ms"))
    add_check("exchange_bybit", payload.get("exchange") == "bybit", payload.get("exchange"))
    add_check("stage_h1f", payload.get("stage") == "H1-F", payload.get("stage"))
    add_check("report_ok_bool", isinstance(payload.get("report_ok"), bool), payload.get("report_ok"))

    add_check("source_refs_dict", isinstance(payload.get("source_refs"), dict), type(payload.get("source_refs")).__name__)
    add_check("source_integrity_dict", isinstance(payload.get("source_integrity"), dict), type(payload.get("source_integrity")).__name__)
    add_check("request_summary_dict", isinstance(payload.get("request_summary"), dict), type(payload.get("request_summary")).__name__)
    add_check("transport_summary_dict", isinstance(payload.get("transport_summary"), dict), type(payload.get("transport_summary")).__name__)
    add_check("attempt_result_dict", isinstance(payload.get("attempt_result"), dict), type(payload.get("attempt_result")).__name__)
    add_check("response_extract_dict", isinstance(payload.get("response_extract"), dict), type(payload.get("response_extract")).__name__)
    add_check("warning_flags_list", isinstance(payload.get("warning_flags"), list), type(payload.get("warning_flags")).__name__)
    add_check("blocking_reasons_list", isinstance(payload.get("blocking_reasons"), list), type(payload.get("blocking_reasons")).__name__)

    invocation_state = payload.get("invocation_state")
    add_check(
        "invocation_state_allowed",
        invocation_state in {
            "blocked_before_invocation",
            "dry_run_ready_not_sent",
            "invocation_success_json_ready",
            "invocation_success_text_only",
            "invocation_success_empty_response",
            "invocation_exception",
        },
        invocation_state,
    )

    provider_target = ((payload.get("request_summary", {}) or {}).get("provider_target"))
    add_check(
        "provider_target_allowed",
        provider_target in {"anthropic_native", "openai_native", ""},
        provider_target,
    )

    selected_ai_tier = ((payload.get("request_summary", {}) or {}).get("selected_ai_tier"))
    add_check(
        "selected_ai_tier_allowed",
        selected_ai_tier in {"light", "standard", "strong", "skip"},
        selected_ai_tier,
    )

    allow_progress = payload.get("allow_progress_to_h1g_response_check")
    add_check("allow_progress_bool", isinstance(allow_progress, bool), allow_progress)

    transport_summary = payload.get("transport_summary", {}) or {}
    add_check("transport_provider_target_match", transport_summary.get("provider_target") == provider_target, {
        "request_summary_provider_target": provider_target,
        "transport_provider_target": transport_summary.get("provider_target"),
    })

    attempt_result = payload.get("attempt_result", {}) or {}
    add_check("invocation_attempted_bool", isinstance(attempt_result.get("invocation_attempted"), bool), attempt_result.get("invocation_attempted"))
    add_check("provider_response_present_bool", isinstance(attempt_result.get("provider_response_present"), bool), attempt_result.get("provider_response_present"))
    add_check("response_text_present_bool", isinstance(attempt_result.get("response_text_present"), bool), attempt_result.get("response_text_present"))
    add_check("parsed_json_present_bool", isinstance(attempt_result.get("parsed_json_present"), bool), attempt_result.get("parsed_json_present"))

    response_extract = payload.get("response_extract", {}) or {}
    add_check("response_extract_idempotency_key_str", isinstance(response_extract.get("idempotency_key"), str), type(response_extract.get("idempotency_key")).__name__)
    add_check("response_extract_response_contract_dict", isinstance(response_extract.get("response_contract"), dict), type(response_extract.get("response_contract")).__name__)

    report = {
        "report_type": "bybit_ai_invocation_attempt_contract_check",
        "report_version": "v2",
        "ts_ms": now_ms,
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    write_json(OUTPUT_LATEST_PATH, report)
    dated_path = OUTPUT_LATEST_PATH.with_name(
        f"bybit_ai_invocation_attempt_contract_{now_ms}.json"
    )
    write_json(dated_path, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUTPUT_LATEST_PATH}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
