//! Strategist applied-params persistence — split from `strategist_scheduler/mod.rs`.
//! 策略師已應用參數持久化 — 從 `strategist_scheduler/mod.rs` 拆出。
//!
//! MODULE_NOTE (EN): Extracted from parent `mod.rs` as post-commit FUP to commit
//!   `f1f7403`, which pushed the file from 1133 → 1342 lines and breached the
//!   §九 1200-line hard limit by 142 lines. Contents are moved verbatim (method
//!   `StrategistScheduler::persist_applied_params`, standalone fn
//!   `load_latest_applied_params`, and the two fail-soft regression tests) with
//!   zero behaviour change — see sibling-child-module pattern established by
//!   commits `585be97` / `3d67a99`. Re-exported from `mod.rs` via
//!   `pub use persist::load_latest_applied_params;` so `main.rs` call sites
//!   (`openclaw_engine::strategist_scheduler::load_latest_applied_params`)
//!   remain unchanged.
//! MODULE_NOTE (中): 從父 `mod.rs` 拆出，為 commit `f1f7403` post-commit FUP —
//!   該 commit 把檔案從 1133 推到 1342 行，超 §九 1200 硬上限 142 行。本檔內
//!   容原封搬出（method `StrategistScheduler::persist_applied_params`、
//!   standalone fn `load_latest_applied_params`、2 個 fail-soft regression
//!   tests），零邏輯變動 — 採 commits `585be97` / `3d67a99` 建立的
//!   sibling-child-module pattern。`mod.rs` 透過
//!   `pub use persist::load_latest_applied_params;` re-export，`main.rs`
//!   呼叫路徑 `openclaw_engine::strategist_scheduler::load_latest_applied_params`
//!   不動。

use super::StrategistScheduler;
use serde_json::Value;
use std::sync::Arc;
use tracing::debug;

impl StrategistScheduler {
    /// STRATEGIST-PARAMS-PERSIST-1 (2026-04-23): persist the just-applied
    /// params to `learning.strategist_applied_params` as an audit trail.
    /// Engine startup reads the latest row per (engine_mode, strategy_name)
    /// and re-issues `UpdateStrategyParams` so tuned values survive restart
    /// instead of reverting to TOML baseline.
    ///
    /// Fail-soft: DB pool unavailable → Ok(()) (skip persist, log at caller).
    /// The tuning cycle has already succeeded in-memory — a persist miss only
    /// means the tuned value won't survive restart, which is strictly less bad
    /// than aborting the cycle.
    ///
    /// STRATEGIST-PARAMS-PERSIST-1（2026-04-23）：把剛應用的參數寫入
    /// `learning.strategist_applied_params` 當 audit + restore 來源。
    /// Engine 啟動讀每 (engine_mode, strategy_name) 最新 row 回放 IPC。
    /// Fail-soft：DB 不可用回 Ok(())，不影響已在內存生效的 tuning。
    pub(super) async fn persist_applied_params(
        &self,
        strategy_name: &str,
        prev_params: &Value,
        applied_params: &Value,
        reason: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let pool = match self.db_pool.get() {
            Some(p) => p,
            None => {
                debug!(
                    strategy = %strategy_name,
                    "persist_applied_params skipped: DB pool unavailable \
                     / DB 連接池不可用，跳過持久化"
                );
                return Ok(());
            }
        };

        let engine_mode = self.tune_target.db_mode();
        let applied_at_ms: i64 = chrono::Utc::now().timestamp_millis();

        sqlx::query(
            "INSERT INTO learning.strategist_applied_params \
             (engine_mode, strategy_name, params_json, applied_at_ms, \
              source, reason, prev_params_json) \
             VALUES ($1, $2, $3, $4, $5, $6, $7)",
        )
        .bind(engine_mode)
        .bind(strategy_name)
        .bind(applied_params)
        .bind(applied_at_ms)
        .bind("strategist_scheduler")
        .bind(reason)
        .bind(prev_params)
        .execute(pool)
        .await?;

        debug!(
            strategy = %strategy_name,
            engine_mode = %engine_mode,
            applied_at_ms,
            "strategist params persisted / 策略師參數已持久化"
        );
        Ok(())
    }
}

