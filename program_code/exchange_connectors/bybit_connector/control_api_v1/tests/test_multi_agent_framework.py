"""
Tests for T2.07 — Scout Agent + Conductor Framework (GAP-H2)
=============================================================
Governance refs: EX-06 §2-§10, DOC-04 §G
"""

import threading
import time
import pytest

from app.multi_agent_framework import (
    AgentMessage,
    AgentRole,
    AgentState,
    ArbitrationResult,
    Conductor,
    DataQualityLevel,
    EventAlert,
    IntelObject,
    MessageBus,
    MessageType,
    ResourcePriority,
    RiskModification,
    RiskVerdict,
    RiskVerdictResult,
    ScoutAgent,
    ScoutConfig,
    TradeIntent,
    VALID_ROUTES,
    arbitrate_conflict,
)


# ─────────────────────────────────────────────
# 1. Enum Constants
# ─────────────────────────────────────────────

class TestAgentRoles:
    """EX-06 §1 — 5 agent roles + conductor."""

    def test_five_agent_roles(self):
        roles = [r for r in AgentRole if r != AgentRole.CONDUCTOR]
        assert len(roles) == 5
        names = {r.value for r in roles}
        assert names == {"scout", "strategist", "guardian", "analyst", "executor"}

    def test_conductor_is_not_agent(self):
        """Conductor is orchestrator, not a 6th agent."""
        assert AgentRole.CONDUCTOR.value == "conductor"

    def test_message_types_count(self):
        """EX-06 §8.2 — 11 structured message types."""
        assert len(MessageType) == 11

    def test_data_quality_levels(self):
        """EX-06 §3.4 — three cognitive levels."""
        assert len(DataQualityLevel) == 3
        assert DataQualityLevel.FACT.value == "fact"
        assert DataQualityLevel.INFERENCE.value == "inference"
        assert DataQualityLevel.HYPOTHESIS.value == "hypothesis"


# ─────────────────────────────────────────────
# 2. Structured Message Objects
# ─────────────────────────────────────────────

class TestAgentMessage:

    def test_unique_id(self):
        m1 = AgentMessage()
        m2 = AgentMessage()
        assert m1.message_id != m2.message_id

    def test_timestamp_auto(self):
        before = int(time.time() * 1000)
        m = AgentMessage()
        assert m.timestamp_ms >= before

    def test_serialization(self):
        m = AgentMessage(
            sender=AgentRole.SCOUT,
            receiver=AgentRole.STRATEGIST,
            message_type=MessageType.INTEL_OBJECT,
            priority=3,
            payload={"key": "value"},
        )
        d = m.to_dict()
        assert d["sender"] == "scout"
        assert d["receiver"] == "strategist"
        assert d["message_type"] == "intel_object"
        assert d["priority"] == 3
        assert d["payload"]["key"] == "value"


class TestIntelObject:

    def test_creation(self):
        intel = IntelObject(
            source="coingecko",
            content="BTC volume spike",
            symbols=["BTC"],
            data_quality=DataQualityLevel.FACT,
            sentiment=SentimentScore.POSITIVE,
            relevance_score=0.8,
        )
        assert intel.intel_id.startswith("intel_")
        assert intel.data_quality == DataQualityLevel.FACT

    def test_serialization(self):
        intel = IntelObject(source="test", content="test", symbols=["ETH"])
        d = intel.to_dict()
        assert "intel_id" in d
        assert d["symbols"] == ["ETH"]
        assert d["data_quality"] == "fact"


class TestEventAlert:

    def test_creation(self):
        alert = EventAlert(
            event_type="fomc",
            severity="high",
            affected_symbols=["BTC", "ETH"],
            lead_time_hours=2.0,
            data_quality=DataQualityLevel.INFERENCE,
        )
        assert alert.alert_id.startswith("alert_")
        assert alert.severity == "high"

    def test_serialization(self):
        alert = EventAlert(event_type="token_unlock", severity="medium", affected_symbols=["SOL"])
        d = alert.to_dict()
        assert d["event_type"] == "token_unlock"
        assert d["data_quality"] == "inference"


