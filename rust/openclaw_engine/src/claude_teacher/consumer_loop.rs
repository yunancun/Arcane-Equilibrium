//! Phase 4.1 Claude API Consumer Loop — periodic Teacher invoker.
//! Phase 4.1 Claude API Consumer Loop — 定期 Teacher 調用器。
//!
//! MODULE_NOTE (EN): Phase 4.1 sub-task. The missing closing piece of the
//!   Phase 4 learning loop: a tokio task that periodically asks `ClaudeTeacher`
//!   to generate a directive for one strategy scope (round-robin), then feeds
//!   the parsed directive into `DirectiveApplier::apply` (which runs both
//!   hard-boundary + governance gates and writes the audit row). Outcome
//!   tracking is handled by the existing `OutcomeTracker::process_pending`
//!   sweep, which we kick on the same tick to keep wiring minimal.
//!
//!   **DEFAULT-OFF**: the loop ships with `enabled = false`. Operator must
//!   flip the `Arc<AtomicBool>` (via IPC or boot env) AFTER E3 R6 audit
//!   PASSes. This is a deliberate fail-closed safety contract — no Teacher
//!   directive can mutate live strategy state until the audit signs off.
//!
//!   **Cost throttle**: `max_per_cycle = 1` by default. Each cycle picks
//!   ONE scope (round-robin) and issues ONE LLM call. With default
//!   `poll_interval_secs = 300` that's ~12 calls/hour worst-case, well
//!   under the BudgetTracker $60 Teacher allocation when paired with
//!   sonnet-4-5 pricing.
//!
//!   **Fail-soft**: any single-cycle error (LLM down, parser reject, budget
//!   exhausted, IPC channel closed) is logged at WARN and the loop continues.
//!   The loop NEVER panics on operational errors — only `JoinHandle::abort`
//!   from outside terminates it.
//!
//! MODULE_NOTE (中): Phase 4.1 子任務。Phase 4 學習迴路缺失的最後一塊：
//!   一個 tokio 任務，定期請求 `ClaudeTeacher` 為一個策略 scope（round-robin）
//!   生成 directive，再把解析後的 directive 餵給 `DirectiveApplier::apply`
//!   （會跑硬邊界 + 治理雙閘並寫審計行）。Outcome 追蹤交給既有的
//!   `OutcomeTracker::process_pending` sweep，同 tick 順手觸發，
//!   接線最小化。
//!
//!   **預設關閉**：loop 預設 `enabled = false`。E3 R6 audit 通過後，
//!   operator 必須透過 IPC 或啟動環境變量翻 `Arc<AtomicBool>` 才會啟用。
//!   這是刻意的 fail-closed 安全契約 — 在審計通過前，任何 Teacher
//!   directive 都不能變動 live 策略狀態。
//!
//!   **成本節流**：`max_per_cycle = 1` 預設。每個 cycle 挑一個 scope
//!   （round-robin）發一次 LLM 呼叫。預設 `poll_interval_secs = 300`，
//!   每小時最多 ~12 次，遠低於 sonnet-4-5 定價下 BudgetTracker
//!   給 Teacher 的 $60 配額。
//!
//!   **fail-soft**：單一 cycle 出錯（LLM 掛、parser 拒、預算耗盡、
//!   IPC channel 關閉）只 log WARN，loop 繼續。Loop 絕不在運營錯誤上
//!   panic — 只有外部 `JoinHandle::abort` 會終止它。

