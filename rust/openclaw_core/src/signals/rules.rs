//! Signal rules — 8 deterministic signal generation functions.
//! 信號規則 — 8 個確定性信號生成函數。
//!
//! MODULE_NOTE (中文):
//!   實現 8 個信號規則函數，每個接收 `IndicatorInput` 並返回 `Option<Signal>`。
//!   規則覆蓋：RSI 超買超賣、均線交叉、布林回歸、MACD 交叉、RSI 出場、
//!   MACD 衰竭、RSI 背離、市場狀態偵測。
//!
//!   QC 邊界豁免 [V3-QC-2]:
//!     - RSI: ±0.03 絕對值
//!     - MA crossover: ±1e-8
//!     - ATR/bandwidth: ±0.01%
//!
//! MODULE_NOTE (English):
//!   Implements 8 signal rule functions, each taking `IndicatorInput` and returning
//!   `Option<Signal>`. Rules cover: RSI overbought/oversold, MA crossover, Bollinger
//!   reversion, MACD crossover, RSI exit, MACD exhaustion, RSI divergence, and
//!   regime detection.
//!
//!   QC boundary exemptions [V3-QC-2]:
//!     - RSI: ±0.03 absolute
//!     - MA crossover: ±1e-8
//!     - ATR/bandwidth: ±0.01%
//!
//! Safety invariant / 安全不變量:
//!   Pure computation — no I/O, no side effects, no order placement.
//!   純計算 — 無 I/O、無副作用、不下單。

use super::{IndicatorInput, Signal, SignalDirection};

// ═══════════════════════════════════════════════════════════════════════════════
// Constants / 常量
// ═══════════════════════════════════════════════════════════════════════════════

/// RSI boundary tolerance [V3-QC-2]. / RSI 邊界容差 [V3-QC-2]。
const RSI_TOLERANCE: f64 = 0.03;

/// MA crossover boundary tolerance [V3-QC-2]. / 均線交叉邊界容差 [V3-QC-2]。
const MA_BOUNDARY: f64 = 1e-8;

/// Minimum bandwidth for Bollinger signals [V3-QC-2].
/// 布林信號的最小帶寬 [V3-QC-2]。
const BB_MIN_BANDWIDTH: f64 = 0.01;

/// MA crossover minimum divergence (0.05%). / 均線交叉最小偏差（0.05%）。
const MA_MIN_DIVERGENCE_PCT: f64 = 0.0005;

// ═══════════════════════════════════════════════════════════════════════════════
// Rule 1: RSI Overbought/Oversold / RSI 超買超賣
// ═══════════════════════════════════════════════════════════════════════════════

