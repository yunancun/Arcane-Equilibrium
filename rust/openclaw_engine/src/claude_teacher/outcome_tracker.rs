// MODULE_NOTE
// EN: OutcomeTracker — periodic sweep that computes the realized PnL impact of
//     applied Teacher directives and writes outcome columns to
//     `learning.directive_executions` (V012 schema).
//
//     For each row where outcome_computed_at IS NULL and ts is at least 1h ago:
//     1. Compute realized PnL in 1h / 4h / 24h / 7d windows from trading.fills,
//        filtered by `strategy_scope`.
//     2. Compute 24h Sharpe (mean / std * sqrt(24)) over hourly bucket returns.
//     3. UPSERT the outcome columns + outcome_computed_at = NOW().
//
//     fail-soft: any DB error -> log warn + return Err to caller. Caller (W3
//     wiring sweep / main.rs) decides whether to retry or skip the row.
//
// 中文: OutcomeTracker — 定期掃描，計算已套用 Teacher directive 的實現 PnL 影響，
//       並把 outcome 欄位寫回 `learning.directive_executions`（V012 schema）。
//
//       對每個 outcome_computed_at IS NULL 且 ts 至少 1 小時前的 row：
//       1. 從 trading.fills 計算 1h/4h/24h/7d 視窗的實現 PnL（用 strategy_scope 過濾）
//       2. 計算 24h Sharpe（每小時報酬的 mean/std*sqrt(24)）
//       3. UPSERT outcome 欄位 + outcome_computed_at = NOW()
//
//       fail-soft：任何 DB 錯誤 → log warn + 回 Err。caller（W3 wiring sweep /
//       main.rs）決定 retry 或 skip。

use crate::database::pool::DbPool;
use std::sync::Arc;
use tracing::{debug, warn};

/// EN: A pending directive execution row that needs outcome computation.
/// 中文: 一個待計算 outcome 的 directive execution row。
#[derive(Debug, Clone)]
pub struct PendingExecution {
    pub execution_id: i64,
    pub executed_at_ms: i64,
    pub strategy_scope: Option<String>,
}

/// EN: Computed outcome for the four PnL windows + 24h Sharpe.
///     Any field may be `None` (no fills in window OR insufficient samples for Sharpe).
/// 中文: 四個 PnL 視窗 + 24h Sharpe 的計算結果。
///       任一欄位可為 `None`（視窗內無 fill 或樣本不足以算 Sharpe）。
#[derive(Debug, Clone, Default, PartialEq)]
pub struct OutcomeWindow {
    pub pnl_1h: Option<f64>,
    pub pnl_4h: Option<f64>,
    pub pnl_24h: Option<f64>,
    pub pnl_7d: Option<f64>,
    pub sharpe_24h: Option<f64>,
}

impl OutcomeWindow {
    /// EN: Returns true if every field is `None` (no fills + no Sharpe samples).
    /// 中文: 全部欄位皆 None 時返回 true（無 fill + 無 Sharpe 樣本）。
    pub fn is_empty(&self) -> bool {
        self.pnl_1h.is_none()
            && self.pnl_4h.is_none()
            && self.pnl_24h.is_none()
            && self.pnl_7d.is_none()
            && self.sharpe_24h.is_none()
    }
}

/// EN: Tracker for Teacher directive outcomes. Owns an Arc<DbPool>.
/// 中文: Teacher directive outcome 追蹤器。持有 Arc<DbPool>。
pub struct OutcomeTracker {
    pool: Arc<DbPool>,
    /// EN: Minimum age (ms) before a directive is eligible for outcome computation.
    ///     Default 1h: too soon to compute outcomes immediately after the directive.
    /// 中文: directive 可被計算 outcome 的最小年齡（毫秒）。預設 1 小時：
    ///       directive 套用後立即計算為時太早。
    min_age_ms: i64,
    /// EN: Minimum hourly buckets needed to compute Sharpe. Default 6 (out of 24).
    /// 中文: 計算 Sharpe 所需最少小時 bucket。預設 6（共 24）。
    sharpe_min_buckets: usize,
}

impl OutcomeTracker {
    /// EN: Construct with default thresholds (1h min age, 6 buckets for Sharpe).
    /// 中文: 用預設閾值構造（1 小時最小年齡，6 個 bucket 算 Sharpe）。
    pub fn new(pool: Arc<DbPool>) -> Self {
        Self {
            pool,
            min_age_ms: 3_600_000, // 1 hour
            sharpe_min_buckets: 6,
        }
    }

