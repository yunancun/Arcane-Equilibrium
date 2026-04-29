//! G7-09c Phase 1 — BBO-aware PostOnly maker limit price helper.
//! G7-09c Phase 1 — 基於 BBO 的 PostOnly maker 限價輔助函式。
//!
//! MODULE_NOTE (EN): Shared `compute_post_only_price()` used by all four
//!   maker-capable strategies (ma_crossover / bb_breakout / grid_trading /
//!   bb_reversion). RCA `7f0e793` showed 4 days × 178 PostOnly orders 100%
//!   rejected by Bybit (`EC_PostOnlyWillTakeLiquidity`) because previous
//!   strategies built `limit_price = ctx.price (last_price) ± offset_bps`.
//!   `last_price` is the most recent trade — not the best resting quote — so
//!   on any nontrivial spread / book staleness the BUY limit landed AT or
//!   ABOVE the ask (→ would take liquidity → PostOnly reject), and SELL
//!   landed AT or BELOW the bid. This helper places strictly passive:
//!     - Buy:  best_bid - buffer_ticks × tick_size
//!     - Sell: best_ask + buffer_ticks × tick_size
//!   When BBO/tick_size are incomplete, it only uses a side-specific quote
//!   that can still be made strictly passive. If no safe maker price can be
//!   derived, it returns `None` so callers skip the new-open intent instead
//!   of emitting a legacy `last_price ± offset_bps` fallback.
//!
//! MODULE_NOTE (中): 共用 `compute_post_only_price()`，由 ma_crossover /
//!   bb_breakout / grid_trading / bb_reversion 四策略呼叫。RCA `7f0e793`
//!   發現 4 天 178 筆 PostOnly 100% 被 Bybit 拒（`EC_PostOnlyWillTakeLiquidity`），
//!   原因為策略以 `ctx.price (last_price) ± offset_bps` 計限價；last_price ≠
//!   best_bid/ask，spread + book 陳舊性導致 BUY 落在 ask 以上、SELL 落在
//!   bid 以下，必跨 book → PostOnly 100% reject。本 helper 嚴格被動掛單：
//!     - Buy:  best_bid - buffer_ticks × tick_size
//!     - Sell: best_ask + buffer_ticks × tick_size
//!   當 BBO/tick_size 不完整時，只使用仍可保證 passive 的單側報價；若無法
//!   推導安全 maker 價，回傳 `None` 讓呼叫端跳過新開倉，而不是發出舊式
//!   `last_price ± offset_bps` fallback。

use tracing::warn;

/// Inputs for `compute_post_only_price()` extracted from `TickContext` at
/// the call site so the helper stays pure (no `ctx` dependency cycle).
/// 從 `TickContext` 抽出參數呼叫本 helper，避免 helper 依賴 ctx 造成迴圈。
#[derive(Debug, Clone, Copy)]
pub struct MakerPriceInputs {
    /// Last traded price — logged on skip for RCA, not used for fallback pricing.
    /// 最新成交價，僅在 skip 時供 RCA 記錄，不再用於 fallback 計價。
    pub last_price: f64,
    /// Best bid from latest tick (None when WS hasn't delivered orderbook yet).
    /// 最新 tick 的 best bid（WS 未送出 orderbook 前為 None）。
    pub best_bid: Option<f64>,
    /// Best ask from latest tick (None when WS hasn't delivered orderbook yet).
    /// 最新 tick 的 best ask（WS 未送出 orderbook 前為 None）。
    pub best_ask: Option<f64>,
    /// Symbol's tick_size from instrument_info cache (None when cache miss).
    /// 由 instrument_info 快取查得的 tick_size（cache miss 時為 None）。
    pub tick_size: Option<f64>,
}

