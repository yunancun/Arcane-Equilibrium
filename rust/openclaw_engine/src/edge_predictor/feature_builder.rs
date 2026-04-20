//! EDGE-P3-1 A5/A6 — feature vector builder from runtime context.
//! EDGE-P3-1 A5/A6 — 從 runtime context 構建 feature vector。
//!
//! MODULE_NOTE (EN): Assembles a `FeatureVectorV1` from the data already on
//!   hand during `on_tick` (PriceEvent / IndicatorSnapshot / PaperState /
//!   OrderIntent). `confluence_score` / `persistence_elapsed_ms` are read from
//!   the intent (A6 plumbs them from MA/BBR/BBB); Grid/FundingArb leave them
//!   `None` → builder falls back to 0.0 (benign under `use_edge_predictor=false`
//!   and trained-against-0 for non-confluence strategies once Stage 2 lands).
//!   All floats are clamp-to-range before handoff so invariant #12
//!   (`all_in_range`) cannot trip on drift from upstream indicators.
//! MODULE_NOTE (中): 從 on_tick 已有資料組裝 `FeatureVectorV1`。confluence 與
//!   persistence 由 intent 攜帶（A6 已接線 MA/BBR/BBB）；Grid/FundingArb 未接線
//!   時為 None → builder 填 0.0，Stage 0 由 use_edge_predictor=false 守門，
//!   Stage 2 模型對這兩策略以 0 訓練。所有 f32 先 clamp 再交棒。
//!
//! Spec: docs/references/2026-04-15--edge_predictor_spec.md v1.4 §3.2

use openclaw_core::indicators::IndicatorSnapshot;
use openclaw_types::PriceEvent;

use super::features::FeatureVectorV1;
use crate::intent_processor::OrderIntent;
use crate::paper_state::PaperState;

