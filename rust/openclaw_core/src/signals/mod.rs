//! Signal generation engine — 8 signal rules + consensus engine.
//! 信號生成引擎 — 8 個信號規則 + 共識引擎。
//!
//! MODULE_NOTE (中文):
//!   移植自 Python `SignalGenerator` + `SignalEngine`。包含 8 個信號規則函數
//!   和一個共識引擎 `SignalEngine`，負責：
//!   1. 對每組指標數據執行全部 8 個規則
//!   2. 維護信號歷史（最多 1000 條）和最新信號映射（最多 500 條）
//!   3. 提供共識摘要（加權方向得分 + 新鮮度衰減）
//!
//!   信號方向：Long / Short / CloseLong / CloseShort / Neutral
//!   共識使用 confidence × freshness_weight（5 分鐘線性衰減）
//!
//! MODULE_NOTE (English):
//!   Ported from Python `SignalGenerator` + `SignalEngine`. Contains 8 signal rule
//!   functions and a consensus engine `SignalEngine`, responsible for:
//!   1. Evaluating all 8 rules against each set of indicator data
//!   2. Maintaining signal history (max 1000) and latest signal map (max 500)
//!   3. Providing consensus summary (weighted direction scores + freshness decay)
//!
//!   Signal directions: Long / Short / CloseLong / CloseShort / Neutral
//!   Consensus uses confidence × freshness_weight (5-minute linear decay)
//!
//! Ported from: Python `signal_rules.py` + `signal_engine.py`
//! 移植自：Python `signal_rules.py` + `signal_engine.py`
//!
//! Safety invariant / 安全不變量:
//!   Pure computation — no I/O, no side effects, no order placement.
//!   純計算 — 無 I/O、無副作用、不下單。

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};

pub mod rules;

/// Type alias for signal rule functions. / 信號規則函數的類型別名。
type RuleFn = fn(&str, &str, &IndicatorInput, u64) -> Option<Signal>;

// Re-export all rule functions for convenience.
// 重新導出所有規則函數以方便使用。
pub use rules::{
    bollinger_reversion, ma_crossover, macd_crossover, macd_exhaustion, regime_detector,
    rsi_divergence, rsi_exit, rsi_overbought_oversold,
};

// ═══════════════════════════════════════════════════════════════════════════════
// Core Types / 核心類型
// ═══════════════════════════════════════════════════════════════════════════════

/// Signal direction. / 信號方向。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SignalDirection {
    Long,
    Short,
    CloseLong,
    CloseShort,
    Neutral,
}

/// A single signal emitted by a rule. / 單一規則發出的信號。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Signal {
    /// Trading symbol (e.g. "BTCUSDT"). / 交易符號。
    pub symbol: String,
    /// Directional intent. / 方向意圖。
    pub direction: SignalDirection,
    /// Confidence level 0.0–1.0. / 信心水平 0.0–1.0。
    pub confidence: f64,
    /// Expected edge in basis points. / 預期優勢（基點）。
    pub edge_bps: f64,
    /// Rule name that generated this signal. / 生成此信號的規則名稱。
    pub source: String,
    /// Timeframe (e.g. "15m", "1h"). / 時間框架。
    pub timeframe: String,
    /// Human-readable reasoning. / 人類可讀的推理。
    pub reasoning: String,
    /// Unix timestamp in milliseconds. / Unix 時間戳（毫秒）。
    pub ts_ms: u64,
}

/// Input indicators for signal rule evaluation.
/// 用於信號規則評估的輸入指標。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct IndicatorInput {
    pub rsi: Option<f64>,
    pub sma: Option<f64>,
    pub ema: Option<f64>,
    pub macd: Option<f64>,
    pub macd_signal: Option<f64>,
    pub macd_histogram: Option<f64>,
    pub bb_percent_b: Option<f64>,
    pub bb_bandwidth: Option<f64>,
    pub atr_percent: Option<f64>,
    pub stoch_k: Option<f64>,
    pub adx: Option<f64>,
    pub volume_ratio: Option<f64>,
}

