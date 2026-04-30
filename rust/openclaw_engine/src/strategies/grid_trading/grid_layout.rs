//! Grid Trading layout — grid levels, health check, rebalance, OU spacing.
//! Grid Trading 佈局 — 網格層級、健康檢查、再平衡、OU 間距。
//!
//! MODULE_NOTE (EN): Split out of `strategies/grid_trading.rs` by GRID-TRADING-MOD-SPLIT-1
//!   (2026-04-23) to honour CLAUDE.md §九's 1200-line hard cap (pre-split 1729 lines).
//!   Contains grid-layout concerns: nearest level lookup, bounds-based health
//!   check (Healthy / OutOfRange / NeedsRebalance), grid rebalance around a
//!   new anchor price, OU-model optimal step computation, and periodic OU
//!   spacing refresh. All logic / signatures preserved byte-identical to
//!   pre-split.
//! MODULE_NOTE (中)：GRID-TRADING-MOD-SPLIT-1（2026-04-23）由
//!   `strategies/grid_trading.rs` 拆出以遵守 CLAUDE.md §九 1200 行硬上限
//!   （拆前 1729 行）。本檔包含網格佈局相關：最近層級查找、基於邊界的健康
//!   檢查（Healthy / OutOfRange / NeedsRebalance）、以新錨定價格為中心的
//!   再平衡、OU 模型最佳步長計算、以及週期性 OU 間距刷新。所有邏輯 / 簽名
//!   與拆前逐字節相同。

use super::{GridHealth, GridTrading};
use crate::strategies::grid_helpers::{self, GridSpacingMode};

impl GridTrading {
    /// Find nearest grid level index for a price in a given symbol's grid.
    /// 找到指定幣種網格中價格最近的等級索引。
    pub(super) fn nearest_grid_idx(&self, symbol: &str, price: f64) -> usize {
        match self.grid_levels.get(symbol) {
            Some(levels) => grid_helpers::nearest_grid_idx(levels, price),
            None => 0,
        }
    }

    /// Check grid health for a symbol: is price within bounds? Should we rebalance?
    /// 檢查指定幣種的網格健康：價格是否在範圍內？是否需要再平衡？
    pub fn check_health(&mut self, symbol: &str, price: f64) -> GridHealth {
        let levels = match self.grid_levels.get(symbol) {
            Some(l) if !l.is_empty() => l,
            _ => return GridHealth::Healthy,
        };
        let lo = levels[0];
        let hi = levels[levels.len() - 1];

        if price < lo || price > hi {
            let count = self
                .out_of_range_count
                .entry(symbol.to_string())
                .or_insert(0);
            *count += 1;
            if *count >= self.max_out_of_range {
                GridHealth::NeedsRebalance
            } else {
                GridHealth::OutOfRange
            }
        } else {
            // Price back in range — reset counter / 價格回到範圍 — 重置計數器
            self.out_of_range_count.insert(symbol.to_string(), 0);
            GridHealth::Healthy
        }
    }

    /// Rebalance the grid centered on the given price.
    /// If OU has enough data, use OU-derived spacing; otherwise ±10% range.
    /// Respects current spacing_mode (Linear or Geometric).
    /// 以指定價格為中心重建網格。
    /// 若 OU 有足夠數據則使用 OU 間距；否則 ±10% 範圍。
    /// 遵循當前 spacing_mode。
    pub(super) fn rebalance(&mut self, symbol: &str, price: f64) {
        let history = self.price_history.get(symbol);
        let (lower, upper) = if history.map(|h| h.len()).unwrap_or(0) >= 20 {
            // Use OU-derived step to compute bounds / 用 OU 推導的步長計算邊界
            let ou_step = self.compute_ou_step(symbol);
            if let Some(step) = ou_step {
                let lo = price - step * (self.grid_count as f64 / 2.0);
                let hi = price + step * (self.grid_count as f64 / 2.0);
                // For geometric mode, ensure lower > 0
                // 幾何模式需確保下界 > 0
                (lo.max(price * 0.01), hi)
            } else {
                (
                    price * (1.0 - self.adaptive_range_pct),
                    price * (1.0 + self.adaptive_range_pct),
                )
            }
        } else {
            (
                price * (1.0 - self.adaptive_range_pct),
                price * (1.0 + self.adaptive_range_pct),
            )
        };

        self.grid_levels.insert(
            symbol.to_string(),
            grid_helpers::build_levels(lower, upper, self.grid_count, &self.spacing_mode),
        );
        self.out_of_range_count.insert(symbol.to_string(), 0);
        self.last_cross_idx.remove(symbol);
    }

    /// Compute OU-derived optimal step size for a symbol (without rebuilding the grid).
    /// Delegates to grid_helpers::compute_ou_step() pure function.
    /// 計算指定幣種的 OU 推導最佳步長。委派給 grid_helpers::compute_ou_step() 純函數。
    pub(super) fn compute_ou_step(&self, symbol: &str) -> Option<f64> {
        let history = self.price_history.get(symbol)?;
        grid_helpers::compute_ou_step_with_cost_floor(
            history,
            self.ou_lookback,
            self.fee_rate,
            self.min_grid_step_bps,
            self.cost_floor_multiplier,
        )
    }

    /// Update grid spacing for a symbol based on OU model (V2). Respects current spacing_mode.
    /// 基於 OU 模型更新指定幣種的網格間距 (V2)。遵循當前 spacing_mode。
    pub fn update_ou_spacing(&mut self, symbol: &str) {
        let history = match self.price_history.get(symbol) {
            Some(h) if h.len() >= 20 => h,
            _ => return,
        };
        let n = history.len().min(self.ou_lookback);
        let prices = &history[history.len() - n..];
        let mu = prices.iter().sum::<f64>() / prices.len() as f64;

        if let Some(step) = self.compute_ou_step(symbol) {
            let gc = self.grid_count;
            let new_levels = match self.spacing_mode {
                GridSpacingMode::Linear => {
                    let lower = mu - step * (gc as f64 / 2.0);
                    grid_helpers::build_linear_levels(lower, lower + step * (gc as f64 - 1.0), gc)
                }
                GridSpacingMode::Geometric => {
                    let half_range = step * (gc as f64 / 2.0);
                    let lower = (mu - half_range).max(mu * 0.01);
                    let upper = mu + half_range;
                    grid_helpers::build_geometric_levels(lower, upper, gc)
                }
            };
            self.grid_levels.insert(symbol.to_string(), new_levels);
        }
    }
}
