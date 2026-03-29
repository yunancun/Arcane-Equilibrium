# OpenClaw ByBit Governance Documents - Structured Extraction Summary

**Project:** OpenClaw / Bybit Trading Agent (Multi-Agent Framework)  
**Extraction Date:** 2026-03-30  
**Phase:** Implementation Bridge (Phase 2)  
**Status:** 9 Governance Documents Analyzed

---

## EXECUTIVE OVERVIEW

The OpenClaw / Bybit Trading Agent is a **Multi-Agent collaborative trading system** orchestrated by OpenClaw (Conductor), comprising 6 specialized Agent roles operating within strict risk boundaries and comprehensive audit frameworks. The system prioritizes account survival, risk governance, and long-term stability over short-term profit maximization.

**Core Design Principle:** Maximum Agent autonomy within hard boundaries (P0/P1), human-only final governance, continuous self-evolution, zero external AI cost required for basic operation.

---

## 1. DOC-01: PROJECT CONSTITUTION & ROOT PRINCIPLES (V2)

### Document Title & Version
- **Full Title:** OpenClaw / Bybit 项目宪法 与根原则
- **English:** Project Constitution / Root Principles V2
- **Version:** V2 (updated from V1.1 based on engineering implementation analysis)

### Core Project Essence
The system is **NOT** a fast-reaction trading model or quantitative script. It is:
> A Multi-Agent collaborative trading system orchestrated by OpenClaw (Conductor), operating within strict risk boundaries, explicit authorization matrices, complete audit chains, and human final governance framework as its core goal of continuous evolution.

### System Components
- **OpenClaw:** Central orchestrator (Conductor) — task distribution, conflict arbitration, resource allocation
- **Scout Agent:** External intelligence (news, events, sentiment)
- **Strategist Agent:** Trading decisions (coin selection, strategy selection, parameter setting, portfolio allocation)
- **Guardian Agent:** Dynamic risk control (adaptive adjustment within hard boundaries)
- **Analyst Agent:** Continuous evolution (post-trade analysis, pattern discovery, strategy incubation, meta-learning)
- **Executor Agent:** Intelligent execution (adversarial stop-loss, maker priority, time-slot awareness)
- **H0 Local Gate:** Independent deterministic gating — always outside all Agent influence, zero-cost, mandatory first safety gate

### Top 7 Priority Ordering (hierarchical conflict resolution)
1. **Account Survival** — absolute priority
2. **Risk Governance**
3. **System Health & State Consistency**
4. **Audit Traceability & Explainability**
5. **Human Final Governance & Takeover Authority**
6. **Real Net PnL** (not gross, not nominal)
7. **Autonomous Capability Enhancement & Continuous Evolution**

(Lower priorities: market coverage, frequency, gross PnL expansion)

### 16 Non-Negotiable Root Principles (§5.1–§5.16)

**V1 Original Principles (§5.1–§5.10):**

1. **Single Write Port Principle** — All order/execution actions through one controlled entry point only. No research/GUI/script has direct exchange write permission.

2. **Read-Write Separation** — Research, inference, learning, GUI, reporting modules: read-only or advisory only. Write permission: extremely limited, auditable, can be locked or circuit-breaker.

3. **AI Output Cannot Be Instant Trade Command** — AI output forms: explanations, suggestions, audit conclusions, time-constrained Decision Lease drafts. NOT immediate trade orders.

4. **Strategy Layer Cannot Bypass Risk Control** — All trading intent must pass through risk governance. Risk layer has: veto power, position-reduction power, delay power, downgrade power, circuit-breaker power.

5. **Survival Evaluation Before Profit Evaluation** — System judged first on "won't spiral out of control", second on "can it profit".

6. **Failure Default Contraction Principle** — When uncertain, default behavior toward conservatism: no new positions, reduce frequency, reduce risk, reduce-only mode, enter cautious/circuit-breaker mode.

7. **Learning Cannot Directly Rewrite Live** — Learning plane isolated from live plane. Learning results → hypotheses, evidence, candidate parameters, change-approval proposals only. Cannot directly modify live config/risk/authorization/code. (But pre-approved L1 micro-adjustments can auto-apply per DOC-06.)

8. **Every Trade Must Be Explainable & Traceable** — System must answer: why do it? why now? why acceptable risk? why allowed to pass? when to admit error? judgment vs execution vs chance?

