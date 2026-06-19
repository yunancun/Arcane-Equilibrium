# P2 Reconciler get_positions Pagination Focused Review

Date: 2026-06-19

Owner: PM-local

Verdict: PASS_WITH_LIMITS

## Scope

This review refreshed the PM-local evidence for `P2-RECONCILER-GET-POSITIONS-PAGINATION`.

Covered:

- Full-scan `PositionManager::get_positions(category, None)` pagination.
- Same-cursor fail-closed behavior for `nextPageCursor`.
- Client-side invariant classification downstream of `BybitApiError::Other`.
- Ghost convergence point-query guard against pagination-truncated false ghosts.

Not covered:

- Formal BB/E2/E4/QA review closure.
- Production `reconcile_ghost_converge` event proof.
- Runtime deploy, rebuild, restart, or Linux cargo.
- Real Bybit private/signed calls, DB writes, auth/risk/order/trading mutation.

## Source Review

- `rust/openclaw_engine/src/position_manager.rs:154` sets full-scan page size to 200 and `:157` caps full-scan pagination at 50 pages, with fail-closed rationale for abnormal pagination.
- `rust/openclaw_engine/src/position_manager.rs:168` documents the split between full-scan pagination and single-symbol point-query behavior.
- `rust/openclaw_engine/src/position_manager.rs:181` keeps single-symbol point-query as one request and ignores cursor, preserving the D2 point-query gate behavior.
- `rust/openclaw_engine/src/position_manager.rs:197` performs full-scan pagination with `settleCoin=USDT`, `limit=200`, optional `cursor`, and `nextPageCursor` loop termination.
- `rust/openclaw_engine/src/position_manager.rs:227` validates cursor advancement before continuing; `:231` fails closed if the page cap is reached with a cursor still remaining.
- `rust/openclaw_engine/src/position_manager.rs:610` parses positions plus `nextPageCursor`, normalizing missing or empty cursor to `None`.
- `rust/openclaw_engine/src/position_manager.rs:641` rejects a response cursor equal to the current request cursor via `BybitApiError::Other`.
- `rust/openclaw_engine/src/position_manager.rs:850` covers cursor extraction, empty/missing cursor termination, parse-list delegation, first non-empty cursor acceptance, same-cursor fail-closed, and advanced cursor acceptance.
- `rust/openclaw_engine/src/event_consumer/dispatch.rs:225` maps `BybitApiError::Other` to `DispatchOutcome::Structural`, so client-side invariant failures do not retry as transient exchange errors.
- `rust/openclaw_engine/src/notification_failsafe/providers/exchange_stop_sync.rs:140` maps client-side invariant failures to `ExchangeStopError::Transport`, preserving "cannot trust sync" behavior.
- `rust/openclaw_engine/src/position_reconciler/tests.rs:927` locks the pagination-truncation false-ghost case: a point-query result of `StillHasPosition` keeps the drift and dispatches no `ConvergeExchangeZero`.
- `rust/openclaw_engine/src/position_reconciler/tests.rs:965` preserves the happy path where `ConfirmedZero` converges.
- `rust/openclaw_engine/src/position_reconciler/tests.rs:1002` preserves fail-closed behavior when point-query fails.
- `rust/openclaw_engine/src/position_reconciler/tests.rs:1036` proves the point-query gate is load-bearing by contrasting a wrongly confirmed zero against `StillHasPosition`.

## Verification

An initial cargo invocation was run from `/Users/ncyu/Projects/TradeBot/srv` and failed before test execution with `could not find Cargo.toml`. That was a command-location error, not a regression failure. The commands below were rerun from `/Users/ncyu/Projects/TradeBot/srv/rust`.

| Command | Result |
|---|---|
| `cargo test -p openclaw_engine position_manager::tests --lib` | PASS, 19 passed |
| `cargo test -p openclaw_engine test_classify_client_side_invariant_error --lib` | PASS, 1 passed |
| `cargo test -p openclaw_engine notification_failsafe::providers::exchange_stop_sync::tests::map_client_side_invariant_to_transport --lib` | PASS, 1 passed |
| `cargo test -p openclaw_engine ghost_pagination_truncation_false_ghost_not_converged --lib` | PASS, 1 passed |
| `cargo test -p openclaw_engine position_reconciler::tests::ghost --lib` | PASS, 11 passed |
| `cargo clippy -p openclaw_engine --lib -- -D warnings` | PASS |

## Conclusion

The PM-local source review and focused regression matrix support the current source behavior: full-scan pagination fails closed on cursor non-advance, client-side invariant errors propagate as structural/sync-untrusted failures, and the ghost point-query gate prevents a pagination-truncated real position from being converged away.

This narrows review risk but does not archive the TODO row. Formal BB/E2/E4/QA review and production event proof remain open.
