# Round 2 Fix Plan: Executive Summary
## 32% → 88% Functional Completion in 6 Batches

**Date**: 2026-03-30  
**Duration**: ~10 sessions over 2-3 weeks  
**Total code**: 2,800 lines core + 2,800 lines tests  

---

## The Gap: Why 75% Code but 32% Functionality?

| Component | Code Status | Functional Status | Root Cause |
|-----------|-------------|-------------------|-----------|
| **Agents** (5 roles) | 100% defined | 20% (only Scout wired) | 4 agents phantom—no handlers |
| **Message Bus** | 100% instantiated | 0% (zero subscribers) | Routes exist but no subscriptions |
| **Learning Pipeline** | L1-L5 gates defined | 20% (L1 only) | No L2-L5 handler code |
| **Perception Plane** | 100% injected | 0% (never called) | `register_data()` never invoked |
| **L2 AI Engine** | 100% complete | 5% (manual trigger only) | No autonomous loop |
| **Paper→Live Gate** | 100% stubbed | 0% (never instantiated) | No execution pathway |

---

## Strategy: 6 Independent Batches

Each batch is:
- **Independently testable** (200-400 unit tests per batch)
- **Independently deployable** (no cross-batch dependencies)
- **Profit-focused** (prioritizes alpha generation over architecture)
- **Session-bounded** (1.5-2 sessions per batch)

### Batch 7: Conductor Event Loop (~13% gain)
**Wire**: Conductor + MessageBus → auto-dispatch to agents  
**Enables**: Batches 8-12 (all depend on message routing)  
**Tests**: 25 tests (event loop, priority queue, subscribers)  
**Impact**: 32% → 45%

### Batch 8: Guardian Veto Gate (~15% gain)
**Implements**: Risk veto agent (rejects conflicting orders)  
**Enables**: Safe autonomous execution (prevents portfolio conflicts)  
**Tests**: 30 tests (directional conflict, leverage cap, Sharpe check)  
**Impact**: 45% → 60%

### Batch 9: Perception Data Marking (~10% gain)
**Activates**: Fact/Inference/Hypothesis marking on all signals  
**Enables**: Confidence-based risk sizing (better decisions with better data)  
**Tests**: 25 tests (mark klines, scout intel, strategy signals)  
**Impact**: 60% → 70%

### Batch 10: Analyst L1+L2 (~7% gain)
**Implements**: Observation handler + weekly pattern discovery  
**Enables**: Regime-specific strategy ranking (learns what works when)  
**Tests**: 35 tests (L1 metrics, L2 Ollama discovery, tier promotion)  
**Impact**: 70% → 77%

### Batch 11: L2 Autonomous Alpha (~5% gain)
**Implements**: Daily overnight L2 reasoning (discover novel factors)  
**Enables**: Strategy variant generation (feeds L3 hypothesis testing)  
**Tests**: 30 tests (daily trigger, budget adjuster, confirmation ROI)  
**Impact**: 77% → 82%

### Batch 12: Paper→Live Bridge (~6% gain)
**Implements**: Exchange stop-loss + live execution gates  
**Enables**: Safe transition to live trading (10% position size ramp-up)  
**Tests**: 30 tests (protective orders, approval gates, emergency disable)  
**Impact**: 82% → 88%

---

## Completion Scorecard

| Metric | Start | End | Gain |
|--------|-------|-----|------|
| **Functional Completion** | 32% | 88% | **+56%** |
| **Agents Wired** | 1/5 | 5/5 | **+4** |
| **Agent Subscribers** | 0 | 100% | **Full** |
| **Learning Tiers** | L1 partial | L1-L2 auto | **+100%** |
| **Perception Coverage** | 0% | 100% | **Full** |
| **Exchange Integration** | None | Stop-loss + Live | **+2 major** |
| **Tests** | 1,798 | 4,598 | **+2,800** |
| **Cost Budget** | Uncapped | $100/mo | **Controlled** |

---

## Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| **L2 API cost overrun** | Budget adjuster + $100/month hard cap |
| **Guardian conflicts with RiskManager** | Guardian wraps (doesn't replace) existing checks |
| **Live catastrophic loss** | Exchange stop-loss + 10% position size + Sharpe > 1.0 gate |
| **False patterns in L2** | L3 hypothesis testing (Batch 13) validates before deployment |

---

## Success Criteria (Post-Batch 12)

✓ All 5 agents wired (Scout, Strategist, Guardian, Analyst, Executor)  
✓ Message bus 100% subscriber coverage  
✓ Learning pipeline autonomous (L1 recording, L2 discovery weekly)  
✓ Perception plane marks all data (fact/inference/hypothesis)  
✓ L2 searches for alpha autonomously (daily overnight runs)  
✓ Exchange stops integrated (Bybit conditional orders)  
✓ Paper→Live transition safe (gates + audit trail)  
✓ Test coverage: 4,598 tests (from 1,798)  
✓ Cost control: L2 spend capped  

---

## Implementation Readiness

- **Codebase state**: Ready (scaffold exists, just needs wiring)
- **Testing infrastructure**: Ready (63 test files, pytest framework)
- **Local AI**: Ready (Ollama + Qwen 3.5 deployed, free)
- **Architecture**: Ready (governance-first, fail-closed, audit trails)

### Next Steps
1. Start Batch 7 (Conductor event loop) → 2 sessions
2. Parallel testing on Batch 8 (Guardian) → can start mid-Batch 7
3. Weekly cadence: 1-2 batches per week
4. Total timeline: ~10 sessions, 2-3 weeks

---

## Key Files

**Plan document**: `/docs/governance_dev/2026-03-30--round2_fix_plan_batches_7_12.md` (2,072 lines)

**Summary**: This document

**To begin**: Start implementing Batch 7 → Conductor Core Loop (conductor_core_loop.py + message_bus integration)
