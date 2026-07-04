//! Feature writer — UPSERT features.online_latest with 34-dim REAL[] feature vectors.
//! 特徵寫入器 — 使用 34 維 REAL[] 特徵向量 UPSERT features.online_latest。
//!
//! MODULE_NOTE (EN): Async consumer receiving FeatureSnapshot from bounded channel.
//!   Flushes every feature_upsert_interval_ms via UPSERT (ON CONFLICT DO UPDATE).
//!   Feature vector is flattened from IndicatorSnapshot (34 dimensions).
//! MODULE_NOTE (中): 從有界通道接收 FeatureSnapshot 的異步消費者。
//!   每 feature_upsert_interval_ms 通過 UPSERT 刷新。
//!   特徵向量從 IndicatorSnapshot 扁平化（34 維）。
//!
//! DB-RUN-4 (Session 12 investigation): There is intentionally NO `features.history`
//! table. `features.online_latest` is a hot cache for inference and PSI drift
//! detection (overwritten in place). The historical training pipeline reads from
//! `trading.decision_context_snapshots.indicators_snapshot` JSONB instead — see
//! `learning.scorer_training_features` VIEW in V005, which JOINs decision context
//! with `trading.decision_outcomes` for label backfill. Do NOT add a separate
//! features history table without first updating that VIEW and the training
//! pipeline; the dual path would fragment feature provenance.
//!
//! DB-RUN-4（Session 12 調查）：刻意 **不** 設 `features.history` 表。online_latest
//! 是推論+PSI 漂移檢測的熱快取（in-place overwrite）；訓練歷史走
//! `trading.decision_context_snapshots.indicators_snapshot` JSONB（V005 的
//! `learning.scorer_training_features` VIEW 會 JOIN 進來）。新增 history 表前必須
//! 先同步更新該 VIEW + 訓練管線，避免特徵來源分裂。

use super::pool::DbPool;
use crate::feature_collector::FeatureSnapshot;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Run the feature writer task: receive FeatureSnapshots, UPSERT to PG.
/// 運行特徵寫入器任務：接收 FeatureSnapshot，UPSERT 到 PG。
pub async fn run_feature_writer(
    mut rx: mpsc::Receiver<FeatureSnapshot>,
    pool: Arc<DbPool>,
    config: Arc<crate::config::ConfigManager>,
    cancel: CancellationToken,
) {
    // Keep only the latest snapshot per (symbol, timeframe) — dedup before flush.
    // 每 (symbol, timeframe) 只保留最新快照 — 刷新前去重。
    let mut latest: HashMap<(String, String), FeatureSnapshot> = HashMap::new();

    let upsert_interval = {
        let cfg = config.get();
        std::time::Duration::from_millis(cfg.database.feature_upsert_interval_ms)
    };
    let mut flush_timer = tokio::time::interval(upsert_interval);
    flush_timer.tick().await; // skip first

    info!("feature_writer started / 特徵寫入器已啟動");

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,
            _ = flush_timer.tick() => {
                if pool.is_available() && !latest.is_empty() {
                    flush_features(&pool, &mut latest).await;
                }
            }
            msg = rx.recv() => {
                match msg {
                    Some(snap) => buffer_snapshot(&mut latest, snap),
                    None => break,
                }
            }
        }
    }

    // Final flush / 最後一次刷新
    if pool.is_available() && !latest.is_empty() {
        flush_features(&pool, &mut latest).await;
    }
    info!("feature_writer stopped / 特徵寫入器已停止");
}

/// 快照進去重緩衝：僅當 ts_ms 不舊於同 key 既有快照時才替換。
///
/// 為什麼：P1-4a（2026-07-04）後 demo/live 多 producer 共享同一 channel，
/// 同 (symbol,timeframe) 快照可能亂序到達；`online_latest` 表語義=最新快照，
/// updated_ts_ms 不得回退，故以 max-ts 保序（同 ts 取後到者，維持原覆寫行為）。
fn buffer_snapshot(
    latest: &mut HashMap<(String, String), FeatureSnapshot>,
    snap: FeatureSnapshot,
) {
    let key = (snap.symbol.clone(), snap.timeframe.clone());
    match latest.get(&key) {
        Some(prev) if prev.ts_ms > snap.ts_ms => {} // 亂序舊快照 → 丟棄
        _ => {
            latest.insert(key, snap);
        }
    }
}

