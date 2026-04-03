> ⚠️ **已過時 / OUTDATED** — 早期歷史提取物，部分內容不反映當前狀態。權威文件：CLAUDE.md + README.md + TODO.md
> ⚠️ **OUTDATED** — Early historical extract. Some content no longer reflects current state. Authoritative: CLAUDE.md + README.md + TODO.md

# OpenClaw ByBit Governance - Implementation Checklist & Codebase Mapping (HISTORICAL)

**Purpose:** Map governance requirements to codebase components and track implementation completeness.

**Last Updated:** 2026-03-30  
**Phase:** 2 (Implementation Bridge active)

---

## PHASE 1: CONSTITUTION & BOUNDARIES (Foundation)

### Section 1: Core System Architecture

- [ ] **Root Principle #1: Single Write Port**
  - Component: `executor.py` or equivalent execution module
  - Requirement: ONE entry point for all order/execution operations
  - Validation: No other module has direct exchange write permission
  - Status: _PENDING_

- [ ] **Root Principle #2: Read-Write Separation**
  - Components: `research/`, `learning/`, `gui/`, `reporting/`
  - Requirement: All except Executor have read-only or suggestion-only capability
  - Validation: Code audit showing no direct API write calls outside Executor
  - Status: _PENDING_

- [ ] **Root Principle #3: AI Output ≠ Instant Command**
  - Component: `decision_lease.py` (shadow control plane)
  - Requirement: AI output forms formal Lease object (TTL, revocable, idempotent)
  - Validation: AI inference chain ends with Lease generation, not direct order placement
  - Status: _IN_DEVELOPMENT_ (shadow-only, per DOC-02 §2.3)

- [ ] **H0 Local Deterministic Gate (Immutable First Gate)**
  - Component: `h0_gate.py` or `deterministic_gate.py`
  - Checks Required:
    - [ ] Freshness check (market data age validation)
    - [ ] Health check (system resources, network, database)
    - [ ] Eligibility check (authorized product family + capability level)
    - [ ] Risk envelope check (position size, leverage, margin within P0/P1)
    - [ ] Cooldown check (consecutive-loss auto-pause)
  - SLA: <1ms execution, <1KB memory, pure in-memory (no external calls)
  - Status: _PENDING_

### Section 2: Governance Layer Infrastructure

- [ ] **H1–H5 AI Governance Pipeline**
  - Components: `thought_gate.py`, `budget_gate.py`, `model_router.py`, `governor.py`, `cost_logger.py`
  - Current Status: Code exists but main pipeline bypasses (Capability C = 30%)
  - Activation Requirement: win_rate > 20% (gating condition)
  - Validation: All gates execute sequentially: H0 → H1 → H2 → H3 → H4 → H5 → I
  - Status: _SHADOW_ONLY_ (awaiting integration)

- [ ] **I Decision Lease Shadow Control Plane**
  - Component: `lease_registry.py`, `lease_lifecycle.py`
  - Lease Properties Required:
    - [ ] Unique ID per lease (idempotency)
    - [ ] TTL (time-to-live) with auto-expiry
    - [ ] Revocation capability (Guardian/Operator callable)
    - [ ] Full audit trail (emission, execution, expiry, revocation)
  - Current Status: Shadow-only (logged but not connected to live execution)
  - Status: _DESIGN_COMPLETE, IMPLEMENTATION_PENDING_

### Section 3: Execution Gate

- [ ] **Executor Module (Lease Consumer)**
  - Component: `executor.py`
  - Requirements:
    - [ ] Validates lease (non-expired, non-revoked, valid ID)
    - [ ] Executes ONLY on valid lease
    - [ ] Cannot generate own leases
    - [ ] Logs all execution with lease ID traceability
  - Status: _PENDING_

---

## PHASE 2: DATA MODEL & CAPABILITIES (Specification)

### Section 4: Data Structure Compliance (DOC-03)

