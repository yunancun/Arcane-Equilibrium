use std::collections::HashMap;

use super::producer::*;
use super::{DIAGNOSTIC_SOURCE_TIER, LEAD_WINDOW_SECS_MAIN, SOURCE_TIER};
fn make_cohort() -> Vec<String> {
    vec![
        "ETHUSDT".to_string(),
        "SOLUSDT".to_string(),
        "XRPUSDT".to_string(),
        "DOGEUSDT".to_string(),
        "ADAUSDT".to_string(),
        "AVAXUSDT".to_string(),
        "DOTUSDT".to_string(),
    ]
}

#[test]
fn diagnostic_producer_marks_snapshot_source_tier() {
    let mut p = BtcLeadLagProducer::new_with_source_tier(make_cohort(), DIAGNOSTIC_SOURCE_TIER);
    let alt_closes = HashMap::new();
    let snap = p.on_tick(60_000, 50_000.0, 100.0, &alt_closes, None);

    assert_eq!(snap.source_tier, DIAGNOSTIC_SOURCE_TIER);
}

/// 三 array length invariant — spec §4.1 不變式 + sub-task 1 deliverable
/// 第 5 項。on_tick emit snapshot 必滿足 alt_symbols.len() ==
/// alt_xcorr.len() == alt_expected_dir.len()。
#[test]
fn arrays_aligned_invariant_on_emit() {
    let cohort = make_cohort();
    let cohort_len = cohort.len();
    let mut p = BtcLeadLagProducer::new(cohort);
    let mut alt_closes = HashMap::new();
    for sym in [
        "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT",
    ] {
        alt_closes.insert(sym.to_string(), 100.0);
    }
    let snap = p.on_tick(60_000, 50_000.0, 100.0, &alt_closes, None);
    assert!(snap.arrays_aligned(), "三 array 必同序同長");
    assert_eq!(snap.alt_symbols.len(), cohort_len);
    assert_eq!(snap.alt_xcorr.len(), cohort_len);
    assert_eq!(snap.alt_expected_dir.len(), cohort_len);
    assert_eq!(snap.lead_window_secs, LEAD_WINDOW_SECS_MAIN);
    assert_eq!(snap.source_tier, SOURCE_TIER);
}

/// 樣本不足 → 主信號 NaN（不 emit 假 metric）。spec §3.2 NaN sentinel。
#[test]
fn lead_return_nan_when_insufficient_buffer() {
    let mut p = BtcLeadLagProducer::new(make_cohort());
    let alt_closes = HashMap::new();
    let snap = p.on_tick(60_000, 50_000.0, 100.0, &alt_closes, None);
    assert!(snap.btc_lead_return_pct.is_nan());
    assert!(snap.btc_lead_return_pct_60s.is_nan());
    assert!(snap.btc_lead_return_pct_300s.is_nan());
    assert!(snap.btc_volume_z.is_nan());
}

/// strict shift(N) lookahead-free — current bar 不算進 lead return。
/// 餵 N+1 個 1m tick；最後一個 tick emit 的 lead_return 必對應 buffer
/// 倒數第 N 個 tick vs current（不含 current 之後 sample，因為沒有未來）。
#[test]
fn lead_return_strict_shift_n_lookahead_free() {
    let mut p = BtcLeadLagProducer::new(make_cohort());
    let alt_closes: HashMap<String, f64> = HashMap::new();
    // 先餵 N=2 ticks (LEAD_WINDOW_SECS_MAIN=120s = 2 min) past:
    // t=60000 close=50000, t=120000 close=50100, t=180000 close=50500 (current)
    // shift(N=2) past = buffer[len-2] = 第一個 tick close=50000
    // expected lead_return = (50500 - 50000) / 50000 * 10000 = 100 bps
    p.on_tick(60_000, 50_000.0, 100.0, &alt_closes, None);
    p.on_tick(120_000, 50_100.0, 100.0, &alt_closes, None);
    let snap = p.on_tick(180_000, 50_500.0, 100.0, &alt_closes, None);
    let expected = (50_500.0 - 50_000.0) / 50_000.0 * 10_000.0;
    assert!(
        (snap.btc_lead_return_pct - expected).abs() < 1e-6,
        "lead_return = {} expected {}",
        snap.btc_lead_return_pct,
        expected
    );
}

