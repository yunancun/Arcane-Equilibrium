//! AI usage log DB I/O — write `learning.ai_usage_log`, query month-to-date totals.
//! AI 用量日誌 DB I/O — 寫入 `learning.ai_usage_log`，查詢月內累計。
//!
//! MODULE_NOTE (EN): Per-call insert + monthly aggregation. The MTD aggregation
//!   uses `date_trunc('month', NOW())` so it auto-resets at month boundary.
//!   All writes are fail-closed: errors propagate to the caller (BudgetTracker).
//!
//!   E5-FN-2 (audit §七 7.2): `insert_usage` uses `ON CONFLICT (request_id)
//!   WHERE request_id <> '' DO NOTHING` against the V018 partial UNIQUE index.
//!   The return value is `Ok(true)` when a new row was inserted and `Ok(false)`
//!   when a duplicate request_id caused the INSERT to no-op. Callers MUST skip
//!   their in-memory cost accumulator on `Ok(false)` to avoid double-billing.
//!
//! MODULE_NOTE (中): 每次調用一條 insert + 月度聚合。MTD 聚合使用
//!   `date_trunc('month', NOW())`，月初自動重置。所有寫入 fail-closed：錯誤
//!   傳遞給 caller（BudgetTracker）。
//!
//!   E5-FN-2（audit §七 7.2）：`insert_usage` 對應 V018 的 request_id 部分
//!   UNIQUE 索引加 ON CONFLICT DO NOTHING。回傳 `Ok(true)` 表示有新行寫入，
//!   `Ok(false)` 表示 request_id 重複（idempotent 去重）。caller 在
//!   `Ok(false)` 時必須跳過 in-memory cost 累加以避免雙計。

use crate::database::pool::DbPool;
use std::collections::HashMap;
use tracing::{debug, warn};

/// Insert one usage row (idempotent on request_id, V018).
/// 插入一條用量列（以 request_id 為冪等鍵，V018）。
///
/// Returns `Ok(true)` when a new row was persisted and `Ok(false)` when the
/// INSERT was deduped by the partial UNIQUE index on `request_id`. Any DB
/// failure other than the benign conflict propagates as Err (fail-closed
/// contract preserved).
///
/// `Ok(true)` 表示成功寫入新行；`Ok(false)` 表示 request_id 與既有行重複而
/// 被索引去重（idempotent）。除此之外的 DB 失敗全部回 Err（fail-closed）。
///
/// Callers supplying `request_id = ""` still get the pre-V018 behaviour
/// (always INSERT, no dedup) because the V018 index is partial on
/// `request_id <> ''`. This keeps legacy code paths compatible.
/// 若 caller 傳入 `request_id = ""`，行為與 V018 前一致（每次都 INSERT 不
/// 去重），因 V018 的索引為 `WHERE request_id <> ''`；保留舊路徑相容。
#[allow(clippy::too_many_arguments)]
pub async fn insert_usage(
    pool: &DbPool,
    scope: &str,
    provider: &str,
    model: &str,
    tokens_in: i32,
    tokens_out: i32,
    cost_usd: f64,
    purpose: &str,
    request_id: &str,
) -> Result<bool, String> {
    let pg = pool
        .get()
        .ok_or_else(|| "usage_io::insert_usage: pool not available".to_string())?;

    // `ON CONFLICT (request_id) WHERE request_id <> '' DO NOTHING` targets the
    // V018 partial UNIQUE index `uq_ai_usage_log_request_id`. `RETURNING 1`
    // yields zero rows on a dedup, letting us distinguish first-insert from
    // duplicate-skip without a separate round-trip.
    //
    // ON CONFLICT 語句配合 V018 的部分 UNIQUE 索引；RETURNING 在去重時返回
    // 零列，讓我們無需額外查詢即可區分「首次寫入」與「重複略過」。
    let inserted: Option<(i32,)> = sqlx::query_as::<_, (i32,)>(
        "INSERT INTO learning.ai_usage_log
            (time, scope, provider, model, tokens_in, tokens_out, cost_usd, purpose, request_id)
         VALUES (NOW(), $1, $2, $3, $4, $5, $6, $7, $8)
         ON CONFLICT (request_id) WHERE request_id <> ''
         DO NOTHING
         RETURNING 1",
    )
    .bind(scope)
    .bind(provider)
    .bind(model)
    .bind(tokens_in)
    .bind(tokens_out)
    .bind(cost_usd as f32)
    .bind(purpose)
    .bind(request_id)
    .fetch_optional(pg)
    .await
    .map_err(|e| format!("ai_usage_log insert failed: {e}"))?;

    let row_inserted = inserted.is_some();
    if row_inserted {
        debug!(
            scope,
            provider, model, tokens_in, tokens_out, cost_usd, "ai_usage_log row inserted"
        );
    } else {
        // Duplicate request_id — this is the E5-FN-2 dedup guard firing.
        // Log at WARN so operator can spot retry storms, but do NOT propagate
        // an error (idempotent contract).
        // 重複 request_id — E5-FN-2 去重守衛觸發。以 WARN 記錄供 operator 排查
        // 重試風暴，但不回 Err（冪等合約）。
        warn!(
            scope,
            provider,
            model,
            request_id,
            cost_usd,
            "ai_usage_log duplicate request_id — INSERT deduped (E5-FN-2) / request_id 重複已去重"
        );
    }
    Ok(row_inserted)
}

/// Sum cost_usd by scope for the current calendar month.
/// 按 scope 加總當月已用 cost_usd。
///
/// Returns a map (scope → MTD USD). Scopes with zero usage may be absent;
/// callers must default-to-zero on miss.
/// 返回 map（scope → 月內美元）。無用量的 scope 可能不存在；caller 應視為 0。
pub async fn load_mtd_usage(pool: &DbPool) -> Result<HashMap<String, f64>, String> {
    let pg = pool
        .get()
        .ok_or_else(|| "usage_io::load_mtd_usage: pool not available".to_string())?;
    let rows: Vec<(String, Option<f64>)> = sqlx::query_as::<_, (String, Option<f64>)>(
        "SELECT scope, COALESCE(SUM(cost_usd)::float8, 0.0) AS mtd
           FROM learning.ai_usage_log
          WHERE time >= date_trunc('month', NOW())
          GROUP BY scope",
    )
    .fetch_all(pg)
    .await
    .map_err(|e| format!("ai_usage_log mtd select failed: {e}"))?;
    let mut out = HashMap::new();
    for (scope, mtd) in rows {
        out.insert(scope, mtd.unwrap_or(0.0));
    }
    Ok(out)
}