/// Compute a strictly passive PostOnly limit price.
///
/// `is_long = true` → buy side (place at-or-below best_bid).
/// `is_long = false` → sell side (place at-or-above best_ask).
///
/// `buffer_ticks` (typically 1) sets how many ticks INSIDE the book the
/// limit sits — buffer_ticks=0 sits exactly on the inside quote (still
/// passive at maker), buffer_ticks=1 sits one tick away (more passive,
/// safer against single-tick book moves).
///
/// 計算嚴格被動的 PostOnly 限價。
/// `is_long = true` → 買單（掛 best_bid 同價或更低）。
/// `is_long = false` → 賣單（掛 best_ask 同價或更高）。
/// `buffer_ticks` 控制離 inside quote 多少 tick；0 = 同價（仍 passive maker），
/// 1 = 退一 tick（更被動，可吸收單 tick 行情）。
///
/// Strict path: when no safe BBO-derived maker price can be computed, return
/// `None` and let the strategy skip the new entry. This avoids turning a
/// PostOnly entry into an accidental taker order during cold starts, crossed
/// books, or instrument-cache misses.
///
/// 嚴格路徑：無法從 BBO 推導安全 maker 價時回傳 `None`，由策略跳過新開倉。
/// 這避免冷啟動、crossed book、instrument cache miss 時把 PostOnly 入場退化成
/// 可能吃單的 last_price fallback。
pub fn compute_post_only_price(
    is_long: bool,
    inputs: MakerPriceInputs,
    fallback_offset_bps: f64,
    buffer_ticks: u32,
    strategy_name: &str,
    symbol: &str,
) -> Option<f64> {
    let tick = match inputs.tick_size {
        Some(t) if t.is_finite() && t > 0.0 => t,
        _ => {
            warn!(
                strategy = strategy_name,
                symbol = symbol,
                is_long = is_long,
                last_price = inputs.last_price,
                best_bid = ?inputs.best_bid,
                best_ask = ?inputs.best_ask,
                tick_size = ?inputs.tick_size,
                fallback_offset_bps = fallback_offset_bps,
                "maker_price strict skip: tick_size unavailable; no last_price fallback \
                 / maker_price 嚴格跳過：tick_size 不可得，不使用 last_price fallback"
            );
            return None;
        }
    };

    let bid = inputs.best_bid.filter(|v| v.is_finite() && *v > 0.0);
    let ask = inputs.best_ask.filter(|v| v.is_finite() && *v > 0.0);

    if let (Some(bid), Some(ask)) = (bid, ask) {
        if ask <= bid {
            warn!(
                strategy = strategy_name,
                symbol = symbol,
                is_long = is_long,
                last_price = inputs.last_price,
                best_bid = bid,
                best_ask = ask,
                tick_size = tick,
                fallback_offset_bps = fallback_offset_bps,
                "maker_price strict skip: locked/crossed book; no last_price fallback \
                 / maker_price 嚴格跳過：locked/crossed book，不使用 last_price fallback"
            );
            return None;
        }
    }

    let buffer = f64::from(buffer_ticks) * tick;
    let cross_buffer = if buffer_ticks == 0 { tick } else { buffer };
    let price = if is_long {
        match (bid, ask) {
            (Some(bid), _) => bid - buffer,
            (None, Some(ask)) => ask - cross_buffer,
            (None, None) => {
                return warn_skip_no_quote(
                    is_long,
                    inputs,
                    fallback_offset_bps,
                    strategy_name,
                    symbol,
                    tick,
                )
            }
        }
    } else {
        match (bid, ask) {
            (_, Some(ask)) => ask + buffer,
            (Some(bid), None) => bid + cross_buffer,
            (None, None) => {
                return warn_skip_no_quote(
                    is_long,
                    inputs,
                    fallback_offset_bps,
                    strategy_name,
                    symbol,
                    tick,
                )
            }
        }
    };

    if price.is_finite() && price > 0.0 {
        Some(price)
    } else {
        warn!(
            strategy = strategy_name,
            symbol = symbol,
            is_long = is_long,
            last_price = inputs.last_price,
            best_bid = ?inputs.best_bid,
            best_ask = ?inputs.best_ask,
            tick_size = ?inputs.tick_size,
            fallback_offset_bps = fallback_offset_bps,
            candidate_price = price,
            "maker_price strict skip: passive price invalid; no last_price fallback \
             / maker_price 嚴格跳過：passive 價無效，不使用 last_price fallback"
        );
        None
    }
}