- [ ] **Trading Object Models**
  - [ ] Order schema (order_id, status, fill_amount, price, timestamp, exchange_response)
  - [ ] Position schema (coin, strategy, size, entry_price, stop_loss, take_profit, pnl, ai_cost)
  - [ ] Strategy schema (strategy_id, parameters, backtest_results, live_performance)
  - [ ] Portfolio schema (positions[], total_value, margin_used, risk_metrics)
  - Status: _TO_VERIFY_ (partially exists, needs consolidation)

- [ ] **State Machine Definitions**
  - [ ] Order lifecycle: submitted → working → partial_fill → fill/cancel/reject
  - [ ] Position states: opening → active → closing → closed
  - [ ] System modes: NORMAL → CAUTIOUS → REDUCED → DEFENSIVE → CIRCUIT_BREAKER → MANUAL_REVIEW
  - [ ] Agent states: idle → analyzing → deciding → executing → monitoring
  - Status: _TO_DEFINE_

- [ ] **Field-Level Validation Rules (DOC-03)**
  - [ ] Max leverage per product family
  - [ ] Max position size per coin
  - [ ] Margin requirement calculations
  - [ ] Fee tier based on VIP level
  - [ ] Slippage bounds
  - Status: _PARTIAL_ (some exist, incomplete mapping)

### Section 5: Agent Capability Blueprint (DOC-04, 10 Goals A–J)

- [ ] **[A] Autonomous Trade Execution**
  - [ ] All 6 product families: spot, margin, perp_linear, perp_inverse, options, other_derivatives
  - [ ] 10+ order types: market, limit, conditional, tp_sl_order, tp_sl_position, trailing_stop, etc.
  - [ ] Margin modes: cross, isolated, portfolio
  - [ ] Position modes: one_way, hedge
  - [ ] Order lifecycle management (submission → working → fill/cancel)
  - [ ] Paper trading engine with realistic slippage (0.05%) and fees (taker 0.055%, maker 0.02%)
  - Current Capability Level: _30%_ (spot only, limited order types)
  - Target: _100%_

- [ ] **[B] Cost & Revenue Awareness**
  - [ ] Track Net PnL (not Gross): net_realized_pnl = realized_pnl - total_fees
  - [ ] Mandatory cost components tracked: fees, slippage, funding, AI cost, AI attention tax, infrastructure
  - [ ] AI cost attribution per position (ai_cost_attributed_usd)
  - [ ] Fee optimization (maker-priority reduces cost from 21bps to 12bps)
  - [ ] cost_edge_ratio monitoring per position (≥0.8 triggers closure recommendation)
  - [ ] Daily/weekly/monthly cost breakdown reports
  - Current Capability Level: _50%_ (cost tracking started, incomplete attribution)
  - Target: _100%_

- [ ] **[C] Compute Path Intelligent Tiering**
  - [ ] Route each decision to lowest-cost tier capable of resolution
  - [ ] L0 (deterministic) → L1 (Ollama) → L1.5 (Haiku+Perplexity) → L2 (Sonnet/Opus)
  - [ ] Proactive market scanning (not just passive proposal review)
  - [ ] Cost accounting integrated into net PnL
  - [ ] 4-layer search degradation: L0 cache → L1 local → L1.5 cloud → L2 full
  - [ ] Hardware constraints: AMD AI MAX 395 + 128GB, Ollama MemoryMax=12G, CPUQuota=150%
  - Current Capability Level: _40%_ (L0 defined, L1–L2 partial)
  - Target: _100%_

- [ ] **[D] Self-Observability (System Health)**
  - [ ] Hardware awareness: CPU, memory, disk I/O monitoring
  - [ ] Network awareness: REST latency, WebSocket stability, egress IP, packet loss
  - [ ] Software awareness: module bottleneck detection, DB query latency, script execution time
  - [ ] Proactive degradation when unhealthy (system health > market judgment)
  - Current Capability Level: _30%_
  - Target: _100%_

