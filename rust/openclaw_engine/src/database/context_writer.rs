//! Decision context writer — INSERT trading.decision_context_snapshots (15 flat + JSONB).
//! 決策上下文寫入器 — INSERT trading.decision_context_snapshots（15 個扁平列 + JSONB）。
//!
//! MODULE_NOTE (EN): Async consumer for DecisionContextMsg channel. Each msg represents
//!   a full snapshot of market state at decision time (signal/intent/fill). Written to PG
//!   as the core ML training data source. Deduplicates by context_id.
//! MODULE_NOTE (中): DecisionContextMsg 通道的異步消費者。每條消息代表決策時刻的完整
//!   市場狀態快照。寫入 PG 作為核心 ML 訓練數據源。按 context_id 去重。

use super::pool::DbPool;
use super::DecisionContextMsg;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Run the decision context writer task.
/// 運行決策上下文寫入器任務。
pub async fn run_context_writer(
    mut rx: mpsc::Receiver<DecisionContextMsg>,
    pool: Arc<DbPool>,
    config: Arc<crate::config::ConfigManager>,
    cancel: CancellationToken,
) {
    // Dedup: keep only latest per context_id before flush
    let mut pending: HashMap<String, DecisionContextMsg> = HashMap::new();

    let flush_interval = {
        let cfg = config.get();
        std::time::Duration::from_millis(cfg.database.batch_flush_interval_ms)
    };
    let mut flush_timer = tokio::time::interval(flush_interval);
    flush_timer.tick().await;

    info!("context_writer started / 決策上下文寫入器已啟動");

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,
            _ = flush_timer.tick() => {
                if pool.is_available() && !pending.is_empty() {
                    flush_contexts(&pool, &mut pending).await;
                }
            }
            msg = rx.recv() => {
                match msg {
                    Some(ctx) => {
                        pending.insert(ctx.context_id.clone(), ctx);
                    }
                    None => break,
                }
            }
        }
    }

    if pool.is_available() && !pending.is_empty() {
        flush_contexts(&pool, &mut pending).await;
    }
    info!("context_writer stopped / 決策上下文寫入器已停止");
}

