# P3 110017 D2 Audit Removed Semantics Focused Review

Date: 2026-06-19

Owner: PM-local

Verdict: PASS_WITH_LIMITS

## Scope

This review refreshed the PM-local evidence for `P3-110017-D2-AUDIT-REMOVED-SEMANTICS`.

Covered:

- D2 ghost convergence dispatch semantics.
- `reconcile_ghost_converge` audit payload semantics.
- Local convergence handler path from `ConvergeExchangeZero` to `converge_exchange_zero_close`.
- Regression coverage for dispatch-only vs handler-confirmed payload wording, ghost convergence behavior, and loop break behavior.

Not covered:

- Formal E2/E4 review closure.
- Production `reconcile_ghost_converge` event proof.
- Runtime deploy, rebuild, restart, or Linux cargo.
- Real Bybit private/signed calls, DB writes, auth/risk/order/trading mutation.

## Source Review

- `rust/openclaw_engine/src/tick_pipeline/mod.rs:627` defines `PipelineCommand::ConvergeExchangeZero`, explicitly separate from `CloseSymbol`.
- `rust/openclaw_engine/src/position_reconciler/orphan_handler.rs:441` documents why D2 must dispatch `ConvergeExchangeZero` instead of `CloseSymbol`: the exchange is already confirmed zero, so no reduce-only close should be sent.
- `rust/openclaw_engine/src/position_reconciler/orphan_handler.rs:451` sends `ConvergeExchangeZero` with `symbol`, local `is_long`, and `ts_ms`.
- `rust/openclaw_engine/src/position_reconciler/orphan_handler.rs:482` documents the audit target as `observability.engine_events` with `event_type='reconcile_ghost_converge'`, deliberately not `trading.order_state_changes`.
- `rust/openclaw_engine/src/position_reconciler/orphan_handler.rs:489` states that `confirmed=false` proves only successful command dispatch, not handler-side local removal.
- `rust/openclaw_engine/src/position_reconciler/orphan_handler.rs:491` builds payloads with `removed_position_semantics` equal to `dispatched-not-confirmed` or `handler-confirmed`.
- `rust/openclaw_engine/src/position_reconciler/orphan_handler.rs:515` inserts the audit payload fire-and-forget into `observability.engine_events`.
- `rust/openclaw_engine/src/position_reconciler/mod.rs:1054` dispatches D2 convergence only after the ghost gate conditions are satisfied; `:1058` records why the audit emitted at dispatch site must use `confirmed=false`.
- `rust/openclaw_engine/src/event_consumer/handlers/mod.rs:412` routes `PipelineCommand::ConvergeExchangeZero` into `lifecycle::handle_converge_exchange_zero`.
- `rust/openclaw_engine/src/event_consumer/handlers/lifecycle.rs:305` documents that the handler follows exchange zero truth and must not route through `ipc_close_symbol`.
- `rust/openclaw_engine/src/event_consumer/handlers/lifecycle.rs:321` calls `pipeline.converge_exchange_zero_close` and flushes a snapshot only if a local position was actually removed.
- `rust/openclaw_engine/src/tick_pipeline/commands.rs:1530` documents the local convergence path as positions-remove plus mirror sync, with no realized PnL/Kelly pollution.
- `rust/openclaw_engine/src/tick_pipeline/commands.rs:1557` implements exchange-only convergence, clears `pending_close_symbols`, and returns whether a local position was removed.
- `rust/openclaw_engine/src/tick_pipeline/commands.rs:1549` preserves the hedge-mode re-review caveat.

## Verification

Commands were run from `/Users/ncyu/Projects/TradeBot/srv/rust`.

| Command | Result |
|---|---|
| `cargo test -p openclaw_engine position_reconciler::orphan_handler::tests::ghost_converge_audit_payload --lib` | PASS, 2 passed |
| `cargo test -p openclaw_engine position_reconciler::orphan_handler::tests --lib` | PASS, 19 passed |
| `cargo test -p openclaw_engine test_converge_exchange_zero_close_removes_drift_position_and_breaks_loop --lib` | PASS, 1 passed |
| `cargo test -p openclaw_engine position_reconciler::tests::ghost --lib` | PASS, 11 passed |
| `cargo clippy -p openclaw_engine --lib -- -D warnings` | PASS |

Linux read-only production DB check:

```text
select count(*) as total,
       count(*) filter (where payload ? 'removed_position_semantics') as semantics_rows
from observability.engine_events
where event_type='reconcile_ghost_converge';

0|0
```

The psql warning about collation version was informational for this read-only count.

## Conclusion

The PM-local source review and focused regression matrix support the current D2 audit semantics: dispatch-site audit rows must use `removed_position_semantics='dispatched-not-confirmed'`, handler-confirmed wording is reserved for a handler-side fact, and the local convergence path removes drifted exchange-zero positions without sending another close order or recording synthetic PnL.

This narrows review risk but does not archive the TODO row. Formal E2/E4 review and production event proof remain open.