- [ ] **[E–J] Additional Capabilities**
  - [ ] [E] Risk Boundary Enforcement (P0/P1/P2 hierarchy)
  - [ ] [F] Strategy Portfolio Management
  - [ ] [G] Market Regime Awareness
  - [ ] [H] Adversarial Market Defense (stop-loss hiding, anti-hunt)
  - [ ] [I] AI Attention Tax Tracking (cost_edge_ratio per position)
  - [ ] [J] Continuous Evolution Engine (Analyst Agent learning loop)
  - Current Capability Level: _20%–40%_ (varies by goal)
  - Target: _100%_

---

## PHASE 3: SAFETY & GOVERNANCE (Audit & Control)

### Section 6: Truth Source & Ownership (DOC-05)

- [ ] **Establish Authoritative Data Sources**

  | Fact | Source | Derivation | Module | Status |
  |------|--------|-----------|--------|--------|
  | Position State | Bybit REST | → Reconciliation → Cache | `reconciliation.py` | _PARTIAL_ |
  | Order State | Bybit V5 | → Matching → Cache | `order_matching.py` | _PENDING_ |
  | Trade Execution | Bybit fills | → Settlement | `settlement.py` | _PENDING_ |
  | Risk State | Guardian computation | → Decision cache | `guardian_agent.py` | _PENDING_ |
  | System Mode | Central state machine | Version-controlled | `system_state.py` | _PENDING_ |
  | Authorization Level | Authorization matrix | Immutable, versioned | `authorization_matrix.py` | _PENDING_ |
  | Audit Events | Append-only log | Write-only | `audit_log.py` | _PENDING_ |

- [ ] **Prevent Multi-Module Conflicts**
  - Code audit: No module maintains alternate version of above facts
  - Caching strategy: Cache is DERIVATIVE, not truth source
  - Status: _PENDING_AUDIT_

### Section 7: Change Governance (DOC-06)

- [ ] **L0 Changes (No Approval Required)**
  - [ ] Bug fixes (trade logic unaffected)
  - [ ] UI/visualization updates
  - [ ] Log message adjustments
  - [ ] Documentation updates
  - Validation: Git commit keywords for auto-categorization
  - Status: _FRAMEWORK_DEFINED_

- [ ] **L1 Changes (Agent Self-Governed)**
  - [ ] P2 risk micro-adjustments (pre-approved ranges)
  - [ ] Strategy parameter tweaks (pre-tested windows)
  - [ ] Backtest hypothesis validation
  - [ ] New strategy incubation (auto-enter live if paper passes)
  - Requirement: Automated log post-notification to Operator
  - Status: _IN_DEVELOPMENT_

- [ ] **L2 Changes (Post-Audit Review)**
  - [ ] P2 range expansion
  - [ ] New product family enablement
  - [ ] AI model version upgrades
  - [ ] Major parameter range shifts
  - Requirement: Operator review within 24h, then auto-approval
  - Status: _PENDING_

- [ ] **L3 Changes (Operator Pre-Approval)**
  - [ ] P0/P1 hard limit modification
  - [ ] Constitutional root principle modification
  - [ ] System architecture changes
  - [ ] Paper → Live first authorization
  - [ ] Authorization matrix modification
  - Requirement: Written approval with reasoning
  - Status: _GOVERNANCE_DEFINED_

### Section 8: Audit & Circuit Breaker (DOC-07)

- [ ] **Six-Element Audit Trail Reconstruction**
  - Every trade must log all 6 elements:
    1. [ ] Pre-decision state (account, position, risk)
    2. [ ] Decision basis (data, analysis, factors)
    3. [ ] Risk approval (conclusion + responsible module)
    4. [ ] Authorization basis (what authorized this?)
    5. [ ] Execution action (what was executed?)
    6. [ ] Post-execution result (error or success?)
  - Component: `audit_trail.py`
  - Validation: Mock trade execution → verify all 6 elements reconstructable
  - Status: _FRAMEWORK_DEFINED, IMPLEMENTATION_PENDING_

- [ ] **Append-Only Audit Log**
  - Storage: Immutable log (database transaction log or file)
  - Write-only: No modification or deletion allowed
  - Format: Structured JSON with timestamp, actor, action, before/after state
  - Status: _PENDING_

