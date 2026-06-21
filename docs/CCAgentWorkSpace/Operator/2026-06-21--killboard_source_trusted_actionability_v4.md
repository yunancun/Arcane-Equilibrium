# Operator Note — Killboard Source-Trusted Actionability v4

Date: 2026-06-21  
Status: source checkpoint only; no runtime change performed

## What Changed

Future alpha killboards will not set top-level `actionable_alpha_found=true`
unless source is also trusted.

Raw candidates remain visible:

- `promotion_ready_count`
- `promotion_ready_candidate_found`

But actual top-level actionability now requires:

- promotion-ready candidate exists
- runtime source is activation-ready

The same source-trust rule applies to `actionable_probe_found`.

## Why

Current runtime source is still old/dirty. We should not call any alpha or probe
"actionable" when the artifact itself is built from a source checkout that is
not activation-ready.

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

Runtime still needs operator-approved source reconcile/sync and alpha-discovery
rerun before the live artifact reflects schema v4.
