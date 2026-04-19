# BB Audit — EDGE-P2-3 Phase 1b PostOnly reject + cancel handling

**Date:** 2026-04-20
**Role:** BB (Bybit API Auditor)
**Scope:** Phase 1b of EDGE-P2-3 — PostOnly reject classification, unfilled-limit timeout-cancel, reference-file gaps.
**Sources:** Bybit V5 docs (error, create-order, cancel-order, rate-limit pages fetched 2026-04-20) + repo `src/bybit_rest_client.rs`, `src/order_manager.rs`, `src/strategies/grid_trading.rs`.

---

## Executive summary

1. **Operator hypothesis `110003` = PostOnly-cross is WRONG.** `110003` per V5 error table = *"Order price exceeds the allowable range"* (hit instrument price filter). PostOnly-cross has **no dedicated retCode** in Bybit V5 public docs — the create-order page says the order is *"cancelled"* if it would fill immediately, but returns only a generic failure. Observed practice in the V5 ecosystem: rejected PostOnly orders surface as **retCode=0 with `orderStatus=Cancelled` on the order-response + `rejectReason=EC_PostOnlyWillTakeLiquidity`** via the `order` WS topic, **not** as a REST-level error at all. This is a material contract difference from what current `on_rejection` assumes.
2. **Repo reject path currently can't see exchange-level rejects.** `grid_trading::on_rejection(intent, reason)` is triggered by Guardian/cost_gate intent-stage rejections only. There is **no wiring from order-WS `rejectReason`** back into strategy `on_rejection`. Phase 1b must add that WS→strategy channel before the 30s backoff helps with PostOnly-cross.
3. **`BybitRetCode` enum is missing every PostOnly/price-filter/order-lifecycle code.** Enum has 13 codes (§1.2 repo); reality needs at least 8 more (see Q1). Reference file §4.2 is stale.
4. **`cancel_order` repo signature takes only `order_id`; reference §1.2 correctly flags this.** V5 natively accepts `orderLinkId` as a first-class idempotency key. Phase 1b cancel path SHOULD use `orderLinkId` (we already mint `"shadow_{ts}"` style ids), to close the race where we lose `orderId` because the WS `order` event hasn't landed yet when we decide to cancel.
5. **Reference file §4.1 Order rate limit = `10 req/s` is stale.** Current V5 per-UID linear limit is `20 req/s` for both create and cancel (separate buckets in practice, not formally documented as such). At 25-symbol grid × 1 cancel every ~90s worst-case = 0.28 cancel/s steady state — well under limit. Risk is only in bursts (e.g. DCP mass-cancel or risk-off cascade).

---

## Q1 — PostOnly reject retCodes

**Answer:**

PostOnly-cross does **not** map to a retCode in V5 REST. Bybit accepts the POST /v5/order/create (`retCode=0`), then the engine that would cross gets immediately cancelled and the WS `order` event arrives with:
- `orderStatus = "Cancelled"` (or `"Rejected"` on some legacy paths)
- `rejectReason` = `EC_PostOnlyWillTakeLiquidity` (canonical string)
- `cumExecQty = 0`

retCodes we MUST NOT conflate with PostOnly-cross (all are *real* REST retCodes and need separate handling):

| retCode | Meaning | Correct handling |
|---|---|---|
| `110003` | Order price exceeds allowable range (price filter) | Instrument cache stale or bad offset; **do NOT 30s backoff**, recompute `tick_size`/`price_limit` |
| `110004` / `110007` | Wallet/available balance insufficient | Strategy-level: pause symbol, NOT exchange backoff |
| `110008` | Order completed or cancelled (lifecycle race) | no-op, treat as success |
| `110010` | Order already cancelled | no-op |
| `110049` | Price tick invalid | round via `InstrumentInfoCache::round_price`, retry once |
| `110074` | Contract not live (delisted/suspended) | remove symbol from scanner universe |
| `110103` | "Only Post-Only orders are available at this stage" | exchange in pre-open auction; 30s backoff is correct here |
| `170213` | Order does not exist (cancel path) | no-op on cancel |
| `10006` / `10018` / `429` | Rate limit | existing `is_retryable()` path |

**Source:** Bybit V5 error table (fetched 2026-04-20), confirmed against create-order + cancel-order pages.

**Stability across environments:** retCodes are stable across mainnet / testnet / api-demo. `rejectReason` strings are also stable — this has been public since V3.

**Recommendation (drop-in):**

