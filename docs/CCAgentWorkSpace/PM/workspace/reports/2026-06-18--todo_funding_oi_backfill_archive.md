# TODO v175 Funding/OI Backfill Completed-Row Archive

Date: 2026-06-18
Role: PM
Scope: TODO active-queue hygiene backed by read-only DB verification

## Decision

Archive `P0-EDGE-1-CAND-FUNDING-OI-BACKFILL` from `TODO.md` §5.

The backfill is completed and still summarized in `TODO.md` §2 as AEG foundation state. The §5 row no longer carried an active owner/action; it mainly preserved usage caveats.

## Read-Only Recheck

Linux production DB, read-only:

- `research.alpha_funding_rates_history`
  - rows: `46539`
  - distinct run_id: `1`
  - run_id: `18b3c2f8-6125-42a8-a42c-cfcc8aec9406`
  - span: `2024-06-03 02:00:00+02` to `2026-06-02 22:00:00+02`
  - NULL funding values: `0`
- `research.alpha_open_interest_history`
  - rows: `348153`
  - distinct run_id: `1`
  - run_id: `18b3c2f8-6125-42a8-a42c-cfcc8aec9406`
  - span: `2024-06-03 01:00:00+02` to `2026-06-03 01:00:00+02`
  - NULL OI values: `0`

## Preserved Caveat

The history tables are run-versioned: `run_id` is part of the primary key. Re-running apply will append a new run instead of idempotently replacing the old one.

Consumers must pin a run_id or deliberately select the latest run. Future cron/refresh work should be opened as a new active row and include clear-old-run/wrapper/rate-limit design rather than reusing this completed row.

## Boundary

Read-only DB verification plus docs/TODO hygiene only.

No CI, deploy, rebuild, restart, production source mutation, runtime mutation, DB write, auth/risk/order/trading mutation.
