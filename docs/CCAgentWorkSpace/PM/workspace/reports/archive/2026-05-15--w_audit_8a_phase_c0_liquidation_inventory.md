# W-AUDIT-8a Phase C0 — Liquidation Revival Inventory

Date: 2026-05-15  
Scope: Phase C0 inventory / guard only. No production WS subscription change, no writer revival, no DB write, no rebuild, no restart, no auth change.

## Verdict

Phase C0 is complete as an inventory and safety-guard packet.

C1 remains blocked until BB proves a safe liquidation topic on an isolated connection. Production must not subscribe `liquidation.*`, `price-limit.*`, `adl-notice.*`, or `allLiquidation` before that proof.

## DB Inventory

`trade-core` read-only inventory:

```text
table|market.liquidations
column|ts|timestamp with time zone|NO
column|symbol|text|NO
column|side|text|NO
column|qty|real|NO
column|price|real|NO
rows|0|latest|none
index|idx_liquidations_ts_desc|CREATE INDEX idx_liquidations_ts_desc ON market.liquidations USING btree (ts DESC)
index|liquidations_pkey|CREATE UNIQUE INDEX liquidations_pkey ON market.liquidations USING btree (symbol, ts, side)
hypertable|market|liquidations|compression_enabled=True
policy|policy_compression|12:00:00|compress_after=7 days
policy|policy_retention|1 day|drop_after=90 days
```

MIT input: existing retention is 90d, not the 30d target in the older Phase C text. Do not add a migration just to shrink retention during C0; revisit after C1 observes real event rate.

## Source Inventory

- `multi_interval_topics.rs` production builder returns kline + ticker + `orderbook.50` + publicTrade only.
- `main_ws.rs` consumes `full_subscription_list()` when `enable_extended_ws=true`; stale logging was corrected from `topics_per_symbol=10` to `7`.
- `config/mod.rs` comment was corrected: extended WS means kline/tickers/orderbook/publicTrade; broken liquidation/price-limit/adl-notice topics remain disabled.
- `ws_client/parsers.rs` and `ws_client/dispatch.rs` still retain legacy parser/dispatch branches for `liquidation.*`, `price-limit.*`, and `adl-notice.*`.
- `database/mod.rs` no longer has `MarketDataMsg::Liquidation`; `market_writer.rs` states the liquidation writer was deleted 2026-04-06. Therefore parser branches are inactive unless a future producer/topic path is deliberately restored.

## Guard Added

Added Rust unit test:

`multi_interval_topics::tests::test_production_subscription_excludes_dormant_poison_topics`

The test fails if production topic builders emit any of:

- `liquidation.`
- `price-limit.`
- `adl-notice.`
- `allLiquidation`

This locks the C0 rule in code: topic revival must be a deliberate C1 change after BB standalone proof, not an accidental list edit.

## Replay Applicability

Replay cannot validate the main C1 safety question: whether a candidate Bybit liquidation topic causes `"handler not found"`, rate-limit pressure, or connection poisoning on a real WS connection. That remains a BB standalone live-public WS probe requirement.

Replay can validate the local fail-closed contract. Added targeted replay adapter coverage:

`replay::strategy_adapter::tests::replay_empty_surface_keeps_liquidation_cascade_fail_closed`

This proves the isolated replay path still supplies `EMPTY_ALPHA_SURFACE`; a strategy declaring `LiquidationCascade` sees `liquidation_pulse=None`, observes `LiquidationCascade` as unavailable, emits no actions, and writes no replay decision trace.

## BB Standalone Probe Contract For C1

C1 may start only after BB provides a standalone probe result with:

1. Isolated WS connection, not the production public market-data connection.
2. Candidate topic explicitly recorded, including whether it is global or per-symbol.
3. 24h run with zero `"handler not found"` / subscription rejection incidents.
4. No evidence of connection poisoning: kline/ticker/orderbook/publicTrade streams on the same probe connection keep receiving data.
5. No Bybit rate-limit or reconnect loop attributable to the candidate liquidation topic.
6. Sample payload captured and mapped to the existing `market.liquidations` shape or a reviewed schema delta.
7. BB + MIT sign-off before any production subscription list change.

Until then, `AlphaSurface.liquidation_pulse` remains `None`, and any strategy declaring `LiquidationCascade` must fail closed.

## Verification

- `cargo test -q -p openclaw_engine multi_interval_topics`: PASS, 11 tests.
- `cargo test -q -p openclaw_engine replay_empty_surface_keeps_liquidation_cascade_fail_closed`: PASS, 1 test.
- `cargo test -q -p openclaw_engine strategy_adapter`: PASS, 4 tests.
- `rustfmt --edition 2021 --check rust/openclaw_engine/src/multi_interval_topics.rs rust/openclaw_engine/src/main_ws.rs`: PASS.
- `rustfmt --check` including `config/mod.rs` traverses existing config submodules and reports pre-existing formatting drift in `config/canary_promotion.rs`, `config/risk_config_advanced.rs`, and `config/risk_config_tests.rs`; no formatting issue was shown for the touched comment itself.
