# Operator Note — Polymarket Promotion-Ready Replay-History Gate

Date: 2026-06-21  
Status: source checkpoint only; no runtime change performed

## What Changed

Polymarket IC candidates are no longer counted as `promotion_ready` just because
they are `READY_FOR_AEG_CHAIN`.

They now need all three before promotion readiness:

- candidate replay built
- dated replay history ready for AEG recheck
- replay-history execution realism status `PASS`

## Why

The system should learn from Polymarket artifacts, but it should not confuse a
statistical IC candidate with deployable alpha. This keeps the candidate visible
for AEG review while preventing under-verified evidence from appearing as
promotion-ready.

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
before the live artifact reflects this stricter scorecard. After that, the
Polymarket lane needs more dated replay history and real execution-realism
evidence before any promotion decision.
