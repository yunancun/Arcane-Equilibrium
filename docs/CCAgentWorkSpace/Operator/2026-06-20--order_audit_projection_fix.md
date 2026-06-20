# Order Audit Projection Fix

PASS_WITH_LIMITS. FlashDip 的 limit price source path 是存在的，缺口在 Working order audit projection。

- Linux read-only PG：19 張 `flash_dip_buy` Working orders 的 `trading.orders.price/context_id/details` 全 NULL。
- 同批 rows 可用 `intent_id` join 回 `trading.intents`，還原 `ctx-*` 與真實 `details.limit_price`。
- Source confirms `OrderDispatchRequest.limit_price -> CreateOrderRequest.price`；不是 limit price 沒送。
- Fix：`PendingOrder` / `TradingMsg::Order` / `flush_orders` 現在把 `price/context_id/details` 寫入既有 `trading.orders` 欄位。
- Focused checks passed：pending-registration 23、trading_writer 14、`cargo check -p openclaw_engine --lib`、touched-file rustfmt、targeted diff-check。

Boundary：source/test/docs + read-only PG only；未 deploy/rebuild/restart trade-core。current old rows remain NULL；下一次安全 rebuild/restart 後新 Working orders 才會直接有 price/context/details。Current no-fill diagnosis: deep-K/no-touch plus old audit blind spot, not missing limit-price submit.
