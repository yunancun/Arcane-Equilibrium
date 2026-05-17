# V095 Linux PG Dry-Run Result

**Date**: 2026-05-17
**Role**: PM(default)
**Scope**: W-AUDIT-8c V095 Linux PostgreSQL empirical dry-run only.

## Verdict

**PASS.**

V095 was tested on `trade-core` against the real `trading_ai` TimescaleDB with
two transaction-wrapped dry-run rounds. No production schema or data change was
persisted.

This is not V095 apply authorization, not runtime deployment, and not
production `allLiquidation*` revival.

## Preflight State

Read-only preflight showed:

- `market.liquidations` columns: `ts`, `symbol`, `side`, `qty`, `price`
- pre-V095 primary key: `symbol,ts,side`
- `_sqlx_migrations.version = 95` row count: `0`

## Dry-Run Method

Each round used one PostgreSQL transaction:

1. `BEGIN`
2. Run `sql/migrations/V095__market_liquidations_identity.sql`
3. Run the same migration again inside the same transaction to verify
   idempotency
4. Run DML probes inside the migrated transaction:
   - same `(symbol, ts, side)` with different `qty` / `price` preserves two rows
   - exact five-field duplicate with `ON CONFLICT DO NOTHING` remains idempotent
   - invalid future `side` is rejected by the V095 `CHECK`
5. `ROLLBACK`

## Observed Evidence

Both dry-run rounds passed with the expected notices:

- `V095: added NOT VALID CHECK chk_market_liquidations_side_v095`
- `V095: dropped old lossy primary key constraint liquidations_pkey`
- `V095: added item-level primary key (symbol, ts, side, qty, price)`
- second in-transaction run:
  - `V095: chk_market_liquidations_side_v095 already present; skipping`
  - `V095: market.liquidations already has item-level primary key; skipping`
- DML probes:
  - `V095 dry-run PASS: invalid future side rejected by CHECK`
  - `V095 dry-run PASS: distinct same-ts/symbol/side items preserved and exact duplicate idempotent`

## Rollback Verification

Read-only post-check after both rounds showed production state unchanged:

- primary key: `symbol,ts,side`
- `chk_market_liquidations_side_v095` count: `0`
- dry-run test rows: `0`
- `_sqlx_migrations.version = 95` row count: `0`

## Next Gate

MIT can now re-sign the W-AUDIT-8c idempotency condition based on this evidence.

Still blocked until separate PM/operator authorization:

- V095 production apply
- `_sqlx_migrations` registration / checksum repair if applicable
- runtime rebuild or restart
- production `allLiquidation*` topic revival
- paper, demo, LiveDemo, live, or mainnet setting changes

PM STATUS: V095 LINUX PG DRY-RUN X2 PASS / MIT RE-SIGN READY / APPLY AND REVIVAL STILL BLOCKED.
