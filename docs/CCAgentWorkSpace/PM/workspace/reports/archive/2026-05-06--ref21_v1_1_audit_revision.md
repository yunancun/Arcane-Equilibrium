# REF-21 V1.1 Audit Revision PM Report

**Date:** 2026-05-06  
**Owner:** PM  
**Status:** Landed as revised governance baseline  
**Primary doc:** `docs/execution_plan/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_1.md`

## Decision

The 8-agent audit is accepted as materially valid. REF-21 V1 is demoted to a
historical direction baseline and must not authorize R2/R3 implementation.
REF-21 V1.1 is now the active plan.

## Key Corrections

- Reframed replay from "equivalent 7 days of live data" to a bounded
  in-sample replay sandbox unless OOS/freeze criteria pass.
- Reaffirmed REF-19 dedicated subprocess model; R3 extends the existing
  `replay_runner` binary instead of embedding production singletons.
- Added B1-B12 hard gates for forbidden dispatch, state pollution, edge
  snapshots, OOS, tier promotion, maker-fill clamp, auth/rate limits, Decision
  Lease canary compatibility, Bybit data reality, failure modes, GUI safety,
  and manifest/idempotency.
- Marked commit `18efb965` `/api/v1/replay/full-chain/prepare` as provisional
  dataset-only foundation, not full REF-21 acceptance.

## Next Review Chain

1. CC + E3: B1/B2/B3/B4/B8/B9/B12.
2. MIT: edge snapshot schema and replay-learning gates.
3. QC: OOS semantics and maker-fill clamp.
4. BB: Bybit data/rate/IP policy.
5. FA: quantified acceptance criteria.

R2/R3 implementation remains blocked until this chain returns at least
Conditional/B or the operator explicitly overrides a gate.
