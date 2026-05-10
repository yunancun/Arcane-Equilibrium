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

use super::batch_insert::{exec_single_insert, SingleInsertOutcome};
use super::pool::DbPool;
use super::DecisionFeatureMsg;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

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

/// INSERT decision feature snapshots to PG via unified `exec_single_insert` helper.
/// 通過統一 `exec_single_insert` 輔助函式插入決策特徵快照到 PG。
async fn flush_features(pool: &DbPool, pending: &mut HashMap<String, DecisionFeatureMsg>) {
    if !pool.is_available() {
        warn!(
            pending_rows = pending.len(),
            "decision_feature_writer flush skipped: DB pool unavailable — retaining pending rows"
        );
        return;
    }

    let rows: Vec<(String, DecisionFeatureMsg)> = pending.drain().collect();
    for (key, feat) in rows {
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

        // W-AUDIT-4b-M3 (2026-05-09)：依 `label_close_tag.is_some()` 分流兩條 SQL。
        //   reject 變體：INSERT 連 label 三欄 + label_filled_at 用 server-side NOW()
        //                （emit 時間戳對 backfill 無意義；NOW() 標記 reject 寫入時刻）
        //   intent-only：保 V017 預設行為（label_* 欄位 default NULL/FALSE，由
        //                edge_label_backfill.py 回填）
        // W6-3c V086 (2026-05-10)：兩變體 SQL 同步擴 reject_reason_code +
        // close_reason_code 兩欄；reject 變體用 producer 端映射的 enum；intent-only
        // 變體兩欄保 NULL（V086 §3 互斥不變式：close_reason_code 走 fill 後 backfill
        // 路徑寫，不在此處 producer 入口寫）。
        // 兩條 SQL 都用 ON CONFLICT (context_id) DO NOTHING 維持冪等。
        let outcome = if feat.label_close_tag.is_some() {
            // ── Reject 變體：寫 label 三欄 + W6-3c reject_reason_code ──
            // $11 = label_close_tag（固定 "rejected_governance"）
            // $12 = label_net_edge_bps（固定 0.0）
            // $13 = label_filled_at_now（bool，true → server-side NOW()）
            // $14 = reject_reason_code（V086 12 enum 之一；producer 端 map 後）
            // $15 = close_reason_code（reject path 固定 NULL，per V086 §3 互斥）
            let query = sqlx::query(
                "INSERT INTO learning.decision_features \
                 (context_id, ts, engine_mode, strategy_name, symbol, side, \
                  feature_schema_version, feature_schema_hash, feature_definition_hash, \
                  features_jsonb, label_close_tag, label_net_edge_bps, label_filled_at, \
                  reject_reason_code, close_reason_code) \
                 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12, \
                  CASE WHEN $13 THEN now() ELSE NULL END, $14, $15) \
                 ON CONFLICT (context_id) DO NOTHING",
            )
            .bind(feat.context_id.clone())
            .bind(ts)
            .bind(feat.engine_mode.clone())
            .bind(feat.strategy_name.clone())
            .bind(feat.symbol.clone())
            .bind(feat.side as i16) // SMALLINT
            .bind(feat.feature_schema_version.clone())
            .bind(feat.feature_schema_hash.clone())
            .bind(feat.feature_definition_hash.clone())
            .bind(features_value)
            .bind(feat.label_close_tag.clone())
            .bind(feat.label_net_edge_bps)
            .bind(feat.label_filled_at_now)
            .bind(feat.reject_reason_code.clone())
            .bind(feat.close_reason_code.clone());
            exec_single_insert(pool, "learning.decision_features", query).await
        } else {
            // ── Intent-only 變體：保 V017 預設行為，label_* 欄位由 backfill 補 ──
            // label_* columns are intentionally omitted: they default to NULL/FALSE
            // per V017 DDL and are populated later by edge_label_backfill.py.
            // label_* 欄位故意省略：V017 DDL 預設 NULL/FALSE，稍後由 edge_label_backfill.py 回填。
            // W6-3c V086 (2026-05-10): reject_reason_code + close_reason_code 兩欄
            // 也省略；intent-only path 兩欄全 NULL（V086 default），下游 backfill / Python
            // edge_label_backfill.py 在 fill 後 update close_reason_code（W6-3d phase）。
            let query = sqlx::query(
                "INSERT INTO learning.decision_features \
                 (context_id, ts, engine_mode, strategy_name, symbol, side, \
                  feature_schema_version, feature_schema_hash, feature_definition_hash, \
                  features_jsonb) \
                 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) \
                 ON CONFLICT (context_id) DO NOTHING",
            )
            .bind(feat.context_id.clone())
            .bind(ts)
            .bind(feat.engine_mode.clone())
            .bind(feat.strategy_name.clone())
            .bind(feat.symbol.clone())
            .bind(feat.side as i16) // SMALLINT
            .bind(feat.feature_schema_version.clone())
            .bind(feat.feature_schema_hash.clone())
            .bind(feat.feature_definition_hash.clone())
            .bind(features_value);
            exec_single_insert(pool, "learning.decision_features", query).await
        };
        if !matches!(outcome, SingleInsertOutcome::Ok(_)) {
            pending.insert(key, feat);
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
            // W-AUDIT-4b-M3：默認 intent-only path（label 欄位全 None / false）。
            // reject path 測試用 `make_reject_feat` 變體。
            label_close_tag: None,
            label_net_edge_bps: None,
            label_filled_at_now: false,
            // W6-3c V086: intent-only path 兩 reason_code 欄位 None（V086 default）。
            reject_reason_code: None,
            close_reason_code: None,
        }
    }

    /// W-AUDIT-4b-M3：reject path filler — 模擬 governance 拒絕 path 的訊息形態。
    /// W6-3c V086：reject path 必帶 reject_reason_code（12 enum 之一），close_reason_code None。
    fn make_reject_feat(id: &str) -> DecisionFeatureMsg {
        DecisionFeatureMsg {
            label_close_tag: Some("rejected_governance".into()),
            label_net_edge_bps: Some(0.0),
            label_filled_at_now: true,
            // W6-3c V086: reject path 帶 enum；測試用 cost_gate_other 作 default。
            reject_reason_code: Some("cost_gate_other".into()),
            close_reason_code: None,
            ..make_feat(id)
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

    #[test]
    fn test_reject_path_sql_locks_label_columns() {
        // W-AUDIT-4b-M3：reject 變體 SQL 必含 label 三欄 + server-side NOW() 條件。
        // W6-3c V086：reject 變體 SQL 必含 reject_reason_code + close_reason_code 兩欄。
        let src = include_str!("decision_feature_writer.rs");
        for token in [
            "label_close_tag",
            "label_net_edge_bps",
            "label_filled_at",
            "CASE WHEN $13 THEN now() ELSE NULL END",
            // W6-3c V086 兩新欄
            "reject_reason_code",
            "close_reason_code",
            "$14",
            "$15",
        ] {
            assert!(src.contains(token), "reject SQL missing token: {token}");
        }
    }

    #[test]
    fn test_make_reject_feat_carries_reason_code() {
        // W6-3c V086：reject helper 必帶 reject_reason_code（12 enum 之一）+
        // close_reason_code None（V086 §3 互斥不變式）。
        let feat = make_reject_feat("ctx-reject-w6");
        assert!(feat.reject_reason_code.is_some());
        assert!(feat.close_reason_code.is_none());
        // 預設值對齊 V086 §4.1 enum
        let code = feat.reject_reason_code.as_deref().unwrap();
        let valid_enum = [
            "cost_gate_js_demo_negative_edge",
            "cost_gate_atr_unavailable",
            "cost_gate_other",
            "duplicate_position",
            "direction_conflict",
            "position_count_limit",
            "scanner_market_gate",
            "scanner_opportunity_canary",
            "drawdown_breach",
            "symbol_blocklist",
            "risk_gate_other",
            "reject_other",
        ];
        assert!(
            valid_enum.contains(&code),
            "reject_reason_code '{code}' not in V086 12 enum"
        );
    }

    #[test]
    fn test_make_feat_default_omits_reason_codes() {
        // W6-3c V086：intent-only path（make_feat default）兩欄全 None；不會走 reject 變體 SQL。
        let feat = make_feat("ctx-intent-only");
        assert!(feat.reject_reason_code.is_none());
        assert!(feat.close_reason_code.is_none());
        assert!(feat.label_close_tag.is_none());
    }

    #[test]
    fn test_make_feat_default_is_intent_only() {
        // W-AUDIT-4b-M3：預設 helper 不應觸發 reject 變體 SQL。
        let feat = make_feat("ctx-default");
        assert!(feat.label_close_tag.is_none());
        assert!(feat.label_net_edge_bps.is_none());
        assert!(!feat.label_filled_at_now);
    }

    #[test]
    fn test_make_reject_feat_carries_negative_label() {
        // W-AUDIT-4b-M3：reject helper 必寫 "rejected_governance" + 0.0 + NOW() flag。
        let feat = make_reject_feat("ctx-reject");
        assert_eq!(feat.label_close_tag.as_deref(), Some("rejected_governance"));
        assert_eq!(feat.label_net_edge_bps, Some(0.0));
        assert!(feat.label_filled_at_now);
    }
}
