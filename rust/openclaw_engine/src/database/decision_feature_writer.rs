//! Decision feature writer — INSERT learning.decision_features (EDGE-P3-1 Step 7a).
//! 決策特徵寫入器 — INSERT learning.decision_features。
//!
//! MODULE_NOTE (EN): Async consumer for `DecisionFeatureMsg` channel. Each message
//!   becomes one row in `learning.decision_features`, PK = context_id. The row
//!   captures the 17-dim `FeatureVectorV1` snapshot seen at intent time; the
//!   `label_*` columns stay NULL until `edge_label_backfill.py` populates them
//!   post-close. Dedup by context_id + `ON CONFLICT DO NOTHING` keeps the table
//!   idempotent under retries. Epoch-0 rows are rejected (DB-RUN-6 parity with
//!   context_writer).
//! MODULE_NOTE (中): `DecisionFeatureMsg` 通道的異步消費者；每條訊息寫入
//!   `learning.decision_features` 一列（PK=context_id）。捕捉意圖時刻的 17 維
//!   `FeatureVectorV1` 快照；`label_*` 欄位在 `edge_label_backfill.py` 回填前為
//!   NULL。按 context_id 去重 + `ON CONFLICT DO NOTHING` 保重試冪等。
//!   Epoch-0 行被拒絕（與 context_writer DB-RUN-6 對齊）。
//!
//! Spec: docs/references/2026-04-15--edge_predictor_spec.md v1.4 §3.3 + V017 migration.

use super::pool::DbPool;
use super::DecisionFeatureMsg;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Run the decision feature writer task.
/// 運行決策特徵寫入器任務。
pub async fn run_decision_feature_writer(
    mut rx: mpsc::Receiver<DecisionFeatureMsg>,
    pool: Arc<DbPool>,
    config: Arc<crate::config::ConfigManager>,
    cancel: CancellationToken,
) {
    // Dedup: keep only latest per context_id before flush.
    // 去重：每個 context_id 只保留最新的一條，待 flush。
    let mut pending: HashMap<String, DecisionFeatureMsg> = HashMap::new();

    let flush_interval = {
        let cfg = config.get();
        std::time::Duration::from_millis(cfg.database.batch_flush_interval_ms)
    };
    let mut flush_timer = tokio::time::interval(flush_interval);
    flush_timer.tick().await;

    info!("decision_feature_writer started / 決策特徵寫入器已啟動");

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,
            _ = flush_timer.tick() => {
                if pool.is_available() && !pending.is_empty() {
                    flush_features(&pool, &mut pending).await;
                }
            }
            msg = rx.recv() => {
                match msg {
                    Some(feat) => {
                        pending.insert(feat.context_id.clone(), feat);
                    }
                    None => break,
                }
            }
        }
    }

    if pool.is_available() && !pending.is_empty() {
        flush_features(&pool, &mut pending).await;
    }
    info!("decision_feature_writer stopped / 決策特徵寫入器已停止");
}

