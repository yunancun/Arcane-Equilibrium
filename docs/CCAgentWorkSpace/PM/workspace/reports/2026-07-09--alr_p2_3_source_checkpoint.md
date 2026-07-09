# PM State/Effect - ALR P2-3 Source Checkpoint

Date: 2026-07-09
State: `ACTIVE_E4_ISOLATED_PENDING`
Mode: `ROLE_FALLBACK_SINGLE_SESSION`

## Effect

- Added the post-persist Rust scanner wake-up, a bounded Python LISTEN consumer,
  process and database locks, source-only systemd user-unit template, and
  no-credential least-privilege role contract.
- The listener reads only `trading.scanner_snapshots` and appends only
  `learning.alr_*` evidence. It exposes false exchange/trading/proof/serving/
  promotion authority counters.
- No database role, credential, unit, engine restart, service, scheduler,
  exchange contact, order action, Decision Lease, Cost Gate, `_latest`, serving,
  promotion, proof, or retention action has occurred.

## Remaining Acceptance

Run the committed isolated PostgreSQL probe on Linux after source alignment.
Then complete E4/QA and request a fresh exact P2-3 prestart E3/BB review before
any production role, credential, engine, or user-service mutation.
