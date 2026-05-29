#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MODULE_NOTE / 模块说明:
- 模块用途: P1-13 持久化账本写入器 fail-closed 行为单元测试。
- 覆盖:
  * 付费调用成功 → 两张账本表各写一行，idempotency_key 落两表。
  * 付费调用账本写失败 → ok=False（caller 必 fail-closed），blocker 状态。
  * 本地/免费调用账本写失败 → ok=True + warning（best-effort，根原则 14）。
- 依赖: 注入 _conn_factory 模拟 DB，不连真实 PG，不发起 provider HTTP。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# H1-F 脚本目录用 sibling import，测试时把其加入 sys.path。
_THIS_DIR = Path(__file__).resolve().parent.parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from bybit_ai_invocation_ledger import (  # noqa: E402
    deterministic_event_ts,
    write_invocation_ledger,
)


class _FakeCursor:
    def __init__(self, sink):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        self._sink.append((sql.strip().split("\n")[0], params))


class _FakeConn:
    def __init__(self, sink, raise_on_execute=False):
        self._sink = sink
        self._raise = raise_on_execute

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        if self._raise:
            class _Boom(_FakeCursor):
                def execute(self, sql, params):
                    raise RuntimeError("simulated_db_write_failure")
            return _Boom(self._sink)
        return _FakeCursor(self._sink)

    def close(self):
        pass


class _PkAwareCursor:
    """模拟两张账本表的 PK + ON CONFLICT DO NOTHING 语义。

    为什么需要它（MED-1 回归）：旧 _FakeCursor 只把 (sql, params) 收集起来，
    断言 idempotency_key 在 params 里——这无法验证 PK 是否跨重试稳定、ON CONFLICT
    是否真正去重，正好掩盖了 now() 导致 PK 每次漂移的 bug。此 cursor 用 (表名, PK)
    集合真实判重，重复 PK 的 INSERT 被丢弃（DO NOTHING），从而可断言「写两次=一行」。
    """

    def __init__(self, store):
        self._store = store

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        head = sql.strip().split("\n")[0]
        if "agent.ai_invocations" in sql:
            # PK = (invocation_id, ts) → params[(ts, invocation_id, ...)]，ts 在第 0 位。
            ts, invocation_id = params[0], params[1]
            pk = ("agent.ai_invocations", invocation_id, ts)
        elif "learning.ai_usage_log" in sql:
            # PK = (time, scope, request_id) → params(time, scope, ..., request_id)。
            time_col, scope, request_id = params[0], params[1], params[-1]
            pk = ("learning.ai_usage_log", time_col, scope, request_id)
        else:
            pk = ("unknown", head)
        # ON CONFLICT DO NOTHING：PK 已存在则丢弃。
        self._store["pks"].add(pk)


class _PkAwareConn:
    def __init__(self, store):
        self._store = store

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return _PkAwareCursor(self._store)

    def close(self):
        pass


def test_deterministic_ts_stable_across_retries():
    # 同一 key 必得同一 ts，否则 PK 漂移、去重失效（MED-1 根因）。
    ts1 = deterministic_event_ts("h1f_1700000123456")
    ts2 = deterministic_event_ts("h1f_1700000123456")
    assert ts1 == ts2
    # 内嵌毫秒被还原成真实事件时间（保 MTD 月份正确）。
    assert ts1.timestamp() == 1700000123.456
    # 不同 key → 不同 ts（不会误合并不同调用）。
    assert deterministic_event_ts("h1f_1700000123456") != deterministic_event_ts(
        "h1f_1700000999999"
    )
    # 无内嵌时间的外部 key 也确定性。
    assert deterministic_event_ts("external-key-xyz") == deterministic_event_ts(
        "external-key-xyz"
    )


