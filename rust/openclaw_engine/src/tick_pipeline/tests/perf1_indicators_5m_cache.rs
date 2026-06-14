//! PERF-1 (2026-06-14)：bar-close gated 5m 指標重算回歸測試。
//!
//! 覆蓋 fix_spec 強制的兩組不變量：
//!   (1) 同一根 5m bar 內，多個 intra-bar tick（不同 ctx.price）回傳的 5m 快照
//!       bit-identical（重算未被觸發），但 bb_breakout 5m Donchian breach 仍每
//!       tick 對 live ctx.price 評估 —— gate 只省指標重算，不 gate 策略分派。
//!   (2) cache-invalidation：推進 5m epoch（新收盤）強制重算；改 ewma_lambda
//!       （熱重載）強制重算。
//!
//! scope fence 驗證：PERF-1 只 gate `cached_or_recompute_indicators_5m`（指標
//! 重算），bb_breakout::on_tick 讀快取衍生 Donchian 層級後仍每 tick 比 live
//! ctx.price，故 intra-bar breach 不會被漏掉（backtest/live divergence 風險閉合）。

use super::*;

use std::sync::Arc;

use openclaw_core::alpha_surface::AlphaSurface;
use openclaw_core::indicators::IndicatorEngine;

use crate::config::{ConfigStore, RiskConfig};
use crate::strategies::bb_breakout::{BbBreakout, BbBreakoutParams};
use crate::strategies::{Strategy, StrategyAction};

const SYM: &str = "BTCUSDT";
/// 5m 對齊基準（可被 300_000 整除）。
const BASE_TS: u64 = 1_715_000_000_000 - (1_715_000_000_000 % 300_000);
const FIVE_MIN_MS: u64 = 300_000;

/// 餵入 `n_closed` 根遞增的 5m 已關閉 K 線到 pipeline 的 kline_manager。
///
/// 每根 bar 用 2 個同週期 tick（open/high-low/close 有區分）+ 下一週期 tick
/// 觸發收盤。回傳最後一根已關閉 bar 的 `open_time_ms`（= 當前 epoch 的時間部分）。
/// donchian period=20、indicator min=30 根，故 n_closed 須 >= 31。
fn seed_5m_bars(pipeline: &mut TickPipeline, n_closed: usize) -> u64 {
    // 用上升趨勢價格序列，確保 donchian.upper 落在歷史窗高點、可被後續 live
    // ctx.price 突破（測 breach 用）。
    for k in 0..=n_closed {
        let period_open = BASE_TS + k as u64 * FIVE_MIN_MS;
        let base_price = 60_000.0 + k as f64 * 10.0;
        // 同一 5m 週期內兩個 tick：低點 + 高點。
        pipeline
            .kline_manager
            .on_tick(SYM, base_price, period_open + 1_000, 1.0, base_price);
        pipeline
            .kline_manager
            .on_tick(SYM, base_price + 5.0, period_open + 2_000, 1.0, base_price + 5.0);
    }
    // 最後一根已關閉 bar 的 open_time = (n_closed-1) 那一根（最後一個週期的 bar
    // 尚在 building，未關閉）。
    BASE_TS + (n_closed as u64 - 1) * FIVE_MIN_MS
}