/// Build `FeatureVectorV1` from runtime context. Always in range (clamped).
/// Strategy-side features (confluence, persistence) are zeroed until A6+
/// plumbs them; predictor gate stays off (`use_edge_predictor=false` default)
/// so the zero defaults never reach inference in Stage 0.
/// 組裝 feature 向量；strategy 端欄位 A6+ 才接線，Stage 0 由 config 守門。
pub fn build_feature_vector(
    intent: &OrderIntent,
    event: &PriceEvent,
    indicators: Option<&IndicatorSnapshot>,
    atr_value: f64,
    paper_state: &PaperState,
) -> FeatureVectorV1 {
    let price = event.last_price;

    // ── Regime ──
    let adx_1h = indicators
        .and_then(|i| i.adx.as_ref())
        .map(|a| clamp_f32(a.adx as f32, 0.0, 100.0))
        .unwrap_or(0.0);
    // bandwidth is already `(upper - lower) / mean` (fraction); × 100 → %.
    let bb_width_pct = indicators
        .and_then(|i| i.bollinger.as_ref())
        .map(|b| clamp_f32((b.bandwidth * 100.0) as f32, 0.0, 50.0))
        .unwrap_or(0.0);
    let atr_pct = if price > 0.0 && atr_value > 0.0 {
        clamp_f32(((atr_value / price) * 100.0) as f32, 0.0, 20.0)
    } else {
        0.0
    };
    let funding_rate = clamp_f32(event.funding_rate.unwrap_or(0.0) as f32, -0.01, 0.01);
    // ewma_vol is decimal stddev → %; keep conservative clamp to the declared
    // [0, 20]% range even though EWMA can spike higher on crises.
    // ewma_vol 為小數 stddev → %；保守 clamp 至聲明範圍。
    let realized_vol_1h = indicators
        .and_then(|i| i.ewma_vol.as_ref())
        .map(|v| clamp_f32((v.ewma_vol * 100.0) as f32, 0.0, 20.0))
        .unwrap_or(0.0);

    // ── Basis / Microstructure ──
    let basis_bps = event
        .index_price
        .filter(|&ip| ip > 0.0 && price > 0.0)
        .map(|ip| clamp_f32((((ip - price) / price) * 10_000.0) as f32, -500.0, 500.0))
        .unwrap_or(0.0);
    // bids5/asks5 only populated on Orderbook events; zero otherwise (benign
    // — Stage 2+ will emit features at decision-time after caching the book).
    // bids5/asks5 僅 Orderbook 事件填充；其它 tick 為 0，Stage 2+ 會從 cache 讀取。
    let orderbook_imbalance_top5 = match (event.bids5.as_ref(), event.asks5.as_ref()) {
        (Some(bids), Some(asks)) => {
            let bid_vol: f64 = bids.iter().map(|&(_, q)| q).sum();
            let ask_vol: f64 = asks.iter().map(|&(_, q)| q).sum();
            let denom = bid_vol + ask_vol;
            if denom > 0.0 {
                clamp_f32(((bid_vol - ask_vol) / denom) as f32, -1.0, 1.0)
            } else {
                0.0
            }
        }
        _ => 0.0,
    };
    let spread_bps = if event.bid_price > 0.0 && event.ask_price > 0.0 {
        let mid = (event.ask_price + event.bid_price) * 0.5;
        if mid > 0.0 {
            clamp_f32(
                (((event.ask_price - event.bid_price) / mid) * 10_000.0) as f32,
                0.0,
                1000.0,
            )
        } else {
            0.0
        }
    } else {
        0.0
    };

    // ── Strategy ── (A6: plumbed via OrderIntent from MA/BBR/BBB; Grid + FundingArb = None → 0.0).
    // A6：MA/BBR/BBB 由 intent 攜帶；Grid/FundingArb 為 None → fill 0.0。
    let confluence_score = clamp_f32(intent.confluence_score.unwrap_or(0.0), 0.0, 65.0);
    let persistence_elapsed_ms = clamp_f32(
        intent.persistence_elapsed_ms.unwrap_or(0) as f32,
        0.0,
        3_600_000.0,
    );
    let side: i8 = if intent.is_long { 1 } else { -1 };

    // ── Position ──
    let balance = paper_state.balance();
    let notional_pct_of_bal = if balance > 0.0 && price > 0.0 {
        clamp_f32(
            (((intent.qty * price) / balance) * 100.0) as f32,
            0.0,
            100.0,
        )
    } else {
        0.0
    };
    let positions = paper_state.positions();
    let concurrent_positions = (positions.len().min(100)) as u8;
    let same_direction_cnt = positions
        .iter()
        .filter(|p| p.is_long == intent.is_long)
        .count()
        .min(100) as u8;

    // ── Time (ts_ms → UTC wall-clock derivatives) ──
    // ts_ms is unix-ms; % 86_400_000 gives ms-of-day without timezone math.
    // ts_ms 為 unix 毫秒；取日內殘值得到 UTC 小時/分鐘，無時區依賴。
    let ms_of_day = (event.ts_ms % 86_400_000) as f64;
    let hour = (ms_of_day / 3_600_000.0) as f32; // 0.0 .. 24.0
    let angle = 2.0 * std::f32::consts::PI * hour / 24.0;
    let tod_sin = clamp_f32(angle.sin(), -1.0, 1.0);
    let tod_cos = clamp_f32(angle.cos(), -1.0, 1.0);
    // Bybit funding settles at 00:00 / 08:00 / 16:00 UTC. Flag the last 15min.
    // Bybit 結算於 UTC 00/08/16；最後 15 分鐘打旗。
    let minute_of_day = (ms_of_day / 60_000.0) as u64;
    let minute_in_8h_window = minute_of_day % (8 * 60);
    let is_funding_settlement_window = if (8 * 60 - 15..8 * 60).contains(&minute_in_8h_window) {
        1
    } else {
        0
    };

    FeatureVectorV1 {
        adx_1h,
        bb_width_pct,
        atr_pct,
        funding_rate,
        realized_vol_1h,
        basis_bps,
        orderbook_imbalance_top5,
        spread_bps,
        confluence_score,
        persistence_elapsed_ms,
        side,
        notional_pct_of_bal,
        concurrent_positions,
        same_direction_cnt,
        tod_sin,
        tod_cos,
        is_funding_settlement_window,
    }
}

#[inline]
fn clamp_f32(v: f32, lo: f32, hi: f32) -> f32 {
    if v.is_finite() {
        v.clamp(lo, hi)
    } else {
        0.0
    }
}

// ============================================================
// Tests
// ============================================================
#[cfg(test)]
mod tests {
    use super::*;
    use openclaw_core::indicators::{AdxResult, AtrResult, BollingerResult, EwmaVolResult};

    fn make_intent(is_long: bool, qty: f64) -> OrderIntent {
        OrderIntent {
            symbol: "BTCUSDT".to_string(),
            is_long,
            qty,
            confidence: 0.6,
            strategy: "ma_crossover".into(),
            order_type: "market".into(),
            limit_price: None,
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: None,
            maker_timeout_ms: None,
        }
    }

