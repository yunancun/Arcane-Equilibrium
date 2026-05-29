#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MODULE_NOTE / 模块说明:
- 模块用途: H1-F apply_ledger_governance 治理决策单元测试（MED-2）。
- 覆盖此前未测的账本写失败分叉:
  * 付费调用 ledger ok=False → 加 invocation_ledger_write_failed blocker
    + allow_progress_to_h1g_response_check=False（fail-closed，禁止进度）。
  * 本地/Ollama 调用 ledger ok=True + errors → best-effort warn，不加 blocker、不禁止进度。
- 依赖: 仅 import attempt_builder 的纯函数 apply_ledger_governance；不跑 main、不发起
  provider HTTP、不连 PG。misc_tools 需在 PYTHONPATH（attempt_builder 顶层 import
  bybit_path_policy）；由 conftest_path 注入 sys.path。
"""

from __future__ import annotations

import sys
from pathlib import Path

# attempt_builder 与 misc_tools 都需在 import path 上。
_TG_DIR = Path(__file__).resolve().parents[1]
_MISC_TOOLS = _TG_DIR.parents[1] / "exchange_connectors/bybit_connector/misc_tools"
for _p in (_TG_DIR, _MISC_TOOLS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

# httpx 是 attempt_builder 顶层依赖；缺失则跳过（Mac sandbox 可能未装）。
pytest.importorskip("httpx")

from bybit_ai_invocation_attempt_builder import apply_ledger_governance  # noqa: E402


def test_paid_ledger_write_false_blocks_progress():
    # 付费调用：writer 返回 ok=False → 必 fail-closed。
    payload = {
        "invocation_state": "invocation_success_json_ready",
        "allow_progress_to_h1g_response_check": True,
        "report_ok": True,
    }
    blocking_reasons: list = []
    warning_flags: list = []
    ledger_result = {
        "ok": False,
        "ledger_state": "invocation_ledger_write_failed",
        "paid": True,
        "errors": ["ledger_write_exception:RuntimeError"],
    }
    apply_ledger_governance(payload, ledger_result, blocking_reasons, warning_flags)

    assert payload["allow_progress_to_h1g_response_check"] is False
    assert payload["invocation_state"] == "invocation_ledger_write_failed"
    assert payload["report_ok"] is False
    assert "invocation_ledger_write_failed" in blocking_reasons
    assert payload["recommended_action"] == "resolve_ledger_write_failure_before_h1g"
    # 付费失败不是 best-effort warn。
    assert "ai_invocation_ledger_local_best_effort_warn" not in warning_flags


def test_local_ledger_write_false_best_effort_not_blocked():
    # 本地/Ollama：writer 返回 ok=True + errors → 仅 warn，不阻断。
    payload = {
        "invocation_state": "invocation_success_json_ready",
        "allow_progress_to_h1g_response_check": True,
        "report_ok": True,
    }
    blocking_reasons: list = []
    warning_flags: list = []
    ledger_result = {
        "ok": True,
        "ledger_state": "ai_invocation_ledger_skipped_local_best_effort",
        "paid": False,
        "errors": ["db_unavailable_local_best_effort"],
    }
    apply_ledger_governance(payload, ledger_result, blocking_reasons, warning_flags)

    # 不阻断、不禁止进度。
    assert payload["allow_progress_to_h1g_response_check"] is True
    assert payload["invocation_state"] == "invocation_success_json_ready"
    assert "invocation_ledger_write_failed" not in blocking_reasons
    # best-effort warn 被加上。
    assert "ai_invocation_ledger_local_best_effort_warn" in warning_flags


def test_clean_ledger_success_no_blocker_no_warn():
    # 正常成功：既不加 blocker 也不加 warn。
    payload = {
        "invocation_state": "invocation_success_json_ready",
        "allow_progress_to_h1g_response_check": True,
        "report_ok": True,
    }
    blocking_reasons: list = []
    warning_flags: list = []
    ledger_result = {
        "ok": True,
        "ledger_state": "ai_invocation_ledger_recorded",
        "paid": True,
        "rows_written": ["agent.ai_invocations", "learning.ai_usage_log"],
        "errors": [],
    }
    apply_ledger_governance(payload, ledger_result, blocking_reasons, warning_flags)

    assert payload["allow_progress_to_h1g_response_check"] is True
    assert blocking_reasons == []
    assert warning_flags == []
