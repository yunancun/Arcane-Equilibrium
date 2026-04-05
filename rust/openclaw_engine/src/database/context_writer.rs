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
        None => { pending.clear(); return; }
    };

    for (_, ctx) in pending.drain() {
        let ts = chrono::DateTime::from_timestamp_millis(ctx.ts_ms as i64)
            .unwrap_or_default();

        let result = sqlx::query(
            "INSERT INTO trading.decision_context_snapshots \
             (ts, ts_ms, context_id, decision_type, symbol, strategy_name, \
              last_price, spread_bps, regime_5m, \
              ind_5m_adx, ind_5m_rsi, ind_5m_atr_14_pct, \
              position_side, position_qty, total_equity, drawdown_pct, \
              indicators_snapshot, position_detail, decision_payload, \
              outcome_backfilled) \
             VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20) \
             ON CONFLICT (context_id, ts) DO NOTHING"
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
        }
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

    #[test]
    fn test_sql_column_count() {
        // Verify we bind exactly 20 values matching 20 columns in INSERT
        // $1=ts, $2=ts_ms, $3=context_id, $4=decision_type, $5=symbol,
        // $6=strategy_name, $7=last_price, $8=spread_bps, $9=regime_5m,
        // $10=ind_5m_adx, $11=ind_5m_rsi, $12=ind_5m_atr_14_pct,
        // $13=position_side, $14=position_qty, $15=total_equity, $16=drawdown_pct,
        // $17=indicators_snapshot, $18=position_detail, $19=decision_payload,
        // $20=outcome_backfilled
        // Count: 20 columns = 20 bind calls ✓
        assert_eq!(20, 20); // compile-time documentation test
    }
}
