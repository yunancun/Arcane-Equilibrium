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

/// Phase 1b close-maker spread guard. Wider books skip maker and go taker.
/// Phase 1b close-maker spread guard。超過此 spread 時跳過 maker，走 taker。
pub const CLOSE_MAKER_SPREAD_GUARD_BPS: f64 = 50.0;

/// Close-maker quote parameters selected by exit reason.
/// 依 exit reason 選出的 close-maker 掛價參數。
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CloseMakerPricePolicy {
    pub buffer_ticks: u32,
    pub offset_bps: f64,
    pub timeout_ms: u64,
}

/// Normalize strategy/risk close tags into their free-text exit reason.
/// 將 strategy/risk close tag 正規化為自由文字 exit reason。
pub fn canonical_close_maker_reason(reason: &str) -> &str {
    let mut current = reason.trim();
    loop {
        if let Some(rest) = current.strip_prefix("strategy_close:") {
            current = rest.trim();
            continue;
        }
        if let Some(rest) = current.strip_prefix("risk_close:") {
            current = rest.trim();
            continue;
        }
        return current;
    }
}

/// Positive close-maker whitelist from Phase 1b spec §4.3.
/// Phase 1b spec §4.3 的 close-maker 正白名單。
pub fn close_maker_price_policy(exit_reason: &str) -> Option<CloseMakerPricePolicy> {
    let reason = canonical_close_maker_reason(exit_reason);
    match reason {
        "grid_close_short" | "grid_close_long" | "bb_mean_revert" | "ma_reverse_cross"
        | "bw_squeeze" | "pctb_revert" => Some(CloseMakerPricePolicy {
            buffer_ticks: 1,
            offset_bps: 0.5,
            // CALIBRATION-2026-05-18: 30_000 → 90_000 per phase_1b_calibration_cell_selection
            // _report.md G-AB-01-C90 (fill 70.8% / saving +3.37 bps simulated, vs 30s baseline
            // 58.3% / 3.34 bps). Sweep dominant axis = timeout_ms. phys_lock family timeout
            // 不變 (15s/10s), 因 sweep top-2 都 grid family. Real fill verification via 24h
            // demo observation post-deploy (E2 caveat: BBO-cross-proxy systematically optimistic).
            timeout_ms: 90_000,
        }),
        "phys_lock_gate4_giveback" => Some(CloseMakerPricePolicy {
            buffer_ticks: 1,
            offset_bps: 0.5,
            timeout_ms: 15_000,
        }),
        "phys_lock_gate4_stale_roc_neg" => Some(CloseMakerPricePolicy {
            buffer_ticks: 1,
            offset_bps: 0.5,
            timeout_ms: 10_000,
        }),
        _ => None,
    }
}

/// Explicit market-only close reasons from the Phase 1b negative whitelist.
/// Phase 1b 負白名單中明確保留 market 的 close reason。
pub fn is_close_maker_market_only_reason(exit_reason: &str) -> bool {
    if close_maker_price_policy(exit_reason).is_some() {
        return false;
    }

    let reason = canonical_close_maker_reason(exit_reason);
    let lower = reason.to_ascii_lowercase();
    let raw_lower = exit_reason.trim().to_ascii_lowercase();

    lower.starts_with("hard stop")
        || lower.starts_with("trailing stop")
        || lower.starts_with("time stop")
        || lower.starts_with("dynamic stop")
        || lower.starts_with("fast_track")
        || lower.starts_with("halt_session")
        || lower.starts_with("take profit")
        || lower.starts_with("cost edge")
        || lower.starts_with("daily loss")
        || lower.starts_with("drawdown")
        || lower.starts_with("consecutive loss")
        || lower.starts_with("bybit_sync")
        || lower.starts_with("orphan_")
        || lower.starts_with("dust_frozen")
        || lower == "trailing_stop"
        || lower == "ipc_close_all"
        || lower == "ipc_close_symbol"
        || raw_lower.contains("/operator/close_position")
        || raw_lower.contains("operator override")
        || raw_lower.contains("shutdown")
        || raw_lower.contains("cancel_token")
        || raw_lower.contains("circuit breaker")
        || raw_lower.contains("authorization")
        || raw_lower.contains("auth expiry")
}

