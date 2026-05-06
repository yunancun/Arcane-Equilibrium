from __future__ import annotations

"""
MAG-019 supervisor cloud ledger policy tests.

MODULE_NOTE (中文):
  鎖住 supervisor cloud escalation 預設關閉、budget/model 顯式配置、packet
  先於 cloud call 建立、以及 allowed 時必須先寫 `agent.ai_invocations` ledger row。
"""

import os
import re
import sys
from pathlib import Path
from typing import Any

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.openclaw_supervisor_policy import (  # noqa: E402
    SupervisorCloudConfig,
    build_escalation_packet,
    build_supervisor_cloud_policy_snapshot,
    record_invocation_before_cloud_call,
)


class _FakeEventStore:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.rows: list[dict[str, Any]] = []

    def record_ai_invocation(self, **kwargs: Any) -> bool:
        self.rows.append(kwargs)
        return self.ok


def test_default_policy_denies_cloud_calls(monkeypatch) -> None:
    monkeypatch.delenv("OPENCLAW_SUPERVISOR_CLOUD_ENABLED", raising=False)
    snapshot = build_supervisor_cloud_policy_snapshot()
    assert snapshot["cloud_enabled"] is False
    assert snapshot["per_agent_cloud_calls_allowed"] is False
    assert snapshot["supervisor_packet_required"] is True
    assert snapshot["ai_invocation_link_required"] is True
    assert snapshot["default_cloud_call_allowed"] is False
    assert snapshot["disabled_reason"] == "cloud_disabled_by_env"


def test_enabled_policy_requires_budget_and_model(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_SUPERVISOR_CLOUD_ENABLED", "1")
    monkeypatch.delenv("OPENCLAW_SUPERVISOR_CLOUD_DAILY_USD_CAP", raising=False)
    monkeypatch.delenv("OPENCLAW_SUPERVISOR_CLOUD_MONTHLY_USD_CAP", raising=False)
    snapshot = build_supervisor_cloud_policy_snapshot()
    assert snapshot["default_cloud_call_allowed"] is False
    assert snapshot["disabled_reason"] == "cloud_budget_missing"

    cfg = SupervisorCloudConfig(
        enabled=True,
        require_budget=True,
        daily_cap_usd=1.0,
        monthly_cap_usd=10.0,
        max_packet_bytes=32768,
        provider=None,
        model=None,
    )
    decision = cfg.evaluate_budget(estimated_cost_usd=0.01)
    assert decision["allowed"] is False
    assert decision["reason"] == "cloud_model_missing"


def test_denied_packet_records_budget_diagnosis_without_event_store_write() -> None:
    cfg = SupervisorCloudConfig(
        enabled=False,
        require_budget=True,
        daily_cap_usd=None,
        monthly_cap_usd=None,
        max_packet_bytes=512,
        provider=None,
        model=None,
    )
    packet = build_escalation_packet(
        trigger_type="healthcheck_fail",
        source_observation_ids=["obs-1"],
        input_summary="safe compressed healthcheck summary",
        config=cfg,
        created_at_ms=1_778_000_000_000,
    )
    store = _FakeEventStore()
    out = record_invocation_before_cloud_call(packet=packet, event_store=store)
    assert out["status"] == "denied"
    assert out["budget_decision"]["reason"] == "cloud_disabled_by_env"
    assert out["result_diagnosis_ids"]
    assert out["diagnoses"][0]["facts"] == ["cloud_disabled_by_env"]
    assert store.rows == []


def test_allowed_packet_records_ai_invocation_before_cloud_call() -> None:
    cfg = SupervisorCloudConfig(
        enabled=True,
        require_budget=True,
        daily_cap_usd=1.0,
        monthly_cap_usd=10.0,
        max_packet_bytes=1024,
        provider="test_cloud",
        model="test-model",
    )
    packet = build_escalation_packet(
        trigger_type="edge_regression",
        source_observation_ids=["obs-a", "obs-b"],
        input_summary="safe compressed edge regression summary",
        estimated_cost_usd=0.02,
        config=cfg,
        created_at_ms=1_778_000_000_000,
    )
    store = _FakeEventStore()
    out = record_invocation_before_cloud_call(
        packet=packet,
        event_store=store,
        estimated_input_tokens=123,
    )
    assert out["status"] == "invocation_recorded"
    assert out["ai_invocation_id"].startswith("ai_supervisor_")
    assert len(store.rows) == 1
    row = store.rows[0]
    assert row["provider"] == "test_cloud"
    assert row["model"] == "test-model"
    assert row["tier"] == "L2"
    assert row["purpose"] == "openclaw_supervisor_escalation"
    assert row["context_id"] == packet["escalation_id"]
    assert row["engine_mode"] is None
    assert row["success"] is False
    assert row["details"]["control_plane"] is True
    assert row["details"]["ledger_phase"] == "before_cloud_call"
    assert "safe compressed edge regression summary" not in str(row["details"])
    assert row["details"]["input_summary_hash"] == packet["prompt_hash"]


def test_event_store_write_failure_fails_visible() -> None:
    cfg = SupervisorCloudConfig(
        enabled=True,
        require_budget=False,
        daily_cap_usd=None,
        monthly_cap_usd=None,
        max_packet_bytes=1024,
        provider="test_cloud",
        model="test-model",
    )
    packet = build_escalation_packet(
        trigger_type="operator_requested",
        source_observation_ids=[],
        input_summary="safe operator summary",
        config=cfg,
    )
    out = record_invocation_before_cloud_call(
        packet=packet,
        event_store=_FakeEventStore(ok=False),
    )
    assert out["status"] == "failed"
    assert out["degraded_reason"] == "ai_invocation_record_failed"


def test_packet_summary_is_bounded_and_hashed() -> None:
    cfg = SupervisorCloudConfig(
        enabled=False,
        require_budget=True,
        daily_cap_usd=None,
        monthly_cap_usd=None,
        max_packet_bytes=300,
        provider=None,
        model=None,
    )
    packet = build_escalation_packet(
        trigger_type="strategy_anomaly",
        source_observation_ids=["obs-x"],
        input_summary="x" * 2000,
        config=cfg,
    )
    assert packet["payload_truncated"] is True
    assert len(packet["input_summary"].encode("utf-8")) <= 320
    assert re.fullmatch(r"[0-9a-f]{64}", packet["prompt_hash"])


def test_policy_module_has_no_cloud_network_call_markers() -> None:
    src = Path(__file__).resolve().parents[1].joinpath(
        "app",
        "openclaw_supervisor_policy.py",
    ).read_text(encoding="utf-8")
    forbidden = (
        "requests.",
        "httpx.",
        "urllib.request",
        "openai.",
        "anthropic.",
        "subprocess.",
        "socket.",
        "INSERT INTO agent.ai_invocations",
    )
    for marker in forbidden:
        assert marker not in src