9. **Exchange-Side Disaster Protection** — Local smart stop-loss is primary layer. Exchange-side must retain disaster protection bottom line. Pre-placed conditional orders on exchange = last defense when local system totally fails.

10. **Cognitive Honesty Principle** — All conclusions must clearly distinguish: facts, inferences, assumptions. Cannot disguise inference as fact, cannot claim assumption is certain. External data (news, sentiment, search): default inference-level, NOT equivalent to exchange-returned fact data.

**V2 New Principles (§5.11–§5.16):**

11. **Agent Maximum Autonomy Principle** — Within P0/P1 hard boundaries, Agent has complete autonomous trading decision authority: coin selection, strategy selection, parameter setting, product family selection, entry/exit timing, P2 parameter adjustment. Operator sets hard boundaries only, does NOT intervene in specific trade decisions. Autonomy ≠ no boundaries — P0/P1 hard limits, constitutional root principles, system architecture are unpassable boundaries.

12. **Continuous Evolution Principle** — System MUST possess continuous learning, adaptation, evolution capability from own trading behavior. NOT optional. Core design goal. Must auto-attribute trade results (alpha / timing / sizing / execution / cost error classification), auto-discover cross-trade cross-strategy systematic patterns, auto-generate & validate improvement hypotheses, auto-experiment in shadow/paper, auto-apply improvements to live after verification. New strategy incubation: if paper verification passes conditions, auto-enter live (no Operator pre-approval needed).

13. **AI Resource Cost Awareness Principle** — Every AI call (local or cloud) has cost (compute resources, latency, power, API fees). System must: integrate AI cost into each trade's Net PnL calculation, track per-position AI attention consumption (cost_edge_ratio), auto-recommend position closure when position's AI attention cost erodes expected margin to unacceptable level, dynamically adjust AI budget by recent ROI (good performance = expand, poor = tighten), treat AI cost as "trade cost component" not "operating overhead".

14. **Zero External Cost Runnable Principle** — System must achieve basic positive net return using ONLY local Ollama + free search (zero external AI API cost). Cloud AI (Haiku/Sonnet/Opus/Perplexity) = enhancement layer, NOT prerequisite for basic operation. When cloud API unavailable or budget exhausted, system auto-degrades to local-AI mode and continues trading (does NOT stop). Four-tier compute path: L0 local deterministic (zero cost) → L1 local Ollama (zero API cost) → L1.5 low-cost cloud → L2 full cloud. Start L0+L1, progressively enable higher tiers after verified performance.

15. **Multi-Agent Collaboration Principle** — System uses Multi-Agent architecture with OpenClaw as central orchestrator. Each Agent: clear responsibility boundary. Agent communication: through formal objects (NOT free text). Agent conflict: orchestrator arbitrates by priority (Guardian risk control conclusion > Strategist trade intent). Resource-limited phase: multiple Agent roles can be performed by same local model via different prompts — but responsibility boundaries must NOT blur.

16. **Portfolio-Level Risk Awareness Principle** — System must NOT think risk only at single-trade level. Must monitor at portfolio level: multiple high-correlation positions' concentration exposure, multiple strategies' overlapping holdings in same coin, capital allocation rationality across strategies, total exposure contraction during broad market downturns. Single trade passing risk control ≠ portfolio-level risk acceptable.

### Net PnL Principle (§6)
**All economic evaluation uses Net PnL, NOT Gross PnL.** System must acknowledge & track real costs:
- Trading fees (maker/taker, VIP level changes)
- Slippage (estimated vs actual)
- Funding / borrowing costs
- AI decision cost (local compute + cloud API)
- AI attention tax per position (continuous monitoring = resource consumption)
- Compute & infrastructure cost
- Necessary operational friction cost

Project rejects narrative: "nominal profit, real loss". System must distinguish: direct trade cost / decision cost / operational allocation cost. Cannot conflate cost categories and distort risk/execution semantics.

**AI Attention Tax (Constitutional-level definition):**
Every position continuously consumes AI budget (monitoring, evaluation, stop-loss check). True position cost = financial cost + AI attention cost. When AI attention cost erodes expected margin to unacceptable level (cost_edge_ratio ≥ 0.8), system should recommend position closure. This naturally biases Agent toward low-maintenance, high-net-value strategies — profitable positions have "shelf life".

### Success Criteria (§13) — Ordered by Priority