    fn make_intent_with_features(
        is_long: bool,
        qty: f64,
        confluence: Option<f32>,
        persistence: Option<u64>,
    ) -> OrderIntent {
        OrderIntent {
            symbol: "BTCUSDT".to_string(),
            is_long,
            qty,
            confidence: 0.6,
            strategy: "ma_crossover".into(),
            order_type: "market".into(),
            limit_price: None,
            confluence_score: confluence,
            persistence_elapsed_ms: persistence,
            time_in_force: None,
            maker_timeout_ms: None,
        }
    }

    fn make_event(ts_ms: u64, last: f64) -> PriceEvent {
        let mut e = PriceEvent::new("BTCUSDT".into(), last, ts_ms);
        e.bid_price = last - 0.5;
        e.ask_price = last + 0.5;
        e.funding_rate = Some(0.0004);
        e.index_price = Some(last + 1.5);
        e
    }

    fn full_indicators() -> IndicatorSnapshot {
        let mut s = IndicatorSnapshot::default();
        s.adx = Some(AdxResult {
            adx: 30.0,
            plus_di: 25.0,
            minus_di: 18.0,
        });
        s.bollinger = Some(BollingerResult {
            upper: 101.0,
            middle: 100.0,
            lower: 99.0,
            bandwidth: 0.02,
            percent_b: 0.5,
        });
        s.atr_14 = Some(AtrResult {
            atr: 1.2,
            atr_percent: 1.2,
        });
        s.ewma_vol = Some(EwmaVolResult {
            ewma_vol: 0.015,
            vol_regime: "normal".into(),
        });
        s
    }

    fn paper_state_with_balance(balance: f64) -> PaperState {
        PaperState::new(balance)
    }

    #[test]
    fn test_build_all_fields_in_range_with_full_context() {
        let intent = make_intent(true, 0.001);
        let event = make_event(1_700_000_000_000, 30_000.0);
        let ind = full_indicators();
        let paper = paper_state_with_balance(10_000.0);
        let f = build_feature_vector(&intent, &event, Some(&ind), 50.0, &paper);
        assert!(f.all_in_range(), "feature vector out of range: {:?}", f);
    }

    #[test]
    fn test_build_without_indicators_still_in_range() {
        // Cold-start: no indicators yet. All indicator-derived fields = 0.
        // 冷啟動：尚無指標，所有指標派生欄位 = 0。
        let intent = make_intent(false, 0.0005);
        let event = make_event(1_700_000_000_000, 30_000.0);
        let paper = paper_state_with_balance(10_000.0);
        let f = build_feature_vector(&intent, &event, None, 0.0, &paper);
        assert!(f.all_in_range());
        assert_eq!(f.adx_1h, 0.0);
        assert_eq!(f.bb_width_pct, 0.0);
        assert_eq!(f.atr_pct, 0.0);
        assert_eq!(f.realized_vol_1h, 0.0);
        assert_eq!(f.side, -1);
    }

    #[test]
    fn test_extreme_indicator_values_get_clamped() {
        // Pathological upstream values — gate must still see in-range features.
        // 上游極端值 — gate 必須仍收到 in-range features。
        let mut ind = IndicatorSnapshot::default();
        ind.adx = Some(AdxResult {
            adx: 500.0,
            plus_di: 0.0,
            minus_di: 0.0,
        }); // > 100
        ind.bollinger = Some(BollingerResult {
            upper: 0.0,
            middle: 1.0,
            lower: 0.0,
            bandwidth: 2.5,
            percent_b: 0.5,
        }); // 250% width
        let intent = make_intent(true, 0.001);
        let mut event = make_event(1_700_000_000_000, 30_000.0);
        event.funding_rate = Some(0.5); // out of [-0.01, 0.01]
        event.index_price = Some(1_000_000.0); // absurd basis
        let paper = paper_state_with_balance(10_000.0);
        let f = build_feature_vector(&intent, &event, Some(&ind), 1e9, &paper);
        assert!(f.all_in_range(), "clamping failed: {:?}", f);
        assert_eq!(f.adx_1h, 100.0);
        assert_eq!(f.bb_width_pct, 50.0);
        assert_eq!(f.funding_rate, 0.01);
        assert_eq!(f.basis_bps, 500.0);
    }