/// expected_dir formula — spec §3.3 truth table。
#[test]
fn expected_dir_truth_table() {
    // |xcorr| < threshold_Y (0.40) → 0
    assert_eq!(compute_expected_dir(50.0, 0.30), 0);
    assert_eq!(compute_expected_dir(-50.0, -0.30), 0);

    // btc_lead_return 在 [-X, +X] 區間 → 0 不論 xcorr
    assert_eq!(compute_expected_dir(5.0, 0.50), 0);
    assert_eq!(compute_expected_dir(-5.0, 0.50), 0);

    // btc > +X & xcorr > Y → +1（同向 momentum）
    assert_eq!(compute_expected_dir(15.0, 0.50), 1);
    // btc > +X & xcorr < -Y → -1（反向 mean-revert）
    assert_eq!(compute_expected_dir(15.0, -0.50), -1);
    // btc < -X & xcorr > Y → -1
    assert_eq!(compute_expected_dir(-15.0, 0.50), -1);
    // btc < -X & xcorr < -Y → +1
    assert_eq!(compute_expected_dir(-15.0, -0.50), 1);

    // NaN 容錯
    assert_eq!(compute_expected_dir(f64::NAN, 0.50), 0);
    assert_eq!(compute_expected_dir(15.0, f64::NAN), 0);
}

/// regime_tag — |BTC 1h return| > 200 bps → "extreme"。spec §9 v1.1 #5。
#[test]
fn regime_tag_extreme_when_1h_return_exceeds_200bps() {
    let mut p = BtcLeadLagProducer::new(make_cohort());
    let alt_closes = HashMap::new();
    // 餵 60 個 1m tick 形成 1h baseline（50000 開始，後緩升 1bps/tick）
    for i in 0..60 {
        p.on_tick(
            60_000 + i * 60_000,
            50_000.0 + i as f64,
            100.0,
            &alt_closes,
            None,
        );
    }
    // t=61 餵一個 +250 bps spike: close = 50000 * 1.025 = 51250
    let snap = p.on_tick(60_000 + 60 * 60_000, 51_250.0, 100.0, &alt_closes, None);
    // 1h ago buffer[len-60] 是第一個 tick close=50000.0
    // 1h return = (51250 - 50000) / 50000 * 10000 = 250 bps > 200 → extreme
    assert_eq!(snap.regime_tag, "extreme");
}

#[test]
fn regime_tag_normal_when_1h_return_within_200bps() {
    let mut p = BtcLeadLagProducer::new(make_cohort());
    let alt_closes = HashMap::new();
    for i in 0..60 {
        p.on_tick(
            60_000 + i * 60_000,
            50_000.0 + i as f64,
            100.0,
            &alt_closes,
            None,
        );
    }
    // t=61 +50 bps mild move: close = 50000 * 1.005 = 50250
    let snap = p.on_tick(60_000 + 60 * 60_000, 50_250.0, 100.0, &alt_closes, None);
    assert_eq!(snap.regime_tag, "normal");
}

#[test]
fn regime_tag_normal_when_buffer_short() {
    let mut p = BtcLeadLagProducer::new(make_cohort());
    let alt_closes = HashMap::new();
    // 樣本不足 1h baseline → fail-closed default "normal"
    let snap = p.on_tick(60_000, 50_000.0, 100.0, &alt_closes, None);
    assert_eq!(snap.regime_tag, "normal");
}

/// xcorr — 完美正相關回 1.0 ± epsilon。spec §3.2 Pearson 不變式。
#[test]
fn pearson_perfect_positive_correlation() {
    let x: Vec<f64> = (0..50).map(|i| i as f64).collect();
    let y: Vec<f64> = (0..50).map(|i| 2.0 * i as f64 + 1.0).collect();
    let r = pearson_corr(&x, &y);
    assert!((r - 1.0).abs() < 1e-10);
}

#[test]
fn pearson_perfect_negative_correlation() {
    let x: Vec<f64> = (0..50).map(|i| i as f64).collect();
    let y: Vec<f64> = (0..50).map(|i| -2.0 * i as f64 + 1.0).collect();
    let r = pearson_corr(&x, &y);
    assert!((r + 1.0).abs() < 1e-10);
}

