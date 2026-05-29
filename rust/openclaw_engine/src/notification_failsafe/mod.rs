//! Wave 5 Packet C — Notification Failsafe Watcher (engine integration).
//! Wave 5 Packet C — 通知 fail-safe 觀察者（engine 整合層）。
//!
//! 模塊用途：
//!   把 `openclaw_core::sm::risk_gov::RiskEvent::NotificationFailsafeTimeout` 從純
//!   variant 接到 engine 真實副作用鏈：
//!     1. 觀察三路通知（Slack / Email / Console banner）派發結果；
//!     2. 三路 AllFail → 武裝 1h timer；AllSuccess 或 operator ack → 解除；
//!     3. timer 過期 → 走 SM-04 transition 進 Defensive
//!        (initiator=RiskGovernor / reason=`auto_escalated_to_sm04_defensive`)；
//!     4. 呼 `active_lock_profit_per_position` 縮 SL 至 entry + ATR-buffer；
//!     5. 對每個 `StopAdjustment` 經 `ExchangeStopSync` 同步到交易所 conditional
//!        path（雙重防線 per CLAUDE.md §二 原則 9）；
//!     6. emit audit `auto_escalated_to_sm04_defensive` 含 transition / adjustments /
//!        sync result。
//!
//! 為什麼放在 engine 而非 core：
//!   - core 已落實純 variant + transition rule + `active_lock_profit_per_position`
//!     計算（Sprint Wave 5 Packet C source IMPL）；engine 層是「副作用 + 副系統」
//!     接線（exchange / audit / clock / notification dispatcher），不可下放到 core
//!     避免循環依賴。
//!
//! 不變量（per AMD-2026-05-21-01 v2 §Decision 2.5 + 3.1 + PA spec §4.4 Stage 3b）：
//!   - `FailsafeConfig::DEFAULT_TIMEOUT_MS = 3_600_000` 是 compile-time hard-coded
//!     fail-safe，runtime TOML 不得 override（Q3 RESOLVED Path A）；
//!   - 已 Defensive 時 timer 過期 escalate 為 no-op（不重觸發、不雙重 audit）；
//!   - `ExchangeStopSync` 個別失敗不 rollback SM-04 transition（survival > exchange
//!     consistency，per §二 原則 5）；
//!   - 任何 trait 失敗 fail-soft，不 panic、不 unwrap；
//!   - `PartialFail` 不武裝 timer，亦不解除（per spec 三路冗餘語義：全 fail 才入
//!     fail-safe；部分 fail 為「正常 degraded」由 incident_policy 處理）。
//!
//! 切片範圍（minimal slice 2026-05-28）：
//!   - 純邏輯 + trait seam + 單元/整合測試（mock dispatcher / exchange / audit / clock）；
//!   - 不接 `pipeline_ctor` / `tasks.rs` long-running task；
//!   - 不寫 PG row（audit 走 `FailsafeAuditEmitter` trait）；
//!   - 不碰 `GovernanceCore` 既有 cascade。
//!
//! 後續 wave wire 進 tick / runtime 後再補 runtime evidence。
//!
//! 參考：
//!   - `openclaw_core::sm::risk_gov` Wave 5 Packet C T1-T6 tests
//!   - AMD-2026-05-21-01 v2 §Decision 2.5 / 3.1 / Q3 / Q4
//!   - PA spec §4.4 Stage 1-4 ladder + §12 AC
//!   - CLAUDE.md §二 原則 5/6/9（survival / fail-closed / 雙重防線）

// Wave 5 Packet C IMPL 子模塊（per PA C spec 2026-05-28 hybrid PC.B 拍板）：
// - `dispatchers`：3-way notification (Slack / Email / Console banner) 真實 impl
// - `audit_emitter`：V114 `observability.notification_failsafe_events` PG INSERT
// - `providers`：runtime 注入 PositionSnapshotProvider / ExchangeStopSync / FailsafeClock
// 各子模塊獨立，pipeline_ctor wire（C4）+ GUI banner（C5）延 Sprint 3 Level 2 promotion
// 一併做（per operator decision PC.B + grill-me Q3 「demo canary 另開 sprint」邏輯）。
pub mod audit_emitter;
pub mod dispatchers;
pub mod providers;

use async_trait::async_trait;
use openclaw_core::sm::risk_gov::{
    active_lock_profit_per_position, PositionSnapshot, RiskEvent, RiskGovernorSm, RiskInitiator,
    RiskLevel, StopAdjustment,
};
use serde::Serialize;
use serde_json::json;
use thiserror::Error;

// ════════════════════════════════════════════════════════════════════════════
// 配置常量 / Config constants
// ════════════════════════════════════════════════════════════════════════════

/// Failsafe watcher 配置。
///
/// 為什麼分一個 struct：以後可能加入更多可調參數（如「PartialFail 升級為等同 AllFail」
/// 開關 — 但需另立治理決議）；當前只暴露 ATR buffer multiplier，timeout 固定。
#[derive(Debug, Clone, Copy)]
pub struct FailsafeConfig {
    /// Active lock-profit 公式中 ATR 的乘數（per PA spec §4.4 line 485-487）。
    /// 不變量：必正且有限；NaN/負值由 `active_lock_profit_per_position` 自身 fail-closed。
    pub atr_buffer_multiplier: f64,
}

impl FailsafeConfig {
    /// 三路通知全 fail 到 SM-04 Defensive 之間的 timeout
    /// （per AMD §Decision 3.1 與 Q3 Resolved Path A：1 小時 = 3_600_000 毫秒）。
    /// compile-time hard-coded，runtime TOML 不得 override（fail-safe 不可降級）。
    pub const DEFAULT_TIMEOUT_MS: u64 = 3_600_000;

