//! Grid Trading Strategy V2 — OU dynamic spacing + fee floor.
//! 網格交易策略 V2 — OU 動態間距 + 手續費地板。
//!
//! Grid levels between lower/upper bounds. Buy on down-cross, sell on up-cross.
//! OU model: optimal spacing = σ/√θ with floor = 2× round-trip fee.

use super::Strategy;
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;

const DEFAULT_GRID_COUNT: usize = 10;
const DEFAULT_QTY_PER_GRID: f64 = 0.001;
const FEE_PCT: f64 = 0.00055; // one-way taker

pub struct GridTrading {
    active: bool,
    grid_levels: Vec<f64>,
    last_cross_idx: Option<usize>,
    net_inventory: f64,
    max_inventory: f64,
    last_trade_ms: u64,
    cooldown_ms: u64,
    qty_per_grid: f64,
    // OU parameters
    price_history: Vec<f64>,
    ou_lookback: usize,
}

impl GridTrading {
    pub fn new(lower: f64, upper: f64) -> Self {
        let mut levels = Vec::with_capacity(DEFAULT_GRID_COUNT);
        let step = (upper - lower) / (DEFAULT_GRID_COUNT as f64 - 1.0);
        for i in 0..DEFAULT_GRID_COUNT {
            levels.push(lower + step * i as f64);
        }
        Self {
            active: true,
            grid_levels: levels,
            last_cross_idx: None,
            net_inventory: 0.0,
            max_inventory: 5.0 * DEFAULT_QTY_PER_GRID,
            last_trade_ms: 0,
            cooldown_ms: 60_000,
            qty_per_grid: DEFAULT_QTY_PER_GRID,
            price_history: Vec::new(),
            ou_lookback: 100,
        }
    }

    /// Find nearest grid level index for a price.
    /// 找到價格最近的網格等級索引。
    fn nearest_grid_idx(&self, price: f64) -> usize {
        let mut best = 0;
        let mut best_dist = f64::MAX;
        for (i, &level) in self.grid_levels.iter().enumerate() {
            let d = (price - level).abs();
            if d < best_dist {
                best_dist = d;
                best = i;
            }
        }
        best
    }

    /// Update grid spacing based on OU model (V2).
    /// 基於 OU 模型更新網格間距 (V2)。
    pub fn update_ou_spacing(&mut self) {
        if self.price_history.len() < 20 { return; }
        let n = self.price_history.len().min(self.ou_lookback);
        let prices = &self.price_history[self.price_history.len() - n..];

        // Estimate OU parameters via regression: ΔX = a + b·X
        let changes: Vec<f64> = prices.windows(2).map(|w| w[1] - w[0]).collect();
        let x_lag: Vec<f64> = prices[..prices.len() - 1].to_vec();

        if changes.is_empty() { return; }
        let n_f = changes.len() as f64;
        let mean_x: f64 = x_lag.iter().sum::<f64>() / n_f;
        let mean_dx: f64 = changes.iter().sum::<f64>() / n_f;

        let mut num = 0.0;
        let mut den = 0.0;
        for i in 0..changes.len() {
            let dx = x_lag[i] - mean_x;
            num += dx * (changes[i] - mean_dx);
            den += dx * dx;
        }

        if den.abs() < 1e-15 { return; }
        let b = num / den;
        let theta = (-b).max(0.001); // mean-reversion speed

        let sigma = (changes.iter().map(|c| c * c).sum::<f64>() / n_f).sqrt();
        let mu = prices.iter().sum::<f64>() / prices.len() as f64;

        // Optimal spacing: σ/√θ, floored at 2× fee
        let ou_step = sigma / theta.sqrt();
        let fee_floor = 2.0 * FEE_PCT * mu;
        let step = ou_step.max(fee_floor);

        if step > 0.0 && mu > 0.0 {
            let lower = mu - step * (DEFAULT_GRID_COUNT as f64 / 2.0);
            let upper = mu + step * (DEFAULT_GRID_COUNT as f64 / 2.0);
            self.grid_levels.clear();
            for i in 0..DEFAULT_GRID_COUNT {
                self.grid_levels.push(lower + step * i as f64);
            }
        }
    }
}

impl Strategy for GridTrading {
    fn name(&self) -> &str { "grid_trading" }
    fn is_active(&self) -> bool { self.active }

    fn on_tick(&mut self, ctx: &TickContext) -> Vec<OrderIntent> {
        self.price_history.push(ctx.price);
        if self.price_history.len() > self.ou_lookback * 2 {
            self.price_history.drain(0..self.ou_lookback);
        }

        // Periodically update grid spacing
        if self.price_history.len() % 50 == 0 {
            self.update_ou_spacing();
        }

        if self.last_trade_ms > 0 && ctx.timestamp_ms < self.last_trade_ms + self.cooldown_ms { return vec![]; }

        let idx = self.nearest_grid_idx(ctx.price);
        if self.last_cross_idx == Some(idx) { return vec![]; }

        let prev_idx = self.last_cross_idx.unwrap_or(idx);
        self.last_cross_idx = Some(idx);

        let mut intents = Vec::new();

        if idx < prev_idx && self.net_inventory < self.max_inventory {
            // Price crossed down → buy
            intents.push(OrderIntent {
                symbol: ctx.symbol.clone(), is_long: true, qty: self.qty_per_grid,
                confidence: 0.5, strategy: self.name().into(),
                order_type: "market".into(), limit_price: None,
            });
            self.net_inventory += self.qty_per_grid;
            self.last_trade_ms = ctx.timestamp_ms;
        } else if idx > prev_idx && self.net_inventory > -self.max_inventory {
            // Price crossed up → sell
            intents.push(OrderIntent {
                symbol: ctx.symbol.clone(), is_long: false, qty: self.qty_per_grid,
                confidence: 0.5, strategy: self.name().into(),
                order_type: "market".into(), limit_price: None,
            });
            self.net_inventory -= self.qty_per_grid;
            self.last_trade_ms = ctx.timestamp_ms;
        }

        intents
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ctx(price: f64, ts: u64) -> TickContext {
        TickContext {
            symbol: "BTC".into(), price, timestamp_ms: ts,
            indicators: None, signals: vec![], h0_allowed: true,
        }
    }

    #[test]
    fn test_grid_creation() {
        let g = GridTrading::new(49000.0, 51000.0);
        assert_eq!(g.grid_levels.len(), DEFAULT_GRID_COUNT);
        assert!((g.grid_levels[0] - 49000.0).abs() < 0.01);
    }

    #[test]
    fn test_grid_buy_on_down_cross() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.on_tick(&ctx(50500.0, 0)); // initial
        let i = g.on_tick(&ctx(49500.0, 100_000)); // cross down
        assert!(!i.is_empty());
        assert!(i[0].is_long);
    }

    #[test]
    fn test_grid_sell_on_up_cross() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.on_tick(&ctx(49500.0, 0));
        let i = g.on_tick(&ctx(50500.0, 100_000));
        assert!(!i.is_empty());
        assert!(!i[0].is_long);
    }

    #[test]
    fn test_inventory_cap() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.net_inventory = g.max_inventory;
        g.on_tick(&ctx(50500.0, 0));
        let i = g.on_tick(&ctx(49500.0, 100_000));
        assert!(i.is_empty()); // can't buy more
    }

    #[test]
    fn test_ou_spacing_update() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        // Fill price history
        for i in 0..60 {
            g.price_history.push(50000.0 + (i as f64 * 0.1).sin() * 100.0);
        }
        g.update_ou_spacing();
        assert_eq!(g.grid_levels.len(), DEFAULT_GRID_COUNT);
    }
}
