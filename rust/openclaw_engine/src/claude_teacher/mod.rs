//! Claude Teacher integration — directive fetch / parse / persist pipeline.
//! Claude Teacher 整合 — directive 拉取 / 解析 / 持久化管線。
//!
//! MODULE_NOTE (EN): Phase 4 sub-task 4-01. Provides a thin facade over an
//!   injectable `LlmClient` (Anthropic real client + Mock client for tests),
//!   a strict fail-closed JSON `parser`, and a PG `writer` that records the
//!   directive into `learning.teacher_directives` and an audit row into
//!   `learning.experiment_ledger`. BudgetTracker is consulted **before** any
//!   DB write — if `record_usage` fails, the entire pipeline aborts and the
//!   directive is dropped (fail-closed cost gate). The Anthropic client never
//!   makes a real network call in dev (no `ANTHROPIC_API_KEY`); the build is
//!   wired through traits so wiring/IPC tasks can swap in real impls later.
//! MODULE_NOTE (中): Phase 4 子任務 4-01。提供薄門面層：可注入的
//!   `LlmClient`（真實 Anthropic + 測試 Mock）、嚴格 fail-closed 的 JSON
//!   `parser`、以及將 directive 寫入 `learning.teacher_directives` 並在
//!   `learning.experiment_ledger` 留下審計行的 `writer`。任何 DB 寫入之前
//!   都會先呼叫 BudgetTracker；`record_usage` 失敗則整個管線中止、
//!   directive 被丟棄（fail-closed 成本閘）。Anthropic client 在 dev 環境
//!   沒有 `ANTHROPIC_API_KEY` 時絕不會發出真實網路呼叫；介面以 trait 注入，
//!   後續 wiring/IPC 子任務可替換為真實實作。

pub mod applier;
pub mod client;
pub mod consumer_loop;
pub mod governance_impl;
pub mod outcome_tracker;
pub mod parser;
pub mod strategy_ipc_impl;
pub mod writer;

pub use applier::{ApplyOutcome, DirectiveApplier, GovernanceCheck, IpcFuture, StrategyIpcSink};
pub use client::{AnthropicClient, LlmClient, LlmClientError, LlmResponse, MockClient};
pub use consumer_loop::{ConsumerLoopConfig, ConsumerLoopStatus, TeacherConsumerLoop};
pub use governance_impl::GovernanceCoreWrapper;
pub use outcome_tracker::{sharpe_from_returns, OutcomeTracker, OutcomeWindow, PendingExecution};
pub use parser::{parse_directive, Directive, DirectiveType, ParserError};
pub use strategy_ipc_impl::{EngineCommandSink, PipelineCommandSink};
pub use writer::{persist_directive, record_execution, WriterError};

use crate::ai_budget::tracker::{BudgetTracker, SCOPE_AGENT_TEACHER};
use crate::database::pool::DbPool;
use std::sync::Arc;
use tracing::{debug, error, warn};

/// Error returned by the high-level Claude Teacher pipeline.
/// Claude Teacher 高階管線回傳的錯誤。
#[derive(Debug)]
pub enum TeacherError {
    /// LLM call failed (network / API key / 5xx).
    /// LLM 調用失敗（網路 / API key / 5xx）。
    Client(LlmClientError),
    /// JSON parser rejected the response (unknown type / extra field / past expiry).
    /// JSON parser 拒絕了回應（未知類型 / 額外欄位 / 過期）。
    Parser(ParserError),
    /// BudgetTracker `record_usage` failed — fail-closed abort.
    /// BudgetTracker `record_usage` 失敗 — fail-closed 中止。
    Budget(String),
    /// PG write failed.
    /// PG 寫入失敗。
    Writer(WriterError),
}

impl std::fmt::Display for TeacherError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            TeacherError::Client(e) => write!(f, "llm client: {e:?}"),
            TeacherError::Parser(e) => write!(f, "parser: {e:?}"),
            TeacherError::Budget(e) => write!(f, "budget: {e}"),
            TeacherError::Writer(e) => write!(f, "writer: {e:?}"),
        }
    }
}

impl std::error::Error for TeacherError {}

