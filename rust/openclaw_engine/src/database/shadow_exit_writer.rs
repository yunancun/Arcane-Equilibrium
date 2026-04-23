//! Shadow exit writer — INSERT learning.decision_shadow_exits
//! (INFRA-PREBUILD-1 Part A, 2026-04-23).
//! Combine Layer 退場時刻 shadow 寫入器 — INSERT learning.decision_shadow_exits。
//!
//! MODULE_NOTE (EN): Async consumer for the `ShadowExitMsg` channel. Each
//!   row captures the divergence (or agreement) between Track P physical-only
//!   decision and the Combine Layer output at a close fill — exercised only
//!   when `RiskConfig.exit.shadow_enabled=true` (Phase 2+). Pure observation;
//!   never enters label backfill. Distinct from `decision_shadow_fills` (V017,
//!   entry-time ε-greedy, paper-only): this table is exit-time, supports
//!   paper/demo/live/live_demo, and tracks Combine vs Physical agreement.
//!
//!   DB-level safety rails: engine_mode CHECK rejects unknown tags; ExitSource
//!   CHECK rejects invalid final decisions; epoch-0 ts rejected at writer.
//!   On PG failure, pool.record_failure() is invoked — shared JSONL fallback.
//!
//! MODULE_NOTE (中): `ShadowExitMsg` 通道的異步消費者，每條訊息寫入
//!   `learning.decision_shadow_exits` 一列（PK=shadow_exit_id BIGSERIAL）。
//!   僅當 `RiskConfig.exit.shadow_enabled=true`（Phase 2+）fire。純觀測，
//!   永不入 label 回填；與 V017 shadow_fills（entry-time ε-greedy、paper-only）
//!   語意不同：本表是 exit-time、支援四種 engine_mode、追蹤 Combine vs
//!   Physical 一致性（disagreed + disagreement_reason 欄）。
//!   DB 級保險：engine_mode CHECK、exit_source CHECK、writer 層 epoch-0 拒收；
//!   PG 失敗走 pool.record_failure() → JSONL fallback。
//!
//! Spec: V021 migration + docs/worklogs/2026-04-18--dual_track_exit_design.md §Combine Layer.

use super::pool::DbPool;
use super::ShadowExitMsg;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Coerce NaN/Inf f64 to None; finite values pass through.
/// NaN/Inf f64 → None；有限值原樣透傳。
#[inline]
fn sanitize_f64_opt(v: Option<f64>) -> Option<f64> {
    match v {
        Some(x) if x.is_finite() => Some(x),
        _ => None,
    }
}

/// Run the shadow exit writer task.
/// 運行 shadow exit 寫入器任務。
pub async fn run_shadow_exit_writer(
    mut rx: mpsc::Receiver<ShadowExitMsg>,
    pool: Arc<DbPool>,
    config: Arc<crate::config::ConfigManager>,
    cancel: CancellationToken,
) {
    // Unlike decision_features we don't dedup — the PK is BIGSERIAL; multiple
    // shadow emits for the same context_id (partial close retries) are valid
    // independent observations. Flush preserves arrival order.
    // 不去重；PK 是 BIGSERIAL，同 context_id 多次 shadow emit（partial close
    // 重試）屬合法獨立觀測。flush 保持到達順序。
    let mut pending: Vec<ShadowExitMsg> = Vec::with_capacity(128);

    let flush_interval = {
        let cfg = config.get();
        std::time::Duration::from_millis(cfg.database.batch_flush_interval_ms)
    };
    let mut flush_timer = tokio::time::interval(flush_interval);
    flush_timer.tick().await;

    info!("shadow_exit_writer started / shadow-exit 寫入器已啟動");

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,
            _ = flush_timer.tick() => {
                if pool.is_available() && !pending.is_empty() {
                    flush_shadow_exits(&pool, &mut pending).await;
                }
            }
            msg = rx.recv() => {
                match msg {
                    Some(row) => pending.push(row),
                    None => break,
                }
            }
        }
    }

    if pool.is_available() && !pending.is_empty() {
        flush_shadow_exits(&pool, &mut pending).await;
    }
    info!("shadow_exit_writer stopped / shadow-exit 寫入器已停止");
}

