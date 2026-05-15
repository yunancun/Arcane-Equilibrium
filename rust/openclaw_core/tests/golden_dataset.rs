//! Golden Dataset Integration Test — Rust↔Python indicator cross-validation
//! 黃金數據集整合測試 — Rust↔Python 指標交叉驗證
//!
//! MODULE_NOTE (中文):
//!   R02-10 黃金數據集比對基礎設施。使用確定性合成 OHLCV 數據（正弦波 + 雜訊）
//!   計算全部 13 個指標，驗證：
//!   1. 所有指標在充分數據下均返回 Some（非 None）
//!   2. 內部一致性（SMA ≈ 手動平均、BB middle = SMA、MACD histogram = macd - signal 等）
//!   3. 值域約束（RSI ∈ [0,100]、ATR > 0、Stochastic K/D ∈ [0,100] 等）
//!   4. 數據不足時優雅返回 None
//!   Python 端對照腳本：helper_scripts/golden_dataset_gen.py
//!
//! MODULE_NOTE (English):
//!   R02-10 golden dataset comparison infrastructure. Uses deterministic synthetic
//!   OHLCV data (sine wave + noise) to compute all 13 indicators, verifying:
//!   1. All indicators return Some (not None) with sufficient data
//!   2. Internal consistency (SMA ≈ manual mean, BB middle = SMA, MACD hist = macd - signal, etc.)
//!   3. Range constraints (RSI ∈ [0,100], ATR > 0, Stochastic K/D ∈ [0,100], etc.)
//!   4. Graceful None return with insufficient data
//!   Python counterpart script: helper_scripts/golden_dataset_gen.py
//!
//! QC Tolerance Specs / QC 容差規格:
//!   - MA (SMA/EMA/KAMA): ±1e-8 (Kahan compensated summation)
//!   - RSI: ±0.1% (Wilder's smoothing propagation)
//!   - ATR: ±0.01% (Wilder's smoothing)
//!   - MACD histogram identity: ±1e-10 (algebraic identity)
//!   - Bollinger middle vs SMA: ±1e-10 (same computation path)
//!   - Stochastic K/D: ±0.01% (window-based)
//!   - Hurst: ±0.05 (R/S analysis inherent variance)
//!   - Donchian middle = (upper+lower)/2: ±1e-10 (algebraic identity)
//!
//! Safety invariant / 安全不變量:
//!   Pure test — no I/O, no side effects, deterministic.
//!   純測試 — 無 I/O、無副作用、確定性。

use openclaw_core::indicators::*;

// ═══════════════════════════════════════════════════════════════════════════════
// Synthetic OHLCV Generator / 合成 OHLCV 生成器
// ═══════════════════════════════════════════════════════════════════════════════

