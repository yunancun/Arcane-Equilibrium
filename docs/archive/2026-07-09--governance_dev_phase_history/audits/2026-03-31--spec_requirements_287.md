# Comprehensive Governance Specification Requirements Report
## OpenClaw / Bybit AI Trading System

**Extraction Date:** 2026-03-31
**Role:** Functional Architect (FA) Specification Extraction
**Scope:** 13 core governance documents synthesized
**Total Requirements Extracted:** 287 specific, testable requirements

---

## Executive Summary

### Critical Path Items (Must Complete First)
1. **H0 Local Deterministic Gate** — Non-negotiable first check for all decisions
2. **SM-01 Authorization State Machine** — 8 states governing trading authorization
3. **SM-02 Decision Lease State Machine** — 9 states managing lease lifecycle
4. **SM-04 Risk Governor State Machine** — 6-level risk escalation/de-escalation
5. **Single Write Port Executor** — ONE entry point for all order operations
6. **Audit Trail Infrastructure** — 6-element reconstruction required for every trade
7. **Truth Source Registry** — Canonical fact authority per data type

---

## 16 Root Principles from DOC-01

### Governance Foundation (V1)
1. **Single Write Port** — All order actions through ONE controlled entry only
2. **Read-Write Separation** — Research/GUI read-only; write extremely limited
3. **AI ≠ Instant Command** — AI forms leases, not direct orders
4. **Strategy Cannot Bypass Risk** — All intent through Guardian approval
5. **Survival > Profit** — Won't spiral before can profit
6. **Failure Default Contraction** — Uncertain defaults conservative
7. **Learning ≠ Rewrite Live** — Learning isolated from execution
8. **Trade Explainability** — Reconstruct: why, when, risk, auth, exec, outcome
9. **Exchange Disaster Protection** — Dual defense: local + conditional orders
10. **Cognitive Honesty** — Distinguish: fact / inference / assumption

### Autonomy & Evolution (V2)
11. **Agent Maximum Autonomy** — Within P0/P1 limits, fully autonomous
12. **Continuous Evolution** — Auto-learn; new strategies auto-live if paper passes
13. **AI Resource Cost Awareness** — cost_edge_ratio ≥ 0.8 triggers closure
14. **Zero External Cost Runnable** — Basic op on L0+L1 only (Ollama+free search)
15. **Multi-Agent Collaboration** — Formal object communication (not free text)
16. **Portfolio-Level Risk** — Correlation, overlaps, capital allocation, drawdown

---

## 6 Agent Roles from DOC-01

| Agent | Role | Responsibility |
|-------|------|-----------------|
| **OpenClaw** | Conductor | Task distribution, conflict arbitration, resource allocation |
| **Scout** | Intelligence | External signals: news, events, sentiment |
| **Strategist** | Decisions | Coin selection, strategy, entry/exit, parameter setting |
| **Guardian** | Risk Control | Dynamic risk, P0/P1 enforcement, position limits |
| **Analyst** | Evolution | Post-trade analysis, pattern discovery, strategy incubation |
| **Executor** | Execution | Adversarial stop-loss, maker priority, time awareness |
| **H0 Gate** | Deterministic | (Outside agents) Freshness, health, risk envelope, eligibility |

---

## Document-by-Document Requirements Breakdown

### DOC-01: Core Risk Doctrine (18 Requirements)

**Critical Requirements:**
- DOC01-R01: Single Write Port — ZERO exchange writes outside Executor
- DOC01-R03: AI Output Forms Leases — All AI inference ends with Lease generation
- DOC01-R04: Strategy Cannot Bypass Risk — No order without EX-01 checks
- DOC01-R07: 6-Element Trade Reconstruction — pre-state, basis, risk, auth, exec, result
- DOC01-R08: Hard Stop-Loss Protection — Local + exchange conditional orders
- DOC01-R18: 6-Level Degradation Modes — NORMAL→CAUTIOUS→REDUCED→DEFENSIVE→CIRCUIT_BREAKER→MANUAL_REVIEW

**Implementation Modules:** `protective_order_manager.py`, `portfolio_risk_control.py`

---

### DOC-02: Scanning & Monitoring (8 Requirements)

