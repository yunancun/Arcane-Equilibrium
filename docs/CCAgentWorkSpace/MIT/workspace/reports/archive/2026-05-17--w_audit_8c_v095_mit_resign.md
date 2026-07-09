# W-AUDIT-8c V095 MIT Re-Sign

**Date**: 2026-05-17
**Role**: MIT(default)
**Scope**: V095 idempotency re-sign after Linux PostgreSQL dry-run evidence. No source, runtime, config, production DB apply, or subscription change.

## Verdict

**MIT RE-SIGN: APPROVE-CONDITIONAL for the prior idempotency condition.**

V095 satisfies MIT's prior storage-identity condition for W-AUDIT-8c source/runtime revival prerequisites:

- one Bybit `allLiquidation.{symbol}` `data[]` item maps through parser/dispatch/writer as one candidate `market.liquidations` row;
- distinct same-millisecond, same-symbol, same-side items are not collapsed when `qty` or `price` differs;
- exact five-field duplicates remain idempotent through `ON CONFLICT (symbol, ts, side, qty, price) DO NOTHING`;
- invalid future `side` values are rejected by the V095 `Buy` / `Sell` CHECK path.

This approval is limited to schema/writer idempotency readiness. It is not V095 production apply authorization and not production `allLiquidation*` topic revival authorization.

## Evidence Reviewed

- PM C1 final signoff: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--c1_final_signoff_result.md`
- PM W-AUDIT-8c source/test closure: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--w_audit_8c_correction_source_test_closure.md`
- PM V095 Linux PG dry-run: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--v095_linux_pg_dry_run_result.md`
- V095 migration: `sql/migrations/V095__market_liquidations_identity.sql`
- V095 static tests: `tests/migrations/test_v095_market_liquidations_identity.py`
- Relevant Rust source/test surfaces: `ws_client` parser/dispatch, `database::market_writer`, and `tick_pipeline::on_tick_helpers` liquidation paths.

Note: the advertised `db-schema-design-financial-time-series` skill file was not present under the listed local skill roots, so this review used the MIT role rules plus the repository migration Guard A/B/C standard.

## Question 1: Idempotency Condition

**Answer: Yes.**

V095 replaces the old lossy primary key `(symbol, ts, side)` with item-level identity `(symbol, ts, side, qty, price)`. The writer conflict target is aligned to the same five fields, and the source/test closure shows parser and writer fail closed for invalid liquidation rows.

MIT's prior concern was that two Bybit items with the same `T/s/S` but different `v` or `p` could be collapsed. V095 directly addresses that by making `qty` and `price` part of the primary key. The Linux DML probes confirmed the exact edge case: distinct same-`ts/symbol/side` rows with different `qty` or `price` are preserved, while an exact five-field duplicate is idempotent.

## Question 2: Linux PG Dry-Run Empirical Gate

**Answer: Yes.**

The dry-run evidence satisfies the migration empirical gate without production persistence:

- executed on `trade-core` against the real `trading_ai` TimescaleDB;
- ran two transaction-wrapped rounds;
- each round applied V095, ran V095 again inside the same transaction, executed DML probes, and then rolled back;
- post-check verified production schema/data remained unchanged: old primary key still present, V095 CHECK absent, dry-run rows absent, and `_sqlx_migrations.version = 95` still absent.

This is sufficient empirical evidence for MIT re-sign because the tested behavior covers both DDL idempotency and the exact lossy-collapse failure mode.

## Question 3: Production Revival Readiness

**Answer: Ready for PM/operator authorization from MIT's schema/idempotency perspective, but still blocked operationally until separately authorized.**

Remaining MIT blocker from C1 signoff is cleared by V095 source/test plus Linux dry-run x2 evidence. I do not see an additional MIT schema/idempotency blocker for production writer/topic revival.

Residual gates are operational/governance gates, not MIT re-sign blockers:

- PM/operator must explicitly authorize V095 production apply.
- PM/operator must explicitly authorize runtime rebuild/restart if needed.
- PM/operator must explicitly authorize production `allLiquidation*` subscription revival.
- Any `_sqlx_migrations` registration/checksum repair must be handled under the production migration procedure, not inferred from this dry-run.

## Explicit Blocks

The following remain **BLOCKED unless separately authorized**:

- V095 production apply;
- runtime restart or rebuild;
- production `allLiquidation*` subscription;
- production liquidation writer revival;
- paper, demo, LiveDemo, live, or mainnet setting changes.

MIT STATUS: V095 IDEMPOTENCY RE-SIGN APPROVED / PRODUCTION APPLY AND REVIVAL STILL BLOCKED PENDING PM-OPERATOR AUTHORIZATION.

MIT AUDIT DONE: `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-17--w_audit_8c_v095_mit_resign.md`
