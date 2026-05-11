//! Shared strategy test harness.
//! 策略測試共用 harness。
//!
//! Strategy tests used to hand-build `TickContext` in every file. This Module
//! gives tests one Interface for common context/position setup while keeping
//! production strategy code untouched.
//! 過去各策略測試手工構造 `TickContext`。本 Module 集中常見 context/position
//! setup，production strategy code 不受影響。

use crate::paper_state::PaperPosition;
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;
use openclaw_core::indicators::IndicatorSnapshot;

pub(crate) struct StrategyHarness {
    symbol: &'static str,
    price: f64,
    timestamp_ms: u64,
    indicators: Option<IndicatorSnapshot>,
    position_state: Option<PaperPosition>,
    is_pinned: bool,
}

impl StrategyHarness {
    pub(crate) fn new(symbol: &'static str) -> Self {
        Self {
            symbol,
            price: 50_000.0,
            timestamp_ms: 0,
            indicators: None,
            position_state: None,
            is_pinned: true,
        }
    }

    pub(crate) fn price(mut self, price: f64) -> Self {
        self.price = price;
        self
    }

    pub(crate) fn timestamp_ms(mut self, timestamp_ms: u64) -> Self {
        self.timestamp_ms = timestamp_ms;
        self
    }

    pub(crate) fn indicators(mut self, indicators: IndicatorSnapshot) -> Self {
        self.indicators = Some(indicators);
        self
    }

    pub(crate) fn position_state(mut self, position: PaperPosition) -> Self {
        self.position_state = Some(position);
        self
    }

    pub(crate) fn is_pinned(mut self, is_pinned: bool) -> Self {
        self.is_pinned = is_pinned;
        self
    }

    pub(crate) fn build(self) -> TickContext<'static> {
        let indicators = self
            .indicators
            .map(|v| Box::leak(Box::new(v)) as &'static IndicatorSnapshot);
        let position_state = self
            .position_state
            .map(|v| Box::leak(Box::new(v)) as &'static PaperPosition);
        TickContext {
            symbol: self.symbol,
            price: self.price,
            timestamp_ms: self.timestamp_ms,
            indicators,
            indicators_5m: None,
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
            open_interest: None,
            best_bid: None,
            best_ask: None,
            tick_size: None,
            alpha_surface_ref: &EMPTY_ALPHA_SURFACE,
            position_state,
            is_pinned: self.is_pinned,
        }
    }

    pub(crate) fn paper_position(
        symbol: &str,
        is_long: bool,
        owner_strategy: &str,
    ) -> PaperPosition {
        PaperPosition {
            symbol: symbol.to_string(),
            is_long,
            qty: 1810.0,
            entry_price: 0.015,
            best_price: 0.015,
            entry_fee: 0.0,
            entry_ts_ms: 0,
            unrealized_pnl: 0.0,
            entry_context_id: String::new(),
            owner_strategy: owner_strategy.to_string(),
            entry_notional: 1810.0 * 0.015,
            max_favorable_pnl_pct: 0.0,
            peak_reached_ts_ms: 0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn harness_builds_position_and_pinned_tick_context() {
        let position = StrategyHarness::paper_position("BTC", true, "ma_crossover");
        let ctx = StrategyHarness::new("BTC")
            .price(42_000.0)
            .timestamp_ms(123)
            .position_state(position)
            .is_pinned(false)
            .build();

        assert_eq!(ctx.symbol, "BTC");
        assert_eq!(ctx.price, 42_000.0);
        assert_eq!(ctx.timestamp_ms, 123);
        assert!(!ctx.is_pinned);
        assert_eq!(ctx.position_state.unwrap().owner_strategy, "ma_crossover");
    }
}
