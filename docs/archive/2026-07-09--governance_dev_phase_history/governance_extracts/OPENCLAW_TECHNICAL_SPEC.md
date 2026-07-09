> ⚠️ **已過時 / OUTDATED** — 早期歷史提取物，部分內容不反映當前狀態。權威文件：CLAUDE.md + README.md + TODO.md
> ⚠️ **OUTDATED** — Early historical extract. Some content no longer reflects current state. Authoritative: CLAUDE.md + README.md + TODO.md

# OpenClaw / Bybit Trading Agent - Technical Specification Summary (HISTORICAL)

**Classification:** Internal Technical Documentation
**Version:** Based on 13 Governance Documents (V1-V2)
**Scope:** 22-document governance spec set, Phase 2 Active Development
**Date:** 2026-03-30

---

# I. SYSTEM ARCHITECTURE OVERVIEW

## A. Component Layers

### 1. Data Plane (Perception Layer)
**Document Reference:** EX-07

Responsible for:
- Market data ingestion from Bybit exchange
- Signal generation and feature engineering
- Data validation and quality checks
- Publish-subscribe model for signal events

Key interfaces:
- Input: Real-time market data, order book, trades
- Output: Typed signal events (e.g., TrendSignal, VolatilitySignal)
- SLA: < 100ms latency, 99.9% uptime

### 2. Decision/Control Plane (Strategy Layer)
**Document Reference:** EX-03, EX-06 (Strategist Agent)

Responsible for:
- Signal consumption and interpretation
- Trading decision generation
- Decision lease creation with parameters
- Learning-based parameter adjustment

Key interfaces:
- Input: Signals from Data Plane, authorized leases, market state
- Output: Decision leases with entry/exit specifications
- SLA: Decision lease creation < 50ms after signal

### 3. Risk Control Plane (Risk Governance Layer)
**Document Reference:** EX-01, SM-04

Responsible for:
- Pre-trade risk validation
- Real-time position and exposure monitoring
- Risk state transitions and enforcement
- Circuit breaker and liquidation logic

Key interfaces:
- Input: Proposed orders, current positions, market data
- Output: Risk approval/rejection, state transitions
- SLA: Risk validation < 10ms, no blocking delays

### 4. Execution Plane (Order Management)
**Document Reference:** EX-02, SM-03

Responsible for:
- Order submission to exchange
- Fill tracking and position updates
- Cancellation and amendment handling
- Execution error recovery

Key interfaces:
- Input: Valid decision leases, risk approval
- Output: Orders to exchange, fill notifications
- SLA: Order submission < 20ms, 99.95% execution success

### 5. Orchestration Plane (Agent Conductor)
**Document Reference:** EX-06

Responsible for:
- OpenClaw conductor role coordination
- Agent message routing
- Shared state management for decision leases
- Agent lifecycle management

Key interfaces:
- Input: Messages from all agents
- Output: Routed messages, state updates
- SLA: Message processing < 5ms per message

### 6. Learning System (Model Improvement)
**Document Reference:** EX-05

Responsible for:
- Historical data analysis
- Model training on approved datasets
- Backtesting new models
- Model versioning and deployment

Key interfaces:
- Input: Trading outcomes (P&L, fills), historical market data
- Output: Updated models, parameter recommendations
- SLA: Non-blocking, async execution


---

# II. STATE MACHINE SPECIFICATIONS

## A. SM-01: Authorization State Machine

**Purpose:** Control who can authorize which decisions

### States
```
┌─────────────────┐
│  PENDING_AUTH   │ ← Initial state
└────────┬────────┘
         │ approve() from authorized signer
         ↓
┌─────────────────┐
│  AUTHORIZED     │ ← Ready to execute
└────────┬────────┘
         │ execute() by executor
         ↓
┌─────────────────┐
│   EXECUTING     │
└────────┬────────┘
         │ completion
         ↓
┌─────────────────┐
│   EXECUTED      │ ← Terminal state
└─────────────────┘

Alternative paths:
PENDING_AUTH → EXPIRED (timeout)
AUTHORIZED → REVOKED (manual cancellation)
```

### Mandatory Configuration
- Authorization timeout: 5-300 seconds (configurable per type)
- Approval signature requirement: Minimum 1, can be M-of-N
- Audit logging: All transitions with actor and timestamp

## B. SM-02: Decision Lease State Machine

**Purpose:** Manage the lifecycle of executable trading decisions

### States
```
┌──────────────────┐
│ LEASE_CREATED    │ ← Strategist generates
└────────┬─────────┘
         │ current_time >= start_time
         ↓
┌──────────────────┐
│ LEASE_ACTIVE     │ ← Executor can begin
└────────┬─────────┘
         │ executor.begin()
         ↓
┌──────────────────┐
│ LEASE_EXECUTING  │
└────────┬─────────┘
         │ all_fills | partial_fills
         ↓
┌──────────────────┐
│ LEASE_FULFILLED  │ ← Terminal, successful
└──────────────────┘

Alternative paths:
LEASE_ACTIVE → LEASE_EXPIRED (current_time > end_time)
LEASE_ACTIVE → LEASE_REVOKED (manual cancellation)
LEASE_EXECUTING → LEASE_FAILED (execution error)
```

