# Profit Evidence Quality Proof-Exclusion Guard

- Generated at: `2026-06-24T02:18:52Z`
- Active blocker: `P0-PROFIT-EVIDENCE-QUALITY`
- Status: `DONE_WITH_CONCERNS`
- Branch: `main`
- Source head before change: `e0b7d54444a35218d3ab13aa1c3840e5db8b2ed4`

## Operator Summary

This round did not repeat the exchange/PG audit and did not mutate runtime state. It implemented the source-only proof-exclusion guard requested by the prior evidence-quality audit:

- Unattributed or lineage-incomplete fill-backed rows are now excluded from bounded-probe proof, Cost Gate proof, promotion proof, and risk-adjusted net PnL proof.
- Bounded result review now separates raw, proof-eligible, and proof-excluded outcomes.
- Runtime/status summaries no longer treat proof-excluded outcomes as successful probe outcomes or as realized-failure samples for auto-disable.
- Alpha downstream summaries propagate proof-exclusion fields and fail closed when proof exclusion is present.

## Operator Action Still Required

The larger `P0-PROFIT-EVIDENCE-QUALITY` blocker is not fully cleared. The prior checkpoint still requires explicit operator authorization before any of the following:

- Bybit order cancel/modify/close.
- PG reconciliation/backfill/write.
- Runtime/service restart or env mutation.
- Cron edit.
- Rust writer enablement.
- Probe/order/live authority.

Until the open-order overhang and SOL/ETH fill-lineage drift are resolved or explicitly quarantined, `P0-PROFIT-CANDIDATE-SELECTION` remains blocked.

## Verification

- Python compile passed for changed source files.
- Focused bounded/result/status/runtime/scorecard tests: `112 passed`.
- Alpha discovery/worklist tests: `90 passed`.
- `git diff --check` passed.

## Boundary

No Cost Gate lowering, no live promotion, no probe/order authority, no Bybit private call, no PG action, no service/cron/runtime mutation, and no order cancel/modify/close occurred in this round.
