# Order Audit Projection Fix

## Verdict

PASS_WITH_LIMITS. FlashDip 的 limit price 沒有在 source 層消失；它已送入 `CreateOrderRequest.price`。真正缺口是 Working order audit row 沒把 `price/context_id/details` 從 `PendingOrder` 投到 `trading.orders`，導致 profitability/no-fill 診斷要靠 `intents` join 才能還原。

## Evidence

- Linux read-only PG：`flash_dip_buy` 有 19 張 Working orders；`trading.orders.price/context_id/details` 全 NULL；同批 `intent_id` join 回 `trading.intents` 可還原 `ctx-*` 與 `details.limit_price`。
- Runtime distribution：19/19 orders 可從 intents 還原 limit price；intent reference vs limit distance median 約 1423bp，支持 deep-K/no-touch 的零 fill 診斷。
- Source audit：`OrderDispatchRequest.limit_price` already maps to `CreateOrderRequest.price`; missing projection was between `PendingOrder -> TradingMsg::Order -> flush_orders`.

## Change

- `PendingOrder` now carries `limit_price`.
- `TradingMsg::Order` now carries `price`, `context_id`, and JSONB `details`.
- `flush_orders` now inserts existing `trading.orders.price/context_id/details` columns.
- Pending-registration regression now asserts Limit+PostOnly emits price/context/details.

## Verification

- `cargo test -p openclaw_engine event_consumer::tests::pending_registration_order_type_tests -- --nocapture` = 23 passed.
- `cargo test -p openclaw_engine database::trading_writer -- --nocapture` = 14 passed.
- `cargo check -p openclaw_engine --lib` PASS.
- Touched-file `rustfmt --edition 2021 --check ...` PASS.
- Targeted `git diff --check` PASS.

Workspace-wide `cargo fmt --check` still fails on unrelated pre-existing `openclaw_core` / `openclaw_types` formatting drift.

## Boundary

No Linux deploy/rebuild/restart, no PG table write/schema migration, no Bybit private/signed/trading call, no credential/auth/risk/order/trading mutation. Current trade-core engine binary has not loaded this source fix; future rows get the projection only after a safe rebuild/restart.