1. Can be clearly defined
2. Boundary clear, responsibility clear
3. Won't randomly write, randomly grant permissions, randomly modify
4. Protects account during abnormal conditions
5. Has complete audit chain
6. Can run stably long-term
7. Can prove effectiveness on net PnL basis
8. Can progressively earn more autonomy in verified scenarios
9. Can achieve basic positive net return with zero external AI cost
10. Can continuously learn & self-evolve from trading behavior

### Constitutional Supremacy Statement (§14)
When later design docs/modules/field specs/GUI/API/strategies/learning conflict with this Constitution:
- This Constitution is the top constraint
- Lower designs must obey higher constitutional principles
- NOT the reverse

Modifications to Constitution follow strict procedure:
- Operator explicitly proposes modification with reasoning
- Assess impact on all downstream documents
- Approval before effect
- Version upgrade + change log
- Check & update all affected downstream docs

---

## 2. DOC-02: BOUNDARY DEFINITION (边界定义) (V2)

### Document Purpose
Answers: Where can Agent act? Where must it stop? Where does each governance layer begin/end? Clear boundary delineation between Agent autonomy, notification-only, and operator approval zones.

### Key Governance Layer Boundaries

#### H0 — Local Deterministic Judgment Core
- **Position:** First gate for all decisions
- **Properties:** Zero cost, minimum latency, pure local, NO AI reasoning
- **Multi-Agent Mapping:** Guardian Agent's hard check layer
- **Checks:**
  - Freshness gate: market data must be FRESH/RECENT (not STALE/EXPIRED)
  - Health gate: system health passing (CPU, memory, network, disk)
  - Eligibility gate: instrument in authorized product family at required capability level
  - Risk envelope: position size, leverage, margin within P0/P1 hard limits
  - Cooldown gate: consecutive-loss auto-pause not active
- **Boundary Rules:**
  - Non-bypassable: every decision must pass H0 before any higher layer
  - H0 failures = immediate rejection (no escalation to AI)
  - Executes in <1ms: pure in-memory, no external calls
  - Can only say NO (reject) or PASS (forward); never generates trading ideas

#### H1–H5 — AI Governance Layers (Multi-Agent Precursors)
V2 Restructure: V1 defined H1–H5 as 5 independent prompt roles. V2 clarifies they are Multi-Agent governance predecessor, mapping to specific Agent responsibilities (see EX-06).

**Current Transitional State (Session 12):**
- Code exists (thought_gate.py, budget_gate.py, model_router.py, governor.py, cost_logger.py)
- Main pipeline currently bypasses them (Capability C = 30%)
- Actual flow: H0 → direct strategy signal → Paper Engine
- Full AI governance integration gated on win_rate > 20%

#### I — Decision Lease Shadow Control Plane
- **Position:** H5 output is NOT instant command — it's a time-bound, revocable Decision Lease (implementation of Root Principle #3)
- **Multi-Agent Mapping:** Strategist signs lease, Executor consumes lease, Guardian can revoke any time
- **Lease Properties:**
  - TTL (Time-to-Live): auto-expires after configured duration
  - Revocability: Guardian or Operator can revoke any active lease anytime
  - Idempotency: unique ID per lease; double-execution prevented
  - Audit trail: all emission, execution, expiry, revocation logged
- **Boundary Rules:**
  - Executor ONLY acts on valid, non-expired, non-revoked lease
  - Executor cannot generate own leases
  - Lease authorizes specific action on specific instrument with specific parameters—no generalization
  - Current state: shadow-only (logged but not connected to live execution)

### Compute Path Trigger Boundaries (§3)

V2 Key Change: V1 described compute paths as passive review (evaluate tier after proposal received). V2 restructures as proactive scan mode: Agent actively scans market opportunities, routes by discovered complexity across compute tiers.

#### Proactive Scan vs Passive Review
- **Proactive:** Agent scans market continuously, identifies opportunities, routes to appropriate compute tier
- **Passive:** Wait for trade proposal, then decide which tier to use

#### Tier Trigger Matrix
Each compute tier has explicit trigger conditions. Agent selects lowest-cost tier capable of handling task:

- **L0:** Local deterministic (lowest latency, zero cost) — freshness, health gates, risk envelope, eligibility
- **L1:** Local Ollama (Qwen2.5 7B, 12GB memory) — regime detection, pattern recognition
- **L1.5:** Low-cost cloud (Haiku + Perplexity, ~$0.01–0.05/call) — market commentary, news sentiment
- **L2:** Full cloud (Sonnet/Opus) — complex multi-factor analysis, strategy evolution