/// Consensus summary for a symbol across active signals.
/// 符號在活躍信號中的共識摘要。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SignalSummary {
    /// Aggregate long score (sum of confidence × freshness). / 多頭總分。
    pub long_score: f64,
    /// Aggregate short score. / 空頭總分。
    pub short_score: f64,
    /// Consensus direction based on dominant score. / 基於主導分數的共識方向。
    pub consensus_direction: SignalDirection,
    /// Number of active (non-expired) signals for this symbol. / 活躍信號數量。
    pub active_signals: usize,
}

/// Accumulated signal engine statistics. / 累計信號引擎統計。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SignalStats {
    /// Total signals generated across all time. / 歷史總信號數。
    pub total_generated: u64,
    /// Signals by direction. / 按方向統計。
    pub long_count: u64,
    pub short_count: u64,
    pub close_long_count: u64,
    pub close_short_count: u64,
    pub neutral_count: u64,
}

// ═══════════════════════════════════════════════════════════════════════════════
// SignalEngine / 信號引擎
// ═══════════════════════════════════════════════════════════════════════════════

/// Maximum signal history entries. / 信號歷史最大條目數。
const MAX_HISTORY: usize = 1000;

/// Maximum latest signal map entries. / 最新信號映射最大條目數。
const MAX_LATEST: usize = 500;

/// Freshness window in milliseconds (5 minutes). / 新鮮度窗口（毫秒，5 分鐘）。
const FRESHNESS_WINDOW_MS: u64 = 5 * 60 * 1000;

/// Signal consensus engine — evaluates rules, tracks history, provides consensus.
/// 信號共識引擎 — 評估規則、追蹤歷史、提供共識。
pub struct SignalEngine {
    /// Rolling signal history (FIFO, max 1000). / 滾動信號歷史（FIFO，最多 1000）。
    history: VecDeque<Signal>,
    /// Latest signal per "symbol:source" key (max 500). / 每個 "symbol:source" 的最新信號。
    latest: HashMap<String, Signal>,
    /// Accumulated statistics. / 累計統計。
    stats: SignalStats,
}

impl SignalEngine {
    /// Create a new empty SignalEngine. / 建立新的空信號引擎。
    pub fn new() -> Self {
        Self {
            history: VecDeque::with_capacity(MAX_HISTORY),
            latest: HashMap::with_capacity(64),
            stats: SignalStats::default(),
        }
    }

    /// Evaluate all 8 rules against indicator data, return generated signals.
    /// 對指標數據評估全部 8 個規則，返回生成的信號。
    ///
    /// Each rule that fires produces a signal. All signals are recorded in
    /// history and latest map. / 每個觸發的規則產生一個信號，記錄到歷史和最新映射。
    pub fn evaluate(
        &mut self,
        symbol: &str,
        timeframe: &str,
        indicators: &IndicatorInput,
        ts_ms: u64,
    ) -> Vec<Signal> {
        let mut signals = Vec::new();

        // Evaluate each rule. Order does not matter — all are independent.
        // 評估每個規則。順序無關 — 全部獨立。
        let rule_fns: &[RuleFn] = &[
            rsi_overbought_oversold,
            ma_crossover,
            bollinger_reversion,
            macd_crossover,
            rsi_exit,
            macd_exhaustion,
            rsi_divergence,
            regime_detector,
        ];

        for rule_fn in rule_fns {
            if let Some(sig) = rule_fn(symbol, timeframe, indicators, ts_ms) {
                self.record_signal(&sig);
                signals.push(sig);
            }
        }

        signals
    }

