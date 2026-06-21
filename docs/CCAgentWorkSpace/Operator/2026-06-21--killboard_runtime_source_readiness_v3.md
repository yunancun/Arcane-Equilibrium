# Operator Note — Killboard Runtime Source-Readiness Visibility v3

Date: 2026-06-21  
Status: source checkpoint only; no runtime change performed

## What Changed

Future alpha-discovery runtime artifacts will include source checkout readiness
at the top level.

New schema:

```text
alpha_discovery_runtime_killboard_v3
```

New key facts:

- whether runtime source is activation-ready
- source activation status
- git checkout status
- expected-head match status

## Why

The current `trade-core` artifact is misleading partly because runtime source is
old/dirty. This patch makes that condition visible inside the alpha artifact
itself once runtime is synced.

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
rerun before the live artifact reflects schema v3.