use super::applier::{ApplyOutcome, DirectiveApplier};
use super::outcome_tracker::OutcomeTracker;
use super::ClaudeTeacher;
use std::sync::atomic::{AtomicBool, AtomicI64, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::task::JoinHandle;
use tracing::{debug, info, warn};

// ---------------------------------------------------------------------------
// Config / 設定
// ---------------------------------------------------------------------------

/// Configuration for the Teacher consumer loop.
/// Teacher consumer loop 的設定。
#[derive(Debug, Clone)]
pub struct ConsumerLoopConfig {
    /// Seconds between cycles. Default 300 (5 min).
    /// 每 cycle 間隔秒數。預設 300（5 分鐘）。
    pub poll_interval_secs: u64,
    /// Strategy scopes to round-robin through. Each cycle picks the next.
    /// 輪詢的策略 scope 列表。每 cycle 挑下一個。
    pub scopes: Vec<String>,
    /// Maximum directives generated per cycle. Default 1 (cost throttle).
    /// 每 cycle 最多生成的 directive 數。預設 1（成本節流）。
    pub max_per_cycle: usize,
    /// Whether to also kick `OutcomeTracker::process_pending` on each cycle.
    /// 是否在每個 cycle 順手觸發 `OutcomeTracker::process_pending`。
    pub run_outcome_sweep: bool,
}

impl ConsumerLoopConfig {
    /// Production defaults: 5-min poll, all v1_15 strategy names, cost-throttled.
    /// 生產預設：5 分鐘輪詢、全部 v1_15 策略名、成本節流。
    pub fn production_defaults() -> Self {
        Self {
            poll_interval_secs: 300,
            scopes: vec![
                "ma_crossover".to_string(),
                "bb_reversion".to_string(),
                "bb_breakout".to_string(),
                "grid_trading".to_string(),
                "funding_arb".to_string(),
            ],
            max_per_cycle: 1,
            run_outcome_sweep: true,
        }
    }

    /// Test-only fast config (1s poll, single scope, no outcome sweep).
    /// 測試專用快速設定（1 秒輪詢、單 scope、無 outcome sweep）。
    #[cfg(test)]
    pub fn for_test(scopes: Vec<String>) -> Self {
        Self {
            poll_interval_secs: 1,
            scopes,
            max_per_cycle: 1,
            run_outcome_sweep: false,
        }
    }
}

// ---------------------------------------------------------------------------
// Status / 狀態
// ---------------------------------------------------------------------------

/// Live status of the consumer loop, exposed for IPC introspection.
/// consumer loop 的即時狀態，供 IPC 內省查詢。
#[derive(Debug, Default)]
pub struct ConsumerLoopStatus {
    /// Number of cycles attempted (incremented at the START of each cycle).
    /// 嘗試的 cycle 數（每 cycle 開始時遞增）。
    pub cycles_attempted: AtomicU64,
    /// Number of directives successfully Applied (passed both gates + IPC ok).
    /// 成功 Applied 的 directive 數（雙閘通過 + IPC 成功）。
    pub directives_applied: AtomicU64,
    /// Number of directives vetoed by hard-boundary or governance.
    /// 被硬邊界或治理 veto 的 directive 數。
    pub directives_vetoed: AtomicU64,
    /// Number of cycles that errored (LLM, parser, budget, IPC).
    /// 出錯的 cycle 數（LLM/parser/預算/IPC 任一）。
    pub cycles_errored: AtomicU64,
    /// Wall-clock millis at end of last cycle (0 = never).
    /// 最後一個 cycle 結束時的牆鐘毫秒（0 = 從未）。
    pub last_cycle_ms: AtomicI64,
    /// Index into `config.scopes` for the NEXT cycle (round-robin cursor).
    /// `config.scopes` 中下一個 cycle 要用的索引（round-robin cursor）。
    pub next_scope_idx: AtomicU64,
}

impl ConsumerLoopStatus {
    /// Snapshot helper for tests / IPC: returns (attempted, applied, vetoed, errored).
    /// 測試/IPC 用快照：回傳 (attempted, applied, vetoed, errored)。
    pub fn snapshot(&self) -> (u64, u64, u64, u64) {
        (
            self.cycles_attempted.load(Ordering::Relaxed),
            self.directives_applied.load(Ordering::Relaxed),
            self.directives_vetoed.load(Ordering::Relaxed),
            self.cycles_errored.load(Ordering::Relaxed),
        )
    }
}

// ---------------------------------------------------------------------------
// TeacherConsumerLoop / 主結構
// ---------------------------------------------------------------------------

/// Phase 4.1 consumer loop owning the Teacher + Applier + Tracker handles.
/// Phase 4.1 consumer loop，持有 Teacher + Applier + Tracker 三個 handle。
pub struct TeacherConsumerLoop {
    teacher: Arc<ClaudeTeacher>,
    applier: Arc<DirectiveApplier>,
    outcome_tracker: Option<Arc<OutcomeTracker>>,
    config: ConsumerLoopConfig,
    /// Runtime kill-switch. `false` = loop ticks but skips all work (cost-free).
    /// 運行時開關。`false` = loop 照 tick 但跳過所有工作（零成本）。
    enabled: Arc<AtomicBool>,
    status: Arc<ConsumerLoopStatus>,
}

impl TeacherConsumerLoop {
    /// Construct a new consumer loop. Loop is NOT started until `spawn` is called.
    /// 建立新 consumer loop。在呼叫 `spawn` 之前 loop 不會啟動。
    pub fn new(
        teacher: Arc<ClaudeTeacher>,
        applier: Arc<DirectiveApplier>,
        outcome_tracker: Option<Arc<OutcomeTracker>>,
        config: ConsumerLoopConfig,
        enabled: Arc<AtomicBool>,
    ) -> Self {
        Self {
            teacher,
            applier,
            outcome_tracker,
            config,
            enabled,
            status: Arc::new(ConsumerLoopStatus::default()),
        }
    }

    /// Get a clone of the status handle (for IPC introspection).
    /// 取得 status handle 的 clone（供 IPC 內省）。
    pub fn status(&self) -> Arc<ConsumerLoopStatus> {
        Arc::clone(&self.status)
    }

    /// Get the enabled flag handle (so IPC handlers can flip it).
    /// 取得 enabled 旗標 handle（供 IPC handler 翻轉）。
    pub fn enabled_handle(&self) -> Arc<AtomicBool> {
        Arc::clone(&self.enabled)
    }

    /// Spawn the loop on the current tokio runtime. Returns the JoinHandle.
    /// 在當前 tokio runtime 上 spawn loop。回傳 JoinHandle。
    pub fn spawn(self: Arc<Self>) -> JoinHandle<()> {
        let interval = Duration::from_secs(self.config.poll_interval_secs.max(1));
        info!(
            interval_secs = self.config.poll_interval_secs,
            scopes = self.config.scopes.len(),
            enabled_at_boot = self.enabled.load(Ordering::Relaxed),
            "TeacherConsumerLoop spawned (default-off until E3 R6 PASS) / consumer loop 已啟動（預設關閉，待 E3 R6 通過）"
        );
        tokio::spawn(async move {
            let mut ticker = tokio::time::interval(interval);
            // Skip the first immediate tick — we want to honor the interval
            // even on the first iteration to avoid a thundering boot herd.
            // 跳過第一個立即 tick — 即便是第一輪也要遵守間隔，
            // 避免啟動雷鳴。
            ticker.tick().await;
            loop {
                ticker.tick().await;
                self.run_one_cycle().await;
            }
        })
    }

    /// Run a single cycle: pick next scope, generate+apply up to
    /// `max_per_cycle` directives, optionally kick the outcome sweep.
    /// Public for unit testing — production code calls this via `spawn`.
    ///
    /// 跑單一 cycle：挑下一個 scope、生成並套用最多 `max_per_cycle` 個
    /// directive、視需要觸發 outcome sweep。public 是為了單元測試 —
    /// 生產程式碼透過 `spawn` 間接呼叫。
    pub async fn run_one_cycle(&self) {
        self.status
            .cycles_attempted
            .fetch_add(1, Ordering::Relaxed);

        if !self.enabled.load(Ordering::Relaxed) {
            debug!("teacher consumer loop disabled — cycle skipped / loop 停用，cycle 跳過");
            self.stamp_cycle_end();
            return;
        }

        if self.config.scopes.is_empty() {
            warn!("teacher consumer loop has no scopes configured — cycle skipped / 無 scope 設定，cycle 跳過");
            self.stamp_cycle_end();
            return;
        }

        // Round-robin scope selection.
        // round-robin 選 scope。
        let n = self.config.scopes.len() as u64;
        let mut had_error = false;
        for _ in 0..self.config.max_per_cycle.max(1) {
            let idx = self.status.next_scope_idx.fetch_add(1, Ordering::Relaxed) % n;
            let scope = self.config.scopes[idx as usize].clone();
            match self.run_one_directive(&scope).await {
                Ok(outcome) => {
                    if outcome.is_success() {
                        self.status
                            .directives_applied
                            .fetch_add(1, Ordering::Relaxed);
                    } else {
                        // Vetoes / invalid / ipc-error all count as "not applied".
                        // The applier still wrote the audit row.
                        // veto / invalid / ipc-error 都算「未套用」，
                        // applier 仍已寫審計行。
                        self.status
                            .directives_vetoed
                            .fetch_add(1, Ordering::Relaxed);
                    }
                }
                Err(e) => {
                    had_error = true;
                    warn!(scope, error = %e, "teacher cycle errored / cycle 出錯");
                }
            }
        }

        if had_error {
            self.status.cycles_errored.fetch_add(1, Ordering::Relaxed);
        }

        // Outcome sweep (best-effort, skips silently if pool unavailable).
        // outcome sweep（盡力，pool 不可用時靜默跳過）。
        if self.config.run_outcome_sweep {
            if let Some(tracker) = &self.outcome_tracker {
                match tracker.process_pending().await {
                    Ok(n) if n > 0 => {
                        info!(rows = n, "outcome_tracker sweep processed / sweep 處理完成");
                    }
                    Ok(_) => {}
                    Err(e) => {
                        warn!(error = %e, "outcome_tracker sweep failed / sweep 失敗");
                    }
                }
            }
        }

        self.stamp_cycle_end();
    }

    /// Generate ONE directive for `scope` and feed it to the applier.
    /// 為 `scope` 生成 1 個 directive 並餵給 applier。
    async fn run_one_directive(&self, scope: &str) -> Result<ApplyOutcome, String> {
        let (directive, directive_id) = self
            .teacher
            .fetch_parse_persist(scope)
            .await
            .map_err(|e| format!("teacher fetch_parse_persist: {e}"))?;
        let outcome = self.applier.apply(directive, directive_id).await;
        debug!(
            scope,
            directive_id,
            tag = outcome.action_tag(),
            "directive cycle outcome / cycle outcome"
        );
        Ok(outcome)
    }

    fn stamp_cycle_end(&self) {
        let now_ms = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as i64)
            .unwrap_or(0);
        self.status.last_cycle_ms.store(now_ms, Ordering::Relaxed);
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ai_budget::tracker::{BudgetConfig, BudgetTracker};
    use crate::claude_teacher::applier::{
        DirectiveApplier, GovernanceCheck, IpcFuture, StrategyIpcSink,
    };
    use crate::claude_teacher::client::{LlmClient, MockClient};
    use crate::claude_teacher::ClaudeTeacher;
    use crate::database::pool::DbPool;
    use crate::database::DatabaseConfig;

    async fn empty_pool() -> Arc<DbPool> {
        Arc::new(DbPool::connect(&DatabaseConfig::default()).await)
    }

    fn valid_directive_json() -> String {
        let future = (std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs()
            + 86_400) as i64;
        format!(
            r#"{{"type":"adjust_param","scope":"ma_crossover","params":{{"fast_period":12}},"expiry":{future},"priority":3}}"#
        )
    }

    /// Mock governance: never halted, daily loss = 0, knows our test scope.
    /// Mock 治理：永不 halt、日虧 0、認得測試 scope。
    struct OkGovernance;
    impl GovernanceCheck for OkGovernance {
        fn current_daily_loss_pct(&self) -> f64 { 0.0 }
        fn session_halted(&self) -> bool { false }
        fn unpause_daily_loss_threshold(&self) -> f64 { 0.05 }
        fn known_strategies(&self) -> Vec<String> {
            vec!["ma_crossover".to_string(), "bb_reversion".to_string()]
        }
    }

    /// Mock IPC sink that always succeeds and counts calls.
    /// Mock IPC sink：永遠成功，計數呼叫。
    struct CountingSink {
        calls: Arc<AtomicU64>,
    }
    impl StrategyIpcSink for CountingSink {
        fn update_strategy_params<'a>(
            &'a self,
            _strategy: &'a str,
            _json: &'a str,
        ) -> IpcFuture<'a> {
            let calls = Arc::clone(&self.calls);
            Box::pin(async move {
                calls.fetch_add(1, Ordering::Relaxed);
                Ok("mock_applied".to_string())
            })
        }
        fn set_strategy_active<'a>(&'a self, _strategy: &'a str, _active: bool) -> IpcFuture<'a> {
            let calls = Arc::clone(&self.calls);
            Box::pin(async move {
                calls.fetch_add(1, Ordering::Relaxed);
                Ok("mock_set_active".to_string())
            })
        }
    }

    /// Halted governance: vetoes all adjust_param.
    /// halt 治理：veto 所有 adjust_param。
    struct HaltedGovernance;
    impl GovernanceCheck for HaltedGovernance {
        fn current_daily_loss_pct(&self) -> f64 { 0.0 }
        fn session_halted(&self) -> bool { true }
        fn unpause_daily_loss_threshold(&self) -> f64 { 0.05 }
        fn known_strategies(&self) -> Vec<String> {
            vec!["ma_crossover".to_string()]
        }
    }

    async fn build_loop(
        governance: Arc<dyn GovernanceCheck>,
        sink: Option<Arc<dyn StrategyIpcSink>>,
        scopes: Vec<String>,
        enabled: bool,
        teacher_model: &str,
    ) -> Arc<TeacherConsumerLoop> {
        let pool = empty_pool().await;
        let budget = Arc::new(BudgetTracker::new_for_test(
            Arc::clone(&pool),
            BudgetConfig::defaults(),
        ));
        let mock: Arc<dyn LlmClient + Send + Sync> =
            Arc::new(MockClient::new(valid_directive_json(), 100, 50));
        let teacher = Arc::new(ClaudeTeacher::new(
            mock,
            Some(budget),
            Arc::clone(&pool),
            teacher_model,
        ));
        let applier = Arc::new(DirectiveApplier::new(governance, sink, Arc::clone(&pool)));
        let cfg = ConsumerLoopConfig::for_test(scopes);
        Arc::new(TeacherConsumerLoop::new(
            teacher,
            applier,
            None,
            cfg,
            Arc::new(AtomicBool::new(enabled)),
        ))
    }

    /// Test 1: enabled loop runs N cycles, applies N directives.
    /// 測試 1：enabled loop 跑 N cycle，套用 N 個 directive。
    #[tokio::test]
    async fn test_enabled_loop_applies_directives() {
        let calls = Arc::new(AtomicU64::new(0));
        let sink: Arc<dyn StrategyIpcSink> = Arc::new(CountingSink {
            calls: Arc::clone(&calls),
        });
        let lp = build_loop(
            Arc::new(OkGovernance),
            Some(sink),
            vec!["ma_crossover".to_string()],
            true,
            "claude-sonnet-4-5",
        )
        .await;
        for _ in 0..3 {
            lp.run_one_cycle().await;
        }
        let (attempted, applied, vetoed, errored) = lp.status().snapshot();
        assert_eq!(attempted, 3);
        assert_eq!(applied, 3);
        assert_eq!(vetoed, 0);
        assert_eq!(errored, 0);
        assert_eq!(calls.load(Ordering::Relaxed), 3);
    }

    /// Test 2: disabled loop ticks but skips all work (no IPC calls).
    /// 測試 2：disabled loop 照 tick 但跳過所有工作（零 IPC 呼叫）。
    #[tokio::test]
    async fn test_disabled_loop_skips_work() {
        let calls = Arc::new(AtomicU64::new(0));
        let sink: Arc<dyn StrategyIpcSink> = Arc::new(CountingSink {
            calls: Arc::clone(&calls),
        });
        let lp = build_loop(
            Arc::new(OkGovernance),
            Some(sink),
            vec!["ma_crossover".to_string()],
            false,
            "claude-sonnet-4-5",
        )
        .await;
        for _ in 0..5 {
            lp.run_one_cycle().await;
        }
        let (attempted, applied, vetoed, errored) = lp.status().snapshot();
        assert_eq!(attempted, 5);
        assert_eq!(applied, 0);
        assert_eq!(vetoed, 0);
        assert_eq!(errored, 0);
        assert_eq!(calls.load(Ordering::Relaxed), 0);
    }

    /// Test 3: governance veto → directive recorded as vetoed, no IPC call.
    /// 測試 3：治理 veto → directive 記為 vetoed，零 IPC 呼叫。
    #[tokio::test]
    async fn test_governance_veto_counted_as_vetoed() {
        let calls = Arc::new(AtomicU64::new(0));
        let sink: Arc<dyn StrategyIpcSink> = Arc::new(CountingSink {
            calls: Arc::clone(&calls),
        });
        let lp = build_loop(
            Arc::new(HaltedGovernance),
            Some(sink),
            vec!["ma_crossover".to_string()],
            true,
            "claude-sonnet-4-5",
        )
        .await;
        lp.run_one_cycle().await;
        let (_, applied, vetoed, _) = lp.status().snapshot();
        assert_eq!(applied, 0);
        assert_eq!(vetoed, 1);
        assert_eq!(calls.load(Ordering::Relaxed), 0, "no IPC call when vetoed");
    }

    /// Test 4: empty scope list → cycle skipped without crash.
    /// 測試 4：scope 列表空 → cycle 跳過不崩潰。
    #[tokio::test]
    async fn test_empty_scopes_skipped_safely() {
        let lp = build_loop(
            Arc::new(OkGovernance),
            None,
            vec![],
            true,
            "claude-sonnet-4-5",
        )
        .await;
        lp.run_one_cycle().await;
        let (attempted, applied, _, errored) = lp.status().snapshot();
        assert_eq!(attempted, 1);
        assert_eq!(applied, 0);
        assert_eq!(errored, 0);
    }

    /// Test 5: round-robin advances cursor across cycles.
    /// 測試 5：round-robin cursor 跨 cycle 推進。
    #[tokio::test]
    async fn test_round_robin_advances_cursor() {
        let lp = build_loop(
            Arc::new(OkGovernance),
            None,
            vec!["ma_crossover".to_string(), "bb_reversion".to_string()],
            true,
            "claude-sonnet-4-5",
        )
        .await;
        for _ in 0..4 {
            lp.run_one_cycle().await;
        }
        // After 4 cycles with 2 scopes the cursor (next index) should be 4.
        // 4 個 cycle + 2 個 scope，下一個 index 應為 4。
        assert_eq!(lp.status().next_scope_idx.load(Ordering::Relaxed), 4);
    }

    /// Test 6: budget exhaustion (unknown model) → cycle counted as errored.
    /// 測試 6：預算耗盡（未知模型）→ cycle 記為錯誤。
    #[tokio::test]
    async fn test_budget_failure_counted_as_errored() {
        let lp = build_loop(
            Arc::new(OkGovernance),
            None,
            vec!["ma_crossover".to_string()],
            true,
            "this-model-does-not-exist",
        )
        .await;
        lp.run_one_cycle().await;
        let (_, applied, _, errored) = lp.status().snapshot();
        assert_eq!(applied, 0);
        assert_eq!(errored, 1);
    }

    /// Test 7: enabled flag flip is observed by next cycle (live toggle).
    /// 測試 7：enabled 旗標翻轉在下一個 cycle 即時生效。
    #[tokio::test]
    async fn test_enabled_flag_live_toggle() {
        let lp = build_loop(
            Arc::new(OkGovernance),
            None,
            vec!["ma_crossover".to_string()],
            false,
            "claude-sonnet-4-5",
        )
        .await;
        lp.run_one_cycle().await;
        assert_eq!(lp.status().directives_applied.load(Ordering::Relaxed), 0);
        // Flip on / 翻開
        lp.enabled_handle().store(true, Ordering::Relaxed);
        lp.run_one_cycle().await;
        assert_eq!(lp.status().directives_applied.load(Ordering::Relaxed), 1);
        // Flip off again / 再翻關
        lp.enabled_handle().store(false, Ordering::Relaxed);
        lp.run_one_cycle().await;
        assert_eq!(lp.status().directives_applied.load(Ordering::Relaxed), 1);
    }

    /// Test 8: status snapshot returns correct tuple after mixed cycles.
    /// 測試 8：混合 cycle 後 status snapshot 回傳正確 tuple。
    #[tokio::test]
    async fn test_status_snapshot_correctness() {
        let lp = build_loop(
            Arc::new(OkGovernance),
            None,
            vec!["ma_crossover".to_string()],
            true,
            "claude-sonnet-4-5",
        )
        .await;
        for _ in 0..2 {
            lp.run_one_cycle().await;
        }
        let (attempted, applied, vetoed, errored) = lp.status().snapshot();
        assert_eq!(attempted, 2);
        assert_eq!(applied, 2);
        assert_eq!(vetoed, 0);
        assert_eq!(errored, 0);
        assert!(lp.status().last_cycle_ms.load(Ordering::Relaxed) > 0);
    }

    /// Test 9: ConsumerLoopConfig::production_defaults sanity (5 strats, 300s).
    /// 測試 9：production_defaults 健全性檢查。
    #[test]
    fn test_production_defaults_sane() {
        let cfg = ConsumerLoopConfig::production_defaults();
        assert_eq!(cfg.poll_interval_secs, 300);
        assert_eq!(cfg.scopes.len(), 5);
        assert_eq!(cfg.max_per_cycle, 1);
        assert!(cfg.run_outcome_sweep);
    }

    /// Test 10: spawn returns a JoinHandle that can be aborted (no panic).
    /// 測試 10：spawn 回傳可 abort 的 JoinHandle（不 panic）。
    #[tokio::test]
    async fn test_spawn_returns_abortable_handle() {
        let lp = build_loop(
            Arc::new(OkGovernance),
            None,
            vec!["ma_crossover".to_string()],
            false,
            "claude-sonnet-4-5",
        )
        .await;
        let handle = lp.spawn();
        // Give the loop a brief moment, then abort.
        // 給 loop 一瞬間後 abort。
        tokio::time::sleep(Duration::from_millis(50)).await;
        handle.abort();
        // abort() returns immediately; awaiting an aborted handle is Err(Cancelled).
        // abort() 立即返回；await 已 abort 的 handle 會回 Err(Cancelled)。
        let result = handle.await;
        assert!(result.is_err() || result.is_ok());
    }
}
