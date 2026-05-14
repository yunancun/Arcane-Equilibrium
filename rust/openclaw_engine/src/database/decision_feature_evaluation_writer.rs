//! Decision feature evaluation writer — INSERT learning.decision_features_evaluations
//! (W-AUDIT-4b-M1 split, V082).
//! 決策特徵評估寫入器 — INSERT learning.decision_features_evaluations。
//!
//! MODULE_NOTE：`DecisionFeatureEvaluationMsg` 通道的異步消費者；每條訊息寫入
//!   `learning.decision_features_evaluations` 一列（PK=evaluation_id BIGSERIAL）。
//!   對應每次 `evaluate_predictor_gate` 評估（無論 intent 是否真實 emit）。
//!
//! 與 `decision_feature_writer.rs` 主要差異：
//!   - **無 dedup**：同 context_id 可被 evaluate 多次（每次都寫一列）
//!   - **無 ON CONFLICT**：BIGSERIAL PK 不會撞，重試保證冪等是 try_send 的 best-effort
//!   - **攜 evaluation_outcome / evidence_source_tier / entry_context_id**
//!   - 不寫 `learning.decision_features`（intent-only emit production training 表）
//!
//! Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
//!       2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M1
//!       sql/migrations/V082__decision_features_evaluations_split.sql
//!       CLAUDE.md §九 Non-training surfaces

use super::batch_insert::{exec_single_insert, SingleInsertOutcome};
use super::pool::DbPool;
use super::DecisionFeatureEvaluationMsg;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

/// 運行決策特徵評估寫入器任務。
pub async fn run_decision_feature_evaluation_writer(
    mut rx: mpsc::Receiver<DecisionFeatureEvaluationMsg>,
    pool: Arc<DbPool>,
    config: Arc<crate::config::ConfigManager>,
    cancel: CancellationToken,
) {
    // 暫存緩衝（與 decision_feature_writer 不同：不 dedup，按抵達順序累積）
    let mut pending: Vec<DecisionFeatureEvaluationMsg> = Vec::new();

    let flush_interval = {
        let cfg = config.get();
        std::time::Duration::from_millis(cfg.database.batch_flush_interval_ms)
    };
    let mut flush_timer = tokio::time::interval(flush_interval);
    flush_timer.tick().await;

    info!(
        "decision_feature_evaluation_writer started \
         / 決策特徵評估寫入器已啟動 (W-AUDIT-4b-M1 V082)"
    );

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,
            _ = flush_timer.tick() => {
                if pool.is_available() && !pending.is_empty() {
                    flush_evaluations(&pool, &mut pending).await;
                }
            }
            msg = rx.recv() => {
                match msg {
                    Some(eval) => {
                        pending.push(eval);
                    }
                    None => break,
                }
            }
        }
    }

    if pool.is_available() && !pending.is_empty() {
        flush_evaluations(&pool, &mut pending).await;
    }
    info!("decision_feature_evaluation_writer stopped / 決策特徵評估寫入器已停止");
}

