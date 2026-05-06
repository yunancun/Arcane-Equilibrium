from __future__ import annotations

from app.multi_agent_framework import (
    AgentMessage,
    AgentRole,
    MessageBus,
    MessageType,
)


def _event_alert() -> AgentMessage:
    return AgentMessage(
        sender=AgentRole.SCOUT,
        receiver=AgentRole.GUARDIAN,
        message_type=MessageType.EVENT_ALERT,
        payload={"event_type": "cpi"},
    )


def test_message_sink_runs_before_subscriber_delivery() -> None:
    calls: list[str] = []
    bus = MessageBus(message_sink=lambda msg: calls.append(f"sink:{msg.message_id}"))
    msg = _event_alert()
    bus.subscribe(AgentRole.GUARDIAN, lambda delivered: calls.append(f"sub:{delivered.message_id}"))

    assert bus.send(msg) is True
    assert calls == [f"sink:{msg.message_id}", f"sub:{msg.message_id}"]


def test_message_sink_exception_does_not_block_subscribers() -> None:
    delivered: list[str] = []

    def _crashing_sink(_msg) -> None:
        raise RuntimeError("db down")

    bus = MessageBus(message_sink=_crashing_sink)
    bus.subscribe(AgentRole.GUARDIAN, lambda msg: delivered.append(msg.message_id))

    msg = _event_alert()
    assert bus.send(msg) is True
    assert delivered == [msg.message_id]


def test_invalid_route_does_not_call_sink_or_subscriber() -> None:
    calls: list[str] = []
    bus = MessageBus(message_sink=lambda _msg: calls.append("sink"))
    bus.subscribe(AgentRole.EXECUTOR, lambda _msg: calls.append("sub"))
    invalid = AgentMessage(
        sender=AgentRole.GUARDIAN,
        receiver=AgentRole.EXECUTOR,
        message_type=MessageType.EVENT_ALERT,
        payload={},
    )

    assert bus.send(invalid) is False
    assert calls == []
    assert bus.total_messages == 0


def test_set_message_sink_installs_and_clears_sink() -> None:
    calls: list[str] = []
    bus = MessageBus()
    msg = _event_alert()

    bus.set_message_sink(lambda _msg: calls.append("sink"))
    assert bus.send(msg) is True
    bus.set_message_sink(None)
    assert bus.send(_event_alert()) is True

    assert calls == ["sink"]