**Cost-Benefit Logic:** Agent routes to lowest cost tier that can resolve the problem

### Authorization Matrix Principle (referenced from DOC-01 §9)
"What the Agent can do" must NOT be decided by vague semantics. Must be explicit authorization matrix binding dimensions:
- Market / product type
- Strategy family
- Risk envelope
- Position level
- Execution method
- System mode
- Current operational phase (shadow / paper / supervised live / constrained live)

Authorization must: displayable explicitly, auditable, versionable, revocable.

---

## 3. DOC-03: FIELD & STATE SPECIFICATION (字段级与状态级规范) (V1.1)

### Document Purpose
Defines all data structures, field-level constraints, state machines, and data model for the system. The "schema contract" between all modules.

### Key Structural Domains (based on extraction)
1. **Trading Object Models:** Orders, Positions, Strategies, Portfolios
2. **State Machines:** Order lifecycle (submitted → working → filled/cancelled), Position states, System modes
3. **Risk Constraints:** Field-level validation rules (max leverage, position size, margin requirements)
4. **Audit Objects:** Transaction logs, state change records, decision traces
5. **AI/Learning Objects:** Model metadata, backtesting results, hypothesis validation records

(Detailed field schemas extracted from document for integration with codebase schema validation)

---

## 4. DOC-04: AGENT CAPABILITY BLUEPRINT (Agent能力蓝图) (V2)

### Document Purpose
Authoritative reference for what Agent can do, should do, must not do — across all product families, strategies, market conditions, operational phases.

V2 Expansion: Incorporates CLAUDE.md A–J ten capability goals, full-product autonomous trading, Multi-Agent orchestration, adversarial market awareness, portfolio-level intelligence, Analyst evolution engine, time-slot awareness, zero-cost-runnable principle.

### Ten Capability Goals (A–J)

#### [A] Autonomous Trade Execution
- **Scope:** Complete order placement, cancellation, amendment, position management
- **Governance:** Every execution passes full pipeline: H0 → H1–H5 AI → Decision Lease → execution gate (NO shortcuts)
- **Product Families:** All 6 Bybit V5: spot, margin, perp_linear, perp_inverse, options, other_derivatives_reserved
- **Order Types:** market, limit, conditional, tp_sl_order, tp_sl_position, trailing_stop, reduce_only, post_only, iceberg, twap, batch
- **Margin Modes:** cross, isolated, portfolio
- **Position Modes:** one_way, hedge
- **Paper Trading:** Realistic slippage (0.05%) + fee model simulation (taker 0.055%, maker 0.02%)
- **Constraints:** Cannot bypass any gate (even under time pressure), cannot execute on unauthorized product families, cannot modify system_mode/execution_authority

#### [B] Cost & Revenue Awareness
- **Core:** Track Net PnL, not Gross PnL. Every decision evaluated on: "After all real costs, does this still have positive expected value?"
- **Mandatory Cost Components:** AI API cost, Bybit fees, slippage, equipment depreciation, electricity, infrastructure
- **Formula:** net_realized_pnl = realized_pnl − total_fees
- **AI Cost Attribution:** Per-position ai_cost_attributed_usd from L1/L1.5/L2 calls
- **Fee Optimization:** Maker-priority reduces cost from ~21bps to ~12bps
- **Per-Position Tracking:** cost_edge_ratio monitoring
- **Reporting:** Daily/weekly/monthly cost breakdown
- **Constraints:** Every trade must have positive net expected value after costs, L1.5/L2 calls gated on win_rate > 20%, L0+L1 (local Ollama) sufficient for basic operation

#### [C] Compute Path Intelligent Tiering
- **Core:** Every computation routed to most cost-effective tier capable of handling it. Proactive market scanning, not just passive proposal review.
- **Four Tiers:** L0 (deterministic) → L1 (local Ollama) → L1.5 (low-cost cloud) → L2 (full cloud)
- **Degradation Path:** L0 cache → L1 local → L1.5 Perplexity → L2 full search
- **Cost Accounting:** Integrated into net PnL
- **Hardware Constraints:** AMD AI MAX 395 + 128GB unified memory; Ollama: MemoryMax=12G, CPUQuota=150%
- **Constraints:** L0 always runs first, higher tiers only when L0 cannot resolve, AI budget adaptive+ROI-based with $2/day conservative ceiling

