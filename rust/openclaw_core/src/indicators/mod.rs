//! Technical indicator engine — 16 indicators with Kahan compensated summation.
//! 技術指標引擎 — 16 個指標，使用 Kahan 補償求和。
//!
//! MODULE_NOTE (中文):
//!   IndicatorEngine — 完整的技術指標計算引擎。包含 16 個指標：SMA(20)、SMA(50)、
//!   EMA(12)、EMA(26)、RSI、MACD、布林帶、ATR(14)、ATR(5)、隨機指標、KAMA、ADX、
//!   赫斯特指數、EWMA 波動率、量比、唐奇安通道。所有涉及累加的運算使用 Kahan
//!   補償求和確保浮點精度 [V3-QC-2]。
//!   提供 `IndicatorSnapshot` 一次性計算全部指標的快照。
//!   新增 `get_conservative_atr()` = max(atr_5, atr_14)，與 Python 端對齊。
//!
//! MODULE_NOTE (English):
//!   IndicatorEngine — complete technical indicator calculation engine. Contains
//!   16 indicators: SMA(20), SMA(50), EMA(12), EMA(26), RSI, MACD, Bollinger Bands,
//!   ATR(14), ATR(5), Stochastic, KAMA, ADX, Hurst Exponent, EWMA Volatility,
//!   Volume Ratio, Donchian Channel.
//!   All summation operations use Kahan compensated summation for floating-point
//!   accuracy [V3-QC-2]. Provides `IndicatorSnapshot` for one-shot computation.
//!   Added `get_conservative_atr()` = max(atr_5, atr_14), aligned with Python side.
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
pub use trend::{
    donchian, donchian_prior, ema, kama, macd, sma, DonchianResult, KamaResult, MacdResult,
};
pub use volatility::{
    atr, bollinger, ewma_vol, hurst, AtrResult, BollingerResult, EwmaVolResult, HurstResult,
};
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

/// G7-02 (2026-04-24): Default EWMA volatility decay constant (lambda).
/// 0.97 mirrors the pre-G7-02 hardcoded value and the RiskMetrics convention
/// for sub-daily series; per-timeframe overrides flow in via
/// `IndicatorEngine::compute_all_with_lambda`.
/// G7-02：預設 EWMA 波動率衰減常數，0.97 保留 G7-02 前的硬編碼行為。
pub const DEFAULT_EWMA_VOL_LAMBDA: f64 = 0.97;

impl IndicatorEngine {
    /// Compute all indicators for given OHLCV data with default parameters.
    /// 使用默認參數計算給定 OHLCV 數據的所有指標。
    ///
    /// Default params / 默認參數:
    ///   SMA(20), SMA(50), EMA(12), EMA(26), RSI(14), MACD(12,26,9),
    ///   Bollinger(20,2.0), ATR(14), ATR(5), Stochastic(14,3), KAMA(10,2,30),
    ///   ADX(14), Hurst(10,50), EWMA_vol(DEFAULT_EWMA_VOL_LAMBDA=0.97),
    ///   VolumeRatio(20), Donchian(20)
    ///
    /// G7-02: thin wrapper over `compute_all_with_lambda` using
    /// `DEFAULT_EWMA_VOL_LAMBDA`. Existing call sites stay bit-identical.
    /// G7-02：薄包裝，保留既有呼叫端 bit-identical 行為。
    pub fn compute_all(
        high: &[f64],
        low: &[f64],
        close: &[f64],
        volume: &[f64],
    ) -> IndicatorSnapshot {
        Self::compute_all_with_lambda(high, low, close, volume, DEFAULT_EWMA_VOL_LAMBDA)
    }