    /// EN: Test-only constructor with overridable thresholds.
    /// 中文: 測試專用，可覆寫閾值。
    #[cfg(test)]
    pub fn new_for_test(pool: Arc<DbPool>, min_age_ms: i64, sharpe_min_buckets: usize) -> Self {
        Self {
            pool,
            min_age_ms,
            sharpe_min_buckets,
        }
    }

    /// EN: Find pending directive_executions and compute outcomes.
    ///     Returns the number of rows processed.
    ///     Skips rows whose age is less than `min_age_ms` (too soon).
    ///     Skips rows with NULL strategy_scope (cannot filter fills).
    /// 中文: 找出待處理 directive_executions 並計算 outcome。
    ///       返回處理的 row 數。跳過年齡小於 min_age_ms 的（太早）。
    ///       跳過 strategy_scope 為 NULL 的（無法過濾 fills）。
    pub async fn process_pending(&self) -> Result<usize, String> {
        let pool = match self.pool.get() {
            Some(p) => p,
            None => {
                debug!("outcome_tracker: pool unavailable, skipping sweep / pool 不可用，跳過 sweep");
                return Ok(0);
            }
        };

        // Pull pending rows whose ts is at least min_age_ms in the past.
        // 拉取 ts 至少 min_age_ms 前的待處理 row。
        let min_age_seconds = self.min_age_ms / 1000;
        let rows: Vec<(i64, chrono::DateTime<chrono::Utc>, Option<String>)> =
            sqlx::query_as(
                "SELECT execution_id::bigint, ts, strategy_scope \
                 FROM learning.directive_executions \
                 WHERE outcome_computed_at IS NULL \
                   AND ts < NOW() - make_interval(secs => $1::bigint) \
                 ORDER BY ts ASC \
                 LIMIT 100",
            )
            .bind(min_age_seconds)
            .fetch_all(pool)
            .await
            .map_err(|e| format!("outcome_tracker: select pending failed: {e}"))?;

        let mut processed = 0_usize;
        for (execution_id, ts, scope_opt) in rows {
            let executed_at_ms = ts.timestamp_millis();
            let outcome = match &scope_opt {
                Some(scope) => self
                    .compute_outcome(executed_at_ms, scope)
                    .await
                    .unwrap_or_default(),
                None => OutcomeWindow::default(),
            };
            if let Err(e) = self.upsert_outcome(execution_id, &outcome).await {
                warn!(execution_id, error = %e, "outcome_tracker: upsert failed / 寫回失敗");
                continue;
            }
            processed += 1;
        }
        Ok(processed)
    }

    /// EN: Compute realized PnL across the four windows + 24h Sharpe for the
    ///     given strategy_scope, starting at executed_at_ms.
    /// 中文: 從 executed_at_ms 起計算指定 strategy_scope 的四個視窗實現 PnL + 24h Sharpe。
    pub async fn compute_outcome(
        &self,
        executed_at_ms: i64,
        strategy_scope: &str,
    ) -> Result<OutcomeWindow, String> {
        let pool = match self.pool.get() {
            Some(p) => p,
            None => return Ok(OutcomeWindow::default()),
        };

        let pnl_1h = self
            .sum_realized_pnl(pool, strategy_scope, executed_at_ms, 3_600_000)
            .await?;
        let pnl_4h = self
            .sum_realized_pnl(pool, strategy_scope, executed_at_ms, 14_400_000)
            .await?;
        let pnl_24h = self
            .sum_realized_pnl(pool, strategy_scope, executed_at_ms, 86_400_000)
            .await?;
        let pnl_7d = self
            .sum_realized_pnl(pool, strategy_scope, executed_at_ms, 604_800_000)
            .await?;
        let sharpe_24h = self
            .compute_sharpe_24h(pool, strategy_scope, executed_at_ms)
            .await?;

        Ok(OutcomeWindow {
            pnl_1h,
            pnl_4h,
            pnl_24h,
            pnl_7d,
            sharpe_24h,
        })
    }

