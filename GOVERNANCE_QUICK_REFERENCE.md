# OpenClaw ByBit Governance - Quick Reference Guide

## 16 Root Principles (DOC-01 §5.1–§5.16)

### V1 Original (§5.1–§5.10)
1. **Single Write Port** — All order actions through ONE controlled entry only
2. **Read-Write Separation** — Research/GUI: read-only. Write: extremely limited
3. **AI ≠ Instant Command** — AI output: suggestions, leases, explanations (not direct orders)
4. **Strategy Cannot Bypass Risk** — All intent through Guardian approval
5. **Survival > Profit** — Judge system on "won't spiral" before "can profit"
6. **Failure Default Contraction** — Uncertain? Default conservative
7. **Learning ≠ Rewrite Live** — Learning isolated from live. Suggestions only
8. **Trade Explainability** — Every trade must reconstruct: why, when, risk acceptance, authorization, execution, outcome
9. **Exchange Disaster Protection** — Local stop-loss + exchange-side condititional orders as dual defense
10. **Cognitive Honesty** — Clearly distinguish: fact / inference / assumption. External data = inference-level

### V2 New (§5.11–§5.16)
11. **Agent Maximum Autonomy** — Within P0/P1 hard limits, Agent fully autonomous on all trading decisions. Operator sets boundaries only
12. **Continuous Evolution** — System MUST auto-learn from trading behavior. New strategies: auto-enter live if paper passes
13. **AI Resource Cost Awareness** — Every AI call counted. cost_edge_ratio ≥ 0.8 → recommend closure
14. **Zero External Cost Runnable** — Basic operation on L0+L1 only (Ollama+free search). Cloud AI = enhancement
15. **Multi-Agent Collaboration** — OpenClaw Conductor + 6 Agents. Formal object communication (not free text)
16. **Portfolio-Level Risk** — Monitor correlation exposure, strategy overlaps, capital allocation, broad-market drawdown

---

## Priority Ordering (Top 7)

1. Account Survival
2. Risk Governance
3. System Health & Consistency
4. Audit Traceability
5. Human Final Governance
6. **Real** Net PnL
7. Autonomous Capability & Evolution

---

## 6 Agent Roles (DOC-01 §1)

| Agent | Responsibility |
|-------|----------------|
| **OpenClaw** | Central Conductor — task distribution, conflict arbitration, resource allocation |
| **Scout** | External intelligence (news, events, sentiment) |
| **Strategist** | Trading decisions (coin, strategy, parameters, portfolio allocation) |
| **Guardian** | Dynamic risk control (adaptive adjustment within P0/P1) |
| **Analyst** | Continuous evolution (post-trade analysis, pattern discovery, strategy incubation) |
| **Executor** | Intelligent execution (adversarial stop-loss, maker priority, time awareness) |

**H0 Local Gate:** Outside all Agents — zero-cost, deterministic, always first

---

## Governance Layers (DOC-02)

| Layer | Role | Cost | Latency |
|-------|------|------|---------|
| **H0** | Deterministic gate (freshness, health, risk envelope, eligibility) | Zero | <1ms |
| **H1–H5** | AI governance (thought, budget, routing, governing, cost) | ~Zero (local) | ~100ms |
| **I** | Decision Lease shadow plane (formal, TTL, revocable) | Zero | ~1ms |

**Flow:** H0 (rejects immediately) → H1–H5 (AI analysis) → I (lease generation) → Executor (consumes lease)

---

## Compute Path (4 Tiers)

| Tier | Technology | Cost | Use Case |
|------|-----------|------|----------|
| **L0** | Deterministic rules | Zero | Freshness, health, risk envelope, eligibility |
| **L1** | Local Ollama (Qwen2.5 7B) | Zero API | Regime detection, pattern recognition |
| **L1.5** | Low-cost cloud (Haiku + Perplexity) | ~$0.01–0.05/call | Market commentary, sentiment |
| **L2** | Full cloud (Sonnet/Opus) | ~$0.10+/call | Complex analysis, strategy evolution |

**Cost Logic:** Agent routes to lowest-cost tier capable of resolution. L0 first, always.

---

## Autonomy Matrix (DOC-01 §4, reaffirmed DOC-04)

### Agent Complete Autonomy (no human intervention)
- Coin selection (650+ symbols → choose which to trade)
- Product family selection
- Strategy selection & parameter setting
- Entry/exit timing
- P2 risk parameter adjustment (within P1 limits)
- Execution method (limit/market/split/iceberg/twap)
- AI resource allocation
- Time-slot aware stop-loss adjustment

### Agent Decides → Notify Operator (post-audit, no pre-approval)
- New strategy live (already paper-verified)
- Significant P2 adjustment (within P1)
- New product family enabled (already paper-tested)
- AI model switching (A/B verified)