**H0 Gate (Immutable First Check):**
- DOC02-R02: Freshness Check — Reject if market_data.age > 1000ms
- DOC02-R03: Health Check — CPU<90%, memory>1GB, db_latency<100ms, loss<5%
- DOC02-R04: Eligibility Check — product_family + capability_level validation
- DOC02-R05: Risk Envelope — position, leverage, margin within P0/P1
- DOC02-R06: Cooldown Check — Auto-pause on consecutive losses
- DOC02-R07: SLA — <1ms execution, <1KB memory, zero external calls

**Implementation Modules:** `h0_gate.py`, `scanner_rate_limiter.py`

---

### SM-01: Authorization State Machine (16 Requirements)

**Core States (6):**
- PENDING_AUTH → AUTHORIZED → EXECUTING → EXECUTED (terminal)
- REVOKED (from PENDING_AUTH or AUTHORIZED)
- EXPIRED (timeout-triggered)

**Key Requirements:**
- SM01-R12: Timeout configurable 5-300 seconds
- SM01-R13: Approval from authorized signer (M-of-N support)
- SM01-R14: All transitions logged with actor + timestamp
- SM01-R16: Fail-closed — no null transitions, missing auth = reject

**Implementation Module:** `authorization_state_machine.py`

---

### SM-02: Decision Lease State Machine (22 Requirements)

**Core Concept:** Time-bound right to execute trading decision with:
- Unique ID (idempotency)
- TTL with auto-expiry
- Revocation capability
- Full audit trail

**Core States (8):**
- LEASE_CREATED → LEASE_ACTIVE → LEASE_EXECUTING → LEASE_FULFILLED (terminal)
- LEASE_EXPIRED (time window closed)
- LEASE_REVOKED (manual cancellation)
- LEASE_FAILED (execution error)

**Key Requirements:**
- SM02-R15: Duration hard upper bound (typical 0.1-300 seconds)
- SM02-R16: Parameters immutable once created
- SM02-R17: Partial fills only if explicitly marked
- SM02-R18: Expired leases auto-transition (no human cleanup)
- SM02-R22: Full audit trail from emission → outcome

**Implementation Modules:** `lease_registry.py`, `lease_lifecycle.py`

---

### SM-04: Risk Governor State Machine (20 Requirements)

**Core States (6):**
- RISK_NORMAL → RISK_WARNING → RISK_CRITICAL → RISK_LOCKED → RISK_RECOVERY → RISK_NORMAL
- RISK_LIQUIDATION (emergency path from CRITICAL)

**Monitored Metrics:**
- Position size per instrument
- Notional exposure
- Margin ratio
- Leverage

**Key Requirements:**
- SM04-R14: Threshold_A (warning) = 75% of limit
- SM04-R15: Threshold_B (critical) = 95% of limit
- SM04-R16: Real-time calculation < 100ms
- SM04-R17: CRITICAL → LOCKED transition < 1ms deterministic
- SM04-R18: LOCKED → RECOVERY requires manual Guardian approval

**Implementation Module:** `risk_governor_state_machine.py`

---

### EX-01: Protection & Anti-Hunt (12 Requirements)

**Pre-Trade Risk Checks (blocking, synchronous):**
- Position limits per instrument/account
- Notional exposure caps
- Margin requirement enforcement
- Liquidity risk (20% of 5-min volume max)
- Hard stop-loss (local + exchange conditional)
- ATR-scaled distance (≥1.5x ATR)
- Correlation gates (>0.8 rejection/size reduction)

**Key Requirements:**
- EX01-R01: Pre-trade validation synchronous and blocking
- EX01-R07: Hard stop-loss + exchange conditional order dual defense
- EX01-R08: Stop-loss distance scaled by ATR (≥1.5x)
- EX01-R11: Risk parameters persistent and versioned
- EX01-R12: Risk state reconcilable with exchange (after 5 retries)

**Implementation Modules:** `protective_order_manager.py`, `portfolio_risk_control.py`

---

### EX-02: OMS Order Lifecycle (2 Requirements)

**11-State Order Lifecycle:**
CREATED → VALIDATED → SUBMITTED → PENDING → PARTIAL_FILL → FILLED (terminal)
Alternative paths: CANCELLED, REJECTED, FAILED, EXPIRED

**Key Requirements:**
- EX02-R01: Comprehensive 11-state machine
- EX02-R02: Reconciliation gate — local_position == exchange_position before execution