/// UPSERT all pending feature snapshots to features.online_latest.
/// 將所有待處理的特徵快照 UPSERT 到 features.online_latest。
async fn flush_features(pool: &DbPool, latest: &mut HashMap<(String, String), FeatureSnapshot>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            latest.clear();
            return;
        }
    };

    for ((symbol, timeframe), snap) in latest.drain() {
        let fv = snap.to_feature_vector();

        // UPSERT: INSERT ... ON CONFLICT (symbol, timeframe) DO UPDATE
        let result = sqlx::query(
            "INSERT INTO features.online_latest (symbol, timeframe, updated_ts_ms, feature_vector, feature_version) \
             VALUES ($1, $2, $3, $4, $5) \
             ON CONFLICT (symbol, timeframe) DO UPDATE SET \
               updated_ts_ms = EXCLUDED.updated_ts_ms, \
               feature_vector = EXCLUDED.feature_vector, \
               feature_version = EXCLUDED.feature_version"
        )
        .bind(&symbol)
        .bind(&timeframe)
        .bind(snap.ts_ms as i64)
        .bind(&fv)
        .bind(&snap.feature_version)  // $5 — G4 E2 fix: was missing, would crash at runtime
        .execute(pg)
        .await;

        match result {
            Ok(_) => {
                pool.record_success();
                debug!(symbol = %symbol, dims = fv.len(), "feature UPSERT ok / 特徵 UPSERT 成功");
            }
            Err(e) => {
                let _ = pool.record_failure();
                warn!(symbol = %symbol, error = %e, "feature UPSERT failed / 特徵 UPSERT 失敗");
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::feature_collector::FEATURE_DIM;
    use openclaw_core::indicators::IndicatorSnapshot;

    #[test]
    fn test_dedup_keeps_latest() {
        let mut latest: HashMap<(String, String), FeatureSnapshot> = HashMap::new();
        let snap1 = FeatureSnapshot::new(
            "BTC".into(),
            1000,
            50000.0,
            IndicatorSnapshot::default(),
            "v1".into(),
        );
        let snap2 = FeatureSnapshot::new(
            "BTC".into(),
            2000,
            51000.0,
            IndicatorSnapshot::default(),
            "v1".into(),
        );
        buffer_snapshot(&mut latest, snap1);
        buffer_snapshot(&mut latest, snap2);
        assert_eq!(latest.len(), 1);
        assert_eq!(latest[&("BTC".into(), "1m".into())].ts_ms, 2000);
    }

    /// P1-4a 多 producer 亂序防護：舊快照晚到不得覆蓋新快照
    /// （updated_ts_ms 單調不回退；同 ts 後到者覆寫維持原行為）。
    #[test]
    fn test_buffer_snapshot_ignores_stale_out_of_order() {
        let mut latest: HashMap<(String, String), FeatureSnapshot> = HashMap::new();
        let newer = FeatureSnapshot::new(
            "BTC".into(),
            2000,
            51000.0,
            IndicatorSnapshot::default(),
            "v1".into(),
        );
        let stale = FeatureSnapshot::new(
            "BTC".into(),
            1000,
            50000.0,
            IndicatorSnapshot::default(),
            "v1".into(),
        );
        buffer_snapshot(&mut latest, newer);
        buffer_snapshot(&mut latest, stale); // 亂序舊快照 → 必須被丟棄
        assert_eq!(latest.len(), 1);
        let kept = &latest[&("BTC".into(), "1m".into())];
        assert_eq!(kept.ts_ms, 2000, "stale 快照不得回捲 ts_ms");
        assert_eq!(kept.price, 51000.0, "stale 快照不得覆蓋特徵內容");

        // 同 ts 後到者覆寫（維持修改前 insert 語義）
        let same_ts = FeatureSnapshot::new(
            "BTC".into(),
            2000,
            52000.0,
            IndicatorSnapshot::default(),
            "v1".into(),
        );
        buffer_snapshot(&mut latest, same_ts);
        assert_eq!(latest[&("BTC".into(), "1m".into())].price, 52000.0);
    }

    #[test]
    fn test_feature_vector_dimension_correct() {
        let snap = FeatureSnapshot::new(
            "ETH".into(),
            0,
            3000.0,
            IndicatorSnapshot::default(),
            "v1".into(),
        );
        assert_eq!(snap.to_feature_vector().len(), FEATURE_DIM);
    }
}
