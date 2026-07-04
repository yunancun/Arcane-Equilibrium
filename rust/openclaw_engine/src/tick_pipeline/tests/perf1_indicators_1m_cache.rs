//! P1-11 (2026-07-04)：bar-close gated 1m 指標重算回歸測試。
//!
//! 背景：PERF-1 (2026-06-14) 只 gate 了 5m 半邊（`cached_or_recompute_indicators_5m`），
//! 1m 側 step_1_2 過去每 tick 無條件呼 `compute_indicators` 重算整套 1m 指標。
//! 本檔驗證補到 1m 側的同構機制 `cached_or_recompute_indicators_1m`：
//!   (1) 同一根 1m bar 內多 tick → 回快取 clone，bit-identical、不觸發重算
//!       （哨兵竄改法直接證明「未重算」，非只靠 epoch 不變推論）。
//!   (2) cache-invalidation：新 1m 收盤推進 epoch → 強制重算；ewma_lambda
//!       熱重載 → 強制重算。
//!   (3) never-cache-None：暖機期重算回 None 不寫快取。
//!   (4) remove_symbol 清 1m 快取 + epoch（防同名 symbol 重入繼承過期快照）。
//!   (5) cache-on vs cache-off（= P1-11 前的每 tick 直接重算路徑）逐 tick
//!       serde byte-identical，含跨 bar 邊界 —— 「重算時機外結果 bit-一致」。
//!
//! scope fence：gate 只作用於「指標重算」；step_1_2 每 tick 仍在回傳的 owned
//! clone 上執行 hurst 滯回打標 / latest_indicators 鏡像 / FeatureSnapshot 發送，
//! clone 上的 mutation 無法污染快取（Rust 所有權保證，見 helper doc）。

use super::*;

use std::sync::Arc;

use crate::config::{ConfigStore, RiskConfig};

const SYM: &str = "BTCUSDT";
/// 1m 對齊基準（可被 60_000 整除）。
const BASE_TS: u64 = 1_715_000_000_000 - (1_715_000_000_000 % 60_000);
const ONE_MIN_MS: u64 = 60_000;

/// 餵入 `n_closed` 根遞增的 1m 已關閉 K 線到 pipeline 的 kline_manager。
///
/// 每根 bar 用 2 個同週期 tick（低點/高點有區分）+ 下一週期 tick 觸發收盤。
/// 回傳最後一根已關閉 bar 的 `open_time_ms`（= 當前 epoch 的時間部分）。
/// indicator min=30 根，故 n_closed 須 >= 31。
fn seed_1m_bars(pipeline: &mut TickPipeline, n_closed: usize) -> u64 {
    for k in 0..=n_closed {
        let period_open = BASE_TS + k as u64 * ONE_MIN_MS;
        let base_price = 60_000.0 + k as f64 * 10.0;
        // 同一 1m 週期內兩個 tick：低點 + 高點。
        pipeline
            .kline_manager
            .on_tick(SYM, base_price, period_open + 1_000, 1.0, base_price);
        pipeline.kline_manager.on_tick(
            SYM,
            base_price + 5.0,
            period_open + 2_000,
            1.0,
            base_price + 5.0,
        );
    }
    // 最後一個週期的 bar 尚在 building，未關閉。
    BASE_TS + (n_closed as u64 - 1) * ONE_MIN_MS
}

// =========================================================================
// (1a) 同一 1m bar 內，多 intra-bar tick → 1m 快照 bit-identical（epoch 不變）。
// =========================================================================
#[test]
fn p1_11_intra_bar_returns_bit_identical_snapshot() {
    let mut pipeline = TickPipeline::new(&[SYM]);
    seed_1m_bars(&mut pipeline, 35);

    // 首次呼叫 → miss → 重算 + populate cache/epoch。
    let first = pipeline
        .cached_or_recompute_indicators_1m(SYM)
        .expect("seeded 35 bars 應產出 Some 1m 快照");

    assert!(
        pipeline.perf1_indicators_1m_cache.contains_key(SYM),
        "首次重算後快取必含該 symbol"
    );
    let epoch_after_first = *pipeline
        .perf1_indicators_1m_epoch
        .get(SYM)
        .expect("epoch 必同步寫入");

    // 同 bar 內多次呼叫（模擬 intra-bar 多 tick）→ 必回 bit-identical 快照，
    // 且 epoch 不變。
    for _ in 0..5 {
        let again = pipeline
            .cached_or_recompute_indicators_1m(SYM)
            .expect("epoch 未變應回快取 Some");
        assert_eq!(
            serde_json::to_string(&again).unwrap(),
            serde_json::to_string(&first).unwrap(),
            "同一 1m bar 內快取快照必與首次重算 bit-identical"
        );
        assert_eq!(
            *pipeline.perf1_indicators_1m_epoch.get(SYM).unwrap(),
            epoch_after_first,
            "epoch 在同 bar 內不得變化"
        );
    }
}