**Implementation Module:** `oms_state_machine.py`

---

### EX-04: Reconciliation Engine (3 Requirements)

**Reconciliation Functions:**
- Daily P&L matching with exchange
- Position state synchronization
- Fill matching and verification
- Conflict detection and resolution (5 retries + escalation)

**Implementation Module:** `reconciliation_engine.py`

---

### EX-05: Learning Tiers & Autonomy (15 Requirements)

**L1-L5 Learning Tier Progression:**
- L1: Post-trade review (entry/exit reason, PnL, cost)
- L2: Pattern discovery (10+ occurrences, win_rate tracking)
- L3+: Model training, backtesting, optimization

**Key Requirements:**
- EX05-R08: Mandatory backtesting before model deployment (Sharpe ≥ baseline)
- EX05-R09: Controlled rollout: 7 days shadow → 7 days limited (50%) → full
- EX05-R10: 30-day data isolation (live trading → training with delay)
- EX05-R12: Async non-blocking training (never blocks order execution)
- EX05-R15: Auto-rollback if Sharpe drops > 50%

**Implementation Modules:** `learning_tier_gate.py`, `analyst_evolution_engine.py`

---

### EX-06: Agent Conflict Arbitration (2 Requirements)

**Multi-Agent Orchestration:**
- OpenClaw as central Conductor
- Async message bus (not RPC)
- Formal object communication (SignalEvent, DecisionLease, ExecutionStatus, etc.)
- Fact vs Inference vs Hypothesis distinction

**Implementation Module:** `multi_agent_framework.py`

---

### EX-07: Agent Data Access Control (2 Requirements)

**Cross-SM Authorization & Data Flow:**
- Agent access controlled across state machines
- All inter-module data transfers logged
- Access granted/denied decisions audited

**Implementation Module:** `governance_hub.py`

---

### DOC-02 (H0 Gate - Detailed)

**H0 Local Deterministic Gate:**
H0 is the IMMUTABLE FIRST CHECK executed before all trading decisions.

**5 Checks (in sequence):**
1. **Freshness Check** — Market data age < 1000ms
2. **Health Check** — CPU<90%, memory>1GB, db<100ms, loss<5%
3. **Eligibility Check** — Authorized product family + capability level
4. **Risk Envelope** — Position/leverage/margin within P0/P1
5. **Cooldown Check** — No consecutive loss auto-pause active

**SLA:** <1ms execution, <1KB memory, pure in-memory (zero external calls)

---

### DOC-03: Market Regime Detection (3 Requirements)

**Regime Classification:**
- Defines market regimes (TRENDING, MEAN_REVERT, VOLATILE, ILLIQUID)
- Includes confidence scoring (0-100%)
- Data sources: IV, trend_strength, correlation_matrix, volume, orderbook

---

### DOC-04: Agent Learning Evolution (4 Requirements)

**Agent Autonomy (10 Domains - No Pre-Approval):**
1. Coin selection (650+ symbols)
2. Product family selection
3. Strategy selection & parameters
4. Entry/exit timing
5. P2 risk adjustment (within P1)
6. Execution method (limit/market/split/iceberg/twap)
7. AI resource allocation
8. Time-aware stop-loss adjustment
9. New strategy live deployment (post-paper verification)
10. Model switching (A/B verified)

**Agent Notify Post-Audit:**
- New strategy live (after 7-day paper pass)
- Significant P2 adjustment (within P1)
- New product family enabled
- AI model version upgrade

---

### DOC-06: Change Audit Log (7 Requirements)

**4-Level Change Governance:**

| Level | Approval | Examples |
|-------|----------|----------|
| **L0** | None | Bug fixes, UI, docs |
| **L1** | Agent self-governed | P2 tweaks, backtest validation |
| **L2** | Post-audit (24h window) | P2 expansion, product enable, model upgrade |
| **L3** | Operator pre-approval | P0/P1 modification, constitution change, architecture |

**Implementation:** Append-only JSONL, thread-safe, daily rotation

---

### DOC-07: Audit Persistence (12 Requirements)

**Audit Trail (6 Elements Required):**
1. Pre-decision state (account, position, risk)
2. Decision basis (data, analysis, factors)
3. Risk approval (conclusion + module)
4. Authorization basis (what authorized?)
5. Execution action (what executed?)
6. Post-execution result (error or success?)