class TestTradeIntent:

    def test_creation(self):
        intent = TradeIntent(
            symbol="BTCUSDT",
            strategy="ma_crossover",
            direction="long",
            size=0.1,
            confidence=0.75,
            thesis="Golden cross on 4H",
            invalidation_condition="Price below 50k",
        )
        assert intent.intent_id.startswith("intent_")
        assert intent.confidence == 0.75

    def test_serialization(self):
        intent = TradeIntent(symbol="ETHUSDT", strategy="grid", direction="short", size=1.0)
        d = intent.to_dict()
        assert d["symbol"] == "ETHUSDT"
        assert d["direction"] == "short"
        assert d["data_quality"] == "inference"


class TestRiskVerdict:

    def test_approved(self):
        v = RiskVerdict(intent_id="intent_abc", result=RiskVerdictResult.APPROVED, reason="Within limits")
        assert v.result == RiskVerdictResult.APPROVED

    def test_rejected(self):
        v = RiskVerdict(intent_id="intent_abc", result=RiskVerdictResult.REJECTED, reason="Exceeds P1")
        assert v.result == RiskVerdictResult.REJECTED

    def test_modified(self):
        v = RiskVerdict(
            intent_id="intent_abc",
            result=RiskVerdictResult.MODIFIED,
            reason="Size reduced",
            modified_params={"size": 0.05},
            p2_modifications=[
                RiskModification(
                    field="size",
                    action="reduce",
                    original_value=0.1,
                    modified_value=0.05,
                    unit="base_qty",
                    reason_code="strategy_soft_risk",
                    reason="Size reduced",
                ).to_dict()
            ],
        )
        assert v.modified_params["size"] == 0.05
        assert v.to_dict()["p2_modifications"][0]["field"] == "size"


# ─────────────────────────────────────────────
# 3. Message Bus
# ─────────────────────────────────────────────

class TestMessageBus:

    def test_valid_route(self):
        bus = MessageBus()
        assert bus.validate_route(AgentRole.SCOUT, AgentRole.STRATEGIST, MessageType.INTEL_OBJECT) is True
        assert bus.validate_route(AgentRole.SCOUT, AgentRole.GUARDIAN, MessageType.EVENT_ALERT) is True
        assert bus.validate_route(AgentRole.STRATEGIST, AgentRole.GUARDIAN, MessageType.TRADE_INTENT) is True
        assert bus.validate_route(AgentRole.GUARDIAN, AgentRole.STRATEGIST, MessageType.RISK_VERDICT) is True
        assert bus.validate_route(AgentRole.STRATEGIST, AgentRole.EXECUTOR, MessageType.APPROVED_INTENT) is True

    def test_invalid_route_blocked(self):
        """Scout cannot send trade_intent (§3.3 — Scout cannot generate trade signals)."""
        bus = MessageBus()
        assert bus.validate_route(AgentRole.SCOUT, AgentRole.EXECUTOR, MessageType.TRADE_INTENT) is False

    def test_send_valid_message(self):
        bus = MessageBus()
        msg = AgentMessage(
            sender=AgentRole.SCOUT,
            receiver=AgentRole.STRATEGIST,
            message_type=MessageType.INTEL_OBJECT,
            payload={"data": "test"},
        )
        assert bus.send(msg) is True
        assert bus.total_messages == 1

    def test_send_invalid_route_rejected(self):
        bus = MessageBus()
        msg = AgentMessage(
            sender=AgentRole.SCOUT,
            receiver=AgentRole.EXECUTOR,
            message_type=MessageType.TRADE_INTENT,
        )
        assert bus.send(msg) is False
        assert bus.total_messages == 0

    def test_subscriber_notification(self):
        bus = MessageBus()
        received = []
        bus.subscribe(AgentRole.STRATEGIST, lambda m: received.append(m))

        msg = AgentMessage(
            sender=AgentRole.SCOUT,
            receiver=AgentRole.STRATEGIST,
            message_type=MessageType.INTEL_OBJECT,
        )
        bus.send(msg)
        assert len(received) == 1
        assert received[0].message_type == MessageType.INTEL_OBJECT

    def test_query_by_receiver(self):
        bus = MessageBus()
        bus.send(AgentMessage(
            sender=AgentRole.SCOUT, receiver=AgentRole.STRATEGIST,
            message_type=MessageType.INTEL_OBJECT,
        ))
        bus.send(AgentMessage(
            sender=AgentRole.SCOUT, receiver=AgentRole.GUARDIAN,
            message_type=MessageType.EVENT_ALERT,
        ))

        strat_msgs = bus.get_messages(receiver=AgentRole.STRATEGIST)
        assert len(strat_msgs) == 1
        guard_msgs = bus.get_messages(receiver=AgentRole.GUARDIAN)
        assert len(guard_msgs) == 1

    def test_query_by_type(self):
        bus = MessageBus()
        bus.send(AgentMessage(
            sender=AgentRole.SCOUT, receiver=AgentRole.STRATEGIST,
            message_type=MessageType.INTEL_OBJECT,
        ))
        bus.send(AgentMessage(
            sender=AgentRole.SCOUT, receiver=AgentRole.GUARDIAN,
            message_type=MessageType.EVENT_ALERT,
        ))
        results = bus.get_messages(msg_type=MessageType.EVENT_ALERT)
        assert len(results) == 1

    def test_audit_callback(self):
        audited = []
        bus = MessageBus(audit_callback=lambda action, data: audited.append((action, data)))
        bus.send(AgentMessage(
            sender=AgentRole.SCOUT, receiver=AgentRole.STRATEGIST,
            message_type=MessageType.INTEL_OBJECT,
        ))
        assert len(audited) == 1
        assert audited[0][0] == "message_sent"

    def test_conductor_broadcast_routes(self):
        """Conductor can send system_directive to all 5 agent roles."""
        bus = MessageBus()
        for target in [AgentRole.SCOUT, AgentRole.STRATEGIST, AgentRole.GUARDIAN,
                       AgentRole.ANALYST, AgentRole.EXECUTOR]:
            assert bus.validate_route(AgentRole.CONDUCTOR, target, MessageType.SYSTEM_DIRECTIVE) is True

    def test_all_valid_routes_from_spec(self):
        """Verify all TABLE 3 routes are in VALID_ROUTES."""
        expected_count = 14  # 9 from TABLE 3 + 5 conductor broadcast targets
        assert len(VALID_ROUTES) == expected_count


