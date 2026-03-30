# Round 2 Fix Plan: Batches 7–12
## Closing the 32% → 85%+ Functional Completion Gap

**Date**: 2026-03-30
**PM/FA Decision**: Governance-first, profitability-focused, 6 independent batches (2-3 sessions each)
**Constraint**: Leverage existing Ollama/Qwen 3.5 (local, free)
**Success Metric**: Each batch independently testable; combined increases functional completion from 32% to 85%+

---

## Executive Summary

### Audit Finding
- **Code completion**: 75% (files written, functions stubbed)
- **Functional completion**: 32% (code that actually executes production logic)
- **Root cause**: 5 critical disconnections between layers:
  1. **Agent Layer**: Only Scout wired; Strategist/Guardian/Analyst/Executor are phantom structs
  2. **Message Bus**: Instantiated but zero subscribers (no message routing)
  3. **Learning Pipeline**: L1 observation records exist; L2-L5 gates defined but no handler code
  4. **Perception Plane**: Injected into context; `register_data()` never called (no data marking)
  5. **L2 AI Engine**: Complete but only manual REST trigger (no autonomous loop)

### Strategy
**Priority order: Things that increase profitability > Architecture elegance**

1. **Batch 7** (Core Agent Loop): Wire Conductor + MessageBus → auto-dispatch to Strategist
2. **Batch 8** (Guardian Shield): Implement Guardian agent with veto power + portfolio conflict detection
3. **Batch 9** (Perception Activation): Call `register_data()` on all market signals + strategy outputs
4. **Batch 10** (Analyst Auto-Run): L1 observation handler + auto-trigger L2 pattern discovery (weekly)
5. **Batch 11** (L2 Autonomous Loop): Auto-trigger L2 reasoning on daily alpha search (overnight runs)
6. **Batch 12** (Exchange Conditionals + Paper→Live Bridge): Stop-loss on exchange side + demo live gating

---

## Batch 7: Core Agent Loop & Conductor Wiring
### Goal
Enable auto-dispatch of market data → Scout → Strategist → Guardian pipeline. Conductor orchestrates all message routing.

### Rationale
- **Current state**: Conductor has 300+ lines but zero production calls
- **Impact**: Unblocks Batches 8–11 (all depend on message routing)
- **Profitability**: Enables strategy execution automation (critical for profitability)

### Specific Tasks

#### Task 7.1: Implement Conductor Core Loop
**File**: `/app/conductor_core_loop.py` (NEW, ~400 lines)

Create the main Conductor orchestration engine:

```python
# Simplified pseudocode structure
class ConductorCoreLoop:
    """
    Orchestrates tick → Scout → Strategist → Guardian → Executor → Paper Engine
    Implements EX-06 §2 (Conductor core responsibilities)
    """

    def __init__(self):
        self.message_queue = queue.PriorityQueue()  # (priority, msg)
        self.lock = threading.RLock()
        self.running = False
        self.loop_thread = None

    def register_agent_handler(self, msg_type: MessageType, handler: Callable):
        """Allow agents to register for message types"""
        self.handlers[msg_type].append(handler)

    def dispatch_message(self, msg: AgentMessage):
        """Thread-safe message dispatch to handler queue"""
        priority = ResourcePriority[msg.sender_role].value
        self.message_queue.put((priority, msg))

    def run_event_loop(self):
        """Main Conductor loop: fetch msg → dispatch to handler → await result"""
        while self.running:
            try:
                priority, msg = self.message_queue.get(timeout=0.1)
                handlers = self.handlers.get(msg.message_type, [])
                for handler in handlers:
                    result = handler(msg)  # Blocks until handler completes
                    self._emit_result_message(msg.msg_id, result)
            except queue.Empty:
                time.sleep(0.01)
            except Exception as e:
                logger.error(f"Conductor loop error: {e}")

    def start(self):
        """Start Conductor event loop in background thread"""
        if not self.running:
            self.running = True
            self.loop_thread = threading.Thread(
                target=self.run_event_loop, daemon=True
            )
            self.loop_thread.start()
            logger.info("Conductor core loop started")

    def stop(self):
        """Gracefully stop Conductor"""
        self.running = False
        if self.loop_thread:
            self.loop_thread.join(timeout=5.0)
```

**Implementation checklist**:
- [ ] Priority queue enforcement (Guardian > Scout > Strategist > Analyst > Scout-routine)
- [ ] Message routing table: `MessageType → [Handlers]`
- [ ] Concurrent safety: `threading.RLock()` around state mutations
- [ ] Timeout protection: handlers > 10s auto-log warning
- [ ] Audit emit: every message dispatch logged to `audit_persistence`

#### Task 7.2: Implement MessageBus Subscriber Registry
**File**: `/app/message_bus.py` (MODIFY existing, ~50 lines added)

Add subscription/dispatch logic:

```python
class MessageBus:
    """
    EX-06 §8.1 — inter-agent message routing.
    Current state: instantiated but zero subscribers.
    Fix: add register_subscriber() + dispatch() + audit trails.
    """

    def __init__(self, conductor: ConductorCoreLoop):
        self.conductor = conductor
        self.subscribers: Dict[MessageType, List[Callable]] = defaultdict(list)
        self.audit_log: List[Tuple[float, str, str]] = []  # (ts, msg_type, destination)

    def subscribe(self, message_type: MessageType, handler: Callable) -> str:
        """
        Agent X registers interest in message_type.
        Returns subscription_id for unsubscribe().
        Emits audit_message_subscription event.
        """
        sub_id = str(uuid.uuid4())
        self.subscribers[message_type].append((sub_id, handler))
        self.audit_log.append((time.time(), message_type.value, handler.__name__))
        logger.info(f"Subscriber {handler.__name__} registered for {message_type}")
        return sub_id

    def dispatch(self, msg: AgentMessage) -> List[Any]:
        """
        1. Find all subscribers for msg.message_type
        2. Dispatch to Conductor priority queue
        3. Collect results
        4. Return combined result
        """
        handlers = self.subscribers.get(msg.message_type, [])
        if not handlers:
            logger.warning(f"No subscribers for {msg.message_type}")
            return []

        results = []
        for sub_id, handler in handlers:
            self.conductor.dispatch_message(msg)  # Puts in queue
            # Conductor will call handler in event loop

        return results
```

**Implementation checklist**:
- [ ] Add `subscribe(message_type, handler)` method
- [ ] Add `dispatch(msg)` method with non-blocking queue insertion
- [ ] Emit `message_subscription` audit events
- [ ] Thread-safe: use `threading.Lock()` for `subscribers` dict
- [ ] Dead subscriber cleanup: track subscriptions with TTL (auto-remove if handler raises 5x)

#### Task 7.3: Wire Conductor into Main Application Loop
**File**: `/app/main.py` (MODIFY, ~30 lines added)

In `create_app()` function:

```python
from .conductor_core_loop import ConductorCoreLoop

def create_app():
    app = FastAPI(...)

    # NEW: Initialize Conductor + MessageBus
    CONDUCTOR = ConductorCoreLoop()
    MESSAGE_BUS = MessageBus(conductor=CONDUCTOR)

    # Register known message handlers
    MESSAGE_BUS.subscribe(MessageType.INTEL_OBJECT, strategist_handler)
    MESSAGE_BUS.subscribe(MessageType.TRADE_INTENT, guardian_handler)
    MESSAGE_BUS.subscribe(MessageType.APPROVED_INTENT, executor_handler)

    # Start Conductor event loop on app startup
    @app.on_event("startup")
    async def startup():
        CONDUCTOR.start()
        logger.info("OpenClaw Conductor initialized")

    @app.on_event("shutdown")
    async def shutdown():
        CONDUCTOR.stop()
        logger.info("OpenClaw Conductor stopped")

    # Inject into pipeline_bridge for tick-by-tick dispatch
    set_conductor_instance(CONDUCTOR)
    set_message_bus_instance(MESSAGE_BUS)

    return app
```

**Implementation checklist**:
- [ ] Import `ConductorCoreLoop` + `MessageBus`
- [ ] Initialize in `create_app()`
- [ ] Register startup/shutdown handlers
- [ ] Inject into `pipeline_bridge.py` via `set_conductor_instance()`

#### Task 7.4: Integration Test Suite
**File**: `/tests/test_conductor_core_loop.py` (NEW, ~400 lines, 25 tests)

**Test cases**:
- [ ] `test_conductor_event_loop_start_stop()` — lifecycle
- [ ] `test_message_queue_fifo()` — queue ordering (non-priority)
- [ ] `test_priority_dispatch()` — Guardian > Scout
- [ ] `test_subscriber_registration()` — add/remove handlers
- [ ] `test_message_dispatch_success()` — msg → handler → result
- [ ] `test_message_dispatch_timeout()` — handler > 10s logs warning
- [ ] `test_concurrent_dispatch()` — 10 threads inserting messages simultaneously
- [ ] `test_audit_trail()` — all dispatches logged
- [ ] `test_dead_subscriber_cleanup()` — handler raises 5x → auto-unsubscribe

### Test Criteria (Batch 7)

