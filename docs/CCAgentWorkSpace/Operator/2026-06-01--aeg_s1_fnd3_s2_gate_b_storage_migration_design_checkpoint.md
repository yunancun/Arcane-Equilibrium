# Operator Brief - AEG-S1 FND-3 / S2 Gate-B / Storage Migration-Design Checkpoint

Date: 2026-06-01
Mode: docs/design/read-only. No DB/runtime/backfill/scoring action was taken.

## What Is Complete

- FND-3 side-evidence artifact contract is complete.
- S2 Gate-B PreLaunch phase-transition probe plan is complete.
- MIT storage migration-design packet is complete.
- PM chose `V125__aeg_alpha_history_storage.sql` as the design reservation to
  avoid V116/V117/V118-124 planning collisions.

## Current Decisions

- `side_evidence.json` is optional, secondary-only, and cannot affect promotion
  gates or override mathematical failures.
- Gate-B requires a real 24h isolated public probe; no real transition means
  inconclusive, not pass.
- Production listing collector work remains blocked until capture-only symbols
  are separated from trading symbols and reviewed.
- AEG storage should use `research.alpha_*` tables plus
  `market.klines` 1095d retention/provenance ledger after future execution
  approval.

## Still Not Authorized

- V125 SQL file creation or migration apply.
- Timescale retention mutation.
- DB provenance ledger or research-history table creation.
- Bybit historical writer.
- Endpoint ingestion/backfill.
- Gate-B 24h probe run.
- Collector runtime.
- Alpha scoring/promotion verdict.

## Recommended Next Work

1. E2/E4/MIT review V125 design and dry-run checklist.
2. If approved, open a separate standalone Gate-B probe implementation/run
   scope: public REST/WS only, artifact-only, no DB writes.
3. Keep FND-3 side evidence as schema/reporting contract until the
   alpha-history runner exists.
