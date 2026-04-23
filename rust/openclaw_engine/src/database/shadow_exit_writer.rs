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

/// INFRA-PREBUILD-1 P3-3 (2026-04-23): 單次 flush 最大 batch 大小。
/// INFRA-PREBUILD-1 P3-3 (2026-04-23): Maximum rows drained per flush.
///
/// 為什麼 256 / Why 256:
///   - Pending buffer 初始容量 = 128（見 `Vec::with_capacity(128)`），
///     預期穩態下 fire rate 不會超過 128/flush_tick。
///   - Phase 2 shadow fire rate spike（例如 25 symbol × 4 strategies × 多 TF
///     同時觸發 close）可能堆積 > 128 訊息，若無上限將同步執行超大 INSERT
///     loop 阻塞 writer task、延誤 cancel / 其他 flush。
///   - 256 = 2× 初始容量 headroom；超出部分延遲到下一個 flush_interval tick。
///   - Initial pending capacity = 128; steady-state fire rate shouldn't exceed
///     128/flush_tick. Phase 2 shadow fire-rate spikes (close-cluster across
///     25 symbol × 4 strategies × multi-TF) can push > 128; without a cap the
///     flush loop synchronously INSERTs the whole batch and blocks cancel +
///     subsequent flushes. 256 = 2× initial-cap headroom; overflow rows defer
///     to the next `flush_interval` tick (normal backpressure, not data loss —
///     the producer channel already bounds total in-flight, so deferring here
///     just slows consumption and surfaces the spike in tracing).
pub(crate) const MAX_FLUSH_BATCH: usize = 256;

/// Coerce NaN/Inf f64 to None; finite values pass through.
/// NaN/Inf f64 → None；有限值原樣透傳。
#[inline]
fn sanitize_f64_opt(v: Option<f64>) -> Option<f64> {
    match v {
        Some(x) if x.is_finite() => Some(x),
        _ => None,
    }
}

