//! Technical indicator engine — 13 indicators with Kahan compensated summation.
//! 技術指標引擎 — 13 個指標，使用 Kahan 補償求和。
//!
//! MODULE_NOTE (中文):
//!   IndicatorEngine — 完整的技術指標計算引擎。包含 13 個指標：SMA、EMA、RSI、
//!   MACD、布林帶、ATR、隨機指標、KAMA、ADX、赫斯特指數、EWMA 波動率、量比、
//!   唐奇安通道。所有涉及累加的運算使用 Kahan 補償求和確保浮點精度 [V3-QC-2]。
//!   提供 `IndicatorSnapshot` 一次性計算全部指標的快照。
//!
//! MODULE_NOTE (English):
//!   IndicatorEngine — complete technical indicator calculation engine. Contains
//!   13 indicators: SMA, EMA, RSI, MACD, Bollinger Bands, ATR, Stochastic, KAMA,
//!   ADX, Hurst Exponent, EWMA Volatility, Volume Ratio, Donchian Channel.
//!   All summation operations use Kahan compensated summation for floating-point
//!   accuracy [V3-QC-2]. Provides `IndicatorSnapshot` for one-shot computation.
//!
//! Ported from: Python `IndicatorEngine` + `SignalEngine` indicator subset.
//! 移植自：Python `IndicatorEngine` + `SignalEngine` 指標子集。
//!
//! Safety invariant / 安全不變量:
//!   Pure computation — no I/O, no side effects, no order placement.
//!   純計算 — 無 I/O、無副作用、不下單。

use serde::{Deserialize, Serialize};

mod momentum;
mod trend;
mod volatility;
mod volume;

// Re-export all indicator functions and result types.
// 重新導出所有指標函數和結果類型。
pub use momentum::{adx, rsi, stochastic, AdxResult, StochResult};
pub use trend::{donchian, ema, kama, macd, sma, DonchianResult, KamaResult, MacdResult};
pub use volatility::{atr, bollinger, ewma_vol, hurst, AtrResult, BollingerResult, EwmaVolResult, HurstResult};
pub use volume::volume_ratio;

// ═══════════════════════════════════════════════════════════════════════════════
// Kahan Compensated Summation / Kahan 補償求和
// ═══════════════════════════════════════════════════════════════════════════════

/// Kahan compensated summation for improved floating-point accuracy [V3-QC-2].
/// Kahan 補償求和，提高浮點精度 [V3-QC-2]。
///
/// Equivalent to Python's `math.fsum()` in spirit — eliminates O(n) rounding
/// drift when summing large sequences of floating-point numbers.
/// 精神上等同於 Python 的 `math.fsum()` — 消除大量浮點數求和時的 O(n) 捨入漂移。
pub(crate) fn kahan_sum(values: &[f64]) -> f64 {
    let mut sum = 0.0_f64;
    let mut comp = 0.0_f64;
    for &v in values {
        let y = v - comp;
        let t = sum + y;
        comp = (t - sum) - y;
        sum = t;
    }
    sum
}

// ═══════════════════════════════════════════════════════════════════════════════
// IndicatorEngine / 指標引擎
// ═══════════════════════════════════════════════════════════════════════════════

/// Stateless indicator engine — wraps all 13 indicators into a single entry point.
/// 無狀態指標引擎 — 將全部 13 個指標封裝為單一入口。
pub struct IndicatorEngine;

