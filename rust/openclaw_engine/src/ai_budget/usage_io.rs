//! AI usage log DB I/O — write `learning.ai_usage_log`, query month-to-date totals.
//! AI 用量日誌 DB I/O — 寫入 `learning.ai_usage_log`，查詢月內累計。
//!
//! MODULE_NOTE (EN): Per-call insert + monthly aggregation. The MTD aggregation
//!   uses `date_trunc('month', NOW())` so it auto-resets at month boundary.
//!   All writes are fail-closed: errors propagate to the caller (BudgetTracker).
//! MODULE_NOTE (中): 每次調用一條 insert + 月度聚合。MTD 聚合使用
//!   `date_trunc('month', NOW())`，月初自動重置。所有寫入 fail-closed：錯誤
//!   傳遞給 caller（BudgetTracker）。

use crate::database::pool::DbPool;
use std::collections::HashMap;
use tracing::debug;

/// Insert one usage row. Returns Err on any DB failure (fail-closed contract).
/// 插入一條用量列。任何 DB 失敗時返回 Err（fail-closed 合約）。
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
) -> Result<(), String> {
    let pg = pool
        .get()
        .ok_or_else(|| "usage_io::insert_usage: pool not available".to_string())?;
    sqlx::query(
        "INSERT INTO learning.ai_usage_log
            (time, scope, provider, model, tokens_in, tokens_out, cost_usd, purpose, request_id)
         VALUES (NOW(), $1, $2, $3, $4, $5, $6, $7, $8)",
    )
    .bind(scope)
    .bind(provider)
    .bind(model)
    .bind(tokens_in)
    .bind(tokens_out)
    .bind(cost_usd as f32)
    .bind(purpose)
    .bind(request_id)
    .execute(pg)
    .await
    .map_err(|e| format!("ai_usage_log insert failed: {e}"))?;
    debug!(
        scope, provider, model, tokens_in, tokens_out, cost_usd, "ai_usage_log row inserted"
    );
    Ok(())
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