// =========================================================================
// (1b) 驗收核心：哨兵竄改法直接證明「同一 1m bar 內多 tick 不觸發重算」。
//      把快取條目換成哨兵值後同 bar 內連續呼叫 → 全部回哨兵（若有任何一次
//      重算，回傳必是真值且快取被覆寫）；新 1m 收盤後 → 重算，哨兵被真值覆蓋。
// =========================================================================
#[test]
fn p1_11_sentinel_proves_no_recompute_within_same_1m_bar() {
    let mut pipeline = TickPipeline::new(&[SYM]);
    seed_1m_bars(&mut pipeline, 35);

    let first = pipeline
        .cached_or_recompute_indicators_1m(SYM)
        .expect("首次 Some");
    const SENTINEL: f64 = 123_456.789;
    assert_ne!(
        first.sma_20,
        Some(SENTINEL),
        "前置：真值不得撞哨兵（否則測試無效）"
    );

    // 竄改快取為哨兵快照（僅測試手段；生產路徑無人寫此 map 除 helper 本身）。
    let mut tampered = first.clone();
    tampered.sma_20 = Some(SENTINEL);
    pipeline
        .perf1_indicators_1m_cache
        .insert(SYM.to_string(), tampered);

    // 同 bar 內多 tick：全部回哨兵 = 走快取、零重算。
    for tick in 0..5 {
        let again = pipeline
            .cached_or_recompute_indicators_1m(SYM)
            .expect("同 bar 內必 Some");
        assert_eq!(
            again.sma_20,
            Some(SENTINEL),
            "tick {tick}: 同一 1m bar 內必回哨兵快照（任何重算都會覆寫回真值）"
        );
    }

    // 推進一根新 1m 收盤 → epoch 變 → 強制重算，哨兵被真值覆蓋。
    let next_open = BASE_TS + 36 * ONE_MIN_MS;
    pipeline
        .kline_manager
        .on_tick(SYM, 60_400.0, next_open + 1_000, 1.0, 60_400.0);
    pipeline.kline_manager.on_tick(
        SYM,
        60_410.0,
        next_open + ONE_MIN_MS + 1_000,
        1.0,
        60_410.0,
    );
    let after = pipeline
        .cached_or_recompute_indicators_1m(SYM)
        .expect("新收盤後仍 Some");
    assert_ne!(
        after.sma_20,
        Some(SENTINEL),
        "新 1m 收盤後必真重算（哨兵被真值覆蓋）"
    );
    assert_ne!(
        pipeline
            .perf1_indicators_1m_cache
            .get(SYM)
            .and_then(|s| s.sma_20),
        Some(SENTINEL),
        "重算後快取條目必被真值刷新"
    );
}

// =========================================================================
// (2a) cache-invalidation：推進 1m epoch（新收盤）→ 強制重算 + 刷新 epoch。
// =========================================================================
#[test]
fn p1_11_new_1m_close_advances_epoch_and_recomputes() {
    let mut pipeline = TickPipeline::new(&[SYM]);
    seed_1m_bars(&mut pipeline, 35);

    let _ = pipeline
        .cached_or_recompute_indicators_1m(SYM)
        .expect("首次 Some");
    let epoch_before = *pipeline.perf1_indicators_1m_epoch.get(SYM).unwrap();

    // 餵入下一根 1m 收盤（時間部分推進）。
    let next_open = BASE_TS + 36 * ONE_MIN_MS;
    pipeline
        .kline_manager
        .on_tick(SYM, 60_400.0, next_open + 1_000, 1.0, 60_400.0);
    pipeline.kline_manager.on_tick(
        SYM,
        60_410.0,
        next_open + ONE_MIN_MS + 1_000,
        1.0,
        60_410.0,
    );

    let _ = pipeline
        .cached_or_recompute_indicators_1m(SYM)
        .expect("新收盤後仍 Some");
    let epoch_after = *pipeline.perf1_indicators_1m_epoch.get(SYM).unwrap();

    assert_ne!(
        epoch_before.0, epoch_after.0,
        "新 1m 收盤後 epoch 的 open_time_ms 部分必推進（強制重算）"
    );
}

// =========================================================================
// (2b) cache-invalidation：改 ewma_lambda("1m")（RiskConfig 熱重載）→ 強制重算。
// =========================================================================
#[test]
fn p1_11_ewma_lambda_hot_reload_forces_recompute() {
    let mut pipeline = TickPipeline::new(&[SYM]);
    seed_1m_bars(&mut pipeline, 35);

    // 接 risk_store，1m lambda=0.90。
    let mut cfg = RiskConfig::default();
    cfg.ewma_vol.lambdas.insert("1m".to_string(), 0.90);
    let store = Arc::new(ConfigStore::new(cfg.clone()));
    pipeline.set_risk_store(Arc::clone(&store));

    let _ = pipeline
        .cached_or_recompute_indicators_1m(SYM)
        .expect("首次 Some");
    let epoch_before = *pipeline.perf1_indicators_1m_epoch.get(SYM).unwrap();
    assert!(
        (epoch_before.1 - 0.90).abs() < 1e-9,
        "epoch lambda 部分必反映 store 的 1m lambda=0.90"
    );

    // 熱重載 lambda → 0.80（不動 K 線，open_time_ms 不變）。
    let mut next = cfg.clone();
    next.ewma_vol.lambdas.insert("1m".to_string(), 0.80);
    store
        .replace(next, crate::config::PatchSource::Operator)
        .expect("lambda 熱重載 replace 必須成功");

    let _ = pipeline
        .cached_or_recompute_indicators_1m(SYM)
        .expect("熱重載後仍 Some");
    let epoch_after = *pipeline.perf1_indicators_1m_epoch.get(SYM).unwrap();

    assert_eq!(
        epoch_before.0, epoch_after.0,
        "open_time_ms 不變（未動 K 線），純驗 lambda 改變觸發重算"
    );
    assert!(
        (epoch_after.1 - 0.80).abs() < 1e-9,
        "lambda 熱重載後 epoch lambda 部分必更新為 0.80（強制重算）"
    );
}

