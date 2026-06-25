# PM Report: Bounded Probe Active Runtime Authorization E3/BB Review

Date: 2026-06-25
Status: DONE_WITH_CONCERNS
Active blocker: `P0-BOUNDED-PROBE-ACTIVE-RUNTIME-AUTHORIZATION-E3-BB-REVIEW-DEMO-ONLY`

## Decision

Closed the runtime-authorization source review checkpoint without granting authority. E3 and BB found no immediate source-level bypass or Bybit request-shape blocker, but both reviews leave enablement blocked until the actual active caller and restart/reconstruction concerns are closed.

## Review Results

- E3: `DONE_WITH_CONCERNS`
  - Current hot path is still no-order: reject handling records bounded-probe placement preview only.
  - Runtime writer evaluation still uses `bounded_probe_adapter_enabled=false`.
  - Active order draft construction is fail-closed on Demo/LiveDemo mode, cap `<=10 USDT`, risk `NORMAL`, Cost Gate `NONE`, Decision Lease, positive prices, positive qty/notional, and Bybit-safe `orderLinkId`.
  - Generic dispatch/cancel/fill surfaces preserve `order_link_id`, context, maker timeout, reference price/source, fee/slippage/liquidity/latency, and Decision Lease release.
- BB: `DONE_WITH_CONCERNS`
  - No source-level blocker found for a future Bybit V5 demo linear PostOnly limit request shape.
  - Cancel-by-`orderLinkId` and WS-state-based reject/fill reconstruction surfaces exist.
  - This is not order authority and must not be treated as bounded-probe proof.

## Remaining Enablement Blockers

- Actual `adapter_enabled=true` bounded-probe caller is not wired or reviewed.
- `exchange_seq` is in-memory; restart-safe `orderLinkId` uniqueness/dedupe is not proven.
- Bounded-probe cap is checked before common exchange rounding; post-round cap enforcement needs a bounded-probe-specific contract.
- Same-process cancel/fill races are handled, but post-restart pending-order reconciliation for created-but-unobserved bounded probes is not proven.
- Generic fill/fee/slippage persistence exists, but bounded-probe candidate-matched outcome proof and matched-control review hook remain separate work.

## Boundary

Source/docs review only. No runtime sync, no `/tmp` runtime artifact, no latest/plan/admission/ledger mutation, no PG read/write, no Bybit API call, no order/cancel/modify, no service/env/crontab mutation, no Rust writer enablement, no global Cost Gate lowering, no live/mainnet action, no active probe/order authority, and no promotion proof.

## Verification

- PM source inspection of active order, dispatch, event-consumer pending/cancel/fill, and local Bybit reference surfaces.
- E3 source-only review: `DONE_WITH_CONCERNS`.
- BB source/reference-only review: `DONE_WITH_CONCERNS`.
- `git diff --check` for docs-only checkpoint.

## Next Safe Action

Open a source-only blocker for the active caller contract: require actual call site review, restart-safe/deduped `orderLinkId`, post-round cap enforcement, pending-order restart reconciliation, and bounded-probe candidate-matched outcome reconstruction before any adapter enablement or order authority.
