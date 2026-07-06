#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MODULE_NOTE / 模块说明:
- 模块用途: WP4 thought-gate advisory_review_packet 回归测试。
- 覆盖: H1-E/H1-H/H1-I/handoff JSON 输出携带 inactive advisory role contract，
  且 contract check / acceptance suite 使用共享 validator fail-closed。
- 边界: 只在 tmp thought-gate runtime 写 fixture/output；不连 DB、不发 provider、不读 secret。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
_TG_DIR = _THIS.parents[1]
_PROGRAM_CODE = _THIS.parents[3]
_REPO = _THIS.parents[4]
_MISC_TOOLS = (
    _PROGRAM_CODE / "exchange_connectors/bybit_connector/misc_tools"
)
for _p in (_TG_DIR, _PROGRAM_CODE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from ml_training.advisory_review_packet import validate_advisory_review_packet  # noqa: E402

_RUNTIME_REL = "docker_projects/trading_services/runtime/bybit/thought_gate"


def _runtime_dir(srv_root: Path) -> Path:
    path = srv_root / _RUNTIME_REL
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(runtime_dir: Path, name: str, payload: dict) -> None:
    (runtime_dir / name).write_text(json.dumps(payload), encoding="utf-8")


def _read_json(runtime_dir: Path, name: str) -> dict:
    return json.loads((runtime_dir / name).read_text(encoding="utf-8"))


def _run_script(script_name: str, srv_root: Path) -> None:
    env = dict(os.environ)
    env["OPENCLAW_SRV_ROOT"] = str(srv_root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(_MISC_TOOLS),
            str(_TG_DIR),
            str(_PROGRAM_CODE),
            env.get("PYTHONPATH", ""),
        ]
    )
    proc = subprocess.run(
        [sys.executable, str(_TG_DIR / script_name)],
        cwd=str(_REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"{script_name} failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def _assert_role_contract(packet: dict) -> None:
    assert validate_advisory_review_packet(packet) is True
    assert packet["not_authority"] is True
    assert packet["inactive_review_packet"] is True
    assert packet["active"] is False
    assert packet["execution_authority"] == "not_granted"
    assert packet["decision_lease_emitted"] is False
    assert packet["demo_envelope_required_for_mutation"] is True
    assert packet["current_packet_grants_demo_mutation"] is False
    for key in (
        "no_order_mutation",
        "no_probe_mutation",
        "no_live_mutation",
        "no_mainnet_mutation",
        "no_runtime_mutation",
        "no_db_mutation",
        "no_secret_mutation",
        "no_promotion_mutation",
        "no_cost_gate_mutation",
        "no_strategy_config_mutation",
    ):
        assert packet[key] is True
    assert packet["input_hashes"]


def test_thought_gate_outputs_carry_inactive_advisory_review_packets(tmp_path):
    runtime_dir = _runtime_dir(tmp_path)
    _write_json(
        runtime_dir,
        "bybit_thought_gate_input_latest.json",
        {
            "policy_inputs": {
                "ai_daily_budget_usd": 5.0,
                "ai_per_call_budget_usd": 0.05,
            },
            "market_context": {"symbol": "ETHUSDT"},
        },
    )
    _write_json(
        runtime_dir,
        "bybit_thought_gate_policy_latest.json",
        {"policy_state": "unit_ready", "max_ai_call_tier": "skip"},
    )
    _write_json(
        runtime_dir,
        "bybit_ai_prompt_prep_latest.json",
        {
            "prep_state": "prompt_prep_ready",
            "readiness_summary": {
                "allow_progress_to_h1d_prompt": True,
                "should_call_ai": False,
            },
            "prompt_budget": {
                "require_json_response": True,
                "response_deadline_ms_hint": 1500,
            },
            "prompt_payload": {
                "system_prompt": "observe only",
                "user_prompt": "summarize no-call state",
                "response_contract": {"constraints": {"action_bias_allowed": ["flat_bias"]}},
            },
            "warning_flags": [],
        },
    )
    _write_json(
        runtime_dir,
        "bybit_ai_route_selector_latest.json",
        {
            "route_decision": {
                "selected_ai_tier": "skip",
                "route_plan": "route_skip",
                "route_reason": "unit_no_call",
                "env_binding_group": "ROUTE_SKIP",
            },
            "warning_flags": [],
        },
    )

    _run_script("bybit_ai_request_envelope_builder.py", tmp_path)
    request = _read_json(runtime_dir, "bybit_ai_request_envelope_latest.json")
    _assert_role_contract(request["advisory_review_packet"])
    assert request["advisory_review_packet"]["input_hashes"] == request["input_hashes"]
    assert {"request_prompt", "request_payload"} <= set(request["input_hashes"])

    _run_script("bybit_ai_request_envelope_contract_check.py", tmp_path)
    request_contract = _read_json(
        runtime_dir, "bybit_ai_request_envelope_contract_latest.json"
    )
    assert request_contract["overall_ok"] is True

    _write_json(
        runtime_dir,
        "bybit_ai_invocation_attempt_latest.json",
        {
            "invocation_type": "bybit_ai_invocation_attempt",
            "invocation_version": "v2",
            "request_summary": {
                "provider_target": "",
                "model_name": "",
                "selected_ai_tier": "skip",
                "route_plan": "route_skip",
                "should_call_ai": False,
            },
            "transport_summary": {"provider_target": ""},
            "attempt_result": {
                "invocation_attempted": False,
                "provider_response_present": False,
                "parsed_json_present": False,
            },
            "response_extract": {"parsed_json_object": None},
            "invocation_state": "blocked_before_invocation",
        },
    )
    _write_json(
        runtime_dir,
        "bybit_ai_response_check_latest.json",
        {
            "report_type": "bybit_ai_response_check",
            "report_version": "v2",
            "overall_ok": True,
            "terminal_mode": "legal_no_ai_call",
            "parsed_json_object": None,
        },
    )

    _run_script("bybit_ai_governed_decision.py", tmp_path)
    governed = _read_json(runtime_dir, "bybit_ai_governed_decision_latest.json")
    _assert_role_contract(governed["advisory_review_packet"])
    assert governed["governance_guards"]["execution_authority"] == "not_granted"
    assert governed["governance_guards"]["no_cost_gate_mutation"] is True

    _run_script("bybit_ai_governed_decision_contract_check.py", tmp_path)
    governed_contract = _read_json(
        runtime_dir, "bybit_ai_governed_decision_contract_latest.json"
    )
    assert governed_contract["overall_ok"] is True

    _run_script("bybit_thought_gate_acceptance_suite.py", tmp_path)
    acceptance = _read_json(runtime_dir, "bybit_thought_gate_acceptance_suite_latest.json")
    assert acceptance["overall_ok"] is True
    _assert_role_contract(acceptance["advisory_review_packet"])

    _write_json(
        runtime_dir,
        "bybit_thought_gate_regression_summary_latest.json",
        {
            "summary_ok": True,
            "recommended_next_build_order": ["H2. query_budget"],
        },
    )
    _run_script("bybit_thought_gate_handoff.py", tmp_path)
    handoff = _read_json(runtime_dir, "bybit_thought_gate_handoff_latest.json")
    _assert_role_contract(handoff["advisory_review_packet"])
    assert handoff["hard_safety_boundaries"]["execution_authority"] == "not_granted"
    assert handoff["hard_safety_boundaries"]["current_packet_grants_demo_mutation"] is False