```python
def test_batch_7_acceptance():
    """Integration test: E2E message flow"""
    conductor = ConductorCoreLoop()
    msg_bus = MessageBus(conductor=conductor)
    conductor.start()

    # Verify message dispatch works
    msg = AgentMessage(
        msg_id=uuid.uuid4(),
        sender_role=AgentRole.SCOUT,
        message_type=MessageType.INTEL_OBJECT,
        payload={"symbol": "BTCUSDT", "signal": "bullish"}
    )

    results = msg_bus.dispatch(msg)

    # Wait for async dispatch
    time.sleep(0.5)

    # Verify handler was called (check audit log)
    audit = conductor.get_audit_trail()
    assert any(a[1] == "intel_object" for a in audit)

    conductor.stop()
```

### Expected Impact
- **Functional completion**: 32% → **45%** (13 point gain)
  - Enables all downstream agent chains
  - Unblocks automated strategy execution
- **Code coverage**: +120 lines core logic, +400 lines tests
- **Risk**: None (only adds routing; no trading logic changes)

---

## Batch 8: Guardian Agent Implementation
### Goal
Implement Guardian agent with veto power over Strategist intents. Validate risk limits, detect portfolio conflicts.

### Rationale
- **Current state**: Guardian role defined in multi_agent_framework.py but zero handler code
- **Impact**: Prevents simultaneous same-direction orders that violate risk limits
- **Profitability**: Protects against catastrophic losses (unblocks safe autonomous execution)

### Specific Tasks

#### Task 8.1: Guardian Agent Class
**File**: `/app/agents/guardian_agent.py` (NEW, ~350 lines)

```python
from .multi_agent_framework import AgentRole, MessageType, RiskVerdictResult

class GuardianAgent:
    """
    EX-06 §2.1 + EX-06 §9 — Risk approval gate.
    Guardian receives TRADE_INTENT → returns RISK_VERDICT (APPROVED/REJECTED/MODIFIED)

    Conflict resolution: Guardian veto always wins (EX-06 §9)
    """

    def __init__(self, risk_manager: RiskManager, portfolio_state):
        self.role = AgentRole.GUARDIAN
        self.risk_manager = risk_manager
        self.portfolio_state = portfolio_state
        self.decision_history: List[Dict] = []  # For audit

    async def handle_trade_intent(self, msg: AgentMessage) -> AgentMessage:
        """
        Input: TRADE_INTENT from Strategist
        Output: RISK_VERDICT (APPROVED|REJECTED|MODIFIED)

        Checks:
        1. Portfolio directional conflict (already long BTC, strategist wants to short)
        2. Leverage limit per symbol (max 5x)
        3. Correlation conflict (two correlated strategies in same direction)
        4. Sharpe ratio degradation (proposed order would hurt portfolio Sharpe < 1.0)
        5. Max drawdown protection (equity curve)
        """
        intent = msg.payload  # Dict: {"strategy": "ma_cross", "symbol": "BTCUSDT", "side": "buy", ...}

        verdict = {
            "intent_id": intent.get("intent_id"),
            "verdict": RiskVerdictResult.APPROVED,
            "reason": "",
            "modified_quantity": None,
            "modified_leverage": None
        }

        # Check 1: Directional conflict
        current_position = self.portfolio_state.get_position(intent["symbol"])
        if current_position:
            if current_position["side"] != intent["side"]:
                # Conflict: already long, strategist wants short
                verdict["verdict"] = RiskVerdictResult.REJECTED
                verdict["reason"] = f"Portfolio conflict: already {current_position['side']}"
                return self._create_verdict_message(verdict)

        # Check 2: Leverage limit
        proposed_leverage = intent.get("leverage", 1.0)
        if proposed_leverage > 5.0:
            verdict["verdict"] = RiskVerdictResult.MODIFIED
            verdict["modified_leverage"] = 5.0
            verdict["reason"] = "Leverage capped at 5x (risk limit)"

        # Check 3: Correlation conflict
        conflicts = self._detect_correlation_conflicts(intent)
        if conflicts:
            verdict["verdict"] = RiskVerdictResult.REJECTED
            verdict["reason"] = f"Correlation conflict with {conflicts}"

        # Check 4: Sharpe ratio impact
        projected_pnl = self._project_pnl(intent)
        current_sharpe = self.portfolio_state.sharpe_ratio()
        new_sharpe = self._compute_new_sharpe(current_sharpe, projected_pnl)

        if new_sharpe < 1.0:
            verdict["verdict"] = RiskVerdictResult.MODIFIED
            verdict["modified_quantity"] = int(intent["qty"] * 0.5)  # 50% of proposed
            verdict["reason"] = f"Sharpe degradation: {current_sharpe:.2f} → {new_sharpe:.2f}"

        # Record decision for audit
        self.decision_history.append({
            "ts_ms": int(time.time() * 1000),
            "intent_id": intent["intent_id"],
            "verdict": verdict["verdict"].value,
            "reason": verdict["reason"]
        })

        return self._create_verdict_message(verdict)

    def _detect_correlation_conflicts(self, intent: Dict) -> List[str]:
        """
        Check if intent symbol is highly correlated (r > 0.8) with existing positions
        in opposite direction.
        """
        symbol = intent["symbol"]
        side = intent["side"]
        conflicts = []

        for existing_pos in self.portfolio_state.open_positions():
            existing_symbol = existing_pos["symbol"]
            existing_side = existing_pos["side"]

            if existing_side != side:  # Opposite direction
                corr = self._compute_correlation(symbol, existing_symbol)
                if corr > 0.8:
                    conflicts.append(existing_symbol)

        return conflicts

    def _compute_correlation(self, sym1: str, sym2: str) -> float:
        """Compute rolling 24h correlation"""
        # Implementation: use kline_manager to fetch 24h prices
        pass

    def _project_pnl(self, intent: Dict) -> float:
        """Simple projection: (current_price - entry_price) * qty"""
        pass

    def _compute_new_sharpe(self, current_sharpe: float, projected_pnl: float) -> float:
        """Estimate Sharpe after order execution"""
        pass

    def _create_verdict_message(self, verdict: Dict) -> AgentMessage:
        """Wrap verdict in AgentMessage envelope"""
        return AgentMessage(
            msg_id=uuid.uuid4(),
            sender_role=AgentRole.GUARDIAN,
            message_type=MessageType.RISK_VERDICT,
            payload=verdict,
            data_quality=DataQualityLevel.FACT
        )
```

**Implementation checklist**:
- [ ] Directional conflict detection (same symbol, opposite side = reject)
- [ ] Leverage cap enforcement (max 5x per symbol, per EX-04 §3)
- [ ] Correlation conflict detection (r > 0.8, opposite direction = reject)
- [ ] Sharpe ratio impact projection (if drops < 1.0, reduce position 50%)
- [ ] Decision audit trail (record all verdicts with ts + reasoning)
- [ ] Integration with existing `RiskManager` (reuse risk limits from risk_routes.py)

#### Task 8.2: Integrate Guardian into Conductor
**File**: `/app/main.py` (MODIFY, ~20 lines)

In `create_app()` where Conductor is initialized:

```python
from .agents.guardian_agent import GuardianAgent

def create_app():
    # ... existing Conductor setup ...

    # NEW: Create Guardian instance
    guardian = GuardianAgent(
        risk_manager=app.state.risk_manager,  # Inject existing RiskManager
        portfolio_state=app.state.paper_engine  # Inject PaperTradingEngine state
    )

    # Register Guardian handler for TRADE_INTENT messages
    MESSAGE_BUS.subscribe(
        MessageType.TRADE_INTENT,
        handler=guardian.handle_trade_intent
    )
```

**Implementation checklist**:
- [ ] Import `GuardianAgent`
- [ ] Initialize with `RiskManager` + `PaperTradingEngine`
- [ ] Register handler in MESSAGE_BUS

#### Task 8.3: Guardian Tests
**File**: `/tests/test_guardian_agent.py` (NEW, ~450 lines, 30 tests)

**Test cases**:
- [ ] `test_guardian_approves_new_position()` — first order → APPROVED
- [ ] `test_guardian_rejects_conflicting_direction()` — already long, intent short → REJECTED
- [ ] `test_guardian_enforces_leverage_cap()` — intent 10x → MODIFIED to 5x
- [ ] `test_guardian_detects_correlation_conflict()` — BTC long + ETH short (r=0.95) → REJECTED
- [ ] `test_guardian_sharpe_degradation_reduction()` — Sharpe < 1.0 → qty reduced 50%
- [ ] `test_guardian_decision_audit_trail()` — all verdicts logged
- [ ] `test_guardian_concurrent_intents()` — 5 intents from Strategist in parallel
- [ ] `test_guardian_max_drawdown_enforcement()` — portfolio DD > limit → REJECTED

### Test Criteria (Batch 8)

```python
def test_batch_8_acceptance():
    """Guardian veto integration test"""
    guardian = GuardianAgent(
        risk_manager=mock_risk_manager,
        portfolio_state=mock_portfolio_state
    )

    # Scenario 1: New position (should APPROVE)
    intent_1 = AgentMessage(
        message_type=MessageType.TRADE_INTENT,
        payload={"intent_id": "t1", "symbol": "BTCUSDT", "side": "buy", "qty": 1.0}
    )
    verdict = guardian.handle_trade_intent(intent_1)
    assert verdict.payload["verdict"] == RiskVerdictResult.APPROVED

    # Scenario 2: Conflicting direction (should REJECT)
    portfolio_state.add_position({"symbol": "BTCUSDT", "side": "buy"})
    intent_2 = AgentMessage(
        message_type=MessageType.TRADE_INTENT,
        payload={"intent_id": "t2", "symbol": "BTCUSDT", "side": "short"}
    )
    verdict = guardian.handle_trade_intent(intent_2)
    assert verdict.payload["verdict"] == RiskVerdictResult.REJECTED
```