// =========================================================================
// (3) 不變量：重算回 None（暖機期 < 30 根）→ 不寫快取（never cache None）。
// =========================================================================
#[test]
fn p1_11_none_recompute_never_cached() {
    let mut pipeline = TickPipeline::new(&[SYM]);
    // 只餵 10 根（< 30 indicator min）→ compute 回 None。
    seed_1m_bars(&mut pipeline, 10);

    let result = pipeline.cached_or_recompute_indicators_1m(SYM);
    assert!(result.is_none(), "< 30 根時 1m 指標應回 None");
    assert!(
        !pipeline.perf1_indicators_1m_cache.contains_key(SYM),
        "重算回 None 時絕不寫入快取（never cache None）"
    );
    assert!(
        !pipeline.perf1_indicators_1m_epoch.contains_key(SYM),
        "重算回 None 時 epoch 也不應寫入"
    );
}

// =========================================================================
// (5) cache-on vs cache-off 逐 tick 對比：cache-off = 直接呼 `compute_indicators`
//     （= P1-11 引入前 step_1_2 的每 tick 行為）。serde byte-identical 是最強
//     斷言（嚴格強於 1e-4 容差），涵蓋 epoch 不變（intra-bar）+ epoch 推進
//     （新 1m 收盤）兩種 regime —— 證「重算時機外結果 bit-一致」。
// =========================================================================
#[test]
fn p1_11_cache_on_vs_cache_off_bit_identical_over_tick_sequence() {
    let mut pipeline = TickPipeline::new(&[SYM]);
    seed_1m_bars(&mut pipeline, 35);

    for tick in 0..8u32 {
        let on = pipeline
            .cached_or_recompute_indicators_1m(SYM)
            .expect("epoch 穩定下 cache-on 必 Some");
        // cache-off：繞過快取直接重算（&self，不動 cache/epoch 狀態）。
        let off = pipeline
            .compute_indicators(SYM)
            .expect("cache-off 直接重算同 epoch 必 Some");
        assert_eq!(
            serde_json::to_string(&on).unwrap(),
            serde_json::to_string(&off).unwrap(),
            "tick {tick}: cache-on 輸出必與 cache-off 直接重算 serde byte-identical"
        );
    }

    // 跨 bar 邊界：推進一根新 1m 收盤 → cache-on 強制重算（新 epoch），再與
    // cache-off 並列，證 epoch 推進後仍 bit-identical（非只 intra-bar 巧合）。
    let next_open = BASE_TS + 36 * ONE_MIN_MS;
    pipeline
        .kline_manager
        .on_tick(SYM, 60_400.0, next_open + 1_000, 1.0, 60_400.0);
    pipeline.kline_manager.on_tick(
        SYM,
        60_410.0,
        next_open + ONE_MIN_MS + 1_000,
        1.0,
        60_410.0,
    );

    let on_next = pipeline
        .cached_or_recompute_indicators_1m(SYM)
        .expect("新收盤後 cache-on 必 Some");
    let off_next = pipeline
        .compute_indicators(SYM)
        .expect("新收盤後 cache-off 必 Some");
    assert_eq!(
        serde_json::to_string(&on_next).unwrap(),
        serde_json::to_string(&off_next).unwrap(),
        "跨 1m bar 邊界後 cache-on 重算輸出仍須與 cache-off serde byte-identical"
    );
}

// =========================================================================
// (4) remove_symbol 清除 1m 快取 + epoch（防同名 symbol 重入繼承過期快照）。
// =========================================================================
#[test]
fn p1_11_remove_symbol_clears_cache_and_epoch() {
    let mut pipeline = TickPipeline::new(&[SYM]);
    seed_1m_bars(&mut pipeline, 35);
    let _ = pipeline
        .cached_or_recompute_indicators_1m(SYM)
        .expect("首次 Some");
    assert!(pipeline.perf1_indicators_1m_cache.contains_key(SYM));
    assert!(pipeline.perf1_indicators_1m_epoch.contains_key(SYM));

    pipeline.remove_symbol(SYM);

    assert!(
        !pipeline.perf1_indicators_1m_cache.contains_key(SYM),
        "remove_symbol 後 1m 快取必清除"
    );
    assert!(
        !pipeline.perf1_indicators_1m_epoch.contains_key(SYM),
        "remove_symbol 後 1m epoch 必清除"
    );
}