# ─────────────────────────────────────────────
# 4. Scout Agent
# ─────────────────────────────────────────────

class TestScoutAgent:

    def test_lifecycle(self):
        scout = ScoutAgent()
        assert scout.state == AgentState.INITIALIZING
        scout.start()
        assert scout.state == AgentState.RUNNING
        scout.pause()
        assert scout.state == AgentState.PAUSED
        scout.stop()
        assert scout.state == AgentState.STOPPED

    def test_produce_intel(self):
        bus = MessageBus()
        scout = ScoutAgent(message_bus=bus)
        intel = scout.produce_intel(
            source="coingecko",
            content="BTC 24h volume up 40%",
            symbols=["BTC"],
            data_quality=DataQualityLevel.FACT,
            sentiment=SentimentScore.POSITIVE,
            relevance_score=0.8,
        )
        assert intel.source == "coingecko"
        assert intel.data_quality == DataQualityLevel.FACT
        assert bus.total_messages == 1  # Routed to Strategist

    def test_produce_intel_low_relevance_not_sent(self):
        """Intel below relevance threshold not sent to bus."""
        bus = MessageBus()
        scout = ScoutAgent(
            config=ScoutConfig(relevance_threshold=0.5),
            message_bus=bus,
        )
        scout.produce_intel(
            source="twitter",
            content="Random noise",
            symbols=[],
            relevance_score=0.1,
        )
        assert bus.total_messages == 0  # Below threshold

    def test_produce_event_alert(self):
        bus = MessageBus()
        scout = ScoutAgent(message_bus=bus)
        alert = scout.produce_event_alert(
            event_type="fomc",
            severity="high",
            affected_symbols=["BTC", "ETH"],
            lead_time_hours=2.0,
            description="FOMC meeting in 2 hours",
        )
        assert alert.event_type == "fomc"
        assert alert.severity == "high"
        assert bus.total_messages == 1  # Routed to Guardian

    def test_high_severity_alert_priority(self):
        """High/critical alerts get priority 1."""
        bus = MessageBus()
        scout = ScoutAgent(message_bus=bus)
        scout.produce_event_alert(
            event_type="liquidation",
            severity="critical",
            affected_symbols=["BTC"],
        )
        msgs = bus.get_messages(receiver=AgentRole.GUARDIAN)
        assert len(msgs) == 1
        assert msgs[0].priority == 1

    def test_data_quality_marking(self):
        """EX-06 §3.4 — all Scout outputs must carry data quality level."""
        scout = ScoutAgent()
        intel_fact = scout.produce_intel(
            source="api", content="price", symbols=["BTC"],
            data_quality=DataQualityLevel.FACT,
        )
        intel_hyp = scout.produce_intel(
            source="model", content="prediction", symbols=["BTC"],
            data_quality=DataQualityLevel.HYPOTHESIS,
        )
        assert intel_fact.data_quality == DataQualityLevel.FACT
        assert intel_hyp.data_quality == DataQualityLevel.HYPOTHESIS

    def test_recent_intel(self):
        scout = ScoutAgent()
        for i in range(5):
            scout.produce_intel(source="src", content=f"item {i}", symbols=["X"])
        recent = scout.get_recent_intel(limit=3)
        assert len(recent) == 3

    def test_stats(self):
        scout = ScoutAgent()
        scout.start()
        scout.produce_intel(source="a", content="b", symbols=["X"])
        scout.produce_intel(source="a", content="c", symbols=["Y"])
        scout.record_scan()
        stats = scout.get_stats()
        assert stats["intel_produced"] == 2
        assert stats["scans_completed"] == 1
        assert stats["state"] == "running"

    def test_scout_cannot_produce_trade_signals(self):
        """EX-06 §3.3 — Scout does NOT generate trade signals.
        Scout produces intel_object, not trade_intent.
        """
        bus = MessageBus()
        # Verify Scout→Executor route for trade_intent is invalid
        assert bus.validate_route(AgentRole.SCOUT, AgentRole.EXECUTOR, MessageType.TRADE_INTENT) is False
        assert bus.validate_route(AgentRole.SCOUT, AgentRole.EXECUTOR, MessageType.APPROVED_INTENT) is False