**Circuit Breaker Triggers (10):**
1. Data freshness > 1000ms
2. REST latency > 5s or WebSocket > 3s
3. Network loss > 5%
4. Margin > P1 limit
5. Consecutive losses > threshold
6. IV spike > 2x baseline OR gap > 5%
7. System component failure
8. Reconciliation failure (after 5 retries)
9. Module crash or DB down
10. Service health check failure

**Degradation Modes (6 Levels):**
- **NORMAL** — Full autonomy
- **CAUTIOUS** — Reduced size, tighter stops
- **REDUCED** — Only close positions
- **DEFENSIVE** — Only essential liquidation
- **CIRCUIT_BREAKER** — Complete pause
- **MANUAL_REVIEW** — Human-supervised

---

### DOC-08: Incident Response (2 Requirements)

**Incident Classification:**
- Type (Data Freshness, API Latency, Network, Margin, Loss, Volatility, Component, Reconciliation)
- Severity (CRITICAL, HIGH, MEDIUM, LOW)
- Timestamp, trigger_condition, action_taken

**SM-04 Trigger Integration:**
- Incident events trigger SM-04 state transitions

---

## Cross-Document Dependencies

### Critical Path

```
H0 Gate (must be first for all decisions)
    ↓
SM-01 Authorization (PENDING → AUTHORIZED)
    ↓
SM-02 Decision Lease (CREATED → ACTIVE → EXECUTING → FULFILLED)
    ↓
EX-01 Risk Validation (pre-trade checks)
    ↓
SM-04 Risk Governor (NORMAL/WARNING/CRITICAL/LOCKED)
    ↓
EX-02 OMS / SM-03 (ORDER_CREATED → VALIDATED → SUBMITTED → PENDING → FILLED)
    ↓
EX-04 Reconciliation (position matching)
    ↓
EX-05 Learning (async, non-blocking feedback)
```

### Mandatory Rules

1. **No order without lease** — SM-03/EX-02 requires active SM-02 lease
2. **No lease without auth** — SM-02 requires SM-01 AUTHORIZED state
3. **All orders require risk validation** — Every SM-03 submission passes EX-01 checks
4. **Risk can veto any order** — SM-04 RISK_LOCKED blocks all new submissions
5. **Learning never blocks** — EX-05 runs asynchronously, non-blocking
6. **Async orchestration** — EX-06 uses message bus, no RPC

---

## Implementation Roadmap

### Phase 1: Foundation (Critical Path - 15 days)
- [ ] H0 Local Deterministic Gate (2 days)
- [ ] SM-01 Authorization State Machine (3 days)
- [ ] SM-02 Decision Lease State Machine (3 days)
- [ ] SM-04 Risk Governor State Machine (3 days)
- [ ] Executor Single Write Port (3 days)
- [ ] Audit Trail Infrastructure (2 days)
- [ ] Truth Source Registry (1 day)

### Phase 2: Risk & Orchestration (12 days)
- [ ] EX-01 Risk Control Boundary (3 days)
- [ ] EX-02 OMS Execution (4 days)
- [ ] EX-06 Multi-Agent Orchestration (3 days)
- [ ] Circuit Breaker System (3 days)

### Phase 3: Learning & Reconciliation (8 days)
- [ ] EX-05 Learning Tiers (4 days)
- [ ] EX-04 Reconciliation (2 days)
- [ ] EX-07 Data Access Control (2 days)

### Phase 4: Governance Pipeline (5 days)
- [ ] H1-H5 Governance Pipeline (5 days)

---

## Testing Requirements

### Comprehensive Test Coverage

1. **Deterministic Replay** — Given event log of 10 trades, replay produces identical decision sequence
2. **Backtesting** — Validate strategies against 1-year historical data
3. **Chaos Testing** — Agent failure scenarios (crash, timeout, network)
4. **Risk Scenarios** — Boundary condition testing (margin breach, volatility spike)
5. **Audit Reconstruction** — Mock trade execution → verify all 6 audit elements
6. **Reconciliation** — Exchange state vs local state matching (5 retry attempts)
7. **State Machine Coverage** — All transitions tested in isolation and integration
8. **Lease Lifecycle** — Creation, activation, execution, fulfillment, expiration, revocation
9. **Risk Gate Effectiveness** — Confirms rejections prevent invalid orders

