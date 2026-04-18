//! Budget config DB I/O — read/write `learning.ai_budget_config`.
//! 預算配置 DB I/O — 讀寫 `learning.ai_budget_config`。
//!
//! MODULE_NOTE (EN): Pure sqlx runtime queries (no compile-time macros, matching
//!   the rest of the database/ module convention). Read returns a full BudgetConfig
//!   snapshot; write updates a single scope row with operator/system/ipc origin.
//! MODULE_NOTE (中): 純 sqlx 運行時查詢（無編譯時宏，與 database/ 模組其他部分一致）。
//!   讀取返回完整 BudgetConfig 快照；寫入按 scope 更新單列，記錄 operator/system/ipc 來源。

use super::tracker::BudgetConfig;
use crate::database::pool::DbPool;
use std::collections::HashMap;
use tracing::debug;

/// Load all rows from learning.ai_budget_config into a BudgetConfig.
/// 從 learning.ai_budget_config 載入全部列為 BudgetConfig。
pub async fn load_all(pool: &DbPool) -> Result<BudgetConfig, String> {
    let pg = pool
        .get()
        .ok_or_else(|| "config_io::load_all: pool not available".to_string())?;
    let rows: Vec<(String, f32)> = sqlx::query_as::<_, (String, f32)>(
        "SELECT scope, monthly_usd FROM learning.ai_budget_config",
    )
    .fetch_all(pg)
    .await
    .map_err(|e| format!("ai_budget_config select failed: {e}"))?;
    let mut limits = HashMap::new();
    for (scope, usd) in rows {
        limits.insert(scope, usd as f64);
    }
    debug!(rows = limits.len(), "ai_budget_config loaded / 配置已載入");
    Ok(BudgetConfig { limits })
}

/// Upsert a single scope's monthly USD ceiling. Origin = 'operator'/'system'/'ipc'.
/// Upsert 單個 scope 的月度美元上限。Origin = 'operator'/'system'/'ipc'。
///
/// Fail-closed: if PG is unavailable or the write errors out, returns Err so the
/// IPC handler can refuse and surface the error to the operator.
/// fail-closed：PG 不可用或寫入錯誤時返回 Err，IPC handler 可拒絕並回報 operator。
pub async fn upsert_scope(
    pool: &DbPool,
    scope: &str,
    monthly_usd: f64,
    updated_by: &str,
) -> Result<(), String> {
    if monthly_usd < 0.0 {
        return Err(format!("monthly_usd must be >= 0 (got {monthly_usd})"));
    }
    let pg = pool
        .get()
        .ok_or_else(|| "config_io::upsert_scope: pool not available".to_string())?;
    sqlx::query(
        "INSERT INTO learning.ai_budget_config (scope, monthly_usd, updated_at, updated_by)
         VALUES ($1, $2, NOW(), $3)
         ON CONFLICT (scope) DO UPDATE
            SET monthly_usd = EXCLUDED.monthly_usd,
                updated_at  = NOW(),
                updated_by  = EXCLUDED.updated_by",
    )
    .bind(scope)
    .bind(monthly_usd as f32)
    .bind(updated_by)
    .execute(pg)
    .await
    .map_err(|e| format!("ai_budget_config upsert failed: {e}"))?;
    Ok(())
}