fn warn_skip_no_quote(
    is_long: bool,
    inputs: MakerPriceInputs,
    fallback_offset_bps: f64,
    strategy_name: &str,
    symbol: &str,
    tick: f64,
) -> Option<f64> {
    warn!(
        strategy = strategy_name,
        symbol = symbol,
        is_long = is_long,
        last_price = inputs.last_price,
        best_bid = ?inputs.best_bid,
        best_ask = ?inputs.best_ask,
        tick_size = tick,
        fallback_offset_bps = fallback_offset_bps,
        "maker_price strict skip: no usable side quote; no last_price fallback \
         / maker_price 嚴格跳過：無可用單側報價，不使用 last_price fallback"
    );
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Helper to build inputs with BBO present.
    /// 建構帶 BBO 的 inputs 輔助函式。
    fn inputs_with_bbo(last: f64, bid: f64, ask: f64, tick: f64) -> MakerPriceInputs {
        MakerPriceInputs {
            last_price: last,
            best_bid: Some(bid),
            best_ask: Some(ask),
            tick_size: Some(tick),
        }
    }

    /// Helper to build inputs without BBO (strict skip path).
    /// 建構無 BBO 的 inputs 輔助函式（嚴格跳過路徑）。
    fn inputs_no_bbo(last: f64, tick: Option<f64>) -> MakerPriceInputs {
        MakerPriceInputs {
            last_price: last,
            best_bid: None,
            best_ask: None,
            tick_size: tick,
        }
    }

    /// G7-09c Phase 1: Buy uses best_bid - buffer×tick (passive below ask).
    /// G7-09c Phase 1：買單使用 best_bid - buffer×tick（在 ask 之下被動掛單）。
    #[test]
    fn buy_uses_best_bid_minus_buffer_ticks() {
        // BTCUSDT-like: bid=29999.0 ask=30001.0 tick=0.1, buffer=1.
        // BTCUSDT 類：bid=29999.0 ask=30001.0 tick=0.1, buffer=1。
        let inputs = inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1);
        let price = compute_post_only_price(true, inputs, 1.0, 1, "test", "BTCUSDT")
            .expect("safe BBO should price");
        // Expected: 29999.0 - 1*0.1 = 29998.9 (strictly below ask 30001.0 → passive).
        // 預期 29999.0 - 0.1 = 29998.9（嚴格低於 ask → 被動）。
        assert!((price - 29_998.9).abs() < 1e-9, "got {price}");
    }

    /// G7-09c Phase 1: Sell uses best_ask + buffer×tick (passive above bid).
    /// G7-09c Phase 1：賣單使用 best_ask + buffer×tick（在 bid 之上被動掛單）。
    #[test]
    fn sell_uses_best_ask_plus_buffer_ticks() {
        let inputs = inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1);
        let price = compute_post_only_price(false, inputs, 1.0, 1, "test", "BTCUSDT")
            .expect("safe BBO should price");
        // Expected: 30001.0 + 1*0.1 = 30001.1 (strictly above bid → passive).
        // 預期 30001.0 + 0.1 = 30001.1（嚴格高於 bid → 被動）。
        assert!((price - 30_001.1).abs() < 1e-9, "got {price}");
    }

    /// buffer_ticks=0 sits exactly on the inside quote (still passive maker).
    /// buffer_ticks=0 掛在 inside quote 同價（仍為被動 maker）。
    #[test]
    fn buffer_zero_sits_on_inside_quote() {
        let inputs = inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1);
        let buy = compute_post_only_price(true, inputs, 1.0, 0, "test", "BTCUSDT")
            .expect("safe BBO should price");
        let sell = compute_post_only_price(false, inputs, 1.0, 0, "test", "BTCUSDT")
            .expect("safe BBO should price");
        assert!((buy - 29_999.0).abs() < 1e-9, "buy got {buy}");
        assert!((sell - 30_001.0).abs() < 1e-9, "sell got {sell}");
    }

    /// Strict skip when no BBO is available.
    /// 無 BBO 時嚴格跳過。
    #[test]
    fn skip_when_no_bbo() {
        let inputs = inputs_no_bbo(30_000.0, Some(0.1));
        let buy = compute_post_only_price(true, inputs, 1.0, 1, "test", "BTCUSDT");
        let sell = compute_post_only_price(false, inputs, 1.0, 1, "test", "BTCUSDT");
        assert!(buy.is_none(), "BUY must skip without a side quote");
        assert!(sell.is_none(), "SELL must skip without a side quote");
    }

    /// Strict skip when only tick_size is missing.
    /// 只有 tick_size 缺失時嚴格跳過。
    #[test]
    fn skip_when_only_tick_size_missing() {
        let inputs = MakerPriceInputs {
            last_price: 30_000.0,
            best_bid: Some(29_999.0),
            best_ask: Some(30_001.0),
            tick_size: None,
        };
        let price = compute_post_only_price(true, inputs, 1.0, 1, "test", "BTCUSDT");
        assert!(price.is_none(), "missing tick_size must skip");
    }

    /// A single best_bid is enough to price a passive buy.
    /// 單側 best_bid 足以為買單產生 passive 價。
    #[test]
    fn buy_uses_single_sided_bid() {
        let inputs = MakerPriceInputs {
            last_price: 30_000.0,
            best_bid: Some(29_999.0),
            best_ask: None,
            tick_size: Some(0.1),
        };
        let price = compute_post_only_price(true, inputs, 1.0, 1, "test", "BTCUSDT")
            .expect("single-sided bid should price buy");
        assert!((price - 29_998.9).abs() < 1e-9, "got {price}");
    }

    /// A single best_ask is enough to price a passive buy by staying below ask.
    /// 單側 best_ask 可讓買單掛在 ask 下方。
    #[test]
    fn buy_uses_single_sided_ask_minus_at_least_one_tick() {
        let inputs = MakerPriceInputs {
            last_price: 30_000.0,
            best_bid: None,
            best_ask: Some(30_001.0),
            tick_size: Some(0.1),
        };
        let price = compute_post_only_price(true, inputs, 1.0, 0, "test", "BTCUSDT")
            .expect("single-sided ask should price buy");
        assert!((price - 30_000.9).abs() < 1e-9, "got {price}");
    }

    /// Strict skip when crossed or locked book appears — defensive, treat as bad data.
    /// Crossed/locked book 嚴格跳過 — 防禦式視為髒資料。
    #[test]
    fn skip_when_crossed_book() {
        let inputs = inputs_with_bbo(30_000.0, 30_002.0, 30_001.0, 0.1);
        let price = compute_post_only_price(true, inputs, 1.0, 1, "test", "BTCUSDT");
        assert!(price.is_none(), "crossed book must skip");
    }

    /// Pathological huge buffer — skip rather than emit invalid price.
    /// 異常巨大 buffer — 跳過而非送出無效價。
    #[test]
    fn skip_when_buffer_pushes_price_negative() {
        // bid=0.5 tick=1.0 buffer=10 → 0.5 - 10 = -9.5 → skip.
        // bid=0.5 tick=1.0 buffer=10 → -9.5 → skip。
        let inputs = inputs_with_bbo(0.5, 0.5, 0.6, 1.0);
        let price = compute_post_only_price(true, inputs, 1.0, 10, "test", "TINYUSDT");
        assert!(price.is_none(), "invalid passive price must skip");
    }

    /// Sanity: with happy-path BBO inputs the price never crosses the book.
    /// 健全性檢查：happy-path BBO 輸入下，價格永不跨 book。
    #[test]
    fn happy_path_never_crosses_book() {
        let inputs = inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1);
        for buffer in 0u32..=5 {
            let buy = compute_post_only_price(true, inputs, 1.0, buffer, "test", "BTCUSDT")
                .expect("safe BBO should price buy");
            let sell = compute_post_only_price(false, inputs, 1.0, buffer, "test", "BTCUSDT")
                .expect("safe BBO should price sell");
            // Buy must be ≤ best_bid → ≤ best_ask. Sell must be ≥ best_ask → ≥ best_bid.
            // 買 ≤ best_bid → 必 ≤ ask；賣 ≥ best_ask → 必 ≥ bid。
            assert!(buy <= 29_999.0 + 1e-9, "buffer={buffer} buy={buy}");
            assert!(sell >= 30_001.0 - 1e-9, "buffer={buffer} sell={sell}");
            assert!(buy < sell, "buffer={buffer} buy {buy} >= sell {sell}");
        }
    }
}
