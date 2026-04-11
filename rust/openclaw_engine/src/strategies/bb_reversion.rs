//! BB Reversion Strategy V2 — Bollinger Band mean reversion + RSI filter.
//! BB 回歸策略 V2 — 布林帶均值回歸 + RSI 過濾。
//!
//! MODULE_NOTE (EN): Mean-reversion entries at Bollinger Band extremes with
//!   RSI oversold/overbought confirmation. Exits on band middle touch or time stop.
//! MODULE_NOTE (中): 在布林帶極端值處均值回歸入場，RSI 超賣/超買確認。
//!   觸及帶中線或時間止損出場。

use std::collections::HashMap;

use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;
use serde::{Deserialize, Serialize};
use tracing::info;

/// Tunable parameters for BB Reversion strategy (Phase 3a).
/// BB 回歸策略的可調參數。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BbReversionParams {
    pub cooldown_ms: u64,
    pub default_qty: f64,
    pub use_limit: bool,
    pub limit_offset_bps: f64,
}

impl Default for BbReversionParams {
    fn default() -> Self {
        Self {
            cooldown_ms: 600_000,
            default_qty: 1e9,
            use_limit: false,
            limit_offset_bps: 10.0,
        }
    }
}

impl StrategyParams for BbReversionParams {
    fn param_ranges() -> Vec<ParamRange> {
        vec![
            ParamRange {
                name: "cooldown_ms".into(),
                min: 60_000.0,
                max: 3_600_000.0,
                step: Some(60_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "default_qty".into(),
                min: 0.001,
                max: 1e12,
                step: None,
                agent_adjustable: false,
                db_persisted: true,
            },
            // GAP-9: use_limit / limit_offset_bps removed from agent-tunable
            // ranges. Paper engine has no order-book sim and silently degrades
            // limit→market, so enabling these would corrupt PnL accounting.
            // Re-add when paper engine grows a real limit-order matcher.
            // GAP-9：use_limit/limit_offset_bps 從可調列表移除（paper 無撮合）。
        ]
    }

    fn validate(&self) -> Result<(), String> {
        if self.cooldown_ms < 60_000 {
            return Err("cooldown_ms must be >= 60s".into());
        }
        if self.limit_offset_bps < 0.0 || self.limit_offset_bps > 200.0 {
            return Err("limit_offset_bps must be in [0, 200]".into());
        }
        Ok(())
    }
}

pub struct BbReversion {
    active: bool,
    /// Per-symbol position tracking: symbol → is_long direction.
    /// 每幣種獨立持倉追蹤：symbol → 多空方向。
    positions: HashMap<String, bool>,
    /// Per-symbol last trade timestamp for cooldown.
    /// 每幣種最後交易時間戳（用於冷卻）。
    last_trade_ms: HashMap<String, u64>,
    pub(crate) cooldown_ms: u64,
    default_qty: f64,
    // RC-07: Limit order support — Agent can switch from market to limit entries
    // RC-07：限價單支持 — Agent 可從市價切換為限價入場
    /// When true, entry orders use limit instead of market / 為 true 時入場用限價單
    pub use_limit: bool,
    /// Basis points inside the band for limit price offset / 限價偏移（基點，band 內側）
    pub limit_offset_bps: f64,
    // RC-04: Per-symbol previous state for rejection rollback / 每幣種拒絕回滾用的先前狀態
    prev_position: HashMap<String, Option<bool>>,
    prev_last_trade_ms: HashMap<String, u64>,
    /// CONF-D: Multiplier applied to emitted intent.confidence (default 1.0, range [0,2]).
    conf_scale: f64,
}

impl BbReversion {
    pub fn new() -> Self {
        Self {
            active: true,
            positions: HashMap::new(),
            last_trade_ms: HashMap::new(),
            cooldown_ms: 600_000,
            default_qty: 1e9,
            use_limit: false,
            limit_offset_bps: 10.0,
            prev_position: HashMap::new(),
            prev_last_trade_ms: HashMap::new(),
            conf_scale: 1.0,
        }
    }

    /// Phase 3a: Update tunable parameters.
    pub fn update_params(&mut self, params: BbReversionParams) -> Result<(), String> {
        params.validate()?;
        self.cooldown_ms = params.cooldown_ms;
        self.default_qty = params.default_qty;
        // GAP-9: paper engine cannot honor limit orders (no order-book sim).
        // Force market mode regardless of incoming param to keep PnL faithful.
        // GAP-9：paper 模式無法支援限價單，強制 market。
        if params.use_limit {
            tracing::warn!(
                strategy = "bb_reversion",
                "use_limit=true ignored: paper engine has no limit-order sim (GAP-9)"
            );
        }
        self.use_limit = false;
        self.limit_offset_bps = params.limit_offset_bps;
        info!(strategy = "bb_reversion", "params updated / 參數已更新");
        Ok(())
    }

    /// Phase 3a: Get current tunable parameters.
    pub fn get_params(&self) -> BbReversionParams {
        BbReversionParams {
            cooldown_ms: self.cooldown_ms,
            default_qty: self.default_qty,
            use_limit: self.use_limit,
            limit_offset_bps: self.limit_offset_bps,
        }
    }