    #[test]
    fn test_orderbook_imbalance_from_bids5_asks5() {
        let intent = make_intent(true, 0.001);
        let mut event = make_event(1_700_000_000_000, 30_000.0);
        event.bids5 = Some(vec![(29_999.5, 1.0), (29_999.0, 0.5)]); // vol = 1.5
        event.asks5 = Some(vec![(30_000.5, 0.5), (30_001.0, 0.5)]); // vol = 1.0
        let paper = paper_state_with_balance(10_000.0);
        let f = build_feature_vector(&intent, &event, None, 0.0, &paper);
        // (1.5 - 1.0) / 2.5 = 0.2
        assert!((f.orderbook_imbalance_top5 - 0.2).abs() < 1e-6);
    }

    #[test]
    fn test_spread_bps_from_bid_ask() {
        let intent = make_intent(true, 0.001);
        let mut event = make_event(1_700_000_000_000, 30_000.0);
        event.bid_price = 29_999.0;
        event.ask_price = 30_001.0;
        // mid = 30_000, spread = 2, bps = 2/30000*1e4 = ~0.667
        let paper = paper_state_with_balance(10_000.0);
        let f = build_feature_vector(&intent, &event, None, 0.0, &paper);
        assert!((f.spread_bps - 0.666_7).abs() < 0.01);
    }

    #[test]
    fn test_notional_pct_zero_balance_safe() {
        // Zero balance must not NaN / Inf the feature; cold-start edge case.
        // 餘額 0 不得產生 NaN/Inf；冷啟動邊界。
        let intent = make_intent(true, 0.001);
        let event = make_event(1_700_000_000_000, 30_000.0);
        let paper = paper_state_with_balance(0.0);
        let f = build_feature_vector(&intent, &event, None, 0.0, &paper);
        assert!(f.all_in_range());
        assert_eq!(f.notional_pct_of_bal, 0.0);
    }

    #[test]
    fn test_side_derives_from_intent() {
        let paper = paper_state_with_balance(1000.0);
        let event = make_event(1_700_000_000_000, 100.0);
        let long = build_feature_vector(&make_intent(true, 1.0), &event, None, 0.0, &paper);
        let short = build_feature_vector(&make_intent(false, 1.0), &event, None, 0.0, &paper);
        assert_eq!(long.side, 1);
        assert_eq!(short.side, -1);
    }

    #[test]
    fn test_tod_cyclic_encoding_midnight_and_noon() {
        // Midnight UTC → sin=0, cos=1; noon UTC → sin=0, cos=-1.
        // 午夜 → (0, 1)；正午 → (0, -1)。
        let paper = paper_state_with_balance(1000.0);
        let intent = make_intent(true, 1.0);
        // 2026-04-15 00:00:00 UTC ms offset cleanly; use 0 ms-of-day surrogate.
        let midnight = make_event(0, 100.0);
        let noon = make_event(12 * 3_600_000, 100.0);
        let f0 = build_feature_vector(&intent, &midnight, None, 0.0, &paper);
        let f12 = build_feature_vector(&intent, &noon, None, 0.0, &paper);
        assert!(f0.tod_sin.abs() < 1e-6);
        assert!((f0.tod_cos - 1.0).abs() < 1e-6);
        assert!(f12.tod_sin.abs() < 1e-4);
        assert!((f12.tod_cos + 1.0).abs() < 1e-4);
    }

    #[test]
    fn test_funding_settlement_window_flags_last_15m() {
        // Bybit settles at 00:00 / 08:00 / 16:00 UTC. Test a point 10 min
        // before 08:00 → should flag (in [7h45, 8h00) window).
        // Bybit 結算於 UTC 00/08/16；測試 07:50 → 應打旗。
        let paper = paper_state_with_balance(1000.0);
        let intent = make_intent(true, 1.0);
        let ts_0750 = (7 * 3600 + 50 * 60) * 1000; // 7:50:00 UTC in ms
        let ev = make_event(ts_0750, 100.0);
        let f = build_feature_vector(&intent, &ev, None, 0.0, &paper);
        assert_eq!(f.is_funding_settlement_window, 1);

        // And 07:30 (25 min before) → should NOT flag.
        // 07:30 尚未進入窗口。
        let ts_0730 = (7 * 3600 + 30 * 60) * 1000;
        let ev2 = make_event(ts_0730, 100.0);
        let f2 = build_feature_vector(&intent, &ev2, None, 0.0, &paper);
        assert_eq!(f2.is_funding_settlement_window, 0);
    }

