# Round 2 Fix Plan: Complete Index
## Design Document for 32% → 88% Functional Completion

**Date**: 2026-03-30  
**Author**: PM/FA (OpenClaw Governance Team)  
**Status**: READY FOR IMPLEMENTATION  
**Total Sessions**: ~10 (over 2-3 weeks)  

---

## Documents in This Plan

### 1. QUICK_REFERENCE.md (5.6 KB)
**For**: Developers wanting the executive summary  
**Contains**:
- Batch checklist (files to create/modify, test counts)
- Session-by-session timeline
- Lines of code per batch
- Critical path dependencies
- Testing strategy overview
- Cost control safeguards

**Read this if**: You need to see what's being built and how long it takes.

### 2. EXECUTIVE_SUMMARY.md (5.1 KB)
**For**: Project managers and stakeholders  
**Contains**:
- Why 75% code but 32% functional (the gap diagnosis)
- 6 batch strategy with rationale
- Completion scorecard (32% → 88%)
- Risk mitigations
- Success criteria
- Implementation readiness checklist

**Read this if**: You need to understand the strategy and risks.

### 3. batches_7_12.md (75 KB, 2,072 lines)
**For**: Engineers implementing the plan  
**Contains**:
- Detailed specification for each of 6 batches
- Exact files to create/modify with line numbers
- Pseudocode or actual code snippets
- Implementation checklists per task
- Test criteria for each batch
- Expected impact on functional completion

**Read this if**: You're about to write code.

---

## How to Use This Plan

### Phase 1: Understanding (30 min)
1. Read: QUICK_REFERENCE.md (5 min)
2. Read: EXECUTIVE_SUMMARY.md (5 min)
3. Skim: batches_7_12.md intro sections (20 min)

### Phase 2: Implementation (10 sessions, 2-3 weeks)
1. Start with Batch 7 (Conductor Core Loop)
   - Follow detailed spec in batches_7_12.md § Batch 7
   - Create files listed under "Specific Tasks"
   - Run test suite: `pytest tests/test_conductor_core_loop.py`
   - Pass acceptance test to proceed
   
2. After Batch 7 completes, begin Batch 8 (Guardian Agent)
   - Can start immediately (independent of Batch 7 if needed)
   - Follow same pattern: spec → code → test → accept

3. Continue Batches 9-12 sequentially
   - Each batch is independently testable
   - No need to wait for earlier batch completion if architecture is clear

### Phase 3: Validation (after Batch 12)
1. Run full test suite: `pytest tests/test_*.py`
2. Verify functional completion: 88%+ (from 32%)
3. Verify agent wiring: `python -m pytest tests/ -k "agent"`
4. Check cost tracking: L2 spend capped at $100/month

---

## Key Metrics

| Metric | Value | Tracked |
|--------|-------|---------|
| Starting functional completion | 32% | Baseline (Round 2 audit) |
| Ending functional completion | 88% | Post-Batch 12 |
| Batches | 6 | Batch 7-12 |
| Sessions required | ~10 | ~1.5-2 per batch |
| Total lines added (core) | 2,800 | Across 14 new files |
| Total lines added (tests) | 2,800 | Across 6 test files |
| Final test count | 4,598 | From 1,798 baseline |
| L2 monthly budget | $100 | Hard cap |

---

## Batch Dependency Graph

```
                        Batch 7 (Conductor)
                             ↓
         ┌────────────────────┼────────────────────┐
         ↓                    ↓                    ↓
    Batch 8 (Guardian)   Batch 10 (Analyst)   Batch 11 (L2)
         ↓                    ↓                    ↓
    Batch 9 (Perception) (independent)       (independent)
         ↓
    Batch 12 (Paper→Live)
         ↓
    Complete (88%)
```

**Critical Path**: Batch 7 → Batch 8 → Batch 12  
**Can parallelize**: Batches 10-11 while doing 8-9  
**Duration**: ~10 sessions (2-3 weeks)

---

## Success Criteria Checklist

After completing all 6 batches:

### Functional Metrics
- [ ] Functional completion: 88% (from 32%)
- [ ] All 5 agents wired (Scout, Strategist, Guardian, Analyst, Executor)
- [ ] Message bus: 100% subscriber coverage
- [ ] Learning pipeline: L1 + L2 autonomous
- [ ] Perception plane: 100% coverage (all signals marked)

### Engineering Metrics
- [ ] Tests: 4,598 total (1,798 baseline + 2,800 new)
- [ ] Code coverage: 85%+ of new code
- [ ] All acceptance tests passing
- [ ] No regressions in Round 1 work

### Product Metrics
- [ ] L2 autonomous daily alpha search (working)
- [ ] Exchange stop-loss orders (live)
- [ ] Paper→Live transition (safe gating)
- [ ] Cost control: L2 spend capped at $100/month