- [ ] **Circuit Breaker Triggers (Automatic Downgrade)**
  - [ ] Data freshness expired (market data stale > threshold)
  - [ ] API latency anomalous (REST > 5s, WebSocket > 3s)
  - [ ] Network packet loss > 5%
  - [ ] Margin utilization > P1 limit
  - [ ] Consecutive losses > threshold
  - [ ] Volatility anomalies (IV spike, gap > threshold)
  - [ ] System component failure (module crash, DB down)
  - [ ] Reconciliation failure (exchange state ≠ local state)
  - Component: `circuit_breaker.py`
  - Status: _PARTIALLY_IMPLEMENTED_

- [ ] **Degradation Mode Transitions (6 Levels)**
  - Mode hierarchy: NORMAL → CAUTIOUS → REDUCED → DEFENSIVE → CIRCUIT_BREAKER → MANUAL_REVIEW
  - [ ] Mode definitions (action allowed per mode)
  - [ ] Transition triggers
  - [ ] Recovery procedure (gradual, no cross-level jumps)
  - Status: _DEFINED, IMPLEMENTATION_PENDING_

---

## PHASE 4: INTEGRATION & FORMALIZATION (Bridge & Boundaries)

### Section 9: Implementation Bridge (DOC-08)

- [ ] **Bybit V5 API Formal Boundary**
  - Component: `bybit_api_interface.py`
  - Mappings required: All product families, order types, error responses, rate limits
  - Status: _PARTIAL_ (spot working, margin/perp/options incomplete)

- [ ] **OMS & Execution Formal Boundary (EX-02)**
  - Component: `oms_execution_boundary.py`
  - Order routing logic, slippage simulation, fee calculation
  - Status: _IN_PROGRESS_

- [ ] **Risk Control Formal Boundary (EX-01)**
  - Component: `risk_control_boundary.py`
  - P0/P1/P2 enforcement, position consolidation, margin calculation
  - Status: _PARTIAL_

- [ ] **Reconciliation Formal Boundary (EX-04)**
  - Component: `reconciliation_boundary.py`
  - State sync (local vs exchange), conflict resolution
  - Status: _PENDING_

- [ ] **Learning Formal Boundary (EX-05)**
  - Component: `learning_boundary.py`
  - Backtesting, strategy validation, meta-learning
  - Status: _PENDING_

- [ ] **Multi-Agent Orchestration Formal Boundary (EX-06)**
  - Component: `orchestration_boundary.py`
  - Inter-Agent communication (formal objects, not free text)
  - Lease lifecycle management
  - Priority arbitration (Guardian > Strategist > others)
  - Status: _IN_DESIGN_

- [ ] **Data Plane Perception Formal Boundary (EX-07)**
  - Component: `perception_boundary.py`
  - Market data ingestion, freshness checking, anomaly detection
  - Status: _PENDING_

### Section 10: Formal Boundary Documents (EX-01 through EX-07)

- [ ] **EX-01: Risk Control Formal Boundary**
  - Status: _FILE_EXISTS_ (`/01_source_documents/EX-01_OpenClaw_Bybit_Risk_Control_Boundary_风控边界定义_V2.docx`)
  - Implementation Status: _TO_EXTRACT_AND_IMPLEMENT_

- [ ] **EX-02: OMS & Execution Formal Boundary**
  - Status: _FILE_EXISTS_
  - Implementation Status: _TO_EXTRACT_AND_IMPLEMENT_

- [ ] **EX-03: Control Plane Formal Boundary**
  - Status: _FILE_EXISTS_
  - Implementation Status: _TO_EXTRACT_AND_IMPLEMENT_

- [ ] **EX-04: Reconciliation Formal Boundary**
  - Status: _FILE_EXISTS_
  - Implementation Status: _TO_EXTRACT_AND_IMPLEMENT_

- [ ] **EX-05: Learning Formal Boundary**
  - Status: _FILE_EXISTS_
  - Implementation Status: _TO_EXTRACT_AND_IMPLEMENT_

- [ ] **EX-06: Multi-Agent Orchestration Formal Boundary**
  - Status: _FILE_EXISTS_
  - Implementation Status: _TO_EXTRACT_AND_IMPLEMENT_