    /// EN: Sum `realized_pnl` from trading.fills in [executed_at, executed_at + window_ms].
    ///     Returns None if zero fills found in the window.
    /// 中文: 從 trading.fills 計算 [executed_at, executed_at + window_ms] 內 realized_pnl 總和。
    ///       窗口內無 fill 時返回 None。
    async fn sum_realized_pnl(
        &self,
        pool: &sqlx::PgPool,
        strategy_scope: &str,
        executed_at_ms: i64,
        window_ms: i64,
    ) -> Result<Option<f64>, String> {
        let start_secs = executed_at_ms / 1000;
        let end_secs = (executed_at_ms + window_ms) / 1000;
        let row: Option<(Option<f64>, i64)> = sqlx::query_as(
            "SELECT SUM(realized_pnl)::float8, COUNT(*)::bigint \
             FROM trading.fills \
             WHERE strategy = $1 \
               AND fill_time >= to_timestamp($2::bigint) \
               AND fill_time <  to_timestamp($3::bigint)",
        )
        .bind(strategy_scope)
        .bind(start_secs)
        .bind(end_secs)
        .fetch_optional(pool)
        .await
        .map_err(|e| format!("outcome_tracker: sum_realized_pnl failed: {e}"))?;

        match row {
            Some((sum, count)) if count > 0 => Ok(sum),
            _ => Ok(None),
        }
    }

    /// EN: Compute 24h hourly-Sharpe = mean / std * sqrt(24) over per-hour SUM(realized_pnl).
    ///     Returns None if fewer than `sharpe_min_buckets` non-zero hourly buckets,
    ///     or if std == 0.
    /// 中文: 計算 24h 的 hourly Sharpe = 每小時 SUM(realized_pnl) 的 mean / std * sqrt(24)。
    ///       非零 bucket 少於 sharpe_min_buckets 或 std == 0 時返回 None。
    async fn compute_sharpe_24h(
        &self,
        pool: &sqlx::PgPool,
        strategy_scope: &str,
        executed_at_ms: i64,
    ) -> Result<Option<f64>, String> {
        let start_secs = executed_at_ms / 1000;
        let end_secs = (executed_at_ms + 86_400_000) / 1000;
        let buckets: Vec<(Option<f64>,)> = sqlx::query_as(
            "SELECT SUM(realized_pnl)::float8 \
             FROM trading.fills \
             WHERE strategy = $1 \
               AND fill_time >= to_timestamp($2::bigint) \
               AND fill_time <  to_timestamp($3::bigint) \
             GROUP BY date_trunc('hour', fill_time) \
             ORDER BY date_trunc('hour', fill_time)",
        )
        .bind(strategy_scope)
        .bind(start_secs)
        .bind(end_secs)
        .fetch_all(pool)
        .await
        .map_err(|e| format!("outcome_tracker: hourly buckets failed: {e}"))?;

        let returns: Vec<f64> = buckets.into_iter().filter_map(|(v,)| v).collect();
        Ok(sharpe_from_returns(&returns, self.sharpe_min_buckets))
    }