### Requires Operator Pre-Approval (extremely rare)
- Modify P0/P1 hard limits
- Modify constitutional principles
- First unverified exchange function
- System architecture changes
- Paper → Live first authorization

---

## Change Governance Categories (DOC-06)

| Category | Approval | Examples |
|----------|----------|----------|
| **L0** | None | Bug fixes, UI updates, docs |
| **L1** | Self-governed by Agent | P2 micro-adjustments, strategy tweaks, backtest validation |
| **L2** | Post-audit review | P2 range expansion, product family enable, AI model upgrade |
| **L3** | Operator pre-approval | P0/P1 modification, constitution change, architecture change, Paper→Live |

---

## Degradation Modes (DOC-07, DOC-01 §12)

1. **NORMAL** — Full autonomy
2. **CAUTIOUS** — Reduced position size, tighter stops
3. **REDUCED** — Only reduce positions, no new entries
4. **DEFENSIVE** — Only essential liquidation
5. **CIRCUIT_BREAKER** — Complete trading pause
6. **MANUAL_REVIEW** — Human-supervised mode

**Recovery Rule:** Must be gradual (no cross-level jumps)

---

## Net PnL Accountability (DOC-01 §6)

**Mandatory Cost Components:**
- Trading fees (maker/taker, VIP changes)
- Slippage (estimated vs actual)
- Funding/borrowing costs
- **AI decision cost** (local compute + cloud API)
- **AI attention tax** (cost_edge_ratio per position)
- Compute & infrastructure
- Operational friction

**AI Attention Tax Formula:**
- position_true_cost = financial_cost + ai_attention_cost
- When cost_edge_ratio ≥ 0.8 → recommend closure
- Profitable positions have shelf life

**Project Principle:** "Nominal profit, real loss" is REJECTED. Net PnL only.

---

## Audit Trail Reconstruction (DOC-07, DOC-01 §11)

**All 6 elements required for every trade:**
1. **Pre-State** — Account, position, risk state before decision
2. **Basis** — Data, analysis, factors for decision
3. **Risk Approval** — Risk conclusion + responsible module
4. **Authorization** — What authorized this action?
5. **Execution** — What was actually executed?
6. **Result** — Error or success? What happened?

**Principle:** If you can't reconstruct these 6 elements → system design FAILED (not "record incomplete")

---

## Success Criteria (DOC-01 §13, ordered)

1. Can be clearly defined
2. Boundary clear, responsibility clear
3. Won't randomly write/grant/modify
4. Protects account in anomalies
5. Has complete audit chain
6. Runs stably long-term
7. Proves effectiveness on **net PnL** basis
8. Progressively earns more autonomy in verified scenarios
9. **Zero external AI cost** achieves basic positive return
10. Continuously self-evolves from trading behavior

---

## Truth Sources (DOC-05, mandatory)

| Fact | True Source | Derivation |
|------|-----------|-----------|
| Position State | Bybit | → Reconciliation → Cache |
| Order State | Bybit V5 REST | → Matching → Cache |
| Trade State | Bybit fills | → Settlement |
| Risk State | Guardian computation | → Decision cache |
| System Mode | Central state machine | Version-controlled |
| Authorization Level | Authorization matrix | Immutable, versioned |
| Audit Events | Audit log | Append-only |

**Rule:** Never allow multiple modules to maintain own "correct version" of same fact.

---

## Implementation Priority (PHASE ordering)

**PHASE 1:** DOC-01 (Constitution) + DOC-02 (Boundaries)  
**PHASE 2:** DOC-03 (Data) + DOC-04 (Capabilities)  
**PHASE 3:** DOC-05 (Truth) + DOC-06 (Changes) + DOC-07 (Audit)  
**PHASE 4:** DOC-08 (Bridge) + EX-01 through EX-07 (Formal Boundaries)

---

## Critical Constitutional Quotes

> "AI output never becomes instant trade command. AI output forms: explanations, suggestions, audit conclusions, time-constrained Decision Lease drafts."

> "Agent autonomy ≠ no boundaries. P0/P1 hard limits, constitutional root principles, system architecture are unpassable."

> "System defaults to contraction when uncertain: no new positions, reduce frequency, reduce risk, reduce-only mode, cautious/circuit-breaker mode."

> "Every position has shelf life. When AI attention cost erodes expected margin, position is no longer worth holding, even if profitable."

> "Success is NOT short-term profit maximization. Success is: clear definition, clear boundaries, protects account, complete audit, stable operation, net PnL proof, continuous evolution, zero-cost operation, self-learning."

---

**For Full Details:** See GOVERNANCE_STRUCTURED_EXTRACT.md