### Expected Impact
- **Functional completion**: 45% → **60%** (15 point gain)
  - Guardian is now a production agent with veto power
  - Enables safe autonomous execution
- **Code coverage**: +350 lines core logic, +450 lines tests
- **Risk reduction**: Prevents simultaneous opposite-direction orders

---

## Batch 9: Perception Data Plane Activation
### Goal
Call `register_data()` on all market signals and strategy outputs. Enable data quality marking for all decision inputs.

### Rationale
- **Current state**: Perception Plane injected but `register_data()` never called (zero data marked)
- **Impact**: All decisions become auditable with cognitive level (fact/inference/hypothesis)
- **Profitability**: Enables informed risk decisions (high confidence data gets bigger positions)

### Specific Tasks

#### Task 9.1: Perception Plane Auto-Marking in Pipeline
**File**: `/app/pipeline_bridge.py` (MODIFY, ~80 lines added)

Add perception plane calls to every data point:

```python
from .perception_data_plane import PerceptionDataPlane, DataSourceType, CognitiveLevel

class PipelineBridge:
    # ... existing code ...

    def __init__(self, ..., perception_plane: PerceptionDataPlane):
        # ... existing ...
        self.perception_plane = perception_plane

    def on_kline_tick(self, symbol: str, kline: Dict):
        """
        Incoming K-line from WebSocket.
        Mark as FACT (exchange source), FRESH.
        """
        self.perception_plane.register_data(
            data_id=f"kline_{symbol}_{kline['time']}",
            source_type=DataSourceType.EXCHANGE_WS,
            cognitive_level=CognitiveLevel.FACT,
            symbol=symbol,
            payload={
                "open": kline["open"],
                "high": kline["high"],
                "low": kline["low"],
                "close": kline["close"],
                "volume": kline["volume"],
                "timestamp_ms": kline["time"]
            },
            metadata={"exchange": "bybit", "interval": "1m"}
        )

        # Continue with normal processing
        self.emit_signal_objects(symbol)

    def on_scout_intel_object(self, intel: IntelObject):
        """
        Incoming IntelObject from Scout.
        Mark as INFERENCE (AI-derived).
        """
        self.perception_plane.register_data(
            data_id=f"scout_{intel.intel_id}",
            source_type=DataSourceType.LOCAL_OLLAMA,  # Or NEWS_FEED if external
            cognitive_level=CognitiveLevel.INFERENCE,
            symbol=intel.symbols[0] if intel.symbols else "UNKNOWN",
            payload={
                "content": intel.content,
                "sentiment": intel.sentiment.value,
                "relevance": intel.relevance_score
            },
            metadata={"source": intel.source, "agent": "scout"}
        )

    def on_strategy_signal(self, strategy_name: str, signal: Dict):
        """
        Outgoing signal from strategy.
        Mark as FACT (computed from facts, deterministic).
        """
        self.perception_plane.register_data(
            data_id=f"strategy_{strategy_name}_{signal['ts']}",
            source_type=DataSourceType.LOCAL_INDICATOR,
            cognitive_level=CognitiveLevel.FACT,
            symbol=signal["symbol"],
            payload={
                "signal_type": signal["type"],  # "entry", "exit"
                "confidence": signal.get("confidence", 1.0),
                "entry_price": signal.get("entry_price"),
                "stop_loss": signal.get("stop_loss"),
                "take_profit": signal.get("take_profit")
            },
            metadata={"strategy": strategy_name, "rule": signal.get("rule_name")}
        )

    def on_trade_intent_submitted(self, intent: Dict):
        """
        Strategist submits TRADE_INTENT to Guardian.
        Mark as INFERENCE (AI decision).
        """
        self.perception_plane.register_data(
            data_id=f"intent_{intent['intent_id']}",
            source_type=DataSourceType.LOCAL_OLLAMA,
            cognitive_level=CognitiveLevel.INFERENCE,
            symbol=intent["symbol"],
            payload={
                "side": intent["side"],
                "qty": intent["qty"],
                "leverage": intent.get("leverage", 1.0),
                "strategy": intent.get("strategy_name"),
                "rationale": intent.get("rationale", "")
            },
            metadata={"agent": "strategist"}
        )

    def on_risk_verdict(self, verdict: Dict):
        """
        Guardian returns RISK_VERDICT.
        Mark as FACT (deterministic rule evaluation).
        """
        self.perception_plane.register_data(
            data_id=f"verdict_{verdict['intent_id']}",
            source_type=DataSourceType.LOCAL_INDICATOR,  # Rules are local
            cognitive_level=CognitiveLevel.FACT,
            symbol=verdict.get("symbol"),
            payload={
                "verdict": verdict["verdict"],
                "reason": verdict.get("reason"),
                "modified_qty": verdict.get("modified_quantity"),
                "modified_leverage": verdict.get("modified_leverage")
            },
            metadata={"agent": "guardian", "intent_id": verdict["intent_id"]}
        )
```

**Implementation checklist**:
- [ ] Add `perception_plane` parameter to `PipelineBridge.__init__()`
- [ ] Call `register_data()` for every tick
- [ ] Call `register_data()` for Scout intel objects
- [ ] Call `register_data()` for strategy signals
- [ ] Call `register_data()` for trade intents
- [ ] Call `register_data()` for risk verdicts
- [ ] Mark correctly: Exchange data = FACT, AI data = INFERENCE, Rules = FACT
- [ ] Include proper metadata (strategy name, agent, rule_name, etc.)

#### Task 9.2: Perception Plane Query Interface for Decisions
**File**: `/app/perception_query_layer.py` (NEW, ~200 lines)

Enable risk decisions to query perception data:

```python
class PerceptionQueryLayer:
    """
    Provides agents with data quality summaries for decision-making.
    E.g., Guardian can ask "What's the confidence level of current BTC price?"
    """

    def __init__(self, perception_plane: PerceptionDataPlane):
        self.perception_plane = perception_plane

    def get_symbol_data_quality(self, symbol: str) -> Dict:
        """
        Return data quality summary for symbol:
        - price_freshness (FRESH/RECENT/STALE/EXPIRED)
        - price_cognitive_level (FACT/INFERENCE/HYPOTHESIS)
        - last_update_ms
        - avg_source_reliability (0.0-1.0)
        """
        # Implementation: query perception_plane for latest symbol data
        recent_data = self.perception_plane.get_data_by_symbol(
            symbol,
            limit=100,
            lookback_seconds=3600
        )

        if not recent_data:
            return {"freshness": "EXPIRED", "cognitive_level": "HYPOTHESIS"}

        latest = recent_data[0]
        return {
            "freshness": latest.freshness.value,
            "cognitive_level": latest.cognitive_level.value,
            "last_update_ms": latest.timestamp_ms,
            "source_type": latest.source_type.value,
            "avg_reliability": sum(d.quality.source_reliability for d in recent_data) / len(recent_data)
        }

    def can_execute_new_entry(self, symbol: str) -> Tuple[bool, str]:
        """
        Query: is current data fresh enough to enter new position?
        EX-07 §2.3: STALE price → no new entry
        """
        quality = self.get_symbol_data_quality(symbol)

        if quality["freshness"] == "EXPIRED":
            return False, "Price data expired > 2 hours"
        elif quality["freshness"] == "STALE":
            return False, "Price data stale (30min-2h)"

        return True, "Data fresh enough"

    def get_decision_confidence(self, intent_id: str) -> float:
        """
        Return confidence of decision: avg of all input data confidence levels.
        E.g., if Scout intel is INFERENCE (0.8) + Price is FACT (1.0)
        → decision confidence = 0.9
        """
        # Implementation: trace back to original intent, find all source data
        # Weight by cognitive level: FACT=1.0, INFERENCE=0.8, HYPOTHESIS=0.5
        pass
```

**Implementation checklist**:
- [ ] Query by symbol to get data quality summary
- [ ] Query by freshness (can_execute_new_entry check)
- [ ] Compute decision confidence as weighted average
- [ ] Thread-safe access to perception_plane state

#### Task 9.3: Tests
**File**: `/tests/test_perception_activation.py` (NEW, ~350 lines, 25 tests)

**Test cases**:
- [ ] `test_register_kline_as_fact()` — K-line marked as FACT
- [ ] `test_register_scout_intel_as_inference()` — Scout signal marked as INFERENCE
- [ ] `test_register_strategy_signal_as_fact()` — Strategy signal marked as FACT (deterministic)
- [ ] `test_perception_query_symbol_quality()` — query data quality for symbol
- [ ] `test_perception_freshness_check()` — STALE price blocks new entry
- [ ] `test_perception_decision_confidence()` — weighted average confidence
- [ ] `test_perception_end_to_end()` — full pipeline: tick → mark → query → decision

### Test Criteria (Batch 9)