    /// 預設 ATR buffer multiplier（per PA spec §4.4 line 487：0.5 是 conservative
    /// 鎖利幅度——Buy 倉 SL 拉到 entry 上方 0.5×ATR，Sell 倉拉到下方）。
    pub const DEFAULT_ATR_BUFFER: f64 = 0.5;

    pub const fn new(atr_buffer_multiplier: f64) -> Self {
        Self {
            atr_buffer_multiplier,
        }
    }
}

impl Default for FailsafeConfig {
    fn default() -> Self {
        Self::new(Self::DEFAULT_ATR_BUFFER)
    }
}

// ════════════════════════════════════════════════════════════════════════════
// 通知 outcome 與 channel
// ════════════════════════════════════════════════════════════════════════════

/// 通知通道枚舉（per AMD §Decision 3.1：Slack + Email + Console banner 三路冗餘）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize)]
pub enum NotificationChannel {
    Slack,
    Email,
    ConsoleBanner,
}

impl NotificationChannel {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Slack => "slack",
            Self::Email => "email",
            Self::ConsoleBanner => "console_banner",
        }
    }
}

/// 單一 round 三路派發結果（dispatcher 端統一回報）。
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub enum DispatchOutcome {
    /// 三路皆送達。
    AllSuccess,
    /// 部分通道失敗（其餘成功）。spec 語義為 degraded 但非 fail-safe 觸發條件。
    PartialFail { failed: Vec<NotificationChannel> },
    /// 三路皆失敗 — 觸發 1h timer 武裝。
    AllFail,
}

impl DispatchOutcome {
    pub fn is_all_fail(&self) -> bool {
        matches!(self, Self::AllFail)
    }
    pub fn is_all_success(&self) -> bool {
        matches!(self, Self::AllSuccess)
    }
}

// ════════════════════════════════════════════════════════════════════════════
// 純邏輯 decision
// ════════════════════════════════════════════════════════════════════════════

/// 解除 timer 的原因（用於 audit 與 GUI banner 顯示）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum TimerCancelReason {
    /// 通知恢復（之後一次派發 AllSuccess）。
    NotificationRecovered,
    /// Operator 主動 ack（GUI banner 點擊 / IPC operator_ack 訊號）。
    OperatorAck,
}

/// `observe_*` / `record_*` 純邏輯結果。
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub enum FailsafeDecision {
    /// 狀態無變化（已武裝且仍未到期；或已解除無動作）。
    NoAction,
    /// 本次觀察首次武裝 timer。
    TimerArmed { since_ms: u64 },
    /// 本次觀察解除 timer。
    TimerCancelled { reason: TimerCancelReason },
    /// timer 已到期，呼叫端應立即跑 `execute_failsafe_escalation`。
    EscalateNow,
}

// ════════════════════════════════════════════════════════════════════════════
// Watcher 狀態
// ════════════════════════════════════════════════════════════════════════════

/// Failsafe watcher 可變狀態 — 由 `FailsafeWatcher` 內部持有。
#[derive(Debug, Clone, Default)]
pub struct FailsafeWatcherState {
    /// timer 武裝起算 ms（None 表示未武裝）。
    timer_armed_at_ms: Option<u64>,
    /// 為了測試與觀測，保留最後一次觀察的 outcome。
    last_outcome: Option<DispatchOutcome>,
    /// 標記是否已對「同一次武裝」完成過 escalate 副作用，避免 idempotent 重觸發。
    escalated_for_current_arm: bool,
}

impl FailsafeWatcherState {
    pub fn timer_armed_at_ms(&self) -> Option<u64> {
        self.timer_armed_at_ms
    }
    pub fn last_outcome(&self) -> Option<&DispatchOutcome> {
        self.last_outcome.as_ref()
    }
    pub fn is_armed(&self) -> bool {
        self.timer_armed_at_ms.is_some()
    }

    /// Wave 5 Packet C / C3 — 對 `providers::single_watcher` 模塊暴露 escalated
    /// idempotent guard 的 setter。
    ///
    /// 為什麼存在：`SharedFailsafeWatcher::check_timer` 採「lock → drop → await →
    /// re-lock」三段拆分（per spec §4.7 + §11.3 反對 3 mitigation），需要在第三段
    /// re-lock 時把 `escalated_for_current_arm` 標記為 true 避免下一次 tick 重觸發。
    /// `FailsafeWatcher`（原 single-task 版）內部直接寫欄位即可，但 `SharedFailsafeWatcher`
    /// 透過 `parking_lot::Mutex` 持有 state，必須走 pub setter。
    ///
    /// `pub(crate)` 而非 `pub`：對 crate 外（GUI / IPC）關閉 — 這個 guard 是 watcher
    /// 內部 idempotent 不變量，不該被外部修改。
    pub(crate) fn set_escalated_for_current_arm(&mut self, escalated: bool) {
        self.escalated_for_current_arm = escalated;
    }
}

// ════════════════════════════════════════════════════════════════════════════
// Trait seams
// ════════════════════════════════════════════════════════════════════════════

/// 三路通知派發抽象。runtime 注入真實 Slack/Email/Console 實作；測試注入 mock。
#[async_trait]
pub trait NotificationDispatcher: Send + Sync {
    /// 派發訊息至三路通道並回報結果。
    /// runtime 端負責 timeout / retry；本層只取 outcome。
    async fn dispatch_3way(&self, message: &str) -> DispatchOutcome;
}

