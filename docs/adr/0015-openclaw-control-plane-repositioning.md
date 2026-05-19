# ADR 0015: OpenClaw Is Control Plane and Gateway, Not Trading Conductor

Date: 2026-05-09
Status: Accepted

## Context

The project was renamed to `玄衡 · Arcane Equilibrium`, while OpenClaw remains
the service-family name for the Control Console, Gateway, API aggregation, and
operator communication surfaces.

## Decision

OpenClaw is not the trading brain, not a second GUI, and not a hot-path trading
conductor. The canonical trading authority remains Rust `openclaw_engine`.
The canonical operator GUI remains the existing FastAPI OpenClaw Control
Console at `trade-core:8000/console`.

External OpenClaw Gateway may relay briefs, diagnostics, proposals, approvals,
and channel events, but any trading side effect must re-enter TradeBot
governance and Rust execution authority.

The legacy `openclaw_core` modules that modeled a parallel cognition/trading
brain are permanent sunset candidates. They may be removed after source
reference audit and tests prove the active Rust execution path no longer uses
them.

## Consequences

- No separate OpenClaw trading GUI is introduced.
- OpenClaw Gateway does not hold Bybit credentials.
- Gateway outage must degrade communication only, not stop the runtime engine.
- Proposal and approval routes remain relay/audit surfaces, not order authority.
- W-AUDIT-5 may schedule removal of the nine legacy `openclaw_core` modules;
  that cleanup is structural only and does not change trading authority.

## Closure Addendum — 2026-05-19 (P2-DEAD-RUST-CLEANUP-1)

The «nine legacy modules» count in §Consequences was a 2026-05-09 estimate. The
W-AUDIT-5 / WP-07 audit (2026-05-16 PA fix-plan) refined the actual production
sunset set to **seven** modules after grep verifying 0 production caller:

1. `attention.rs` (424 LOC)
2. `attribution.rs` (267 LOC)
3. `cognitive.rs` (524 LOC)
4. `dream.rs` (936 LOC)
5. `message_bus.rs` (296 LOC)
6. `order_match.rs` (308 LOC)
7. `opportunity.rs` (861 LOC)

Total: 3616 LOC retired in commit `449f628b` (2026-05-18 cleanup sprint).

The 9 vs 7 discrepancy is reconciled as follows:
- The ADR-0015 estimate was made before granular grep audit; the WP-07 audit was
  empirically the SoT.
- 2 additional `openclaw_core::risk/{checks,config}.rs` were already
  refactored out earlier in commit `2007b677` (ARCH-RC1 1C-1 Batch 0-4) as
  separate concerns (risk config migration, not cognition/brain sunset). Those
  2 are not the «missing 2» — they belong to a different refactor lineage.
- No further modules in current `rust/openclaw_core/src/` meet the
  «parallel cognition/trading brain» criterion. The retirement set is closed.

ADR-0015 §Consequences «nine» wording is preserved as historical record. This
addendum is the authoritative closure note.
