//! PG writer for Claude Teacher directives + ExperimentLedger audit.
//! Claude Teacher directive 的 PG writer + ExperimentLedger 審計。
//!
//! MODULE_NOTE (EN): Inserts a directive into `learning.teacher_directives`
//!   (V004 schema, SERIAL PK), captures the returned `directive_id`, then
//!   writes a matching audit row into `learning.experiment_ledger` via the
//!   existing `experiment_ledger_pg::create_hypothesis` helper. When the DB
//!   pool is unavailable (cold start / unit test), returns `Ok(0)` so the
//!   higher-level pipeline can still exercise its happy path without PG.
//! MODULE_NOTE (中): 將 directive 插入 `learning.teacher_directives`
//!   （V004 schema，SERIAL PK），取回 `directive_id`，並透過現有的
//!   `experiment_ledger_pg::create_hypothesis` helper 在
//!   `learning.experiment_ledger` 寫入對應審計行。當 DB pool 不可用
//!   （冷啟動 / 單元測試）時回傳 `Ok(0)`，使上層管線在無 PG 情況下
//!   仍可走完 happy path。

use super::applier::ApplyOutcome;
use super::parser::Directive;
use crate::database::experiment_ledger_pg::{create_hypothesis, Hypothesis};
use crate::database::pool::DbPool;
use std::sync::Arc;
use tracing::{debug, warn};

/// Writer error variants.
/// Writer 錯誤類型。
#[derive(Debug)]
pub enum WriterError {
    /// `INSERT ... RETURNING directive_id` failed.
    /// `INSERT ... RETURNING directive_id` 失敗。
    InsertFailed(String),
}

/// Persist a directive into PG (`learning.teacher_directives`) and write a
/// matching audit row into `learning.experiment_ledger`. Returns the inserted
/// `directive_id` (or `0` if PG is unavailable — silent skip mode).
///
/// 將 directive 寫入 PG（`learning.teacher_directives`）並在
/// `learning.experiment_ledger` 寫入對應審計行。回傳 `directive_id`
/// （PG 不可用時回傳 `0` — 靜默跳過模式）。
pub async fn persist_directive(
    pool: &Arc<DbPool>,
    directive: &Directive,
    raw_response: &serde_json::Value,
    ai_model_used: &str,
    status: &str,
) -> Result<i64, WriterError> {
    if !pool.is_available() {
        debug!("persist_directive: pool unavailable — silent skip / pool 不可用，靜默跳過");
        return Ok(0);
    }
    let pg = match pool.get() {
        Some(p) => p,
        None => return Ok(0),
    };

    // Map parser type → V004 directive_type column.
    // 將 parser type → V004 directive_type 欄位。
    let directive_type_str = match directive.directive_type {
        super::parser::DirectiveType::AdjustParam => "parameter_review",
        super::parser::DirectiveType::PauseStrategy => "risk_assessment",
        super::parser::DirectiveType::BoostArm => "experiment",
        super::parser::DirectiveType::Unpause => "risk_assessment",
    };

    // hypothesis_id is a deterministic correlation key shared with ledger.
    // hypothesis_id 是與 ledger 共享的確定性關聯鍵。
    let hypothesis_id = format!(
        "teacher-{}-{}-{}",
        directive_type_str, directive.scope, directive.expiry
    );

    let content = serde_json::json!({
        "directive": {
            "type": directive_type_str,
            "scope": directive.scope,
            "params": directive.params,
            "expiry": directive.expiry,
            "priority": directive.priority,
        },
        "raw": raw_response,
        "hypothesis_id": hypothesis_id,
    });

    // INSERT ... RETURNING directive_id (V004 PK is SERIAL).
    // 1) Insert directive row / 寫入 directive 行
    let row: Result<(i32,), _> = sqlx::query_as(
        "INSERT INTO learning.teacher_directives \
         (hypothesis_id, directive_type, content, ai_model_used, cost_usd, status) \
         VALUES ($1, $2, $3, $4, $5, $6) \
         RETURNING directive_id",
    )
    .bind(&hypothesis_id)
    .bind(directive_type_str)
    .bind(&content)
    .bind(ai_model_used)
    .bind(0.0_f64) // cost_usd is recorded by BudgetTracker upstream; mirror as 0 here
    .bind(status)
    .fetch_one(pg)
    .await;

    let directive_id = match row {
        Ok((id,)) => id as i64,
        Err(e) => {
            warn!(error = %e, "teacher_directives insert failed / 插入失敗");
            return Err(WriterError::InsertFailed(e.to_string()));
        }
    };

    // 2) ExperimentLedger audit row (best-effort — log failure, don't abort).
    //    ExperimentLedger 審計行（盡力寫入 — 失敗只 log，不中止）。
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0);
    let h = Hypothesis {
        hypothesis_id: hypothesis_id.clone(),
        description: format!(
            "claude_teacher directive {directive_type_str} for {}",
            directive.scope
        ),
        strategy_name: directive.scope.clone(),
        regime: "all".into(),
        proposed_by: "claude_teacher".into(),
        proposed_at_ms: now_ms,
        expires_at_ms: (directive.expiry as u64).saturating_mul(1_000),
        status: "PENDING".into(),
        source_type: "claude_directive".into(),
        metadata: serde_json::json!({
            "directive_id": directive_id,
            "priority": directive.priority,
            "ai_model_used": ai_model_used,
        }),
        trigger_condition: format!("teacher::{directive_type_str}"),
        ..Default::default()
    };
    let ok = create_hypothesis(pool, &h).await;
    if !ok {
        warn!(
            directive_id,
            "experiment_ledger audit row write failed (best-effort) / 審計行寫入失敗（盡力）"
        );
    }

    debug!(directive_id, hypothesis_id = %hypothesis_id, "teacher directive persisted / directive 已持久化");
    Ok(directive_id)
}