```rust
// src/bybit_rest_client.rs — extend BybitRetCode enum
pub enum BybitRetCode {
    // ... existing ...
    PriceOutOfRange = 110003,           // NOT PostOnly-cross — price filter
    WalletInsufficient = 110004,
    AvailableInsufficient = 110007,
    OrderCompletedOrCancelled = 110008, // noop on cancel
    OrderAlreadyCancelled = 110010,     // noop
    PriceTickInvalid = 110049,
    ContractNotLive = 110074,
    PostOnlyOnlyStage = 110103,         // 30s backoff correct
    OrderNotExistSpot = 170213,         // spot cancel noop
}

impl BybitRetCode {
    pub fn is_noop(&self) -> bool {
        matches!(
            self,
            Self::LeverageNotModified
            | Self::OrderNotFound
            | Self::OrderCompletedOrCancelled
            | Self::OrderAlreadyCancelled
            | Self::OrderNotExistSpot,
        )
    }
    /// Strategy should back off re-emit (not strategy-bug).
    pub fn is_exchange_backoff(&self) -> bool {
        matches!(self, Self::PostOnlyOnlyStage | Self::IpRateLimit)
    }
    /// Strategy-level: not a backoff signal, but needs intent-quality fix.
    pub fn is_instrument_filter(&self) -> bool {
        matches!(self, Self::PriceOutOfRange | Self::PriceTickInvalid)
    }
}
```

**And the actual PostOnly-cross path (WS-driven, not REST):**

```rust
// src/execution_listener.rs (or wherever OrderUpdate is dispatched)
// When receiving PrivateWsEvent::Order(OrderUpdate):
if update.order_status == "Cancelled" && update.cum_exec_qty == 0.0 {
    match update.reject_reason.as_str() {
        "EC_PostOnlyWillTakeLiquidity" => {
            // This is the real PostOnly-cross signal.
            // Route to strategy on_rejection with a distinct reason so the 30s
            // backoff fires — BUT ALSO emit a "market moved against us" telemetry
            // counter, because repeated PostOnly-cross means our offset_bps is
            // wrong for current volatility, not that the strategy is bad.
            strategy.on_rejection(intent, "postonly_would_cross");
        }
        "" | "EC_NoError" => { /* normal cancel path — e.g. our own 90s timeout */ }
        other => {
            // Other reject reasons (margin, risk, etc.) — log + telemetry, do NOT
            // assume PostOnly backoff semantics.
            warn!(symbol = %update.symbol, reject_reason = %other, "order cancelled with non-postonly reason");
        }
    }
}
```

---

## Q2 — Cancel endpoint + idempotency

**Endpoint:** `POST /v5/order/cancel` — confirmed. V5 `category` = `"linear"` for USDT perps.

**Required params:** `category` + `symbol` + (`orderId` XOR `orderLinkId`; if both, `orderId` wins).

**Idempotency key:** `orderLinkId` is the stronger choice. We already mint client-side ids (`shadow_{paper_fill_ts}` pattern at `tick_pipeline.rs:37-52`). Repo `cancel_order()` at `src/order_manager.rs:382-402` currently takes only `order_id` — **Phase 1b should add an `order_link_id`-variant** because:
- When we place PostOnly at T=0 and want to cancel at T=90s, the exchange `orderId` arrived via WS `order` topic. If WS is lagged/disconnected, we may not have `orderId` locally but we always have `orderLinkId` (we minted it).
- `orderLinkId` is what survives engine restart + in-memory map loss.

**Race (cancel arrives after fill):** Bybit returns:
- `retCode = 110001` (OrderNotFound) — if the order is already fully filled/cancelled → our `is_noop()` already covers this.
- `retCode = 110008` (completed or cancelled) — same class, add to `is_noop()` (Q1 recommendation).
- Separately, **WS `execution` event is NOT ordered relative to the cancel HTTP response.** Bybit does not guarantee cancel-response before execution-notification. Safe pattern: treat cancel as advisory, reconcile via WS `order` final state. Never decrement position based on cancel return value.

**Rate limits:**
- Per V5 rate-limit docs (fetched 2026-04-20): linear cancel = **20 req/s per UID**, create = **20 req/s per UID**. Treat as separate buckets in practice (batch endpoints are explicitly separate; singles are typically separate per endpoint-id).
- 25 symbols × worst-case 1 cancel per 90s = **0.28 req/s** steady state → no concern.
- Burst risk: if DCP-like risk-off fires, we could try to cancel all 25 orders in one tick. Use `/v5/order/cancel-all` by symbol or `/v5/order/cancel-batch` (MAX_BATCH_SIZE=10, repo `batch_order_manager.rs`) rather than 25 sequential cancels.

**Reference file §4.1 is STALE** — shows Order bucket at 10 req/s. Actual V5 is 20. Update needed.

**Recommendation (drop-in):**