#### [D] Self-Observability
- **Scope:** Monitor own hardware, network, software health. Proactive degrade/pause when unhealthy (system health > market judgment)
- **Hardware Awareness:** CPU usage, memory pressure, disk I/O
- **Network Awareness:** REST latency, WebSocket stability, public egress IP, packet loss
- **Software Awareness:** Module bottleneck detection, DB query latency, script execution time
- **Degradation Trigger:** System health failing → escalate status, recommend mode downgrade

(Capability E–J detailed in full document extraction)

### Autonomy Matrix (§4 from DOC-01, reaffirmed here)

**Agent has COMPLETE AUTONOMY (no human intervention needed):**
- Select trading coins (scan 650+ symbols, decide which to trade)
- Select product family
- Select strategy
- Set strategy parameters
- Decide entry/exit timing
- Dynamically adjust P2 risk parameters within P1 limits
- Strategy weight adjustment & elimination of underperformers
- Execution method selection
- AI compute resource allocation
- Regime-aware stop-loss/take-profit/holding-time adjustment

**Agent decides, then notifies Operator (post-audit, no pre-approval):**
- New strategy going live (already verified in shadow+paper)
- Significant P2 parameter adjustment (still within P1 hard limits)
- New product family enablement (already verified in paper)
- AI model switching (A/B verified)

**Requires Operator Approval (extremely rare):**
- Modify P0/P1 hard limits themselves
- Modify constitutional root principles
- First-time enable completely new, unverified exchange function
- System architecture changes (add/delete Agent, modify governance chain)
- Paper → Live first-time authorization

---

## 5. DOC-05: TRUTH SOURCE & OWNERSHIP MATRIX (真相源与所有权矩阵) (V1.1)

### Document Purpose
Identify single source of truth for each critical fact. Prevent multiple modules from maintaining conflicting versions of same critical state.

### Mandatory Truth Sources (at minimum)

1. **Position State** — Bybit → reconciliation engine → cache
2. **Order State** — Bybit V5 REST → matching engine → cache
3. **Trade Execution State** — Bybit fills → settlement engine
4. **Risk State** — Guardian Agent computation → decision cache
5. **System Mode** — Central state machine (mode_state.json or DB)
6. **Agent Running Mode** — Agent runtime supervisor
7. **Decision Lease State** — Lease registry (shadow plane currently)
8. **Authorization Level** — Authorization matrix store (versioned, immutable)
9. **Audit Events** — Audit log (append-only, no modification/deletion allowed)

**Key Rule:** Never allow multiple modules to each maintain "their own correct version" of a critical fact.

---

## 6. DOC-06: CHANGE GOVERNANCE (变更治理) (V2)

### Document Purpose
Procedures for changes to system configuration, risk parameters, strategies, authorization, code, and governance itself.

### Change Categories

**L0 Changes (Zero Governance):** No approval needed
- Minor bug fixes not affecting trade logic
- UI/visualization updates
- Log message adjustments
- Documentation updates

**L1 Changes (Self-Governed by Agent):** Agent can auto-apply, post-notify Operator
- P2 risk parameter micro-adjustments (within pre-approved ranges per Root Principle §5.12)
- Strategy parameter tweaks (within pre-tested windows)
- Backtest hypothesis validation experiments
- New strategy incubation (if paper validation passes)

**L2 Changes (Operator Review):** Post-audit, general approval delegation
- Significant P2 range expansion
- New product family enablement
- AI model version upgrades
- Major parameter range shifts

**L3 Changes (Operator Pre-Approval):** Must get written approval BEFORE change
- P0/P1 hard limit modifications
- Constitutional root principle modifications
- System architecture changes (Agent add/remove, governance chain reorder)
- First Paper → Live authorization
- Authorization matrix modifications

### Change Governance Principles
- Changes traceable: before/after state, reasoning, approval authority
- Rollback capability: previous versions preserved, can revert
- Audit visibility: all changes logged, reviewable
- Version control: all governance documents versioned, change-logged

---

## 7. DOC-07: AUDIT & CIRCUIT BREAKER POLICY (审计事故与熔断政策) (V1.1)

### Document Purpose
Define audit trail requirements, incident detection triggers, circuit-breaker modes, and incident response procedures.