    /// G7-02 (2026-04-24): Compute all indicators with an explicit EWMA Vol
    /// lambda decay constant. Wired from `RiskConfig.ewma_vol` so operators
    /// can tune lambda per timeframe (1m / 5m / 1h / 4h …) via TOML hot-reload.
    /// All other indicator parameters remain at the `compute_all` defaults.
    ///
    /// G7-02：以顯式 EWMA Vol lambda 計算全部指標。lambda 由
    /// `RiskConfig.ewma_vol` 透過 TOML 熱重載驅動，operator 可逐 timeframe 調整。
    pub fn compute_all_with_lambda(
        high: &[f64],
        low: &[f64],
        close: &[f64],
        volume: &[f64],
        ewma_lambda: f64,
    ) -> IndicatorSnapshot {
        // SMA / EMA with additional periods to match Python side.
        // 額外週期的 SMA / EMA，與 Python 端對齊。
        let sma_50_val = sma(close, 50);
        let ema_26_val = ema(close, 26);

        // ATR(5) — short-term volatility, used by conservative_atr.
        // ATR(5) — 短期波動率，用於 conservative_atr。
        let atr_5_val = atr(high, low, close, 5);

        IndicatorSnapshot {
            sma_20: sma(close, 20),
            sma_50: sma_50_val,
            ema_12: ema(close, 12),
            ema_26: ema_26_val,
            rsi_14: rsi(close, 14),
            macd: macd(close, 12, 26, 9),
            bollinger: bollinger(close, 20, 2.0),
            atr_14: atr(high, low, close, 14),
            atr_5: atr_5_val,
            stochastic: stochastic(high, low, close, 14, 3),
            kama: kama(close, 10, 2, 30),
            adx: adx(high, low, close, 14),
            hurst: hurst(
                close,
                10,
                50,
                volatility::DEFAULT_HURST_TRENDING_THRESHOLD,
                volatility::DEFAULT_HURST_MEAN_REVERTING_THRESHOLD,
            ),
            ewma_vol: ewma_vol(close, ewma_lambda),
            volume_ratio: volume_ratio(volume, 20),
            donchian: donchian_prior(high, low, close, 20),
        }
    }
}

/// Snapshot of all indicator values at a single point in time.
/// 單一時間點的所有指標值快照。
///
/// Contains 16 indicators aligned with the Python IndicatorEngine.
/// 包含 16 個指標，與 Python IndicatorEngine 對齊。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct IndicatorSnapshot {
    pub sma_20: Option<f64>,
    /// SMA(50) — medium-term trend filter, aligned with Python side.
    /// SMA(50) — 中期趨勢過濾器，與 Python 端對齊。
    pub sma_50: Option<f64>,
    pub ema_12: Option<f64>,
    /// EMA(26) — medium-term exponential trend, aligned with Python side.
    /// EMA(26) — 中期指數趨勢，與 Python 端對齊。
    pub ema_26: Option<f64>,
    pub rsi_14: Option<f64>,
    pub macd: Option<MacdResult>,
    pub bollinger: Option<BollingerResult>,
    /// ATR(14) — standard period average true range.
    /// ATR(14) — 標準週期平均真實波幅。
    pub atr_14: Option<AtrResult>,
    /// ATR(5) — short-term average true range, used by conservative_atr.
    /// ATR(5) — 短期平均真實波幅，用於 conservative_atr。
    pub atr_5: Option<AtrResult>,
    pub stochastic: Option<StochResult>,
    pub kama: Option<KamaResult>,
    pub adx: Option<AdxResult>,
    pub hurst: Option<HurstResult>,
    pub ewma_vol: Option<EwmaVolResult>,
    pub volume_ratio: Option<f64>,
    pub donchian: Option<DonchianResult>,
}

impl IndicatorSnapshot {
    /// Get conservative ATR = max(atr_5, atr_14). Aligned with Python get_conservative_atr().
    /// 取保守 ATR = max(atr_5, atr_14)。與 Python get_conservative_atr() 對齊。
    ///
    /// Returns the larger of the two ATR values (absolute), providing a more
    /// conservative volatility estimate for position sizing and stop-loss.
    /// 返回兩個 ATR 值（絕對值）中較大者，為倉位管理和止損提供更保守的波動率估計。
    pub fn get_conservative_atr(&self) -> Option<AtrResult> {
        match (&self.atr_5, &self.atr_14) {
            (Some(a5), Some(a14)) => {
                if a5.atr >= a14.atr {
                    Some(a5.clone())
                } else {
                    Some(a14.clone())
                }
            }
            (Some(a5), None) => Some(a5.clone()),
            (None, Some(a14)) => Some(a14.clone()),
            (None, None) => None,
        }
    }
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
        // 100 根合成 K 線 — 足夠計算所有指標
        let n = 100;
        let close: Vec<f64> = (0..n)
            .map(|i| 100.0 + (i as f64 * 0.1).sin() * 5.0)
            .collect();
        let high: Vec<f64> = close.iter().map(|c| c + 1.0).collect();
        let low: Vec<f64> = close.iter().map(|c| c - 1.0).collect();
        let volume: Vec<f64> = (0..n)
            .map(|i| 1000.0 + (i as f64 * 0.3).cos() * 200.0)
            .collect();

        let snap = IndicatorEngine::compute_all(&high, &low, &close, &volume);

