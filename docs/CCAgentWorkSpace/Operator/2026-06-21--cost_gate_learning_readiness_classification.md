# Operator Note: Cost-Gate Learning Readiness Classification

Date: 2026-06-21

## What Changed

Alpha-discovery no longer treats a cost-gate learning plan as an actionable probe just because the plan says `OPERATOR_REVIEW`.

The cost-gate lane now requires actual runtime learning evidence:

- No ledger -> enable/sync runtime writer and cron first.
- Admission rows only -> refresh blocked-signal outcomes first.
- Too few blocked outcomes -> keep accumulating.
- Reviewed outcomes fail thresholds -> keep Cost Gate blocked.
- Reviewed outcomes clear thresholds -> operator review before any demo probe authority.

## Practical Read

If an old runtime alpha artifact still says `ACTIONABLE_PROBE_READY`, check whether it was generated before v318. Under v318 source, the current observed runtime state with no `probe_ledger.jsonl` should not count as `actionable_probe_found=true`.

## Boundary

This is status classification only. It does not install cron, enable the writer, lower Cost Gate, grant order authority, place or cancel orders, call Bybit private APIs, write PG, mutate runtime config, or create promotion proof.
