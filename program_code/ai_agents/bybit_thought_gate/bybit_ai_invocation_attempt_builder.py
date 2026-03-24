#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MODULE_NOTE / 模块说明:
- role / 角色:
  H1-F provider-native AI invocation attempt builder.
  H1-F 原生 provider AI 调用尝试构建器。

- purpose / 目的:
  Consume H1-E provider-native request envelope and perform:
  - dry-run only
  - or real provider-native SDK invocation

  消费 H1-E 的 provider-native 请求封装，并执行：
  - dry-run
  - 或真实的 provider-native SDK 调用

- design / 设计原则:
  1) No legacy H1F compatibility variables.
     不再使用旧 H1F 兼容变量。
  2) Route-selected provider_target/model from H1-E is the single truth.
     H1-E 中 route 选出的 provider_target/model 是唯一真源。
  3) Invocation layer only does transport work, not trade authorization.
     调用层只负责传输，不负责交易授权。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir
from typing import Any, Dict, List, Optional, Tuple

import httpx


RUNTIME_BASE = get_thought_gate_runtime_dir()
REQUEST_PATH = RUNTIME_BASE / "bybit_ai_request_envelope_latest.json"
OUTPUT_LATEST_PATH = RUNTIME_BASE / "bybit_ai_invocation_attempt_latest.json"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if raw == "":
        return default
    try:
        return int(raw)
    except Exception:
        return default


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if raw == "":
        return default
    try:
        return float(raw)
    except Exception:
        return default


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw == "":
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def preview_text(text: Optional[str], limit: int = 1200) -> Optional[str]:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def try_parse_json_object(text: Optional[str]) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    stripped = text.strip()

    # 先直接整体解析
    try:
        value = json.loads(stripped)
        if isinstance(value, dict):
            return value
    except Exception:
        pass

    # 再尝试抽取首尾 JSON object
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = stripped[start : end + 1]
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except Exception:
            return None

    return None


def sdk_object_to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict()
        except Exception:
            pass
    if isinstance(obj, dict):
        return obj
    return {"repr": repr(obj)}


def extract_openai_output_text(response: Any) -> Optional[str]:
    # 新版 SDK 常见快捷属性
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    # 尝试从 model_dump 结构中提取
    dumped = sdk_object_to_dict(response)
    if not isinstance(dumped, dict):
        return None

    parts: List[str] = []
    for item in dumped.get("output", []) or []:
        for content in item.get("content", []) or []:
            text_value = content.get("text")
            if isinstance(text_value, str) and text_value.strip():
                parts.append(text_value.strip())

    if parts:
        return "\n".join(parts).strip()

    return None


def extract_anthropic_output_text(message: Any) -> Optional[str]:
    dumped = sdk_object_to_dict(message)
    if not isinstance(dumped, dict):
        return None

    parts: List[str] = []
    for block in dumped.get("content", []) or []:
        if block.get("type") == "text":
            text_value = block.get("text")
            if isinstance(text_value, str) and text_value.strip():
                parts.append(text_value.strip())

    if parts:
        return "\n".join(parts).strip()

    return None


def invoke_openai_native(
    *,
    api_key: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int,
    temperature: float,
    connect_timeout_sec: float,
    read_timeout_sec: float,
    max_retries: int,
) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    from openai import OpenAI, NOT_GIVEN

    client = OpenAI(
        api_key=api_key,
        timeout=httpx.Timeout(
            connect=connect_timeout_sec,
            read=read_timeout_sec,
            write=read_timeout_sec,
            pool=connect_timeout_sec,
        ),
        max_retries=max_retries,
    )

    model_name_str = str(model_name)
    reasoning_effort = env_str("BYBIT_OPENAI_REASONING_EFFORT", "minimal").strip().lower() or "minimal"
    text_verbosity = env_str("BYBIT_OPENAI_TEXT_VERBOSITY", "low").strip().lower() or "low"
    omit_temperature_for_gpt5 = env_str("BYBIT_OPENAI_GPT5_OMIT_TEMPERATURE", "1").strip().lower() not in {"0", "false", "no", "off"}

    request_kwargs = {
        "model": model_name,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        ],
        "max_output_tokens": max_output_tokens,
    }

    if model_name_str.startswith("gpt-5"):
        request_kwargs["reasoning"] = {"effort": reasoning_effort}
        request_kwargs["text"] = {"verbosity": text_verbosity}
        request_kwargs["temperature"] = NOT_GIVEN if omit_temperature_for_gpt5 else temperature
    else:
        request_kwargs["temperature"] = temperature

    response = client.responses.create(**request_kwargs)

    dumped = sdk_object_to_dict(response)
    text = extract_openai_output_text(response)

    usage_summary = None
    if isinstance(dumped, dict):
        usage_summary = dumped.get("usage")

    return text, dumped, usage_summary

