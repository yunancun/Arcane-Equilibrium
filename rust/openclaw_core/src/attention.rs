//! Attention-based market data throttling / 基於注意力的行情節流
//!
//! MODULE_NOTE (中文):
//!   注意力評估器 — 根據交易上下文（session 狀態、持倉、掛單距離、波動率）
//!   計算 Agent 對某個交易對的關注度，決定行情處理的節流間隔。
//!   高關注 = 更頻繁處理；低關注 = 節省計算資源。
//!
//! MODULE_NOTE (English):
//!   Attention assessor — computes how closely the Agent should watch a symbol
//!   based on trading context (session state, positions, order proximity, volatility).
//!   Higher attention = more frequent data processing; lower = save compute.
//!
//! Ported from: Python `MarketDataDispatcher._assess_attention()` logic.
//! 移植自：Python `MarketDataDispatcher._assess_attention()` 邏輯。
//!
//! Safety invariant / 安全不變量:
//!   Read-only assessment — never places or modifies orders.
//!   僅做只讀評估 — 永不下單或修改訂單。

use std::collections::{HashMap, VecDeque};

// ═══════════════════════════════════════════════════════════════════════════════
// Attention Levels / 注意力等級
// ═══════════════════════════════════════════════════════════════════════════════

/// Attention level determines throttle interval for market data processing.
/// 注意力等級決定行情處理的節流間隔。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum AttentionLevel {
    /// No active session — check once per minute.
    /// 無活躍 session — 每分鐘檢查一次。
    Dormant,
    /// Session active, no positions/orders — every 10s.
    /// Session 活躍但無持倉/訂單 — 每 10 秒。
    Low,
    /// Has positions, no pending orders — every 3s.
    /// 有持倉但無掛單 — 每 3 秒。
    Medium,
    /// Limit orders within 0.5% of price — every 500ms.
    /// 限價單在當前價 0.5% 以內 — 每 500 毫秒。
    High,
    /// Volatility spike ≥1% OR orders within 0.15% — every update.
    /// 波動率飆升 ≥1% 或訂單在 0.15% 以內 — 每次更新。
    Critical,
}

