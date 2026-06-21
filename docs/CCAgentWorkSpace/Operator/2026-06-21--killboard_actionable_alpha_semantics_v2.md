# Operator Note — Killboard Actionable-Alpha Semantics v2

Date: 2026-06-21  
Status: source checkpoint only; no runtime change performed

## What Changed

Runtime killboard `actionable_alpha_found` now means there is at least one
profitability-scorecard `promotion_ready` row.

Raw `READY_FOR_AEG_CHAIN` is still visible, but under clearer names:

- `ready_for_aeg_chain`
- `aeg_candidate_artifact_found`

## Why

An AEG candidate artifact is not the same as promotion-ready alpha. This matters
for Polymarket, where IC/replay artifacts can exist before dated replay history
and execution realism are strong enough.

## Boundaries

This checkpoint did not:

- sync runtime source
- refresh runtime artifacts
- install or edit crontab
- write PG
- call Bybit private/signed APIs
- restart services
- grant order authority
- create promotion proof

## Next Step

Runtime still needs operator-approved source sync and alpha-discovery rerun
before the live artifact reflects schema `alpha_discovery_runtime_killboard_v2`.