/// 構造一份 5m IndicatorSnapshot，帶可調 (bandwidth, percent_b, vol) 與真實
/// prior-bar Donchian（upper=110）。
///
/// 與 bb_breakout 既有測試 `indicator_with_runtime_donchian` 同構：prior-bar
/// Donchian upper=110（窗內 high[19]=110），current-bar high=999 不參與
/// `donchian_prior`。bw 低（< squeeze_bw）→ squeeze；bw 高（>= expansion_bw）
/// + percent_b>1.0 + 高 vol → expansion long。`Box::leak` 取 `'static` ref
/// （test-only，對齊既有 helper）。
fn snapshot_5m_with_prior_donchian(bw: f64, pct_b: f64, vol: f64) -> &'static IndicatorSnapshot {
    let mut high = vec![100.0; 21];
    let mut low = vec![90.0; 21];
    let close = vec![95.0; 21];
    let volume = vec![1000.0; 21];
    high[19] = 110.0;
    low[19] = 88.0;
    high[20] = 999.0;
    low[20] = 1.0;
    let donchian = IndicatorEngine::compute_all(&high, &low, &close, &volume).donchian;

    Box::leak(Box::new(IndicatorSnapshot {
        bollinger: Some(openclaw_core::indicators::BollingerResult {
            upper: 112.0,
            middle: 100.0,
            lower: 88.0,
            bandwidth: bw,
            percent_b: pct_b,
        }),
        volume_ratio: Some(vol),
        donchian,
        ..IndicatorSnapshot::default()
    }))
}

// =========================================================================
// (1a) 同一 5m bar 內，多 intra-bar tick → 5m 快照 bit-identical（重算未觸發）。
// =========================================================================
#[test]
fn perf1_intra_bar_returns_bit_identical_snapshot_without_recompute() {
    let mut pipeline = TickPipeline::new(&[SYM]);
    seed_5m_bars(&mut pipeline, 35);

    // 首次呼叫 → miss → 重算 + populate cache/epoch。
    let first = pipeline
        .cached_or_recompute_indicators_5m(SYM)
        .expect("seeded 35 bars 應產出 Some 5m 快照");

    // 快照與 epoch 已寫入。
    assert!(
        pipeline.perf1_indicators_5m_cache.contains_key(SYM),
        "首次重算後快取必含該 symbol"
    );
    let epoch_after_first = *pipeline
        .perf1_indicators_5m_epoch
        .get(SYM)
        .expect("epoch 必同步寫入");

    // 後續同 bar 內多次呼叫（模擬 intra-bar 多 tick，價格不影響 5m epoch）→
    // 必回 bit-identical 快照（與每 tick 重算結果相同），且 epoch 不變。
    for _ in 0..5 {
        let again = pipeline
            .cached_or_recompute_indicators_5m(SYM)
            .expect("epoch 未變應回快取 Some");
        assert_eq!(
            serde_json::to_string(&again).unwrap(),
            serde_json::to_string(&first).unwrap(),
            "同一 5m bar 內快取快照必與首次重算 bit-identical"
        );
        assert_eq!(
            *pipeline.perf1_indicators_5m_epoch.get(SYM).unwrap(),
            epoch_after_first,
            "epoch 在同 bar 內不得變化"
        );
    }
}

/// 構造一個 5m signal_timeframe 的 ctx（複用同一份 squeeze+Donchian 5m 快照），
/// 只變 live `price`。1m 指標走同一 squeeze 快照（bb_breakout 1m 路徑用於
/// squeeze 偵測；此處用 5m 路徑，1m 僅佔位）。
fn ctx_5m_with_price(
    snap_5m: &'static IndicatorSnapshot,
    surface: &'static AlphaSurface<'static>,
    price: f64,
    ts: u64,
) -> TickContext<'static> {
    TickContext {
        symbol: "BTC",
        price,
        timestamp_ms: ts,
        indicators: Some(snap_5m),
        indicators_5m: Some(snap_5m),
        signals: &[],
        h0_allowed: true,
        funding_rate: None,
        index_price: None,
        open_interest: None,
        best_bid: None,
        best_ask: None,
        tick_size: None,
        alpha_surface_ref: surface,
        position_state: None,
        is_pinned: true,
    }
}

