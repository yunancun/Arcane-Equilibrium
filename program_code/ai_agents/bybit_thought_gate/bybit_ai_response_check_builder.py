#!/usr/bin/env python3
"""
MODULE_NOTE / 模块说明:
- role / 角色:
  H1-G AI response check builder / H1-G AI 响应检查构建器

- purpose / 目的:
  Read the latest H1-F invocation result, validate whether the AI response
  satisfies the requested JSON response contract, and produce a normalized
  handoff object for the next stage.
  读取最新 H1-F 调用结果，验证 AI 返回是否满足约定 JSON 契约，
  并生成面向下一阶段的标准化交接对象。

- design / 设计原则:
  1) Structural build success != semantic pass.
     结构构建成功不等于语义校验通过。
  2) H1-G only checks response-contract quality, not trading correctness.
     H1-G 仅检查响应契约质量，不评判交易观点本身对错。
  3) Output should be deterministic and easy to consume by H1-H.
     输出必须确定性，便于 H1-H 消费。
"""

from __future__ import annotations

import json
import time
from numbers import Number
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
INPUT_PATH = RUNTIME_DIR / "bybit_ai_invocation_attempt_latest.json"
LATEST_PATH = RUNTIME_DIR / "bybit_ai_response_check_latest.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def now_ms() -> int:
    return int(time.time() * 1000)


def is_number(value: Any) -> bool:
    return isinstance(value, Number) and not isinstance(value, bool)