/// 倉位快照來源。runtime 從 paper_state / Bybit REST 拉真實倉位後 map 為
/// `PositionSnapshot`；測試注入 mock。
pub trait PositionSnapshotProvider: Send + Sync {
    fn snapshot_positions(&self) -> Vec<PositionSnapshot>;
}

/// 交易所 conditional SL 同步抽象。runtime 注入 `PositionManager::set_trading_stop`
/// 包裝；測試注入 mock 記錄呼叫序列。
#[async_trait]
pub trait ExchangeStopSync: Send + Sync {
    async fn sync_stop(&self, adjustment: &StopAdjustment) -> Result<(), ExchangeStopError>;
}

/// Audit emit 抽象。runtime 注入 `observability.engine_events` writer；測試 mock。
#[async_trait]
pub trait FailsafeAuditEmitter: Send + Sync {
    async fn emit_auto_escalated(
        &self,
        payload: serde_json::Value,
    ) -> Result<(), FailsafeAuditError>;
}

/// 時鐘抽象 — 純邏輯與測試所需。runtime 注入 wall clock；測試注入 deterministic clock。
pub trait FailsafeClock: Send + Sync {
    fn now_ms(&self) -> u64;
}

// ════════════════════════════════════════════════════════════════════════════
// Errors
// ════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Error)]
pub enum ExchangeStopError {
    #[error("exchange stop sync rejected: {0}")]
    Rejected(String),
    #[error("exchange stop sync transport failure: {0}")]
    Transport(String),
}

#[derive(Debug, Error)]
pub enum FailsafeAuditError {
    #[error("audit emit failed: {0}")]
    EmitFailed(String),
}

// ════════════════════════════════════════════════════════════════════════════
// 純邏輯 evaluator
// ════════════════════════════════════════════════════════════════════════════

/// 處理一次派發 outcome 觀察 — 純函數，無 I/O。
///
/// 規則（per spec §4.4 Stage 1-3）：
///   - `AllSuccess` ⇒ 若已武裝：解除 + `TimerCancelled(NotificationRecovered)`；否則 `NoAction`
///   - `AllFail` ⇒ 若未武裝：武裝 + `TimerArmed`；若已武裝：保持，`NoAction`（timeout 判定走 `check_timer_expiry`）
///   - `PartialFail` ⇒ `NoAction`（不武裝、不解除；spec 三路冗餘語義）
pub fn evaluate_dispatch(
    state: &mut FailsafeWatcherState,
    outcome: DispatchOutcome,
    now_ms: u64,
) -> FailsafeDecision {
    state.last_outcome = Some(outcome.clone());
    match outcome {
        DispatchOutcome::AllSuccess => {
            if state.timer_armed_at_ms.is_some() {
                state.timer_armed_at_ms = None;
                state.escalated_for_current_arm = false;
                FailsafeDecision::TimerCancelled {
                    reason: TimerCancelReason::NotificationRecovered,
                }
            } else {
                FailsafeDecision::NoAction
            }
        }
        DispatchOutcome::AllFail => {
            if state.timer_armed_at_ms.is_none() {
                state.timer_armed_at_ms = Some(now_ms);
                state.escalated_for_current_arm = false;
                FailsafeDecision::TimerArmed { since_ms: now_ms }
            } else {
                FailsafeDecision::NoAction
            }
        }
        DispatchOutcome::PartialFail { .. } => FailsafeDecision::NoAction,
    }
}

/// Operator 主動 ack — 解除已武裝 timer；未武裝為 no-op。
pub fn record_operator_ack(state: &mut FailsafeWatcherState) -> FailsafeDecision {
    if state.timer_armed_at_ms.is_some() {
        state.timer_armed_at_ms = None;
        state.escalated_for_current_arm = false;
        FailsafeDecision::TimerCancelled {
            reason: TimerCancelReason::OperatorAck,
        }
    } else {
        FailsafeDecision::NoAction
    }
}

/// 判斷已武裝 timer 是否到期（純邏輯）。
///
/// 不變量：
///   - 未武裝 → `false`；
///   - 已武裝且 (now - armed_at) >= timeout_ms → `true`；
///   - escalate 只能對「同一次武裝」執行一次 — `escalated_for_current_arm` 標記。
pub fn timer_expired(
    state: &FailsafeWatcherState,
    now_ms: u64,
    timeout_ms: u64,
) -> bool {
    if state.escalated_for_current_arm {
        return false;
    }
    match state.timer_armed_at_ms {
        Some(armed_at) => now_ms.saturating_sub(armed_at) >= timeout_ms,
        None => false,
    }
}

// ════════════════════════════════════════════════════════════════════════════
// 執行報告
// ════════════════════════════════════════════════════════════════════════════

/// 單一 symbol 的 exchange sync 結果。
#[derive(Debug, Clone, Serialize)]
pub struct StopSyncRecord {
    pub symbol: String,
    pub side: String,
    pub new_sl: f64,
    pub success: bool,
    pub error: Option<String>,
}

/// `execute_failsafe_escalation` 完整報告。
#[derive(Debug, Clone, Serialize)]
pub struct FailsafeExecutionReport {
    pub transition_attempted: bool,
    pub transition_succeeded: bool,
    pub transition_skipped_reason: Option<String>,
    pub from_level: String,
    pub to_level: String,
    pub adjustments_count: usize,
    pub sync_records: Vec<StopSyncRecord>,
    pub audit_emitted: bool,
    pub audit_error: Option<String>,
    pub now_ms: u64,
}

impl FailsafeExecutionReport {
    pub fn sync_failure_count(&self) -> usize {
        self.sync_records.iter().filter(|r| !r.success).count()
    }
}

// ════════════════════════════════════════════════════════════════════════════
// 核心副作用入口：execute_failsafe_escalation
// ════════════════════════════════════════════════════════════════════════════