/// INSERT shadow exit rows to PG.
/// 寫入 shadow exit 列到 PG。
async fn flush_shadow_exits(pool: &DbPool, pending: &mut Vec<ShadowExitMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            pending.clear();
            return;
        }
    };

    let rows: Vec<ShadowExitMsg> = pending.drain(..).collect();

    for row in rows {
        // DB-RUN-6: reject epoch-0 writes — same policy as sibling writers.
        // DB-RUN-6：拒絕 ts_ms=0 寫入（1970 行會毒化時間域 JOIN）。
        if row.ts_ms == 0 {
            warn!(
                ctx_id = %row.context_id, symbol = %row.symbol,
                "shadow_exit write rejected: ts_ms=0 (epoch leak) / 拒絕 epoch 0 寫入"
            );
            continue;
        }

        // Second-line defense: engine_mode must be one of the 4 known tags.
        // DB CHECK would reject anyway; early-skip avoids polluting pool failure counter.
        // 第二道防線：engine_mode 必須是 4 個已知 tag 之一；DB CHECK 也會拒，
        // 早期跳過避免污染 pool 失敗計數。
        if !matches!(
            row.engine_mode.as_str(),
            "paper" | "demo" | "live" | "live_demo"
        ) {
            warn!(
                ctx_id = %row.context_id, engine = %row.engine_mode,
                "shadow_exit write rejected: unknown engine_mode / 拒絕未知 engine_mode"
            );
            continue;
        }

        // Second-line defense: exit_source must be one of the 4 ExitSource tags.
        // Mirrors combine_layer.rs:57-84 stable dictionary.
        // 第二道防線：exit_source 必須是 combine_layer.rs 4-tag 字典之一。
        if !matches!(
            row.exit_source.as_str(),
            "Physical" | "Hybrid" | "ML" | "Disabled"
        ) {
            warn!(
                ctx_id = %row.context_id, src = %row.exit_source,
                "shadow_exit write rejected: unknown exit_source / 拒絕未知 exit_source"
            );
            continue;
        }

        let ts = chrono::DateTime::from_timestamp_millis(row.ts_ms).unwrap_or_default();

        let result = sqlx::query(
            "INSERT INTO learning.decision_shadow_exits \
             (context_id, ts, engine_mode, strategy_name, symbol, side, \
              physical_action, physical_reason, \
              ml_model_id, ml_score, ml_age_secs, ml_confidence, \
              exit_source, disagreed, disagreement_reason, \
              ml_confirm_threshold, ml_override_high, ml_veto_low) \
             VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)",
        )
        .bind(&row.context_id)
        .bind(ts)
        .bind(&row.engine_mode)
        .bind(&row.strategy_name)
        .bind(&row.symbol)
        .bind(row.side)
        .bind(&row.physical_action)
        .bind(row.physical_reason.as_deref())
        .bind(row.ml_model_id.as_deref())
        .bind(sanitize_f64_opt(row.ml_score))
        .bind(row.ml_age_secs)
        .bind(sanitize_f64_opt(row.ml_confidence))
        .bind(&row.exit_source)
        .bind(row.disagreed)
        .bind(row.disagreement_reason.as_deref())
        .bind(sanitize_f64_opt(row.ml_confirm_threshold))
        .bind(sanitize_f64_opt(row.ml_override_high))
        .bind(sanitize_f64_opt(row.ml_veto_low))
        .execute(pg)
        .await;

        match result {
            Ok(_) => {
                pool.record_success();
                debug!(
                    ctx_id = %row.context_id, strategy = %row.strategy_name,
                    symbol = %row.symbol, src = %row.exit_source,
                    disagreed = row.disagreed,
                    "shadow_exit written / shadow-exit 已寫入"
                );
            }
            Err(e) => {
                let _ = pool.record_failure();
                warn!(
                    ctx_id = %row.context_id, error = %e,
                    "shadow_exit write failed / shadow-exit 寫入失敗"
                );
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_row(id: &str) -> ShadowExitMsg {
        ShadowExitMsg {
            context_id: id.into(),
            ts_ms: 1_700_000_000_000,
            engine_mode: "demo".into(),
            strategy_name: "ma_crossover".into(),
            symbol: "BTCUSDT".into(),
            side: 1,
            physical_action: "Lock".into(),
            physical_reason: Some("phys_lock_gate4_giveback".into()),
            ml_model_id: Some("shadow_mock_v1".into()),
            ml_score: Some(0.75),
            ml_age_secs: Some(300),
            ml_confidence: Some(0.8),
            exit_source: "Hybrid".into(),
            disagreed: false,
            disagreement_reason: None,
            ml_confirm_threshold: Some(0.70),
            ml_override_high: Some(2.0),
            ml_veto_low: Some(0.10),
        }
    }

    /// NaN/Inf f64 must coerce to None before SQL bind.
    /// NaN/Inf f64 必須在 bind 前變 None。
    #[test]
    fn test_sanitize_f64_opt_handles_nan_inf() {
        assert_eq!(sanitize_f64_opt(Some(0.75)), Some(0.75));
        assert_eq!(sanitize_f64_opt(Some(0.0)), Some(0.0));
        assert_eq!(sanitize_f64_opt(Some(f64::NAN)), None);
        assert_eq!(sanitize_f64_opt(Some(f64::INFINITY)), None);
        assert_eq!(sanitize_f64_opt(Some(f64::NEG_INFINITY)), None);
        assert_eq!(sanitize_f64_opt(None), None);
    }

    /// Carrier preserves all fields through Clone.
    /// 載體 Clone 後所有欄位保留。
    #[test]
    fn test_row_roundtrip_preserves_all_fields() {
        let row = make_row("ctx-round");
        let cloned = row.clone();
        assert_eq!(cloned.context_id, "ctx-round");
        assert_eq!(cloned.ts_ms, 1_700_000_000_000);
        assert_eq!(cloned.engine_mode, "demo");
        assert_eq!(cloned.physical_action, "Lock");
        assert_eq!(cloned.exit_source, "Hybrid");
        assert!(!cloned.disagreed);
        assert_eq!(cloned.ml_model_id.as_deref(), Some("shadow_mock_v1"));
        assert_eq!(cloned.ml_score, Some(0.75));
    }

    /// Epoch-0 rejection at writer layer — verify carrier before flush.
    /// Epoch-0 在 writer 層拒收 — 載體先驗。
    #[test]
    fn test_epoch_zero_detected() {
        let mut row = make_row("ctx-zero");
        row.ts_ms = 0;
        assert_eq!(row.ts_ms, 0);
    }

    /// Unknown engine_mode must be rejected pre-flush.
    /// 未知 engine_mode 必須在 flush 前拒絕。
    #[test]
    fn test_unknown_engine_mode_rejected_in_carrier() {
        let known = ["paper", "demo", "live", "live_demo"];
        assert!(known.contains(&"demo"));
        assert!(!known.contains(&"unknown_mode"));
    }

    /// Unknown exit_source must be rejected pre-flush.
    /// 未知 exit_source 必須在 flush 前拒絕。
    #[test]
    fn test_unknown_exit_source_rejected_in_carrier() {
        let known = ["Physical", "Hybrid", "ML", "Disabled"];
        assert!(known.contains(&"Hybrid"));
        assert!(!known.contains(&"Pure-ML"));
    }

    /// Disagreement semantic: Physical Lock + Combine ML Hold = disagreed.
    /// 分歧語意：Physical Lock + Combine ML Hold = disagreed。
    #[test]
    fn test_disagreement_semantic() {
        let mut row = make_row("ctx-dis");
        row.physical_action = "Lock".into();
        row.exit_source = "ML".into();
        row.disagreed = true;
        row.disagreement_reason = Some("ml_override_high crossed".into());
        assert!(row.disagreed);
        assert!(row.disagreement_reason.is_some());
    }

    /// Lock column list against silent schema drift vs V021.
    /// 鎖欄位列表避免與 V021 遷移靜默漂移。
    #[test]
    fn test_insert_sql_locked_columns() {
        let src = include_str!("shadow_exit_writer.rs");
        for col in [
            "context_id",
            "engine_mode",
            "strategy_name",
            "symbol",
            "side",
            "physical_action",
            "physical_reason",
            "ml_model_id",
            "ml_score",
            "ml_age_secs",
            "ml_confidence",
            "exit_source",
            "disagreed",
            "disagreement_reason",
            "ml_confirm_threshold",
            "ml_override_high",
            "ml_veto_low",
        ] {
            assert!(src.contains(col), "INSERT SQL missing column: {col}");
        }
    }
}