/// STRATEGIST-PARAMS-PERSIST-1 (2026-04-23): load the latest applied params
/// per (engine_mode, strategy_name) from `learning.strategist_applied_params`.
/// Used by `main.rs` startup to restore tuned params via `UpdateStrategyParams`
/// IPC **before** scheduler spawn — ensures rebuild does not silently revert
/// parameters to TOML baseline (which would reset the
/// STRATEGIST-AUTO-PROMOTE-CRITERIA-1 stability counter forever).
///
/// Fail-soft semantics:
///   - `db_pool.get() == None`   → `Ok(vec![])` (DB disabled; nothing to restore)
///   - SQL error                  → `Err(_)` (caller logs + continues startup)
///   - Empty table                → `Ok(vec![])` (first boot after migration)
///
/// Returns `Vec<(strategy_name, params_json_string)>` — ready to send as
/// `PipelineCommand::UpdateStrategyParams` payload without further parsing.
///
/// STRATEGIST-PARAMS-PERSIST-1（2026-04-23）：從
/// `learning.strategist_applied_params` 讀每 (engine_mode, strategy_name) 最新
/// 1 row，給 `main.rs` 啟動時以 IPC 恢復調諧參數，避免 rebuild 靜默回到 TOML
/// baseline 重置 AUTO-PROMOTE 穩定計數器。
/// Fail-soft：pool=None → 空 Vec；SQL 錯 → Err（caller log+continue）。
pub async fn load_latest_applied_params(
    db_pool: &Arc<crate::database::pool::DbPool>,
    engine_mode: &str,
) -> Result<Vec<(String, String)>, Box<dyn std::error::Error + Send + Sync>> {
    let pool = match db_pool.get() {
        Some(p) => p,
        None => {
            debug!(
                engine_mode,
                "load_latest_applied_params: DB pool unavailable, \
                 returning empty / DB 連接池不可用，回空 Vec"
            );
            return Ok(Vec::new());
        }
    };

    // DISTINCT ON picks the row with the highest applied_at_ms per
    // (engine_mode, strategy_name) — matches the index
    // `idx_strategist_applied_engine_strategy_ts` (ORDER BY applied_at_ms DESC).
    // DISTINCT ON 配合索引取每組最新 1 row。
    let rows: Vec<(String, serde_json::Value)> =
        sqlx::query_as::<_, (String, serde_json::Value)>(
            "SELECT DISTINCT ON (engine_mode, strategy_name) \
                strategy_name, params_json \
             FROM learning.strategist_applied_params \
             WHERE engine_mode = $1 \
             ORDER BY engine_mode, strategy_name, applied_at_ms DESC",
        )
        .bind(engine_mode)
        .fetch_all(pool)
        .await?;

    let out: Vec<(String, String)> = rows
        .into_iter()
        .map(|(name, val)| (name, val.to_string()))
        .collect();
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ai_service_client::AiServiceClient;
    use crate::tick_pipeline::PipelineKind;
    use tokio_util::sync::CancellationToken;

    fn mk_deps() -> (
        Arc<AiServiceClient>,
        Arc<crate::database::pool::DbPool>,
        CancellationToken,
    ) {
        (
            Arc::new(AiServiceClient::new()),
            Arc::new(crate::database::pool::DbPool::disconnected()),
            CancellationToken::new(),
        )
    }

    // ═══════════════════════════════════════════════════════════════════
    // STRATEGIST-PARAMS-PERSIST-1 tests (2026-04-23).
    // Verify fail-soft semantics when DB pool is disconnected:
    //   1. persist_applied_params returns Ok(()) with pool=None
    //   2. load_latest_applied_params returns Ok(vec![]) with pool=None
    // Real PG integration deferred to Linux CI (requires live learning schema).
    // STRATEGIST-PARAMS-PERSIST-1 測試（2026-04-23）。驗 fail-soft：
    //   1. pool=None 時 persist 回 Ok(())，不 raise
    //   2. pool=None 時 load 回 Ok(vec![])
    // 真 PG 整合測試延後 Linux CI（需 live learning schema）。
    // ═══════════════════════════════════════════════════════════════════

    #[tokio::test]
    async fn test_persist_applied_params_fails_soft_on_pool_none() {
        // Simulate "DB disabled" (disconnected DbPool). persist_applied_params
        // must swallow the miss and return Ok(()) — the in-memory tune cycle
        // has already succeeded, failing here would trigger a retry loop that
        // re-IPCs the same applied params and spams warn logs.
        // 模擬 DB 停擺：persist 必須回 Ok(())，不然會觸發 retry 噴 log。
        let (ai, pool, cancel) = mk_deps();
        let (tune_tx, _tune_rx) = tokio::sync::mpsc::unbounded_channel();
        let sched = StrategistScheduler::new(
            ai,
            tune_tx,
            PipelineKind::Demo,
            None,
            pool,
            cancel,
        );

        let prev = serde_json::json!({"cooldown_ms": 50000.0});
        let applied = serde_json::json!({"cooldown_ms": 55000.0});
        let result = sched
            .persist_applied_params("ma_crossover", &prev, &applied, "top_deviation_pair")
            .await;
        assert!(
            result.is_ok(),
            "persist_applied_params must fail-soft when db_pool is disconnected, \
             got: {:?}",
            result.err()
        );
    }

    #[tokio::test]
    async fn test_load_latest_applied_params_empty_on_pool_none() {
        // Symmetric fail-soft on the read path: startup restore must not abort
        // engine boot when DB is disabled. Return empty vec → main.rs sees
        // "nothing to restore" and continues normally.
        // 讀路徑對稱 fail-soft：DB 停擺時返回空 Vec，engine 啟動不受阻。
        let pool = Arc::new(crate::database::pool::DbPool::disconnected());
        let result = load_latest_applied_params(&pool, "demo").await;
        assert!(
            result.is_ok(),
            "load_latest_applied_params must fail-soft when db_pool is disconnected, \
             got: {:?}",
            result.err()
        );
        let rows = result.unwrap();
        assert!(
            rows.is_empty(),
            "expected empty vec from disconnected pool, got {} rows",
            rows.len()
        );
    }
}