// =========================================================================
// (1b) scope fence：bb_breakout 5m Donchian breach 每 tick 對 live ctx.price
//      評估 —— 快取的只是 Donchian 層級值（upper=110），live 價的突破判定仍逐
//      tick。同一份（快取的）5m 快照下，價突破 upper → 入場；價未達 upper →
//      Donchian Hard 硬拒。證明 PERF-1 只 gate 指標重算、未 gate 策略分派。
// =========================================================================
#[test]
fn perf1_bb_breakout_donchian_breach_evaluated_per_tick_on_live_price() {
    // enable_oi_signal 預設 false → 空 AlphaSurface 不 fail-closed。
    let surface: &'static AlphaSurface<'static> =
        Box::leak(Box::new(AlphaSurface::empty()));

    let mut p = BbBreakoutParams::default();
    p.signal_timeframe = "5m".to_string();
    p.min_persistence_ms = 0;

    // squeeze 快照（低 bw）建立 squeeze 狀態；expansion 快照（高 bw + 高 %B +
    // 高 vol）為「breakout-ready」的快取快照（Donchian prior upper=110）。
    // expansion 快照在兩個價格變體間複用 —— 模擬同一根 5m bar 的快取快照在多個
    // intra-bar tick 複用。
    let squeeze = snapshot_5m_with_prior_donchian(0.01, 0.5, 1.0);
    let expansion = snapshot_5m_with_prior_donchian(0.05, 1.1, 2.0);

    // 場景 A：價突破 upper（110.0 >= 110）→ 入場。
    let mut s_breach = BbBreakout::new();
    s_breach.update_params(p.clone()).expect("valid 5m params");
    // 首 tick 建立 squeeze。
    s_breach.on_tick(&ctx_5m_with_price(squeeze, surface, 95.0, 0), surface);
    let actions_breach =
        s_breach.on_tick(&ctx_5m_with_price(expansion, surface, 110.0, 700_000), surface);

    // 場景 B：複用同一份 expansion（快取）5m 快照，但 live 價未達 upper（109.0
    // < 110）→ Donchian Hard 硬拒。
    let mut s_no_breach = BbBreakout::new();
    s_no_breach.update_params(p).expect("valid 5m params");
    s_no_breach.on_tick(&ctx_5m_with_price(squeeze, surface, 95.0, 0), surface);
    let actions_no_breach =
        s_no_breach.on_tick(&ctx_5m_with_price(expansion, surface, 109.0, 700_000), surface);

    assert_eq!(
        actions_breach.len(),
        1,
        "live price >= donchian.upper(110) → 突破 → 入場（per-tick 對 live price 評估）"
    );
    assert!(
        matches!(actions_breach[0], StrategyAction::Open(_)),
        "突破應為 Open intent"
    );
    assert!(
        actions_no_breach.is_empty(),
        "live price < donchian.upper(110) → 未突破 → Donchian Hard 硬拒（per-tick 評估生效）"
    );
    // 同一份快取的 5m 快照下，breach 判定隨 live ctx.price 改變 → 證明快取層級值
    // 不影響「每 tick 對 live 價的突破評估」，dispatch 未被 gate。
    assert_ne!(
        actions_breach.len(),
        actions_no_breach.len(),
        "同一快取 5m 快照下，breach 判定必隨 live ctx.price 改變 → dispatch 未被 gate"
    );
}

// =========================================================================
// (2a) cache-invalidation：推進 5m epoch（新收盤）→ 強制重算 + 刷新 epoch。
// =========================================================================
#[test]
fn perf1_new_5m_close_advances_epoch_and_recomputes() {
    let mut pipeline = TickPipeline::new(&[SYM]);
    seed_5m_bars(&mut pipeline, 35);

    let _ = pipeline
        .cached_or_recompute_indicators_5m(SYM)
        .expect("首次 Some");
    let epoch_before = *pipeline.perf1_indicators_5m_epoch.get(SYM).unwrap();

    // 餵入下一根 5m 收盤（時間部分推進）。
    let next_open = BASE_TS + 35 * FIVE_MIN_MS;
    pipeline
        .kline_manager
        .on_tick(SYM, 60_400.0, next_open + 1_000, 1.0, 60_400.0);
    // 再餵下一週期 tick 觸發上一根收盤。
    pipeline
        .kline_manager
        .on_tick(SYM, 60_410.0, next_open + FIVE_MIN_MS + 1_000, 1.0, 60_410.0);

    let _ = pipeline
        .cached_or_recompute_indicators_5m(SYM)
        .expect("新收盤後仍 Some");
    let epoch_after = *pipeline.perf1_indicators_5m_epoch.get(SYM).unwrap();

    assert_ne!(
        epoch_before.0, epoch_after.0,
        "新 5m 收盤後 epoch 的 open_time_ms 部分必推進（強制重算）"
    );
}