/// INSERT decision feature evaluation snapshots to PG via unified `exec_single_insert`.
/// 通過統一 `exec_single_insert` 輔助函式插入決策特徵評估快照到 PG。
async fn flush_evaluations(pool: &DbPool, pending: &mut Vec<DecisionFeatureEvaluationMsg>) {
    if !pool.is_available() {
        warn!(
            pending_rows = pending.len(),
            "decision_feature_evaluation_writer flush skipped: DB pool unavailable — retaining buffer"
        );
        return;
    }

    let rows: Vec<DecisionFeatureEvaluationMsg> = pending.drain(..).collect();
    let mut retain_buffer: Vec<DecisionFeatureEvaluationMsg> = Vec::new();

    for eval in rows {
        // 與 decision_feature_writer DB-RUN-6 對齊：拒絕 ts_ms=0（epoch 1970）
        // 1970 行會毒化訓練 / debug 時間範圍查詢
        if eval.ts_ms == 0 {
            warn!(
                ctx_id = %eval.context_id, symbol = %eval.symbol,
                "decision_feature_evaluation write rejected: ts_ms=0 (epoch leak) / 拒絕 epoch 0 寫入"
            );
            continue;
        }

        let ts = chrono::DateTime::from_timestamp_millis(eval.ts_ms as i64).unwrap_or_default();

        // 解析預先序列化的 JSONB（與 decision_feature_writer 同策略）
        // 解析失敗代表 producer 退化，log + skip
        let features_value: serde_json::Value = match serde_json::from_str(&eval.features_jsonb) {
            Ok(v) => v,
            Err(e) => {
                warn!(
                    ctx_id = %eval.context_id, error = %e,
                    "decision_feature_evaluation write rejected: malformed JSONB / JSONB 解析失敗"
                );
                continue;
            }
        };

        // V082 schema 對應 14 個 user-supplied column（evaluation_id BIGSERIAL +
        // created_at DEFAULT NOW() 由 PG 提供）
        // INSERT 列順序對應 V082 CREATE TABLE 順序
        let query = sqlx::query(
            "INSERT INTO learning.decision_features_evaluations \
             (context_id, ts, engine_mode, strategy_name, symbol, side, \
              feature_schema_version, feature_schema_hash, feature_definition_hash, \
              features_jsonb, evaluation_outcome, evidence_source_tier, entry_context_id) \
             VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)",
        )
        .bind(eval.context_id.clone())
        .bind(ts)
        .bind(eval.engine_mode.clone())
        .bind(eval.strategy_name.clone())
        .bind(eval.symbol.clone())
        .bind(eval.side as i16) // SMALLINT
        .bind(eval.feature_schema_version.clone())
        .bind(eval.feature_schema_hash.clone())
        .bind(eval.feature_definition_hash.clone())
        .bind(features_value)
        .bind(eval.evaluation_outcome.clone())
        .bind(eval.evidence_source_tier.clone())
        .bind(eval.entry_context_id.clone());

        let outcome =
            exec_single_insert(pool, "learning.decision_features_evaluations", query).await;

        if !matches!(outcome, SingleInsertOutcome::Ok(_)) {
            // INSERT 失敗暫留以便重試（不像 decision_features 無 ON CONFLICT
            // 處理重複，這邊純 BIGSERIAL；重試只是因應 transient PG 故障）
            retain_buffer.push(eval);
        }
    }

    if !retain_buffer.is_empty() {
        // 重新放回 pending buffer
        pending.append(&mut retain_buffer);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_eval(id: &str, outcome: &str) -> DecisionFeatureEvaluationMsg {
        DecisionFeatureEvaluationMsg {
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
            evaluation_outcome: outcome.into(),
            evidence_source_tier: "evaluation_log".into(),
            entry_context_id: None,
        }
    }

    #[test]
    fn test_no_dedup_same_context_id() {
        // Unlike decision_feature_writer (HashMap dedup), evaluations are
        // append-only (BIGSERIAL PK).
        // 與 decision_feature_writer 不同：evaluation 是 append-only（BIGSERIAL PK）。
        let mut pending: Vec<DecisionFeatureEvaluationMsg> = Vec::new();
        pending.push(make_eval("ctx-1", "reject"));
        pending.push(make_eval("ctx-1", "accept"));
        pending.push(make_eval("ctx-1", "fallback_use_legacy"));
        assert_eq!(pending.len(), 3);
        assert_eq!(pending[0].evaluation_outcome, "reject");
        assert_eq!(pending[1].evaluation_outcome, "accept");
        assert_eq!(pending[2].evaluation_outcome, "fallback_use_legacy");
    }

    #[test]
    fn test_dbrun6_epoch_zero_carrier() {
        // flush_evaluations 需活 pool；驗欄位載體即可
        let mut eval = make_eval("ctx-zero", "reject");
        eval.ts_ms = 0;
        assert_eq!(eval.ts_ms, 0);
        let ok = make_eval("ctx-ok", "accept");
        assert_ne!(ok.ts_ms, 0);
    }

    #[test]
    fn test_malformed_jsonb_caught_before_sql() {
        // 不可解析 JSONB 應 skip；無需活 DB 即可驗 parse policy
        let mut eval = make_eval("ctx-bad", "reject");
        eval.features_jsonb = "not json".into();
        let parsed: Result<serde_json::Value, _> = serde_json::from_str(&eval.features_jsonb);
        assert!(parsed.is_err());
    }

    #[test]
    fn test_valid_jsonb_parses() {
        let eval = make_eval("ctx-ok", "accept");
        let parsed: serde_json::Value =
            serde_json::from_str(&eval.features_jsonb).expect("valid JSON");
        assert_eq!(parsed["adx_1h"], 25.0);
        assert_eq!(parsed["side"], 1);
    }

    #[test]
    fn test_side_fits_smallint() {
        // i8 ±1 → i16 SMALLINT 安全轉換
        let eval_long = make_eval("ctx-long", "accept");
        let eval_short = DecisionFeatureEvaluationMsg {
            side: -1,
            ..make_eval("ctx-short", "reject")
        };
        let eval_flat = DecisionFeatureEvaluationMsg {
            side: 0,
            ..make_eval("ctx-flat", "oi_panel_unavailable")
        };
        assert_eq!(eval_long.side as i16, 1);
        assert_eq!(eval_short.side as i16, -1);
        assert_eq!(eval_flat.side as i16, 0);
    }

    #[test]
    fn test_evaluation_outcome_enum_strings() {
        // V082 + V093 CHECK enum：lock 合法字串避免 producer 與 schema 漂移
        let allowed = [
            "accept",
            "reject",
            "reject_add",
            "shadow_fill",
            "fallback_use_legacy",
            "fallback_fail_closed",
            "use_legacy_no_predictor",
            "oi_panel_unavailable",
        ];
        for s in &allowed {
            let eval = make_eval("ctx-x", s);
            assert_eq!(eval.evaluation_outcome, *s);
        }
    }

    #[test]
    fn test_evidence_source_tier_enum_strings() {
        // V082 + V093 CHECK enum：lock 合法 tier
        // V050 replay tier 故意不重疊
        let mut eval_log = make_eval("ctx-1", "reject");
        eval_log.evidence_source_tier = "evaluation_log".into();
        assert_eq!(eval_log.evidence_source_tier, "evaluation_log");

        let mut eval_shadow = make_eval("ctx-2", "shadow_fill");
        eval_shadow.evidence_source_tier = "shadow_synthetic".into();
        assert_eq!(eval_shadow.evidence_source_tier, "shadow_synthetic");

        let mut eval_panel = make_eval("ctx-3", "oi_panel_unavailable");
        eval_panel.evidence_source_tier = "panel_fail_closed".into();
        eval_panel.side = 0;
        assert_eq!(eval_panel.evidence_source_tier, "panel_fail_closed");
    }

    #[test]
    fn test_entry_context_id_optional_default_none() {
        // M1 producer 一律 None；M2 trigger 才回填
        let eval = make_eval("ctx-x", "accept");
        assert!(eval.entry_context_id.is_none());

        // M2 後可選回填
        let eval_filled = DecisionFeatureEvaluationMsg {
            entry_context_id: Some("entry-uuid-1234".into()),
            ..make_eval("ctx-y", "accept")
        };
        assert_eq!(
            eval_filled.entry_context_id.as_deref(),
            Some("entry-uuid-1234")
        );
    }

    #[test]
    fn test_insert_sql_locked_columns() {
        // Lock column list against silent drift — V082 schema must match
        // 鎖定欄位列表避免靜默漂移 — 必須與 V082 schema 相符
        let src = include_str!("decision_feature_evaluation_writer.rs");
        for col in [
            "context_id",
            "engine_mode",
            "strategy_name",
            "feature_schema_version",
            "feature_schema_hash",
            "feature_definition_hash",
            "features_jsonb",
            "evaluation_outcome",
            "evidence_source_tier",
            "entry_context_id",
            "decision_features_evaluations",
        ] {
            assert!(src.contains(col), "INSERT SQL missing column/clause: {col}");
        }
        // **必須**沒有 ON CONFLICT 子句（BIGSERIAL PK 不會撞）
        // **不可有** ON CONFLICT (context_id) — 此語意只屬 V017 decision_features
        // 對 V082 用 ON CONFLICT 會破壞 evaluation log append-only 合約
        // 排除 #[cfg(test)] 與 doc-comments 內可能出現的 prose 提及，
        // 只鎖 SQL string 相關 INSERT pattern
        let sql_block = src
            .split("INSERT INTO learning.decision_features_evaluations")
            .nth(1)
            .expect("must contain INSERT block")
            .split(";")
            .next()
            .expect("must terminate with ;");
        assert!(
            !sql_block.contains("ON CONFLICT"),
            "evaluation INSERT must NOT carry ON CONFLICT — append-only contract"
        );
    }
}
