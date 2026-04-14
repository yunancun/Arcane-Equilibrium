# R-06 Deep Analysis: AIE + FA + FM Assessment

**Date**: 2026-04-13
**Status**: Draft — pending Operator decision on direction
**Context**: G-1/R-06 "full 5-agent wiring" re-evaluated from value perspective

---

## 1. Executive Summary

Original R-06 plan (IPC plumbing) is **100% ceremony, 0% value delivery**. Deep analysis reveals:

- **Path A (Python Agent pipeline) is BROKEN at Executor** — `_paper_engine=None` since DEAD-PY-2
- **Analyst output has zero consumers** — PatternInsight produced but Rust never reads it
- **Conductor methods have zero production callers** — only tests call dispatch/resolve/allocate
- **Adding Rust→Python IPC = connecting pipes to empty buckets**

Recommended: **Redefine R-06 as "Agent Value Delivery"** — close learning loops, not add plumbing.

---

## 2. System Architecture: Two Parallel Trading Paths

| Path | Components | Status |
|------|-----------|--------|
| **Path A** Python Agent | Scout→Strategist→Guardian→Executor | **Executor BROKEN**: `_paper_engine=None` (DEAD-PY-2 deleted PaperTradingEngine), all APPROVED_INTENT return `success=False` |
| **Path B** Rust Pipeline | 5 strategies→IntentProcessor→paper_state | Running but all strategies gross edge near 0 or negative |
| **Bridge** | StrategistScheduler (5min Rust→Python→Ollama→param tuning→Rust apply) | Connected and functional, but param tuning hasn't improved edge yet |

---

## 3. Agent Actual vs Nominal Function

| Agent | Nominal | Actual | Output Consumed By |
|-------|---------|--------|--------------------|
| **Scout** | Market intel scan | Produces IntelObject → MessageBus | Strategist receives |
| **Strategist** | Trade intent + param tuning | (1) Intel→TradeIntent→Guardian; (2) IPC→Ollama→param recommendations | Guardian (intents); Rust (params) |
| **Guardian** | Risk review | 5 deterministic checks → APPROVED/REJECTED/MODIFIED | Executor (but Executor broken) |
| **Analyst** | Trade attribution | L1 rolling metrics + L2 PatternInsight | TruthRegistry records, **Rust engine never reads** |
| **Executor** | Execute approved intents | `_paper_engine.submit_order()` → **always fails** (None) | Nothing |
| **Conductor** | Orchestration | Agent registry + lifecycle mgmt | **dispatch/resolve/process_trade_intent = zero production calls** |

---

## 4. H0-H5 Governance Layer Status

- **H0**: Active — Rust deterministic hard gate (freshness/health/eligibility/risk/cooldown)
- **H1**: Active — AI call budget/complexity/cooldown gate
- **H2**: Not implemented (no code)
- **H3**: Active — Model router (complexity → L1_9b/L1_27b/L2)
- **H4**: Active — AI output structure validation (fail-closed)
- **H5**: Not implemented (no code)

---

## 5. Learning Loop Status

```
Strategist param tuning ──→ Rust strategy params ──→ Trade results
       ^                                                 |
       |    StrategistScheduler reads fills metrics       |
       └─────────────────────────────────────────────────┘
                          (CLOSED but not improving edge)

Guardian rejections ──→ ??? ──→ Strategist next decision
                        ^
                  NO FEEDBACK PATH

Analyst PatternInsight ──→ ??? ──→ Strategy improvement
                            ^
                      RUST NEVER READS
```

---

## 6. Original R-06 Value Assessment

| Item | Original Plan | Value |
|------|--------------|-------|
| Conductor stub→real | IPC handler calls Conductor methods | Conductor methods themselves have zero callers = **idle** |
| Rust→analyst_evaluate | Fire-and-forget on fills | Analyst output has no consumer = **extra log line** |
| Rust→conductor_evaluate | 2min health check | Pure monitoring, no decision impact. GUI already has agent health endpoint |
| Rust→scout_scan | Trigger scan from Rust | Rust Scanner already independent. Python Scout works via MessageBus |

**Conclusion: Original R-06 is 100% plumbing, 0% value.**

---

## 7. Recommended Directions

### Direction A: Fix Executor IPC Bridge (make Path A work)
- ExecutorAgent uses Rust IPC `SubmitOrder` instead of `_paper_engine.submit_order()`
- Risk: Two paths trading simultaneously = position conflicts
- Needs: Mutual exclusion design
- Recommendation: Do as shadow-only first

### Direction B: Close Learning Loops (highest value)
- Analyst PatternInsight → DB → Strategist reads next cycle
- Guardian rejection stats → DB → Strategist adjusts risk appetite
- This makes agents ACTUALLY USEFUL for the first time
- Recommendation: **Do this first**

### Direction C: Skip R-06, Fix Strategies Directly
- Phase 5 PAUSED because strategies have negative edge
- Agent tuning assumes strategies CAN be profitable
- If strategy logic is fundamentally flawed, agent tuning is optimizing a losing system
- Recommendation: Valid concern, but need data (which Direction B provides)

---

## 8. Proposed R-06-v2 Scope

**Step 1** (P0): Executor IPC bridge — `_paper_engine is None` → fallback to Rust IPC `SubmitOrder` (shadow=True default). ~50 lines Python.

**Step 2** (P1): Analyst → DB → Strategist feedback — PatternInsight writes `learning.pattern_insights`, StrategistScheduler reads and includes in Ollama prompt. ~100 lines (Rust DB + prompt).

**Step 3** (P1): Guardian rejection feedback — per-strategy reject_rate writes DB, Strategist reads to adjust aggressiveness. ~60 lines.

**Step 4** (P2): Conductor stub→real — now has actual purpose (coordinating Analyst + Guardian feedback). ~30 lines Python.

**Not doing**: Rust→Python fire-and-forget IPC, Conductor health polling, Rust→scout_scan.

---

## 9. Key File References

| File | Role | Lines |
|------|------|-------|
| `executor_agent.py:370-384` | Broken execution path (`_paper_engine is None`) |
| `strategy_wiring.py:287-294` | `PAPER_ENGINE = None` (ARCH-RC1 1C-3-F retired) |
| `paper_trading_wiring.py:58-74` | `ENGINE = None` stub (PaperTradingEngine deleted) |
| `analyst_agent.py:487-562` | PatternInsight → TruthRegistry (unread by Rust) |
| `guardian_agent.py:290-298` | Verdict sent back to Strategist (no DB persistence) |
| `multi_agent_framework.py:769-804` | Conductor.dispatch_market_event (zero production callers) |
| `strategist_scheduler.rs:162-254` | Evaluate cycle (reads fills metrics, not Analyst insights) |
| `ai_service.py:524-547` | `_handle_conductor()` stub |