// =========================================================================
// (2b) cache-invalidation：改 ewma_lambda（RiskConfig 熱重載）→ 強制重算。
// =========================================================================
#[test]
fn perf1_ewma_lambda_hot_reload_forces_recompute() {
    let mut pipeline = TickPipeline::new(&[SYM]);
    seed_5m_bars(&mut pipeline, 35);

    // 接 risk_store，5m lambda=0.90。
    let mut cfg = RiskConfig::default();
    cfg.ewma_vol.lambdas.insert("5m".to_string(), 0.90);
    let store = Arc::new(ConfigStore::new(cfg.clone()));
    pipeline.set_risk_store(Arc::clone(&store));

    let _ = pipeline
        .cached_or_recompute_indicators_5m(SYM)
        .expect("首次 Some");
    let epoch_before = *pipeline.perf1_indicators_5m_epoch.get(SYM).unwrap();
    assert!(
        (epoch_before.1 - 0.90).abs() < 1e-9,
        "epoch lambda 部分必反映 store 的 5m lambda=0.90"
    );

    // 熱重載 lambda → 0.80（不動 K 線，open_time_ms 不變）。模擬 IPC
    // patch_risk_config 後的原子 replace（與 risk_governance_hot_reload 同模式）。
    let mut next = cfg.clone();
    next.ewma_vol.lambdas.insert("5m".to_string(), 0.80);
    store
        .replace(next, crate::config::PatchSource::Operator)
        .expect("lambda 熱重載 replace 必須成功");

    let _ = pipeline
        .cached_or_recompute_indicators_5m(SYM)
        .expect("熱重載後仍 Some");
    let epoch_after = *pipeline.perf1_indicators_5m_epoch.get(SYM).unwrap();

    assert_eq!(
        epoch_before.0, epoch_after.0,
        "open_time_ms 不變（未動 K 線），純驗 lambda 改變觸發重算"
    );
    assert!(
        (epoch_after.1 - 0.80).abs() < 1e-9,
        "lambda 熱重載後 epoch lambda 部分必更新為 0.80（強制重算）"
    );
    assert_ne!(
        epoch_before.1, epoch_after.1,
        "lambda 在 epoch key 內 → 改 lambda 必使 epoch 不同 → 重算（防服務過期快照）"
    );
}

// =========================================================================
// (3) 不變量：重算回 None（暖機期 < 30 根）→ 不寫快取（never cache None）。
// =========================================================================
#[test]
fn perf1_none_recompute_never_cached() {
    let mut pipeline = TickPipeline::new(&[SYM]);
    // 只餵 10 根（< 30 indicator min）→ compute 回 None。
    seed_5m_bars(&mut pipeline, 10);

    let result = pipeline.cached_or_recompute_indicators_5m(SYM);
    assert!(result.is_none(), "< 30 根時 5m 指標應回 None");
    assert!(
        !pipeline.perf1_indicators_5m_cache.contains_key(SYM),
        "重算回 None 時絕不寫入快取（never cache None）"
    );
    assert!(
        !pipeline.perf1_indicators_5m_epoch.contains_key(SYM),
        "重算回 None 時 epoch 也不應寫入"
    );
}