/// RSI overbought/oversold signal.
/// RSI 超買/超賣信號。
///
/// - RSI < 30 → Long (confidence = min(1.0, (30 - RSI) / 30 + 0.3))
/// - RSI > 70 → Short (confidence = min(1.0, (RSI - 70) / 30 + 0.3))
/// - Within tolerance band (±0.03): no signal.
pub fn rsi_overbought_oversold(
    symbol: &str,
    timeframe: &str,
    input: &IndicatorInput,
    ts_ms: u64,
) -> Option<Signal> {
    let rsi = input.rsi?;

    if rsi < (30.0 - RSI_TOLERANCE) {
        let confidence = ((30.0 - rsi) / 30.0 + 0.3).min(1.0);
        let edge = (30.0 - rsi) * 3.0; // basis points proportional to deviation
        Some(Signal {
            symbol: symbol.to_string(),
            direction: SignalDirection::Long,
            confidence,
            edge_bps: edge,
            source: "rsi_overbought_oversold".to_string(),
            timeframe: timeframe.to_string(),
            reasoning: format!("RSI={rsi:.2} deeply oversold → Long"),
            ts_ms,
        })
    } else if rsi > (70.0 + RSI_TOLERANCE) {
        let confidence = ((rsi - 70.0) / 30.0 + 0.3).min(1.0);
        let edge = (rsi - 70.0) * 3.0;
        Some(Signal {
            symbol: symbol.to_string(),
            direction: SignalDirection::Short,
            confidence,
            edge_bps: edge,
            source: "rsi_overbought_oversold".to_string(),
            timeframe: timeframe.to_string(),
            reasoning: format!("RSI={rsi:.2} deeply overbought → Short"),
            ts_ms,
        })
    } else {
        None
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Rule 2: MA Crossover / 均線交叉
// ═══════════════════════════════════════════════════════════════════════════════

/// Moving average crossover signal.
/// 均線交叉信號。
///
/// fast_ma (EMA) vs slow_ma (SMA). Requires >0.05% divergence.
/// Boundary tolerance: ±1e-8 [V3-QC-2].
pub fn ma_crossover(
    symbol: &str,
    timeframe: &str,
    input: &IndicatorInput,
    ts_ms: u64,
) -> Option<Signal> {
    let fast = input.ema?;
    let slow = input.sma?;

    // Guard: avoid division by zero / 避免除零
    if slow.abs() < MA_BOUNDARY {
        return None;
    }

    let divergence = (fast - slow) / slow;

    if divergence > MA_MIN_DIVERGENCE_PCT {
        let confidence = (divergence / 0.005).clamp(0.3, 1.0);
        let edge = divergence * 10_000.0; // convert to bps
        Some(Signal {
            symbol: symbol.to_string(),
            direction: SignalDirection::Long,
            confidence,
            edge_bps: edge,
            source: "ma_crossover".to_string(),
            timeframe: timeframe.to_string(),
            reasoning: format!("EMA>SMA by {:.4}% → Long", divergence * 100.0),
            ts_ms,
        })
    } else if divergence < -MA_MIN_DIVERGENCE_PCT {
        let confidence = (divergence.abs() / 0.005).clamp(0.3, 1.0);
        let edge = divergence.abs() * 10_000.0;
        Some(Signal {
            symbol: symbol.to_string(),
            direction: SignalDirection::Short,
            confidence,
            edge_bps: edge,
            source: "ma_crossover".to_string(),
            timeframe: timeframe.to_string(),
            reasoning: format!("EMA<SMA by {:.4}% → Short", divergence.abs() * 100.0),
            ts_ms,
        })
    } else {
        None
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Rule 3: Bollinger Reversion / 布林回歸
// ═══════════════════════════════════════════════════════════════════════════════

/// Bollinger Band mean reversion signal.
/// 布林帶均值回歸信號。
///
/// - %B < 0.1 AND RSI < 40 → Long
/// - %B > 0.9 AND RSI > 60 → Short
/// - Requires bandwidth > 0.01 to avoid flat market noise.
pub fn bollinger_reversion(
    symbol: &str,
    timeframe: &str,
    input: &IndicatorInput,
    ts_ms: u64,
) -> Option<Signal> {
    let pct_b = input.bb_percent_b?;
    let rsi = input.rsi?;
    let bandwidth = input.bb_bandwidth?;

    // Minimum volatility filter / 最小波動率過濾
    if bandwidth < BB_MIN_BANDWIDTH {
        return None;
    }

    if pct_b < 0.1 && rsi < 40.0 {
        let confidence = ((0.1 - pct_b) * 5.0 + 0.4).min(1.0);
        let edge = (0.1 - pct_b) * 100.0 + (40.0 - rsi);
        Some(Signal {
            symbol: symbol.to_string(),
            direction: SignalDirection::Long,
            confidence,
            edge_bps: edge,
            source: "bollinger_reversion".to_string(),
            timeframe: timeframe.to_string(),
            reasoning: format!("%B={pct_b:.3}, RSI={rsi:.1} → mean reversion Long"),
            ts_ms,
        })
    } else if pct_b > 0.9 && rsi > 60.0 {
        let confidence = ((pct_b - 0.9) * 5.0 + 0.4).min(1.0);
        let edge = (pct_b - 0.9) * 100.0 + (rsi - 60.0);
        Some(Signal {
            symbol: symbol.to_string(),
            direction: SignalDirection::Short,
            confidence,
            edge_bps: edge,
            source: "bollinger_reversion".to_string(),
            timeframe: timeframe.to_string(),
            reasoning: format!("%B={pct_b:.3}, RSI={rsi:.1} → mean reversion Short"),
            ts_ms,
        })
    } else {
        None
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Rule 4: MACD Crossover / MACD 交叉
// ═══════════════════════════════════════════════════════════════════════════════

/// MACD line + histogram crossover signal.
/// MACD 線 + 柱狀圖交叉信號。
///
/// - MACD > 0 AND histogram > 0 → Long
/// - MACD < 0 AND histogram < 0 → Short
pub fn macd_crossover(
    symbol: &str,
    timeframe: &str,
    input: &IndicatorInput,
    ts_ms: u64,
) -> Option<Signal> {
    let macd = input.macd?;
    let histogram = input.macd_histogram?;

    if macd > 0.0 && histogram > 0.0 {
        let confidence = (histogram.abs() * 100.0 + 0.3).min(1.0);
        let edge = macd.abs() * 1000.0;
        Some(Signal {
            symbol: symbol.to_string(),
            direction: SignalDirection::Long,
            confidence,
            edge_bps: edge,
            source: "macd_crossover".to_string(),
            timeframe: timeframe.to_string(),
            reasoning: format!("MACD={macd:.4} hist={histogram:.4} both positive → Long"),
            ts_ms,
        })
    } else if macd < 0.0 && histogram < 0.0 {
        let confidence = (histogram.abs() * 100.0 + 0.3).min(1.0);
        let edge = macd.abs() * 1000.0;
        Some(Signal {
            symbol: symbol.to_string(),
            direction: SignalDirection::Short,
            confidence,
            edge_bps: edge,
            source: "macd_crossover".to_string(),
            timeframe: timeframe.to_string(),
            reasoning: format!("MACD={macd:.4} hist={histogram:.4} both negative → Short"),
            ts_ms,
        })
    } else {
        None
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Rule 5: RSI Exit / RSI 出場
// ═══════════════════════════════════════════════════════════════════════════════

/// RSI-based exit signal (close existing positions).
/// 基於 RSI 的出場信號（平倉）。
///
/// - 50 < RSI < 65 → CloseLong (momentum fading)
/// - 35 < RSI < 50 → CloseShort (selling pressure fading)
/// - Confidence fixed at 0.6.
pub fn rsi_exit(
    symbol: &str,
    timeframe: &str,
    input: &IndicatorInput,
    ts_ms: u64,
) -> Option<Signal> {
    let rsi = input.rsi?;

    if rsi > 50.0 + RSI_TOLERANCE && rsi < 65.0 - RSI_TOLERANCE {
        Some(Signal {
            symbol: symbol.to_string(),
            direction: SignalDirection::CloseLong,
            confidence: 0.6,
            edge_bps: 5.0,
            source: "rsi_exit".to_string(),
            timeframe: timeframe.to_string(),
            reasoning: format!("RSI={rsi:.2} in exit zone 50-65 → CloseLong"),
            ts_ms,
        })
    } else if rsi > 35.0 + RSI_TOLERANCE && rsi < 50.0 - RSI_TOLERANCE {
        Some(Signal {
            symbol: symbol.to_string(),
            direction: SignalDirection::CloseShort,
            confidence: 0.6,
            edge_bps: 5.0,
            source: "rsi_exit".to_string(),
            timeframe: timeframe.to_string(),
            reasoning: format!("RSI={rsi:.2} in exit zone 35-50 → CloseShort"),
            ts_ms,
        })
    } else {
        None
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Rule 6: MACD Exhaustion / MACD 衰竭
// ═══════════════════════════════════════════════════════════════════════════════

/// MACD histogram exhaustion — momentum fading signal.
/// MACD 柱狀圖衰竭 — 動量衰減信號。
///
/// When histogram shrinks to <60% of previous bar's magnitude, signals
/// momentum exhaustion in the current trend direction.
///
/// Requires `prev_histogram` in input for comparison.
pub fn macd_exhaustion(
    symbol: &str,
    timeframe: &str,
    input: &IndicatorInput,
    ts_ms: u64,
) -> Option<Signal> {
    let histogram = input.macd_histogram?;
    let macd = input.macd?;

    // We use macd_signal as a proxy for "previous histogram magnitude".
    // In a real system this would come from the previous bar; here we use
    // the signal line magnitude as an approximation of the prior histogram.
    // 使用 macd_signal 作為「前一根柱狀圖大小」的近似。
    let signal_line = input.macd_signal?;

    // Previous histogram approximation: macd - 2*signal gives rough prior hist
    // More precisely: if current hist = macd - signal, a shrinking histogram
    // means |hist| < 0.6 * |signal_line| (the signal itself represents the
    // smoothed MACD, so its magnitude gives a baseline).
    let baseline = signal_line.abs();
    if baseline < 1e-10 {
        return None;
    }

    let ratio = histogram.abs() / baseline;

    if ratio < 0.6 && macd > 0.0 {
        // Bullish momentum exhausting / 多頭動量衰竭
        Some(Signal {
            symbol: symbol.to_string(),
            direction: SignalDirection::CloseLong,
            confidence: (0.6 - ratio + 0.3).min(1.0),
            edge_bps: (0.6 - ratio) * 50.0,
            source: "macd_exhaustion".to_string(),
            timeframe: timeframe.to_string(),
            reasoning: format!("MACD hist ratio={ratio:.2} < 0.6, bullish exhaustion → CloseLong"),
            ts_ms,
        })
    } else if ratio < 0.6 && macd < 0.0 {
        // Bearish momentum exhausting / 空頭動量衰竭
        Some(Signal {
            symbol: symbol.to_string(),
            direction: SignalDirection::CloseShort,
            confidence: (0.6 - ratio + 0.3).min(1.0),
            edge_bps: (0.6 - ratio) * 50.0,
            source: "macd_exhaustion".to_string(),
            timeframe: timeframe.to_string(),
            reasoning: format!("MACD hist ratio={ratio:.2} < 0.6, bearish exhaustion → CloseShort"),
            ts_ms,
        })
    } else {
        None
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Rule 7: RSI Divergence / RSI 背離
// ═══════════════════════════════════════════════════════════════════════════════

/// RSI divergence signal.
/// RSI 背離信號。
///
/// Detects price-RSI divergence using `stoch_k` as a proxy for recent price
/// momentum relative to RSI:
///   - High stoch_k (>70) + low RSI (<50) → bearish divergence → CloseLong
///   - Low stoch_k (<30) + high RSI (>50) → bullish divergence → CloseShort
///
/// The 3-point divergence threshold is approximated by requiring a stoch-RSI
/// spread of at least 20 points (proxy for "price higher high + RSI lower high
/// by 3+ pts").
pub fn rsi_divergence(
    symbol: &str,
    timeframe: &str,
    input: &IndicatorInput,
    ts_ms: u64,
) -> Option<Signal> {
    let rsi = input.rsi?;
    let stoch_k = input.stoch_k?;

    // Bearish divergence: price making highs (stoch_k > 70) but RSI weakening (< 50)
    // 空頭背離：價格創高（stoch_k > 70）但 RSI 走弱（< 50）
    let rsi_stoch_spread = (stoch_k - rsi).abs();
    if stoch_k > 70.0 && rsi < 50.0 && rsi_stoch_spread >= 20.0 {
        let confidence = ((rsi_stoch_spread - 20.0) / 30.0 + 0.4).min(1.0);
        Some(Signal {
            symbol: symbol.to_string(),
            direction: SignalDirection::CloseLong,
            confidence,
            edge_bps: rsi_stoch_spread,
            source: "rsi_divergence".to_string(),
            timeframe: timeframe.to_string(),
            reasoning: format!(
                "Bearish divergence: stoch_k={stoch_k:.1}, RSI={rsi:.1}, spread={rsi_stoch_spread:.1} → CloseLong"
            ),
            ts_ms,
        })
    }
    // Bullish divergence: price making lows (stoch_k < 30) but RSI holding (> 50)
    // 多頭背離：價格創低（stoch_k < 30）但 RSI 撐住（> 50）
    else if stoch_k < 30.0 && rsi > 50.0 && rsi_stoch_spread >= 20.0 {
        let confidence = ((rsi_stoch_spread - 20.0) / 30.0 + 0.4).min(1.0);
        Some(Signal {
            symbol: symbol.to_string(),
            direction: SignalDirection::CloseShort,
            confidence,
            edge_bps: rsi_stoch_spread,
            source: "rsi_divergence".to_string(),
            timeframe: timeframe.to_string(),
            reasoning: format!(
                "Bullish divergence: stoch_k={stoch_k:.1}, RSI={rsi:.1}, spread={rsi_stoch_spread:.1} → CloseShort"
            ),
            ts_ms,
        })
    } else {
        None
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Rule 8: Regime Detector / 市場狀態偵測
// ═══════════════════════════════════════════════════════════════════════════════

/// Market regime detection — classifies current market state.
/// 市場狀態偵測 — 分類當前市場狀態。
///
/// Regimes:
///   - "squeeze": low bandwidth + low ADX → consolidation
///   - "trending": high ADX (>25) → directional
///   - "volatile": high ATR% (>3%) → high volatility
///   - "ranging": default fallback
///
/// Always returns Neutral direction with regime metadata in reasoning.
pub fn regime_detector(
    symbol: &str,
    timeframe: &str,
    input: &IndicatorInput,
    ts_ms: u64,
) -> Option<Signal> {
    let adx = input.adx;
    let bandwidth = input.bb_bandwidth;
    let atr_pct = input.atr_percent;

    // Need at least one indicator to classify / 至少需要一個指標來分類
    if adx.is_none() && bandwidth.is_none() && atr_pct.is_none() {
        return None;
    }

    let (regime, confidence) = classify_regime(adx, bandwidth, atr_pct);

    Some(Signal {
        symbol: symbol.to_string(),
        direction: SignalDirection::Neutral,
        confidence,
        edge_bps: 0.0,
        source: "regime_detector".to_string(),
        timeframe: timeframe.to_string(),
        reasoning: format!(
            "Regime={regime} (ADX={}, BW={}, ATR%={})",
            adx.map_or("N/A".to_string(), |v| format!("{v:.1}")),
            bandwidth.map_or("N/A".to_string(), |v| format!("{v:.4}")),
            atr_pct.map_or("N/A".to_string(), |v| format!("{v:.2}%")),
        ),
        ts_ms,
    })
}

/// Classify market regime from indicator values.
/// 從指標值分類市場狀態。
fn classify_regime(
    adx: Option<f64>,
    bandwidth: Option<f64>,
    atr_pct: Option<f64>,
) -> (&'static str, f64) {
    // Squeeze: low bandwidth AND low ADX / 擠壓：低帶寬且低 ADX
    if let (Some(bw), Some(a)) = (bandwidth, adx) {
        if bw < 0.02 && a < 20.0 {
            return ("squeeze", 0.7);
        }
    }

    // Trending: high ADX / 趨勢：高 ADX
    if let Some(a) = adx {
        if a > 25.0 {
            return ("trending", (a / 50.0).min(1.0));
        }
    }

    // Volatile: high ATR% / 高波動：高 ATR%
    if let Some(atr) = atr_pct {
        if atr > 3.0 {
            return ("volatile", (atr / 10.0).min(1.0));
        }
    }

    // Default: ranging / 默認：震盪
    ("ranging", 0.4)
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    /// Helper: build an IndicatorInput with all None. / 輔助：建立全 None 的輸入。
    fn empty_input() -> IndicatorInput {
        IndicatorInput {
            rsi: None,
            sma: None,
            ema: None,
            macd: None,
            macd_signal: None,
            macd_histogram: None,
            bb_percent_b: None,
            bb_bandwidth: None,
            atr_percent: None,
            stoch_k: None,
            adx: None,
            volume_ratio: None,
        }
    }

    // ── Rule 1: RSI overbought/oversold ──

    #[test]
    fn test_rsi_oversold_long() {
        let mut input = empty_input();
        input.rsi = Some(20.0);
        let sig = rsi_overbought_oversold("BTCUSDT", "15m", &input, 1000).unwrap();
        assert_eq!(sig.direction, SignalDirection::Long);
        assert!(sig.confidence > 0.3);
        assert!(sig.confidence <= 1.0);
    }

    #[test]
    fn test_rsi_overbought_short() {
        let mut input = empty_input();
        input.rsi = Some(85.0);
        let sig = rsi_overbought_oversold("BTCUSDT", "15m", &input, 1000).unwrap();
        assert_eq!(sig.direction, SignalDirection::Short);
        assert!(sig.confidence > 0.3);
    }

    #[test]
    fn test_rsi_neutral_zone() {
        let mut input = empty_input();
        input.rsi = Some(50.0);
        assert!(rsi_overbought_oversold("BTCUSDT", "15m", &input, 1000).is_none());
    }

    // ── Rule 2: MA crossover ──

    #[test]
    fn test_ma_crossover_long() {
        let mut input = empty_input();
        input.ema = Some(100.1); // fast
        input.sma = Some(100.0); // slow — 0.1% divergence
        let sig = ma_crossover("BTCUSDT", "1h", &input, 2000).unwrap();
        assert_eq!(sig.direction, SignalDirection::Long);
    }

    #[test]
    fn test_ma_crossover_short() {
        let mut input = empty_input();
        input.ema = Some(99.9);
        input.sma = Some(100.0);
        let sig = ma_crossover("BTCUSDT", "1h", &input, 2000).unwrap();
        assert_eq!(sig.direction, SignalDirection::Short);
    }

    #[test]
    fn test_ma_crossover_too_close() {
        let mut input = empty_input();
        input.ema = Some(100.001);
        input.sma = Some(100.0); // only 0.001% — below 0.05% threshold
        assert!(ma_crossover("BTCUSDT", "1h", &input, 2000).is_none());
    }

    // ── Rule 3: Bollinger reversion ──

    #[test]
    fn test_bollinger_long() {
        let mut input = empty_input();
        input.bb_percent_b = Some(0.05);
        input.rsi = Some(35.0);
        input.bb_bandwidth = Some(0.03);
        let sig = bollinger_reversion("BTCUSDT", "4h", &input, 3000).unwrap();
        assert_eq!(sig.direction, SignalDirection::Long);
    }

    #[test]
    fn test_bollinger_short() {
        let mut input = empty_input();
        input.bb_percent_b = Some(0.95);
        input.rsi = Some(65.0);
        input.bb_bandwidth = Some(0.03);
        let sig = bollinger_reversion("BTCUSDT", "4h", &input, 3000).unwrap();
        assert_eq!(sig.direction, SignalDirection::Short);
    }

    #[test]
    fn test_bollinger_low_bandwidth_rejected() {
        let mut input = empty_input();
        input.bb_percent_b = Some(0.05);
        input.rsi = Some(35.0);
        input.bb_bandwidth = Some(0.005); // below 0.01 minimum
        assert!(bollinger_reversion("BTCUSDT", "4h", &input, 3000).is_none());
    }

    // ── Rule 4: MACD crossover ──

    #[test]
    fn test_macd_crossover_long() {
        let mut input = empty_input();
        input.macd = Some(0.5);
        input.macd_histogram = Some(0.2);
        let sig = macd_crossover("ETHUSDT", "15m", &input, 4000).unwrap();
        assert_eq!(sig.direction, SignalDirection::Long);
    }

    #[test]
    fn test_macd_crossover_short() {
        let mut input = empty_input();
        input.macd = Some(-0.5);
        input.macd_histogram = Some(-0.2);
        let sig = macd_crossover("ETHUSDT", "15m", &input, 4000).unwrap();
        assert_eq!(sig.direction, SignalDirection::Short);
    }

    // ── Rule 5: RSI exit ──

    #[test]
    fn test_rsi_exit_close_long() {
        let mut input = empty_input();
        input.rsi = Some(58.0);
        let sig = rsi_exit("BTCUSDT", "1h", &input, 5000).unwrap();
        assert_eq!(sig.direction, SignalDirection::CloseLong);
        assert!((sig.confidence - 0.6).abs() < 1e-10);
    }

    #[test]
    fn test_rsi_exit_close_short() {
        let mut input = empty_input();
        input.rsi = Some(42.0);
        let sig = rsi_exit("BTCUSDT", "1h", &input, 5000).unwrap();
        assert_eq!(sig.direction, SignalDirection::CloseShort);
    }

    // ── Rule 6: MACD exhaustion ──

    #[test]
    fn test_macd_exhaustion_close_long() {
        let mut input = empty_input();
        input.macd = Some(0.5);
        input.macd_signal = Some(0.4);
        input.macd_histogram = Some(0.1); // ratio = 0.1/0.4 = 0.25 < 0.6
        let sig = macd_exhaustion("BTCUSDT", "1h", &input, 6000).unwrap();
        assert_eq!(sig.direction, SignalDirection::CloseLong);
    }

    #[test]
    fn test_macd_exhaustion_no_signal_strong() {
        let mut input = empty_input();
        input.macd = Some(0.5);
        input.macd_signal = Some(0.3);
        input.macd_histogram = Some(0.25); // ratio = 0.25/0.3 = 0.83 > 0.6
        assert!(macd_exhaustion("BTCUSDT", "1h", &input, 6000).is_none());
    }

    // ── Rule 7: RSI divergence ──

    #[test]
    fn test_rsi_divergence_bearish() {
        let mut input = empty_input();
        input.rsi = Some(45.0);
        input.stoch_k = Some(75.0); // spread = 30 >= 20
        let sig = rsi_divergence("BTCUSDT", "4h", &input, 7000).unwrap();
        assert_eq!(sig.direction, SignalDirection::CloseLong);
    }

    #[test]
    fn test_rsi_divergence_bullish() {
        let mut input = empty_input();
        input.rsi = Some(55.0);
        input.stoch_k = Some(25.0); // spread = 30 >= 20
        let sig = rsi_divergence("BTCUSDT", "4h", &input, 7000).unwrap();
        assert_eq!(sig.direction, SignalDirection::CloseShort);
    }

    // ── Rule 8: Regime detector ──

    #[test]
    fn test_regime_trending() {
        let mut input = empty_input();
        input.adx = Some(35.0);
        let sig = regime_detector("BTCUSDT", "1d", &input, 8000).unwrap();
        assert_eq!(sig.direction, SignalDirection::Neutral);
        assert!(sig.reasoning.contains("trending"));
    }

    #[test]
    fn test_regime_squeeze() {
        let mut input = empty_input();
        input.adx = Some(15.0);
        input.bb_bandwidth = Some(0.01);
        let sig = regime_detector("BTCUSDT", "1d", &input, 8000).unwrap();
        assert_eq!(sig.direction, SignalDirection::Neutral);
        assert!(sig.reasoning.contains("squeeze"));
    }

    #[test]
    fn test_regime_no_data() {
        let input = empty_input();
        assert!(regime_detector("BTCUSDT", "1d", &input, 8000).is_none());
    }
}
