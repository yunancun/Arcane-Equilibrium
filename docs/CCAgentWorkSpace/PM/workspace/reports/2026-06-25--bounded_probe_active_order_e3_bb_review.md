# PM Report: Bounded Probe Active Order E3/BB Review

Date: 2026-06-25
Status: DONE_WITH_CONCERNS
Source HEAD: `cf46e0614aba768db7c2c67a6816c9101e1fdb3b`
Active blocker: `P0-BOUNDED-PROBE-ACTIVE-ORDER-WIRING-E3-BB-REVIEW-DEMO-ONLY`

## Decision

E3 and BB both returned PASS with no blocking findings for the current source-only active bounded Demo order envelope.

This does not grant runtime probe/order authority. The runtime writer remains adapter-disabled, the hot path remains preview-only, no Bybit call was made, and no order/cancel/modify path was exercised.

## Evidence

- E3 PASS: risk NORMAL gates, Rust admission, operator authorization checks, Decision Lease id propagation, lineage hooks, and Cost Gate `NONE` checks are preserved.
- E3 PASS: production runtime admission still defaults adapter-disabled in `rust/openclaw_engine/src/demo_learning_lane_writer.rs`; `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` still records preview only in the hot path.
- BB PASS: no blocking exchange-facing source issue in the dormant limit/PostOnly active-order envelope. Official reference checked: Bybit V5 Place Order, <https://bybit-exchange.github.io/docs/v5/order/create-order>.

## Runtime Caveats Before Any Enablement

- Pin the approved bounded Demo notional cap; the source default is `10 USDT`, but future runtime review should not allow caller-expanded caps.
- Enforce Bybit-compatible `orderLinkId` length, charset, and uniqueness before any order submission.
- Require a positive limit price sourced from reviewed near-touch placement or add explicit draft validation.
- Make maker timeout/cancel-by-`orderLinkId` reviewed and explicit before runtime use.
- Confirm fills, fees, slippage, order state, and matched controls remain reconstructable through context/order-link/order/WS state.

## Boundary

No runtime sync, no `/tmp` runtime artifact, no latest/plan/admission/ledger mutation, no PG read/write, no Bybit API call, no service/env/crontab mutation, no Rust writer enablement, no global Cost Gate lowering, no live/mainnet action, no active probe/order authority, and no promotion proof.

## Next Safe Action

Open a source/runtime authorization hardening checkpoint before any adapter enablement or Demo order authority. That checkpoint should address the caveats above and then go through the runtime/exchange chain before any order path can be activated.