// =========================================================================
// (5) E4 bit-identical 驗：對代表性 tick 序列逐 tick 比 cache-on（gated helper）
//     vs cache-off（直接 compute_indicators_for_timeframe）的 5m 指標輸出，
//     斷言全 16 指標 1e-4 容差內一致 + serde byte-identical（無漂移）。
//
//     與 (1a) 的差異：(1a) 只證「cache-hit clone == 首次重算」（cache-on 內部
//     自洽）；本測獨立把同一 epoch 下的 cache-on 輸出與「完全不走 cache 的直接
//     重算」並列對比，證 gate 引入後輸出對齊 baseline 行為（cache-off = PERF-1
//     之前的每 tick 重算路徑）。涵蓋 epoch 不變（intra-bar）+ epoch 推進（新
//     5m 收盤）兩種 regime，跨 bar 邊界仍 bit-identical。
// =========================================================================

/// 逐欄抽出 IndicatorSnapshot 的所有 f64 標量為 (label, value) 對，供 1e-4 容差比對。
/// Option=None 的指標跳過（兩側必同時 None，由 serde byte-identical 斷言保證）。
fn snapshot_scalars(s: &IndicatorSnapshot) -> Vec<(&'static str, f64)> {
    let mut v: Vec<(&'static str, f64)> = Vec::new();
    let mut push = |k: &'static str, x: Option<f64>| {
        if let Some(x) = x {
            v.push((k, x));
        }
    };
    push("sma_20", s.sma_20);
    push("sma_50", s.sma_50);
    push("ema_12", s.ema_12);
    push("ema_26", s.ema_26);
    push("rsi_14", s.rsi_14);
    push("volume_ratio", s.volume_ratio);
    if let Some(m) = &s.macd {
        v.push(("macd.macd", m.macd));
        v.push(("macd.signal", m.signal));
        v.push(("macd.histogram", m.histogram));
    }
    if let Some(b) = &s.bollinger {
        v.push(("bb.upper", b.upper));
        v.push(("bb.middle", b.middle));
        v.push(("bb.lower", b.lower));
        v.push(("bb.bandwidth", b.bandwidth));
        v.push(("bb.percent_b", b.percent_b));
    }
    if let Some(a) = &s.atr_14 {
        v.push(("atr_14", a.atr));
    }
    if let Some(a) = &s.atr_5 {
        v.push(("atr_5", a.atr));
    }
    if let Some(st) = &s.stochastic {
        v.push(("stoch.k", st.k));
        v.push(("stoch.d", st.d));
    }
    if let Some(k) = &s.kama {
        v.push(("kama", k.kama));
    }
    if let Some(a) = &s.adx {
        v.push(("adx", a.adx));
    }
    if let Some(h) = &s.hurst {
        v.push(("hurst", h.hurst));
    }
    if let Some(e) = &s.ewma_vol {
        v.push(("ewma_vol", e.ewma_vol));
    }
    if let Some(d) = &s.donchian {
        v.push(("donchian.upper", d.upper));
        v.push(("donchian.lower", d.lower));
        v.push(("donchian.middle", d.middle));
    }
    v
}

/// 比對兩份快照全標量在 1e-4 相對容差內（abs<1e-12 退化用絕對容差），並回欄位數。
fn assert_snapshots_within_1e4(label: &str, cache_on: &IndicatorSnapshot, cache_off: &IndicatorSnapshot) -> usize {
    let on = snapshot_scalars(cache_on);
    let off = snapshot_scalars(cache_off);
    assert_eq!(
        on.len(),
        off.len(),
        "{label}: cache-on vs cache-off 指標欄位數必一致（Some/None 集合相同）"
    );
    for ((kon, von), (koff, voff)) in on.iter().zip(off.iter()) {
        assert_eq!(kon, koff, "{label}: 欄位順序/集合必一致 {kon} vs {koff}");
        let denom = von.abs().max(voff.abs());
        let rel = if denom < 1e-12 { (von - voff).abs() } else { (von - voff).abs() / denom };
        assert!(
            rel < 1e-4,
            "{label}: 指標 {kon} cache-on={von} cache-off={voff} 相對誤差 {rel:.3e} >= 1e-4（漂移）"
        );
    }
    on.len()
}