```python
def test_batch_9_acceptance():
    """Perception plane activation test"""
    perception = PerceptionDataPlane()
    bridge = PipelineBridge(..., perception_plane=perception)
    query = PerceptionQueryLayer(perception)

    # Register a K-line tick
    bridge.on_kline_tick("BTCUSDT", {
        "time": 1700000000000,
        "open": 50000, "high": 51000, "low": 49000, "close": 50500,
        "volume": 100
    })

    # Query data quality
    quality = query.get_symbol_data_quality("BTCUSDT")
    assert quality["freshness"] == "FRESH"
    assert quality["cognitive_level"] == "fact"

    # Register stale Scout intel
    intel = IntelObject(...)
    bridge.on_scout_intel_object(intel)

    # Simulate time passing
    time.sleep(2)
    perception.update_freshness()

    # Query should reflect staleness
    quality = query.get_symbol_data_quality("BTCUSDT")
    # (depends on time elapsed)
```

### Expected Impact
- **Functional completion**: 60% → **70%** (10 point gain)
  - All decisions now auditable with data quality marking
  - Enables confidence-based risk sizing
- **Code coverage**: +200 lines core, +350 lines tests
- **Compliance**: Enables EX-07 data quality enforcement

---

## Batch 10: Analyst Agent L1 Handler + Auto-Trigger L2
### Goal
Implement Analyst agent L1 observation handler. Auto-trigger L2 pattern discovery weekly.

### Rationale
- **Current state**: L1 observation records exist; L2-L5 gates defined but no handler code
- **Impact**: Weekly learning cycle identifies patterns (e.g., "MA cross wins 60% on high volatility")
- **Profitability**: Enables strategy parameterization based on learned patterns

### Specific Tasks

#### Task 10.1: Analyst L1 Observation Handler
**File**: `/app/agents/analyst_agent.py` (NEW, ~450 lines)

```python
from .learning_tier_gate import LearningTier, AnalystState, Observation

class AnalystAgent:
    """
    EX-05 §3 — Analyst evolution engine L1–L5.
    Task 10.1 implements L1 (Post-Trade Review):
      - Passive observation recording (zero cost)
      - Basic metrics: win rate, Sharpe, drawdown
      - Audit trail for all trades

    L2-L5 handlers added in future batches.
    """

    def __init__(self, learning_gate: LearningTierGate, audit_sink):
        self.role = AgentRole.ANALYST
        self.learning_gate = learning_gate
        self.audit_sink = audit_sink
        self.current_tier = LearningTier.L1
        self.observations: List[Observation] = []

    async def handle_round_trip_complete(self, msg: AgentMessage) -> None:
        """
        Input: ROUND_TRIP_COMPLETE from Executor
        L1 action: record passive observation

        Observation includes:
        - Entry signal (strategy, rule, timestamp)
        - Execution details (fill price, qty, slippage)
        - Exit signal (timestamp, exit price, reason)
        - P&L (absolute, %)
        - Holding time
        - Market regime (trending/ranging/high-vol)
        - Strategy performance at entry time (Sharpe, win rate)
        """
        report = msg.payload  # ExecutionReport

        obs = Observation(
            obs_id=str(uuid.uuid4()),
            ts_ms=int(time.time() * 1000),

            # Trade metadata
            strategy_name=report["strategy"],
            symbol=report["symbol"],
            side=report["side"],
            qty=report["qty"],

            # Entry
            entry_ts_ms=report["entry_ts_ms"],
            entry_price=report["entry_price"],
            entry_signal_rule=report["signal_rule"],
            entry_slippage=report["entry_price"] - report["trade_price"],

            # Exit
            exit_ts_ms=report["exit_ts_ms"],
            exit_price=report["exit_price"],
            exit_reason=report["exit_reason"],  # "take_profit" / "stop_loss" / "time_stop"

            # P&L
            pnl_absolute=report["pnl"],
            pnl_percent=report["pnl_percent"],

            # Timing
            holding_time_seconds=(report["exit_ts_ms"] - report["entry_ts_ms"]) / 1000,

            # Market context
            regime_at_entry=report.get("regime", "unknown"),
            volatility_at_entry=report.get("atr", 0),

            # Strategy state at entry
            strategy_win_rate_at_entry=report.get("strategy_win_rate", 0.0),
            strategy_sharpe_at_entry=report.get("strategy_sharpe", 0.0),

            # Data quality
            price_data_quality=report.get("price_quality", "RECENT"),
            signal_confidence=report.get("signal_confidence", 0.5)
        )

        # Store observation
        self.observations.append(obs)
        self.learning_gate.record_observation(obs)

        logger.info(f"L1 observation recorded: {strategy}_{symbol} PnL={pnl_percent:.1%}")

        # Emit audit event
        self.audit_sink.emit("analyst_l1_observation_recorded", {
            "obs_id": obs.obs_id,
            "strategy": obs.strategy_name,
            "symbol": obs.symbol,
            "pnl": obs.pnl_percent,
            "regime": obs.regime_at_entry
        })

    def get_l1_metrics(self) -> Dict:
        """
        Return L1 summary metrics (passive):
        - total_trades
        - win_rate
        - sharpe_ratio
        - max_drawdown
        - avg_holding_time
        """
        if not self.observations:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "avg_holding_time_seconds": 0
            }

        pnl_list = [o.pnl_percent for o in self.observations]
        win_count = sum(1 for p in pnl_list if p > 0)

        return {
            "total_trades": len(self.observations),
            "win_rate": win_count / len(self.observations) if self.observations else 0.0,
            "sharpe_ratio": self._compute_sharpe(pnl_list),
            "max_drawdown": self._compute_max_drawdown(pnl_list),
            "avg_holding_time_seconds": sum(o.holding_time_seconds for o in self.observations) / len(self.observations),
            "avg_pnl_percent": sum(pnl_list) / len(pnl_list),
            "observation_count": len(self.observations)
        }

    def _compute_sharpe(self, pnl_list: List[float]) -> float:
        """Sharpe ratio of trade returns (assuming 252 trading days/year)"""
        if len(pnl_list) < 2:
            return 0.0
        import statistics
        mean_pnl = statistics.mean(pnl_list)
        stdev_pnl = statistics.stdev(pnl_list) if len(pnl_list) > 1 else 0.0
        if stdev_pnl == 0:
            return 0.0
        # Scale to annual
        sharpe = (mean_pnl / stdev_pnl) * math.sqrt(252)
        return sharpe

    def _compute_max_drawdown(self, pnl_list: List[float]) -> float:
        """Max drawdown from cumulative P&L"""
        if not pnl_list:
            return 0.0
        cum_pnl = 0
        peak = 0
        max_dd = 0
        for pnl in pnl_list:
            cum_pnl += pnl
            if cum_pnl > peak:
                peak = cum_pnl
            dd = (peak - cum_pnl) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        return max_dd
```

**Implementation checklist**:
- [ ] `handle_round_trip_complete()` creates Observation from ExecutionReport
- [ ] Call `learning_gate.record_observation()` for tier eligibility tracking
- [ ] Compute L1 metrics: win rate, Sharpe, max drawdown, avg holding time
- [ ] Thread-safe observation storage
- [ ] Audit emit for all observations

#### Task 10.2: L2 Pattern Discovery Trigger
**File**: `/app/agents/analyst_agent.py` (MODIFY, ~250 lines added to Task 10.1)

Add L2 auto-trigger when conditions met:

```python
class AnalystAgent:
    # ... L1 code from Task 10.1 ...

    def check_tier_promotion(self) -> Optional[PromotionEvent]:
        """
        Check if Analyst should promote from L1 → L2.
        EX-05 §3.2: L2 unlocks at 500+ observations + win_rate > 20%
        """
        metrics = self.get_l1_metrics()

        if (metrics["observation_count"] >= 500 and
            metrics["win_rate"] > 0.20):

            logger.info("Analyst L1→L2 promotion eligible!")
            return PromotionEvent.AUTO_PROMOTE_L1_TO_L2

        return None

    async def handle_l2_pattern_discovery_trigger(self):
        """
        Weekly trigger: analyze all observations, find patterns.
        Run locally (Ollama Qwen 3.5).
        """
        if self.current_tier < LearningTier.L2:
            logger.warning("L2 not unlocked, skipping pattern discovery")
            return

        metrics = self.get_l1_metrics()

        # Group observations by regime
        obs_by_regime = defaultdict(list)
        for obs in self.observations[-500:]:  # Last 500 (weekly volume)
            obs_by_regime[obs.regime_at_entry].append(obs)

        # Query Ollama to find patterns
        patterns = []
        for regime, regime_obs in obs_by_regime.items():
            if not regime_obs:
                continue

            pattern = await self._discover_patterns_in_regime(regime, regime_obs)
            if pattern:
                patterns.append(pattern)

        # Record patterns (enables L3)
        for pattern in patterns:
            self.learning_gate.record_pattern(pattern)

        logger.info(f"L2 pattern discovery: found {len(patterns)} patterns")
        return patterns

    async def _discover_patterns_in_regime(self, regime: str, obs_list: List[Observation]) -> Optional[Dict]:
        """
        Ollama-based pattern discovery for single regime.
        Example patterns:
        - "MA cross wins 65% in trending regime"
        - "Grid works best high-vol, loses in ranging"
        - "Funding arb avg 0.3% per day"
        """
        # Build summary for Ollama
        summary = {
            "regime": regime,
            "total_trades": len(obs_list),
            "win_rate": sum(1 for o in obs_list if o.pnl_percent > 0) / len(obs_list),
            "avg_pnl": sum(o.pnl_percent for o in obs_list) / len(obs_list),
            "strategies": list(set(o.strategy_name for o in obs_list)),
            "sharpe": self._compute_sharpe([o.pnl_percent for o in obs_list])
        }

        prompt = f"""
        Analyze this trading performance data and identify patterns:

        Regime: {summary['regime']}
        Total trades: {summary['total_trades']}
        Win rate: {summary['win_rate']:.1%}
        Avg P&L: {summary['avg_pnl']:.2%}
        Sharpe: {summary['sharpe']:.2f}
        Strategies tested: {', '.join(summary['strategies'])}

        Questions:
        1. Which strategy(ies) performed best in this regime?
        2. What's the statistically significant win rate vs random?
        3. Any unexpected patterns or anomalies?

        Respond as JSON: {"pattern": "description", "confidence": 0.0-1.0, "recommendation": "action"}
        """

        # Call Ollama (local, fast)
        from .ollama_client import get_ollama_client
        client = get_ollama_client()

        try:
            response = await client.generate(
                model="qwen:3.5",
                prompt=prompt,
                temperature=0.3,  # Deterministic
                top_p=0.8
            )

            pattern_json = self._extract_json(response)
            if pattern_json:
                return {
                    "pattern_id": str(uuid.uuid4()),
                    "regime": regime,
                    "description": pattern_json["pattern"],
                    "confidence": pattern_json["confidence"],
                    "recommendation": pattern_json.get("recommendation"),
                    "ts_ms": int(time.time() * 1000)
                }
        except Exception as e:
            logger.error(f"Ollama pattern discovery failed: {e}")

        return None
```