/// Record a directive execution outcome into `learning.directive_executions`.
/// 4-02 audit helper — every ApplyOutcome (Applied / Vetoed / Invalid /
/// IpcError) is written here so the full decision trail is persisted for
/// 4-03 outcome-tracker + operator review. Silent-skips when PG pool is
/// unavailable (cold start / unit tests).
///
/// 將 directive 套用結果寫入 `learning.directive_executions`。
/// 4-02 審計輔助 — 每一種 ApplyOutcome（Applied / Vetoed / Invalid /
/// IpcError）都在此寫入，確保完整決策軌跡留存，供 4-03 outcome-tracker
/// 與 operator 復核使用。PG pool 不可用時靜默跳過（冷啟動 / 單元測試）。
pub async fn record_execution(
    pool: &Arc<DbPool>,
    directive_id: i64,
    outcome: &ApplyOutcome,
) -> Result<(), WriterError> {
    if !pool.is_available() {
        debug!(
            directive_id,
            "record_execution: pool unavailable — silent skip / pool 不可用，靜默跳過"
        );
        return Ok(());
    }
    let pg = match pool.get() {
        Some(p) => p,
        None => return Ok(()),
    };

    let (action_taken, success, result_json) = match outcome {
        ApplyOutcome::Applied { action_summary, .. } => (
            "applied",
            true,
            serde_json::json!({
                "outcome": "applied",
                "action_summary": action_summary,
            }),
        ),
        ApplyOutcome::VetoedByGovernance { reason, .. } => (
            "vetoed_by_governance",
            false,
            serde_json::json!({
                "outcome": "vetoed_by_governance",
                "reason": reason,
            }),
        ),
        ApplyOutcome::VetoedByHardBoundary {
            boundary, reason, ..
        } => (
            "vetoed_by_hard_boundary",
            false,
            serde_json::json!({
                "outcome": "vetoed_by_hard_boundary",
                "boundary": boundary,
                "reason": reason,
            }),
        ),
        ApplyOutcome::InvalidDirective { error, .. } => (
            "invalid_directive",
            false,
            serde_json::json!({
                "outcome": "invalid_directive",
                "error": error,
            }),
        ),
        ApplyOutcome::IpcError { error, .. } => (
            "ipc_error",
            false,
            serde_json::json!({
                "outcome": "ipc_error",
                "error": error,
            }),
        ),
    };

    let row: Result<(i32,), _> = sqlx::query_as(
        "INSERT INTO learning.directive_executions \
         (directive_id, action_taken, result, success) \
         VALUES ($1, $2, $3, $4) \
         RETURNING execution_id",
    )
    .bind(directive_id as i32)
    .bind(action_taken)
    .bind(&result_json)
    .bind(success)
    .fetch_one(pg)
    .await;

    match row {
        Ok((_id,)) => {
            debug!(
                directive_id,
                action_taken, "directive_execution audit row written / 審計行已寫入"
            );
            Ok(())
        }
        Err(e) => {
            warn!(
                directive_id,
                error = %e,
                "directive_executions insert failed / 審計行插入失敗"
            );
            Err(WriterError::InsertFailed(e.to_string()))
        }
    }
}