### Mandatory Configuration
- Valid time window: end_time > start_time (typically 0.1-300 seconds)
- Partial fill handling: Allowed / Not allowed (per lease)
- Max lease duration: Hard limit, e.g., 5 minutes
- State change notifications: Async events for all transitions

## C. SM-03: OMS Execution State Machine

**Purpose:** Track order lifecycle and fills

### States
```
┌──────────────────┐
│  ORDER_CREATED   │ ← Executor instantiates
└────────┬─────────┘
         │ risk.validate()
         ↓
┌──────────────────┐
│ ORDER_VALIDATED  │ ← Ready for submission
└────────┬─────────┘
         │ submit_to_exchange()
         ↓
┌──────────────────┐
│ ORDER_SUBMITTED  │
└────────┬─────────┘
         │ exchange.ack
         ↓
┌──────────────────┐
│  ORDER_PENDING   │ ← Waiting for fills
└────────┬─────────┘
         │ partial fill
         ↓
┌──────────────────────────┐
│ ORDER_PARTIAL_FILL       │
└────────┬─────────────────┘
         │ final fill
         ↓
┌──────────────────┐
│  ORDER_FILLED    │ ← Terminal, successful
└──────────────────┘

Alternative paths:
ORDER_VALIDATED → ORDER_REJECTED (exchange rejects)
ORDER_PENDING → ORDER_CANCELLED (manual/lease expiration)
ORDER_PENDING → ORDER_FAILED (connection error)
```

### Mandatory Configuration
- Risk validation: Blocking, synchronous
- Exchange timeout: 30s default, 10s for cancellation
- Fill reconciliation: Within 1 second of exchange report
- Partial fill handling: Explicit tracking of filled vs. remainder

## D. SM-04: Risk Governor State Machine

**Purpose:** Continuous risk state management

### States
```
┌────────────────┐
│ RISK_NORMAL    │ ← All metrics within bounds
└────────┬───────┘
         │ metric > threshold_warning
         ↓
┌────────────────┐
│ RISK_WARNING   │ ← Alert, no blocks yet
└────────┬───────┘
         │ metric > threshold_critical
         ↓
┌────────────────┐
│RISK_CRITICAL   │ ← Auto-lock trading
└────────┬───────┘
         │ auto-trigger
         ↓
┌────────────────┐
│ RISK_LOCKED    │ ← No new orders
└────────┬───────┘
         │ begin_unwind
         ↓
┌────────────────┐
│ RISK_RECOVERY  │ ← Closing positions
└────────┬───────┘
         │ metric <= threshold_warning
         ↓
┌────────────────┐
│ RISK_NORMAL    │ ← Resume trading
└────────────────┘

Emergency path:
RISK_CRITICAL → RISK_LIQUIDATION (forced close)
```

### Mandatory Configuration
- Metrics monitored: Position size, notional exposure, margin ratio, leverage
- Threshold A (warning): 70-85% of limit
- Threshold B (critical): 95-100% of limit
- Calculation frequency: Real-time, < 100ms
- CRITICAL → LOCKED transition: < 1ms (must be deterministic)
- LOCKED → RECOVERY: Requires manual approval


---

# III. RISK CONTROL ARCHITECTURE (EX-01)

## A. Pre-Trade Risk Checks

**Applied:** Before every SM-03 order submission

### Dimensions Checked
1. **Position Size Risk**
   - Per-instrument limit: Configurable, e.g., 100 BTC
   - Aggregated portfolio limit: e.g., 500 BTC notional
   - Short position limit: e.g., 50 BTC

2. **Notional Exposure Risk**
   - Leverage limit: e.g., 5x maximum
   - Daily notional traded: e.g., $10M cap
   - Sector concentration: e.g., 30% max in any sector

3. **Margin Risk**
   - Maintenance margin ratio: e.g., > 5%
   - Initial margin requirement: e.g., > 20%
   - Liquidation risk flag: Trigger at 50% of liquidation

4. **Liquidity Risk**
   - Order size vs. market depth: Max 20% of 5-minute volume
   - Spread limit: Reject if bid-ask > 0.5% for major pairs
   - Time-weighted average price impact: < 0.3%

### Configuration Management
- Risk parameters are versioned with change tracking
- Changes require approval workflow
- Can be adjusted per trading pair, timeframe, or global

## B. Real-Time Risk Monitoring

**Applied:** Continuous, feeding SM-04

### Metrics Calculated
1. Current position (BTC, ETH, etc.)
2. Unrealized P&L (position × current mark price)
3. Notional exposure (position × mark price)
4. Margin available / margin required
5. Leverage ratio

