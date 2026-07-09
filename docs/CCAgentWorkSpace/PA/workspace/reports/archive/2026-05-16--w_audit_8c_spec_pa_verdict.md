# PA Verdict -- W-AUDIT-8c Liquidation Cluster Strategy Spec v0.1

Date: 2026-05-16
Author: PA(default)
Scope: Design/spec only for W-AUDIT-8c A4-B Liquidation Cluster Reaction. No runtime implementation, no WebSocket subscription, no risk config, no database schema, no shared memory/TODO/CLAUDE edits.

## Verdict

**APPROVE FOR DESIGN ONLY / BLOCKED FOR IMPLEMENTATION.**

The v0.1 spec is architecturally consistent with ARCH-04 / ADR-0021 because it consumes the existing `Strategy::on_tick(ctx, surface)` interface and declares `AlphaSourceTag::LiquidationCascade` through AlphaSurface Tier 3. It is not authorized for E1 runtime work until W-AUDIT-8a C1 returns a final BB + MIT signed PASS for `allLiquidation.{symbol}`.

## Required Decision

PA freezes the primary hypothesis as **post-cascade short-term mean reversion**.

Reasoning:

- Liquidation clusters are forced-flow events. The cleaner design-time hypothesis is that price impact mean-reverts after the burst decelerates, not that the strategy should add leverage into the active cascade.
- The hypothesis can be implemented with explicit fail-closed event guards: fresh pulse required, side dominance required, quiet window preregistered, and no TA fallback.
- A momentum-continuation branch is allowed only as a preregistered sensitivity. It cannot make v0.1 eligible for Stage 1 Demo without a separate spec update.

## Evidence Read

Key sources reviewed:

- `AGENTS.md`, `CLAUDE.md`, `TODO.md`, `.codex/MEMORY.md`
- `.codex/agents/PA.md`, `.claude/agents/PA.md`, PA profile/memory/latest reports
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--w_audit_8a_phase_c0_liquidation_inventory.md`
- `docs/execution_plan/2026-05-15--w_audit_8a_c1_liquidation_topic_probe_plan.md`
- `docs/execution_plan/2026-05-16--w_audit_8a_c1_v2_resilient_proof.md`
- `docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md`
- `docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`
- `docs/adr/0021-alpha-source-architecture-upgrade.md`
- `docs/governance_dev/SPECIFICATION_REGISTER.md`
- `rust/openclaw_core/src/alpha_surface.rs`
- `rust/openclaw_engine/src/strategies/mod.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
- `rust/openclaw_engine/src/replay/strategy_adapter.rs`

## Architecture Findings

Facts:

- `AlphaSourceTag::LiquidationCascade` and `AlphaSurface.liquidation_pulse` already exist.
- `Strategy::on_tick(ctx, surface)` is the active interface.
- C0 added replay coverage proving an empty AlphaSurface keeps a future `LiquidationCascade` consumer fail-closed.
- `market.liquidations` exists but currently has 0 rows.
- Production topic builders are guarded against liquidation and poison topics.
- C1 v2 proof is in flight, not passed.

Inference:

- The correct next W-AUDIT-8c artifact is a gated strategy spec, not source implementation.
- The strategy must be event-triggered through a post-C1 in-memory pulse provider; strategy-side PG or REST polling would be the wrong architecture boundary.

Assumption:

- BB/MIT will sign the exact Buy/Sell side mapping before any strategy direction logic is enabled. Without that sign-off, the spec requires no-action.

## Replay Applicability

Replay cannot currently validate edge for this strategy because the required real liquidation data is absent and C1 is not passed. Replay can only validate fail-closed behavior before C1; that coverage already exists in `replay_empty_surface_keeps_liquidation_cascade_fail_closed`.

The spec therefore sets Stage 0R acceptance as a future replay packet after C1 PASS, real `market.liquidations` rows, and MIT schema sign-off. It mirrors W-AUDIT-8b by requiring explicit `K_total`, PSR/DSR, CSCV PBO, block bootstrap, sample floors, plateau checks, and fail-closed `eligible_for_demo_canary=false` when data or prerequisites are missing.

## Boundary Check

No edits were made to:

- shared PA memory
- `TODO.md`
- `CLAUDE.md`
- risk configs
- Rust runtime/source
- production subscriptions
- database schema

No `git add`, `git commit`, or `git push` was run.

## 16 Principles / Hard Boundary Review

Relevant result: compliant for design phase.

- Single write entry: no execution/write path touched.
- Read/write separation: spec is read-only; future replay tooling must stay read-only.
- Strategy cannot bypass risk: any future action remains a normal `StrategyAction::Open` through governance.
- Survival over profit: active-cascade chasing is not the primary hypothesis; missing/stale data fails closed.
- Failure defaults conservative: C1 missing, stale pulse, mixed side, ambiguous side mapping, or low sample power all emit no action or `eligible_for_demo_canary=false`.
- Explainability: future reports must include C1 proof id, side mapping, cluster construction, K_total, and replay acceptance reasons.
- Cognitive honesty: fact/inference/assumption are separated above.

Hard boundaries touched: zero. No live auth, Decision Lease, `max_retries`, `execution_authority`, or runtime mode semantics are changed.

## E1 Dispatch Recommendation

Do not dispatch runtime E1 yet.

After C1 PASS + BB/MIT sign-off, dispatch in this order:

1. E1-C1-REVIVE: parser/writer revival for `allLiquidation.{symbol}` plus in-memory `LiquidationPulseProvider`.
2. E1-8C-STAGE0R: read-only replay query/report packet for `liquidation_cluster_reaction`.
3. E2 + BB + MIT: adversarial review of topic safety, side semantics, as-of joins, DSR/PBO, and fail-closed gates.
4. Only after green Stage 0R: E1 strategy skeleton and Stage 1 Demo request packet.

## Changed Files

- `docs/execution_plan/2026-05-16--w_audit_8c_liquidation_cluster_strategy_spec.md`
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8c_spec_pa_verdict.md`

## Blockers

- W-AUDIT-8a C1 v2 proof is still in flight; no final PASS exists.
- MIT schema review for `allLiquidation.{symbol}` payload to `market.liquidations` is not signed.
- `market.liquidations` has no usable replay sample yet.
- Stage 0R edge replay cannot run until the above blockers clear.

