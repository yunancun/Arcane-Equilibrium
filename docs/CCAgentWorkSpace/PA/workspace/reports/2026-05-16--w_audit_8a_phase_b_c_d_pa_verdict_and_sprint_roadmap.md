# PA Verdict + Sprint Roadmap: W-AUDIT-8a Phase B/C/D Alpha Surface Infrastructure

Date: 2026-05-16  
Role: PA(default)  
Workgroup: A-3 / W-AUDIT-8a  
Repo root: `/Users/ncyu/Projects/TradeBot/srv`  
Report status: PA design verdict, docs-only  
Implementation status: Not authorized by this report

## Verdict

PA verdict: APPROVED-CONDITIONAL for planning; IMPLEMENTATION-NOT-AUTHORIZED.

The Phase B/C/D infrastructure roadmap is coherent if PM treats it as four complete alpha-source loops rather than a set of isolated fields in `AlphaSurface`.

Required invariant:

```text
schema/storage contract -> writer/producer -> AlphaSurface consumer -> healthcheck -> Stage 0R evidence -> Demo micro-canary
```

Phase B is not blank. Current source already contains the major Tier 2 producer/writer/slot/dispatch work. The remaining Phase B risk is consumer completeness and evidence quality, especially funding-panel consumption and OI unavailable-reason reporting.

Phase C is blocked only for liquidation production revival. Orderflow and spread microstructure can proceed as a separate design/implementation lane, provided it does not rely on unproven liquidation topics.

Phase D should proceed only through normalized providers for event alerts, regime tag, and sentiment panel. Raw news/scout artifacts should not be handed to strategies as unconstrained alpha authority.

## Evidence Read

Governance and role files read:

- `AGENTS.md`
- `CLAUDE.md`
- `TODO.md`
- `.codex/MEMORY.md`
- `.codex/agents/PM.md`
- `.codex/AGENT_DISPATCH_PROTOCOL.md`
- `.codex/SUBAGENT_EXECUTION_RULES.md`
- `.codex/agents/PA.md`
- `.claude/agents/PA.md`
- `docs/CCAgentWorkSpace/PA/profile.md`
- `docs/CCAgentWorkSpace/PA/memory.md`

Execution and architecture references read:

- `docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`
- `docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md`
- `docs/execution_plan/2026-05-15--w_audit_8a_c1_liquidation_topic_probe_plan.md`
- `docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md`
- `docs/adr/0021-alpha-source-architecture-upgrade.md`
- `docs/architecture/2026-05-10--ARCH-04-graduated-canary-5-stage.md`
- `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`

Current source and commits inspected:

- `0b76a4db`: funding curve aggregator and V085 writer.
- `3d0ea347`: OI delta aggregator, V087, BTC lead-lag.
- `ddf0cebe`: WS main-loop integration, V092, healthcheck `[66]`.
- `rust/openclaw_core/src/alpha_surface.rs`
- `rust/openclaw_engine/src/panel_aggregator/`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
- `rust/openclaw_engine/src/strategies/bb_breakout/mod.rs`
- `helper_scripts/db/passive_wait_healthcheck/checks_derived_ml_hygiene.py`
- `helper_scripts/db/passive_wait_healthcheck/runner.py`

## Current-State Findings

1. Tier 2 schema and writer are materially landed.

   V085/V087/V092 and the Rust `panel_aggregator` path provide the current funding/OI panel substrate. This report does not recommend relanding those migrations or changing panel schemas.

2. Tier 2 consumer readiness is mixed.

   OI has a concrete `bb_breakout` consumer path with fail-closed semantics. Funding has dispatch availability and the W-AUDIT-8b Stage 0R plan, but no production promotion-ready strategy consumer.

3. Healthcheck `[66]` is necessary but not sufficient.

   It proves panel table freshness. It does not prove that a strategy actually received and used a fresh panel, nor does it prove that missing/stale branches were reported correctly.

4. Liquidation remains governed by C1.

   The existing `market.liquidations` table is not authorization to revive production subscriptions. No strategy should see a synthetic or mock `LiquidationPulse`.

5. Tier 4 must be normalized.

   Existing event/news/regime schema candidates are useful, but strategies need normalized `EventAlert`, `RegimeTag`, and `SentimentPanel` providers with TTL, source, freshness, and skip reporting.

