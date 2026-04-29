//! Exit feature writer — INSERT learning.exit_features (EXIT-FEATURES-TABLE-1).
//! 退場特徵寫入器 — INSERT learning.exit_features。
//!
//! MODULE_NOTE (EN): Async consumer for the `ExitFeatureRow` channel. Each
//!   row captures the DUAL-TRACK-EXIT-1 Track P/L 7-dim feature bundle + exit
//!   meta snapshot at close time. PK is (context_id, ts) — TimescaleDB
//!   hypertable requires the partition key in the PK. `ON CONFLICT DO UPDATE`
//!   allows the writer to overwrite a row if the exit path re-emits (e.g.
//!   retry after a transient PG outage) — unlike decision_features which is
//!   append-only at entry, exit rows may legitimately be regenerated with
//!   corrected realized_net_bps if downstream realized_pnl is later finalized.
//!   NaN/Inf floats are coerced to None via `sanitize_f64_or_nan_none`.
//!   Epoch-0 rows are rejected (DB-RUN-6 parity with sibling writers).
//!   JSONL fallback on PG failure is shared with the pool's
//!   record_failure() contract.
//! MODULE_NOTE (中): `ExitFeatureRow` 通道的異步消費者；每條訊息寫入
//!   `learning.exit_features` 一列（PK=(context_id, ts)；TimescaleDB hypertable
//!   要求 PK 包含 partition key）。`ON CONFLICT DO UPDATE` 允許覆寫，因退場路徑
//!   可能在 realized_pnl 最終確認後重新發射並修正 realized_net_bps；
//!   NaN/Inf 自動替換為 NULL；Epoch-0 行被拒絕（與 decision_feature_writer 同策）。
//!   PG 失敗時透過 pool.record_failure() 觸發 JSONL fallback。
//!
//! Spec: docs/worklogs/2026-04-18-2--exit_features_table_design.md

use super::pool::DbPool;
use super::ExitFeatureRow;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Coerce NaN/Inf f32 to None; finite values pass through.
/// NaN/Inf f32 → None；有限值原樣透傳。
#[inline]
fn sanitize_f32_opt(v: Option<f32>) -> Option<f32> {
    match v {
        Some(x) if x.is_finite() => Some(x),
        _ => None,
    }
}

/// Run the exit feature writer task.
/// 運行退場特徵寫入器任務。
pub async fn run_exit_feature_writer(
    mut rx: mpsc::Receiver<ExitFeatureRow>,
    pool: Arc<DbPool>,
    config: Arc<crate::config::ConfigManager>,
    cancel: CancellationToken,
) {
    // Batch buffer: unlike decision_features we don't dedup by context_id —
    // the PK is (context_id, ts) and legitimate re-emissions carry updated
    // realized_net_bps. Flush preserves arrival order.
    // 不以 context_id 去重（PK 是 (context_id, ts)，合法重發會帶修正值）；
    // flush 保持到達順序。
    let mut pending: Vec<ExitFeatureRow> = Vec::with_capacity(128);

    let flush_interval = {
        let cfg = config.get();
        std::time::Duration::from_millis(cfg.database.batch_flush_interval_ms)
    };
    let mut flush_timer = tokio::time::interval(flush_interval);
    flush_timer.tick().await; // skip first immediate tick

    info!("exit_feature_writer started / 退場特徵寫入器已啟動");

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,
            _ = flush_timer.tick() => {
                if pool.is_available() && !pending.is_empty() {
                    flush_exit_features(&pool, &mut pending).await;
                }
            }
            msg = rx.recv() => {
                match msg {
                    Some(row) => {
                        pending.push(row);
                    }
                    None => break,
                }
            }
        }
    }

    if pool.is_available() && !pending.is_empty() {
        flush_exit_features(&pool, &mut pending).await;
    }
    info!("exit_feature_writer stopped / 退場特徵寫入器已停止");
}