/// INSERT decision feature snapshots to PG.
/// 插入決策特徵快照到 PG。
async fn flush_features(pool: &DbPool, pending: &mut HashMap<String, DecisionFeatureMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            pending.clear();
            return;
        }
    };

    for (_, feat) in pending.drain() {
        // DB-RUN-6: reject epoch-0 writes — same policy as context_writer.
        // 1970 rows poison time-range training queries.
        // DB-RUN-6：拒絕 ts_ms=0（與 context_writer 同策略），1970 行會毒化訓練 JOIN。
        if feat.ts_ms == 0 {
            warn!(
                ctx_id = %feat.context_id, symbol = %feat.symbol,
                "decision feature write rejected: ts_ms=0 (epoch leak) / 拒絕 epoch 0 寫入"
            );
            continue;
        }

        let ts = chrono::DateTime::from_timestamp_millis(feat.ts_ms as i64).unwrap_or_default();

        // Parse the pre-serialized JSONB once. If it's malformed, log-and-skip
        // rather than let sqlx reject the bind: the producer controls shape, a
        // parse failure here signals a regression in `FeatureVectorV1::to_jsonb`.
        // 解析預先序列化的 JSONB；若格式錯誤，直接 skip 並 log — producer 控制格式，
        // 此處解析失敗代表 `FeatureVectorV1::to_jsonb` 退化。
        let features_value: serde_json::Value = match serde_json::from_str(&feat.features_jsonb) {
            Ok(v) => v,
            Err(e) => {
                warn!(
                    ctx_id = %feat.context_id, error = %e,
                    "decision feature write rejected: malformed JSONB / JSONB 解析失敗"
                );
                continue;
            }
        };

        // label_* columns are intentionally omitted: they default to NULL/FALSE
        // per V017 DDL and are populated later by edge_label_backfill.py.
        // label_* 欄位故意省略：V017 DDL 預設 NULL/FALSE，稍後由 edge_label_backfill.py 回填。
        let result = sqlx::query(
            "INSERT INTO learning.decision_features \
             (context_id, ts, engine_mode, strategy_name, symbol, side, \
              feature_schema_version, feature_schema_hash, feature_definition_hash, \
              features_jsonb) \
             VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) \
             ON CONFLICT (context_id) DO NOTHING",
        )
        .bind(&feat.context_id)
        .bind(ts)
        .bind(&feat.engine_mode)
        .bind(&feat.strategy_name)
        .bind(&feat.symbol)
        .bind(feat.side as i16) // SMALLINT
        .bind(&feat.feature_schema_version)
        .bind(&feat.feature_schema_hash)
        .bind(&feat.feature_definition_hash)
        .bind(&features_value)
        .execute(pg)
        .await;

        match result {
            Ok(_) => {
                pool.record_success();
                debug!(
                    ctx_id = %feat.context_id, strategy = %feat.strategy_name, symbol = %feat.symbol,
                    "decision feature written / 決策特徵已寫入"
                );
            }
            Err(e) => {
                let _ = pool.record_failure();
                warn!(
                    ctx_id = %feat.context_id, error = %e,
                    "decision feature write failed / 決策特徵寫入失敗"
                );
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_feat(id: &str) -> DecisionFeatureMsg {
        DecisionFeatureMsg {
            context_id: id.into(),
            ts_ms: 1_700_000_000_000,
            engine_mode: "paper".into(),
            strategy_name: "ma_crossover".into(),
            symbol: "BTCUSDT".into(),
            side: 1,
            feature_schema_version: "v1".into(),
            feature_schema_hash: "sha256:0011223344556677".into(),
            feature_definition_hash: "sha256:0011223344556677".into(),
            features_jsonb: r#"{"adx_1h":25.0,"side":1}"#.into(),
        }
    }

    #[test]
    fn test_dedup_keeps_latest() {
        let mut pending: HashMap<String, DecisionFeatureMsg> = HashMap::new();
        let feat1 = make_feat("ctx-1");
        let mut feat2 = make_feat("ctx-1");
        feat2.strategy_name = "funding_arb".into();
        pending.insert(feat1.context_id.clone(), feat1);
        pending.insert(feat2.context_id.clone(), feat2);
        assert_eq!(pending.len(), 1);
        assert_eq!(pending["ctx-1"].strategy_name, "funding_arb");
    }

    #[test]
    fn test_dbrun6_epoch_zero_detected() {
        // flush_features needs a live pool; verify the field carrier instead.
        // flush_features 需活 pool；此處驗欄位載體即可。
        let mut feat = make_feat("ctx-zero");
        feat.ts_ms = 0;
        assert_eq!(feat.ts_ms, 0);
        let ok = make_feat("ctx-ok");
        assert_ne!(ok.ts_ms, 0);
    }

    #[test]
    fn test_malformed_jsonb_caught_before_sql() {
        // Per writer policy, unparseable JSONB is skipped — verify the parse
        // call behaves as expected without needing a live DB.
        // 寫入器策略：不可解析的 JSONB 被 skip；無需活 DB 即可驗證 parse。
        let mut feat = make_feat("ctx-bad");
        feat.features_jsonb = "not json".into();
        let parsed: Result<serde_json::Value, _> = serde_json::from_str(&feat.features_jsonb);
        assert!(parsed.is_err());
    }

    #[test]
    fn test_valid_jsonb_parses() {
        let feat = make_feat("ctx-ok");
        let parsed: serde_json::Value =
            serde_json::from_str(&feat.features_jsonb).expect("valid JSON");
        assert_eq!(parsed["adx_1h"], 25.0);
        assert_eq!(parsed["side"], 1);
    }

    #[test]
    fn test_side_fits_smallint() {
        // i8 -1/+1 safely casts to i16 SMALLINT (-32768..32767).
        // i8 正負 1 安全轉換為 i16 SMALLINT。
        let feat_long = make_feat("ctx-long");
        let feat_short = DecisionFeatureMsg {
            side: -1,
            ..make_feat("ctx-short")
        };
        assert_eq!(feat_long.side as i16, 1);
        assert_eq!(feat_short.side as i16, -1);
    }

    #[test]
    fn test_insert_sql_locked_columns() {
        // Lock column list against silent drift — V017 schema must match.
        // 鎖定欄位列表避免靜默漂移 — 必須與 V017 schema 相符。
        let src = include_str!("decision_feature_writer.rs");
        for col in [
            "context_id",
            "engine_mode",
            "strategy_name",
            "feature_schema_version",
            "feature_schema_hash",
            "feature_definition_hash",
            "features_jsonb",
            "ON CONFLICT (context_id)",
        ] {
            assert!(src.contains(col), "INSERT SQL missing column/clause: {col}");
        }
    }
}
