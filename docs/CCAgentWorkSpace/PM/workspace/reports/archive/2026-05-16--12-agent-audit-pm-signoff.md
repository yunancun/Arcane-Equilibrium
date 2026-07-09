# PM Sign-off: 12-Agent Consolidated Audit Fix Plan
## 2026-05-16

### Verdict: APPROVED-CONDITIONAL

PA delivered a strong consolidated fix plan from 12 parallel audit agents.
13 WPs across 4 waves. Estimated 12-15 sessions total effort.

### 5 PM Reprioritizations

1. **WP-02 P0 -> P1**: Runtime already calls `donchian_prior()` since `75741eff`.
   Base `donchian()` retaining current-bar is hygiene, not live P0.
2. **WP-08 MIT-P0-2 cron conflict**: "6/12 not installed" vs TODO P0-V3-CRON-NOT-INSTALLED
   DONE 2026-05-09. PA must reconcile before dispatch.
3. **AI-E-F-01 budget $100->$2**: Requires operator decision on target value.
4. **R4 "CRITICAL" -> P2**: Doc drift is cosmetic, not critical.
5. **WP-06 split recommended**: WP-06a (Rust clone/Arc), WP-06b (Python deepcopy),
   WP-06c (orjson) for parallel dispatch.

### True P0 Items
- WP-01 GUI Safety (A3-BLOCKER-1/2: emergency stop / close all one-click)
- P0-EDGE-1 (structural, not code-fixable)

### Approved Wave Sequence
- Wave 1: WP-01 + WP-02 + WP-05 + WP-09 (zero file overlap, max parallel)
- Wave 2: WP-03 + WP-04 + WP-10 + WP-07 (independent)
- Wave 3: WP-08 + WP-06 + WP-13 (Linux access / focused)
- Wave 4: WP-11 + WP-12 (phased / deferred)

### Operator Actions Required
1. Confirm PM reprioritizations
2. Decide AI budget_config.toml target ($2 or justified higher)
3. Confirm PG tuning values + restart window
4. Approve session dispatch order
5. Confirm EDGE-P2-3 Phase 1b 3-gate monitoring continues in parallel

### Deliverables
- Approved report: `srv/2026-05-16--full-system-audit-fix-plan.md`
- TODO v33: `srv/TODO.md` section 11.6 (13 WPs + wave table)
- PA source: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--12-agent-consolidated-fix-plan.md`
