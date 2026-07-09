# REF-21 V1.2 Closure Revision PM Report

**Date:** 2026-05-06  
**Owner:** PM  
**Status:** Landed as active governance baseline  
**Primary doc:** `docs/execution_plan/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_2.md`  
**GUI companion:** `docs/execution_plan/2026-05-06--ref21_gui_ux_spec_v1.md`

## Decision

The V1.1 adversarial closure audit is accepted. The deployed provisional
`/api/v1/replay/full-chain/prepare` endpoint is a governance bypass unless it is
disabled by default and treated only as an R1 hardening tool.

## Immediate Code Action

The endpoint is now guarded by `OPENCLAW_REPLAY_PREPARE_ENABLED=0` by default.
When disabled, it returns `replay_full_chain_prepare_disabled` before market
data, scanner, strategy, or risk calls are made. Tests cover disabled and
enabled paths.

## V1.2 Additions

- B1 adds replay subprocess mainnet-env and `authorization.json` prohibitions.
- B3 replaces byte-equal singleton snapshots with symbol audit, write
  confinement, and forbidden write roots.
- B6/B7 reserve V057 replay evidence tier migration and concrete promotion
  gates.
- B4/B15 reserve V059 edge snapshots and V058 symbol-universe snapshots.
- B8 adds maker clamp defaults and deprecated-strategy contamination exclusion.
- B12 adds numeric timeout/rollback criteria.
- B13 adds DreamEngine/MLDE applier wiring as a prerequisite B-gate.
- B14 adds missing 16-principle acceptance for survival, cost edge, L0 fallback,
  and portfolio risk.
- GUI/UX is split into a companion spec for A3 + TW review.

## Status

R2/R3 remain blocked. R1 is limited to hardening the disabled dataset endpoint.