        assert!(snap.sma_20.is_some());
        assert!(snap.sma_50.is_some());
        assert!(snap.ema_12.is_some());
        assert!(snap.ema_26.is_some());
        assert!(snap.rsi_14.is_some());
        assert!(snap.macd.is_some());
        assert!(snap.bollinger.is_some());
        assert!(snap.atr_14.is_some());
        assert!(snap.atr_5.is_some());
        assert!(snap.stochastic.is_some());
        assert!(snap.kama.is_some());
        assert!(snap.adx.is_some());
        assert!(snap.hurst.is_some());
        assert!(snap.ewma_vol.is_some());
        assert!(snap.volume_ratio.is_some());
        assert!(snap.donchian.is_some());
    }

    #[test]
    fn test_compute_all_uses_prior_bar_donchian_snapshot() {
        let mut high = vec![100.0; 21];
        let mut low = vec![90.0; 21];
        let close = vec![95.0; 21];
        let volume = vec![1000.0; 21];
        high[19] = 110.0;
        low[19] = 88.0;
        high[20] = 999.0;
        low[20] = 1.0;

        let snap = IndicatorEngine::compute_all(&high, &low, &close, &volume);
        let donchian = snap
            .donchian
            .expect("21 bars should produce prior Donchian");

        assert!(
            (donchian.upper - 110.0).abs() < 1e-12,
            "runtime indicator snapshot must exclude the current bar high"
        );
        assert!(
            (donchian.lower - 88.0).abs() < 1e-12,
            "runtime indicator snapshot must exclude the current bar low"
        );
    }

    #[test]
    fn test_compute_all_insufficient_data() {
        // 5 bars — most indicators should return None gracefully
        // 5 根 K 線 — 大多數指標應優雅地返回 None
        let close = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let high = vec![1.5, 2.5, 3.5, 4.5, 5.5];
        let low = vec![0.5, 1.5, 2.5, 3.5, 4.5];
        let volume = vec![100.0, 200.0, 300.0, 400.0, 500.0];

        let snap = IndicatorEngine::compute_all(&high, &low, &close, &volume);

        // Most should be None with only 5 bars
        assert!(snap.sma_20.is_none());
        assert!(snap.sma_50.is_none());
        assert!(snap.ema_26.is_none());
        assert!(snap.rsi_14.is_none());
        assert!(snap.macd.is_none());
        assert!(snap.adx.is_none());
        assert!(snap.hurst.is_none());
        assert!(snap.donchian.is_none());
        // ATR(5) needs period+1=6 bars, so should be None with 5 bars
        // ATR(5) 需要 period+1=6 根 K 線，5 根時應為 None
        assert!(snap.atr_5.is_none());
    }

    #[test]
    fn test_conservative_atr() {
        // Test get_conservative_atr() returns max(atr_5, atr_14).
        // 測試 get_conservative_atr() 返回 max(atr_5, atr_14)。
        let n = 100;
        let close: Vec<f64> = (0..n)
            .map(|i| 100.0 + (i as f64 * 0.1).sin() * 5.0)
            .collect();
        let high: Vec<f64> = close.iter().map(|c| c + 1.0).collect();
        let low: Vec<f64> = close.iter().map(|c| c - 1.0).collect();
        let volume: Vec<f64> = (0..n).map(|_| 1000.0).collect();

        let snap = IndicatorEngine::compute_all(&high, &low, &close, &volume);
        let conservative = snap.get_conservative_atr();
        assert!(conservative.is_some());

        let c = conservative.unwrap();
        let a5 = snap.atr_5.unwrap();
        let a14 = snap.atr_14.unwrap();
        // Should be the max of the two
        assert!((c.atr - a5.atr.max(a14.atr)).abs() < 1e-12);
    }

    #[test]
    fn test_conservative_atr_partial() {
        // When only one ATR is available, conservative_atr should return it.
        // 當只有一個 ATR 可用時，conservative_atr 應返回它。
        let mut snap = IndicatorSnapshot::default();
        assert!(snap.get_conservative_atr().is_none());

        snap.atr_14 = Some(AtrResult {
            atr: 2.0,
            atr_percent: 1.0,
        });
        let c = snap.get_conservative_atr().unwrap();
        assert!((c.atr - 2.0).abs() < 1e-12);

        snap.atr_5 = Some(AtrResult {
            atr: 3.0,
            atr_percent: 1.5,
        });
        let c = snap.get_conservative_atr().unwrap();
        assert!((c.atr - 3.0).abs() < 1e-12);
    }
}
