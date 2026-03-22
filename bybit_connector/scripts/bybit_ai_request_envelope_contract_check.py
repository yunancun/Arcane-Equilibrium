#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MODULE_NOTE / 模块说明:
- role / 角色:
  Contract check for provider-native H1-E request envelope.
  面向 provider-native H1-E 请求封装的契约检查器。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


REQUEST_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate/bybit_ai_request_envelope_latest.json"
)
OUTPUT_LATEST_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate/bybit_ai_request_envelope_contract_latest.json"
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

    add_check("report_exists", REQUEST_PATH.exists(), str(REQUEST_PATH))

    payload: Dict[str, Any] = {}
    if REQUEST_PATH.exists():
        payload = read_json(REQUEST_PATH)

    add_check("request_type_expected", payload.get("request_type") == "bybit_ai_request_envelope", payload.get("request_type"))
    add_check("request_version_allowed", payload.get("request_version") in {"v2"}, payload.get("request_version"))
    add_check("ts_ms_int", isinstance(payload.get("ts_ms"), int), payload.get("ts_ms"))
    add_check("exchange_bybit", payload.get("exchange") == "bybit", payload.get("exchange"))
    add_check("stage_h1e", payload.get("stage") == "H1-E", payload.get("stage"))
    add_check("report_ok_bool", isinstance(payload.get("report_ok"), bool), payload.get("report_ok"))

    add_check("source_refs_dict", isinstance(payload.get("source_refs"), dict), type(payload.get("source_refs")).__name__)
    add_check("source_integrity_dict", isinstance(payload.get("source_integrity"), dict), type(payload.get("source_integrity")).__name__)
    add_check("request_summary_dict", isinstance(payload.get("request_summary"), dict), type(payload.get("request_summary")).__name__)
    add_check("provider_runtime_dict", isinstance(payload.get("provider_runtime"), dict), type(payload.get("provider_runtime")).__name__)
    add_check("budget_context_dict", isinstance(payload.get("budget_context"), dict), type(payload.get("budget_context")).__name__)
    add_check("request_payload_dict", isinstance(payload.get("request_payload"), dict), type(payload.get("request_payload")).__name__)
    add_check("warning_flags_list", isinstance(payload.get("warning_flags"), list), type(payload.get("warning_flags")).__name__)
    add_check("blocking_reasons_list", isinstance(payload.get("blocking_reasons"), list), type(payload.get("blocking_reasons")).__name__)

    request_state = payload.get("request_state")
    add_check(
        "request_state_allowed",
        request_state in {"ready_provider_native_ai_request", "blocked_provider_native_request"},
        request_state,
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

    allow_progress = payload.get("allow_progress_to_h1f_invocation")
    add_check("allow_progress_bool", isinstance(allow_progress, bool), allow_progress)

    request_payload = payload.get("request_payload", {}) or {}
    add_check("request_payload_provider_target_match", request_payload.get("provider_target") == provider_target, {
        "request_summary_provider_target": provider_target,
        "request_payload_provider_target": request_payload.get("provider_target"),
    })

    add_check("request_payload_model_name_str", isinstance(request_payload.get("model_name"), str), request_payload.get("model_name"))
    add_check("request_payload_max_output_tokens_int", isinstance(request_payload.get("max_output_tokens"), int), request_payload.get("max_output_tokens"))
    add_check("request_payload_system_prompt_str", isinstance(request_payload.get("system_prompt"), str), type(request_payload.get("system_prompt")).__name__)
    add_check("request_payload_user_prompt_str", isinstance(request_payload.get("user_prompt"), str), type(request_payload.get("user_prompt")).__name__)
    add_check("request_payload_response_contract_dict", isinstance(request_payload.get("response_contract"), dict), type(request_payload.get("response_contract")).__name__)

    report = {
        "report_type": "bybit_ai_request_envelope_contract_check",
        "report_version": "v2",
        "ts_ms": now_ms,
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    write_json(OUTPUT_LATEST_PATH, report)
    dated_path = OUTPUT_LATEST_PATH.with_name(
        f"bybit_ai_request_envelope_contract_{now_ms}.json"
    )
    write_json(dated_path, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUTPUT_LATEST_PATH}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
