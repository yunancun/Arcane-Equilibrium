//! BB Reversion Strategy V2 — Bollinger Band mean reversion + RSI filter.
//! BB 回歸策略 V2 — 布林帶均值回歸 + RSI 過濾。

use super::Strategy;
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;

pub struct BbReversion {
    active: bool,
    position: Option<bool>,
    last_trade_ms: u64,
    cooldown_ms: u64,
    default_qty: f64,
    // RC-07: Limit order support — Agent can switch from market to limit entries
    // RC-07：限價單支持 — Agent 可從市價切換為限價入場
    /// When true, entry orders use limit instead of market / 為 true 時入場用限價單
    pub use_limit: bool,
    /// Basis points inside the band for limit price offset / 限價偏移（基點，band 內側）
    pub limit_offset_bps: f64,
    // RC-04: Previous state for rejection rollback / 拒絕回滾用的先前狀態
    prev_position: Option<bool>,
    prev_last_trade_ms: u64,
}

impl BbReversion {
    pub fn new() -> Self {
        Self {
            active: true, position: None, last_trade_ms: 0, cooldown_ms: 600_000, default_qty: 1e9,
            use_limit: false, limit_offset_bps: 10.0,
            prev_position: None, prev_last_trade_ms: 0,
        }
    }

    /// Build an entry intent — may be limit or market depending on use_limit.
    /// 建構入場意圖 — 根據 use_limit 決定限價或市價單。
    fn make_entry_intent(&self, ctx: &TickContext, is_long: bool, conf: f64,
                         bb_lower: f64, bb_upper: f64) -> OrderIntent {
        let (order_type, limit_price) = if self.use_limit {
            // RC-07: Place limit order slightly inside the Bollinger band
            // RC-07：在布林帶內側略偏位置掛限價單
            let price = if is_long {
                // Buy near lower band: slightly above / 在下軌附近買入：略高於下軌
                bb_lower * (1.0 + self.limit_offset_bps / 10_000.0)
            } else {
                // Sell near upper band: slightly below / 在上軌附近賣出：略低於上軌
                bb_upper * (1.0 - self.limit_offset_bps / 10_000.0)
            };
            ("limit".to_string(), Some(price))
        } else {
            ("market".to_string(), None)
        };
        OrderIntent {
            symbol: ctx.symbol.clone(), is_long, qty: self.default_qty, confidence: conf,
            strategy: self.name().into(), order_type, limit_price,
        }
    }

    /// Build an exit intent — always market for guaranteed fills.
    /// 建構出場意圖 — 永遠使用市價單以確保成交。
    fn make_exit_intent(&self, ctx: &TickContext, is_long: bool, conf: f64) -> OrderIntent {
        OrderIntent {
            symbol: ctx.symbol.clone(), is_long, qty: self.default_qty, confidence: conf,
            strategy: self.name().into(), order_type: "market".into(), limit_price: None,
        }
    }
}

impl Strategy for BbReversion {
    fn name(&self) -> &str { "bb_reversion" }
    fn is_active(&self) -> bool { self.active }

    /// RC-04: Revert position and last_trade_ms on rejection.
    /// RC-04：拒絕時回滾 position 和 last_trade_ms。
    fn on_rejection(&mut self, _intent: &OrderIntent, _reason: &str) {
        self.position = self.prev_position;
        self.last_trade_ms = self.prev_last_trade_ms;
    }