impl AttentionLevel {
    /// Get the throttle interval in seconds for this attention level.
    /// 獲取此注意力等級的節流間隔（秒）。
    #[must_use]
    pub fn throttle_interval_secs(self) -> f64 {
        match self {
            Self::Dormant => 60.0,
            Self::Low => 10.0,
            Self::Medium => 3.0,
            Self::High => 0.5,
            Self::Critical => 0.0,
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Attention Assessor / 注意力評估器
// ═══════════════════════════════════════════════════════════════════════════════

/// Computes attention level based on market state and trading context.
/// 根據市場狀態和交易上下文計算注意力等級。
///
/// Maintains a sliding window of price history per symbol for volatility detection.
/// 維護每個交易對的滑動窗口價格歷史，用於波動率檢測。
pub struct AttentionAssessor {
    // ── Config thresholds / 配置閾值 ──
    /// High attention trigger: order within this % of current price.
    /// 高關注觸發：訂單在當前價此百分比以內。
    proximity_threshold_pct: f64,

    /// Critical trigger: order within this % (proximity * 0.3).
    /// 危急觸發：訂單在此百分比以內（proximity * 0.3）。
    critical_proximity_pct: f64,

    /// Volatility spike threshold: % sudden move triggers critical.
    /// 波動率飆升閾值：突然變動百分比觸發危急。
    volatility_spike_pct: f64,

    /// Seconds of price history to keep per symbol.
    /// 每個交易對保留的價格歷史秒數。
    price_history_window_secs: u64,

    /// Minimum baseline data points for volatility detection.
    /// 波動率檢測所需的最少基線數據點。
    min_baseline_candles: usize,

    // ── State / 狀態 ──
    /// Per-symbol price history: (timestamp_ms, price).
    /// 每個交易對的價格歷史：（時間戳毫秒, 價格）。
    price_history: HashMap<String, VecDeque<(u64, f64)>>,

    /// Current attention level (last assessed).
    /// 當前注意力等級（上次評估結果）。
    current_level: AttentionLevel,
}

impl AttentionAssessor {
    /// Create a new assessor with default thresholds.
    /// 使用預設閾值創建新的評估器。
    #[must_use]
    pub fn new() -> Self {
        Self {
            proximity_threshold_pct: 0.5,
            critical_proximity_pct: 0.5 * 0.3, // 0.15
            volatility_spike_pct: 1.0,
            price_history_window_secs: 60,
            min_baseline_candles: 5,
            price_history: HashMap::new(),
            current_level: AttentionLevel::Dormant,
        }
    }

    /// Get the current attention level.
    /// 獲取當前注意力等級。
    #[must_use]
    pub fn current_level(&self) -> AttentionLevel {
        self.current_level
    }

    /// Get throttle interval for current level (seconds).
    /// 獲取當前級別的節流間隔（秒）。
    #[must_use]
    pub fn throttle_interval_secs(&self) -> f64 {
        self.current_level.throttle_interval_secs()
    }

    /// Assess attention level based on current market state.
    /// 根據當前市場狀態評估注意力級別。
    ///
    /// Decision hierarchy / 決策層級:
    /// 1. No session → Dormant
    /// 2. Volatility spike → Critical
    /// 3. Order proximity → High or Critical
    /// 4. Has positions → Medium
    /// 5. Else → Low
    ///
    /// # Arguments / 參數
    /// - `symbol` — trading pair / 交易對
    /// - `current_price` — latest price / 最新價格
    /// - `ts_ms` — timestamp in milliseconds / 毫秒時間戳
    /// - `has_session` — whether a trading session is active / 是否有活躍 session
    /// - `has_positions` — whether positions exist / 是否有持倉
    /// - `pending_orders` — slice of (price, qty) for active limit orders / 活躍限價單的 (價格, 數量) 切片
    pub fn assess(
        &mut self,
        symbol: &str,
        current_price: f64,
        ts_ms: u64,
        has_session: bool,
        has_positions: bool,
        pending_orders: &[(f64, f64)],
    ) -> AttentionLevel {
        // Always record price for volatility tracking.
        // 始終記錄價格用於波動率追蹤。
        self.record_price(symbol, ts_ms, current_price);

        // 1. No session → Dormant / 無 session → 休眠
        if !has_session {
            self.current_level = AttentionLevel::Dormant;
            return self.current_level;
        }

        // 2. Check volatility spike → Critical / 檢查波動率飆升 → 危急
        if self.detect_volatility_spike(symbol, current_price, ts_ms) {
            self.current_level = AttentionLevel::Critical;
            return self.current_level;
        }

        // 3. Check order proximity → High/Critical / 檢查訂單距離 → 高/危急
        if !pending_orders.is_empty() {
            let closest = Self::closest_order_distance_pct(current_price, pending_orders);
            if closest <= self.critical_proximity_pct {
                // Very close: within 0.15% → critical (about to fill)
                // 非常接近：0.15% 以內 → 危急（即將成交）
                self.current_level = AttentionLevel::Critical;
                return self.current_level;
            }
            if closest <= self.proximity_threshold_pct {
                // Close: within 0.5% → high
                // 接近：0.5% 以內 → 高關注
                self.current_level = AttentionLevel::High;
                return self.current_level;
            }
        }

        // 4. Has positions → Medium / 有持倉 → 中等關注
        if has_positions {
            self.current_level = AttentionLevel::Medium;
            return self.current_level;
        }

        // 5. Active session but nothing happening → Low
        // 有 session 但無事發生 → 低關注
        self.current_level = AttentionLevel::Low;
        self.current_level
    }

    /// Record a price for volatility detection and prune old entries.
    /// 記錄價格用於波動性檢測，並裁剪過期條目。
    fn record_price(&mut self, symbol: &str, ts_ms: u64, price: f64) {
        let history = self.price_history.entry(symbol.to_owned()).or_default();
        history.push_back((ts_ms, price));

        // Prune entries older than window / 裁剪窗口外的舊數據
        let cutoff_ms = ts_ms.saturating_sub(self.price_history_window_secs * 1000);
        while let Some(&(ts, _)) = history.front() {
            if ts < cutoff_ms {
                history.pop_front();
            } else {
                break;
            }
        }
    }

    /// Detect if current price has a volatility spike vs baseline.
    /// 檢測當前價格相對基準是否有波動性跳動。
    ///
    /// Uses prices older than 2 seconds as baseline, requires `min_baseline_candles` points.
    /// 使用超過 2 秒前的價格作為基線，需要 `min_baseline_candles` 個數據點。
    fn detect_volatility_spike(&self, symbol: &str, current_price: f64, ts_ms: u64) -> bool {
        let history = match self.price_history.get(symbol) {
            Some(h) if h.len() >= self.min_baseline_candles => h,
            _ => return false,
        };

        // Baseline: prices older than 2 seconds / 基線：超過 2 秒前的價格
        let cutoff_ms = ts_ms.saturating_sub(2000);
        let mut sum = 0.0_f64;
        let mut count = 0_usize;
        for &(ts, price) in history {
            if ts <= cutoff_ms {
                sum += price;
                count += 1;
            }
        }

        // Need at least 3 baseline points / 至少需要 3 個基線點
        if count < 3 {
            return false;
        }

        let avg_baseline = sum / count as f64;
        if avg_baseline <= 0.0 {
            return false;
        }

        let change_pct = (current_price - avg_baseline).abs() / avg_baseline * 100.0;
        change_pct >= self.volatility_spike_pct
    }

    /// Find closest order distance as percentage of current price.
    /// 計算最近訂單距離（佔當前價格的百分比）。
    ///
    /// Returns `f64::INFINITY` if no valid orders or price is non-positive.
    /// 如果無有效訂單或價格非正數則返回 `f64::INFINITY`。
    #[must_use]
    fn closest_order_distance_pct(current_price: f64, orders: &[(f64, f64)]) -> f64 {
        if orders.is_empty() || current_price <= 0.0 {
            return f64::INFINITY;
        }

        orders
            .iter()
            .filter(|(price, _)| *price > 0.0)
            .map(|(price, _)| (current_price - price).abs() / current_price * 100.0)
            .fold(f64::INFINITY, f64::min)
    }
}

impl Default for AttentionAssessor {
    fn default() -> Self {
        Self::new()
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    /// Helper: generate a base timestamp (arbitrary epoch).
    /// 輔助：生成基準時間戳。
    const BASE_TS: u64 = 1_700_000_000_000; // ms

    #[test]
    fn test_dormant_no_session() {
        // No session → Dormant regardless of other state.
        // 無 session → 休眠，無論其他狀態如何。
        let mut a = AttentionAssessor::new();
        let level = a.assess("BTCUSDT", 50000.0, BASE_TS, false, true, &[(50010.0, 1.0)]);
        assert_eq!(level, AttentionLevel::Dormant);
        assert!((a.throttle_interval_secs() - 60.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_low_session_no_positions_no_orders() {
        // Active session, no positions, no orders → Low.
        // 活躍 session，無持倉，無訂單 → 低關注。
        let mut a = AttentionAssessor::new();
        let level = a.assess("BTCUSDT", 50000.0, BASE_TS, true, false, &[]);
        assert_eq!(level, AttentionLevel::Low);
        assert!((a.throttle_interval_secs() - 10.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_medium_has_positions_no_orders() {
        // Has positions, no pending orders → Medium.
        // 有持倉，無掛單 → 中等關注。
        let mut a = AttentionAssessor::new();
        let level = a.assess("BTCUSDT", 50000.0, BASE_TS, true, true, &[]);
        assert_eq!(level, AttentionLevel::Medium);
        assert!((a.throttle_interval_secs() - 3.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_high_order_within_half_percent() {
        // Limit order at 50200 vs price 50000 → 0.4% distance → High.
        // 限價單 50200 vs 價格 50000 → 0.4% 距離 → 高關注。
        let mut a = AttentionAssessor::new();
        let orders = [(50200.0, 1.0)];
        let level = a.assess("BTCUSDT", 50000.0, BASE_TS, true, false, &orders);
        assert_eq!(level, AttentionLevel::High);
        assert!((a.throttle_interval_secs() - 0.5).abs() < f64::EPSILON);
    }

    #[test]
    fn test_critical_order_within_015_percent() {
        // Limit order at 50050 vs price 50000 → 0.1% distance → Critical.
        // 限價單 50050 vs 價格 50000 → 0.1% 距離 → 危急。
        let mut a = AttentionAssessor::new();
        let orders = [(50050.0, 1.0)];
        let level = a.assess("BTCUSDT", 50000.0, BASE_TS, true, false, &orders);
        assert_eq!(level, AttentionLevel::Critical);
        assert!((a.throttle_interval_secs() - 0.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_critical_volatility_spike() {
        // Build up baseline prices, then inject a 1.5% spike → Critical.
        // 累積基線價格，然後注入 1.5% 的跳動 → 危急。
        let mut a = AttentionAssessor::new();

        // Seed 10 baseline prices at ~50000, spread across 10 seconds (older than 2s).
        // 種入 10 個約 50000 的基線價格，分佈在 10 秒內（超過 2 秒前）。
        for i in 0..10 {
            let ts = BASE_TS + i * 1000; // 1s apart
            a.assess("BTCUSDT", 50000.0, ts, true, false, &[]);
        }

        // Now at ts = BASE_TS + 10_000, inject spike: 50000 * 1.015 = 50750.
        // 現在 ts = BASE_TS + 10_000，注入跳動：50000 * 1.015 = 50750。
        let spike_ts = BASE_TS + 10_000;
        let level = a.assess("BTCUSDT", 50750.0, spike_ts, true, false, &[]);
        assert_eq!(level, AttentionLevel::Critical);
    }

    #[test]
    fn test_no_spike_with_insufficient_history() {
        // Only 2 data points — not enough for volatility detection → falls through to Low.
        // 只有 2 個數據點 — 不足以檢測波動率 → 降級為低關注。
        let mut a = AttentionAssessor::new();
        a.assess("BTCUSDT", 50000.0, BASE_TS, true, false, &[]);
        a.assess("BTCUSDT", 50000.0, BASE_TS + 1000, true, false, &[]);
        let level = a.assess("BTCUSDT", 55000.0, BASE_TS + 2000, true, false, &[]);
        // Even though price jumped 10%, insufficient baseline → Low.
        // 即使價格跳了 10%，基線不足 → 低關注。
        assert_eq!(level, AttentionLevel::Low);
    }

    #[test]
    fn test_order_distance_calculation() {
        // Verify closest_order_distance_pct math.
        // 驗證最近訂單距離計算的數學正確性。
        let orders = [(50500.0, 1.0), (49000.0, 2.0), (51000.0, 0.5)];
        let dist = AttentionAssessor::closest_order_distance_pct(50000.0, &orders);
        // Closest is 50500: |50000 - 50500| / 50000 * 100 = 1.0%
        assert!((dist - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_order_distance_empty_orders() {
        // No orders → infinity.
        // 無訂單 → 無窮大。
        let dist = AttentionAssessor::closest_order_distance_pct(50000.0, &[]);
        assert!(dist.is_infinite());
    }

    #[test]
    fn test_price_history_pruning() {
        // Prices older than 60s should be pruned.
        // 超過 60 秒的價格應被裁剪。
        let mut a = AttentionAssessor::new();

        // Insert price at t=0
        a.record_price("BTCUSDT", BASE_TS, 50000.0);
        assert_eq!(a.price_history["BTCUSDT"].len(), 1);

        // Insert price at t=61s → old entry should be pruned.
        // 在 t=61s 插入價格 → 舊條目應被裁剪。
        a.record_price("BTCUSDT", BASE_TS + 61_000, 50100.0);
        assert_eq!(a.price_history["BTCUSDT"].len(), 1);
        assert_eq!(a.price_history["BTCUSDT"][0].1, 50100.0);
    }

    #[test]
    fn test_throttle_intervals_all_levels() {
        // Verify all throttle intervals match specification.
        // 驗證所有節流間隔符合規格。
        assert!((AttentionLevel::Dormant.throttle_interval_secs() - 60.0).abs() < f64::EPSILON);
        assert!((AttentionLevel::Low.throttle_interval_secs() - 10.0).abs() < f64::EPSILON);
        assert!((AttentionLevel::Medium.throttle_interval_secs() - 3.0).abs() < f64::EPSILON);
        assert!((AttentionLevel::High.throttle_interval_secs() - 0.5).abs() < f64::EPSILON);
        assert!((AttentionLevel::Critical.throttle_interval_secs() - 0.0).abs() < f64::EPSILON);
    }
}