# ─────────────────────────────────────────────
# 5. Conflict Arbitration
# ─────────────────────────────────────────────

class TestConflictArbitration:

    def test_open_vs_tighten_guardian_wins(self):
        """EX-06 §9 — Guardian wins when Strategist wants open but Guardian says tighten."""
        result = arbitrate_conflict("open_vs_tighten")
        assert result.winner == AgentRole.GUARDIAN
        assert result.decision == "guardian_veto"

    def test_scout_bearish_strategist_bullish(self):
        """Scout bearish + Strategist bullish → Guardian intervenes."""
        result = arbitrate_conflict("scout_bearish_strategist_bullish")
        assert result.winner == AgentRole.GUARDIAN
        assert result.decision == "guardian_tighten"

    def test_analyst_vs_strategist(self):
        """Analyst suggestion not forced — Strategist has autonomy."""
        result = arbitrate_conflict("analyst_vs_strategist")
        assert result.winner == AgentRole.STRATEGIST
        assert result.decision == "strategist_autonomy"

    def test_executor_anomaly_guardian_wins(self):
        """Executor anomaly → Guardian can trigger CIRCUIT_BREAKER."""
        result = arbitrate_conflict("executor_anomaly")
        assert result.winner == AgentRole.GUARDIAN
        assert "circuit_breaker" in result.decision

    def test_resource_contention(self):
        """Conductor allocates by priority."""
        result = arbitrate_conflict("resource_contention")
        assert result.winner == AgentRole.CONDUCTOR

    def test_unknown_scenario_conductor_default(self):
        result = arbitrate_conflict("unknown_scenario_xyz")
        assert result.winner == AgentRole.CONDUCTOR
        assert result.decision == "conductor_default"


# ─────────────────────────────────────────────
# 6. Conductor
# ─────────────────────────────────────────────

class TestConductorLifecycle:

    def test_register_agent(self):
        c = Conductor()
        info = c.register_agent(AgentRole.SCOUT, resource_mode="local")
        assert info.role == AgentRole.SCOUT
        assert info.state == AgentState.INITIALIZING

    def test_set_agent_state(self):
        c = Conductor()
        c.register_agent(AgentRole.GUARDIAN)
        assert c.set_agent_state(AgentRole.GUARDIAN, AgentState.RUNNING) is True
        info = c.get_agent_info(AgentRole.GUARDIAN)
        assert info.state == AgentState.RUNNING

    def test_set_state_unregistered(self):
        c = Conductor()
        assert c.set_agent_state(AgentRole.SCOUT, AgentState.RUNNING) is False

    def test_heartbeat(self):
        c = Conductor()
        c.register_agent(AgentRole.ANALYST)
        assert c.heartbeat(AgentRole.ANALYST) is True
        info = c.get_agent_info(AgentRole.ANALYST)
        assert info.last_heartbeat_ms > 0

    def test_heartbeat_unregistered(self):
        c = Conductor()
        assert c.heartbeat(AgentRole.ANALYST) is False

    def test_get_all_agents(self):
        c = Conductor()
        c.register_agent(AgentRole.SCOUT)
        c.register_agent(AgentRole.GUARDIAN)
        c.register_agent(AgentRole.STRATEGIST)
        agents = c.get_all_agents()
        assert len(agents) == 3