**Implementation checklist**:
- [ ] Implement `check_tier_promotion()` (L1→L2 gate: 500+ obs + 20% win rate)
- [ ] Implement `handle_l2_pattern_discovery_trigger()` (weekly batch)
- [ ] Group observations by regime
- [ ] Call Ollama to analyze patterns per regime
- [ ] Record patterns in `learning_gate`
- [ ] Emit audit events for all patterns

#### Task 10.3: Weekly Scheduler for L2 Trigger
**File**: `/app/analyst_scheduler.py` (NEW, ~100 lines)

Wire L2 discovery into daily task scheduler:

```python
import schedule
import threading

class AnalystScheduler:
    """
    Schedule periodic Analyst tasks:
    - Weekly: L2 pattern discovery (Sunday 00:00 UTC)
    - Daily: tier eligibility check
    - Hourly: L1 metrics update (for real-time dashboards)
    """

    def __init__(self, analyst: AnalystAgent):
        self.analyst = analyst
        self.scheduler = schedule.Scheduler()
        self.running = False
        self.thread = None

    def schedule_jobs(self):
        """Define recurring tasks"""
        # Weekly L2 discovery (Sunday midnight UTC)
        self.scheduler.every().sunday.at("00:00").do(
            self._run_l2_discovery
        )

        # Daily tier check (every day 01:00 UTC)
        self.scheduler.every().day.at("01:00").do(
            self._check_tier_promotion
        )

        # Hourly metrics refresh
        self.scheduler.every().hour.do(
            self._refresh_metrics
        )

    def _run_l2_discovery(self):
        """Async wrapper for L2 discovery"""
        logger.info("Analyst: starting L2 pattern discovery")
        asyncio.run(self.analyst.handle_l2_pattern_discovery_trigger())

    def _check_tier_promotion(self):
        """Check if tier promotion is due"""
        promotion_event = self.analyst.check_tier_promotion()
        if promotion_event:
            logger.info(f"Analyst promotion eligible: {promotion_event}")

    def _refresh_metrics(self):
        """Update L1 metrics (for dashboards)"""
        metrics = self.analyst.get_l1_metrics()
        # Store in Redis or database for dashboard

    def run(self):
        """Start scheduler thread"""
        if not self.running:
            self.running = True
            self.schedule_jobs()
            self.thread = threading.Thread(
                target=self._scheduler_loop, daemon=True
            )
            self.thread.start()
            logger.info("Analyst scheduler started")

    def _scheduler_loop(self):
        """Main scheduler loop"""
        while self.running:
            self.scheduler.run_pending()
            time.sleep(60)  # Check every minute

    def stop(self):
        """Stop scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
```

**Implementation checklist**:
- [ ] Schedule L2 discovery weekly (Sunday midnight UTC)
- [ ] Schedule tier eligibility check daily
- [ ] Schedule metrics refresh hourly
- [ ] Run in background thread (daemon=True)

#### Task 10.4: Tests
**File**: `/tests/test_analyst_agent.py` (NEW, ~500 lines, 35 tests)

**Test cases**:
- [ ] `test_analyst_l1_observation_recording()` — round trip → observation
- [ ] `test_analyst_l1_metrics_calculation()` — win rate, Sharpe, drawdown
- [ ] `test_analyst_l1_to_l2_promotion_gate()` — 500+ obs + 20% win rate → eligible
- [ ] `test_analyst_l2_pattern_discovery()` — find patterns via Ollama
- [ ] `test_analyst_pattern_per_regime()` — group by regime, analyze each
- [ ] `test_analyst_scheduler_weekly_trigger()` — L2 runs weekly
- [ ] `test_analyst_scheduler_tier_check_daily()` — promotion check daily

### Test Criteria (Batch 10)

```python
def test_batch_10_acceptance():
    """Analyst L1→L2 flow test"""
    analyst = AnalystAgent(learning_gate, audit_sink)
    scheduler = AnalystScheduler(analyst)
    scheduler.run()

    # Simulate 500 round-trip completions
    for i in range(500):
        msg = AgentMessage(
            message_type=MessageType.ROUND_TRIP_COMPLETE,
            payload={
                "strategy": "ma_cross",
                "symbol": "BTCUSDT",
                "entry_ts_ms": int(time.time() * 1000) - 3600000,
                "exit_ts_ms": int(time.time() * 1000),
                "pnl_percent": 0.05 if i % 5 == 0 else -0.02,  # 20% win rate
                "regime": "trending" if i < 250 else "ranging"
            }
        )
        asyncio.run(analyst.handle_round_trip_complete(msg))

    # Check metrics
    metrics = analyst.get_l1_metrics()
    assert metrics["total_trades"] == 500
    assert metrics["win_rate"] >= 0.20

    # Check L2 eligibility
    promotion = analyst.check_tier_promotion()
    assert promotion == PromotionEvent.AUTO_PROMOTE_L1_TO_L2

    # Verify patterns would be discovered
    patterns = asyncio.run(analyst.handle_l2_pattern_discovery_trigger())
    assert len(patterns) > 0

    scheduler.stop()
```

### Expected Impact
- **Functional completion**: 70% → **77%** (7 point gain)
  - L1 fully functional (observation recording)
  - L2 callable (pattern discovery)
  - Analyst agent wired into message bus
- **Code coverage**: +450 lines core logic (Analyst + Scheduler), +500 lines tests
- **Operational benefit**: Weekly learning cycle identifies strategy win conditions

---

## Batch 11: L2 Autonomous Alpha Search Loop
### Goal
Implement autonomous overnight L2 reasoning loop. Daily trigger searches for alpha, generates strategy variants.

### Rationale
- **Current state**: L2 AI Engine complete but only manual REST trigger (no autonomous loop)
- **Impact**: Daily overnight reasoning finds novel alpha signals (e.g., "high-vol BTC correlates with funding rate spikes")
- **Profitability**: Discovers alpha factors not coded in static strategies; feeds into Batch 12 variant deployment

### Specific Tasks

#### Task 11.1: L2 Daily Auto-Trigger Scheduler
**File**: `/app/layer2_daily_scheduler.py` (NEW, ~250 lines)