## Sprint Roadmap

| Sprint | PA allocation | Dispatch intent | Required exit evidence |
| --- | --- | --- | --- |
| N+3 | Phase B closeout + Phase C1 decision + Phase C2/C3 design | Finish funding/OI consumer evidence; audit `[66]` and strategy unavailable reasons; review C1 proof; lock microstructure schema/writer/consumer/healthcheck plan. | Funding/OI consumer report, `[66]` status, OI unavailable breakdown, C1 PASS/FAIL packet, microstructure design accepted. |
| N+4 | Phase C implementation + Phase D contract review | Implement orderflow/spread only after MIT approval; wire optional `AlphaSurface.orderflow`; add microstructure healthcheck; continue W-AUDIT-8b only if Stage 0R is green. | Fresh microstructure panel, finite feature checks, strategy skip reasons, no promotion without Stage 0R, Tier 4 contract approved. |
| N+5 | Phase D implementation + canary preparation | Implement EventAlert/RegimeTag/SentimentPanel providers and healthchecks; prepare Demo micro-canary only after replay preflight passes. | Tier 4 freshness and correctness checks, consumer suppression/skip reports, Stage 0R replay packet, Demo packet only if green. |

## Required Tier Coverage

| Tier | Schema | Writer | Consumer | Healthcheck |
| --- | --- | --- | --- | --- |
| Tier 1 TA/OHLCV | Existing market/indicator storage | Existing writers | Existing strategy paths and `tier1_only` fallback | Existing data/indicator freshness gates |
| Tier 2 funding/OI | V085/V087/V092 landed | `panel_aggregator` funding/OI producers | Dispatch injection; OI in `bb_breakout`; funding via W-AUDIT-8b Stage 0R first | `[66]` plus future consumer-path report |
| Tier 3 orderflow/spread/liquidation | Future microstructure panel; existing `market.liquidations` only after C1 | Future WS-derived writer; liquidation writer only after C1 PASS | Optional `AlphaSurface` fields, fail-closed | New freshness/finite/coverage/parser checks |
| Tier 4 event/regime/sentiment | Existing raw schema candidates; future panel only if justified | Future normalized providers | Optional/fail-closed consumers with suppress/skip reporting | New TTL, freshness, unknown-ratio, sample/cost checks |

## PA Constraints for Next Dispatch

- Do not assign an implementation owner to "Phase C" as a single blob. Split liquidation C1 from orderflow/spread C2/C3.
- Do not allow funding/OI reports to claim readiness from DB freshness alone.
- Do not use paper mode as promotion evidence.
- Do not let A4-C diagnostic artifacts become hidden AlphaSurface authority.
- Do not revive `allLiquidation*` or related production topics without the C1 proof report and PM/MIT/BB approval.
- Do not create a new Tier 4 strategy consumer until the provider defines TTL, source, freshness, and skip behavior.

## Assumptions

1. Local `main` aligned with `origin/main` at `abaa4de7` before this PA drafting session.
2. The unrelated modified file `.claude/agents/E3.md` existed before PA edits and was not touched; PM later committed that C-1 guard separately as `197ca14d`.
3. V085/V087/V092 are treated as landed for planning because TODO/memory/current source point to Phase B partial land; this report did not query production DB state.
4. Passive health runner `[66]` is the current authoritative panel healthcheck unless OPS separately requires cron/systemd installation.
5. W-AUDIT-8b remains Stage 0R/read-only until its own gate evidence is green.
6. Final `git status` also showed sibling untracked reports/plans outside this dispatch, including Phase 1b, W-AUDIT-8b, W-AUDIT-8c, and MIT AC-19 docs. They were not edited by this PA session.

## Files Changed By This PA Session

- `docs/execution_plan/2026-05-16--w_audit_8a_phase_b_c_d_infrastructure_spec.md`
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8a_phase_b_c_d_pa_verdict_and_sprint_roadmap.md`

## Deliverable

Created planning spec:

- `docs/execution_plan/2026-05-16--w_audit_8a_phase_b_c_d_infrastructure_spec.md`

PA sign-off:

```text
PA DESIGN DONE: W-AUDIT-8a Phase B/C/D infrastructure spec v0.1 is ready for PM review.
Implementation remains blocked until PM dispatches scoped E1/E2/E4 tasks under the sprint map above.
```