    fn on_tick(&mut self, ctx: &TickContext) -> Vec<OrderIntent> {
        let ind = match &ctx.indicators { Some(i) => i, None => return vec![] };
        if self.last_trade_ms > 0 && ctx.timestamp_ms < self.last_trade_ms + self.cooldown_ms { return vec![]; }

        let bb = match &ind.bollinger { Some(b) => b, None => return vec![] };
        let rsi = ind.rsi_14.unwrap_or(50.0);

        // A4: Hurst regime boost — mean-reverting regime boosts reversion confidence
        // A4：Hurst 市场状态 — 均值回归型市场提升回归信心
        let hurst_boost: f64 = match &ind.hurst {
            Some(h) if h.regime == "mean_reverting" => 0.1,
            _ => 0.0,
        };

        // RC-04: Snapshot state before any mutation for rejection rollback.
        // RC-04：在任何變更前快照狀態，供拒絕回滾使用。
        self.prev_position = self.position;
        self.prev_last_trade_ms = self.last_trade_ms;

        let mut intents = Vec::new();
        match self.position {
            None => {
                // Entry: oversold long / 入場：超賣做多
                if bb.percent_b < 0.0 && rsi < 30.0 {
                    intents.push(self.make_entry_intent(
                        ctx, true, (0.6_f64 + hurst_boost).min(1.0), bb.lower, bb.upper,
                    ));
                    self.position = Some(true);
                    self.last_trade_ms = ctx.timestamp_ms;
                // Entry: overbought short / 入場：超買做空
                } else if bb.percent_b > 1.0 && rsi > 70.0 {
                    intents.push(self.make_entry_intent(
                        ctx, false, (0.6_f64 + hurst_boost).min(1.0), bb.lower, bb.upper,
                    ));
                    self.position = Some(false);
                    self.last_trade_ms = ctx.timestamp_ms;
                }
            }
            Some(is_long) => {
                // Exit: always market for guaranteed fills / 出場：永遠市價確保成交
                if bb.percent_b >= 0.2 && bb.percent_b <= 0.8 {
                    intents.push(self.make_exit_intent(ctx, !is_long, 0.5));
                    self.position = None;
                    self.last_trade_ms = ctx.timestamp_ms;
                }
            }
        }
        intents
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use openclaw_core::indicators::{BollingerResult, IndicatorSnapshot};

    fn ctx_bb(pct_b: f64, rsi: f64, ts: u64) -> TickContext {
        TickContext {
            symbol: "BTC".into(), price: 50000.0, timestamp_ms: ts,
            indicators: Some(IndicatorSnapshot {
                bollinger: Some(BollingerResult {
                    upper: 51000.0, middle: 50000.0, lower: 49000.0,
                    bandwidth: 0.04, percent_b: pct_b,
                }),
                rsi_14: Some(rsi), ..Default::default()
            }),
            signals: vec![], h0_allowed: true,
        }
    }

    #[test]
    fn test_long_oversold() {
        let mut s = BbReversion::new();
        let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        assert_eq!(i.len(), 1);
        assert!(i[0].is_long);
    }

    #[test]
    fn test_exit_mean() {
        let mut s = BbReversion::new();
        s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        let i = s.on_tick(&ctx_bb(0.5, 50.0, 700_000));
        assert_eq!(i.len(), 1);
    }

    // ── RC-07: Limit order tests / RC-07 限價單測試 ──

    #[test]
    fn test_limit_order_long() {
        // RC-07: use_limit=true, oversold entry produces limit order with correct price
        // RC-07：use_limit=true，超賣入場產生正確限價的限價單
        let mut s = BbReversion::new();
        s.use_limit = true;
        s.limit_offset_bps = 10.0; // 10 bps = 0.1%
        let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        assert_eq!(i.len(), 1);
        assert!(i[0].is_long);
        assert_eq!(i[0].order_type, "limit");
        // limit_price = lower * (1 + 10/10000) = 49000 * 1.001 = 49049.0
        let expected = 49000.0 * (1.0 + 10.0 / 10_000.0);
        assert!((i[0].limit_price.unwrap() - expected).abs() < 1e-6,
            "expected limit_price={}, got={}", expected, i[0].limit_price.unwrap());
    }

    #[test]
    fn test_limit_order_short() {
        // RC-07: use_limit=true, overbought entry produces limit order
        // RC-07：use_limit=true，超買入場產生限價單
        let mut s = BbReversion::new();
        s.use_limit = true;
        s.limit_offset_bps = 10.0;
        let i = s.on_tick(&ctx_bb(1.1, 75.0, 0));
        assert_eq!(i.len(), 1);
        assert!(!i[0].is_long);
        assert_eq!(i[0].order_type, "limit");
        // limit_price = upper * (1 - 10/10000) = 51000 * 0.999 = 50949.0
        let expected = 51000.0 * (1.0 - 10.0 / 10_000.0);
        assert!((i[0].limit_price.unwrap() - expected).abs() < 1e-6,
            "expected limit_price={}, got={}", expected, i[0].limit_price.unwrap());
    }

    #[test]
    fn test_market_order_default() {
        // RC-07: use_limit=false (default), entries produce market orders
        // RC-07：use_limit=false（默認），入場產生市價單
        let mut s = BbReversion::new();
        assert!(!s.use_limit); // verify default is false / 確認默認為 false
        let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        assert_eq!(i.len(), 1);
        assert_eq!(i[0].order_type, "market");
        assert!(i[0].limit_price.is_none());
    }

    #[test]
    fn test_exit_always_market() {
        // RC-07: Even with use_limit=true, exit orders are always market
        // RC-07：即使 use_limit=true，出場單永遠是市價單
        let mut s = BbReversion::new();
        s.use_limit = true;
        // Enter long with limit order / 限價入場做多
        let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        assert_eq!(i[0].order_type, "limit");
        // Exit at mean reversion / 均值回歸出場
        let i = s.on_tick(&ctx_bb(0.5, 50.0, 700_000));
        assert_eq!(i.len(), 1);
        assert_eq!(i[0].order_type, "market", "exit must always be market");
        assert!(i[0].limit_price.is_none(), "exit must have no limit_price");
    }
}