def int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def main() -> int:
    ts_ms = now_ms()

    inv = read_json(INPUT_PATH)

    request_summary = inv.get("request_summary") or {}
    attempt_result = inv.get("attempt_result") or {}
    response_extract = inv.get("response_extract") or {}
    warning_flags = inv.get("warning_flags") or []

    parsed_json_object = response_extract.get("parsed_json_object")
    if not isinstance(parsed_json_object, dict):
        parsed_json_object = None

    response_contract = response_extract.get("response_contract") or {}
    required_fields = response_contract.get("required_fields") or []
    constraints = response_contract.get("constraints") or {}

    expected_analysis_mode = constraints.get("analysis_mode")
    allowed_action_bias = constraints.get("action_bias_allowed") or []
    max_key_reasons = int_or_default(constraints.get("max_key_reasons"), 999999)
    max_risk_notes = int_or_default(constraints.get("max_risk_notes"), 999999)
    max_why_not_trade = int_or_default(constraints.get("max_why_not_trade"), 999999)

    response_text_present = bool(attempt_result.get("response_text_present"))
    parsed_json_present = bool(attempt_result.get("parsed_json_present")) and parsed_json_object is not None

    required_fields_present = {
        field: (parsed_json_object is not None and field in parsed_json_object)
        for field in required_fields
    }
    required_fields_ok = all(required_fields_present.values()) if required_fields else parsed_json_object is not None

    analysis_mode_ok = (
        parsed_json_object is not None
        and expected_analysis_mode is not None
        and parsed_json_object.get("analysis_mode") == expected_analysis_mode
    )

    action_bias_ok = (
        parsed_json_object is not None
        and parsed_json_object.get("action_bias") in allowed_action_bias
    )

    confidence_ok = (
        parsed_json_object is not None
        and is_number(parsed_json_object.get("confidence_0_to_1"))
        and 0.0 <= float(parsed_json_object.get("confidence_0_to_1")) <= 1.0
    )

    edge_assessment_ok = (
        parsed_json_object is not None
        and is_number(parsed_json_object.get("edge_assessment_bps"))
    )

    def list_field_ok(name: str, max_items: int) -> tuple[bool, int]:
        if parsed_json_object is None:
            return False, -1
        value = parsed_json_object.get(name)
        if not isinstance(value, list):
            return False, -1
        if not all(isinstance(item, str) for item in value):
            return False, len(value)
        if len(value) > max_items:
            return False, len(value)
        return True, len(value)

    key_reasons_ok, key_reasons_count = list_field_ok("key_reasons", max_key_reasons)
    risk_notes_ok, risk_notes_count = list_field_ok("risk_notes", max_risk_notes)
    why_not_trade_ok, why_not_trade_count = list_field_ok("why_not_trade", max_why_not_trade)

    validation = {
        "required_fields_present": required_fields_present,
        "required_fields_ok": required_fields_ok,
        "analysis_mode_ok": analysis_mode_ok,
        "action_bias_ok": action_bias_ok,
        "confidence_ok": confidence_ok,
        "edge_assessment_ok": edge_assessment_ok,
        "key_reasons_ok": key_reasons_ok,
        "risk_notes_ok": risk_notes_ok,
        "why_not_trade_ok": why_not_trade_ok,
        "key_reasons_count": key_reasons_count,
        "risk_notes_count": risk_notes_count,
        "why_not_trade_count": why_not_trade_count,
    }

    failed_validation_checks = [
        name for name, ok in [
            ("required_fields_ok", required_fields_ok),
            ("analysis_mode_ok", analysis_mode_ok),
            ("action_bias_ok", action_bias_ok),
            ("confidence_ok", confidence_ok),
            ("edge_assessment_ok", edge_assessment_ok),
            ("key_reasons_ok", key_reasons_ok),
            ("risk_notes_ok", risk_notes_ok),
            ("why_not_trade_ok", why_not_trade_ok),
        ]
        if not ok
    ]

    blocking_reasons: list[str] = []
    if not response_text_present:
        blocking_reasons.append("response_text_missing")
    if response_text_present and not parsed_json_present:
        blocking_reasons.append("parsed_json_not_available")
    blocking_reasons.extend(failed_validation_checks)

    if not response_text_present:
        response_check_state = "response_missing"
        allow_progress_to_h1h = False
        normalized_response = None
        recommended_action = "inspect_h1f_invocation_and_response_text"
    elif parsed_json_present and not failed_validation_checks:
        response_check_state = "response_contract_pass"
        allow_progress_to_h1h = True
        normalized_response = (
            {field: parsed_json_object.get(field) for field in required_fields}
            if required_fields
            else parsed_json_object
        )
        recommended_action = "may_progress_to_h1h_ai_result_handoff"
    else:
        response_check_state = "response_contract_fail"
        allow_progress_to_h1h = False
        normalized_response = parsed_json_object
        recommended_action = "tighten_prompt_or_harden_response_parser"

    payload = {
        "response_type": "bybit_ai_response_check",
        "response_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "H1-G",
        "report_ok": True,
        "source_refs": {
            "ai_invocation_attempt_path": str(INPUT_PATH),
        },
        "source_integrity": {
            "ai_invocation_attempt_present": INPUT_PATH.exists(),
            "source_errors": [],
        },
        "request_summary": {
            "route_plan": request_summary.get("route_plan"),
            "provider_target": request_summary.get("provider_target"),
            "model_name": request_summary.get("model_name"),
            "selected_ai_tier": request_summary.get("selected_ai_tier"),
            "invocation_state": inv.get("invocation_state"),
        },
        "response_presence": {
            "response_text_present": response_text_present,
            "parsed_json_present": parsed_json_present,
            "provider_response_present": bool(attempt_result.get("provider_response_present")),
            "usage_summary_present": response_extract.get("usage_summary") is not None,
        },
        "contract_expectations": {
            "required_fields": required_fields,
            "constraints": constraints,
        },
        "validation": validation,
        "normalized_response": normalized_response,
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "response_check_state": response_check_state,
        "allow_progress_to_h1h": allow_progress_to_h1h,
        "recommended_action": recommended_action,
        "operator_message": (
            "H1-G AI response check built. This object verifies whether the provider-native "
            "AI response satisfies the requested JSON contract and prepares a normalized "
            "handoff object for H1-H."
        ),
    }

    dated_path = RUNTIME_DIR / f"bybit_ai_response_check_{ts_ms}.json"
    write_json(LATEST_PATH, payload)
    write_json(dated_path, payload)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved_latest={LATEST_PATH}")
    print(f"saved_dated={dated_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