class TestConductorTaskDistribution:

    def _setup_conductor(self) -> Conductor:
        c = Conductor()
        for role in [AgentRole.SCOUT, AgentRole.STRATEGIST, AgentRole.GUARDIAN,
                     AgentRole.ANALYST, AgentRole.EXECUTOR]:
            c.register_agent(role)
            c.set_agent_state(role, AgentState.RUNNING)
        return c

    def test_price_event_dispatched(self):
        c = self._setup_conductor()
        notified = c.dispatch_market_event({"type": "price_update", "symbol": "BTC"})
        assert AgentRole.SCOUT in notified
        assert AgentRole.STRATEGIST in notified
        assert AgentRole.GUARDIAN in notified

    def test_fill_event_dispatched(self):
        c = self._setup_conductor()
        notified = c.dispatch_market_event({"type": "fill", "order_id": "123"})
        assert AgentRole.EXECUTOR in notified
        assert AgentRole.ANALYST in notified

    def test_risk_alert_dispatched(self):
        c = self._setup_conductor()
        notified = c.dispatch_market_event({"type": "risk_alert"})
        assert AgentRole.GUARDIAN in notified

    def test_paused_agent_not_dispatched(self):
        c = self._setup_conductor()
        c.set_agent_state(AgentRole.STRATEGIST, AgentState.PAUSED)
        notified = c.dispatch_market_event({"type": "price_update"})
        assert AgentRole.STRATEGIST not in notified


class TestConductorConflictArbitration:

    def test_resolve_conflict_with_audit(self):
        audited = []
        c = Conductor(audit_callback=lambda a, d: audited.append((a, d)))
        result = c.resolve_conflict("open_vs_tighten")
        assert result.winner == AgentRole.GUARDIAN
        assert len(audited) == 1
        assert audited[0][0] == "conflict_arbitration"

    def test_guardian_always_beats_strategist(self):
        """Core principle: Guardian ALWAYS overrides Strategist."""
        c = Conductor()
        for scenario in ["open_vs_tighten", "scout_bearish_strategist_bullish", "executor_anomaly"]:
            result = c.resolve_conflict(scenario)
            assert result.winner == AgentRole.GUARDIAN, f"Guardian should win in {scenario}"


class TestConductorResourceAllocation:

    def test_priority_allocation(self):
        """EX-06 §9 — Guardian > Scout(urgent) > Strategist > Analyst."""
        c = Conductor()
        c.set_resource_budget(1.0)
        requests = [
            (AgentRole.ANALYST, 0.5),
            (AgentRole.GUARDIAN, 0.5),
            (AgentRole.STRATEGIST, 0.5),
        ]
        allocated = c.allocate_resource(requests)
        # Guardian gets first, then Strategist, then Analyst
        assert allocated[AgentRole.GUARDIAN] == 0.5
        assert allocated[AgentRole.STRATEGIST] == 0.5
        assert allocated[AgentRole.ANALYST] == 0.0  # budget exhausted

    def test_budget_limit(self):
        c = Conductor()
        c.set_resource_budget(0.5)
        requests = [
            (AgentRole.GUARDIAN, 1.0),
            (AgentRole.STRATEGIST, 1.0),
        ]
        allocated = c.allocate_resource(requests)
        assert allocated[AgentRole.GUARDIAN] == 0.5
        assert allocated[AgentRole.STRATEGIST] == 0.0


class TestConductorDirectives:

    def test_broadcast_to_all(self):
        c = Conductor()
        sent = c.broadcast_directive("degrade", {"reason": "high load"})
        assert sent == 5  # All 5 agent roles

    def test_broadcast_to_specific(self):
        c = Conductor()
        sent = c.broadcast_directive(
            "pause_trading",
            {"reason": "maintenance"},
            targets=[AgentRole.STRATEGIST, AgentRole.EXECUTOR],
        )
        assert sent == 2