    /// EN: Persist outcome to learning.directive_executions and stamp outcome_computed_at.
    /// 中文: 寫回 learning.directive_executions 並 stamp outcome_computed_at。
    pub async fn upsert_outcome(
        &self,
        execution_id: i64,
        outcome: &OutcomeWindow,
    ) -> Result<(), String> {
        let pool = match self.pool.get() {
            Some(p) => p,
            None => return Ok(()),
        };
        sqlx::query(
            "UPDATE learning.directive_executions \
             SET outcome_pnl_1h = $1, \
                 outcome_pnl_4h = $2, \
                 outcome_pnl_24h = $3, \
                 outcome_pnl_7d = $4, \
                 outcome_sharpe_24h = $5, \
                 outcome_computed_at = NOW() \
             WHERE execution_id = $6",
        )
        .bind(outcome.pnl_1h.map(|v| v as f32))
        .bind(outcome.pnl_4h.map(|v| v as f32))
        .bind(outcome.pnl_24h.map(|v| v as f32))
        .bind(outcome.pnl_7d.map(|v| v as f32))
        .bind(outcome.sharpe_24h.map(|v| v as f32))
        .bind(execution_id)
        .execute(pool)
        .await
        .map_err(|e| format!("outcome_tracker: upsert failed: {e}"))?;
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Pure helper / 純函數 — extracted for unit testing without a live PG.
// ---------------------------------------------------------------------------

/// EN: Compute hourly-Sharpe = mean / std * sqrt(24) for a vector of hourly returns.
///     Returns None if `returns.len() < min_buckets` or sample std is zero.
/// 中文: 對小時報酬向量計算 hourly-Sharpe。樣本數少於 min_buckets 或樣本 std 為 0 時回 None。
pub fn sharpe_from_returns(returns: &[f64], min_buckets: usize) -> Option<f64> {
    if returns.len() < min_buckets {
        return None;
    }
    let n = returns.len() as f64;
    let mean = returns.iter().sum::<f64>() / n;
    let var = returns.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / n;
    let std = var.sqrt();
    if std <= f64::EPSILON {
        return None;
    }
    Some(mean / std * (24f64).sqrt())
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::database::DatabaseConfig;

    async fn empty_pool() -> Arc<DbPool> {
        Arc::new(DbPool::connect(&DatabaseConfig::default()).await)
    }

    /// EN: With no PG pool, process_pending returns 0 (no error).
    /// 中文: 無 PG pool 時 process_pending 返回 0（不報錯）。
    #[tokio::test]
    async fn test_process_pending_no_pool_returns_zero() {
        let pool = empty_pool().await;
        let tracker = OutcomeTracker::new(pool);
        let n = tracker.process_pending().await.unwrap();
        assert_eq!(n, 0);
    }

    /// EN: With no PG pool, compute_outcome returns the default (all None).
    /// 中文: 無 PG pool 時 compute_outcome 返回預設（全 None）。
    #[tokio::test]
    async fn test_compute_outcome_no_pool_returns_default() {
        let pool = empty_pool().await;
        let tracker = OutcomeTracker::new(pool);
        let outcome = tracker.compute_outcome(1_000, "ma_crossover").await.unwrap();
        assert!(outcome.is_empty());
    }

    /// EN: sharpe_from_returns: zero-length input → None.
    /// 中文: 空輸入 → None。
    #[test]
    fn test_sharpe_from_returns_empty_returns_none() {
        assert!(sharpe_from_returns(&[], 6).is_none());
    }

    /// EN: sharpe_from_returns: below min_buckets → None.
    /// 中文: 不足 min_buckets → None。
    #[test]
    fn test_sharpe_from_returns_below_min_buckets_returns_none() {
        let r = vec![0.1, 0.2, 0.3];
        assert!(sharpe_from_returns(&r, 6).is_none());
    }

    /// EN: sharpe_from_returns: zero std (constant returns) → None (avoid div-by-zero).
    /// 中文: std=0（常數報酬）→ None（避免除以零）。
    #[test]
    fn test_sharpe_from_returns_zero_std_returns_none() {
        let r = vec![0.5; 8];
        assert!(sharpe_from_returns(&r, 6).is_none());
    }

    /// EN: sharpe_from_returns: known small case sanity check.
    /// 中文: 已知小案例 sanity check。
    #[test]
    fn test_sharpe_from_returns_positive_drift_positive_sharpe() {
        // Slightly positive drift with low variance → positive Sharpe.
        // 略正漂移加低變異 → 正 Sharpe。
        let r = vec![0.1, 0.15, 0.05, 0.12, 0.08, 0.11, 0.13, 0.09];
        let s = sharpe_from_returns(&r, 6).expect("should compute");
        assert!(s > 0.0);
    }

    /// EN: sharpe_from_returns: symmetric returns → near-zero mean → near-zero Sharpe.
    /// 中文: 對稱報酬 → mean 近 0 → Sharpe 近 0。
    #[test]
    fn test_sharpe_from_returns_zero_drift_near_zero_sharpe() {
        let r = vec![1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0];
        let s = sharpe_from_returns(&r, 6).expect("should compute");
        assert!(s.abs() < 1e-9);
    }

    /// EN: OutcomeWindow::is_empty true for default.
    /// 中文: 預設 OutcomeWindow::is_empty 為 true。
    #[test]
    fn test_outcome_window_default_is_empty() {
        let w = OutcomeWindow::default();
        assert!(w.is_empty());
    }

    /// EN: OutcomeWindow::is_empty false when any field is Some.
    /// 中文: 任一欄位有值時 is_empty 為 false。
    #[test]
    fn test_outcome_window_with_pnl_not_empty() {
        let w = OutcomeWindow {
            pnl_1h: Some(1.5),
            ..Default::default()
        };
        assert!(!w.is_empty());
    }
}