    #[test]
    fn test_same_direction_cnt_reflects_paper_state() {
        let mut paper = paper_state_with_balance(10_000.0);
        // Two longs already open; third long intent should see same_direction=2.
        // 已有兩倉同方向；新 long 意圖應看到 same_direction=2。
        paper.import_positions(vec![
            ("ETHUSDT".into(), true, 1.0, 2_000.0, 0),
            ("SOLUSDT".into(), true, 10.0, 100.0, 0),
        ]);
        let intent = make_intent(true, 0.01);
        let event = make_event(1_700_000_000_000, 30_000.0);
        let f = build_feature_vector(&intent, &event, None, 0.0, &paper);
        assert_eq!(f.concurrent_positions, 2);
        assert_eq!(f.same_direction_cnt, 2);
        // Opposite-direction intent → same_direction_cnt stays 0 from its perspective.
        let short = make_intent(false, 0.01);
        let fs = build_feature_vector(&short, &event, None, 0.0, &paper);
        assert_eq!(fs.same_direction_cnt, 0);
    }

    #[test]
    fn test_atr_pct_uses_passed_atr_value_not_indicator_field() {
        // atr_value arg wins; allows callers to pick atr_5 / atr_14 / conservative.
        // atr_value 參數優先；caller 可挑 atr_5 / atr_14 / conservative。
        let mut ind = IndicatorSnapshot::default();
        ind.atr_14 = Some(AtrResult {
            atr: 999.0,
            atr_percent: 9.99,
        });
        let intent = make_intent(true, 0.001);
        let event = make_event(1_700_000_000_000, 100.0);
        let paper = paper_state_with_balance(10_000.0);
        // atr_value=5.0 → atr_pct = 5/100*100 = 5.0; IndicatorSnapshot.atr_14 ignored.
        let f = build_feature_vector(&intent, &event, Some(&ind), 5.0, &paper);
        assert!((f.atr_pct - 5.0).abs() < 1e-6);
    }

    // ── A6: Strategy-side plumbing tests ──

    #[test]
    fn test_confluence_none_means_zero() {
        // Grid / FundingArb pass None → feature is 0.0 not some uninitialized junk.
        // Grid/FundingArb 傳 None → feature = 0.0，非未初始化雜值。
        let intent = make_intent_with_features(true, 0.001, None, None);
        let event = make_event(1_700_000_000_000, 30_000.0);
        let paper = paper_state_with_balance(10_000.0);
        let f = build_feature_vector(&intent, &event, None, 0.0, &paper);
        assert_eq!(f.confluence_score, 0.0);
        assert_eq!(f.persistence_elapsed_ms, 0.0);
    }

    #[test]
    fn test_confluence_some_propagates_through() {
        // MA/BBR/BBB pass Some — feature reflects the strategy's own compute_score.
        // MA/BBR/BBB 傳 Some — feature 對應策略自己算出的 compute_score。
        let intent = make_intent_with_features(true, 0.001, Some(48.0), Some(180_000));
        let event = make_event(1_700_000_000_000, 30_000.0);
        let paper = paper_state_with_balance(10_000.0);
        let f = build_feature_vector(&intent, &event, None, 0.0, &paper);
        assert!((f.confluence_score - 48.0).abs() < 1e-6);
        assert!((f.persistence_elapsed_ms - 180_000.0).abs() < 1e-6);
        assert!(f.all_in_range());
    }

    #[test]
    fn test_confluence_clamped_above_65() {
        // If strategy ever emits a score above 65 (shouldn't happen but be
        // defensive), builder clamps so invariant #12 does not fail closed.
        // 策略若錯發 > 65，builder clamp 至 65 避免 invariant #12 fail-closed。
        let intent = make_intent_with_features(true, 0.001, Some(80.0), Some(10_000_000));
        let event = make_event(1_700_000_000_000, 30_000.0);
        let paper = paper_state_with_balance(10_000.0);
        let f = build_feature_vector(&intent, &event, None, 0.0, &paper);
        assert_eq!(f.confluence_score, 65.0);
        assert_eq!(f.persistence_elapsed_ms, 3_600_000.0);
        assert!(f.all_in_range());
    }

    #[test]
    fn test_persistence_zero_is_valid() {
        // Freshly-onset signal (elapsed=0 right at check() transition) must pass
        // range check: [0, 3_600_000] is inclusive at the low end.
        // 剛剛轉換的信號（elapsed=0）須通過範圍檢查。
        let intent = make_intent_with_features(true, 0.001, Some(0.0), Some(0));
        let event = make_event(1_700_000_000_000, 30_000.0);
        let paper = paper_state_with_balance(10_000.0);
        let f = build_feature_vector(&intent, &event, None, 0.0, &paper);
        assert_eq!(f.confluence_score, 0.0);
        assert_eq!(f.persistence_elapsed_ms, 0.0);
        assert!(f.all_in_range());
    }
}