    /// Build an entry intent — may be limit or market depending on use_limit.
    /// 建構入場意圖 — 根據 use_limit 決定限價或市價單。
    fn make_entry_intent(
        &self,
        ctx: &TickContext,
        is_long: bool,
        conf: f64,
        bb_lower: f64,
        bb_upper: f64,
    ) -> OrderIntent {
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
        // CONF-D: scale entry confidence
        let scaled = (conf * self.conf_scale).clamp(0.0, 1.0);
        OrderIntent {
            symbol: ctx.symbol.clone(),
            is_long,
            qty: self.default_qty,
            confidence: scaled,
            strategy: self.name().into(),
            order_type,
            limit_price,
        }
    }

}

impl Strategy for BbReversion {
    fn name(&self) -> &str {
        "bb_reversion"
    }
    fn is_active(&self) -> bool {
        self.active
    }
    fn set_active(&mut self, active: bool) {
        self.active = active;
    }

    /// RC-04: Revert per-symbol position and last_trade_ms on rejection.
    /// RC-04：拒絕時回滾該幣種的 position 和 last_trade_ms。
    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        let sym = &intent.symbol;
        if let Some(prev) = self.prev_position.get(sym) {
            match prev {
                Some(b) => { self.positions.insert(sym.clone(), *b); }
                None => { self.positions.remove(sym); }
            }
        }
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 { self.last_trade_ms.remove(sym); } else { self.last_trade_ms.insert(sym.clone(), ts); }
        }
    }

    fn on_external_close(&mut self, symbol: &str) {
        self.positions.remove(symbol);
    }

    fn on_tick(&mut self, ctx: &TickContext) -> Vec<StrategyAction> {
        let ind = match &ctx.indicators {
            Some(i) => i,
            None => return vec![],
        };
        let last_ms = self.last_trade_ms.get(&ctx.symbol).copied().unwrap_or(0);
        if last_ms > 0 && ctx.timestamp_ms < last_ms + self.cooldown_ms {
            return vec![];
        }

        let bb = match &ind.bollinger {
            Some(b) => b,
            None => return vec![],
        };
        let rsi = ind.rsi_14.unwrap_or(50.0);

        // A4: Hurst regime boost — mean-reverting regime boosts reversion confidence
        // A4：Hurst 市场状态 — 均值回归型市场提升回归信心
        let hurst_boost: f64 = match &ind.hurst {
            Some(h) if h.regime == "mean_reverting" => 0.1,
            _ => 0.0,
        };

        // RC-04: Snapshot per-symbol state before any mutation for rejection rollback.
        // RC-04：在任何變更前快照該幣種狀態，供拒絕回滾使用。
        self.prev_position.insert(ctx.symbol.clone(), self.positions.get(&ctx.symbol).copied());
        self.prev_last_trade_ms.insert(ctx.symbol.clone(), last_ms);

        let mut intents = Vec::new();
        match self.positions.get(&ctx.symbol).copied() {
            None => {
                // Entry: oversold long / 入場：超賣做多
                if bb.percent_b < 0.0 && rsi < 30.0 {
                    intents.push(StrategyAction::Open(self.make_entry_intent(
                        ctx,
                        true,
                        (0.6_f64 + hurst_boost).min(1.0),
                        bb.lower,
                        bb.upper,
                    )));
                    self.positions.insert(ctx.symbol.clone(), true);
                    self.last_trade_ms.insert(ctx.symbol.clone(), ctx.timestamp_ms);
                // Entry: overbought short / 入場：超買做空
                } else if bb.percent_b > 1.0 && rsi > 70.0 {
                    intents.push(StrategyAction::Open(self.make_entry_intent(
                        ctx,
                        false,
                        (0.6_f64 + hurst_boost).min(1.0),
                        bb.lower,
                        bb.upper,
                    )));
                    self.positions.insert(ctx.symbol.clone(), false);
                    self.last_trade_ms.insert(ctx.symbol.clone(), ctx.timestamp_ms);
                }
            }
            Some(_is_long) => {
                // Exit: %B returns to [0.2, 0.8] = textbook mean-reversion target reached.
                // Wider than exact 0.5 to handle crypto mean-overshoot.
                // 出場：%B 回到 [0.2, 0.8] = 教科書均值回歸目標。比精確 0.5 更寬以應對加密貨幣超調。
                if bb.percent_b >= 0.2 && bb.percent_b <= 0.8 {
                    let exit_conf = (0.55_f64 + hurst_boost).clamp(0.4, 0.8);
                    intents.push(StrategyAction::Close {
                        symbol: ctx.symbol.clone(),
                        confidence: exit_conf,
                        reason: "bb_mean_revert".into(),
                    });
                    self.positions.remove(&ctx.symbol);
                    self.last_trade_ms.insert(ctx.symbol.clone(), ctx.timestamp_ms);
                }
            }
        }
        intents
    }

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let params: BbReversionParams = serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(params)
    }

    fn get_params_json(&self) -> String {
        serde_json::to_string(&self.get_params()).unwrap_or_default()
    }

    fn param_ranges_json(&self) -> String {
        serde_json::to_string(&BbReversionParams::param_ranges()).unwrap_or_default()
    }

    fn conf_scale(&self) -> f64 {
        self.conf_scale
    }
    fn set_conf_scale(&mut self, scale: f64) {
        self.conf_scale = scale.clamp(0.0, 2.0);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use openclaw_core::indicators::{BollingerResult, IndicatorSnapshot};

    fn ctx_bb(pct_b: f64, rsi: f64, ts: u64) -> TickContext {
        TickContext {
            symbol: "BTC".into(),
            price: 50000.0,
            timestamp_ms: ts,
            indicators: Some(IndicatorSnapshot {
                bollinger: Some(BollingerResult {
                    upper: 51000.0,
                    middle: 50000.0,
                    lower: 49000.0,
                    bandwidth: 0.04,
                    percent_b: pct_b,
                }),
                rsi_14: Some(rsi),
                ..Default::default()
            }),
            signals: vec![],
            h0_allowed: true,
        }
    }

    #[test]
    fn test_long_oversold() {
        let mut s = BbReversion::new();
        let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        }
    }

    #[test]
    fn test_exit_mean() {
        let mut s = BbReversion::new();
        s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        let i = s.on_tick(&ctx_bb(0.5, 50.0, 700_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close { reason, .. } => assert_eq!(reason, "bb_mean_revert"),
            other => panic!("expected StrategyAction::Close, got {:?}", other),
        }
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
        let intent = match &i[0] {
            StrategyAction::Open(intent) => intent,
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        };
        assert!(intent.is_long);
        assert_eq!(intent.order_type, "limit");
        // limit_price = lower * (1 + 10/10000) = 49000 * 1.001 = 49049.0
        let expected = 49000.0 * (1.0 + 10.0 / 10_000.0);
        assert!(
            (intent.limit_price.unwrap() - expected).abs() < 1e-6,
            "expected limit_price={}, got={}",
            expected,
            intent.limit_price.unwrap()
        );
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
        let intent = match &i[0] {
            StrategyAction::Open(intent) => intent,
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        };
        assert!(!intent.is_long);
        assert_eq!(intent.order_type, "limit");
        // limit_price = upper * (1 - 10/10000) = 51000 * 0.999 = 50949.0
        let expected = 51000.0 * (1.0 - 10.0 / 10_000.0);
        assert!(
            (intent.limit_price.unwrap() - expected).abs() < 1e-6,
            "expected limit_price={}, got={}",
            expected,
            intent.limit_price.unwrap()
        );
    }

    #[test]
    fn test_market_order_default() {
        // RC-07: use_limit=false (default), entries produce market orders
        // RC-07：use_limit=false（默認），入場產生市價單
        let mut s = BbReversion::new();
        assert!(!s.use_limit); // verify default is false / 確認默認為 false
        let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        assert_eq!(i.len(), 1);
        let intent = match &i[0] {
            StrategyAction::Open(intent) => intent,
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        };
        assert_eq!(intent.order_type, "market");
        assert!(intent.limit_price.is_none());
    }

    #[test]
    fn test_exit_always_market() {
        // RC-07: Even with use_limit=true, exit orders are always market
        // RC-07：即使 use_limit=true，出場單永遠是市價單
        // With StrategyAction::Close, exit is no longer an OrderIntent —
        // it's a Close action that the pipeline handles directly.
        // 使用 StrategyAction::Close 後，出場不再是 OrderIntent。
        let mut s = BbReversion::new();
        s.use_limit = true;
        // Enter long with limit order / 限價入場做多
        let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        let entry_intent = match &i[0] {
            StrategyAction::Open(intent) => intent,
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        };
        assert_eq!(entry_intent.order_type, "limit");
        // Exit at mean reversion / 均值回歸出場
        let i = s.on_tick(&ctx_bb(0.5, 50.0, 700_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close { reason, .. } => {
                assert_eq!(reason, "bb_mean_revert", "exit must be a Close action");
            }
            other => panic!("expected StrategyAction::Close, got {:?}", other),
        }
    }

    #[test]
    fn test_bb_rev_param_ranges() {
        assert!(!BbReversionParams::param_ranges().is_empty());
    }

    #[test]
    fn test_bb_rev_validate() {
        assert!(BbReversionParams::default().validate().is_ok());
        assert!(BbReversionParams {
            cooldown_ms: 1000,
            ..Default::default()
        }
        .validate()
        .is_err());
    }

    #[test]
    fn test_bb_rev_update_roundtrip() {
        let mut s = BbReversion::new();
        let p = BbReversionParams {
            use_limit: true, // GAP-9: should be coerced to false
            limit_offset_bps: 20.0,
            ..Default::default()
        };
        assert!(s.update_params(p).is_ok());
        assert!(
            !s.get_params().use_limit,
            "GAP-9: use_limit must be coerced to false (paper has no limit sim)"
        );
        assert!((s.get_params().limit_offset_bps - 20.0).abs() < 0.01);
    }
}