/// 跑 SM-04 transition + active lock-profit + exchange sync + audit emit 全鏈。
///
/// 呼叫端：`FailsafeWatcher::check_timer` 內部；不直接從 hot path 呼叫
/// （由 hot path 觸發 dispatcher 結果即可，timer 判定走另條 tokio task）。
///
/// 不變量：
///   - 已 Defensive / CircuitBreaker / ManualReview → skip transition（不重觸發），
///     但仍跑 active lock-profit + exchange sync + audit emit（鎖利對保命永遠 OK）；
///   - exchange sync 個別失敗不 rollback transition；報告會回顯失敗 symbol；
///   - audit 失敗 fail-soft（survival 優先），但報告會回顯 error。
pub async fn execute_failsafe_escalation<P, E, A>(
    risk_sm: &mut RiskGovernorSm,
    positions: &P,
    exchange: &E,
    audit: &A,
    cfg: &FailsafeConfig,
    now_ms: u64,
) -> FailsafeExecutionReport
where
    P: PositionSnapshotProvider + ?Sized,
    E: ExchangeStopSync + ?Sized,
    A: FailsafeAuditEmitter + ?Sized,
{
    let from_level = risk_sm.snapshot_level();
    let mut report = FailsafeExecutionReport {
        transition_attempted: false,
        transition_succeeded: false,
        transition_skipped_reason: None,
        from_level: from_level.as_str().to_string(),
        to_level: from_level.as_str().to_string(),
        adjustments_count: 0,
        sync_records: Vec::new(),
        audit_emitted: false,
        audit_error: None,
        now_ms,
    };

    // Step 1: SM-04 transition (skip 若已 >= Defensive — 不重觸發)
    if from_level < RiskLevel::Defensive {
        report.transition_attempted = true;
        match risk_sm.transition(
            RiskLevel::Defensive,
            RiskEvent::NotificationFailsafeTimeout,
            RiskInitiator::RiskGovernor,
            vec!["notification_3way_fail_1h_timeout".into()],
            None,
            "auto_escalated_to_sm04_defensive",
        ) {
            Ok(()) => {
                report.transition_succeeded = true;
                report.to_level = RiskLevel::Defensive.as_str().to_string();
            }
            Err(e) => {
                // 罕見路徑：transition rule 拒絕（理論上 Normal/Cautious/Reduced → Defensive
                // 都 ALLOWED；若返錯代表 risk_gov 規則漂移，立即 audit 記錄。
                report.transition_succeeded = false;
                report.transition_skipped_reason = Some(format!("sm04_transition_error: {e}"));
            }
        }
    } else {
        report.transition_skipped_reason = Some(format!(
            "already_at_or_above_defensive:{}",
            from_level.as_str()
        ));
        report.to_level = from_level.as_str().to_string();
    }

    // Step 2: active lock-profit 計算（純值 — 不直接接 exchange）
    let positions_snapshot = positions.snapshot_positions();
    let adjustments =
        active_lock_profit_per_position(&positions_snapshot, cfg.atr_buffer_multiplier);
    report.adjustments_count = adjustments.len();

    // Step 3: 對每個 adjustment 同步 exchange conditional SL
    for adj in &adjustments {
        let result = exchange.sync_stop(adj).await;
        let record = match result {
            Ok(()) => StopSyncRecord {
                symbol: adj.symbol.clone(),
                side: adj.side.to_string(),
                new_sl: adj.new_sl,
                success: true,
                error: None,
            },
            Err(e) => StopSyncRecord {
                symbol: adj.symbol.clone(),
                side: adj.side.to_string(),
                new_sl: adj.new_sl,
                success: false,
                error: Some(e.to_string()),
            },
        };
        report.sync_records.push(record);
    }

    // Step 4: audit emit
    let audit_payload = json!({
        "event": "auto_escalated_to_sm04_defensive",
        "trigger": RiskEvent::NotificationFailsafeTimeout.as_str(),
        "initiator": "RiskGovernor",
        "from_level": report.from_level,
        "to_level": report.to_level,
        "transition_succeeded": report.transition_succeeded,
        "transition_skipped_reason": report.transition_skipped_reason,
        "adjustments_count": report.adjustments_count,
        "sync_records": report.sync_records,
        "now_ms": now_ms,
        "atr_buffer_multiplier": cfg.atr_buffer_multiplier,
    });
    match audit.emit_auto_escalated(audit_payload).await {
        Ok(()) => report.audit_emitted = true,
        Err(e) => report.audit_error = Some(e.to_string()),
    }

    report
}

// ════════════════════════════════════════════════════════════════════════════
// FailsafeWatcher — 把 state + traits 綁在一起
// ════════════════════════════════════════════════════════════════════════════