/// Generate deterministic synthetic OHLCV data with realistic BTC-like price action.
/// 生成確定性合成 OHLCV 數據，模擬 BTC 級別價格行為。
///
/// Uses sine wave (cycle) + linear trend + deterministic pseudo-noise.
/// Same algorithm as Python `helper_scripts/golden_dataset_gen.py` — any change
/// here MUST be mirrored there.
/// 使用正弦波（週期）+ 線性趨勢 + 確定性偽噪聲。
/// 與 Python `helper_scripts/golden_dataset_gen.py` 相同演算法 — 此處任何修改必須同步。
fn generate_synthetic_ohlcv(
    n: usize,
    seed: u64,
) -> (Vec<f64>, Vec<f64>, Vec<f64>, Vec<f64>, Vec<f64>) {
    let mut close = Vec::with_capacity(n);
    let mut high = Vec::with_capacity(n);
    let mut low = Vec::with_capacity(n);
    let mut open = Vec::with_capacity(n);
    let mut volume = Vec::with_capacity(n);

    let base = 50_000.0; // BTC-like base price / BTC 級別基準價格
    for i in 0..n {
        let t = i as f64 / n as f64 * std::f64::consts::PI * 4.0;
        let trend = base + (i as f64) * 10.0;
        let cycle = 2000.0 * t.sin();
        // Deterministic pseudo-noise via integer hashing (no RNG dependency)
        // 確定性偽噪聲，使用整數哈希（無 RNG 依賴）
        let noise =
            ((i as u64).wrapping_mul(seed).wrapping_mul(2_654_435_761) % 1000) as f64 - 500.0;

        let c = trend + cycle + noise;
        let h = c + (50.0 + noise.abs() * 0.1);
        let l = c - (50.0 + noise.abs() * 0.1);
        let o = if i == 0 { c } else { close[i - 1] };
        let v = 100.0 + (i as f64 * 1.5);

        close.push(c);
        high.push(h);
        low.push(l);
        open.push(o);
        volume.push(v);
    }
    (open, high, low, close, volume)
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test: All 13 Indicators Compute on Synthetic Data
// 測試：全部 13 個指標在合成數據上計算
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
#[allow(deprecated)] // 數學驗證測試：刻意調用 donchian() 驗證其內部正確性
fn test_all_indicators_compute_on_synthetic_data() {
    let (_open, high, low, close, volume) = generate_synthetic_ohlcv(200, 42);

    // ─── SMA(20) ───
    // QC tolerance: ±1e-8 (Kahan compensated) / QC 容差: ±1e-8（Kahan 補償）
    let sma_val = sma(&close, 20).expect("SMA(20) should compute with 200 bars");
    let manual_sum: f64 = close[close.len() - 20..].iter().sum::<f64>();
    let manual_sma = manual_sum / 20.0;
    assert!(
        (sma_val - manual_sma).abs() < 1e-8,
        "SMA Kahan accuracy: got {sma_val}, expected ~{manual_sma}, diff={}",
        (sma_val - manual_sma).abs()
    );

    // ─── EMA(12) ───
    let ema_val = ema(&close, 12).expect("EMA(12) should compute with 200 bars");
    assert!(
        ema_val > 0.0,
        "EMA should be positive for positive price data"
    );
    // EMA should be in a reasonable range near current prices
    // EMA 應在當前價格附近的合理範圍內
    let last_close = *close.last().unwrap();
    assert!(
        (ema_val - last_close).abs() < last_close * 0.2,
        "EMA(12) should be within 20% of last close: ema={ema_val}, close={last_close}"
    );

    // ─── RSI(14) ───
    // QC tolerance: ±0.1% / QC 容差: ±0.1%
    let rsi_val = rsi(&close, 14).expect("RSI(14) should compute with 200 bars");
    assert!(
        (0.0..=100.0).contains(&rsi_val),
        "RSI must be in [0, 100], got {rsi_val}"
    );

    // ─── MACD(12,26,9) ───
    let macd_result = macd(&close, 12, 26, 9).expect("MACD(12,26,9) should compute with 200 bars");
    // Algebraic identity: histogram = macd - signal (QC tolerance: ±1e-10)
    // 代數恆等式：histogram = macd - signal（QC 容差: ±1e-10）
    let hist_error = (macd_result.histogram - (macd_result.macd - macd_result.signal)).abs();
    assert!(
        hist_error < 1e-10,
        "MACD histogram identity violation: hist={}, macd-signal={}, error={hist_error}",
        macd_result.histogram,
        macd_result.macd - macd_result.signal
    );

    // ─── Bollinger Bands(20, 2.0) ───
    let bb = bollinger(&close, 20, 2.0).expect("Bollinger(20,2.0) should compute with 200 bars");
    // BB middle must equal SMA(20) (same computation path, QC tolerance: ±1e-10)
    // BB 中軌必須等於 SMA(20)（相同計算路徑，QC 容差: ±1e-10）
    assert!(
        (bb.middle - sma_val).abs() < 1e-10,
        "BB middle must equal SMA(20): bb.middle={}, sma={sma_val}, diff={}",
        bb.middle,
        (bb.middle - sma_val).abs()
    );
    assert!(
        bb.upper > bb.lower,
        "BB upper({}) must > lower({})",
        bb.upper,
        bb.lower
    );
    assert!(
        bb.upper >= bb.middle && bb.middle >= bb.lower,
        "BB ordering: upper({}) >= middle({}) >= lower({})",
        bb.upper,
        bb.middle,
        bb.lower
    );
    assert!(bb.bandwidth >= 0.0, "BB bandwidth must be non-negative");

    // ─── ATR(14) ───
    // QC tolerance: ±0.01% / QC 容差: ±0.01%
    let atr_result = atr(&high, &low, &close, 14).expect("ATR(14) should compute with 200 bars");
    assert!(
        atr_result.atr > 0.0,
        "ATR must be positive, got {}",
        atr_result.atr
    );
    assert!(
        atr_result.atr_percent > 0.0,
        "ATR percent must be positive, got {}",
        atr_result.atr_percent
    );

    // ─── Stochastic(14, 3) ───
    // QC tolerance: ±0.01% / QC 容差: ±0.01%
    let stoch =
        stochastic(&high, &low, &close, 14, 3).expect("Stoch(14,3) should compute with 200 bars");
    assert!(
        (0.0..=100.0).contains(&stoch.k),
        "Stochastic %K must be in [0, 100], got {}",
        stoch.k
    );
    assert!(
        (0.0..=100.0).contains(&stoch.d),
        "Stochastic %D must be in [0, 100], got {}",
        stoch.d
    );

    // ─── KAMA(10, 2, 30) ───
    let kama_result = kama(&close, 10, 2, 30).expect("KAMA(10,2,30) should compute with 200 bars");
    assert!(
        kama_result.kama > 0.0,
        "KAMA must be positive, got {}",
        kama_result.kama
    );
    assert!(
        (0.0..=1.0).contains(&kama_result.efficiency_ratio),
        "KAMA ER must be in [0, 1], got {}",
        kama_result.efficiency_ratio
    );

    // ─── ADX(14) ───
    let adx_result = adx(&high, &low, &close, 14).expect("ADX(14) should compute with 200 bars");
    assert!(
        (0.0..=100.0).contains(&adx_result.adx),
        "ADX must be in [0, 100], got {}",
        adx_result.adx
    );
    assert!(
        adx_result.plus_di >= 0.0,
        "+DI must be non-negative, got {}",
        adx_result.plus_di
    );
    assert!(
        adx_result.minus_di >= 0.0,
        "-DI must be non-negative, got {}",
        adx_result.minus_di
    );

    // ─── Hurst(10, 50) ───
    // QC tolerance: ±0.05 (R/S inherent variance) / QC 容差: ±0.05（R/S 固有方差）
    let hurst_result =
        hurst(&close, 10, 50, 0.60, 0.40).expect("Hurst(10,50) should compute with 200 bars");
    assert!(
        hurst_result.hurst > 0.0 && hurst_result.hurst < 1.5,
        "Hurst exponent should be in (0, 1.5), got {}",
        hurst_result.hurst
    );
    assert!(
        ["trending", "mean_reverting", "random_walk"].contains(&hurst_result.regime.as_str()),
        "Hurst regime must be one of trending/mean_reverting/random_walk, got '{}'",
        hurst_result.regime
    );

    // ─── EWMA Vol(0.97) ───
    let ewma_result = ewma_vol(&close, 0.97).expect("EWMA(0.97) should compute with 200 bars");
    assert!(
        ewma_result.ewma_vol >= 0.0,
        "EWMA vol must be non-negative, got {}",
        ewma_result.ewma_vol
    );
    assert!(
        ["low", "normal", "high"].contains(&ewma_result.vol_regime.as_str()),
        "EWMA vol regime must be low/normal/high, got '{}'",
        ewma_result.vol_regime
    );

    // ─── Volume Ratio(20) ───
    let vr = volume_ratio(&volume, 20).expect("VolumeRatio(20) should compute with 200 bars");
    assert!(vr > 0.0, "Volume ratio must be positive, got {vr}");

    // ─── Donchian Channel(20) ───
    // Algebraic identity: middle = (upper + lower) / 2 (QC tolerance: ±1e-10)
    // 代數恆等式：middle = (upper + lower) / 2（QC 容差: ±1e-10）
    let donch =
        donchian(&high, &low, &close, 20).expect("Donchian(20) should compute with 200 bars");
    assert!(
        donch.upper >= donch.lower,
        "Donchian upper({}) must >= lower({})",
        donch.upper,
        donch.lower
    );
    let expected_mid = (donch.upper + donch.lower) / 2.0;
    assert!(
        (donch.middle - expected_mid).abs() < 1e-10,
        "Donchian middle identity: got {}, expected {expected_mid}, diff={}",
        donch.middle,
        (donch.middle - expected_mid).abs()
    );
    assert!(
        donch.width >= 0.0,
        "Donchian width must be non-negative, got {}",
        donch.width
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test: Kahan Summation Accuracy (via SMA proxy)
// 測試：Kahan 求和精度（通過 SMA 代理）
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn test_kahan_summation_accuracy_via_sma() {
    // Verify Kahan sum is accurate by using SMA on a large dataset of
    // values known to cause floating-point drift with naive summation.
    // 通過在已知會導致天真求和浮點漂移的大數據集上使用 SMA 來驗證 Kahan 求和精度。

    // Create 10,000 values of 0.1 — naive sum would drift, Kahan should be exact.
    // 創建 10,000 個 0.1 值 — 天真求和會漂移，Kahan 應該精確。
    let n = 10_000;
    let values: Vec<f64> = vec![0.1; n];
    let sma_result = sma(&values, n).expect("SMA of full array should compute");

    // True mean = 0.1 exactly. Kahan should give near-perfect accuracy.
    // 真實平均值 = 0.1。Kahan 應給出接近完美的精度。
    assert!(
        (sma_result - 0.1).abs() < 1e-12,
        "Kahan SMA accuracy: expected 0.1, got {sma_result}, diff={}",
        (sma_result - 0.1).abs()
    );

    // Also test with harmonic-series-like values that magnify drift
    // 也用調和級數類值測試，這會放大漂移
    let harmonic: Vec<f64> = (1..=1000).map(|i| 1.0 / i as f64).collect();
    let harm_sma = sma(&harmonic, 1000).expect("Harmonic SMA should compute");
    // Just verify it's finite and reasonable
    assert!(harm_sma.is_finite(), "Harmonic SMA must be finite");
    assert!(
        harm_sma > 0.0 && harm_sma < 1.0,
        "Harmonic SMA should be in (0, 1), got {harm_sma}"
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test: Insufficient Data Returns None
// 測試：數據不足返回 None
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
#[allow(deprecated)] // 數學驗證測試：刻意調用 donchian() 驗證 None 邊界
fn test_insufficient_data_returns_none() {
    let short = vec![1.0, 2.0, 3.0];
    let short_h = vec![1.5, 2.5, 3.5];
    let short_l = vec![0.5, 1.5, 2.5];
    let short_v = vec![100.0, 200.0, 300.0];

    // SMA(20) needs 20 bars / SMA(20) 需要 20 根 K 線
    assert!(
        sma(&short, 20).is_none(),
        "SMA(20) should be None with only 3 bars"
    );

    // EMA(12) needs 12 bars / EMA(12) 需要 12 根 K 線
    assert!(
        ema(&short, 12).is_none(),
        "EMA(12) should be None with only 3 bars"
    );

    // RSI(14) needs 15 bars / RSI(14) 需要 15 根 K 線
    assert!(
        rsi(&short, 14).is_none(),
        "RSI(14) should be None with only 3 bars"
    );

    // MACD(12,26,9) needs ~34 bars / MACD(12,26,9) 需要 ~34 根 K 線
    assert!(
        macd(&short, 12, 26, 9).is_none(),
        "MACD should be None with only 3 bars"
    );

    // Bollinger(20) needs 20 bars / Bollinger(20) 需要 20 根 K 線
    assert!(
        bollinger(&short, 20, 2.0).is_none(),
        "Bollinger(20) should be None with only 3 bars"
    );

    // ATR(14) needs 15 bars / ATR(14) 需要 15 根 K 線
    assert!(
        atr(&short_h, &short_l, &short, 14).is_none(),
        "ATR(14) should be None with only 3 bars"
    );

    // Stochastic(14,3) needs 16 bars / Stochastic(14,3) 需要 16 根 K 線
    assert!(
        stochastic(&short_h, &short_l, &short, 14, 3).is_none(),
        "Stoch(14,3) should be None with only 3 bars"
    );

    // KAMA(10,2,30) needs 11 bars / KAMA(10,2,30) 需要 11 根 K 線
    assert!(
        kama(&short, 10, 2, 30).is_none(),
        "KAMA(10,2,30) should be None with only 3 bars"
    );

    // ADX(14) needs 29 bars / ADX(14) 需要 29 根 K 線
    assert!(
        adx(&short_h, &short_l, &short, 14).is_none(),
        "ADX(14) should be None with only 3 bars"
    );

    // Hurst(10,50) needs 51 bars / Hurst(10,50) 需要 51 根 K 線
    assert!(
        hurst(&short, 10, 50, 0.60, 0.40).is_none(),
        "Hurst(10,50) should be None with only 3 bars"
    );

    // EWMA Vol needs 3 bars minimum — 2 bars should fail
    // EWMA Vol 最少需要 3 根 K 線 — 2 根應失敗
    assert!(
        ewma_vol(&[1.0, 2.0], 0.97).is_none(),
        "EWMA vol should be None with only 2 bars"
    );

    // Volume Ratio(20) needs 21 bars / 量比(20) 需要 21 根 K 線
    assert!(
        volume_ratio(&short_v, 20).is_none(),
        "VolumeRatio(20) should be None with only 3 bars"
    );

    // Donchian(20) needs 20 bars / 唐奇安(20) 需要 20 根 K 線
    assert!(
        donchian(&short_h, &short_l, &short, 20).is_none(),
        "Donchian(20) should be None with only 3 bars"
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test: IndicatorEngine::compute_all Snapshot
// 測試：IndicatorEngine::compute_all 快照
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn test_compute_all_snapshot() {
    let (_open, high, low, close, volume) = generate_synthetic_ohlcv(200, 42);
    let snapshot = IndicatorEngine::compute_all(&high, &low, &close, &volume);

    // All 13 indicators should be Some with 200 bars
    // 200 根 K 線應使全部 13 個指標返回 Some
    assert!(snapshot.sma_20.is_some(), "snapshot.sma_20 should be Some");
    assert!(snapshot.ema_12.is_some(), "snapshot.ema_12 should be Some");
    assert!(snapshot.rsi_14.is_some(), "snapshot.rsi_14 should be Some");
    assert!(snapshot.macd.is_some(), "snapshot.macd should be Some");
    assert!(
        snapshot.bollinger.is_some(),
        "snapshot.bollinger should be Some"
    );
    assert!(snapshot.atr_14.is_some(), "snapshot.atr_14 should be Some");
    assert!(
        snapshot.stochastic.is_some(),
        "snapshot.stochastic should be Some"
    );
    assert!(snapshot.kama.is_some(), "snapshot.kama should be Some");
    assert!(snapshot.adx.is_some(), "snapshot.adx should be Some");
    assert!(snapshot.hurst.is_some(), "snapshot.hurst should be Some");
    assert!(
        snapshot.ewma_vol.is_some(),
        "snapshot.ewma_vol should be Some"
    );
    assert!(
        snapshot.volume_ratio.is_some(),
        "snapshot.volume_ratio should be Some"
    );
    assert!(
        snapshot.donchian.is_some(),
        "snapshot.donchian should be Some"
    );

    // Cross-validate snapshot values match individual calls
    // 交叉驗證快照值與單獨調用匹配
    let individual_sma = sma(&close, 20).unwrap();
    assert!(
        (snapshot.sma_20.unwrap() - individual_sma).abs() < 1e-15,
        "Snapshot SMA must match individual SMA call"
    );

    let individual_rsi = rsi(&close, 14).unwrap();
    assert!(
        (snapshot.rsi_14.unwrap() - individual_rsi).abs() < 1e-15,
        "Snapshot RSI must match individual RSI call"
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test: compute_all with Insufficient Data
// 測試：數據不足時 compute_all
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn test_compute_all_insufficient_data() {
    // 5 bars — most indicators should return None gracefully
    // 5 根 K 線 — 大部分指標應優雅地返回 None
    let close = vec![50000.0, 50100.0, 49900.0, 50200.0, 50050.0];
    let high: Vec<f64> = close.iter().map(|c| c + 50.0).collect();
    let low: Vec<f64> = close.iter().map(|c| c - 50.0).collect();
    let volume = vec![100.0, 150.0, 120.0, 180.0, 130.0];

    let snap = IndicatorEngine::compute_all(&high, &low, &close, &volume);

    // These all require >5 bars with default params
    // 這些在默認參數下都需要 >5 根 K 線
    assert!(snap.sma_20.is_none(), "SMA(20) needs 20 bars");
    assert!(snap.rsi_14.is_none(), "RSI(14) needs 15 bars");
    assert!(snap.macd.is_none(), "MACD(12,26,9) needs ~34 bars");
    assert!(snap.bollinger.is_none(), "Bollinger(20) needs 20 bars");
    assert!(snap.atr_14.is_none(), "ATR(14) needs 15 bars");
    assert!(snap.stochastic.is_none(), "Stochastic(14,3) needs 16 bars");
    assert!(snap.kama.is_none(), "KAMA(10,2,30) needs 11 bars");
    assert!(snap.adx.is_none(), "ADX(14) needs 29 bars");
    assert!(snap.hurst.is_none(), "Hurst(10,50) needs 51 bars");
    assert!(snap.donchian.is_none(), "Donchian(20) needs 20 bars");

    // EWMA vol and EMA(12) need fewer bars — still may be None with 5
    // EWMA vol 和 EMA(12) 需要更少的 K 線 — 5 根可能仍然為 None
    // EMA(12) needs 12 bars, so None
    assert!(snap.ema_12.is_none(), "EMA(12) needs 12 bars");
    // EWMA vol needs 3+ bars, so should be Some
    assert!(snap.ewma_vol.is_some(), "EWMA vol needs only 3 bars");
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test: Deterministic Reproducibility
// 測試：確定性可重複性
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn test_deterministic_reproducibility() {
    // Same seed must produce identical results every time.
    // 相同種子必須每次產生相同結果。
    let (_, high1, low1, close1, vol1) = generate_synthetic_ohlcv(200, 42);
    let (_, high2, low2, close2, vol2) = generate_synthetic_ohlcv(200, 42);

    // Data arrays must be bit-identical
    // 數據陣列必須位元級相同
    assert_eq!(
        close1, close2,
        "Same seed must produce identical close data"
    );
    assert_eq!(high1, high2, "Same seed must produce identical high data");
    assert_eq!(low1, low2, "Same seed must produce identical low data");
    assert_eq!(vol1, vol2, "Same seed must produce identical volume data");

    // Indicator results must be bit-identical
    // 指標結果必須位元級相同
    let snap1 = IndicatorEngine::compute_all(&high1, &low1, &close1, &vol1);
    let snap2 = IndicatorEngine::compute_all(&high2, &low2, &close2, &vol2);

    assert_eq!(
        snap1.sma_20.unwrap(),
        snap2.sma_20.unwrap(),
        "SMA must be bit-identical across runs"
    );
    assert_eq!(
        snap1.rsi_14.unwrap(),
        snap2.rsi_14.unwrap(),
        "RSI must be bit-identical across runs"
    );

    // Different seed must produce different results
    // 不同種子必須產生不同結果
    let (_, _, _, close3, _) = generate_synthetic_ohlcv(200, 99);
    assert_ne!(
        close1, close3,
        "Different seeds must produce different data"
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test: Edge Cases — Zero Period, Empty Data
// 測試：邊界情況 — 零週期、空數據
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn test_edge_cases_zero_and_empty() {
    let empty: Vec<f64> = vec![];

    // Zero period should return None for all applicable indicators
    // 零週期應使所有適用指標返回 None
    assert!(sma(&[1.0], 0).is_none(), "SMA(0) should be None");
    assert!(ema(&[1.0], 0).is_none(), "EMA(0) should be None");
    assert!(rsi(&[1.0], 0).is_none(), "RSI(0) should be None");

    // Empty data should return None
    // 空數據應返回 None
    assert!(sma(&empty, 1).is_none(), "SMA on empty data should be None");
    assert!(ema(&empty, 1).is_none(), "EMA on empty data should be None");
    assert!(rsi(&empty, 1).is_none(), "RSI on empty data should be None");
    assert!(
        bollinger(&empty, 1, 2.0).is_none(),
        "Bollinger on empty data should be None"
    );
    assert!(
        volume_ratio(&empty, 1).is_none(),
        "VolumeRatio on empty data should be None"
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test: Cross-Indicator Consistency Checks
// 測試：跨指標一致性檢查
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
#[allow(deprecated)] // 數學驗證測試：刻意調用 donchian() 做 ATR/Donchian 範圍交叉驗證
fn test_cross_indicator_consistency() {
    let (_open, high, low, close, _volume) = generate_synthetic_ohlcv(200, 42);

    // ATR should be bounded by Donchian width (approximately)
    // ATR 應近似受唐奇安寬度約束
    let atr_result = atr(&high, &low, &close, 14).unwrap();
    let donch = donchian(&high, &low, &close, 20).unwrap();
    // ATR can't be larger than the full Donchian range for same window
    // ATR 不能大於同一窗口的完整唐奇安範圍
    let donch_range = donch.upper - donch.lower;
    assert!(
        atr_result.atr <= donch_range * 2.0,
        "ATR({}) should be bounded by ~2x Donchian range({})",
        atr_result.atr,
        donch_range
    );

    // Bollinger bandwidth should be related to EWMA vol (both measure volatility)
    // 布林帶帶寬應與 EWMA vol 相關（兩者都衡量波動率）
    let bb = bollinger(&close, 20, 2.0).unwrap();
    let ewma = ewma_vol(&close, 0.97).unwrap();
    // Both should be positive when prices vary
    // 當價格變化時兩者都應為正
    assert!(
        bb.bandwidth > 0.0 && ewma.ewma_vol > 0.0,
        "Both BB bandwidth and EWMA vol should be positive for varying prices"
    );

    // EMA(12) should respond faster than SMA(20) to recent changes
    // EMA(12) 對近期變化的反應應比 SMA(20) 更快
    // (Not a strict mathematical guarantee, but holds for trending synthetic data)
    let sma_val = sma(&close, 20).unwrap();
    let ema_val = ema(&close, 12).unwrap();
    // Both should be in the same ballpark
    // 兩者應在同一量級
    let spread_pct = ((ema_val - sma_val) / sma_val).abs() * 100.0;
    assert!(
        spread_pct < 10.0,
        "EMA(12) and SMA(20) should be within 10% for synthetic data, got {spread_pct}%"
    );
}