/// High-level Claude Teacher facade. Holds an injected LLM client, an optional
/// BudgetTracker (None disables cost accounting — only used in unit tests that
/// already verify BudgetTracker integration explicitly), and a DB pool handle.
/// Claude Teacher 高階門面。持有注入的 LLM client、可選 BudgetTracker
/// （None 表示停用成本記帳，只在已單獨驗證 BudgetTracker 整合的單元測試
/// 中使用），以及 DB pool 句柄。
pub struct ClaudeTeacher {
    /// Injected LLM client (Anthropic / Mock / future providers).
    /// 注入的 LLM client（Anthropic / Mock / 未來其他 provider）。
    client: Arc<dyn LlmClient + Send + Sync>,
    /// Optional budget tracker. **MUST** be Some in production.
    /// 可選預算追蹤器。**生產環境必須** 為 Some。
    budget: Option<Arc<BudgetTracker>>,
    /// PG pool handle for directive + ledger persistence.
    /// PG pool 句柄，用於 directive + ledger 持久化。
    pool: Arc<DbPool>,
    /// Model id used for cost accounting (must match BudgetTracker pricing map).
    /// 用於成本記帳的模型 id（必須對應 BudgetTracker 的定價表）。
    model: String,
}

impl ClaudeTeacher {
    /// Construct a new ClaudeTeacher with explicit dependencies.
    /// 以顯式依賴構造新的 ClaudeTeacher。
    pub fn new(
        client: Arc<dyn LlmClient + Send + Sync>,
        budget: Option<Arc<BudgetTracker>>,
        pool: Arc<DbPool>,
        model: impl Into<String>,
    ) -> Self {
        Self {
            client,
            budget,
            pool,
            model: model.into(),
        }
    }

    /// Fetch a directive from the LLM, charge BudgetTracker (fail-closed),
    /// parse the response, and persist it to PG. Returns the inserted
    /// `directive_id` from `learning.teacher_directives` on success.
    ///
    /// 從 LLM 拉取 directive、向 BudgetTracker 計費（fail-closed）、
    /// 解析回應並寫入 PG。成功時回傳 `learning.teacher_directives` 的
    /// `directive_id`。
    ///
    /// Order of operations (do **NOT** reorder — fail-closed contract):
    /// 1. LLM call
    /// 2. BudgetTracker.record_usage  ← if Err, abort BEFORE any DB write
    /// 3. parser.parse_directive
    /// 4. writer.persist_directive (PG + ExperimentLedger audit row)
    pub async fn fetch_and_persist_directive(&self, scope: &str) -> Result<i64, TeacherError> {
        let (_directive, directive_id) = self.fetch_parse_persist(scope).await?;
        Ok(directive_id)
    }

    /// Phase 4.1 entry — fetch + budget + parse + persist, returning BOTH the
    /// parsed `Directive` and the freshly inserted `directive_id`. The
    /// `TeacherConsumerLoop` calls this method then immediately feeds the
    /// returned directive to `DirectiveApplier::apply` (which records the
    /// `directive_executions` audit row).
    ///
    /// Phase 4.1 入口 — 拉取 + 預算 + 解析 + 持久化，**同時** 回傳
    /// 已解析的 `Directive` 和剛 insert 的 `directive_id`。
    /// `TeacherConsumerLoop` 呼叫本方法後立即把回傳的 directive 餵給
    /// `DirectiveApplier::apply`（後者寫 `directive_executions` 審計行）。
    pub async fn fetch_parse_persist(&self, scope: &str) -> Result<(Directive, i64), TeacherError> {
        // 1) LLM call / LLM 呼叫
        let resp = self
            .client
            .call_with_messages(scope)
            .await
            .map_err(TeacherError::Client)?;

        // 2) BudgetTracker — fail-closed: any error aborts before DB write.
        //    BudgetTracker — fail-closed：任何錯誤都在 DB 寫入前中止。
        if let Some(budget) = &self.budget {
            // E5-FN-2 Plan N: mint deterministic (request_id, event_time_ms) once;
            // a retry at this site would reuse the tuple so the hypertable PK
            // collapses the duplicate row instead of double-billing.
            // E5-FN-2 Plan N：鑄造確定性 (request_id, event_time_ms) 一次；
            // 本點重試會沿用 tuple，hypertable PK 折疊重複列而非雙重計費。
            let (request_id, event_time_ms) =
                crate::ai_budget::make_request_id("teacher");
            match budget
                .record_usage(
                    SCOPE_AGENT_TEACHER,
                    "anthropic",
                    &self.model,
                    resp.tokens_in,
                    resp.tokens_out,
                    "directive_generation",
                    &request_id,
                    event_time_ms,
                )
                .await
            {
                Ok(cost_usd) => {
                    debug!(
                        cost_usd,
                        tokens_in = resp.tokens_in,
                        tokens_out = resp.tokens_out,
                        "teacher: budget recorded / 預算已記錄"
                    );
                }
                Err(e) => {
                    error!(
                        error = %e,
                        "teacher: budget record_usage failed — aborting (fail-closed) / 預算記錄失敗，已中止"
                    );
                    return Err(TeacherError::Budget(e));
                }
            }
        } else {
            warn!("teacher: budget tracker disabled — proceeding without cost accounting / 預算追蹤器已停用");
        }

        // 3) Parse / 解析
        let directive = parse_directive(&resp.content_json).map_err(TeacherError::Parser)?;

        // 4) Persist / 持久化
        let directive_id = persist_directive(
            &self.pool,
            &directive,
            &resp.raw_json,
            &self.model,
            "PENDING",
        )
        .await
        .map_err(TeacherError::Writer)?;

        Ok((directive, directive_id))
    }
}