#[test]
fn perf1_cache_on_vs_cache_off_bit_identical_over_tick_sequence() {
    let mut pipeline = TickPipeline::new(&[SYM]);
    seed_5m_bars(&mut pipeline, 35);

    // 代表性 tick 序列：對同一 epoch 連跑 8 個 intra-bar tick，cache-on 走 gated
    // helper（首 tick 重算+寫 cache，後續回 clone），cache-off 走「不碰 cache 的
    // 直接重算」（= PERF-1 引入前的每 tick 行為）。逐 tick 並列對比。
    let mut total_fields = 0usize;
    for tick in 0..8u32 {
        let on = pipeline
            .cached_or_recompute_indicators_5m(SYM)
            .expect("epoch 穩定下 cache-on 必 Some");
        // cache-off：繞過 cache 直接重算（&self，不動 cache/epoch 狀態）。
        let off = pipeline
            .compute_indicators_for_timeframe(SYM, "5m")
            .expect("cache-off 直接重算同 epoch 必 Some");

        // (a) serde byte-identical（最強斷言：clone 必逐位元相同）。
        assert_eq!(
            serde_json::to_string(&on).unwrap(),
            serde_json::to_string(&off).unwrap(),
            "tick {tick}: cache-on 輸出必與 cache-off 直接重算 serde byte-identical"
        );
        // (b) 任務要求的 1e-4 容差逐欄驗（即使 serde 已過，明確證指標數值無漂移）。
        let n = assert_snapshots_within_1e4(&format!("intra-bar tick {tick}"), &on, &off);
        assert!(n >= 5, "代表性快照至少含 5 個非 None 標量指標，實得 {n}");
        total_fields = n;
    }
    assert!(total_fields > 0, "序列必比對到非空指標集合");

    // 跨 bar 邊界：推進一根新 5m 收盤 → cache-on 強制重算（新 epoch），再與
    // cache-off 並列，證 epoch 推進後仍 bit-identical（非只 intra-bar 巧合）。
    let next_open = BASE_TS + 35 * FIVE_MIN_MS;
    pipeline
        .kline_manager
        .on_tick(SYM, 60_400.0, next_open + 1_000, 1.0, 60_400.0);
    pipeline
        .kline_manager
        .on_tick(SYM, 60_410.0, next_open + FIVE_MIN_MS + 1_000, 1.0, 60_410.0);

    let on_next = pipeline
        .cached_or_recompute_indicators_5m(SYM)
        .expect("新收盤後 cache-on 必 Some");
    let off_next = pipeline
        .compute_indicators_for_timeframe(SYM, "5m")
        .expect("新收盤後 cache-off 必 Some");
    assert_eq!(
        serde_json::to_string(&on_next).unwrap(),
        serde_json::to_string(&off_next).unwrap(),
        "跨 5m bar 邊界後 cache-on 重算輸出仍須與 cache-off serde byte-identical"
    );
    assert_snapshots_within_1e4("cross-bar boundary", &on_next, &off_next);
}

// =========================================================================
// (4) remove_symbol 清除 PERF-1 快取 + epoch（防同名 symbol 重入繼承過期快照）。
// =========================================================================
#[test]
fn perf1_remove_symbol_clears_cache_and_epoch() {
    let mut pipeline = TickPipeline::new(&[SYM]);
    seed_5m_bars(&mut pipeline, 35);
    let _ = pipeline
        .cached_or_recompute_indicators_5m(SYM)
        .expect("首次 Some");
    assert!(pipeline.perf1_indicators_5m_cache.contains_key(SYM));
    assert!(pipeline.perf1_indicators_5m_epoch.contains_key(SYM));

    pipeline.remove_symbol(SYM);

    assert!(
        !pipeline.perf1_indicators_5m_cache.contains_key(SYM),
        "remove_symbol 後 PERF-1 快取必清除"
    );
    assert!(
        !pipeline.perf1_indicators_5m_epoch.contains_key(SYM),
        "remove_symbol 後 PERF-1 epoch 必清除"
    );
}