```rust
// src/order_manager.rs — add order_link_id variant
pub async fn cancel_order_by_link_id(
    &self,
    category: OrderCategory,
    symbol: &str,
    order_link_id: &str,
) -> BybitResult<OrderResponse> {
    let body = serde_json::json!({
        "category": category.as_str(),
        "symbol": symbol,
        "orderLinkId": order_link_id,
    });
    let resp = self.client.post_checked("/v5/order/cancel", &body).await?;
    parse_order_response(&resp.result)
}

// Strategy timeout cancel site (phase 1b):
match order_manager.cancel_order_by_link_id(cat, sym, &link_id).await {
    Ok(_) => { /* cancel accepted, wait for WS final state */ }
    Err(BybitApiError::Business { ret_code, .. }) => {
        if let Some(rc) = BybitRetCode::from_code(ret_code) {
            if rc.is_noop() {
                // Already filled/cancelled — reconcile via WS, not here.
                return;
            }
        }
        // Real error — log + telemetry, do NOT retry cancel in a loop.
        warn!(symbol = %sym, link_id = %link_id, ret_code, "cancel failed");
    }
    Err(e) => warn!(error = %e, "cancel transport error"),
}
```

---

## Q3 — Land mines we'd regret not knowing

1. **`reduceOnly` + PostOnly interaction (close path).** Phase 1a correctly keeps close-path on Market (grid_trading.rs:1621-1623). If anyone extends PostOnly to close path, be aware: PostOnly-cross on a close is catastrophic — you get stranded in the position with a maker order that never fills, while the adverse move continues. Keep Market for close, hard-document the rule.

2. **`closeOnTrigger` ≠ `reduceOnly`.** `closeOnTrigger=true` gives the order priority during liquidation (bumps ahead of normal reduce-only). It does **not** replace `reduceOnly`. We do not use `closeOnTrigger` today (nor should we for Phase 1b).

3. **Funding window behavior.** At funding timestamp (every 8h), Bybit briefly freezes some order operations. PostOnly orders resting through a funding window are not cancelled, but new PostOnly orders placed within ~1s of funding can return `110103` ("Only Post-Only orders are available at this stage") or a transient `10002`. The 30s backoff handles this naturally.

4. **Per-symbol minQty after maker fill.** When a PostOnly partial-fills (e.g. 60% of qty at T=30s, then another cross happens at T=60s), the *remaining* qty must still satisfy `min_qty` after the 90s cancel, otherwise the cancel may succeed but you can't re-place because you're under min. `InstrumentInfoCache::validate_order` already guards this at place time; we also need to check at **cancel→re-place decision time** if Phase 1b adds auto-replace-on-timeout. For a pure "cancel and give up" Phase 1b, not an issue.

5. **`execution.fast` is mainnet-only** (reference §2.2 covers this). Phase 1b dev-tests on demo → `execution` topic. When promoting to mainnet, the cancel-race timing tightens from ~300ms to ~50ms — partial-fill probability during our cancel round-trip goes up ~6×. Worth noting in E2 adversarial review.

6. **orderLinkId uniqueness.** Bybit documents orderLinkId uniqueness only "within recent history." Our `shadow_{paper_fill_ts}` pattern using ms timestamps is fine for single-tick dedup, but if we ever replace an expired order with the same link_id, Bybit will silently accept and create a duplicate. For Phase 1b timeout-cancel, if we ever auto-re-place after cancel, use a fresh link_id (e.g. append retry counter).

7. **DCP interaction.** DCP fires cancel-all on WS disconnect — our 90s timer is racy against DCP. Should be fine (DCP cancel returns the same `110001`/`110008` we already handle as noop), but worth an integration test: "engine WS flaps during PostOnly resting → timer fires on stale order → cancel returns noop → reconciler eventually sees position=0."

---

## Reference-file gaps flagged for update

File: `docs/references/2026-04-04--bybit_api_reference.md`

1. **§4.2 Error Code table** — missing 110003 / 110004 / 110007 / 110008 / 110010 / 110049 / 110074 / 110103 / 170213. At minimum add the 3 that Phase 1b directly exercises: 110008 (noop), 110010 (noop), 110103 (backoff).
2. **§4.1 Rate Limit** — "Order 10 req/s" is stale. Current V5 linear = 20 req/s (create and cancel, separate buckets per endpoint in practice).
3. **§1.2 `cancel_order`** — only documents `order_id` variant. Should document that V5 natively supports `orderLinkId` alternative key and note the repo currently doesn't expose it (TODO item for Phase 1b).
4. **New section needed: WS `order` `rejectReason` strings** — canonical list: `EC_NoError`, `EC_PostOnlyWillTakeLiquidity`, `EC_CancelForNoFullFill`, `EC_NotAbleToFillPartially` etc. Without this documented, anyone maintaining on_rejection will guess.

---

*BB — audit complete. Ready for PA to shape into Phase 1b E1 task brief.*