def invoke_anthropic_native(

    *,
    api_key: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int,
    temperature: float,
    connect_timeout_sec: float,
    read_timeout_sec: float,
    max_retries: int,
) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    from anthropic import Anthropic

    client = Anthropic(
        api_key=api_key,
        timeout=httpx.Timeout(
            connect=connect_timeout_sec,
            read=read_timeout_sec,
            write=read_timeout_sec,
            pool=connect_timeout_sec,
        ),
        max_retries=max_retries,
    )

    message = client.messages.create(
        model=model_name,
        max_tokens=max_output_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": user_prompt,
            }
        ],
    )

    dumped = sdk_object_to_dict(message)
    text = extract_anthropic_output_text(message)

    usage_summary = None
    if isinstance(dumped, dict):
        usage = dumped.get("usage")
        if isinstance(usage, dict):
            usage_summary = usage

    return text, dumped, usage_summary


def main() -> None:
    now_ms = int(time.time() * 1000)
    start_ts = time.perf_counter()

    request_payload = read_json(REQUEST_PATH)

    request_summary = request_payload.get("request_summary", {}) or {}
    provider_runtime = request_payload.get("provider_runtime", {}) or {}
    request_body = request_payload.get("request_payload", {}) or {}

    provider_target = str(request_body.get("provider_target", "")).strip()
    model_name = str(request_body.get("model_name", "")).strip()
    selected_ai_tier = str(request_body.get("selected_ai_tier", "skip")).strip()

    system_prompt = str(request_body.get("system_prompt", ""))
    user_prompt = str(request_body.get("user_prompt", ""))
    response_contract = request_body.get("response_contract", {}) or {}
    idempotency_key = str(request_body.get("idempotency_key", ""))

    max_output_tokens = int(request_body.get("max_output_tokens", 0) or 0)
    temperature = float(request_body.get("temperature", provider_runtime.get("temperature", 0.1)) or 0.1)

    connect_timeout_sec = float(provider_runtime.get("connect_timeout_sec", 1.0) or 1.0)
    read_timeout_sec = float(provider_runtime.get("read_timeout_sec", 5.0) or 5.0)
    max_retries = int(provider_runtime.get("max_retries", 0) or 0)

    dry_run = env_bool("BYBIT_AI_DRY_RUN", False)
    log_provider_errors = env_bool("BYBIT_AI_LOG_PROVIDER_ERRORS", True)

    blocking_reasons: List[str] = []
    warning_flags: List[str] = list(request_payload.get("warning_flags", []) or [])

    if not bool(request_payload.get("allow_progress_to_h1f_invocation", False)):
        blocking_reasons.append("request_envelope_disallows_h1f")

    if provider_target not in {"openai_native", "anthropic_native"}:
        blocking_reasons.append("provider_target_missing_or_invalid")

    if not model_name:
        blocking_reasons.append("model_name_missing")

    if max_output_tokens <= 0:
        blocking_reasons.append("max_output_tokens_invalid")

    provider_secret_name = ""
    provider_api_key = ""

    if provider_target == "openai_native":
        provider_secret_name = "OPENAI_API_KEY"
        provider_api_key = env_str("OPENAI_API_KEY", "")
        if not provider_api_key:
            blocking_reasons.append("openai_api_key_missing")
    elif provider_target == "anthropic_native":
        provider_secret_name = "ANTHROPIC_API_KEY"
        provider_api_key = env_str("ANTHROPIC_API_KEY", "")
        if not provider_api_key:
            blocking_reasons.append("anthropic_api_key_missing")

    invocation_attempted = False
    http_status = None
    latency_ms = None
    provider_response_present = False
    response_text_present = False
    parsed_json_present = False

    ai_response_text: Optional[str] = None
    raw_response_preview: Optional[str] = None
    usage_summary: Optional[Dict[str, Any]] = None
    parsed_json_object: Optional[Dict[str, Any]] = None

    invocation_state = "blocked_before_invocation"
    recommended_action = "resolve_invocation_blockers"
    allow_progress_to_h1g_response_check = False

    provider_exception_class: Optional[str] = None
    provider_exception_message: Optional[str] = None

    raw_provider_payload: Optional[Dict[str, Any]] = None

    if not blocking_reasons:
        if dry_run:
            latency_ms = int((time.perf_counter() - start_ts) * 1000)
            invocation_state = "dry_run_ready_not_sent"
            recommended_action = "switch_ai_dry_run_off_then_retry"
            allow_progress_to_h1g_response_check = False
        else:
            invocation_attempted = True
            try:
                if provider_target == "openai_native":
                    ai_response_text, raw_provider_payload, usage_summary = invoke_openai_native(
                        api_key=provider_api_key,
                        model_name=model_name,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        max_output_tokens=max_output_tokens,
                        temperature=temperature,
                        connect_timeout_sec=connect_timeout_sec,
                        read_timeout_sec=read_timeout_sec,
                        max_retries=max_retries,
                    )
                elif provider_target == "anthropic_native":
                    ai_response_text, raw_provider_payload, usage_summary = invoke_anthropic_native(
                        api_key=provider_api_key,
                        model_name=model_name,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        max_output_tokens=max_output_tokens,
                        temperature=temperature,
                        connect_timeout_sec=connect_timeout_sec,
                        read_timeout_sec=read_timeout_sec,
                        max_retries=max_retries,
                    )

                latency_ms = int((time.perf_counter() - start_ts) * 1000)
                provider_response_present = raw_provider_payload is not None
                response_text_present = bool(ai_response_text and ai_response_text.strip())

                parsed_json_object = try_parse_json_object(ai_response_text)
                parsed_json_present = parsed_json_object is not None

                raw_response_preview = preview_text(
                    json.dumps(raw_provider_payload, ensure_ascii=False, indent=2)
                    if raw_provider_payload is not None else None
                )

                if parsed_json_present:
                    invocation_state = "invocation_success_json_ready"
                    recommended_action = "may_progress_to_h1g_response_check"
                    allow_progress_to_h1g_response_check = True
                elif response_text_present:
                    invocation_state = "invocation_success_text_only"
                    recommended_action = "inspect_response_and_harden_json_contract"
                    allow_progress_to_h1g_response_check = False
                else:
                    invocation_state = "invocation_success_empty_response"
                    recommended_action = "inspect_empty_provider_response"
                    allow_progress_to_h1g_response_check = False

            except Exception as exc:
                latency_ms = int((time.perf_counter() - start_ts) * 1000)
                provider_exception_class = exc.__class__.__name__
                provider_exception_message = str(exc)
                raw_response_preview = preview_text(str(exc))
                invocation_state = "invocation_exception"
                recommended_action = "inspect_provider_native_invocation_exception"
                allow_progress_to_h1g_response_check = False

    response_extract: Dict[str, Any] = {
        "idempotency_key": idempotency_key,
        "ai_response_text": ai_response_text,
        "raw_response_preview": raw_response_preview if log_provider_errors else None,
        "usage_summary": usage_summary,
        "parsed_json_object": parsed_json_object,
        "response_contract": response_contract,
    }

    if provider_exception_class or provider_exception_message:
        response_extract["provider_exception"] = {
            "class_name": provider_exception_class,
            "message": provider_exception_message,
        }

    payload: Dict[str, Any] = {
        "invocation_type": "bybit_ai_invocation_attempt",
        "invocation_version": "v2",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H1-F",
        "report_ok": True,
        "source_refs": {
            "ai_request_envelope_path": str(REQUEST_PATH),
        },
        "source_integrity": {
            "ai_request_envelope_present": REQUEST_PATH.exists(),
            "source_errors": [],
        },
        "request_summary": {
            "prep_state": request_summary.get("prep_state", "unknown"),
            "selected_ai_tier": selected_ai_tier,
            "should_call_ai": request_summary.get("should_call_ai", False),
            "route_plan": request_summary.get("route_plan"),
            "provider_target": provider_target,
            "model_name": model_name,
        },
        "transport_summary": {
            "provider_target": provider_target,
            "sdk_mode": provider_runtime.get("sdk_mode"),
            "dry_run": dry_run,
            "connect_timeout_sec": connect_timeout_sec,
            "read_timeout_sec": read_timeout_sec,
            "max_retries": max_retries,
            "temperature": temperature,
            "provider_secret_name": provider_secret_name,
            "source_map": dict(provider_runtime.get("source_map", {}) or {}),
        },
        "attempt_result": {
            "invocation_attempted": invocation_attempted,
            "http_status": http_status,
            "latency_ms": latency_ms,
            "provider_response_present": provider_response_present,
            "response_text_present": response_text_present,
            "parsed_json_present": parsed_json_present,
        },
        "response_extract": response_extract,
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "invocation_state": invocation_state,
        "allow_progress_to_h1g_response_check": allow_progress_to_h1g_response_check,
        "recommended_action": recommended_action,
        "operator_message": (
            "H1-F provider-native invocation attempt built. "
            "This object records dry-run or real SDK invocation using the active provider target, "
            "without using legacy H1F compatibility variables."
        ),
    }

    write_json(OUTPUT_LATEST_PATH, payload)
    dated_path = OUTPUT_LATEST_PATH.with_name(
        f"bybit_ai_invocation_attempt_{now_ms}.json"
    )
    write_json(dated_path, payload)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUTPUT_LATEST_PATH}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