class TestConductorTradeIntentPipeline:

    def test_approved_intent_forwarded(self):
        bus = MessageBus()
        c = Conductor(message_bus=bus)

        intent = TradeIntent(symbol="BTCUSDT", strategy="grid", direction="long", size=0.1)

        def guardian_approve(i):
            return RiskVerdict(intent_id=i.intent_id, result=RiskVerdictResult.APPROVED, reason="OK")

        allowed, verdict = c.process_trade_intent(intent, guardian_approve)
        assert allowed is True
        assert verdict.result == RiskVerdictResult.APPROVED
        # Message should be on bus (Strategist → Executor)
        msgs = bus.get_messages(receiver=AgentRole.EXECUTOR)
        assert len(msgs) == 1
        assert msgs[0].message_type == MessageType.APPROVED_INTENT

    def test_rejected_intent_not_forwarded(self):
        bus = MessageBus()
        c = Conductor(message_bus=bus)

        intent = TradeIntent(symbol="BTCUSDT", strategy="grid", direction="long", size=1.0)

        def guardian_reject(i):
            return RiskVerdict(intent_id=i.intent_id, result=RiskVerdictResult.REJECTED, reason="P1 exceeded")

        allowed, verdict = c.process_trade_intent(intent, guardian_reject)
        assert allowed is False
        assert verdict.result == RiskVerdictResult.REJECTED
        msgs = bus.get_messages(receiver=AgentRole.EXECUTOR)
        assert len(msgs) == 0  # Not forwarded

    def test_modified_intent_forwarded_with_changes(self):
        bus = MessageBus()
        c = Conductor(message_bus=bus)

        intent = TradeIntent(symbol="ETHUSDT", strategy="bb_breakout", direction="long", size=1.0)

        def guardian_modify(i):
            return RiskVerdict(
                intent_id=i.intent_id,
                result=RiskVerdictResult.MODIFIED,
                reason="Size reduced",
                modified_params={"size": 0.5},
            )

        allowed, verdict = c.process_trade_intent(intent, guardian_modify)
        assert allowed is True
        msgs = bus.get_messages(receiver=AgentRole.EXECUTOR)
        assert len(msgs) == 1
        assert msgs[0].payload["metadata"].get("guardian_modified") is True


# ─────────────────────────────────────────────
# 7. Conductor Status
# ─────────────────────────────────────────────

class TestConductorStatus:

    def test_status_fields(self):
        c = Conductor()
        c.register_agent(AgentRole.SCOUT)
        c.set_agent_state(AgentRole.SCOUT, AgentState.RUNNING)
        c.register_agent(AgentRole.GUARDIAN)
        status = c.get_status()
        assert status["role"] == "conductor"
        assert status["agents_registered"] == 2
        assert status["agents_running"] == 1
        assert "resource_budget_usd" in status

    def test_status_after_operations(self):
        c = Conductor()
        c.resolve_conflict("open_vs_tighten")
        c.broadcast_directive("test", {})
        status = c.get_status()
        assert status["arbitrations"] == 1
        assert status["directives_issued"] == 5


# ─────────────────────────────────────────────
# 8. Resource Priority
# ─────────────────────────────────────────────

class TestResourcePriority:

    def test_priority_ordering(self):
        """EX-06 §9 TABLE 4 — Guardian > Scout(urgent) > Strategist > Analyst > Scout(routine)."""
        assert ResourcePriority.GUARDIAN < ResourcePriority.SCOUT_URGENT
        assert ResourcePriority.SCOUT_URGENT < ResourcePriority.STRATEGIST
        assert ResourcePriority.STRATEGIST < ResourcePriority.ANALYST
        assert ResourcePriority.ANALYST < ResourcePriority.SCOUT_ROUTINE


# ─────────────────────────────────────────────
# 9. Thread Safety
# ─────────────────────────────────────────────

class TestThreadSafety:

    def test_concurrent_message_sending(self):
        bus = MessageBus()
        errors = []

        def send_messages(n):
            try:
                for _ in range(n):
                    bus.send(AgentMessage(
                        sender=AgentRole.SCOUT,
                        receiver=AgentRole.STRATEGIST,
                        message_type=MessageType.INTEL_OBJECT,
                    ))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=send_messages, args=(20,)) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert bus.total_messages == 100

    def test_concurrent_conductor_operations(self):
        c = Conductor()
        for role in AgentRole:
            if role != AgentRole.CONDUCTOR:
                c.register_agent(role)

        errors = []

        def ops():
            try:
                for _ in range(10):
                    c.heartbeat(AgentRole.SCOUT)
                    c.resolve_conflict("open_vs_tighten")
                    c.get_status()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=ops) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# ─────────────────────────────────────────────