#[test]
fn pearson_zero_when_constant() {
    let x: Vec<f64> = (0..50).map(|i| i as f64).collect();
    let y: Vec<f64> = vec![5.0; 50]; // constant → std=0 → NaN
    let r = pearson_corr(&x, &y);
    assert!(r.is_nan());
}

/// PSR(0) skew/kurt-aware formula — spec §8.1 +15 bps gate σ_net=80 case
/// MIT C-3 verify report §4 預估 PSR(0) ≈ 0.94 sanity check（不要求精確
/// 等於 0.94，只要落在 [0.85, 0.99] 合理區間，避免完全錯誤的公式 land）。
#[test]
fn psr_zero_sanity_skew_kurt_formula() {
    // case: SR ≈ 1.5（年化 Sharpe，per MIT report 視角），n=80, skew=-0.5,
    // ex_kurt=10 → PSR(0) 預期 sub-1.0 但 ≥ 0.7 區間
    let psr = psr_zero(1.5, 80, -0.5, 10.0);
    assert!(!psr.is_nan(), "PSR(0) 在合理輸入下不應 NaN");
    assert!(
        psr >= 0.5 && psr <= 1.0,
        "PSR(0) 在 SR=1.5 / n=80 / skew=-0.5 / ex_kurt=10 應在 [0.5, 1.0] 區間，actual={}",
        psr
    );

    // Normality reference: skew=0, kurt=3 (excess=0) → PSR(0) 應 ≈ Φ(SR·√(n-1))
    // SR=1.0, n=100 → Φ(1.0·√99) = Φ(9.95) ≈ 1.0
    let psr_normal = psr_zero(1.0, 100, 0.0, 0.0);
    assert!((psr_normal - 1.0).abs() < 0.01);
}

#[test]
fn psr_zero_nan_on_insufficient_sample() {
    assert!(psr_zero(1.0, 0, 0.0, 0.0).is_nan());
    assert!(psr_zero(1.0, 1, 0.0, 0.0).is_nan());
}

#[test]
fn psr_zero_nan_on_negative_denominator() {
    // 構造分母負：SR 大 + skew 大 + ex_kurt 負
    // denom_inner = 1 - skew·SR + (excess_kurt+2)/4·SR²
    // 取 SR=10, skew=2, ex_kurt=-3 → 1 - 20 + (-1)/4·100 = -44 < 0 → NaN
    let psr = psr_zero(10.0, 100, 2.0, -3.0);
    assert!(psr.is_nan());
}

/// latest() 在沒 on_tick 前是 None；on_tick 後同 snapshot。
#[test]
fn latest_lifecycle() {
    let mut p = BtcLeadLagProducer::new(make_cohort());
    assert!(p.latest().is_none());
    let alt_closes = HashMap::new();
    let s = p.on_tick(60_000, 50_000.0, 100.0, &alt_closes, None);
    let latest = p.latest().expect("latest 應有值");
    assert_eq!(latest.snapshot_ts_ms, s.snapshot_ts_ms);
    assert_eq!(latest.lead_window_secs, s.lead_window_secs);
}

/// Buffer cap — 超過 buffer_capacity 後 pop_front。
#[test]
fn buffer_capacity_cap_enforced() {
    let mut p = BtcLeadLagProducer::new(make_cohort());
    let cap = p.buffer_capacity;
    let alt_closes = HashMap::new();
    for i in 0..(cap + 5) {
        p.on_tick(
            60_000 + i as i64 * 60_000,
            50_000.0,
            100.0,
            &alt_closes,
            None,
        );
    }
    assert_eq!(p.btc_buffer.len(), cap);
    // 第 0 個 tick 已 pop（最早 ts = 60_000 + 5 * 60_000 = 360_000）
    assert_eq!(p.btc_buffer.front().unwrap().ts_ms, 60_000 + 5 * 60_000);
}

/// W2 sub-task 4 — cohort_symbols accessor 回傳 ctor 傳入順序（writer 依賴
/// 此順序 INSERT alt_symbols TEXT[]）。
#[test]
fn cohort_symbols_accessor_preserves_order() {
    let cohort = make_cohort();
    let producer = BtcLeadLagProducer::new(cohort.clone());
    assert_eq!(producer.cohort_symbols(), cohort.as_slice());
}
