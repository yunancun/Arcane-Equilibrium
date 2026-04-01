> ⚠️ FROZEN — 本文件為歷史提取物，內容已整合至後續文檔。僅供歷史參考，不再更新。
> ⚠️ FROZEN — This file is a historical extract. Content has been consolidated into later documents. For reference only.

# Round 2 Fix Plan: Quick Reference

## Batch Checklist

### Batch 7: Conductor Core Loop
```
Files to create:
  ✓ /app/conductor_core_loop.py (400 lines)
  ✓ /tests/test_conductor_core_loop.py (400 lines)
Files to modify:
  ✓ /app/message_bus.py (+50 lines: subscribe/dispatch)
  ✓ /app/main.py (+30 lines: initialization)
Tests: 25 (priority queue, subscribers, dispatch)
Impact: 32% → 45% (+13%)
Duration: 2 sessions
```

### Batch 8: Guardian Agent
```
Files to create:
  ✓ /app/agents/guardian_agent.py (350 lines)
  ✓ /tests/test_guardian_agent.py (450 lines)
Files to modify:
  ✓ /app/main.py (+20 lines: init Guardian)
Tests: 30 (conflict detection, leverage cap, Sharpe check)
Impact: 45% → 60% (+15%)
Duration: 2 sessions
```

### Batch 9: Perception Plane Activation
```
Files to create:
  ✓ /app/perception_query_layer.py (200 lines)
  ✓ /tests/test_perception_activation.py (350 lines)
Files to modify:
  ✓ /app/pipeline_bridge.py (+80 lines: register_data calls)
Tests: 25 (mark kline, mark intel, mark signals)
Impact: 60% → 70% (+10%)
Duration: 1.5 sessions
```

### Batch 10: Analyst L1 Handler + L2 Trigger
```
Files to create:
  ✓ /app/agents/analyst_agent.py (700 lines)
  ✓ /app/analyst_scheduler.py (100 lines)
  ✓ /tests/test_analyst_agent.py (500 lines)
Tests: 35 (L1 metrics, L2 discovery, tier promotion)
Impact: 70% → 77% (+7%)
Duration: 2 sessions
```

### Batch 11: L2 Autonomous Alpha Search
```
Files to create:
  ✓ /app/layer2_daily_scheduler.py (250 lines)
  ✓ /app/layer2_budget_adjuster.py (200 lines)
  ✓ /tests/test_layer2_daily_scheduler.py (400 lines)
Tests: 30 (daily trigger, budget adjust, confirmation ROI)
Impact: 77% → 82% (+5%)
Duration: 1.5 sessions
```

### Batch 12: Paper→Live Bridge + Exchange Stops
```
Files to create:
  ✓ /app/live_execution_routes.py (200 lines)
  ✓ /tests/test_paper_live_integration.py (400 lines)
Files to modify:
  ✓ /app/protective_order_manager.py (+150 lines: exchange stops)
  ✓ /app/paper_live_gate.py (+200 lines: approval gates)
  ✓ /app/main.py (+20 lines: init PaperLiveGate)
Tests: 30 (protective orders, approval gates, E2E)
Impact: 82% → 88% (+6%)
Duration: 2 sessions
```

---

## Functional Completion Timeline

```
Session #1-2:   Batch 7 (Conductor)
  32% ──→ 45%  ████ Conductor wired, message bus active

Session #3-4:   Batch 8 (Guardian)
  45% ──→ 60%  ████████ Guardian veto gate operational

Session #5:     Batch 9 (Perception)
  60% ──→ 70%  ███████████ Data quality marking active

Session #6-7:   Batch 10 (Analyst)
  70% ──→ 77%  ████████████████ L1 passive, L2 auto-trigger weekly

Session #8:     Batch 11 (L2 Loop)
  77% ──→ 82%  █████████████████ Daily overnight alpha search

Session #9-10:  Batch 12 (Paper→Live)
  82% ──→ 88%  ██████████████████ Live execution with safety gates
```

---

## Core Code Additions per Batch

| Batch | Core Lines | Test Lines | New Files | Modified Files |
|-------|-----------|-----------|-----------|----------------|
| 7 | 400 | 400 | 2 | 2 |
| 8 | 350 | 450 | 2 | 1 |
| 9 | 200 | 350 | 2 | 1 |
| 10 | 700 | 500 | 3 | 1 |
| 11 | 450 | 400 | 3 | 1 |
| 12 | 350 | 400 | 2 | 3 |
| **Total** | **2,800** | **2,800** | **14** | **9** |

---

## Critical Path Dependencies

```
Batch 7 (Conductor) ←─ BLOCKER ─→ Batches 8-12
    ↓
Batch 8 (Guardian) ←─ supports ─→ Batch 12 (safety gates)
    ↓
Batch 9 (Perception) ←─ supports ─→ Batch 8 (confidence-based sizing)
    ↓
Batch 10 (Analyst) ←─ independent ─→ can start after Batch 7
    ↓
Batch 11 (L2) ←─ independent ─→ can start after Batch 7
    ↓
Batch 12 (Paper→Live) ←─ depends on ─→ Batches 7+8 (routing+veto)
```

**Key insight**: Batch 7 must complete first. Batches 8-12 can then run in parallel or sequential.

---

## Testing Strategy

Each batch has:
- **Unit tests**: Individual component isolation (50-70% of tests)
- **Integration tests**: E2E message flow (20-30%)
- **Acceptance test**: One canonical test per batch (marked `test_batch_X_acceptance()`)

**Total new tests**: 2,800 lines  
**Expected coverage**: 85%+ of new code  
**Framework**: pytest (existing in repo)

---

## Cost Control Safeguards

| Component | Budget | Hard Cap | Auto-Adjust |
|-----------|--------|----------|-------------|
| L2 sessions | $2/session | $3/day max | Yes (Batch 11) |
| L2 monthly | $60 baseline | $100/month | Yes |
| Conductor | Free (local) | N/A | N/A |
| Analyst | Free (Ollama) | N/A | N/A |
| Guardian | Free (local) | N/A | N/A |

---

## Success Metrics (Final)

- [ ] **Functional completion**: 88% (from 32%)
- [ ] **Agents**: 5/5 wired (Scout, Strategist, Guardian, Analyst, Executor)
- [ ] **Tests**: 4,598 total (from 1,798)
- [ ] **Learning**: L1 + L2 autonomous (weekly discovery)
- [ ] **Perception**: 100% coverage (all signals marked)
- [ ] **L2 AI**: Autonomous daily alpha search
- [ ] **Exchange**: Stop-loss orders live
- [ ] **Paper→Live**: Safe transition pathway
- [ ] **Cost**: Capped at $100/month L2 spend
- [ ] **Profitability**: Strategy variants tested before deployment

---

## Begin Here

1. Read: `/docs/governance_dev/2026-03-30--round2_fix_plan_batches_7_12.md` (full 2,072 line plan)
2. Start: Batch 7 → `conductor_core_loop.py` (400 lines)
3. Run tests: `pytest tests/test_conductor_core_loop.py`
4. Move to Batch 8 when Batch 7 passes acceptance test

---

**Last updated**: 2026-03-30  
**Next review**: After Batch 7 completion  
**Questions**: Refer to full plan document
