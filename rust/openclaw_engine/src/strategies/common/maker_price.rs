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
//!   When BBO or tick_size are unavailable (cold start / instrument cache
//!   miss), it falls back to the legacy `last_price ± offset_bps` formula
//!   and emits a `tracing::warn!` so operator can detect over-reliance on
//!   the fallback in production.
//!
//! MODULE_NOTE (中): 共用 `compute_post_only_price()`，由 ma_crossover /
//!   bb_breakout / grid_trading / bb_reversion 四策略呼叫。RCA `7f0e793`
//!   發現 4 天 178 筆 PostOnly 100% 被 Bybit 拒（`EC_PostOnlyWillTakeLiquidity`），
//!   原因為策略以 `ctx.price (last_price) ± offset_bps` 計限價；last_price ≠
//!   best_bid/ask，spread + book 陳舊性導致 BUY 落在 ask 以上、SELL 落在
//!   bid 以下，必跨 book → PostOnly 100% reject。本 helper 嚴格被動掛單：
//!     - Buy:  best_bid - buffer_ticks × tick_size
//!     - Sell: best_ask + buffer_ticks × tick_size
//!   當 BBO 或 tick_size 不可得（冷啟動 / instrument cache miss）時，回退至
//!   舊式 `last_price ± offset_bps` 公式並發 `tracing::warn!`，方便 operator
//!   偵測 fallback 在 production 過度被觸發。

use tracing::warn;

/// Inputs for `compute_post_only_price()` extracted from `TickContext` at
/// the call site so the helper stays pure (no `ctx` dependency cycle).
/// 從 `TickContext` 抽出參數呼叫本 helper，避免 helper 依賴 ctx 造成迴圈。
#[derive(Debug, Clone, Copy)]
pub struct MakerPriceInputs {
    /// Last traded price — used only as fallback when BBO unavailable.
    /// 最新成交價，僅在 BBO 不可得時 fallback 使用。
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
/// Fallback path: when BBO 或 tick_size 缺失，回退至 `last_price ± offset_bps`
/// 並 `tracing::warn!`。fallback 路徑保留是為了不讓冷啟動 / cache miss 阻擋下單，
/// 但 production 上應極少觸發；warn rate 高代表 BBO 管線斷線需排查。
pub fn compute_post_only_price(
    is_long: bool,
    inputs: MakerPriceInputs,
    fallback_offset_bps: f64,
    buffer_ticks: u32,
    strategy_name: &str,
    symbol: &str,
) -> f64 {
    // Happy path: both BBO and tick_size present + sane (>0).
    // 正常路徑：BBO 與 tick_size 皆存在且 > 0。
    if let (Some(bid), Some(ask), Some(tick)) =
        (inputs.best_bid, inputs.best_ask, inputs.tick_size)
    {
        if bid > 0.0 && ask > 0.0 && tick > 0.0 && ask >= bid {
            let offset = f64::from(buffer_ticks) * tick;
            let price = if is_long {
                // Buy limit BELOW best_bid (or at best_bid when buffer=0).
                // 買單掛 best_bid 之下（buffer=0 時為 best_bid 同價）。
                bid - offset
            } else {
                // Sell limit ABOVE best_ask (or at best_ask when buffer=0).
                // 賣單掛 best_ask 之上（buffer=0 時為 best_ask 同價）。
                ask + offset
            };
            // Defensive: never return ≤0 — in pathological inputs (huge buffer
            // vs tiny bid) fall back rather than emitting an invalid order.
            // 防禦：不回 ≤0 — 異常輸入（buffer 比 bid 大）走 fallback 而非送無效單。
            if price > 0.0 {
                return price;
            }
        }
    }

    // Fallback path: BBO/tick_size missing or pathological.
    // Emit a warn so operator can detect over-reliance on fallback in
    // production via log scraping. Use the same offset semantics as the
    // pre-fix algorithm so behaviour is recognisable to existing tests.
    // Fallback 路徑：BBO/tick_size 缺失或異常。發 warn 以利日誌追蹤。
    // offset 語義與 pre-fix 算法一致，方便既有測試辨識。
    let offset = fallback_offset_bps / 10_000.0;
    let price = if is_long {
        inputs.last_price * (1.0 - offset)
    } else {
        inputs.last_price * (1.0 + offset)
    };
    warn!(
        strategy = strategy_name,
        symbol = symbol,
        is_long = is_long,
        last_price = inputs.last_price,
        best_bid = ?inputs.best_bid,
        best_ask = ?inputs.best_ask,
        tick_size = ?inputs.tick_size,
        fallback_price = price,
        "G7-09c maker_price fallback: BBO/tick_size unavailable, using last_price ± offset_bps \
         / G7-09c maker_price 回退：BBO/tick_size 不可得，改用 last_price ± offset_bps"
    );
    price
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

    /// Helper to build inputs without BBO (cold-start path).
    /// 建構無 BBO 的 inputs 輔助函式（冷啟動路徑）。
    fn inputs_no_bbo(last: f64) -> MakerPriceInputs {
        MakerPriceInputs {
            last_price: last,
            best_bid: None,
            best_ask: None,
            tick_size: None,
        }
    }

    /// G7-09c Phase 1: Buy uses best_bid - buffer×tick (passive below ask).
    /// G7-09c Phase 1：買單使用 best_bid - buffer×tick（在 ask 之下被動掛單）。
    #[test]
    fn buy_uses_best_bid_minus_buffer_ticks() {
        // BTCUSDT-like: bid=29999.0 ask=30001.0 tick=0.1, buffer=1.
        // BTCUSDT 類：bid=29999.0 ask=30001.0 tick=0.1, buffer=1。
        let inputs = inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1);
        let price = compute_post_only_price(true, inputs, 1.0, 1, "test", "BTCUSDT");
        // Expected: 29999.0 - 1*0.1 = 29998.9 (strictly below ask 30001.0 → passive).
        // 預期 29999.0 - 0.1 = 29998.9（嚴格低於 ask → 被動）。
        assert!((price - 29_998.9).abs() < 1e-9, "got {price}");
    }