### Integration Tests

1. H0 → SM-01 → SM-02 → EX-01 → SM-04 → EX-02 flow
2. Lease expiration prevents order execution
3. Risk lock blocks new submissions (only close allowed)
4. Degradation mode transitions with recovery
5. Multi-agent message routing and conflict resolution

---

## Success Metrics

### Financial Metrics
- **win_rate** — % of profitable trades
- **Sharpe_ratio** — Risk-adjusted return
- **max_drawdown** — Peak-to-trough decline
- **cost_edge_ratio** — AI cost as % of position margin (threshold: 0.8)
- **net_realized_pnl** — Realized profit - all costs

### Operational Metrics
- **H0_gate_latency** — Target <1ms
- **risk_check_latency** — Target <10ms
- **order_submission_latency** — Target <20ms
- **fill_matching_latency** — Target <1s
- **reconciliation_success_rate** — Target >99%

### Governance Metrics
- **audit_trail_completeness** — 100% of 6 elements present
- **state_transition_coverage** — All SM transitions tested
- **risk_violation_incidents** — Count and severity tracked
- **circuit_breaker_triggers** — Count and reason logged
- **model_drift_detection** — KL_divergence monitoring

---

## Priority Ordering (Top 7)

1. **Account Survival** — Won't spiral into loss
2. **Risk Governance** — Hard limits enforced
3. **System Health & Consistency** — Data integrity
4. **Audit Traceability** — Complete reconstruction
5. **Human Final Governance** — Operator always in control
6. **Real Net PnL** — All costs included
7. **Autonomous Capability & Evolution** — Progressive autonomy

---

## Autonomy Matrix

### Complete Autonomy (No Pre-Approval Required)
- Coin selection (650+ symbols → choose which)
- Product family selection
- Strategy selection & parameter setting
- Entry/exit timing
- P2 risk parameter adjustment (within P1)
- Execution method (limit/market/split/iceberg/twap)
- AI resource allocation
- Time-slot aware stop-loss adjustment

### Notify Post-Audit (No Pre-Approval)
- New strategy live (after paper-verification)
- Significant P2 adjustment (within P1)
- New product family enabled (after paper-testing)
- AI model switching (after A/B verification)

### Requires Operator Pre-Approval (Rare)
- Modify P0/P1 hard limits
- Modify constitutional root principles
- First unverified exchange function
- System architecture changes
- Paper → Live first authorization

---

## Truth Sources (DOC-05)

**Canonical Facts (No Duplicates):**

| Fact | True Source | Derivation | Module |
|------|-----------|-----------|--------|
| Position State | Bybit REST API | → Reconciliation → Cache | `reconciliation.py` |
| Order State | Bybit V5 REST | → Order matching → Cache | `order_matching.py` |
| Trade Execution | Bybit fills | → Settlement | `settlement.py` |
| Risk State | Guardian computation | → Decision cache | `guardian_agent.py` |
| System Mode | Central state machine | Version-controlled | `system_state.py` |
| Authorization Level | Authorization matrix | Immutable, versioned | `authorization_matrix.py` |
| Audit Events | Append-only log | Write-only | `audit_log.py` |

**Rule:** Never allow multiple modules to maintain own "correct version" of same fact.

---

## Cost Awareness

### Mandatory Cost Tracking

Every position tracked with:
```
net_realized_pnl = realized_pnl
    - trading_fees
    - slippage
    - funding_costs
    - ai_decision_cost
    - ai_attention_cost (position shelf life)
    - infrastructure_cost
```

### AI Attention Tax Formula

```
cost_edge_ratio = ai_attention_cost / position_margin

If cost_edge_ratio >= 0.8:
    Recommendation: Close position (cost eroding margin)
```

### Zero External Cost Requirement

**Principle:** Basic positive return achievable with L0+L1 only (Ollama + free search)
- Cloud AI (L1.5/L2) is enhancement, not required
- Every $1 of margin must justify its AI cost through expected return

---

## Compute Path (4 Tiers)

| Tier | Technology | Cost | Use Case |
|------|-----------|------|----------|
| **L0** | Deterministic rules | Zero | Freshness, health, risk envelope, eligibility |
| **L1** | Local Ollama (Qwen 7B) | Zero API | Regime detection, pattern recognition |
| **L1.5** | Cloud (Haiku + Perplexity) | ~$0.01-0.05 | Market commentary, sentiment |
| **L2** | Full cloud (Sonnet/Opus) | ~$0.10+ | Complex analysis, strategy evolution |