# 10. Integration: Full Pipeline
# ─────────────────────────────────────────────

class TestFullPipeline:

    def test_scout_to_strategist_to_guardian_to_executor(self):
        """Full EX-06 pipeline: Scout intel → Strategist intent → Guardian review → Executor."""
        bus = MessageBus()
        scout = ScoutAgent(message_bus=bus)
        conductor = Conductor(message_bus=bus)

        # Register agents
        for role in [AgentRole.SCOUT, AgentRole.STRATEGIST, AgentRole.GUARDIAN, AgentRole.EXECUTOR]:
            conductor.register_agent(role)
            conductor.set_agent_state(role, AgentState.RUNNING)

        # 1. Scout produces intel → Strategist
        intel = scout.produce_intel(
            source="exchange",
            content="BTC funding rate -0.03%",
            symbols=["BTC"],
            data_quality=DataQualityLevel.FACT,
            sentiment=SentimentScore.NEGATIVE,
            relevance_score=0.9,
        )
        assert bus.total_messages == 1

        # 2. Strategist creates trade_intent → Guardian
        intent = TradeIntent(
            symbol="BTCUSDT",
            strategy="funding_arb",
            direction="short",
            size=0.5,
            confidence=0.7,
            thesis="Negative funding = short premium",
        )
        intent_msg = AgentMessage(
            sender=AgentRole.STRATEGIST,
            receiver=AgentRole.GUARDIAN,
            message_type=MessageType.TRADE_INTENT,
            payload=intent.to_dict(),
        )
        assert bus.send(intent_msg) is True

        # 3. Guardian approves → Conductor routes to Executor
        def guardian_approve(i):
            return RiskVerdict(intent_id=i.intent_id, result=RiskVerdictResult.APPROVED, reason="Within P2 limits")

        allowed, verdict = conductor.process_trade_intent(intent, guardian_approve)
        assert allowed is True

        # 4. Verify messages on bus
        executor_msgs = bus.get_messages(receiver=AgentRole.EXECUTOR)
        assert len(executor_msgs) == 1
        assert executor_msgs[0].message_type == MessageType.APPROVED_INTENT

    def test_guardian_veto_blocks_pipeline(self):
        """Guardian veto stops intent from reaching Executor."""
        bus = MessageBus()
        conductor = Conductor(message_bus=bus)

        intent = TradeIntent(symbol="BTCUSDT", direction="long", size=2.0)

        def guardian_reject(i):
            return RiskVerdict(intent_id=i.intent_id, result=RiskVerdictResult.REJECTED, reason="Exceeds drawdown limit")

        allowed, verdict = conductor.process_trade_intent(intent, guardian_reject)
        assert allowed is False
        assert bus.get_messages(receiver=AgentRole.EXECUTOR) == []


# ─────────────────────────────────────────────
# 11. Edge Cases
# ─────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_conductor(self):
        c = Conductor()
        status = c.get_status()
        assert status["agents_registered"] == 0
        assert status["agents_running"] == 0

    def test_scout_without_bus(self):
        """Scout works without message bus (standalone mode)."""
        scout = ScoutAgent()
        intel = scout.produce_intel(source="test", content="test", symbols=["BTC"])
        assert intel.intel_id.startswith("intel_")
        stats = scout.get_stats()
        assert stats["intel_produced"] == 1

    def test_duplicate_agent_registration(self):
        """Re-registering overwrites previous info."""
        c = Conductor()
        c.register_agent(AgentRole.SCOUT, resource_mode="local")
        c.register_agent(AgentRole.SCOUT, resource_mode="cloud")
        info = c.get_agent_info(AgentRole.SCOUT)
        assert info.resource_mode == "cloud"

    def test_subscriber_error_does_not_crash(self):
        """Bad subscriber callback doesn't crash the bus."""
        bus = MessageBus()
        bus.subscribe(AgentRole.STRATEGIST, lambda m: 1 / 0)  # Will raise
        msg = AgentMessage(
            sender=AgentRole.SCOUT,
            receiver=AgentRole.STRATEGIST,
            message_type=MessageType.INTEL_OBJECT,
        )
        # Should not raise
        assert bus.send(msg) is True
        assert bus.total_messages == 1


# Import SentimentScore for test usage
from app.multi_agent_framework import SentimentScore