impl IndicatorEngine {
    /// Compute all indicators for given OHLCV data with default parameters.
    /// 使用默認參數計算給定 OHLCV 數據的所有指標。
    ///
    /// Default params / 默認參數:
    ///   SMA(20), EMA(12), RSI(14), MACD(12,26,9), Bollinger(20,2.0),
    ///   ATR(14), Stochastic(14,3), KAMA(10,2,30), ADX(14),
    ///   Hurst(10,50), EWMA_vol(0.97), VolumeRatio(20), Donchian(20)
    pub fn compute_all(
        high: &[f64],
        low: &[f64],
        close: &[f64],
        volume: &[f64],
    ) -> IndicatorSnapshot {
        IndicatorSnapshot {
            sma_20: sma(close, 20),
            ema_12: ema(close, 12),
            rsi_14: rsi(close, 14),
            macd: macd(close, 12, 26, 9),
            bollinger: bollinger(close, 20, 2.0),
            atr: atr(high, low, close, 14),
            stochastic: stochastic(high, low, close, 14, 3),
            kama: kama(close, 10, 2, 30),
            adx: adx(high, low, close, 14),
            hurst: hurst(close, 10, 50),
            ewma_vol: ewma_vol(close, 0.97),
            volume_ratio: volume_ratio(volume, 20),
            donchian: donchian(high, low, close, 20),
        }
    }
}

/// Snapshot of all indicator values at a single point in time.
/// 單一時間點的所有指標值快照。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct IndicatorSnapshot {
    pub sma_20: Option<f64>,
    pub ema_12: Option<f64>,
    pub rsi_14: Option<f64>,
    pub macd: Option<MacdResult>,
    pub bollinger: Option<BollingerResult>,
    pub atr: Option<AtrResult>,
    pub stochastic: Option<StochResult>,
    pub kama: Option<KamaResult>,
    pub adx: Option<AdxResult>,
    pub hurst: Option<HurstResult>,
    pub ewma_vol: Option<EwmaVolResult>,
    pub volume_ratio: Option<f64>,
    pub donchian: Option<DonchianResult>,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kahan_sum_accuracy() {
        // Classic Kahan test: summing many small values
        let vals: Vec<f64> = (0..10_000).map(|_| 0.1).collect();
        let result = kahan_sum(&vals);
        assert!((result - 1000.0).abs() < 1e-10);
    }

    #[test]
    fn test_kahan_sum_empty() {
        assert!((kahan_sum(&[]) - 0.0).abs() < 1e-15);
    }

    #[test]
    fn test_compute_all_sufficient_data() {
        // 100 bars of synthetic data — enough for all indicators
        let n = 100;
        let close: Vec<f64> = (0..n)
            .map(|i| 100.0 + (i as f64 * 0.1).sin() * 5.0)
            .collect();
        let high: Vec<f64> = close.iter().map(|c| c + 1.0).collect();
        let low: Vec<f64> = close.iter().map(|c| c - 1.0).collect();
        let volume: Vec<f64> = (0..n).map(|i| 1000.0 + (i as f64 * 0.3).cos() * 200.0).collect();

        let snap = IndicatorEngine::compute_all(&high, &low, &close, &volume);

        assert!(snap.sma_20.is_some());
        assert!(snap.ema_12.is_some());
        assert!(snap.rsi_14.is_some());
        assert!(snap.macd.is_some());
        assert!(snap.bollinger.is_some());
        assert!(snap.atr.is_some());
        assert!(snap.stochastic.is_some());
        assert!(snap.kama.is_some());
        assert!(snap.adx.is_some());
        assert!(snap.hurst.is_some());
        assert!(snap.ewma_vol.is_some());
        assert!(snap.volume_ratio.is_some());
        assert!(snap.donchian.is_some());
    }

    #[test]
    fn test_compute_all_insufficient_data() {
        // 5 bars — most indicators should return None gracefully
        let close = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let high = vec![1.5, 2.5, 3.5, 4.5, 5.5];
        let low = vec![0.5, 1.5, 2.5, 3.5, 4.5];
        let volume = vec![100.0, 200.0, 300.0, 400.0, 500.0];

        let snap = IndicatorEngine::compute_all(&high, &low, &close, &volume);

        // Most should be None with only 5 bars
        assert!(snap.sma_20.is_none());
        assert!(snap.rsi_14.is_none());
        assert!(snap.macd.is_none());
        assert!(snap.adx.is_none());
        assert!(snap.hurst.is_none());
        assert!(snap.donchian.is_none());
    }
}