// S-04: use shared now_ms() from openclaw_core instead of local copy.
// S-04：使用 openclaw_core 的共用 now_ms() 取代本地副本。
use openclaw_core::now_ms;

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ai_budget::tracker::BudgetConfig;
    use crate::database::DatabaseConfig;

    async fn empty_pool() -> Arc<DbPool> {
        let cfg = DatabaseConfig {
            database_url: String::new(),
            ..Default::default()
        };
        Arc::new(DbPool::connect(&cfg).await)
    }

    fn valid_directive_json() -> String {
        // expiry far in the future / 過期時間設在很遠的未來
        let future = (now_ms() / 1000 + 86_400) as i64;
        format!(
            r#"{{"type":"adjust_param","scope":"ma_crossover","params":{{"fast_period":12}},"expiry":{future},"priority":3}}"#
        )
    }

    // Test 5: MockClient returns the configured fixture verbatim.
    // 測試 5：MockClient 原樣回傳配置的 fixture。
    #[tokio::test]
    async fn test_mock_client_returns_fixture() {
        let fixture = valid_directive_json();
        let mock = MockClient::new(fixture.clone(), 100, 50);
        let resp = mock.call_with_messages("ma_crossover").await.unwrap();
        assert_eq!(resp.content_json, fixture);
        assert_eq!(resp.tokens_in, 100);
        assert_eq!(resp.tokens_out, 50);
    }

    // Test 6: full pipeline with mock client, in-memory pool, real budget tracker.
    //         DB write is silently skipped (pool empty), parser + budget paths exercised.
    // 測試 6：完整管線（mock client + 空 pool + 真 BudgetTracker）。
    //         DB 寫入靜默跳過，parser + budget 路徑被覆蓋。
    #[tokio::test]
    async fn test_fetch_and_persist_with_mock() {
        let pool = empty_pool().await;
        let budget = Arc::new(BudgetTracker::new_for_test(
            Arc::clone(&pool),
            BudgetConfig::defaults(),
        ));
        let mock: Arc<dyn LlmClient + Send + Sync> =
            Arc::new(MockClient::new(valid_directive_json(), 200, 80));
        let teacher =
            ClaudeTeacher::new(mock, Some(Arc::clone(&budget)), pool, "claude-sonnet-4-5");
        let result = teacher.fetch_and_persist_directive("ma_crossover").await;
        // With empty pool, persist returns Ok(0) (silent skip — see writer.rs).
        assert!(result.is_ok(), "pipeline should succeed: {result:?}");
        // Budget cache reflects the spend.
        let teacher_used = budget.get_remaining(SCOPE_AGENT_TEACHER).await.unwrap();
        assert!(teacher_used < 60.0, "budget should have been charged");
    }

    // Test 8: BudgetTracker.record_usage failure aborts BEFORE any DB write.
    //         We trigger failure by injecting an unknown model (compute_cost_usd Err).
    // 測試 8：record_usage 失敗時，DB 寫入前中止。
    //         以未知模型觸發失敗（compute_cost_usd 回傳 Err）。
    #[tokio::test]
    async fn test_record_usage_failure_aborts_persist() {
        let pool = empty_pool().await;
        let budget = Arc::new(BudgetTracker::new_for_test(
            Arc::clone(&pool),
            BudgetConfig::defaults(),
        ));
        let mock: Arc<dyn LlmClient + Send + Sync> =
            Arc::new(MockClient::new(valid_directive_json(), 100, 50));
        // Unknown model id → BudgetTracker.compute_cost_usd → Err.
        let teacher = ClaudeTeacher::new(
            mock,
            Some(Arc::clone(&budget)),
            pool,
            "this-model-does-not-exist",
        );
        let err = teacher
            .fetch_and_persist_directive("ma_crossover")
            .await
            .expect_err("must fail-close on unknown model");
        match err {
            TeacherError::Budget(_) => {}
            other => panic!("expected Budget error, got {other:?}"),
        }
    }
}