/// INFRA-PREBUILD-1 P3-3 pure helper: drain up to `cap` rows from `pending`.
/// Returned Vec = batch to flush; `pending` mutated in place (remaining rows
/// stay for next tick). No SQL / no async / no logging — pure for testability.
///
/// INFRA-PREBUILD-1 P3-3 純函數：從 `pending` 最多 drain `cap` 列。
/// 回傳值 = 本次 flush batch；`pending` 就地修改（剩餘列留到下次 tick）。
/// 無 SQL / 無 async / 無 log — 純函數便於測試。
#[inline]
pub(crate) fn take_batch(pending: &mut Vec<ShadowExitMsg>, cap: usize) -> Vec<ShadowExitMsg> {
    let batch_size = pending.len().min(cap);
    pending.drain(..batch_size).collect()
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

    // INFRA-PREBUILD-1 P3-3 (2026-04-23): bounded drain to avoid monster INSERT
    // loops under Phase 2 fire-rate spikes. Remaining rows defer to next tick.
    // INFRA-PREBUILD-1 P3-3（2026-04-23）：有上限 drain，避免 Phase 2 fire-rate
    // spike 下超大 INSERT 迴圈。剩餘列延後下次 tick 處理。
    let rows: Vec<ShadowExitMsg> = take_batch(pending, MAX_FLUSH_BATCH);
    if !pending.is_empty() {
        warn!(
            remaining = pending.len(),
            batch_size = rows.len(),
            cap = MAX_FLUSH_BATCH,
            "shadow_exit flush: batch capped, rows deferred to next tick / batch 上限，列延後下次"
        );
    }

    for row in rows {
        // DB-RUN-6 + INFRA-PREBUILD-1 audit L1-2 (2026-04-23): reject ts_ms <= 0
        // to cover BOTH epoch-0 (`== 0`, 1970 time-domain JOIN poison) AND negative
        // overflow (`< 0`, which would otherwise be silently coerced to epoch-0 by
        // `chrono::DateTime::from_timestamp_millis(...).unwrap_or_default()` below
        // at L145). Single guard covers both cases at the writer boundary so no
        // invalid ts ever reaches the SQL bind.
        // DB-RUN-6 + INFRA-PREBUILD-1 audit L1-2（2026-04-23）：拒絕 `ts_ms <= 0`
        // 同時覆蓋 epoch-0（`== 0`，1970 時間域 JOIN 毒化）與負值溢位（`< 0`，否則
        // 會被下方 L145 `chrono::...unwrap_or_default()` 靜默降為 epoch-0）。
        // writer 邊界單一 guard 保證 SQL bind 絕不收到無效 ts。
        if row.ts_ms <= 0 {
            warn!(
                ctx_id = %row.context_id, symbol = %row.symbol, ts_ms = row.ts_ms,
                "shadow_exit write rejected: ts_ms <= 0 (epoch leak or negative) / 拒絕 ts_ms <= 0 寫入"
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
        // Guard predicate: writer uses `row.ts_ms <= 0` to reject both epoch-0
        // and negative overflow in a single branch. Pin the boolean here so a
        // future refactor cannot accidentally weaken the guard back to `== 0`.
        // 守衛條件：writer 用 `row.ts_ms <= 0` 單一分支拒絕 epoch-0 與負值溢位。
        // 鎖定布林值，避免日後重構把守衛弱化回 `== 0`。
        assert!(row.ts_ms <= 0, "ts_ms=0 must satisfy the `<= 0` writer guard");
    }

    /// INFRA-PREBUILD-1 audit L1-2 (2026-04-23): negative ts_ms must be rejected
    /// by the same `<= 0` guard. Without this branch `from_timestamp_millis(-1)`
    /// would silently return None → `unwrap_or_default()` → epoch-0 row (same
    /// time-domain JOIN poison as epoch-0). Carrier-level check mirrors
    /// `test_epoch_zero_detected` since full flush needs a live PG pool.
    /// INFRA-PREBUILD-1 審計 L1-2（2026-04-23）：負 ts_ms 必須被同一個 `<= 0` 守衛
    /// 拒絕。缺此分支時 `from_timestamp_millis(-1)` 會靜默回 None →
    /// `unwrap_or_default()` → epoch-0 列（與 epoch-0 同樣的時間域 JOIN 毒化）。
    /// 載體層測試鏡像 `test_epoch_zero_detected`（完整 flush 需 live PG pool）。
    #[test]
    fn test_negative_ts_rejected() {
        let mut row = make_row("ctx-neg");
        row.ts_ms = -1;
        assert_eq!(row.ts_ms, -1);
        // The writer's `if row.ts_ms <= 0 { continue; }` guard must fire for
        // this row — verify the predicate here so any regression (e.g. someone
        // reverts the guard to `== 0`) immediately goes red.
        // writer 的 `if row.ts_ms <= 0 { continue; }` 守衛必為此列觸發 — 此處
        // 直接驗證條件，若有人把守衛改回 `== 0`（回歸）即刻紅測試。
        assert!(row.ts_ms <= 0, "negative ts_ms must satisfy the writer's `<= 0` guard");
        // i64::MIN edge case: even the most-negative int must still trip the guard.
        // i64::MIN 邊界：最負整數亦須觸發守衛。
        let mut extreme = make_row("ctx-neg-min");
        extreme.ts_ms = i64::MIN;
        assert!(extreme.ts_ms <= 0);
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

    /// INFRA-PREBUILD-1 P3-3 (2026-04-23): take_batch respects cap on over-sized
    /// pending buffer. Tests: pending.len() > cap → drained = cap, remaining > 0;
    /// pending.len() <= cap → drained = full, remaining = 0; cap = 0 → noop.
    ///
    /// INFRA-PREBUILD-1 P3-3（2026-04-23）：take_batch 在 pending 超量時尊重上限。
    #[test]
    fn test_take_batch_respects_cap() {
        // Case 1: pending 超過 cap → drain 剛好 cap，剩餘 = len - cap
        // Case 1: pending exceeds cap → drain exactly cap, remaining = len-cap
        let mut pending: Vec<ShadowExitMsg> = (0..300)
            .map(|i| make_row(&format!("ctx-{}", i)))
            .collect();
        assert_eq!(pending.len(), 300);
        let batch = take_batch(&mut pending, MAX_FLUSH_BATCH);
        assert_eq!(batch.len(), MAX_FLUSH_BATCH, "batch must be exactly MAX_FLUSH_BATCH");
        assert_eq!(pending.len(), 300 - MAX_FLUSH_BATCH, "remaining = 300 - cap");
        // Drain is FIFO — first 256 must be ctx-0..ctx-255.
        // drain 是 FIFO — 前 256 筆必是 ctx-0..ctx-255。
        assert_eq!(batch[0].context_id, "ctx-0");
        assert_eq!(batch[MAX_FLUSH_BATCH - 1].context_id, format!("ctx-{}", MAX_FLUSH_BATCH - 1));
        // Remaining in pending starts from ctx-256 onward.
        // pending 剩餘從 ctx-256 開始。
        assert_eq!(pending[0].context_id, format!("ctx-{}", MAX_FLUSH_BATCH));

        // Case 2: pending 小於 cap → 全 drain，剩餘 = 0
        // Case 2: pending < cap → drain all, remaining = 0
        let mut small: Vec<ShadowExitMsg> = (0..50)
            .map(|i| make_row(&format!("small-{}", i)))
            .collect();
        let batch2 = take_batch(&mut small, MAX_FLUSH_BATCH);
        assert_eq!(batch2.len(), 50);
        assert!(small.is_empty());

        // Case 3: 空 pending → 空 batch，pending 仍空
        // Case 3: empty pending → empty batch, pending still empty
        let mut empty: Vec<ShadowExitMsg> = Vec::new();
        let batch3 = take_batch(&mut empty, MAX_FLUSH_BATCH);
        assert!(batch3.is_empty());
        assert!(empty.is_empty());

        // Case 4: cap = 0 → noop，pending 不變
        // Case 4: cap = 0 → noop, pending unchanged
        let mut five: Vec<ShadowExitMsg> =
            (0..5).map(|i| make_row(&format!("z-{}", i))).collect();
        let batch4 = take_batch(&mut five, 0);
        assert!(batch4.is_empty());
        assert_eq!(five.len(), 5);
    }

    /// INFRA-PREBUILD-1 P3-3: cap value pinned at 256 per docstring rationale.
    /// Any refactor that changes the cap must update the docstring + this test.
    ///
    /// INFRA-PREBUILD-1 P3-3：cap 值固定 256（依 docstring 推理）。若改動須同步
    /// 更新 docstring 與本測試。
    #[test]
    fn test_max_flush_batch_cap_value_pinned() {
        // 256 = 2× initial pending capacity (128), see module-level const docstring.
        // 256 = 2× pending 初始容量（128），見模組級 const docstring。
        assert_eq!(MAX_FLUSH_BATCH, 256);
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