- [ ] **EX-07: Data Plane Perception Formal Boundary**
  - Status: _FILE_EXISTS_
  - Implementation Status: _TO_EXTRACT_AND_IMPLEMENT_

---

## CRITICAL PATH ITEMS (Must Complete First)

### Tier 0: Governance Framework (Blocking all downstream)

- [ ] **H0 Local Gate** — Non-negotiable, must execute first on all decisions
  - Estimated Effort: 2 days
  - Blocker Status: YES (nothing else can proceed without this)

- [ ] **Executor Single Write Port** — Prevent multiple write paths
  - Estimated Effort: 3 days
  - Blocker Status: YES

- [ ] **Audit Trail Infrastructure** — Logging all 6 elements
  - Estimated Effort: 2 days
  - Blocker Status: YES (required for compliance validation)

- [ ] **Truth Source Registry** — Establish canonical data source per fact
  - Estimated Effort: 1 day
  - Blocker Status: YES (prevents state conflicts)

### Tier 1: Risk & Safety (Enable basic operations)

- [ ] **Circuit Breaker System** — Auto-pause on anomalies
  - Estimated Effort: 3 days
  - Blocker Status: PARTIAL (nice-to-have but strongly recommended)

- [ ] **Decision Lease Framework** — Formal object wrapper on AI output
  - Estimated Effort: 2 days
  - Blocker Status: YES (Root Principle #3 enforcement)

### Tier 2: Autonomy & Intelligence (Enable Agent capability)

- [ ] **H1–H5 Pipeline Integration** — Full governance layer active
  - Estimated Effort: 5 days
  - Blocker Status: NO (shadow-only acceptable for MVP)
  - Gating Condition: win_rate > 20%

- [ ] **Compute Path Routing (L0–L2)** — Cost-aware tier selection
  - Estimated Effort: 4 days
  - Blocker Status: NO (L0+L1 sufficient for MVP)

- [ ] **Analyst Evolution Engine** — Continuous learning loop
  - Estimated Effort: 6 days
  - Blocker Status: NO (nice-to-have for Phase 2+)

---

## VERIFICATION CHECKLIST

### Code Review Gates

- [ ] All governance requirements mapped to code modules
- [ ] No write permission outside Executor (audit: grep all exchange API imports)
- [ ] H0 gate executes before every trading decision (trace execution flow)
- [ ] Audit trail captures all 6 elements (integration test)
- [ ] Truth sources marked (no duplicate state machines)
- [ ] Change governance categories enforced (git hook or CI/CD rule)
- [ ] Circuit breaker triggers defined (test each trigger condition)
- [ ] Degradation modes testable (unit tests for each mode)

### System Tests

- [ ] Mock trade execution → audit trail reconstructable (all 6 elements)
- [ ] Lease lifecycle → revocation prevents execution
- [ ] H0 rejection → order not placed (no bypass possible)
- [ ] System degradation → trades reduce/stop appropriately
- [ ] Recovery gradual → can't jump modes

### Operator Sign-Off Required

- [ ] Constitution (DOC-01) acceptance: _SIGNATURE_________
- [ ] Boundary Definition (DOC-02) acceptance: _SIGNATURE_________
- [ ] Authorization Matrix (DOC-05) acceptance: _SIGNATURE_________
- [ ] Change Governance (DOC-06) acceptance: _SIGNATURE_________
- [ ] Circuit Breaker Policy (DOC-07) acceptance: _SIGNATURE_________

---

## TRACKING & ROLLOUT

**Current Session:** 12 (2026-03-29)  
**Capability Status:**
- A (Trade Execution): 30%
- B (Cost Awareness): 50%
- C (Compute Tiering): 40%
- D (Self-Observability): 30%
- E–J (Other): 20–40%

**Next Milestone:** Capability C = 100% (compute path complete)  
**Following Milestone:** H1–H5 pipeline integration (gated on win_rate > 20%)

---

**Last Updated:** 2026-03-30  
**Maintained By:** OpenClaw Engineering

