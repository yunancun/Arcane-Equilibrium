//! Feature writer — UPSERT features.online_latest with 34-dim REAL[] feature vectors.
//! 特徵寫入器 — 使用 34 維 REAL[] 特徵向量 UPSERT features.online_latest。
//!
//! MODULE_NOTE (EN): Async consumer receiving FeatureSnapshot from bounded channel.
//!   Flushes every feature_upsert_interval_ms via UPSERT (ON CONFLICT DO UPDATE).
//!   Feature vector is flattened from IndicatorSnapshot (34 dimensions).
//! MODULE_NOTE (中): 從有界通道接收 FeatureSnapshot 的異步消費者。
//!   每 feature_upsert_interval_ms 通過 UPSERT 刷新。
//!   特徵向量從 IndicatorSnapshot 扁平化（34 維）。

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
                    Some(snap) => {
                        let key = (snap.symbol.clone(), snap.timeframe.clone());
                        latest.insert(key, snap);
                    }
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
            0.0,
            IndicatorSnapshot::default(),
            "v1".into(),
        );
        let snap2 = FeatureSnapshot::new(
            "BTC".into(),
            2000,
            51000.0,
            0.0,
            IndicatorSnapshot::default(),
            "v1".into(),
        );
        latest.insert(("BTC".into(), "1m".into()), snap1);
        latest.insert(("BTC".into(), "1m".into()), snap2);
        assert_eq!(latest.len(), 1);
        assert_eq!(latest[&("BTC".into(), "1m".into())].ts_ms, 2000);
    }

    #[test]
    fn test_feature_vector_dimension_correct() {
        let snap = FeatureSnapshot::new(
            "ETH".into(),
            0,
            3000.0,
            0.0,
            IndicatorSnapshot::default(),
            "v1".into(),
        );
        assert_eq!(snap.to_feature_vector().len(), FEATURE_DIM);
    }
}