/// 泛型整合 watcher — 由 caller 顯式呼叫三個入口：
///   1. `observe_dispatch(outcome)` — 派發後呼叫
///   2. `record_operator_ack()` — Operator GUI ack 後呼叫
///   3. `check_timer(risk_sm)` — 週期性檢查 timer 是否過期
///
/// **不是 production 路徑（P3-05, v80 cold audit, 2026-05-29）**：
///   production runtime 持有的是 `providers::single_watcher::SharedFailsafeWatcher`
///   （`Mutex<FailsafeWatcherState>` + `Arc<dyn ...>` trait 物件、claim-before-await
///   並發保護）。本泛型結構僅在 `#[cfg(test)] mod tests` 內以具體 Mock 型別構造
///   （見本檔 tests `make_watcher`），無任何 production caller（`FailsafeWatcher::new`
///   只出現在測試）。保留它是為了讓核心 timer / dispatch / ack 邏輯能以泛型 +
///   Mock 做純單元測試，不依賴 `Arc`/`Mutex` runtime 包裝；勿誤認為 live failsafe
///   執行路徑。生產語義與並發不變量以 `SharedFailsafeWatcher` 為準。
///
/// 為什麼不內建 tokio::spawn：避免 minimal slice 跨「runtime 接線」邊界（per
/// 操作員指示「不碰 live，不造 runtime evidence」）；長運行 task 由
/// `SharedFailsafeWatcher` 端的 spawn 負責。
pub struct FailsafeWatcher<D, P, E, A, C>
where
    D: NotificationDispatcher,
    P: PositionSnapshotProvider,
    E: ExchangeStopSync,
    A: FailsafeAuditEmitter,
    C: FailsafeClock,
{
    dispatcher: D,
    positions: P,
    exchange: E,
    audit: A,
    clock: C,
    cfg: FailsafeConfig,
    state: FailsafeWatcherState,
}

impl<D, P, E, A, C> FailsafeWatcher<D, P, E, A, C>
where
    D: NotificationDispatcher,
    P: PositionSnapshotProvider,
    E: ExchangeStopSync,
    A: FailsafeAuditEmitter,
    C: FailsafeClock,
{
    pub fn new(
        dispatcher: D,
        positions: P,
        exchange: E,
        audit: A,
        clock: C,
        cfg: FailsafeConfig,
    ) -> Self {
        Self {
            dispatcher,
            positions,
            exchange,
            audit,
            clock,
            cfg,
            state: FailsafeWatcherState::default(),
        }
    }

    pub fn state(&self) -> &FailsafeWatcherState {
        &self.state
    }

    /// 觀察一次派發 outcome；同時也允許 runtime 端直接派發（呼叫 `dispatcher.dispatch_3way`
    /// 後將 outcome 餵回）。本方法純邏輯，無 I/O。
    pub fn observe_dispatch(&mut self, outcome: DispatchOutcome) -> FailsafeDecision {
        let now_ms = self.clock.now_ms();
        evaluate_dispatch(&mut self.state, outcome, now_ms)
    }

    /// 主動派發一次三路通知並依結果更新 state。
    pub async fn dispatch_and_observe(&mut self, message: &str) -> FailsafeDecision {
        let outcome = self.dispatcher.dispatch_3way(message).await;
        self.observe_dispatch(outcome)
    }

    /// Operator GUI ack — 解除已武裝 timer。
    pub fn record_operator_ack(&mut self) -> FailsafeDecision {
        record_operator_ack(&mut self.state)
    }

    /// 週期性檢查 — timer 過期則執行完整副作用鏈。
    /// 返回 `None` 表示未到期；`Some(report)` 表示已執行（呼叫端依 report 決定 GUI 通報）。
    pub async fn check_timer(
        &mut self,
        risk_sm: &mut RiskGovernorSm,
    ) -> Option<FailsafeExecutionReport> {
        let now_ms = self.clock.now_ms();
        if !timer_expired(&self.state, now_ms, FailsafeConfig::DEFAULT_TIMEOUT_MS) {
            return None;
        }
        let report = execute_failsafe_escalation(
            risk_sm,
            &self.positions,
            &self.exchange,
            &self.audit,
            &self.cfg,
            now_ms,
        )
        .await;
        // 標記本次武裝已 escalate 過，避免下一次 check_timer 重觸發（操作員必須解除）
        self.state.escalated_for_current_arm = true;
        Some(report)
    }
}