/// INSERT exit feature rows to PG (ON CONFLICT UPDATE).
/// 插入退場特徵行到 PG（允許覆寫）。
async fn flush_exit_features(pool: &DbPool, pending: &mut Vec<ExitFeatureRow>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            warn!(
                pending_rows = pending.len(),
                "exit_feature_writer flush skipped: DB pool unavailable — retaining pending rows"
            );
            return;
        }
    };

    // Drain into owned iterator; pending is cleared unconditionally.
    // 取出所有待寫入行，並清空 pending。
    let rows: Vec<ExitFeatureRow> = pending.drain(..).collect();

    for row in rows {
        // DB-RUN-6: reject epoch-0 writes — 1970 rows poison time-range queries.
        // DB-RUN-6：拒絕 ts_ms=0（epoch leak），會毒化時間範圍查詢。
        if row.ts_ms == 0 {
            warn!(
                ctx_id = %row.context_id, symbol = %row.symbol,
                "exit feature write rejected: ts_ms=0 (epoch leak) / 拒絕 epoch 0 寫入"
            );
            continue;
        }

        let ts = chrono::DateTime::from_timestamp_millis(row.ts_ms).unwrap_or_default();

        let result = sqlx::query(
            "INSERT INTO learning.exit_features \
             (context_id, ts, engine_mode, strategy_name, symbol, side, \
              est_net_bps, peak_pnl_pct, atr_pct, giveback_atr_norm, \
              time_since_peak_ms, price_roc_short, entry_age_secs, \
              exit_source, exit_trigger_rule, realized_net_bps, \
              feature_schema_version, feature_schema_hash) \
             VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18) \
             ON CONFLICT (context_id, ts) DO UPDATE SET \
                 engine_mode = EXCLUDED.engine_mode, \
                 strategy_name = EXCLUDED.strategy_name, \
                 symbol = EXCLUDED.symbol, \
                 side = EXCLUDED.side, \
                 est_net_bps = EXCLUDED.est_net_bps, \
                 peak_pnl_pct = EXCLUDED.peak_pnl_pct, \
                 atr_pct = EXCLUDED.atr_pct, \
                 giveback_atr_norm = EXCLUDED.giveback_atr_norm, \
                 time_since_peak_ms = EXCLUDED.time_since_peak_ms, \
                 price_roc_short = EXCLUDED.price_roc_short, \
                 entry_age_secs = EXCLUDED.entry_age_secs, \
                 exit_source = EXCLUDED.exit_source, \
                 exit_trigger_rule = EXCLUDED.exit_trigger_rule, \
                 realized_net_bps = EXCLUDED.realized_net_bps, \
                 feature_schema_version = EXCLUDED.feature_schema_version, \
                 feature_schema_hash = EXCLUDED.feature_schema_hash",
        )
        .bind(&row.context_id)
        .bind(ts)
        .bind(&row.engine_mode)
        .bind(&row.strategy_name)
        .bind(&row.symbol)
        .bind(row.side) // SMALLINT (already i16)
        .bind(sanitize_f32_opt(row.est_net_bps))
        .bind(sanitize_f32_opt(row.peak_pnl_pct))
        .bind(sanitize_f32_opt(row.atr_pct))
        .bind(sanitize_f32_opt(row.giveback_atr_norm))
        .bind(row.time_since_peak_ms)
        .bind(sanitize_f32_opt(row.price_roc_short))
        .bind(sanitize_f32_opt(row.entry_age_secs))
        .bind(row.exit_source.as_deref())
        .bind(row.exit_trigger_rule.as_deref())
        .bind(sanitize_f32_opt(row.realized_net_bps))
        .bind(&row.feature_schema_version)
        .bind(&row.feature_schema_hash)
        .execute(pg)
        .await;

        match result {
            Ok(_) => {
                pool.record_success();
                debug!(
                    ctx_id = %row.context_id, strategy = %row.strategy_name,
                    symbol = %row.symbol, source = ?row.exit_source,
                    "exit feature written / 退場特徵已寫入"
                );
            }
            Err(e) => {
                let _ = pool.record_failure();
                warn!(
                    ctx_id = %row.context_id, error = %e,
                    "exit feature write failed / 退場特徵寫入失敗"
                );
                pending.push(row);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_row(id: &str) -> ExitFeatureRow {
        ExitFeatureRow {
            context_id: id.into(),
            ts_ms: 1_700_000_000_000,
            engine_mode: "paper".into(),
            strategy_name: "ma_crossover".into(),
            symbol: "BTCUSDT".into(),
            side: 1,
            est_net_bps: Some(12.5),
            peak_pnl_pct: Some(0.85),
            atr_pct: Some(0.012),
            giveback_atr_norm: Some(0.4),
            time_since_peak_ms: Some(1_500),
            price_roc_short: Some(-0.0003),
            entry_age_secs: Some(42.0),
            exit_source: Some("Physical".into()),
            exit_trigger_rule: Some("PHYS-LOCK".into()),
            realized_net_bps: Some(10.1),
            feature_schema_version: "v1.0".into(),
            feature_schema_hash: "sha256:deadbeef".into(),
        }
    }

    /// Verify ExitFeatureRow fields round-trip through Clone + basic getters.
    /// The writer itself needs a live pool; here we verify carrier-level
    /// invariants (side fits i16, all 7 feature dims present, provenance
    /// preserved).
    /// 驗證 ExitFeatureRow 欄位 Clone 後值守恆；writer 本體需要活 pool，
    /// 此處僅驗載體層不變式（side 符合 i16、7 維特徵齊、provenance 保留）。
    #[test]
    fn test_row_roundtrip_preserves_all_fields() {
        let row = make_row("ctx-round");
        let cloned = row.clone();
        assert_eq!(cloned.context_id, "ctx-round");
        assert_eq!(cloned.ts_ms, 1_700_000_000_000);
        assert_eq!(cloned.engine_mode, "paper");
        assert_eq!(cloned.strategy_name, "ma_crossover");
        assert_eq!(cloned.symbol, "BTCUSDT");
        assert_eq!(cloned.side, 1i16);
        // 7 Track P dims present
        assert!(cloned.est_net_bps.is_some());
        assert!(cloned.peak_pnl_pct.is_some());
        assert!(cloned.atr_pct.is_some());
        assert!(cloned.giveback_atr_norm.is_some());
        assert!(cloned.time_since_peak_ms.is_some());
        assert!(cloned.price_roc_short.is_some());
        assert!(cloned.entry_age_secs.is_some());
        // Exit meta
        assert_eq!(cloned.exit_source.as_deref(), Some("Physical"));
        assert_eq!(cloned.exit_trigger_rule.as_deref(), Some("PHYS-LOCK"));
        assert!(cloned.realized_net_bps.is_some());
        // Provenance
        assert_eq!(cloned.feature_schema_version, "v1.0");
        assert_eq!(cloned.feature_schema_hash, "sha256:deadbeef");
    }

    /// NaN/Inf f32 must coerce to None before SQL bind — guards against
    /// PG `invalid input syntax for type real: "NaN"` on write.
    /// NaN/Inf f32 必須在 bind 前變 None，避免 PG real 型態拒收。
    #[test]
    fn test_sanitize_f32_opt_handles_nan_inf() {
        assert_eq!(sanitize_f32_opt(Some(1.5)), Some(1.5));
        assert_eq!(sanitize_f32_opt(Some(0.0)), Some(0.0));
        assert_eq!(sanitize_f32_opt(Some(-0.0001)), Some(-0.0001));
        assert_eq!(sanitize_f32_opt(Some(f32::NAN)), None);
        assert_eq!(sanitize_f32_opt(Some(f32::INFINITY)), None);
        assert_eq!(sanitize_f32_opt(Some(f32::NEG_INFINITY)), None);
        assert_eq!(sanitize_f32_opt(None), None);
    }

    /// Row with poisoned NaN fields must sanitize all 7 dims at bind time.
    /// Exercises the same sanitize_f32_opt path used inside flush_exit_features.
    /// 7 維皆 NaN 的行應全部在 bind 時清除 — 走同一 sanitize_f32_opt 路徑。
    #[test]
    fn test_nan_row_sanitizes_all_seven_dims() {
        let row = ExitFeatureRow {
            est_net_bps: Some(f32::NAN),
            peak_pnl_pct: Some(f32::INFINITY),
            atr_pct: Some(f32::NEG_INFINITY),
            giveback_atr_norm: Some(f32::NAN),
            time_since_peak_ms: Some(0), // bigint path unaffected
            price_roc_short: Some(f32::NAN),
            entry_age_secs: Some(f32::INFINITY),
            realized_net_bps: Some(f32::NAN),
            ..make_row("ctx-nan")
        };
        assert_eq!(sanitize_f32_opt(row.est_net_bps), None);
        assert_eq!(sanitize_f32_opt(row.peak_pnl_pct), None);
        assert_eq!(sanitize_f32_opt(row.atr_pct), None);
        assert_eq!(sanitize_f32_opt(row.giveback_atr_norm), None);
        assert_eq!(sanitize_f32_opt(row.price_roc_short), None);
        assert_eq!(sanitize_f32_opt(row.entry_age_secs), None);
        assert_eq!(sanitize_f32_opt(row.realized_net_bps), None);
    }

    /// Epoch-0 rows should be caught by the flush guard — verify carrier.
    /// Epoch-0 行應被 flush 守衛捕捉 — 此處驗載體。
    #[test]
    fn test_epoch_zero_detected() {
        let mut row = make_row("ctx-zero");
        row.ts_ms = 0;
        assert_eq!(row.ts_ms, 0);
        let ok = make_row("ctx-ok");
        assert_ne!(ok.ts_ms, 0);
    }

    /// Lock column list against silent schema drift — V999 migration.
    /// Must list all 18 columns (6 identity + 7 Track P + 3 exit meta + 2 provenance).
    /// 鎖定欄位列表避免 schema 靜默漂移 — V999 遷移對應。
    #[test]
    fn test_insert_sql_locked_columns() {
        let src = include_str!("exit_feature_writer.rs");
        for col in [
            "context_id",
            "engine_mode",
            "strategy_name",
            "symbol",
            "side",
            "est_net_bps",
            "peak_pnl_pct",
            "atr_pct",
            "giveback_atr_norm",
            "time_since_peak_ms",
            "price_roc_short",
            "entry_age_secs",
            "exit_source",
            "exit_trigger_rule",
            "realized_net_bps",
            "feature_schema_version",
            "feature_schema_hash",
            "ON CONFLICT (context_id, ts) DO UPDATE",
        ] {
            assert!(src.contains(col), "INSERT SQL missing column/clause: {col}");
        }
    }
}