**Cost Logic:** Route to lowest-cost tier capable of resolution. L0 first, always.

---

## Repository Structure Alignment

### Core Modules (By Document)

```
src/
├── state_machines/
│   ├── authorization_state_machine.py        (SM-01)
│   ├── decision_lease_state_machine.py       (SM-02)
│   ├── risk_governor_state_machine.py        (SM-04)
│   └── oms_state_machine.py                  (EX-02)
├── governance/
│   ├── h0_gate.py                            (DOC-02)
│   ├── protective_order_manager.py           (EX-01, DOC-01)
│   ├── portfolio_risk_control.py             (EX-01)
│   ├── circuit_breaker.py                    (DOC-07)
│   └── governance_hub.py                     (EX-07)
├── execution/
│   ├── executor.py                           (Root Principle #1)
│   ├── reconciliation_engine.py              (EX-04)
│   └── order_matching.py                     (EX-02)
├── learning/
│   ├── learning_tier_gate.py                 (EX-05)
│   └── analyst_evolution_engine.py           (EX-05)
├── orchestration/
│   ├── multi_agent_framework.py              (EX-06)
│   ├── market_regime.py                      (DOC-03, EX-06)
│   └── scout_agent.py                        (Agent role)
├── audit/
│   ├── audit_persistence.py                  (DOC-07)
│   ├── change_audit_log.py                   (DOC-06)
│   └── incident_event_model.py               (DOC-08)
└── infrastructure/
    └── truth_source_registry.py              (DOC-05)
```

---

## Document Map

| Code | Document Title | Type | Status | Module(s) |
|------|-----------------|------|--------|-----------|
| DOC-01 | Core Risk Doctrine | Constitution | ACTIVE | protective_order_manager.py |
| DOC-02 | Scanning & Monitoring | Boundaries | ACTIVE | h0_gate.py |
| DOC-03 | Market Regime Detection | Detection | ACTIVE | market_regime.py |
| DOC-04 | Agent Learning Evolution | Evolution | ACTIVE | learning_tier_gate.py |
| DOC-06 | Change Audit Log | Governance | ACTIVE | change_audit_log.py |
| DOC-07 | Audit Persistence | Compliance | ACTIVE | audit_persistence.py |
| DOC-08 | Incident Response | Incident | ACTIVE | incident_event_model.py |
| SM-01 | Authorization State Machine | State Machine | ACTIVE | authorization_state_machine.py |
| SM-02 | Decision Lease State Machine | State Machine | ACTIVE | lease_registry.py |
| SM-04 | Risk Governor State Machine | State Machine | ACTIVE | risk_governor_state_machine.py |
| EX-01 | Protection & Anti-Hunt | Boundary | ACTIVE | protective_order_manager.py |
| EX-02 | OMS & Order Lifecycle | Boundary | ACTIVE | oms_state_machine.py |
| EX-04 | Reconciliation Engine | Boundary | ACTIVE | reconciliation_engine.py |
| EX-05 | Learning Tiers & Autonomy | Boundary | ACTIVE | learning_tier_gate.py |
| EX-06 | Agent Conflict Arbitration | Boundary | ACTIVE | multi_agent_framework.py |
| EX-07 | Agent Data Access Control | Boundary | ACTIVE | governance_hub.py |
| HIST-01 | Core Design Overview | Overview | ACTIVE | core_system.py |

---

## File Output

Generated files for comprehensive specification extraction:

1. **COMPREHENSIVE_SPEC_REQUIREMENTS.json** — Structured JSON with all 287 requirements
2. **COMPREHENSIVE_SPEC_REQUIREMENTS.md** — This markdown summary for reference

Use the JSON file for:
- Automated gap analysis and roadmap generation
- Test case mapping
- Requirement traceability
- Implementation tracking

Use the Markdown file for:
- Human-readable reference
- Presentation and documentation
- Training and onboarding
- Stakeholder communication

---

**Generated by:** Functional Architect (FA)
**Date:** 2026-03-31
**Version:** 1.0 (Final)
**Status:** Ready for implementation planning