def test_retry_with_same_key_dedupes_to_one_row_per_table():
    # MED-1 真实去重回归：相同 idempotency_key 写两次，每张表只应留一行。
    store = {"pks": set()}
    factory = lambda dsn=None: _PkAwareConn(store)  # noqa: E731
    kwargs = dict(
        idempotency_key="h1f_1700000123456",
        provider_target="openai_native",
        model_name="gpt-x",
        selected_ai_tier="standard",
        route_plan="route_b_standard",
        invocation_state="invocation_success_json_ready",
        usage_summary={"input_tokens": 100, "output_tokens": 50},
        cost_usd=0.0123,
        latency_ms=420,
        prompt_material="sys+user",
        response_material="resp",
        _conn_factory=factory,
    )
    r1 = write_invocation_ledger(**kwargs)
    r2 = write_invocation_ledger(**kwargs)  # 重试：同 key。
    assert r1["ok"] is True and r2["ok"] is True
    inv_rows = [pk for pk in store["pks"] if pk[0] == "agent.ai_invocations"]
    usage_rows = [pk for pk in store["pks"] if pk[0] == "learning.ai_usage_log"]
    # 写两次、每表恰好一行 —— now() 旧实现会得到两行（double-count），故此断言守 MED-1。
    assert len(inv_rows) == 1, inv_rows
    assert len(usage_rows) == 1, usage_rows


def test_paid_call_success_writes_both_ledgers():
    sink = []
    result = write_invocation_ledger(
        idempotency_key="idem-abc",
        provider_target="openai_native",
        model_name="gpt-x",
        selected_ai_tier="standard",
        route_plan="route_b_standard",
        invocation_state="invocation_success_json_ready",
        usage_summary={"input_tokens": 100, "output_tokens": 50},
        cost_usd=0.0123,
        latency_ms=420,
        prompt_material="sys+user",
        response_material="resp",
        _conn_factory=lambda dsn=None: _FakeConn(sink),
    )
    assert result["ok"] is True
    assert result["paid"] is True
    assert "agent.ai_invocations" in result["rows_written"]
    assert "learning.ai_usage_log" in result["rows_written"]
    # 两表都用同一 idempotency_key 作去重键。
    assert all("idem-abc" in str(p) for _, p in sink)


def test_paid_call_ledger_failure_fail_closed():
    sink = []
    result = write_invocation_ledger(
        idempotency_key="idem-fail",
        provider_target="anthropic_native",
        model_name="claude-x",
        selected_ai_tier="standard",
        route_plan="route_c_escalated_standard",
        invocation_state="invocation_success_json_ready",
        usage_summary={"input_tokens": 10, "output_tokens": 5},
        cost_usd=0.01,
        latency_ms=100,
        _conn_factory=lambda dsn=None: _FakeConn(sink, raise_on_execute=True),
    )
    # 付费调用账本写失败必 fail-closed。
    assert result["ok"] is False
    assert result["ledger_state"] == "invocation_ledger_write_failed"
    assert result["errors"]


def test_paid_call_db_unavailable_fail_closed():
    result = write_invocation_ledger(
        idempotency_key="idem-nodb",
        provider_target="openai_native",
        model_name="gpt-x",
        selected_ai_tier="standard",
        route_plan="route_b_standard",
        invocation_state="invocation_success_json_ready",
        usage_summary={},
        cost_usd=None,
        latency_ms=10,
        _conn_factory=lambda dsn=None: None,  # DB 不可用
    )
    assert result["ok"] is False
    assert "db_unavailable_for_paid_call" in result["errors"]


def test_local_call_ledger_failure_best_effort():
    sink = []
    result = write_invocation_ledger(
        idempotency_key="idem-local",
        provider_target="ollama_local",
        model_name="qwen",
        selected_ai_tier="light",
        route_plan="route_a_light",
        invocation_state="invocation_success_json_ready",
        usage_summary={"input_tokens": 5, "output_tokens": 3},
        cost_usd=0.0,
        latency_ms=80,
        _conn_factory=lambda dsn=None: _FakeConn(sink, raise_on_execute=True),
    )
    # 本地路径写失败仍 best-effort：ok=True + 带 error 标记。
    assert result["ok"] is True
    assert result["paid"] is False
    assert result["errors"]


def test_local_call_db_unavailable_best_effort():
    result = write_invocation_ledger(
        idempotency_key="idem-local2",
        provider_target="ollama_local",
        model_name="qwen",
        selected_ai_tier="light",
        route_plan="route_a_light",
        invocation_state="invocation_success_json_ready",
        usage_summary={},
        cost_usd=0.0,
        latency_ms=5,
        _conn_factory=lambda dsn=None: None,
    )
    assert result["ok"] is True
    assert result["paid"] is False
