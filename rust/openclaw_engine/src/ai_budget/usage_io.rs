//! AI usage log DB I/O — write `learning.ai_usage_log`, query month-to-date totals.
//! AI 用量日誌 DB I/O — 寫入 `learning.ai_usage_log`，查詢月內累計。
//!
//! MODULE_NOTE (EN): Per-call insert + monthly aggregation. The MTD aggregation
//!   uses `date_trunc('month', NOW())` so it auto-resets at month boundary.
//!   Inserts are idempotent via `ON CONFLICT (time, scope, request_id)` on the
//!   existing hypertable PK — a caller-provided deterministic `(event_time_ms,
//!   request_id)` tuple is written verbatim, so retries with the same tuple
//!   collapse to one row (E5-FN-2 Plan N, supersedes V018 partial UNIQUE which
//!   could not apply on the TimescaleDB hypertable).
//!   All writes are fail-closed: errors propagate to the caller (BudgetTracker).
//! MODULE_NOTE (中): 每次調用一條 insert + 月度聚合。MTD 聚合使用
//!   `date_trunc('month', NOW())`，月初自動重置。插入透過既有 hypertable PK
//!   `(time, scope, request_id)` 的 `ON CONFLICT` 達成冪等 — caller 傳入
//!   確定性 `(event_time_ms, request_id)` tuple 直寫，同 tuple 的重試會被
//!   PK 合併為一列（E5-FN-2 Plan N，取代在 TimescaleDB hypertable 上無法
//!   套用的 V018 partial UNIQUE 設計）。所有寫入 fail-closed：錯誤傳遞給
//!   caller（BudgetTracker）。

use crate::database::pool::DbPool;
use chrono::{DateTime, Utc};
use std::collections::HashMap;
use tracing::debug;

/// Insert one usage row. Returns `Ok(true)` on fresh insert, `Ok(false)` when the
/// `(time, scope, request_id)` PK already exists (idempotent dedup). Returns Err
/// on any DB failure (fail-closed contract).
///
/// `event_time_ms` is written as `time` verbatim — callers must persist the same
/// value across retries so the PK collapses duplicates.
///
/// 插入一條用量列。`Ok(true)` 為新插入，`Ok(false)` 代表 PK
/// `(time, scope, request_id)` 已存在（冪等去重）。任何 DB 失敗時返回 Err
/// （fail-closed 合約）。
///
/// `event_time_ms` 作為 `time` 原樣寫入 — caller 必須在重試時傳同值，PK
/// 才能折疊重複。
#[allow(clippy::too_many_arguments)]
pub async fn insert_usage(
    pool: &DbPool,
    event_time_ms: i64,
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
    let event_time: DateTime<Utc> = DateTime::<Utc>::from_timestamp_millis(event_time_ms)
        .ok_or_else(|| format!("usage_io::insert_usage: bad event_time_ms {event_time_ms}"))?;
    // ON CONFLICT (time, scope, request_id) piggybacks on the existing hypertable PK.
    // RETURNING 1 + fetch_optional: Some(row) → fresh insert; None → duplicate.
    // ON CONFLICT 搭配既有 hypertable PK (time, scope, request_id) 做冪等。
    // RETURNING 1 + fetch_optional：Some(row) → 新插入；None → 重複。
    let row: Option<(i32,)> = sqlx::query_as::<_, (i32,)>(
        "INSERT INTO learning.ai_usage_log
            (time, scope, provider, model, tokens_in, tokens_out, cost_usd, purpose, request_id)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
         ON CONFLICT (time, scope, request_id) DO NOTHING
         RETURNING 1",
    )
    .bind(event_time)
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
    let inserted = row.is_some();
    debug!(
        scope,
        provider,
        model,
        tokens_in,
        tokens_out,
        cost_usd,
        request_id,
        inserted,
        "ai_usage_log row insert attempted"
    );
    Ok(inserted)
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
