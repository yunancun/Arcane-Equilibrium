// P1-4a G3-DRIFT-LANE-FIX（2026-07-04 冷審計 R2）：非 paper 路徑 FeatureSnapshot
// 發送回歸測試。
//
// 被測意圖：`features.online_latest` 的唯一 producer = TickPipeline step_1_2 的
// FeatureSnapshot emit。歷史上只有 Paper pipeline 接 feature channel，Paper 封存
// 後表凍結（2026-05-06）、G3 drift 偵測全鏈 no-op。本檔證明：**Demo kind**（現行
// 活躍 pipeline）只要接上 feature channel，指標暖機後每 tick 都會 emit 快照，
// 且向量維度符合 features.online_latest 的 34 維契約（feature_writer 端負責
// 去重 + interval flush，故 per-tick emit 不等於 per-tick DB 寫）。
//
// 走真實 `TickPipeline::on_tick` → `on_tick_step_1_2_klines_indicators` 路徑
// （非 mock），透過 mpsc receiver 讀回快照驗證（範式對齊 klines_turnover_gating）。

use super::super::*;
use crate::feature_collector::{FeatureSnapshot, FEATURE_DIM};

const BASE_TS: u64 = 1_704_067_200_000; // 2024-01-01 00:00:00 UTC，對齊分鐘邊界

/// 構造帶 base 量的 Trade 事件（對齊 step_1_2 取值約定：volume_24h 於 Trade
/// 事件語義下承載單筆 base 數量）。
fn trade_event(symbol: &str, price: f64, qty: f64, ts: u64) -> PriceEvent {
    let mut e = PriceEvent::new(symbol.to_string(), price, ts);
    e.event_kind = Some(PriceEventKind::Trade);
    e.volume_24h = qty;
    e.trade_qty = Some(qty);
    e
}

/// Demo kind + feature channel 接線 → 指標暖機（≥30 根已收 1m bar）後 emit
/// FeatureSnapshot，且維度 = FEATURE_DIM（34，online_latest 契約）。
#[test]
fn test_demo_pipeline_emits_feature_snapshot_when_channel_wired() {
    let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<FeatureSnapshot>(64);
    p.set_feature_channel(tx);

    // 每分鐘一筆 Trade，共 40 分鐘：第 i 筆 tick 收掉前一根 1m bar，
    // compute_indicators 需 ≥30 根已收 bar，故尾段 tick 必產 emit。
    // 價格微幅波動避免指標全平退化。
    for i in 0..40u64 {
        let price = 50_000.0 + (i as f64) * 10.0;
        p.on_tick(&trade_event("BTCUSDT", price, 0.5, BASE_TS + i * 60_000));
    }

    let mut snaps: Vec<FeatureSnapshot> = Vec::new();
    while let Ok(s) = rx.try_recv() {
        snaps.push(s);
    }
    assert!(
        !snaps.is_empty(),
        "Demo pipeline 暖機後必須 emit FeatureSnapshot（G3 drift lane 斷供回歸）"
    );
    let last = snaps.last().unwrap();
    assert_eq!(last.symbol, "BTCUSDT");
    assert_eq!(last.timeframe, "1m");
    assert_eq!(
        last.to_feature_vector().len(),
        FEATURE_DIM,
        "特徵向量必須符合 features.online_latest 34 維契約"
    );
    // ts_ms 對齊事件時間軸（單 producer 順序餵入 → 單調不減）
    assert!(snaps.windows(2).all(|w| w[0].ts_ms <= w[1].ts_ms));
}

/// 未接線（feature_tx=None）→ 同樣輸入零 emit 也零 panic（fail-soft 對照組，
/// 釘住「接線與否」是唯一開關——排除 emit 被 pipeline kind 誤 gate 的可能）。
#[test]
fn test_demo_pipeline_without_channel_is_failsoft_noop() {
    let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    for i in 0..40u64 {
        let price = 50_000.0 + (i as f64) * 10.0;
        p.on_tick(&trade_event("BTCUSDT", price, 0.5, BASE_TS + i * 60_000));
    }
    // 無 channel 可斷言接收；走到這裡未 panic 即為 fail-soft 成立。
}