### Audit Trail Requirements
Every actionable decision must be reconstructable post-hoc with:
1. **Pre-Decision State:** Account, position, risk state before decision
2. **Decision Basis:** Why was decision made? What data, analysis, factors?
3. **Risk Approval:** What risk conclusion was reached? By which module?
4. **Authorization Basis:** What authorized this action to proceed?
5. **Execution Action:** What was actually executed?
6. **Post-Execution Result:** What happened? Error or success?

**Audit Design Principle:** If system performed action but cannot clearly reconstruct the above six elements, system design has FAILED (not "record not detailed enough").

### Circuit Breaker Triggers
System automatically downgrade/pause when:
- Data freshness expired
- API latency anomalous
- Network packet loss exceeds threshold
- Margin utilization exceeds P1 levels
- Consecutive losses exceed threshold
- Volatility anomalies (IV spike, gap)
- System component failure (module crash, DB connection lost)
- Reconciliation failure (exchange state ≠ local state)

### Degradation Modes (§12 from DOC-01)
System supports multi-level degradation from normal to complete stop:
1. **NORMAL** — Full autonomy
2. **CAUTIOUS** — Reduced position size, tighter stops
3. **REDUCED** — Only reduce positions, no new entries
4. **DEFENSIVE** — Only essential liquidation
5. **CIRCUIT_BREAKER** — Complete trading pause
6. **MANUAL_REVIEW** — Human-supervised mode

Recovery from high-risk mode → normal mode MUST be gradual (no cross-level jumps).

---

## 8. DOC-08: IMPLEMENTATION BRIDGE (实施桥梁) (V1)

### Document Purpose
Bridges gap between governance principles and concrete implementation. Specifies HOW to build the system to satisfy WHY (DOC-01) and WHAT (DOC-04).

### Key Implementation Domains

1. **Bybit V5 API Formal Boundary** — Exact API mappings, response parsing, error handling
2. **OMS & Execution Formal Boundary** — Order routing, execution slippage simulation, fee calculation
3. **Risk Control Boundary** — P0/P1 limit enforcement, position consolidation, margin calculation
4. **Reconciliation Formal Boundary** — State sync between local cache and exchange, conflict resolution
5. **Learning Boundary** — Backtesting framework, strategy validation, meta-learning
6. **Multi-Agent Orchestration Formal Boundary** — Inter-Agent communication protocol, lease lifecycle, priority arbitration
7. **Data Plane Perception Formal Boundary** — Market data ingestion, freshness checking, anomaly detection

(Implementation details in separate EX-01 through EX-07 formal boundary documents)

---

## 9. DOC-NAV: GOVERNANCE NAVIGATOR (治理文件导航) (V3)

### Document Purpose
Index and cross-reference guide for all 22 governance documents. Helps navigate relationships, dependencies, and lookup paths.

### Document Relationship Map

```
DOC-01 Constitution (WHY)
├─ DOC-02 Boundary Definition (WHERE)
├─ DOC-04 Agent Capability Blueprint (WHAT)
├─ DOC-03 Field & State Specification (DATA MODEL)
├─ DOC-05 Truth Source & Ownership (AUTHORITATIVE SOURCES)
├─ DOC-06 Change Governance (HOW TO CHANGE)
├─ DOC-07 Audit & Circuit Breaker (SAFETY & AUDIT)
└─ DOC-08 Implementation Bridge (HOW TO BUILD)

EX-01 through EX-07: Formal Boundary Definitions
└─ EX-01: Risk Control Boundary
└─ EX-02: OMS & Execution Boundary
└─ EX-03: Control Plane Boundary
└─ EX-04: Reconciliation Boundary
└─ EX-05: Learning Boundary
└─ EX-06: Multi-Agent Orchestration Boundary
└─ EX-07: Data Plane Perception Boundary
```

### Navigation Rules
- Start with DOC-01 for governance philosophy
- Use DOC-02 to understand operational boundaries
- Reference DOC-04 for capability validation
- Check DOC-03 for data structure compliance
- Consult EX-01 through EX-07 for implementation-level details
- Use DOC-NAV as index for cross-document lookup

---

## KEY CODEBASE IMPLEMENTATION MANDATES

Based on governance extraction, the following are **constitutional-level requirements** for implementation:

### 1. Non-Negotiable Principles (from Root Principles §5)
- [CRITICAL] H0 local deterministic gate always executes first, non-bypassable
- [CRITICAL] All write operations through single controlled entry point (Executor)
- [CRITICAL] AI output never becomes instant trade command
- [CRITICAL] Strategy layer cannot bypass Guardian risk control
- [CRITICAL] Every trade must be fully explainable & traceable
- [CRITICAL] Exchange-side disaster protection always maintained
- [CRITICAL] System defaults to contraction when uncertain