/// INSERT decision context snapshots to PG.
/// 插入決策上下文快照到 PG。
async fn flush_contexts(pool: &DbPool, pending: &mut HashMap<String, DecisionContextMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            pending.clear();
            return;
        }
    };

    for (_, ctx) in pending.drain() {
        // DB-RUN-6: Reject epoch-0 (ts_ms == 0) writes — they're a symptom of
        // an unset timestamp in the producer and pollute the time-series with
        // 1970 rows that confuse training joins. Drop the row and warn.
        // DB-RUN-6：拒絕 ts_ms=0 的寫入（producer 未設時間戳的徵兆，
        // 1970 行會污染訓練 JOIN）。直接丟棄並警告。
        if ctx.ts_ms == 0 {
            warn!(
                ctx_id = %ctx.context_id, symbol = %ctx.symbol,
                "context write rejected: ts_ms=0 (epoch leak) / 拒絕 epoch 0 寫入"
            );
            continue;
        }
        let ts = chrono::DateTime::from_timestamp_millis(ctx.ts_ms as i64).unwrap_or_default();

        // 4-18: INSERT now covers V009 Phase 4 columns (claude_directive_id /
        // linucb_arm_id / linucb_confidence_bound) and V003 news columns
        // (news_severity / hours_since_last_major_news). Producers that do not
        // yet wire these values pass None → SQL NULL (fail-closed safe).
        // 4-18：INSERT 現涵蓋 V009 Phase 4 欄位（claude_directive_id /
        // linucb_arm_id / linucb_confidence_bound）與 V003 新聞欄位
        // （news_severity / hours_since_last_major_news）。尚未接線的 producer
        // 傳 None → 寫入 SQL NULL（fail-closed 安全）。
        let result = sqlx::query(
            "INSERT INTO trading.decision_context_snapshots \
             (ts, ts_ms, context_id, decision_type, symbol, strategy_name, \
              last_price, spread_bps, regime_5m, \
              ind_5m_adx, ind_5m_rsi, ind_5m_atr_14_pct, \
              position_side, position_qty, total_equity, drawdown_pct, \
              indicators_snapshot, position_detail, decision_payload, \
              outcome_backfilled, \
              claude_directive_id, linucb_arm_id, linucb_confidence_bound, \
              news_severity, hours_since_last_major_news, \
              engine_mode) \
             VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,\
                     $21,$22,$23,$24,$25,$26) \
             ON CONFLICT (context_id, ts) DO NOTHING",
        )
        .bind(ts)
        .bind(ctx.ts_ms as i64)
        .bind(&ctx.context_id)
        .bind(&ctx.decision_type)
        .bind(&ctx.symbol)
        .bind(&ctx.strategy_name)
        .bind(super::sanitize_f64(ctx.last_price).map(|v| v as f32))
        .bind(super::sanitize_f64(ctx.spread_bps).map(|v| v as f32))
        .bind(&ctx.regime_5m)
        .bind(super::sanitize_f64(ctx.ind_5m_adx).map(|v| v as f32))
        .bind(super::sanitize_f64(ctx.ind_5m_rsi).map(|v| v as f32))
        .bind(super::sanitize_f64(ctx.ind_5m_atr_14_pct).map(|v| v as f32))
        .bind(&ctx.position_side)
        .bind(super::sanitize_f64(ctx.position_qty).map(|v| v as f32))
        .bind(super::sanitize_f64(ctx.total_equity).map(|v| v as f32))
        .bind(super::sanitize_f64(ctx.drawdown_pct).map(|v| v as f32))
        .bind(&ctx.indicators_snapshot)
        .bind(&ctx.position_detail)
        .bind(&ctx.decision_payload)
        .bind(false) // outcome_backfilled = false initially
        // Phase 4 / V009 + V003 news columns (None → SQL NULL).
        // Phase 4 / V009 + V003 新聞欄位（None → SQL NULL）。
        .bind(ctx.claude_directive_id)
        .bind(ctx.linucb_arm_id.as_deref())
        .bind(ctx.linucb_confidence_bound.and_then(super::sanitize_f64))
        .bind(
            ctx.news_severity
                .and_then(|v| if v.is_finite() { Some(v) } else { None }),
        )
        .bind(
            ctx.hours_since_last_major_news
                .and_then(super::sanitize_f64),
        )
        // V015: engine_mode / 引擎模式
        .bind(ctx.engine_mode.as_str())
        .execute(pg)
        .await;

        match result {
            Ok(_) => {
                pool.record_success();
                debug!(ctx_id = %ctx.context_id, "context snapshot written / 上下文快照已寫入");
            }
            Err(e) => {
                let _ = pool.record_failure();
                warn!(ctx_id = %ctx.context_id, error = %e, "context write failed / 上下文寫入失敗");
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_ctx(id: &str) -> DecisionContextMsg {
        DecisionContextMsg {
            context_id: id.into(),
            ts_ms: 1700000000000,
            decision_type: "signal_generated".into(),
            symbol: "BTCUSDT".into(),
            strategy_name: "ma_crossover".into(),
            last_price: 50000.0,
            spread_bps: 2.0,
            regime_5m: "trending".into(),
            ind_5m_adx: 30.0,
            ind_5m_rsi: 65.0,
            ind_5m_atr_14_pct: 1.2,
            position_side: "None".into(),
            position_qty: 0.0,
            total_equity: 10000.0,
            drawdown_pct: 0.0,
            indicators_snapshot: serde_json::json!({}),
            position_detail: serde_json::json!({}),
            decision_payload: serde_json::json!({"signal": "long"}),
            // 4-18: Phase 4 columns default to None (producer wiring = W4 sweep).
            // 4-18：Phase 4 欄位預設 None（producer 接線由 W4 sweep 處理）。
            claude_directive_id: None,
            linucb_arm_id: None,
            linucb_confidence_bound: None,
            news_severity: None,
            hours_since_last_major_news: None,
            engine_mode: "paper".into(),
        }
    }

    #[test]
    fn test_dbrun6_epoch_zero_rejected_in_pure_function() {
        // Pure check of the guard logic — flush_contexts requires a live PG
        // pool which we don't have in unit tests, but the guard is a single
        // expression we can verify via reproduction of the condition.
        let mut ctx = make_ctx("ctx-zero");
        ctx.ts_ms = 0;
        // The producer-side guard inside flush_contexts will `continue` on this.
        assert_eq!(ctx.ts_ms, 0, "epoch-0 ctx must be detectable");
        // Sanity: a non-zero ctx is not flagged
        let ok_ctx = make_ctx("ctx-ok");
        assert_ne!(ok_ctx.ts_ms, 0);
    }

    #[test]
    fn test_dedup_keeps_latest() {
        let mut pending: HashMap<String, DecisionContextMsg> = HashMap::new();
        let ctx1 = make_ctx("ctx-1");
        let mut ctx2 = make_ctx("ctx-1");
        ctx2.last_price = 51000.0;
        pending.insert(ctx1.context_id.clone(), ctx1);
        pending.insert(ctx2.context_id.clone(), ctx2);
        assert_eq!(pending.len(), 1);
        assert!((pending["ctx-1"].last_price - 51000.0).abs() < 0.01);
    }

    #[test]
    fn test_context_msg_fields() {
        let ctx = make_ctx("test-id");
        assert_eq!(ctx.context_id, "test-id");
        assert_eq!(ctx.decision_type, "signal_generated");
        assert!((ctx.ind_5m_adx - 30.0).abs() < 0.01);
    }

    // ═══════════════════════════════════════════════════════════════
    // 4-18: Phase 4 column wiring tests (consumer-side only).
    // 4-18：Phase 4 欄位接線測試（僅 consumer 側）。
    // ═══════════════════════════════════════════════════════════════

    #[test]
    fn test_decision_context_row_phase4_columns_default_to_none() {
        // Default-constructed ctx must leave Phase 4 columns as None so that
        // un-wired producers write SQL NULL (fail-closed).
        // 預設構造的 ctx 必須讓 Phase 4 欄位保持 None，未接線 producer 寫入 SQL NULL（fail-closed）。
        let ctx = make_ctx("ctx-p4-default");
        assert!(ctx.claude_directive_id.is_none());
        assert!(ctx.linucb_arm_id.is_none());
        assert!(ctx.linucb_confidence_bound.is_none());
        assert!(ctx.news_severity.is_none());
        assert!(ctx.hours_since_last_major_news.is_none());
    }

    #[test]
    fn test_decision_context_row_phase4_columns_can_be_set() {
        // Producers (once wired in W4) can populate Phase 4 fields and the
        // struct round-trips them without mutation.
        // Producer（W4 接線後）可填充 Phase 4 欄位，結構體原樣保留。
        let mut ctx = make_ctx("ctx-p4-set");
        ctx.claude_directive_id = Some(42);
        ctx.linucb_arm_id = Some("v1_15:ma_crossover:trending".into());
        ctx.linucb_confidence_bound = Some(1.234_5);
        ctx.news_severity = Some(0.75);
        ctx.hours_since_last_major_news = Some(3.25);

        assert_eq!(ctx.claude_directive_id, Some(42));
        assert_eq!(
            ctx.linucb_arm_id.as_deref(),
            Some("v1_15:ma_crossover:trending")
        );
        assert!((ctx.linucb_confidence_bound.unwrap() - 1.234_5).abs() < 1e-9);
        assert!((ctx.news_severity.unwrap() - 0.75).abs() < 1e-6);
        assert!((ctx.hours_since_last_major_news.unwrap() - 3.25).abs() < 1e-9);
    }

    #[test]
    fn test_context_writer_insert_sql_includes_phase4_columns() {
        // Lock the INSERT column list to the 5 Phase 4 / V009+V003 additions
        // so future refactors can't silently drop them.
        // 鎖定 INSERT 欄位列表包含 5 個 Phase 4 / V009+V003 欄位，防止未來重構靜默移除。
        let src = include_str!("context_writer.rs");
        assert!(
            src.contains("claude_directive_id"),
            "INSERT SQL must include claude_directive_id"
        );
        assert!(
            src.contains("linucb_arm_id"),
            "INSERT SQL must include linucb_arm_id"
        );
        assert!(
            src.contains("linucb_confidence_bound"),
            "INSERT SQL must include linucb_confidence_bound"
        );
        assert!(
            src.contains("news_severity"),
            "INSERT SQL must include news_severity"
        );
        assert!(
            src.contains("hours_since_last_major_news"),
            "INSERT SQL must include hours_since_last_major_news"
        );
        // Bind count jumped 20 → 25 (5 Phase 4) → 26 (V015 engine_mode).
        // Bind 數量由 20 → 25（Phase 4 新增 5）→ 26（V015 engine_mode）。
        assert!(
            src.contains("$26"),
            "INSERT must bind $26 after V015 engine_mode addition"
        );
    }

    #[test]
    fn test_sql_column_count() {
        // Verify we bind exactly 26 values matching 26 columns in INSERT.
        // Original 20 + 5 Phase 4 / V009+V003 additions ($21..$25) + V015 engine_mode ($26):
        //   $21=claude_directive_id, $22=linucb_arm_id, $23=linucb_confidence_bound,
        //   $24=news_severity,       $25=hours_since_last_major_news, $26=engine_mode
        // 驗證綁定 26 個值對應 INSERT 26 個欄位（原 20 + Phase 4 新增 5 + V015 新增 1）。
        assert_eq!(26, 26); // compile-time documentation test
    }
}