```python
import schedule
import asyncio
from .layer2_engine import Layer2Engine
from .layer2_types import Layer2Config

class Layer2DailyScheduler:
    """
    Schedule L2 autonomous alpha search:
    - Daily trigger: 02:00 UTC (off-market hours)
    - Session budget: $2 USD (Sonnet model)
    - Search focus: regime-specific alpha factors
    - Output: recommendations for L3 hypothesis testing
    """

    def __init__(self, layer2_engine: Layer2Engine, config: Layer2Config):
        self.layer2 = layer2_engine
        self.config = config
        self.scheduler = schedule.Scheduler()
        self.running = False
        self.thread = None

        # Track recent findings to avoid redundant searches
        self.recent_findings: List[Dict] = []  # Last 7 days of findings

    def schedule_jobs(self):
        """Daily L2 alpha search at 02:00 UTC"""
        self.scheduler.every().day.at("02:00").do(
            self._run_daily_alpha_search
        )

    def _run_daily_alpha_search(self):
        """Trigger L2 reasoning session"""
        logger.info("Layer2: starting daily alpha search (02:00 UTC)")
        asyncio.run(self._daily_alpha_search_async())

    async def _daily_alpha_search_async(self):
        """
        Main L2 session:
        1. Fetch current market state (volatility, regime, correlations)
        2. Fetch strategy performance vs regime (from Analyst L1 metrics)
        3. Query: "What alpha factors correlate with strategy wins in current regime?"
        4. Generate 3-5 hypothesis recommendations
        5. Store for L3 (if promoted)
        """
        try:
            # Step 1: Get current market context
            market_state = self._fetch_market_state()

            # Step 2: Get recent strategy performance
            strategy_performance = self._fetch_strategy_metrics()

            # Step 3: Construct search prompt
            prompt = self._build_search_prompt(market_state, strategy_performance)

            # Step 4: Run L2 session (Sonnet model, $2 budget)
            config = Layer2Config(
                model_id="claude-sonnet",
                session_budget_usd=2.0,
                allow_web_search=True,
                include_recent_trades=True
            )

            session = await self.layer2.start_session(
                prompt=prompt,
                config=config,
                tags=["daily_alpha_search", f"regime_{market_state['regime']}"]
            )

            # Step 5: Wait for completion
            while session.state != SESSION_STATE_COMPLETED:
                if session.state == SESSION_STATE_FAILED:
                    logger.error(f"L2 session failed: {session.error}")
                    return
                if session.state == SESSION_STATE_BUDGET_EXCEEDED:
                    logger.warning(f"L2 session budget exceeded (normal)")
                    break

                await asyncio.sleep(5)

            # Step 6: Extract recommendations
            recommendations = [r for r in session.recommendations if r.confidence > 0.6]

            if recommendations:
                logger.info(f"L2 alpha search found {len(recommendations)} recommendations")
                self._record_findings(recommendations, market_state)
            else:
                logger.info("L2 alpha search: no high-confidence findings")

        except Exception as e:
            logger.error(f"L2 daily search error: {e}", exc_info=True)

    def _fetch_market_state(self) -> Dict:
        """Current market conditions"""
        # Implementation: query KlineManager + market_regime
        return {
            "regime": "trending",  # or "ranging", "high_vol"
            "atr_14": 1250,  # Average True Range
            "implied_vol": 0.65,
            "funding_rate_8h": 0.0012,
            "correlation_matrix": {...}  # BTC-ETH, etc.
        }

    def _fetch_strategy_metrics(self) -> Dict:
        """Strategy performance vs regime"""
        # Implementation: query Analyst L1 metrics, group by regime
        return {
            "ma_cross": {
                "trending": {"win_rate": 0.58, "sharpe": 1.2},
                "ranging": {"win_rate": 0.35, "sharpe": -0.5}
            },
            "grid": {
                "high_vol": {"win_rate": 0.62, "sharpe": 0.8},
                "low_vol": {"win_rate": 0.48, "sharpe": 0.1}
            }
        }

    def _build_search_prompt(self, market_state: Dict, perf: Dict) -> str:
        """Construct L2 search prompt"""
        return f"""
        You are the Layer 2 Alpha Discovery Engine for OpenClaw trading system.

        ## Current Market State
        - Regime: {market_state['regime']}
        - ATR(14): {market_state['atr_14']}
        - Implied Vol: {market_state['implied_vol']}
        - 8h Funding Rate: {market_state['funding_rate_8h']}

        ## Recent Strategy Performance
        {json.dumps(perf, indent=2)}

        ## Your Task
        Identify 3-5 alpha factors that explain strategy wins/losses.
        Focus on:
        1. Regime-specific patterns (MA cross wins in trending, grid wins in high-vol)
        2. Correlation patterns (funding rate spikes during certain market phases)
        3. Timing patterns (best trade times, worst times)
        4. Feature importance (which market metrics matter most)

        For each factor:
        - State the hypothesis clearly
        - Estimate success probability
        - Recommend how to test it (paper trading experiment)

        Output as JSON array of recommendations.
        """

    def _record_findings(self, recommendations: List, market_state: Dict):
        """Store findings for L3 hypothesis testing"""
        finding = {
            "finding_id": str(uuid.uuid4()),
            "ts_ms": int(time.time() * 1000),
            "regime": market_state["regime"],
            "recommendations": [
                {
                    "hypothesis": r.content,
                    "confidence": r.confidence,
                    "suggested_experiment": r.metadata.get("experiment")
                }
                for r in recommendations
            ]
        }

        self.recent_findings.append(finding)
        if len(self.recent_findings) > 7:  # Keep last 7 days
            self.recent_findings.pop(0)

        # Emit audit event
        logger.info(f"L2 finding recorded: {finding['finding_id']}")

    def run(self):
        """Start scheduler"""
        if not self.running:
            self.running = True
            self.schedule_jobs()
            self.thread = threading.Thread(
                target=self._scheduler_loop, daemon=True
            )
            self.thread.start()
            logger.info("Layer2 daily scheduler started")

    def _scheduler_loop(self):
        """Main loop"""
        while self.running:
            self.scheduler.run_pending()
            time.sleep(60)

    def stop(self):
        """Stop scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
```

**Implementation checklist**:
- [ ] Schedule daily L2 at 02:00 UTC (off-market)
- [ ] Fetch market state (regime, volatility, funding rate)
- [ ] Fetch strategy metrics from Analyst L1
- [ ] Build prompt with market + performance context
- [ ] Run L2 session with $2 budget
- [ ] Extract recommendations (confidence > 0.6)
- [ ] Record findings for L3 (next batch)
- [ ] Thread-safe

#### Task 11.2: L2 Session Cost Tracking & Auto-Adjustment
**File**: `/app/layer2_budget_adjuster.py` (NEW, ~200 lines)

Adaptive budget based on finding quality:

```python
class Layer2BudgetAdjuster:
    """
    Track L2 session effectiveness.
    If findings lead to profitable L3 experiments → increase daily budget
    If findings don't confirm → decrease budget

    Keeps total L2 cost under $100/month while maximizing alpha discovery.
    """

    def __init__(self, config_sink):
        self.config_sink = config_sink
        self.session_history: List[Dict] = []
        self.finding_confirmations: Dict[str, bool] = {}  # finding_id → confirmed

    def record_session(self, session_id: str, cost_usd: float, finding_count: int):
        """Record L2 session result"""
        self.session_history.append({
            "session_id": session_id,
            "cost_usd": cost_usd,
            "finding_count": finding_count,
            "ts_ms": int(time.time() * 1000),
            "roi": None  # Set later when L3 confirms/rejects
        })

    def confirm_finding(self, finding_id: str, confirmed: bool):
        """L3 experiment result: did finding predict profitable trades?"""
        self.finding_confirmations[finding_id] = confirmed

        # Recalculate ROI
        self._update_roi()

    def _update_roi(self):
        """
        Calculate: (profitable_findings / total_findings) × (cost_per_finding)
        If ROI > 2% (e.g., 5 profitable trades × 0.5% edge = 2.5% per finding)
        → increase daily budget by 10%
        """
        total_findings = len(self.finding_confirmations)
        if total_findings < 10:
            return  # Need more data

        confirmed_count = sum(1 for c in self.finding_confirmations.values() if c)
        confirmation_rate = confirmed_count / total_findings

        if confirmation_rate > 0.4:  # > 40% of findings confirm
            logger.info(f"L2 confirmation rate {confirmation_rate:.1%}: increasing budget")
            self._increase_daily_budget()
        elif confirmation_rate < 0.2:  # < 20%
            logger.info(f"L2 confirmation rate {confirmation_rate:.1%}: decreasing budget")
            self._decrease_daily_budget()

    def _increase_daily_budget(self):
        """Increase daily L2 budget by 10% (max $3/day = $90/month)"""
        current = self.config_sink.get_config("layer2.daily_budget_usd")
        new_budget = min(current * 1.1, 3.0)
        self.config_sink.set_config("layer2.daily_budget_usd", new_budget)
        logger.info(f"L2 budget increased to ${new_budget:.2f}/day")

    def _decrease_daily_budget(self):
        """Decrease daily L2 budget by 10% (min $0.5/day)"""
        current = self.config_sink.get_config("layer2.daily_budget_usd")
        new_budget = max(current * 0.9, 0.5)
        self.config_sink.set_config("layer2.daily_budget_usd", new_budget)
        logger.info(f"L2 budget decreased to ${new_budget:.2f}/day")
```

**Implementation checklist**:
- [ ] Track session cost, finding count
- [ ] Record L3 confirmation results
- [ ] Compute confirmation rate
- [ ] Auto-adjust budget if > 40% or < 20% confirmation
- [ ] Keep daily budget between $0.5 and $3 (max $90/month)

#### Task 11.3: Tests
**File**: `/tests/test_layer2_daily_scheduler.py` (NEW, ~400 lines, 30 tests)

**Test cases**:
- [ ] `test_l2_daily_trigger_at_02_utc()` — scheduler fires at correct time
- [ ] `test_l2_search_prompt_construction()` — prompt includes market state + perf
- [ ] `test_l2_session_config_budget_limit()` — session budget = $2 max
- [ ] `test_l2_recommendation_filtering()` — only confidence > 0.6
- [ ] `test_l2_finding_storage()` — findings recorded, max 7-day history
- [ ] `test_l2_budget_adjuster_increase()` — > 40% confirmation → budget increase
- [ ] `test_l2_budget_adjuster_decrease()` — < 20% confirmation → budget decrease
- [ ] `test_l2_e2e_daily_search()` — full flow: trigger → session → recommendations

### Test Criteria (Batch 11)

```python
def test_batch_11_acceptance():
    """L2 autonomous alpha search test"""
    layer2 = Layer2Engine(config)
    scheduler = Layer2DailyScheduler(layer2, config)
    scheduler.run()

    # Manually trigger (instead of waiting 24h)
    scheduler._run_daily_alpha_search()

    # Wait for L2 session to complete
    time.sleep(30)

    # Verify findings were recorded
    assert len(scheduler.recent_findings) > 0
    finding = scheduler.recent_findings[0]
    assert "recommendations" in finding
    assert len(finding["recommendations"]) > 0

    # Verify each recommendation has hypothesis + confidence
    for rec in finding["recommendations"]:
        assert "hypothesis" in rec
        assert 0 <= rec["confidence"] <= 1.0

    scheduler.stop()
```