### 2. Multi-Agent Orchestration Requirements
- OpenClaw acts as Conductor for all Agent communication
- Each Agent has clear, non-overlapping responsibility boundary
- Inter-Agent conflict resolved by priority (Guardian > Strategist > others)
- Decision Lease must be formal object, not free-text (idempotent, TTL-based, revocable)

### 3. Cost Tracking & Net PnL Accountability
- Every trade decision includes cost accounting
- AI attention tax tracked per-position (cost_edge_ratio ≥ 0.8 triggers closure recommendation)
- System must achieve basic positive return on L0+L1 only (zero external API cost)
- AI budget adaptive, ROI-based, conservative $2/day ceiling

### 4. Compute Path Intelligence
- Proactive market scanning (not just passive proposal review)
- Route each decision to lowest-cost tier capable of resolution
- L0 always runs first; higher tiers only when needed
- Four-tier degradation path implemented

### 5. Degradation & Circuit-Breaker
- Minimum 6 operational modes (NORMAL → CAUTIOUS → REDUCED → DEFENSIVE → CIRCUIT_BREAKER → MANUAL_REVIEW)
- Explicit trigger conditions for each transition
- Recovery always gradual (no cross-level jumps)

### 6. Audit & Traceability
- All six audit reconstruction elements mandatory: pre-state, basis, approval, authorization, execution, result
- Append-only audit log (no modification/deletion)
- 100% trade reconstructability requirement

### 7. Authorization Matrix Enforcement
- Explicit matrix binding: market/strategy/risk/position/execution/mode/phase
- Cannot be overridden by vague logic
- Version control on authorization changes
- Operator final approval authority preserved

### 8. System Health Priority
- System health assessment BEFORE market judgment
- When unhealthy, data quality/API stability/reconciliation failures override market opportunity
- Proactive degradation rather than attempt to push through

---

## DOCUMENT INTERDEPENDENCIES FOR DEVELOPMENT

```
PHASE 1: Foundation (Constitution & Boundary)
├─ Implement DOC-01 (Constitutional Root Principles)
└─ Implement DOC-02 (Governance Layer Boundaries: H0, H1-H5, I)

PHASE 2: Data & Capability (Field Specs & Agent Blueprint)
├─ Implement DOC-03 (Field & State Specification)
└─ Implement DOC-04 (Agent Capability Blueprint A-J)

PHASE 3: Safety & Governance (Truth Source, Change, Audit)
├─ Implement DOC-05 (Truth Source & Ownership)
├─ Implement DOC-06 (Change Governance Procedures)
└─ Implement DOC-07 (Audit & Circuit Breaker)

PHASE 4: Integration (Implementation Bridge & Formalization)
├─ Implement DOC-08 (Implementation Bridge)
└─ Implement EX-01 through EX-07 (Formal Boundaries)
```

---

## CRITICAL QUOTES FROM CONSTITUTION (DOC-01)

> "The system's autonomy is: Agent has maximum freedom within hard boundaries, Operator only sets hard boundaries, never intervenes in specific trade decisions. Agent autonomy ≠ no boundaries—P0/P1 hard limits, constitutional root principles, system architecture are unpassable."

> "System must acknowledge and pursue Net PnL, not Gross PnL. Every cost must be admitted and tracked, including AI decision cost and AI attention tax. Project rejects the narrative: 'nominal profit, real loss'."

> "Every position has shelf life. When AI attention cost erodes expected margin (cost_edge_ratio ≥ 0.8), the position is no longer worth holding, even if profitable."

> "Success is defined NOT by short-term nominal profit maximization, but by: clear definition, clear boundaries/responsibilities, cannot randomly write/grant/modify, protects account in anomalies, has complete audit, runs stably long-term, proves effectiveness on net PnL, progressively earns more autonomy, operates zero-cost at basic level, continuously self-evolves."

> "When system cannot reliably judge, default behavior should shift conservative: no new positions, reduce frequency, reduce risk, reduce-only mode, cautious/circuit-breaker mode."

---

**END OF EXTRACTION**

*This summary captures the core governance structure. For implementation details, consult formal boundary documents (EX-01 through EX-07).*

