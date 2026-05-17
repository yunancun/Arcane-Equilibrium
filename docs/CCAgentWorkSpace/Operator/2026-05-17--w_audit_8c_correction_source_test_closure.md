# W-AUDIT-8c Correction Source/Test Closure

**Date**: 2026-05-17T18:49Z
**Role**: PM(default)
**Scope**: W-AUDIT-8c correction-scoped source/test packet after C1 technical PASS. This is not production revival.

## PM Verdict

**SOURCE/TEST CORRECTION DONE.**
**Production `allLiquidation*` writer/topic revival remains BLOCKED.**

This packet resolves the C1 post-signoff correction requirements in source and tests:

1. Correct Bybit side semantics are encoded and tested: `S=Buy` is long liquidation with mean-reversion direction `+1`; `S=Sell` is short liquidation with direction `-1`.
2. V095 source migration changes `market.liquidations` identity to one item per row with `PRIMARY KEY (symbol, ts, side, qty, price)`.
3. Parser and writer now fail closed for invalid liquidation rows instead of coercing/defaulting them.
4. Production subscription builders remain unchanged and still exclude `allLiquidation*`.

## Dispatch Chain

- PM(default): scope, boundary, and final integration.
- E1(worker): source/test implementation for W-AUDIT-8c correction packet.
- E2(explorer): adversarial source review; initial RETURN fixed, re-review APPROVE-CONDITIONAL only on excluding unrelated dirty GUI files from commit.
- E4(worker): targeted regression verification PASS.
- MIT(default): APPROVE-CONDITIONAL; production revival still requires Linux PG dry-run and V095 apply authorization.
- BB(default): APPROVE after corrected side mapping and fail-closed parser checks.

QA was not dispatched as a separate end-to-end runtime role because this checkpoint is source/test only and does not deploy, restart, apply DB changes, or subscribe to production `allLiquidation*`.

## Files

Source/test files in scope:

- `docs/execution_plan/2026-05-16--w_audit_8c_liquidation_cluster_strategy_spec.md`
- `sql/migrations/V095__market_liquidations_identity.sql`
- `tests/migrations/test_v095_market_liquidations_identity.py`
- `rust/openclaw_engine/src/ws_client/parsers.rs`
- `rust/openclaw_engine/src/ws_client/dispatch.rs`
- `rust/openclaw_engine/src/ws_client/tests.rs`
- `rust/openclaw_engine/src/database/mod.rs`
- `rust/openclaw_engine/src/database/market_writer.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs`

Explicitly excluded unrelated pre-existing GUI dirty files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-demo.html`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_performance_metrics_gui_contract.py`

## Verification

Local Mac verification passed:

- `./venvs/mac_dev/bin/python -m pytest tests/migrations/test_v095_market_liquidations_identity.py -q` -> 6 passed
- `cd rust && cargo test -p openclaw_engine --lib all_liquidation -- --nocapture` -> 6 passed
- `cd rust && cargo test -p openclaw_engine --lib liquidation -- --nocapture` -> 14 passed
- `cd rust && cargo test -p openclaw_engine --lib ws_client::tests -- --nocapture` -> 29 passed
- `cd rust && cargo test -p openclaw_engine --lib multi_interval_topics::tests::test_production_subscription_excludes_dormant_poison_topics -- --nocapture` -> 1 passed
- `rustfmt --edition 2021 --check` on touched Rust files -> PASS
- `git diff --check` on scoped files -> PASS

## Remaining Gate

Before any production writer revival:

1. Run V095 Linux `trade-core` PG dry-run twice against real TimescaleDB.
2. Verify same `(symbol, ts, side)` with different `qty` or `price` preserves both rows.
3. Verify exact five-field duplicate is idempotent.
4. Verify invalid future `side` inserts reject after constraint validation.
5. Apply V095 only after PM runtime authorization and MIT re-sign.
6. Keep production `allLiquidation*` subscription disabled until a separate PM runtime dispatch explicitly authorizes revival.

No runtime deploy, Linux DB apply, rebuild, restart, auth mutation, paper/live/mainnet enablement, strategy/risk mutation, or production `allLiquidation*` subscription happened in this checkpoint.

PM STATUS: W-AUDIT-8C SOURCE/TEST CORRECTION DONE / PRODUCTION REVIVAL BLOCKED BY V095 LINUX DRY-RUN + APPLY AUTHORIZATION + MIT RE-SIGN.
