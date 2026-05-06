from __future__ import annotations

from app.base_agent import BaseAgent
from app.multi_agent_framework import AgentRole


class _FakeStore:
    def __init__(self):
        self.state_changes: list[dict] = []
        self.ai_invocations: list[dict] = []

    def record_state_change(self, **kwargs):
        self.state_changes.append(kwargs)
        return True

    def record_ai_invocation(self, **kwargs):
        self.ai_invocations.append(kwargs)
        return True


def test_base_agent_lifecycle_records_state_changes() -> None:
    store = _FakeStore()
    agent = BaseAgent(role=AgentRole.SCOUT, event_store=store)

    agent.start()
    agent.pause()
    agent.stop()

    assert [
        (row["from_state"], row["to_state"], row["trigger_event"])
        for row in store.state_changes
    ] == [
        ("initializing", "running", "start"),
        ("running", "paused", "pause"),
        ("paused", "stopped", "stop"),
    ]
    assert {row["agent_name"] for row in store.state_changes} == {"scout"}


def test_base_agent_ai_invocation_helper_delegates_fail_soft() -> None:
    store = _FakeStore()
    agent = BaseAgent(role=AgentRole.STRATEGIST, event_store=store)

    assert agent._record_ai_invocation(
        provider="ollama",
        model="l1_9b",
        tier="L1",
        purpose="unit_test",
        prompt_material="prompt",
        success=True,
        details={"intel_id": "intel-1"},
    )

    assert len(store.ai_invocations) == 1
    row = store.ai_invocations[0]
    assert row["provider"] == "ollama"
    assert row["purpose"] == "unit_test"
    assert row["details"] == {"agent": "strategist", "intel_id": "intel-1"}


def test_base_agent_without_event_store_is_noop() -> None:
    agent = BaseAgent(role=AgentRole.GUARDIAN)

    assert agent._record_ai_invocation(
        provider="ollama",
        model="l1_9b",
        purpose="unit_test",
        success=False,
    ) is False