    /// Get consensus signal summary for a symbol.
    /// 獲取符號的共識信號摘要。
    ///
    /// Aggregates confidence × freshness_weight for all non-expired signals.
    /// Freshness decays linearly over 5 minutes. / 對所有未過期信號聚合
    /// confidence × freshness_weight。新鮮度在 5 分鐘內線性衰減。
    pub fn get_signal_summary(&self, symbol: &str, now_ms: u64) -> SignalSummary {
        let mut long_score = 0.0_f64;
        let mut short_score = 0.0_f64;
        let mut active = 0_usize;

        for sig in self.latest.values() {
            if sig.symbol != symbol {
                continue;
            }

            // Freshness: linear decay from 1.0 to 0.0 over FRESHNESS_WINDOW_MS
            // 新鮮度：在 FRESHNESS_WINDOW_MS 內從 1.0 線性衰減到 0.0
            let age_ms = now_ms.saturating_sub(sig.ts_ms);
            if age_ms > FRESHNESS_WINDOW_MS {
                continue; // expired / 已過期
            }
            let freshness = 1.0 - (age_ms as f64 / FRESHNESS_WINDOW_MS as f64);
            let weight = sig.confidence * freshness;

            match sig.direction {
                SignalDirection::Long => long_score += weight,
                SignalDirection::Short => short_score += weight,
                SignalDirection::CloseLong => short_score += weight * 0.5,
                SignalDirection::CloseShort => long_score += weight * 0.5,
                SignalDirection::Neutral => {} // no directional contribution
            }

            active += 1;
        }

        let consensus_direction = if long_score > short_score && long_score > 0.1 {
            SignalDirection::Long
        } else if short_score > long_score && short_score > 0.1 {
            SignalDirection::Short
        } else {
            SignalDirection::Neutral
        };

        SignalSummary {
            long_score,
            short_score,
            consensus_direction,
            active_signals: active,
        }
    }

    /// Get accumulated statistics. / 獲取累計統計。
    pub fn get_stats(&self) -> &SignalStats {
        &self.stats
    }

    /// Get signal history length. / 獲取信號歷史長度。
    pub fn history_len(&self) -> usize {
        self.history.len()
    }

    /// Get latest map size. / 獲取最新映射大小。
    pub fn latest_len(&self) -> usize {
        self.latest.len()
    }

    // ── Internal helpers / 內部輔助 ──

    /// Record a signal into history and latest map, enforcing size limits.
    /// 將信號記錄到歷史和最新映射，強制大小限制。
    fn record_signal(&mut self, sig: &Signal) {
        // Update stats / 更新統計
        self.stats.total_generated += 1;
        match sig.direction {
            SignalDirection::Long => self.stats.long_count += 1,
            SignalDirection::Short => self.stats.short_count += 1,
            SignalDirection::CloseLong => self.stats.close_long_count += 1,
            SignalDirection::CloseShort => self.stats.close_short_count += 1,
            SignalDirection::Neutral => self.stats.neutral_count += 1,
        }

        // Push to history, evict oldest if at capacity / 推入歷史，超限時淘汰最舊
        if self.history.len() >= MAX_HISTORY {
            self.history.pop_front();
        }
        self.history.push_back(sig.clone());

        // Update latest map / 更新最新映射
        let key = format!("{}:{}", sig.symbol, sig.source);
        self.latest.insert(key, sig.clone());

        // Evict oldest from latest if over limit / 超限時從最新映射淘汰最舊
        if self.latest.len() > MAX_LATEST {
            self.evict_oldest_latest();
        }
    }

    /// Evict the oldest entry from the latest map (by ts_ms).
    /// 從最新映射中淘汰最舊的條目（按 ts_ms）。
    fn evict_oldest_latest(&mut self) {
        if let Some(oldest_key) = self
            .latest
            .iter()
            .min_by_key(|(_, sig)| sig.ts_ms)
            .map(|(k, _)| k.clone())
        {
            self.latest.remove(&oldest_key);
        }
    }
}

impl Default for SignalEngine {
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

    fn sample_input_oversold() -> IndicatorInput {
        IndicatorInput {
            rsi: Some(20.0),
            sma: Some(100.0),
            ema: Some(100.2),
            macd: Some(0.5),
            macd_signal: Some(0.4),
            macd_histogram: Some(0.1),
            bb_percent_b: Some(0.05),
            bb_bandwidth: Some(0.03),
            atr_percent: Some(2.0),
            stoch_k: Some(15.0),
            adx: Some(30.0),
            volume_ratio: Some(1.5),
        }
    }

    #[test]
    fn test_engine_evaluate_produces_signals() {
        let mut engine = SignalEngine::new();
        let input = sample_input_oversold();
        let signals = engine.evaluate("BTCUSDT", "15m", &input, 1000);
        // With oversold RSI=20, multiple rules should fire
        assert!(!signals.is_empty(), "expected at least one signal");
        // RSI oversold should definitely fire
        assert!(signals.iter().any(|s| s.source == "rsi_overbought_oversold"));
    }