### Update Frequency
- On every mark price update: < 100ms
- On every fill from exchange: < 1s
- Batch calculation: Every 1 second minimum


---

# IV. LEARNING SYSTEM ARCHITECTURE (EX-05)

## A. Data Isolation

### Training Data
- Historical market data: 1-2 years of clean ticks
- No live trading data until 30+ days after execution
- Manual curation of data for model training

### Live Feedback
- Execution fills: Recorded asynchronously
- P&L outcomes: Calculated end-of-day
- Delay before training: Minimum 7 days

## B. Model Lifecycle

### Development Phase
1. Feature engineering on training data
2. Model training with cross-validation
3. Backtesting on hold-out test set
4. Parameter sensitivity analysis

### Deployment Phase
1. Versioning: Each model version tracked with hash
2. Shadow mode: Run on live signals, don't trade (7 days)
3. Limited production: Trade at reduced position size (7 days)
4. Full production: Normal position limits after 14-day window

### Monitoring Phase
- Win rate: Must exceed historical baseline
- Model drift: Compare current predictions vs. training distribution
- Automatic rollback: If Sharpe ratio drops > 50%

---

# V. MULTI-AGENT ORCHESTRATION (EX-06)

## A. Agent Roles

### Scout Agent (Data Plane)
- **Input:** Market data stream
- **Output:** Typed signal events
- **Responsibility:** Signal generation, no decisions
- **Constraints:** Stateless, pure function of current market state

### Strategist Agent (Control Plane)
- **Input:** Signal events, current positions, market state
- **Output:** Decision leases
- **Responsibility:** Trading logic, parameter selection
- **Constraints:** Must respect risk parameters, create leases with bounds

### Executor Agent (Execution Plane)
- **Input:** Active decision leases, market data
- **Output:** Orders to exchange, fill tracking
- **Responsibility:** Order submission, fill management
- **Constraints:** Cannot modify lease parameters, only execute as specified

### OpenClaw (Orchestration / Conductor)
- **Input:** Messages from all agents
- **Output:** Routed messages, shared state updates
- **Responsibility:** Coordination, state management, failure handling
- **Constraints:** Passive routing, no business logic

## B. Communication Pattern

### Async Message Bus
- Broker: Redis/Kafka/RabbitMQ (configurable)
- Message format: JSON with envelope (source, target, timestamp, id)
- Ordering: Total ordering per decision lease
- Retention: 7 days minimum for replay

### Message Types
```
Scout → Strategist: SignalEvent
Strategist → Executor: DecisionLeaseCreated
Executor → Strategist: ExecutionStatus, FillReport
Strategist → Risk: RiskCheckRequired
Risk → Executor: RiskApproval / RiskRejection
Executor → Strategist: OrderFilled, OrderCancelled
OpenClaw → All: StateUpdate, Heartbeat
```

## C. Failure Handling

### Agent Crash
- Leases remain active, continue with existing parameters
- Dead letter queue for unprocessed messages
- Restart logic: Exponential backoff (1s, 2s, 4s, ... 60s max)

### Message Loss
- Idempotent message handling (message IDs)
- Dead letter queue for unackable messages
- Manual replay capability from event log

### Network Partition
- Timeout: 5 seconds for any agent response
- Fallback: Assume agent is unhealthy after timeout
- Recovery: Explicit health check and state synchronization

---

# VI. COMPLIANCE & AUDIT REQUIREMENTS

## A. Audit Trail

- Every state transition logged with: timestamp, actor, old_state, new_state, reason
- Every order submission logged with: decision_lease_id, risk_approval, parameters
- Every fill logged with: order_id, fill_qty, fill_price, exchange_timestamp

## B. Compliance Reporting

- Daily P&L reconciliation with exchange
- Risk limit breach report (if any)
- Model performance report for learning system
- Agent health report for orchestration

## C. Deterministic Replay

- Event log stored immutably
- Replay capability: Re-execute exact sequence of decisions
- Reproducibility: Same inputs → same outputs (no randomness)

---

# VII. IMPLEMENTATION PRIORITY MATRIX

| Component | Document | Phase | Priority | Risk |
|-----------|----------|-------|----------|------|
| Auth State Machine | SM-01 | Phase 1 | CRITICAL | LOW |
| Lease State Machine | SM-02 | Phase 1 | CRITICAL | MEDIUM |
| Order State Machine | SM-03 | Phase 1 | CRITICAL | HIGH |
| Risk Governor | SM-04 | Phase 1 | CRITICAL | HIGH |
| Risk Control Checks | EX-01 | Phase 2 | CRITICAL | HIGH |
| Agent Orchestration | EX-06 | Phase 2 | HIGH | MEDIUM |
| Data Plane Perception | EX-07 | Phase 2 | HIGH | LOW |
| Learning System | EX-05 | Phase 3 | HIGH | MEDIUM |
| Reconciliation | EX-04 | Phase 3 | HIGH | LOW |
| Control Plane | EX-03 | Phase 2 | MEDIUM | MEDIUM |