### Expected Impact
- **Functional completion**: 77% → **82%** (5 point gain)
  - L2 autonomous loop now operational
  - Daily alpha discovery running
- **Code coverage**: +250 lines core logic (Scheduler + Budget Adjuster), +400 lines tests
- **Business impact**: Discovers novel alpha factors; feeds L3 hypothesis testing

---

## Batch 12: Exchange Conditional Orders + Paper→Live Bridge
### Goal
Implement exchange-side stop-loss orders. Create PaperLiveGate for safe transition to live trading.

### Rationale
- **Current state**: Stop-loss logic only in Paper Engine (no exchange protection)
- **Impact**: Protects against catastrophic loss if system crashes mid-trade
- **Profitability**: Enables live trading with safety guardrails

### Specific Tasks

#### Task 12.1: Protective Order Manager Integration
**File**: `/app/protective_order_manager.py` (MODIFY existing, ~150 lines added)

Enhance existing protective_order_manager.py to wire into Paper→Live flow:

```python
# EXISTING: class ProtectiveOrderManager (lines 1-200)
# Already handles: hard stop, trailing stop, time stop
# MODIFY: Add wire to exchange API

class ProtectiveOrderManager:
    # ... existing code ...

    async def submit_stop_loss_to_exchange(
        self,
        position_id: str,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        stop_loss_price: float,
        order_type: str = "STOP"  # "STOP", "TRAILING_STOP"
    ) -> Dict:
        """
        NEW: Submit stop-loss order directly to exchange (Bybit).
        This creates a conditional order that executes automatically
        if price breaches stop_loss_price.

        Returns: {"order_id": str, "status": "pending", ...}
        """
        if not self.bybit_connector:
            raise ValueError("Bybit connector not available (live mode only)")

        # Determine order details
        stop_side = "Sell" if side == "buy" else "Buy"

        if order_type == "STOP":
            # Simple stop: triggers at stop_loss_price
            response = await self.bybit_connector.create_conditional_order(
                symbol=symbol,
                order_type="STOP",
                side=stop_side,
                qty=qty,
                stop_price=stop_loss_price,
                position_mode="OneWay",
                reduce_only=True  # Close position, don't open short
            )

        elif order_type == "TRAILING_STOP":
            # Trailing stop: follows price up by trailing_distance
            trailing_distance = entry_price - stop_loss_price
            response = await self.bybit_connector.create_conditional_order(
                symbol=symbol,
                order_type="TRAILING_STOP",
                side=stop_side,
                qty=qty,
                trailing_amount=trailing_distance,
                position_mode="OneWay",
                reduce_only=True
            )

        # Record in audit
        order_record = {
            "exchange_order_id": response["orderId"],
            "position_id": position_id,
            "symbol": symbol,
            "stop_price": stop_loss_price,
            "status": "active",
            "created_ts_ms": int(time.time() * 1000)
        }

        self.exchange_stops[response["orderId"]] = order_record

        logger.info(f"Exchange stop submitted: {symbol} SL={stop_loss_price}")

        return {
            "order_id": response["orderId"],
            "status": "active",
            "stop_price": stop_loss_price
        }

    async def cancel_exchange_stop(self, exchange_order_id: str) -> None:
        """Cancel stop-loss order on exchange"""
        if not self.bybit_connector:
            return

        await self.bybit_connector.cancel_order(exchange_order_id)
        if exchange_order_id in self.exchange_stops:
            del self.exchange_stops[exchange_order_id]

        logger.info(f"Exchange stop cancelled: {exchange_order_id}")
```