    #[test]
    fn test_engine_stats_tracking() {
        let mut engine = SignalEngine::new();
        let input = sample_input_oversold();
        let signals = engine.evaluate("BTCUSDT", "15m", &input, 1000);
        let stats = engine.get_stats();
        assert_eq!(stats.total_generated, signals.len() as u64);
    }

    #[test]
    fn test_engine_history_limit() {
        let mut engine = SignalEngine::new();
        let mut input = IndicatorInput::default();
        input.rsi = Some(20.0); // will trigger RSI oversold each time

        // Generate > 1000 signals
        for i in 0..1100 {
            engine.evaluate(&format!("SYM{i}"), "15m", &input, i as u64);
        }
        assert!(engine.history_len() <= MAX_HISTORY);
    }

    #[test]
    fn test_engine_latest_limit() {
        let mut engine = SignalEngine::new();
        let mut input = IndicatorInput::default();
        input.rsi = Some(20.0);

        // Generate signals for > 500 unique symbol:source keys
        for i in 0..600 {
            engine.evaluate(&format!("SYM{i}"), "15m", &input, i as u64);
        }
        assert!(engine.latest_len() <= MAX_LATEST);
    }

    #[test]
    fn test_consensus_long_direction() {
        let mut engine = SignalEngine::new();
        let input = sample_input_oversold(); // strongly oversold → Long bias
        engine.evaluate("BTCUSDT", "15m", &input, 1000);
        let summary = engine.get_signal_summary("BTCUSDT", 1000);
        // With RSI=20, we expect a long bias
        assert!(summary.long_score > 0.0);
        assert!(summary.active_signals > 0);
    }

    #[test]
    fn test_consensus_freshness_decay() {
        let mut engine = SignalEngine::new();
        let input = sample_input_oversold();
        engine.evaluate("BTCUSDT", "15m", &input, 1000);

        // Immediately after: signals are fresh
        let fresh = engine.get_signal_summary("BTCUSDT", 1000);
        // 6 minutes later: all signals expired (> 5min window)
        let expired = engine.get_signal_summary("BTCUSDT", 1000 + FRESHNESS_WINDOW_MS + 1);

        assert!(fresh.active_signals > 0);
        assert_eq!(expired.active_signals, 0);
        assert!((expired.long_score).abs() < 1e-10);
    }

    #[test]
    fn test_consensus_neutral_when_no_signals() {
        let engine = SignalEngine::new();
        let summary = engine.get_signal_summary("BTCUSDT", 1000);
        assert_eq!(summary.consensus_direction, SignalDirection::Neutral);
        assert_eq!(summary.active_signals, 0);
    }

    #[test]
    fn test_empty_input_produces_regime_only_if_data() {
        let mut engine = SignalEngine::new();
        let input = IndicatorInput::default();
        let signals = engine.evaluate("BTCUSDT", "15m", &input, 1000);
        // All-None input should produce no signals (regime also needs at least one indicator)
        assert!(signals.is_empty());
    }

    #[test]
    fn test_signal_serde_roundtrip() {
        let sig = Signal {
            symbol: "BTCUSDT".to_string(),
            direction: SignalDirection::Long,
            confidence: 0.75,
            edge_bps: 15.0,
            source: "test".to_string(),
            timeframe: "1h".to_string(),
            reasoning: "test signal".to_string(),
            ts_ms: 12345,
        };
        let json = serde_json::to_string(&sig).unwrap();
        let deser: Signal = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.symbol, "BTCUSDT");
        assert_eq!(deser.direction, SignalDirection::Long);
        assert!((deser.confidence - 0.75).abs() < 1e-10);
    }

    #[test]
    fn test_signal_direction_serde() {
        for dir in [
            SignalDirection::Long,
            SignalDirection::Short,
            SignalDirection::CloseLong,
            SignalDirection::CloseShort,
            SignalDirection::Neutral,
        ] {
            let json = serde_json::to_string(&dir).unwrap();
            let deser: SignalDirection = serde_json::from_str(&json).unwrap();
            assert_eq!(deser, dir);
        }
    }
}
