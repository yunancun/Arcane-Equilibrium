# AMD-2026-05-31-01: Alpha-Edge Evidence Governance

Date: 2026-05-31
Status: **Active**
Index: `docs/governance_dev/SPECIFICATION_REGISTER.md` Amendments section
Related ADR: `docs/adr/0047-alpha-edge-regime-evidence-governance.md`

## Purpose

Record the operator clarification that governs Alpha-Edge S1-Sx research after the S1-W1-S1 / S2-W0-S1 / S4-W0-S1 dispatch.

This amendment prevents three misinterpretations:

1. Bull-market data is banned.
2. Bybit market APIs provide predictive trend judgment.
3. News / X / Reddit / market commentary can become primary strategy evidence.

All three interpretations are wrong.

## Decision

1. **Bull-market data remains allowed.** It must be labeled when it is the base sample or dominates a result.
2. **S4 is downgraded to a global regime/falsification overlay.** It is not a standalone bull-data alpha proof track.
3. **S1-Sx promotion evidence must be math-primary.** Quantitative gates, leak-free backtests, breadth, survivorship, freshness, and execution realism are the proof surface.
4. **Bybit API is raw market-state input.** Trend/state classification must be computed locally from Bybit data and project math rules.
5. **External narrative evidence is secondary.** Future news / X / Reddit agents may annotate context and event risk, but cannot override quantitative gates or become the main signal.

## Required Cascade

- ADR-0047 accepted and linked from active governance records.
- README, CLAUDE, `.codex/MEMORY.md`, `CONTEXT.md`, and Bybit API reference updated with the short rule.
- Alpha-Edge engineering packet must include:
  - alpha-history storage,
  - automated breadth-ladder,
  - local trend/state classifier,
  - global regime robustness gates,
  - narrative-side-evidence boundaries.
- TODO must point to the new SSOT documents and keep only the active next actions.

## Non-Goals

- No runtime deploy.
- No database write.
- No order, auth, live, or secret mutation.
- No relaxation of Stage 0R / Demo / LiveDemo / true-live gates.
- No new permission for external narrative feeds to influence trading directly.

## Acceptance

- Each future S1-Sx candidate verdict includes regime, breadth, freshness, survivorship, and execution-realism matrices.
- Bull-heavy or stale-year-dominated metrics are labeled in the report and cannot silently drive aggregate verdicts.
- Bull-only positive results are classified as `regime-bet / learning-only` unless non-bull slices independently pass.
- External narrative feeds are stored and reported as corroborating context only.

## References

- ADR-0047: `docs/adr/0047-alpha-edge-regime-evidence-governance.md`
- PM decision report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--alpha_edge_operator_decisions.md`
- Alpha-Edge plan: `docs/execution_plan/2026-05-31--alpha_edge_research_execution_plan.md`

## Sign-off

| Role | Date | Status |
|---|---:|---|
| Operator | 2026-05-31 | ✅ Approved clarification |
| PM | 2026-05-31 | ✅ Amendment recorded |
| QC | 2026-05-31 | ✅ Quant gate recommendations incorporated |
| MIT | 2026-05-31 | ✅ Data/storage findings incorporated |
| PA | 2026-05-31 | ✅ Engineering arrangement incorporated |