### Risk Metrics
- [ ] Zero new security vulnerabilities
- [ ] Governance compliance: 100% (audit trail for all decisions)
- [ ] Emergency disable working (Paper→Live)

---

## File Organization

```
/docs/governance_dev/
├── 2026-03-30--ROUND2_FIX_PLAN_INDEX.md          (this file)
├── 2026-03-30--round2_fix_plan_QUICK_REFERENCE.md
├── 2026-03-30--round2_fix_plan_EXECUTIVE_SUMMARY.md
└── 2026-03-30--round2_fix_plan_batches_7_12.md    (main spec)

/app/
├── conductor_core_loop.py                          (Batch 7, NEW)
├── agents/
│   ├── guardian_agent.py                          (Batch 8, NEW)
│   └── analyst_agent.py                           (Batch 10, NEW)
├── perception_query_layer.py                      (Batch 9, NEW)
├── analyst_scheduler.py                           (Batch 10, NEW)
├── layer2_daily_scheduler.py                      (Batch 11, NEW)
├── layer2_budget_adjuster.py                      (Batch 11, NEW)
├── live_execution_routes.py                       (Batch 12, NEW)
├── message_bus.py                                 (MODIFY: +50 lines)
├── pipeline_bridge.py                             (MODIFY: +80 lines)
├── protective_order_manager.py                    (MODIFY: +150 lines)
├── paper_live_gate.py                             (MODIFY: +200 lines)
└── main.py                                        (MODIFY: +70 lines)

/tests/
├── test_conductor_core_loop.py                    (Batch 7, NEW)
├── test_guardian_agent.py                         (Batch 8, NEW)
├── test_perception_activation.py                  (Batch 9, NEW)
├── test_analyst_agent.py                          (Batch 10, NEW)
├── test_layer2_daily_scheduler.py                 (Batch 11, NEW)
└── test_paper_live_integration.py                 (Batch 12, NEW)
```

---

## Starting Point

**To begin Batch 7 immediately**:

1. Create `/app/conductor_core_loop.py` (400 lines)
   - See: batches_7_12.md § Batch 7 → Task 7.1

2. Modify `/app/message_bus.py` (+50 lines)
   - See: batches_7_12.md § Batch 7 → Task 7.2

3. Create `/tests/test_conductor_core_loop.py` (400 lines)
   - See: batches_7_12.md § Batch 7 → Task 7.4

4. Run tests:
   ```bash
   cd /sessions/upbeat-laughing-rubin/BybitOpenClaw
   pytest tests/test_conductor_core_loop.py -v
   ```

5. Verify acceptance test passes:
   ```bash
   pytest tests/test_conductor_core_loop.py::test_batch_7_acceptance -v
   ```

6. Proceed to Batch 8 when Batch 7 acceptance test passes.

---

## Q&A

**Q: Can we parallelize batches?**  
A: Yes. Batch 7 must complete first. Then Batches 8-12 can run sequentially or parallel. Batches 10-11 can be worked in parallel with Batches 8-9 once routing is wired.

**Q: How long is each batch?**  
A: 1.5-2 sessions per batch. Batches 9 and 11 are shorter (1.5 sessions). Batches 7, 8, 10, 12 are longer (2 sessions).

**Q: What if we hit a blocker?**  
A: Each batch is independently testable. If Batch 8 hits an issue, restart it without blocking Batches 10-11. Batch 12 requires Batch 7+8 to be working.

**Q: What about costs?**  
A: Batch 11 has L2 cost control. Default budget is $2/session, $3/day max, $100/month cap. The budget adjuster auto-adjusts based on finding quality.

**Q: What about the existing tests (1,798)?**  
A: They should pass with zero regressions. Add 2,800 new tests on top. Expected final: 4,598 tests.

**Q: What about governance compliance?**  
A: All batches respect the existing governance-first architecture. New code fits into existing contracts (EX-06 for agents, EX-07 for perception, etc.).

---

## Related Documents

- **Round 1 Results**: `/docs/governance_dev/changelogs/2026-03-30_*.md` (8 phases completed)
- **Audit Report**: `/docs/references/2026-03-27--phase2_round2_strategic_audit_report.md`
- **Governance Docs**: `/docs/governance_dev/` (22 total governance references)

---

## Last Updated

**Date**: 2026-03-30  
**By**: PM/FA  
**Status**: READY FOR COWORK SESSION  
**Next Review**: After Batch 7 completion

---

## Begin Implementation

→ **START HERE**: Read QUICK_REFERENCE.md (5 min)  
→ **THEN**: Read batches_7_12.md § Batch 7 (30 min)  
→ **CODE**: Implement Batch 7 (2 sessions)  
→ **TEST**: Run full test suite  
→ **NEXT**: Batch 8 (repeat)  

**Timeline**: ~10 sessions, 2-3 weeks to 88% functional completion.