**Implementation checklist**:
- [ ] Add `submit_stop_loss_to_exchange()` method
- [ ] Support both STOP and TRAILING_STOP
- [ ] Track exchange stops in `self.exchange_stops` dict
- [ ] Call Bybit API to create conditional orders
- [ ] Set `reduce_only=True` (close position, don't short)
- [ ] Audit trail for all exchange stops

#### Task 12.2: PaperLiveGate Implementation
**File**: `/app/paper_live_gate.py` (MODIFY existing, ~200 lines added)

Wire up PaperLiveGate to transition from Paper to Live mode:

```python
# EXISTING: class PaperLiveGate (lines 1-150)
# Already handles: gate conditions, risk mode control
# MODIFY: Add live execution pathway

class PaperLiveGate:
    # ... existing code ...

    async def approve_live_execution(
        self,
        intent: Dict,
        paper_result: Dict
    ) -> Dict:
        """
        NEW: Gateway for live execution.
        Checks:
        1. Paper trading has been profitable (Sharpe > 1.0 last 30 days)
        2. Live mode is explicitly enabled by operator
        3. Position size in live mode = 10% of paper mode (conservative ramp-up)
        4. Stop-loss is submitted to exchange first

        Returns: {"approved": bool, "live_qty": float, "reason": str}
        """

        # Gate 1: Paper trading profitability
        paper_metrics = self._compute_paper_metrics(last_days=30)
        if paper_metrics["sharpe"] < 1.0:
            return {
                "approved": False,
                "live_qty": 0,
                "reason": f"Paper Sharpe {paper_metrics['sharpe']:.2f} < 1.0 threshold"
            }

        # Gate 2: Live mode explicitly enabled
        if not self.live_mode_enabled:
            return {
                "approved": False,
                "live_qty": 0,
                "reason": "Live mode not enabled by operator"
            }

        # Gate 3: Position size cap (10% of paper)
        paper_qty = intent["qty"]
        live_qty = max(paper_qty * 0.1, 0.001)  # Min 0.001 BTC

        # Gate 4: Submit exchange stop-loss first
        try:
            stop_response = await self.protective_order_manager.submit_stop_loss_to_exchange(
                position_id=intent["position_id"],
                symbol=intent["symbol"],
                side=intent["side"],
                qty=live_qty,
                entry_price=intent["entry_price"],
                stop_loss_price=intent["stop_loss_price"]
            )

            if stop_response["status"] != "active":
                return {
                    "approved": False,
                    "live_qty": 0,
                    "reason": f"Failed to submit exchange stop-loss"
                }

        except Exception as e:
            logger.error(f"Exchange stop submission failed: {e}")
            return {
                "approved": False,
                "live_qty": 0,
                "reason": f"Exchange stop error: {str(e)}"
            }

        # Approval: all gates passed
        return {
            "approved": True,
            "live_qty": live_qty,
            "reason": "All gates passed",
            "paper_qty": paper_qty,
            "position_size_factor": 0.1,  # 10% ramp-up
            "exchange_stop_id": stop_response["order_id"]
        }

    def enable_live_mode(self, operator_name: str):
        """Operator explicitly enables live trading"""
        self.live_mode_enabled = True
        self.live_mode_enabled_by = operator_name
        self.live_mode_enabled_ts_ms = int(time.time() * 1000)

        logger.warning(f"LIVE MODE ENABLED by {operator_name} at {datetime.now()}")

        # Emit governance event (requires approval audit)
        self.audit_sink.emit("live_mode_enabled", {
            "operator": operator_name,
            "timestamp": self.live_mode_enabled_ts_ms
        })

    def disable_live_mode(self, reason: str):
        """Operator disables live trading (emergency fallback)"""
        self.live_mode_enabled = False

        logger.warning(f"LIVE MODE DISABLED: {reason}")

        # Emit governance event
        self.audit_sink.emit("live_mode_disabled", {
            "reason": reason,
            "timestamp": int(time.time() * 1000)
        })
```

**Implementation checklist**:
- [ ] Check paper trading Sharpe last 30 days (gate: > 1.0)
- [ ] Check live mode explicitly enabled
- [ ] Cap live position size to 10% of paper (conservative ramp-up)
- [ ] Submit exchange stop-loss before execution
- [ ] Return approval with live_qty + exchange_stop_id
- [ ] Audit all approvals

#### Task 12.3: Live Order Execution Routes
**File**: `/app/live_execution_routes.py` (NEW, ~200 lines)

REST API for live execution approval:

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

live_router = APIRouter(
    prefix="/api/v1/live",
    tags=["Live Execution / 实盘执行"]
)

PAPER_LIVE_GATE: Optional[PaperLiveGate] = None

def set_paper_live_gate(gate: PaperLiveGate):
    global PAPER_LIVE_GATE
    PAPER_LIVE_GATE = gate

class EnableLiveRequest(BaseModel):
    """Request to enable live trading"""
    operator_name: str
    confirmation: str = "I understand the risks and approve live trading"

class ApproveExecutionRequest(BaseModel):
    """Request approval for live order execution"""
    intent_id: str
    symbol: str
    side: str  # "buy" or "sell"
    qty: float
    entry_price: float
    stop_loss_price: float
    position_id: str

@live_router.post("/enable-live-mode")
async def enable_live_mode(req: EnableLiveRequest):
    """
    Operator explicitly enables live trading.
    Requires authentication token (operator_name verified against auth system).
    """
    if PAPER_LIVE_GATE is None:
        raise HTTPException(status_code=503, detail="PaperLiveGate not ready")

    PAPER_LIVE_GATE.enable_live_mode(req.operator_name)

    return {
        "status": "live_mode_enabled",
        "operator": req.operator_name,
        "timestamp": int(time.time() * 1000)
    }

@live_router.post("/approve-execution")
async def approve_execution(req: ApproveExecutionRequest):
    """
    Request live execution approval.
    Returns: {"approved": bool, "live_qty": float, ...}
    """
    if PAPER_LIVE_GATE is None:
        raise HTTPException(status_code=503, detail="PaperLiveGate not ready")

    intent = {
        "intent_id": req.intent_id,
        "symbol": req.symbol,
        "side": req.side,
        "qty": req.qty,
        "entry_price": req.entry_price,
        "stop_loss_price": req.stop_loss_price,
        "position_id": req.position_id
    }

    approval = await PAPER_LIVE_GATE.approve_live_execution(
        intent=intent,
        paper_result={}  # Latest paper trading result
    )

    return approval

@live_router.get("/live-mode-status")
async def get_live_mode_status():
    """Check if live mode is enabled"""
    if PAPER_LIVE_GATE is None:
        raise HTTPException(status_code=503)

    return {
        "live_mode_enabled": PAPER_LIVE_GATE.live_mode_enabled,
        "enabled_by": getattr(PAPER_LIVE_GATE, "live_mode_enabled_by", None),
        "enabled_ts_ms": getattr(PAPER_LIVE_GATE, "live_mode_enabled_ts_ms", None)
    }

@live_router.post("/disable-live-mode")
async def disable_live_mode(reason: str):
    """Operator disables live trading (emergency)"""
    if PAPER_LIVE_GATE is None:
        raise HTTPException(status_code=503)

    PAPER_LIVE_GATE.disable_live_mode(reason)

    return {"status": "live_mode_disabled", "reason": reason}
```

**Implementation checklist**:
- [ ] POST `/live/enable-live-mode` — operator enables live trading
- [ ] POST `/live/approve-execution` — request execution approval
- [ ] GET `/live/live-mode-status` — check current status
- [ ] POST `/live/disable-live-mode` — emergency disable
- [ ] Authentication: operator_name verified

#### Task 12.4: E2E Tests
**File**: `/tests/test_paper_live_integration.py` (NEW, ~400 lines, 30 tests)

**Test cases**:
- [ ] `test_protective_order_manager_submit_stop()` — exchange stop submission
- [ ] `test_protective_order_manager_trailing_stop()` — trailing stop order
- [ ] `test_paper_live_gate_approval_gate_1_sharpe()` — Sharpe < 1.0 → rejected
- [ ] `test_paper_live_gate_approval_gate_2_live_mode()` — live mode not enabled → rejected
- [ ] `test_paper_live_gate_approval_gate_3_position_sizing()` — live qty = 10% paper qty
- [ ] `test_paper_live_gate_approval_gate_4_exchange_stop()` — stop not submitted → rejected
- [ ] `test_paper_live_gate_full_approval()` — all gates pass → approved
- [ ] `test_live_execution_enable_mode()` — operator enables live mode
- [ ] `test_live_execution_approve_order()` — order approval with live_qty
- [ ] `test_live_execution_disable_mode_emergency()` — emergency disable

### Test Criteria (Batch 12)

```python
def test_batch_12_acceptance():
    """Paper→Live bridge E2E test"""

    # Setup: protective order manager + paper live gate
    pom = ProtectiveOrderManager(bybit_connector_mock)
    plg = PaperLiveGate(pom, audit_sink)

    # Scenario 1: Live mode disabled (default)
    approval = plg.approve_live_execution(
        intent={"symbol": "BTCUSDT", "qty": 1.0},
        paper_result={}
    )
    assert approval["approved"] == False
    assert "not enabled" in approval["reason"].lower()

    # Scenario 2: Enable live mode
    plg.enable_live_mode("test_operator")
    assert plg.live_mode_enabled == True

    # Scenario 3: Paper Sharpe too low (< 1.0)
    approval = plg.approve_live_execution(
        intent={"symbol": "BTCUSDT", "qty": 1.0},
        paper_result={}
    )
    assert approval["approved"] == False
    assert "Sharpe" in approval["reason"]

    # Scenario 4: All gates pass (mock Sharpe > 1.0)
    plg._compute_paper_metrics = lambda **kw: {"sharpe": 1.5}
    bybit_connector_mock.create_conditional_order = AsyncMock(
        return_value={"orderId": "123"}
    )

    approval = plg.approve_live_execution(
        intent={
            "symbol": "BTCUSDT",
            "side": "buy",
            "qty": 1.0,
            "entry_price": 50000,
            "stop_loss_price": 49000,
            "position_id": "pos1"
        },
        paper_result={}
    )

    assert approval["approved"] == True
    assert approval["live_qty"] == 0.1  # 10% of 1.0
    assert approval["exchange_stop_id"] == "123"
```

### Expected Impact
- **Functional completion**: 82% → **88%** (6 point gain)
  - Exchange stops wired
  - PaperLiveGate fully operational
  - Live execution pathway complete
- **Code coverage**: +350 lines core logic (Protective Order Manager + PaperLiveGate + Routes), +400 lines tests
- **Safety**: Catastrophic loss protection via exchange-side stops
- **Compliance**: All live execution requires explicit operator approval + audit trail

---

## Summary: Batch 7–12 Implementation Timeline

### Batch 7: Core Agent Loop & Conductor
- **Effort**: 2 sessions, 1 day each
- **Files**: 2 new (conductor_core_loop.py, tests), 3 modified (message_bus.py, main.py, pipeline_bridge.py)
- **Lines**: 400 core, 400 tests
- **Impact**: 32% → 45% (+13)

### Batch 8: Guardian Agent
- **Effort**: 2 sessions, 1 day each
- **Files**: 1 new (guardian_agent.py), 2 modified (main.py, tests)
- **Lines**: 350 core, 450 tests
- **Impact**: 45% → 60% (+15)

### Batch 9: Perception Plane Activation
- **Effort**: 1.5 sessions
- **Files**: 2 new (perception_query_layer.py, tests), 1 modified (pipeline_bridge.py)
- **Lines**: 200 core, 350 tests
- **Impact**: 60% → 70% (+10)

### Batch 10: Analyst L1 + L2
- **Effort**: 2 sessions
- **Files**: 2 new (analyst_agent.py, analyst_scheduler.py), 1 modified (tests)
- **Lines**: 700 core, 500 tests
- **Impact**: 70% → 77% (+7)

### Batch 11: L2 Autonomous Loop
- **Effort**: 1.5 sessions
- **Files**: 2 new (layer2_daily_scheduler.py, layer2_budget_adjuster.py), 1 modified (tests)
- **Lines**: 450 core, 400 tests
- **Impact**: 77% → 82% (+5)

### Batch 12: Paper→Live Bridge
- **Effort**: 2 sessions
- **Files**: 2 new (live_execution_routes.py, tests), 3 modified (protective_order_manager.py, paper_live_gate.py, main.py)
- **Lines**: 350 core, 400 tests
- **Impact**: 82% → 88% (+6)

---

## Grand Totals: Batches 7–12

| Metric | Value |
|--------|-------|
| Total sessions | ~10 sessions (over 2-3 weeks) |
| Total new files | 12 files |
| Total modified files | 15 files |
| Total lines of code (core) | 2,800 lines |
| Total lines of tests | 2,800 lines |
| Starting functional completion | 32% |
| Ending functional completion | 88% |
| Completion gain | **+56 percentage points** |

---

## Risk & Mitigations

### Risk 1: L2 API Cost Overrun
- **Mitigation**: Budget adjuster (Task 11.2) caps daily spend, auto-adjusts based on ROI
- **Safeguard**: Hard max $100/month across all L2 sessions

### Risk 2: Guardian Conflicts with Legacy Risk Manager
- **Mitigation**: Guardian wraps existing RiskManager; no replacing
- **Safeguard**: Both checks must pass (Guardian AND RiskManager)

### Risk 3: Live Mode Catastrophic Loss
- **Mitigation**: Exchange stop-loss (Task 12.1) + position size 10% of paper
- **Safeguard**: Sharpe > 1.0 gate + explicit operator approval

### Risk 4: Learning Pipeline False Patterns
- **Mitigation**: L3 hypothesis testing (Batch 13, out of scope) validates patterns before deployment
- **Safeguard**: 40%+ confirmation rate required to increase L2 budget

---

## Success Metrics (Post-Batch 12)

✓ **Functional completion**: 88% (vs 32%)
✓ **Agent completion**: 5 agents wired (Scout, Strategist, Guardian, Analyst, Executor)
✓ **Message bus**: 100% subscriber coverage
✓ **Learning pipeline**: L1 fully operational, L2 autonomous
✓ **Perception plane**: All data marked with cognitive level
✓ **Exchange integration**: Stop-loss orders on Bybit
✓ **Paper→Live**: Safe transition pathway
✓ **Test coverage**: 2,800+ new tests
✓ **Cost control**: L2 spend capped at $100/month

---

## Next: Batch 13+ (Out of Scope)

- **Batch 13**: L3 Hypothesis Tester (run controlled experiments)
- **Batch 14**: L4 Strategy Evolution (evolve parameters, deploy variants)
- **Batch 15**: L5 Meta-Learning (optimize learning itself)
- **Batch 16**: Multi-Exchange Support (extend to Binance, Deribit)
- **Batch 17**: Live Trading at Scale (10x position sizes)

