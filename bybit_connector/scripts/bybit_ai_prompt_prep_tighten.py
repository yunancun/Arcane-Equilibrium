#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MODULE_NOTE / 模块说明:
- role / 角色:
  H1-D local prompt tightener / H1-D 本地 prompt 收紧器

- purpose / 目的:
  Read latest bybit_ai_prompt_prep object, then locally compress:
  1) fact lines
  2) warning lines
  3) system prompt / user prompt
  4) response contract list limits
  在不改坏原始 builder 结构的前提下，
  对最新 H1-D 产物做本地收紧和压缩。

- design / 设计原则:
  1) Keep schema compatible with current contract check.
     保持与当前 contract check 兼容。
  2) Prefer deterministic local compression before asking model to be concise.
     优先做本地确定性压缩，再要求模型简短输出。
  3) Keep raw JSON requirement explicit.
     明确要求输出裸 JSON。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


RUNTIME_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
LATEST_PATH = RUNTIME_DIR / "bybit_ai_prompt_prep_latest.json"


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(float(raw))
    except Exception:
        return default


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_fact_lines(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        if not isinstance(line, str):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k and k not in out:
            out[k] = v
    return out


def unique_keep_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if not isinstance(item, str):
            continue
        v = item.strip()
        if not v:
            continue
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def main() -> int:
    if not LATEST_PATH.exists():
        raise FileNotFoundError(f"missing latest prompt prep file: {LATEST_PATH}")

    payload = load_json(LATEST_PATH)

    readiness = payload.get("readiness_summary", {}) or {}
    selected_ai_tier = str(readiness.get("selected_ai_tier", "light")).strip() or "light"

    active_max_output_tokens = env_int("BYBIT_AI_ACTIVE_MAX_OUTPUT_TOKENS", 0)

    max_output_tokens_by_tier = {
        "light": env_int("BYBIT_AI_MAX_OUTPUT_TOKENS_LIGHT", 500),
        "standard": env_int("BYBIT_AI_MAX_OUTPUT_TOKENS_STANDARD", 700),
        "strong": env_int("BYBIT_AI_MAX_OUTPUT_TOKENS_STRONG", 900),
    }

    max_output_tokens = (
        active_max_output_tokens
        if active_max_output_tokens > 0
        else max_output_tokens_by_tier.get(selected_ai_tier, max_output_tokens_by_tier["light"])
    )

    # ===== local deterministic fact compression / 本地确定性事实压缩 =====
    fact_priority = [
        "exchange",
        "symbol",
        "system_mode",
        "execution_state",
        "market_friction_state",
        "risk_envelope_state",
        "trade_eligibility_state",
        "spread_bps",
        "volatility_bps",
        "slippage_buy_bps",
        "slippage_sell_bps",
        "recent_trade_count",
        "required_edge_bps",
        "total_cost_floor_bps",
    ]

    fact_map = parse_fact_lines(payload.get("fact_lines", []) or [])
    selected_fact_lines = [f"{k}={fact_map[k]}" for k in fact_priority if k in fact_map]

    # 如果太少，则回退补一些原始 facts
    if len(selected_fact_lines) < 8:
        original_lines = [x for x in (payload.get("fact_lines", []) or []) if isinstance(x, str) and x.strip()]
        for line in original_lines:
            if line not in selected_fact_lines:
                selected_fact_lines.append(line)
            if len(selected_fact_lines) >= 12:
                break

    # ===== local deterministic warning compression / 本地确定性 warning 压缩 =====
    warning_priority = [
        "recent_trade_last_price_missing",
        "recent_trade_last_ts_missing",
        "runtime_state_reference_old",
        "freshness_soft_warning_present",
    ]

    original_warnings = unique_keep_order(payload.get("warning_flags", []) or [])
    selected_warnings = []
    for w in warning_priority + original_warnings:
        if w not in selected_warnings:
            selected_warnings.append(w)
        if len(selected_warnings) >= 4:
            break

    facts_block = "\n".join(f"- {x}" for x in selected_fact_lines) if selected_fact_lines else "- no_facts_available"
    warnings_block = "\n".join(f"- {x}" for x in selected_warnings) if selected_warnings else "- none"

    response_contract = {
        "format": "json_object",
        "required_fields": [
            "analysis_mode",
            "market_regime",
            "action_bias",
            "confidence_0_to_1",
            "edge_assessment_bps",
            "key_reasons",
            "risk_notes",
            "why_not_trade",
        ],
        "constraints": {
            "analysis_mode": "observation_only",
            "action_bias_allowed": ["long_bias", "short_bias", "flat_bias"],
            "max_key_reasons": 4,
            "max_risk_notes": 4,
            "max_why_not_trade": 4,
            "tier": selected_ai_tier,
        },
    }

    system_prompt = (
        "You are a conservative trading analysis assistant operating in observation-only mode. "
        "You are NOT allowed to authorize live execution. "
        "Use only supplied facts. Do not infer missing data. "
        "Return raw JSON only. "
        "Do not wrap JSON in markdown fences. "
        "Do not add any text before or after the JSON object. "
        "Keep output compact and short."
    )

    user_prompt = (
        "Analyze this Bybit snapshot conservatively.\n"
        "If evidence is weak or data quality is limited, prefer flat_bias.\n"
        "Keep all text brief.\n"
        "Each item in key_reasons, risk_notes, and why_not_trade must be short.\n"
        "Return one JSON object only.\n\n"
        "FACTS:\n"
        f"{facts_block}\n\n"
        "WARNINGS:\n"
        f"{warnings_block}\n\n"
        "RESPONSE_RULES:\n"
        "- raw JSON only\n"
        "- no markdown fences\n"
        "- no prose outside JSON\n"
        "- confidence_0_to_1 must be numeric\n"
        "- edge_assessment_bps must be numeric\n"
        "- key_reasons max 4 items\n"
        "- risk_notes max 4 items\n"
        "- why_not_trade max 4 items\n"
        "- keep each list item concise\n\n"
        "RESPONSE_CONTRACT:\n"
        f"{json.dumps(response_contract, ensure_ascii=False, separators=(',', ':'))}"
    )

    prompt_budget = payload.get("prompt_budget", {}) or {}
    prompt_budget["max_output_tokens_hint"] = max_output_tokens
    prompt_budget["max_fact_count"] = len(selected_fact_lines)
    prompt_budget["require_json_response"] = True
    payload["prompt_budget"] = prompt_budget

    prompt_payload = payload.get("prompt_payload", {}) or {}
    prompt_payload["system_prompt"] = system_prompt
    prompt_payload["user_prompt"] = user_prompt
    prompt_payload["response_contract"] = response_contract
    payload["prompt_payload"] = prompt_payload

    payload["fact_lines"] = selected_fact_lines
    payload["warning_flags"] = selected_warnings
    payload["report_ok"] = True
    payload["operator_message"] = (
        "H1-D AI prompt prep locally tightened after builder. "
        "Facts/warnings compressed deterministically, raw JSON requirement hardened, "
        "and output contract narrowed for higher parse stability."
    )

    ts_ms = int(time.time() * 1000)
    payload["ts_ms"] = ts_ms

    dated_path = RUNTIME_DIR / f"bybit_ai_prompt_prep_{ts_ms}.json"
    dump_json(LATEST_PATH, payload)
    dump_json(dated_path, payload)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved_latest={LATEST_PATH}")
    print(f"saved_dated={dated_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