    /// G7-09c Phase 1: Sell uses best_ask + buffer×tick (passive above bid).
    /// G7-09c Phase 1：賣單使用 best_ask + buffer×tick（在 bid 之上被動掛單）。
    #[test]
    fn sell_uses_best_ask_plus_buffer_ticks() {
        let inputs = inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1);
        let price = compute_post_only_price(false, inputs, 1.0, 1, "test", "BTCUSDT");
        // Expected: 30001.0 + 1*0.1 = 30001.1 (strictly above bid → passive).
        // 預期 30001.0 + 0.1 = 30001.1（嚴格高於 bid → 被動）。
        assert!((price - 30_001.1).abs() < 1e-9, "got {price}");
    }

    /// buffer_ticks=0 sits exactly on the inside quote (still passive maker).
    /// buffer_ticks=0 掛在 inside quote 同價（仍為被動 maker）。
    #[test]
    fn buffer_zero_sits_on_inside_quote() {
        let inputs = inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1);
        let buy = compute_post_only_price(true, inputs, 1.0, 0, "test", "BTCUSDT");
        let sell = compute_post_only_price(false, inputs, 1.0, 0, "test", "BTCUSDT");
        assert!((buy - 29_999.0).abs() < 1e-9, "buy got {buy}");
        assert!((sell - 30_001.0).abs() < 1e-9, "sell got {sell}");
    }

    /// Fallback when BBO unavailable — uses last_price ± offset_bps.
    /// BBO 不可得時 fallback — 使用 last_price ± offset_bps。
    #[test]
    fn fallback_when_no_bbo_uses_last_price_offset() {
        let inputs = inputs_no_bbo(30_000.0);
        let buy = compute_post_only_price(true, inputs, 1.0, 1, "test", "BTCUSDT");
        let sell = compute_post_only_price(false, inputs, 1.0, 1, "test", "BTCUSDT");
        // 1 bps offset = 0.0001 → buy 30000 * 0.9999 = 29997.0, sell 30000 * 1.0001 = 30003.0.
        // 1 bps 偏移 = 0.0001。
        assert!((buy - 29_997.0).abs() < 1e-9, "buy got {buy}");
        assert!((sell - 30_003.0).abs() < 1e-9, "sell got {sell}");
    }

    /// Fallback when only tick_size missing — still goes to fallback path
    /// because we need all three (BBO + tick) to compute a precise passive price.
    /// 只有 tick_size 缺失時亦走 fallback — 必須三者俱全才能算精確被動價。
    #[test]
    fn fallback_when_only_tick_size_missing() {
        let inputs = MakerPriceInputs {
            last_price: 30_000.0,
            best_bid: Some(29_999.0),
            best_ask: Some(30_001.0),
            tick_size: None,
        };
        let price = compute_post_only_price(true, inputs, 1.0, 1, "test", "BTCUSDT");
        assert!((price - 29_997.0).abs() < 1e-9, "got {price}");
    }

    /// Fallback when crossed book (ask < bid) — defensive, treat as bad data.
    /// Crossed book（ask < bid）走 fallback — 防禦式，視為髒資料。
    #[test]
    fn fallback_when_crossed_book() {
        let inputs = inputs_with_bbo(30_000.0, 30_002.0, 30_001.0, 0.1);
        let price = compute_post_only_price(true, inputs, 1.0, 1, "test", "BTCUSDT");
        // Crossed → fallback → 30000 * 0.9999 = 29997.0.
        // Crossed → fallback → 29997.0。
        assert!((price - 29_997.0).abs() < 1e-9, "got {price}");
    }

    /// Pathological huge buffer — fallback rather than negative price.
    /// 異常巨大 buffer — fallback 而非負價。
    #[test]
    fn fallback_when_buffer_pushes_price_negative() {
        // bid=0.5 tick=1.0 buffer=10 → 0.5 - 10 = -9.5 → fallback.
        // bid=0.5 tick=1.0 buffer=10 → -9.5 → fallback。
        let inputs = inputs_with_bbo(0.5, 0.5, 0.6, 1.0);
        let price = compute_post_only_price(true, inputs, 1.0, 10, "test", "TINYUSDT");
        // Fallback uses last=0.5 with 1bps offset → 0.5 * 0.9999 ≈ 0.49995.
        // Fallback 用 last=0.5 + 1bps → 0.49995。
        assert!((price - 0.499_95).abs() < 1e-9, "got {price}");
    }

    /// Sanity: with happy-path BBO inputs the price never crosses the book.
    /// 健全性檢查：happy-path BBO 輸入下，價格永不跨 book。
    #[test]
    fn happy_path_never_crosses_book() {
        let inputs = inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1);
        for buffer in 0u32..=5 {
            let buy = compute_post_only_price(true, inputs, 1.0, buffer, "test", "BTCUSDT");
            let sell = compute_post_only_price(false, inputs, 1.0, buffer, "test", "BTCUSDT");
            // Buy must be ≤ best_bid → ≤ best_ask. Sell must be ≥ best_ask → ≥ best_bid.
            // 買 ≤ best_bid → 必 ≤ ask；賣 ≥ best_ask → 必 ≥ bid。
            assert!(buy <= 29_999.0 + 1e-9, "buffer={buffer} buy={buy}");
            assert!(sell >= 30_001.0 - 1e-9, "buffer={buffer} sell={sell}");
            assert!(buy < sell, "buffer={buffer} buy {buy} >= sell {sell}");
        }
    }
}