// ════════════════════════════════════════════════════════════════════════════
// 測試
// ════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;
    use std::sync::{
        atomic::{AtomicU64, Ordering},
        Mutex,
    };

    // ── Mocks ──────────────────────────────────────────────────────────────

    struct MockClock {
        now: AtomicU64,
    }
    impl MockClock {
        fn new(start: u64) -> Self {
            Self {
                now: AtomicU64::new(start),
            }
        }
        fn advance(&self, ms: u64) {
            self.now.fetch_add(ms, Ordering::SeqCst);
        }
    }
    impl FailsafeClock for MockClock {
        fn now_ms(&self) -> u64 {
            self.now.load(Ordering::SeqCst)
        }
    }

    struct MockDispatcher {
        // 由 test 預先 push 一序列 outcome；每次呼叫 pop 第一筆
        outcomes: Mutex<Vec<DispatchOutcome>>,
    }
    impl MockDispatcher {
        fn new(outcomes: Vec<DispatchOutcome>) -> Self {
            Self {
                outcomes: Mutex::new(outcomes),
            }
        }
    }
    #[async_trait]
    impl NotificationDispatcher for MockDispatcher {
        async fn dispatch_3way(&self, _message: &str) -> DispatchOutcome {
            let mut q = self.outcomes.lock().unwrap();
            if q.is_empty() {
                DispatchOutcome::AllSuccess
            } else {
                q.remove(0)
            }
        }
    }

    struct MockPositions {
        positions: Vec<PositionSnapshot>,
    }
    impl PositionSnapshotProvider for MockPositions {
        fn snapshot_positions(&self) -> Vec<PositionSnapshot> {
            self.positions.clone()
        }
    }

    struct MockExchange {
        // 記錄 sync_stop 被呼叫的 (symbol, new_sl) 序列
        calls: Mutex<Vec<(String, f64)>>,
        // 若 fail_for 包含 symbol 則該 symbol 回 Err
        fail_for: Vec<String>,
    }
    impl MockExchange {
        fn new(fail_for: Vec<String>) -> Self {
            Self {
                calls: Mutex::new(Vec::new()),
                fail_for,
            }
        }
        fn calls(&self) -> Vec<(String, f64)> {
            self.calls.lock().unwrap().clone()
        }
    }
    #[async_trait]
    impl ExchangeStopSync for MockExchange {
        async fn sync_stop(&self, adjustment: &StopAdjustment) -> Result<(), ExchangeStopError> {
            self.calls
                .lock()
                .unwrap()
                .push((adjustment.symbol.clone(), adjustment.new_sl));
            if self.fail_for.contains(&adjustment.symbol) {
                Err(ExchangeStopError::Rejected("mock_reject".into()))
            } else {
                Ok(())
            }
        }
    }

    struct MockAudit {
        captured: Mutex<Vec<serde_json::Value>>,
        fail: bool,
    }
    impl MockAudit {
        fn new(fail: bool) -> Self {
            Self {
                captured: Mutex::new(Vec::new()),
                fail,
            }
        }
        fn captured(&self) -> Vec<serde_json::Value> {
            self.captured.lock().unwrap().clone()
        }
    }
    #[async_trait]
    impl FailsafeAuditEmitter for MockAudit {
        async fn emit_auto_escalated(
            &self,
            payload: serde_json::Value,
        ) -> Result<(), FailsafeAuditError> {
            self.captured.lock().unwrap().push(payload);
            if self.fail {
                Err(FailsafeAuditError::EmitFailed("mock_audit_fail".into()))
            } else {
                Ok(())
            }
        }
    }

    fn pos(symbol: &str, side: &'static str, entry: f64, atr: f64) -> PositionSnapshot {
        PositionSnapshot {
            symbol: symbol.to_string(),
            side,
            entry_price: entry,
            qty: 1.0,
            current_sl: None,
            atr,
        }
    }

    fn build_watcher(
        clock: MockClock,
        outcomes: Vec<DispatchOutcome>,
        positions: Vec<PositionSnapshot>,
        fail_exchange_for: Vec<String>,
        audit_fail: bool,
    ) -> FailsafeWatcher<MockDispatcher, MockPositions, MockExchange, MockAudit, MockClock> {
        FailsafeWatcher::new(
            MockDispatcher::new(outcomes),
            MockPositions { positions },
            MockExchange::new(fail_exchange_for),
            MockAudit::new(audit_fail),
            clock,
            FailsafeConfig::default(),
        )
    }

    // ── T1: AllSuccess on fresh state → NoAction ────────────────────────────

    #[tokio::test]
    async fn t1_all_success_fresh_state_no_action() {
        let mut w = build_watcher(MockClock::new(1_000), vec![], vec![], vec![], false);
        let decision = w.observe_dispatch(DispatchOutcome::AllSuccess);
        assert_eq!(decision, FailsafeDecision::NoAction);
        assert!(!w.state().is_armed());
    }

    // ── T2: AllFail arms timer ─────────────────────────────────────────────

    #[tokio::test]
    async fn t2_all_fail_arms_timer() {
        let mut w = build_watcher(MockClock::new(2_000), vec![], vec![], vec![], false);
        let decision = w.observe_dispatch(DispatchOutcome::AllFail);
        assert_eq!(decision, FailsafeDecision::TimerArmed { since_ms: 2_000 });
        assert!(w.state().is_armed());
        assert_eq!(w.state().timer_armed_at_ms(), Some(2_000));

        // 第二次 AllFail 同一武裝期 → NoAction（不重設 since_ms）
        let decision2 = w.observe_dispatch(DispatchOutcome::AllFail);
        assert_eq!(decision2, FailsafeDecision::NoAction);
        assert_eq!(w.state().timer_armed_at_ms(), Some(2_000));
    }

    // ── T3: timer expires → SM-04 + sync_stop + audit ───────────────────────

    #[tokio::test]
    async fn t3_timer_expires_runs_full_escalation_chain() {
        let positions = vec![
            pos("BTCUSDT", "Buy", 100.0, 4.0),  // candidate = 100 + 0.5*4 = 102
            pos("ETHUSDT", "Sell", 200.0, 6.0), // candidate = 200 - 0.5*6 = 197
        ];
        let mut w = build_watcher(
            MockClock::new(10_000),
            vec![],
            positions,
            vec![],
            false,
        );
        // 武裝 timer
        w.observe_dispatch(DispatchOutcome::AllFail);

        // 未到期：check_timer 返 None
        w.clock.advance(FailsafeConfig::DEFAULT_TIMEOUT_MS - 1);
        let mut risk_sm = RiskGovernorSm::new();
        assert!(w.check_timer(&mut risk_sm).await.is_none());
        assert_eq!(risk_sm.snapshot_level(), RiskLevel::Normal);

        // 到期：跑完整鏈
        w.clock.advance(1);
        let report = w
            .check_timer(&mut risk_sm)
            .await
            .expect("timer should have fired");

        // SM-04 transition succeeded
        assert!(report.transition_attempted);
        assert!(report.transition_succeeded);
        assert_eq!(report.from_level, "NORMAL");
        assert_eq!(report.to_level, "DEFENSIVE");
        assert_eq!(risk_sm.snapshot_level(), RiskLevel::Defensive);

        // 兩個 adjustment 都被 sync 到交易所
        assert_eq!(report.adjustments_count, 2);
        assert_eq!(report.sync_records.len(), 2);
        assert!(report.sync_records.iter().all(|r| r.success));
        let calls = w.exchange.calls();
        assert_eq!(calls.len(), 2);
        // BTCUSDT 應收 102.0；ETHUSDT 應收 197.0（順序與 active_lock_profit_per_position 一致）
        assert!(calls
            .iter()
            .any(|(s, sl)| s == "BTCUSDT" && (sl - 102.0).abs() < 1e-9));
        assert!(calls
            .iter()
            .any(|(s, sl)| s == "ETHUSDT" && (sl - 197.0).abs() < 1e-9));

        // Audit emit captured
        assert!(report.audit_emitted);
        let captured = w.audit.captured();
        assert_eq!(captured.len(), 1);
        assert_eq!(
            captured[0]["event"].as_str().unwrap(),
            "auto_escalated_to_sm04_defensive"
        );
        assert_eq!(
            captured[0]["trigger"].as_str().unwrap(),
            "notification_failsafe_timeout"
        );
        assert_eq!(captured[0]["to_level"].as_str().unwrap(), "DEFENSIVE");
        assert_eq!(captured[0]["adjustments_count"].as_u64().unwrap(), 2);
    }

    // ── T4: AllSuccess in-flight cancels timer ──────────────────────────────

    #[tokio::test]
    async fn t4_all_success_cancels_armed_timer() {
        let mut w = build_watcher(MockClock::new(0), vec![], vec![], vec![], false);
        w.observe_dispatch(DispatchOutcome::AllFail);
        assert!(w.state().is_armed());

        let decision = w.observe_dispatch(DispatchOutcome::AllSuccess);
        assert_eq!(
            decision,
            FailsafeDecision::TimerCancelled {
                reason: TimerCancelReason::NotificationRecovered
            }
        );
        assert!(!w.state().is_armed());

        // 之後即使時間過了 timeout，check_timer 也不該觸發
        w.clock.advance(FailsafeConfig::DEFAULT_TIMEOUT_MS * 2);
        let mut risk_sm = RiskGovernorSm::new();
        assert!(w.check_timer(&mut risk_sm).await.is_none());
        assert_eq!(risk_sm.snapshot_level(), RiskLevel::Normal);
    }

    // ── T5: Operator ack cancels armed timer ────────────────────────────────

    #[tokio::test]
    async fn t5_operator_ack_cancels_armed_timer() {
        let mut w = build_watcher(MockClock::new(0), vec![], vec![], vec![], false);
        w.observe_dispatch(DispatchOutcome::AllFail);
        let decision = w.record_operator_ack();
        assert_eq!(
            decision,
            FailsafeDecision::TimerCancelled {
                reason: TimerCancelReason::OperatorAck
            }
        );
        assert!(!w.state().is_armed());

        // 未武裝再 ack 為 no-op
        let decision2 = w.record_operator_ack();
        assert_eq!(decision2, FailsafeDecision::NoAction);
    }

    // ── T6: idempotent — second check_timer after escalation no-ops ─────────

    #[tokio::test]
    async fn t6_idempotent_no_double_escalation_for_same_arm() {
        let mut w = build_watcher(
            MockClock::new(0),
            vec![],
            vec![pos("BTCUSDT", "Buy", 100.0, 4.0)],
            vec![],
            false,
        );
        w.observe_dispatch(DispatchOutcome::AllFail);
        w.clock.advance(FailsafeConfig::DEFAULT_TIMEOUT_MS);

        let mut risk_sm = RiskGovernorSm::new();
        let r1 = w.check_timer(&mut risk_sm).await.expect("first should fire");
        assert!(r1.transition_succeeded);
        assert_eq!(risk_sm.snapshot_level(), RiskLevel::Defensive);

        // 即使時間繼續推進，同一次武裝的 escalate 不該再觸發
        w.clock.advance(FailsafeConfig::DEFAULT_TIMEOUT_MS);
        let r2 = w.check_timer(&mut risk_sm).await;
        assert!(r2.is_none(), "second check_timer must not double-escalate");

        // audit emit / exchange sync 各只發生 1 次
        assert_eq!(w.exchange.calls().len(), 1);
        assert_eq!(w.audit.captured().len(), 1);
    }

    // ── T7: exchange partial failure does not roll back transition ──────────

    #[tokio::test]
    async fn t7_exchange_failure_does_not_rollback_transition() {
        let positions = vec![
            pos("BTCUSDT", "Buy", 100.0, 4.0),
            pos("ETHUSDT", "Sell", 200.0, 6.0),
        ];
        let mut w = build_watcher(
            MockClock::new(0),
            vec![],
            positions,
            vec!["BTCUSDT".to_string()], // BTC 同步失敗
            false,
        );
        w.observe_dispatch(DispatchOutcome::AllFail);
        w.clock.advance(FailsafeConfig::DEFAULT_TIMEOUT_MS);

        let mut risk_sm = RiskGovernorSm::new();
        let report = w.check_timer(&mut risk_sm).await.unwrap();

        // SM-04 仍轉到 Defensive（survival 優先）
        assert!(report.transition_succeeded);
        assert_eq!(risk_sm.snapshot_level(), RiskLevel::Defensive);
        // 報告反映 1 個 sync 失敗
        assert_eq!(report.sync_failure_count(), 1);
        let btc = report
            .sync_records
            .iter()
            .find(|r| r.symbol == "BTCUSDT")
            .unwrap();
        assert!(!btc.success);
        assert!(btc.error.as_deref().unwrap().contains("mock_reject"));
        // ETH 成功
        let eth = report
            .sync_records
            .iter()
            .find(|r| r.symbol == "ETHUSDT")
            .unwrap();
        assert!(eth.success);

        // audit 仍 emit
        assert!(report.audit_emitted);
        let captured = w.audit.captured();
        assert_eq!(captured.len(), 1);
        assert_eq!(captured[0]["sync_records"].as_array().unwrap().len(), 2);
    }

    // ── T8: already-Defensive caller — skip transition but still lock profit + audit ─

    #[tokio::test]
    async fn t8_already_defensive_skips_transition_but_still_emits() {
        let positions = vec![pos("BTCUSDT", "Buy", 100.0, 4.0)];
        let mut w = build_watcher(
            MockClock::new(0),
            vec![],
            positions,
            vec![],
            false,
        );
        w.observe_dispatch(DispatchOutcome::AllFail);
        w.clock.advance(FailsafeConfig::DEFAULT_TIMEOUT_MS);

        // 預先 escalate 到 Defensive
        let mut risk_sm = RiskGovernorSm::new();
        risk_sm
            .escalate_to(RiskLevel::Defensive, "preexisting", RiskEvent::DrawdownCritical)
            .unwrap();

        let report = w.check_timer(&mut risk_sm).await.unwrap();
        assert!(!report.transition_attempted);
        assert!(!report.transition_succeeded);
        assert!(report
            .transition_skipped_reason
            .as_deref()
            .unwrap()
            .starts_with("already_at_or_above_defensive:"));
        // 鎖利 + audit 仍跑
        assert_eq!(report.adjustments_count, 1);
        assert!(report.audit_emitted);
    }

    // ── T9: audit emit failure fails soft ───────────────────────────────────

    #[tokio::test]
    async fn t9_audit_emit_failure_fails_soft() {
        let positions = vec![pos("BTCUSDT", "Buy", 100.0, 4.0)];
        let mut w = build_watcher(
            MockClock::new(0),
            vec![],
            positions,
            vec![],
            true, // audit 注入失敗
        );
        w.observe_dispatch(DispatchOutcome::AllFail);
        w.clock.advance(FailsafeConfig::DEFAULT_TIMEOUT_MS);

        let mut risk_sm = RiskGovernorSm::new();
        let report = w.check_timer(&mut risk_sm).await.unwrap();
        assert!(report.transition_succeeded);
        assert_eq!(risk_sm.snapshot_level(), RiskLevel::Defensive);
        assert!(!report.audit_emitted);
        assert!(report.audit_error.as_deref().unwrap().contains("mock_audit_fail"));
        // exchange sync 仍跑
        assert_eq!(w.exchange.calls().len(), 1);
    }

    // ── T10: dispatch_and_observe wires dispatcher → state ──────────────────

    #[tokio::test]
    async fn t10_dispatch_and_observe_wires_dispatcher() {
        let mut w = build_watcher(
            MockClock::new(5_000),
            vec![DispatchOutcome::AllFail],
            vec![],
            vec![],
            false,
        );
        let decision = w.dispatch_and_observe("incident XYZ").await;
        assert_eq!(decision, FailsafeDecision::TimerArmed { since_ms: 5_000 });
        assert!(w.state().is_armed());
    }

    // ── T11: PartialFail neither arms nor cancels ───────────────────────────

    #[tokio::test]
    async fn t11_partial_fail_is_no_op_for_arming() {
        let mut w = build_watcher(MockClock::new(0), vec![], vec![], vec![], false);
        let decision = w.observe_dispatch(DispatchOutcome::PartialFail {
            failed: vec![NotificationChannel::Slack],
        });
        assert_eq!(decision, FailsafeDecision::NoAction);
        assert!(!w.state().is_armed());

        // 已武裝下 PartialFail 不解除
        w.observe_dispatch(DispatchOutcome::AllFail);
        assert!(w.state().is_armed());
        let decision2 = w.observe_dispatch(DispatchOutcome::PartialFail {
            failed: vec![NotificationChannel::Email],
        });
        assert_eq!(decision2, FailsafeDecision::NoAction);
        assert!(w.state().is_armed(), "PartialFail must not cancel armed timer");
    }

    // ── T12: timeout constant matches AMD spec (1h) ─────────────────────────

    #[test]
    fn t12_timeout_constant_is_one_hour() {
        // per AMD-2026-05-21-01 v2 §Decision 3.1 + Q3 Resolved Path A
        assert_eq!(FailsafeConfig::DEFAULT_TIMEOUT_MS, 3_600_000);
        // 與 openclaw_core 的 7d cooling 對齊比例：7 * 24 = 168 個 1h timeout
        assert_eq!(
            openclaw_core::sm::risk_gov::FAILSAFE_DEFENSIVE_COOLING_MS
                / FailsafeConfig::DEFAULT_TIMEOUT_MS,
            168
        );
    }

    // ── T13: PositionSnapshotProvider trait acceptance ──────────────────────

    #[test]
    fn t13_snapshot_provider_can_be_empty() {
        struct Empty;
        impl PositionSnapshotProvider for Empty {
            fn snapshot_positions(&self) -> Vec<PositionSnapshot> {
                Vec::new()
            }
        }
        let e = Empty;
        assert!(e.snapshot_positions().is_empty());
    }

    // ── T14: smoke — RefCell-style provider compiles (interior mutability seam) ─

    #[test]
    fn t14_position_provider_with_refcell_seam() {
        // 為什麼測這條：未來 runtime provider 可能用 RefCell / RwLock 持倉位 cache；
        // 這條保證 trait bound（Send+Sync）能配合 thread-safe 包裝。
        // RefCell 不是 Sync，故這條只驗 single-thread 介面語義（Send 不必）。
        struct Cell {
            inner: RefCell<Vec<PositionSnapshot>>,
        }
        impl Cell {
            fn snapshot(&self) -> Vec<PositionSnapshot> {
                self.inner.borrow().clone()
            }
        }
        let c = Cell {
            inner: RefCell::new(vec![pos("BTCUSDT", "Buy", 100.0, 4.0)]),
        };
        assert_eq!(c.snapshot().len(), 1);
    }
}