/// Whether a close reason is in the positive maker-first whitelist.
/// close reason 是否在 maker-first 正白名單。
pub fn is_close_maker_positive_reason(exit_reason: &str) -> bool {
    close_maker_price_policy(exit_reason).is_some()
}

/// Compute a strictly passive close-maker limit price.
///
/// `position_is_long=true` means the close order is a SELL, so this helper
/// reuses `compute_post_only_price(is_long=false, ...)`. `position_is_long=false`
/// means the close order is a BUY.
///
/// 計算嚴格被動的 close-maker 限價。多倉平倉是 SELL，因此反向呼叫
/// `compute_post_only_price(is_long=false, ...)`；空倉平倉則反向為 BUY。
pub fn compute_close_limit_price(
    position_is_long: bool,
    inputs: MakerPriceInputs,
    policy: CloseMakerPricePolicy,
    strategy_name: &str,
    symbol: &str,
) -> Option<f64> {
    let bid = inputs.best_bid.filter(|v| v.is_finite() && *v > 0.0);
    let ask = inputs.best_ask.filter(|v| v.is_finite() && *v > 0.0);

    let mut buffer_ticks = policy.buffer_ticks.max(1);
    if let (Some(bid), Some(ask)) = (bid, ask) {
        if ask <= bid {
            warn!(
                strategy = strategy_name,
                symbol = symbol,
                position_is_long = position_is_long,
                best_bid = bid,
                best_ask = ask,
                "close_maker strict skip: locked/crossed book \
                 / close_maker 嚴格跳過：locked/crossed book"
            );
            return None;
        }
        let mid = (bid + ask) * 0.5;
        let spread_bps = ((ask - bid) / mid) * 10_000.0;
        if spread_bps.is_finite() && spread_bps > CLOSE_MAKER_SPREAD_GUARD_BPS {
            warn!(
                strategy = strategy_name,
                symbol = symbol,
                position_is_long = position_is_long,
                spread_bps = spread_bps,
                guard_bps = CLOSE_MAKER_SPREAD_GUARD_BPS,
                "close_maker strict skip: spread exceeds guard \
                 / close_maker 嚴格跳過：spread 超過 guard"
            );
            return None;
        }

        if let Some(tick) = inputs.tick_size.filter(|v| v.is_finite() && *v > 0.0) {
            let half_spread = (ask - bid) * 0.5;
            let required_ticks = (half_spread / tick).ceil();
            if required_ticks.is_finite() && required_ticks > f64::from(buffer_ticks) {
                if required_ticks > f64::from(u32::MAX) {
                    warn!(
                        strategy = strategy_name,
                        symbol = symbol,
                        tick_size = tick,
                        half_spread = half_spread,
                        "close_maker strict skip: small-tick widening overflow \
                         / close_maker 嚴格跳過：small-tick buffer 擴張溢出"
                    );
                    return None;
                }
                buffer_ticks = required_ticks as u32;
            }
        }
    }

    compute_post_only_price(
        !position_is_long,
        inputs,
        policy.offset_bps,
        buffer_ticks,
        strategy_name,
        symbol,
    )
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
    use crate::tick_pipeline::build_risk_close_tag;
    use std::borrow::Cow;

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

    #[test]
    fn close_policy_accepts_positive_whitelist_with_prefixes() {
        let positives = [
            Cow::Borrowed("grid_close_short"),
            Cow::Borrowed("strategy_close:grid_close_long"),
            Cow::Borrowed("bb_mean_revert"),
            Cow::Owned(build_risk_close_tag("phys_lock_gate4_giveback")),
            Cow::Owned(build_risk_close_tag("phys_lock_gate4_stale_roc_neg")),
            Cow::Borrowed("strategy_close:ma_reverse_cross"),
            Cow::Borrowed("bw_squeeze"),
            Cow::Borrowed("pctb_revert"),
        ];

        for reason in positives {
            assert!(
                is_close_maker_positive_reason(reason.as_ref()),
                "{reason} must be close-maker eligible"
            );
            assert!(
                !is_close_maker_market_only_reason(reason.as_ref()),
                "{reason} must not be classified market-only"
            );
        }
    }

    #[test]
    fn close_policy_rejects_negative_whitelist_and_unknown() {
        let market_only = [
            "risk_close:HARD STOP: loss",
            "risk_close:TRAILING STOP: peak",
            "risk_close:TIME STOP: age",
            "risk_close:DYNAMIC STOP: atr",
            "risk_close:fast_track_reduce_half",
            "risk_close:halt_session:daily_loss",
            "TAKE PROFIT: pnl 2% >= 1%",
            "COST EDGE: ratio 0.90 >= 0.80",
            "DAILY LOSS",
            "DRAWDOWN",
            "CONSECUTIVE LOSS",
            "bybit_sync",
            "orphan_recovery",
            "dust_frozen",
            "trailing_stop",
            "ipc_close_all",
            "risk_close:ipc_close_symbol",
            "engine shutdown",
            "authorization expired",
            "circuit breaker",
        ];

        for reason in market_only {
            assert!(
                is_close_maker_market_only_reason(reason),
                "{reason} must remain market-only"
            );
            assert!(
                !is_close_maker_positive_reason(reason),
                "{reason} must not be close-maker eligible"
            );
        }
        assert!(
            close_maker_price_policy("future_unknown_exit").is_none(),
            "unknown exits fail closed by absence from the positive whitelist"
        );
    }

    #[test]
    fn close_limit_price_inverts_direction_and_uses_timeout_policy() {
        let inputs = inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1);
        let policy = close_maker_price_policy("grid_close_long").expect("grid close policy");
        // CALIBRATION-2026-05-18: grid family timeout_ms updated 30_000 → 90_000
        // per phase_1b_calibration_cell_selection_report.md G-AB-01-C90.
        assert_eq!(policy.timeout_ms, 90_000);

        let long_close_sell =
            compute_close_limit_price(true, inputs, policy, "grid_trading", "BTCUSDT")
                .expect("long close should price as passive sell");
        assert!((long_close_sell - 30_002.0).abs() < 1e-9);

        let short_close_buy =
            compute_close_limit_price(false, inputs, policy, "grid_trading", "BTCUSDT")
                .expect("short close should price as passive buy");
        assert!((short_close_buy - 29_998.0).abs() < 1e-9);

        assert_eq!(
            close_maker_price_policy("phys_lock_gate4_giveback")
                .expect("giveback policy")
                .timeout_ms,
            15_000
        );
        assert_eq!(
            close_maker_price_policy("phys_lock_gate4_stale_roc_neg")
                .expect("stale ROC policy")
                .timeout_ms,
            10_000
        );
    }

    #[test]
    fn close_limit_price_spread_guard_strict_skips() {
        let inputs = inputs_with_bbo(100.0, 99.0, 100.0, 0.1);
        let policy = close_maker_price_policy("grid_close_long").expect("policy");

        let price = compute_close_limit_price(true, inputs, policy, "grid_trading", "WIDEUSDT");

        assert!(
            price.is_none(),
            "spread above 50 bps must strict-skip to market fallback"
        );
    }

    #[test]
    fn close_limit_price_small_tick_widens_without_crossing() {
        let inputs = inputs_with_bbo(0.010010, 0.010000, 0.010020, 0.000001);
        let policy = close_maker_price_policy("pctb_revert").expect("policy");

        let sell = compute_close_limit_price(true, inputs, policy, "bb_breakout", "1000BONKUSDT")
            .expect("small-tick close should widen instead of crossing");

        assert!(
            (sell - 0.010030).abs() < 1e-12,
            "half-spread 10 ticks should widen sell close to ask + 10 ticks, got {sell}"
        );
        assert!(
            sell > inputs.best_ask.unwrap(),
            "widened sell must remain strictly passive"
        );
    }
}
