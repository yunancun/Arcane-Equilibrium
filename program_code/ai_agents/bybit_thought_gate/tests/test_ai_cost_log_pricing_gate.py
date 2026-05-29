#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MODULE_NOTE / 模块说明:
- 模块用途: H5-A bybit_ai_cost_log 治理门控单元测试（MED-2）。
- 覆盖 pricing_not_bound_for_paid_call 这条此前未测的 fail-closed 路径:
  * 付费 provider + pricing 未绑定 → log_ok=False（阻断，不让无法核算的付费支出过 cost gate）。
  * 免费/本地 provider + pricing 未绑定 → 仅 warn，不阻断（根原则 14：基线无需付费服务）。
- 依赖: 以 subprocess 跑 cost_log（脚本从 runtime dir 读 5 份输入 JSON、写报告）。
  OPENCLAW_SRV_ROOT 指向 tmp 根，PYTHONPATH 加入 misc_tools 以解析 helper import。
  不连真实 PG、不发起 provider HTTP、不设任何 pricing env（故 pricing 必然未绑定）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
_TG_DIR = _THIS.parents[1]
_COST_LOG = _TG_DIR / "bybit_ai_cost_log.py"
_MISC_TOOLS = (
    _TG_DIR.parents[1]
    / "exchange_connectors/bybit_connector/misc_tools"
)
_RUNTIME_REL = "docker_projects/trading_services/runtime/bybit/thought_gate"


def _write_inputs(runtime_dir: Path, *, provider_target: str) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)

    def w(name: str, obj: dict) -> None:
        (runtime_dir / name).write_text(json.dumps(obj), encoding="utf-8")

    # H1/H4 闭合 + budget 齐备，使唯一的差异点落在 pricing 门控上。
    w("bybit_thought_gate_final_audit_latest.json",
      {"audit_summary": {"runtime_still_protected": True}})
    w("bybit_query_budget_runtime_latest.json",
      {"runtime_summary": {}, "runtime_assessment": {}, "warning_flags": []})
    w("bybit_compute_governor_final_audit_latest.json",
      {"audit_summary": {"h4_stage_closed": True}})
    w("bybit_ai_request_envelope_latest.json",
      {"request_summary": {
          "provider_target": provider_target,
          "model_name": "test-model",
          "selected_ai_tier": "standard",
          "route_plan": "route_b_standard",
          "should_call_ai": True,
      },
       "request_payload": {"max_output_tokens": 512},
       "budget_context": {"ai_daily_budget_usd": 5.0, "ai_per_call_budget_usd": 0.05}})
    w("bybit_ai_invocation_attempt_latest.json",
      {"transport_summary": {},
       "attempt_result": {
           "invocation_attempted": True,
           "provider_response_present": True,
           "latency_ms": 300,
       },
       "response_extract": {"usage_summary": {
           "input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
       }}})


def _run_cost_log(srv_root: Path) -> dict:
    env = dict(os.environ)
    env["OPENCLAW_SRV_ROOT"] = str(srv_root)
    # cost_log 用 `from bybit_path_policy import ...` 等 sibling import，需 misc_tools 在 path。
    env["PYTHONPATH"] = str(_MISC_TOOLS) + os.pathsep + env.get("PYTHONPATH", "")
    # 不设任何 BYBIT_*_INPUT_USD_PER_1M / *_OUTPUT_USD_PER_1M → pricing table 必未绑定。
    for k in list(env.keys()):
        if k.startswith("BYBIT_") and ("INPUT_USD" in k or "OUTPUT_USD" in k):
            env.pop(k)
    proc = subprocess.run(
        [sys.executable, str(_COST_LOG)],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, f"cost_log failed: {proc.stderr}"
    report_path = srv_root / _RUNTIME_REL / "bybit_ai_cost_log_latest.json"
    return json.loads(report_path.read_text(encoding="utf-8"))


def test_paid_unpriced_call_blocks(tmp_path):
    runtime_dir = tmp_path / _RUNTIME_REL
    _write_inputs(runtime_dir, provider_target="openai_native")
    report = _run_cost_log(tmp_path)
    # 付费 + 未定价：必 fail-closed。
    assert report["log_ok"] is False
    assert "pricing_not_bound_for_paid_call" in report["blocking_reasons"]
    assert report["allow_progress_to_h5b_governance_audit"] is False


def test_free_unpriced_call_warns_only(tmp_path):
    runtime_dir = tmp_path / _RUNTIME_REL
    _write_inputs(runtime_dir, provider_target="ollama_local")
    report = _run_cost_log(tmp_path)
    # 免费/本地 + 未定价：不阻断（仅 pricing 未绑定的 soft warn）。
    assert report["log_ok"] is True
    assert "pricing_not_bound_for_paid_call" not in report["blocking_reasons"]
    assert "provider_pricing_table_not_bound_in_mainline" in report["warning_flags"]
